from __future__ import annotations

import json
import logging
import os
import re
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

import httpx
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.flexible_pricing import query_flexible_pricing_catalog
from app.flexible_workflow import _normalize_product_name, _normalize_region, _to_float
from app.models import PriceComponent, QuoteWorkbook, RowQuoteProgress, RowQuoteSummary
from app.pricebook import HOURS_PER_MONTH, load_pricebook, pick_ecs_match


class TaskCancelledError(Exception):
    pass

logger = logging.getLogger(__name__)

# Concurrency configuration
ROW_QUOTE_MAAS_BATCH_SIZE = int(os.getenv("ROW_QUOTE_MAAS_BATCH_SIZE", "3"))
ROW_QUOTE_MAAS_CONCURRENCY = int(os.getenv("ROW_QUOTE_MAAS_CONCURRENCY", "6"))
ROW_QUOTE_MAAS_GLOBAL_CONCURRENCY = int(os.getenv("ROW_QUOTE_MAAS_GLOBAL_CONCURRENCY", "12"))
ROW_QUOTE_MAAS_TIMEOUT_SECONDS = int(os.getenv("ROW_QUOTE_MAAS_TIMEOUT_SECONDS", "120"))
ROW_QUOTE_MAAS_MAX_RETRIES = int(os.getenv("ROW_QUOTE_MAAS_MAX_RETRIES", "1"))

# Clamp per-task concurrency to global limit
ROW_QUOTE_MAAS_CONCURRENCY = min(ROW_QUOTE_MAAS_CONCURRENCY, ROW_QUOTE_MAAS_GLOBAL_CONCURRENCY)

# Process-level semaphore: limits total concurrent MaaS requests across all tasks
_maas_global_semaphore = threading.BoundedSemaphore(ROW_QUOTE_MAAS_GLOBAL_CONCURRENCY)

ROW_QUOTE_COLUMNS = [
    "华为云产品名",
    "华为云规格",
    "数量",
    "单价",
    "按需月价",
    "包月价",
    "RI 1Y月价",
    "报价状态",
    "映射说明",
    "置信度",
]

QUOTE_STATUS_QUOTED = "已报价"
QUOTE_STATUS_NON_QUOTE = "非报价行"
QUOTE_STATUS_MISSING_PRICE = "缺少价格"
QUOTE_STATUS_MANUAL = "需人工确认"

NETWORK_PRODUCTS = {"EIP", "NAT Gateway", "VPN", "Direct Connect as a Service", "ELB", "VPC"}
SECONDS_PER_MONTH = HOURS_PER_MONTH * 3600
GPU_KEYWORDS = (
    "gpu",
    "nvidia",
    "tesla",
    "l20",
    "h20",
    "t4",
    "a10",
    "a100",
    "h100",
    "v100",
    "p40",
    "p100",
)
CCI_PRIORITY_KEYWORDS = (
    "serverless",
    "cloud container instance",
    "cci",
    "pod-cpu",
    "pod cpu",
    "pod-memory",
    "pod memory",
    "vcpu-second",
    "cpu-second",
    "gib-second",
    "gb-second",
    "内存秒",
    "核秒",
    "gib/秒",
    "核/秒",
)
CCE_CLUSTER_KEYWORDS = (
    "cluster type",
    "cluster scale",
    "master nodes",
    "3 masters",
    "single",
    "50 nodes",
    "200 nodes",
    "1000 nodes",
    "2000 nodes",
    "standard/turbo",
)


def _row_debug_enabled() -> bool:
    value = os.getenv("ROW_QUOTE_DEBUG", "")
    return value.lower() in {"1", "true", "yes", "on"}


def _debug_log(event: str, **payload: Any) -> None:
    if not _row_debug_enabled():
        return
    logger.warning("ROW_QUOTE_DEBUG %s", json.dumps({"event": event, **payload}, ensure_ascii=False, default=str))


@dataclass
class RowCandidate:
    row_id: str
    sheet: str
    row_number: int
    cells: dict[str, str]
    local_cells: dict[str, str]
    inherited_cells: dict[str, str]
    header_context: list[dict[str, str]]
    merged_group_keys: tuple[str, ...] = ()


@dataclass
class RowMapping:
    row_id: str
    is_quote_row: bool
    huawei_product: str | None = None
    huawei_spec: str | None = None
    quantity: float | None = None
    rationale: str = ""
    confidence: float = 0


@dataclass(frozen=True)
class MergedCellInfo:
    key: str
    coord: str
    anchor_row: int
    anchor_col: int


@dataclass
class PriceResult:
    product_name: str | None = None
    spec: str | None = None
    quantity: float | None = None
    unit_price: float | None = None
    ondemand_monthly: float | None = None
    monthly_price: float | None = None
    ri_1y_monthly: float | None = None
    status: str = QUOTE_STATUS_NON_QUOTE
    rationale: str = ""
    confidence: float = 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_ascii_filename(filename: str, default: str = "huawei-row-quote") -> str:
    stem = re.sub(r"\.xlsx$", "", filename, flags=re.I).strip() or default
    normalized = unicodedata.normalize("NFKD", stem)
    ascii_stem = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_stem).strip("-._")
    return ascii_stem or default


def _cell_text(value: Any, limit: int = 160) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def _build_merged_metadata(ws: Any) -> tuple[dict[tuple[int, int], MergedCellInfo], dict[int, tuple[str, ...]]]:
    cell_lookup: dict[tuple[int, int], MergedCellInfo] = {}
    row_group_keys: dict[int, set[str]] = {}
    for merged_range in ws.merged_cells.ranges:
        min_col, min_row, max_col, max_row = merged_range.bounds
        info = MergedCellInfo(
            key=f"{ws.title}!{merged_range.coord}",
            coord=merged_range.coord,
            anchor_row=min_row,
            anchor_col=min_col,
        )
        for row_number in range(min_row, max_row + 1):
            for column_number in range(min_col, max_col + 1):
                cell_lookup[(row_number, column_number)] = info
            if max_row > min_row:
                row_group_keys.setdefault(row_number, set()).add(info.key)
    return cell_lookup, {row_number: tuple(sorted(keys)) for row_number, keys in row_group_keys.items()}


def _resolved_cell_text(
    ws: Any,
    row_number: int,
    column: int,
    merged_lookup: dict[tuple[int, int], MergedCellInfo],
) -> tuple[str, str]:
    raw_value = _cell_text(ws.cell(row=row_number, column=column).value)
    if raw_value:
        return raw_value, "local"
    info = merged_lookup.get((row_number, column))
    if info is None:
        return "", "empty"
    inherited_value = _cell_text(ws.cell(row=info.anchor_row, column=info.anchor_col).value)
    if inherited_value:
        if info.anchor_row != row_number or info.anchor_col != column:
            _debug_log(
                "merged_cell_expand",
                sheet=ws.title,
                row_number=row_number,
                column=get_column_letter(column),
                merged_range=info.coord,
                anchor_row=info.anchor_row,
                anchor_column=get_column_letter(info.anchor_col),
                value=inherited_value,
            )
        return inherited_value, "merged"
    return "", "empty"


