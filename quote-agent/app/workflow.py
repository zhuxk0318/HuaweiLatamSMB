from __future__ import annotations

from copy import copy
import os
import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from openpyxl import load_workbook

from app.models import (
    EvsTypeKey,
    NormalizedVM,
    QuoteLine,
    QuotePreviewResponse,
    QuoteRequest,
    QuoteSummary,
    QuoteWorkbook,
    SheetSelection,
)
from app.pricebook import load_pricebook, pick_ecs_match
from app.rvtools import parse_rvtools_workbook

HOURS_PER_MONTH = 730
TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "rvtools_quote_template.xlsx"

TEMPLATE_SHEET_ORDER = ["Summary", "HWC", "ECS", "Información"]
ECS_DATA_START_ROW = 3
ECS_TOTAL_ROW = 21
ECS_TEMPLATE_ROW = 20
HWC_STORAGE_ROW = 2
HWC_STORAGE_TOTAL_ROW = 3
HWC_NETWORK_HEADER_ROW = 7
HWC_NETWORK_ROW = 8
HWC_NETWORK_TOTAL_ROW = 9

# ── LLM classification constants (Phase 2B) ──────────────────────────────────────

_LLM_CLASSIFY_MAX_ROWS = 80
_LLM_CLASSIFY_SKIP_VM_COUNT = 20
_LLM_CLASSIFY_TIMEOUT_SECONDS = 5
_MAAS_SUMMARY_SKIP_LINE_COUNT = 20
_MAAS_SUMMARY_TIMEOUT_SECONDS = 5

_VALID_WORKLOAD_CATEGORIES = frozenset({
    "sap_hana_db", "sap_app", "sql_db", "oracle_db", "sybase_db",
    "windows_app", "linux_app", "unknown",
})
_VALID_STORAGE_CLASS_HINTS = frozenset({
    "ultra-high-io", "general-purpose-ssd", "manual_review",
})
_VALID_LICENSE_HINTS = frozenset({
    "windows", "suse_linux", "red_hat_linux", "ubuntu_linux",
    "centos_linux", "linux", "sql_server", "oracle", "unknown",
})
_VALID_ECS_FAMILY_HINTS = frozenset({
    "memory_optimized", "general_purpose", "compute_optimized", "high_io", "unknown",
})

_LLM_CLASSIFY_SYSTEM_PROMPT = (
    "You are a VM workload classifier for Huawei Cloud migration quotes.\n"
    "Return JSON only. Do NOT produce prices. Do NOT modify CPU, memory, or storage values.\n"
    "Do NOT invent products. Only classify workload and hints.\n"
    "Keep existing local classification unless there is strong evidence to change it.\n"
    "Output schema:\n"
    '{"rows": [{"row_index": int, "workload_category": str, "storage_class_hint": str, '
    '"license_hint": str, "ecs_family_hint": str, "classification_confidence": float, '
    '"classification_rationale": str, "review_flags": [str]}]}\n'
    "Allowed workload_category values: sap_hana_db, sap_app, sql_db, oracle_db, sybase_db, "
    "windows_app, linux_app, unknown\n"
    "Allowed storage_class_hint values: ultra-high-io, general-purpose-ssd, manual_review\n"
    "Allowed license_hint values: windows, suse_linux, red_hat_linux, ubuntu_linux, "
    "centos_linux, linux, sql_server, oracle, unknown\n"
    "Allowed ecs_family_hint values: memory_optimized, general_purpose, compute_optimized, "
    "high_io, unknown\n"
    "classification_confidence must be between 0 and 1.\n"
    "review_flags must be an array of strings."
)


class QuoteState(TypedDict, total=False):
    request: QuoteRequest
    file_bytes: bytes
    sheet_selection: SheetSelection
    parsed_vms: list[dict[str, Any]]
    normalized_vms: list[dict[str, Any]]
    quote_lines: list[dict[str, Any]]
    summary: dict[str, Any]
    workbook: QuoteWorkbook
    pricebook: dict[str, Any]
    raw_vinfo: list[dict[str, Any]]
    raw_vdisk: list[dict[str, Any]]
    # Phase 6 multi-file fields
    files: list[dict[str, Any]]  # [{"filename": str, "content": bytes}, ...]
    source_filenames: list[str]


def _request_model(state: QuoteState) -> QuoteRequest:
    return QuoteRequest.model_validate(state["request"])


def parse_rvtools(state: QuoteState) -> QuoteState:
    sheet_selection = state.get("sheet_selection") or SheetSelection()
    parsed, raw_vinfo, raw_vdisk = parse_rvtools_workbook(state["file_bytes"], sheet_selection=sheet_selection)
    return {
        "parsed_vms": [item.model_dump() for item in parsed],
        "raw_vinfo": raw_vinfo,
        "raw_vdisk": raw_vdisk,
    }


def parse_rvtools_multi(state: QuoteState) -> QuoteState:
    """Parse multiple RVTools/inventory files and merge results.
    Each file is parsed independently; results are concatenated.
    The source_filename from each file is tagged onto its parsed VMs.
    """
    sheet_selection = state.get("sheet_selection") or SheetSelection()
    files = state.get("files", [])

    if not files:
        # Fallback to single-file mode
        return parse_rvtools(state)

    all_parsed: list[dict[str, Any]] = []
    all_raw_vinfo: list[dict[str, Any]] = []
    all_raw_vdisk: list[dict[str, Any]] = []
    source_filenames: list[str] = []

    for file_entry in files:
        filename = file_entry.get("filename", "unknown.xlsx")
        content = file_entry.get("content", b"")
        source_filenames.append(filename)

        parsed, raw_vinfo, raw_vdisk = parse_rvtools_workbook(content, sheet_selection=sheet_selection)

        # Tag each parsed VM with its source filename
        for item in parsed:
            item_dict = item.model_dump()
            if not item_dict.get("source_dc"):
                # Derive DC label from filename if not already set
                # e.g. "SAPCloud_RVTools_export_all_2026-03-30_AMU.xlsx" → "AMU"
                base = filename.rsplit(".", 1)[0]  # strip extension
                parts = base.split("_")
                # Take last meaningful segment (often AMU, CDLV, etc.)
                dc_hint = parts[-1] if parts else base
                item_dict["source_dc"] = dc_hint
            all_parsed.append(item_dict)

        # Tag raw rows with source filename
        for row in raw_vinfo:
            row["_source_filename"] = filename
        for row in raw_vdisk:
            row["_source_filename"] = filename

        all_raw_vinfo.extend(raw_vinfo)
        all_raw_vdisk.extend(raw_vdisk)

    return {
        "parsed_vms": all_parsed,
        "raw_vinfo": all_raw_vinfo,
        "raw_vdisk": all_raw_vdisk,
        "source_filenames": source_filenames,
    }


