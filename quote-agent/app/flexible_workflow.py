from __future__ import annotations

import json
import logging
import os
import re
from copy import copy
from pathlib import Path
from datetime import datetime, timezone
from io import BytesIO, StringIO
from typing import Any, TypedDict

import httpx
import pandas as pd
from openpyxl import load_workbook
from langgraph.graph import END, START, StateGraph

from app.flexible_pricing import query_flexible_pricing_catalog
from app.models import (
    AuditEntry,
    ComputeSpec,
    FlexibleDocumentDiagnostic,
    FlexibleInputProfile,
    FlexibleQuoteBlocker,
    FlexibleQuoteContext,
    FlexibleQuoteDiagnostics,
    FlexibleQuoteLine,
    FlexibleQuotePreviewResponse,
    FlexibleSchemaMapping,
    FlexibleQuoteSummary,
    FlexibleReviewRequest,
    GenericSpec,
    HumanFeedback,
    MatchedProduct,
    NetworkSpec,
    PriceComponent,
    QuoteWorkbook,
    RequirementItem,
    StorageSpec,
)

SUPPORTED_EXTENSIONS = {"xlsx", "csv", "txt"}

# ---------------------------------------------------------------------------
# Template profile configs (Phase E2)
# ---------------------------------------------------------------------------

_BILLING_ECS_HEADERS = [
    "Source Resource", "Source Lines", "Source Qty", "Source Unit", "Source SKU",
    "Huawei Product", "Huawei Spec Hint", "Target Qty", "Target Unit",
    "Matched SKU", "Matched Tier", "Status", "Unit Price USD", "Monthly Price USD",
]

_BILLING_STATUS_SORT_ORDER = {"quoted": 0, "unquoted": 1, "manual_review": 2, "unsupported": 3}

_TEMPLATE_PROFILES: dict[str, dict[str, Any]] = {
    "rvtools_default": {
        "template_path": Path(__file__).resolve().parents[1] / "templates" / "rvtools_quote_template.xlsx",
        "required_sheets": ["Summary", "HWC", "ECS", "Información"],
        "ecs_data_start_row": 3,
        "ecs_total_row": 21,
        "ecs_template_row": 20,
        "ecs_headers": _BILLING_ECS_HEADERS,
        "hwc_use_blended_unit_price": True,
        "summary_cells": {"title": "B4", "total_ondemand": "C7", "total_ri": "D7", "metrics": "B9", "metrics_c": "C9", "metrics_d": "D9", "extra_c": "C11", "extra_d": "D11", "list_c": "C12", "list_d": "D12", "description": "B16", "notes": "B19"},
    },
}

FLEXIBLE_PREVIEW_STAGES = [
    "ingest_files",
    "load_pricebook",
    "parse_documents",
    "understand_input",
    "extract_requirement_items",
    "normalize_requirements",
    "deduplicate_items",
    "map_to_huawei_product",
    "validate_quote_readiness",
    "return_blockers",
    "resolve_price_components",
    "quote_items",
    "summarize_quote",
]
PRODUCT_SYNONYMS = {
    "ecs": "ECS",
    "elastic cloud server": "ECS",
    "云服务器": "ECS",
    "弹性云服务器": "ECS",
    "弹性计算": "ECS",
    "cvm": "ECS",
    "虚拟机": "ECS",
    "服务器": "ECS",
    "计算": "ECS",
    "gpu": "ECS",
    "evs": "EVS",
    "elastic volume service": "EVS",
    "云硬盘": "EVS",
    "磁盘": "EVS",
    "存储": "EVS",
    "cbr": "CBR",
    "cloud backup and recovery": "CBR",
    "云备份": "CBR",
    "备份": "CBR",
    "eip": "EIP",
    "elastic ip": "EIP",
    "公网ip": "EIP",
    "弹性公网": "EIP",
    "弹性公网ip": "EIP",
    "cce": "CCE",
    "cloud container engine": "CCE",
    "容器": "CCE",
    "容器引擎": "CCE",
    "cci": "CCI",
    "cloud container instance": "CCI",
    "serverless": "CCI",
    "serverless container": "CCI",
    "容器实例": "CCI",
    "serverless容器": "CCI",
    "pod-cpu": "CCI",
    "pod-memory": "CCI",
    "sfs turbo": "SFS Turbo",
    "弹性文件": "SFS Turbo",
    "文件存储": "SFS Turbo",
    "nat gateway": "NAT Gateway",
    "nat网关": "NAT Gateway",
    "vpn": "VPN",
    "vpn网关": "VPN",
    "direct connect as a service": "Direct Connect as a Service",
    "dcas": "Direct Connect as a Service",
    "云专线": "Direct Connect as a Service",
    "专线": "Direct Connect as a Service",
    "rds": "RDS",
    "关系型数据库": "RDS",
    "云数据库": "RDS",
    "数据库": "RDS",
    "dds": "DDS",
    "document database service": "DDS",
    "文档数据库": "DDS",
    "dws": "DWS",
    "data warehouse service": "DWS",
    "数据仓库": "DWS",
    "obs": "OBS",
    "object storage service": "OBS",
    "对象存储": "OBS",
    "elb": "ELB",
    "elastic load balance": "ELB",
    "负载均衡": "ELB",
    "waf": "WAF",
    "web应用防火墙": "WAF",
    "hss": "HSS",
    "host security service": "HSS",
    "主机安全": "HSS",
    "vpc": "VPC",
    "虚拟私有云": "VPC",
    "workspace": "Workspace",
    "云桌面": "Workspace",
    "drs": "DRS",
    "数据复制服务": "DRS",
    "css": "CSS",
    "云搜索服务": "CSS",
    "lts": "LTS",
    "log tank service": "LTS",
    "日志服务": "LTS",
    "dli": "DLI",
    "data lake insight": "DLI",
    "数据湖计算": "DLI",
    "dcs": "DCS",
    "distributed cache service": "DCS",
    "redis": "DCS",
    "云数据库redis": "DCS",
    "geminidb": "GeminiDB",
    "gemini": "GeminiDB",
    "ctsdb": "GeminiDB",
    "时序数据库": "GeminiDB",
    "dms": "DMS",
    "distributed message service": "DMS",
    "kafka": "DMS",
    "ckafka": "DMS",
    "消息服务": "DMS",
    "dataarts studio": "DataArts Studio",
    "dataarts": "DataArts Studio",
    "wedata": "DataArts Studio",
    "数据开发治理": "DataArts Studio",
    "cloud connect": "Cloud Connect",
    "云联网": "Cloud Connect",
    "ccn": "Cloud Connect",
    "kms": "DEW",
    "dew": "DEW",
    "data encryption workshop": "DEW",
    "密钥管理": "DEW",
    "anti-ddos": "Anti-DDoS",
    "ddos": "Anti-DDoS",
    "ddos防护": "Anti-DDoS",
    "cfw": "CFW",
    "cloud firewall": "CFW",
    "云防火墙": "CFW",
    "ces": "CES",
    "cloud eye": "CES",
    "云监控": "CES",
    "modelarts": "ModelArts",
    "functiongraph": "FunctionGraph",
    "函数": "FunctionGraph",
    "gaussdb": "GaussDB",
    "高斯数据库": "GaussDB",
}
SPEC_REQUIRED_PRODUCTS = {"ECS", "EVS", "RDS", "SFS Turbo", "DDS", "DWS", "OBS", "CCE", "CCI", "DCS", "GeminiDB", "DMS", "DataArts Studio"}
NETWORK_PRODUCTS = {"EIP", "NAT Gateway", "VPN", "Direct Connect as a Service", "ELB", "VPC", "Cloud Connect"}
DEFAULT_SCHEMA_ALIASES = {
    "product": [
        "华为云.产品名称",
        "华为云.产品",
        "华为云.服务",
        "product",
        "service",
        "service name",
        "item",
        "resource",
        "product name",
        "service type",
        "产品名称",
        "产品",
        "云产品",
        "服务名称",
        "服务",
        "产品类别",
    ],
    "quantity": [
        "华为云.数量",
        "华为云.实例数",
        "quantity",
        "qty",
        "count",
        "instances",
        "instance count",
        "number",
        "数量",
        "个数",
        "实例数",
        "台数",
    ],
    "region": [
        "华为云.区域",
        "华为云.地域",
        "region",
        "site",
        "country",
        "deployment country",
        "location",
        "区域",
        "地域",
        "国家",
        "部署区域",
    ],
    "spec": [
        "华为云.规格",
        "华为云.配置",
        "华为云.sku",
        "spec",
        "sku",
        "flavor",
        "size",
        "configuration",
        "instance type",
        "规格",
        "配置",
        "实例规格",
        "型号",
    ],
    "notes": ["notes", "remark", "description", "comments", "备注", "说明", "描述"],
}
HUAWEI_COLUMN_KEYWORDS = {
    "product": ["产品名称", "产品", "服务", "product", "service"],
    "quantity": ["数量", "实例数", "个数", "quantity", "qty"],
    "region": ["区域", "地域", "region"],
    "spec": ["规格", "配置", "sku", "flavor", "configuration"],
    "notes": ["备注", "说明", "notes", "remark"],
}
logger = logging.getLogger(__name__)


class FlexibleQuoteState(TypedDict, total=False):
    files: list[dict[str, Any]]
    quote_context: FlexibleQuoteContext
    parsed_documents: list[dict[str, Any]]
    understanding: dict[str, Any]
    requirements: list[dict[str, Any]]
    matched_products: list[dict[str, Any]]
    quote_ready_items: list[dict[str, Any]]
    quote_blockers: list[dict[str, Any]]
    price_catalog: list[dict[str, Any]]
    price_components: list[dict[str, Any]]
    quote_lines: list[dict[str, Any]]
    unquoted_items: list[dict[str, Any]]
    summary: dict[str, Any]
    audit_log: list[dict[str, Any]]
    workbook: QuoteWorkbook
    review_feedback: list[dict[str, Any]]
    progress_callback: Any
    diagnostics: dict[str, Any]
    billing_lines: list[dict[str, Any]]
    standardized_billing_resources: list[dict[str, Any]]
    mapped_billing_resources: list[dict[str, Any]]