def _row_cells(
    ws: Any,
    row_number: int,
    max_col: int,
    merged_lookup: dict[tuple[int, int], MergedCellInfo],
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    cells: dict[str, str] = {}
    local_cells: dict[str, str] = {}
    inherited_cells: dict[str, str] = {}
    for column in range(1, max_col + 1):
        value, source = _resolved_cell_text(ws, row_number, column, merged_lookup)
        if value:
            column_key = get_column_letter(column)
            cells[column_key] = value
            if source == "local":
                local_cells[column_key] = value
            elif source == "merged":
                inherited_cells[column_key] = value
    return cells, local_cells, inherited_cells


def _header_context(
    ws: Any,
    row_number: int,
    max_col: int,
    merged_lookup: dict[tuple[int, int], MergedCellInfo],
) -> list[dict[str, str]]:
    context: list[dict[str, str]] = []
    start = max(1, row_number - 5)
    for candidate_row in range(start, row_number):
        cells, local_cells, inherited_cells = _row_cells(ws, candidate_row, max_col, merged_lookup)
        if cells:
            context.append(
                {
                    "row_number": str(candidate_row),
                    "cells": json.dumps(cells, ensure_ascii=False),
                    "local_cells": json.dumps(local_cells, ensure_ascii=False),
                    "inherited_cells": json.dumps(inherited_cells, ensure_ascii=False),
                }
            )
    return context[-3:]


def _collect_rows(workbook: Any) -> tuple[list[RowCandidate], dict[str, int]]:
    rows: list[RowCandidate] = []
    original_widths: dict[str, int] = {}
    worksheets = workbook.worksheets[:1]
    for ws in worksheets:
        max_col = ws.max_column
        merged_lookup, merged_row_groups = _build_merged_metadata(ws)
        original_widths[ws.title] = max_col
        for row_number in range(2, ws.max_row + 1):
            cells, local_cells, inherited_cells = _row_cells(ws, row_number, max_col, merged_lookup)
            rows.append(
                RowCandidate(
                    row_id=f"{ws.title}!{row_number}",
                    sheet=ws.title,
                    row_number=row_number,
                    cells=cells,
                    local_cells=local_cells,
                    inherited_cells=inherited_cells,
                    header_context=_header_context(ws, row_number, max_col, merged_lookup),
                    merged_group_keys=merged_row_groups.get(row_number, ()),
                )
            )
    return rows, original_widths


def _joined_row(row: RowCandidate) -> str:
    return " ".join(row.cells.values())


def _joined_local_row(row: RowCandidate) -> str:
    return " ".join(row.local_cells.values())


def _joined_inherited_row(row: RowCandidate) -> str:
    return " ".join(row.inherited_cells.values())


def _joined_header_context(row: RowCandidate) -> str:
    parts: list[str] = []
    for item in row.header_context:
        try:
            cells = json.loads(item["cells"])
        except Exception:
            cells = {}
        parts.extend(str(value) for value in cells.values())
    return " ".join(parts)


def _format_quantity(value: float | int | None) -> str | None:
    if value is None:
        return None
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def _looks_like_header_or_group(row: RowCandidate) -> bool:
    text = _joined_row(row).lower()
    if not text:
        return True
    header_keywords = [
        "product",
        "service",
        "quantity",
        "qty",
        "region",
        "spec",
        "sku",
        "产品",
        "服务",
        "数量",
        "区域",
        "规格",
        "配置",
        "单价",
    ]
    keyword_hits = sum(1 for keyword in header_keywords if keyword.lower() in text)
    if keyword_hits >= 2 and not _normalize_product_name(text):
        return True
    if len(row.cells) <= 2 and any(marker in text for marker in ["小计", "合计", "subtotal", "total", "分类", "类别", "标题", "title"]):
        return True
    return False


def _extract_quantity(row: RowCandidate) -> float | None:
    for context_row in reversed(row.header_context):
        headers = json.loads(context_row["cells"])
        for column, header in headers.items():
            header_text = str(header).lower()
            if any(marker in header_text for marker in ["quantity", "qty", "数量", "实例数", "台数", "个数", "count"]):
                value = _to_float(row.cells.get(column))
                if value is not None:
                    return value
    text = _joined_row(row)
    explicit = re.search(r"(?:数量|qty|quantity|count|实例数|台数)\s*[:：]?\s*(\d+(?:\.\d+)?)", text, re.I)
    if explicit:
        return float(explicit.group(1))
    return None


def _extract_region(row: RowCandidate, fallback_region: str | None) -> str | None:
    text = _joined_row(row)
    for token in re.split(r"[\s,，;/|]+", text):
        region = _normalize_region(token)
        if region:
            return region
    return fallback_region


def _extract_sku(text: str) -> str | None:
    patterns = [
        r"\b[a-z]\d+n?\.(?:\d+xlarge|xlarge|large|\d+u)\.\d+g?\b",
        r"\bx\d\.\d+u\.\d+g\b",
        r"\bmysql\.[a-z0-9.]+\b",
        r"\bgp-?ssd\b",
        r"\bsas\b",
        r"\bcbr-basic\b",
        r"\beip-standard\b",
        r"\bnat-basic\b",
        r"\bvpn-basic\b",
        r"\bdcas-\d+g\b",
        r"\bcce-standard\b",
        r"\bsfs-turbo-standard\b",
    ]
    lowered = text.lower()
    for pattern in patterns:
        matched = re.search(pattern, lowered)
        if matched:
            return matched.group(0).replace("gpssd", "gp-ssd")
    return None


def _extract_compute_shape(text: str) -> tuple[int | None, float | None]:
    cpu_match = re.search(r"(\d+)\s*(?:vcpu|cpu|core|cores|核|c)", text, re.I)
    mem_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:gib|gb|g|内存)", text, re.I)
    cpu = int(float(cpu_match.group(1))) if cpu_match else None
    memory = float(mem_match.group(1)) if mem_match else None
    return cpu, memory


def _extract_cci_resource_kind(text: str) -> str | None:
    lowered = text.lower()
    if any(token in lowered for token in ["pod-cpu", "pod cpu", "pod-核", "pod cpu", "vcpu-second", "cpu-second", "核/秒", "核秒"]):
        return "cpu"
    if any(token in lowered for token in ["pod-memory", "pod memory", "pod-内存", "gib-second", "gb-second", "memory-second", "内存/秒", "内存秒", "gib/秒", "gb/秒"]):
        return "memory"
    return None


def _extract_capacity_gib(text: str) -> float | None:
    matched = re.search(r"(\d+(?:\.\d+)?)\s*(?:gib|gb|g|tb|t)", text, re.I)
    if not matched:
        return None
    value = float(matched.group(1))
    unit = matched.group(0).lower()
    return value * 1024 if "t" in unit and "gb" not in unit and "gib" not in unit else value


def _normalize_mapping_spec(product: str | None, spec_text: str | None, row_text: str) -> str | None:
    combined = " ".join(part for part in [spec_text or "", row_text] if part).strip()
    if not combined:
        return spec_text
    if product == "ECS":
        cpu, memory = _extract_compute_shape(combined)
        if cpu and memory:
            return f"{cpu}vCPU {_format_quantity(memory)}GB"
    if product == "CCI":
        cpu, memory = _extract_compute_shape(combined)
        resource_kind = _extract_cci_resource_kind(combined)
        if cpu and memory:
            return f"{cpu}vCPU {memory:g}GiB"
        if resource_kind == "cpu" and cpu:
            return f"{cpu}vCPU"
        if resource_kind == "memory" and memory:
            return f"{memory:g}GiB"
    if product in {"EVS", "SFS Turbo", "OBS"}:
        capacity = _extract_capacity_gib(combined)
        if capacity is not None:
            return f"{_format_quantity(capacity)}GB"
    return spec_text


def _contains_gpu_terms(*parts: str | None) -> bool:
    combined = " ".join(part for part in parts if part).lower()
    return any(keyword in combined for keyword in GPU_KEYWORDS)


def _should_force_cci(*parts: str | None) -> bool:
    combined = " ".join(part for part in parts if part).lower()
    return any(keyword in combined for keyword in CCI_PRIORITY_KEYWORDS)


def _should_force_cce_cluster(*parts: str | None) -> bool:
    combined = " ".join(part for part in parts if part).lower()
    return any(keyword in combined for keyword in CCE_CLUSTER_KEYWORDS)


