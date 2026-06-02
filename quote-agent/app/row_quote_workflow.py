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
from app.models import PriceComponent, QuoteWorkbook, RowQuoteProgress, RowQuoteSummary, SheetSelection, SheetSelectionError, resolve_sheet_selection
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

ROW_QUOTE_COLUMNS_EN = [
    "Huawei Cloud Product",
    "Huawei Cloud Spec",
    "Quantity",
    "Unit Price",
    "On-demand Monthly",
    "Monthly Price",
    "RI 1Y Monthly",
    "Quote Status",
    "Mapping Notes",
    "Confidence",
    "ecs_vcpu",
    "ecs_mem",
    "composite_family",
    "composite_part",
    "composite_group_key",
    "group_total_monthly_price",
    "group_quote_status",
    "group_component_count",
    "group_quoted_component_count",
]

ROW_QUOTE_COLUMNS_ZH = [
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
    "ecs_vcpu",
    "ecs_mem",
    "composite_family",
    "composite_part",
    "composite_group_key",
    "group_total_monthly_price",
    "group_quote_status",
    "group_component_count",
    "group_quoted_component_count",
]

ROW_QUOTE_COLUMNS = ROW_QUOTE_COLUMNS_EN

_QUOTE_STATUS_LABELS: dict[str, dict[str, str]] = {
    "quoted": {"en": "Quoted", "zh": "已报价"},
    "non_quote": {"en": "Non-quote row", "zh": "非报价行"},
    "missing_price": {"en": "Missing price", "zh": "缺少价格"},
    "manual": {"en": "Manual review", "zh": "需人工确认"},
}

QUOTE_STATUS_QUOTED = "Quoted"
QUOTE_STATUS_NON_QUOTE = "Non-quote row"
QUOTE_STATUS_MISSING_PRICE = "Missing price"
QUOTE_STATUS_MANUAL = "Manual review"


def _quote_language(quote_context: dict[str, Any]) -> str:
    lang = str(quote_context.get("language", "") or "").strip().lower()
    return lang if lang in {"zh", "en", "es"} else "en"


def _row_quote_columns(lang: str) -> list[str]:
    return ROW_QUOTE_COLUMNS_ZH if lang == "zh" else ROW_QUOTE_COLUMNS_EN


def _status_label(key: str, lang: str) -> str:
    labels = _QUOTE_STATUS_LABELS.get(key, {})
    return labels.get(lang) or labels.get("en") or key

NETWORK_PRODUCTS = {"EIP", "NAT Gateway", "VPN", "Direct Connect as a Service", "ELB", "VPC", "Cloud Connect"}
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
    "50 nodes",
    "200 nodes",
    "1000 nodes",
    "2000 nodes",
    "standard/turbo",
)

DB_FAMILY_KEYWORDS = (
    "mysql",
    "postgresql",
    "postgres",
    "redis",
    "mongodb",
    "geminidb",
    "ctsdb",
    "时序数据库",
    "kafka",
    "ckafka",
    "云数据库",
    "数据库",
    "relational database",
    "document database",
)