def _classify_vm_locally(item: dict[str, Any]) -> dict[str, Any]:
    """Deterministic local classification based on VM attributes.
    Returns a dict of classification fields to merge into the item.
    Does NOT call LLM.
    """
    vm_name = str(item.get("vm_name", "")).strip().lower()
    os_str = str(item.get("os", "")).strip().lower()
    workload_type = str(item.get("workload_type", "") or "").strip().lower()
    memory_gib = float(item.get("memory_gib", 0))
    disk_gib = float(item.get("disk_gib", 0))

    combined = f"{vm_name} {workload_type}"

    # ── workload_category ────────────────────────────────────────────────
    # Order matters: specific DB types before generic SAP
    if any(kw in combined for kw in ("hana", "bd hana")):
        workload_category = "sap_hana_db"
    elif any(kw in combined for kw in ("sql server", "mssql", "ms sql")):
        workload_category = "sql_db"
    elif "oracle" in combined:
        workload_category = "oracle_db"
    elif "sybase" in combined:
        workload_category = "sybase_db"
    elif "sap" in combined:
        workload_category = "sap_app"
    else:
        workload_category = "unknown"

    # ── storage_class_hint ───────────────────────────────────────────────
    if workload_category in ("sap_hana_db", "sql_db", "oracle_db", "sybase_db"):
        storage_class_hint = "ultra-high-io"
    elif workload_category == "sap_app":
        storage_class_hint = "general-purpose-ssd"
    else:
        # unknown: infer from resource scale
        if memory_gib >= 128 and disk_gib >= 500:
            storage_class_hint = "ultra-high-io"
        else:
            storage_class_hint = "general-purpose-ssd"

    # ── license_hint ─────────────────────────────────────────────────────
    if "windows" in os_str:
        license_hint = "windows"
    elif "suse" in os_str:
        license_hint = "suse_linux"
    elif "red hat" in os_str or "rhel" in os_str:
        license_hint = "red_hat_linux"
    elif "ubuntu" in os_str:
        license_hint = "ubuntu_linux"
    elif "centos" in os_str:
        license_hint = "centos_linux"
    elif "linux" in os_str:
        license_hint = "linux"
    else:
        license_hint = "unknown"

    # ── ecs_family_hint ──────────────────────────────────────────────────
    if workload_category == "sap_hana_db" or memory_gib >= 128:
        ecs_family_hint = "memory_optimized"
    else:
        ecs_family_hint = "general_purpose"

    # ── classification_confidence / rationale ────────────────────────────
    if workload_category != "unknown":
        classification_confidence = 0.8
    elif memory_gib >= 128 and disk_gib >= 500:
        classification_confidence = 0.55
    else:
        classification_confidence = 0.4

    # Build rationale
    rationale_parts: list[str] = []
    if workload_category == "sap_hana_db":
        rationale_parts.append("Matched HANA workload from Tipo SAP / VM name.")
    elif workload_category == "sql_db":
        rationale_parts.append("Matched SQL Server workload from Tipo SAP / VM name.")
    elif workload_category == "oracle_db":
        rationale_parts.append("Matched Oracle workload from Tipo SAP / VM name.")
    elif workload_category == "sybase_db":
        rationale_parts.append("Matched Sybase workload from Tipo SAP / VM name.")
    elif workload_category == "sap_app":
        rationale_parts.append("Matched SAP application workload from Tipo SAP / VM name.")
    else:
        if memory_gib >= 128 and disk_gib >= 500:
            rationale_parts.append("Large memory+storage VM, possible database workload.")
        else:
            rationale_parts.append("No workload type matched.")

    if license_hint != "unknown":
        rationale_parts.append(f"Detected {license_hint} OS.")

    classification_rationale = " ".join(rationale_parts)

    # ── review_flags ─────────────────────────────────────────────────────
    review_flags: list[str] = []
    if workload_category == "sap_hana_db":
        review_flags.append("hana_storage_class_review")
    elif workload_category in ("sql_db", "oracle_db", "sybase_db"):
        review_flags.append("database_storage_class_review")
    elif workload_category == "unknown":
        review_flags.append("workload_unclassified")

    if license_hint == "windows":
        review_flags.append("windows_license_review")

    return {
        "workload_category": workload_category,
        "storage_class_hint": storage_class_hint,
        "license_hint": license_hint,
        "ecs_family_hint": ecs_family_hint,
        "classification_confidence": classification_confidence,
        "classification_rationale": classification_rationale,
        "review_flags": review_flags,
    }


def normalize_inventory(state: QuoteState) -> QuoteState:
    normalized: list[dict[str, Any]] = []
    for item in state["parsed_vms"]:
        power_state = str(item.get("power_state", "")).strip().lower()
        if power_state and power_state not in {"poweredon", "powered on", "on"}:
            action = "exclude_powered_off"
            review_reason = "VM is not powered on in RVTools."
        elif int(item["vcpu"]) <= 0 or float(item["memory_gib"]) <= 0:
            action = "manual_review"
            review_reason = "Missing CPU or memory values."
        elif float(item["disk_gib"]) <= 0:
            action = "manual_review"
            review_reason = "No disk capacity found in vDisk."
        else:
            action = "quote"
            review_reason = None

        # Apply local deterministic classification
        classification = _classify_vm_locally(item)
        merged = {**item, **classification}

        normalized.append(
            NormalizedVM(
                **merged,
                action=action,
                review_reason=review_reason,
            ).model_dump()
        )
    return {"normalized_vms": normalized}