def _apply_product_priority(row: RowCandidate, mapping: RowMapping) -> RowMapping:
    row_text = _joined_row(row)
    local_row_text = _joined_local_row(row)
    inherited_row_text = _joined_inherited_row(row)
    header_text = _joined_header_context(row)
    combined = " ".join([header_text, row_text, mapping.rationale or "", mapping.huawei_spec or ""])
    local_combined = " ".join([local_row_text, mapping.rationale or "", mapping.huawei_spec or ""])
    forced_product: str | None = None
    note: str | None = None
    if _should_force_cce_cluster(local_combined):
        forced_product = "CCE"
        note = "Local cluster pricing keywords force product mapping to CCE."
    elif _should_force_cci(local_combined):
        forced_product = "CCI"
        note = "Local Serverless/Pod keywords force product mapping to CCI."
    elif _should_force_cci(combined):
        forced_product = "CCI"
        note = "Serverless/Pod keywords from merged/header context force product mapping to CCI."
    elif _should_force_cce_cluster(combined):
        forced_product = "CCE"
        note = "Cluster pricing keywords from row/header context force product mapping to CCE."
    if not forced_product or forced_product == mapping.huawei_product:
        return mapping
    rationale = f"{mapping.rationale} {note}".strip()
    _debug_log(
        "product_priority_override",
        row_id=row.row_id,
        previous_product=mapping.huawei_product,
        forced_product=forced_product,
        local_row_text=local_row_text,
        inherited_row_text=inherited_row_text,
        header_text=header_text,
    )
    return RowMapping(
        row_id=mapping.row_id,
        is_quote_row=mapping.is_quote_row,
        huawei_product=forced_product,
        huawei_spec=_normalize_mapping_spec(forced_product, mapping.huawei_spec, combined),
        quantity=mapping.quantity,
        rationale=rationale,
        confidence=max(mapping.confidence, 0.82),
    )


def _fallback_mapping(row: RowCandidate) -> RowMapping:
    if _looks_like_header_or_group(row):
        mapping = RowMapping(row_id=row.row_id, is_quote_row=False, rationale="空行、标题行或分组行。", confidence=0.9)
        _debug_log("fallback_mapping", row_id=row.row_id, source="header_or_group", mapping=mapping.__dict__)
        return mapping
    text = _joined_row(row)
    local_text = _joined_local_row(row)
    header_text = _joined_header_context(row)
    local_combined = local_text.strip()
    combined_text = " ".join([header_text, text]).strip()
    if _should_force_cce_cluster(local_combined):
        quantity = _extract_quantity(row)
        rationale = "按行内集群管理关键词优先识别为 CCE。"
        if quantity is None:
            quantity = 1
            rationale = f"{rationale} 数量按 1 估算。"
        mapping = RowMapping(
            row_id=row.row_id,
            is_quote_row=True,
            huawei_product="CCE",
            huawei_spec=_normalize_mapping_spec("CCE", _extract_sku(text) or text[:120], combined_text),
            quantity=quantity,
            rationale=rationale,
            confidence=0.84,
        )
        _debug_log("fallback_mapping", row_id=row.row_id, source="local_cce_cluster_priority", mapping=mapping.__dict__)
        return mapping
    if _should_force_cci(local_combined):
        quantity = _extract_quantity(row)
        rationale = "按行内 serverless/pod 关键词优先识别为 CCI。"
        if quantity is None:
            quantity = 1
            rationale = f"{rationale} 数量按 1 估算。"
        mapping = RowMapping(
            row_id=row.row_id,
            is_quote_row=True,
            huawei_product="CCI",
            huawei_spec=_normalize_mapping_spec("CCI", _extract_sku(text) or text[:120], combined_text),
            quantity=quantity,
            rationale=rationale,
            confidence=0.88,
        )
        _debug_log("fallback_mapping", row_id=row.row_id, source="local_cci_priority", mapping=mapping.__dict__)
        return mapping
    if _should_force_cci(combined_text):
        quantity = _extract_quantity(row)
        rationale = "按 serverless/pod 关键词优先识别为 CCI。"
        if quantity is None:
            quantity = 1
            rationale = f"{rationale} 数量按 1 估算。"
        mapping = RowMapping(
            row_id=row.row_id,
            is_quote_row=True,
            huawei_product="CCI",
            huawei_spec=_normalize_mapping_spec("CCI", _extract_sku(text) or text[:120], combined_text),
            quantity=quantity,
            rationale=rationale,
            confidence=0.86,
        )
        _debug_log("fallback_mapping", row_id=row.row_id, source="cci_priority", mapping=mapping.__dict__)
        return mapping
    if _should_force_cce_cluster(combined_text):
        quantity = _extract_quantity(row)
        rationale = "按集群管理关键词优先识别为 CCE。"
        if quantity is None:
            quantity = 1
            rationale = f"{rationale} 数量按 1 估算。"
        mapping = RowMapping(
            row_id=row.row_id,
            is_quote_row=True,
            huawei_product="CCE",
            huawei_spec=_normalize_mapping_spec("CCE", _extract_sku(text) or text[:120], combined_text),
            quantity=quantity,
            rationale=rationale,
            confidence=0.82,
        )
        _debug_log("fallback_mapping", row_id=row.row_id, source="cce_cluster_priority", mapping=mapping.__dict__)
        return mapping
    product = _normalize_product_name(text)
    if product:
        quantity = _extract_quantity(row)
        rationale = "按本地关键词识别为可报价行。"
        if quantity is None:
            quantity = 1
            rationale = f"{rationale} 数量按 1 估算。"
        mapping = RowMapping(
            row_id=row.row_id,
            is_quote_row=True,
            huawei_product=product,
            huawei_spec=_normalize_mapping_spec(product, _extract_sku(text) or text[:120], text),
            quantity=quantity,
            rationale=rationale,
            confidence=0.72,
        )
        _debug_log("fallback_mapping", row_id=row.row_id, source="keyword_match", mapping=mapping.__dict__)
        return mapping
    mapping = RowMapping(row_id=row.row_id, is_quote_row=True, rationale="行内有内容但无法自动匹配华为云产品。", confidence=0.25)
    _debug_log("fallback_mapping", row_id=row.row_id, source="unmatched", mapping=mapping.__dict__)
    return mapping


def _has_strong_local_product_signal(row: RowCandidate, anchor_product: str) -> bool:
    local_text = _joined_local_row(row)
    if not local_text:
        return False
    if _should_force_cce_cluster(local_text) and anchor_product != "CCE":
        return True
    if _should_force_cci(local_text) and anchor_product != "CCI":
        return True
    local_product = _normalize_product_name(local_text)
    return bool(local_product and local_product != anchor_product)


@dataclass
class AnchorPlan:
    group_anchor: dict[str, str] = field(default_factory=dict)
    row_dependencies: dict[str, tuple[str, ...]] = field(default_factory=dict)


def build_anchor_plan(rows: list[RowCandidate]) -> AnchorPlan:
    plan = AnchorPlan()
    grouped_rows: dict[str, list[RowCandidate]] = {}
    for row in rows:
        for group_key in row.merged_group_keys:
            grouped_rows.setdefault(group_key, []).append(row)
    for group_key, members in grouped_rows.items():
        anchor_row = next((row for row in members if row.cells and not _looks_like_header_or_group(row)), None)
        if anchor_row is None:
            continue
        plan.group_anchor[group_key] = anchor_row.row_id
        for row in members:
            if row.row_id != anchor_row.row_id:
                deps = plan.row_dependencies.get(row.row_id, ())
                if anchor_row.row_id not in deps:
                    plan.row_dependencies[row.row_id] = deps + (anchor_row.row_id,)
    return plan


