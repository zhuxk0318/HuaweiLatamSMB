from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
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
    CloudBillingFinalQuoteItem,
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
    ManualReviewCandidate,
    MatchedProduct,
    NetworkSpec,
    PriceComponent,
    QuoteWorkbook,
    RequirementItem,
    StorageSpec,
)
from app.rvtools import CPU_COLUMNS, MEMORY_GIB_COLUMNS, MEMORY_MIB_COLUMNS, OS_COLUMNS, STORAGE_GIB_COLUMNS, STORAGE_MIB_COLUMNS, VM_NAME_COLUMNS

SUPPORTED_EXTENSIONS = {"xlsx", "csv", "txt", "pdf"}


def _get_billing_llm_timeout_seconds() -> int:
    return int(os.getenv("BILLING_LLM_TIMEOUT_SECONDS", "240"))


def _get_billing_final_composition_timeout_seconds() -> int:
    return int(os.getenv("BILLING_FINAL_COMPOSITION_TIMEOUT_SECONDS", "420"))

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
    # ── Billing primary chain (source of truth for Cloud Billing) ──
    billing_lines: list[dict[str, Any]]
    billing_groups: list[dict[str, Any]]
    llm_aggregated_billing_items: list[dict[str, Any]]
    # ── Billing legacy compat (debug/export fallback only) ──
    standardized_billing_resources: list[dict[str, Any]]
    mapped_billing_resources: list[dict[str, Any]]
    billing_gap_analysis: dict[str, Any]
    billing_reconciliation: dict[str, Any]
    safe_usage_quoted_count: int
    manual_review_candidates: list[dict[str, Any]]
    manual_review_decisions: list[dict[str, Any]]
    applied_manual_review_results: list[dict[str, Any]]
    manual_review_apply_summary: dict[str, Any]
    # ── Final quotation items (Phase 8B) ──
    final_billing_quote_items: list[dict[str, Any]]
    # ── LLM composition candidates (Phase 10) ──
    llm_composition_candidates: list[dict[str, Any]]
    # ── Full-document LLM analysis/review (PDF and future document adapters) ──
    cloud_billing_analysis_items: list[dict[str, Any]]
    cloud_billing_mapping_review: list[dict[str, Any]]


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