class FlexibleWorkflowError(ValueError):
    def __init__(self, message: str, *, stage: str, detail: str | None = None, diagnostics: dict[str, Any] | None = None):
        super().__init__(detail or message)
        self.message = message
        self.stage = stage
        self.detail = detail or message
        self.diagnostics = diagnostics or {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_audit(state: FlexibleQuoteState, stage: str, message: str, **details: Any) -> list[dict[str, Any]]:
    audit = list(state.get("audit_log", []))
    audit.append(AuditEntry(timestamp=_now_iso(), stage=stage, message=message, details=details).model_dump())
    return audit


def _report_progress(state: FlexibleQuoteState, stage: str, status: str, message: str) -> None:
    callback = state.get("progress_callback")
    if callable(callback):
        callback(stage, status, message)


def _diagnostics(state: FlexibleQuoteState) -> FlexibleQuoteDiagnostics:
    return FlexibleQuoteDiagnostics.model_validate(state.get("diagnostics", {}))


def _update_diagnostics(state: FlexibleQuoteState, **updates: Any) -> dict[str, Any]:
    diagnostics = _diagnostics(state)
    merged = diagnostics.model_copy(update=updates)
    return merged.model_dump()


def _serialize_cell(value: Any, *, limit: int = 80) -> str:
    text = str(value).strip()
    return text[:limit] if len(text) > limit else text


def _normalize_product_name(raw_name: str) -> str | None:
    key = re.sub(r"\s+", " ", raw_name.strip().lower())
    direct = PRODUCT_SYNONYMS.get(key)
    if direct:
        return direct
    compact_key = re.sub(r"[\s/._-]+", "", key)
    candidates = []
    for synonym, product in PRODUCT_SYNONYMS.items():
        compact_synonym = re.sub(r"[\s/._-]+", "", synonym.lower())
        if compact_synonym and compact_synonym in compact_key:
            candidates.append((len(compact_synonym), product))
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return None


def _normalize_region(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    aliases = {
        "mexico": "mexico",
        "mx": "mexico",
        "chile": "chile",
        "cl": "chile",
        "brazil": "brazil",
        "br": "brazil",
    }
    return aliases.get(normalized)


def _append_note(notes: str | None, addition: str) -> str:
    return f"{notes} | {addition}".strip(" |") if notes else addition


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not pd.isna(value):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    matched = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    return float(matched.group(0)) if matched else None


def _parse_spec_text(product: str | None, spec_text: str | None):
    text = (spec_text or "").strip()
    if not text:
        return None
    sku_match = re.search(r"([a-z]\d\.\d+u\.\d+g|mysql\.[a-z0-9.]+|gp-ssd|sas|cbr-basic|eip-standard|nat-basic|vpn-basic|dcas-\dg|cce-standard|sfs-turbo-standard)", text.lower())
    sku = sku_match.group(1) if sku_match else None
    if product == "ECS":
        cpu_match = re.search(r"(\d+)\s*(?:vcpu|cpu|core|核|c)", text, re.I)
        cpu = _to_float(cpu_match.group(1)) if cpu_match else None
        memory = _to_float(re.search(r"(\d+(?:\.\d+)?)\s*(?:gib|gb|g)", text, re.I).group(1)) if re.search(r"(\d+(?:\.\d+)?)\s*(?:gib|gb|g)", text, re.I) else None
        return ComputeSpec(vcpu=int(cpu) if cpu else None, memory_gib=memory, sku=sku)
    if product in {"EVS", "SFS Turbo"}:
        capacity = _to_float(text)
        return StorageSpec(capacity_gib=capacity, tier=text if not sku else None, sku=sku)
    if product in NETWORK_PRODUCTS:
        bandwidth = _to_float(text)
        return NetworkSpec(bandwidth_mbps=bandwidth, tier=text if not sku else None, sku=sku)
    return GenericSpec(tier=text, sku=sku, description=text)


def ingest_files(state: FlexibleQuoteState) -> FlexibleQuoteState:
    _report_progress(state, "ingest_files", "running", "Validating uploaded files.")
    files = state.get("files", [])
    normalized: list[dict[str, Any]] = []
    for item in files:
        filename = item["filename"]
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type for flexible quote: {filename}")
        normalized.append({"filename": filename, "content": item["content"], "extension": ext})
    message = f"Ingested {len(normalized)} file(s)."
    _report_progress(state, "ingest_files", "completed", message)
    return {"files": normalized, "audit_log": _append_audit(state, "ingest_files", message)}


def load_pricebook(state: FlexibleQuoteState) -> FlexibleQuoteState:
    _report_progress(state, "load_pricebook", "running", "Loading local pricing catalog.")
    catalog = [item.model_dump() for item in query_flexible_pricing_catalog()]
    message = f"Loaded {len(catalog)} local catalog row(s)."
    _report_progress(state, "load_pricebook", "completed", message)
    return {
        "price_catalog": catalog,
        "audit_log": _append_audit(state, "load_pricebook", message),
    }


def _clean_header_cell(value: Any) -> str:
    text = str(value).strip()
    if not text or text.lower().startswith("unnamed:"):
        return ""
    return re.sub(r"\s+", " ", text)


def _row_values(frame: pd.DataFrame, row_index: int) -> list[str]:
    return [_clean_header_cell(value) for value in frame.iloc[row_index].tolist()]


def _count_header_keywords(values: list[str]) -> int:
    keywords = [
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
        "地域",
        "规格",
        "配置",
        "腾讯云",
        "华为云",
        "aws",
        "azure",
    ]
    joined = " ".join(values).lower()
    return sum(1 for keyword in keywords if keyword.lower() in joined)


def _detect_excel_header_depth(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 1
    first_rows = min(4, len(frame))
    first = _row_values(frame, 0)
    second = _row_values(frame, 1) if first_rows > 1 else []
    first_joined = " ".join(first).lower()
    second_joined = " ".join(second).lower()
    has_group_header = any(marker in first_joined for marker in ["腾讯云", "华为云", "aws", "azure", "gcp"])
    has_second_field_header = _count_header_keywords(second) >= 2 or any(
        marker in second_joined for marker in ["数量", "规格", "区域", "产品", "qty", "spec", "region", "product"]
    )
    if has_group_header and has_second_field_header:
        return 2
    return 1


def _forward_fill_header(values: list[str]) -> list[str]:
    filled: list[str] = []
    current = ""
    for value in values:
        if value:
            current = value
        filled.append(current)
    return filled


def _make_unique_columns(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    unique: list[str] = []
    for index, raw_column in enumerate(columns, start=1):
        base = raw_column or f"column_{index}"
        count = seen.get(base, 0)
        seen[base] = count + 1
        unique.append(base if count == 0 else f"{base}#{count + 1}")
    return unique


def _flatten_excel_columns(frame: pd.DataFrame, header_depth: int) -> list[str]:
    header_rows = [_forward_fill_header(_row_values(frame, row_index)) for row_index in range(header_depth)]
    columns: list[str] = []
    width = len(frame.columns)
    for column_index in range(width):
        parts: list[str] = []
        for row in header_rows:
            value = row[column_index] if column_index < len(row) else ""
            if value and value not in parts:
                parts.append(value)
        columns.append(".".join(parts))
    return _make_unique_columns(columns)


def _parse_excel_workbook(content: bytes, filename: str) -> list[dict[str, Any]]:
    workbook = pd.read_excel(BytesIO(content), sheet_name=None, header=None)
    documents: list[dict[str, Any]] = []
    for sheet_name, raw_frame in workbook.items():
        frame = raw_frame.fillna("")
        if frame.empty:
            documents.append({"filename": filename, "sheet": sheet_name, "columns": [], "rows": []})
            continue
        header_depth = _detect_excel_header_depth(frame)
        columns = _flatten_excel_columns(frame, header_depth)
        data_frame = frame.iloc[header_depth:].copy()
        data_frame.columns = columns
        rows: list[dict[str, Any]] = []
        for offset, row in enumerate(data_frame.to_dict(orient="records"), start=header_depth + 1):
            normalized_row = {str(key): value for key, value in row.items()}
            if not any(str(value).strip() for value in normalized_row.values()):
                continue
            normalized_row["_line_number"] = offset
            rows.append(normalized_row)
        documents.append(
            {
                "filename": filename,
                "sheet": sheet_name,
                "columns": [str(column) for column in columns],
                "rows": rows,
                "header_depth": header_depth,
                "header_preview": [
                    [_serialize_cell(value) for value in frame.iloc[index].tolist()]
                    for index in range(min(header_depth, len(frame)))
                ],
            }
        )
    return documents


def _documents_contain_any(parsed_documents: list[dict[str, Any]], markers: list[str]) -> bool:
    text_parts: list[str] = []
    for document in parsed_documents:
        text_parts.extend(str(column) for column in document.get("columns", []))
        for header_row in document.get("header_preview", []):
            text_parts.extend(str(value) for value in header_row)
        for row in document.get("rows", [])[:5]:
            text_parts.extend(str(value) for value in row.values())
    text = " ".join(text_parts).lower()
    return any(marker.lower() in text for marker in markers)


def _infer_input_profile(parsed_documents: list[dict[str, Any]]) -> FlexibleInputProfile:
    comparison_markers = ["腾讯云", "华为云", "aws", "azure", "gcp", "to huawei", "comparison", "对比"]
    if _documents_contain_any(parsed_documents, comparison_markers):
        return FlexibleInputProfile(
            quote_purpose="unit_price_comparison",
            quantity_policy="default_to_one_for_unit_price",
            confidence=0.8,
            rationale="Input appears to compare source cloud and Huawei Cloud product rows.",
        )
    return FlexibleInputProfile(
        quote_purpose="purchase_quote",
        quantity_policy="required",
        confidence=0.5,
        rationale="Input does not clearly indicate a unit price comparison.",
    )


def _coerce_input_profile(raw_profile: Any, fallback: FlexibleInputProfile) -> FlexibleInputProfile:
    if not isinstance(raw_profile, dict):
        return fallback
    try:
        return FlexibleInputProfile.model_validate(raw_profile)
    except Exception:
        purpose = str(raw_profile.get("quote_purpose") or raw_profile.get("purpose") or "").lower()
        policy = str(raw_profile.get("quantity_policy") or "").lower()
        if "comparison" in purpose or "unit" in policy:
            return FlexibleInputProfile(
                quote_purpose="unit_price_comparison",
                quantity_policy="default_to_one_for_unit_price",
                confidence=_to_float(raw_profile.get("confidence")) or fallback.confidence,
                rationale=str(raw_profile.get("rationale") or "LLM indicated a comparison-style input."),
            )
        return fallback


def _strip_sep_header(text: str) -> tuple[str, bool]:
    """Remove a leading ``SEP=,`` line if present; return (cleaned_text, had_sep)."""
    lines = text.splitlines()
    if lines and re.match(r"^SEP\s*=\s*,", lines[0].strip()):
        return "\n".join(lines[1:]), True
    return text, False


def _drop_empty_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Drop columns whose name is blank / Unnamed:* or that are entirely empty."""
    to_drop: list[str] = []
    for col in frame.columns:
        col_str = str(col).strip()
        if not col_str or col_str.lower().startswith("unnamed:"):
            to_drop.append(col)
            continue
        if frame[col].astype(str).str.strip().replace("", pd.NA).isna().all():
            to_drop.append(col)
    return frame.drop(columns=to_drop) if to_drop else frame


def _parse_csv_document(content: bytes, filename: str) -> dict[str, Any]:
    """Parse a CSV file into a single document dict.

    Handles:
    - UTF-8 BOM (``utf-8-sig`` decode)
    - Leading ``SEP=,`` directive line
    - Trailing empty columns
    - Adds ``_line_number`` to every data row (1-based, header = row 1)
    - Adds lightweight metadata (``document_type``, ``dialect``) when detected
    """
    text = content.decode("utf-8-sig", errors="ignore")
    text, had_sep = _strip_sep_header(text)
    frame = pd.read_csv(StringIO(text))
    frame = _drop_empty_columns(frame)
    frame = frame.fillna("")

    columns = [str(col) for col in frame.columns]
    rows: list[dict[str, Any]] = []
    for offset, record in enumerate(frame.to_dict(orient="records"), start=2):
        row = {str(k): v for k, v in record.items()}
        row["_line_number"] = offset
        rows.append(row)

    doc: dict[str, Any] = {
        "filename": filename,
        "sheet": "csv",
        "columns": columns,
        "rows": rows,
    }
    if had_sep:
        doc["document_type"] = "azure_billing_csv"
        doc["dialect"] = "excel_sep_header"
    return doc


# ---------------------------------------------------------------------------
# Billing document detection & standardization (Phase B)
# ---------------------------------------------------------------------------

_BILLING_COLUMN_PATTERNS: list[set[str]] = [
    # Azure billing
    {"PRODUCT FAMILY", "PRODUCT TYPE", "PRODUCT SKU", "UNIT TYPE"},
    # AWS Cost Explorer (common columns)
    {"product/ProductFamily", "product/Sku", "lineItem/UsageType"},
    # GCP billing export
    {"service.description", "sku.description", "usage.unit"},
]


def _detect_billing_document(document: dict[str, Any]) -> bool:
    """Return True if the document looks like a cloud billing export."""
    # Explicit metadata from Phase A
    doc_type = document.get("document_type", "")
    if doc_type and "billing" in doc_type:
        return True
    # Column-pattern heuristic (vendor-agnostic)
    columns_upper = {c.upper().strip() for c in document.get("columns", [])}
    for pattern in _BILLING_COLUMN_PATTERNS:
        if {c.upper().strip() for c in pattern}.issubset(columns_upper):
            return True
    return False


def _infer_billing_vendor(document: dict[str, Any]) -> str:
    """Best-effort vendor detection from document metadata or column names."""
    doc_type = document.get("document_type", "")
    if "azure" in doc_type.lower():
        return "azure"
    columns_upper = {c.upper() for c in document.get("columns", [])}
    if any("AZURE" in c for c in columns_upper):
        return "azure"
    if any(c.startswith("LINEITEM/") for c in columns_upper):
        return "aws"
    if any(c.startswith("SERVICE.") or c.startswith("SKU.") for c in columns_upper):
        return "gcp"
    return "unknown"


def _extract_billing_lines(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert document rows into a uniform billing_line dict list.

    Column mapping is vendor-agnostic: we look for known column names and
    fall back to case-insensitive matching.  Unknown columns are preserved
    in ``raw_row``.
    """
    vendor = _infer_billing_vendor(document)
    columns = document.get("columns", [])
    rows = document.get("rows", [])
    filename = document.get("filename", "")
    sheet = document.get("sheet", "")

    # Build a case-insensitive column lookup
    col_index: dict[str, str] = {}
    for col in columns:
        col_index[col.upper().strip()] = col

    def _col(upper_name: str) -> str | None:
        return col_index.get(upper_name)

    # Known column names (Azure primary, AWS/GCP secondary)
    col_date = _col("DATE (UTC)") or _col("LINEITEM/USAGESTARTDATE") or _col("usage.start_time")
    col_period = _col("SERVICE PERIOD (UTC)") or _col("BILLING_PERIOD_START")
    col_txn = _col("TRANSACTION TYPE") or _col("LINEITEM/LINEITEMTYPE")
    col_family = _col("PRODUCT FAMILY") or _col("PRODUCT/PRODUCTFAMILY") or _col("SERVICE.DESCRIPTION")
    col_type = _col("PRODUCT TYPE") or _col("PRODUCT/SKU") or _col("SKU.DESCRIPTION")
    col_sku = _col("PRODUCT SKU") or _col("LINEITEM/PRODUCTCODE")
    col_unit = _col("UNIT TYPE") or _col("LINEITEM/USAGETYPE") or _col("USAGE.UNIT")
    col_qty = _col("QUANTITY") or _col("LINEITEM/USAGEAMOUNT") or _col("USAGE.AMOUNT")
    col_amount = _col("CHARGES/CREDITS") or _col("LINEITEM/BLENDEDCOST") or _col("COST")
    col_currency = _col("CHARGES/CREDITS CURRENCY") or _col("LINEITEM/BLENDEDCOSTUNIT") or _col("CURRENCY")
    col_region = _col("METER REGION") or _col("PRODUCT/REGION") or _col("LOCATION.REGION")

    lines: list[dict[str, Any]] = []
    for row in rows:
        line: dict[str, Any] = {
            "vendor": vendor,
            "source_file": filename,
            "source_sheet": sheet,
            "line_number": row.get("_line_number"),
            "service_period": str(row.get(col_period, "")).strip() if col_period else "",
            "transaction_type": str(row.get(col_txn, "")).strip() if col_txn else "",
            "product_family": str(row.get(col_family, "")).strip() if col_family else "",
            "product_type": str(row.get(col_type, "")).strip() if col_type else "",
            "product_sku": str(row.get(col_sku, "")).strip() if col_sku else "",
            "unit_type": str(row.get(col_unit, "")).strip() if col_unit else "",
            "quantity_raw": str(row.get(col_qty, "")).strip() if col_qty else "",
            "amount_raw": str(row.get(col_amount, "")).strip() if col_amount else "",
            "currency": str(row.get(col_currency, "")).strip() if col_currency else "",
            "region_hint": str(row.get(col_region, "")).strip() if col_region else "",
            "raw_row": {k: v for k, v in row.items() if k != "_line_number"},
        }
        lines.append(line)
    return lines


def _group_billing_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group billing lines by (product_family, product_type, product_sku, unit_type).

    Each group carries: key, line_numbers, total_quantity, total_amount,
    sample rows (up to 3).
    """
    groups: dict[tuple[str, ...], dict[str, Any]] = {}
    for line in lines:
        key = (
            line["product_family"],
            line["product_type"],
            line["product_sku"],
            line["unit_type"],
        )
        if key not in groups:
            groups[key] = {
                "product_family": key[0],
                "product_type": key[1],
                "product_sku": key[2],
                "unit_type": key[3],
                "vendor": line["vendor"],
                "source_file": line["source_file"],
                "source_sheet": line["source_sheet"],
                "line_numbers": [],
                "quantity_raw_list": [],
                "amount_raw_list": [],
                "sample_rows": [],
                "service_period": line["service_period"],
                "transaction_types": set(),
                "currency": line["currency"],
                "region_hint": line["region_hint"],
            }
        g = groups[key]
        g["line_numbers"].append(line["line_number"])
        g["quantity_raw_list"].append(line["quantity_raw"])
        g["amount_raw_list"].append(line["amount_raw"])
        if len(g["sample_rows"]) < 3:
            g["sample_rows"].append(line["raw_row"])
        if line["transaction_type"]:
            g["transaction_types"].add(line["transaction_type"])
    # Summarise
    result: list[dict[str, Any]] = []
    for g in groups.values():
        qty_sum = sum(_to_float(q) or 0 for q in g.pop("quantity_raw_list"))
        amt_sum = sum(_to_float(a) or 0 for a in g.pop("amount_raw_list"))
        g["total_quantity"] = qty_sum
        g["total_amount"] = amt_sum
        g["transaction_types"] = sorted(g["transaction_types"])
        result.append(g)
    return result


# -- Deterministic fallback (no LLM) ------------------------------------------

_RESOURCE_KIND_KEYWORDS: list[tuple[str, list[str]]] = [
    ("vm", ["virtual machine", "vm ", "serie d", "serie f", "serie b", "serie e", "compute", "burstable", "memory optimized"]),
    ("disk", ["disk", "disco", "managed disk", "page blob"]),
    ("file_storage", ["file", "archivo", "file sync", "nfs", "smb"]),
    ("object_storage", ["blob", "object storage", "obs", "s3"]),
    ("database", ["database", "mysql", "postgres", "sql", "maria", "redis", "cosmos", "dynamodb"]),
    ("load_balancer", ["load balancer", "application gateway", "alb", "nlb"]),
    ("waf", ["waf", "firewall", "defender"]),
    ("vpn_gateway", ["vpn", "virtual network private link", "private link", "expressroute"]),
    ("public_ip", ["ip", "direcciones ip", "public ip", "elastic ip"]),
    ("backup", ["backup", "recovery", "site recovery"]),
    ("monitoring", ["monitor", "log analytics", "insights", "alert"]),
    ("developer_tool", ["api management", "devops", "pipelines", "test plans", "repos", "boards", "key vault"]),
    ("security", ["defender", "security center", "sentinel"]),
    ("containers", ["container", "kubernetes", "aks", "ecs", "gke"]),
    ("data", ["fabric", "synapse", "databricks", "data factory", "data lake"]),
]


def _classify_resource_kind_fallback(product_type: str, product_sku: str, unit_type: str) -> str:
    """Deterministic keyword-based resource_kind classification."""
    text = f"{product_type} {product_sku} {unit_type}".lower()
    for kind, keywords in _RESOURCE_KIND_KEYWORDS:
        for kw in keywords:
            if kw in text:
                return kind
    return "unsupported"


def _infer_quantity_interpretation_fallback(unit_type: str) -> str:
    """Deterministic quantity_interpretation from unit_type text."""
    ut = unit_type.lower()
    if any(k in ut for k in ["hora", "hour", "hora de"]):
        return "instance_hours"
    if any(k in ut for k in ["vcore", "núcleo virtual", "virtual core"]):
        return "vcore_hours"
    if any(k in ut for k in ["gateway", "puerta de enlace"]):
        return "gateway_hours"
    if any(k in ut for k in ["ip", "dirección"]):
        return "ip_hours"
    if any(k in ut for k in ["gb/mes", "gb/month", "gib/mes"]):
        return "capacity_gib_month"
    if any(k in ut for k in ["gb", "gib"]):
        return "traffic_gb"
    if any(k in ut for k in ["operación", "operation", "transacción", "transaction", "10k", "10 000"]):
        return "ops_10k"
    if any(k in ut for k in ["millón", "million"]):
        return "requests_million"
    if any(k in ut for k in ["usuario", "user"]):
        return "user_month"
    if any(k in ut for k in ["mes", "month", "servidor"]):
        return "instance_hours"
    if "reservation" in ut or "year" in ut:
        return "instance_hours"
    return "unknown"


def _apply_quantity_rule(quantity: float, rule: str) -> float:
    """Apply a derived_quantity_rule to a raw quantity value."""
    if rule == "hours_div_744":
        return round(quantity / 744, 4) if quantity else 0.0
    if rule == "keep_raw_capacity":
        return quantity
    if rule == "keep_raw_count":
        return quantity
    if rule == "keep_raw_usage":
        return quantity
    return quantity


def _infer_derived_quantity_rule(quantity_interpretation: str) -> str:
    """Map quantity_interpretation to a derived_quantity_rule."""
    if quantity_interpretation in ("instance_hours", "vcore_hours", "gateway_hours", "ip_hours"):
        return "hours_div_744"
    if quantity_interpretation in ("capacity_gib_month",):
        return "keep_raw_capacity"
    if quantity_interpretation in ("instance_hours",):
        return "keep_raw_count"
    return "keep_raw_usage"


def _infer_region_hint_from_sku(sku: str) -> str | None:
    """Extract a weak region hint from SKU text (e.g. 'Sur de Brasil')."""
    sku_lower = sku.lower()
    region_hints = {
        "brasil": "brazil",
        "brazil": "brazil",
        "sur de brasil": "brazil",
        "méxico": "mexico",
        "mexico": "mexico",
        "chile": "chile",
        "us east": "us_east",
        "us west": "us_west",
        "eu west": "eu_west",
        "east us": "us_east",
        "west us": "us_west",
        "west europe": "eu_west",
        "southeast asia": "sea",
    }
    for hint, region in region_hints.items():
        if hint in sku_lower:
            return region
    return None


def _standardize_billing_group_fallback(group: dict[str, Any]) -> dict[str, Any]:
    """Deterministic fallback: classify a billing group without LLM."""
    product_type = group.get("product_type", "")
    product_sku = group.get("product_sku", "")
    unit_type = group.get("unit_type", "")
    resource_kind = _classify_resource_kind_fallback(product_type, product_sku, unit_type)
    quantity_interpretation = _infer_quantity_interpretation_fallback(unit_type)
    derived_quantity_rule = _infer_derived_quantity_rule(quantity_interpretation)
    raw_qty = group.get("total_quantity", 0)
    derived_qty = _apply_quantity_rule(raw_qty, derived_quantity_rule)
    region_hint = group.get("region_hint") or _infer_region_hint_from_sku(product_sku) or ""

    return {
        "resource_kind": resource_kind,
        "resource_subtype": product_type,
        "spec_hint": product_sku,
        "quantity_interpretation": quantity_interpretation,
        "derived_quantity_rule": derived_quantity_rule,
        "operating_system_hint": "windows" if "windows" in product_sku.lower() else None,
        "deployment_model_hint": None,
        "confidence": 0.5,
        "rationale": "fallback keyword classification",
        "needs_manual_review": resource_kind == "unsupported",
        # Aggregated data carried through
        "product_family": group.get("product_family", ""),
        "product_type": product_type,
        "product_sku": product_sku,
        "unit_type": unit_type,
        "vendor": group.get("vendor", "unknown"),
        "source_file": group.get("source_file", ""),
        "source_sheet": group.get("source_sheet", ""),
        "source_line_numbers": group.get("line_numbers", []),
        "service_period": group.get("service_period", ""),
        "transaction_types": group.get("transaction_types", []),
        "raw_quantity": raw_qty,
        "derived_quantity": derived_qty,
        "derived_unit": quantity_interpretation.replace("_", " ") if quantity_interpretation != "unknown" else "unknown",
        "amount": group.get("total_amount", 0),
        "currency": group.get("currency", ""),
        "region_hint": region_hint,
    }


# -- LLM standardization -------------------------------------------------------

_BILLING_LLM_SYSTEM_PROMPT = (
    "You are a cloud billing analyst. Given grouped billing line items, classify each group "
    "into a standardized resource model. Return compact JSON only — no prose.\n\n"
    "Output schema per group:\n"
    '{"resource_kind","resource_subtype","spec_hint","quantity_interpretation",'
    '"derived_quantity_rule","operating_system_hint","deployment_model_hint",'
    '"confidence","rationale","needs_manual_review"}\n\n'
    "resource_kind ∈ {vm, disk, file_storage, object_storage, database, load_balancer, "
    "waf, vpn_gateway, public_ip, private_link, security, backup, monitoring, "
    "developer_tool, containers, data, unsupported}\n"
    "quantity_interpretation ∈ {instance_hours, vcore_hours, gateway_hours, ip_hours, "
    "disk_months, capacity_gib_month, traffic_gb, ops_10k, requests_million, user_month, unknown}\n"
    "derived_quantity_rule ∈ {hours_div_744, keep_raw_capacity, keep_raw_count, keep_raw_usage, unknown}\n"
    "confidence ∈ [0, 1]\n"
    "needs_manual_review ∈ {true, false}\n\n"
    "Return a JSON object with key \"groups\" containing an array of results, one per input group, "
    "in the same order."
)


def _standardize_billing_groups_with_llm(
    groups: list[dict[str, Any]],
    quote_context: FlexibleQuoteContext,
) -> list[dict[str, Any]] | None:
    """Call MaaS LLM to classify billing groups. Returns None on failure."""
    api_key = os.getenv("HUAWEI_MAAS_API_KEY")
    base_url = os.getenv("HUAWEI_MAAS_BASE_URL")
    model = os.getenv("HUAWEI_MAAS_MODEL")
    if not api_key or not base_url or not model:
        return None

    # Build compact prompt: only the fields the LLM needs
    llm_input = []
    for g in groups:
        llm_input.append({
            "product_family": g["product_family"],
            "product_type": g["product_type"],
            "product_sku": g["product_sku"],
            "unit_type": g["unit_type"],
            "total_quantity": g["total_quantity"],
            "total_amount": g["total_amount"],
            "sample_rows": g["sample_rows"],
        })

    try:
        with httpx.Client(timeout=60) as client:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _BILLING_LLM_SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps({"groups": llm_input}, ensure_ascii=False)},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            llm_results = parsed.get("groups", [])
            if len(llm_results) != len(groups):
                logger.warning("LLM returned %d results for %d groups — falling back", len(llm_results), len(groups))
                return None
            return llm_results
    except Exception as exc:
        logger.warning("Billing LLM standardization failed: %s", exc)
        return None


def _standardize_billing_lines(
    lines: list[dict[str, Any]],
    quote_context: FlexibleQuoteContext,
) -> list[dict[str, Any]]:
    """Standardize billing lines into unified resource descriptions.

    Tries LLM first; falls back to deterministic keyword classification.
    """
    groups = _group_billing_lines(lines)
    if not groups:
        return []

    # Try LLM
    llm_results = _standardize_billing_groups_with_llm(groups, quote_context)

    results: list[dict[str, Any]] = []
    for idx, group in enumerate(groups):
        if llm_results and idx < len(llm_results):
            lr = llm_results[idx]
            # Merge LLM result with group data
            raw_qty = group.get("total_quantity", 0)
            derived_rule = lr.get("derived_quantity_rule", "keep_raw_usage")
            derived_qty = _apply_quantity_rule(raw_qty, derived_rule)
            qty_interp = lr.get("quantity_interpretation", "unknown")
            region_hint = group.get("region_hint") or _infer_region_hint_from_sku(group.get("product_sku", "")) or ""
            results.append({
                "resource_kind": lr.get("resource_kind", "unsupported"),
                "resource_subtype": lr.get("resource_subtype", group.get("product_type", "")),
                "spec_hint": lr.get("spec_hint", group.get("product_sku", "")),
                "quantity_interpretation": qty_interp,
                "derived_quantity_rule": derived_rule,
                "operating_system_hint": lr.get("operating_system_hint"),
                "deployment_model_hint": lr.get("deployment_model_hint"),
                "confidence": lr.get("confidence", 0.5),
                "rationale": lr.get("rationale", ""),
                "needs_manual_review": lr.get("needs_manual_review", True),
                "product_family": group.get("product_family", ""),
                "product_type": group.get("product_type", ""),
                "product_sku": group.get("product_sku", ""),
                "unit_type": group.get("unit_type", ""),
                "vendor": group.get("vendor", "unknown"),
                "source_file": group.get("source_file", ""),
                "source_sheet": group.get("source_sheet", ""),
                "source_line_numbers": group.get("line_numbers", []),
                "service_period": group.get("service_period", ""),
                "transaction_types": group.get("transaction_types", []),
                "raw_quantity": raw_qty,
                "derived_quantity": derived_qty,
                "derived_unit": qty_interp.replace("_", " ") if qty_interp != "unknown" else "unknown",
                "amount": group.get("total_amount", 0),
                "currency": group.get("currency", ""),
                "region_hint": region_hint,
            })
        else:
            # Fallback
            results.append(_standardize_billing_group_fallback(group))

    return results


def _build_requirements_from_standardized_billing(
    resources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert standardized billing resources into RequirementItem dicts.

    This only creates standardized placeholder requirements — no Huawei Cloud
    product mapping is performed (that is Phase C).
    """
    requirements: list[dict[str, Any]] = []
    for idx, res in enumerate(resources):
        kind = res.get("resource_kind", "unsupported")
        subtype = res.get("resource_subtype", "")
        spec_hint = res.get("spec_hint", "")
        vendor = res.get("vendor", "unknown")

        # Build raw_product_name: "kind | subtype | spec_hint"
        parts = [kind]
        if subtype:
            parts.append(subtype)
        if spec_hint and spec_hint != subtype:
            parts.append(spec_hint)
        raw_product_name = " | ".join(parts)

        # Build spec
        if kind == "vm":
            spec = ComputeSpec(sku=spec_hint).model_dump()
        elif kind in ("disk", "file_storage", "object_storage"):
            capacity = _to_float(res.get("derived_quantity"))
            spec = StorageSpec(sku=spec_hint, capacity_gib=capacity).model_dump()
        else:
            spec = GenericSpec(description=spec_hint).model_dump()

        # Build notes with provenance
        line_nums = res.get("source_line_numbers", [])
        notes_parts = [
            f"vendor={vendor}",
            f"family={res.get('product_family', '')}",
            f"type={res.get('product_type', '')}",
            f"sku={res.get('product_sku', '')}",
            f"unit={res.get('unit_type', '')}",
            f"lines={line_nums}",
            f"confidence={res.get('confidence', 0):.2f}",
        ]
        rationale = res.get("rationale", "")
        if rationale:
            notes_parts.append(f"rationale={rationale[:80]}")
        notes = " | ".join(notes_parts)

        # Use first line_number as representative row_number
        row_number = line_nums[0] if line_nums else idx + 1

        req = RequirementItem(
            item_id=f"billing::{res.get('source_file', '')}::{idx}",
            source_file=res.get("source_file", ""),
            source_sheet=res.get("source_sheet", ""),
            row_number=row_number,
            raw_product_name=raw_product_name,
            quantity=res.get("derived_quantity"),
            quantity_source="billing_standardized",
            unit=res.get("derived_unit", "unknown"),
            region=None,
            normalized_product=None,
            spec=spec,
            notes=notes,
        )
        requirements.append(req.model_dump())
    return requirements


# ---------------------------------------------------------------------------
# Billing → Huawei product mapping (Phase C)
# ---------------------------------------------------------------------------

# Direct resource_kind → Huawei product mapping
_DIRECT_KIND_TO_HUAWEI: dict[str, str] = {
    "vm": "ECS",
    "disk": "EVS",
    "file_storage": "SFS Turbo",
    "object_storage": "OBS",
    "database": "RDS",
    "vpn_gateway": "VPN",
    "public_ip": "EIP",
    "load_balancer": "ELB",
    "waf": "WAF",
    "backup": "CBR",
    "security": "HSS",
}

# Disk tier hints from source SKU / product_type text
_DISK_TIER_HINTS: list[tuple[str, str]] = [
    ("ssd premium", "high_io"),
    ("premium", "high_io"),
    ("ultra disk", "ultra_high_io"),
    ("ssd estándar", "high_io"),
    ("hdd estándar", "common"),
    ("standard hdd", "common"),
    ("standard", "common"),
]


def _infer_huawei_product_from_resource_kind(resource_kind: str) -> str | None:
    """Map a standardized resource_kind to a Huawei product key, or None if unsupported."""
    return _DIRECT_KIND_TO_HUAWEI.get(resource_kind)


def _infer_disk_tier_hint(text: str) -> str | None:
    """Extract EVS tier hint from source text."""
    lower = text.lower()
    for pattern, tier in _DISK_TIER_HINTS:
        if pattern in lower:
            return tier
    return None


def _build_huawei_spec_hint(resource: dict[str, Any], huawei_product: str) -> dict[str, Any]:
    """Build a Huawei-side spec dict for a mapped billing resource.

    Returns a dict that can be passed to ComputeSpec/StorageSpec/GenericSpec .model_dump().
    """
    kind = resource.get("resource_kind", "unsupported")
    spec_hint = resource.get("spec_hint", "")
    derived_qty = resource.get("derived_quantity")
    os_hint = resource.get("operating_system_hint")
    deploy_hint = resource.get("deployment_model_hint")

    if kind == "vm":
        return ComputeSpec(sku=spec_hint).model_dump()

    if kind == "disk":
        capacity = _to_float(derived_qty)
        tier = _infer_disk_tier_hint(f"{spec_hint} {resource.get('product_type', '')}")
        return StorageSpec(sku=spec_hint, capacity_gib=capacity, tier=tier).model_dump()

    if kind in ("file_storage", "object_storage"):
        qty_interp = resource.get("quantity_interpretation", "")
        if qty_interp == "capacity_gib_month":
            capacity = _to_float(derived_qty)
            return StorageSpec(sku=spec_hint, capacity_gib=capacity).model_dump()
        return GenericSpec(sku=spec_hint, description=spec_hint).model_dump()

    if kind == "database":
        # Preserve engine hint in description
        desc_parts = [spec_hint]
        if os_hint:
            desc_parts.append(f"os={os_hint}")
        return GenericSpec(sku=spec_hint, description=" | ".join(desc_parts)).model_dump()

    # ELB, WAF, VPN, EIP, CBR, HSS, etc.
    return GenericSpec(sku=spec_hint, description=spec_hint).model_dump()


def _map_standardized_billing_resource(
    resource: dict[str, Any],
    idx: int,
) -> list[dict[str, Any]]:
    """Map a single standardized billing resource to one or more Huawei target candidates.

    Returns a list (1 for direct mapping, 2+ for composite 1→N mapping).
    """
    kind = resource.get("resource_kind", "unsupported")
    subtype = resource.get("resource_subtype", "")
    spec_hint = resource.get("spec_hint", "")
    source_file = resource.get("source_file", "")
    source_sheet = resource.get("source_sheet", "")
    line_numbers = resource.get("source_line_numbers", [])
    vendor = resource.get("vendor", "unknown")
    confidence = resource.get("confidence", 0)
    rationale = resource.get("rationale", "")

    # -- 1→N composite mappings -----------------------------------------------
    # Application Gateway WAF v2 → ELB + WAF
    if kind == "load_balancer" and "waf" in subtype.lower():
        base = {
            "source_standardized_id": f"billing::{source_file}::{idx}",
            "vendor": vendor,
            "source_file": source_file,
            "source_sheet": source_sheet,
            "source_line_numbers": line_numbers,
            "resource_kind": kind,
            "product_family": resource.get("product_family", ""),
            "product_type": resource.get("product_type", ""),
            "product_sku": resource.get("product_sku", ""),
            "unit_type": resource.get("unit_type", ""),
            "region_hint": resource.get("region_hint", ""),
            "mapping_method": "composite_split",
            "confidence": confidence,
            "rationale": "Application Gateway WAF v2 splits into ELB + WAF",
            "needs_manual_review": False,
        }
        derived_qty = resource.get("derived_quantity", 0)
        derived_unit = resource.get("derived_unit", "unknown")
        return [
            {
                **base,
                "mapped_id": f"billing-map::{source_file}::{idx}::elb",
                "huawei_product": "ELB",
                "huawei_spec_hint": GenericSpec(sku=spec_hint, description="load balancer component").model_dump(),
                "quantity": derived_qty,
                "unit": derived_unit,
                "unresolved_fields": [],
            },
            {
                **base,
                "mapped_id": f"billing-map::{source_file}::{idx}::waf",
                "huawei_product": "WAF",
                "huawei_spec_hint": GenericSpec(sku=spec_hint, description="WAF component").model_dump(),
                "quantity": derived_qty,
                "unit": derived_unit,
                "unresolved_fields": [],
            },
        ]

    # -- Direct 1→1 mapping ---------------------------------------------------
    huawei_product = _infer_huawei_product_from_resource_kind(kind)
    if huawei_product is not None:
        spec = _build_huawei_spec_hint(resource, huawei_product)
        return [
            {
                "mapped_id": f"billing-map::{source_file}::{idx}::{huawei_product}",
                "source_standardized_id": f"billing::{source_file}::{idx}",
                "vendor": vendor,
                "source_file": source_file,
                "source_sheet": source_sheet,
                "source_line_numbers": line_numbers,
                "resource_kind": kind,
                "product_family": resource.get("product_family", ""),
                "product_type": resource.get("product_type", ""),
                "product_sku": resource.get("product_sku", ""),
                "unit_type": resource.get("unit_type", ""),
                "huawei_product": huawei_product,
                "huawei_spec_hint": spec,
                "quantity": resource.get("derived_quantity", 0),
                "unit": resource.get("derived_unit", "unknown"),
                "region_hint": resource.get("region_hint", ""),
                "mapping_method": "direct_kind_map",
                "confidence": confidence,
                "rationale": f"direct mapping: {kind} → {huawei_product}",
                "needs_manual_review": False,
                "unresolved_fields": [],
            },
        ]

    # -- Unsupported / needs_manual_review -------------------------------------
    return [
        {
            "mapped_id": f"billing-map::{source_file}::{idx}::unsupported",
            "source_standardized_id": f"billing::{source_file}::{idx}",
            "vendor": vendor,
            "source_file": source_file,
            "source_sheet": source_sheet,
            "source_line_numbers": line_numbers,
            "resource_kind": kind,
            "product_family": resource.get("product_family", ""),
            "product_type": resource.get("product_type", ""),
            "product_sku": resource.get("product_sku", ""),
            "unit_type": resource.get("unit_type", ""),
            "huawei_product": None,
            "huawei_spec_hint": GenericSpec(description=spec_hint).model_dump(),
            "quantity": resource.get("derived_quantity", 0),
            "unit": resource.get("derived_unit", "unknown"),
            "region_hint": resource.get("region_hint", ""),
            "mapping_method": "unsupported",
            "confidence": confidence,
            "rationale": rationale or f"no direct mapping for resource_kind={kind}",
            "needs_manual_review": True,
            "unresolved_fields": ["huawei_product", "spec"],
        },
    ]


def _map_standardized_billing_resources_to_huawei(
    resources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map all standardized billing resources to Huawei target candidates."""
    mapped: list[dict[str, Any]] = []
    for idx, res in enumerate(resources):
        mapped.extend(_map_standardized_billing_resource(res, idx))
    return mapped


def _build_requirements_from_mapped_billing_resources(
    mapped_resources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert mapped billing resources into RequirementItem dicts.

    This replaces _build_requirements_from_standardized_billing for the
    billing path — requirements now carry Huawei product candidates.
    """
    requirements: list[dict[str, Any]] = []
    for mr in mapped_resources:
        huawei_product = mr.get("huawei_product")
        spec_hint_data = mr.get("huawei_spec_hint", {})
        vendor = mr.get("vendor", "unknown")
        line_nums = mr.get("source_line_numbers", [])
        mapped_id = mr.get("mapped_id", "")

        # Build raw_product_name with Huawei semantics
        if huawei_product:
            product_type = mr.get("product_type", "")
            product_sku = mr.get("product_sku", "")
            parts = [huawei_product]
            if product_type and product_type.lower() not in huawei_product.lower():
                parts.append(product_type)
            if product_sku and product_sku.lower() not in huawei_product.lower() and product_sku != product_type:
                parts.append(product_sku)
            raw_product_name = " | ".join(parts)
        else:
            kind = mr.get("resource_kind", "unsupported")
            subtype = mr.get("product_type", "")
            sku = mr.get("product_sku", "")
            parts = [kind]
            if subtype:
                parts.append(subtype)
            if sku and sku != subtype:
                parts.append(sku)
            raw_product_name = " | ".join(parts)

        # Build notes with full provenance
        notes_parts = [
            f"vendor={vendor}",
            f"family={mr.get('product_family', '')}",
            f"type={mr.get('product_type', '')}",
            f"sku={mr.get('product_sku', '')}",
            f"unit={mr.get('unit_type', '')}",
            f"lines={line_nums}",
            f"src_id={mr.get('source_standardized_id', '')}",
            f"mapping={mr.get('mapping_method', '')}",
            f"confidence={mr.get('confidence', 0):.2f}",
        ]
        rationale = mr.get("rationale", "")
        if rationale:
            notes_parts.append(f"rationale={rationale[:80]}")
        notes = " | ".join(notes_parts)

        # row_number: use first source line_number
        row_number = line_nums[0] if line_nums else 0

        req = RequirementItem(
            item_id=mapped_id,
            source_file=mr.get("source_file", ""),
            source_sheet=mr.get("source_sheet", ""),
            row_number=row_number,
            raw_product_name=raw_product_name,
            quantity=mr.get("quantity"),
            quantity_source="billing_standardized",
            unit=mr.get("unit", "unknown"),
            region=None,
            normalized_product=huawei_product,
            spec=spec_hint_data,
            notes=notes,
        )
        requirements.append(req.model_dump())
    return requirements


def parse_documents(state: FlexibleQuoteState) -> FlexibleQuoteState:
    _report_progress(state, "parse_documents", "running", "Parsing uploaded documents.")
    documents: list[dict[str, Any]] = []
    for upload in state["files"]:
        if upload["extension"] == "xlsx":
            documents.extend(_parse_excel_workbook(upload["content"], upload["filename"]))
        elif upload["extension"] == "csv":
            documents.append(_parse_csv_document(upload["content"], upload["filename"]))
        else:
            text = upload["content"].decode("utf-8", errors="ignore")
            rows: list[dict[str, Any]] = []
            for index, line in enumerate(text.splitlines(), start=1):
                parts = [part.strip() for part in re.split(r"[,|\t]", line) if part.strip()]
                if len(parts) >= 4:
                    rows.append(
                        {
                            "product": parts[0],
                            "quantity": parts[1],
                            "region": parts[2],
                            "spec": parts[3],
                            "notes": " | ".join(parts[4:]) if len(parts) > 4 else "",
                            "_line_number": index,
                        }
                    )
            documents.append(
                {
                    "filename": upload["filename"],
                    "sheet": "txt",
                    "columns": ["product", "quantity", "region", "spec", "notes"],
                    "rows": rows,
                }
            )
    message = f"Parsed {len(documents)} document segment(s)."
    _report_progress(state, "parse_documents", "completed", message)
    return {
        "parsed_documents": documents,
        "diagnostics": _update_diagnostics(state),
        "audit_log": _append_audit(state, "parse_documents", message),
    }


def _maas_understanding(parsed_documents: list[dict[str, Any]], quote_context: FlexibleQuoteContext) -> dict[str, Any]:
    api_key = os.getenv("HUAWEI_MAAS_API_KEY")
    base_url = os.getenv("HUAWEI_MAAS_BASE_URL")
    model = os.getenv("HUAWEI_MAAS_MODEL")
    if not api_key or not base_url or not model:
        raise FlexibleWorkflowError(
            "Flexible preview failed during LLM schema understanding.",
            stage="understand_input",
            detail="MaaS environment variables are missing.",
        )

    prompt = {
        "quote_context": quote_context.model_dump(),
        "documents": [
            {
                "filename": item["filename"],
                "sheet": item["sheet"],
                "columns": item["columns"],
                "header_preview": item.get("header_preview", []),
                "sample_rows": [
                    {key: _serialize_cell(value) for key, value in row.items()}
                    for row in item["rows"][:8]
                ],
            }
            for item in parsed_documents[:6]
        ],
    }
    last_error: Exception | None = None
    for attempt in range(1, 3):
        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "temperature": 0.1,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "Return compact JSON only. schema_mapping must map product, quantity, region, spec, notes "
                                    "to exact column names or null. Include profile with quote_purpose, quantity_policy, "
                                    "confidence, rationale. Use quote_purpose=unit_price_comparison and "
                                    "quantity_policy=default_to_one_for_unit_price when the file is a vendor/cloud comparison "
                                    "sheet and missing quantities should mean one reference unit, not a purchase volume. "
                                    "extraction_hints can be brief strings."
                                ),
                            },
                            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                        ],
                    },
                )
                response.raise_for_status()
                payload = response.json()
                content = payload["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                FlexibleSchemaMapping.model_validate(parsed.get("schema_mapping", {}))
                parsed["_llm_model"] = model
                parsed["_llm_attempts"] = attempt
                return parsed
        except Exception as exc:
            last_error = exc
            logger.warning("Flexible preview LLM understanding attempt %s failed: %s", attempt, exc)
    raise FlexibleWorkflowError(
        "Flexible preview failed during LLM schema understanding.",
        stage="understand_input",
        detail=f"LLM schema understanding failed: {last_error}",
        diagnostics=FlexibleQuoteDiagnostics(
            llm_used=False,
            llm_model=model,
            llm_attempts=2,
            llm_error=str(last_error),
        ).model_dump(),
    )


def understand_input(state: FlexibleQuoteState) -> FlexibleQuoteState:
    _report_progress(state, "understand_input", "running", "Understanding input schema.")
    parsed = state.get("parsed_documents", [])
    quote_context = FlexibleQuoteContext.model_validate(state.get("quote_context", {}))
    llm_output = _maas_understanding(parsed, quote_context)
    inferred_profile = _infer_input_profile(parsed)
    profile = _coerce_input_profile(llm_output.get("profile"), inferred_profile)
    if inferred_profile.quote_purpose == "unit_price_comparison" and profile.quote_purpose in {"unknown", "purchase_quote"}:
        profile = inferred_profile
    understanding = {
        "profile": profile.model_dump(),
        "schema_mapping": FlexibleSchemaMapping.model_validate(llm_output.get("schema_mapping", {})).model_dump(),
        "extraction_hints": llm_output.get("extraction_hints", {}),
    }
    message = f"Used MaaS schema understanding ({profile.quote_purpose})."
    _report_progress(state, "understand_input", "completed", message)
    diagnostics = _update_diagnostics(
        state,
        llm_used=True,
        llm_model=llm_output.get("_llm_model"),
        llm_attempts=llm_output.get("_llm_attempts", 1),
        llm_error=None,
        input_profile=profile,
    )
    return {
        "understanding": understanding,
        "diagnostics": diagnostics,
        "audit_log": _append_audit(state, "understand_input", message),
    }


def _pick_column(columns: list[str], aliases: list[str]) -> str | None:
    lowered = {str(column).strip().lower(): str(column) for column in columns}
    for alias in aliases:
        key = str(alias).strip().lower()
        if key in lowered:
            return lowered[key]
    for key, original in lowered.items():
        if any(str(alias).strip().lower() in key for alias in aliases):
            return original
    return None


def _resolve_selected_column(columns: list[str], mapping: str | list[str] | None, field: str) -> str | None:
    if isinstance(mapping, str):
        lowered = {str(column).strip().lower(): str(column) for column in columns}
        direct = lowered.get(mapping.strip().lower())
        if direct:
            return direct
        return _pick_column(columns, [mapping])
    if isinstance(mapping, list):
        return _pick_column(columns, [str(item) for item in mapping])
    return _pick_column(columns, DEFAULT_SCHEMA_ALIASES[field])


def _nonempty_count(rows: list[dict[str, Any]], column: str | None) -> int:
    if not column:
        return 0
    return sum(1 for row in rows if str(row.get(column, "")).strip())


def _prefer_huawei_column(columns: list[str], rows: list[dict[str, Any]], selected: str | None, field: str) -> str | None:
    if selected and selected.strip().lower().startswith("华为云.") and _nonempty_count(rows, selected) > 0:
        return selected
    keywords = HUAWEI_COLUMN_KEYWORDS[field]
    for column in columns:
        text = str(column).strip().lower()
        if not text.startswith("华为云."):
            continue
        if any(keyword.lower() in text for keyword in keywords) and _nonempty_count(rows, str(column)) > 0:
            return str(column)
    if selected and _nonempty_count(rows, selected) > 0:
        return selected
    for column in columns:
        text = str(column).strip().lower()
        if "." not in text:
            continue
        if any(keyword.lower() in text for keyword in keywords) and _nonempty_count(rows, str(column)) > 0:
            return str(column)
    for column in columns:
        text = str(column).strip().lower()
        if any(keyword.lower() in text for keyword in keywords) and _nonempty_count(rows, str(column)) > 0:
            return str(column)
    return selected


def extract_requirement_items(state: FlexibleQuoteState) -> FlexibleQuoteState:
    _report_progress(state, "extract_requirement_items", "running", "Extracting requirement rows.")
    parsed_documents = state.get("parsed_documents", [])

    # -- Billing document fast path -------------------------------------------
    billing_documents = [d for d in parsed_documents if _detect_billing_document(d)]
    if billing_documents:
        return _extract_billing_requirement_items(state, billing_documents, parsed_documents)

    # -- Original requirement-spreadsheet path ---------------------------------
    understanding = FlexibleSchemaMapping.model_validate(state["understanding"]["schema_mapping"])
    requirements: list[dict[str, Any]] = []
    diagnostics = _diagnostics(state)
    document_diagnostics: list[FlexibleDocumentDiagnostic] = []
    for document in parsed_documents:
        product_column = _prefer_huawei_column(
            document["columns"],
            document["rows"],
            _resolve_selected_column(document["columns"], understanding.product, "product"),
            "product",
        )
        quantity_column = _prefer_huawei_column(
            document["columns"],
            document["rows"],
            _resolve_selected_column(document["columns"], understanding.quantity, "quantity"),
            "quantity",
        )
        region_column = _prefer_huawei_column(
            document["columns"],
            document["rows"],
            _resolve_selected_column(document["columns"], understanding.region, "region"),
            "region",
        )
        spec_column = _prefer_huawei_column(
            document["columns"],
            document["rows"],
            _resolve_selected_column(document["columns"], understanding.spec, "spec"),
            "spec",
        )
        notes_column = _prefer_huawei_column(
            document["columns"],
            document["rows"],
            _resolve_selected_column(document["columns"], understanding.notes, "notes"),
            "notes",
        )
        extracted_rows = 0
        candidate_rows = 0
        for index, row in enumerate(document["rows"], start=1):
            raw_product = str(row.get(product_column, "") if product_column else "").strip()
            if not raw_product:
                continue
            candidate_rows += 1
            requirement = RequirementItem(
                item_id=f"{document['filename']}::{document['sheet']}::{index}",
                source_file=document["filename"],
                source_sheet=document["sheet"],
                row_number=int(row.get("_line_number", index)),
                raw_product_name=raw_product,
                quantity=_to_float(row.get(quantity_column)) if quantity_column else None,
                quantity_source="source_file" if quantity_column and _to_float(row.get(quantity_column)) is not None else None,
                unit="item",
                region=_normalize_region(str(row.get(region_column, ""))) if region_column else None,
                spec=_parse_spec_text(None, str(row.get(spec_column, ""))) if spec_column else None,
                notes=str(row.get(notes_column, "")).strip() if notes_column else None,
            )
            requirements.append(requirement.model_dump())
            extracted_rows += 1
        reason = None
        if not product_column:
            reason = "No product column could be identified."
        elif candidate_rows == 0:
            reason = "Product column was mapped, but every row was empty."
        document_diagnostics.append(
            FlexibleDocumentDiagnostic(
                filename=document["filename"],
                sheet=document["sheet"],
                columns=[str(column) for column in document["columns"]],
                row_count=len(document["rows"]),
                selected_columns={
                    "product": product_column,
                    "quantity": quantity_column,
                    "region": region_column,
                    "spec": spec_column,
                    "notes": notes_column,
                },
                candidate_rows=candidate_rows,
                extracted_rows=extracted_rows,
                reason=reason,
            )
        )
    message = f"Extracted {len(requirements)} requirement item(s)."
    _report_progress(state, "extract_requirement_items", "completed", message)
    diagnostics = diagnostics.model_copy(
        update={
            "documents": document_diagnostics,
            "message": message,
        }
    )
    if not requirements:
        raise FlexibleWorkflowError(
            "Flexible preview failed because no recognizable requirement rows were found.",
            stage="extract_requirement_items",
            detail="No recognizable requirement rows were found in the uploaded files.",
            diagnostics=diagnostics.model_dump(),
        )
    return {
        "requirements": requirements,
        "diagnostics": diagnostics.model_dump(),
        "audit_log": _append_audit(state, "extract_requirement_items", message),
    }


def _extract_billing_requirement_items(
    state: FlexibleQuoteState,
    billing_documents: list[dict[str, Any]],
    all_documents: list[dict[str, Any]],
) -> FlexibleQuoteState:
    """Billing-specific extraction path: billing_lines → standardize → map → RequirementItem."""
    quote_context = FlexibleQuoteContext.model_validate(state.get("quote_context", {}))

    # 1. Extract billing lines from all billing documents
    all_billing_lines: list[dict[str, Any]] = []
    for doc in billing_documents:
        all_billing_lines.extend(_extract_billing_lines(doc))

    # 2. Standardize (LLM with fallback)
    standardized = _standardize_billing_lines(all_billing_lines, quote_context)

    # 3. Map to Huawei product candidates (Phase C)
    mapped = _map_standardized_billing_resources_to_huawei(standardized)

    # 4. Build RequirementItem from mapped resources
    requirements = _build_requirements_from_mapped_billing_resources(mapped)

    # 5. Build diagnostics
    diagnostics = _diagnostics(state)
    document_diagnostics: list[FlexibleDocumentDiagnostic] = []
    for doc in all_documents:
        is_billing = _detect_billing_document(doc)
        document_diagnostics.append(
            FlexibleDocumentDiagnostic(
                filename=doc["filename"],
                sheet=doc["sheet"],
                columns=[str(c) for c in doc.get("columns", [])],
                row_count=len(doc.get("rows", [])),
                selected_columns={"billing_path": str(is_billing)},
                candidate_rows=len(doc.get("rows", [])),
                extracted_rows=len(requirements) if is_billing else 0,
                reason="billing document — extracted via standardization+mapping path" if is_billing else None,
            )
        )

    message = f"Extracted {len(requirements)} mapped billing resource(s) from {len(billing_documents)} billing document(s)."
    _report_progress(state, "extract_requirement_items", "completed", message)
    diagnostics = diagnostics.model_copy(
        update={
            "documents": document_diagnostics,
            "message": message,
        }
    )
    if not requirements:
        raise FlexibleWorkflowError(
            "Flexible preview failed because no recognizable billing resources were found.",
            stage="extract_requirement_items",
            detail="Billing documents were detected but no resources could be standardized.",
            diagnostics=diagnostics.model_dump(),
        )
    return {
        "requirements": requirements,
        "billing_lines": all_billing_lines,
        "standardized_billing_resources": standardized,
        "mapped_billing_resources": mapped,
        "diagnostics": diagnostics.model_dump(),
        "audit_log": _append_audit(state, "extract_requirement_items", message),
    }


def normalize_requirements(state: FlexibleQuoteState) -> FlexibleQuoteState:
    _report_progress(state, "normalize_requirements", "running", "Normalizing products, regions, and specs.")
    quote_context = FlexibleQuoteContext.model_validate(state["quote_context"])
    normalized: list[dict[str, Any]] = []
    for item in state["requirements"]:
        requirement = RequirementItem.model_validate(item)
        # Billing requirements already have normalized_product and structured spec
        # from Phase C mapping — preserve them, only fill region.
        is_billing = requirement.quantity_source == "billing_standardized"
        if is_billing and requirement.normalized_product:
            product = requirement.normalized_product
            spec = requirement.spec
        else:
            product = _normalize_product_name(requirement.raw_product_name)
            spec = requirement.spec
            if isinstance(spec, dict):
                spec = _parse_spec_text(product, spec.get("description") or spec.get("tier") or spec.get("sku"))
            elif spec:
                spec = _parse_spec_text(product, " ".join(str(value) for value in spec.model_dump().values() if value))
        normalized.append(
            requirement.model_copy(
                update={
                    "normalized_product": product,
                    "region": requirement.region or quote_context.region,
                    "spec": spec,
                }
            ).model_dump()
        )
    message = "Normalized products, regions, and specs."
    _report_progress(state, "normalize_requirements", "completed", message)
    return {"requirements": normalized, "audit_log": _append_audit(state, "normalize_requirements", message)}


def deduplicate_items(state: FlexibleQuoteState) -> FlexibleQuoteState:
    _report_progress(state, "deduplicate_items", "running", "Deduplicating requirement items.")
    grouped: dict[str, RequirementItem] = {}
    for item in state["requirements"]:
        requirement = RequirementItem.model_validate(item)
        spec_key = json.dumps(requirement.spec.model_dump(), sort_keys=True) if requirement.spec else ""
        key = "|".join([str(requirement.normalized_product), str(requirement.region), spec_key, requirement.source_file])
        existing = grouped.get(key)
        if existing and existing.quantity is not None and requirement.quantity is not None:
            grouped[key] = existing.model_copy(update={"quantity": existing.quantity + requirement.quantity})
        else:
            grouped[key] = requirement
    deduped = [item.model_dump() for item in grouped.values()]
    message = f"Reduced to {len(deduped)} unique requirement item(s)."
    _report_progress(state, "deduplicate_items", "completed", message)
    return {"requirements": deduped, "audit_log": _append_audit(state, "deduplicate_items", message)}


def map_to_huawei_product(state: FlexibleQuoteState) -> FlexibleQuoteState:
    _report_progress(state, "map_to_huawei_product", "running", "Mapping items to Huawei Cloud products.")
    matched: list[dict[str, Any]] = []
    for item in state["requirements"]:
        requirement = RequirementItem.model_validate(item)
        if requirement.normalized_product:
            matched.append(
                MatchedProduct(
                    item_id=requirement.item_id,
                    product=requirement.normalized_product,
                    match_method="rule_match",
                    confidence=1,
                    rationale="Matched using local product synonym rules.",
                ).model_dump()
            )
            continue
        matched.append(
            MatchedProduct(
                item_id=requirement.item_id,
                product=None,
                match_method="llm_fallback",
                confidence=0,
                rationale="No deterministic product mapping hit.",
            ).model_dump()
        )
    message = "Mapped requirements to supported Huawei Cloud products."
    _report_progress(state, "map_to_huawei_product", "completed", message)
    return {"matched_products": matched, "audit_log": _append_audit(state, "map_to_huawei_product", message)}


def validate_quote_readiness(state: FlexibleQuoteState) -> FlexibleQuoteState:
    _report_progress(state, "validate_quote_readiness", "running", "Validating quote readiness.")
    matched_by_item = {item["item_id"]: MatchedProduct.model_validate(item) for item in state.get("matched_products", [])}
    ready_items: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    unquoted: list[dict[str, Any]] = []
    catalog = [PriceComponent.model_validate(item) for item in state.get("price_catalog", [])]
    profile = FlexibleInputProfile.model_validate(
        state.get("understanding", {}).get("profile", FlexibleInputProfile().model_dump())
    )
    quote_context = FlexibleQuoteContext.model_validate(state.get("quote_context", {}))

    for raw_item in state["requirements"]:
        requirement = RequirementItem.model_validate(raw_item)
        matched = matched_by_item.get(requirement.item_id)
        product = matched.product if matched else requirement.normalized_product
        is_billing = requirement.quantity_source == "billing_standardized"
        status_reason_prefix = ""
        if (
            (requirement.quantity is None or requirement.quantity <= 0)
            and profile.quantity_policy == "default_to_one_for_unit_price"
            and profile.quote_purpose == "unit_price_comparison"
        ):
            requirement = requirement.model_copy(
                update={
                    "quantity": 1,
                    "quantity_source": "inferred_unit_price",
                    "notes": _append_note(
                        requirement.notes,
                        "Quantity inferred as 1 for unit price comparison; not a committed purchase quantity.",
                    ),
                }
            )
            status_reason_prefix = "Quantity inferred as 1 for unit price comparison. "

        # For billing requirements, inherit region from quote_context if still None
        if is_billing and not requirement.region and quote_context.region:
            requirement = requirement.model_copy(update={"region": quote_context.region})

        status = "ready"
        reason = ""
        if not product:
            status = "needs_manual_review"
            reason = "Product could not be mapped to the supported catalog."
        elif requirement.quantity is None or requirement.quantity <= 0:
            status = "needs_quantity"
            reason = "Quantity is missing."
        elif not requirement.region:
            status = "needs_region"
            reason = "Region is missing."
        elif product in SPEC_REQUIRED_PRODUCTS and not requirement.spec:
            status = "needs_spec"
            reason = "Specification is missing."
        else:
            has_confirmed_price = any(
                item.product == product and item.region == requirement.region and item.confirmed and item.status == "confirmed"
                for item in catalog
            )
            if not has_confirmed_price:
                status = "needs_price_confirmation"
                reason = "No locally confirmed price is available for this product and region."

        if status == "ready" and status_reason_prefix:
            reason = status_reason_prefix.strip()
        updated = requirement.model_copy(update={"normalized_product": product, "status": status, "status_reason": reason})
        if status == "ready":
            ready_items.append(updated.model_dump())
        elif status == "needs_price_confirmation":
            unquoted.append(updated.model_dump())
        else:
            blockers.append(
                FlexibleQuoteBlocker(
                    item_id=updated.item_id,
                    product=updated.raw_product_name,
                    status=status,
                    message=reason,
                    source_file=updated.source_file,
                    source_sheet=updated.source_sheet,
                    row_number=updated.row_number,
                ).model_dump()
            )
        raw_item.update(updated.model_dump())

    message = f"Ready={len(ready_items)}, blockers={len(blockers)}, unquoted={len(unquoted)}."
    _report_progress(state, "validate_quote_readiness", "completed", message)
    return {
        "requirements": state["requirements"],
        "quote_ready_items": ready_items,
        "quote_blockers": blockers,
        "unquoted_items": unquoted,
        "audit_log": _append_audit(state, "validate_quote_readiness", message),
    }


def _route_after_validation(state: FlexibleQuoteState) -> str:
    if state.get("quote_ready_items"):
        return "ready"
    return "needs_input" if state.get("quote_blockers") and not state.get("review_feedback") else "ready"


def return_blockers(state: FlexibleQuoteState) -> FlexibleQuoteState:
    _report_progress(state, "return_blockers", "running", "Preparing blockers for manual completion.")
    message = "Returning blockers for human completion."
    _report_progress(state, "return_blockers", "completed", message)
    return {"audit_log": _append_audit(state, "return_blockers", message)}


def incorporate_feedback(state: FlexibleQuoteState) -> FlexibleQuoteState:
    feedback_by_item = {item["item_id"]: HumanFeedback.model_validate(item) for item in state.get("review_feedback", [])}
    updated: list[dict[str, Any]] = []
    for raw_item in state["requirements"]:
        requirement = RequirementItem.model_validate(raw_item)
        feedback = feedback_by_item.get(requirement.item_id)
        if not feedback:
            updated.append(requirement.model_dump())
            continue
        spec = requirement.spec
        if feedback.spec_text:
            spec = _parse_spec_text(requirement.normalized_product, feedback.spec_text)
        notes = requirement.notes or ""
        if feedback.notes:
            notes = f"{notes} | {feedback.notes}".strip(" |")
        updated.append(
            requirement.model_copy(
                update={
                    "quantity": feedback.quantity if feedback.quantity is not None else requirement.quantity,
                    "quantity_source": "human_feedback" if feedback.quantity is not None else requirement.quantity_source,
                    "region": feedback.region or requirement.region,
                    "spec": spec,
                    "notes": notes or None,
                }
            ).model_dump()
        )
    return {"requirements": updated, "review_feedback": [], "audit_log": _append_audit(state, "incorporate_feedback", f"Applied {len(feedback_by_item)} human feedback row(s).")}


def resolve_price_components(state: FlexibleQuoteState) -> FlexibleQuoteState:
    _report_progress(state, "resolve_price_components", "running", "Resolving confirmed price components.")
    catalog = [PriceComponent.model_validate(item) for item in state.get("price_catalog", [])]
    resolved: list[dict[str, Any]] = []
    unquoted = [RequirementItem.model_validate(item) for item in state.get("unquoted_items", [])]
    for raw_item in state.get("quote_ready_items", []):
        requirement = RequirementItem.model_validate(raw_item)
        product = requirement.normalized_product
        if not product or not requirement.region:
            continue
        candidates = [item for item in catalog if item.product == product and item.region == requirement.region and item.confirmed and item.status == "confirmed" and item.price is not None]
        # Spec-aware matching
        matched_component = _match_price_component_by_spec(requirement, candidates)
        if matched_component is None:
            unquoted.append(requirement.model_copy(update={"status": "needs_price_confirmation", "status_reason": "No confirmed local price matched the requested spec."}))
            continue
        # Enrich resolved component with per-item traceability
        resolved_entry = matched_component.model_dump()
        resolved_entry["requirement_item_id"] = requirement.item_id
        resolved_entry["match_rationale"] = _billing_requirement_assumption(requirement, matched_component)
        resolved.append(resolved_entry)
    message = f"Resolved {len(resolved)} price component(s)."
    _report_progress(state, "resolve_price_components", "completed", message)
    return {
        "price_components": resolved,
        "unquoted_items": [item.model_dump() for item in unquoted],
        "audit_log": _append_audit(state, "resolve_price_components", message),
    }


# ---------------------------------------------------------------------------
# Billing-aware price matching helpers (Phase D)
# ---------------------------------------------------------------------------

def _match_price_component_by_spec(
    requirement: RequirementItem,
    candidates: list[PriceComponent],
) -> PriceComponent | None:
    """Match a requirement to the best price component from candidates.

    Strategy varies by product type:
    - ECS: match by sku first, then by family hint
    - EVS: match by tier, then by sku
    - RDS: match by sku/family hint (engine-aware)
    - Generic (VPN/EIP/ELB/WAF/CBR/HSS): single candidate or tier match
    - SFS Turbo / OBS: capacity-tier match or single candidate
    """
    if not candidates:
        return None
    if not requirement.spec:
        # No spec — if only one candidate, use it; otherwise ambiguous
        if len(candidates) == 1:
            return candidates[0]
        return None

    spec_data = requirement.spec.model_dump()
    sku_hint = str(spec_data.get("sku") or "").lower().strip()
    tier_hint = str(spec_data.get("tier") or "").lower().strip()
    product = requirement.normalized_product

    # -- ECS: exact sku match, then family substring match ---------------
    if product == "ECS" and sku_hint:
        exact = [c for c in candidates if (c.sku or "").lower() == sku_hint]
        if exact:
            return exact[0]
        # Try family substring match (e.g. "d8" matches "General computing D8")
        family_hint = sku_hint.split()[0] if sku_hint else ""
        if family_hint:
            family_match = [c for c in candidates if family_hint in (c.family or "").lower() or family_hint in (c.sku or "").lower()]
            if family_match:
                return family_match[0]
        # No confident match — do NOT fall through to first candidate
        return None

    # -- EVS: tier match -----------------------------------------------
    if product == "EVS":
        if tier_hint:
            tier_match = [c for c in candidates if tier_hint in ((c.tier or "").lower(), (c.sku or "").lower())]
            if tier_match:
                return tier_match[0]
        if sku_hint:
            sku_match = [c for c in candidates if (c.sku or "").lower() == sku_hint]
            if sku_match:
                return sku_match[0]
        # Conservative default: high-io for missing tier
        default_tier = [c for c in candidates if "high-io" in ((c.tier or "").lower(), (c.sku or "").lower())]
        if default_tier:
            return default_tier[0]
        if len(candidates) == 1:
            return candidates[0]
        return None

    # -- RDS: engine-aware matching ------------------------------------
    if product == "RDS":
        # Try to identify engine from sku/description
        desc = str(spec_data.get("description") or "").lower()
        engine_hint = ""
        for engine in ["mysql", "postgresql", "sqlserver", "gaussdb", "mariadb"]:
            if engine in desc or engine in sku_hint:
                engine_hint = engine
                break
        if engine_hint:
            engine_match = [c for c in candidates if engine_hint in ((c.sku or "").lower() + " " + (c.family or "").lower())]
            if engine_match:
                # If multiple, try sku hint
                if sku_hint:
                    sku_match = [c for c in engine_match if sku_hint in (c.sku or "").lower()]
                    if sku_match:
                        return sku_match[0]
                # Single engine match — use it
                if len(engine_match) == 1:
                    return engine_match[0]
                # Multiple RDS for same engine — pick smallest/cheapest as conservative
                # This is acceptable because we know the engine at least
                engine_match.sort(key=lambda c: c.price or float("inf"))
                return engine_match[0]
        # No engine hint — do not blindly pick first
        return None

    # -- SFS Turbo / OBS: tier or single candidate ----------------------
    if product in ("SFS Turbo", "OBS"):
        if tier_hint:
            tier_match = [c for c in candidates if tier_hint in ((c.tier or "").lower(), (c.sku or "").lower())]
            if tier_match:
                return tier_match[0]
        if sku_hint:
            sku_match = [c for c in candidates if sku_hint in ((c.sku or "").lower(), (c.tier or "").lower())]
            if sku_match:
                return sku_match[0]
        # Single candidate is safe
        if len(candidates) == 1:
            return candidates[0]
        # Multiple without distinguishing spec — ambiguous
        return None

    # -- Generic products (VPN/EIP/ELB/WAF/CBR/HSS) -------------------
    # These typically have very few confirmed items per region
    if tier_hint:
        tier_match = [c for c in candidates if tier_hint in ((c.tier or "").lower(), (c.sku or "").lower())]
        if tier_match:
            return tier_match[0]
    if sku_hint:
        sku_match = [c for c in candidates if sku_hint in ((c.sku or "").lower(), (c.tier or "").lower())]
        if sku_match:
            return sku_match[0]
    # Single confirmed candidate is safe to use
    if len(candidates) == 1:
        return candidates[0]
    # Multiple generic candidates without spec — pick first with a note
    # (for VPN/EIP/ELB/WAF/CBR/HSS this is acceptable)
    return candidates[0]


def _billing_requirement_assumption(
    requirement: RequirementItem,
    matched: PriceComponent,
) -> str:
    """Build a match rationale string for a resolved price component."""
    is_billing = requirement.quantity_source == "billing_standardized"
    parts: list[str] = []
    if is_billing:
        parts.append("Billing-derived requirement matched to Huawei Cloud pricing.")
    if matched.sku:
        parts.append(f"matched_sku={matched.sku}")
    if matched.tier:
        parts.append(f"matched_tier={matched.tier}")
    if requirement.spec:
        spec_data = requirement.spec.model_dump()
        req_sku = spec_data.get("sku")
        req_tier = spec_data.get("tier")
        if req_sku and (matched.sku or "").lower() != str(req_sku).lower():
            parts.append(f"spec_sku={req_sku} did not exactly match catalog sku — approximate match used")
        if req_tier and (matched.tier or "").lower() != str(req_tier).lower():
            parts.append(f"spec_tier={req_tier} defaulted to catalog tier={matched.tier}")
    return "; ".join(parts) if parts else "direct catalog match"


def quote_items(state: FlexibleQuoteState) -> FlexibleQuoteState:
    _report_progress(state, "quote_items", "running", "Calculating quote lines.")
    # Index resolved components by requirement_item_id (not product,region)
    components_by_item: dict[str, PriceComponent] = {}
    for item in state.get("price_components", []):
        item_id = item.get("requirement_item_id")
        if item_id:
            components_by_item[item_id] = PriceComponent.model_validate(item)
    lines: list[dict[str, Any]] = []
    for raw_item in state.get("quote_ready_items", []):
        requirement = RequirementItem.model_validate(raw_item)
        component = components_by_item.get(requirement.item_id)
        if not component or requirement.quantity is None or component.price is None or not requirement.normalized_product or not requirement.region:
            continue
        assumption = "Quoted strictly from locally confirmed pricing cache."
        if requirement.quantity_source == "inferred_unit_price":
            assumption = (
                "Quantity inferred as 1 for unit price comparison; quoted value is a reference unit price, "
                "not a committed purchase total."
            )
        elif requirement.quantity_source == "billing_standardized":
            assumption = (
                "Quoted from billing-standardized requirement using target region "
                f"{requirement.region}."
            )
        # Append match rationale if available
        match_rationale = None
        for pc in state.get("price_components", []):
            if pc.get("requirement_item_id") == requirement.item_id:
                match_rationale = pc.get("match_rationale")
                break
        if match_rationale:
            assumption = f"{assumption} {match_rationale}"
        lines.append(
            FlexibleQuoteLine(
                line_id=f"line::{requirement.item_id}",
                requirement_item_id=requirement.item_id,
                product=requirement.normalized_product,
                region=requirement.region,
                quantity=requirement.quantity,
                unit=component.unit,
                billing_mode=component.billing_mode,
                matched_sku=component.sku,
                matched_tier=component.tier,
                unit_price=component.price,
                monthly_price=round(component.price * requirement.quantity, 4),
                currency=component.currency,
                assumption=assumption,
            ).model_dump()
        )
    message = f"Quoted {len(lines)} line(s)."
    _report_progress(state, "quote_items", "completed", message)
    return {"quote_lines": lines, "audit_log": _append_audit(state, "quote_items", message)}


def summarize_quote(state: FlexibleQuoteState) -> FlexibleQuoteState:
    _report_progress(state, "summarize_quote", "running", "Building flexible quote summary.")
    lines = [FlexibleQuoteLine.model_validate(item) for item in state.get("quote_lines", [])]
    inferred_count = sum(
        1
        for item in state.get("requirements", [])
        if RequirementItem.model_validate(item).quantity_source == "inferred_unit_price"
    )
    billing_count = sum(
        1
        for item in state.get("requirements", [])
        if RequirementItem.model_validate(item).quantity_source == "billing_standardized"
    )
    assumptions = [
        "Flexible quote uses only the local confirmed pricing catalog.",
        "RVTools and flexible quote flows remain fully separate.",
    ]
    if billing_count:
        assumptions.append(
            f"{billing_count} item(s) derived from cloud billing standardization; "
            "quantities were converted before Huawei Cloud pricing lookup."
        )
        quote_context = FlexibleQuoteContext.model_validate(state.get("quote_context", {}))
        if quote_context.region:
            assumptions.append(
                f"Target Huawei Cloud region taken from quote_context: {quote_context.region}."
            )
    if inferred_count:
        assumptions.append(
            f"{inferred_count} item(s) use quantity=1 inferred for unit price comparison; these are reference unit prices, not committed purchase quantities."
        )
    unquoted_count = len(state.get("unquoted_items", []))
    risks = [
        "Items without confirmed local pricing are returned as unquoted.",
        "Spec matching is deterministic and may require manual refinement for ambiguous rows.",
    ]
    if billing_count and unquoted_count:
        risks.append(
            f"{unquoted_count} billing-derived item(s) could not be matched to a confirmed Huawei Cloud price — "
            "these require manual spec/price confirmation."
        )
    summary = FlexibleQuoteSummary(
        total_input_items=len(state.get("requirements", [])),
        quote_ready_items=len(state.get("quote_ready_items", [])),
        quoted_items=len(lines),
        blocker_count=len(state.get("quote_blockers", [])),
        unquoted_count=unquoted_count,
        total_monthly_price=round(sum(item.monthly_price for item in lines), 2),
        summary=(
            f"Quoted {len(lines)} item(s), found {len(state.get('quote_blockers', []))} blocker(s), "
            f"and left {unquoted_count} item(s) awaiting price confirmation."
        ),
        assumptions=assumptions,
        risks=risks,
    )
    message = "Built flexible quote summary."
    _report_progress(state, "summarize_quote", "completed", message)
    return {"summary": summary.model_dump(), "audit_log": _append_audit(state, "summarize_quote", message)}


def build_flexible_preview_response(state: FlexibleQuoteState) -> FlexibleQuotePreviewResponse:
    return FlexibleQuotePreviewResponse(
        requirements=[RequirementItem.model_validate(item) for item in state.get("requirements", [])],
        quote_ready_items=[RequirementItem.model_validate(item) for item in state.get("quote_ready_items", [])],
        quote_blockers=[FlexibleQuoteBlocker.model_validate(item) for item in state.get("quote_blockers", [])],
        quote_lines=[FlexibleQuoteLine.model_validate(item) for item in state.get("quote_lines", [])],
        unquoted_items=[RequirementItem.model_validate(item) for item in state.get("unquoted_items", [])],
        matched_products=[MatchedProduct.model_validate(item) for item in state.get("matched_products", [])],
        summary=FlexibleQuoteSummary.model_validate(state.get("summary", {})),
        audit_log=[AuditEntry.model_validate(item) for item in state.get("audit_log", [])],
        quote_context=FlexibleQuoteContext.model_validate(state.get("quote_context", {})),
        diagnostics=FlexibleQuoteDiagnostics.model_validate(state.get("diagnostics", {})),
    )


# ---------------------------------------------------------------------------
# Billing template export helpers (Phase E)
# ---------------------------------------------------------------------------

def _select_billing_template_profile(state: FlexibleQuoteState) -> str:
    """Select a billing template profile name from state.

    Currently only 'rvtools_default' is supported.
    Future: inspect state/quote_context for profile hints.
    """
    return "rvtools_default"


def _template_profile_config(profile: str) -> dict[str, Any]:
    """Return the config dict for a billing template profile."""
    if profile not in _TEMPLATE_PROFILES:
        raise ValueError(f"Unknown billing template profile: {profile}")
    return _TEMPLATE_PROFILES[profile]


def _billing_copy_row_style(ws: Any, src_row: int, dst_row: int, max_col: int) -> None:
    ws.row_dimensions[dst_row].height = ws.row_dimensions[src_row].height
    for col in range(1, max_col + 1):
        src = ws.cell(src_row, col)
        dst = ws.cell(dst_row, col)
        if src.has_style:
            dst._style = copy(src._style)  # type: ignore[attr-defined]
        if src.number_format:
            dst.number_format = src.number_format
        if src.font:
            dst.font = copy(src.font)
        if src.fill:
            dst.fill = copy(src.fill)
        if src.border:
            dst.border = copy(src.border)
        if src.alignment:
            dst.alignment = copy(src.alignment)
        if src.protection:
            dst.protection = copy(src.protection)


def _billing_clear_row_values(ws: Any, row: int, max_col: int) -> None:
    for col in range(1, max_col + 1):
        ws.cell(row, col).value = None


def _billing_safe_text(value: Any) -> str:
    return "" if value in (None, "") else str(value)


def _billing_safe_number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_billing_spec_hint(spec: dict[str, Any]) -> str:
    """Render a Huawei spec hint dict as a compact readable string."""
    if not spec:
        return ""
    parts: list[str] = []
    sku = spec.get("sku")
    tier = spec.get("tier")
    capacity = spec.get("capacity_gib")
    desc = spec.get("description")
    if sku:
        parts.append(f"sku={sku}")
    if tier:
        parts.append(f"tier={tier}")
    if capacity is not None:
        parts.append(f"capacity={capacity}")
    if desc and desc != sku:
        # Truncate long descriptions
        d = str(desc)[:60]
        parts.append(d)
    return "; ".join(parts) if parts else ""


def _format_source_line_numbers(lines: Any) -> str:
    """Render source line numbers as a compact comma-separated string, not Python list repr."""
    if not lines:
        return ""
    if isinstance(lines, list):
        return ", ".join(str(n) for n in lines)
    return str(lines)


def _billing_row_sort_key(row: dict[str, Any]) -> tuple:
    """Sort key for detail rows: quoted first, then unquoted, manual_review, unsupported."""
    status = row.get("status", "unsupported")
    return (_BILLING_STATUS_SORT_ORDER.get(status, 99),)


def _billing_hwc_sort_key(row: dict[str, Any]) -> tuple:
    """Sort key for HWC rows: by total descending (biggest cost first)."""
    return (-_billing_safe_number(row.get("total")),)


def _build_billing_detail_rows(state: FlexibleQuoteState) -> list[dict[str, Any]]:
    """Build one detail row per mapped_billing_resource, enriched with quote status and price.

    Rows are sorted: quoted → unquoted → manual_review → unsupported.
    """
    mapped = state.get("mapped_billing_resources", [])
    quote_lines_by_item: dict[str, dict[str, Any]] = {}
    for ql in state.get("quote_lines", []):
        rid = ql.get("requirement_item_id", "")
        quote_lines_by_item[rid] = ql

    unquoted_ids: set[str] = set()
    for uq in state.get("unquoted_items", []):
        unquoted_ids.add(uq.get("item_id", ""))

    blocker_ids: set[str] = set()
    for blk in state.get("quote_blockers", []):
        blocker_ids.add(blk.get("item_id", ""))

    rows: list[dict[str, Any]] = []
    for mr in mapped:
        mapped_id = mr.get("mapped_id", "")
        # Determine status
        if mapped_id in quote_lines_by_item:
            status = "quoted"
        elif mapped_id in unquoted_ids:
            status = "unquoted"
        elif mapped_id in blocker_ids:
            status = "manual_review"
        elif mr.get("needs_manual_review"):
            status = "manual_review"
        elif mr.get("huawei_product") is None:
            status = "unsupported"
        else:
            status = "unquoted"

        # Get price data from quote line
        ql = quote_lines_by_item.get(mapped_id, {})

        # Source resource label
        product_type = mr.get("product_type", "")
        product_sku = mr.get("product_sku", "")
        source_label = f"{product_type} | {product_sku}" if product_type != product_sku else product_type or product_sku

        # Format spec hint
        spec_hint_raw = mr.get("huawei_spec_hint", {})
        spec_hint_str = _format_billing_spec_hint(spec_hint_raw) if isinstance(spec_hint_raw, dict) else _billing_safe_text(spec_hint_raw)

        # Format source line numbers
        source_lines_str = _format_source_line_numbers(mr.get("source_line_numbers", []))

        # Price fields: only for quoted rows
        if status == "quoted":
            unit_price = ql.get("unit_price", None)
            monthly_price = ql.get("monthly_price", None)
        else:
            unit_price = None
            monthly_price = None

        row = {
            "source_resource": source_label,
            "source_lines": source_lines_str,
            "source_qty": mr.get("quantity", 0),
            "source_unit": mr.get("unit_type", ""),
            "source_sku": product_sku,
            "huawei_product": mr.get("huawei_product") or "",
            "huawei_spec_hint": spec_hint_str,
            "target_qty": mr.get("quantity", 0),
            "target_unit": mr.get("unit", ""),
            "matched_sku": ql.get("matched_sku", "") if status == "quoted" else "",
            "matched_tier": ql.get("matched_tier", "") if status == "quoted" else "",
            "status": status,
            "unit_price_usd": unit_price,
            "monthly_price_usd": monthly_price,
        }
        rows.append(row)

    # Sort by status priority
    rows.sort(key=_billing_row_sort_key)
    return rows


def _populate_billing_ecs_sheet(ws: Any, rows: list[dict[str, Any]], config: dict[str, Any]) -> None:
    """Populate the ECS sheet as a billing detail page with 14 columns."""
    num_cols = 14
    headers = config["ecs_headers"]
    ecs_data_start = config["ecs_data_start_row"]
    ecs_total = config["ecs_total_row"]
    ecs_template = config["ecs_template_row"]

    # Write header row (row 2)
    for col_idx, header in enumerate(headers, start=1):
        ws.cell(2, col_idx, header)

    extra_rows = max(0, len(rows) - (ecs_total - ecs_data_start))
    if extra_rows:
        ws.insert_rows(ecs_total, extra_rows)
        for row_idx in range(ecs_total, ecs_total + extra_rows):
            _billing_copy_row_style(ws, ecs_template, row_idx, num_cols)

    total_row = ecs_total + extra_rows
    for row_idx in range(ecs_data_start, total_row):
        _billing_clear_row_values(ws, row_idx, num_cols)

    for offset, item in enumerate(rows):
        row_idx = ecs_data_start + offset
        ws.cell(row_idx, 1, _billing_safe_text(item.get("source_resource")))
        ws.cell(row_idx, 2, _billing_safe_text(item.get("source_lines")))
        ws.cell(row_idx, 3, item.get("source_qty") if item.get("source_qty") not in ("", None) else None)
        ws.cell(row_idx, 4, _billing_safe_text(item.get("source_unit")))
        ws.cell(row_idx, 5, _billing_safe_text(item.get("source_sku")))
        ws.cell(row_idx, 6, _billing_safe_text(item.get("huawei_product")))
        ws.cell(row_idx, 7, _billing_safe_text(item.get("huawei_spec_hint")))
        ws.cell(row_idx, 8, item.get("target_qty") if item.get("target_qty") not in ("", None) else None)
        ws.cell(row_idx, 9, _billing_safe_text(item.get("target_unit")))
        ws.cell(row_idx, 10, _billing_safe_text(item.get("matched_sku")))
        ws.cell(row_idx, 11, _billing_safe_text(item.get("matched_tier")))
        ws.cell(row_idx, 12, _billing_safe_text(item.get("status")))
        up = item.get("unit_price_usd")
        price_cell = ws.cell(row_idx, 13, up if up is not None else None)
        if up is not None:
            price_cell.number_format = "#,##0.00"
        mp = item.get("monthly_price_usd")
        monthly_cell = ws.cell(row_idx, 14, mp if mp is not None else None)
        if mp is not None:
            monthly_cell.number_format = "#,##0.00"

    # Total row
    _billing_clear_row_values(ws, total_row, num_cols)
    quoted_rows = [r for r in rows if r.get("status") == "quoted"]
    ws.cell(total_row, 12, f"Quoted: {len(quoted_rows)} / {len(rows)}")
    total_price = round(sum(_billing_safe_number(r.get("monthly_price_usd")) for r in quoted_rows), 2)
    total_cell = ws.cell(total_row, 14, total_price)
    total_cell.number_format = "#,##0.00"


def _build_billing_hwc_rows(state: FlexibleQuoteState) -> list[dict[str, Any]]:
    """Aggregate quote_lines by Huawei product for HWC sheet.

    Sorted by total descending (biggest cost first).
    """
    quote_lines = state.get("quote_lines", [])
    product_agg: dict[str, dict[str, Any]] = {}
    for ql in quote_lines:
        product = ql.get("product", "")
        if product not in product_agg:
            product_agg[product] = {"product": product, "quantity": 0.0, "total": 0.0, "unit_price": None, "count": 0, "blended": False}
        pa = product_agg[product]
        pa["quantity"] += _billing_safe_number(ql.get("quantity"))
        pa["total"] += _billing_safe_number(ql.get("monthly_price"))
        pa["count"] += 1

    rows: list[dict[str, Any]] = []
    for product in sorted(product_agg.keys()):
        pa = product_agg[product]
        pa["blended"] = pa["count"] > 1
        # Blended unit price if multiple lines
        if pa["quantity"] > 0:
            pa["unit_price"] = round(pa["total"] / pa["quantity"], 6)
        elif pa["count"] > 0:
            pa["unit_price"] = round(pa["total"] / pa["count"], 6)
        pa["quantity"] = round(pa["quantity"], 2)
        pa["total"] = round(pa["total"], 2)
        rows.append(pa)

    # Sort by total descending
    rows.sort(key=_billing_hwc_sort_key)
    return rows


def _populate_billing_hwc_sheet(ws: Any, hwc_rows: list[dict[str, Any]], config: dict[str, Any]) -> None:
    """Populate HWC sheet with Huawei product aggregation."""
    use_blended = config.get("hwc_use_blended_unit_price", True)

    # Write header
    ws.cell(1, 1, "HUAWEI CLOUD Product")
    ws.cell(1, 2, "Quantity")
    ws.cell(1, 3, "Unit Price")
    ws.cell(1, 4, "Total USD")

    for offset, row in enumerate(hwc_rows, start=2):
        ws.cell(offset, 1, _billing_safe_text(row.get("product")))
        ws.cell(offset, 2, row.get("quantity") if row.get("quantity") else 0)
        if use_blended or not row.get("blended"):
            ws.cell(offset, 3, row.get("unit_price") if row.get("unit_price") is not None else None)
        else:
            ws.cell(offset, 3, None)  # Leave blank for multi-price products
        ws.cell(offset, 4, row.get("total") if row.get("total") else 0)

    # Total row
    total_row = len(hwc_rows) + 2
    ws.cell(total_row, 1, None)
    ws.cell(total_row, 2, None)
    ws.cell(total_row, 3, "Total")
    ws.cell(total_row, 4, round(sum(_billing_safe_number(r.get("total")) for r in hwc_rows), 2))


def _populate_billing_summary_sheet(ws: Any, state: FlexibleQuoteState, config: dict[str, Any]) -> None:
    """Populate Summary sheet with billing-derived totals."""
    summary = FlexibleQuoteSummary.model_validate(state.get("summary", {}))
    mapped = state.get("mapped_billing_resources", [])
    quote_lines = state.get("quote_lines", [])
    quote_context = FlexibleQuoteContext.model_validate(state.get("quote_context", {}))
    cells = config["summary_cells"]

    # Source filenames
    source_files = list({mr.get("source_file", "") for mr in mapped if mr.get("source_file")})
    title = ", ".join(source_files[:3])
    if len(source_files) > 3:
        title += f" +{len(source_files) - 3} more"

    total_monthly = summary.total_monthly_price
    quoted_count = len(quote_lines)
    unquoted_count = len(state.get("unquoted_items", []))
    blocker_count = len(state.get("quote_blockers", []))
    mapped_products = len({mr.get("huawei_product") for mr in mapped if mr.get("huawei_product")})
    manual_review_count = sum(1 for mr in mapped if mr.get("needs_manual_review"))

    ws[cells["title"]] = f"Billing Quote: {title}"
    ws[cells["total_ondemand"]] = total_monthly
    ws[cells["total_ri"]] = total_monthly
    ws[cells["metrics"]] = (
        f"Quoted: {quoted_count} | Unquoted: {unquoted_count} | "
        f"Blockers: {blocker_count} | Manual review: {manual_review_count}"
    )
    ws[cells["metrics_c"]] = total_monthly
    ws[cells["metrics_d"]] = total_monthly
    ws[cells["extra_c"]] = 0
    ws[cells["extra_d"]] = 0
    ws[cells["list_c"]] = total_monthly
    ws[cells["list_d"]] = total_monthly
    ws["B13"] = None
    ws["C13"] = None
    ws["D13"] = None
    ws[cells["description"]] = (
        f"Billing-derived quote: {mapped_products} Huawei product(s) mapped from "
        f"{len(mapped)} source resource(s). Target region: {quote_context.region or 'N/A'}. "
        f"Export date: {datetime.now(timezone.utc).strftime('%d.%m.%Y')}."
    )

    # Structured assumptions and risks
    notes_parts: list[str] = []
    if summary.assumptions:
        notes_parts.append("ASSUMPTIONS:")
        for a in summary.assumptions:
            notes_parts.append(f"  - {a}")
    if summary.risks:
        notes_parts.append("")
        notes_parts.append("RISKS:")
        for r in summary.risks:
            notes_parts.append(f"  - {r}")
    if unquoted_count + manual_review_count > 0:
        notes_parts.append("")
        notes_parts.append(f"ATTENTION: {unquoted_count} unquoted + {manual_review_count} manual review item(s) require confirmation.")
    ws[cells["notes"]] = "\n".join(notes_parts)


def _populate_billing_info_sheet(ws: Any, state: FlexibleQuoteState, profile: str) -> None:
    """Populate Información sheet with provenance and risks."""
    mapped = state.get("mapped_billing_resources", [])
    summary = FlexibleQuoteSummary.model_validate(state.get("summary", {}))
    quote_context = FlexibleQuoteContext.model_validate(state.get("quote_context", {}))

    source_files = list({mr.get("source_file", "") for mr in mapped if mr.get("source_file")})
    vendors = list({mr.get("vendor", "") for mr in mapped if mr.get("vendor")})

    manual_review_count = sum(1 for mr in mapped if mr.get("needs_manual_review"))
    unsupported_count = sum(1 for mr in mapped if mr.get("huawei_product") is None)

    lines: list[str] = [
        f"Template profile: {profile}",
        f"Vendor: {', '.join(vendors)}",
        f"Source file(s): {', '.join(source_files)}",
        f"Target region: {quote_context.region or 'N/A'}",
        f"Export timestamp: {_now_iso()}",
        "",
        f"Mapped resources: {len(mapped)}",
        f"Quote lines: {len(state.get('quote_lines', []))}",
        f"Unquoted items: {len(state.get('unquoted_items', []))}",
        f"Manual review: {manual_review_count}",
        f"Unsupported: {unsupported_count}",
        f"Blockers: {len(state.get('quote_blockers', []))}",
        "",
    ]

    # Check for blended / tier defaults
    has_blended = any(
        ql.get("assumption", "") and "approximate" in ql.get("assumption", "").lower()
        for ql in state.get("quote_lines", [])
    )
    has_tier_default = any(
        ql.get("assumption", "") and "default" in ql.get("assumption", "").lower()
        for ql in state.get("quote_lines", [])
    )
    if has_blended:
        lines.append("Note: Approximate/spec matching was used for some items.")
    if has_tier_default:
        lines.append("Note: Default tier was used for some EVS items (no exact tier match).")

    # Unsupported/unquoted top items
    unsupported = [mr for mr in mapped if mr.get("huawei_product") is None or mr.get("needs_manual_review")]
    if unsupported:
        lines.append("")
        lines.append(f"Unsupported/manual review items ({len(unsupported)}):")
        for mr in unsupported[:10]:
            lines.append(f"  - {mr.get('product_type', '')} | {mr.get('product_sku', '')}")
        if len(unsupported) > 10:
            lines.append(f"  ... and {len(unsupported) - 10} more")

    lines.append("")
    if summary.assumptions:
        lines.append("Assumptions:")
        for a in summary.assumptions:
            lines.append(f"  - {a}")
    if summary.risks:
        lines.append("Risks:")
        for r in summary.risks:
            lines.append(f"  - {r}")

    for row_idx, line in enumerate(lines, start=1):
        ws.cell(row_idx, 1, line)


def _export_flexible_billing_template_workbook(state: FlexibleQuoteState) -> QuoteWorkbook:
    """Export billing quote using a template selected by profile."""
    profile = _select_billing_template_profile(state)
    config = _template_profile_config(profile)
    template_path = config["template_path"]

    if not template_path.exists():
        raise FileNotFoundError(f"Billing template not found at {template_path}")

    workbook = load_workbook(template_path)
    for sheet_name in config["required_sheets"]:
        if sheet_name not in workbook.sheetnames:
            raise KeyError(f"Template missing required sheet: {sheet_name}")

    # ECS sheet → billing detail page
    detail_rows = _build_billing_detail_rows(state)
    _populate_billing_ecs_sheet(workbook["ECS"], detail_rows, config)

    # HWC sheet → Huawei product aggregation
    hwc_rows = _build_billing_hwc_rows(state)
    _populate_billing_hwc_sheet(workbook["HWC"], hwc_rows, config)

    # Summary sheet
    _populate_billing_summary_sheet(workbook["Summary"], state, config)

    # Información sheet
    _populate_billing_info_sheet(workbook["Información"], state, profile)

    quote_context = FlexibleQuoteContext.model_validate(state.get("quote_context", {}))
    region = quote_context.region or "unknown"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"billing-quote-{region}-{stamp}.xlsx"
    output = BytesIO()
    workbook.save(output)
    return QuoteWorkbook(filename=filename, content=output.getvalue())


def export_flexible_workbook(state: FlexibleQuoteState) -> FlexibleQuoteState:
    """Export flexible quote workbook.

    Billing state (with mapped_billing_resources) uses the RVTools template.
    Normal flexible state uses the generic multi-sheet workbook.
    """
    is_billing = bool(state.get("mapped_billing_resources") or state.get("billing_lines"))
    if is_billing:
        wb = _export_flexible_billing_template_workbook(state)
        return {"workbook": wb}

    # Original generic export
    summary = FlexibleQuoteSummary.model_validate(state.get("summary", {}))
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        pd.DataFrame(
            [
                {
                    **summary.model_dump(),
                    "generated_at_utc": _now_iso(),
                    "quote_context": json.dumps(FlexibleQuoteContext.model_validate(state.get("quote_context", {})).model_dump()),
                }
            ]
        ).to_excel(writer, sheet_name="Summary", index=False)
        pd.DataFrame(state.get("requirements", [])).to_excel(writer, sheet_name="Standard Requirements", index=False)
        pd.DataFrame(state.get("quote_lines", [])).to_excel(writer, sheet_name="Quote Lines", index=False)
        pd.DataFrame(state.get("unquoted_items", [])).to_excel(writer, sheet_name="Unquoted Items", index=False)
        pd.DataFrame(state.get("matched_products", [])).to_excel(writer, sheet_name="Mapping & Assumptions", index=False)
        pd.DataFrame(state.get("audit_log", [])).to_excel(writer, sheet_name="Audit Log", index=False)

    filename = f"flexible-quote-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.xlsx"
    return {"workbook": QuoteWorkbook(filename=filename, content=output.getvalue())}


def build_flexible_preview_graph():
    graph = StateGraph(FlexibleQuoteState)
    graph.add_node("ingest_files", ingest_files)
    graph.add_node("load_pricebook", load_pricebook)
    graph.add_node("parse_documents", parse_documents)
    graph.add_node("understand_input", understand_input)
    graph.add_node("extract_requirement_items", extract_requirement_items)
    graph.add_node("normalize_requirements", normalize_requirements)
    graph.add_node("deduplicate_items", deduplicate_items)
    graph.add_node("map_to_huawei_product", map_to_huawei_product)
    graph.add_node("validate_quote_readiness", validate_quote_readiness)
    graph.add_node("return_blockers", return_blockers)
    graph.add_node("resolve_price_components", resolve_price_components)
    graph.add_node("quote_items", quote_items)
    graph.add_node("summarize_quote", summarize_quote)

    graph.add_edge(START, "ingest_files")
    graph.add_edge("ingest_files", "load_pricebook")
    graph.add_edge("load_pricebook", "parse_documents")
    graph.add_edge("parse_documents", "understand_input")
    graph.add_edge("understand_input", "extract_requirement_items")
    graph.add_edge("extract_requirement_items", "normalize_requirements")
    graph.add_edge("normalize_requirements", "deduplicate_items")
    graph.add_edge("deduplicate_items", "map_to_huawei_product")
    graph.add_edge("map_to_huawei_product", "validate_quote_readiness")
    graph.add_conditional_edges("validate_quote_readiness", _route_after_validation, {"needs_input": "return_blockers", "ready": "resolve_price_components"})
    graph.add_edge("return_blockers", "summarize_quote")
    graph.add_edge("resolve_price_components", "quote_items")
    graph.add_edge("quote_items", "summarize_quote")
    graph.add_edge("summarize_quote", END)
    return graph.compile()


def build_flexible_review_graph():
    graph = StateGraph(FlexibleQuoteState)
    graph.add_node("incorporate_feedback", incorporate_feedback)
    graph.add_node("validate_quote_readiness", validate_quote_readiness)
    graph.add_node("return_blockers", return_blockers)
    graph.add_node("resolve_price_components", resolve_price_components)
    graph.add_node("quote_items", quote_items)
    graph.add_node("summarize_quote", summarize_quote)

    graph.add_edge(START, "incorporate_feedback")
    graph.add_edge("incorporate_feedback", "validate_quote_readiness")
    graph.add_conditional_edges("validate_quote_readiness", _route_after_validation, {"needs_input": "return_blockers", "ready": "resolve_price_components"})
    graph.add_edge("return_blockers", "summarize_quote")
    graph.add_edge("resolve_price_components", "quote_items")
    graph.add_edge("quote_items", "summarize_quote")
    graph.add_edge("summarize_quote", END)
    return graph.compile()


def build_flexible_export_graph():
    graph = StateGraph(FlexibleQuoteState)
    graph.add_node("incorporate_feedback", incorporate_feedback)
    graph.add_node("validate_quote_readiness", validate_quote_readiness)
    graph.add_node("return_blockers", return_blockers)
    graph.add_node("resolve_price_components", resolve_price_components)
    graph.add_node("quote_items", quote_items)
    graph.add_node("summarize_quote", summarize_quote)
    graph.add_node("export_workbook", export_flexible_workbook)

    graph.add_edge(START, "incorporate_feedback")
    graph.add_edge("incorporate_feedback", "validate_quote_readiness")
    graph.add_conditional_edges("validate_quote_readiness", _route_after_validation, {"needs_input": "return_blockers", "ready": "resolve_price_components"})
    graph.add_edge("return_blockers", "summarize_quote")
    graph.add_edge("resolve_price_components", "quote_items")
    graph.add_edge("quote_items", "summarize_quote")
    graph.add_edge("summarize_quote", "export_workbook")
    graph.add_edge("export_workbook", END)
    return graph.compile()


def build_flexible_review_state(request: FlexibleReviewRequest) -> FlexibleQuoteState:
    return {
        "requirements": [item.model_dump() for item in request.requirements],
        "quote_context": request.quote_context.model_dump(),
        "matched_products": [item.model_dump() for item in request.matched_products],
        "audit_log": [item.model_dump() for item in request.audit_log],
        "review_feedback": [item.model_dump() for item in request.feedback],
        "price_catalog": [item.model_dump() for item in query_flexible_pricing_catalog()],
    }


flexible_preview_graph = build_flexible_preview_graph()
flexible_review_graph = build_flexible_review_graph()
flexible_export_graph = build_flexible_export_graph()