def resolve_final_mapping(
    row: RowCandidate,
    raw_mapping: RowMapping | None,
    raw_mappings: dict[str, RowMapping],
    anchor_plan: AnchorPlan,
) -> RowMapping | None:
    if raw_mapping is None:
        return None
    deps = anchor_plan.row_dependencies.get(row.row_id, ())
    for dep_id in deps:
        if dep_id not in raw_mappings:
            return None
    if not deps:
        return _apply_product_priority(row, raw_mapping)
    anchor_id = deps[0]
    anchor_mapping = raw_mappings.get(anchor_id)
    if (
        not anchor_mapping
        or not anchor_mapping.is_quote_row
        or not anchor_mapping.huawei_product
        or anchor_mapping.confidence < 0.75
    ):
        return _apply_product_priority(row, raw_mapping)
    if _has_strong_local_product_signal(row, anchor_mapping.huawei_product):
        return _apply_product_priority(row, raw_mapping)
    if raw_mapping.huawei_product and raw_mapping.confidence >= 0.75:
        return _apply_product_priority(row, raw_mapping)
    if raw_mapping.huawei_product == anchor_mapping.huawei_product:
        return _apply_product_priority(row, raw_mapping)
    inherited = RowMapping(
        row_id=raw_mapping.row_id,
        is_quote_row=raw_mapping.is_quote_row,
        huawei_product=anchor_mapping.huawei_product,
        huawei_spec=raw_mapping.huawei_spec,
        quantity=raw_mapping.quantity,
        rationale=f"{raw_mapping.rationale} Inherited product classification from merged-row anchor {anchor_id}.".strip(),
        confidence=max(raw_mapping.confidence, anchor_mapping.confidence),
    )
    return _apply_product_priority(row, inherited)


def _apply_anchor_inheritance(rows: list[RowCandidate], mappings: dict[str, RowMapping]) -> dict[str, RowMapping]:
    if not mappings:
        return mappings
    threshold = 0.75
    rows_by_id = {row.row_id: row for row in rows}
    grouped_rows: dict[str, list[RowCandidate]] = {}
    for row in rows:
        for group_key in row.merged_group_keys:
            grouped_rows.setdefault(group_key, []).append(row)
    for group_key, members in grouped_rows.items():
        anchor_row = next((row for row in members if row.cells and not _looks_like_header_or_group(row)), None)
        if anchor_row is None:
            _debug_log("anchor_skip", group_key=group_key, reason="no_non_header_anchor")
            continue
        anchor_mapping = mappings.get(anchor_row.row_id)
        if (
            not anchor_mapping
            or not anchor_mapping.is_quote_row
            or not anchor_mapping.huawei_product
            or anchor_mapping.confidence < threshold
        ):
            _debug_log(
                "anchor_skip",
                group_key=group_key,
                anchor_row_id=anchor_row.row_id,
                reason="anchor_mapping_not_eligible",
                anchor_mapping=anchor_mapping.__dict__ if anchor_mapping else None,
            )
            continue
        _debug_log("anchor_selected", group_key=group_key, anchor_row_id=anchor_row.row_id, anchor_mapping=anchor_mapping.__dict__)
        for row in members:
            if row.row_id == anchor_row.row_id:
                continue
            mapping = mappings.get(row.row_id)
            if not mapping or not mapping.is_quote_row:
                _debug_log(
                    "anchor_child_decision",
                    group_key=group_key,
                    row_id=row.row_id,
                    decision="skip_non_quote_or_missing_mapping",
                    mapping=mapping.__dict__ if mapping else None,
                )
                continue
            if _has_strong_local_product_signal(row, anchor_mapping.huawei_product):
                _debug_log(
                    "anchor_child_decision",
                    group_key=group_key,
                    row_id=row.row_id,
                    decision="explicit_override",
                    local_row_text=_joined_local_row(row),
                    anchor_product=anchor_mapping.huawei_product,
                    mapping=mapping.__dict__,
                )
                continue
            if mapping.huawei_product and mapping.confidence >= threshold:
                _debug_log(
                    "anchor_child_decision",
                    group_key=group_key,
                    row_id=row.row_id,
                    decision="keep_local_mapping",
                    anchor_product=anchor_mapping.huawei_product,
                    mapping=mapping.__dict__,
                )
                continue
            if mapping.huawei_product == anchor_mapping.huawei_product:
                _debug_log(
                    "anchor_child_decision",
                    group_key=group_key,
                    row_id=row.row_id,
                    decision="local_same_as_anchor",
                    anchor_product=anchor_mapping.huawei_product,
                    mapping=mapping.__dict__,
                )
                continue
            inherited_mapping = RowMapping(
                row_id=mapping.row_id,
                is_quote_row=mapping.is_quote_row,
                huawei_product=anchor_mapping.huawei_product,
                huawei_spec=mapping.huawei_spec,
                quantity=mapping.quantity,
                rationale=f"{mapping.rationale} Inherited product classification from merged-row anchor {anchor_row.row_id}.".strip(),
                confidence=max(mapping.confidence, anchor_mapping.confidence),
            )
            mappings[row.row_id] = _apply_product_priority(rows_by_id[row.row_id], inherited_mapping)
            _debug_log(
                "anchor_child_decision",
                group_key=group_key,
                row_id=row.row_id,
                decision="anchor_inheritance",
                anchor_row_id=anchor_row.row_id,
                anchor_product=anchor_mapping.huawei_product,
                mapping=mappings[row.row_id].__dict__,
            )
    return mappings