def _looks_like_placeholder_header(values: list[str]) -> bool:
    meaningful = [value.strip().lower() for value in values if value.strip()]
    if not meaningful:
        return False
    placeholder_like = sum(1 for value in meaningful if re.fullmatch(r"column\d+", value))
    return placeholder_like >= max(3, len(meaningful) // 2)


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
    second_has_billing_header = _count_header_keywords(second) >= 4 or any(
        marker in second_joined
        for marker in [
            "product family",
            "product type",
            "product sku",
            "unit type",
            "transaction type",
            "charges/credits",
            "service period",
        ]
    )
    second_has_inventory_header = (
        _document_has_any_column(second, VM_NAME_COLUMNS)
        and _document_has_any_column(second, CPU_COLUMNS)
        and _document_has_any_column(second, MEMORY_GIB_COLUMNS + MEMORY_MIB_COLUMNS)
    )
    if has_group_header and has_second_field_header:
        return 2
    if _looks_like_placeholder_header(first) and second_has_billing_header:
        return 2
    if len([value for value in first if value]) <= 2 and second_has_inventory_header:
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
    header_row_indexes = list(range(header_depth))
    if header_depth > 1 and _looks_like_placeholder_header(_row_values(frame, 0)):
        header_row_indexes = header_row_indexes[1:]
    header_rows = [_forward_fill_header(_row_values(frame, row_index)) for row_index in header_row_indexes]
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
        document = {
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
        if _detect_billing_document(document):
            vendor = _infer_billing_vendor(document)
            document["document_type"] = f"{vendor}_billing_xlsx" if vendor != "unknown" else "billing_xlsx"
        documents.append(document)
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


def _normalize_llm_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
        return "".join(parts)
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        if isinstance(content.get("content"), str):
            return content["content"]
    return ""


def _parse_llm_json_content(content: Any) -> dict[str, Any]:
    text = _normalize_llm_message_content(content).strip()
    if not text:
        raise ValueError("Empty LLM content")
    fence_match = re.match(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        object_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not object_match:
            raise
        parsed = json.loads(object_match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("LLM content did not decode to a JSON object")
    return parsed


def _build_heuristic_schema_understanding(parsed_documents: list[dict[str, Any]]) -> dict[str, Any]:
    schema_mapping: dict[str, str | list[str] | None] = {}
    for field in ("product", "quantity", "region", "spec", "notes"):
        candidates: list[str] = []
        for document in parsed_documents:
            columns = [str(column) for column in document.get("columns", [])]
            rows = list(document.get("rows", []))
            selected = _pick_column(columns, DEFAULT_SCHEMA_ALIASES[field])
            preferred = _prefer_huawei_column(columns, rows, selected, field)
            if preferred and preferred not in candidates:
                candidates.append(preferred)
        schema_mapping[field] = candidates or None
    profile = _infer_input_profile(parsed_documents)
    return {
        "schema_mapping": schema_mapping,
        "profile": profile.model_dump(),
        "extraction_hints": {
            "mode": "heuristic_fallback",
            "rationale": "Built from local header aliases after MaaS schema understanding failed.",
        },
        "_llm_model": None,
        "_llm_attempts": 0,
    }


def _sanitize_schema_mapping_payload(raw_mapping: Any) -> dict[str, Any]:
    if not isinstance(raw_mapping, dict):
        return {}
    sanitized: dict[str, Any] = {}
    for field in ("product", "quantity", "region", "spec", "notes"):
        value = raw_mapping.get(field)
        if isinstance(value, dict):
            flattened = [str(item).strip() for item in value.values() if str(item).strip()]
            deduped = list(dict.fromkeys(flattened))
            sanitized[field] = deduped or None
        else:
            sanitized[field] = value
    return sanitized


def _resolve_selected_columns(columns: list[str], mapping: str | list[str] | None, field: str) -> list[str]:
    candidates: list[str] = []
    if isinstance(mapping, str):
        selected = _resolve_selected_column(columns, mapping, field)
        return [selected] if selected else []
    if isinstance(mapping, list):
        for item in mapping:
            selected = _resolve_selected_column(columns, str(item), field)
            if selected and selected not in candidates:
                candidates.append(selected)
        return candidates
    selected = _resolve_selected_column(columns, None, field)
    return [selected] if selected else []


def _join_columns_as_spec(row: dict[str, Any], columns: list[str]) -> str | None:
    parts: list[str] = []
    for column in columns:
        value = str(row.get(column, "")).strip()
        if not value:
            continue
        label = column.split(".")[-1].strip()
        parts.append(f"{label}={value}")
    return " | ".join(parts) if parts else None


def _document_has_any_column(columns: list[str], aliases: list[str]) -> bool:
    normalized_candidates: set[str] = set()
    for column in columns:
        raw = str(column).strip().lower()
        normalized_candidates.add(re.sub(r"[^a-z0-9]", "", raw))
        normalized_candidates.add(re.sub(r"[^a-z0-9]", "", raw.split(".")[-1]))
    return any(re.sub(r"[^a-z0-9]", "", alias.strip().lower()) in normalized_candidates for alias in aliases)


def _column_matches_aliases(column: str | None, aliases: list[str]) -> bool:
    if not column:
        return False
    raw = str(column).strip().lower()
    candidates = [raw, raw.split(".")[-1]]
    normalized_candidates = {re.sub(r"[^a-z0-9]", "", item) for item in candidates}
    return any(
        alias_norm in normalized_candidates
        for alias_norm in (re.sub(r"[^a-z0-9]", "", alias.strip().lower()) for alias in aliases)
    )


def _looks_like_vm_inventory_document(document: dict[str, Any]) -> bool:
    columns = [str(column) for column in document.get("columns", [])]
    score = 0
    if _document_has_any_column(columns, VM_NAME_COLUMNS):
        score += 1
    if _document_has_any_column(columns, CPU_COLUMNS):
        score += 1
    if _document_has_any_column(columns, MEMORY_GIB_COLUMNS + MEMORY_MIB_COLUMNS):
        score += 1
    if _document_has_any_column(columns, STORAGE_GIB_COLUMNS + STORAGE_MIB_COLUMNS):
        score += 1
    return score >= 3


def _inventory_spec_columns(columns: list[str]) -> list[str]:
    ordered_aliases = (
        CPU_COLUMNS
        + MEMORY_GIB_COLUMNS
        + MEMORY_MIB_COLUMNS
        + STORAGE_GIB_COLUMNS
        + STORAGE_MIB_COLUMNS
        + OS_COLUMNS
    )
    selected: list[str] = []
    for alias in ordered_aliases:
        match = _pick_column(columns, [alias])
        if match and match not in selected:
            selected.append(match)
    return selected


def _inventory_value(row: dict[str, Any], aliases: list[str]) -> Any:
    keys = [str(key) for key in row.keys()]
    for alias in aliases:
        normalized_alias = re.sub(r"[^a-z0-9]", "", alias.strip().lower())
        for key in keys:
            candidates = [key.strip().lower(), key.strip().lower().split(".")[-1]]
            normalized_candidates = {re.sub(r"[^a-z0-9]", "", item) for item in candidates}
            if normalized_alias in normalized_candidates:
                return row.get(key)
    return None


def _build_inventory_compute_spec(row: dict[str, Any]) -> ComputeSpec | None:
    cpu = _to_float(_inventory_value(row, CPU_COLUMNS))
    memory = _to_float(_inventory_value(row, MEMORY_GIB_COLUMNS))
    if memory is None:
        memory_raw = _to_float(_inventory_value(row, MEMORY_MIB_COLUMNS))
        memory = memory_raw / 1024 if memory_raw and memory_raw > 512 else memory_raw
    sku = str(_inventory_value(row, ["Tipo", "Type", "Instance Type"]) or "").strip() or None
    if cpu is None and memory is None and not sku:
        return None
    return ComputeSpec(vcpu=int(cpu) if cpu else None, memory_gib=memory, sku=sku)


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
    for idx, g in enumerate(groups.values()):
        qty_sum = sum(_to_float(q) or 0 for q in g.pop("quantity_raw_list"))
        amt_sum = sum(_to_float(a) or 0 for a in g.pop("amount_raw_list"))
        g["group_id"] = f"g{idx}"
        g["total_quantity"] = qty_sum
        g["total_amount"] = amt_sum
        g["transaction_types"] = sorted(g["transaction_types"])
        result.append(g)
    return result


# ---------------------------------------------------------------------------
# Azure / cloud-vendor spec normalization (Phase Next+1)
# ---------------------------------------------------------------------------

# Azure VM shape table: (family_prefix, shape_name) -> (vcpu, memory_gib, huawei_family_hint)
_AZURE_VM_SHAPES: dict[str, tuple[int, float, str]] = {
    # Dv3 series (General purpose)
    "D2 v3": (2, 8.0, "general"),
    "D4 v3": (4, 16.0, "general"),
    "D8 v3": (8, 32.0, "general"),
    "D16 v3": (16, 64.0, "general"),
    "D32 v3": (32, 128.0, "general"),
    # DSv3 series (General purpose + premium storage)
    "D2s v3": (2, 8.0, "general"),
    "D4s v3": (4, 16.0, "general"),
    "D8s v3": (8, 32.0, "general"),
    # FSv2 series (Compute optimized)
    "F2s v2": (2, 4.0, "general"),
    "F4s v2": (4, 8.0, "general"),
    "F8s v2": (8, 16.0, "general"),
    "F16s v2": (16, 32.0, "general"),
    # B series (Burstable)
    "B1MS": (1, 2.0, "general"),
    "B1S": (1, 1.0, "general"),
    "B2MS": (2, 4.0, "general"),
    "B2S": (2, 1.0, "general"),
    # Ev3 series (Memory optimized)
    "E2 v3": (2, 16.0, "memory"),
    "E4 v3": (4, 32.0, "memory"),
    "E8 v3": (8, 64.0, "memory"),
}

# Azure managed disk SKU table: sku_name -> (tier_hint, default_capacity_gib)
_AZURE_DISK_SKUS: dict[str, tuple[str, float]] = {
    "P4": ("high_io", 32.0),
    "P6": ("high_io", 64.0),
    "P10": ("high_io", 128.0),
    "P15": ("high_io", 256.0),
    "P20": ("high_io", 512.0),
    "P30": ("high_io", 1024.0),
    "P40": ("high_io", 2048.0),
    "P50": ("high_io", 4095.0),
    "S4": ("common", 32.0),
    "S6": ("common", 64.0),
    "S10": ("common", 128.0),
    "S15": ("common", 256.0),
    "S20": ("common", 512.0),
    "S30": ("common", 1024.0),
    "S40": ("common", 2048.0),
    "S50": ("common", 4095.0),
    "E4": ("ultra_high_io", 4.0),
    "E6": ("ultra_high_io", 8.0),
    "E10": ("ultra_high_io", 16.0),
    "E15": ("ultra_high_io", 32.0),
    "E20": ("ultra_high_io", 64.0),
    "E30": ("ultra_high_io", 128.0),
}


def _extract_azure_vm_shape(spec_text: str) -> dict[str, Any] | None:
    """Extract Azure VM shape info from spec/sku text.

    Returns dict with vcpu, memory_gib, family_hint, source_shape, or None.
    """
    text = spec_text.strip()
    if not text:
        return None

    # Try direct match against known shapes
    for shape_name, (vcpu, mem, family_hint) in _AZURE_VM_SHAPES.items():
        if shape_name in text:
            return {
                "vcpu": vcpu,
                "memory_gib": mem,
                "family_hint": family_hint,
                "source_shape": shape_name,
            }

    # Try regex extraction for patterns like "D8 v3", "F2s v2"
    vm_match = re.search(
        r"([A-Z]\d+(?:s|S)?\s*v\d+|B\d+MS|B\d+S)",
        text,
    )
    if vm_match:
        candidate = vm_match.group(1)
        if candidate in _AZURE_VM_SHAPES:
            vcpu, mem, family_hint = _AZURE_VM_SHAPES[candidate]
            return {
                "vcpu": vcpu,
                "memory_gib": mem,
                "family_hint": family_hint,
                "source_shape": candidate,
            }

    return None


def _extract_azure_disk_shape(spec_text: str, notes: str | None = None) -> dict[str, Any] | None:
    """Extract Azure managed disk shape info from spec/sku text.

    Returns dict with tier_hint, capacity_gib, source_sku, or None.
    """
    text = spec_text.strip()
    if not text:
        return None

    # Skip snapshot/backup items — they are not disk-month pricing
    combined = (text + " " + (notes or "")).lower()
    if any(k in combined for k in ("instantánea", "snapshot", "backup", "copia de seguridad")):
        return None

    # Try to find a known disk SKU pattern (P10, S10, E30, etc.)
    disk_match = re.search(r"\b([PS]\d+|E\d+)\b", text)
    if disk_match:
        sku_name = disk_match.group(1)
        if sku_name in _AZURE_DISK_SKUS:
            tier, capacity = _AZURE_DISK_SKUS[sku_name]
            return {
                "tier_hint": tier,
                "capacity_gib": capacity,
                "source_sku": sku_name,
            }

    # Infer tier from text keywords
    lower = text.lower()
    if any(k in lower for k in ("ssd premium", "premium ssd", "premium", "ultra disk")):
        return {
            "tier_hint": "high_io",
            "capacity_gib": None,
            "source_sku": None,
        }
    if any(k in lower for k in ("hdd estándar", "standard hdd", "estándar", "standard")):
        return {
            "tier_hint": "common",
            "capacity_gib": None,
            "source_sku": None,
        }

    return None


def _extract_azure_mysql_shape(spec_text: str, notes: str | None = None) -> dict[str, Any] | None:
    """Extract Azure MySQL Flexible Server shape info from spec/sku text.

    Returns dict with engine, vcore, family_hint, or None.
    """
    text = spec_text.strip()
    if not text:
        return None

    lower = text.lower()

    # Must be MySQL
    if "mysql" not in lower:
        return None

    # Skip storage/IO items — only compute instances
    if any(k in lower for k in ("storage", "almacenamiento", "iops", "paid io", "lrs paid")):
        return None

    # Extract vCore count
    vcore = None
    vcore_match = re.search(r"(\d+)\s*(?:vcore|v.cpu|núcleo virtual|core)", lower)
    if vcore_match:
        vcore = int(vcore_match.group(1))

    # Extract family hint
    family_hint = "general"
    if "burstable" in lower or "b1ms" in lower or "bs series" in lower:
        family_hint = "general"
    elif "memory optimized" in lower or "mo series" in lower:
        family_hint = "memory"
    elif "compute optimized" in lower:
        family_hint = "general"

    # Extract shape name
    shape_match = re.search(r"(B\d+MS|B\d+S)", text)
    source_shape = shape_match.group(1) if shape_match else None

    return {
        "engine": "mysql",
        "vcore": vcore or 1,
        "family_hint": family_hint,
        "source_shape": source_shape,
    }


def _normalize_billing_compute_spec(requirement: RequirementItem) -> ComputeSpec | None:
    """Enrich a billing ECS requirement with normalized VM shape from Azure spec.

    Returns a ComputeSpec with vcpu, memory_gib, sku, or None if no shape found.
    """
    spec_data = requirement.spec.model_dump() if requirement.spec else {}
    sku_text = str(spec_data.get("sku") or spec_data.get("description") or "")
    notes = requirement.notes or ""

    # Try Azure VM shape extraction
    shape = _extract_azure_vm_shape(sku_text)
    if shape is None:
        # Also try from raw_product_name
        shape = _extract_azure_vm_shape(requirement.raw_product_name)

    if shape:
        return ComputeSpec(
            sku=shape["source_shape"],
            vcpu=shape["vcpu"],
            memory_gib=shape["memory_gib"],
        )

    # No shape found — keep existing spec
    return None


def _normalize_billing_storage_spec(requirement: RequirementItem) -> StorageSpec | None:
    """Enrich a billing EVS/OBS/SFS Turbo requirement with normalized storage shape.

    Returns a StorageSpec with tier, capacity_gib, sku, or None if no shape found.
    """
    spec_data = requirement.spec.model_dump() if requirement.spec else {}
    sku_text = str(spec_data.get("sku") or spec_data.get("description") or "")
    notes = requirement.notes or ""
    product = requirement.normalized_product

    # Try Azure disk shape extraction (EVS only)
    if product == "EVS":
        shape = _extract_azure_disk_shape(sku_text, notes)
        if shape is None:
            shape = _extract_azure_disk_shape(requirement.raw_product_name, notes)

        if shape:
            capacity = shape.get("capacity_gib")
            if capacity is None and requirement.unit and "capacity" in (requirement.unit or "").lower():
                capacity = requirement.quantity
            return StorageSpec(
                sku=shape.get("source_sku") or sku_text[:40],
                tier=shape.get("tier_hint"),
                capacity_gib=capacity,
            )

    # OBS / SFS Turbo capacity: infer tier from access pattern keywords
    if product in ("OBS", "SFS Turbo") and requirement.unit and "capacity" in (requirement.unit or "").lower():
        tier = _infer_obs_sfs_tier(sku_text + " " + requirement.raw_product_name, product)
        capacity = requirement.quantity
        return StorageSpec(
            sku=sku_text[:40] if sku_text else None,
            tier=tier,
            capacity_gib=capacity,
        )

    # EVS: if requirement already has capacity_gib_month unit, build spec from quantity
    if product == "EVS" and requirement.unit and "capacity" in (requirement.unit or "").lower() and requirement.quantity:
        return StorageSpec(
            sku=sku_text[:40] if sku_text else None,
            capacity_gib=requirement.quantity,
        )

    return None


def _infer_obs_sfs_tier(text: str, product: str) -> str | None:
    """Infer OBS or SFS Turbo access tier from Azure SKU text."""
    lower = text.lower()
    if product == "OBS":
        if any(k in lower for k in ("cool", "infrequent", "esporádico", "frio")):
            return "infrequent-access"
        if any(k in lower for k in ("frecuente", "hot", "frequente", "premium")):
            return "standard"
        # Default OBS tier for capacity
        return "standard"
    if product == "SFS Turbo":
        if any(k in lower for k in ("cool", "infrequent", "esporádico")):
            return "20mbps-per-tib"
        if any(k in lower for k in ("frecuente", "hot", "premium")):
            return "standard"
        return "standard"
    return None


def _normalize_billing_rds_spec(requirement: RequirementItem) -> GenericSpec | None:
    """Enrich a billing RDS requirement with normalized MySQL shape from Azure spec.

    Returns a GenericSpec with engine, vcore info, or None if no shape found.
    """
    spec_data = requirement.spec.model_dump() if requirement.spec else {}
    sku_text = str(spec_data.get("sku") or spec_data.get("description") or "")
    notes = requirement.notes or ""

    # Try Azure MySQL shape extraction
    shape = _extract_azure_mysql_shape(sku_text, notes)
    if shape is None:
        shape = _extract_azure_mysql_shape(requirement.raw_product_name, notes)

    if shape:
        desc_parts = [f"engine={shape['engine']}"]
        if shape.get("vcore"):
            desc_parts.append(f"vcore={shape['vcore']}")
        if shape.get("family_hint"):
            desc_parts.append(f"family={shape['family_hint']}")
        if shape.get("source_shape"):
            desc_parts.append(f"shape={shape['source_shape']}")
        return GenericSpec(
            sku=shape.get("source_shape") or f"{shape['engine']}.{shape.get('vcore', 1)}vcore",
            description=" | ".join(desc_parts),
        )

    return None


# -- Deterministic fallback (no LLM) ------------------------------------------

_RESOURCE_KIND_KEYWORDS: list[tuple[str, list[str]]] = [
    # Phase 5E: database checked BEFORE vm — prevents Azure MySQL compute
    # from being misclassified as vm/ECS when text contains both "mysql" and "compute".
    ("database", ["database", "mysql", "postgres", "sql", "maria", "redis", "cosmos", "dynamodb"]),
    # Phase 5E: backup checked BEFORE vm — prevents "Backup - Azure VM" from
    # being misclassified as vm/ECS when text contains "backup" and "vm".
    ("backup", ["backup", "recovery", "site recovery"]),
    ("vm", ["virtual machine", "vm ", "serie d", "serie f", "serie b", "serie e", "compute", "burstable", "memory optimized"]),
    ("disk", ["disk", "disco", "managed disk", "page blob"]),
    ("file_storage", ["file", "archivo", "file sync", "nfs", "smb"]),
    ("object_storage", ["blob", "object storage", "obs", "s3"]),
    ("load_balancer", ["load balancer", "application gateway", "alb", "nlb"]),
    ("waf", ["waf", "firewall"]),
    ("private_link", ["virtual network private link", "private link"]),
    ("vpn_gateway", ["vpn", "expressroute"]),
    # Phase 5E: "ip" keyword removed from public_ip — too broad, matches
    # "Pipelines", "API Management", etc. Use more specific phrases instead.
    ("public_ip", ["direcciones ip", "public ip", "elastic ip", "ip address"]),
    ("security", ["defender", "security center", "sentinel"]),
    ("monitoring", ["monitor", "log analytics", "insights", "alert"]),
    # Phase 5E: developer_tool items that don't map to a Huawei product
    # are classified as unsupported → needs_manual_review, not redirected
    # to an unrelated product like EIP.
    ("developer_tool", ["api management", "devops", "pipelines", "test plans", "repos", "boards", "key vault"]),
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
        with httpx.Client(timeout=_get_billing_llm_timeout_seconds()) as client:
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
    *,
    use_llm: bool = True,
) -> list[dict[str, Any]]:
    """Standardize billing lines into unified resource descriptions.

    Tries LLM first; falls back to deterministic keyword classification.
    """
    groups = _group_billing_lines(lines)
    if not groups:
        return []

    llm_results = _standardize_billing_groups_with_llm(groups, quote_context) if use_llm else None

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


# ---------------------------------------------------------------------------
# Billing aggregation via LLM (replaces per-group standardization + mapping)
# ---------------------------------------------------------------------------

_BILLING_AGGREGATION_SYSTEM_PROMPT = (
    "You are a cloud billing analyst. Given ALL billing groups from a cloud invoice, "
    "produce AGGREGATED quote items that merge related groups into minimal billable entries.\n\n"
    "Rules:\n"
    "- Merge multiple compute-hour groups for the same VM family into ONE ECS item.\n"
    "- Merge multiple disk groups for the same SKU into ONE EVS item.\n"
    "- Merge gateway-hour groups for the same gateway type into ONE VPN item.\n"
    "- Keep database compute and database storage as SEPARATE items.\n"
    "- Traffic, operations, and request-based usage that cannot be reliably priced "
    "should get resource_kind=unsupported and needs_manual_review=true.\n"
    "- Do NOT output prices — only aggregated quantities and Huawei product hints.\n"
    "- derived_quantity must be in monthly units (instance-month, disk-month, gateway-month, GB-month).\n"
    "- For hour-based quantities, divide total hours by 744 to get instance-months.\n\n"
    "Output schema per item:\n"
    '{"aggregate_label","resource_kind","source_group_ids","aggregation_type",'
    '"source_sku_hint","huawei_product","huawei_spec_hint",'
    '"derived_quantity","derived_unit","confidence","rationale","needs_manual_review"}\n\n'
    "resource_kind ∈ {ecs, evs, rds, obs, sfs_turbo, vpn, elb, waf, eip, cbr, hss, unsupported}\n"
    "aggregation_type ∈ {vm_family, disk_sku, db_instance, db_storage, gateway, "
    "traffic_usage, backup_storage, unsupported}\n"
    "derived_unit ∈ {instance-month, disk-month, gateway-month, GB-month, vcore-month, item-month, unknown}\n"
    "confidence ∈ [0, 1]\n"
    "needs_manual_review ∈ {true, false}\n\n"
    "Return a JSON object with key \"items\" containing an array of aggregated items."
)


def _build_billing_aggregation_prompt(
    groups: list[dict[str, Any]],
    quote_context: FlexibleQuoteContext,
) -> dict[str, Any]:
    """Build the compact JSON prompt for the billing aggregation LLM call."""
    vendor = groups[0]["vendor"] if groups else "unknown"
    compact_groups = []
    for g in groups:
        compact_groups.append({
            "group_id": g.get("group_id", ""),
            "product_family": g.get("product_family", ""),
            "product_type": g.get("product_type", ""),
            "product_sku": g.get("product_sku", ""),
            "unit_type": g.get("unit_type", ""),
            "total_quantity": g.get("total_quantity", 0),
            "total_amount": g.get("total_amount", 0),
            "sample_rows": g.get("sample_rows", []),
            "line_numbers": g.get("line_numbers", []),
        })
    return {
        "quote_context": quote_context.model_dump(),
        "vendor": vendor,
        "groups": compact_groups,
    }


def _aggregate_billing_groups_with_llm(
    groups: list[dict[str, Any]],
    quote_context: FlexibleQuoteContext,
) -> list[dict[str, Any]] | None:
    """Call MaaS LLM to aggregate billing groups into quote items.

    Sends the entire invoice's groups in one call.
    Returns None on failure (caller should use fallback).
    """
    api_key = os.getenv("HUAWEI_MAAS_API_KEY")
    base_url = os.getenv("HUAWEI_MAAS_BASE_URL")
    model = os.getenv("HUAWEI_MAAS_MODEL")
    if not api_key or not base_url or not model:
        return None

    prompt_data = _build_billing_aggregation_prompt(groups, quote_context)

    try:
        with httpx.Client(timeout=_get_billing_llm_timeout_seconds()) as client:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _BILLING_AGGREGATION_SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(prompt_data, ensure_ascii=False)},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            items = parsed.get("items", [])
            if not items:
                logger.warning("LLM aggregation returned 0 items — falling back")
                return None
            return items
    except Exception as exc:
        logger.warning("Billing LLM aggregation failed: %s", exc)
        return None


def _aggregate_billing_groups_fallback(
    groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Deterministic fallback aggregation when LLM is unavailable.

    Aggregates by (resource_kind, product_sku, unit_type) to produce
    fewer items than raw groups. Each item is marked with lower confidence
    and needs_manual_review if resource_kind is unsupported.
    """
    # First classify each group using existing fallback
    classified: list[dict[str, Any]] = []
    for g in groups:
        classified.append(_standardize_billing_group_fallback(g))

    # Aggregate by (resource_kind, spec_hint, derived_unit)
    agg_key: dict[tuple[str, ...], dict[str, Any]] = {}
    for c in classified:
        key = (
            c.get("resource_kind", "unsupported"),
            c.get("spec_hint", ""),
            c.get("derived_unit", "unknown"),
        )
        if key not in agg_key:
            agg_key[key] = {
                "resource_kind": key[0],
                "spec_hint": key[1],
                "derived_unit": key[2],
                "source_group_ids": [],
                "source_line_numbers": [],
                "raw_quantity_sum": 0.0,
                "derived_quantity_sum": 0.0,
                "amount_sum": 0.0,
                "product_family": c.get("product_family", ""),
                "product_type": c.get("product_type", ""),
                "product_sku": c.get("product_sku", ""),
                "unit_type": c.get("unit_type", ""),
                "vendor": c.get("vendor", "unknown"),
                "source_file": c.get("source_file", ""),
                "source_sheet": c.get("source_sheet", ""),
                "currency": c.get("currency", ""),
                "region_hint": c.get("region_hint", ""),
                "service_period": c.get("service_period", ""),
                "transaction_types": c.get("transaction_types", []),
                "quantity_interpretation": c.get("quantity_interpretation", "unknown"),
                "confidence": c.get("confidence", 0.5),
                "rationale": c.get("rationale", ""),
                "needs_manual_review": c.get("needs_manual_review", True),
            }
        a = agg_key[key]
        a["source_group_ids"].append(c.get("product_family", "") + "|" + c.get("product_type", "") + "|" + c.get("product_sku", "") + "|" + c.get("unit_type", ""))
        a["source_line_numbers"].extend(c.get("source_line_numbers", []))
        a["raw_quantity_sum"] += c.get("raw_quantity", 0)
        a["derived_quantity_sum"] += c.get("derived_quantity", 0)
        a["amount_sum"] += c.get("amount", 0)
        # Lower confidence for merged items
        a["confidence"] = min(a["confidence"], c.get("confidence", 0.5)) * 0.9

    # Build aggregated items
    kind_to_huawei: dict[str, str] = {
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
    kind_to_agg_type: dict[str, str] = {
        "vm": "vm_family",
        "disk": "disk_sku",
        "database": "db_instance",
        "vpn_gateway": "gateway",
        "public_ip": "gateway",
        "load_balancer": "gateway",
        "backup": "backup_storage",
        "object_storage": "disk_sku",
        "file_storage": "disk_sku",
    }

    results: list[dict[str, Any]] = []
    for a in agg_key.values():
        kind = a["resource_kind"]
        huawei_product = kind_to_huawei.get(kind)
        agg_type = kind_to_agg_type.get(kind, "unsupported")
        is_unsupported = kind == "unsupported" or huawei_product is None
        # Normalize unmapped kinds to "unsupported"
        if is_unsupported and kind != "unsupported":
            kind = "unsupported"

        # Build aggregate_label
        label_parts = [huawei_product or kind]
        if a["spec_hint"]:
            label_parts.append(a["spec_hint"])
        aggregate_label = " | ".join(label_parts)

        results.append({
            "aggregate_label": aggregate_label,
            "resource_kind": kind,
            "source_group_ids": a["source_group_ids"],
            "aggregation_type": agg_type,
            "source_sku_hint": a["spec_hint"],
            "huawei_product": huawei_product,
            "huawei_spec_hint": a["spec_hint"],
            "derived_quantity": round(a["derived_quantity_sum"], 4),
            "derived_unit": a["derived_unit"],
            "confidence": round(a["confidence"], 2) if not is_unsupported else 0.3,
            "rationale": a["rationale"] or "fallback aggregation",
            "needs_manual_review": is_unsupported,
            # Carry through for requirement building
            "product_family": a["product_family"],
            "product_type": a["product_type"],
            "product_sku": a["product_sku"],
            "unit_type": a["unit_type"],
            "vendor": a["vendor"],
            "source_file": a["source_file"],
            "source_sheet": a["source_sheet"],
            "source_line_numbers": a["source_line_numbers"],
            "service_period": a["service_period"],
            "transaction_types": a["transaction_types"],
            "raw_quantity": a["raw_quantity_sum"],
            "amount": a["amount_sum"],
            "currency": a["currency"],
            "region_hint": a["region_hint"],
        })
    return results


def _normalize_llm_aggregated_billing_items(
    items: list[dict[str, Any]],
    groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize and validate LLM-aggregated billing items.

    Ensures each item has required fields and valid references.
    Items with invalid source_group_ids are kept but marked needs_manual_review.
    """
    valid_group_ids = set()
    for idx, g in enumerate(groups):
        gid = g.get("group_id", f"g{idx}")
        valid_group_ids.add(gid)

    normalized: list[dict[str, Any]] = []
    for item in items:
        # Ensure required fields with defaults
        norm = {
            "aggregate_label": item.get("aggregate_label", "unknown"),
            "resource_kind": item.get("resource_kind", "unsupported"),
            "source_group_ids": item.get("source_group_ids", []),
            "aggregation_type": item.get("aggregation_type", "unsupported"),
            "source_sku_hint": item.get("source_sku_hint", ""),
            "huawei_product": item.get("huawei_product"),
            "huawei_spec_hint": item.get("huawei_spec_hint", ""),
            "derived_quantity": _to_float(item.get("derived_quantity")) or 0.0,
            "derived_unit": item.get("derived_unit", "unknown"),
            "confidence": min(1.0, max(0.0, _to_float(item.get("confidence")) or 0.3)),
            "rationale": item.get("rationale", ""),
            "needs_manual_review": item.get("needs_manual_review", True),
        }
        # Validate resource_kind
        valid_kinds = {"ecs", "evs", "rds", "obs", "sfs_turbo", "vpn", "elb", "waf", "eip", "cbr", "hss", "unsupported"}
        if norm["resource_kind"] not in valid_kinds:
            norm["resource_kind"] = "unsupported"
            norm["needs_manual_review"] = True
            norm["confidence"] = min(norm["confidence"], 0.3)

        # Validate huawei_product mapping
        kind_to_huawei = {
            "ecs": "ECS", "evs": "EVS", "rds": "RDS", "obs": "OBS",
            "sfs_turbo": "SFS Turbo", "vpn": "VPN", "elb": "ELB",
            "waf": "WAF", "eip": "EIP", "cbr": "CBR", "hss": "HSS",
        }
        if norm["resource_kind"] != "unsupported" and not norm["huawei_product"]:
            norm["huawei_product"] = kind_to_huawei.get(norm["resource_kind"])

        # Carry through extra fields if present (from fallback)
        for key in ("product_family", "product_type", "product_sku", "unit_type",
                     "vendor", "source_file", "source_sheet", "source_line_numbers",
                     "service_period", "transaction_types", "raw_quantity", "amount",
                     "currency", "region_hint"):
            if key in item:
                norm[key] = item[key]
            elif key not in norm:
                norm[key] = "" if key != "raw_quantity" and key != "amount" else 0

        normalized.append(norm)
    return normalized


def _build_requirements_from_llm_aggregated_billing_items(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert LLM-aggregated billing items into RequirementItem dicts.

    Each aggregated item becomes one RequirementItem with:
    - normalized_product set to Huawei product
    - spec structured by resource_kind
    - quantity_source = billing_standardized
    """
    requirements: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        kind = item.get("resource_kind", "unsupported")
        huawei_product = item.get("huawei_product")
        spec_hint = item.get("huawei_spec_hint") or item.get("source_sku_hint", "")
        derived_qty = item.get("derived_quantity", 0)
        derived_unit = item.get("derived_unit", "unknown")
        vendor = item.get("vendor", "unknown")
        source_file = item.get("source_file", "")
        source_sheet = item.get("source_sheet", "")
        line_nums = item.get("source_line_numbers", [])

        # Build raw_product_name
        if huawei_product:
            parts = [huawei_product]
            if spec_hint and spec_hint.lower() not in huawei_product.lower():
                parts.append(spec_hint)
            raw_product_name = " | ".join(parts)
        else:
            parts = [kind]
            if spec_hint:
                parts.append(spec_hint)
            raw_product_name = " | ".join(parts)

        # Build spec — normalize billing resource_kind aliases to canonical kinds
        # Billing aggregation upstream uses vm/disk/file_storage/object_storage/database,
        # but the spec builders expect ecs/evs/obs/sfs_turbo/rds.
        _BILLING_KIND_ALIAS: dict[str, str] = {
            "vm": "ecs",
            "disk": "evs",
            "file_storage": "sfs_turbo",
            "object_storage": "obs",
            "database": "rds",
        }
        canonical_kind = _BILLING_KIND_ALIAS.get(kind, kind)

        if canonical_kind == "ecs":
            # VM / ECS → ComputeSpec with vCPU+memory hints if available
            vcpu = item.get("vcpu") or item.get("v_core")
            mem = item.get("memory_gib") or item.get("memory_gb")
            spec = ComputeSpec(
                sku=spec_hint,
                vcpu=int(vcpu) if vcpu else None,
                memory_gib=_to_float(mem) if mem else None,
            ).model_dump()
        elif canonical_kind in ("evs", "obs", "sfs_turbo"):
            capacity = _to_float(derived_qty)
            tier_hint = item.get("tier") or item.get("storage_tier")
            spec = StorageSpec(
                sku=spec_hint,
                capacity_gib=capacity if capacity else None,
                tier=tier_hint,
            ).model_dump()
        elif canonical_kind == "rds":
            # Database → ComputeSpec-like structured info stored in GenericSpec
            # with engine/compute/storage hints preserved in description
            # (no dedicated DatabaseSpec yet, but keep structured clues)
            engine = item.get("engine") or item.get("source_engine", "")
            vcpu = item.get("vcpu") or item.get("v_core")
            mem = item.get("memory_gib") or item.get("memory_gb")
            desc_parts: list[str] = []
            if engine:
                desc_parts.append(f"engine={engine}")
            if vcpu:
                desc_parts.append(f"vcpu={vcpu}")
            if mem:
                desc_parts.append(f"mem={mem}GiB")
            if spec_hint and spec_hint not in desc_parts:
                desc_parts.append(spec_hint)
            spec = GenericSpec(
                sku=spec_hint,
                description="; ".join(desc_parts) if desc_parts else spec_hint,
            ).model_dump()
        else:
            spec = GenericSpec(sku=spec_hint, description=spec_hint).model_dump()

        # Build notes
        notes_parts = [
            f"vendor={vendor}",
            f"family={item.get('product_family', '')}",
            f"type={item.get('product_type', '')}",
            f"sku={item.get('product_sku', '')}",
            f"unit={item.get('unit_type', '')}",
            f"lines={line_nums}",
            f"agg_type={item.get('aggregation_type', '')}",
            f"confidence={item.get('confidence', 0):.2f}",
        ]
        rationale = item.get("rationale", "")
        if rationale:
            notes_parts.append(f"rationale={rationale[:80]}")
        if item.get("needs_manual_review"):
            notes_parts.append("needs_review=true")
        notes = " | ".join(notes_parts)

        row_number = line_nums[0] if line_nums else idx + 1

        req = RequirementItem(
            item_id=f"billing-agg::{source_file}::{idx}",
            source_file=source_file,
            source_sheet=source_sheet,
            row_number=row_number,
            raw_product_name=raw_product_name,
            quantity=derived_qty,
            quantity_source="billing_standardized",
            unit=derived_unit,
            region=None,
            normalized_product=huawei_product,
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
        elif upload["extension"] == "pdf":
            from app.cloud_billing_document import parse_cloud_billing_pdf

            documents.append(parse_cloud_billing_pdf(upload["content"], upload["filename"]))
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
                choices = payload.get("choices") or []
                if not choices:
                    raise ValueError("MaaS returned no choices")
                message = choices[0].get("message") or {}
                parsed = _parse_llm_json_content(message.get("content"))
                parsed["schema_mapping"] = _sanitize_schema_mapping_payload(parsed.get("schema_mapping", {}))
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
    fallback_error: str | None = None
    try:
        llm_output = _maas_understanding(parsed, quote_context)
        llm_used = True
    except FlexibleWorkflowError as exc:
        fallback_error = exc.detail or str(exc)
        logger.warning("Falling back to heuristic schema understanding: %s", fallback_error)
        llm_output = _build_heuristic_schema_understanding(parsed)
        llm_used = False
    inferred_profile = _infer_input_profile(parsed)
    profile = _coerce_input_profile(llm_output.get("profile"), inferred_profile)
    if inferred_profile.quote_purpose == "unit_price_comparison" and profile.quote_purpose in {"unknown", "purchase_quote"}:
        profile = inferred_profile
    understanding = {
        "profile": profile.model_dump(),
        "schema_mapping": FlexibleSchemaMapping.model_validate(
            _sanitize_schema_mapping_payload(llm_output.get("schema_mapping", {}))
        ).model_dump(),
        "extraction_hints": llm_output.get("extraction_hints", {}),
    }
    message = (
        f"Used MaaS schema understanding ({profile.quote_purpose})."
        if llm_used
        else f"Used heuristic schema fallback ({profile.quote_purpose})."
    )
    _report_progress(state, "understand_input", "completed", message)
    diagnostics = _update_diagnostics(
        state,
        llm_used=llm_used,
        llm_model=llm_output.get("_llm_model"),
        llm_attempts=llm_output.get("_llm_attempts", 1),
        llm_error=None if llm_used else fallback_error,
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
    quote_context = FlexibleQuoteContext.model_validate(state.get("quote_context", {}))
    for document in parsed_documents:
        is_inventory_like = _looks_like_vm_inventory_document(document)
        product_column = _prefer_huawei_column(
            document["columns"],
            document["rows"],
            _resolve_selected_column(document["columns"], understanding.product, "product"),
            "product",
        )
        if is_inventory_like and _column_matches_aliases(product_column, VM_NAME_COLUMNS):
            product_column = None
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
        spec_columns = _resolve_selected_columns(document["columns"], understanding.spec, "spec")
        if is_inventory_like and not spec_columns:
            spec_columns = _inventory_spec_columns(document["columns"])
        extracted_rows = 0
        candidate_rows = 0
        for index, row in enumerate(document["rows"], start=1):
            raw_product = str(row.get(product_column, "") if product_column else "").strip()
            synthesized_inventory_row = False
            if not raw_product and is_inventory_like:
                raw_product = "ECS"
                synthesized_inventory_row = True
            if not raw_product:
                continue
            candidate_rows += 1
            spec_text = _join_columns_as_spec(row, spec_columns) if spec_columns else (
                str(row.get(spec_column, "")) if spec_column else ""
            )
            quantity = _to_float(row.get(quantity_column)) if quantity_column else None
            quantity_source = "source_file" if quantity_column and quantity is not None else None
            if quantity is None and synthesized_inventory_row:
                quantity = 1
                quantity_source = "source_file"
            note_prefix = None
            if synthesized_inventory_row:
                note_prefix = "Inventory-style row inferred as ECS from CPU/memory/storage columns."
            inventory_spec = _build_inventory_compute_spec(row) if synthesized_inventory_row else None
            requirement = RequirementItem(
                item_id=f"{document['filename']}::{document['sheet']}::{index}",
                source_file=document["filename"],
                source_sheet=document["sheet"],
                row_number=int(row.get("_line_number", index)),
                raw_product_name=raw_product,
                quantity=quantity,
                quantity_source=quantity_source,
                unit="item",
                region=(
                    _normalize_region(str(row.get(region_column, "")))
                    if region_column else (quote_context.region if synthesized_inventory_row else None)
                ),
                spec=(
                    inventory_spec
                    or (_parse_spec_text("ECS" if synthesized_inventory_row else None, spec_text) if spec_text else None)
                ),
                notes=_append_note(str(row.get(notes_column, "")).strip() if notes_column else None, note_prefix),
            )
            requirements.append(requirement.model_dump())
            extracted_rows += 1
        reason = None
        if not product_column:
            reason = "No product column could be identified."
            if is_inventory_like and extracted_rows > 0:
                reason = "Inventory-style rows were inferred as ECS from CPU/memory/storage columns."
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
                    "spec": spec_columns[0] if len(spec_columns) == 1 else ",".join(spec_columns) if spec_columns else spec_column,
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


def extract_others_requirement_items(state: FlexibleQuoteState) -> FlexibleQuoteState:
    """Others-specific extraction: row-by-row only, no billing aggregation.

    Phase 6A/6E: If billing documents are detected, raises an error directing
    the user to the Cloud Billing Quote path. Otherwise, delegates to the
    standard requirement-spreadsheet extraction (non-billing path of
    extract_requirement_items).
    """
    _report_progress(state, "extract_others_requirement_items", "running", "Extracting requirement rows (row-by-row).")
    parsed_documents = state.get("parsed_documents", [])

    # Phase 6E: Guard — reject billing documents in Others path
    billing_documents = [d for d in parsed_documents if _detect_billing_document(d)]
    if billing_documents:
        filenames = ", ".join(d.get("filename", "?") for d in billing_documents)
        raise FlexibleWorkflowError(
            "Billing/export documents detected in Others Quote path. "
            "Please use the Cloud Billing Quote path for Azure/AWS/GCP billing exports.",
            stage="extract_others_requirement_items",
            detail=f"Detected billing documents: {filenames}. These should be processed via Cloud Billing Quote for accurate aggregation and pricing.",
            diagnostics=_diagnostics(state).model_dump(),
        )

    # Standard row-by-row extraction (same as the non-billing path in extract_requirement_items)
    understanding = FlexibleSchemaMapping.model_validate(state["understanding"]["schema_mapping"])
    requirements: list[dict[str, Any]] = []
    diagnostics = _diagnostics(state)
    document_diagnostics: list[FlexibleDocumentDiagnostic] = []
    quote_context = FlexibleQuoteContext.model_validate(state.get("quote_context", {}))
    for document in parsed_documents:
        is_inventory_like = _looks_like_vm_inventory_document(document)
        product_column = _prefer_huawei_column(
            document["columns"],
            document["rows"],
            _resolve_selected_column(document["columns"], understanding.product, "product"),
            "product",
        )
        if is_inventory_like and _column_matches_aliases(product_column, VM_NAME_COLUMNS):
            product_column = None
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
        spec_columns = _resolve_selected_columns(document["columns"], understanding.spec, "spec")
        if is_inventory_like and not spec_columns:
            spec_columns = _inventory_spec_columns(document["columns"])
        extracted_rows = 0
        candidate_rows = 0
        for index, row in enumerate(document["rows"], start=1):
            raw_product = str(row.get(product_column, "") if product_column else "").strip()
            synthesized_inventory_row = False
            if not raw_product and is_inventory_like:
                raw_product = "ECS"
                synthesized_inventory_row = True
            if not raw_product:
                continue
            candidate_rows += 1
            spec_text = _join_columns_as_spec(row, spec_columns) if spec_columns else (
                str(row.get(spec_column, "")) if spec_column else ""
            )
            quantity = _to_float(row.get(quantity_column)) if quantity_column else None
            quantity_source = "source_file" if quantity_column and quantity is not None else None
            if quantity is None and synthesized_inventory_row:
                quantity = 1
                quantity_source = "source_file"
            note_prefix = None
            if synthesized_inventory_row:
                note_prefix = "Inventory-style row inferred as ECS from CPU/memory/storage columns."
            inventory_spec = _build_inventory_compute_spec(row) if synthesized_inventory_row else None
            requirement = RequirementItem(
                item_id=f"{document['filename']}::{document['sheet']}::{index}",
                source_file=document["filename"],
                source_sheet=document["sheet"],
                row_number=int(row.get("_line_number", index)),
                raw_product_name=raw_product,
                quantity=quantity,
                quantity_source=quantity_source,
                unit="item",
                region=(
                    _normalize_region(str(row.get(region_column, "")))
                    if region_column else (quote_context.region if synthesized_inventory_row else None)
                ),
                spec=(
                    inventory_spec
                    or (_parse_spec_text("ECS" if synthesized_inventory_row else None, spec_text) if spec_text else None)
                ),
                notes=_append_note(str(row.get(notes_column, "")).strip() if notes_column else None, note_prefix),
            )
            requirements.append(requirement.model_dump())
            extracted_rows += 1
        reason = None
        if not product_column:
            reason = "No product column could be identified."
            if is_inventory_like and extracted_rows > 0:
                reason = "Inventory-style rows were inferred as ECS from CPU/memory/storage columns."
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
                    "spec": spec_columns[0] if len(spec_columns) == 1 else ",".join(spec_columns) if spec_columns else spec_column,
                    "notes": notes_column,
                },
                candidate_rows=candidate_rows,
                extracted_rows=extracted_rows,
                reason=reason,
            )
        )
    message = f"Extracted {len(requirements)} requirement item(s) (row-by-row)."
    _report_progress(state, "extract_others_requirement_items", "completed", message)
    diagnostics = diagnostics.model_copy(
        update={
            "documents": document_diagnostics,
            "message": message,
        }
    )
    if not requirements:
        raise FlexibleWorkflowError(
            "Others Quote failed because no recognizable requirement rows were found.",
            stage="extract_others_requirement_items",
            detail="No recognizable requirement rows were found in the uploaded files.",
            diagnostics=diagnostics.model_dump(),
        )
    return {
        "requirements": requirements,
        "diagnostics": diagnostics.model_dump(),
        "audit_log": _append_audit(state, "extract_others_requirement_items", message),
    }


def normalize_others_requirements(state: FlexibleQuoteState) -> FlexibleQuoteState:
    """Others-specific normalize: row-by-row only, no billing reclassification.

    Phase 6C: For Others items (quantity_source != billing_standardized),
    only standard product normalization and spec enrichment are applied.
    Billing-specific reclassification is explicitly skipped.
    """
    _report_progress(state, "normalize_others_requirements", "running", "Normalizing products, regions, and specs (row-by-row).")
    quote_context = FlexibleQuoteContext.model_validate(state["quote_context"])
    normalized: list[dict[str, Any]] = []
    for item in state["requirements"]:
        requirement = RequirementItem.model_validate(item)
        # Others path: always use standard product normalization
        # No billing reclassification, no billing spec enrichment
        product = _normalize_product_name(requirement.raw_product_name)
        spec = requirement.spec
        unit = requirement.unit
        if isinstance(spec, dict):
            spec = _parse_spec_text(product, spec.get("description") or spec.get("tier") or spec.get("sku"))
        elif spec:
            spec_data = spec.model_dump()
            if product == "ECS" and (spec_data.get("vcpu") or spec_data.get("memory_gib")):
                spec = spec
            else:
                spec = _parse_spec_text(product, " ".join(str(value) for value in spec_data.values() if value))
        normalized.append(
            requirement.model_copy(
                update={
                    "normalized_product": product,
                    "region": requirement.region or quote_context.region,
                    "spec": spec,
                    "unit": unit,
                }
            ).model_dump()
        )
    message = "Normalized products, regions, and specs (row-by-row)."
    _report_progress(state, "normalize_others_requirements", "completed", message)
    return {"requirements": normalized, "audit_log": _append_audit(state, "normalize_others_requirements", message)}


def summarize_others_quote(state: FlexibleQuoteState) -> FlexibleQuoteState:
    """Others-specific summary: row-by-row quote summary without billing analysis.

    Phase 6D: Skips billing gap analysis, reconciliation, blocker triage,
    and billing-specific assumptions. Produces a clean row-quote summary.
    """
    _report_progress(state, "summarize_others_quote", "running", "Building Others quote summary.")
    lines = [FlexibleQuoteLine.model_validate(item) for item in state.get("quote_lines", [])]
    inferred_count = sum(
        1
        for item in state.get("requirements", [])
        if RequirementItem.model_validate(item).quantity_source == "inferred_unit_price"
    )
    assumptions = [
        "Flexible quote uses only the local confirmed pricing catalog.",
        "RVTools and flexible quote flows remain fully separate.",
    ]
    if inferred_count:
        assumptions.append(
            f"{inferred_count} item(s) use quantity=1 inferred for unit price comparison; these are reference unit prices, not committed purchase quantities."
        )
    unquoted_count = len(state.get("unquoted_items", []))
    risks = [
        "Items without confirmed local pricing are returned as unquoted.",
        "Spec matching is deterministic and may require manual refinement for ambiguous rows.",
    ]
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
    # Manual review design (kept — it's useful for Others too)
    manual_review_design = _analyze_manual_review_design(state)
    if manual_review_design["total_candidates"] > 0:
        scope_count = manual_review_design["scope_decision_count"]
        mapping_count = manual_review_design["mapping_decision_count"]
        assumptions.append(
            f"MANUAL REVIEW: {manual_review_design['total_candidates']} unsupported item(s) need review — "
            f"{mapping_count} need product mapping, {scope_count} may be out of scope."
        )
    # Apply manual review inputs if present
    manual_review_inputs = state.get("manual_review_decisions", [])
    apply_result: dict[str, Any] = {}
    if manual_review_inputs:
        candidates = manual_review_design.get("candidates", [])
        validated = _validate_manual_review_inputs(manual_review_inputs, candidates)
        apply_result = _apply_manual_review_inputs(state, validated, candidates=candidates)
        apply_summary = apply_result.get("manual_review_apply_summary", {})
        if apply_summary.get("decisions_applied", 0) > 0:
            assumptions.append(
                f"MANUAL REVIEW APPLY: {apply_summary['decisions_applied']} decision(s) applied — "
                f"{apply_summary['excluded_by_manual_review']} excluded, "
                f"{apply_summary['mapped_overrides']} override(s) recorded, "
                f"{apply_summary['unresolved_after_manual_review']} unresolved."
            )
    summary = summary.model_copy(update={"assumptions": assumptions})
    message = "Built Others quote summary."
    _report_progress(state, "summarize_others_quote", "completed", message)
    result: dict[str, Any] = {
        "summary": summary.model_dump(),
        "billing_manual_review_design": manual_review_design,
        "audit_log": _append_audit(state, "summarize_others_quote", message),
    }
    if apply_result:
        result["applied_manual_review_results"] = apply_result.get("applied_manual_review_results", [])
        result["manual_review_apply_summary"] = apply_result.get("manual_review_apply_summary", {})
    return result


def _extract_billing_requirement_items(
    state: FlexibleQuoteState,
    billing_documents: list[dict[str, Any]],
    all_documents: list[dict[str, Any]],
) -> FlexibleQuoteState:
    """Billing-specific extraction path — the PRIMARY billing intermediate chain.

    Main chain (source of truth for Cloud Billing):
        billing_lines → billing_groups → llm_aggregated_billing_items → requirements

    Legacy compat chain (debug/export fallback only, NOT the primary truth):
        standardized_billing_resources → mapped_billing_resources

    Downstream normalize/map/price/summary/export should prefer
    llm_aggregated_billing_items and requirements over the legacy compat fields.
    """
    quote_context = FlexibleQuoteContext.model_validate(state.get("quote_context", {}))

    # 1. Extract billing lines from all billing documents
    all_billing_lines: list[dict[str, Any]] = []
    for doc in billing_documents:
        all_billing_lines.extend(_extract_billing_lines(doc))

    # 2. Group billing lines
    billing_groups = _group_billing_lines(all_billing_lines)

    # 3. Aggregate with LLM (single call for entire invoice)
    use_llm = not bool(state.get("skip_billing_llm"))
    raw_items = _aggregate_billing_groups_with_llm(billing_groups, quote_context) if use_llm else None

    if raw_items is not None:
        # LLM succeeded — normalize its output
        llm_aggregated_billing_items = _normalize_llm_aggregated_billing_items(raw_items, billing_groups)
    else:
        # Fallback — deterministic aggregation (not row-level)
        llm_aggregated_billing_items = _aggregate_billing_groups_fallback(billing_groups)

    # 4. Build RequirementItem from aggregated items
    requirements = _build_requirements_from_llm_aggregated_billing_items(llm_aggregated_billing_items)

    # 5. Legacy compat chain — debug/export fallback only, NOT primary truth
    #    These fields are kept for backward compatibility with older export templates
    #    and debug inspection. Downstream billing logic should prefer
    #    llm_aggregated_billing_items and requirements.
    standardized = _standardize_billing_lines(
        all_billing_lines,
        quote_context,
        use_llm=use_llm,
    )
    mapped = _map_standardized_billing_resources_to_huawei(standardized)

    # 6. Build diagnostics
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
                reason="billing document — extracted via LLM aggregation path" if is_billing else None,
            )
        )

    message = f"Extracted {len(requirements)} aggregated billing item(s) from {len(billing_documents)} billing document(s) ({len(billing_groups)} groups → {len(llm_aggregated_billing_items)} items)."
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
            detail="Billing documents were detected but no resources could be aggregated.",
            diagnostics=diagnostics.model_dump(),
        )
    return {
        "requirements": requirements,
        "billing_lines": all_billing_lines,
        "billing_groups": billing_groups,
        "llm_aggregated_billing_items": llm_aggregated_billing_items,
        "standardized_billing_resources": standardized,
        "mapped_billing_resources": mapped,
        "diagnostics": diagnostics.model_dump(),
        "audit_log": _append_audit(state, "extract_requirement_items", message),
    }


def _has_capacity_evidence(requirement: RequirementItem) -> bool:
    """Check if a requirement has strong evidence that it represents storage capacity.

    Evidence must come from the source data, not just quantity magnitude:
    - unit text explicitly contains GB/month, Datos almacenados, or similar
    - notes/source SKU explicitly names storage capacity
    - spec already has capacity_gib set from a recognized capacity source

    Just having a large quantity is NOT sufficient evidence.
    """
    unit = (requirement.unit or "").lower()
    raw_lower = requirement.raw_product_name.lower()
    notes = (requirement.notes or "").lower()
    spec_data = requirement.spec.model_dump() if requirement.spec else {}

    # Explicit capacity unit text from source
    capacity_unit_keywords = (
        "datos almacenados", "data stored", "gb/mes", "gb/month",
        "gib/mes", "gib/month", "capacity gib month", "disk month",
        "disco/mes", "metadatos (gb/mes)", "metadata (gb/month)",
    )
    if any(k in unit for k in capacity_unit_keywords):
        return True

    # Source SKU / product_type explicitly names capacity storage
    # (checked in notes which carries vendor/family/type/sku/unit lineage)
    if any(k in notes for k in ("datos almacenados", "data stored", "gb/mes", "gb/month")):
        return True

    # Spec already has capacity_gib from a recognized source (not from unknown reclassification)
    # Only trust if the unit was already capacity-like
    if spec_data.get("capacity_gib") and any(k in unit for k in ("capacity", "gb/mes", "gb/month", "gib/mes", "gib/month")):
        return True

    return False


def _should_reclassify_as_non_capacity_usage(
    requirement: RequirementItem,
) -> tuple[bool, str | None]:
    """Detect when a billing requirement was incorrectly reclassified as capacity.

    Returns (should_reject, reason).
    If should_reject is True, the requirement should NOT be priced as capacity_gib_month.
    """
    product = requirement.normalized_product
    unit = (requirement.unit or "").lower()
    raw_lower = requirement.raw_product_name.lower()
    notes = (requirement.notes or "").lower()

    # Operation/request keywords that indicate the source was NOT capacity
    operation_keywords = (
        "operación", "operation", "lista", "list", "lectura", "read",
        "escritura", "write", "transacción", "transaction", "request",
        "10 000", "10k", "solicitud",
    )

    # If unit is capacity_gib_month but the source (in notes) was operations/requests,
    # it was incorrectly auto-reclassified — reject it
    if unit == "capacity gib month":
        # Check if the source unit (in notes) indicates operations/requests
        if any(k in notes for k in operation_keywords):
            return True, "Source usage is operations/requests, not storage capacity."
        if any(k in raw_lower for k in operation_keywords):
            return True, "Source usage is operations/requests, not storage capacity."
        # Also check: if the notes don't contain any capacity evidence keywords,
        # the reclassification was based on quantity alone — reject
        if not _has_capacity_evidence(requirement.model_copy(update={"unit": "unknown"})):
            return True, "Source usage could not be safely confirmed as storage capacity for GB-month pricing."

    # SFS Turbo / OBS / EVS with unknown unit — must NOT auto-reclassify
    if product in ("SFS Turbo", "OBS", "EVS") and unit in ("unknown", ""):
        if not _has_capacity_evidence(requirement):
            return True, f"{product} with unknown unit lacks capacity evidence — cannot safely price as GB-month."

    # EVS instance hours without disk/capacity evidence
    if product == "EVS" and "instance hour" in unit:
        if not _has_capacity_evidence(requirement):
            return True, "EVS instance hours without disk/capacity evidence — cannot safely price as capacity."

    # RDS user month — not a standard Huawei billing model
    if product == "RDS" and "user month" in unit:
        return True, "RDS user-month is not a standard Huawei Cloud billing model."

    return False, None


def _reclassify_billing_unit_and_product(
    requirement: RequirementItem,
) -> tuple[str | None, str | None, Any]:
    """Reclassify a billing requirement's unit and product when the initial
    aggregation produced an inaccurate unit or product mapping.

    Returns (updated_product, updated_unit, updated_spec) — only the changed
    fields; None means keep the original value.

    Phase Next+5: tightened SFS Turbo unknown→capacity — now requires explicit
    capacity evidence (unit text with GB/month / Datos almacenados, or spec
    with capacity_gib from recognized source). Large quantity alone is NOT
    sufficient to reclassify as capacity.

    Also fixes EVS instance-hours→capacity, ECS Backup→CBR, ECS MySQL→RDS.

    Phase 5C/5E: Protected products (RDS, CBR, OBS, SFS Turbo, VPN, ELB, EIP,
    HSS, etc.) are never redirected by this function — normalize_requirements
    guards them via _BILLING_PROTECTED_PRODUCTS. Only ECS items can be
    reclassified to CBR/RDS when the source text clearly indicates backup/DB.
    """
    product = requirement.normalized_product
    unit = requirement.unit
    spec = requirement.spec
    raw_lower = requirement.raw_product_name.lower()
    spec_data = spec.model_dump() if spec else {}

    # --- SFS Turbo: unknown unit → capacity gib month ONLY with evidence ---
    if product == "SFS Turbo" and unit in ("unknown", ""):
        if _has_capacity_evidence(requirement):
            qty = requirement.quantity or 0
            tier = _infer_obs_sfs_tier(raw_lower, "SFS Turbo")
            sku_text = str(spec_data.get("sku") or "")
            return None, "capacity gib month", StorageSpec(
                sku=sku_text[:40] if sku_text else None,
                tier=tier,
                capacity_gib=qty,
            )
        # No capacity evidence — do NOT reclassify. Keep unknown.
        return None, None, None

    # --- OBS: unknown unit → capacity gib month ONLY with evidence ---
    if product == "OBS" and unit in ("unknown", ""):
        if _has_capacity_evidence(requirement):
            qty = requirement.quantity or 0
            tier = _infer_obs_sfs_tier(raw_lower, "OBS")
            sku_text = str(spec_data.get("sku") or "")
            return None, "capacity gib month", StorageSpec(
                sku=sku_text[:40] if sku_text else None,
                tier=tier,
                capacity_gib=qty,
            )
        return None, None, None

    # --- EVS: instance hours with capacity_gib in spec → capacity gib month ---
    # Only reclassify if there's actual capacity evidence (not just large qty)
    if product == "EVS" and unit in ("instance hours", "unknown", ""):
        if _has_capacity_evidence(requirement):
            capacity = spec_data.get("capacity_gib") or requirement.quantity
            if capacity and capacity > 0:
                tier = spec_data.get("tier")
                sku_text = str(spec_data.get("sku") or "")
                return None, "capacity gib month", StorageSpec(
                    sku=sku_text[:40] if sku_text else None,
                    tier=tier,
                    capacity_gib=capacity,
                )
        # No capacity evidence — do NOT reclassify
        return None, None, None

    # --- ECS: "Backup - Azure VM" → CBR ---
    if product == "ECS" and "backup" in raw_lower and "vm" in raw_lower:
        sku_text = str(spec_data.get("sku") or "")
        return "CBR", unit, GenericSpec(
            sku=sku_text[:40] if sku_text else None,
            description="Azure VM Backup → CBR",
        )

    # --- ECS: MySQL Flexible Server compute → RDS ---
    if product == "ECS" and "mysql" in raw_lower and ("compute" in raw_lower or "núcleo" in raw_lower or "memory optimized" in raw_lower):
        sku_text = str(spec_data.get("sku") or spec_data.get("description") or "")
        # Extract vcore from text
        vcore = None
        vcore_match = re.search(r"(\d+)\s*(?:núcleo|vcore|vcpu|core)", raw_lower)
        if vcore_match:
            vcore = int(vcore_match.group(1))
        desc_parts = ["engine=mysql"]
        if vcore:
            desc_parts.append(f"vcore={vcore}")
        return "RDS", unit, GenericSpec(
            sku=sku_text[:40] if sku_text else None,
            description=" ".join(desc_parts),
        )

    return None, None, None


# ---------------------------------------------------------------------------
# Billing quote reconciliation (Phase Next+5)
# ---------------------------------------------------------------------------

_UNQUOTED_REASON_SUSPICIOUS_RECLASSIFICATION = "suspicious_capacity_reclassification"


def _source_amount_by_requirement(requirement: RequirementItem, state: FlexibleQuoteState) -> float | None:
    """Look up the source billing amount for a requirement from aggregated billing items."""
    agg_items = state.get("llm_aggregated_billing_items", [])
    agg_amount_by_id: dict[str, float] = {}
    for idx, ai in enumerate(agg_items):
        aid = f'billing-agg::{ai.get("source_file", "")}::{idx}'
        agg_amount_by_id[aid] = _to_float(ai.get("amount")) or 0.0
    return agg_amount_by_id.get(requirement.item_id)


def _quoted_vs_source_delta(
    quote_line: FlexibleQuoteLine,
    state: FlexibleQuoteState,
) -> dict[str, Any]:
    """Compute the delta between a quoted line and its source billing amount."""
    # Find the requirement for this quote line
    requirements = state.get("quote_ready_items", []) + state.get("unquoted_items", [])
    req_by_id: dict[str, RequirementItem] = {}
    for raw in requirements:
        r = RequirementItem.model_validate(raw)
        req_by_id[r.item_id] = r

    requirement = req_by_id.get(quote_line.requirement_item_id)
    source_amount = _source_amount_by_requirement(requirement, state) if requirement else None

    quoted_amount = quote_line.monthly_price
    if source_amount is not None and source_amount != 0:
        delta = quoted_amount - source_amount
        ratio = quoted_amount / source_amount
    else:
        delta = quoted_amount
        ratio = float("inf") if quoted_amount > 0 else 0.0

    return {
        "line_id": quote_line.line_id,
        "product": quote_line.product,
        "quoted_amount": round(quoted_amount, 2),
        "source_amount": round(source_amount, 2) if source_amount is not None else None,
        "delta": round(delta, 2),
        "delta_ratio": round(ratio, 4) if ratio != float("inf") else None,
    }


def _is_suspicious_billing_quote(
    quote_line: FlexibleQuoteLine,
    state: FlexibleQuoteState,
) -> bool:
    """Check if a quoted line has a suspiciously high price vs source amount."""
    delta_info = _quoted_vs_source_delta(quote_line, state)
    source_amount = delta_info.get("source_amount")
    ratio = delta_info.get("delta_ratio")

    if source_amount is None or source_amount == 0:
        return False  # No source to compare against

    # Suspicious if quoted > source * 1.5 for storage products
    product = quote_line.product
    if product in ("SFS Turbo", "OBS", "EVS", "RDS"):
        if ratio is not None and ratio > 1.5:
            return True

    # Suspicious if quoted > source * 2.0 for any product
    if ratio is not None and ratio > 2.0:
        return True

    return False


def _analyze_billing_quote_reconciliation(state: FlexibleQuoteState) -> dict[str, Any]:
    """Full reconciliation: compare quoted amounts to source billing amounts.

    Identifies:
    - Lines where quoted > source * 1.2 (overstated)
    - Lines that were suspiciously reclassified as capacity
    - Top positive deltas by product
    """
    quote_lines = [FlexibleQuoteLine.model_validate(ql) for ql in state.get("quote_lines", [])]

    # Compute deltas for all lines
    all_deltas = [_quoted_vs_source_delta(ql, state) for ql in quote_lines]

    # Suspicious lines
    suspicious = [d for d in all_deltas if _is_suspicious_billing_quote(
        FlexibleQuoteLine.model_validate(next(ql for ql in state.get("quote_lines", []) if ql.get("line_id") == d["line_id"])),
        state,
    )]

    # Top positive deltas (overstated quotes)
    positive_deltas = sorted(
        [d for d in all_deltas if d["delta"] > 0 and d["source_amount"] is not None],
        key=lambda x: -x["delta"],
    )[:10]

    # Suspicious reclassification items (from unquoted)
    reclassification_items = []
    for raw in state.get("unquoted_items", []):
        item = RequirementItem.model_validate(raw)
        reason_class = _classify_unquoted_reason(item)
        if reason_class == _UNQUOTED_REASON_SUSPICIOUS_RECLASSIFICATION:
            reclassification_items.append({
                "item_id": item.item_id,
                "product": item.normalized_product,
                "unit": item.unit,
                "quantity": item.quantity,
                "reason": item.status_reason,
            })

    # Summary stats
    total_quoted = sum(d["quoted_amount"] for d in all_deltas)
    total_source = sum(d["source_amount"] for d in all_deltas if d["source_amount"] is not None)
    overstated_total = sum(d["delta"] for d in positive_deltas)

    return {
        "suspicious_count": len(suspicious),
        "suspicious_items": suspicious[:10],
        "top_positive_deltas": positive_deltas,
        "reclassification_count": len(reclassification_items),
        "reclassification_items": reclassification_items[:10],
        "total_quoted": round(total_quoted, 2),
        "total_alignable_source": round(total_source, 2),
        "overstated_total": round(overstated_total, 2),
    }


def normalize_requirements(state: FlexibleQuoteState) -> FlexibleQuoteState:
    _report_progress(state, "normalize_requirements", "running", "Normalizing products, regions, and specs.")
    quote_context = FlexibleQuoteContext.model_validate(state["quote_context"])
    # Phase 5C: Protected products — once set by billing aggregation, normalize
    # must NOT redirect them to a different product. Only spec enrichment and
    # unit refinement are allowed for these products.
    _BILLING_PROTECTED_PRODUCTS = frozenset({
        "RDS", "CBR", "OBS", "SFS Turbo", "VPN", "ELB", "EIP", "HSS",
        "DDS", "DWS", "WAF", "NAT Gateway", "Direct Connect as a Service",
    })
    normalized: list[dict[str, Any]] = []
    for item in state["requirements"]:
        requirement = RequirementItem.model_validate(item)
        is_billing = requirement.quantity_source == "billing_standardized"
        if is_billing and requirement.normalized_product:
            product = requirement.normalized_product
            spec = requirement.spec
            # Enrich billing spec with vendor-specific shape normalization
            enriched_spec = None
            if product == "ECS":
                enriched_spec = _normalize_billing_compute_spec(requirement)
            elif product in ("EVS", "OBS", "SFS Turbo"):
                enriched_spec = _normalize_billing_storage_spec(requirement)
            elif product == "RDS":
                enriched_spec = _normalize_billing_rds_spec(requirement)
            if enriched_spec is not None:
                spec = enriched_spec
            # Phase Next+4: reclassify unit/product after spec enrichment
            # Phase 5C: For protected products, only allow unit/spec refinement,
            # never product redirection. This prevents normalize from undoing
            # the billing aggregation's product direction.
            reclass_product, reclass_unit, reclass_spec = _reclassify_billing_unit_and_product(
                requirement.model_copy(update={"spec": spec})
            )
            if reclass_product is not None and product not in _BILLING_PROTECTED_PRODUCTS:
                product = reclass_product
            if reclass_unit is not None:
                unit = reclass_unit
            else:
                unit = requirement.unit
            if reclass_spec is not None:
                spec = reclass_spec
        else:
            product = _normalize_product_name(requirement.raw_product_name)
            spec = requirement.spec
            unit = requirement.unit
            if isinstance(spec, dict):
                spec = _parse_spec_text(product, spec.get("description") or spec.get("tier") or spec.get("sku"))
            elif spec:
                spec_data = spec.model_dump()
                if product == "ECS" and (spec_data.get("vcpu") or spec_data.get("memory_gib")):
                    spec = spec
                else:
                    spec = _parse_spec_text(product, " ".join(str(value) for value in spec_data.values() if value))
        normalized.append(
            requirement.model_copy(
                update={
                    "normalized_product": product,
                    "region": requirement.region or quote_context.region,
                    "spec": spec,
                    "unit": unit,
                }
            ).model_dump()
        )
    message = "Normalized products, regions, and specs."
    _report_progress(state, "normalize_requirements", "completed", message)
    return {"requirements": normalized, "audit_log": _append_audit(state, "normalize_requirements", message)}


def deduplicate_items(state: FlexibleQuoteState) -> FlexibleQuoteState:
    _report_progress(state, "deduplicate_items", "running", "Deduplicating requirement items.")
    # Billing-derived requirements already represent grouped source resources and
    # carry stable lineage ids used by downstream detail export. Keep them
    # one-to-one instead of collapsing by product/spec.
    billing_items: list[RequirementItem] = []
    grouped: dict[str, RequirementItem] = {}
    for item in state["requirements"]:
        requirement = RequirementItem.model_validate(item)
        if requirement.quantity_source == "billing_standardized":
            billing_items.append(requirement)
            continue
        spec_key = json.dumps(requirement.spec.model_dump(), sort_keys=True) if requirement.spec else ""
        key = "|".join([str(requirement.normalized_product), str(requirement.region), spec_key, requirement.source_file])
        existing = grouped.get(key)
        if existing and existing.quantity is not None and requirement.quantity is not None:
            grouped[key] = existing.model_copy(update={"quantity": existing.quantity + requirement.quantity})
        else:
            grouped[key] = requirement
    deduped = [item.model_dump() for item in billing_items] + [item.model_dump() for item in grouped.values()]
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

        # Phase Next+5: quote gating — reject suspicious capacity reclassification
        if status == "ready" and is_billing:
            should_reject, reject_reason = _should_reclassify_as_non_capacity_usage(requirement)
            if should_reject:
                status = "needs_price_confirmation"
                reason = reject_reason or "Source usage could not be safely confirmed as storage capacity for GB-month pricing."

        updated = requirement.model_copy(update={"normalized_product": product, "status": status, "status_reason": reason})
        if status == "ready":
            ready_items.append(updated.model_dump())
            raw_item.update(updated.model_dump())
        elif status == "needs_price_confirmation":
            unquoted.append(updated.model_dump())
            raw_item.update(updated.model_dump())
        else:
            # Phase Next+7: blocker triage — check if this blocker can be safely
            # downgraded to unquoted instead of remaining a blocker.
            should_downgrade, downgrade_reason = _should_downgrade_blocker_to_unquoted(updated)
            if should_downgrade:
                # Downgrade: move to unquoted with triage note
                downgraded = updated.model_copy(update={
                    "status": "needs_price_confirmation",
                    "status_reason": f"{reason} [TRIAGE: {downgrade_reason}]",
                })
                unquoted.append(downgraded.model_dump())
                raw_item.update(downgraded.model_dump())
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
    safe_usage_quoted_count = 0
    for raw_item in state.get("quote_ready_items", []):
        requirement = RequirementItem.model_validate(raw_item)
        product = requirement.normalized_product
        if not product or not requirement.region:
            continue
        candidates = [item for item in catalog if item.product == product and item.region == requirement.region and item.confirmed and item.status == "confirmed" and item.price is not None]
        # Spec-aware matching
        matched_component = _match_price_component_by_spec(requirement, candidates)
        match_rationale_extra = ""
        # Phase Next+4: if spec match failed, try product-specific candidate matchers
        if matched_component is None:
            if product == "SFS Turbo":
                matched_component = _match_sfs_turbo_component_by_tier_and_unit(requirement, candidates)
                if matched_component:
                    match_rationale_extra = "SFS Turbo tier+unit candidate match (Phase Next+4)"
            elif product == "ECS":
                matched_component = _match_ecs_component_by_shape_family(requirement, candidates)
                if matched_component:
                    match_rationale_extra = "ECS compatible family fallback by vCPU+memory (Phase Next+4)"
            elif product == "RDS":
                matched_component = _match_rds_component_by_engine_family(requirement, candidates)
                if matched_component:
                    match_rationale_extra = "RDS engine+family candidate match (Phase Next+4)"
        # Phase Next+6: safe usage matching for capacity-based usage items
        # Only runs if no match yet AND requirement is billing-derived with usage unit
        if matched_component is None and requirement.quantity_source == "billing_standardized":
            usage_candidates = _candidate_usage_components_for_requirement(requirement, catalog)
            if usage_candidates:
                if product == "OBS":
                    matched_component = _match_obs_usage_component(requirement, usage_candidates)
                    if matched_component:
                        match_rationale_extra = "OBS safe capacity usage match (Phase Next+6)"
                elif product == "SFS Turbo":
                    matched_component = _match_sfs_usage_component(requirement, usage_candidates)
                    if matched_component:
                        match_rationale_extra = "SFS Turbo safe capacity usage match (Phase Next+6)"
                elif product == "RDS":
                    matched_component = _match_rds_storage_component(requirement, usage_candidates)
                    if matched_component:
                        match_rationale_extra = "RDS safe storage usage match (Phase Next+6)"
                elif product == "CBR":
                    matched_component = _match_cbr_storage_component(requirement, usage_candidates)
                    if matched_component:
                        match_rationale_extra = "CBR safe backup storage usage match (Phase Next+6)"
                # Final safety gate
                if matched_component:
                    is_safe, unsafe_reason = _is_safe_usage_quote(requirement, matched_component)
                    if not is_safe:
                        matched_component = None
                        match_rationale_extra = ""
                    else:
                        safe_usage_quoted_count += 1
        if matched_component is None:
            # Determine stable unquoted reason
            unquoted_reason = _stable_unquoted_reason(requirement, candidates)
            unquoted.append(requirement.model_copy(update={"status": "needs_price_confirmation", "status_reason": unquoted_reason}))
            continue
        # Billing price semantics check (product-aware unit compatibility)
        can_price, semantics_reason = _billing_can_price_requirement(requirement, matched_component)
        if not can_price:
            unquoted_reason = _stable_unquoted_reason(requirement, candidates, semantics_reason)
            unquoted.append(
                requirement.model_copy(
                    update={
                        "status": "needs_price_confirmation",
                        "status_reason": unquoted_reason,
                    }
                )
            )
            continue
        # Enrich resolved component with per-item traceability
        resolved_entry = matched_component.model_dump()
        resolved_entry["requirement_item_id"] = requirement.item_id
        rationale = _billing_requirement_assumption(requirement, matched_component)
        if match_rationale_extra:
            rationale = f"{rationale}; {match_rationale_extra}"
        resolved_entry["match_rationale"] = rationale
        resolved.append(resolved_entry)
    message = f"Resolved {len(resolved)} price component(s) ({safe_usage_quoted_count} via safe usage matching)."
    _report_progress(state, "resolve_price_components", "completed", message)
    return {
        "price_components": resolved,
        "unquoted_items": [item.model_dump() for item in unquoted],
        "safe_usage_quoted_count": safe_usage_quoted_count,
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

    # -- ECS: exact sku match, then vcpu+memory, then family hint --------
    if product == "ECS":
        # 1. Exact SKU match
        if sku_hint:
            exact = [c for c in candidates if (c.sku or "").lower() == sku_hint]
            if exact:
                return exact[0]
        # 2. vCPU + memory match (from Azure shape normalization)
        vcpu_hint = spec_data.get("vcpu")
        mem_hint = spec_data.get("memory_gib")
        if vcpu_hint and mem_hint:
            # Try to match by parsing catalog SKU patterns like "c7n.2xlarge.4" or "x0.4u.8g"
            vcpu_int = int(vcpu_hint) if isinstance(vcpu_hint, (int, float)) else None
            mem_float = float(mem_hint) if isinstance(mem_hint, (int, float)) else None
            if vcpu_int and mem_float:
                vcpu_mem_match = []
                for c in candidates:
                    c_sku = (c.sku or "").lower()
                    # Parse Huawei SKU patterns: x0.4u.8g, c7n.2xlarge.4, m7n.xlarge.8
                    # Pattern: prefix.Nu.Mg or prefix.Nxlarge.M
                    u_match = re.search(r"\.(\d+)u\.(\d+)g", c_sku)
                    if u_match:
                        c_vcpu = int(u_match.group(1))
                        c_mem = int(u_match.group(2))
                        if c_vcpu == vcpu_int and c_mem == int(mem_float):
                            vcpu_mem_match.append(c)
                            continue
                    # Pattern: .Nxlarge.M or .Nlarge.M
                    xl_match = re.search(r"\.(\d*)(?:x)?large\.(\d+)", c_sku)
                    if xl_match:
                        multiplier_str = xl_match.group(1)
                        multiplier = int(multiplier_str) if multiplier_str else 1
                        c_vcpu = multiplier * 4  # xlarge = 4 vCPU base
                        c_mem_multiplier = int(xl_match.group(2))
                        if c_vcpu == vcpu_int:
                            vcpu_mem_match.append(c)
                            continue
                if vcpu_mem_match:
                    # If multiple matches, prefer general computing family
                    general = [c for c in vcpu_mem_match if "general" in (c.family or "").lower()]
                    if general:
                        return general[0]
                    return vcpu_mem_match[0]
        # 3. Family substring match (e.g. "d8" matches "General computing D8")
        if sku_hint:
            family_hint = sku_hint.split()[0] if sku_hint else ""
            if family_hint:
                family_match = [c for c in candidates if family_hint in (c.family or "").lower() or family_hint in (c.sku or "").lower()]
                if family_match:
                    return family_match[0]
        # No confident match — do NOT fall through to first candidate
        return None

    # -- EVS: tier match (with snapshot protection) ----------------------
    if product == "EVS":
        # Block snapshot items from matching disk catalog
        sku_lower = sku_hint.lower()
        if any(k in sku_lower for k in ("snapshot", "instantánea", "backup", "copia")):
            return None
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

    # -- RDS: engine-aware matching (with vcore hint) --------------------
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
                # Try vcore hint from spec normalization
                vcore_hint = spec_data.get("vcore")
                if vcore_hint and len(engine_match) > 1:
                    # Pick the cheapest RDS that's >= vcore (conservative)
                    # For now, pick smallest/cheapest as conservative
                    engine_match.sort(key=lambda c: c.price or float("inf"))
                    return engine_match[0]
                # Single engine match — use it
                if len(engine_match) == 1:
                    return engine_match[0]
                # Multiple RDS for same engine — pick smallest/cheapest as conservative
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
        # For capacity-based requirements, default to standard tier
        if requirement.unit and "capacity" in (requirement.unit or "").lower():
            default_tier = [c for c in candidates if "standard" in ((c.tier or "").lower(), (c.sku or "").lower())]
            if default_tier:
                return default_tier[0]
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


# ---------------------------------------------------------------------------
# Candidate matching helpers (Phase Next+4)
# ---------------------------------------------------------------------------

def _candidate_price_components_for_requirement(
    requirement: RequirementItem,
    catalog: list[PriceComponent],
) -> list[PriceComponent]:
    """Return confirmed catalog candidates matching the requirement's product and region."""
    if not requirement.normalized_product or not requirement.region:
        return []
    return [
        item for item in catalog
        if item.product == requirement.normalized_product
        and item.region == requirement.region
        and item.confirmed
        and item.status == "confirmed"
        and item.price is not None
    ]


def _filter_candidates_by_billing_product_semantics(
    requirement: RequirementItem,
    candidates: list[PriceComponent],
) -> list[PriceComponent]:
    """Filter candidates by billing price semantic compatibility.

    Only keeps candidates whose catalog unit is compatible with the
    requirement's billing semantic family.
    """
    semantic = _billing_requirement_price_semantic(requirement)
    product = requirement.normalized_product or ""
    compatible_products = _COMPATIBLE_SEMANTICS.get(semantic, {})
    compatible_units = compatible_products.get(product, set())

    if not compatible_units:
        return candidates  # No filter defined — return all

    filtered = []
    for c in candidates:
        comp_unit = (c.unit or "").lower()
        for pattern in compatible_units:
            if pattern in comp_unit:
                filtered.append(c)
                break
    return filtered


def _match_sfs_turbo_component_by_tier_and_unit(
    requirement: RequirementItem,
    candidates: list[PriceComponent],
) -> PriceComponent | None:
    """Match SFS Turbo requirement to catalog by tier and unit.

    For capacity_gib_month: match GB-month candidates, prefer tier match.
    For unknown unit: only match if source evidence confirms storage capacity
    (Phase Next+6: unknown no longer auto-treated as capacity).
    """
    req_unit = (requirement.unit or "").lower()
    if "capacity gib month" in req_unit or "gb/month" in req_unit:
        pass  # explicit capacity — proceed
    elif req_unit == "unknown" or req_unit == "":
        # Phase Next+6: unknown unit requires capacity evidence
        if not _billing_has_capacity_evidence(requirement):
            return None
    else:
        return None

    # Filter to GB-month candidates
    gb_candidates = [c for c in candidates if "gb-month" in (c.unit or "").lower()]
    if not gb_candidates:
        return None

    # Try tier match from spec
    spec_data = requirement.spec.model_dump() if requirement.spec else {}
    tier_hint = str(spec_data.get("tier") or "").lower().strip()
    if tier_hint:
        tier_match = [c for c in gb_candidates if tier_hint in ((c.tier or "").lower(), (c.sku or "").lower())]
        if tier_match:
            return tier_match[0]

    # Infer tier from raw product name
    raw_lower = requirement.raw_product_name.lower()
    inferred_tier = _infer_obs_sfs_tier(raw_lower, "SFS Turbo")
    if inferred_tier:
        tier_match = [c for c in gb_candidates if inferred_tier in ((c.tier or "").lower(), (c.sku or "").lower())]
        if tier_match:
            return tier_match[0]

    # Single GB-month candidate is safe
    if len(gb_candidates) == 1:
        return gb_candidates[0]

    # Multiple GB-month candidates without tier — default to standard
    standard = [c for c in gb_candidates if "standard" in ((c.tier or "").lower(), (c.sku or "").lower())]
    if standard:
        return standard[0]

    return None


def _match_ecs_component_by_shape_family(
    requirement: RequirementItem,
    candidates: list[PriceComponent],
) -> PriceComponent | None:
    """Match ECS requirement by vCPU+memory even when SKU names differ.

    This is a compatible family fallback: if vCPU+memory match exactly
    but the catalog SKU doesn't match the Azure shape name, we still
    accept the match (with an assumption).
    """
    if not requirement.spec:
        return None
    spec_data = requirement.spec.model_dump()
    vcpu_hint = spec_data.get("vcpu")
    mem_hint = spec_data.get("memory_gib")
    if not vcpu_hint or not mem_hint:
        return None

    vcpu_int = int(vcpu_hint) if isinstance(vcpu_hint, (int, float)) else None
    mem_float = float(mem_hint) if isinstance(mem_hint, (int, float)) else None
    if not vcpu_int or not mem_float:
        return None

    # Parse catalog SKU patterns for vCPU+memory match
    matches: list[PriceComponent] = []
    for c in candidates:
        c_sku = (c.sku or "").lower()
        # Pattern: prefix.Nu.Mg
        u_match = re.search(r"\.(\d+)u\.(\d+)g", c_sku)
        if u_match:
            c_vcpu = int(u_match.group(1))
            c_mem = int(u_match.group(2))
            if c_vcpu == vcpu_int and c_mem == int(mem_float):
                matches.append(c)
                continue
        # Pattern: .Nxlarge.M or .Nlarge.M
        xl_match = re.search(r"\.(\d*)(?:x)?large\.(\d+)", c_sku)
        if xl_match:
            multiplier_str = xl_match.group(1)
            multiplier = int(multiplier_str) if multiplier_str else 1
            c_vcpu = multiplier * 4
            if c_vcpu == vcpu_int:
                matches.append(c)
                continue

    if not matches:
        return None

    # Prefer general computing family
    general = [c for c in matches if "general" in (c.family or "").lower()]
    if general:
        return general[0]
    return matches[0]


def _match_rds_component_by_engine_family(
    requirement: RequirementItem,
    candidates: list[PriceComponent],
) -> PriceComponent | None:
    """Match RDS requirement by engine + vcore hint.

    For MySQL compute (instance hours): match mysql.* SKUs.
    """
    if not requirement.spec:
        return None
    spec_data = requirement.spec.model_dump()
    desc = str(spec_data.get("description") or spec_data.get("sku") or "").lower()
    raw_lower = requirement.raw_product_name.lower()

    # Identify engine
    engine_hint = ""
    for engine in ["mysql", "postgresql", "sqlserver", "gaussdb", "mariadb"]:
        if engine in desc or engine in raw_lower:
            engine_hint = engine
            break
    if not engine_hint:
        return None

    # Filter candidates by engine
    engine_match = [c for c in candidates if engine_hint in ((c.sku or "").lower() + " " + (c.family or "").lower())]
    if not engine_match:
        return None

    # Try vcore hint
    vcore = None
    vcore_match = re.search(r"vcore[=:](\d+)", desc)
    if vcore_match:
        vcore = int(vcore_match.group(1))
    if not vcore:
        vcore_match2 = re.search(r"(\d+)\s*(?:núcleo|vcore|vcpu|core)", raw_lower)
        if vcore_match2:
            vcore = int(vcore_match2.group(1))

    if vcore:
        # Try to match by vcore in SKU (e.g., mysql.s2.medium = 1 vcore)
        # Huawei RDS naming: mysql.s2.{size} where medium=1vcore, large=2vcore, xlarge=4vcore
        vcore_size_map = {1: "medium", 2: "large", 4: "xlarge"}
        target_size = vcore_size_map.get(vcore)
        if target_size:
            size_match = [c for c in engine_match if target_size in (c.sku or "").lower()]
            if size_match:
                return size_match[0]

    # Single engine match — safe
    if len(engine_match) == 1:
        return engine_match[0]

    # Multiple — pick cheapest (conservative)
    engine_match.sort(key=lambda c: c.price or float("inf"))
    return engine_match[0]


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


# ---------------------------------------------------------------------------
# Safe usage matching helpers (Phase Next+6)
# ---------------------------------------------------------------------------

# Capacity evidence keywords in source unit / notes / raw product name
_CAPACITY_EVIDENCE_KEYWORDS = (
    "gb/month", "gb/mes", "gib/mes", "gib/month",
    "datos almacenados", "stored data", "data stored",
    "capacity gib", "disk month", "disco/mes",
)

# Non-capacity keywords that disqualify a line from being treated as capacity
_NON_CAPACITY_KEYWORDS = (
    "operacion", "operation", "request", "metadata", "metadato",
    "list", "write", "read", "transaction", "throughput",
    "ops", "io", "traffic", "bandwidth",
)


def _billing_has_capacity_evidence(requirement: RequirementItem) -> bool:
    """Check if a billing requirement has strong evidence of being storage capacity.

    Evidence sources:
    - Source unit text contains capacity keywords (GB/month, Datos almacenados, etc.)
    - Notes contain capacity unit evidence
    - Spec already has a credible capacity_gib value
    """
    # Check spec capacity
    if requirement.spec:
        spec_data = requirement.spec.model_dump() if hasattr(requirement.spec, "model_dump") else requirement.spec
        cap = spec_data.get("capacity_gib")
        if cap is not None and cap > 0:
            return True

    # Check source unit
    req_unit = (requirement.unit or "").lower()
    for kw in _CAPACITY_EVIDENCE_KEYWORDS:
        if kw in req_unit:
            return True

    # Check notes for source unit evidence
    notes = (requirement.notes or "").lower()
    # Look for "unit=..." patterns in notes which carry the original source unit
    unit_match = re.search(r"unit=([^|]+)", notes)
    if unit_match:
        source_unit = unit_match.group(1).lower().strip()
        for kw in _CAPACITY_EVIDENCE_KEYWORDS:
            if kw in source_unit:
                return True
        # If source unit contains non-capacity keywords, explicitly NOT capacity
        for kw in _NON_CAPACITY_KEYWORDS:
            if kw in source_unit:
                return False

    # Check raw product name for storage capacity hints
    raw = (requirement.raw_product_name or "").lower()
    # "Almacenamiento" (storage) in raw name is a capacity hint for RDS
    if "almacenamiento" in raw or "storage" in raw:
        # But only if not mixed with non-capacity keywords
        if not any(kw in raw for kw in ("io", "paid", "operation", "request")):
            return True

    return False


def _billing_usage_semantic(requirement: RequirementItem) -> str:
    """Classify a billing requirement's usage type for safe matching.

    Returns one of:
    - "capacity_gib_month" — storage capacity, compatible with GB-month pricing
    - "ops_10k" — operations/requests, NOT compatible with capacity pricing
    - "traffic_gb" — traffic/bandwidth, NOT compatible with capacity pricing
    - "request_usage" — request-based, NOT compatible with capacity pricing
    - "unknown" — cannot safely classify
    """
    req_unit = (requirement.unit or "").lower()

    # Explicit capacity
    if any(k in req_unit for k in ("capacity gib month", "gb/month", "gib/mes", "gb/mes", "disk month", "disco/mes")):
        return "capacity_gib_month"

    # Explicit non-capacity
    if any(k in req_unit for k in ("ops 10k", "requests million", "operation")):
        return "ops_10k"
    if any(k in req_unit for k in ("traffic gb", "traffic")):
        return "traffic_gb"
    if "user month" in req_unit:
        return "request_usage"

    # Unknown unit — check evidence
    if req_unit in ("unknown", ""):
        if _billing_has_capacity_evidence(requirement):
            return "capacity_gib_month"
        return "unknown"

    return "unknown"


def _candidate_usage_components_for_requirement(
    requirement: RequirementItem,
    catalog: list[PriceComponent],
) -> list[PriceComponent]:
    """Return confirmed catalog candidates for a requirement's product and region
    that have GB-month unit (suitable for capacity usage pricing)."""
    if not requirement.normalized_product or not requirement.region:
        return []
    return [
        item for item in catalog
        if item.product == requirement.normalized_product
        and item.region == requirement.region
        and item.confirmed
        and item.status == "confirmed"
        and item.price is not None
        and "gb-month" in (item.unit or "").lower()
    ]


def _match_obs_usage_component(
    requirement: RequirementItem,
    candidates: list[PriceComponent],
) -> PriceComponent | None:
    """Safe OBS usage matching: only capacity_gib_month -> OBS GB-month.

    Explicitly blocks: ops_10k, traffic, unknown without evidence.
    """
    usage_sem = _billing_usage_semantic(requirement)
    if usage_sem != "capacity_gib_month":
        return None

    # Must have capacity evidence
    if not _billing_has_capacity_evidence(requirement):
        return None

    # Filter to GB-month candidates
    gb_candidates = [c for c in candidates if "gb-month" in (c.unit or "").lower()]
    if not gb_candidates:
        return None

    # Tier match from spec or raw product name
    spec_data = requirement.spec.model_dump() if hasattr(requirement.spec, "model_dump") else (requirement.spec or {})
    tier_hint = str(spec_data.get("tier") or "").lower().strip()
    if tier_hint:
        tier_match = [c for c in gb_candidates if tier_hint in ((c.tier or "").lower(), (c.sku or "").lower())]
        if tier_match:
            return tier_match[0]

    raw_lower = requirement.raw_product_name.lower()
    inferred_tier = _infer_obs_sfs_tier(raw_lower, "OBS")
    if inferred_tier:
        tier_match = [c for c in gb_candidates if inferred_tier in ((c.tier or "").lower(), (c.sku or "").lower())]
        if tier_match:
            return tier_match[0]

    # Default to standard
    standard = [c for c in gb_candidates if "standard" in ((c.tier or "").lower(), (c.sku or "").lower())]
    if standard:
        return standard[0]

    if len(gb_candidates) == 1:
        return gb_candidates[0]

    return None


def _match_sfs_usage_component(
    requirement: RequirementItem,
    candidates: list[PriceComponent],
) -> PriceComponent | None:
    """Safe SFS Turbo usage matching: only capacity_gib_month -> SFS Turbo GB-month.

    Explicitly blocks: metadata, ops_10k, requests, throughput-like unknown.
    """
    usage_sem = _billing_usage_semantic(requirement)
    if usage_sem != "capacity_gib_month":
        return None

    # Must have capacity evidence
    if not _billing_has_capacity_evidence(requirement):
        return None

    # Check notes for non-capacity keywords (metadata, list, write, read, transaction)
    notes = (requirement.notes or "").lower()
    unit_match = re.search(r"unit=([^|]+)", notes)
    if unit_match:
        source_unit = unit_match.group(1).lower().strip()
        for kw in _NON_CAPACITY_KEYWORDS:
            if kw in source_unit:
                return None

    # Filter to GB-month candidates
    gb_candidates = [c for c in candidates if "gb-month" in (c.unit or "").lower()]
    if not gb_candidates:
        return None

    # Tier match
    spec_data = requirement.spec.model_dump() if hasattr(requirement.spec, "model_dump") else (requirement.spec or {})
    tier_hint = str(spec_data.get("tier") or "").lower().strip()
    if tier_hint:
        tier_match = [c for c in gb_candidates if tier_hint in ((c.tier or "").lower(), (c.sku or "").lower())]
        if tier_match:
            return tier_match[0]

    raw_lower = requirement.raw_product_name.lower()
    inferred_tier = _infer_obs_sfs_tier(raw_lower, "SFS Turbo")
    if inferred_tier:
        tier_match = [c for c in gb_candidates if inferred_tier in ((c.tier or "").lower(), (c.sku or "").lower())]
        if tier_match:
            return tier_match[0]

    # Default to standard
    standard = [c for c in gb_candidates if "standard" in ((c.tier or "").lower(), (c.sku or "").lower())]
    if standard:
        return standard[0]

    if len(gb_candidates) == 1:
        return gb_candidates[0]

    return None


def _match_rds_storage_component(
    requirement: RequirementItem,
    candidates: list[PriceComponent],
) -> PriceComponent | None:
    """Safe RDS storage usage matching: only capacity_gib_month -> RDS GB-month.

    Only quotes if catalog has a RDS component with GB-month unit.
    Explicitly blocks: paid IO, requests, user month -> instance-month.
    """
    usage_sem = _billing_usage_semantic(requirement)
    if usage_sem != "capacity_gib_month":
        return None

    # Must have capacity evidence
    if not _billing_has_capacity_evidence(requirement):
        return None

    # Only match if catalog has a GB-month RDS component
    gb_candidates = [c for c in candidates if "gb-month" in (c.unit or "").lower()]
    if not gb_candidates:
        return None

    # Single GB-month candidate is safe
    if len(gb_candidates) == 1:
        return gb_candidates[0]

    # Multiple — prefer standard/general tier
    standard = [c for c in gb_candidates if "standard" in ((c.tier or "").lower(), (c.sku or "").lower())]
    if standard:
        return standard[0]

    return gb_candidates[0]


def _match_cbr_storage_component(
    requirement: RequirementItem,
    candidates: list[PriceComponent],
) -> PriceComponent | None:
    """Safe CBR backup storage matching: only capacity_gib_month -> CBR GB-month.

    Only quotes if catalog has a CBR component with GB-month unit.
    Explicitly blocks: backup storage -> protected-server-month.
    """
    usage_sem = _billing_usage_semantic(requirement)
    if usage_sem != "capacity_gib_month":
        return None

    # Must have capacity evidence
    if not _billing_has_capacity_evidence(requirement):
        return None

    # Only match if catalog has a GB-month CBR component
    gb_candidates = [c for c in candidates if "gb-month" in (c.unit or "").lower()]
    if not gb_candidates:
        return None

    if len(gb_candidates) == 1:
        return gb_candidates[0]

    return gb_candidates[0]


def _is_safe_usage_quote(
    requirement: RequirementItem,
    component: PriceComponent,
) -> tuple[bool, str | None]:
    """Final safety gate for usage-based quotes.

    Returns (is_safe, reason_if_unsafe).
    Ensures usage quote doesn't bypass reconciliation guard.
    """
    # Must pass billing semantics check
    can_price, reason = _billing_can_price_requirement(requirement, component)
    if not can_price:
        return False, reason

    # Usage semantic must be capacity
    usage_sem = _billing_usage_semantic(requirement)
    if usage_sem != "capacity_gib_month":
        return False, f"Usage semantic '{usage_sem}' is not safe for capacity pricing."

    # Must have capacity evidence
    if not _billing_has_capacity_evidence(requirement):
        return False, "No capacity evidence in source data — cannot safely quote as GB-month."

    # Catalog component must be GB-month
    comp_unit = (component.unit or "").lower()
    if "gb-month" not in comp_unit:
        return False, f"Catalog unit '{component.unit}' is not GB-month — incompatible with capacity usage."

    return True, None


# ---------------------------------------------------------------------------
# Billing price semantics (Phase Next)
# ---------------------------------------------------------------------------

# Semantic families for billing requirement units
_BILLING_SEMANTIC_INSTANCE_MONTH = "instance_month"
_BILLING_SEMANTIC_CAPACITY_MONTH = "capacity_month"
_BILLING_SEMANTIC_GATEWAY_MONTH = "gateway_month"
_BILLING_SEMANTIC_IP_MONTH = "ip_month"
_BILLING_SEMANTIC_PROTECTED_RESOURCE_MONTH = "protected_resource_month"
_BILLING_SEMANTIC_TRAFFIC_USAGE = "traffic_usage"
_BILLING_SEMANTIC_REQUEST_USAGE = "request_usage"
_BILLING_SEMANTIC_UNKNOWN = "unknown"

# Which semantic families are compatible with which catalog unit patterns
# Key: semantic family of the requirement
# Value: set of (product, catalog_unit_substring) pairs that are compatible
_COMPATIBLE_SEMANTICS: dict[str, dict[str, set[str]]] = {
    _BILLING_SEMANTIC_INSTANCE_MONTH: {
        "ECS": {"instance-month"},
        "RDS": {"instance-month"},
        "ELB": {"instance-month"},
        "WAF": {"instance-month"},
        "DDS": {"instance-month"},
        "GaussDB": {"instance-month"},
        "DWS": {"node-month"},
    },
    _BILLING_SEMANTIC_CAPACITY_MONTH: {
        "EVS": {"gb-month"},
        "OBS": {"gb-month"},
        "SFS Turbo": {"gb-month"},
    },
    _BILLING_SEMANTIC_GATEWAY_MONTH: {
        "VPN": {"gateway-month", "connection-month"},
        "NAT Gateway": {"gateway-month"},
    },
    _BILLING_SEMANTIC_IP_MONTH: {
        "EIP": {"ip-month"},
    },
    _BILLING_SEMANTIC_PROTECTED_RESOURCE_MONTH: {
        "CBR": {"protected-server-month"},
        "HSS": {"server-month"},
    },
    # traffic_usage and request_usage have NO compatible catalog entries
    # by design — they remain unquoted
}


def _billing_requirement_price_semantic(requirement: RequirementItem) -> str:
    """Classify a billing requirement's unit into a pricing semantic family.

    This determines whether the requirement can safely be priced against
    a Huawei Cloud catalog item.
    """
    req_unit = (requirement.unit or "").lower()
    product = requirement.normalized_product

    # Traffic / bandwidth usage — never priceable as month-fee
    if any(k in req_unit for k in ("traffic gb", "traffic")):
        return _BILLING_SEMANTIC_TRAFFIC_USAGE

    # Request / operation usage — never priceable as month-fee
    if any(k in req_unit for k in ("ops 10k", "requests million", "operation")):
        return _BILLING_SEMANTIC_REQUEST_USAGE

    # User-month — request usage (not a standard Huawei billing model)
    if "user month" in req_unit:
        return _BILLING_SEMANTIC_REQUEST_USAGE

    # Unknown unit — cannot safely price
    if req_unit in ("unknown", ""):
        return _BILLING_SEMANTIC_UNKNOWN

    # Capacity GB/month — compatible with storage products only
    if any(k in req_unit for k in ("capacity gib month", "gb/month", "gib/mes", "gb/mes")):
        if product in ("EVS", "OBS", "SFS Turbo"):
            return _BILLING_SEMANTIC_CAPACITY_MONTH
        # RDS storage capacity is GB/month but catalog only has instance-month
        # CBR backup storage is GB/month but catalog only has protected-server-month
        # These are NOT compatible — treat as capacity that can't map to catalog
        return _BILLING_SEMANTIC_CAPACITY_MONTH

    # Disk months — compatible with EVS
    if any(k in req_unit for k in ("disk month", "disco/mes")):
        return _BILLING_SEMANTIC_CAPACITY_MONTH

    # Gateway hours — compatible with VPN/NAT
    if any(k in req_unit for k in ("gateway hour", "hora de puerta de enlace")):
        return _BILLING_SEMANTIC_GATEWAY_MONTH

    # IP hours — compatible with EIP
    if any(k in req_unit for k in ("ip hour", "hora de ip")):
        return _BILLING_SEMANTIC_IP_MONTH

    # vCore hours — compatible with RDS instance-month
    if any(k in req_unit for k in ("vcore hour", "núcleo virtual/hora")):
        if product == "RDS":
            return _BILLING_SEMANTIC_INSTANCE_MONTH
        return _BILLING_SEMANTIC_INSTANCE_MONTH

    # Instance hours — compatible with ECS/RDS/ELB/HSS instance-month
    if any(k in req_unit for k in ("instance hour", "hora de proceso", "instance-month", "gateway-month")):
        # Product-specific routing
        if product == "VPN":
            return _BILLING_SEMANTIC_GATEWAY_MONTH
        if product == "EIP":
            return _BILLING_SEMANTIC_IP_MONTH
        if product == "HSS":
            return _BILLING_SEMANTIC_PROTECTED_RESOURCE_MONTH
        if product == "CBR":
            return _BILLING_SEMANTIC_PROTECTED_RESOURCE_MONTH
        if product in ("EVS", "OBS", "SFS Turbo"):
            # Disk/file/object storage with "instance hours" unit is likely
            # a misclassified usage line — not compatible with capacity pricing
            return _BILLING_SEMANTIC_UNKNOWN
        return _BILLING_SEMANTIC_INSTANCE_MONTH

    return _BILLING_SEMANTIC_UNKNOWN


def _billing_can_price_requirement(
    requirement: RequirementItem,
    component: PriceComponent,
) -> tuple[bool, str]:
    """Check if a billing requirement can be safely priced against a catalog component.

    Returns (is_compatible, reason).
    """
    if requirement.quantity_source != "billing_standardized":
        return True, ""

    semantic = _billing_requirement_price_semantic(requirement)
    product = requirement.normalized_product or ""
    comp_unit = (component.unit or "").lower()

    # Traffic and request usage are never priceable as month-fee
    if semantic == _BILLING_SEMANTIC_TRAFFIC_USAGE:
        return False, (
            f"Traffic/bandwidth usage ({requirement.unit}) cannot be priced "
            f"with {product} {component.unit} catalog item."
        )
    if semantic == _BILLING_SEMANTIC_REQUEST_USAGE:
        return False, (
            f"Request/operation usage ({requirement.unit}) cannot be priced "
            f"with {product} {component.unit} catalog item."
        )
    if semantic == _BILLING_SEMANTIC_UNKNOWN:
        return False, (
            f"Unknown or unclassifiable billing unit ({requirement.unit}) "
            f"cannot be safely priced with {product} {component.unit} catalog item."
        )

    # Check semantic compatibility with catalog
    compatible_products = _COMPATIBLE_SEMANTICS.get(semantic, {})
    compatible_units = compatible_products.get(product, set())

    if compatible_units:
        # Check if the catalog unit matches any compatible unit pattern
        for pattern in compatible_units:
            if pattern in comp_unit:
                return True, ""
        # Semantic is known but catalog unit doesn't match
        return False, (
            f"Billing semantic '{semantic}' for {product} is not compatible "
            f"with catalog unit '{component.unit}'. "
            f"Compatible units: {', '.join(sorted(compatible_units))}."
        )

    # No compatible mapping defined for this (semantic, product) pair
    # This means the semantic is valid but the product doesn't support it
    # via the standard _COMPATIBLE_SEMANTICS table.
    # However, if the catalog component's unit is actually compatible,
    # allow it (e.g., RDS storage GB/month matching a hypothetical RDS GB-month catalog item).
    if semantic == _BILLING_SEMANTIC_CAPACITY_MONTH and product in ("RDS", "CBR"):
        comp_unit_lower = (component.unit or "").lower()
        if "gb" in comp_unit_lower and "month" in comp_unit_lower:
            return True, ""
        return False, (
            f"Storage capacity usage ({requirement.unit}) cannot be priced "
            f"with {product} {component.unit} catalog item. "
            f"{product} catalog only supports instance-month pricing."
        )
    if semantic == _BILLING_SEMANTIC_INSTANCE_MONTH and product in ("EVS", "OBS", "SFS Turbo"):
        return False, (
            f"Instance-hour usage for {product} is likely a misclassified billing line. "
            f"{product} catalog only supports capacity (GB-month) pricing."
        )

    # Default: if no specific rule, be conservative
    return False, (
        f"No compatible pricing semantic defined for "
        f"{product} with billing unit '{requirement.unit}' "
        f"against catalog unit '{component.unit}'."
    )


def _billing_price_semantics(
    requirement: RequirementItem,
    component: PriceComponent,
) -> dict[str, Any]:
    """Return full billing price semantics analysis for a requirement + component pair."""
    semantic = _billing_requirement_price_semantic(requirement)
    can_price, reason = _billing_can_price_requirement(requirement, component)
    return {
        "semantic": semantic,
        "can_price": can_price,
        "reason": reason,
        "req_unit": requirement.unit,
        "comp_unit": component.unit,
        "product": requirement.normalized_product,
    }


def _billing_quantity_for_component(
    requirement: RequirementItem,
    component: PriceComponent,
) -> float | None:
    """Compute the effective quantity for a billing requirement against a component.

    Returns None if the quantity cannot be reliably derived.
    """
    qty = requirement.quantity
    if qty is None or qty <= 0:
        return None
    # For instance-month catalog items, the quantity is already in months
    comp_unit = (component.unit or "").lower()
    if "month" in comp_unit:
        return qty
    # For hour-based catalog items, convert
    if "hour" in comp_unit:
        return qty * 744  # month -> hours
    return qty


def _billing_units_compatible(requirement: RequirementItem, component: PriceComponent) -> bool:
    """Check if a billing requirement's unit is compatible with a catalog component's unit.

    Uses the billing price semantics system for product-aware compatibility.
    """
    can_price, _ = _billing_can_price_requirement(requirement, component)
    return can_price


def _billing_quote_quantity(requirement: RequirementItem, component: PriceComponent) -> float:
    quantity = requirement.quantity or 0.0
    if requirement.quantity_source != "billing_standardized":
        return quantity
    component_unit = (component.unit or "").lower()
    requirement_unit = (requirement.unit or "").lower()
    monthly_units = (
        "instance-month",
        "gateway-month",
        "ip-month",
        "connection-month",
        "protected-server-month",
        "disk-month",
        "vcore-month",
        "gb-month",
    )
    if any(unit in component_unit for unit in monthly_units):
        return quantity
    if "hours" in requirement_unit and "hour" not in component_unit:
        return round(quantity / 744, 4)
    return quantity


def quote_items(state: FlexibleQuoteState) -> FlexibleQuoteState:
    _report_progress(state, "quote_items", "running", "Calculating quote lines.")
    # Index resolved components by requirement_item_id.
    # A single requirement may legitimately map to multiple priced components
    # (for example ELB + WAF), so keep the full list rather than the last item.
    components_by_item: dict[str, list[PriceComponent]] = {}
    for item in state.get("price_components", []):
        item_id = item.get("requirement_item_id")
        if item_id:
            components_by_item.setdefault(item_id, []).append(PriceComponent.model_validate(item))
    lines: list[dict[str, Any]] = []
    for raw_item in state.get("quote_ready_items", []):
        requirement = RequirementItem.model_validate(raw_item)
        components = components_by_item.get(requirement.item_id, [])
        if not components or requirement.quantity is None or not requirement.normalized_product or not requirement.region:
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
        for idx, component in enumerate(components):
            if component.price is None:
                continue
            quote_quantity = _billing_quote_quantity(requirement, component)
            component_product = component.product or requirement.normalized_product
            line_suffix = component_product.lower().replace(" ", "_") if component_product else str(idx)
            lines.append(
                FlexibleQuoteLine(
                    line_id=f"line::{requirement.item_id}::{line_suffix}::{idx}",
                    requirement_item_id=requirement.item_id,
                    product=component_product,
                    region=requirement.region,
                    quantity=quote_quantity,
                    unit=component.unit,
                    billing_mode=component.billing_mode,
                    matched_sku=component.sku,
                    matched_tier=component.tier,
                    unit_price=component.price,
                    monthly_price=round(component.price * quote_quantity, 4),
                    currency=component.currency,
                    assumption=assumption,
                ).model_dump()
            )
    message = f"Quoted {len(lines)} line(s)."
    _report_progress(state, "quote_items", "completed", message)
    return {"quote_lines": lines, "audit_log": _append_audit(state, "quote_items", message)}


# ---------------------------------------------------------------------------
# Billing gap analysis (Phase Next+3)
# ---------------------------------------------------------------------------

_UNQUOTED_REASON_NO_MAPPING = "no_huawei_product_mapping"
_UNQUOTED_REASON_NO_CATALOG = "no_catalog_candidate"
_UNQUOTED_REASON_NO_COMPATIBLE_UNIT = "no_compatible_price_unit"
_UNQUOTED_REASON_SPEC_AMBIGUOUS = "spec_not_specific_enough"
_UNQUOTED_REASON_USAGE_UNSUPPORTED = "usage_not_supported_yet"
_UNQUOTED_REASON_MANUAL_REVIEW = "manual_review_required"
_UNQUOTED_REASON_SUSPICIOUS_RECLASSIFICATION = "suspicious_capacity_reclassification"
_UNQUOTED_REASON_UNKNOWN = "unknown"


def _stable_unquoted_reason(
    requirement: RequirementItem,
    candidates: list[PriceComponent],
    semantics_reason: str | None = None,
) -> str:
    """Build a stable unquoted reason string for a requirement that could not be priced.

    Uses the safe usage semantic system to produce stable, specific reasons
    instead of generic fallbacks.
    """
    product = requirement.normalized_product or ""
    req_unit = (requirement.unit or "").lower()

    # If semantics check gave a specific reason, use it as base
    if semantics_reason:
        return semantics_reason

    # No candidates at all
    if not candidates:
        return f"No confirmed local price is available for {product} and the requested region."

    # Classify by usage semantic
    usage_sem = _billing_usage_semantic(requirement)

    if usage_sem == "ops_10k":
        return f"{product} operations/requests usage ({req_unit}) cannot be priced with available catalog items."
    if usage_sem == "traffic_gb":
        return f"{product} traffic/bandwidth usage ({req_unit}) cannot be priced with available catalog items."
    if usage_sem == "request_usage":
        return f"{product} request-based usage ({req_unit}) is not a standard Huawei Cloud billing model."
    if usage_sem == "unknown":
        if not _billing_has_capacity_evidence(requirement):
            return f"{product} with unknown unit lacks capacity evidence — cannot safely price as GB-month."
        return f"{product} unknown unit with capacity evidence but no compatible GB-month catalog item found."

    # capacity_gib_month but no compatible catalog unit
    if usage_sem == "capacity_gib_month":
        # Check if any GB-month candidates exist
        gb_candidates = [c for c in candidates if "gb-month" in (c.unit or "").lower()]
        if not gb_candidates:
            return f"Storage capacity usage ({req_unit}) cannot be priced with {product} — no GB-month catalog item exists."
        return f"Storage capacity usage ({req_unit}) for {product} could not be matched to a specific GB-month catalog item."

    return "No confirmed local price matched the requested spec."


def _classify_unquoted_reason(item: RequirementItem) -> str:
    """Classify an unquoted item's reason into a stable category."""
    reason = (item.status_reason or "").lower()
    if item.normalized_product is None:
        return _UNQUOTED_REASON_NO_MAPPING
    # Phase Next+5: detect suspicious capacity reclassification
    if "capacity evidence" in reason or "suspicious_capacity_reclassification" in reason:
        return _UNQUOTED_REASON_SUSPICIOUS_RECLASSIFICATION
    if "no confirmed local price" in reason or "no confirmed" in reason or "no locally confirmed" in reason:
        return _UNQUOTED_REASON_NO_CATALOG
    if "not compatible" in reason or "cannot be priced" in reason:
        # "Storage capacity usage" is capacity, not ops/traffic — classify as no_compatible_price_unit
        if "storage capacity" in reason or "capacity usage" in reason:
            return _UNQUOTED_REASON_NO_COMPATIBLE_UNIT
        if any(k in reason for k in ("traffic", "request", "operation", "ops")):
            return _UNQUOTED_REASON_USAGE_UNSUPPORTED
        # Generic "usage" without capacity context — check if it's ops/traffic
        if "usage" in reason and "capacity" not in reason:
            return _UNQUOTED_REASON_USAGE_UNSUPPORTED
        return _UNQUOTED_REASON_NO_COMPATIBLE_UNIT
    # Phase Next+6: user-month is usage_not_supported_yet, not unknown
    if "user-month" in reason or "user month" in reason:
        return _UNQUOTED_REASON_USAGE_UNSUPPORTED
    if "ambiguous" in reason or "spec" in reason:
        return _UNQUOTED_REASON_SPEC_AMBIGUOUS
    if "manual" in reason or item.status == "needs_manual_review":
        return _UNQUOTED_REASON_MANUAL_REVIEW
    return _UNQUOTED_REASON_UNKNOWN


# ---------------------------------------------------------------------------
# Blocker triage categories (Phase Next+7)
# ---------------------------------------------------------------------------

_BLOCKER_UNSUPPORTED_PRODUCT = "unsupported_product"
_BLOCKER_SPEC_NOT_SPECIFIC_ENOUGH = "spec_not_specific_enough"
_BLOCKER_PRICING_BLOCKED_BY_CATALOG_GAP = "pricing_blocked_by_catalog_gap"
_BLOCKER_SUSPICIOUS_SOURCE_SEMANTICS = "suspicious_source_semantics"
_BLOCKER_MANUAL_REVIEW_REQUIRED = "manual_review_required"
_BLOCKER_MISSING_REGION = "missing_region"

_BLOCKER_CATEGORY_ALL = frozenset({
    _BLOCKER_UNSUPPORTED_PRODUCT,
    _BLOCKER_SPEC_NOT_SPECIFIC_ENOUGH,
    _BLOCKER_PRICING_BLOCKED_BY_CATALOG_GAP,
    _BLOCKER_SUSPICIOUS_SOURCE_SEMANTICS,
    _BLOCKER_MANUAL_REVIEW_REQUIRED,
    _BLOCKER_MISSING_REGION,
})


def _classify_billing_blocker(item: RequirementItem) -> str:
    """Classify a blocker into a stable, auditable category.

    The classification is based on the item's status, status_reason,
    normalized_product, and quantity_source.  Returns one of the
    _BLOCKER_* constants.
    """
    status = item.status
    reason = (item.status_reason or "").lower()

    # 1. Missing region is unambiguous
    if status == "needs_region":
        return _BLOCKER_MISSING_REGION

    # 2. No Huawei product mapping at all → unsupported product
    if item.normalized_product is None:
        return _BLOCKER_UNSUPPORTED_PRODUCT

    # 3. Status needs_manual_review with no product mapping
    if status == "needs_manual_review" and "could not be mapped" in reason:
        return _BLOCKER_UNSUPPORTED_PRODUCT

    # 4. Spec missing for a product that requires it
    if status == "needs_spec":
        return _BLOCKER_SPEC_NOT_SPECIFIC_ENOUGH

    # 5. needs_manual_review with spec-related reason
    if status == "needs_manual_review" and any(
        k in reason for k in ("spec", "ambiguous", "shape", "configuration", "规格")
    ):
        return _BLOCKER_SPEC_NOT_SPECIFIC_ENOUGH

    # 6. needs_quantity — often a billing item with unclear quantity semantics
    if status == "needs_quantity":
        # If it's a billing item, the quantity issue is likely a source semantics problem
        if item.quantity_source == "billing_standardized":
            return _BLOCKER_SUSPICIOUS_SOURCE_SEMANTICS
        return _BLOCKER_SPEC_NOT_SPECIFIC_ENOUGH

    # 7. Suspicious source semantics — must check BEFORE catalog/price patterns
    #    because "safely confirmed" contains "confirmed" which would otherwise
    #    match the catalog gap rule.
    if item.quantity_source == "billing_standardized" and any(
        k in reason for k in ("suspicious", "reclassify", "capacity evidence", "unsafe", "safely confirmed")
    ):
        return _BLOCKER_SUSPICIOUS_SOURCE_SEMANTICS

    # 8. needs_price_confirmation but classified as blocker (shouldn't normally happen,
    #    but if it does, it's a catalog gap)
    if status == "needs_price_confirmation":
        return _BLOCKER_PRICING_BLOCKED_BY_CATALOG_GAP

    # 9. needs_manual_review with catalog / price reason
    if status == "needs_manual_review" and any(
        k in reason for k in ("price", "catalog", "confirmed", "candidate")
    ):
        return _BLOCKER_PRICING_BLOCKED_BY_CATALOG_GAP

    # 10. Default: manual_review_required
    return _BLOCKER_MANUAL_REVIEW_REQUIRED


def _should_downgrade_blocker_to_unquoted(item: RequirementItem) -> tuple[bool, str | None]:
    """Decide whether a blocker can be safely downgraded to unquoted.

    Returns (should_downgrade, reason).
    A blocker should be downgraded when it is essentially "cannot price right now"
    rather than "requires human decision before proceeding".

    Safe to downgrade:
    - pricing_blocked_by_catalog_gap: known product, just no catalog entry
    - spec_not_specific_enough for billing items: known product direction,
      just need more spec detail — not a blocking decision
    - suspicious_source_semantics for billing items: the item is flagged
      for safety, but doesn't block other items

    NOT safe to downgrade:
    - unsupported_product: no Huawei mapping at all, needs human decision
    - manual_review_required: explicitly flagged for human review
    - missing_region: region is a structural requirement
    """
    category = _classify_billing_blocker(item)

    if category == _BLOCKER_PRICING_BLOCKED_BY_CATALOG_GAP:
        return True, "Catalog gap — item has product mapping but no confirmed price; safe as unquoted."

    if category == _BLOCKER_SPEC_NOT_SPECIFIC_ENOUGH:
        # Only downgrade billing items (not manually entered ones)
        if item.quantity_source == "billing_standardized":
            return True, "Billing item with insufficient spec — safe as unquoted, not a blocking decision."
        return False, None

    if category == _BLOCKER_SUSPICIOUS_SOURCE_SEMANTICS:
        # Only downgrade if it's a billing item (source semantics issues are
        # inherently about billing data, not manual requirements)
        if item.quantity_source == "billing_standardized":
            return True, "Billing item with suspicious source semantics — safe as unquoted for review."
        return False, None

    return False, None


def _summarize_billing_blockers(state: FlexibleQuoteState) -> list[dict[str, Any]]:
    """Summarize all blockers with their triage category.

    Returns a list of dicts: {item_id, product, category, status, message, source_file}.
    """
    result: list[dict[str, Any]] = []
    for raw in state.get("quote_blockers", []):
        blocker = FlexibleQuoteBlocker.model_validate(raw)
        # Find the matching requirement to get full context
        matching_req = None
        for req_raw in state.get("requirements", []):
            if req_raw.get("item_id") == blocker.item_id:
                matching_req = RequirementItem.model_validate(req_raw)
                break
        if matching_req is None:
            # Build a minimal RequirementItem from blocker data
            matching_req = RequirementItem(
                item_id=blocker.item_id,
                source_file=blocker.source_file,
                source_sheet=blocker.source_sheet,
                row_number=blocker.row_number,
                raw_product_name=blocker.product,
                status=blocker.status,
                status_reason=blocker.message,
            )
        category = _classify_billing_blocker(matching_req)
        result.append({
            "item_id": blocker.item_id,
            "product": blocker.product,
            "category": category,
            "status": blocker.status,
            "message": blocker.message,
            "source_file": blocker.source_file,
        })
    return result


def _top_blocker_categories(state: FlexibleQuoteState, limit: int = 10) -> list[dict[str, Any]]:
    """Return top blocker categories by count.

    Each entry: {category, count, items (first 5 item_ids)}.
    """
    summary = _summarize_billing_blockers(state)
    by_category: dict[str, list[str]] = {}
    for entry in summary:
        cat = entry["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(entry["item_id"])

    result: list[dict[str, Any]] = []
    for cat in sorted(by_category, key=lambda c: -len(by_category[c])):
        ids = by_category[cat]
        result.append({
            "category": cat,
            "count": len(ids),
            "items": ids[:5],
        })
        if len(result) >= limit:
            break
    return result


def _analyze_billing_blocker_triage(state: FlexibleQuoteState) -> dict[str, Any]:
    """Full blocker triage analysis: categories, counts, downgrade candidates.

    Returns dict with:
    - blocker_total: total blocker count
    - blocker_categories: {category: count}
    - top_blocker_categories: top N by count
    - downgradable_count: how many blockers can be safely downgraded
    - downgradable_items: list of {item_id, category, reason}
    - remaining_blocker_count: blockers - downgradable
    """
    summary = _summarize_billing_blockers(state)
    top_cats = _top_blocker_categories(state, limit=10)

    # Category counts
    category_counts: dict[str, int] = {}
    for entry in summary:
        cat = entry["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # Downgrade candidates
    downgradable: list[dict[str, Any]] = []
    for raw in state.get("quote_blockers", []):
        blocker = FlexibleQuoteBlocker.model_validate(raw)
        matching_req = None
        for req_raw in state.get("requirements", []):
            if req_raw.get("item_id") == blocker.item_id:
                matching_req = RequirementItem.model_validate(req_raw)
                break
        if matching_req is None:
            matching_req = RequirementItem(
                item_id=blocker.item_id,
                source_file=blocker.source_file,
                source_sheet=blocker.source_sheet,
                row_number=blocker.row_number,
                raw_product_name=blocker.product,
                status=blocker.status,
                status_reason=blocker.message,
            )
        should, reason = _should_downgrade_blocker_to_unquoted(matching_req)
        if should:
            downgradable.append({
                "item_id": blocker.item_id,
                "category": _classify_billing_blocker(matching_req),
                "reason": reason,
            })

    return {
        "blocker_total": len(summary),
        "blocker_categories": category_counts,
        "top_blocker_categories": top_cats,
        "downgradable_count": len(downgradable),
        "downgradable_items": downgradable,
        "remaining_blocker_count": len(summary) - len(downgradable),
    }


# ---------------------------------------------------------------------------
# Manual review design for unsupported_product blockers (Phase Next+8)
# ---------------------------------------------------------------------------

_MANUAL_REVIEW_TARGET_PRODUCT_SELECTION = "target_product_selection"
_MANUAL_REVIEW_CAPACITY_OR_TIER_CONFIRMATION = "capacity_or_tier_confirmation"
_MANUAL_REVIEW_BILLING_MODEL_SELECTION = "billing_model_selection"
_MANUAL_REVIEW_SERVICE_SCOPE_DECISION = "service_scope_decision"
_MANUAL_REVIEW_UNSUPPORTED_BY_CATALOG = "unsupported_by_current_catalog"
_MANUAL_REVIEW_UNKNOWN = "unknown"

_MANUAL_REVIEW_NEED_ALL = frozenset({
    _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION,
    _MANUAL_REVIEW_CAPACITY_OR_TIER_CONFIRMATION,
    _MANUAL_REVIEW_BILLING_MODEL_SELECTION,
    _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
    _MANUAL_REVIEW_UNSUPPORTED_BY_CATALOG,
    _MANUAL_REVIEW_UNKNOWN,
})

# Minimal fields per manual review need
_MINIMAL_FIELDS_BY_REVIEW_NEED: dict[str, list[str]] = {
    _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION: ["huawei_product_family"],
    _MANUAL_REVIEW_CAPACITY_OR_TIER_CONFIRMATION: ["capacity_gib", "tier"],
    _MANUAL_REVIEW_BILLING_MODEL_SELECTION: ["billing_basis"],
    _MANUAL_REVIEW_SERVICE_SCOPE_DECISION: ["include_in_quote", "mapped_as"],
    _MANUAL_REVIEW_UNSUPPORTED_BY_CATALOG: ["huawei_product_family"],
    _MANUAL_REVIEW_UNKNOWN: ["huawei_product_family"],
}

# Azure product type → manual review need heuristic
_AZURE_PRODUCT_TYPE_REVIEW_HINTS: list[tuple[list[str], str]] = [
    # (keywords in product_type, review_need)
    (["api management", "api gateway", "apim"], _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION),
    (["dns", "domain", "zone"], _MANUAL_REVIEW_SERVICE_SCOPE_DECISION),
    (["fabric", "synapse", "datalake", "lake", "data factory", "data lake"], _MANUAL_REVIEW_UNSUPPORTED_BY_CATALOG),
    (["monitor", "log analytics", "insights", "alert", "diagnostic"], _MANUAL_REVIEW_SERVICE_SCOPE_DECISION),
    (["bastion", "jump box", "jumpbox"], _MANUAL_REVIEW_SERVICE_SCOPE_DECISION),
    (["key vault", "vault", "hsm"], _MANUAL_REVIEW_SERVICE_SCOPE_DECISION),
    (["container registry", "artifact", "acr"], _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION),
    (["test plans", "devops", "pipelines", "boards"], _MANUAL_REVIEW_SERVICE_SCOPE_DECISION),
    (["bandwidth", "egress", "interregional", "peering"], _MANUAL_REVIEW_BILLING_MODEL_SELECTION),
    (["tables", "cosmos", "storage table"], _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION),
    (["private link", "private endpoint", "service endpoint"], _MANUAL_REVIEW_SERVICE_SCOPE_DECISION),
    (["cdn", "front door", "application gateway"], _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION),
    (["notification", "event grid", "service bus", "queue"], _MANUAL_REVIEW_UNSUPPORTED_BY_CATALOG),
    (["virtual network", "vnet", "subnet", "nsg"], _MANUAL_REVIEW_SERVICE_SCOPE_DECISION),
]

# Azure product type → suggested Huawei target family (conservative)
_AZURE_PRODUCT_TYPE_FAMILY_HINTS: list[tuple[list[str], str], str] = [
    # ((keywords), suggested_family)
    ((["api management", "api gateway", "apim"],), "API Gateway"),
    ((["dns", "domain"],), "DNS"),
    ((["cdn", "front door"],), "CDN"),
    ((["container registry", "acr"],), "SWR"),
    ((["key vault", "vault"],), "DEW"),
    ((["bastion"],), "Bastion"),
    ((["load balancer", "application gateway"],), "ELB"),
    ((["monitor", "log analytics"],), "LTS"),
    ((["event grid", "notification"],), "DMS"),
]


def _classify_manual_review_need(item: RequirementItem) -> str:
    """Classify what kind of manual review an unsupported_product blocker needs.

    Uses the raw_product_name and notes to infer the review need.
    Returns one of the _MANUAL_REVIEW_* constants.
    """
    text = (item.raw_product_name or "").lower()
    notes = (item.notes or "").lower()
    combined = f"{text} {notes}"

    for keywords, review_need in _AZURE_PRODUCT_TYPE_REVIEW_HINTS:
        if any(k in combined for k in keywords):
            return review_need

    # Default: need to decide which Huawei product to target
    return _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION


def _minimal_manual_review_fields(item: RequirementItem) -> list[str]:
    """Return the minimal set of fields a human must provide for this blocker.

    Based on the manual review need classification.
    """
    review_need = _classify_manual_review_need(item)
    return list(_MINIMAL_FIELDS_BY_REVIEW_NEED.get(review_need, ["huawei_product_family"]))


def _suggest_huawei_target_family(item: RequirementItem) -> str | None:
    """Suggest a Huawei product family for an unsupported blocker.

    Returns a family name string if a safe inference can be made,
    or None if no safe suggestion exists.
    """
    text = (item.raw_product_name or "").lower()
    notes = (item.notes or "").lower()
    combined = f"{text} {notes}"

    for (keywords,), family in _AZURE_PRODUCT_TYPE_FAMILY_HINTS:
        if any(k in combined for k in keywords):
            return family

    return None


def _build_manual_review_candidates(state: FlexibleQuoteState) -> list[dict[str, Any]]:
    """Build structured manual review candidates from unsupported_product blockers.

    Each candidate contains: candidate_id, source_label, source_product_type,
    source_product_sku, source_amount, source_quantity, source_unit,
    blocker_category, manual_review_need, minimal_fields_required,
    suggested_huawei_target_family, reason, source_line_numbers.
    """
    candidates: list[dict[str, Any]] = []
    agg_items = state.get("llm_aggregated_billing_items", [])

    for raw in state.get("quote_blockers", []):
        blocker = FlexibleQuoteBlocker.model_validate(raw)

        # Only process unsupported_product blockers
        matching_req = None
        for req_raw in state.get("requirements", []):
            if req_raw.get("item_id") == blocker.item_id:
                matching_req = RequirementItem.model_validate(req_raw)
                break
        if matching_req is None:
            matching_req = RequirementItem(
                item_id=blocker.item_id,
                source_file=blocker.source_file,
                source_sheet=blocker.source_sheet,
                row_number=blocker.row_number,
                raw_product_name=blocker.product,
                status=blocker.status,
                status_reason=blocker.message,
            )

        blocker_category = _classify_billing_blocker(matching_req)
        if blocker_category != _BLOCKER_UNSUPPORTED_PRODUCT:
            continue

        # Find source amount/quantity from aggregated billing items
        source_amount = 0.0
        source_quantity = 0.0
        source_unit = ""
        source_product_type = ""
        source_product_sku = ""
        source_line_numbers: list[int] = []

        for agg in agg_items:
            agg_id = f"billing-agg::{agg.get('source_file', '')}::{agg_items.index(agg)}"
            if agg_id == blocker.item_id:
                source_amount = _to_float(agg.get("amount")) or 0.0
                source_quantity = _to_float(agg.get("derived_quantity")) or 0.0
                source_unit = agg.get("derived_unit", "")
                source_product_type = agg.get("product_type", "")
                source_product_sku = agg.get("product_sku", "")
                source_line_numbers = agg.get("source_line_numbers", [])
                break

        review_need = _classify_manual_review_need(matching_req)
        minimal_fields = _minimal_manual_review_fields(matching_req)
        suggested_family = _suggest_huawei_target_family(matching_req)

        # Build source label from blocker product name
        source_label = blocker.product
        # Clean up "unsupported | " prefix
        if source_label.lower().startswith("unsupported"):
            source_label = re.sub(r"^unsupported\s*\|\s*", "", source_label, flags=re.I).strip()

        candidates.append({
            "candidate_id": blocker.item_id,
            "source_label": source_label,
            "source_product_type": source_product_type,
            "source_product_sku": source_product_sku,
            "source_amount": round(source_amount, 2),
            "source_quantity": round(source_quantity, 4),
            "source_unit": source_unit,
            "blocker_category": blocker_category,
            "manual_review_need": review_need,
            "minimal_fields_required": minimal_fields,
            "suggested_huawei_target_family": suggested_family,
            "reason": blocker.message,
            "source_line_numbers": source_line_numbers,
        })

    # Sort by source amount descending (biggest cost items first)
    candidates.sort(key=lambda c: -c["source_amount"])
    return candidates


def _analyze_manual_review_design(state: FlexibleQuoteState) -> dict[str, Any]:
    """Full manual review design analysis.

    Returns dict with:
    - total_candidates: number of unsupported_product blockers needing review
    - candidates: list of manual review candidate dicts
    - categories: {manual_review_need: count}
    - top_unsupported_by_amount: top 5 by source amount
    - minimal_field_frequency: {field_name: count} across all candidates
    - scope_decision_count: how many are service_scope_decision (likely out-of-scope)
    - mapping_decision_count: how many need target_product_selection
    """
    candidates = _build_manual_review_candidates(state)

    # Category counts
    categories: dict[str, int] = {}
    for c in candidates:
        cat = c["manual_review_need"]
        categories[cat] = categories.get(cat, 0) + 1

    # Top unsupported by source amount
    top_by_amount = candidates[:5]

    # Minimal field frequency
    field_freq: dict[str, int] = {}
    for c in candidates:
        for field in c["minimal_fields_required"]:
            field_freq[field] = field_freq.get(field, 0) + 1

    scope_count = categories.get(_MANUAL_REVIEW_SERVICE_SCOPE_DECISION, 0)
    mapping_count = categories.get(_MANUAL_REVIEW_TARGET_PRODUCT_SELECTION, 0)

    return {
        "total_candidates": len(candidates),
        "candidates": candidates,
        "categories": categories,
        "top_unsupported_by_amount": [
            {
                "source_label": c["source_label"],
                "source_amount": c["source_amount"],
                "manual_review_need": c["manual_review_need"],
                "suggested_family": c["suggested_huawei_target_family"],
            }
            for c in top_by_amount
        ],
        "minimal_field_frequency": field_freq,
        "scope_decision_count": scope_count,
        "mapping_decision_count": mapping_count,
    }


# ---------------------------------------------------------------------------
# Manual review apply — Phase Next+9
# ---------------------------------------------------------------------------

# Allowed billing_basis values for billing_model_selection
_ALLOWED_BILLING_BASIS = frozenset({"capacity", "instance", "request"})

# Required fields per decision_type for manual review input
_MANUAL_REVIEW_INPUT_REQUIRED_FIELDS: dict[str, list[str]] = {
    _MANUAL_REVIEW_SERVICE_SCOPE_DECISION: ["include_in_quote"],
    _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION: ["huawei_product_family"],
    _MANUAL_REVIEW_BILLING_MODEL_SELECTION: ["billing_basis"],
    _MANUAL_REVIEW_UNSUPPORTED_BY_CATALOG: ["huawei_product_family"],
    _MANUAL_REVIEW_CAPACITY_OR_TIER_CONFIRMATION: ["capacity_gib", "tier"],
    _MANUAL_REVIEW_UNKNOWN: ["huawei_product_family"],
}

# All allowed field names across all decision types
_MANUAL_REVIEW_ALL_ALLOWED_FIELDS = frozenset({
    "include_in_quote", "mapped_as", "huawei_product_family",
    "billing_basis", "capacity_gib", "tier",
})


def _manual_review_input_errors(
    inputs: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate manual review inputs against candidates.

    Returns a list of error dicts (empty if all inputs are valid).
    Each error: {"candidate_id": ..., "error": ..., "detail": ...}
    """
    candidate_ids = {c["candidate_id"] for c in candidates}
    candidate_by_id = {c["candidate_id"]: c for c in candidates}
    errors: list[dict[str, Any]] = []

    for inp in inputs:
        cid = inp.get("candidate_id")
        dt = inp.get("decision_type")
        fields = inp.get("fields", {})

        # candidate_id must exist
        if not cid:
            errors.append({"candidate_id": None, "error": "missing_candidate_id", "detail": "candidate_id is required"})
            continue
        if cid not in candidate_ids:
            errors.append({"candidate_id": cid, "error": "unknown_candidate_id", "detail": f"candidate_id '{cid}' not found in manual_review_candidates"})
            continue

        candidate = candidate_by_id[cid]

        # decision_type must be compatible with candidate's manual_review_need
        if dt != candidate["manual_review_need"]:
            errors.append({
                "candidate_id": cid,
                "error": "wrong_decision_type",
                "detail": f"decision_type '{dt}' does not match candidate's manual_review_need '{candidate['manual_review_need']}'",
            })
            continue

        # Check required fields
        required = _MANUAL_REVIEW_INPUT_REQUIRED_FIELDS.get(dt, [])
        for rf in required:
            if rf not in fields:
                errors.append({
                    "candidate_id": cid,
                    "error": "missing_required_field",
                    "detail": f"field '{rf}' is required for decision_type '{dt}'",
                })

        # Check for disallowed fields
        for fk in fields:
            if fk not in _MANUAL_REVIEW_ALL_ALLOWED_FIELDS:
                errors.append({
                    "candidate_id": cid,
                    "error": "disallowed_field",
                    "detail": f"field '{fk}' is not an allowed manual review input field",
                })

        # Type/value checks
        if "include_in_quote" in fields and not isinstance(fields["include_in_quote"], bool):
            errors.append({
                "candidate_id": cid,
                "error": "invalid_field_type",
                "detail": "include_in_quote must be bool",
            })
        if "huawei_product_family" in fields:
            val = fields["huawei_product_family"]
            if not isinstance(val, str) or not val.strip():
                errors.append({
                    "candidate_id": cid,
                    "error": "invalid_field_type",
                    "detail": "huawei_product_family must be a non-empty string",
                })
        if "billing_basis" in fields:
            val = fields["billing_basis"]
            if val not in _ALLOWED_BILLING_BASIS:
                errors.append({
                    "candidate_id": cid,
                    "error": "invalid_field_value",
                    "detail": f"billing_basis must be one of {sorted(_ALLOWED_BILLING_BASIS)}, got '{val}'",
                })
        if "mapped_as" in fields and fields["mapped_as"] is not None:
            if not isinstance(fields["mapped_as"], str) or not fields["mapped_as"].strip():
                errors.append({
                    "candidate_id": cid,
                    "error": "invalid_field_type",
                    "detail": "mapped_as must be null or a non-empty string",
                })

    return errors


def _validate_manual_review_inputs(
    inputs: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate and return only valid inputs. Invalid ones are dropped.

    Returns the subset of inputs that pass all validation checks.
    """
    errors = _manual_review_input_errors(inputs, candidates)
    error_ids = {e["candidate_id"] for e in errors if e.get("candidate_id")}
    return [inp for inp in inputs if inp.get("candidate_id") not in error_ids]


def _apply_manual_review_decision(
    candidate: dict[str, Any],
    decision: dict[str, Any],
) -> dict[str, Any]:
    """Apply a single manual review decision to a candidate.

    Returns an applied result dict with:
    - candidate_id, decision_type, fields (the decision fields)
    - outcome: what happened (excluded, override_recorded, etc.)
    - overrides: dict of field overrides for downstream workflow
    """
    cid = candidate["candidate_id"]
    dt = decision["decision_type"]
    fields = decision.get("fields", {})
    overrides: dict[str, Any] = {}

    if dt == _MANUAL_REVIEW_SERVICE_SCOPE_DECISION:
        include = fields.get("include_in_quote")
        if include is False:
            outcome = "excluded_by_manual_review"
        elif include is True:
            mapped_as = fields.get("mapped_as")
            if mapped_as:
                outcome = "include_with_mapping_override"
                overrides["mapped_as"] = mapped_as
            else:
                outcome = "include_but_needs_mapping"
            overrides["include_in_quote"] = True
        else:
            outcome = "no_change"

    elif dt == _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION:
        family = fields.get("huawei_product_family")
        if family:
            outcome = "product_family_override"
            overrides["huawei_product_family"] = family
        else:
            outcome = "no_change"

    elif dt == _MANUAL_REVIEW_BILLING_MODEL_SELECTION:
        basis = fields.get("billing_basis")
        if basis:
            outcome = "billing_basis_override"
            overrides["billing_basis"] = basis
        else:
            outcome = "no_change"

    elif dt == _MANUAL_REVIEW_UNSUPPORTED_BY_CATALOG:
        family = fields.get("huawei_product_family")
        if family:
            outcome = "unsupported_family_override_recorded"
            overrides["huawei_product_family"] = family
        else:
            outcome = "no_change"

    elif dt == _MANUAL_REVIEW_CAPACITY_OR_TIER_CONFIRMATION:
        capacity = fields.get("capacity_gib")
        tier = fields.get("tier")
        if capacity is not None or tier:
            outcome = "capacity_or_tier_override"
            if capacity is not None:
                overrides["capacity_gib"] = capacity
            if tier:
                overrides["tier"] = tier
        else:
            outcome = "no_change"

    else:
        outcome = "no_change"

    return {
        "candidate_id": cid,
        "decision_type": dt,
        "fields": fields,
        "outcome": outcome,
        "overrides": overrides,
    }


def _apply_manual_review_inputs(
    state: FlexibleQuoteState,
    validated_inputs: list[dict[str, Any]],
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Apply validated manual review inputs to workflow state.

    Returns a dict with:
    - manual_review_decisions: list of decision dicts
    - applied_manual_review_results: list of applied result dicts
    - manual_review_apply_summary: counts of outcomes
    """
    if candidates is None:
        candidates = state.get("manual_review_candidates",
                               state.get("billing_manual_review_design", {}).get("candidates", []))
    candidate_by_id = {c["candidate_id"]: c for c in candidates}

    decisions: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    for inp in validated_inputs:
        cid = inp.get("candidate_id")
        candidate = candidate_by_id.get(cid)
        if candidate is None:
            continue

        result = _apply_manual_review_decision(candidate, inp)
        decisions.append(inp)
        results.append(result)

    # Compute summary counts
    excluded_count = sum(1 for r in results if r["outcome"] == "excluded_by_manual_review")
    override_count = sum(1 for r in results if "override" in r["outcome"])
    needs_mapping_count = sum(1 for r in results if r["outcome"] == "include_but_needs_mapping")
    no_change_count = sum(1 for r in results if r["outcome"] == "no_change")
    unresolved_candidates = len(candidates) - len(results)

    return {
        "manual_review_decisions": decisions,
        "applied_manual_review_results": results,
        "manual_review_apply_summary": {
            "decisions_applied": len(results),
            "excluded_by_manual_review": excluded_count,
            "mapped_overrides": override_count,
            "include_but_needs_mapping": needs_mapping_count,
            "no_change": no_change_count,
            "unresolved_after_manual_review": unresolved_candidates,
        },
    }


def _summarize_quoted_billing_items(state: FlexibleQuoteState) -> list[dict[str, Any]]:
    """Summarize quoted items by Huawei product."""
    by_product: dict[str, dict[str, Any]] = {}
    for ql in state.get("quote_lines", []):
        product = ql.get("product", "?")
        if product not in by_product:
            by_product[product] = {
                "huawei_product": product,
                "count": 0,
                "total_quantity": 0.0,
                "total_monthly_price": 0.0,
                "matched_units": set(),
                "matched_skus": set(),
            }
        d = by_product[product]
        d["count"] += 1
        d["total_quantity"] += ql.get("quantity", 0)
        d["total_monthly_price"] += ql.get("monthly_price", 0)
        if ql.get("matched_sku"):
            d["matched_skus"].add(ql["matched_sku"])
        if ql.get("unit"):
            d["matched_units"].add(ql["unit"])
    # Convert sets to sorted lists
    for d in by_product.values():
        d["matched_units"] = sorted(d["matched_units"])
        d["matched_skus"] = sorted(d["matched_skus"])
    return sorted(by_product.values(), key=lambda x: -x["total_monthly_price"])


def _summarize_unquoted_billing_items(state: FlexibleQuoteState) -> list[dict[str, Any]]:
    """Summarize unquoted items with source amount and reason classification."""
    # Build source amount map from llm_aggregated_billing_items
    agg_amount_by_id: dict[str, float] = {}
    for idx, ai in enumerate(state.get("llm_aggregated_billing_items", [])):
        aid = f'billing-agg::{ai.get("source_file", "")}::{idx}'
        agg_amount_by_id[aid] = _to_float(ai.get("amount")) or 0.0

    by_key: dict[str, dict[str, Any]] = {}
    for raw_item in state.get("unquoted_items", []):
        item = RequirementItem.model_validate(raw_item)
        reason_class = _classify_unquoted_reason(item)
        source_amount = agg_amount_by_id.get(item.item_id, 0.0)
        key = (
            item.normalized_product or "None",
            item.unit or "?",
            reason_class,
        )
        if key not in by_key:
            by_key[key] = {
                "normalized_product": key[0],
                "unit": key[1],
                "reason_class": key[2],
                "count": 0,
                "total_source_amount": 0.0,
                "total_quantity": 0.0,
                "sample_raw_names": [],
            }
        d = by_key[key]
        d["count"] += 1
        d["total_source_amount"] += source_amount
        d["total_quantity"] += item.quantity or 0
        if len(d["sample_raw_names"]) < 3:
            d["sample_raw_names"].append(item.raw_product_name[:60])
    return sorted(by_key.values(), key=lambda x: -x["total_source_amount"])


def _top_unquoted_categories(state: FlexibleQuoteState, limit: int = 10) -> list[dict[str, Any]]:
    """Return top N unquoted gap categories by source amount."""
    summary = _summarize_unquoted_billing_items(state)
    return summary[:limit]


def _analyze_billing_quote_gap(state: FlexibleQuoteState) -> dict[str, Any]:
    """Full gap analysis: quoted breakdown, unquoted breakdown, top gaps."""
    quoted_summary = _summarize_quoted_billing_items(state)
    unquoted_summary = _summarize_unquoted_billing_items(state)
    top_gaps = _top_unquoted_categories(state, limit=10)

    # Compute totals
    total_quoted = sum(d["total_monthly_price"] for d in quoted_summary)
    total_unquoted_source = sum(d["total_source_amount"] for d in unquoted_summary)
    total_source = total_quoted + total_unquoted_source

    # Reason distribution
    reason_counts: dict[str, int] = {}
    reason_amounts: dict[str, float] = {}
    for d in unquoted_summary:
        rc = d["reason_class"]
        reason_counts[rc] = reason_counts.get(rc, 0) + d["count"]
        reason_amounts[rc] = reason_amounts.get(rc, 0) + d["total_source_amount"]

    return {
        "quoted_total": round(total_quoted, 2),
        "unquoted_source_total": round(total_unquoted_source, 2),
        "total_source_amount": round(total_source, 2),
        "quoted_pct": round(total_quoted / total_source * 100, 1) if total_source else 0,
        "unquoted_pct": round(total_unquoted_source / total_source * 100, 1) if total_source else 0,
        "quoted_by_product": quoted_summary,
        "unquoted_by_category": unquoted_summary,
        "top_gaps": top_gaps,
        "reason_distribution": {
            "counts": reason_counts,
            "source_amounts": {k: round(v, 2) for k, v in reason_amounts.items()},
        },
    }


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
        # Check for usage-based unquoted items
        usage_unquoted = sum(
            1
            for item in state.get("unquoted_items", [])
            if RequirementItem.model_validate(item).quantity_source == "billing_standardized"
            and any(k in (RequirementItem.model_validate(item).unit or "").lower()
                    for k in ("traffic gb", "ops 10k", "requests million", "unknown"))
        )
        if usage_unquoted:
            assumptions.append(
                f"{usage_unquoted} usage-based billing line(s) remain unquoted until a compatible "
                "Huawei pricing metric is defined (traffic, operations, and request-based usage "
                "cannot be reliably priced with instance-month or capacity-month catalog items)."
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
    # Phase 8F: Final quotation item statistics (when available)
    final_items_raw = state.get("final_billing_quote_items", [])
    if final_items_raw:
        final_items = [CloudBillingFinalQuoteItem.model_validate(fi) for fi in final_items_raw]
        fi_quoted = sum(1 for fi in final_items if fi.status == "quoted")
        fi_partial = sum(1 for fi in final_items if fi.status == "partial")
        fi_manual = sum(1 for fi in final_items if fi.status == "manual_review")
        fi_unquoted = sum(1 for fi in final_items if fi.status == "unquoted")
        fi_src_total = sum(fi.source_monthly_total_usd or 0 for fi in final_items)
        fi_hwc_total = sum(fi.huawei_monthly_total_usd or 0 for fi in final_items if fi.huawei_monthly_total_usd is not None)
        assumptions.append(
            f"FINAL QUOTATION: {len(final_items)} business-level item(s) — "
            f"{fi_quoted} quoted, {fi_partial} partial, {fi_manual} manual review, {fi_unquoted} unquoted."
        )
        if fi_src_total > 0:
            assumptions.append(
                f"FINAL QUOTATION: Source cloud monthly total ≈ ${fi_src_total:,.2f} USD."
            )
        if fi_hwc_total > 0:
            assumptions.append(
                f"FINAL QUOTATION: Huawei Cloud monthly total ≈ ${fi_hwc_total:,.2f} USD."
            )
        if fi_partial > 0:
            risks.append(
                f"FINAL QUOTATION: {fi_partial} item(s) are partially quoted — "
                "some sub-components could not be automatically priced."
            )
        if fi_manual > 0:
            risks.append(
                f"FINAL QUOTATION: {fi_manual} item(s) require manual review before pricing."
            )
        # Update summary text to reflect final items
        summary = summary.model_copy(update={
            "summary": (
                f"Final quotation: {len(final_items)} business-level item(s) "
                f"({fi_quoted} quoted, {fi_partial} partial, {fi_manual} review, {fi_unquoted} unquoted). "
                f"Internal: {len(lines)} quote line(s), {len(state.get('quote_blockers', []))} blocker(s)."
            ),
        })
    # Phase Next+5: reconciliation audit
    reconciliation = _analyze_billing_quote_reconciliation(state)
    if reconciliation["suspicious_count"] > 0:
        risks.append(
            f"PRICING AUDIT: {reconciliation['suspicious_count']} quoted line(s) have suspiciously high "
            f"prices vs source billing amounts (overstated total: ${reconciliation['overstated_total']:,.2f}). "
            "Review top deltas in reconciliation report."
        )
    if reconciliation["reclassification_count"] > 0:
        assumptions.append(
            f"PRICING AUDIT: {reconciliation['reclassification_count']} item(s) were blocked from capacity "
            "pricing because source usage could not be confirmed as storage capacity."
        )
    # Update summary with audit-informed risks/assumptions
    # Phase Next+6: mention safe storage-capacity usage quotes
    safe_usage_count = state.get("safe_usage_quoted_count", 0)
    if safe_usage_count > 0:
        assumptions.append(
            f"{safe_usage_count} storage-capacity usage item(s) were newly quoted using safe GB-month matching "
            "(only items with explicit capacity evidence and compatible Huawei catalog units)."
        )
    # Phase Next+7: blocker triage analysis
    blocker_triage = _analyze_billing_blocker_triage(state)
    if blocker_triage["blocker_total"] > 0:
        cat_summary = ", ".join(
            f"{cat}={count}" for cat, count in sorted(
                blocker_triage["blocker_categories"].items(), key=lambda x: -x[1]
            )
        )
        assumptions.append(
            f"BLOCKER TRIAGE: {blocker_triage['blocker_total']} blocker(s) classified — {cat_summary}."
        )
        if blocker_triage["downgradable_count"] > 0:
            assumptions.append(
                f"BLOCKER TRIAGE: {blocker_triage['downgradable_count']} blocker(s) could be safely downgraded to unquoted "
                f"(remaining true blockers: {blocker_triage['remaining_blocker_count']})."
            )
    summary = summary.model_copy(update={"assumptions": assumptions, "risks": risks})
    message = "Built flexible quote summary."
    _report_progress(state, "summarize_quote", "completed", message)
    # Billing gap analysis (Phase Next+3)
    gap = _analyze_billing_quote_gap(state)
    # Manual review design (Phase Next+8)
    manual_review_design = _analyze_manual_review_design(state)
    if manual_review_design["total_candidates"] > 0:
        scope_count = manual_review_design["scope_decision_count"]
        mapping_count = manual_review_design["mapping_decision_count"]
        assumptions.append(
            f"MANUAL REVIEW: {manual_review_design['total_candidates']} unsupported item(s) need review — "
            f"{mapping_count} need product mapping, {scope_count} may be out of scope."
        )
    # Phase Next+9: apply manual review inputs if present
    manual_review_inputs = state.get("manual_review_decisions", [])
    apply_result: dict[str, Any] = {}
    if manual_review_inputs:
        candidates = manual_review_design.get("candidates", [])
        validated = _validate_manual_review_inputs(manual_review_inputs, candidates)
        apply_result = _apply_manual_review_inputs(state, validated, candidates=candidates)
        apply_summary = apply_result.get("manual_review_apply_summary", {})
        if apply_summary.get("decisions_applied", 0) > 0:
            assumptions.append(
                f"MANUAL REVIEW APPLY: {apply_summary['decisions_applied']} decision(s) applied — "
                f"{apply_summary['excluded_by_manual_review']} excluded, "
                f"{apply_summary['mapped_overrides']} override(s) recorded, "
                f"{apply_summary['unresolved_after_manual_review']} unresolved."
            )
    summary = summary.model_copy(update={"assumptions": assumptions})
    result: dict[str, Any] = {
        "summary": summary.model_dump(),
        "billing_gap_analysis": gap,
        "billing_reconciliation": reconciliation,
        "billing_blocker_analysis": blocker_triage,
        "billing_manual_review_design": manual_review_design,
        "audit_log": _append_audit(state, "summarize_quote", message),
    }
    if apply_result:
        result["applied_manual_review_results"] = apply_result.get("applied_manual_review_results", [])
        result["manual_review_apply_summary"] = apply_result.get("manual_review_apply_summary", {})
    return result


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
        manual_review_candidates=[
            ManualReviewCandidate.model_validate(c)
            for c in state.get("billing_manual_review_design", {}).get("candidates", [])
        ],
        billing_lines=list(state.get("billing_lines", [])),
        llm_aggregated_billing_items=list(state.get("llm_aggregated_billing_items", [])),
        mapped_billing_resources=list(state.get("mapped_billing_resources", [])),
        billing_gap_analysis=dict(state.get("billing_gap_analysis", {})),
        billing_reconciliation=dict(state.get("billing_reconciliation", {})),
        final_billing_quote_items=[
            CloudBillingFinalQuoteItem.model_validate(fi)
            for fi in state.get("final_billing_quote_items", [])
        ],
    )


# ---------------------------------------------------------------------------
# Manual review apply API wrapper (Phase Next+10)
# ---------------------------------------------------------------------------

# Mapping from internal error names to stable API error codes
_API_ERROR_CODE_MAP: dict[str, str] = {
    "missing_candidate_id": "unknown_candidate_id",
    "unknown_candidate_id": "unknown_candidate_id",
    "wrong_decision_type": "wrong_decision_type",
    "missing_required_field": "missing_required_field",
    "invalid_field_type": "invalid_field_type",
    "invalid_field_value": "invalid_field_value",
    "disallowed_field": "unexpected_field",
}

_VALID_API_ERROR_CODES: frozenset[str] = frozenset({
    "unknown_candidate_id",
    "wrong_decision_type",
    "missing_required_field",
    "invalid_field_type",
    "invalid_field_value",
    "unexpected_field",
})


def apply_manual_review_from_api(
    decisions: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    *,
    reprice: bool = False,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """API-facing wrapper: validate + apply manual review decisions.

    Returns a dict matching ManualReviewApplyResponse shape:
    - applied_count: int
    - errors: list[ManualReviewApplyError-shaped dicts]
    - results: list[ManualReviewApplyResult-shaped dicts]
    - summary: dict with outcome counts
    - reprice_preview_summary: dict (only if reprice=True and state provided)
    """
    raw_inputs = [
        {
            "candidate_id": d.get("candidate_id", ""),
            "decision_type": d.get("decision_type", ""),
            "fields": d.get("fields", {}),
        }
        for d in decisions
    ]

    raw_errors = _manual_review_input_errors(raw_inputs, candidates)

    api_errors: list[dict[str, Any]] = []
    for e in raw_errors:
        internal_code = e.get("error", "")
        api_code = _API_ERROR_CODE_MAP.get(internal_code, internal_code)
        api_errors.append({
            "candidate_id": e.get("candidate_id"),
            "code": api_code,
            "message": e.get("detail", ""),
        })

    validated = _validate_manual_review_inputs(raw_inputs, candidates)

    if not validated:
        return {
            "applied_count": 0,
            "errors": api_errors,
            "results": [],
            "summary": {
                "decisions_applied": 0,
                "excluded_by_manual_review": 0,
                "mapped_overrides": 0,
                "include_but_needs_mapping": 0,
                "no_change": 0,
                "unresolved_after_manual_review": len(candidates),
            },
        }

    candidate_by_id = {c["candidate_id"]: c for c in candidates}
    applied_results: list[dict[str, Any]] = []
    full_applied: list[dict[str, Any]] = []
    for inp in validated:
        cid = inp.get("candidate_id")
        candidate = candidate_by_id.get(cid)
        if candidate is None:
            continue
        result = _apply_manual_review_decision(candidate, inp)
        full_applied.append(result)
        applied_results.append({
            "candidate_id": result["candidate_id"],
            "outcome": result["outcome"],
            "overrides": result.get("overrides", {}),
        })

    excluded_count = sum(1 for r in applied_results if r["outcome"] == "excluded_by_manual_review")
    override_count = sum(1 for r in applied_results if "override" in r["outcome"])
    needs_mapping_count = sum(1 for r in applied_results if r["outcome"] == "include_but_needs_mapping")
    no_change_count = sum(1 for r in applied_results if r["outcome"] == "no_change")
    unresolved = len(candidates) - len(applied_results)

    response = {
        "applied_count": len(applied_results),
        "errors": api_errors,
        "results": applied_results,
        "summary": {
            "decisions_applied": len(applied_results),
            "excluded_by_manual_review": excluded_count,
            "mapped_overrides": override_count,
            "include_but_needs_mapping": needs_mapping_count,
            "no_change": no_change_count,
            "unresolved_after_manual_review": unresolved,
        },
    }

    # Phase Next+11: optional repricing
    if reprice and state is not None and full_applied:
        # Inject into state for rebuild
        rebuild_state = dict(state)
        rebuild_state["applied_manual_review_results"] = full_applied
        reprice_result = _rebuild_billing_state_after_manual_review(rebuild_state)

        if reprice_result:
            response["reprice_preview_summary"] = reprice_result.get("manual_review_reprice_summary", {})
            response["reprice_updated_counts"] = {
                "quoted_items": FlexibleQuoteSummary.model_validate(reprice_result["summary"]).quoted_items,
                "blocker_count": FlexibleQuoteSummary.model_validate(reprice_result["summary"]).blocker_count,
                "unquoted_count": FlexibleQuoteSummary.model_validate(reprice_result["summary"]).unquoted_count,
                "total_monthly_price": FlexibleQuoteSummary.model_validate(reprice_result["summary"]).total_monthly_price,
            }

    return response


# ---------------------------------------------------------------------------
# Manual review repricing (Phase Next+11)
# ---------------------------------------------------------------------------

# Map from huawei_product_family override string to FlexibleProductKey
_FAMILY_TO_PRODUCT_KEY: dict[str, str] = {
    "API Gateway": "ELB",
    "DNS": "DNS",
    "DWS": "DWS",
    "DDS": "DDS",
    "DCS": "DCS",
    "DMS": "DMS",
    "FunctionGraph": "FunctionGraph",
    "ModelArts": "ModelArts",
    "DataArts Studio": "DataArts Studio",
    "CSS": "CSS",
    "LTS": "LTS",
    "DLI": "DLI",
    "DEW": "DEW",
    "HSS": "HSS",
    "CFW": "CFW",
    "CES": "CES",
    "Anti-DDoS": "Anti-DDoS",
    "Cloud Connect": "Cloud Connect",
    "Workspace": "Workspace",
    "DRS": "DRS",
    "GeminiDB": "GeminiDB",
    "GaussDB": "GaussDB",
    "CCI": "CCI",
    "VPC": "VPC",
}

# All valid FlexibleProductKey values (for validation)
_VALID_PRODUCT_KEYS: frozenset[str] = frozenset({
    "ECS", "EVS", "CBR", "EIP", "CCE", "CCI", "SFS Turbo", "NAT Gateway",
    "VPN", "Direct Connect as a Service", "RDS", "DDS", "DWS", "OBS", "ELB",
    "WAF", "HSS", "VPC", "Workspace", "DRS", "CSS", "LTS", "DLI", "DCS",
    "GeminiDB", "DMS", "DataArts Studio", "Cloud Connect", "DEW",
    "Anti-DDoS", "CFW", "CES", "ModelArts", "FunctionGraph", "GaussDB",
})


def _resolve_product_key(family_override: str) -> str | None:
    """Resolve a huawei_product_family override to a FlexibleProductKey.

    Returns the key if valid, None otherwise.
    """
    # Direct match first
    if family_override in _VALID_PRODUCT_KEYS:
        return family_override
    # Then try the mapping table
    return _FAMILY_TO_PRODUCT_KEY.get(family_override)


def _apply_manual_review_overrides_to_requirements(
    state: dict[str, Any],
    applied_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply manual review overrides to requirements and blockers.

    Returns a dict with updated:
    - requirements: list of requirement dicts (with overrides applied)
    - quote_blockers: list of blocker dicts (excluded items removed)
    - excluded_by_manual_review: list of excluded item IDs
    - manual_review_effective_requirements: list of requirement dicts that
      were modified by manual review overrides
    """
    requirements = [dict(r) for r in state.get("requirements", [])]
    blockers = [dict(b) for b in state.get("quote_blockers", [])]
    unquoted = [dict(u) for u in state.get("unquoted_items", [])]

    excluded_ids: list[str] = []
    effective_overrides: list[dict[str, Any]] = []

    # Index requirements by item_id
    req_by_id: dict[str, dict[str, Any]] = {}
    for r in requirements:
        rid = r.get("item_id", "")
        if rid:
            req_by_id[rid] = r

    for ar in applied_results:
        cid = ar.get("candidate_id", "")
        outcome = ar.get("outcome", "")
        overrides = ar.get("overrides", {})

        req = req_by_id.get(cid)
        if req is None:
            continue

        # --- service_scope_decision: include_in_quote=false → exclude ---
        if outcome == "excluded_by_manual_review":
            excluded_ids.append(cid)
            # Remove from blockers
            blockers = [b for b in blockers if b.get("item_id") != cid]
            # Mark requirement as excluded
            req["status"] = "excluded_by_manual_review"
            req["status_reason"] = "Excluded by manual review decision."
            effective_overrides.append({
                "item_id": cid,
                "override_type": "excluded",
                "changes": {"status": "excluded_by_manual_review"},
            })
            continue

        # --- product family override (target_product_selection, unsupported_by_catalog) ---
        if outcome in ("product_family_override", "unsupported_family_override_recorded"):
            family = overrides.get("huawei_product_family")
            if family:
                product_key = _resolve_product_key(family)
                if product_key:
                    req["normalized_product"] = product_key
                    req["status"] = "ready"
                    req["status_reason"] = f"Product family overridden to {product_key} by manual review."
                    effective_overrides.append({
                        "item_id": cid,
                        "override_type": "product_family",
                        "changes": {"normalized_product": product_key},
                    })
                else:
                    # Family specified but not a valid key — move to unquoted
                    req["status"] = "needs_price_confirmation"
                    req["status_reason"] = (
                        f"Manual review specified family '{family}' but no matching Huawei Cloud product key found."
                    )
                    effective_overrides.append({
                        "item_id": cid,
                        "override_type": "product_family_unresolvable",
                        "changes": {"status": "needs_price_confirmation"},
                    })

        # --- include_with_mapping_override ---
        if outcome == "include_with_mapping_override":
            mapped_as = overrides.get("mapped_as")
            if mapped_as:
                product_key = _resolve_product_key(mapped_as)
                if product_key:
                    req["normalized_product"] = product_key
                    req["status"] = "ready"
                    req["status_reason"] = f"Mapped to {product_key} by manual review."
                    effective_overrides.append({
                        "item_id": cid,
                        "override_type": "mapping_override",
                        "changes": {"normalized_product": product_key},
                    })

        # --- billing_basis_override ---
        if outcome == "billing_basis_override":
            basis = overrides.get("billing_basis")
            if basis:
                # Store in notes for downstream pricing
                existing_notes = req.get("notes", "") or ""
                req["notes"] = _append_note(existing_notes, f"MANUAL REVIEW: billing_basis={basis}")
                effective_overrides.append({
                    "item_id": cid,
                    "override_type": "billing_basis",
                    "changes": {"billing_basis": basis},
                })

        # --- capacity_or_tier_override ---
        if outcome == "capacity_or_tier_override":
            capacity = overrides.get("capacity_gib")
            tier = overrides.get("tier")
            spec = req.get("spec")
            if spec and isinstance(spec, dict):
                if capacity is not None:
                    spec["capacity_gib"] = capacity
                if tier:
                    spec["tier"] = tier
            else:
                # Build a minimal spec
                new_spec = {"spec_type": "storage"}
                if capacity is not None:
                    new_spec["capacity_gib"] = capacity
                if tier:
                    new_spec["tier"] = tier
                req["spec"] = new_spec
            effective_overrides.append({
                "item_id": cid,
                "override_type": "capacity_or_tier",
                "changes": {"capacity_gib": capacity, "tier": tier},
            })

    return {
        "requirements": requirements,
        "quote_blockers": blockers,
        "unquoted_items": unquoted,
        "excluded_by_manual_review": excluded_ids,
        "manual_review_effective_requirements": effective_overrides,
    }


def _recompute_billing_after_manual_review(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Recompute readiness, pricing, and quote items after manual review overrides.

    Takes a state with updated requirements (from _apply_manual_review_overrides_to_requirements)
    and reruns the pipeline from validate_quote_readiness onward.

    Returns updated state fields:
    - quote_ready_items, quote_blockers, unquoted_items, price_components,
      quote_lines, summary, billing_gap_analysis, billing_reconciliation,
      billing_blocker_analysis, billing_manual_review_design
    """
    catalog = state.get("price_catalog", [])
    region = FlexibleQuoteContext.model_validate(state.get("quote_context", {})).region

    # Re-run map_to_huawei_product (needed because normalized_product may have changed)
    mapped: list[dict[str, Any]] = []
    for item in state.get("requirements", []):
        requirement = RequirementItem.model_validate(item)
        if requirement.status == "excluded_by_manual_review":
            # Skip excluded items from mapping
            continue
        if requirement.normalized_product:
            mapped.append(
                MatchedProduct(
                    item_id=requirement.item_id,
                    product=requirement.normalized_product,
                    match_method="rule_match",
                    confidence=1,
                    rationale="Matched using local product synonym rules.",
                ).model_dump()
            )
        else:
            mapped.append(
                MatchedProduct(
                    item_id=requirement.item_id,
                    product=None,
                    match_method="llm_fallback",
                    confidence=0,
                    rationale="No deterministic product mapping hit.",
                ).model_dump()
            )

    # Re-run validate_quote_readiness
    # Exclude items that were excluded by manual review from the readiness check
    active_requirements = [
        r for r in state.get("requirements", [])
        if r.get("status") != "excluded_by_manual_review"
    ]
    val_state = {
        "requirements": active_requirements,
        "quote_context": state.get("quote_context", {}),
        "price_catalog": catalog,
        "matched_products": mapped,
        "understanding": state.get("understanding", {"profile": {}}),
        "audit_log": [],
        "progress_callback": None,
    }
    val_result = validate_quote_readiness(val_state)

    # Re-run resolve_price_components
    res_state = {
        "quote_ready_items": val_result["quote_ready_items"],
        "price_catalog": catalog,
        "unquoted_items": val_result["unquoted_items"],
        "audit_log": [],
        "progress_callback": None,
    }
    res_result = resolve_price_components(res_state)

    # Re-run quote_items
    quote_state = {
        "quote_ready_items": val_result["quote_ready_items"],
        "price_components": res_result["price_components"],
        "audit_log": [],
        "progress_callback": None,
    }
    quote_result = quote_items(quote_state)

    # Re-run summarize_quote
    sum_state = {
        "requirements": active_requirements,
        "quote_ready_items": val_result["quote_ready_items"],
        "quote_lines": quote_result["quote_lines"],
        "quote_blockers": val_result["quote_blockers"],
        "unquoted_items": res_result["unquoted_items"],
        "quote_context": state.get("quote_context", {}),
        "llm_aggregated_billing_items": state.get("llm_aggregated_billing_items", []),
        "audit_log": [],
        "progress_callback": None,
    }
    sum_result = summarize_quote(sum_state)

    return {
        "requirements": state.get("requirements", []),
        "matched_products": mapped,
        "quote_ready_items": val_result["quote_ready_items"],
        "quote_blockers": val_result["quote_blockers"],
        "unquoted_items": res_result["unquoted_items"],
        "price_components": res_result["price_components"],
        "quote_lines": quote_result["quote_lines"],
        "summary": sum_result["summary"],
        "billing_gap_analysis": sum_result.get("billing_gap_analysis", {}),
        "billing_reconciliation": sum_result.get("billing_reconciliation", {}),
        "billing_blocker_analysis": sum_result.get("billing_blocker_analysis", {}),
        "billing_manual_review_design": sum_result.get("billing_manual_review_design", {}),
    }


def _build_manual_review_closure_summary(
    before_summary: FlexibleQuoteSummary,
    after_summary: FlexibleQuoteSummary,
    excluded_ids: list[str],
    effective_overrides: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a stable outcome breakdown for manual review closure.

    Categories:
    - excluded_by_manual_review: items excluded via include_in_quote=false
    - newly_quoted_after_manual_review: items that went from unquoted/blocked → quoted
    - moved_to_unquoted_after_manual_review: items that went from blocked → unquoted
    - still_blocked_after_manual_review: items that remain blocked
    - unchanged_existing_quotes: quoted items that were already quoted before

    Also includes top unresolved items for delivery-facing reporting.
    """
    excluded_count = len(excluded_ids)

    # Newly quoted = max(0, after.quoted - before.quoted)
    newly_quoted = max(0, after_summary.quoted_items - before_summary.quoted_items)

    # Unchanged existing quotes = min(before.quoted, after.quoted)
    unchanged_existing = min(before_summary.quoted_items, after_summary.quoted_items)

    # Still blocked after = after.blocker_count
    still_blocked = after_summary.blocker_count

    # Moved to unquoted = items that were blockers before but are now unquoted
    # Approximation: (before.blockers - excluded - still_blocked) that didn't become quoted
    # More precise: after.unquoted - before.unquoted - newly_quoted_from_unquoted
    # But simplest stable calculation:
    moved_to_unquoted = max(0, after_summary.unquoted_count - before_summary.unquoted_count - newly_quoted)

    # Total decisions that had an effect (excluded or overrode)
    effective_override_count = len(effective_overrides)

    # Categorize effective overrides
    product_family_overrides = sum(
        1 for o in effective_overrides
        if o.get("override_type") in ("product_family", "mapping_override")
    )
    spec_overrides = sum(
        1 for o in effective_overrides
        if o.get("override_type") == "capacity_or_tier"
    )
    billing_basis_overrides = sum(
        1 for o in effective_overrides
        if o.get("override_type") == "billing_basis"
    )

    return {
        "excluded_by_manual_review": excluded_count,
        "newly_quoted_after_manual_review": newly_quoted,
        "moved_to_unquoted_after_manual_review": moved_to_unquoted,
        "still_blocked_after_manual_review": still_blocked,
        "unchanged_existing_quotes": unchanged_existing,
        "product_family_overrides": product_family_overrides,
        "spec_overrides": spec_overrides,
        "billing_basis_overrides": billing_basis_overrides,
        "total_effective_overrides": effective_override_count,
    }


def _rebuild_billing_state_after_manual_review(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Orchestrate: apply overrides → recompute → produce repricing summary.

    Reads applied_manual_review_results from state.
    Returns updated state with new counts and manual_review_reprice_summary.
    """
    applied_results = state.get("applied_manual_review_results", [])
    if not applied_results:
        return {}

    # Step 1: Apply overrides to requirements
    override_result = _apply_manual_review_overrides_to_requirements(state, applied_results)

    # Merge overrides into state
    merged_state = dict(state)
    merged_state["requirements"] = override_result["requirements"]
    merged_state["quote_blockers"] = override_result["quote_blockers"]
    merged_state["unquoted_items"] = override_result["unquoted_items"]

    # Step 2: Recompute from readiness onward
    recompute_result = _recompute_billing_after_manual_review(merged_state)

    # Step 3: Build repricing summary
    old_summary = FlexibleQuoteSummary.model_validate(state.get("summary", {}))
    new_summary = FlexibleQuoteSummary.model_validate(recompute_result["summary"])

    reprice_summary = {
        "before": {
            "quoted_items": old_summary.quoted_items,
            "blocker_count": old_summary.blocker_count,
            "unquoted_count": old_summary.unquoted_count,
            "total_monthly_price": old_summary.total_monthly_price,
        },
        "after": {
            "quoted_items": new_summary.quoted_items,
            "blocker_count": new_summary.blocker_count,
            "unquoted_count": new_summary.unquoted_count,
            "total_monthly_price": new_summary.total_monthly_price,
        },
        "excluded_by_manual_review": len(override_result["excluded_by_manual_review"]),
        "effective_overrides": len(override_result["manual_review_effective_requirements"]),
        "quote_delta": new_summary.quoted_items - old_summary.quoted_items,
        "blocker_delta": new_summary.blocker_count - old_summary.blocker_count,
        "unquoted_delta": new_summary.unquoted_count - old_summary.unquoted_count,
        "price_delta": round(new_summary.total_monthly_price - old_summary.total_monthly_price, 2),
    }

    result = {
        "requirements": recompute_result["requirements"],
        "matched_products": recompute_result["matched_products"],
        "quote_ready_items": recompute_result["quote_ready_items"],
        "quote_blockers": recompute_result["quote_blockers"],
        "unquoted_items": recompute_result["unquoted_items"],
        "price_components": recompute_result["price_components"],
        "quote_lines": recompute_result["quote_lines"],
        "summary": recompute_result["summary"],
        "billing_gap_analysis": recompute_result["billing_gap_analysis"],
        "billing_reconciliation": recompute_result["billing_reconciliation"],
        "billing_blocker_analysis": recompute_result["billing_blocker_analysis"],
        "billing_manual_review_design": recompute_result["billing_manual_review_design"],
        "excluded_by_manual_review": override_result["excluded_by_manual_review"],
        "manual_review_effective_requirements": override_result["manual_review_effective_requirements"],
        "manual_review_reprice_summary": reprice_summary,
    }

    # Step 4: Build closure summary with outcome breakdown
    closure = _build_manual_review_closure_summary(
        before_summary=old_summary,
        after_summary=new_summary,
        excluded_ids=override_result["excluded_by_manual_review"],
        effective_overrides=override_result["manual_review_effective_requirements"],
    )
    # Merge breakdown into reprice_summary for API/export alignment
    reprice_summary["outcome_breakdown"] = closure
    result["manual_review_closure_summary"] = closure

    return result


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
    """Build one detail row per billing resource, enriched with quote status and price.

    PRIMARY: prefers llm_aggregated_billing_items when available.
    FALLBACK: mapped_billing_resources for backward compatibility only.

    Phase 5D: This is the correct precedence — aggregated items are the
    source of truth for Cloud Billing; mapped resources are legacy compat.

    Rows are sorted: quoted → unquoted → manual_review → unsupported.
    """
    # Prefer aggregated items, fall back to mapped resources
    agg_items = state.get("llm_aggregated_billing_items", [])
    mapped = state.get("mapped_billing_resources", [])

    # Build detail source: use aggregated items if present, else mapped
    use_aggregated = bool(agg_items)
    detail_source: list[dict[str, Any]] = []
    if use_aggregated:
        for idx, item in enumerate(agg_items):
            detail_source.append({
                "detail_id": f"billing-agg::{item.get('source_file', '')}::{idx}",
                "product_type": item.get("product_type", ""),
                "product_sku": item.get("product_sku", "") or item.get("source_sku_hint", ""),
                "huawei_product": item.get("huawei_product"),
                "huawei_spec_hint": item.get("huawei_spec_hint", ""),
                "quantity": item.get("derived_quantity", 0),
                "unit_type": item.get("unit_type", ""),
                "unit": item.get("derived_unit", ""),
                "source_line_numbers": item.get("source_line_numbers", []),
                "needs_manual_review": item.get("needs_manual_review", False),
            })
    else:
        for mr in mapped:
            detail_source.append({
                "detail_id": mr.get("mapped_id", ""),
                "product_type": mr.get("product_type", ""),
                "product_sku": mr.get("product_sku", ""),
                "huawei_product": mr.get("huawei_product"),
                "huawei_spec_hint": mr.get("huawei_spec_hint", {}),
                "quantity": mr.get("quantity", 0),
                "unit_type": mr.get("unit_type", ""),
                "unit": mr.get("unit", ""),
                "source_line_numbers": mr.get("source_line_numbers", []),
                "needs_manual_review": mr.get("needs_manual_review", False),
            })

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
    for ds in detail_source:
        detail_id = ds["detail_id"]
        # Determine status
        if detail_id in quote_lines_by_item:
            status = "quoted"
        elif detail_id in unquoted_ids:
            status = "unquoted"
        elif detail_id in blocker_ids:
            status = "manual_review"
        elif ds.get("needs_manual_review"):
            status = "manual_review"
        elif ds.get("huawei_product") is None:
            status = "unsupported"
        else:
            status = "unquoted"

        # Get price data from quote line
        ql = quote_lines_by_item.get(detail_id, {})

        # Source resource label
        product_type = ds.get("product_type", "")
        product_sku = ds.get("product_sku", "")
        source_label = f"{product_type} | {product_sku}" if product_type != product_sku else product_type or product_sku

        # Format spec hint
        spec_hint_raw = ds.get("huawei_spec_hint", "")
        spec_hint_str = _format_billing_spec_hint(spec_hint_raw) if isinstance(spec_hint_raw, dict) else _billing_safe_text(spec_hint_raw)

        # Format source line numbers
        source_lines_str = _format_source_line_numbers(ds.get("source_line_numbers", []))

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
            "source_qty": ds.get("quantity", 0),
            "source_unit": ds.get("unit_type", ""),
            "source_sku": product_sku,
            "huawei_product": ds.get("huawei_product") or "",
            "huawei_spec_hint": spec_hint_str,
            "target_qty": ds.get("quantity", 0),
            "target_unit": ds.get("unit", ""),
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
    """Populate the ECS sheet as a billing detail page with 14 columns.

    Phase 9A.3: Row 1 has merged group headers:
      - A1:F1 = "Source Cloud" (covers source-side columns)
      - G1:O1 = "Huawei Cloud" (covers Huawei-side columns)
    Row 2 has individual column headers.
    """
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    num_cols = 14
    headers = config["ecs_headers"]
    ecs_data_start = config["ecs_data_start_row"]
    ecs_total = config["ecs_total_row"]
    ecs_template = config["ecs_template_row"]

    # ── Phase 9A.3: Row 1 group headers with merge ──
    group_header_font = Font(bold=True, size=12, color="FFFFFF")
    source_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    huawei_fill = PatternFill(start_color="548235", end_color="548235", fill_type="solid")
    center_align = Alignment(horizontal="center", vertical="center")

    # Unmerge any existing merged cells in row 1 to avoid MergedCell errors
    existing_merges = list(ws.merged_cells.ranges)
    for merge_range in existing_merges:
        if merge_range.min_row == 1:
            ws.unmerge_cells(str(merge_range))

    # Source Cloud header: A1:E1 (columns 1-5 are source-side)
    ws.merge_cells("A1:E1")
    cell_src = ws.cell(1, 1, "Source Cloud")
    cell_src.font = group_header_font
    cell_src.fill = source_fill
    cell_src.alignment = center_align

    # Huawei Cloud header: F1:N1 (columns 6-14 are Huawei-side)
    ws.merge_cells("F1:N1")
    cell_hwc = ws.cell(1, 6, "Huawei Cloud")
    cell_hwc.font = group_header_font
    cell_hwc.fill = huawei_fill
    cell_hwc.alignment = center_align

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

    # Billing gap analysis summary (Phase Next+3)
    gap = state.get("billing_gap_analysis")
    if gap:
        notes_parts.append("")
        notes_parts.append("GAP ANALYSIS:")
        notes_parts.append(f"  Quoted: ${gap.get('quoted_total', 0):,.2f} ({gap.get('quoted_pct', 0)}%)")
        notes_parts.append(f"  Unquoted source: ${gap.get('unquoted_source_total', 0):,.2f} ({gap.get('unquoted_pct', 0)}%)")
        top_gaps = gap.get("top_gaps", [])
        if top_gaps:
            notes_parts.append("  Top unquoted gaps (by source amount):")
            for tg in top_gaps[:5]:
                prod = tg.get("normalized_product", "?")
                unit = tg.get("unit", "?")
                amt = tg.get("total_source_amount", 0)
                reason = tg.get("reason_class", "?")
                notes_parts.append(f"    - {prod} [{unit}]: ${amt:,.2f} ({reason})")
        reason_dist = gap.get("reason_distribution", {})
        reason_amounts = reason_dist.get("source_amounts", {})
        if reason_amounts:
            notes_parts.append("  Unquoted reason breakdown:")
            for rc, ra in sorted(reason_amounts.items(), key=lambda x: -x[1]):
                if ra > 0:
                    notes_parts.append(f"    - {rc}: ${ra:,.2f}")

    # Billing reconciliation audit (Phase Next+5)
    reconciliation = state.get("billing_reconciliation")
    if reconciliation:
        suspicious_count = reconciliation.get("suspicious_count", 0)
        reclass_count = reconciliation.get("reclassification_count", 0)
        if suspicious_count > 0 or reclass_count > 0:
            notes_parts.append("")
            notes_parts.append("RECONCILIATION WARNING:")
            if suspicious_count > 0:
                notes_parts.append(f"  {suspicious_count} quoted line(s) with suspicious price vs source delta")
            if reclass_count > 0:
                notes_parts.append(f"  {reclass_count} item(s) blocked from capacity pricing (no evidence)")
            top_deltas = reconciliation.get("top_positive_deltas", [])
            if top_deltas:
                notes_parts.append("  Top overstated deltas:")
                for td in top_deltas[:5]:
                    prod = td.get("product", "?")
                    delta = td.get("delta", 0)
                    ratio = td.get("delta_ratio")
                    ratio_str = f"{ratio:.1f}x" if ratio else "?"
                    notes_parts.append(f"    - {prod}: +${delta:,.2f} ({ratio_str})")

    # Blocker triage (Phase Next+7)
    blocker_analysis = state.get("billing_blocker_analysis")
    if blocker_analysis and blocker_analysis.get("blocker_total", 0) > 0:
        notes_parts.append("")
        notes_parts.append("BLOCKER TRIAGE:")
        notes_parts.append(f"  Total blockers: {blocker_analysis['blocker_total']}")
        cat_counts = blocker_analysis.get("blocker_categories", {})
        if cat_counts:
            for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
                notes_parts.append(f"    - {cat}: {cnt}")
        downgradable = blocker_analysis.get("downgradable_count", 0)
        remaining = blocker_analysis.get("remaining_blocker_count", 0)
        if downgradable > 0:
            notes_parts.append(f"  Downgradable to unquoted: {downgradable}")
            notes_parts.append(f"  True blockers (need human review): {remaining}")

    # Manual review design (Phase Next+8)
    manual_review = state.get("billing_manual_review_design")
    if manual_review and manual_review.get("total_candidates", 0) > 0:
        notes_parts.append("")
        notes_parts.append("MANUAL REVIEW DESIGN:")
        notes_parts.append(f"  Unsupported items needing review: {manual_review['total_candidates']}")
        scope_count = manual_review.get("scope_decision_count", 0)
        mapping_count = manual_review.get("mapping_decision_count", 0)
        notes_parts.append(f"  Need product mapping: {mapping_count}")
        notes_parts.append(f"  May be out of scope: {scope_count}")
        top_unsupported = manual_review.get("top_unsupported_by_amount", [])
        if top_unsupported:
            notes_parts.append("  Top unsupported items (by source amount):")
            for tu in top_unsupported[:5]:
                label = tu.get("source_label", "?")
                amt = tu.get("source_amount", 0)
                family = tu.get("suggested_family") or "no suggestion"
                notes_parts.append(f"    - {label}: ${amt:,.2f} → {family}")

    # Manual review apply (Phase Next+9)
    apply_summary = state.get("manual_review_apply_summary")
    if apply_summary and apply_summary.get("decisions_applied", 0) > 0:
        notes_parts.append("")
        notes_parts.append("MANUAL REVIEW APPLY:")
        notes_parts.append(f"  Decisions applied: {apply_summary['decisions_applied']}")
        notes_parts.append(f"  Excluded by manual review: {apply_summary['excluded_by_manual_review']}")
        notes_parts.append(f"  Mapped overrides: {apply_summary['mapped_overrides']}")
        notes_parts.append(f"  Include but needs mapping: {apply_summary.get('include_but_needs_mapping', 0)}")
        notes_parts.append(f"  Unresolved after manual review: {apply_summary['unresolved_after_manual_review']}")

    # Manual review repricing (Phase Next+11)
    reprice_summary = state.get("manual_review_reprice_summary")
    if reprice_summary:
        notes_parts.append("")
        notes_parts.append("MANUAL REVIEW REPRICE:")
        before = reprice_summary.get("before", {})
        after = reprice_summary.get("after", {})
        notes_parts.append(f"  Baseline: {before.get('quoted_items', '?')} quoted, {before.get('blocker_count', '?')} blocked, ${before.get('total_monthly_price', 0):,.2f}/mo")
        notes_parts.append(f"  After review: {after.get('quoted_items', '?')} quoted, {after.get('blocker_count', '?')} blocked, ${after.get('total_monthly_price', 0):,.2f}/mo")
        breakdown = reprice_summary.get("outcome_breakdown", {})
        if breakdown:
            notes_parts.append(f"  Excluded from quote: {breakdown.get('excluded_by_manual_review', 0)}")
            notes_parts.append(f"  Newly quoted: {breakdown.get('newly_quoted_after_manual_review', 0)}")
            notes_parts.append(f"  Moved to unquoted: {breakdown.get('moved_to_unquoted_after_manual_review', 0)}")
            notes_parts.append(f"  Still blocked: {breakdown.get('still_blocked_after_manual_review', 0)}")
            notes_parts.append(f"  Unchanged quotes: {breakdown.get('unchanged_existing_quotes', 0)}")
        else:
            notes_parts.append(f"  Excluded from quote: {reprice_summary.get('excluded_by_manual_review', 0)}")
            notes_parts.append(f"  Effective overrides: {reprice_summary.get('effective_overrides', 0)}")
        price_delta = reprice_summary.get("price_delta", 0)
        if price_delta != 0:
            notes_parts.append(f"  Price change: ${price_delta:,.2f}/mo (from newly quoted items)")

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

    # Billing gap analysis (Phase Next+3)
    gap = state.get("billing_gap_analysis")
    if gap:
        lines.append("GAP ANALYSIS:")
        lines.append(f"  Quoted total: ${gap.get('quoted_total', 0):,.2f} ({gap.get('quoted_pct', 0)}% of source)")
        lines.append(f"  Unquoted source total: ${gap.get('unquoted_source_total', 0):,.2f} ({gap.get('unquoted_pct', 0)}%)")
        top_gaps = gap.get("top_gaps", [])
        if top_gaps:
            lines.append(f"  Top {min(len(top_gaps), 5)} unquoted gap categories:")
            for tg in top_gaps[:5]:
                prod = tg.get("normalized_product", "?")
                unit = tg.get("unit", "?")
                amt = tg.get("total_source_amount", 0)
                cnt = tg.get("count", 0)
                reason = tg.get("reason_class", "?")
                lines.append(f"    - {prod} [{unit}]: ${amt:,.2f} ({cnt} items, reason: {reason})")
        reason_dist = gap.get("reason_distribution", {})
        reason_counts = reason_dist.get("counts", {})
        reason_amounts = reason_dist.get("source_amounts", {})
        if reason_amounts:
            lines.append("  Unquoted reason breakdown:")
            for rc in sorted(reason_amounts, key=lambda k: -reason_amounts[k]):
                ra = reason_amounts[rc]
                cnt = reason_counts.get(rc, 0)
                if ra > 0:
                    lines.append(f"    - {rc}: {cnt} item(s), ${ra:,.2f}")
        lines.append("")

    # Billing reconciliation audit (Phase Next+5)
    reconciliation = state.get("billing_reconciliation")
    if reconciliation:
        suspicious_count = reconciliation.get("suspicious_count", 0)
        reclass_count = reconciliation.get("reclassification_count", 0)
        if suspicious_count > 0 or reclass_count > 0:
            lines.append("RECONCILIATION WARNING:")
            if suspicious_count > 0:
                lines.append(f"  {suspicious_count} quoted line(s) with suspicious price vs source delta")
                overstated = reconciliation.get("overstated_total", 0)
                if overstated > 0:
                    lines.append(f"  Overstated total: ${overstated:,.2f}")
            if reclass_count > 0:
                lines.append(f"  {reclass_count} item(s) blocked from capacity pricing (no evidence)")
            top_deltas = reconciliation.get("top_positive_deltas", [])
            if top_deltas:
                lines.append(f"  Top {min(len(top_deltas), 5)} overstated deltas:")
                for td in top_deltas[:5]:
                    prod = td.get("product", "?")
                    quoted = td.get("quoted_amount", 0)
                    source = td.get("source_amount", 0)
                    delta = td.get("delta", 0)
                    ratio = td.get("delta_ratio")
                    ratio_str = f"{ratio:.1f}x" if ratio else "?"
                    lines.append(f"    - {prod}: quoted=${quoted:,.2f} vs source=${source:,.2f} (+${delta:,.2f}, {ratio_str})")
            lines.append("")

    # Blocker triage (Phase Next+7)
    blocker_analysis = state.get("billing_blocker_analysis")
    if blocker_analysis and blocker_analysis.get("blocker_total", 0) > 0:
        lines.append("BLOCKER TRIAGE:")
        lines.append(f"  Total blockers: {blocker_analysis['blocker_total']}")
        cat_counts = blocker_analysis.get("blocker_categories", {})
        if cat_counts:
            lines.append("  Blocker categories:")
            for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
                lines.append(f"    - {cat}: {cnt}")
        top_cats = blocker_analysis.get("top_blocker_categories", [])
        if top_cats:
            lines.append(f"  Top blocker categories:")
            for tc in top_cats[:5]:
                lines.append(f"    - {tc['category']}: {tc['count']} item(s)")
        downgradable = blocker_analysis.get("downgradable_count", 0)
        remaining = blocker_analysis.get("remaining_blocker_count", 0)
        if downgradable > 0:
            lines.append(f"  Downgradable to unquoted: {downgradable}")
        lines.append(f"  True blockers (need human review): {remaining}")
        lines.append("")

    # Manual review design (Phase Next+8)
    manual_review = state.get("billing_manual_review_design")
    if manual_review and manual_review.get("total_candidates", 0) > 0:
        lines.append("MANUAL REVIEW DESIGN:")
        lines.append(f"  Unsupported items needing review: {manual_review['total_candidates']}")
        mr_categories = manual_review.get("categories", {})
        if mr_categories:
            lines.append("  Review need categories:")
            for cat, cnt in sorted(mr_categories.items(), key=lambda x: -x[1]):
                lines.append(f"    - {cat}: {cnt}")
        top_unsupported = manual_review.get("top_unsupported_by_amount", [])
        if top_unsupported:
            lines.append(f"  Top {min(len(top_unsupported), 5)} unsupported items (by source amount):")
            for tu in top_unsupported[:5]:
                label = tu.get("source_label", "?")
                amt = tu.get("source_amount", 0)
                family = tu.get("suggested_family") or "no suggestion"
                need = tu.get("manual_review_need", "?")
                lines.append(f"    - {label}: ${amt:,.2f} (need: {need}, suggest: {family})")
        field_freq = manual_review.get("minimal_field_frequency", {})
        if field_freq:
            lines.append("  Minimal fields to collect:")
            for field, cnt in sorted(field_freq.items(), key=lambda x: -x[1]):
                lines.append(f"    - {field}: {cnt} item(s)")
        scope_count = manual_review.get("scope_decision_count", 0)
        mapping_count = manual_review.get("mapping_decision_count", 0)
        lines.append(f"  Summary: {mapping_count} need product mapping, {scope_count} may be out of scope")
        lines.append("")

    # Manual review apply (Phase Next+9)
    apply_summary = state.get("manual_review_apply_summary")
    if apply_summary and apply_summary.get("decisions_applied", 0) > 0:
        lines.append("MANUAL REVIEW APPLY:")
        lines.append(f"  Decisions applied: {apply_summary['decisions_applied']}")
        lines.append(f"  Excluded by manual review: {apply_summary['excluded_by_manual_review']}")
        lines.append(f"  Mapped overrides: {apply_summary['mapped_overrides']}")
        lines.append(f"  Include but needs mapping: {apply_summary.get('include_but_needs_mapping', 0)}")
        lines.append(f"  Unresolved after manual review: {apply_summary['unresolved_after_manual_review']}")
        # Show individual applied results
        applied_results = state.get("applied_manual_review_results", [])
        if applied_results:
            lines.append("  Applied decisions:")
            for ar in applied_results:
                cid = ar.get("candidate_id", "?")
                outcome = ar.get("outcome", "?")
                overrides = ar.get("overrides", {})
                override_str = ", ".join(f"{k}={v}" for k, v in overrides.items()) if overrides else "none"
                lines.append(f"    - {cid}: {outcome} ({override_str})")
        lines.append("")

    # Manual review repricing (Phase Next+11)
    reprice_summary = state.get("manual_review_reprice_summary")
    if reprice_summary:
        lines.append("MANUAL REVIEW REPRICE:")
        before = reprice_summary.get("before", {})
        after = reprice_summary.get("after", {})
        lines.append(f"  Baseline: {before.get('quoted_items', '?')} quoted, {before.get('blocker_count', '?')} blocked, {before.get('unquoted_count', '?')} unquoted, ${before.get('total_monthly_price', 0):,.2f}/mo")
        lines.append(f"  After review: {after.get('quoted_items', '?')} quoted, {after.get('blocker_count', '?')} blocked, {after.get('unquoted_count', '?')} unquoted, ${after.get('total_monthly_price', 0):,.2f}/mo")
        breakdown = reprice_summary.get("outcome_breakdown", {})
        if breakdown:
            lines.append(f"  Excluded from quote: {breakdown.get('excluded_by_manual_review', 0)}")
            lines.append(f"  Newly quoted: {breakdown.get('newly_quoted_after_manual_review', 0)}")
            lines.append(f"  Moved to unquoted: {breakdown.get('moved_to_unquoted_after_manual_review', 0)}")
            lines.append(f"  Still blocked: {breakdown.get('still_blocked_after_manual_review', 0)}")
            lines.append(f"  Unchanged quotes: {breakdown.get('unchanged_existing_quotes', 0)}")
            lines.append(f"  Product family overrides: {breakdown.get('product_family_overrides', 0)}")
            lines.append(f"  Spec overrides: {breakdown.get('spec_overrides', 0)}")
            lines.append(f"  Billing basis overrides: {breakdown.get('billing_basis_overrides', 0)}")
        else:
            lines.append(f"  Excluded from quote: {reprice_summary.get('excluded_by_manual_review', 0)}")
            lines.append(f"  Effective overrides: {reprice_summary.get('effective_overrides', 0)}")
        price_delta = reprice_summary.get("price_delta", 0)
        if price_delta != 0:
            lines.append(f"  Price change: ${price_delta:,.2f}/mo (from newly quoted items)")
        # Top unresolved items after manual review
        blockers_after = state.get("quote_blockers", [])
        if blockers_after:
            lines.append(f"  Top unresolved items ({len(blockers_after)}):")
            for b in blockers_after[:5]:
                product = b.get("product", "?")
                msg = b.get("message", "")
                lines.append(f"    - {product}: {msg}")
            if len(blockers_after) > 5:
                lines.append(f"    ... and {len(blockers_after) - 5} more")
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


def _populate_billing_quotation_sheet(workbook: Any, state: FlexibleQuoteState) -> None:
    """Populate the Quotation sheet with final_billing_quote_items.

    Phase 8E: This is the main customer-readable sheet.
    Columns: Source Cloud Service, Source Config Summary, Quantity,
    Source Billing Basis, Source Monthly USD, Huawei Cloud Product,
    Huawei Config Summary, Huawei Quantity, Huawei Unit Price USD,
    Huawei Billing Basis, Huawei Monthly USD, Status, Notes.
    """
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    final_items_raw = state.get("final_billing_quote_items", [])
    final_items = [CloudBillingFinalQuoteItem.model_validate(fi) for fi in final_items_raw]

    # Create or get the Quotation sheet
    if "Quotation" in workbook.sheetnames:
        ws = workbook["Quotation"]
    else:
        ws = workbook.create_sheet("Quotation", 0)  # Insert as first sheet

    headers = [
        "Source Cloud Service",
        "Source Config Summary",
        "Quantity",
        "Source Billing Basis",
        "Source Monthly USD",
        "Huawei Cloud Product",
        "Huawei Config Summary",
        "Huawei Quantity",
        "Huawei Unit Price USD",
        "Huawei Billing Basis",
        "Huawei Monthly USD",
        "Status",
        "Notes",
    ]

    # Styles
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font_white = Font(bold=True, size=11, color="FFFFFF")
    thin_border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )
    number_fmt = "#,##0.00"

    # Title row
    ws.cell(1, 1, "Cloud Billing Quotation — Final Items")
    ws.cell(1, 1).font = Font(bold=True, size=14)

    # Header row
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(3, col_idx, header)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        cell.border = thin_border

    # Data rows
    status_colors = {
        "quoted": PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"),
        "partial": PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid"),
        "manual_review": PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid"),
        "unquoted": PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid"),
    }

    for row_offset, item in enumerate(final_items):
        row = 4 + row_offset
        ws.cell(row, 1, item.source_service_name)
        ws.cell(row, 2, item.source_config_summary or "")
        ws.cell(row, 3, item.source_quantity if item.source_quantity is not None else "")
        ws.cell(row, 4, item.source_pricing_basis or "")
        src_monthly = item.source_monthly_total_usd
        c5 = ws.cell(row, 5, src_monthly if src_monthly is not None else None)
        if src_monthly is not None:
            c5.number_format = number_fmt
        ws.cell(row, 6, item.huawei_product or "")
        ws.cell(row, 7, item.huawei_spec_summary or "")
        ws.cell(row, 8, item.huawei_quantity if item.huawei_quantity is not None else "")
        c9 = ws.cell(row, 9, item.huawei_unit_price_usd if item.huawei_unit_price_usd is not None else None)
        if item.huawei_unit_price_usd is not None:
            c9.number_format = number_fmt
        ws.cell(row, 10, item.huawei_billing_basis or "")
        c11 = ws.cell(row, 11, item.huawei_monthly_total_usd if item.huawei_monthly_total_usd is not None else None)
        if item.huawei_monthly_total_usd is not None:
            c11.number_format = number_fmt
        ws.cell(row, 12, item.status)
        # Notes: composition_notes + manual_review_reason
        notes = list(item.composition_notes)
        if item.manual_review_reason:
            notes.append(item.manual_review_reason)
        ws.cell(row, 13, "; ".join(notes) if notes else "")

        # Apply status color to status cell
        fill = status_colors.get(item.status)
        if fill:
            ws.cell(row, 12).fill = fill

    # Total row — clearly separated from data rows (Phase 9A.4)
    # Data rows are 4..(4+len-1); total row is 4+len+1 (with a blank gap row)
    total_row = 4 + len(final_items) + 1
    total_fill = PatternFill(start_color="D9E2F3", end_color="D9E2F3", fill_type="solid")
    total_font = Font(bold=True, size=11)
    ws.cell(total_row, 1, "TOTAL")
    ws.cell(total_row, 1).font = total_font
    ws.cell(total_row, 1).fill = total_fill
    # Mark column 2 so parsers can identify this as a summary row
    ws.cell(total_row, 2, "— summary row —")
    ws.cell(total_row, 2).font = Font(italic=True, size=9, color="808080")
    # Sum source monthly
    src_total = sum(
        fi.source_monthly_total_usd or 0
        for fi in final_items
        if fi.source_monthly_total_usd is not None
    )
    c_src = ws.cell(total_row, 5, round(src_total, 2) if src_total else None)
    if src_total:
        c_src.number_format = number_fmt
        c_src.font = total_font
        c_src.fill = total_fill
    # Sum Huawei monthly
    hwc_total = sum(
        fi.huawei_monthly_total_usd or 0
        for fi in final_items
        if fi.huawei_monthly_total_usd is not None
    )
    c_hwc = ws.cell(total_row, 11, round(hwc_total, 2) if hwc_total else None)
    if hwc_total:
        c_hwc.number_format = number_fmt
        c_hwc.font = total_font
        c_hwc.fill = total_fill
    # Status summary — placed in Notes column (13) not Status column (12)
    # to avoid polluting status counts when the sheet is read back
    quoted = sum(1 for fi in final_items if fi.status == "quoted")
    partial = sum(1 for fi in final_items if fi.status == "partial")
    mr = sum(1 for fi in final_items if fi.status == "manual_review")
    uq = sum(1 for fi in final_items if fi.status == "unquoted")
    ws.cell(total_row, 12, "")  # Leave status cell empty for TOTAL row
    ws.cell(total_row, 13, f"Quoted: {quoted} | Partial: {partial} | Review: {mr} | Unquoted: {uq}")
    ws.cell(total_row, 13).font = Font(italic=True, size=9)

    # Column widths
    col_widths = [25, 30, 10, 18, 16, 20, 30, 12, 16, 18, 16, 14, 40]
    for idx, width in enumerate(col_widths, start=1):
        ws.column_dimensions[ws.cell(3, idx).column_letter].width = width


def _quoted_filename_from_state(state: FlexibleQuoteState) -> str:
    """Build a download filename: Quoted-{first source stem}.xlsx.

    Source may be .xlsx/.csv/.pdf; the original extension is stripped and the
    export is always .xlsx. Stems are ASCII-safe. Falls back to
    'Quoted-cloud-billing.xlsx' when no usable source name is available.
    """
    default = "Quoted-cloud-billing.xlsx"
    files = state.get("files", []) or []
    raw = ""
    for f in files:
        name = f.get("filename") if isinstance(f, dict) else None
        if name:
            raw = name
            break
    stem = re.sub(r"\.(xlsx|xls|csv|pdf|txt)$", "", raw, flags=re.I).strip()
    if not stem:
        return default
    normalized = unicodedata.normalize("NFKD", stem)
    ascii_stem = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_stem).strip("-._")
    if not ascii_stem:
        return default
    return f"Quoted-{ascii_stem}.xlsx"


def _export_flexible_billing_template_workbook(state: FlexibleQuoteState) -> QuoteWorkbook:
    """Export billing quote using a template selected by profile.

    Phase 8E: Dual-layer output.
    - Main sheet "Quotation" uses final_billing_quote_items (customer-readable)
    - Auxiliary sheet "Billing Detail" (ECS) retains internal aggregated items
    - HWC sheet retains Huawei product aggregation
    """
    profile = _select_billing_template_profile(state)
    config = _template_profile_config(profile)
    template_path = config["template_path"]

    if not template_path.exists():
        raise FileNotFoundError(f"Billing template not found at {template_path}")

    workbook = load_workbook(template_path)
    for sheet_name in config["required_sheets"]:
        if sheet_name not in workbook.sheetnames:
            raise KeyError(f"Template missing required sheet: {sheet_name}")

    # ── Phase 8E: Quotation sheet (main, customer-readable) ──
    _populate_billing_quotation_sheet(workbook, state)

    # ECS sheet → billing detail page (auxiliary / audit)
    detail_rows = _build_billing_detail_rows(state)
    _populate_billing_ecs_sheet(workbook["ECS"], detail_rows, config)

    # HWC sheet → Huawei product aggregation
    hwc_rows = _build_billing_hwc_rows(state)
    _populate_billing_hwc_sheet(workbook["HWC"], hwc_rows, config)

    # Summary sheet
    _populate_billing_summary_sheet(workbook["Summary"], state, config)

    # Información sheet
    _populate_billing_info_sheet(workbook["Información"], state, profile)

    filename = _quoted_filename_from_state(state)
    output = BytesIO()
    workbook.save(output)
    return QuoteWorkbook(filename=filename, content=output.getvalue())


def _inventory_row_lookup(state: FlexibleQuoteState) -> dict[tuple[str, str | None, int], dict[str, Any]]:
    lookup: dict[tuple[str, str | None, int], dict[str, Any]] = {}
    for document in state.get("parsed_documents", []):
        if not _looks_like_vm_inventory_document(document):
            continue
        filename = document.get("filename", "")
        sheet = document.get("sheet")
        for row in document.get("rows", []):
            line_number_raw = row.get("_line_number")
            try:
                line_number = int(line_number_raw)
            except (TypeError, ValueError):
                continue
            lookup[(filename, sheet, line_number)] = row
    return lookup


def _inventory_disk_gib(row: dict[str, Any] | None) -> float:
    if not row:
        return 0.0
    disk_gib = _to_float(_inventory_value(row, STORAGE_GIB_COLUMNS))
    if disk_gib is not None:
        return round(disk_gib, 2)
    disk_mib = _to_float(_inventory_value(row, STORAGE_MIB_COLUMNS))
    if disk_mib is not None:
        return round(disk_mib / 1024, 2)
    return 0.0


def _inventory_raw_memory_mb(row: dict[str, Any] | None, spec: ComputeSpec | None) -> float | None:
    if row:
        memory_mb = _to_float(_inventory_value(row, MEMORY_MIB_COLUMNS))
        if memory_mb is not None:
            return memory_mb
    if spec and spec.memory_gib is not None:
        return round(spec.memory_gib * 1024, 2)
    return None


def _inventory_raw_storage_mib(row: dict[str, Any] | None, disk_gib: float) -> float | None:
    if row:
        storage_mib = _to_float(_inventory_value(row, STORAGE_MIB_COLUMNS))
        if storage_mib is not None:
            return storage_mib
    if disk_gib > 0:
        return round(disk_gib * 1024, 2)
    return None


def _inventory_review_reason(
    requirement: RequirementItem,
    blocker_by_item: dict[str, dict[str, Any]],
    unquoted_by_item: dict[str, dict[str, Any]],
) -> str | None:
    blocker = blocker_by_item.get(requirement.item_id)
    if blocker:
        return str(blocker.get("message") or requirement.status_reason or "").strip() or None
    unquoted = unquoted_by_item.get(requirement.item_id)
    if unquoted:
        return str(unquoted.get("reason") or requirement.status_reason or "No matched price was found.").strip() or None
    return requirement.status_reason


def _build_inventory_template_quote_lines(state: FlexibleQuoteState) -> list[dict[str, Any]]:
    from app.models import QuoteLine

    row_lookup = _inventory_row_lookup(state)
    quote_lines_by_item: dict[str, list[FlexibleQuoteLine]] = {}
    for raw_line in state.get("quote_lines", []):
        line = FlexibleQuoteLine.model_validate(raw_line)
        quote_lines_by_item.setdefault(line.requirement_item_id, []).append(line)

    blocker_by_item = {
        item.get("item_id", ""): item
        for item in state.get("quote_blockers", [])
        if item.get("item_id")
    }
    unquoted_by_item = {
        item.get("item_id", ""): item
        for item in state.get("unquoted_items", [])
        if item.get("item_id")
    }

    template_lines: list[dict[str, Any]] = []
    for raw_requirement in state.get("requirements", []):
        requirement = RequirementItem.model_validate(raw_requirement)
        if requirement.normalized_product != "ECS":
            continue
        spec = requirement.spec if isinstance(requirement.spec, ComputeSpec) else None
        row = row_lookup.get((requirement.source_file, requirement.source_sheet, requirement.row_number or 0))
        vm_name = str(_inventory_value(row, VM_NAME_COLUMNS) or requirement.raw_product_name or requirement.item_id).strip()
        os_name = str(_inventory_value(row, OS_COLUMNS) or "").strip()
        disk_gib = _inventory_disk_gib(row)
        raw_memory_mb = _inventory_raw_memory_mb(row, spec)
        raw_storage_mib = _inventory_raw_storage_mib(row, disk_gib)
        quoted_lines = quote_lines_by_item.get(requirement.item_id, [])
        quoted_line = quoted_lines[0] if quoted_lines else None
        monthly_price = round(sum(line.monthly_price for line in quoted_lines), 4)
        action = "quote" if quoted_line else "manual_review"
        template_lines.append(
            QuoteLine(
                vm_name=vm_name,
                power_state="",
                os=os_name,
                vcpu=spec.vcpu or 0 if spec else 0,
                memory_gib=spec.memory_gib or 0 if spec and spec.memory_gib is not None else 0,
                disk_gib=disk_gib,
                customer=None,
                workload_type=None,
                source_sheet=requirement.source_sheet,
                source_dc=requirement.source_sheet,
                raw_memory_mb=raw_memory_mb,
                raw_storage_mib=raw_storage_mib,
                workload_category=None,
                storage_class_hint="general-purpose-ssd" if disk_gib > 0 else None,
                license_hint=None,
                ecs_family_hint=None,
                classification_confidence=None,
                classification_rationale=None,
                review_flags=[],
                action=action,
                review_reason=None if quoted_line else _inventory_review_reason(requirement, blocker_by_item, unquoted_by_item),
                region=requirement.region or "mexico",
                evs_type="gpssd",
                ecs_category=None,
                ecs_family_label=None,
                ecs_spec=quoted_line.matched_sku if quoted_line else (spec.sku if spec else None),
                ecs_vcpu=spec.vcpu if spec else None,
                ecs_mem=spec.memory_gib if spec else None,
                ecs_ondemand_monthly_usd=monthly_price if quoted_line else 0,
                ecs_ri_1y_monthly_usd=monthly_price if quoted_line else 0,
                evs_monthly_usd=0,
                total_ondemand_monthly_usd=monthly_price if quoted_line else 0,
                total_ri_1y_monthly_usd=monthly_price if quoted_line else 0,
                evs_selected_type="gpssd",
                evs_selected_label="General Purpose SSD",
                ecs_family_policy=None,
            ).model_dump()
        )
    return template_lines


def _should_use_inventory_template_export(state: FlexibleQuoteState) -> bool:
    if state.get("mapped_billing_resources") or state.get("billing_lines"):
        return False
    if any(_looks_like_vm_inventory_document(document) for document in state.get("parsed_documents", [])):
        return True
    requirements = [RequirementItem.model_validate(item) for item in state.get("requirements", [])]
    if not requirements:
        return False
    ecs_requirements = [
        requirement
        for requirement in requirements
        if requirement.normalized_product == "ECS" and isinstance(requirement.spec, ComputeSpec)
    ]
    return len(ecs_requirements) == len(requirements)


def _export_inventory_template_workbook(state: FlexibleQuoteState) -> QuoteWorkbook:
    from app.models import QuoteRequest, QuoteSummary
    from app.workflow import export_excel

    template_lines = _build_inventory_template_quote_lines(state)
    quote_context = FlexibleQuoteContext.model_validate(state.get("quote_context", {}))
    source_files = sorted({item.get("source_file", "") for item in state.get("requirements", []) if item.get("source_file")})
    source_filename = source_files[0] if source_files else "inventory.xlsx"
    quoted_lines = [item for item in template_lines if item.get("action") == "quote"]
    manual_lines = [item for item in template_lines if item.get("action") == "manual_review"]
    total_disk = round(sum(_billing_safe_number(item.get("disk_gib")) for item in template_lines), 2)
    total_price = round(sum(_billing_safe_number(item.get("total_ondemand_monthly_usd")) for item in quoted_lines), 2)
    summary = QuoteSummary(
        total_vms=len(template_lines),
        excluded_vms=0,
        manual_review_vms=len(manual_lines),
        quoted_vms=len(quoted_lines),
        total_disk_gib=total_disk,
        total_ondemand_monthly_usd=total_price,
        total_ri_1y_monthly_usd=total_price,
        summary="Inventory-style Others quote exported with the RVTools template layout.",
        assumptions=[
            "Inventory-style Others input was normalized into ECS template rows.",
        ],
        risks=["Some non-ECS components may require manual review."] if manual_lines else [],
    )
    request = QuoteRequest(
        region=quote_context.region or "mexico",
        evs_type="gpssd",
        lang=quote_context.language,
        source_filename=source_filename,
    )
    result = export_excel(
        {
            "summary": summary.model_dump(),
            "request": request.model_dump(),
            "quote_lines": template_lines,
            "source_filenames": source_files or [source_filename],
            "pricebook": {},
        }
    )
    return QuoteWorkbook.model_validate(result["workbook"])


def export_flexible_workbook(state: FlexibleQuoteState) -> FlexibleQuoteState:
    """Export flexible quote workbook.

    Billing state (with mapped_billing_resources) uses the RVTools template.
    Normal flexible state uses the generic multi-sheet workbook.
    """
    is_billing = bool(state.get("mapped_billing_resources") or state.get("billing_lines"))
    if is_billing:
        wb = _export_flexible_billing_template_workbook(state)
        return {"workbook": wb}
    if _should_use_inventory_template_export(state):
        wb = _export_inventory_template_workbook(state)
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
        "billing_lines": list(request.billing_lines),
        "llm_aggregated_billing_items": list(request.llm_aggregated_billing_items),
        "mapped_billing_resources": list(request.mapped_billing_resources),
        "billing_gap_analysis": dict(request.billing_gap_analysis),
        "billing_reconciliation": dict(request.billing_reconciliation),
        "final_billing_quote_items": [item.model_dump() for item in request.final_billing_quote_items],
        "price_catalog": [item.model_dump() for item in query_flexible_pricing_catalog()],
    }


flexible_preview_graph = build_flexible_preview_graph()
flexible_review_graph = build_flexible_review_graph()
flexible_export_graph = build_flexible_export_graph()