CCE_EXCLUSION_KEYWORDS = (
    "低频存储",
    "infrequent access",
    "归档",
    "archive",
    "对象存储",
    "object storage",
    "obs",
    "cos",
    "低频",
    "标准存储",
    "standard storage",
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
    composite_family: str | None = None
    composite_part: str | None = None
    composite_group_key: str | None = None


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
    ecs_vcpu: int | None = None
    ecs_mem: float | None = None
    composite_family: str | None = None
    composite_part: str | None = None
    composite_group_key: str | None = None
    # Group-level aggregation fields (backfilled after pricing all rows)
    group_total_monthly_price: float | None = None
    group_quote_status: str | None = None
    group_component_count: int | None = None
    group_quoted_component_count: int | None = None


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
    if row_number > 2:
        cells, local_cells, inherited_cells = _row_cells(ws, 1, max_col, merged_lookup)
        if cells:
            context.append(
                {
                    "row_number": "1",
                    "cells": json.dumps(cells, ensure_ascii=False),
                    "local_cells": json.dumps(local_cells, ensure_ascii=False),
                    "inherited_cells": json.dumps(inherited_cells, ensure_ascii=False),
                }
            )
    start = max(1, row_number - 5)
    for candidate_row in range(start, row_number):
        if candidate_row == 1 and context:
            continue
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
    if context and context[0].get("row_number") == "1":
        return [context[0], *context[-5:]]
    return context[-5:]


def _collect_rows(workbook: Any, selected_sheet_names: list[str] | None = None) -> tuple[list[RowCandidate], dict[str, int]]:
    rows: list[RowCandidate] = []
    original_widths: dict[str, int] = {}
    if selected_sheet_names is not None:
        worksheets = [ws for ws in workbook.worksheets if ws.title in selected_sheet_names]
    else:
        worksheets = workbook.worksheets[:1]
    for ws in worksheets:
        max_col = ws.max_column
        merged_lookup, merged_row_groups = _build_merged_metadata(ws)
        original_widths[ws.title] = max_col
        for row_number in range(2, ws.max_row + 1):
            cells, local_cells, inherited_cells = _row_cells(ws, row_number, max_col, merged_lookup)
            if not cells:
                continue
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


def _iter_table_header_context(row: RowCandidate) -> list[dict[str, str]]:
    primary_headers = [item for item in row.header_context if str(item.get("row_number")) == "1"]
    return primary_headers or row.header_context


def _value_by_header(row: RowCandidate, patterns: list[str]) -> str | None:
    for item in _iter_table_header_context(row):
        try:
            headers = json.loads(item["cells"])
        except Exception:
            continue
        for column, header in headers.items():
            header_text = str(header).strip().lower()
            if any(re.search(pattern, header_text, re.I) for pattern in patterns):
                value = row.cells.get(column)
                if value is not None:
                    return str(value).strip()
    return None


# ---------------------------------------------------------------------------
# Rule Layer 1: Hard exclusions
# ---------------------------------------------------------------------------
# Template VMs, powered-off VMs, header/group rows, and traffic rows that
# are never chargeable (e.g. DC outbound).  This layer runs first and
# short-circuits all further processing.

def _forced_non_quote_mapping(row: RowCandidate) -> RowMapping | None:
    """Exclude template VMs and powered-off VMs from quoting."""
    name = _value_by_header(row, [r"\bvm\b", r"\bname\b", r"vm\s*name"])
    powerstate = _value_by_header(row, [r"power\s*state", r"powerstate"])
    template = _value_by_header(row, [r"\btemplate\b"])
    local_text = _joined_local_row(row).lower()

    if template and template.strip().lower() in {"true", "yes", "y", "1"}:
        return RowMapping(row.row_id, False, rationale="Template VM row is excluded from quote.", confidence=0.95)
    if name and re.search(r"\b(tmpl|template)\b", name, re.I):
        return RowMapping(row.row_id, False, rationale="Template VM row is excluded from quote.", confidence=0.95)
    if re.search(r"\b(tmpl|template)\b", local_text):
        return RowMapping(row.row_id, False, rationale="Template VM row is excluded from quote.", confidence=0.9)
    if powerstate and powerstate.strip().lower() in {"poweredoff", "powered off", "off"}:
        return RowMapping(row.row_id, False, rationale="Powered-off VM row is excluded from quote.", confidence=0.9)
    return None


def _apply_hard_exclusions(row: RowCandidate) -> RowMapping | None:
    """Layer 1 — hard exclusions that always take priority.

    Returns a non-quote RowMapping if the row should be excluded, or None
    if the row should proceed to further rule layers.
    """
    # Template / powered-off VMs
    forced = _forced_non_quote_mapping(row)
    if forced:
        return forced

    # DC outbound traffic — Huawei does not charge for DC traffic
    local_text = _joined_local_row(row).lower()
    combined = " ".join([_joined_header_context(row), local_text, _joined_row(row)]).lower()
    if "出方向流量" in local_text or "outbound traffic" in local_text:
        if "direct connect" in combined or "专线" in combined or "dc" in combined:
            return RowMapping(row.row_id, False, rationale="Direct Connect outbound traffic is not charged by Huawei Cloud.", confidence=0.92)

    # Empty, header, or group rows
    if _looks_like_header_or_group(row):
        return RowMapping(row.row_id, False, rationale="Empty, header, or group row.", confidence=0.9)

    return None


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
    if any(marker in text for marker in ["兜底折扣", "默认兜底折扣", "折扣", "discount"]):
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
    for context_row in _iter_table_header_context(row):
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
        r"\bgp-?ssd-v2\b",
        r"\bgp-?ssd\b",
        r"\bhigh-io\b",
        r"\bultra-high-io\b",
        r"\bsas\b",
        r"\bcbr-basic\b",
        r"\beip-standard\b",
        r"\bnat-(?:small|middle|large|basic)\b",
        r"\bvpn-(?:basic|professional-1|professional-2)\b",
        r"\bdcas-\d+g\b",
        r"\bcce-standard\b",
        r"\bsfs-turbo-(?:standard|20mbps-per-tib|40mbps-per-tib|125mbps-per-tib|250mbps-per-tib)\b",
        r"\bobs-(?:standard|infrequent-access)\b",
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


def _extract_ecs_shape_from_row(row: RowCandidate) -> tuple[int | None, float | None]:
    cpu: int | None = None
    memory: float | None = None
    for context_row in _iter_table_header_context(row):
        try:
            headers = json.loads(context_row["cells"])
        except Exception:
            continue
        for column, header in headers.items():
            header_text = str(header).strip().lower()
            value = _to_float(row.cells.get(column))
            if value is None or value <= 0:
                continue
            if cpu is None and re.search(r"\b(num\s*)?(v?cpus?|cores?)\b|核", header_text):
                cpu = int(value)
                continue
            if memory is None and re.search(r"\b(mem|memory|ram)\b|内存", header_text):
                # RVTools commonly exports Memory in MiB without a unit in the cell.
                memory = value / 1024 if "mb" in header_text or ("gb" not in header_text and "gib" not in header_text and value > 512) else value
    if cpu and memory:
        return cpu, memory
    return _extract_compute_shape(_joined_row(row))


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


def _normalize_spec_alias(product: str | None, spec_text: str | None, row_text: str = "") -> str | None:
    """Normalize LLM/spec output to a catalog-hittable key.

    This runs *before* price lookup so that specs like "High-performance (SAS)"
    or "Ultra High I/O" map to catalog sku keys like "high-io" or "ultra-high-io".
    """
    if not product or not spec_text:
        return spec_text
    combined = " ".join(part for part in [spec_text, row_text] if part).lower()
    if product == "EVS":
        row_only = (row_text or "").lower()
        if re.search(r"gpssd[\s-]?v2|general\s*purpose\s*ssd\s*v2|额外性能", row_only, re.I):
            return "gpssd-v2"
        if re.search(r"ultra[\s-]?high\s*i/?o|增强型\s*ssd|ultra[\s-]?high", row_only, re.I):
            return "ultra-high-io"
        if re.search(r"gpssd|general\s*purpose\s*ssd|通用型\s*ssd", row_only, re.I):
            return "gpssd"
        if re.search(r"high\s*i/?o|高性能|high[\s-]?performance", row_only, re.I):
            return "high-io"
        if re.search(r"ultra[\s-]?high\s*i/?o|增强型\s*ssd|ultra[\s-]?high", combined, re.I):
            return "ultra-high-io"
        if re.search(r"gpssd[\s-]?v2|general\s*purpose\s*ssd\s*v2|额外性能", combined, re.I):
            return "gpssd-v2"
        if re.search(r"gpssd|general\s*purpose\s*ssd|通用型\s*ssd", combined, re.I):
            return "gpssd"
        if re.search(r"high\s*i/?o|high[\s-]?performance|高性能", combined, re.I):
            return "high-io"
        if re.search(r"common\s*i/?o|普通\s*i/?o", combined, re.I):
            return "sas"
    if product == "OBS":
        if re.search(r"低频|infrequent\s*access|ia|归档|archive", combined, re.I):
            return "obs-infrequent-access"
        if re.search(r"标准|standard|single[\s-]?az|multi[\s-]?az", combined, re.I):
            return "obs-standard"
    if product == "SFS Turbo":
        if re.search(r"20\s*mb|通用性能型", combined, re.I):
            return "sfs-turbo-20mbps-per-tib"
        if re.search(r"40\s*mb|turbo标准型|turbo\s*standard", combined, re.I):
            return "sfs-turbo-40mbps-per-tib"
        if re.search(r"125\s*mb", combined, re.I):
            return "sfs-turbo-125mbps-per-tib"
        if re.search(r"250\s*mb", combined, re.I):
            return "sfs-turbo-250mbps-per-tib"
    if product == "NAT Gateway":
        if re.search(r"标准型\s*nat|标准型.*网关实例|cu费", combined, re.I):
            return "nat-small"
        if re.search(r"小型|small", combined, re.I):
            return "nat-small"
        if re.search(r"中型|middle|medium", combined, re.I):
            return "nat-middle"
        if re.search(r"大型|large", combined, re.I):
            return "nat-large"
    if product == "VPN":
        if re.search(r"vpn网关|vpn\s*gateway|实例", combined, re.I) and not re.search(r"出流量|outbound|traffic", combined, re.I):
            return "vpn-professional-1"
        if re.search(r"professional\s*1|专业型\s*1", combined, re.I):
            return "vpn-professional-1"
        if re.search(r"professional\s*2|专业型\s*2", combined, re.I):
            return "vpn-professional-2"
    if product == "Direct Connect as a Service":
        if re.search(r"100\s*g|100ge", combined, re.I):
            return "dcas-100g"
        if re.search(r"10\s*g|10ge", combined, re.I):
            return "dcas-10g"
        if re.search(r"1\s*g|1ge", combined, re.I):
            return "dcas-1g"
    return spec_text


def _contains_gpu_terms(*parts: str | None) -> bool:
    combined = " ".join(part for part in parts if part).lower()
    return any(keyword in combined for keyword in GPU_KEYWORDS)


def _should_force_cci(*parts: str | None) -> bool:
    combined = " ".join(part for part in parts if part).lower()
    if any(keyword in combined for keyword in CCI_PRIORITY_KEYWORDS):
        return True
    # Match CCI only as an explicit product token. Substring matching breaks
    # Spanish RVTools exports because words such as "Producción" contain "cci".
    return re.search(r"(?<![a-z0-9])cci(?![a-z0-9])", combined) is not None


def _is_db_family_context(*parts: str | None) -> bool:
    combined = " ".join(part for part in parts if part).lower()
    if any(keyword in combined for keyword in DB_FAMILY_KEYWORDS):
        return True
    for token in ("rds", "dds", "dcs", "geminidb", "gemini"):
        if re.search(rf"(?<![a-z0-9]){token}(?![a-z0-9])", combined):
            return True
    return False


def _should_force_cce_cluster(*parts: str | None) -> bool:
    combined = " ".join(part for part in parts if part).lower()
    if any(keyword in combined for keyword in CCE_EXCLUSION_KEYWORDS):
        return False
    return any(keyword in combined for keyword in CCE_CLUSTER_KEYWORDS)


# ---------------------------------------------------------------------------
# Composite product family / part detection
# ---------------------------------------------------------------------------

_COMPOSITE_FAMILY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("rds", ("mysql", "云数据库mysql", "云数据库 mysql", "relational database", "rds")),
    ("rds", ("postgresql", "postgres", "云数据库postgresql", "云数据库 postgresql")),
    ("dds", ("mongodb", "dds", "document database", "副本集")),
    ("dws", ("dws", "data warehouse", "数据仓库", "tchouse")),
]

_COMPOSITE_PART_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("cpu", ("cpu", "cpu时间", "核", "vcpu")),
    ("memory", ("内存", "memory", "ram")),
    ("storage", ("硬盘", "存储", "storage", "磁盘", "disk", "节点存储")),
    ("compute", ("节点", "node", "计算")),
]