def _maas_map_rows(rows: list[RowCandidate], quote_context: dict[str, Any], mapping_progress_callback: Any = None, cancel_check: Any = None) -> dict[str, RowMapping]:
    api_key = os.getenv("HUAWEI_MAAS_API_KEY")
    base_url = os.getenv("HUAWEI_MAAS_BASE_URL")
    model = os.getenv("HUAWEI_MAAS_MODEL")
    if not api_key or not base_url or not model:
        return {}

    if callable(cancel_check) and cancel_check():
        return {}

    BATCH_SIZE = ROW_QUOTE_MAAS_BATCH_SIZE
    MAX_RETRIES = ROW_QUOTE_MAAS_MAX_RETRIES
    TIMEOUT = ROW_QUOTE_MAAS_TIMEOUT_SECONDS
    CONCURRENCY = ROW_QUOTE_MAAS_CONCURRENCY
    SUPPORTED_PRODUCTS = [
        "ECS", "EVS", "CBR", "EIP", "CCE", "CCI", "SFS Turbo", "NAT Gateway", "VPN",
        "Direct Connect as a Service", "RDS", "DDS", "DWS", "OBS", "ELB", "WAF",
        "HSS", "VPC", "Workspace", "DRS", "CSS", "DLI", "ModelArts", "FunctionGraph", "GaussDB",
    ]

    SYSTEM_PROMPT = (
        "Return JSON only with rows[]. For each input row, classify is_quote_row. "
        "For quote rows provide huawei_product, huawei_spec, quantity if visible, "
        "rationale, confidence. Do not calculate prices. Mark empty/title/group rows "
        "as is_quote_row=false. Serverless container pricing rows must map to CCI, not CCE. "
        "Rows containing Serverless, Pod-CPU, Pod-Memory, vCPU-second, GiB-second, 核/秒, 内存/秒 "
        "should map to CCI. CCE is for cluster management pricing such as Cluster Type, "
        "Cluster Scale, Master Nodes, 50/200/1000/2000 nodes, or 3 Masters. "
        "Use quote_context.customer_notes as an explicit instruction from the user when interpreting ambiguous rows and choosing practical Huawei Cloud mappings."
    )

    batches: list[tuple[int, list[RowCandidate]]] = [
        (start, rows[start : start + BATCH_SIZE]) for start in range(0, len(rows), BATCH_SIZE)
    ]

    def _run_batch(start: int, batch: list[RowCandidate]) -> tuple[int, dict[str, RowMapping]]:
        if callable(cancel_check) and cancel_check():
            return start, {}
        batch_rows = {
            row.row_id: {
                "sheet": row.sheet,
                "row_number": row.row_number,
                "cells": row.cells,
                "local_cells": row.local_cells,
                "inherited_cells": row.inherited_cells,
                "header_context": row.header_context,
                "merged_group_keys": row.merged_group_keys,
            }
            for row in batch
        }
        prompt = {
            "quote_context": quote_context,
            "supported_products": SUPPORTED_PRODUCTS,
            "rows": [
                {
                    "row_id": row.row_id,
                    "sheet": row.sheet,
                    "row_number": row.row_number,
                    "header_context": row.header_context,
                    "cells": row.cells,
                }
                for row in batch
            ],
        }
        _debug_log("maas_request", model=model, batch_start=start, prompt=prompt)
        payload = None
        with _maas_global_semaphore:
            for attempt in range(1 + MAX_RETRIES):
                if callable(cancel_check) and cancel_check():
                    return start, {}
                try:
                    with httpx.Client(timeout=TIMEOUT) as client:
                        response = client.post(
                            f"{base_url.rstrip('/')}/chat/completions",
                            headers={"Authorization": f"Bearer {api_key}"},
                            json={
                                "model": model,
                                "temperature": 0.1,
                                "response_format": {"type": "json_object"},
                                "messages": [
                                    {"role": "system", "content": SYSTEM_PROMPT},
                                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                                ],
                            },
                        )
                        response.raise_for_status()
                        content = response.json()["choices"][0]["message"]["content"]
                        _debug_log("maas_response_raw", model=model, batch_start=start, attempt=attempt + 1, response=content)
                        payload = json.loads(content)
                        break
                except Exception as exc:
                    logger.warning("Row quote MaaS batch mapping attempt %d failed: %s", attempt + 1, exc)
                    _debug_log("maas_response_error", model=model, batch_start=start, attempt=attempt + 1, error=str(exc))

        if callable(cancel_check) and cancel_check():
            return start, {}
        result: dict[str, RowMapping] = {}
        if payload:
            for item in payload.get("rows", []):
                row_id = str(item.get("row_id") or "")
                if not row_id:
                    continue
                product = item.get("huawei_product") or item.get("product_name")
                product = _normalize_product_name(str(product)) if product else None
                source_row = batch_rows.get(row_id)
                row_text = " ".join(source_row["cells"].values()) if source_row else ""
                mapping = RowMapping(
                    row_id=row_id,
                    is_quote_row=bool(item.get("is_quote_row")),
                    huawei_product=product,
                    huawei_spec=_normalize_mapping_spec(product, str(item.get("huawei_spec") or item.get("spec") or "") or None, row_text),
                    quantity=_to_float(item.get("quantity")),
                    rationale=str(item.get("rationale") or item.get("mapping_note") or ""),
                    confidence=max(0, min(1, _to_float(item.get("confidence")) or 0)),
                )
                if source_row:
                    mapping = _apply_product_priority(
                        RowCandidate(
                            row_id=row_id,
                            sheet=str(source_row["sheet"]),
                            row_number=int(source_row["row_number"]),
                            cells=dict(source_row["cells"]),
                            local_cells=dict(source_row["local_cells"]),
                            inherited_cells=dict(source_row["inherited_cells"]),
                            header_context=list(source_row["header_context"]),
                            merged_group_keys=tuple(source_row["merged_group_keys"]),
                        ),
                        mapping,
                    )
                result[row_id] = mapping
                _debug_log("maas_mapping", row_id=row_id, mapping=mapping.__dict__, source_row=source_row)
        return start, result

    mapped: dict[str, RowMapping] = {}
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = {executor.submit(_run_batch, start, batch): start for start, batch in batches}
        for future in as_completed(futures):
            if callable(cancel_check) and cancel_check():
                for f in futures:
                    f.cancel()
                break
            start, batch_mappings = future.result()
            if callable(cancel_check) and cancel_check():
                for f in futures:
                    f.cancel()
                break
            mapped.update(batch_mappings)
            if callable(mapping_progress_callback):
                mapping_progress_callback(min(start + BATCH_SIZE, len(rows)), len(rows))
    return mapped


def _extract_cce_cluster_shape(text: str) -> tuple[str | None, str | None]:
    lowered = text.lower()
    scale_match = re.search(r"\b(50|200|1000|2000)\s*nodes?\b", lowered)
    master_nodes = None
    if "3 masters" in lowered or "3 master" in lowered:
        master_nodes = "3-masters"
    elif "single" in lowered:
        master_nodes = "single"
    scale = scale_match.group(1) if scale_match else None
    return scale, master_nodes


def _price_cce(mapping: RowMapping, region: str, row_text: str, quantity: float) -> PriceResult:
    spec_text = " ".join([mapping.huawei_spec or "", mapping.rationale or "", row_text])
    scale, master_nodes = _extract_cce_cluster_shape(spec_text)
    candidates = _confirmed_flexible_candidates("CCE", region, spec_text)
    selected = None
    if scale and master_nodes:
        expected_sku = f"cce-standard-turbo-{scale}-{master_nodes}"
        selected = next((item for item in candidates if (item.sku or "").lower() == expected_sku), None)
    if not selected:
        selected = next((item for item in candidates if item.billing_mode == "monthly"), None)
    if not selected:
        return PriceResult(
            product_name="CCE",
            spec=mapping.huawei_spec,
            quantity=quantity,
            status=QUOTE_STATUS_MISSING_PRICE,
            rationale="CCE 管理节点价格未匹配到已确认本地价格。",
            confidence=mapping.confidence,
        )
    management_monthly = float(selected.price or 0) if selected.billing_mode == "monthly" else 0.0
    management_hourly = 0.0
    if selected.sku:
        hourly_item = next(
            (
                item for item in query_flexible_pricing_catalog(product="CCE", region=region)
                if item.confirmed and item.status == "confirmed" and item.price is not None
                and item.sku == selected.sku and item.billing_mode == "hourly"
            ),
            None,
        )
        if hourly_item:
            management_hourly = float(hourly_item.price or 0)
        yearly_item = next(
            (
                item for item in query_flexible_pricing_catalog(product="CCE", region=region)
                if item.confirmed and item.status == "confirmed" and item.price is not None
                and item.sku == selected.sku and item.billing_mode == "yearly"
            ),
            None,
        )
    else:
        yearly_item = None
    worker_count = quantity if quantity > 0 else 1
    ecs_result = _price_ecs(
        RowMapping(
            row_id=mapping.row_id,
            is_quote_row=True,
            huawei_product="ECS",
            huawei_spec=mapping.huawei_spec,
            quantity=worker_count,
            rationale="CCE worker nodes priced using ECS rates.",
            confidence=mapping.confidence,
        ),
        region,
        row_text,
        worker_count,
    )
    if ecs_result.status not in {QUOTE_STATUS_QUOTED, QUOTE_STATUS_MISSING_PRICE}:
        ecs_result = _price_ecs(mapping, region, row_text, worker_count)
    total_ondemand = round((management_hourly * HOURS_PER_MONTH) + (ecs_result.ondemand_monthly or 0), 4)
    total_monthly = round(management_monthly + (ecs_result.monthly_price or 0), 4)
    total_ri = None
    if yearly_item is not None:
        total_ri = round(float(yearly_item.price or 0) / 12 + (ecs_result.ri_1y_monthly or 0), 4)
    rationale = (
        f"{mapping.rationale} CCE control plane is charged once using the local CCE management price, "
        "and worker nodes are priced separately using ECS rates."
    ).strip()
    spec = selected.sku or mapping.huawei_spec or "CCE"
    if ecs_result.spec:
        spec = f"control-plane {spec} + worker {ecs_result.spec}"
    return PriceResult(
        product_name="CCE",
        spec=spec,
        quantity=worker_count,
        unit_price=round(management_hourly, 6) if management_hourly else ecs_result.unit_price,
        ondemand_monthly=total_ondemand,
        monthly_price=total_monthly,
        ri_1y_monthly=total_ri,
        status=QUOTE_STATUS_QUOTED,
        rationale=rationale,
        confidence=mapping.confidence,
    )


