from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, TypedDict

import httpx
import pandas as pd
from langgraph.graph import END, START, StateGraph

from app.models import (
    EvsTypeKey,
    NormalizedVM,
    QuoteLine,
    QuotePreviewResponse,
    QuoteRequest,
    QuoteSummary,
    QuoteWorkbook,
)
from app.pricebook import load_pricebook, pick_ecs_match
from app.rvtools import parse_rvtools_workbook

HOURS_PER_MONTH = 730


class QuoteState(TypedDict, total=False):
    request: QuoteRequest
    file_bytes: bytes
    parsed_vms: list[dict[str, Any]]
    normalized_vms: list[dict[str, Any]]
    quote_lines: list[dict[str, Any]]
    summary: dict[str, Any]
    workbook: QuoteWorkbook
    pricebook: dict[str, Any]
    raw_vinfo: list[dict[str, Any]]
    raw_vdisk: list[dict[str, Any]]


def _request_model(state: QuoteState) -> QuoteRequest:
    return QuoteRequest.model_validate(state["request"])


def parse_rvtools(state: QuoteState) -> QuoteState:
    parsed, raw_vinfo, raw_vdisk = parse_rvtools_workbook(state["file_bytes"])
    return {
        "parsed_vms": [item.model_dump() for item in parsed],
        "raw_vinfo": raw_vinfo,
        "raw_vdisk": raw_vdisk,
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

        normalized.append(
            NormalizedVM(
                **item,
                action=action,
                review_reason=review_reason,
            ).model_dump()
        )
    return {"normalized_vms": normalized}


def load_pricebook_node(_: QuoteState) -> QuoteState:
    return {"pricebook": load_pricebook()}


def _evs_monthly(region_catalog: dict[str, Any], evs_type: EvsTypeKey, disk_gib: float) -> float:
    evs_item = next(item for item in region_catalog["evs"] if item["key"] == evs_type)
    return round(float(disk_gib) * float(evs_item["monthlyEquivalentUsdPerGb"]), 4)


def quote_inventory(state: QuoteState) -> QuoteState:
    request = _request_model(state)
    region_catalog = state["pricebook"]["pricingCatalog"][request.region]
    lines: list[dict[str, Any]] = []

    for item in state["normalized_vms"]:
        evs_monthly = _evs_monthly(region_catalog, request.evs_type, float(item["disk_gib"]))
        if item["action"] != "quote":
            lines.append(
                QuoteLine(
                    **item,
                    region=request.region,
                    evs_type=request.evs_type,
                    evs_monthly_usd=evs_monthly,
                ).model_dump()
            )
            continue

        match = pick_ecs_match(region_catalog, int(item["vcpu"]), float(item["memory_gib"]))
        if not match:
            item = {
                **item,
                "action": "manual_review",
                "review_reason": "No ECS spec matched the requested CPU/memory shape.",
            }
            lines.append(
                QuoteLine(
                    **item,
                    region=request.region,
                    evs_type=request.evs_type,
                    evs_monthly_usd=evs_monthly,
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
                ecs_ondemand_monthly_usd=ondemand,
                ecs_ri_1y_monthly_usd=ri,
                evs_monthly_usd=evs_monthly,
                total_ondemand_monthly_usd=round(ondemand + evs_monthly, 4),
                total_ri_1y_monthly_usd=round(ri + evs_monthly, 4),
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
        with httpx.Client(timeout=20) as client:
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


def export_excel(state: QuoteState) -> QuoteState:
    summary = QuoteSummary.model_validate(state["summary"])
    request = _request_model(state)
    quote_lines = pd.DataFrame(state["quote_lines"])
    manual_review = quote_lines[quote_lines["action"] == "manual_review"]
    raw_rvtools = pd.concat(
        [
            pd.DataFrame(state["raw_vinfo"]).assign(source_sheet="vInfo"),
            pd.DataFrame(state["raw_vdisk"]).assign(source_sheet="vDisk"),
        ],
        ignore_index=True,
    )
    pricebook_used = pd.DataFrame(
        [
            {
                "region": request.region,
                "evs_type": request.evs_type,
                "source_file": state["pricebook"].get("sourceFile", ""),
                "exported_at": state["pricebook"].get("exportedAt", ""),
                **state["pricebook"]["pricingMetadata"],
            }
        ]
    )

    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        pd.DataFrame(
            [
                {
                    "source_filename": request.source_filename,
                    "region": request.region,
                    "evs_type": request.evs_type,
                    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                    **summary.model_dump(),
                    "assumptions": " | ".join(summary.assumptions),
                    "risks": " | ".join(summary.risks),
                }
            ]
        ).to_excel(writer, sheet_name="Summary", index=False)
        quote_lines.to_excel(writer, sheet_name="Quote Lines", index=False)
        manual_review.to_excel(writer, sheet_name="Manual Review", index=False)
        raw_rvtools.to_excel(writer, sheet_name="Raw RVTools", index=False)
        pricebook_used.to_excel(writer, sheet_name="Pricebook Used", index=False)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"quote-{request.region}-{stamp}.xlsx"
    return {"workbook": QuoteWorkbook(filename=filename, content=output.getvalue())}


def build_preview_graph():
    graph = StateGraph(QuoteState)
    graph.add_node("parse_rvtools", parse_rvtools)
    graph.add_node("normalize_inventory", normalize_inventory)
    graph.add_node("load_pricebook", load_pricebook_node)
    graph.add_node("quote_inventory", quote_inventory)
    graph.add_node("summarize_quote", summarize_quote)
    graph.add_edge(START, "parse_rvtools")
    graph.add_edge("parse_rvtools", "normalize_inventory")
    graph.add_edge("normalize_inventory", "load_pricebook")
    graph.add_edge("load_pricebook", "quote_inventory")
    graph.add_edge("quote_inventory", "summarize_quote")
    graph.add_edge("summarize_quote", END)
    return graph.compile()


def build_export_graph():
    graph = StateGraph(QuoteState)
    graph.add_node("parse_rvtools", parse_rvtools)
    graph.add_node("normalize_inventory", normalize_inventory)
    graph.add_node("load_pricebook", load_pricebook_node)
    graph.add_node("quote_inventory", quote_inventory)
    graph.add_node("summarize_quote", summarize_quote)
    graph.add_node("export_excel", export_excel)
    graph.add_edge(START, "parse_rvtools")
    graph.add_edge("parse_rvtools", "normalize_inventory")
    graph.add_edge("normalize_inventory", "load_pricebook")
    graph.add_edge("load_pricebook", "quote_inventory")
    graph.add_edge("quote_inventory", "summarize_quote")
    graph.add_edge("summarize_quote", "export_excel")
    graph.add_edge("export_excel", END)
    return graph.compile()


preview_graph = build_preview_graph()
export_graph = build_export_graph()