def _detect_composite_family(*parts: str | None) -> str | None:
    combined = " ".join(part for part in parts if part).lower()
    for family, keywords in _COMPOSITE_FAMILY_RULES:
        if any(k in combined for k in keywords):
            return family
    return None


def _detect_composite_part(*parts: str | None) -> str | None:
    combined = " ".join(part for part in parts if part).lower()
    for part_type, keywords in _COMPOSITE_PART_RULES:
        if any(k in combined for k in keywords):
            return part_type
    return None


def _composite_group_key(sheet: str, family: str, *name_parts: str | None) -> str:
    """Generate a stable group key for composite product sub-rows.

    The key is deterministic within a single workbook analysis so that
    CPU / memory / storage sub-rows of the same DB instance share a key.
    Only uses shared context (header, parent product name), not row-specific text.
    """
    base = " ".join(part for part in name_parts if part).strip().lower()
    # Normalize: keep only alnum + space, collapse whitespace
    base = re.sub(r"[^\w\s]", "", base)
    base = re.sub(r"\s+", " ", base).strip()
    # Extract only the DB product name part (e.g., "云数据库mysql", "postgresql", "mongodb")
    # to make the key stable across sub-rows that share the same parent product
    db_name_match = re.search(
        r"(云数据库\s*mysql|云数据库\s*postgresql|mysql|postgresql|mongodb|dds|dws|tchouse|数据仓库)",
        base,
    )
    if db_name_match:
        base = db_name_match.group(1)
    # Truncate to keep key readable
    if len(base) > 60:
        base = base[:60]
    return f"{sheet}:{family}:{base or 'default'}"


# ---------------------------------------------------------------------------
# Rule Layer 4: Product priority overrides (post-LLM corrections)
# ---------------------------------------------------------------------------
# After LLM mapping (or fallback), correct the product when context
# clearly indicates a different product.  This layer handles:
#   - DB family context overriding CCI/CCE → RDS/DDS/DCS/GeminiDB/DMS
#   - OBS/storage context overriding CCE → OBS
#   - CCI/CCE forcing from local keywords
#
# Composite sub-row routing (Layer 3) and composite metadata enrichment
# (Layer 6) are handled by their own dedicated functions.

def _apply_product_priority_overrides(row: RowCandidate, mapping: RowMapping) -> RowMapping:
    """Layer 4 — post-LLM product corrections based on row context.

    This is the SINGLE definition point for:
      - DB family context overrides (CCI/CCE → RDS/DDS/DCS/GeminiDB/DMS)
      - OBS/storage context overrides (CCE → OBS)
      - CCI/CCE forcing from local/merged keywords
    """
    row_text = _joined_row(row)
    local_row_text = _joined_local_row(row)
    inherited_row_text = _joined_inherited_row(row)
    header_text = _joined_header_context(row)
    semantic_context = " ".join([header_text, inherited_row_text, local_row_text, row_text])
    combined = " ".join([semantic_context, mapping.rationale or "", mapping.huawei_spec or ""])
    local_combined = " ".join([local_row_text, mapping.rationale or "", mapping.huawei_spec or ""])
    db_context = _is_db_family_context(combined)

    context_lower = semantic_context.lower()
    context_product: str | None = None
    if "云监控" in context_lower or re.search(r"(?<![a-z0-9])ces(?![a-z0-9])", context_lower):
        context_product = "CES"
    elif "日志服务" in context_lower or re.search(r"(?<![a-z0-9])cls(?![a-z0-9])", context_lower) or "log tank service" in context_lower:
        context_product = "LTS"
    elif "wedata" in context_lower or "数据开发治理" in context_lower or "dataarts" in context_lower:
        context_product = "DataArts Studio"
    elif "密钥管理" in context_lower or re.search(r"(?<![a-z0-9])kms(?![a-z0-9])", context_lower) or re.search(r"(?<![a-z0-9])dew(?![a-z0-9])", context_lower):
        context_product = "DEW"
    elif "云防火墙" in context_lower or re.search(r"(?<![a-z0-9])cfw(?![a-z0-9])", context_lower):
        context_product = "CFW"
    elif "高防eip" in context_lower or "ddos" in context_lower or "ddos防护" in context_lower:
        context_product = "Anti-DDoS"
    if context_product and mapping.huawei_product != context_product:
        note = f"Local product context overrides LLM {mapping.huawei_product or 'unknown'} to {context_product}."
        return RowMapping(
            row_id=mapping.row_id,
            is_quote_row=mapping.is_quote_row,
            huawei_product=context_product,
            huawei_spec=_normalize_mapping_spec(context_product, mapping.huawei_spec, semantic_context),
            quantity=mapping.quantity,
            rationale=f"{mapping.rationale} {note}".strip(),
            confidence=max(mapping.confidence, 0.82),
        )

    # DB family context corrects generic/wrong DB mappings.
    if db_context:
        lowered = semantic_context.lower()
        if "kafka" in lowered or "ckafka" in lowered or re.search(r"(?<![a-z0-9])dms(?![a-z0-9])", lowered):
            corrected = "DMS"
        elif "geminidb" in lowered or "ctsdb" in lowered or "时序数据库" in lowered or re.search(r"(?<![a-z0-9])gemini(?![a-z0-9])", lowered):
            corrected = "GeminiDB"
        elif "mongodb" in lowered or "副本集" in lowered or "document database" in lowered or re.search(r"(?<![a-z0-9])dds(?![a-z0-9])", lowered):
            corrected = "DDS"
        elif "redis" in lowered or re.search(r"(?<![a-z0-9])dcs(?![a-z0-9])", lowered):
            corrected = "DCS"
        else:
            corrected = "RDS"
    else:
        corrected = None

    if corrected and mapping.huawei_product in ("CCI", "CCE", "RDS", "DDS", "DCS", "GeminiDB", "DMS") and mapping.huawei_product != corrected:
        note = f"DB family context overrides LLM {mapping.huawei_product} to {corrected}."
        _debug_log("product_priority_override", row_id=row.row_id, previous_product=mapping.huawei_product, forced_product=corrected)
        return RowMapping(
            row_id=mapping.row_id,
            is_quote_row=mapping.is_quote_row,
            huawei_product=corrected,
            huawei_spec=_normalize_mapping_spec(corrected, mapping.huawei_spec, combined),
            quantity=mapping.quantity,
            rationale=f"{mapping.rationale} {note}".strip(),
            confidence=max(mapping.confidence, 0.82),
        )

    # OBS/storage context overrides CCE → OBS
    if mapping.huawei_product == "CCE":
        lowered = combined.lower()
        if any(k in lowered for k in ("低频存储", "infrequent access", "对象存储", "object storage", "obs", "cos", "标准存储", "standard storage")):
            note = "OBS/storage context overrides LLM CCE to OBS."
            _debug_log("product_priority_override", row_id=row.row_id, previous_product="CCE", forced_product="OBS")
            return RowMapping(
                row_id=mapping.row_id,
                is_quote_row=mapping.is_quote_row,
                huawei_product="OBS",
                huawei_spec=_normalize_mapping_spec("OBS", mapping.huawei_spec, combined),
                quantity=mapping.quantity,
                rationale=f"{mapping.rationale} {note}".strip(),
                confidence=max(mapping.confidence, 0.82),
            )

    # CCI/CCE forcing from local/merged keywords
    forced_product: str | None = None
    note: str | None = None
    if _should_force_cce_cluster(local_combined):
        forced_product = "CCE"
        note = "Local cluster pricing keywords force product mapping to CCE."
    elif _should_force_cci(local_combined) and not db_context:
        forced_product = "CCI"
        note = "Local Serverless/Pod keywords force product mapping to CCI."
    elif _should_force_cci(combined) and not db_context:
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


# ---------------------------------------------------------------------------
# Rule Layer 5: Spec normalization
# ---------------------------------------------------------------------------
# _normalize_mapping_spec and _normalize_spec_alias are already defined
# above.  This layer runs after product routing/priority overrides and
# before pricing, so that specs map to catalog-hittable keys.
# (The functions are called inline at the appropriate points; no new
# wrapper is needed — they are already single-definition-point helpers.)