def _confirmed_flexible_candidates(product: str, region: str, spec_text: str | None) -> list[PriceComponent]:
    candidates = [
        item
        for item in query_flexible_pricing_catalog(product=product, region=region)
        if item.confirmed and item.status == "confirmed" and item.price is not None
    ]
    spec = (spec_text or "").lower()
    sku = _extract_sku(spec)
    if sku:
        narrowed = [item for item in candidates if (item.sku or "").lower() == sku]
        if narrowed:
            return narrowed
    if spec:
        narrowed = [
            item
            for item in candidates
            if (item.sku and item.sku.lower() in spec) or (item.tier and item.tier.lower() in spec)
        ]
        if narrowed:
            return narrowed
    return candidates


def _price_ecs(mapping: RowMapping, region: str, row_text: str, quantity: float) -> PriceResult:
    pricebook = load_pricebook()
    region_catalog = pricebook["pricingCatalog"].get(region)
    if not region_catalog:
        return PriceResult(status=QUOTE_STATUS_MISSING_PRICE, rationale="本地区没有本地 ECS 价格。", confidence=mapping.confidence)
    spec_text = " ".join([mapping.huawei_spec or "", row_text])
    sku = _extract_sku(spec_text)
    match = None
    if sku:
        match = next((item for item in region_catalog["ecs"] if str(item.get("spec", "")).lower() == sku.lower()), None)
    if not match:
        cpu, memory = _extract_compute_shape(spec_text)
        if cpu and memory:
            match = pick_ecs_match(region_catalog, cpu, memory)
    if not match:
        return PriceResult(
            product_name="ECS",
            spec=mapping.huawei_spec,
            quantity=quantity,
            status=QUOTE_STATUS_MISSING_PRICE,
            rationale="未能按 ECS 规格匹配本地价格。",
            confidence=mapping.confidence,
        )
    unit_price = round(float(match["hourlyUsd"]), 6)
    ondemand = round(unit_price * HOURS_PER_MONTH * quantity, 4)
    monthly = round(float(match.get("monthlyUsd") or unit_price * HOURS_PER_MONTH) * quantity, 4)
    ri = round(float(match.get("ri1YearMonthlyUsd") or 0) * quantity, 4)
    return PriceResult(
        product_name="ECS",
        spec=str(match["spec"]),
        quantity=quantity,
        unit_price=unit_price,
        ondemand_monthly=ondemand,
        monthly_price=monthly,
        ri_1y_monthly=ri,
        status=QUOTE_STATUS_QUOTED,
        rationale=mapping.rationale or "ECS 规格按本地价格库匹配。",
        confidence=mapping.confidence,
    )


def _price_evs(mapping: RowMapping, region: str, row_text: str, quantity: float) -> PriceResult:
    region_catalog = load_pricebook()["pricingCatalog"].get(region)
    if not region_catalog:
        return PriceResult(product_name="EVS", quantity=quantity, status=QUOTE_STATUS_MISSING_PRICE, rationale="本地区没有本地 EVS 价格。", confidence=mapping.confidence)
    spec_text = " ".join([mapping.huawei_spec or "", row_text])
    key = "sas" if re.search(r"\bsas\b|high\s*i/o|高\s*i/o", spec_text, re.I) else "gpssd"
    capacity = _extract_capacity_gib(spec_text)
    if capacity is None:
        return PriceResult(
            product_name="EVS",
            spec=mapping.huawei_spec,
            quantity=quantity,
            status=QUOTE_STATUS_MISSING_PRICE,
            rationale="EVS 缺少容量，无法计算 GB 月价。",
            confidence=mapping.confidence,
        )
    item = next((price for price in region_catalog["evs"] if price["key"] == key), None)
    if not item:
        return PriceResult(product_name="EVS", quantity=quantity, status=QUOTE_STATUS_MISSING_PRICE, rationale="EVS 类型未覆盖。", confidence=mapping.confidence)
    unit_price = round(float(item["hourlyUsdPerGb"]), 6)
    ondemand = round(unit_price * HOURS_PER_MONTH * capacity * quantity, 4)
    monthly = round(float(item["monthlyUsdPerGb"]) * capacity * quantity, 4)
    return PriceResult(
        product_name="EVS",
        spec=f"{item['resourceSpecCode']} {capacity:g}GB",
        quantity=quantity,
        unit_price=unit_price,
        ondemand_monthly=ondemand,
        monthly_price=monthly,
        ri_1y_monthly=None,
        status=QUOTE_STATUS_QUOTED,
        rationale=mapping.rationale or "EVS 容量按本地价格库计算。",
        confidence=mapping.confidence,
    )


def _price_catalog_product(mapping: RowMapping, region: str, quantity: float) -> PriceResult:
    product = mapping.huawei_product
    if not product:
        return PriceResult(quantity=quantity, status=QUOTE_STATUS_MANUAL, rationale="无法识别华为云产品。", confidence=mapping.confidence)
    candidates = _confirmed_flexible_candidates(product, region, mapping.huawei_spec)
    if not candidates:
        return PriceResult(
            product_name=product,
            spec=mapping.huawei_spec,
            quantity=quantity,
            status=QUOTE_STATUS_MISSING_PRICE,
            rationale="产品或规格未匹配到已确认本地价格。",
            confidence=mapping.confidence,
        )
    item = candidates[0]
    price = float(item.price or 0)
    return PriceResult(
        product_name=product,
        spec=item.sku or item.tier or mapping.huawei_spec,
        quantity=quantity,
        unit_price=round(price, 4),
        ondemand_monthly=round(price * quantity, 4),
        monthly_price=round(price * quantity, 4),
        ri_1y_monthly=None,
        status=QUOTE_STATUS_QUOTED,
        rationale=mapping.rationale or "按本地 flexible 价格目录匹配。",
        confidence=mapping.confidence,
    )