def _build_llm_classify_payload(normalized_vms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build the minimal row payload to send to LLM for classification."""
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(normalized_vms[:_LLM_CLASSIFY_MAX_ROWS]):
        rows.append({
            "row_index": idx,
            "vm_name": item.get("vm_name", ""),
            "customer": item.get("customer"),
            "workload_type": item.get("workload_type"),
            "os": item.get("os", ""),
            "vcpu": item.get("vcpu", 0),
            "memory_gib": item.get("memory_gib", 0),
            "disk_gib": item.get("disk_gib", 0),
            # Phase 2A local classification for LLM context
            "workload_category": item.get("workload_category"),
            "storage_class_hint": item.get("storage_class_hint"),
            "license_hint": item.get("license_hint"),
            "ecs_family_hint": item.get("ecs_family_hint"),
            "classification_confidence": item.get("classification_confidence"),
            "classification_rationale": item.get("classification_rationale"),
            "review_flags": item.get("review_flags", []),
        })
    return rows


def _validate_llm_classification_row(
    row: dict[str, Any],
    total_rows: int,
) -> dict[str, Any]:
    """Validate and sanitize a single LLM classification row.
    Returns only fields that pass validation; unknown fields are dropped.
    Invalid enum values are dropped (not applied).
    """
    result: dict[str, Any] = {}

    row_index = row.get("row_index")
    if not isinstance(row_index, int) or row_index < 0 or row_index >= total_rows:
        return result  # invalid index → skip entire row
    result["row_index"] = row_index

    # Enum fields — only accept if value is in the allowed set
    if row.get("workload_category") in _VALID_WORKLOAD_CATEGORIES:
        result["workload_category"] = row["workload_category"]
    if row.get("storage_class_hint") in _VALID_STORAGE_CLASS_HINTS:
        result["storage_class_hint"] = row["storage_class_hint"]
    if row.get("license_hint") in _VALID_LICENSE_HINTS:
        result["license_hint"] = row["license_hint"]
    if row.get("ecs_family_hint") in _VALID_ECS_FAMILY_HINTS:
        result["ecs_family_hint"] = row["ecs_family_hint"]

    # classification_confidence — clamp to [0, 1]
    conf = row.get("classification_confidence")
    if isinstance(conf, (int, float)):
        result["classification_confidence"] = max(0.0, min(1.0, float(conf)))

    # classification_rationale — must be a non-empty string
    rationale = row.get("classification_rationale")
    if isinstance(rationale, str) and rationale.strip():
        result["classification_rationale"] = rationale.strip()

    # review_flags — must be a list of strings
    flags = row.get("review_flags")
    if isinstance(flags, list):
        result["review_flags"] = [f for f in flags if isinstance(f, str)]

    return result


def _merge_llm_classification(
    local: dict[str, Any],
    llm: dict[str, Any],
) -> dict[str, Any]:
    """Merge LLM classification into local classification.
    LLM valid fields override local. review_flags are merged/deduped.
    classification_confidence: LLM overrides only if >= local.
    classification_rationale: LLM replaces local (prefixed with 'LLM:').
    """
    merged = dict(local)

    # Simple override fields
    for field in ("workload_category", "storage_class_hint", "license_hint", "ecs_family_hint"):
        if field in llm:
            merged[field] = llm[field]

    # classification_confidence: LLM overrides only if >= local
    if "classification_confidence" in llm:
        local_conf = local.get("classification_confidence") or 0
        if llm["classification_confidence"] >= local_conf:
            merged["classification_confidence"] = llm["classification_confidence"]

    # classification_rationale: replace with LLM rationale, prefixed
    if "classification_rationale" in llm:
        merged["classification_rationale"] = f"LLM: {llm['classification_rationale']}"

    # review_flags: merge and dedupe
    if "review_flags" in llm:
        local_flags = set(local.get("review_flags") or [])
        llm_flags = set(llm["review_flags"])
        merged["review_flags"] = sorted(local_flags | llm_flags)

    return merged


def classify_inventory_context(state: QuoteState) -> QuoteState:
    """LLM-enhanced classification node (Phase 2B).
    Calls MaaS to refine Phase 2A local classification.
    Only modifies classification fields — never touches CPU/memory/storage/action/prices.
    Falls back to local classification on any failure.
    """
    normalized_vms = state.get("normalized_vms", [])
    if not normalized_vms:
        return {}
    if len(normalized_vms) > _LLM_CLASSIFY_SKIP_VM_COUNT:
        return {}

    # Check MaaS configuration
    api_key = os.getenv("HUAWEI_MAAS_API_KEY")
    base_url = os.getenv("HUAWEI_MAAS_BASE_URL")
    model = os.getenv("HUAWEI_MAAS_MODEL")
    if not api_key or not base_url or not model:
        return {}  # no MaaS → keep local classification unchanged

    # Build minimal payload for LLM
    rows_payload = _build_llm_classify_payload(normalized_vms)
    if not rows_payload:
        return {}

    try:
        with httpx.Client(timeout=_LLM_CLASSIFY_TIMEOUT_SECONDS) as client:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _LLM_CLASSIFY_SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps({"rows": rows_payload})},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            parsed = json.loads(content)
    except Exception:
        return {}  # any failure → fallback to local classification

    # Validate LLM output structure
    llm_rows = parsed.get("rows")
    if not isinstance(llm_rows, list):
        return {}

    # Build index of validated LLM results by row_index
    total_rows = len(normalized_vms)
    llm_by_index: dict[int, dict[str, Any]] = {}
    for row in llm_rows:
        if not isinstance(row, dict):
            continue
        validated = _validate_llm_classification_row(row, total_rows)
        if "row_index" in validated:
            llm_by_index[validated.pop("row_index")] = validated

    if not llm_by_index:
        return {}  # no valid rows → fallback

    # Merge LLM classification into normalized_vms
    updated_vms: list[dict[str, Any]] = []
    for idx, item in enumerate(normalized_vms):
        if idx in llm_by_index:
            updated_vms.append(_merge_llm_classification(item, llm_by_index[idx]))
        else:
            updated_vms.append(item)

    return {"normalized_vms": updated_vms}


def load_pricebook_node(_: QuoteState) -> QuoteState:
    return {"pricebook": load_pricebook()}


def _evs_monthly(region_catalog: dict[str, Any], evs_type: EvsTypeKey, disk_gib: float) -> float:
    evs_item = next(item for item in region_catalog["evs"] if item["key"] == evs_type)
    return round(float(disk_gib) * float(evs_item["monthlyEquivalentUsdPerGb"]), 4)


# ── Phase 8C: per-VM ECS/EVS selection helpers ──────────────────────────────────

_EVS_TYPE_LABELS: dict[str, str] = {
    "ultra-high-io": "Ultra High I/O",
    "high-io": "High I/O",
    "gpssd": "General Purpose SSD",
    "sas": "High I/O",
}


def _resolve_evs_type_for_vm(item: dict[str, Any]) -> str:
    """Resolve the EVS type key for a single VM based on its workload category.

    Rules:
        - DB workloads (sap_hana_db, sql_db, oracle_db, sybase_db) → ultra-high-io
        - SAP app → high-io
        - All others → high-io (default for migrated VMs)
    """
    workload_category = item.get("workload_category", "unknown") or "unknown"
    db_categories = {"sap_hana_db", "sql_db", "oracle_db", "sybase_db"}
    if workload_category in db_categories:
        return "ultra-high-io"
    return "high-io"


def _resolve_family_policy_for_vm(item: dict[str, Any]) -> str:
    """Resolve the ECS family policy for a single VM based on its workload category.

    Rules:
        - sap_hana_db → sap_hana_db (M-series first)
        - sql_db / oracle_db / sybase_db → sap_db (C-series first)
        - sap_app → sap_app (S-series first)
        - All others → default
    """
    workload_category = item.get("workload_category", "unknown") or "unknown"
    if workload_category == "sap_hana_db":
        return "sap_hana_db"
    if workload_category in ("sql_db", "oracle_db", "sybase_db"):
        return "sap_db"
    if workload_category == "sap_app":
        return "sap_app"
    return "default"


def quote_inventory(state: QuoteState) -> QuoteState:
    request = _request_model(state)
    region_catalog = state["pricebook"]["pricingCatalog"][request.region]
    lines: list[dict[str, Any]] = []

    for item in state["normalized_vms"]:
        # Phase 8C: per-VM EVS type and ECS family policy
        evs_selected_type = _resolve_evs_type_for_vm(item)
        evs_selected_label = _EVS_TYPE_LABELS.get(evs_selected_type, evs_selected_type)
        family_policy = _resolve_family_policy_for_vm(item)

        evs_monthly = _evs_monthly(region_catalog, evs_selected_type, float(item["disk_gib"]))
        if item["action"] != "quote":
            lines.append(
                QuoteLine(
                    **item,
                    region=request.region,
                    evs_type=request.evs_type,
                    evs_monthly_usd=evs_monthly,
                    evs_selected_type=evs_selected_type,
                    evs_selected_label=evs_selected_label,
                    ecs_family_policy=family_policy,
                ).model_dump()
            )
            continue

        match = pick_ecs_match(
            region_catalog,
            int(item["vcpu"]),
            float(item["memory_gib"]),
            strategy="nearest",
            family_policy=family_policy,
        )
        if not match:
            item = {
                **item,
                "action": "manual_review",
                "review_reason": "No ECS spec matched the requested CPU/memory shape by nearest match.",
            }
            lines.append(
                QuoteLine(
                    **item,
                    region=request.region,
                    evs_type=request.evs_type,
                    evs_monthly_usd=evs_monthly,
                    evs_selected_type=evs_selected_type,
                    evs_selected_label=evs_selected_label,
                    ecs_family_policy=family_policy,
                ).model_dump()
            )
            continue

        ondemand = round(float(match["hourlyUsd"]) * HOURS_PER_MONTH, 4)
        ri = round(float(match["ri1YearMonthlyUsd"]), 4)
        lines.append(
            QuoteLine(
                **item,
                region=request.region,
                evs_type=request.evs_type,
                ecs_category=match["category"],
                ecs_family_label=match["familyLabel"],
                ecs_spec=match["spec"],
                ecs_vcpu=int(match["vcpu"]),
                ecs_mem=float(match["memoryGiB"]),
                ecs_ondemand_monthly_usd=ondemand,
                ecs_ri_1y_monthly_usd=ri,
                evs_monthly_usd=evs_monthly,
                total_ondemand_monthly_usd=round(ondemand + evs_monthly, 4),
                total_ri_1y_monthly_usd=round(ri + evs_monthly, 4),
                evs_selected_type=evs_selected_type,
                evs_selected_label=evs_selected_label,
                ecs_family_policy=family_policy,
            ).model_dump()
        )

    return {"quote_lines": lines}


def _fallback_summary(state: QuoteState) -> QuoteSummary:
    quote_lines = [QuoteLine.model_validate(item) for item in state["quote_lines"]]
    total_vms = len(quote_lines)
    excluded = [item for item in quote_lines if item.action == "exclude_powered_off"]
    manual = [item for item in quote_lines if item.action == "manual_review"]
    quoted = [item for item in quote_lines if item.action == "quote"]
    total_disk = round(sum(item.disk_gib for item in quote_lines), 2)
    ondemand = round(sum(item.total_ondemand_monthly_usd for item in quoted), 2)
    ri = round(sum(item.total_ri_1y_monthly_usd for item in quoted), 2)

    return QuoteSummary(
        total_vms=total_vms,
        excluded_vms=len(excluded),
        manual_review_vms=len(manual),
        quoted_vms=len(quoted),
        total_disk_gib=total_disk,
        total_ondemand_monthly_usd=ondemand,
        total_ri_1y_monthly_usd=ri,
        summary=(
            f"Quoted {len(quoted)} of {total_vms} VMs for {_request_model(state).region}. "
            f"Excluded {len(excluded)} powered-off VMs and flagged {len(manual)} VM(s) for manual review."
        ),
        assumptions=[
            "Pricing uses the exported local Huawei Cloud pricebook JSON generated from pricingCatalog.ts.",
            "Only ECS and EVS are included in V1. CBR, licenses, discounts, and right-sizing are excluded.",
            "CBR is shown as a placeholder in this phase and is not included as a paid service unless configured.",
        ],
        risks=[
            "Manual review lines need follow-up before commercial use.",
            "RI values assume the cached 1-year monthly price stored in the pricebook export.",
        ],
    )


def _maas_summary(request: QuoteRequest, summary: QuoteSummary, quote_lines: list[dict[str, Any]]) -> QuoteSummary:
    api_key = os.getenv("HUAWEI_MAAS_API_KEY")
    base_url = os.getenv("HUAWEI_MAAS_BASE_URL")
    model = os.getenv("HUAWEI_MAAS_MODEL")
    if not api_key or not base_url or not model:
        return summary
    if len(quote_lines) > _MAAS_SUMMARY_SKIP_LINE_COUNT:
        return summary

    prompt = {
        "region": request.region,
        "language": request.lang,
        "quoted_vms": summary.quoted_vms,
        "manual_review_vms": summary.manual_review_vms,
        "excluded_vms": summary.excluded_vms,
        "total_ondemand_monthly_usd": summary.total_ondemand_monthly_usd,
        "total_ri_1y_monthly_usd": summary.total_ri_1y_monthly_usd,
        "top_quote_lines": quote_lines[:10],
    }
    try:
        with httpx.Client(timeout=_MAAS_SUMMARY_TIMEOUT_SECONDS) as client:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Return JSON with summary, assumptions, risks. Keep it concise and executive level."
                            ),
                        },
                        {"role": "user", "content": str(prompt)},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return summary.model_copy(
                update={
                    "summary": parsed.get("summary", summary.summary),
                    "assumptions": parsed.get("assumptions", summary.assumptions),
                    "risks": parsed.get("risks", summary.risks),
                }
            )
    except Exception:
        return summary


def summarize_quote(state: QuoteState) -> QuoteState:
    summary = _fallback_summary(state)
    enriched = _maas_summary(_request_model(state), summary, state["quote_lines"])
    return {"summary": enriched.model_dump()}


def build_preview_response(state: QuoteState) -> QuotePreviewResponse:
    request = _request_model(state)
    lines = [QuoteLine.model_validate(item) for item in state["quote_lines"]]
    return QuotePreviewResponse(
        source_filename=request.source_filename,
        region=request.region,
        evs_type=request.evs_type,
        lang=request.lang,
        summary=QuoteSummary.model_validate(state["summary"]),
        quote_lines=[item for item in lines if item.action == "quote"],
        manual_review_lines=[item for item in lines if item.action == "manual_review"],
        excluded_lines=[item for item in lines if item.action == "exclude_powered_off"],
    )


# ── Phase 3 export helpers ────────────────────────────────────────────────────────


def _blank_none(value: Any) -> Any:
    """Replace None with empty string for Excel output. Pass other values through."""
    if value is None:
        return ""
    return value


def _storage_type_label(hint: str | None) -> str:
    """Map storage_class_hint to human-readable label for export."""
    mapping = {
        "ultra-high-io": "Ultra High I/O",
        "general-purpose-ssd": "general purpose ssd",
    }
    if hint in mapping:
        return mapping[hint]
    return hint or ""


def _copy_row_style(ws: Any, src_row: int, dst_row: int, max_col: int) -> None:
    """Clone row styles from one row to another."""
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


def _clear_row_values(ws: Any, row: int, max_col: int) -> None:
    for col in range(1, max_col + 1):
        ws.cell(row, col).value = None


def _safe_number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_text(value: Any) -> str:
    return "" if value in (None, "") else str(value)


def _format_disk_label(value: Any) -> str:
    if value in (None, ""):
        return ""
    number = _safe_number(value)
    if number.is_integer():
        return f"{int(number)} GiB"
    return f"{round(number, 2)} GiB"


def _template_title(source_filenames: list[str] | None, source_filename: str) -> str:
    filenames = [name for name in (source_filenames or []) if name]
    if not filenames:
        return source_filename
    if len(filenames) == 1:
        return filenames[0]
    first = filenames[0]
    return f"{first} + {len(filenames) - 1} more"


# ── Phase 4 DC grouping helpers ───────────────────────────────────────────────────


def _dc_label(line: dict[str, Any]) -> str:
    """Derive a DC label from a quote line dict.
    Priority: source_dc → source_sheet → Default.
    Preserves original casing (e.g. AMU, CDLV).
    """
    dc = line.get("source_dc")
    if isinstance(dc, str) and dc.strip():
        return dc.strip()
    sheet = line.get("source_sheet")
    if isinstance(sheet, str) and sheet.strip():
        return sheet.strip()
    return "Default"


def _group_quote_lines_by_dc(lines: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group all quote lines by DC label, preserving first-occurrence order."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in lines:
        dc = _dc_label(item)
        if dc not in groups:
            groups[dc] = []
        groups[dc].append(item)
    return groups


def _build_ecs_export_rows(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build ECS sheet rows from quote lines.
    Includes all lines (quote, manual_review, exclude_powered_off).
    """
    rows: list[dict[str, Any]] = []
    for item in lines:
        # Phase 8D: use evs_selected_label if available, otherwise fall back to storage_class_hint
        evs_label = item.get("evs_selected_label") or _storage_type_label(item.get("storage_class_hint"))
        rows.append({
            "Origen/DC": _dc_label(item),
            "VM": _blank_none(item.get("vm_name")),
            "Cliente": _blank_none(item.get("customer")),
            "Tipo SAP": _blank_none(item.get("workload_type")),
            "CPUs": _blank_none(item.get("vcpu")),
            "Memory": _blank_none(item.get("raw_memory_mb")),
            "Memory GB": _blank_none(item.get("memory_gib")),
            "Total disk capacity MiB": _blank_none(item.get("raw_storage_mib")),
            "Total disk capacity GiB": _blank_none(item.get("disk_gib")),
            "OS according to the configuration file": _blank_none(item.get("os")),
            # Classification columns
            "workload_category": _blank_none(item.get("workload_category")),
            "storage_class_hint": _blank_none(item.get("storage_class_hint")),
            "license_hint": _blank_none(item.get("license_hint")),
            "ecs_family_hint": _blank_none(item.get("ecs_family_hint")),
            "review_flags": "|".join(item.get("review_flags") or []) if item.get("review_flags") else "",
            # Huawei Cloud quote columns
            "HC Flavor": _blank_none(item.get("ecs_spec")),
            "HC vCPU": _blank_none(item.get("ecs_vcpu")),
            "HC Memory": _blank_none(item.get("ecs_mem")),
            "Storage(GB)": _blank_none(item.get("disk_gib")),
            "Tipo Storage": evs_label,
            "Precio Storage": _blank_none(item.get("evs_monthly_usd")),
            "Backup (CBR)": 0,
            "ECS On Demand /mes (USD)": _blank_none(item.get("ecs_ondemand_monthly_usd")),
            "ECS RI 1 año /mes (USD)": _blank_none(item.get("ecs_ri_1y_monthly_usd")),
            "ECS RI 3 años /mes (USD)": "",
            "Total On Demand": _blank_none(item.get("total_ondemand_monthly_usd")),
            "Total RI 1Y": _blank_none(item.get("total_ri_1y_monthly_usd")),
            "Total RI 3Y": "",
            "Action": _blank_none(item.get("action")),
            "Review Reason": _blank_none(item.get("review_reason")),
        })
    return rows


def _build_hwc_rows(
    lines: list[dict[str, Any]],
    request: QuoteRequest,
    pricebook: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build HWC sheet rows: EVS and CBR summary grouped by DC.
    Phase 8D: uses evs_selected_type instead of storage_class_hint for grouping.
    """
    dc_groups = _group_quote_lines_by_dc(lines)
    rows: list[dict[str, Any]] = []

    # Derive unit prices from pricebook if available
    gpssd_unit_price: float = 0.0
    high_io_unit_price: float = 0.0
    ultra_unit_price: float = 0.0
    try:
        region_catalog = pricebook["pricingCatalog"][request.region]
        for evs_item in region_catalog["evs"]:
            if evs_item["key"] == "gpssd":
                gpssd_unit_price = float(evs_item["monthlyEquivalentUsdPerGb"])
            if evs_item["key"] in ("high-io", "sas"):
                high_io_unit_price = float(evs_item["monthlyEquivalentUsdPerGb"])
            if evs_item["key"] in ("uhio", "uh-i", "ultra-high-io"):
                ultra_unit_price = float(evs_item["monthlyEquivalentUsdPerGb"])
    except (KeyError, StopIteration):
        pass

    # Per-DC rows
    for dc, dc_lines in dc_groups.items():
        quoted = [item for item in dc_lines if item.get("action") == "quote"]

        # Phase 8D: group by evs_selected_type
        gpssd_lines = [item for item in quoted if item.get("evs_selected_type") == "gpssd"]
        high_io_lines = [item for item in quoted if item.get("evs_selected_type") == "high-io"]
        ultra_lines = [item for item in quoted if item.get("evs_selected_type") == "ultra-high-io"]

        gpssd_qty = round(sum(item.get("disk_gib", 0) for item in gpssd_lines), 2)
        high_io_qty = round(sum(item.get("disk_gib", 0) for item in high_io_lines), 2)
        ultra_qty = round(sum(item.get("disk_gib", 0) for item in ultra_lines), 2)
        gpssd_total = round(sum(item.get("evs_monthly_usd", 0) for item in gpssd_lines), 4)
        high_io_total = round(sum(item.get("evs_monthly_usd", 0) for item in high_io_lines), 4)
        ultra_total = round(sum(item.get("evs_monthly_usd", 0) for item in ultra_lines), 4)

        # Unit price: pricebook first, then line-average fallback
        dc_gpssd_price = gpssd_unit_price
        if dc_gpssd_price == 0.0 and gpssd_qty > 0:
            dc_gpssd_price = round(gpssd_total / gpssd_qty, 6)
        dc_high_io_price = high_io_unit_price
        if dc_high_io_price == 0.0 and high_io_qty > 0:
            dc_high_io_price = round(high_io_total / high_io_qty, 6)
        dc_ultra_price = ultra_unit_price
        if dc_ultra_price == 0.0 and ultra_qty > 0:
            dc_ultra_price = round(ultra_total / ultra_qty, 6)

        evs_total = round(gpssd_total + high_io_total + ultra_total, 4)
        dc_disk_total = round(gpssd_qty + high_io_qty + ultra_qty, 2)

        rows.append({
            "DC": dc,
            "Huawei Cloud Resource": "Elastic Volume Service (EVS)",
            "Storage Class": "General Purpose SSD",
            "Quantity": gpssd_qty,
            "Unit": "GB",
            "Unit Price": dc_gpssd_price,
            "Total Monthly": gpssd_total,
        })
        rows.append({
            "DC": dc,
            "Huawei Cloud Resource": "Elastic Volume Service (EVS)",
            "Storage Class": "High I/O",
            "Quantity": high_io_qty,
            "Unit": "GB",
            "Unit Price": dc_high_io_price,
            "Total Monthly": high_io_total,
        })
        rows.append({
            "DC": dc,
            "Huawei Cloud Resource": "Elastic Volume Service (EVS)",
            "Storage Class": "Ultra High I/O",
            "Quantity": ultra_qty,
            "Unit": "GB",
            "Unit Price": dc_ultra_price,
            "Total Monthly": ultra_total,
        })
        rows.append({
            "DC": dc,
            "Huawei Cloud Resource": "EVS Total",
            "Storage Class": "",
            "Quantity": dc_disk_total,
            "Unit": "GB",
            "Unit Price": "",
            "Total Monthly": evs_total,
        })
        rows.append({
            "DC": dc,
            "Huawei Cloud Resource": "Cloud Backup and Recovery (CBR)",
            "Storage Class": "",
            "Quantity": dc_disk_total,
            "Unit": "GB",
            "Unit Price": 0,
            "Total Monthly": 0,
        })
        rows.append({
            "DC": dc,
            "Huawei Cloud Resource": "CBR Total",
            "Storage Class": "",
            "Quantity": 0,
            "Unit": "GB",
            "Unit Price": "",
            "Total Monthly": 0,
        })

    # Global ALL totals
    all_quoted = [item for item in lines if item.get("action") == "quote"]
    all_evs_total = round(sum(item.get("evs_monthly_usd", 0) for item in all_quoted), 4)
    all_disk_total = round(sum(item.get("disk_gib", 0) for item in all_quoted), 2)

    rows.append({
        "DC": "ALL",
        "Huawei Cloud Resource": "EVS Total",
        "Storage Class": "",
        "Quantity": all_disk_total,
        "Unit": "GB",
        "Unit Price": "",
        "Total Monthly": all_evs_total,
    })
    rows.append({
        "DC": "ALL",
        "Huawei Cloud Resource": "CBR Total",
        "Storage Class": "",
        "Quantity": 0,
        "Unit": "GB",
        "Unit Price": "",
        "Total Monthly": 0,
    })

    return rows


def _build_summary_rows(
    summary: QuoteSummary,
    lines: list[dict[str, Any]],
    request: QuoteRequest,
    source_filenames: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build Summary sheet rows in Metric/Value column layout with DC-grouped totals."""
    quoted = [item for item in lines if item.get("action") == "quote"]

    ecs_ondemand = round(sum(item.get("ecs_ondemand_monthly_usd", 0) for item in quoted), 2)
    ecs_ri_1y = round(sum(item.get("ecs_ri_1y_monthly_usd", 0) for item in quoted), 2)
    evs_monthly = round(sum(item.get("evs_monthly_usd", 0) for item in quoted), 2)
    grand_ondemand = round(sum(item.get("total_ondemand_monthly_usd", 0) for item in quoted), 2)
    grand_ri_1y = round(sum(item.get("total_ri_1y_monthly_usd", 0) for item in quoted), 2)

    rows: list[dict[str, Any]] = [
        {"Metric": "Source Filename", "Value": request.source_filename},
        {"Metric": "Source File Count", "Value": len(source_filenames) if source_filenames else 1},
        {"Metric": "Source Filenames", "Value": ", ".join(source_filenames) if source_filenames else request.source_filename},
        {"Metric": "Region", "Value": request.region},
        {"Metric": "Generated At UTC", "Value": datetime.now(timezone.utc).isoformat()},
        {"Metric": "Total VMs", "Value": summary.total_vms},
        {"Metric": "Quoted VMs", "Value": summary.quoted_vms},
        {"Metric": "Manual Review VMs", "Value": summary.manual_review_vms},
        {"Metric": "Excluded VMs", "Value": summary.excluded_vms},
        {"Metric": "Total Storage GiB", "Value": summary.total_disk_gib},
        {"Metric": "ECS On Demand Monthly", "Value": ecs_ondemand},
        {"Metric": "ECS RI 1Y Monthly", "Value": ecs_ri_1y},
        {"Metric": "EVS Monthly", "Value": evs_monthly},
        {"Metric": "CBR Monthly", "Value": 0},
        {"Metric": "Grand Total On Demand", "Value": grand_ondemand},
        {"Metric": "Grand Total RI 1Y", "Value": grand_ri_1y},
    ]

    # Per-DC breakdown
    dc_groups = _group_quote_lines_by_dc(lines)
    for dc, dc_lines in dc_groups.items():
        dc_quoted = [item for item in dc_lines if item.get("action") == "quote"]
        dc_manual = [item for item in dc_lines if item.get("action") == "manual_review"]
        dc_excluded = [item for item in dc_lines if item.get("action") == "exclude_powered_off"]

        dc_ecs_ondemand = round(sum(item.get("ecs_ondemand_monthly_usd", 0) for item in dc_quoted), 2)
        dc_ecs_ri_1y = round(sum(item.get("ecs_ri_1y_monthly_usd", 0) for item in dc_quoted), 2)
        dc_evs = round(sum(item.get("evs_monthly_usd", 0) for item in dc_quoted), 2)
        dc_storage = round(sum(item.get("disk_gib", 0) for item in dc_quoted), 2)
        dc_grand_ondemand = round(sum(item.get("total_ondemand_monthly_usd", 0) for item in dc_quoted), 2)
        dc_grand_ri_1y = round(sum(item.get("total_ri_1y_monthly_usd", 0) for item in dc_quoted), 2)

        rows.extend([
            {"Metric": f"{dc} - Total VMs", "Value": len(dc_lines)},
            {"Metric": f"{dc} - Quoted VMs", "Value": len(dc_quoted)},
            {"Metric": f"{dc} - Manual Review VMs", "Value": len(dc_manual)},
            {"Metric": f"{dc} - Excluded VMs", "Value": len(dc_excluded)},
            {"Metric": f"{dc} - Storage GiB", "Value": dc_storage},
            {"Metric": f"{dc} - ECS On Demand Monthly", "Value": dc_ecs_ondemand},
            {"Metric": f"{dc} - ECS RI 1Y Monthly", "Value": dc_ecs_ri_1y},
            {"Metric": f"{dc} - EVS Monthly", "Value": dc_evs},
            {"Metric": f"{dc} - CBR Monthly", "Value": 0},
            {"Metric": f"{dc} - Grand Total On Demand", "Value": dc_grand_ondemand},
            {"Metric": f"{dc} - Grand Total RI 1Y", "Value": dc_grand_ri_1y},
        ])

    rows.append({"Metric": "Assumptions", "Value": " | ".join(summary.assumptions)})
    rows.append({"Metric": "Risks", "Value": " | ".join(summary.risks)})
    return rows


def _populate_template_ecs_sheet(ws: Any, rows: list[dict[str, Any]]) -> None:
    extra_rows = max(0, len(rows) - (ECS_TOTAL_ROW - ECS_DATA_START_ROW))
    if extra_rows:
        ws.insert_rows(ECS_TOTAL_ROW, extra_rows)
        for row_idx in range(ECS_TOTAL_ROW, ECS_TOTAL_ROW + extra_rows):
            _copy_row_style(ws, ECS_TEMPLATE_ROW, row_idx, 14)

    total_row = ECS_TOTAL_ROW + extra_rows
    for row_idx in range(ECS_DATA_START_ROW, total_row):
        _clear_row_values(ws, row_idx, 14)

    for offset, item in enumerate(rows):
        row_idx = ECS_DATA_START_ROW + offset
        ws.cell(row_idx, 1, _safe_text(item.get("VM")))
        ws.cell(row_idx, 2, item.get("CPUs") if item.get("CPUs") not in ("", None) else None)
        ws.cell(row_idx, 3, item.get("Memory GB") if item.get("Memory GB") not in ("", None) else None)
        ws.cell(row_idx, 4, _safe_text(item.get("Tipo SAP")) or _safe_text(item.get("workload_category")) or "x86_64")
        ws.cell(row_idx, 5, _format_disk_label(item.get("Total disk capacity GiB")))
        ws.cell(row_idx, 6, _safe_text(item.get("OS according to the configuration file")))
        ws.cell(row_idx, 7, None)
        ws.cell(row_idx, 8, _safe_text(item.get("HC Flavor")))
        ws.cell(row_idx, 9, item.get("HC vCPU") if item.get("HC vCPU") not in ("", None) else None)
        ws.cell(row_idx, 10, item.get("HC Memory") if item.get("HC Memory") not in ("", None) else None)
        ws.cell(row_idx, 11, _safe_text(item.get("Tipo Storage")))
        storage_cell = ws.cell(row_idx, 12, item.get("Storage(GB)") if item.get("Storage(GB)") not in ("", None) else None)
        storage_cell.number_format = "0.00"
        ws.cell(row_idx, 13, item.get("ECS On Demand /mes (USD)") if item.get("Action") == "quote" else None)
        ws.cell(row_idx, 14, item.get("ECS RI 1 año /mes (USD)") if item.get("Action") == "quote" else None)

    _clear_row_values(ws, total_row, 14)
    ws.cell(total_row, 2, round(sum(_safe_number(item.get("CPUs")) for item in rows), 2))
    ws.cell(total_row, 3, round(sum(_safe_number(item.get("Memory GB")) for item in rows), 2))
    quoted = [item for item in rows if item.get("Action") == "quote"]
    ws.cell(total_row, 9, round(sum(_safe_number(item.get("HC vCPU")) for item in quoted), 2))
    ws.cell(total_row, 10, round(sum(_safe_number(item.get("HC Memory")) for item in quoted), 2))
    total_storage_cell = ws.cell(total_row, 12, round(sum(_safe_number(item.get("Storage(GB)")) for item in quoted), 2))
    total_storage_cell.number_format = "0.00"
    ws.cell(total_row, 13, round(sum(_safe_number(item.get("ECS On Demand /mes (USD)")) for item in quoted), 2))
    ws.cell(total_row, 14, round(sum(_safe_number(item.get("ECS RI 1 año /mes (USD)")) for item in quoted), 2))


def _populate_template_hwc_sheet(ws: Any, lines: list[dict[str, Any]], request: QuoteRequest, pricebook: dict[str, Any]) -> None:
    """Phase 8D: uses evs_selected_type for grouping instead of storage_class_hint."""
    quoted = [item for item in lines if item.get("action") == "quote"]
    gpssd_lines = [item for item in quoted if item.get("evs_selected_type") == "gpssd"]
    high_io_lines = [item for item in quoted if item.get("evs_selected_type") == "high-io"]
    ultra_lines = [item for item in quoted if item.get("evs_selected_type") == "ultra-high-io"]
    gpssd_qty = round(sum(_safe_number(item.get("disk_gib")) for item in gpssd_lines), 2)
    high_io_qty = round(sum(_safe_number(item.get("disk_gib")) for item in high_io_lines), 2)
    ultra_qty = round(sum(_safe_number(item.get("disk_gib")) for item in ultra_lines), 2)
    gpssd_total = round(sum(_safe_number(item.get("evs_monthly_usd")) for item in gpssd_lines), 2)
    high_io_total = round(sum(_safe_number(item.get("evs_monthly_usd")) for item in high_io_lines), 2)
    ultra_total = round(sum(_safe_number(item.get("evs_monthly_usd")) for item in ultra_lines), 2)

    gpssd_unit_price = 0.0
    high_io_unit_price = 0.0
    ultra_unit_price = 0.0
    try:
        region_catalog = pricebook["pricingCatalog"][request.region]
        for evs_item in region_catalog["evs"]:
            if evs_item["key"] == "gpssd":
                gpssd_unit_price = float(evs_item["monthlyEquivalentUsdPerGb"])
            if evs_item["key"] in ("high-io", "sas"):
                high_io_unit_price = float(evs_item["monthlyEquivalentUsdPerGb"])
            if evs_item["key"] in ("uhio", "uh-i", "ultra-high-io"):
                ultra_unit_price = float(evs_item["monthlyEquivalentUsdPerGb"])
    except (KeyError, TypeError, ValueError):
        pass

    if gpssd_unit_price == 0 and gpssd_qty > 0:
        gpssd_unit_price = round(gpssd_total / gpssd_qty, 6)
    if high_io_unit_price == 0 and high_io_qty > 0:
        high_io_unit_price = round(high_io_total / high_io_qty, 6)
    if ultra_unit_price == 0 and ultra_qty > 0:
        ultra_unit_price = round(ultra_total / ultra_qty, 6)

    # Determine how many extra rows we need for High I/O and Ultra High I/O
    extra_storage_rows = 0
    if high_io_qty > 0 or high_io_total > 0:
        extra_storage_rows += 1
    if ultra_qty > 0 or ultra_total > 0:
        extra_storage_rows += 1

    if extra_storage_rows > 0:
        ws.insert_rows(HWC_STORAGE_TOTAL_ROW, extra_storage_rows)
        insert_offset = 0
        if high_io_qty > 0 or high_io_total > 0:
            _copy_row_style(ws, HWC_STORAGE_ROW, HWC_STORAGE_TOTAL_ROW + insert_offset, 4)
            ws.cell(HWC_STORAGE_TOTAL_ROW + insert_offset, 1, "Elastic Volume Service (EVS) High I/O")
            ws.cell(HWC_STORAGE_TOTAL_ROW + insert_offset, 2, high_io_qty)
            ws.cell(HWC_STORAGE_TOTAL_ROW + insert_offset, 3, high_io_unit_price)
            ws.cell(HWC_STORAGE_TOTAL_ROW + insert_offset, 4, high_io_total)
            insert_offset += 1
        if ultra_qty > 0 or ultra_total > 0:
            _copy_row_style(ws, HWC_STORAGE_ROW, HWC_STORAGE_TOTAL_ROW + insert_offset, 4)
            ws.cell(HWC_STORAGE_TOTAL_ROW + insert_offset, 1, "Elastic Volume Service (EVS) Ultra High I/O")
            ws.cell(HWC_STORAGE_TOTAL_ROW + insert_offset, 2, ultra_qty)
            ws.cell(HWC_STORAGE_TOTAL_ROW + insert_offset, 3, ultra_unit_price)
            ws.cell(HWC_STORAGE_TOTAL_ROW + insert_offset, 4, ultra_total)
            insert_offset += 1
        storage_total_row = HWC_STORAGE_TOTAL_ROW + extra_storage_rows
        network_header_row = HWC_NETWORK_HEADER_ROW + extra_storage_rows
        network_row = HWC_NETWORK_ROW + extra_storage_rows
        network_total_row = HWC_NETWORK_TOTAL_ROW + extra_storage_rows
    else:
        storage_total_row = HWC_STORAGE_TOTAL_ROW
        network_header_row = HWC_NETWORK_HEADER_ROW
        network_row = HWC_NETWORK_ROW
        network_total_row = HWC_NETWORK_TOTAL_ROW

    ws.cell(HWC_STORAGE_ROW, 1, "Elastic Volume Service (EVS) General Purpose SSD")
    ws.cell(HWC_STORAGE_ROW, 2, gpssd_qty)
    ws.cell(HWC_STORAGE_ROW, 3, gpssd_unit_price)
    ws.cell(HWC_STORAGE_ROW, 4, gpssd_total)

    ws.cell(storage_total_row, 1, None)
    ws.cell(storage_total_row, 2, None)
    ws.cell(storage_total_row, 3, "EVS Total")
    ws.cell(storage_total_row, 4, round(gpssd_total + high_io_total + ultra_total, 2))

    ws.cell(network_header_row, 1, "HUAWEI CLOUD Networking")
    ws.cell(network_header_row, 2, "Cantidad")
    ws.cell(network_header_row, 3, "Price per")
    ws.cell(network_header_row, 4, "Total")
    ws.cell(network_row, 1, "VPN S2S Enterprise")
    ws.cell(network_row, 2, 0)
    ws.cell(network_row, 3, 0)
    ws.cell(network_row, 4, 0)
    ws.cell(network_total_row, 1, None)
    ws.cell(network_total_row, 2, None)
    ws.cell(network_total_row, 3, "Total")
    ws.cell(network_total_row, 4, 0)


def _populate_template_summary_sheet(
    ws: Any,
    summary: QuoteSummary,
    lines: list[dict[str, Any]],
    request: QuoteRequest,
    source_filenames: list[str] | None = None,
) -> None:
    quoted = [item for item in lines if item.get("action") == "quote"]
    ecs_ondemand = round(sum(_safe_number(item.get("ecs_ondemand_monthly_usd")) for item in quoted), 2)
    ecs_ri_1y = round(sum(_safe_number(item.get("ecs_ri_1y_monthly_usd")) for item in quoted), 2)
    evs_total = round(sum(_safe_number(item.get("evs_monthly_usd")) for item in quoted), 2)
    vpn_total = 0.0
    list_ondemand = round(ecs_ondemand + evs_total + vpn_total, 2)
    list_ri_1y = round(ecs_ri_1y + evs_total + vpn_total, 2)
    discounted_ondemand = round(list_ondemand * 0.8, 2)
    discounted_ri_1y = round(list_ri_1y * 0.8, 2)

    ws["B4"] = _template_title(source_filenames, request.source_filename)
    ws["C7"] = ecs_ondemand
    ws["D7"] = ecs_ri_1y
    ws["B9"] = "Elastic Volume Service (EVS)"
    ws["C9"] = evs_total
    ws["D9"] = evs_total
    ws["C11"] = vpn_total
    ws["D11"] = vpn_total
    ws["C12"] = list_ondemand
    ws["D12"] = list_ri_1y
    ws["B13"] = None
    ws["C13"] = None
    ws["D13"] = None
    ws["B16"] = f"Basados en la pestaña <ECS> con {summary.total_vms} VM(s) analizadas."
    ws["B19"] = (
        "1. No se incluye ningun tipo de licenciamiento de S.O ni Bases de datos.\n"
        "2. Valores no incluyen servicios de migración a Huawei Cloud.\n"
        "3. Valores expresados en Dólares americanos.\n"
        "4. El monitoreo de plataforma se hará mediante CloudEye.\n"
        "5. Valores no incluyen IVA.\n"
        "6. Valores sujetos a cambios.\n"
        "7. CBR se muestra como placeholder en esta fase.\n"
        f"8. Cotización generada al día {datetime.now(timezone.utc).strftime('%d.%m.%Y')}."
    )


def export_excel(state: QuoteState) -> QuoteState:
    summary = QuoteSummary.model_validate(state["summary"])
    request = _request_model(state)
    quote_lines = state["quote_lines"]
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"RVTools quote template was not found at {TEMPLATE_PATH}")

    workbook = load_workbook(TEMPLATE_PATH)
    for sheet_name in TEMPLATE_SHEET_ORDER:
        if sheet_name not in workbook.sheetnames:
            raise KeyError(f"RVTools quote template is missing required sheet: {sheet_name}")

    ecs_rows = _build_ecs_export_rows(quote_lines)
    _populate_template_ecs_sheet(workbook["ECS"], ecs_rows)
    _populate_template_hwc_sheet(workbook["HWC"], quote_lines, request, state.get("pricebook", {}))
    _populate_template_summary_sheet(
        workbook["Summary"],
        summary,
        quote_lines,
        request,
        source_filenames=state.get("source_filenames"),
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"quote-{request.region}-{stamp}.xlsx"
    output = BytesIO()
    workbook.save(output)
    return {"workbook": QuoteWorkbook(filename=filename, content=output.getvalue())}


def build_preview_graph():
    graph = StateGraph(QuoteState)
    graph.add_node("parse_rvtools", parse_rvtools)
    graph.add_node("normalize_inventory", normalize_inventory)
    graph.add_node("classify_inventory_context", classify_inventory_context)
    graph.add_node("load_pricebook", load_pricebook_node)
    graph.add_node("quote_inventory", quote_inventory)
    graph.add_node("summarize_quote", summarize_quote)
    graph.add_edge(START, "parse_rvtools")
    graph.add_edge("parse_rvtools", "normalize_inventory")
    graph.add_edge("normalize_inventory", "classify_inventory_context")
    graph.add_edge("classify_inventory_context", "load_pricebook")
    graph.add_edge("load_pricebook", "quote_inventory")
    graph.add_edge("quote_inventory", "summarize_quote")
    graph.add_edge("summarize_quote", END)
    return graph.compile()


def build_export_graph():
    graph = StateGraph(QuoteState)
    graph.add_node("parse_rvtools", parse_rvtools)
    graph.add_node("normalize_inventory", normalize_inventory)
    graph.add_node("classify_inventory_context", classify_inventory_context)
    graph.add_node("load_pricebook", load_pricebook_node)
    graph.add_node("quote_inventory", quote_inventory)
    graph.add_node("summarize_quote", summarize_quote)
    graph.add_node("export_excel", export_excel)
    graph.add_edge(START, "parse_rvtools")
    graph.add_edge("parse_rvtools", "normalize_inventory")
    graph.add_edge("normalize_inventory", "classify_inventory_context")
    graph.add_edge("classify_inventory_context", "load_pricebook")
    graph.add_edge("load_pricebook", "quote_inventory")
    graph.add_edge("quote_inventory", "summarize_quote")
    graph.add_edge("summarize_quote", "export_excel")
    graph.add_edge("export_excel", END)
    return graph.compile()


preview_graph = build_preview_graph()
export_graph = build_export_graph()


def build_multi_preview_graph():
    """Preview graph that supports multiple RVTools files."""
    graph = StateGraph(QuoteState)
    graph.add_node("parse_rvtools_multi", parse_rvtools_multi)
    graph.add_node("normalize_inventory", normalize_inventory)
    graph.add_node("classify_inventory_context", classify_inventory_context)
    graph.add_node("load_pricebook", load_pricebook_node)
    graph.add_node("quote_inventory", quote_inventory)
    graph.add_node("summarize_quote", summarize_quote)
    graph.add_edge(START, "parse_rvtools_multi")
    graph.add_edge("parse_rvtools_multi", "normalize_inventory")
    graph.add_edge("normalize_inventory", "classify_inventory_context")
    graph.add_edge("classify_inventory_context", "load_pricebook")
    graph.add_edge("load_pricebook", "quote_inventory")
    graph.add_edge("quote_inventory", "summarize_quote")
    graph.add_edge("summarize_quote", END)
    return graph.compile()


def build_multi_export_graph():
    """Export graph that supports multiple RVTools files."""
    graph = StateGraph(QuoteState)
    graph.add_node("parse_rvtools_multi", parse_rvtools_multi)
    graph.add_node("normalize_inventory", normalize_inventory)
    graph.add_node("classify_inventory_context", classify_inventory_context)
    graph.add_node("load_pricebook", load_pricebook_node)
    graph.add_node("quote_inventory", quote_inventory)
    graph.add_node("summarize_quote", summarize_quote)
    graph.add_node("export_excel", export_excel)
    graph.add_edge(START, "parse_rvtools_multi")
    graph.add_edge("parse_rvtools_multi", "normalize_inventory")
    graph.add_edge("normalize_inventory", "classify_inventory_context")
    graph.add_edge("classify_inventory_context", "load_pricebook")
    graph.add_edge("load_pricebook", "quote_inventory")
    graph.add_edge("quote_inventory", "summarize_quote")
    graph.add_edge("summarize_quote", "export_excel")
    graph.add_edge("export_excel", END)
    return graph.compile()


multi_preview_graph = build_multi_preview_graph()
multi_export_graph = build_multi_export_graph()