# ---------------------------------------------------------------------------
# Rule Layer 6: Composite metadata enrichment
# ---------------------------------------------------------------------------
# Tag a mapping with composite_family / composite_part / composite_group_key
# if the row belongs to a composite DB family, even when no product
# override happened.  This ensures every return path carries composite
# metadata when applicable.

def _enrich_composite_metadata(row: RowCandidate, mapping: RowMapping) -> RowMapping:
    """Layer 6 — tag mapping with composite metadata if applicable.

    If the mapping already has composite metadata, return it unchanged.
    Otherwise, detect composite family/part from row context and tag.
    """
    if mapping.composite_family:
        return mapping

    row_text = _joined_row(row)
    local_row_text = _joined_local_row(row)
    header_text = _joined_header_context(row)
    inherited_row_text = _joined_inherited_row(row)

    composite_family = _detect_composite_family(header_text, inherited_row_text, row_text)
    composite_part = _detect_composite_part(row_text, local_row_text)
    if not composite_family or not composite_part:
        return mapping

    group_key = _composite_group_key(row.sheet, composite_family, header_text, inherited_row_text, row_text)
    return RowMapping(
        row_id=mapping.row_id,
        is_quote_row=mapping.is_quote_row,
        huawei_product=mapping.huawei_product,
        huawei_spec=mapping.huawei_spec,
        quantity=mapping.quantity,
        rationale=mapping.rationale,
        confidence=mapping.confidence,
        composite_family=composite_family,
        composite_part=composite_part,
        composite_group_key=group_key,
    )


# ---------------------------------------------------------------------------
# Unified post-LLM pipeline: layers 3→4→5→6 applied in order
# ---------------------------------------------------------------------------

def _apply_product_priority(row: RowCandidate, mapping: RowMapping) -> RowMapping:
    """Apply post-LLM rule layers in order: composite routing → priority
    overrides → composite metadata enrichment.

    The decision order is:
      Layer 2: special product routing (may override product)
      Layer 3: composite sub-row routing (may override product)
      Layer 4: product priority overrides (DB context, CCI/CCE forcing)
      Layer 6: composite metadata enrichment (tag if not already tagged)

    Spec normalization (Layer 5) is applied inline by each layer that
    overrides the product.
    """
    # Layer 2: special product routing
    special_override = _apply_special_product_routing(row)
    if special_override:
        _debug_log("special_product_routing", row_id=row.row_id, previous_product=mapping.huawei_product, forced_product=special_override.huawei_product)
        mapping = special_override

    # Layer 3: composite sub-row routing
    composite_override = _apply_composite_routing(row, mapping)
    if composite_override:
        _debug_log("composite_subrow_routing", row_id=row.row_id, family=composite_override.composite_family, part=composite_override.composite_part, previous_product=mapping.huawei_product, forced_product=composite_override.huawei_product)
        mapping = composite_override

    # Layer 4: product priority overrides
    mapping = _apply_product_priority_overrides(row, mapping)

    # Layer 6: composite metadata enrichment
    mapping = _enrich_composite_metadata(row, mapping)

    return mapping


# ---------------------------------------------------------------------------
# Rule Layer 2: Special product routing
# ---------------------------------------------------------------------------
# Network / traffic sub-rows that map to a specific product before LLM
# or generic keyword matching.  These are *product routing* decisions,
# not exclusions (Layer 1 already handled non-quote traffic).

def _apply_special_product_routing(row: RowCandidate) -> RowMapping | None:
    """Layer 2 — route special sub-rows to their correct Huawei product.

    Returns a RowMapping if a special routing rule fires, or None to
    let the row proceed to composite routing / LLM / fallback.
    """
    text = _joined_row(row).lower()
    local_text = _joined_local_row(row).lower()
    header_text = _joined_header_context(row).lower()
    combined = " ".join([header_text, local_text, text])

    # VPN outbound traffic — not a VPN instance fee
    if "外网出流量" in local_text or (("vpn" in combined or "vpn网关" in combined) and ("出流量" in local_text or "outbound" in local_text)):
        return RowMapping(row.row_id, True, huawei_product="VPN", huawei_spec="outbound-traffic", quantity=1, rationale="VPN outbound traffic row; price requires manual review.", confidence=0.7)

    # Cloud Connect (CCN) rows
    if "云联网" in combined or "ccn" in combined or "cloud connect" in combined:
        quantity = _extract_quantity(row) or 1
        return RowMapping(row.row_id, True, huawei_product="Cloud Connect", huawei_spec=_extract_sku(text) or text[:80], quantity=quantity, rationale="Cloud Connect (CCN) product mapping.", confidence=0.82)

    # CLB/ELB traffic sub-row → EIP
    if ("负载均衡" in combined or "clb" in combined or "elb" in combined) and ("流量" in combined or "traffic" in combined):
        if "实例" not in local_text and "instance" not in local_text and "lcu" not in local_text:
            quantity = _extract_quantity(row) or 1
            return RowMapping(row.row_id, True, huawei_product="EIP", huawei_spec="by-traffic", quantity=quantity, rationale="Load balancer traffic sub-row maps to EIP by traffic.", confidence=0.78)

    # 共享带宽包 → EIP
    if "共享带宽" in combined or "带宽包" in combined:
        if "传统型" in combined or "增强型" in combined or "95" in combined:
            spec = "by-bandwidth-shared" if "传统型" in combined else "enhanced-95"
            quantity = _extract_quantity(row) or 1
            return RowMapping(row.row_id, True, huawei_product="EIP", huawei_spec=spec, quantity=quantity, rationale="Shared bandwidth package maps to EIP.", confidence=0.8)

    return None


# ---------------------------------------------------------------------------
# Rule Layer 3: Composite DB sub-row routing
# ---------------------------------------------------------------------------
# When a row is part of a composite DB family (RDS/DDS/DWS) and has a
# detectable part (cpu/memory/storage/compute), route it to the correct
# product: storage→EVS, compute→DB product family.
# This is the SINGLE definition point for composite sub-row routing.

def _apply_composite_routing(row: RowCandidate, mapping: RowMapping | None = None) -> RowMapping | None:
    """Layer 3 — route composite DB sub-rows to the correct product.

    If *mapping* is provided (post-LLM), this may override the product
    on the existing mapping.  If *mapping* is None (pre-LLM fallback),
    this returns a fresh RowMapping or None.

    Returns a RowMapping if composite routing fires, or None.
    """
    text = _joined_row(row).lower()
    local_text = _joined_local_row(row).lower()
    header_text = _joined_header_context(row).lower()
    combined = " ".join([header_text, local_text, text])

    composite_family = _detect_composite_family(header_text, _joined_inherited_row(row), text)
    composite_part = _detect_composite_part(text, local_text)
    if not composite_family or not composite_part:
        return None

    group_key = _composite_group_key(row.sheet, composite_family, header_text, _joined_inherited_row(row), text)
    quantity = (mapping.quantity if mapping else None) or _extract_quantity(row) or 1

    if composite_part == "storage":
        target_product = "EVS"
        spec = _normalize_mapping_spec("EVS", (mapping.huawei_spec if mapping else None) or _extract_sku(text) or text[:80], combined)
        rationale = f"Composite {composite_family} storage sub-row routed to EVS."
        confidence = 0.82
    elif composite_part in ("cpu", "memory", "compute"):
        target_product = {"rds": "RDS", "dds": "DDS", "dws": "DWS"}.get(composite_family)
        if not target_product:
            return None
        spec = _normalize_mapping_spec(target_product, (mapping.huawei_spec if mapping else None) or _extract_sku(text) or text[:80], combined)
        rationale = f"Composite {composite_family} {composite_part} sub-row routed to {target_product}."
        confidence = 0.82
    else:
        return None

    # When called post-LLM with an existing mapping, only override if the
    # product is clearly wrong (CCI, CCE, generic, or wrong DB family).
    if mapping is not None:
        if composite_part == "storage":
            # Storage sub-rows always route to EVS regardless of LLM output
            if mapping.huawei_product == target_product:
                # Already correct product — just tag composite metadata
                return None
        elif composite_part in ("cpu", "memory", "compute"):
            # Only override if current product is clearly wrong
            if mapping.huawei_product not in ("CCI", "CCE", "RDS", "DDS", "DWS", "EVS", None):
                return None
            if mapping.huawei_product == target_product:
                return None

    return RowMapping(
        row_id=row.row_id,
        is_quote_row=True,
        huawei_product=target_product,
        huawei_spec=spec,
        quantity=quantity,
        rationale=rationale,
        confidence=confidence,
        composite_family=composite_family,
        composite_part=composite_part,
        composite_group_key=group_key,
    )