def _price_cci(mapping: RowMapping, region: str, quantity: float, row_text: str = "") -> PriceResult:
    spec_text = mapping.huawei_spec or ""
    cpu, memory = _extract_compute_shape(spec_text)
    resource_kind = _extract_cci_resource_kind(" ".join(part for part in [spec_text, row_text, mapping.rationale] if part))
    if not cpu or not memory:
        if resource_kind == "cpu":
            cpu = quantity if quantity > 0 else cpu
        elif resource_kind == "memory":
            memory = quantity if quantity > 0 else memory
    candidates = _confirmed_flexible_candidates("CCI", region, mapping.huawei_spec)
    cpu_item = next((item for item in candidates if (item.tier or "").lower() == "cpu"), None)
    memory_item = next((item for item in candidates if (item.tier or "").lower() == "memory"), None)
    if resource_kind == "cpu" and not cpu_item:
        return PriceResult(
            product_name="CCI",
            spec=mapping.huawei_spec,
            quantity=quantity,
            status=QUOTE_STATUS_MISSING_PRICE,
            rationale="CCI CPU 未匹配到已确认本地价格。",
            confidence=mapping.confidence,
        )
    if resource_kind == "memory" and not memory_item:
        return PriceResult(
            product_name="CCI",
            spec=mapping.huawei_spec,
            quantity=quantity,
            status=QUOTE_STATUS_MISSING_PRICE,
            rationale="CCI Memory 未匹配到已确认本地价格。",
            confidence=mapping.confidence,
        )
    if not resource_kind and (not cpu_item or not memory_item):
        return PriceResult(
            product_name="CCI",
            spec=mapping.huawei_spec,
            quantity=quantity,
            status=QUOTE_STATUS_MISSING_PRICE,
            rationale="CCI 产品或规格未匹配到已确认本地价格。",
            confidence=mapping.confidence,
        )
    if resource_kind == "cpu":
        if not cpu:
            return PriceResult(
                product_name="CCI",
                spec=mapping.huawei_spec,
                quantity=quantity,
                status=QUOTE_STATUS_MANUAL,
                rationale="CCI CPU 行需要可识别的 vCPU 数量。",
                confidence=mapping.confidence,
            )
        cpu_unit_price = float(cpu_item.price or 0)
        monthly = cpu_unit_price * cpu * SECONDS_PER_MONTH
        unit_price = cpu_unit_price * 3600
        spec = f"{cpu:g}vCPU"
        rationale = mapping.rationale or "按本地 CCI CPU 秒级价格目录估算。"
        return PriceResult(
            product_name="CCI",
            spec=spec,
            quantity=cpu,
            unit_price=round(unit_price, 6),
            ondemand_monthly=round(monthly, 4),
            monthly_price=round(monthly, 4),
            ri_1y_monthly=None,
            status=QUOTE_STATUS_QUOTED,
            rationale=rationale,
            confidence=mapping.confidence,
        )
    if resource_kind == "memory":
        if not memory:
            return PriceResult(
                product_name="CCI",
                spec=mapping.huawei_spec,
                quantity=quantity,
                status=QUOTE_STATUS_MANUAL,
                rationale="CCI Memory 行需要可识别的 GiB 数量。",
                confidence=mapping.confidence,
            )
        memory_unit_price = float(memory_item.price or 0)
        monthly = memory_unit_price * memory * SECONDS_PER_MONTH
        unit_price = memory_unit_price * 3600
        spec = f"{memory:g}GiB"
        rationale = mapping.rationale or "按本地 CCI Memory 秒级价格目录估算。"
        return PriceResult(
            product_name="CCI",
            spec=spec,
            quantity=memory,
            unit_price=round(unit_price, 6),
            ondemand_monthly=round(monthly, 4),
            monthly_price=round(monthly, 4),
            ri_1y_monthly=None,
            status=QUOTE_STATUS_QUOTED,
            rationale=rationale,
            confidence=mapping.confidence,
        )
    if not cpu or not memory:
        return PriceResult(
            product_name="CCI",
            spec=mapping.huawei_spec,
            quantity=quantity,
            status=QUOTE_STATUS_MANUAL,
            rationale="CCI 需要可识别的 vCPU 和内存规格。",
            confidence=mapping.confidence,
        )
    cpu_unit_price = float(cpu_item.price or 0)
    memory_unit_price = float(memory_item.price or 0)
    monthly = (cpu_unit_price * cpu + memory_unit_price * memory) * SECONDS_PER_MONTH * quantity
    unit_price = (cpu_unit_price * cpu + memory_unit_price * memory) * 3600
    return PriceResult(
        product_name="CCI",
        spec=f"{int(cpu)}vCPU {memory:g}GiB",
        quantity=quantity,
        unit_price=round(unit_price, 6),
        ondemand_monthly=round(monthly, 4),
        monthly_price=round(monthly, 4),
        ri_1y_monthly=None,
        status=QUOTE_STATUS_QUOTED,
        rationale=mapping.rationale or "按本地 CCI CPU/Memory 秒级价格目录估算。",
        confidence=mapping.confidence,
    )


def _price_row(mapping: RowMapping, row: RowCandidate, quote_context: dict[str, Any]) -> PriceResult:
    _debug_log("price_input", row_id=row.row_id, mapping=mapping.__dict__, row_cells=row.cells, quote_context=quote_context)
    if not mapping.is_quote_row:
        result = PriceResult(status=QUOTE_STATUS_NON_QUOTE, rationale=mapping.rationale, confidence=mapping.confidence)
        _debug_log("price_result", row_id=row.row_id, result=result.__dict__)
        return result
    row_text = _joined_row(row)
    if _contains_gpu_terms(row_text, mapping.huawei_spec, mapping.rationale):
        result = PriceResult(
            product_name=mapping.huawei_product,
            spec=mapping.huawei_spec,
            quantity=mapping.quantity,
            status=QUOTE_STATUS_MANUAL,
            rationale="LATAM regions currently do not provide GPU quoting in this tool. Manual review required.",
            confidence=mapping.confidence,
        )
        _debug_log("price_result", row_id=row.row_id, result=result.__dict__)
        return result
    if not mapping.huawei_product:
        result = PriceResult(status=QUOTE_STATUS_MANUAL, rationale=mapping.rationale or "无法识别华为云产品。", confidence=mapping.confidence)
        _debug_log("price_result", row_id=row.row_id, result=result.__dict__)
        return result
    region = _extract_region(row, quote_context.get("region"))
    if not region:
        result = PriceResult(
            product_name=mapping.huawei_product,
            spec=mapping.huawei_spec,
            quantity=mapping.quantity,
            status=QUOTE_STATUS_MANUAL,
            rationale="缺少报价区域。",
            confidence=mapping.confidence,
        )
        _debug_log("price_result", row_id=row.row_id, result=result.__dict__)
        return result
    quantity = mapping.quantity
    rationale = mapping.rationale
    if quantity is None or quantity <= 0:
        quantity = 1
        rationale = f"{rationale} 数量按 1 估算。".strip()
        mapping = RowMapping(
            row_id=mapping.row_id,
            is_quote_row=mapping.is_quote_row,
            huawei_product=mapping.huawei_product,
            huawei_spec=mapping.huawei_spec,
            quantity=quantity,
            rationale=rationale,
            confidence=mapping.confidence,
        )
    if mapping.huawei_product == "ECS":
        result = _price_ecs(mapping, region, row_text, quantity)
        _debug_log("price_result", row_id=row.row_id, region=region, result=result.__dict__)
        return result
    if mapping.huawei_product == "EVS":
        result = _price_evs(mapping, region, row_text, quantity)
        _debug_log("price_result", row_id=row.row_id, region=region, result=result.__dict__)
        return result
    if mapping.huawei_product == "CCE":
        result = _price_cce(mapping, region, row_text, quantity)
        _debug_log("price_result", row_id=row.row_id, region=region, result=result.__dict__)
        return result
    if mapping.huawei_product == "CCI":
        result = _price_cci(mapping, region, quantity, row_text)
        _debug_log("price_result", row_id=row.row_id, region=region, result=result.__dict__)
        return result
    result = _price_catalog_product(mapping, region, quantity)
    _debug_log("price_result", row_id=row.row_id, region=region, result=result.__dict__)
    return result


def _write_quote_headers(ws: Any, start_col: int) -> None:
    fill = PatternFill(fill_type="solid", fgColor="E6F0FF")
    font = Font(bold=True, color="1F2A44")
    for offset, header in enumerate(ROW_QUOTE_COLUMNS):
        cell = ws.cell(row=1, column=start_col + offset, value=header)
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        width = max(12, min(24, len(header) + 4))
        ws.column_dimensions[get_column_letter(start_col + offset)].width = width


