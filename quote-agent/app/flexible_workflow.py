from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, TypedDict

import httpx
import pandas as pd
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
    "dli": "DLI",
    "data lake insight": "DLI",
    "modelarts": "ModelArts",
    "functiongraph": "FunctionGraph",
    "函数": "FunctionGraph",
    "gaussdb": "GaussDB",
    "高斯数据库": "GaussDB",
}
SPEC_REQUIRED_PRODUCTS = {"ECS", "EVS", "RDS", "SFS Turbo", "DDS", "DWS", "OBS", "CCE", "CCI"}
NETWORK_PRODUCTS = {"EIP", "NAT Gateway", "VPN", "Direct Connect as a Service", "ELB", "VPC"}
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


def parse_documents(state: FlexibleQuoteState) -> FlexibleQuoteState:
    _report_progress(state, "parse_documents", "running", "Parsing uploaded documents.")
    documents: list[dict[str, Any]] = []
    for upload in state["files"]:
        if upload["extension"] == "xlsx":
            documents.extend(_parse_excel_workbook(upload["content"], upload["filename"]))
        elif upload["extension"] == "csv":
            frame = pd.read_csv(BytesIO(upload["content"])).fillna("")
            documents.append(
                {
                    "filename": upload["filename"],
                    "sheet": "csv",
                    "columns": [str(column) for column in frame.columns],
                    "rows": frame.to_dict(orient="records"),
                }
            )
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
    understanding = FlexibleSchemaMapping.model_validate(state["understanding"]["schema_mapping"])
    requirements: list[dict[str, Any]] = []
    diagnostics = _diagnostics(state)
    document_diagnostics: list[FlexibleDocumentDiagnostic] = []
    for document in state["parsed_documents"]:
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


def normalize_requirements(state: FlexibleQuoteState) -> FlexibleQuoteState:
    _report_progress(state, "normalize_requirements", "running", "Normalizing products, regions, and specs.")
    quote_context = FlexibleQuoteContext.model_validate(state["quote_context"])
    normalized: list[dict[str, Any]] = []
    for item in state["requirements"]:
        requirement = RequirementItem.model_validate(item)
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

    for raw_item in state["requirements"]:
        requirement = RequirementItem.model_validate(raw_item)
        matched = matched_by_item.get(requirement.item_id)
        product = matched.product if matched else requirement.normalized_product
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
        if requirement.spec:
            spec_data = requirement.spec.model_dump()
            sku = str(spec_data.get("sku") or "").lower()
            tier = str(spec_data.get("tier") or "").lower()
            if sku:
                candidates = [item for item in candidates if (item.sku or "").lower() == sku] or candidates
            elif tier:
                candidates = [item for item in candidates if tier in ((item.tier or "").lower(), (item.sku or "").lower())] or candidates
        if not candidates:
            unquoted.append(requirement.model_copy(update={"status": "needs_price_confirmation", "status_reason": "No confirmed local price matched the requested spec."}))
            continue
        resolved.append(candidates[0].model_dump())
    message = f"Resolved {len(resolved)} price component(s)."
    _report_progress(state, "resolve_price_components", "completed", message)
    return {
        "price_components": resolved,
        "unquoted_items": [item.model_dump() for item in unquoted],
        "audit_log": _append_audit(state, "resolve_price_components", message),
    }


def quote_items(state: FlexibleQuoteState) -> FlexibleQuoteState:
    _report_progress(state, "quote_items", "running", "Calculating quote lines.")
    components_by_key = {(item["product"], item["region"]): PriceComponent.model_validate(item) for item in state.get("price_components", [])}
    lines: list[dict[str, Any]] = []
    for raw_item in state.get("quote_ready_items", []):
        requirement = RequirementItem.model_validate(raw_item)
        key = (requirement.normalized_product, requirement.region)
        component = components_by_key.get(key)
        if not component or requirement.quantity is None or component.price is None or not requirement.normalized_product or not requirement.region:
            continue
        assumption = "Quoted strictly from locally confirmed pricing cache."
        if requirement.quantity_source == "inferred_unit_price":
            assumption = (
                "Quantity inferred as 1 for unit price comparison; quoted value is a reference unit price, "
                "not a committed purchase total."
            )
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
    assumptions = [
        "Flexible quote uses only the local confirmed pricing catalog.",
        "RVTools and flexible quote flows remain fully separate.",
    ]
    if inferred_count:
        assumptions.append(
            f"{inferred_count} item(s) use quantity=1 inferred for unit price comparison; these are reference unit prices, not committed purchase quantities."
        )
    summary = FlexibleQuoteSummary(
        total_input_items=len(state.get("requirements", [])),
        quote_ready_items=len(state.get("quote_ready_items", [])),
        quoted_items=len(lines),
        blocker_count=len(state.get("quote_blockers", [])),
        unquoted_count=len(state.get("unquoted_items", [])),
        total_monthly_price=round(sum(item.monthly_price for item in lines), 2),
        summary=(
            f"Quoted {len(lines)} item(s), found {len(state.get('quote_blockers', []))} blocker(s), "
            f"and left {len(state.get('unquoted_items', []))} item(s) awaiting price confirmation."
        ),
        assumptions=assumptions,
        risks=[
            "Items without confirmed local pricing are returned as unquoted.",
            "Spec matching is deterministic and may require manual refinement for ambiguous rows.",
        ],
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


def export_flexible_workbook(state: FlexibleQuoteState) -> FlexibleQuoteState:
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