def _fallback_mapping(row: RowCandidate) -> RowMapping:
    """Pre-LLM fallback mapping using the rule layers in order.

    Decision order:
      Layer 1: hard exclusions (template, powered-off, header/group, DC traffic)
      Layer 2: special product routing (VPN, CCN, CLB→EIP, bandwidth→EIP)
      Layer 3: composite sub-row routing (DB storage→EVS, DB compute→RDS/DDS/DWS)
      Layer 4: CCI/CCE forcing from keywords
      generic: _normalize_product_name keyword match
      unmatched: low-confidence quote row
    """
    # Layer 1: hard exclusions
    excluded = _apply_hard_exclusions(row)
    if excluded:
        _debug_log("fallback_mapping", row_id=row.row_id, source="hard_exclusion", mapping=excluded.__dict__)
        return excluded

    # Layer 2: special product routing
    special = _apply_special_product_routing(row)
    if special:
        _debug_log("fallback_mapping", row_id=row.row_id, source="special_product_routing", mapping=special.__dict__)
        return special

    # Layer 3: composite sub-row routing
    composite = _apply_composite_routing(row)
    if composite:
        _debug_log("fallback_mapping", row_id=row.row_id, source="composite_routing", mapping=composite.__dict__)
        return composite

    # Layer 4: CCI/CCE forcing from keywords
    text = _joined_row(row)
    local_text = _joined_local_row(row)
    header_text = _joined_header_context(row)
    local_combined = local_text.strip()
    combined_text = " ".join([header_text, text]).strip()
    db_context = _is_db_family_context(combined_text)

    if _should_force_cce_cluster(local_combined):
        quantity = _extract_quantity(row)
        rationale = "In-row cluster management keywords force CCE mapping."
        if quantity is None:
            quantity = 1
            rationale = f"{rationale} Quantity estimated as 1."
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
    if _should_force_cci(local_combined) and not db_context:
        quantity = _extract_quantity(row)
        rationale = "In-row serverless/pod keywords force CCI mapping."
        if quantity is None:
            quantity = 1
            rationale = f"{rationale} Quantity estimated as 1."
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
    if _should_force_cci(combined_text) and not db_context:
        quantity = _extract_quantity(row)
        rationale = "Serverless/pod keywords force CCI mapping."
        if quantity is None:
            quantity = 1
            rationale = f"{rationale} Quantity estimated as 1."
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
        rationale = "Cluster management keywords force CCE mapping."
        if quantity is None:
            quantity = 1
            rationale = f"{rationale} Quantity estimated as 1."
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

    # Generic keyword match
    product = _normalize_product_name(text)
    if product:
        quantity = _extract_quantity(row)
        rationale = "Matched as quoteable row via local keywords."
        if quantity is None:
            quantity = 1
            rationale = f"{rationale} Quantity estimated as 1."
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
    mapping = RowMapping(row_id=row.row_id, is_quote_row=True, rationale="Row has content but no Huawei Cloud product could be auto-matched.", confidence=0.25)
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
    # Layer 1: hard exclusions (template, powered-off, header/group, DC traffic)
    excluded = _apply_hard_exclusions(row)
    if excluded:
        _debug_log(
            "hard_exclusion_override",
            row_id=row.row_id,
            raw_mapping=raw_mapping.__dict__ if raw_mapping else None,
            forced_mapping=excluded.__dict__,
        )
        return excluded
    if raw_mapping is None:
        return None
    if not raw_mapping.is_quote_row:
        fallback = _fallback_mapping(row)
        if fallback.is_quote_row and fallback.huawei_product:
            return _apply_product_priority(row, fallback)
        return raw_mapping
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
        "DCS", "GeminiDB", "DMS", "DataArts Studio", "Cloud Connect", "KMS", "DEW",
        "Anti-DDoS", "CFW", "CES", "LTS",
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
            rationale="CCE management node price did not match any confirmed local price.",
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


def _confirmed_flexible_candidates(product: str, region: str, spec_text: str | None, row_text: str = "") -> list[PriceComponent]:
    candidates = [
        item
        for item in query_flexible_pricing_catalog(product=product, region=region)
        if item.confirmed and item.status == "confirmed" and item.price is not None
    ]
    # Apply spec alias normalization before matching
    normalized = _normalize_spec_alias(product, spec_text, row_text)
    spec = (normalized or spec_text or "").lower()
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


def _ecs_pricing_rationale(base: str, mapping: RowMapping) -> str:
    if "quantity estimated as 1" in (mapping.rationale or "").lower():
        return f"{base} Quantity estimated as 1."
    return base


def _price_ecs(
    mapping: RowMapping,
    region: str,
    row_text: str,
    quantity: float,
    original_shape: tuple[int | None, float | None] | None = None,
) -> PriceResult:
    pricebook = load_pricebook()
    region_catalog = pricebook["pricingCatalog"].get(region)
    if not region_catalog:
        return PriceResult(status=QUOTE_STATUS_MISSING_PRICE, rationale="No local ECS pricing for this region.", confidence=mapping.confidence)
    spec_text = " ".join([mapping.huawei_spec or "", row_text])
    row_sku = _extract_sku(row_text)
    match = None
    rationale = ""
    cpu, memory = original_shape or (None, None)
    if cpu and memory:
        match = pick_ecs_match(region_catalog, cpu, memory)
        rationale = (
            f"Matched ECS by original row CPU/memory "
            f"({cpu}vCPU/{_format_quantity(memory)}GiB) to closest available flavor."
        )
    if not match and row_sku:
        match = next((item for item in region_catalog["ecs"] if str(item.get("spec", "")).lower() == row_sku.lower()), None)
        if match:
            rationale = "Matched ECS by explicit SKU in the original row."
    if not match:
        cpu, memory = _extract_compute_shape(spec_text)
        if cpu and memory:
            match = pick_ecs_match(region_catalog, cpu, memory)
            rationale = (
                f"Matched ECS by extracted CPU/memory "
                f"({cpu}vCPU/{_format_quantity(memory)}GiB) to closest available flavor."
            )
    if not match:
        return PriceResult(
            product_name="ECS",
            spec=mapping.huawei_spec,
            quantity=quantity,
            status=QUOTE_STATUS_MISSING_PRICE,
            rationale="Could not match ECS spec to local pricing.",
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
        rationale=_ecs_pricing_rationale(rationale or "ECS spec matched from local pricebook.", mapping),
        confidence=mapping.confidence,
        ecs_vcpu=int(match["vcpu"]),
        ecs_mem=float(match["memoryGiB"]),
    )


def _price_evs(mapping: RowMapping, region: str, row_text: str, quantity: float) -> PriceResult:
    region_catalog = load_pricebook()["pricingCatalog"].get(region)
    if not region_catalog:
        return PriceResult(product_name="EVS", quantity=quantity, status=QUOTE_STATUS_MISSING_PRICE, rationale="No local EVS pricing for this region.", confidence=mapping.confidence)
    spec_text = " ".join([mapping.huawei_spec or "", row_text])
    # Use spec alias normalization first, then fall back to legacy logic
    alias = _normalize_spec_alias("EVS", mapping.huawei_spec, row_text)
    if alias and alias in ("high-io", "ultra-high-io", "gpssd-v2", "gpssd", "sas"):
        key = alias
    else:
        key = "sas" if re.search(r"\bsas\b|high\s*i/o|高\s*i/o", spec_text, re.I) else "gpssd"
    capacity = _extract_capacity_gib(spec_text)
    item = next((price for price in region_catalog["evs"] if price["key"] == key), None)
    if not item:
        return PriceResult(product_name="EVS", quantity=quantity, status=QUOTE_STATUS_MISSING_PRICE, rationale="EVS type not covered.", confidence=mapping.confidence)
    if capacity is None:
        capacity = 1
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
        rationale=mapping.rationale or "EVS capacity priced from local pricebook.",
        confidence=mapping.confidence,
    )