def _write_price_result(ws: Any, row_number: int, start_col: int, result: PriceResult) -> None:
    values = [
        result.product_name,
        result.spec,
        result.quantity,
        result.unit_price,
        result.ondemand_monthly,
        result.monthly_price,
        result.ri_1y_monthly,
        result.status,
        result.rationale,
        result.confidence,
    ]
    for offset, value in enumerate(values):
        cell = ws.cell(row=row_number, column=start_col + offset, value=value)
        cell.alignment = Alignment(vertical="top", wrap_text=True)
        if isinstance(value, float):
            cell.number_format = "0.00"


def _summarize(results: list[PriceResult]) -> RowQuoteSummary:
    quoted = [item for item in results if item.status == QUOTE_STATUS_QUOTED]
    missing = [item for item in results if item.status == QUOTE_STATUS_MISSING_PRICE]
    manual = [item for item in results if item.status == QUOTE_STATUS_MANUAL]
    non_quote = [item for item in results if item.status == QUOTE_STATUS_NON_QUOTE]
    return RowQuoteSummary(
        total_rows=len(results),
        quoted_rows=len(quoted),
        unmatched_rows=len(missing),
        manual_review_rows=len(manual),
        missing_price_rows=len(missing),
        non_quote_rows=len(non_quote),
        total_ondemand_monthly=round(sum(item.ondemand_monthly or 0 for item in quoted), 2),
        total_monthly=round(sum(item.monthly_price or 0 for item in quoted), 2),
        total_ri_1y_monthly=round(sum(item.ri_1y_monthly or 0 for item in quoted), 2),
    )


def annotate_row_quote_workbook(upload: dict[str, Any], quote_context: dict[str, Any], progress_callback: Any = None, stage_callback: Any = None, cancel_check: Any = None) -> tuple[QuoteWorkbook, RowQuoteSummary]:
    filename = str(upload.get("filename") or "flexible.xlsx")
    if not filename.lower().endswith(".xlsx"):
        raise ValueError("Only Excel .xlsx files are supported for row-level flexible quote annotation.")
    content = upload.get("content") or b""
    if not content:
        raise ValueError("Uploaded Excel file is empty.")

    workbook = load_workbook(BytesIO(content))

    if callable(stage_callback):
        stage_callback("collect_rows")
    rows, original_widths = _collect_rows(workbook)
    if callable(cancel_check) and cancel_check():
        raise TaskCancelledError("Task was cancelled by user.")
    _debug_log(
        "collect_rows",
        filename=filename,
        row_count=len(rows),
        rows=[
            {"row_id": row.row_id, "sheet": row.sheet, "row_number": row.row_number, "cells": row.cells, "header_context": row.header_context}
            for row in rows
        ],
        quote_context=quote_context,
    )
    total_rows = len(rows)
    anchor_plan = build_anchor_plan(rows)

    if callable(stage_callback):
        stage_callback("pipeline_rows")
    if callable(cancel_check) and cancel_check():
        raise TaskCancelledError("Task was cancelled by user.")
    if callable(progress_callback):
        progress_callback(RowQuoteProgress(
            total_rows=total_rows,
            mapped_rows=0,
            priced_rows=0,
            stage_processed_rows=0,
            stage_total_rows=total_rows,
        ))

    for ws in workbook.worksheets[:1]:
        start_col = original_widths[ws.title] + 1
        _write_quote_headers(ws, start_col)

    raw_mappings: dict[str, RowMapping] = {}
    final_mappings: dict[str, RowMapping] = {}
    results: list[PriceResult] = []
    rows_by_id = {row.row_id: row for row in rows}
    priced_row_ids: set[str] = set()
    mapped_count = 0
    priced_count = 0

    def _emit_progress() -> None:
        if not callable(progress_callback):
            return
        quoted = sum(1 for r in results if r.status == QUOTE_STATUS_QUOTED)
        manual = sum(1 for r in results if r.status == QUOTE_STATUS_MANUAL)
        missing = sum(1 for r in results if r.status == QUOTE_STATUS_MISSING_PRICE)
        non_quote = sum(1 for r in results if r.status == QUOTE_STATUS_NON_QUOTE)
        progress_callback(RowQuoteProgress(
            total_rows=total_rows,
            processed_rows=priced_count,
            quoted_rows=quoted,
            manual_review_rows=manual,
            missing_price_rows=missing,
            unmatched_rows=0,
            non_quote_rows=non_quote,
            mapped_rows=mapped_count,
            priced_rows=priced_count,
            stage_processed_rows=priced_count,
            stage_total_rows=total_rows,
        ))

    def _try_price_ready_rows() -> None:
        nonlocal priced_count
        for row in rows:
            if callable(cancel_check) and cancel_check():
                return
            if row.row_id in priced_row_ids:
                continue
            if row.row_id not in final_mappings:
                raw = raw_mappings.get(row.row_id)
                if raw is None:
                    continue
                resolved = resolve_final_mapping(row, raw, raw_mappings, anchor_plan)
                if resolved is None:
                    continue
                final_mappings[row.row_id] = resolved
            mapping = final_mappings[row.row_id]
            if not raw_mappings.get(row.row_id):
                fallback = _fallback_mapping(row)
                final_mappings[row.row_id] = fallback
                mapping = fallback
            if raw_mappings.get(row.row_id) and mapping.is_quote_row:
                fallback = _fallback_mapping(row)
                if not mapping.quantity and fallback.quantity:
                    mapping = RowMapping(
                        row_id=mapping.row_id, is_quote_row=mapping.is_quote_row,
                        huawei_product=mapping.huawei_product, huawei_spec=mapping.huawei_spec,
                        quantity=fallback.quantity, rationale=mapping.rationale, confidence=mapping.confidence,
                    )
                if not mapping.huawei_product:
                    mapping = RowMapping(
                        row_id=mapping.row_id, is_quote_row=mapping.is_quote_row,
                        huawei_product=fallback.huawei_product, huawei_spec=mapping.huawei_spec,
                        quantity=mapping.quantity, rationale=mapping.rationale, confidence=mapping.confidence,
                    )
                if not mapping.huawei_spec:
                    mapping = RowMapping(
                        row_id=mapping.row_id, is_quote_row=mapping.is_quote_row,
                        huawei_product=mapping.huawei_product, huawei_spec=fallback.huawei_spec,
                        quantity=mapping.quantity, rationale=mapping.rationale, confidence=mapping.confidence,
                    )
                final_mappings[row.row_id] = mapping
            result = _price_row(mapping, rows_by_id[row.row_id], quote_context)
            results.append(result)
            ws = workbook[row.sheet]
            _write_price_result(ws, row.row_number, original_widths[row.sheet] + 1, result)
            priced_row_ids.add(row.row_id)
            priced_count = len(priced_row_ids)
        _emit_progress()

    def on_mapping_progress(new_mapped_count: int, total: int) -> None:
        nonlocal mapped_count
        mapped_count = new_mapped_count
        _try_price_ready_rows()

    llm_mappings = _maas_map_rows(rows, quote_context, mapping_progress_callback=on_mapping_progress, cancel_check=cancel_check)
    raw_mappings.update(llm_mappings)
    mapped_count = len(raw_mappings)

    for row in rows:
        if row.row_id not in raw_mappings:
            raw_mappings[row.row_id] = _fallback_mapping(row)
    mapped_count = len(raw_mappings)

    _try_price_ready_rows()

    if callable(cancel_check) and cancel_check():
        raise TaskCancelledError("Task was cancelled by user.")

    output = BytesIO()
    workbook.save(output)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_stem = _safe_ascii_filename(filename)
    summary = _summarize(results)
    _debug_log("annotate_complete", filename=filename, summary=summary.model_dump())
    return QuoteWorkbook(filename=f"{safe_stem}-huawei-row-quote-{stamp}.xlsx", content=output.getvalue()), summary