def _price_catalog_product(mapping: RowMapping, region: str, quantity: float, row_text: str = "") -> PriceResult:
    product = mapping.huawei_product
    if not product:
        return PriceResult(quantity=quantity, status=QUOTE_STATUS_MANUAL, rationale="Could not identify Huawei Cloud product.", confidence=mapping.confidence)
    normalized_spec = _normalize_spec_alias(product, mapping.huawei_spec, row_text)
    if product == "CES":
        return PriceResult(
            product_name="CES",
            spec=normalized_spec or mapping.huawei_spec or "free",
            quantity=quantity,
            unit_price=0,
            ondemand_monthly=0,
            monthly_price=0,
            status=QUOTE_STATUS_QUOTED,
            rationale=mapping.rationale or "Cloud Eye basic monitoring is treated as free in this catalog.",
            confidence=mapping.confidence,
        )
    if product in {"VPN", "Cloud Connect", "DEW", "Anti-DDoS", "CFW", "DMS", "DCS", "GeminiDB", "DataArts Studio", "LTS"}:
        if normalized_spec in {"outbound-traffic"} or not query_flexible_pricing_catalog(product=product, region=region):
            return PriceResult(
                product_name=product,
                spec=normalized_spec or mapping.huawei_spec,
                quantity=quantity,
                status=QUOTE_STATUS_MANUAL,
                rationale=mapping.rationale or "Product mapping identified, but local price requires manual review.",
                confidence=mapping.confidence,
            )
    candidates = _confirmed_flexible_candidates(product, region, normalized_spec or mapping.huawei_spec, row_text)
    if not candidates:
        return PriceResult(
            product_name=product,
            spec=normalized_spec or mapping.huawei_spec,
            quantity=quantity,
            status=QUOTE_STATUS_MISSING_PRICE,
            rationale="Product or spec did not match any confirmed local price.",
            confidence=mapping.confidence,
        )
    item = candidates[0]
    price = float(item.price or 0)
    return PriceResult(
        product_name=product,
        spec=item.sku or item.tier or normalized_spec or mapping.huawei_spec,
        quantity=quantity,
        unit_price=round(price, 4),
        ondemand_monthly=round(price * quantity, 4),
        monthly_price=round(price * quantity, 4),
        ri_1y_monthly=None,
        status=QUOTE_STATUS_QUOTED,
        rationale=mapping.rationale or "Matched from local flexible pricing catalog.",
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
            rationale="CCI CPU did not match any confirmed local price.",
            confidence=mapping.confidence,
        )
    if resource_kind == "memory" and not memory_item:
        return PriceResult(
            product_name="CCI",
            spec=mapping.huawei_spec,
            quantity=quantity,
            status=QUOTE_STATUS_MISSING_PRICE,
            rationale="CCI Memory did not match any confirmed local price.",
            confidence=mapping.confidence,
        )
    if not resource_kind and (not cpu_item or not memory_item):
        return PriceResult(
            product_name="CCI",
            spec=mapping.huawei_spec,
            quantity=quantity,
            status=QUOTE_STATUS_MISSING_PRICE,
            rationale="CCI product or spec did not match any confirmed local price.",
            confidence=mapping.confidence,
        )
    if resource_kind == "cpu":
        if not cpu:
            return PriceResult(
                product_name="CCI",
                spec=mapping.huawei_spec,
                quantity=quantity,
                status=QUOTE_STATUS_MANUAL,
                rationale="CCI CPU row requires identifiable vCPU count.",
                confidence=mapping.confidence,
            )
        cpu_unit_price = float(cpu_item.price or 0)
        monthly = cpu_unit_price * cpu * SECONDS_PER_MONTH
        unit_price = cpu_unit_price * 3600
        spec = f"{cpu:g}vCPU"
        rationale = mapping.rationale or "Estimated from local CCI CPU per-second pricing catalog."
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
                rationale="CCI Memory row requires identifiable GiB count.",
                confidence=mapping.confidence,
            )
        memory_unit_price = float(memory_item.price or 0)
        monthly = memory_unit_price * memory * SECONDS_PER_MONTH
        unit_price = memory_unit_price * 3600
        spec = f"{memory:g}GiB"
        rationale = mapping.rationale or "Estimated from local CCI Memory per-second pricing catalog."
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
            rationale="CCI requires identifiable vCPU and memory specs.",
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
        rationale=mapping.rationale or "Estimated from local CCI CPU/Memory per-second pricing catalog.",
        confidence=mapping.confidence,
    )


def _price_row(mapping: RowMapping, row: RowCandidate, quote_context: dict[str, Any]) -> PriceResult:
    _debug_log("price_input", row_id=row.row_id, mapping=mapping.__dict__, row_cells=row.cells, quote_context=quote_context)
    _composite_kwargs = {"composite_family": mapping.composite_family, "composite_part": mapping.composite_part, "composite_group_key": mapping.composite_group_key}
    if not mapping.is_quote_row:
        result = PriceResult(status=QUOTE_STATUS_NON_QUOTE, rationale=mapping.rationale, confidence=mapping.confidence, **_composite_kwargs)
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
            **_composite_kwargs,
        )
        _debug_log("price_result", row_id=row.row_id, result=result.__dict__)
        return result
    if not mapping.huawei_product:
        result = PriceResult(status=QUOTE_STATUS_MANUAL, rationale=mapping.rationale or "Could not identify Huawei Cloud product.", confidence=mapping.confidence, **_composite_kwargs)
        _debug_log("price_result", row_id=row.row_id, result=result.__dict__)
        return result
    region = _extract_region(row, quote_context.get("region"))
    if not region:
        result = PriceResult(
            product_name=mapping.huawei_product,
            spec=mapping.huawei_spec,
            quantity=mapping.quantity,
            status=QUOTE_STATUS_MANUAL,
            rationale="Missing quote region.",
            confidence=mapping.confidence,
            **_composite_kwargs,
        )
        _debug_log("price_result", row_id=row.row_id, result=result.__dict__)
        return result
    quantity = mapping.quantity
    rationale = mapping.rationale
    if quantity is None or quantity <= 0:
        quantity = 1
        rationale = f"{rationale} Quantity estimated as 1.".strip()
        mapping = RowMapping(
            row_id=mapping.row_id,
            is_quote_row=mapping.is_quote_row,
            huawei_product=mapping.huawei_product,
            huawei_spec=mapping.huawei_spec,
            quantity=quantity,
            rationale=rationale,
            confidence=mapping.confidence,
            composite_family=mapping.composite_family,
            composite_part=mapping.composite_part,
            composite_group_key=mapping.composite_group_key,
        )
    if mapping.huawei_product == "ECS":
        result = _price_ecs(mapping, region, row_text, quantity, _extract_ecs_shape_from_row(row))
    elif mapping.huawei_product == "EVS":
        result = _price_evs(mapping, region, row_text, quantity)
    elif mapping.huawei_product == "CCE":
        result = _price_cce(mapping, region, row_text, quantity)
    elif mapping.huawei_product == "CCI":
        result = _price_cci(mapping, region, quantity, row_text)
    else:
        result = _price_catalog_product(mapping, region, quantity, row_text)
    # Propagate composite metadata from mapping to result
    if mapping.composite_family:
        result = PriceResult(
            product_name=result.product_name,
            spec=result.spec,
            quantity=result.quantity,
            unit_price=result.unit_price,
            ondemand_monthly=result.ondemand_monthly,
            monthly_price=result.monthly_price,
            ri_1y_monthly=result.ri_1y_monthly,
            status=result.status,
            rationale=result.rationale,
            confidence=result.confidence,
            ecs_vcpu=result.ecs_vcpu,
            ecs_mem=result.ecs_mem,
            composite_family=mapping.composite_family,
            composite_part=mapping.composite_part,
            composite_group_key=mapping.composite_group_key,
        )
    _debug_log("price_result", row_id=row.row_id, region=region, result=result.__dict__)
    return result


def _write_quote_headers(ws: Any, start_col: int, lang: str = "en") -> None:
    fill = PatternFill(fill_type="solid", fgColor="E6F0FF")
    font = Font(bold=True, color="1F2A44")
    columns = _row_quote_columns(lang)
    for offset, header in enumerate(columns):
        cell = ws.cell(row=1, column=start_col + offset, value=header)
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        width = max(12, min(24, len(header) + 4))
        ws.column_dimensions[get_column_letter(start_col + offset)].width = width


def _write_price_result(ws: Any, row_number: int, start_col: int, result: PriceResult, lang: str = "en") -> None:
    status_key = {
        QUOTE_STATUS_QUOTED: "quoted",
        QUOTE_STATUS_NON_QUOTE: "non_quote",
        QUOTE_STATUS_MISSING_PRICE: "missing_price",
        QUOTE_STATUS_MANUAL: "manual",
    }.get(result.status, "")
    display_status = _status_label(status_key, lang) if status_key else result.status
    values = [
        result.product_name,
        result.spec,
        result.quantity,
        result.unit_price,
        result.ondemand_monthly,
        result.monthly_price,
        result.ri_1y_monthly,
        display_status,
        result.rationale,
        result.confidence,
        result.ecs_vcpu,
        result.ecs_mem,
        result.composite_family,
        result.composite_part,
        result.composite_group_key,
        result.group_total_monthly_price,
        result.group_quote_status,
        result.group_component_count,
        result.group_quoted_component_count,
    ]
    for offset, value in enumerate(values):
        cell = ws.cell(row=row_number, column=start_col + offset, value=value)
        cell.alignment = Alignment(vertical="top", wrap_text=True)
        if isinstance(value, float):
            cell.number_format = "0.00"


# ---------------------------------------------------------------------------
# Composite group-level aggregation
# ---------------------------------------------------------------------------

GROUP_STATUS_QUOTED = "group_quoted"
GROUP_STATUS_PARTIALLY_QUOTED = "partially_quoted"
GROUP_STATUS_MANUAL_REVIEW = "manual_review"
GROUP_STATUS_MISSING_PRICE = "missing_price"


def _aggregate_composite_groups(results: list[PriceResult]) -> None:
    """Backfill group-level aggregation fields on composite sub-rows.

    For every distinct composite_group_key, compute:
      - group_total_monthly_price: sum of monthly_price for quoted sub-rows
      - group_component_count: total sub-rows in the group
      - group_quoted_component_count: sub-rows with status == Quoted
      - group_quote_status: derived from the above

    Then backfill these values onto every sub-row in the group and
    append a short group-level rationale note.
    """
    # Collect groups
    groups: dict[str, list[int]] = {}
    for idx, r in enumerate(results):
        if r.composite_group_key:
            groups.setdefault(r.composite_group_key, []).append(idx)

    if not groups:
        return

    for _key, indices in groups.items():
        total_count = len(indices)
        quoted_indices = [i for i in indices if results[i].status == QUOTE_STATUS_QUOTED]
        quoted_count = len(quoted_indices)
        total_price = round(sum(results[i].monthly_price or 0 for i in quoted_indices), 4)

        has_manual = any(results[i].status == QUOTE_STATUS_MANUAL for i in indices)
        has_missing = any(results[i].status == QUOTE_STATUS_MISSING_PRICE for i in indices)

        # Derive group status
        if quoted_count == total_count:
            group_status = GROUP_STATUS_QUOTED
        elif quoted_count > 0:
            group_status = GROUP_STATUS_PARTIALLY_QUOTED
        elif has_manual:
            group_status = GROUP_STATUS_MANUAL_REVIEW
        else:
            group_status = GROUP_STATUS_MISSING_PRICE

        # Build short rationale suffix
        if group_status == GROUP_STATUS_QUOTED:
            group_note = "Composite group total computed from quoted components."
        elif group_status == GROUP_STATUS_PARTIALLY_QUOTED:
            group_note = "Composite group partially quoted; some components still need review."
        elif group_status == GROUP_STATUS_MANUAL_REVIEW:
            group_note = "Composite group requires manual review."
        else:
            group_note = "Composite group has missing prices."

        # Backfill every sub-row
        for i in indices:
            r = results[i]
            r.group_total_monthly_price = total_price
            r.group_quote_status = group_status
            r.group_component_count = total_count
            r.group_quoted_component_count = quoted_count
            if group_note and group_note not in (r.rationale or ""):
                r.rationale = f"{r.rationale} {group_note}".strip()


def _backfill_group_columns(
    workbook: Any,
    rows: list[RowCandidate],
    results: list[PriceResult],
    priced_row_ids: set[str],
    original_widths: dict[str, int],
    lang: str,
) -> None:
    """After _aggregate_composite_groups, write group-level fields into the workbook cells.

    The group columns are the last 4 columns in the quote section.
    We overwrite those cells for every priced row that has group data.
    """
    columns = _row_quote_columns(lang)
    # Find the offset of the 4 group columns within ROW_QUOTE_COLUMNS
    group_col_names = [
        "group_total_monthly_price",
        "group_quote_status",
        "group_component_count",
        "group_quoted_component_count",
    ]
    group_col_offsets = [columns.index(name) for name in group_col_names]

    # Build a mapping from row_id to PriceResult
    # results are appended in pricing order; we need to match by row_id
    # We iterate rows and results together — results list is built one-per-priced-row
    result_by_row_id: dict[str, PriceResult] = {}
    row_idx = 0
    for row in rows:
        if row.row_id in priced_row_ids:
            if row_idx < len(results):
                result_by_row_id[row.row_id] = results[row_idx]
                row_idx += 1

    for row in rows:
        result = result_by_row_id.get(row.row_id)
        if result is None:
            continue
        if result.group_total_monthly_price is None and result.group_quote_status is None:
            continue
        ws = workbook[row.sheet]
        start_col = original_widths[row.sheet] + 1
        group_values = [
            result.group_total_monthly_price,
            result.group_quote_status,
            result.group_component_count,
            result.group_quoted_component_count,
        ]
        for offset_in_section, value in zip(group_col_offsets, group_values):
            cell = ws.cell(row=row.row_number, column=start_col + offset_in_section, value=value)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if isinstance(value, float):
                cell.number_format = "0.00"


# ---------------------------------------------------------------------------
# Composite Summary sheet
# ---------------------------------------------------------------------------

COMPOSITE_SUMMARY_SHEET_NAME = "Composite Summary"

COMPOSITE_SUMMARY_COLUMNS = [
    "composite_group_key",
    "composite_family",
    "group_quote_status",
    "group_total_monthly_price",
    "group_component_count",
    "group_quoted_component_count",
    "source_sheet",
    "source_rows",
    "group_parts",
    "group_products",
    "group_notes",
]


@dataclass
class CompositeSummaryRow:
    composite_group_key: str
    composite_family: str
    group_quote_status: str
    group_total_monthly_price: float
    group_component_count: int
    group_quoted_component_count: int
    source_sheet: str
    source_rows: str  # e.g. "2,3,4"
    group_parts: str  # e.g. "cpu,memory,storage"
    group_products: str  # e.g. "RDS,EVS"
    group_notes: str = ""


def _build_composite_summary_rows(
    results: list[PriceResult],
    rows: list[RowCandidate],
    priced_row_ids: set[str],
) -> list[CompositeSummaryRow]:
    """Build one summary row per composite_group_key from already-aggregated PriceResults.

    Preserves first-occurrence order of groups as they appear in the results list.
    """
    # Build row_id → PriceResult mapping (same logic as _backfill_group_columns)
    result_by_row_id: dict[str, PriceResult] = {}
    row_idx = 0
    for row in rows:
        if row.row_id in priced_row_ids:
            if row_idx < len(results):
                result_by_row_id[row.row_id] = results[row_idx]
                row_idx += 1

    # Build row_id → RowCandidate mapping
    candidate_by_id: dict[str, RowCandidate] = {row.row_id: row for row in rows}

    # Collect groups in first-occurrence order
    seen_keys: set[str] = set()
    ordered_keys: list[str] = []
    # We iterate results to preserve order; but we also need the RowCandidate for row_number/sheet
    # Use result_by_row_id to go from result → row_id → candidate
    row_id_list = [row.row_id for row in rows if row.row_id in priced_row_ids]

    for row_id in row_id_list:
        result = result_by_row_id.get(row_id)
        if not result or not result.composite_group_key:
            continue
        if result.composite_group_key not in seen_keys:
            seen_keys.add(result.composite_group_key)
            ordered_keys.append(result.composite_group_key)

    if not ordered_keys:
        return []

    # For each group key, collect all sub-rows
    group_members: dict[str, list[tuple[RowCandidate, PriceResult]]] = {}
    for row_id in row_id_list:
        result = result_by_row_id.get(row_id)
        if not result or not result.composite_group_key:
            continue
        candidate = candidate_by_id.get(row_id)
        if candidate:
            group_members.setdefault(result.composite_group_key, []).append((candidate, result))

    summary_rows: list[CompositeSummaryRow] = []
    for key in ordered_keys:
        members = group_members.get(key, [])
        if not members:
            continue
        # Use the first result's aggregated group fields (they're all the same within a group)
        first_result = members[0][1]
        # Source sheet: use the sheet of the first member
        source_sheet = members[0][0].sheet
        # Source rows: comma-separated row numbers
        source_rows = ",".join(str(m[0].row_number) for m in members)
        # Group parts: deduplicated, comma-separated
        parts_set: list[str] = []
        for _, r in members:
            if r.composite_part and r.composite_part not in parts_set:
                parts_set.append(r.composite_part)
        group_parts = ",".join(parts_set)
        # Group products: deduplicated, comma-separated
        products_set: list[str] = []
        for _, r in members:
            if r.product_name and r.product_name not in products_set:
                products_set.append(r.product_name)
        group_products = ",".join(products_set)
        # Group notes: short description
        group_notes = ""
        if first_result.group_quote_status == GROUP_STATUS_QUOTED:
            group_notes = "All components quoted."
        elif first_result.group_quote_status == GROUP_STATUS_PARTIALLY_QUOTED:
            group_notes = "Some components need review."
        elif first_result.group_quote_status == GROUP_STATUS_MANUAL_REVIEW:
            group_notes = "All components require manual review."
        elif first_result.group_quote_status == GROUP_STATUS_MISSING_PRICE:
            group_notes = "All components have missing prices."

        summary_rows.append(CompositeSummaryRow(
            composite_group_key=key,
            composite_family=first_result.composite_family or "",
            group_quote_status=first_result.group_quote_status or "",
            group_total_monthly_price=first_result.group_total_monthly_price or 0,
            group_component_count=first_result.group_component_count or 0,
            group_quoted_component_count=first_result.group_quoted_component_count or 0,
            source_sheet=source_sheet,
            source_rows=source_rows,
            group_parts=group_parts,
            group_products=group_products,
            group_notes=group_notes,
        ))

    return summary_rows


def _write_composite_summary_sheet(
    workbook: Any,
    summary_rows: list[CompositeSummaryRow],
) -> None:
    """Write (or replace) the Composite Summary sheet in the workbook."""
    # Remove existing sheet if present to avoid duplicates
    if COMPOSITE_SUMMARY_SHEET_NAME in workbook.sheetnames:
        del workbook[COMPOSITE_SUMMARY_SHEET_NAME]

    ws = workbook.create_sheet(COMPOSITE_SUMMARY_SHEET_NAME)

    # Write headers
    header_fill = PatternFill(fill_type="solid", fgColor="E6F0FF")
    header_font = Font(bold=True, color="1F2A44")
    for col_idx, header in enumerate(COMPOSITE_SUMMARY_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        width = max(12, min(30, len(header) + 4))
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # Write data rows
    for row_idx, sr in enumerate(summary_rows, start=2):
        values = [
            sr.composite_group_key,
            sr.composite_family,
            sr.group_quote_status,
            sr.group_total_monthly_price,
            sr.group_component_count,
            sr.group_quoted_component_count,
            sr.source_sheet,
            sr.source_rows,
            sr.group_parts,
            sr.group_products,
            sr.group_notes,
        ]
        for col_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
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


def annotate_row_quote_workbook(upload: dict[str, Any], quote_context: dict[str, Any], progress_callback: Any = None, stage_callback: Any = None, cancel_check: Any = None, sheet_selection: SheetSelection | None = None) -> tuple[QuoteWorkbook, RowQuoteSummary]:
    filename = str(upload.get("filename") or "flexible.xlsx")
    if not filename.lower().endswith(".xlsx"):
        raise ValueError("Only Excel .xlsx files are supported for row-level flexible quote annotation.")
    content = upload.get("content") or b""
    if not content:
        raise ValueError("Uploaded Excel file is empty.")

    workbook = load_workbook(BytesIO(content))

    if sheet_selection is None:
        sheet_selection = SheetSelection()

    try:
        selected_sheet_names = resolve_sheet_selection(
            [ws.title for ws in workbook.worksheets],
            sheet_selection,
        )
    except SheetSelectionError as exc:
        raise ValueError(str(exc)) from exc

    if callable(stage_callback):
        stage_callback("collect_rows")
    rows, original_widths = _collect_rows(workbook, selected_sheet_names=selected_sheet_names)
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

    lang = _quote_language(quote_context)

    for ws in [ws for ws in workbook.worksheets if ws.title in selected_sheet_names]:
        start_col = original_widths[ws.title] + 1
        _write_quote_headers(ws, start_col, lang)

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
                        composite_family=mapping.composite_family, composite_part=mapping.composite_part,
                        composite_group_key=mapping.composite_group_key,
                    )
                if not mapping.huawei_product:
                    mapping = RowMapping(
                        row_id=mapping.row_id, is_quote_row=mapping.is_quote_row,
                        huawei_product=fallback.huawei_product, huawei_spec=mapping.huawei_spec,
                        quantity=mapping.quantity, rationale=mapping.rationale, confidence=mapping.confidence,
                        composite_family=mapping.composite_family, composite_part=mapping.composite_part,
                        composite_group_key=mapping.composite_group_key,
                    )
                if not mapping.huawei_spec:
                    mapping = RowMapping(
                        row_id=mapping.row_id, is_quote_row=mapping.is_quote_row,
                        huawei_product=mapping.huawei_product, huawei_spec=fallback.huawei_spec,
                        quantity=mapping.quantity, rationale=mapping.rationale, confidence=mapping.confidence,
                        composite_family=mapping.composite_family, composite_part=mapping.composite_part,
                        composite_group_key=mapping.composite_group_key,
                    )
                final_mappings[row.row_id] = mapping
            result = _price_row(mapping, rows_by_id[row.row_id], quote_context)
            results.append(result)
            ws = workbook[row.sheet]
            _write_price_result(ws, row.row_number, original_widths[row.sheet] + 1, result, lang)
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

    # Aggregate composite group-level fields and backfill into workbook
    _aggregate_composite_groups(results)
    _backfill_group_columns(workbook, rows, results, priced_row_ids, original_widths, lang)

    # Write Composite Summary sheet
    composite_summary_rows = _build_composite_summary_rows(results, rows, priced_row_ids)
    _write_composite_summary_sheet(workbook, composite_summary_rows)

    output = BytesIO()
    workbook.save(output)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_stem = _safe_ascii_filename(filename)
    summary = _summarize(results)
    _debug_log("annotate_complete", filename=filename, summary=summary.model_dump())
    return QuoteWorkbook(filename=f"{safe_stem}-huawei-row-quote-{stamp}.xlsx", content=output.getvalue()), summary
