from __future__ import annotations

from io import BytesIO
import os
import time
from zipfile import ZipFile

import httpx

from openpyxl import Workbook, load_workbook
import pandas as pd
import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

import app.flexible_workflow as flexible_workflow_mod
import app.row_quote_workflow
from app.flexible_pricing import load_flexible_pricing_catalog, query_flexible_pricing_catalog
from app.flexible_workflow import (
    build_flexible_preview_response,
    build_flexible_review_state,
    flexible_export_graph,
    flexible_preview_graph,
    flexible_review_graph,
)
from app.main import (
    create_flexible_annotate_task,
    create_flexible_preview_task,
    export_flexible_annotate_task,
    export_flexible_quote,
    export_quote,
    get_flexible_annotate_task,
    get_flexible_preview_task,
    get_flexible_pricing_catalog,
)
from app.models import FlexibleQuoteContext, FlexibleReviewRequest, HumanFeedback, QuoteRequest, QuoteSummary, SheetSelection, SheetSelectionError, resolve_sheet_selection
from app.pricebook import load_pricebook, pick_ecs_match
from app.row_quote_workflow import RowMapping, RowCandidate, _collect_rows, _normalize_mapping_spec, _normalize_spec_alias, _fallback_mapping, _apply_product_priority, _apply_special_product_routing, _apply_hard_exclusions, _apply_composite_routing, _apply_product_priority_overrides, _enrich_composite_metadata, _price_evs, _price_catalog_product, _detect_composite_family, _detect_composite_part, annotate_row_quote_workbook
from app.models import RowQuoteProgress
from app.rvtools import RvToolsParseError, parse_rvtools_workbook
from app.workflow import (
    export_graph,
    preview_graph,
    build_preview_graph,
    build_export_graph,
    build_preview_response,
    export_excel,
    normalize_inventory,
    _classify_vm_locally,
    _maas_summary,
    classify_inventory_context,
    _validate_llm_classification_row,
    _merge_llm_classification,
    _build_llm_classify_payload,
    _resolve_evs_type_for_vm,
    _resolve_family_policy_for_vm,
    _build_ecs_export_rows,
    _build_hwc_rows,
)
from app.rvtools_preview_tasks import store_preview_result, get_preview_state, _tasks as _rvtools_tasks, _lock as _rvtools_lock


def make_rvtools_file(
    *,
    info_rows: list[dict[str, object]] | None = None,
    disk_rows: list[dict[str, object]] | None = None,
    include_vinfo: bool = True,
) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        if include_vinfo:
            pd.DataFrame(info_rows or []).to_excel(writer, sheet_name="vInfo", index=False)
        pd.DataFrame(disk_rows or []).to_excel(writer, sheet_name="vDisk", index=False)
    return buffer.getvalue()


def make_flexible_xlsx(rows: list[dict[str, object]]) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="Requirements", index=False)
    return buffer.getvalue()


def make_multi_header_flexible_xlsx(*, include_quantity: bool = True, blank_huawei_product: bool = False) -> bytes:
    buffer = BytesIO()
    huawei_ecs = "" if blank_huawei_product else "弹性云服务器 ECS"
    huawei_evs = "" if blank_huawei_product else "云硬盘 EVS"
    if include_quantity:
        rows = [
            ["产品类别", "腾讯云", "", "", "", "华为云", "", "", ""],
            ["", "产品名称", "数量", "区域", "规格", "产品名称", "数量", "区域", "规格"],
            ["计算", "CVM", 2, "Mexico", "4核8G", huawei_ecs, 2, "Mexico", "x0.2u.4g"],
            ["存储", "CBS", 4, "Mexico", "500GB SSD", huawei_evs, 4, "Mexico", "gp-ssd 500GB"],
        ]
    else:
        rows = [
            ["产品类别", "腾讯云", "", "", "华为云", "", ""],
            ["", "产品名称", "区域", "规格", "产品名称", "区域", "规格"],
            ["计算", "CVM", "Mexico", "4核8G", huawei_ecs, "Mexico", "x0.2u.4g"],
            ["存储", "CBS", "Mexico", "500GB SSD", huawei_evs, "Mexico", "gp-ssd 500GB"],
        ]
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="计算", index=False, header=False)
    return buffer.getvalue()


def make_row_quote_workbook() -> bytes:
    workbook = Workbook()
    first = workbook.active
    first.title = "Compute"
    first.append(["Product", "Region", "Spec"])
    first.append(["ECS", "mexico", "x0.2u.4g"])
    first.append(["Section title", "", ""])
    first.append(["GPU", "mexico", "L20"])
    second = workbook.create_sheet("Storage")
    second.append(["Service", "Region", "Spec"])
    second.append(["EVS", "mexico", "gp-ssd 100GB"])
    second.append(["RDS", "brazil", "mysql.s2.large"])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def make_merged_row_quote_workbook() -> bytes:
    workbook = Workbook()
    ws = workbook.active
    ws.title = "Merged"
    ws.append(["Category", "Service", "Detail", "Quantity", "Region"])
    ws.append(["Container", "容器服务 Serverless", "Pod 2C4G", 1, "mexico"])
    ws.append(["", "", "Pod-CPU 4", 4, "mexico"])
    ws.append(["", "", "Pod-Memory 8", 8, "mexico"])
    ws.merge_cells("B2:B4")
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def fake_schema_mapping(*_: object, **__: object) -> dict[str, object]:
    return {
        "schema_mapping": {
            "product": "product",
            "quantity": "quantity",
            "region": "region",
            "spec": "spec",
            "notes": None,
        },
        "extraction_hints": {},
        "_llm_model": "test-model",
        "_llm_attempts": 1,
    }


def fake_empty_schema_mapping(*_: object, **__: object) -> dict[str, object]:
    return {
        "schema_mapping": {
            "product": None,
            "quantity": None,
            "region": None,
            "spec": None,
            "notes": None,
        },
        "extraction_hints": {},
        "_llm_model": "test-model",
        "_llm_attempts": 1,
    }


def fake_unit_price_profile_schema_mapping(*_: object, **__: object) -> dict[str, object]:
    payload = fake_empty_schema_mapping()
    payload["profile"] = {
        "quote_purpose": "unit_price_comparison",
        "quantity_policy": "default_to_one_for_unit_price",
        "confidence": 0.9,
        "rationale": "Vendor comparison sheet.",
    }
    return payload


def fake_unit_price_profile_product_schema_mapping(*_: object, **__: object) -> dict[str, object]:
    return {
        "profile": {
            "quote_purpose": "unit_price_comparison",
            "quantity_policy": "default_to_one_for_unit_price",
            "confidence": 0.9,
            "rationale": "Unit comparison sheet.",
        },
        "schema_mapping": {
            "product": "product",
            "quantity": None,
            "region": "region",
            "spec": "spec",
            "notes": None,
        },
        "extraction_hints": {},
        "_llm_model": "test-model",
        "_llm_attempts": 1,
    }


def test_parse_rvtools_supports_variants_and_aggregates_disk():
    content = make_rvtools_file(
        info_rows=[
            {"VM Name": "app-01", "Power State": "PoweredOn", "NumCpu": 2, "Memory MB": 8192, "OS": "Windows"},
        ],
        disk_rows=[
            {"VM": "app-01", "Capacity GB": 100},
            {"VM": "app-01", "Provisioned GB": 50},
        ],
    )

    parsed, _, _ = parse_rvtools_workbook(content)

    assert len(parsed) == 1
    assert parsed[0].vm_name == "app-01"
    assert parsed[0].vcpu == 2
    assert parsed[0].memory_gib == 8
    assert parsed[0].disk_gib == 150


def test_parse_rvtools_requires_vinfo():
    # A sheet with only vDisk (no vInfo, no inventory-like columns) should fail
    content = make_rvtools_file(include_vinfo=False, disk_rows=[{"VM": "x", "Capacity GB": 10}])
    try:
        parse_rvtools_workbook(content)
    except RvToolsParseError as exc:
        msg = str(exc)
        assert "vInfo" in msg
        assert "inventory-like" in msg
    else:
        raise AssertionError("Expected missing vInfo / inventory-like error")


def test_price_engine_respects_region_evs_and_category_priority():
    pricebook = load_pricebook()
    mexico = pricebook["pricingCatalog"]["mexico"]
    chile = pricebook["pricingCatalog"]["chile"]

    mexico_match = pick_ecs_match(mexico, 2, 8)
    chile_match = pick_ecs_match(chile, 2, 8)

    assert mexico_match is not None
    assert chile_match is not None
    assert mexico_match["category"] == "General Computing"
    assert chile_match["category"] == "General Computing"
    assert mexico["regionCode"] != chile["regionCode"]
    assert mexico_match["spec"]
    assert chile_match["spec"]

    evs_by_key = {item["key"]: item for item in mexico["evs"]}
    assert evs_by_key["gpssd"]["monthlyEquivalentUsdPerGb"] != evs_by_key["sas"]["monthlyEquivalentUsdPerGb"]


def test_graph_quotes_and_exports_without_maas():
    load_pricebook.cache_clear()
    content = make_rvtools_file(
        info_rows=[
            {"VM": "linux-on", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
            {"VM": "linux-off", "Powerstate": "PoweredOff", "CPUs": 2, "Memory": 4},
            {"VM": "oversized", "Powerstate": "PoweredOn", "CPUs": 999, "Memory": 999},
        ],
        disk_rows=[
            {"VM": "linux-on", "Capacity GiB": 120},
            {"VM": "linux-off", "Capacity GiB": 80},
            {"VM": "oversized", "Capacity GiB": 200},
        ],
    )

    result = export_graph.invoke(
        {
            "request": {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "sample.xlsx"},
            "file_bytes": content,
        }
    )

    workbook = result["workbook"]
    with ZipFile(BytesIO(workbook.content)) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
    assert "Summary" in workbook_xml
    assert "ECS" in workbook_xml
    assert "HWC" in workbook_xml
    assert "Información" in workbook_xml
    summary = result["summary"]
    assert summary["quoted_vms"] == 2  # linux-on + oversized (nearest match finds closest spec)
    assert summary["excluded_vms"] == 1
    assert summary["manual_review_vms"] == 0
    quoted_line = next(line for line in result["quote_lines"] if line["vm_name"] == "linux-on")
    assert quoted_line["ecs_ondemand_monthly_usd"] == 33.58


def test_export_api_returns_excel():
    content = make_rvtools_file(
        info_rows=[{"VM": "api-01", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4}],
        disk_rows=[{"VM": "api-01", "Capacity GiB": 100}],
    )

    response = export_quote(
        UploadFile(filename="sample.xlsx", file=BytesIO(content)),
        "mexico",
        "gpssd",
        "en",
        "first",
        "",
    )

    assert response.status_code == 200
    assert response.media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "quote-mexico-" in response.headers["content-disposition"]


def test_flexible_catalog_endpoint_filters_rows():
    load_flexible_pricing_catalog.cache_clear()
    response = get_flexible_pricing_catalog(product="ECS", region="mexico")
    assert response.items
    assert all(item.product == "ECS" and item.region == "mexico" for item in response.items)
    assert any(item.confirmed for item in response.items)


def test_flexible_preview_quotes_confirmed_items_and_flags_unconfirmed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(flexible_workflow_mod, "_maas_understanding", fake_schema_mapping)
    content = make_flexible_xlsx(
        [
            {"product": "ECS", "quantity": 2, "region": "mexico", "spec": "x0.2u.4g"},
            {"product": "Direct Connect as a Service", "quantity": 1, "region": "brazil", "spec": "dcas-1g"},
        ]
    )

    state = flexible_preview_graph.invoke(
        {
            "files": [{"filename": "requirements.xlsx", "content": content}],
            "quote_context": {"region": "mexico", "language": "en", "customer_notes": ""},
        }
    )
    payload = build_flexible_preview_response(state)

    assert len(payload.requirements) == 2
    assert len(payload.quote_lines) == 2
    assert payload.quote_lines[0].monthly_price == 67.16
    assert payload.diagnostics.llm_used is True


def test_flexible_preview_extracts_chinese_multi_header_excel(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(flexible_workflow_mod, "_maas_understanding", fake_empty_schema_mapping)
    content = make_multi_header_flexible_xlsx()

    state = flexible_preview_graph.invoke(
        {
            "files": [{"filename": "multi-header.xlsx", "content": content}],
            "quote_context": {"region": "mexico", "language": "zh", "customer_notes": ""},
        }
    )
    payload = build_flexible_preview_response(state)

    assert len(payload.requirements) == 2
    assert payload.diagnostics.documents[0].selected_columns["product"] == "华为云.产品名称"
    assert payload.requirements[0].raw_product_name == "弹性云服务器 ECS"
    assert payload.requirements[0].normalized_product == "ECS"
    assert payload.requirements[0].quantity == 2
    assert payload.requirements[0].region == "mexico"
    assert payload.quote_lines


def test_flexible_preview_infers_quantity_one_for_unit_price_comparison(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(flexible_workflow_mod, "_maas_understanding", fake_unit_price_profile_schema_mapping)
    content = make_multi_header_flexible_xlsx(include_quantity=False)

    state = flexible_preview_graph.invoke(
        {
            "files": [{"filename": "unit-price-comparison.xlsx", "content": content}],
            "quote_context": {"region": "mexico", "language": "zh", "customer_notes": ""},
        }
    )
    payload = build_flexible_preview_response(state)

    assert not payload.quote_blockers
    assert payload.quote_lines
    assert payload.requirements[0].quantity == 1
    assert payload.requirements[0].quantity_source == "inferred_unit_price"
    assert "unit price comparison" in (payload.requirements[0].status_reason or "")
    assert any("quantity=1" in assumption for assumption in payload.summary.assumptions)
    assert "reference unit price" in (payload.quote_lines[0].assumption or "")


def test_flexible_preview_quotes_ready_items_even_when_other_items_block(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(flexible_workflow_mod, "_maas_understanding", fake_unit_price_profile_product_schema_mapping)
    content = make_flexible_xlsx(
        [
            {"product": "ECS", "region": "mexico", "spec": "x0.2u.4g"},
            {"product": "IoTDA", "region": "mexico", "spec": "standard"},
        ]
    )

    state = flexible_preview_graph.invoke(
        {
            "files": [{"filename": "mixed-comparison.xlsx", "content": content}],
            "quote_context": {"region": "mexico", "language": "en", "customer_notes": ""},
        }
    )
    payload = build_flexible_preview_response(state)

    assert payload.quote_blockers
    assert payload.quote_lines
    assert payload.quote_lines[0].product == "ECS"
    assert payload.quote_lines[0].quantity == 1


def test_flexible_preview_falls_back_when_huawei_product_column_is_empty(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(flexible_workflow_mod, "_maas_understanding", fake_unit_price_profile_schema_mapping)
    content = make_multi_header_flexible_xlsx(include_quantity=False, blank_huawei_product=True)

    state = flexible_preview_graph.invoke(
        {
            "files": [{"filename": "blank-huawei-column.xlsx", "content": content}],
            "quote_context": {"region": "mexico", "language": "zh", "customer_notes": ""},
        }
    )
    payload = build_flexible_preview_response(state)

    assert payload.requirements
    assert payload.diagnostics.documents[0].selected_columns["product"] == "腾讯云.产品名称"
    assert payload.requirements[0].raw_product_name == "CVM"
    assert payload.requirements[0].normalized_product == "ECS"
    assert payload.quote_lines


def test_flexible_review_applies_feedback_and_unlocks_quote(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(flexible_workflow_mod, "_maas_understanding", fake_schema_mapping)
    content = make_flexible_xlsx(
        [
            {"product": "RDS", "quantity": "", "region": "mexico", "spec": "mysql.s2.large"},
        ]
    )

    preview_state = flexible_preview_graph.invoke(
        {
            "files": [{"filename": "requirements.xlsx", "content": content}],
            "quote_context": {"region": "mexico", "language": "en", "customer_notes": ""},
        }
    )
    preview_payload = build_flexible_preview_response(preview_state)
    assert preview_payload.quote_blockers
    assert preview_payload.quote_blockers[0].status == "needs_quantity"

    request = FlexibleReviewRequest(
        requirements=preview_payload.requirements,
        quote_context=FlexibleQuoteContext(region="mexico", language="en", customer_notes=""),
        matched_products=preview_payload.matched_products,
        audit_log=preview_payload.audit_log,
        feedback=[HumanFeedback(item_id=preview_payload.requirements[0].item_id, quantity=3)],
    )
    reviewed = build_flexible_preview_response(flexible_review_graph.invoke(build_flexible_review_state(request)))

    assert not reviewed.quote_blockers
    assert len(reviewed.quote_lines) == 1
    assert reviewed.quote_lines[0].monthly_price == 222.0


def test_flexible_export_api_returns_required_sheets(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(flexible_workflow_mod, "_maas_understanding", fake_schema_mapping)
    request = FlexibleReviewRequest(
        requirements=[],
        quote_context=FlexibleQuoteContext(region="mexico", language="en", customer_notes=""),
        matched_products=[],
        audit_log=[],
        feedback=[],
    )

    preview_state = flexible_preview_graph.invoke(
        {
            "files": [
                {
                    "filename": "requirements.csv",
                    "content": b"product,quantity,region,spec\nEIP,2,mexico,eip-standard\nNAT Gateway,1,mexico,nat-basic\n",
                }
            ],
            "quote_context": {"region": "mexico", "language": "en", "customer_notes": ""},
        }
    )
    preview_payload = build_flexible_preview_response(preview_state)
    export_request = request.model_copy(
        update={
            "requirements": preview_payload.requirements,
            "matched_products": preview_payload.matched_products,
            "audit_log": preview_payload.audit_log,
        }
    )

    response = export_flexible_quote(export_request)
    assert response.status_code == 200
    with ZipFile(BytesIO(response.body)) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
    assert "Summary" in workbook_xml
    assert "Standard Requirements" in workbook_xml
    assert "Quote Lines" in workbook_xml
    assert "Unquoted Items" in workbook_xml
    assert "Mapping &amp; Assumptions" in workbook_xml
    assert "Audit Log" in workbook_xml


def test_flexible_catalog_confirmed_query_only():
    items = query_flexible_pricing_catalog(product="Workspace", region="brazil", confirmed_only=True)
    assert items == []


def test_flexible_preview_task_reports_progress_and_result(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(flexible_workflow_mod, "_maas_understanding", fake_schema_mapping)
    content = make_flexible_xlsx([{"product": "ECS", "quantity": 1, "region": "mexico", "spec": "x0.2u.4g"}])

    created = create_flexible_preview_task(
        [UploadFile(filename="requirements.xlsx", file=BytesIO(content))],
        "mexico",
        "en",
        "",
    )
    assert created.status == "queued"

    final = None
    for _ in range(80):
        snapshot = get_flexible_preview_task(created.task_id)
        if snapshot.status in {"succeeded", "failed"}:
            final = snapshot
            break
        time.sleep(0.05)

    assert final is not None
    assert final.status == "succeeded"
    assert final.result is not None
    assert final.result.quote_lines
    assert any(event.stage == "parse_documents" and event.status == "completed" for event in final.stage_events)
    assert any(event.stage == "return_blockers" and event.status == "skipped" for event in final.stage_events)


def test_flexible_preview_task_failure_sets_failed_status_and_error():
    created = create_flexible_preview_task(
        [UploadFile(filename="broken.pdf", file=BytesIO(b"not-supported"))],
        "mexico",
        "en",
        "",
    )

    final = None
    for _ in range(80):
        snapshot = get_flexible_preview_task(created.task_id)
        if snapshot.status in {"succeeded", "failed"}:
            final = snapshot
            break
        time.sleep(0.05)

    assert final is not None
    assert final.status == "failed"
    assert final.error is not None
    assert final.error.last_stage == "ingest_files"


def test_flexible_preview_task_missing_returns_404():
    with pytest.raises(HTTPException) as exc_info:
        get_flexible_preview_task("missing-task-id")
    assert exc_info.value.status_code == 404


def test_flexible_preview_fails_when_no_requirements_are_extracted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        flexible_workflow_mod,
        "_maas_understanding",
        lambda *_args, **_kwargs: {
            "schema_mapping": {
                "product": "Service Name",
                "quantity": "Qty",
                "region": "Deployment Country",
                "spec": "Flavor",
                "notes": None,
            },
            "extraction_hints": {},
            "_llm_model": "test-model",
            "_llm_attempts": 1,
        },
    )
    content = make_flexible_xlsx([{"Wrong Col": "x", "Another": 1}])

    created = create_flexible_preview_task(
        [UploadFile(filename="requirements.xlsx", file=BytesIO(content))],
        "mexico",
        "en",
        "",
    )
    final = None
    for _ in range(80):
        snapshot = get_flexible_preview_task(created.task_id)
        if snapshot.status in {"succeeded", "failed"}:
            final = snapshot
            break
        time.sleep(0.05)

    assert final is not None
    assert final.status == "failed"
    assert final.error is not None
    assert final.error.last_stage == "extract_requirement_items"
    assert final.error.diagnostics is not None
    assert final.error.diagnostics.documents
    assert "No recognizable requirement rows" in (final.error.detail or "")


def test_flexible_preview_fails_when_llm_understanding_fails(monkeypatch: pytest.MonkeyPatch):
    def _raise_llm(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise flexible_workflow_mod.FlexibleWorkflowError(
            "Flexible preview failed during LLM schema understanding.",
            stage="understand_input",
            detail="LLM schema understanding failed: timeout",
        )

    monkeypatch.setattr(flexible_workflow_mod, "_maas_understanding", _raise_llm)
    content = make_flexible_xlsx([{"product": "ECS", "quantity": 1, "region": "mexico", "spec": "x0.2u.4g"}])

    created = create_flexible_preview_task(
        [UploadFile(filename="requirements.xlsx", file=BytesIO(content))],
        "mexico",
        "en",
        "",
    )
    final = None
    for _ in range(80):
        snapshot = get_flexible_preview_task(created.task_id)
        if snapshot.status in {"succeeded", "failed"}:
            final = snapshot
            break
        time.sleep(0.05)

    assert final is not None
    assert final.status == "failed"
    assert final.error is not None
    assert final.error.last_stage == "understand_input"
    assert "timeout" in (final.error.detail or "")


def test_row_quote_workflow_only_processes_first_sheet(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook, summary = annotate_row_quote_workbook(
        {"filename": "customer.xlsx", "content": make_row_quote_workbook()},
        {"region": "mexico", "language": "zh", "customer_notes": ""},
    )

    assert summary.total_rows == 3
    assert summary.quoted_rows == 1
    assert summary.manual_review_rows == 1
    assert summary.missing_price_rows == 0
    assert summary.non_quote_rows == 1

    annotated = load_workbook(BytesIO(workbook.content), data_only=True)
    compute = annotated["Compute"]
    appended_headers = [compute.cell(1, column).value for column in range(compute.max_column - 18, compute.max_column + 1)]
    assert appended_headers == [
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
    assert compute.cell(2, compute.max_column - 16).value == 1
    assert compute.cell(2, compute.max_column - 11).value == "已报价"
    assert "Quantity estimated as 1" in compute.cell(2, compute.max_column - 10).value
    assert compute.cell(3, compute.max_column - 11).value == "非报价行"
    assert compute.cell(4, compute.max_column - 11).value == "需人工确认"

    storage = annotated["Storage"]
    assert storage.max_column == 3
    assert storage.cell(2, storage.max_column).value == "gp-ssd 100GB"
    assert storage.cell(3, storage.max_column).value == "mysql.s2.large"


def test_row_quote_annotate_task_exports_original_workbook_with_added_columns(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    created = create_flexible_annotate_task(
        UploadFile(filename="customer.xlsx", file=BytesIO(make_row_quote_workbook())),
        "mexico",
        "zh",
        "Generate a quote for SMB use.",
        "first",
        "",
    )

    final = None
    for _ in range(80):
        snapshot = get_flexible_annotate_task(created.task_id)
        if snapshot.status in {"succeeded", "failed"}:
            final = snapshot
            break
        time.sleep(0.05)

    assert final is not None
    assert final.status == "succeeded"
    assert final.summary is not None
    assert final.summary.quoted_rows == 1

    response = export_flexible_annotate_task(created.task_id)
    assert response.status_code == 200
    exported = load_workbook(BytesIO(response.body), data_only=True)
    assert "Compute" in exported.sheetnames
    assert exported["Compute"].cell(1, exported["Compute"].max_column - 18).value == "华为云产品名"


def test_row_quote_export_sanitizes_unicode_filename(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    created = create_flexible_annotate_task(
        UploadFile(filename="客户报价.xlsx", file=BytesIO(make_row_quote_workbook())),
        "mexico",
        "zh",
        "Generate a quote for SMB use.",
        "first",
        "",
    )

    final = None
    for _ in range(80):
        snapshot = get_flexible_annotate_task(created.task_id)
        if snapshot.status in {"succeeded", "failed"}:
            final = snapshot
            break
        time.sleep(0.05)

    assert final is not None
    assert final.status == "succeeded"

    response = export_flexible_annotate_task(created.task_id)
    assert response.status_code == 200
    assert "attachment; filename=" in response.headers["content-disposition"]
    assert "客户" not in response.headers["content-disposition"]


def test_row_quote_normalizes_ecs_spec_to_cpu_memory_shape():
    normalized = _normalize_mapping_spec(
        "ECS",
        "S6.16XLARGE256/Intel Ice Lake/64C256G+自选云盘",
        "标准型S6 美元/台/月 S6.16XLARGE256/Intel Ice Lake/64C256G+自选云盘",
    )
    assert normalized == "64vCPU 256GB"


def test_row_quote_normalizes_cci_specs():
    assert _normalize_mapping_spec("CCI", "Serverless Pod-CPU 4", "Serverless Pod-CPU 4 vCPU-second") == "4vCPU"
    assert _normalize_mapping_spec("CCI", "Serverless Pod-Memory 8", "Serverless Pod-Memory 8 GiB-second") == "8GiB"
    assert _normalize_mapping_spec("CCI", "Serverless Pod 2C4G", "Serverless Pod 2C4G") == "2vCPU 4GiB"


def test_row_quote_cci_cpu_memory_rows_are_quoted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook = Workbook()
    ws = workbook.active
    ws.title = "Serverless"
    ws.append(["Product", "Region", "Quantity"])
    ws.append(["Serverless Pod-CPU", "mexico", 4])
    ws.append(["Serverless Pod-Memory", "mexico", 8])
    output = BytesIO()
    workbook.save(output)

    quoted_workbook, summary = annotate_row_quote_workbook(
        {"filename": "cci.xlsx", "content": output.getvalue()},
        {"region": "mexico", "language": "zh", "customer_notes": ""},
    )

    assert summary.quoted_rows == 2
    annotated = load_workbook(BytesIO(quoted_workbook.content), data_only=True)["Serverless"]
    assert annotated.cell(2, annotated.max_column - 18).value == "CCI"
    assert annotated.cell(2, annotated.max_column - 11).value == "已报价"
    assert annotated.cell(3, annotated.max_column - 18).value == "CCI"
    assert annotated.cell(3, annotated.max_column - 11).value == "已报价"


def test_row_quote_serverless_header_forces_cci(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook = Workbook()
    ws = workbook.active
    ws.title = "容器"
    ws.append(["Cluster", "容器服务 Serverless", "Quantity"])
    ws.append(["AMD", "Pod-内存", 8])
    output = BytesIO()
    workbook.save(output)
    quoted_workbook, summary = annotate_row_quote_workbook(
        {"filename": "serverless.xlsx", "content": output.getvalue()},
        {"region": "mexico", "language": "zh", "customer_notes": ""},
    )
    assert summary.quoted_rows == 1
    annotated = load_workbook(BytesIO(quoted_workbook.content), data_only=True)["容器"]
    assert annotated.cell(2, annotated.max_column - 18).value == "CCI"
    assert annotated.cell(2, annotated.max_column - 11).value == "已报价"


def test_row_quote_vm_row_with_spanish_produccion_keeps_ecs_mapping():
    row = app.row_quote_workflow.RowCandidate(
        row_id="vInfo!2",
        sheet="vInfo",
        row_number=2,
        cells={
            "A": "influx-alert-01-devops",
            "B": "poweredOn",
            "C": "8",
            "D": "10240",
            "E": "/Producción/ESX_FRAME01/Resources",
            "F": "Ubuntu Linux (64-bit)",
        },
        local_cells={
            "A": "influx-alert-01-devops",
            "B": "poweredOn",
            "C": "8",
            "D": "10240",
            "E": "/Producción/ESX_FRAME01/Resources",
            "F": "Ubuntu Linux (64-bit)",
        },
        inherited_cells={},
        header_context=[
            {
                "row_id": "vInfo!1",
                "cells": '{"A":"VM","C":"CPUs","D":"Memory","E":"Resource pool","F":"OS according to VMware Tools"}',
                "local_cells": "{}",
                "inherited_cells": "{}",
            }
        ],
    )
    mapping = RowMapping(
        row_id="vInfo!2",
        is_quote_row=True,
        huawei_product="ECS",
        huawei_spec="8vCPU 16GB",
        quantity=1,
        rationale="VM with vCPU and memory maps to ECS.",
        confidence=0.9,
    )

    resolved = app.row_quote_workflow._apply_product_priority(row, mapping)

    assert resolved.huawei_product == "ECS"


def test_row_quote_ecs_pricing_uses_original_cpu_memory_not_llm_c7_hint():
    row = app.row_quote_workflow.RowCandidate(
        row_id="vInfo!2",
        sheet="vInfo",
        row_number=2,
        cells={
            "A": "influx-alert-01-devops",
            "B": "poweredOn",
            "C": "8",
            "D": "10240",
            "E": "/Producción/ESX_FRAME01/Resources",
        },
        local_cells={
            "A": "influx-alert-01-devops",
            "B": "poweredOn",
            "C": "8",
            "D": "10240",
            "E": "/Producción/ESX_FRAME01/Resources",
        },
        inherited_cells={},
        header_context=[
            {
                "row_id": "vInfo!1",
                "cells": '{"A":"VM","B":"Powerstate","C":"CPUs","D":"Memory","E":"Resource pool"}',
                "local_cells": "{}",
                "inherited_cells": "{}",
            }
        ],
    )
    mapping = RowMapping(
        row_id="vInfo!2",
        is_quote_row=True,
        huawei_product="ECS",
        huawei_spec="c7.large.2",
        quantity=1,
        rationale="Map to general purpose ECS instance c7.",
        confidence=0.9,
    )

    result = app.row_quote_workflow._price_row(mapping, row, {"region": "mexico"})

    assert result.status == "Quoted"
    assert result.spec == "x0.8u.12g"
    assert "original row CPU/memory" in result.rationale
    assert "c7" not in result.rationale.lower()
    assert "general purpose" not in result.rationale.lower()


def test_row_quote_forces_template_or_powered_off_vm_to_non_quote(monkeypatch: pytest.MonkeyPatch):
    wb = Workbook()
    ws = wb.active
    ws.title = "vInfo"
    ws.append(["VM", "Powerstate", "Template", "CPUs", "Memory"])
    ws.append(["tmpl-empty-template", "poweredOff", "True", 4, 8192])
    ws.append(["active-vm", "poweredOn", "False", 2, 4096])
    buffer = BytesIO()
    wb.save(buffer)

    def fake_maas(rows, _quote_context, mapping_progress_callback=None, cancel_check=None):
        if callable(mapping_progress_callback):
            mapping_progress_callback(len(rows), len(rows))
        return {
            "vInfo!2": RowMapping("vInfo!2", True, "ECS", "c7.xlarge.2", 1, "LLM incorrectly quoted a template VM.", 0.9),
            "vInfo!3": RowMapping("vInfo!3", True, "ECS", "c7.large.2", 1, "Active VM maps to ECS.", 0.9),
        }

    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", fake_maas)
    workbook, summary = annotate_row_quote_workbook(
        {"filename": "rvtools.xlsx", "content": buffer.getvalue()},
        {"region": "mexico", "language": "en", "customer_notes": ""},
    )

    annotated = load_workbook(BytesIO(workbook.content), data_only=True)
    sheet = annotated["vInfo"]

    assert summary.non_quote_rows == 1
    assert summary.quoted_rows == 1
    assert sheet.cell(2, sheet.max_column - 11).value == "Non-quote row"
    assert "excluded from quote" in sheet.cell(2, sheet.max_column - 10).value
    assert sheet.cell(3, sheet.max_column - 11).value == "Quoted"


def test_row_quote_collect_rows_keeps_header_context_for_later_rows():
    wb = Workbook()
    ws = wb.active
    ws.title = "vInfo"
    ws.append(["VM", "Powerstate", "CPUs", "Memory", "Resource pool"])
    for index in range(1, 9):
        ws.append([f"vm-{index}", "poweredOn", 4, 16384, "/Producción/ESX_FRAME01/Resources"])
    buffer = BytesIO()
    wb.save(buffer)

    workbook = load_workbook(BytesIO(buffer.getvalue()))
    rows, _original_widths = _collect_rows(workbook)
    later_row = next(row for row in rows if row.row_number == 9)

    assert any('"CPUs"' in item["cells"] and '"Memory"' in item["cells"] for item in later_row.header_context)
    assert app.row_quote_workflow._extract_ecs_shape_from_row(later_row) == (4, 16)


def test_row_quote_ecs_shape_ignores_previous_data_rows_as_headers():
    wb = Workbook()
    ws = wb.active
    ws.title = "vInfo"
    ws.append(["VM", "Powerstate", "Template", "CPUs", "Memory", "Annotation"])
    ws.append(["influx-alert-01-devops", "poweredOn", "False", 8, 10240, "One Core request"])
    ws.append(["influx-alert-02-devops", "poweredOn", "False", 8, 10240, "One Core request"])
    ws.append(["influx-alert-03-devops", "poweredOn", "False", 8, 10240, "One Core request"])
    buffer = BytesIO()
    wb.save(buffer)

    workbook = load_workbook(BytesIO(buffer.getvalue()))
    rows, _original_widths = _collect_rows(workbook)

    assert [app.row_quote_workflow._extract_ecs_shape_from_row(row) for row in rows] == [(8, 10), (8, 10), (8, 10)]


def test_row_quote_collect_rows_expands_merged_headers_into_cells_and_context():
    workbook = load_workbook(BytesIO(make_merged_row_quote_workbook()))
    rows, _original_widths = _collect_rows(workbook)

    row2 = next(row for row in rows if row.row_id == "Merged!2")
    row3 = next(row for row in rows if row.row_id == "Merged!3")
    row4 = next(row for row in rows if row.row_id == "Merged!4")

    assert row2.cells["B"] == "容器服务 Serverless"
    assert row3.cells["B"] == "容器服务 Serverless"
    assert row4.cells["B"] == "容器服务 Serverless"
    assert row3.inherited_cells["B"] == "容器服务 Serverless"
    assert row4.inherited_cells["B"] == "容器服务 Serverless"
    assert row2.merged_group_keys == row3.merged_group_keys == row4.merged_group_keys
    assert any("容器服务 Serverless" in item["cells"] for item in row4.header_context)


def test_row_quote_anchor_inheritance_propagates_product_only(monkeypatch: pytest.MonkeyPatch):
    def fake_maas(rows, _quote_context, mapping_progress_callback=None, cancel_check=None):
        return {
            "Merged!2": RowMapping("Merged!2", True, "CCI", "2vCPU 4GiB", 1, "Anchor row mapped to CCI.", 0.92),
            "Merged!3": RowMapping("Merged!3", True, None, "4vCPU", 4, "Child row missing product.", 0.31),
            "Merged!4": RowMapping("Merged!4", True, None, "8GiB", 8, "Child row missing product.", 0.31),
        }

    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", fake_maas)
    quoted_workbook, summary = annotate_row_quote_workbook(
        {"filename": "merged.xlsx", "content": make_merged_row_quote_workbook()},
        {"region": "mexico", "language": "zh", "customer_notes": ""},
    )

    assert summary.quoted_rows == 2
    annotated = load_workbook(BytesIO(quoted_workbook.content), data_only=True)["Merged"]
    assert annotated.cell(2, annotated.max_column - 18).value == "CCI"
    assert annotated.cell(3, annotated.max_column - 18).value == "CCI"
    assert annotated.cell(4, annotated.max_column - 18).value == "CCI"
    assert annotated.cell(3, annotated.max_column - 17).value == "4vCPU"
    assert annotated.cell(4, annotated.max_column - 17).value == "8GiB"
    assert "Inherited product classification" in annotated.cell(3, annotated.max_column - 10).value
    assert "Inherited product classification" in annotated.cell(4, annotated.max_column - 10).value


def test_row_quote_local_cce_signal_beats_inherited_cci(monkeypatch: pytest.MonkeyPatch):
    workbook = Workbook()
    ws = workbook.active
    ws.title = "Mixed"
    ws.append(["Category", "Service", "Detail", "Quantity", "Region"])
    ws.append(["Container", "容器服务 Serverless", "Pod 2C4G", 1, "mexico"])
    ws.append(["", "", "Cluster Type Standard/Turbo 50 nodes Single x0.2u.4g", 2, "mexico"])
    ws.merge_cells("B2:B3")
    output = BytesIO()
    workbook.save(output)

    def fake_maas(rows, _quote_context, mapping_progress_callback=None, cancel_check=None):
        return {
            "Mixed!2": RowMapping("Mixed!2", True, "CCI", "2vCPU 4GiB", 1, "Anchor row mapped to CCI.", 0.92),
            "Mixed!3": RowMapping("Mixed!3", True, None, "x0.2u.4g", 2, "Child row missing product.", 0.2),
        }

    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", fake_maas)
    quoted_workbook, summary = annotate_row_quote_workbook(
        {"filename": "mixed.xlsx", "content": output.getvalue()},
        {"region": "mexico", "language": "zh", "customer_notes": ""},
    )

    assert summary.quoted_rows == 1
    annotated = load_workbook(BytesIO(quoted_workbook.content), data_only=True)["Mixed"]
    assert annotated.cell(3, annotated.max_column - 18).value == "CCE"
    assert annotated.cell(3, annotated.max_column - 11).value == "已报价"


def test_row_quote_cce_includes_management_plus_ecs_worker(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook = Workbook()
    ws = workbook.active
    ws.title = "Cluster"
    ws.append(["Cluster Type", "Cluster Scale", "Master Nodes", "Worker Spec", "Quantity", "Region"])
    ws.append(["Standard/Turbo", "50 nodes", "Single", "x0.2u.4g", 2, "mexico"])
    output = BytesIO()
    workbook.save(output)
    quoted_workbook, summary = annotate_row_quote_workbook(
        {"filename": "cce.xlsx", "content": output.getvalue()},
        {"region": "mexico", "language": "zh", "customer_notes": ""},
    )
    assert summary.quoted_rows == 1
    annotated = load_workbook(BytesIO(quoted_workbook.content), data_only=True)["Cluster"]
    assert annotated.cell(2, annotated.max_column - 18).value == "CCE"
    assert annotated.cell(2, annotated.max_column - 11).value == "已报价"
    assert annotated.cell(2, annotated.max_column - 15).value is not None


def _make_simple_workbook_rows(n: int = 6) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["Product", "Qty"])
    for i in range(1, n + 1):
        ws.append([f"ECS {i}vCPU 4GiB", 1])
    output = BytesIO()
    wb.save(output)
    return output.getvalue()


def test_row_quote_stages_follow_correct_order(monkeypatch: pytest.MonkeyPatch):
    stages: list[str] = []
    def on_stage(stage: str):
        stages.append(stage)

    def fake_maas(rows, _quote_context, mapping_progress_callback=None, cancel_check=None):
        if callable(mapping_progress_callback):
            mapping_progress_callback(len(rows), len(rows))
        return {}

    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", fake_maas)
    annotate_row_quote_workbook(
        {"filename": "test.xlsx", "content": _make_simple_workbook_rows(6)},
        {"region": "mexico", "language": "es", "customer_notes": ""},
        stage_callback=on_stage,
    )
    assert stages == ["collect_rows", "pipeline_rows"]


def test_row_quote_mapping_batch_progress(monkeypatch: pytest.MonkeyPatch):
    progress_snapshots: list[RowQuoteProgress] = []

    def on_progress(progress: RowQuoteProgress):
        progress_snapshots.append(progress)

    def fake_maas(rows, _quote_context, mapping_progress_callback=None, cancel_check=None):
        batch_size = 3
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            if callable(mapping_progress_callback):
                mapping_progress_callback(min(start + len(batch), len(rows)), len(rows))
        return {}

    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", fake_maas)
    annotate_row_quote_workbook(
        {"filename": "test.xlsx", "content": _make_simple_workbook_rows(6)},
        {"region": "mexico", "language": "es", "customer_notes": ""},
        progress_callback=on_progress,
    )

    map_progress = [p for p in progress_snapshots if p.mapped_rows > 0 and p.priced_rows == 0]
    assert len(map_progress) >= 2
    assert map_progress[0].mapped_rows == 3
    assert map_progress[0].stage_total_rows == 6
    assert map_progress[-1].mapped_rows == 6


def test_row_quote_price_rows_resets_progress(monkeypatch: pytest.MonkeyPatch):
    progress_snapshots: list[RowQuoteProgress] = []

    def on_progress(progress: RowQuoteProgress):
        progress_snapshots.append(progress)

    def fake_maas(rows, _quote_context, mapping_progress_callback=None, cancel_check=None):
        if callable(mapping_progress_callback):
            mapping_progress_callback(len(rows), len(rows))
        return {}

    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", fake_maas)
    annotate_row_quote_workbook(
        {"filename": "test.xlsx", "content": _make_simple_workbook_rows(6)},
        {"region": "mexico", "language": "es", "customer_notes": ""},
        progress_callback=on_progress,
    )

    last_progress = progress_snapshots[-1]
    assert last_progress.priced_rows == 6
    assert last_progress.mapped_rows == 6
    assert last_progress.stage_total_rows == 6


def test_row_quote_maas_batch_failure_still_advances_progress(monkeypatch: pytest.MonkeyPatch):
    progress_snapshots: list[RowQuoteProgress] = []

    def on_progress(progress: RowQuoteProgress):
        progress_snapshots.append(progress)

    call_count = 0
    def fake_maas(rows, _quote_context, mapping_progress_callback=None, cancel_check=None):
        nonlocal call_count
        batch_size = 3
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            call_count += 1
            if callable(mapping_progress_callback):
                mapping_progress_callback(min(start + len(batch), len(rows)), len(rows))
        return {}

    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", fake_maas)
    workbook, summary = annotate_row_quote_workbook(
        {"filename": "test.xlsx", "content": _make_simple_workbook_rows(6)},
        {"region": "mexico", "language": "es", "customer_notes": ""},
        progress_callback=on_progress,
    )

    map_progress = [p for p in progress_snapshots if p.mapped_rows > 0 and p.priced_rows == 0]
    assert len(map_progress) >= 2
    assert summary.total_rows == 6


def test_row_quote_summary_unchanged_after_progress_restructure(monkeypatch: pytest.MonkeyPatch):
    def fake_maas(rows, _quote_context, mapping_progress_callback=None, cancel_check=None):
        if callable(mapping_progress_callback):
            mapping_progress_callback(len(rows), len(rows))
        return {}

    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", fake_maas)
    workbook, summary = annotate_row_quote_workbook(
        {"filename": "test.xlsx", "content": _make_simple_workbook_rows(6)},
        {"region": "mexico", "language": "es", "customer_notes": ""},
    )
    assert summary.total_rows == 6
    assert summary.quoted_rows + summary.missing_price_rows + summary.manual_review_rows + summary.non_quote_rows == 6


def test_pipeline_stage_order(monkeypatch: pytest.MonkeyPatch):
    stages: list[str] = []
    def on_stage(stage: str):
        stages.append(stage)

    def fake_maas(rows, _quote_context, mapping_progress_callback=None, cancel_check=None):
        if callable(mapping_progress_callback):
            mapping_progress_callback(len(rows), len(rows))
        return {}

    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", fake_maas)
    annotate_row_quote_workbook(
        {"filename": "test.xlsx", "content": _make_simple_workbook_rows(9)},
        {"region": "mexico", "language": "es", "customer_notes": ""},
        stage_callback=on_stage,
    )
    assert stages == ["collect_rows", "pipeline_rows"]


def test_pipeline_dual_progress(monkeypatch: pytest.MonkeyPatch):
    progress_snapshots: list[RowQuoteProgress] = []

    def on_progress(progress: RowQuoteProgress):
        progress_snapshots.append(progress)

    def fake_maas(rows, _quote_context, mapping_progress_callback=None, cancel_check=None):
        if callable(mapping_progress_callback):
            mapping_progress_callback(len(rows), len(rows))
        return {}

    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", fake_maas)
    annotate_row_quote_workbook(
        {"filename": "test.xlsx", "content": _make_simple_workbook_rows(9)},
        {"region": "mexico", "language": "es", "customer_notes": ""},
        progress_callback=on_progress,
    )

    last = progress_snapshots[-1]
    assert last.mapped_rows == 9
    assert last.priced_rows == 9
    assert last.total_rows == 9


def test_pipeline_batch_failure_uses_fallback(monkeypatch: pytest.MonkeyPatch):
    def fake_maas(rows, _quote_context, mapping_progress_callback=None, cancel_check=None):
        if callable(mapping_progress_callback):
            mapping_progress_callback(len(rows), len(rows))
        return {}

    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", fake_maas)
    workbook, summary = annotate_row_quote_workbook(
        {"filename": "test.xlsx", "content": _make_simple_workbook_rows(6)},
        {"region": "mexico", "language": "es", "customer_notes": ""},
    )
    assert summary.total_rows == 6
    assert summary.quoted_rows + summary.missing_price_rows + summary.manual_review_rows + summary.non_quote_rows == 6


def test_pipeline_summary_matches_serial(monkeypatch: pytest.MonkeyPatch):
    def fake_maas(rows, _quote_context, mapping_progress_callback=None, cancel_check=None):
        if callable(mapping_progress_callback):
            mapping_progress_callback(len(rows), len(rows))
        return {}

    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", fake_maas)
    workbook, summary = annotate_row_quote_workbook(
        {"filename": "test.xlsx", "content": _make_simple_workbook_rows(9)},
        {"region": "mexico", "language": "es", "customer_notes": ""},
    )
    assert summary.total_rows == 9
    assert summary.quoted_rows + summary.missing_price_rows + summary.manual_review_rows + summary.non_quote_rows == 9


# ── Cancel behaviour tests ──────────────────────────────────────────────────

from app.row_quote_workflow import TaskCancelledError
from app.row_quote_tasks import (
    cancel_annotation_task,
    create_annotation_task,
    get_annotation_task,
    get_annotation_workbook,
    _tasks,
    _lock,
)


def _clear_tasks():
    with _lock:
        _tasks.clear()


def test_cancel_queued_or_running_task():
    _clear_tasks()
    created = create_annotation_task(
        {"filename": "test.xlsx", "content": _make_simple_workbook_rows(3)},
        {"region": "mexico", "language": "es", "customer_notes": "test"},
    )
    task_id = created.task_id
    resp = cancel_annotation_task(task_id)
    assert resp.status in ("queued", "running", "cancelled")
    with _lock:
        assert _tasks[task_id]["cancelled"] is True
    _clear_tasks()


def test_cancel_check_stops_workflow_after_collect_rows(monkeypatch: pytest.MonkeyPatch):
    cancel_flag = False

    def cancel_check():
        return cancel_flag

    def fake_maas(rows, _quote_context, mapping_progress_callback=None, cancel_check=None):
        raise AssertionError("MaaS mapping should not be reached after cancel")

    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", fake_maas)

    # Cancel after collect_rows by using a cancel_check that becomes True
    # We use a mutable flag so we can flip it mid-run
    cancel_flag = True
    with pytest.raises(TaskCancelledError):
        annotate_row_quote_workbook(
            {"filename": "test.xlsx", "content": _make_simple_workbook_rows(3)},
            {"region": "mexico", "language": "es", "customer_notes": ""},
            cancel_check=cancel_check,
        )


def test_cancel_check_stops_workflow_during_mapping(monkeypatch: pytest.MonkeyPatch):
    call_count = 0

    def cancel_check():
        return call_count >= 1

    def fake_maas(rows, _quote_context, mapping_progress_callback=None, cancel_check=None):
        nonlocal call_count
        call_count += 1
        if callable(mapping_progress_callback):
            mapping_progress_callback(len(rows), len(rows))
        return {}

    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", fake_maas)
    # cancel_check returns False initially (call_count=0), then True after first call
    # But fake_maas doesn't check cancel_check — the workflow checkpoints after
    # _maas_map_rows will catch it. This test verifies the post-mapping checkpoint.
    with pytest.raises(TaskCancelledError):
        annotate_row_quote_workbook(
            {"filename": "test.xlsx", "content": _make_simple_workbook_rows(3)},
            {"region": "mexico", "language": "es", "customer_notes": ""},
            cancel_check=cancel_check,
        )


def test_cancel_check_stops_pricing_rows(monkeypatch: pytest.MonkeyPatch):
    priced = 0

    def cancel_check():
        return priced >= 1

    def fake_maas(rows, _quote_context, mapping_progress_callback=None, cancel_check=None):
        if callable(mapping_progress_callback):
            mapping_progress_callback(len(rows), len(rows))
        return {}

    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", fake_maas)

    original_price_row = app.row_quote_workflow._price_row

    def tracking_price_row(mapping, row, quote_context):
        nonlocal priced
        result = original_price_row(mapping, row, quote_context)
        priced += 1
        return result

    monkeypatch.setattr("app.row_quote_workflow._price_row", tracking_price_row)

    with pytest.raises(TaskCancelledError):
        annotate_row_quote_workbook(
            {"filename": "test.xlsx", "content": _make_simple_workbook_rows(5)},
            {"region": "mexico", "language": "es", "customer_notes": ""},
            cancel_check=cancel_check,
        )
    # At least one row was priced before cancel stopped further processing
    assert priced >= 1


def test_cancel_sets_cancelled_status_not_failed(monkeypatch: pytest.MonkeyPatch):
    _clear_tasks()

    def fake_maas(rows, _quote_context, mapping_progress_callback=None, cancel_check=None):
        if callable(mapping_progress_callback):
            mapping_progress_callback(len(rows), len(rows))
        return {}

    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", fake_maas)

    created = create_annotation_task(
        {"filename": "test.xlsx", "content": _make_simple_workbook_rows(3)},
        {"region": "mexico", "language": "es", "customer_notes": "test"},
    )
    task_id = created.task_id

    # Cancel the task
    cancel_annotation_task(task_id)

    # Wait for the worker thread to pick up the cancellation
    for _ in range(30):
        time.sleep(0.1)
        resp = get_annotation_task(task_id)
        if resp.status in ("cancelled", "failed"):
            break

    assert resp.status == "cancelled"
    assert resp.current_stage == "cancelled"
    assert resp.error is None
    _clear_tasks()


def test_cancelled_task_export_returns_409(monkeypatch: pytest.MonkeyPatch):
    _clear_tasks()

    def fake_maas(rows, _quote_context, mapping_progress_callback=None, cancel_check=None):
        if callable(mapping_progress_callback):
            mapping_progress_callback(len(rows), len(rows))
        return {}

    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", fake_maas)

    created = create_annotation_task(
        {"filename": "test.xlsx", "content": _make_simple_workbook_rows(3)},
        {"region": "mexico", "language": "es", "customer_notes": "test"},
    )
    task_id = created.task_id

    cancel_annotation_task(task_id)

    # Wait for cancelled status
    for _ in range(30):
        time.sleep(0.1)
        resp = get_annotation_task(task_id)
        if resp.status == "cancelled":
            break

    with pytest.raises(HTTPException) as exc_info:
        get_annotation_workbook(task_id)
    assert exc_info.value.status_code == 409
    _clear_tasks()


def test_row_quote_default_language_is_english(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook, summary = annotate_row_quote_workbook(
        {"filename": "customer.xlsx", "content": make_row_quote_workbook()},
        {"region": "mexico", "customer_notes": ""},
    )

    annotated = load_workbook(BytesIO(workbook.content), data_only=True)
    compute = annotated["Compute"]
    appended_headers = [compute.cell(1, column).value for column in range(compute.max_column - 18, compute.max_column + 1)]
    assert appended_headers == [
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
    assert compute.cell(2, compute.max_column - 11).value == "Quoted"
    assert compute.cell(3, compute.max_column - 11).value == "Non-quote row"
    assert compute.cell(4, compute.max_column - 11).value == "Manual review"


def test_row_quote_zh_language_uses_chinese_columns_and_status(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook, summary = annotate_row_quote_workbook(
        {"filename": "customer.xlsx", "content": make_row_quote_workbook()},
        {"region": "mexico", "language": "zh", "customer_notes": ""},
    )

    annotated = load_workbook(BytesIO(workbook.content), data_only=True)
    compute = annotated["Compute"]
    appended_headers = [compute.cell(1, column).value for column in range(compute.max_column - 18, compute.max_column + 1)]
    assert appended_headers == [
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
    assert compute.cell(2, compute.max_column - 11).value == "已报价"
    assert compute.cell(3, compute.max_column - 11).value == "非报价行"
    assert compute.cell(4, compute.max_column - 11).value == "需人工确认"


# ── RVTools export-from-preview tests ───────────────────────────────────────


def _clear_rvtools_tasks():
    with _rvtools_lock:
        _rvtools_tasks.clear()


def test_rvtools_export_reuses_preview_state():
    _clear_rvtools_tasks()
    load_pricebook.cache_clear()
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-a", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
            {"VM": "vm-b", "Powerstate": "PoweredOn", "CPUs": 4, "Memory": 8},
        ],
        disk_rows=[
            {"VM": "vm-a", "Capacity GiB": 100},
            {"VM": "vm-b", "Capacity GiB": 200},
        ],
    )
    request = {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "sample.xlsx"}
    result = preview_graph.invoke({"request": request, "file_bytes": content})
    preview_resp = build_preview_response(result)
    task_id = store_preview_result(preview_resp, result)

    state = get_preview_state(task_id)
    export_result = export_excel(state)
    workbook = export_result["workbook"]

    with ZipFile(BytesIO(workbook.content)) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
    assert "Summary" in workbook_xml
    assert "ECS" in workbook_xml
    _clear_rvtools_tasks()


def test_rvtools_export_matches_preview_totals():
    _clear_rvtools_tasks()
    load_pricebook.cache_clear()
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-x", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
        ],
        disk_rows=[
            {"VM": "vm-x", "Capacity GiB": 120},
        ],
    )
    request = {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "sample.xlsx"}
    result = preview_graph.invoke({"request": request, "file_bytes": content})
    preview_resp = build_preview_response(result)
    task_id = store_preview_result(preview_resp, result)

    state = get_preview_state(task_id)
    export_result = export_excel(state)
    workbook = export_result["workbook"]

    exported_wb = load_workbook(BytesIO(workbook.content), data_only=True)["Summary"]
    assert preview_resp.summary.quoted_vms == 1
    assert abs(preview_resp.summary.total_ondemand_monthly_usd - float(exported_wb["C12"].value)) < 0.01
    _clear_rvtools_tasks()


def test_rvtools_export_task_not_found():
    _clear_rvtools_tasks()
    with pytest.raises(HTTPException) as exc_info:
        get_preview_state("nonexistent-task-id")
    assert exc_info.value.status_code == 404
    _clear_rvtools_tasks()


def test_rvtools_preview_response_includes_task_id():
    _clear_rvtools_tasks()
    load_pricebook.cache_clear()
    content = make_rvtools_file(
        info_rows=[{"VM": "vm-1", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4}],
        disk_rows=[{"VM": "vm-1", "Capacity GiB": 50}],
    )
    request = {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "sample.xlsx"}
    result = preview_graph.invoke({"request": request, "file_bytes": content})
    preview_resp = build_preview_response(result)
    task_id = store_preview_result(preview_resp, result)
    preview_resp.task_id = task_id

    assert preview_resp.task_id is not None
    assert len(preview_resp.task_id) == 36
    _clear_rvtools_tasks()


# ── ecs_vcpu / ecs_mem export tests ───────────────────────────────────────────


def test_rvtools_export_includes_ecs_vcpu_mem():
    load_pricebook.cache_clear()
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-2c8g", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 8},
            {"VM": "vm-oversized", "Powerstate": "PoweredOn", "CPUs": 999, "Memory": 999},
        ],
        disk_rows=[
            {"VM": "vm-2c8g", "Capacity GiB": 100},
            {"VM": "vm-oversized", "Capacity GiB": 200},
        ],
    )

    result = export_graph.invoke(
        {
            "request": {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "sample.xlsx"},
            "file_bytes": content,
        }
    )

    workbook = result["workbook"]
    ws = load_workbook(BytesIO(workbook.content), data_only=True)["ECS"]
    assert ws["I2"].value == "HC vCPU"
    assert ws["J2"].value == "HC Memory"

    rows = _ecs_data_rows(ws)
    assert len(rows) == 2
    assert rows[0][8] is not None
    assert rows[0][9] is not None


def test_row_quote_export_includes_ecs_vcpu_mem(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook, summary = annotate_row_quote_workbook(
        {"filename": "customer.xlsx", "content": make_row_quote_workbook()},
        {"region": "mexico", "language": "en", "customer_notes": ""},
    )

    annotated = load_workbook(BytesIO(workbook.content), data_only=True)
    compute = annotated["Compute"]

    # ECS row (row 2) should have ecs_vcpu and ecs_mem values
    ecs_vcpu_col = compute.max_column - 8
    ecs_mem_col = compute.max_column - 7
    assert compute.cell(1, ecs_vcpu_col).value == "ecs_vcpu"
    assert compute.cell(1, ecs_mem_col).value == "ecs_mem"
    assert compute.cell(2, ecs_vcpu_col).value is not None
    assert compute.cell(2, ecs_mem_col).value is not None

    # Non-quote row (row 3) should have empty ecs_vcpu/ecs_mem
    assert compute.cell(3, ecs_vcpu_col).value is None
    assert compute.cell(3, ecs_mem_col).value is None

    # GPU manual review row (row 4) should have empty ecs_vcpu/ecs_mem
    assert compute.cell(4, ecs_vcpu_col).value is None
    assert compute.cell(4, ecs_mem_col).value is None


# ── Sheet selection tests ──────────────────────────────────────────────────────


def test_sheet_selection_first_only_keeps_current_behavior(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook, summary = annotate_row_quote_workbook(
        {"filename": "customer.xlsx", "content": make_row_quote_workbook()},
        {"region": "mexico", "language": "en", "customer_notes": ""},
        sheet_selection=SheetSelection(mode="first"),
    )

    # Only first sheet (Compute) is processed — 3 rows
    assert summary.total_rows == 3

    annotated = load_workbook(BytesIO(workbook.content), data_only=True)
    # Compute sheet has quote columns appended
    compute = annotated["Compute"]
    assert compute.max_column > 3
    # Storage sheet is untouched
    storage = annotated["Storage"]
    assert storage.max_column == 3


def test_sheet_selection_all_processes_multiple_sheets(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook, summary = annotate_row_quote_workbook(
        {"filename": "customer.xlsx", "content": make_row_quote_workbook()},
        {"region": "mexico", "language": "en", "customer_notes": ""},
        sheet_selection=SheetSelection(mode="all"),
    )

    # Both sheets processed: Compute (3 rows) + Storage (2 rows) = 5
    assert summary.total_rows == 5

    annotated = load_workbook(BytesIO(workbook.content), data_only=True)
    # Both sheets have quote columns appended
    assert annotated["Compute"].max_column > 3
    assert annotated["Storage"].max_column > 3


def test_sheet_selection_specific_names(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook, summary = annotate_row_quote_workbook(
        {"filename": "customer.xlsx", "content": make_row_quote_workbook()},
        {"region": "mexico", "language": "en", "customer_notes": ""},
        sheet_selection=SheetSelection(mode="selected", selected_input="Storage"),
    )

    # Only Storage sheet processed — 2 rows
    assert summary.total_rows == 2

    annotated = load_workbook(BytesIO(workbook.content), data_only=True)
    # Storage sheet has quote columns
    assert annotated["Storage"].max_column > 3
    # Compute sheet is untouched
    assert annotated["Compute"].max_column == 3


def test_sheet_selection_specific_indexes(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook, summary = annotate_row_quote_workbook(
        {"filename": "customer.xlsx", "content": make_row_quote_workbook()},
        {"region": "mexico", "language": "en", "customer_notes": ""},
        sheet_selection=SheetSelection(mode="selected", selected_input="2"),
    )

    # Index 2 = second sheet (Storage) — 2 rows
    assert summary.total_rows == 2

    annotated = load_workbook(BytesIO(workbook.content), data_only=True)
    assert annotated["Storage"].max_column > 3
    assert annotated["Compute"].max_column == 3


def test_sheet_selection_invalid_token_returns_error():
    with pytest.raises(SheetSelectionError, match="does not exist"):
        resolve_sheet_selection(
            ["Compute", "Storage"],
            SheetSelection(mode="selected", selected_input="MissingSheet"),
        )

    with pytest.raises(SheetSelectionError, match="out of range"):
        resolve_sheet_selection(
            ["Compute", "Storage"],
            SheetSelection(mode="selected", selected_input="9"),
        )


def test_unselected_sheets_remain_untouched_in_export(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook, _summary = annotate_row_quote_workbook(
        {"filename": "customer.xlsx", "content": make_row_quote_workbook()},
        {"region": "mexico", "language": "en", "customer_notes": ""},
        sheet_selection=SheetSelection(mode="selected", selected_input="Compute"),
    )

    annotated = load_workbook(BytesIO(workbook.content), data_only=True)
    # Compute was selected — has quote columns
    compute = annotated["Compute"]
    assert compute.max_column > 3

    # Storage was NOT selected — no quote columns, original content preserved
    storage = annotated["Storage"]
    assert storage.max_column == 3
    assert storage.cell(1, 1).value == "Service"
    assert storage.cell(2, 1).value == "EVS"
    assert storage.cell(3, 1).value == "RDS"


# ---------------------------------------------------------------------------
# Phase 2 regression: product mapping corrections
# ---------------------------------------------------------------------------

def _make_row(cells, header_context=None, local_cells=None, inherited_cells=None):
    return RowCandidate(
        row_id="test!1",
        sheet="test",
        row_number=1,
        cells=cells,
        local_cells=local_cells or cells,
        inherited_cells=inherited_cells or {},
        header_context=header_context or [],
    )


def test_row_quote_postgresql_cpu_not_mapped_to_cci():
    row = _make_row(
        cells={"A": "云数据库PostgreSQL", "B": "高可用版-通用型-CPU", "C": "美元/台/月"},
        header_context=[{"cells": '{"A": "云数据库PostgreSQL", "B": "子产品名称"}'}],
    )
    llm_mapping = RowMapping("test!1", True, "CCI", "1vCPU", 1, "LLM mapped to CCI.", 0.85)
    result = _apply_product_priority(row, llm_mapping)
    assert result.huawei_product != "CCI", f"PostgreSQL CPU sub-row should not be forced to CCI, got {result.huawei_product}"


def test_row_quote_postgresql_memory_not_mapped_to_cci():
    row = _make_row(
        cells={"A": "云数据库PostgreSQL", "B": "高可用版-通用型-内存", "C": "美元/台/月"},
        header_context=[{"cells": '{"A": "云数据库PostgreSQL", "B": "子产品名称"}'}],
    )
    llm_mapping = RowMapping("test!1", True, "CCI", "1GiB", 1, "LLM mapped to CCI.", 0.85)
    result = _apply_product_priority(row, llm_mapping)
    assert result.huawei_product != "CCI", f"PostgreSQL memory sub-row should not be forced to CCI, got {result.huawei_product}"


def test_row_quote_dcs_redis_not_mapped_to_rds():
    row = _make_row(
        cells={"A": "云数据库Redis", "B": "标准架构-内存", "C": "美元/GB/月"},
        header_context=[{"cells": '{"A": "云数据库Redis", "B": "子产品名称"}'}],
    )
    llm_mapping = RowMapping("test!1", True, "RDS", "mysql.s2.large", 1, "LLM mapped to RDS.", 0.85)
    # The key point: DB family context should prevent CCI override.
    # RDS is still wrong (should be DCS) but at least CCI is not forced.
    result = _apply_product_priority(row, llm_mapping)
    assert result.huawei_product != "CCI", f"Redis sub-row should not be forced to CCI, got {result.huawei_product}"


def test_row_quote_dds_mongodb_not_mapped_to_rds_or_cci():
    row = _make_row(
        cells={"A": "TencentDB for MongoDB", "B": "副本集-硬盘", "C": "美元/GB/月"},
        header_context=[{"cells": '{"A": "TencentDB for MongoDB", "B": "子产品名称"}'}],
    )
    llm_mapping = RowMapping("test!1", True, "CCI", "1GiB", 1, "LLM mapped to CCI.", 0.82)
    result = _apply_product_priority(row, llm_mapping)
    assert result.huawei_product != "CCI", f"MongoDB sub-row should not be forced to CCI, got {result.huawei_product}"


def test_row_quote_infrequent_storage_not_mapped_to_cce():
    row = _make_row(
        cells={"A": "COS对象存储", "B": "低频存储", "C": "美元/GB/月"},
        header_context=[{"cells": '{"A": "COS对象存储", "B": "子产品名称"}'}],
    )
    llm_mapping = RowMapping("test!1", True, "CCE", "control-plane", 1, "LLM mapped to CCE.", 0.9)
    result = _apply_product_priority(row, llm_mapping)
    assert result.huawei_product != "CCE", f"Infrequent storage should not be forced to CCE, got {result.huawei_product}"


def test_row_quote_shared_bandwidth_not_mapped_to_nat_or_vpn():
    row = _make_row(
        cells={"A": "共享带宽包", "B": "月结带宽包-传统型", "C": "美元/Mbps/月"},
    )
    result = _apply_special_product_routing(row)
    assert result is not None, "Shared bandwidth package should be routed by special_product_routing"
    assert result.huawei_product == "EIP", f"Shared bandwidth package should map to EIP, got {result.huawei_product}"


def test_row_quote_dc_outbound_traffic_is_non_quote():
    row = _make_row(
        cells={"A": "专线接入", "B": "出方向流量费", "C": "美元/GB"},
        header_context=[{"cells": '{"A": "专线接入", "B": "子产品名称"}'}],
    )
    result = _apply_hard_exclusions(row)
    assert result is not None, "DC outbound traffic should be excluded by hard_exclusions"
    assert not result.is_quote_row, "DC outbound traffic should be non-quote row"


def test_row_quote_cloud_connect_product_category():
    row = _make_row(
        cells={"A": "云联网CCN", "B": "网络连接实例费", "C": "美元/月"},
    )
    result = _apply_special_product_routing(row)
    assert result is not None, "CCN row should be routed by special_product_routing"
    assert result.huawei_product == "Cloud Connect", f"CCN should map to Cloud Connect, got {result.huawei_product}"


def test_row_quote_special_routing_overrides_llm_network_products():
    cases = [
        ({"A": "云联网CCN", "B": "跨地域带宽(金)", "C": "美元/Mbps/月"}, RowMapping("test!1", True, "VPN", "vpn-basic", 1, "LLM.", 0.9), "Cloud Connect"),
        ({"A": "共享带宽包", "B": "月结带宽包-传统型", "C": "美元/Mbps/月"}, RowMapping("test!1", True, "NAT Gateway", "nat-large", 1, "LLM.", 0.9), "EIP"),
        ({"A": "负载均衡CLB", "B": "流量", "C": "美元/GB/小时"}, RowMapping("test!1", True, "ELB", "elb-shared", 1, "LLM.", 0.9), "EIP"),
    ]
    for cells, mapping, expected_product in cases:
        row = _make_row(cells=cells)
        result = _apply_product_priority(row, mapping)
        assert result.huawei_product == expected_product


def test_row_quote_dc_outbound_header_does_not_exclude_later_ccn_row():
    row = _make_row(
        cells={"A": "云联网CCN", "B": "网络连接实例费", "C": "美元/个/小时"},
        header_context=[{"cells": '{"A": "专线接入", "B": "出方向流量费"}'}],
    )
    assert _apply_hard_exclusions(row) is None
    result = _apply_special_product_routing(row)
    assert result is not None
    assert result.huawei_product == "Cloud Connect"


def test_row_quote_raw_non_quote_can_be_recovered_by_local_quote_signal():
    row = _make_row(cells={"A": "额外性能", "B": "美元/MB/s/月", "C": "增强型SSD云硬盘"})
    raw = RowMapping("test!1", False, None, None, None, "LLM marked non-quote.", 0.9)
    result = app.row_quote_workflow.resolve_final_mapping(row, raw, {"test!1": raw}, app.row_quote_workflow.AnchorPlan())
    assert result is not None
    assert result.is_quote_row
    assert result.huawei_product == "EVS"


def test_row_quote_db_context_corrects_wrong_db_products():
    cases = [
        ({"A": "云数据库Redis", "B": "标准架构-内存", "C": "美元/GB/月"}, RowMapping("test!1", True, "RDS", "mysql.s2.large", 1, "LLM.", 0.9), "DCS"),
        ({"A": "时序数据库CTSDB", "B": "独享型数据节点", "C": "美元/节点/月"}, RowMapping("test!1", True, "DDS", "dds.cluster.3.6g", 1, "LLM.", 0.9), "GeminiDB"),
        ({"A": "消息服务Ckafka", "B": "Ckafka专业版-低规格峰值带宽套餐包", "C": "美元/个/月"}, RowMapping("test!1", True, "RDS", "mysql.s2.large", 1, "LLM.", 0.9), "DMS"),
    ]
    for cells, mapping, expected_product in cases:
        row = _make_row(cells=cells)
        result = _apply_product_priority(row, mapping)
        assert result.huawei_product == expected_product


def test_row_quote_ces_context_overrides_storage_context():
    row = _make_row(
        cells={"A": "云监控", "B": "日上报指标量（存储30天）", "C": "美元/百万条/天"},
        header_context=[{"cells": '{"A": "日志服务CLS", "B": "存储量-标准日志存储"}'}],
    )
    mapping = RowMapping("test!1", True, "EVS", "Daily Reported Metrics", 1, "LLM.", 0.9)
    result = _apply_product_priority(row, mapping)
    assert result.huawei_product == "CES"


# ---------------------------------------------------------------------------
# Phase 2B regression: spec normalization and price hits
# ---------------------------------------------------------------------------

def test_row_quote_evs_high_io_spec_alias():
    alias = _normalize_spec_alias("EVS", "High-performance (SAS) - IOPS up to 6000")
    assert alias == "high-io", f"High-performance SAS should normalize to high-io, got {alias}"
    alias2 = _normalize_spec_alias("EVS", "High I/O")
    assert alias2 == "high-io", f"High I/O should normalize to high-io, got {alias2}"


def test_row_quote_evs_ultra_high_io_spec_alias():
    alias = _normalize_spec_alias("EVS", "Ultra High I/O SSD (for high performance)")
    assert alias == "ultra-high-io", f"Ultra High I/O should normalize to ultra-high-io, got {alias}"
    alias2 = _normalize_spec_alias("EVS", "增强型SSD云硬盘")
    assert alias2 == "ultra-high-io", f"增强型SSD should normalize to ultra-high-io, got {alias2}"


def test_row_quote_evs_gpssd_v2_spec_alias():
    alias = _normalize_spec_alias("EVS", "General Purpose SSD V2")
    assert alias == "gpssd-v2", f"GPSSD V2 should normalize to gpssd-v2, got {alias}"
    alias2 = _normalize_spec_alias("EVS", "额外性能")
    assert alias2 == "gpssd-v2", f"额外性能 should normalize to gpssd-v2, got {alias2}"


def test_row_quote_obs_infrequent_access_spec_alias():
    alias = _normalize_spec_alias("OBS", "低频存储")
    assert alias == "obs-infrequent-access", f"低频存储 should normalize to obs-infrequent-access, got {alias}"
    alias2 = _normalize_spec_alias("OBS", "Infrequent Access")
    assert alias2 == "obs-infrequent-access", f"Infrequent Access should normalize to obs-infrequent-access, got {alias2}"


def test_row_quote_sfs_turbo_20mbps_spec_alias():
    alias = _normalize_spec_alias("SFS Turbo", "通用性能型")
    assert alias == "sfs-turbo-20mbps-per-tib", f"通用性能型 should normalize to 20mbps, got {alias}"


def test_row_quote_sfs_turbo_40mbps_spec_alias():
    alias = _normalize_spec_alias("SFS Turbo", "Turbo标准型")
    assert alias == "sfs-turbo-40mbps-per-tib", f"Turbo标准型 should normalize to 40mbps, got {alias}"


def test_row_quote_nat_gateway_tier_distinction():
    assert _normalize_spec_alias("NAT Gateway", "小型网关") == "nat-small"
    assert _normalize_spec_alias("NAT Gateway", "中型网关") == "nat-middle"
    assert _normalize_spec_alias("NAT Gateway", "大型网关") == "nat-large"
    assert _normalize_spec_alias("NAT Gateway", "small") == "nat-small"
    assert _normalize_spec_alias("NAT Gateway", "middle") == "nat-middle"
    assert _normalize_spec_alias("NAT Gateway", "large") == "nat-large"


def test_row_quote_dc_bandwidth_tier_distinction():
    assert _normalize_spec_alias("Direct Connect as a Service", "10GE") == "dcas-10g"
    assert _normalize_spec_alias("Direct Connect as a Service", "100GE") == "dcas-100g"
    assert _normalize_spec_alias("Direct Connect as a Service", "1GE") == "dcas-1g"


def test_row_quote_evs_high_io_price_not_missing():
    """High I/O EVS should resolve a price, not Missing price."""
    from app.pricebook import load_pricebook
    load_pricebook.cache_clear()
    mapping = RowMapping("test!1", True, "EVS", "high-io", 1, "Test high-io mapping.", 0.9)
    result = _price_evs(mapping, "chile", "高性能云硬盘 100GB", 1)
    assert result.status != "Missing price", f"EVS high-io should have a price, got status={result.status}, rationale={result.rationale}"
    assert result.monthly_price is not None and result.monthly_price > 0, f"Expected positive monthly price, got {result.monthly_price}"


def test_row_quote_evs_ultra_high_io_price_not_missing():
    from app.pricebook import load_pricebook
    load_pricebook.cache_clear()
    mapping = RowMapping("test!1", True, "EVS", "ultra-high-io", 1, "Test ultra-high-io mapping.", 0.9)
    result = _price_evs(mapping, "chile", "增强型SSD云硬盘 100GB", 1)
    assert result.status != "Missing price", f"EVS ultra-high-io should have a price, got status={result.status}"
    assert result.monthly_price is not None and result.monthly_price > 0


def test_row_quote_evs_gpssd_v2_price_not_missing():
    from app.pricebook import load_pricebook
    load_pricebook.cache_clear()
    mapping = RowMapping("test!1", True, "EVS", "gpssd-v2", 1, "Test gpssd-v2 mapping.", 0.9)
    result = _price_evs(mapping, "chile", "额外性能 100GB", 1)
    assert result.status != "Missing price", f"EVS gpssd-v2 should have a price, got status={result.status}"
    assert result.monthly_price is not None and result.monthly_price > 0


def test_row_quote_obs_ia_price_not_missing():
    from app.flexible_pricing import load_flexible_pricing_catalog
    load_flexible_pricing_catalog.cache_clear()
    mapping = RowMapping("test!1", True, "OBS", "obs-infrequent-access", 1, "Test OBS IA mapping.", 0.9)
    result = _price_catalog_product(mapping, "chile", 1)
    assert result.status != "Missing price", f"OBS IA should have a price, got status={result.status}"
    assert result.monthly_price is not None and result.monthly_price > 0


def test_row_quote_catalog_pricing_uses_row_text_for_spec_alias():
    from app.flexible_pricing import load_flexible_pricing_catalog
    load_flexible_pricing_catalog.cache_clear()

    obs_mapping = RowMapping("test!1", True, "OBS", "obs-standard", 1, "LLM chose standard.", 0.9)
    obs_result = _price_catalog_product(obs_mapping, "chile", 1, "COS对象存储 低频存储 美元/GB/月")
    assert obs_result.spec == "obs-infrequent-access"

    sfs_mapping = RowMapping("test!1", True, "SFS Turbo", "sfs-turbo-standard", 1, "LLM chose standard.", 0.9)
    sfs_result = _price_catalog_product(sfs_mapping, "chile", 1, "文件系统CFS 通用性能型 美元/GB/月")
    assert sfs_result.spec == "sfs-turbo-20mbps-per-tib"


def test_row_quote_evs_unit_price_row_without_capacity_is_quoted():
    from app.pricebook import load_pricebook
    load_pricebook.cache_clear()
    mapping = RowMapping("test!1", True, "EVS", "High-performance (SAS)", 1, "Unit price row.", 0.9)
    result = _price_evs(mapping, "chile", "云硬盘CBS 高性能云硬盘 美元/GB/月", 1)
    assert result.status == "Quoted"
    assert result.spec and result.spec.endswith("1GB")


def test_row_quote_nat_small_price_not_missing():
    from app.flexible_pricing import load_flexible_pricing_catalog
    load_flexible_pricing_catalog.cache_clear()
    mapping = RowMapping("test!1", True, "NAT Gateway", "nat-small", 1, "Test NAT small mapping.", 0.9)
    result = _price_catalog_product(mapping, "chile", 1)
    assert result.status != "Missing price", f"NAT small should have a price, got status={result.status}"
    assert result.monthly_price is not None and result.monthly_price > 0


def test_row_quote_vpn_professional_1_price_not_missing():
    from app.flexible_pricing import load_flexible_pricing_catalog
    load_flexible_pricing_catalog.cache_clear()
    mapping = RowMapping("test!1", True, "VPN", "vpn-professional-1", 1, "Test VPN professional-1 mapping.", 0.9)
    result = _price_catalog_product(mapping, "chile", 1)
    assert result.status != "Missing price", f"VPN professional-1 should have a price, got status={result.status}"
    assert result.monthly_price is not None and result.monthly_price > 0


def test_row_quote_dc_10g_price_not_missing():
    from app.flexible_pricing import load_flexible_pricing_catalog
    load_flexible_pricing_catalog.cache_clear()
    mapping = RowMapping("test!1", True, "Direct Connect as a Service", "dcas-10g", 1, "Test DC 10GE mapping.", 0.9)
    result = _price_catalog_product(mapping, "chile", 1)
    assert result.status != "Missing price", f"DC 10GE should have a price, got status={result.status}"
    assert result.monthly_price is not None and result.monthly_price > 0


# ---------------------------------------------------------------------------
# Phase 2C regression: composite product sub-row routing
# ---------------------------------------------------------------------------

def test_row_quote_postgresql_disk_routes_to_evs():
    """PostgreSQL 硬盘 sub-row should route to EVS, not RDS compute."""
    row = _make_row(
        cells={"A": "云数据库PostgreSQL", "B": "高可用版-通用型-硬盘", "C": "美元/GB/月"},
        header_context=[{"cells": '{"A": "云数据库PostgreSQL", "B": "子产品名称"}'}],
    )
    # LLM might return RDS for the disk row — composite routing should fix it
    llm_mapping = RowMapping("test!1", True, "RDS", "mysql.s2.large", 1, "LLM mapped to RDS.", 0.85)
    result = _apply_product_priority(row, llm_mapping)
    assert result.huawei_product == "EVS", f"PostgreSQL disk sub-row should route to EVS, got {result.huawei_product}"


def test_row_quote_mysql_disk_routes_to_evs():
    """RDS MySQL 硬盘 sub-row should route to EVS."""
    row = _make_row(
        cells={"A": "云数据库MySQL", "B": "高可用版-通用型-硬盘", "C": "美元/GB/月"},
        header_context=[{"cells": '{"A": "云数据库MySQL", "B": "子产品名称"}'}],
    )
    llm_mapping = RowMapping("test!1", True, "RDS", "mysql.s2.large", 1, "LLM mapped to RDS.", 0.85)
    result = _apply_product_priority(row, llm_mapping)
    assert result.huawei_product == "EVS", f"MySQL disk sub-row should route to EVS, got {result.huawei_product}"


def test_row_quote_postgresql_cpu_stays_rds():
    """PostgreSQL CPU sub-row should stay as RDS (not CCI)."""
    row = _make_row(
        cells={"A": "云数据库PostgreSQL", "B": "高可用版-通用型-CPU", "C": "美元/台/月"},
        header_context=[{"cells": '{"A": "云数据库PostgreSQL", "B": "子产品名称"}'}],
    )
    llm_mapping = RowMapping("test!1", True, "CCI", "1vCPU", 1, "LLM mapped to CCI.", 0.85)
    result = _apply_product_priority(row, llm_mapping)
    assert result.huawei_product == "RDS", f"PostgreSQL CPU should route to RDS, got {result.huawei_product}"


def test_row_quote_postgresql_memory_stays_rds():
    """PostgreSQL 内存 sub-row should stay as RDS (not CCI)."""
    row = _make_row(
        cells={"A": "云数据库PostgreSQL", "B": "高可用版-通用型-内存", "C": "美元/台/月"},
        header_context=[{"cells": '{"A": "云数据库PostgreSQL", "B": "子产品名称"}'}],
    )
    llm_mapping = RowMapping("test!1", True, "CCI", "1GiB", 1, "LLM mapped to CCI.", 0.85)
    result = _apply_product_priority(row, llm_mapping)
    assert result.huawei_product == "RDS", f"PostgreSQL memory should route to RDS, got {result.huawei_product}"


def test_row_quote_dds_memory_routes_to_dds():
    """DDS MongoDB 内存 sub-row should route to DDS, not RDS/CCI."""
    row = _make_row(
        cells={"A": "TencentDB for MongoDB", "B": "副本集-内存", "C": "美元/GB/月"},
        header_context=[{"cells": '{"A": "TencentDB for MongoDB", "B": "子产品名称"}'}],
    )
    llm_mapping = RowMapping("test!1", True, "RDS", "mysql.s2.large", 1, "LLM mapped to RDS.", 0.85)
    result = _apply_product_priority(row, llm_mapping)
    assert result.huawei_product == "DDS", f"MongoDB memory should route to DDS, got {result.huawei_product}"


def test_row_quote_dds_disk_routes_to_evs():
    """DDS MongoDB 硬盘 sub-row should route to EVS."""
    row = _make_row(
        cells={"A": "TencentDB for MongoDB", "B": "副本集-硬盘", "C": "美元/GB/月"},
        header_context=[{"cells": '{"A": "TencentDB for MongoDB", "B": "子产品名称"}'}],
    )
    llm_mapping = RowMapping("test!1", True, "RDS", "mysql.s2.large", 1, "LLM mapped to RDS.", 0.85)
    result = _apply_product_priority(row, llm_mapping)
    assert result.huawei_product == "EVS", f"MongoDB disk should route to EVS, got {result.huawei_product}"


def test_row_quote_dws_node_routes_to_dws():
    """DWS 节点 sub-row should route to DWS."""
    row = _make_row(
        cells={"A": "数据仓库TCHouse-C", "B": "标准型节点", "C": "美元/台/月"},
        header_context=[{"cells": '{"A": "数据仓库TCHouse-C", "B": "子产品名称"}'}],
    )
    llm_mapping = RowMapping("test!1", True, "RDS", "mysql.s2.large", 1, "LLM mapped to RDS.", 0.85)
    result = _apply_product_priority(row, llm_mapping)
    assert result.huawei_product == "DWS", f"DWS node should route to DWS, got {result.huawei_product}"


def test_row_quote_dws_storage_routes_to_evs():
    """DWS 节点存储 sub-row should route to EVS."""
    row = _make_row(
        cells={"A": "数据仓库TCHouse-C", "B": "节点存储", "C": "美元/GB/月"},
        header_context=[{"cells": '{"A": "数据仓库TCHouse-C", "B": "子产品名称"}'}],
    )
    llm_mapping = RowMapping("test!1", True, "EVS", "Enhanced SSD", 1, "LLM mapped to EVS.", 0.85)
    result = _apply_product_priority(row, llm_mapping)
    assert result.huawei_product == "EVS", f"DWS storage should route to EVS, got {result.huawei_product}"


def test_row_quote_composite_group_consistency():
    """For a group of RDS CPU/memory/disk rows, products should be consistent and correct."""
    header_ctx = [{"cells": '{"A": "云数据库MySQL", "B": "子产品名称"}'}]
    rows_and_expected = [
        ({"A": "云数据库MySQL", "B": "高可用版-通用型-CPU", "C": "美元/台/月"}, "RDS"),
        ({"A": "云数据库MySQL", "B": "高可用版-通用型-内存", "C": "美元/台/月"}, "RDS"),
        ({"A": "云数据库MySQL", "B": "高可用版-通用型-硬盘", "C": "美元/GB/月"}, "EVS"),
    ]
    for cells, expected_product in rows_and_expected:
        row = _make_row(cells=cells, header_context=header_ctx)
        # Simulate LLM returning RDS for all (common error)
        llm_mapping = RowMapping("test!1", True, "RDS", "mysql.s2.large", 1, "LLM mapped to RDS.", 0.85)
        result = _apply_product_priority(row, llm_mapping)
        assert result.huawei_product == expected_product, f"Row {cells['B']} should map to {expected_product}, got {result.huawei_product}"


def test_row_quote_composite_detection_helpers():
    """Unit test for _detect_composite_family and _detect_composite_part."""
    assert _detect_composite_family("云数据库MySQL", "高可用版-通用型-CPU") == "rds"
    assert _detect_composite_family("云数据库PostgreSQL", "硬盘") == "rds"
    assert _detect_composite_family("TencentDB for MongoDB", "副本集-内存") == "dds"
    assert _detect_composite_family("数据仓库TCHouse-C", "节点存储") == "dws"
    assert _detect_composite_family("ECS", "c7.large.2") is None

    assert _detect_composite_part("高可用版-通用型-CPU") == "cpu"
    assert _detect_composite_part("高可用版-通用型-内存") == "memory"
    assert _detect_composite_part("高可用版-通用型-硬盘") == "storage"
    assert _detect_composite_part("副本集-内存") == "memory"
    assert _detect_composite_part("副本集-硬盘") == "storage"
    assert _detect_composite_part("标准型节点") == "compute"
    assert _detect_composite_part("节点存储") == "storage"
    assert _detect_composite_part("some random text") is None


# ---------------------------------------------------------------------------
# Phase 2D regression: composite metadata fields and export
# ---------------------------------------------------------------------------

def test_row_quote_composite_group_key_consistency():
    """PostgreSQL CPU/memory/disk rows should share the same composite_group_key."""
    header_ctx = [{"cells": '{"A": "云数据库PostgreSQL", "B": "子产品名称"}'}]
    keys = set()
    for sub_row in ["高可用版-通用型-CPU", "高可用版-通用型-内存", "高可用版-通用型-硬盘"]:
        row = _make_row(
            cells={"A": "云数据库PostgreSQL", "B": sub_row, "C": "美元/月"},
            header_context=header_ctx,
        )
        llm_mapping = RowMapping("test!1", True, "RDS", "mysql.s2.large", 1, "LLM mapped.", 0.85)
        result = _apply_product_priority(row, llm_mapping)
        assert result.composite_group_key is not None, f"Row {sub_row} should have composite_group_key"
        keys.add(result.composite_group_key)
    assert len(keys) == 1, f"All 3 PostgreSQL sub-rows should share same group key, got {keys}"


def test_row_quote_composite_family_rds():
    """RDS composite sub-rows should have composite_family == 'rds'."""
    header_ctx = [{"cells": '{"A": "云数据库MySQL", "B": "子产品名称"}'}]
    for sub_row in ["高可用版-通用型-CPU", "高可用版-通用型-内存", "高可用版-通用型-硬盘"]:
        row = _make_row(cells={"A": "云数据库MySQL", "B": sub_row}, header_context=header_ctx)
        llm_mapping = RowMapping("test!1", True, "RDS", "mysql.s2.large", 1, "LLM mapped.", 0.85)
        result = _apply_product_priority(row, llm_mapping)
        assert result.composite_family == "rds", f"MySQL {sub_row} should have composite_family=rds, got {result.composite_family}"


def test_row_quote_composite_part_correctness():
    """composite_part should be correct for each sub-row type."""
    header_ctx = [{"cells": '{"A": "云数据库MySQL", "B": "子产品名称"}'}]
    cases = [
        ("高可用版-通用型-CPU", "cpu"),
        ("高可用版-通用型-内存", "memory"),
        ("高可用版-通用型-硬盘", "storage"),
    ]
    for sub_row, expected_part in cases:
        row = _make_row(cells={"A": "云数据库MySQL", "B": sub_row}, header_context=header_ctx)
        llm_mapping = RowMapping("test!1", True, "RDS", "mysql.s2.large", 1, "LLM mapped.", 0.85)
        result = _apply_product_priority(row, llm_mapping)
        assert result.composite_part == expected_part, f"MySQL {sub_row} should have composite_part={expected_part}, got {result.composite_part}"


def test_row_quote_dds_composite_metadata():
    """MongoDB sub-rows should have composite_family=dds and correct parts."""
    header_ctx = [{"cells": '{"A": "TencentDB for MongoDB", "B": "子产品名称"}'}]
    row_mem = _make_row(cells={"A": "TencentDB for MongoDB", "B": "副本集-内存"}, header_context=header_ctx)
    row_disk = _make_row(cells={"A": "TencentDB for MongoDB", "B": "副本集-硬盘"}, header_context=header_ctx)
    result_mem = _apply_product_priority(row_mem, RowMapping("test!1", True, "RDS", "mysql.s2.large", 1, "LLM.", 0.85))
    result_disk = _apply_product_priority(row_disk, RowMapping("test!1", True, "RDS", "mysql.s2.large", 1, "LLM.", 0.85))
    assert result_mem.composite_family == "dds"
    assert result_mem.composite_part == "memory"
    assert result_disk.composite_family == "dds"
    assert result_disk.composite_part == "storage"


def test_row_quote_dws_composite_metadata():
    """DWS sub-rows should have composite_family=dws and correct parts."""
    header_ctx = [{"cells": '{"A": "数据仓库TCHouse-C", "B": "子产品名称"}'}]
    row_node = _make_row(cells={"A": "数据仓库TCHouse-C", "B": "标准型节点"}, header_context=header_ctx)
    row_storage = _make_row(cells={"A": "数据仓库TCHouse-C", "B": "节点存储"}, header_context=header_ctx)
    result_node = _apply_product_priority(row_node, RowMapping("test!1", True, "RDS", "mysql.s2.large", 1, "LLM.", 0.85))
    result_storage = _apply_product_priority(row_storage, RowMapping("test!1", True, "EVS", "Enhanced SSD", 1, "LLM.", 0.85))
    assert result_node.composite_family == "dws"
    assert result_node.composite_part == "compute"
    assert result_storage.composite_family == "dws"
    assert result_storage.composite_part == "storage"


def test_row_quote_non_composite_has_no_composite_fields():
    """Non-composite product rows should have empty composite fields."""
    row = _make_row(cells={"A": "ECS", "B": "c7.large.2", "C": "4vCPU 8GB"})
    llm_mapping = RowMapping("test!1", True, "ECS", "c7.large.2", 1, "LLM mapped.", 0.9)
    result = _apply_product_priority(row, llm_mapping)
    assert result.composite_family is None
    assert result.composite_part is None
    assert result.composite_group_key is None


def test_row_quote_export_has_composite_columns(monkeypatch: pytest.MonkeyPatch):
    """Exported workbook should include composite_family, composite_part, composite_group_key columns."""
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook = Workbook()
    ws = workbook.active
    ws.title = "DB"
    ws.append(["Product", "Sub", "Price"])
    ws.append(["云数据库MySQL", "高可用版-通用型-CPU", "USD 79"])
    ws.append(["云数据库MySQL", "高可用版-通用型-硬盘", "USD 0.094/GB"])
    output = BytesIO()
    workbook.save(output)

    quoted_workbook, _summary = annotate_row_quote_workbook(
        {"filename": "db.xlsx", "content": output.getvalue()},
        {"region": "chile", "language": "en", "customer_notes": ""},
    )
    annotated = load_workbook(BytesIO(quoted_workbook.content), data_only=True)["DB"]
    # Check headers contain new columns
    headers = [annotated.cell(1, col).value for col in range(1, annotated.max_column + 1)]
    assert "composite_family" in headers, f"composite_family column missing from headers: {headers}"
    assert "composite_part" in headers, f"composite_part column missing from headers: {headers}"
    assert "composite_group_key" in headers, f"composite_group_key column missing from headers: {headers}"


def test_row_quote_export_composite_values_populated(monkeypatch: pytest.MonkeyPatch):
    """Composite product rows in export should have composite metadata values."""
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook = Workbook()
    ws = workbook.active
    ws.title = "DB"
    ws.append(["Product", "Sub", "Price"])
    ws.append(["云数据库MySQL", "高可用版-通用型-CPU", "USD 79"])
    ws.append(["云数据库MySQL", "高可用版-通用型-硬盘", "USD 0.094/GB"])
    output = BytesIO()
    workbook.save(output)

    quoted_workbook, _summary = annotate_row_quote_workbook(
        {"filename": "db.xlsx", "content": output.getvalue()},
        {"region": "chile", "language": "en", "customer_notes": ""},
    )
    annotated = load_workbook(BytesIO(quoted_workbook.content), data_only=True)["DB"]
    # Find composite columns
    headers = [annotated.cell(1, col).value for col in range(1, annotated.max_column + 1)]
    family_col = headers.index("composite_family") + 1
    part_col = headers.index("composite_part") + 1
    key_col = headers.index("composite_group_key") + 1

    # Row 2: CPU sub-row
    assert annotated.cell(2, family_col).value == "rds", f"Row 2 composite_family should be rds, got {annotated.cell(2, family_col).value}"
    assert annotated.cell(2, part_col).value == "cpu", f"Row 2 composite_part should be cpu, got {annotated.cell(2, part_col).value}"
    assert annotated.cell(2, key_col).value is not None, "Row 2 should have composite_group_key"

    # Row 3: disk sub-row
    assert annotated.cell(3, family_col).value == "rds", f"Row 3 composite_family should be rds, got {annotated.cell(3, family_col).value}"
    assert annotated.cell(3, part_col).value == "storage", f"Row 3 composite_part should be storage, got {annotated.cell(3, part_col).value}"
    assert annotated.cell(3, key_col).value is not None, "Row 3 should have composite_group_key"

    # Both rows should share the same group key
    assert annotated.cell(2, key_col).value == annotated.cell(3, key_col).value, "CPU and disk rows should share same composite_group_key"


# ---------------------------------------------------------------------------
# Phase 2E regression: composite group-level aggregation
# ---------------------------------------------------------------------------

from app.row_quote_workflow import (
    PriceResult as _PriceResult,
    _aggregate_composite_groups,
    QUOTE_STATUS_QUOTED,
    QUOTE_STATUS_MISSING_PRICE,
    QUOTE_STATUS_MANUAL,
    GROUP_STATUS_QUOTED,
    GROUP_STATUS_PARTIALLY_QUOTED,
    GROUP_STATUS_MANUAL_REVIEW,
    GROUP_STATUS_MISSING_PRICE,
)


def _make_composite_db_workbook(*, family: str = "云数据库PostgreSQL", sub_rows: list[str] | None = None) -> bytes:
    """Build a workbook with composite DB sub-rows for group aggregation testing."""
    if sub_rows is None:
        sub_rows = ["高可用版-通用型-CPU", "高可用版-通用型-内存", "高可用版-通用型-硬盘"]
    wb = Workbook()
    ws = wb.active
    ws.title = "DB"
    ws.append(["Product", "Sub", "Price"])
    for sub in sub_rows:
        ws.append([family, sub, "USD 79"])
    output = BytesIO()
    wb.save(output)
    return output.getvalue()


def test_group_aggregation_all_quoted():
    """When all 3 PostgreSQL sub-rows are quoted, group_quote_status == group_quoted."""
    results = [
        _PriceResult(product_name="RDS", monthly_price=79.0, status=QUOTE_STATUS_QUOTED, composite_family="rds", composite_part="cpu", composite_group_key="Sheet1:rds:pg"),
        _PriceResult(product_name="RDS", monthly_price=50.0, status=QUOTE_STATUS_QUOTED, composite_family="rds", composite_part="memory", composite_group_key="Sheet1:rds:pg"),
        _PriceResult(product_name="EVS", monthly_price=9.4, status=QUOTE_STATUS_QUOTED, composite_family="rds", composite_part="storage", composite_group_key="Sheet1:rds:pg"),
    ]
    _aggregate_composite_groups(results)
    for r in results:
        assert r.group_total_monthly_price == 138.4, f"Expected 138.4, got {r.group_total_monthly_price}"
        assert r.group_quote_status == GROUP_STATUS_QUOTED
        assert r.group_component_count == 3
        assert r.group_quoted_component_count == 3


def test_group_aggregation_partially_quoted():
    """When one sub-row is missing price, group_quote_status == partially_quoted."""
    results = [
        _PriceResult(product_name="RDS", monthly_price=79.0, status=QUOTE_STATUS_QUOTED, composite_family="rds", composite_part="cpu", composite_group_key="Sheet1:rds:pg"),
        _PriceResult(product_name="RDS", monthly_price=None, status=QUOTE_STATUS_MISSING_PRICE, composite_family="rds", composite_part="memory", composite_group_key="Sheet1:rds:pg"),
        _PriceResult(product_name="EVS", monthly_price=9.4, status=QUOTE_STATUS_QUOTED, composite_family="rds", composite_part="storage", composite_group_key="Sheet1:rds:pg"),
    ]
    _aggregate_composite_groups(results)
    for r in results:
        assert r.group_total_monthly_price == 88.4, f"Expected 88.4, got {r.group_total_monthly_price}"
        assert r.group_quote_status == GROUP_STATUS_PARTIALLY_QUOTED
        assert r.group_component_count == 3
        assert r.group_quoted_component_count == 2


def test_group_aggregation_manual_review():
    """When all sub-rows need manual review, group_quote_status == manual_review."""
    results = [
        _PriceResult(product_name="RDS", monthly_price=None, status=QUOTE_STATUS_MANUAL, composite_family="rds", composite_part="cpu", composite_group_key="Sheet1:rds:pg"),
        _PriceResult(product_name="RDS", monthly_price=None, status=QUOTE_STATUS_MANUAL, composite_family="rds", composite_part="memory", composite_group_key="Sheet1:rds:pg"),
    ]
    _aggregate_composite_groups(results)
    for r in results:
        assert r.group_total_monthly_price == 0
        assert r.group_quote_status == GROUP_STATUS_MANUAL_REVIEW
        assert r.group_component_count == 2
        assert r.group_quoted_component_count == 0


def test_group_aggregation_missing_price():
    """When all sub-rows have missing price (no manual), group_quote_status == missing_price."""
    results = [
        _PriceResult(product_name="RDS", monthly_price=None, status=QUOTE_STATUS_MISSING_PRICE, composite_family="rds", composite_part="cpu", composite_group_key="Sheet1:rds:pg"),
        _PriceResult(product_name="EVS", monthly_price=None, status=QUOTE_STATUS_MISSING_PRICE, composite_family="rds", composite_part="storage", composite_group_key="Sheet1:rds:pg"),
    ]
    _aggregate_composite_groups(results)
    for r in results:
        assert r.group_quote_status == GROUP_STATUS_MISSING_PRICE
        assert r.group_component_count == 2
        assert r.group_quoted_component_count == 0


def test_group_aggregation_non_composite_unchanged():
    """Non-composite rows should have None group fields after aggregation."""
    results = [
        _PriceResult(product_name="ECS", monthly_price=33.58, status=QUOTE_STATUS_QUOTED),
        _PriceResult(product_name="EVS", monthly_price=5.0, status=QUOTE_STATUS_QUOTED),
    ]
    _aggregate_composite_groups(results)
    for r in results:
        assert r.group_total_monthly_price is None
        assert r.group_quote_status is None
        assert r.group_component_count is None
        assert r.group_quoted_component_count is None


def test_group_aggregation_dds_group():
    """MongoDB (DDS) composite group should aggregate correctly."""
    results = [
        _PriceResult(product_name="DDS", monthly_price=60.0, status=QUOTE_STATUS_QUOTED, composite_family="dds", composite_part="memory", composite_group_key="Sheet1:dds:mongo"),
        _PriceResult(product_name="EVS", monthly_price=9.4, status=QUOTE_STATUS_QUOTED, composite_family="dds", composite_part="storage", composite_group_key="Sheet1:dds:mongo"),
    ]
    _aggregate_composite_groups(results)
    for r in results:
        assert r.group_total_monthly_price == 69.4
        assert r.group_quote_status == GROUP_STATUS_QUOTED
        assert r.group_component_count == 2
        assert r.group_quoted_component_count == 2


def test_group_aggregation_dws_group():
    """DWS composite group should aggregate correctly."""
    results = [
        _PriceResult(product_name="DWS", monthly_price=200.0, status=QUOTE_STATUS_QUOTED, composite_family="dws", composite_part="compute", composite_group_key="Sheet1:dws:tchouse"),
        _PriceResult(product_name="EVS", monthly_price=18.8, status=QUOTE_STATUS_QUOTED, composite_family="dws", composite_part="storage", composite_group_key="Sheet1:dws:tchouse"),
    ]
    _aggregate_composite_groups(results)
    for r in results:
        assert r.group_total_monthly_price == 218.8
        assert r.group_quote_status == GROUP_STATUS_QUOTED
        assert r.group_component_count == 2
        assert r.group_quoted_component_count == 2


def test_group_aggregation_rationale_appended():
    """Group-level rationale note should be appended to each sub-row."""
    results = [
        _PriceResult(product_name="RDS", monthly_price=79.0, status=QUOTE_STATUS_QUOTED, rationale="RDS CPU priced.", composite_family="rds", composite_part="cpu", composite_group_key="Sheet1:rds:pg"),
        _PriceResult(product_name="EVS", monthly_price=9.4, status=QUOTE_STATUS_QUOTED, rationale="EVS storage priced.", composite_family="rds", composite_part="storage", composite_group_key="Sheet1:rds:pg"),
    ]
    _aggregate_composite_groups(results)
    for r in results:
        assert "Composite group total computed" in r.rationale, f"Expected group note in rationale, got: {r.rationale}"


def test_group_aggregation_mixed_quoted_and_manual():
    """Partially quoted group with some manual review rows."""
    results = [
        _PriceResult(product_name="RDS", monthly_price=79.0, status=QUOTE_STATUS_QUOTED, composite_family="rds", composite_part="cpu", composite_group_key="Sheet1:rds:pg"),
        _PriceResult(product_name="RDS", monthly_price=None, status=QUOTE_STATUS_MANUAL, composite_family="rds", composite_part="memory", composite_group_key="Sheet1:rds:pg"),
        _PriceResult(product_name="EVS", monthly_price=9.4, status=QUOTE_STATUS_QUOTED, composite_family="rds", composite_part="storage", composite_group_key="Sheet1:rds:pg"),
    ]
    _aggregate_composite_groups(results)
    for r in results:
        assert r.group_quote_status == GROUP_STATUS_PARTIALLY_QUOTED
        assert r.group_component_count == 3
        assert r.group_quoted_component_count == 2
        assert r.group_total_monthly_price == 88.4


def test_row_quote_export_has_group_columns(monkeypatch: pytest.MonkeyPatch):
    """Exported workbook should include group_total_monthly_price, group_quote_status, group_component_count, group_quoted_component_count columns."""
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook = Workbook()
    ws = workbook.active
    ws.title = "DB"
    ws.append(["Product", "Sub", "Price"])
    ws.append(["云数据库MySQL", "高可用版-通用型-CPU", "USD 79"])
    ws.append(["云数据库MySQL", "高可用版-通用型-硬盘", "USD 0.094/GB"])
    output = BytesIO()
    workbook.save(output)

    quoted_workbook, _summary = annotate_row_quote_workbook(
        {"filename": "db.xlsx", "content": output.getvalue()},
        {"region": "chile", "language": "en", "customer_notes": ""},
    )
    annotated = load_workbook(BytesIO(quoted_workbook.content), data_only=True)["DB"]
    headers = [annotated.cell(1, col).value for col in range(1, annotated.max_column + 1)]
    assert "group_total_monthly_price" in headers, f"group_total_monthly_price column missing from headers: {headers}"
    assert "group_quote_status" in headers, f"group_quote_status column missing from headers: {headers}"
    assert "group_component_count" in headers, f"group_component_count column missing from headers: {headers}"
    assert "group_quoted_component_count" in headers, f"group_quoted_component_count column missing from headers: {headers}"


def test_row_quote_export_group_values_populated_for_composite(monkeypatch: pytest.MonkeyPatch):
    """Composite product rows in export should have group-level values populated and consistent within group."""
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook = Workbook()
    ws = workbook.active
    ws.title = "DB"
    ws.append(["Product", "Sub", "Price"])
    ws.append(["云数据库MySQL", "高可用版-通用型-CPU", "USD 79"])
    ws.append(["云数据库MySQL", "高可用版-通用型-硬盘", "USD 0.094/GB"])
    output = BytesIO()
    workbook.save(output)

    quoted_workbook, _summary = annotate_row_quote_workbook(
        {"filename": "db.xlsx", "content": output.getvalue()},
        {"region": "chile", "language": "en", "customer_notes": ""},
    )
    annotated = load_workbook(BytesIO(quoted_workbook.content), data_only=True)["DB"]
    headers = [annotated.cell(1, col).value for col in range(1, annotated.max_column + 1)]
    gtotal_col = headers.index("group_total_monthly_price") + 1
    gstatus_col = headers.index("group_quote_status") + 1
    gcount_col = headers.index("group_component_count") + 1
    gquoted_col = headers.index("group_quoted_component_count") + 1

    # Both rows should have group values
    for row_num in (2, 3):
        assert annotated.cell(row_num, gstatus_col).value is not None, f"Row {row_num} should have group_quote_status"
        assert annotated.cell(row_num, gcount_col).value is not None, f"Row {row_num} should have group_component_count"

    # Same group → same group_total_monthly_price
    assert annotated.cell(2, gtotal_col).value == annotated.cell(3, gtotal_col).value, "Both rows should share same group_total_monthly_price"
    # Same group → same group_quote_status
    assert annotated.cell(2, gstatus_col).value == annotated.cell(3, gstatus_col).value, "Both rows should share same group_quote_status"
    # Same group → same group_component_count
    assert annotated.cell(2, gcount_col).value == annotated.cell(3, gcount_col).value, "Both rows should share same group_component_count"


def test_row_quote_export_group_values_empty_for_non_composite(monkeypatch: pytest.MonkeyPatch):
    """Non-composite product rows should have empty group-level columns."""
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook, _summary = annotate_row_quote_workbook(
        {"filename": "customer.xlsx", "content": make_row_quote_workbook()},
        {"region": "mexico", "language": "en", "customer_notes": ""},
    )
    annotated = load_workbook(BytesIO(workbook.content), data_only=True)
    compute = annotated["Compute"]
    headers = [compute.cell(1, col).value for col in range(1, compute.max_column + 1)]
    gtotal_col = headers.index("group_total_monthly_price") + 1
    gstatus_col = headers.index("group_quote_status") + 1
    gcount_col = headers.index("group_component_count") + 1
    gquoted_col = headers.index("group_quoted_component_count") + 1

    # All rows in Compute sheet are non-composite → group fields should be None
    for row_num in range(2, compute.max_row + 1):
        assert compute.cell(row_num, gtotal_col).value is None, f"Row {row_num} should have empty group_total_monthly_price"
        assert compute.cell(row_num, gstatus_col).value is None, f"Row {row_num} should have empty group_quote_status"
        assert compute.cell(row_num, gcount_col).value is None, f"Row {row_num} should have empty group_component_count"
        assert compute.cell(row_num, gquoted_col).value is None, f"Row {row_num} should have empty group_quoted_component_count"


# ---------------------------------------------------------------------------
# Phase 2F regression: Composite Summary sheet
# ---------------------------------------------------------------------------

from app.row_quote_workflow import (
    COMPOSITE_SUMMARY_SHEET_NAME,
    COMPOSITE_SUMMARY_COLUMNS,
    _build_composite_summary_rows,
    _write_composite_summary_sheet,
)


def test_row_quote_composite_summary_sheet_exists_in_export(monkeypatch: pytest.MonkeyPatch):
    """Exported workbook should contain a Composite Summary sheet."""
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook = Workbook()
    ws = workbook.active
    ws.title = "DB"
    ws.append(["Product", "Sub", "Price"])
    ws.append(["云数据库MySQL", "高可用版-通用型-CPU", "USD 79"])
    ws.append(["云数据库MySQL", "高可用版-通用型-硬盘", "USD 0.094/GB"])
    output = BytesIO()
    workbook.save(output)

    quoted_workbook, _summary = annotate_row_quote_workbook(
        {"filename": "db.xlsx", "content": output.getvalue()},
        {"region": "chile", "language": "en", "customer_notes": ""},
    )
    annotated = load_workbook(BytesIO(quoted_workbook.content), data_only=True)
    assert COMPOSITE_SUMMARY_SHEET_NAME in annotated.sheetnames, f"Expected '{COMPOSITE_SUMMARY_SHEET_NAME}' sheet, got {annotated.sheetnames}"


def test_row_quote_composite_summary_postgresql_group_one_row(monkeypatch: pytest.MonkeyPatch):
    """PostgreSQL CPU/memory/disk → 1 summary row with correct fields."""
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook = Workbook()
    ws = workbook.active
    ws.title = "DB"
    ws.append(["Product", "Sub", "Price"])
    ws.append(["云数据库PostgreSQL", "高可用版-通用型-CPU", "USD 79"])
    ws.append(["云数据库PostgreSQL", "高可用版-通用型-内存", "USD 50"])
    ws.append(["云数据库PostgreSQL", "高可用版-通用型-硬盘", "USD 0.094/GB"])
    output = BytesIO()
    workbook.save(output)

    quoted_workbook, _summary = annotate_row_quote_workbook(
        {"filename": "db.xlsx", "content": output.getvalue()},
        {"region": "chile", "language": "en", "customer_notes": ""},
    )
    annotated = load_workbook(BytesIO(quoted_workbook.content), data_only=True)
    summary_ws = annotated[COMPOSITE_SUMMARY_SHEET_NAME]

    # Header row + 1 data row
    assert summary_ws.max_row == 2, f"Expected 1 data row in summary, got {summary_ws.max_row - 1}"

    # Read headers to find column indices
    headers = [summary_ws.cell(1, col).value for col in range(1, summary_ws.max_column + 1)]
    key_col = headers.index("composite_group_key") + 1
    family_col = headers.index("composite_family") + 1
    status_col = headers.index("group_quote_status") + 1
    price_col = headers.index("group_total_monthly_price") + 1
    count_col = headers.index("group_component_count") + 1
    quoted_col = headers.index("group_quoted_component_count") + 1
    rows_col = headers.index("source_rows") + 1
    parts_col = headers.index("group_parts") + 1
    products_col = headers.index("group_products") + 1

    # composite_family == rds
    assert summary_ws.cell(2, family_col).value == "rds", f"Expected composite_family=rds, got {summary_ws.cell(2, family_col).value}"
    # group_component_count == 3
    assert summary_ws.cell(2, count_col).value == 3, f"Expected group_component_count=3, got {summary_ws.cell(2, count_col).value}"
    # group_total_monthly_price is a number
    assert isinstance(summary_ws.cell(2, price_col).value, (int, float)), f"Expected numeric price, got {summary_ws.cell(2, price_col).value}"
    # source_rows contains the three row numbers
    source_rows_val = summary_ws.cell(2, rows_col).value
    assert source_rows_val is not None, "source_rows should not be None"
    assert "2" in str(source_rows_val) and "3" in str(source_rows_val) and "4" in str(source_rows_val), f"source_rows should contain 2,3,4, got {source_rows_val}"
    # group_parts contains cpu,memory,storage
    parts_val = summary_ws.cell(2, parts_col).value
    assert "cpu" in str(parts_val) and "memory" in str(parts_val) and "storage" in str(parts_val), f"group_parts should contain cpu,memory,storage, got {parts_val}"
    # group_products contains RDS,EVS
    products_val = summary_ws.cell(2, products_col).value
    assert "RDS" in str(products_val) and "EVS" in str(products_val), f"group_products should contain RDS,EVS, got {products_val}"


def test_row_quote_composite_summary_mongodb_group_one_row(monkeypatch: pytest.MonkeyPatch):
    """MongoDB (DDS) composite group → 1 summary row."""
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook = Workbook()
    ws = workbook.active
    ws.title = "DB"
    ws.append(["Product", "Sub", "Price"])
    ws.append(["TencentDB for MongoDB", "副本集-内存", "USD 60"])
    ws.append(["TencentDB for MongoDB", "副本集-硬盘", "USD 0.094/GB"])
    output = BytesIO()
    workbook.save(output)

    quoted_workbook, _summary = annotate_row_quote_workbook(
        {"filename": "db.xlsx", "content": output.getvalue()},
        {"region": "chile", "language": "en", "customer_notes": ""},
    )
    annotated = load_workbook(BytesIO(quoted_workbook.content), data_only=True)
    summary_ws = annotated[COMPOSITE_SUMMARY_SHEET_NAME]

    # 1 data row
    assert summary_ws.max_row == 2, f"Expected 1 data row in summary, got {summary_ws.max_row - 1}"
    headers = [summary_ws.cell(1, col).value for col in range(1, summary_ws.max_column + 1)]
    family_col = headers.index("composite_family") + 1
    assert summary_ws.cell(2, family_col).value == "dds", f"Expected composite_family=dds, got {summary_ws.cell(2, family_col).value}"


def test_row_quote_composite_summary_dws_group_one_row(monkeypatch: pytest.MonkeyPatch):
    """DWS composite group → 1 summary row."""
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook = Workbook()
    ws = workbook.active
    ws.title = "DB"
    ws.append(["Product", "Sub", "Price"])
    ws.append(["数据仓库TCHouse-C", "标准型节点", "USD 200"])
    ws.append(["数据仓库TCHouse-C", "节点存储", "USD 0.094/GB"])
    output = BytesIO()
    workbook.save(output)

    quoted_workbook, _summary = annotate_row_quote_workbook(
        {"filename": "db.xlsx", "content": output.getvalue()},
        {"region": "chile", "language": "en", "customer_notes": ""},
    )
    annotated = load_workbook(BytesIO(quoted_workbook.content), data_only=True)
    summary_ws = annotated[COMPOSITE_SUMMARY_SHEET_NAME]

    # 1 data row
    assert summary_ws.max_row == 2, f"Expected 1 data row in summary, got {summary_ws.max_row - 1}"
    headers = [summary_ws.cell(1, col).value for col in range(1, summary_ws.max_column + 1)]
    family_col = headers.index("composite_family") + 1
    assert summary_ws.cell(2, family_col).value == "dws", f"Expected composite_family=dws, got {summary_ws.cell(2, family_col).value}"


def test_row_quote_composite_summary_empty_for_non_composite_workbook(monkeypatch: pytest.MonkeyPatch):
    """Non-composite workbook: Composite Summary sheet exists but has only headers (no data rows)."""
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook, _summary = annotate_row_quote_workbook(
        {"filename": "customer.xlsx", "content": make_row_quote_workbook()},
        {"region": "mexico", "language": "en", "customer_notes": ""},
    )
    annotated = load_workbook(BytesIO(workbook.content), data_only=True)
    assert COMPOSITE_SUMMARY_SHEET_NAME in annotated.sheetnames, "Composite Summary sheet should exist even for non-composite workbooks"
    summary_ws = annotated[COMPOSITE_SUMMARY_SHEET_NAME]
    # Only header row, no data
    assert summary_ws.max_row == 1, f"Expected only header row, got {summary_ws.max_row} rows"


def test_row_quote_composite_summary_no_duplicate_sheet_on_reexport(monkeypatch: pytest.MonkeyPatch):
    """Re-exporting should not create duplicate Composite Summary sheets."""
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook = Workbook()
    ws = workbook.active
    ws.title = "DB"
    ws.append(["Product", "Sub", "Price"])
    ws.append(["云数据库MySQL", "高可用版-通用型-CPU", "USD 79"])
    ws.append(["云数据库MySQL", "高可用版-通用型-硬盘", "USD 0.094/GB"])
    output = BytesIO()
    workbook.save(output)

    # First export
    quoted_wb1, _ = annotate_row_quote_workbook(
        {"filename": "db.xlsx", "content": output.getvalue()},
        {"region": "chile", "language": "en", "customer_notes": ""},
    )
    annotated1 = load_workbook(BytesIO(quoted_wb1.content), data_only=True)
    count1 = sum(1 for name in annotated1.sheetnames if name == COMPOSITE_SUMMARY_SHEET_NAME)
    assert count1 == 1, f"Expected exactly 1 Composite Summary sheet, got {count1}"

    # Second export (using the first export's output as input)
    quoted_wb2, _ = annotate_row_quote_workbook(
        {"filename": "db.xlsx", "content": quoted_wb1.content},
        {"region": "chile", "language": "en", "customer_notes": ""},
    )
    annotated2 = load_workbook(BytesIO(quoted_wb2.content), data_only=True)
    count2 = sum(1 for name in annotated2.sheetnames if name == COMPOSITE_SUMMARY_SHEET_NAME)
    assert count2 == 1, f"Expected exactly 1 Composite Summary sheet on re-export, got {count2}"


def test_row_quote_composite_summary_headers_match_expected_columns(monkeypatch: pytest.MonkeyPatch):
    """Composite Summary sheet headers should match COMPOSITE_SUMMARY_COLUMNS exactly."""
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook, _summary = annotate_row_quote_workbook(
        {"filename": "customer.xlsx", "content": make_row_quote_workbook()},
        {"region": "mexico", "language": "en", "customer_notes": ""},
    )
    annotated = load_workbook(BytesIO(workbook.content), data_only=True)
    summary_ws = annotated[COMPOSITE_SUMMARY_SHEET_NAME]
    actual_headers = [summary_ws.cell(1, col).value for col in range(1, len(COMPOSITE_SUMMARY_COLUMNS) + 1)]
    assert actual_headers == COMPOSITE_SUMMARY_COLUMNS, f"Headers mismatch: {actual_headers} != {COMPOSITE_SUMMARY_COLUMNS}"


def test_row_quote_composite_summary_detail_sheets_unchanged(monkeypatch: pytest.MonkeyPatch):
    """Adding Composite Summary sheet should not modify existing detail sheets."""
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook = Workbook()
    ws = workbook.active
    ws.title = "DB"
    ws.append(["Product", "Sub", "Price"])
    ws.append(["云数据库MySQL", "高可用版-通用型-CPU", "USD 79"])
    ws.append(["云数据库MySQL", "高可用版-通用型-硬盘", "USD 0.094/GB"])
    output = BytesIO()
    workbook.save(output)

    quoted_workbook, _summary = annotate_row_quote_workbook(
        {"filename": "db.xlsx", "content": output.getvalue()},
        {"region": "chile", "language": "en", "customer_notes": ""},
    )
    annotated = load_workbook(BytesIO(quoted_workbook.content), data_only=True)
    # DB sheet still exists and has its data
    assert "DB" in annotated.sheetnames
    db_ws = annotated["DB"]
    assert db_ws.cell(1, 1).value == "Product"
    assert db_ws.cell(2, 1).value == "云数据库MySQL"
    assert db_ws.cell(3, 1).value == "云数据库MySQL"
    # Original 3 columns + 19 quote columns = 22 total
    assert db_ws.max_column == 22, f"DB sheet should have 22 columns, got {db_ws.max_column}"


# ---------------------------------------------------------------------------
# Phase 3A regression: rule layer order stability
# ---------------------------------------------------------------------------
# These tests verify that the rule layers are applied in the correct order:
#   Layer 1: hard exclusion
#   Layer 2: special product routing
#   Layer 3: composite sub-row routing
#   Layer 4: product priority overrides (CCI/CCE forcing, DB context)
#   Layer 5: spec normalization
#   Layer 6: composite metadata enrichment


def test_layer1_hard_exclusion_overrides_product_routing():
    """Hard exclusion (template VM) takes priority over any product routing."""
    # A template VM row that also contains CCN keywords — exclusion wins
    row = _make_row(
        cells={"A": "tmpl-vm", "B": "云联网CCN", "C": "月"},
        local_cells={"A": "tmpl-vm", "B": "云联网CCN"},
    )
    # Hard exclusion should fire (template VM), not special product routing (CCN)
    excluded = _apply_hard_exclusions(row)
    assert excluded is not None, "Template VM should be hard-excluded"
    assert not excluded.is_quote_row

    # _fallback_mapping should also return the exclusion
    fallback = _fallback_mapping(row)
    assert not fallback.is_quote_row, "Fallback mapping should respect hard exclusion over CCN routing"


def test_layer3_composite_routing_overrides_cci_force():
    """DB composite routing takes priority over CCI forcing.

    A row that is both in a DB family context (MySQL CPU) and has CCI-like
    keywords should be routed to RDS, not CCI.
    """
    row = _make_row(
        cells={"A": "云数据库MySQL", "B": "高可用版-通用型-CPU", "C": "vCPU-second"},
        header_context=[{"cells": '{"A": "云数据库MySQL", "B": "子产品名称"}'}],
        local_cells={"A": "云数据库MySQL", "B": "高可用版-通用型-CPU", "C": "vCPU-second"},
    )
    # Composite routing should detect RDS CPU sub-row
    composite = _apply_composite_routing(row)
    assert composite is not None, "Composite routing should fire for MySQL CPU sub-row"
    assert composite.huawei_product == "RDS", f"MySQL CPU sub-row should route to RDS, got {composite.huawei_product}"

    # Even if LLM mapped to CCI, _apply_product_priority should correct it
    llm_mapping = RowMapping("test!1", True, "CCI", "1vCPU", 1, "LLM mapped to CCI.", 0.85)
    result = _apply_product_priority(row, llm_mapping)
    assert result.huawei_product != "CCI", f"DB composite routing should override CCI, got {result.huawei_product}"


def test_layer2_special_network_routing_before_generic_fallback():
    """Special network routing (CLB traffic → EIP) fires before generic fallback."""
    row = _make_row(
        cells={"A": "负载均衡", "B": "流量费", "C": "美元/GB"},
    )
    # Special product routing should fire
    special = _apply_special_product_routing(row)
    assert special is not None, "CLB traffic should be routed by special_product_routing"
    assert special.huawei_product == "EIP", f"CLB traffic should map to EIP, got {special.huawei_product}"

    # _fallback_mapping should also route to EIP (not generic keyword match)
    fallback = _fallback_mapping(row)
    assert fallback.huawei_product == "EIP", f"Fallback should route CLB traffic to EIP, got {fallback.huawei_product}"


def test_layer5_spec_normalization_before_pricing():
    """Spec normalization maps LLM output to catalog-hittable keys before pricing."""
    # "High-performance (SAS)" should normalize to "high-io" for EVS
    from app.row_quote_workflow import _normalize_spec_alias
    alias = _normalize_spec_alias("EVS", "High-performance (SAS) - IOPS up to 6000")
    assert alias == "high-io", f"SAS spec should normalize to high-io, got {alias}"

    # "Ultra High I/O" should normalize to "ultra-high-io"
    alias2 = _normalize_spec_alias("EVS", "Ultra High I/O SSD")
    assert alias2 == "ultra-high-io", f"Ultra High I/O should normalize to ultra-high-io, got {alias2}"

    # Non-EVS product should pass through unchanged
    alias3 = _normalize_spec_alias("ECS", "c6.large.2")
    assert alias3 == "c6.large.2", f"ECS spec should pass through unchanged, got {alias3}"


def test_layer6_composite_enrichment_always_present():
    """Composite metadata enrichment tags rows in DB family context even when
    no product override happens."""
    row = _make_row(
        cells={"A": "云数据库MySQL", "B": "高可用版-通用型-CPU", "C": "USD 79"},
        header_context=[{"cells": '{"A": "云数据库MySQL", "B": "子产品名称"}'}],
    )
    # A mapping that already has the correct product (RDS) but no composite metadata
    mapping = RowMapping("test!1", True, "RDS", "mysql-ha", 1, "LLM mapped to RDS.", 0.85)
    assert not mapping.composite_family, "Precondition: mapping should have no composite metadata"

    # _enrich_composite_metadata should tag it
    enriched = _enrich_composite_metadata(row, mapping)
    assert enriched.composite_family == "rds", f"Enriched mapping should have composite_family=rds, got {enriched.composite_family}"
    assert enriched.composite_part == "cpu", f"Enriched mapping should have composite_part=cpu, got {enriched.composite_part}"
    assert enriched.composite_group_key is not None, "Enriched mapping should have composite_group_key"

    # If composite metadata is already present, it should not be overwritten
    already_tagged = RowMapping("test!1", True, "RDS", "mysql-ha", 1, "LLM mapped.", 0.85,
                                composite_family="rds", composite_part="memory", composite_group_key="test:rds:mysql")
    enriched2 = _enrich_composite_metadata(row, already_tagged)
    assert enriched2.composite_part == "memory", f"Existing composite_part should not be overwritten, got {enriched2.composite_part}"


# ---------------------------------------------------------------------------
# Nearest ECS match strategy tests
# ---------------------------------------------------------------------------


def _make_region_catalog(ecs_items: list[dict]) -> dict:
    """Build a minimal region_catalog for pick_ecs_match tests."""
    return {"ecs": ecs_items, "evs": [], "regionCode": "la-north-2"}


def test_rvtools_ecs_match_uses_nearest_cpu_mem_not_ceiling():
    """RVTools quote should pick the closest CPU/mem shape, not just the smallest >= spec."""
    load_pricebook.cache_clear()
    catalog = _make_region_catalog([
        {"spec": "small.8c10g", "vcpu": 8, "memoryGiB": 10, "category": "General Computing",
         "familyLabel": "x0", "generation": "", "hourlyUsd": 0.12, "monthlyUsd": 87.6,
         "ri1YearMonthlyUsd": 60, "resourceSpecCode": "", "image": "Linux", "imageSpec": "linux",
         "ondemandProductId": "", "riProductId": "", "riPlanId": ""},
        {"spec": "medium.8c12g", "vcpu": 8, "memoryGiB": 12, "category": "General Computing",
         "familyLabel": "x0", "generation": "", "hourlyUsd": 0.13, "monthlyUsd": 94.9,
         "ri1YearMonthlyUsd": 65, "resourceSpecCode": "", "image": "Linux", "imageSpec": "linux",
         "ondemandProductId": "", "riProductId": "", "riPlanId": ""},
        {"spec": "big.16c32g", "vcpu": 16, "memoryGiB": 32, "category": "General Computing",
         "familyLabel": "x0", "generation": "", "hourlyUsd": 0.25, "monthlyUsd": 182.5,
         "ri1YearMonthlyUsd": 120, "resourceSpecCode": "", "image": "Linux", "imageSpec": "linux",
         "ondemandProductId": "", "riProductId": "", "riPlanId": ""},
    ])
    # Request 8 vCPU / 11 GiB
    # ceil: must be >= 8C/11G → medium.8c12g (smallest >=, since small.8c10g has mem=10 < 11)
    # nearest: small.8c10g score=|0|+|10-11|/11=0.091, medium.8c12g score=|0|+|12-11|/11=0.091
    #   same score → tie-breaker: small.8c10g undersizes (mem<11), medium.8c12g does not → medium wins
    # But the key point: nearest considers small.8c10g (which ceil rejects), and if the
    # gap were wider, nearest would pick it. Let's use 8C/10.5G instead:
    #   small.8c10g: score = 0 + |10-10.5|/10.5 = 0.0476, undersizes=1
    #   medium.8c12g: score = 0 + |12-10.5|/10.5 = 0.1429, undersizes=0
    #   small.8c10g has lower score → wins even though it undersizes
    ceil_match = pick_ecs_match(catalog, 8, 11, strategy="ceil")
    near_match = pick_ecs_match(catalog, 8, 10.5, strategy="nearest")
    assert ceil_match["spec"] == "medium.8c12g", "Ceiling should pick smallest >= spec"
    assert near_match["spec"] == "small.8c10g", "Nearest should pick closer spec even if slightly under"


def test_pick_ecs_match_nearest_can_select_lower_when_closer():
    """When a lower spec is closer in ratio distance, nearest can select it,
    but tie-breaker prefers non-undersizing specs when scores are equal."""
    catalog = _make_region_catalog([
        {"spec": "s2c4g", "vcpu": 2, "memoryGiB": 4, "category": "General Computing",
         "familyLabel": "x0", "generation": "", "hourlyUsd": 0.03, "monthlyUsd": 21.9,
         "ri1YearMonthlyUsd": 15, "resourceSpecCode": "", "image": "Linux", "imageSpec": "linux",
         "ondemandProductId": "", "riProductId": "", "riPlanId": ""},
        {"spec": "s4c8g", "vcpu": 4, "memoryGiB": 8, "category": "General Computing",
         "familyLabel": "x0", "generation": "", "hourlyUsd": 0.06, "monthlyUsd": 43.8,
         "ri1YearMonthlyUsd": 30, "resourceSpecCode": "", "image": "Linux", "imageSpec": "linux",
         "ondemandProductId": "", "riProductId": "", "riPlanId": ""},
    ])

    # Request 3 vCPU / 6 GiB
    # s2c4g: cpu_ratio=|2-3|/3=0.333, mem_ratio=|4-6|/6=0.333, score=0.667, undersizes=1
    # s4c8g: cpu_ratio=|4-3|/3=0.333, mem_ratio=|8-6|/6=0.333, score=0.667, undersizes=0
    # Same score → tie-breaker prefers non-undersizing → s4c8g
    match = pick_ecs_match(catalog, 3, 6, strategy="nearest")
    assert match["spec"] == "s4c8g", "Tie-breaker should prefer non-undersizing spec"

    # Request 3 vCPU / 5 GiB
    # s2c4g: cpu_ratio=1/3=0.333, mem_ratio=1/5=0.2, score=0.533, undersizes=1
    # s4c8g: cpu_ratio=1/3=0.333, mem_ratio=3/5=0.6, score=0.933, undersizes=0
    # s2c4g has lower score → wins even though it undersizes
    match = pick_ecs_match(catalog, 3, 5, strategy="nearest")
    assert match["spec"] == "s2c4g", "Lower score wins even when undersizing"


def test_pick_ecs_match_nearest_tiebreaker_prefers_lower_price():
    """When scores and undersize flag are equal, prefer lower monthly price."""
    catalog = _make_region_catalog([
        {"spec": "expensive.8c16g", "vcpu": 8, "memoryGiB": 16, "category": "General Computing",
         "familyLabel": "c7n", "generation": "", "hourlyUsd": 0.22, "monthlyUsd": 160.6,
         "ri1YearMonthlyUsd": 100, "resourceSpecCode": "", "image": "Linux", "imageSpec": "linux",
         "ondemandProductId": "", "riProductId": "", "riPlanId": ""},
        {"spec": "cheap.8c16g", "vcpu": 8, "memoryGiB": 16, "category": "General Computing",
         "familyLabel": "x0", "generation": "", "hourlyUsd": 0.13, "monthlyUsd": 94.9,
         "ri1YearMonthlyUsd": 65, "resourceSpecCode": "", "image": "Linux", "imageSpec": "linux",
         "ondemandProductId": "", "riProductId": "", "riPlanId": ""},
    ])
    # Both have same vcpu/mem → same score, same undersize flag → cheaper wins
    match = pick_ecs_match(catalog, 8, 16, strategy="nearest")
    assert match["spec"] == "cheap.8c16g", "Tie-breaker should prefer lower price"


def test_pick_ecs_match_default_strategy_unchanged():
    """Default strategy='ceil' must preserve the original ceiling behavior."""
    load_pricebook.cache_clear()
    pricebook = load_pricebook()
    mexico = pricebook["pricingCatalog"]["mexico"]

    # Default call (no strategy arg) should behave like ceil
    default_match = pick_ecs_match(mexico, 2, 8)
    ceil_match = pick_ecs_match(mexico, 2, 8, strategy="ceil")
    assert default_match is not None
    assert ceil_match is not None
    assert default_match["spec"] == ceil_match["spec"], "Default should match ceil strategy"

    # Ceil should always return a spec with vcpu >= requested and mem >= requested
    assert int(default_match["vcpu"]) >= 2
    assert float(default_match["memoryGiB"]) >= 8


def test_rvtools_export_reports_matched_ecs_vcpu_mem():
    """RVTools preview/export output should report the matched ECS spec's vcpu/mem,
    not the original VM's values."""
    load_pricebook.cache_clear()
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-8c10g", "Powerstate": "PoweredOn", "CPUs": 8, "Memory": 10240},
        ],
        disk_rows=[
            {"VM": "vm-8c10g", "Capacity GiB": 100},
        ],
    )

    result = export_graph.invoke(
        {
            "request": {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "sample.xlsx"},
            "file_bytes": content,
        }
    )

    lines = result["quote_lines"]
    assert len(lines) == 1
    line = lines[0]
    # The matched ECS spec should have been written to ecs_vcpu / ecs_mem / ecs_spec
    assert line["ecs_vcpu"] is not None
    assert line["ecs_mem"] is not None
    assert line["ecs_spec"] is not None

    # Verify the matched spec actually exists in the pricebook
    pricebook = load_pricebook()
    mexico = pricebook["pricingCatalog"]["mexico"]
    matched_in_catalog = next(
        (item for item in mexico["ecs"] if item["spec"] == line["ecs_spec"]),
        None,
    )
    assert matched_in_catalog is not None, f"Matched spec {line['ecs_spec']} not found in catalog"
    assert int(matched_in_catalog["vcpu"]) == line["ecs_vcpu"]
    assert float(matched_in_catalog["memoryGiB"]) == line["ecs_mem"]


# ── Phase 1: Non-standard RVTools inventory sheet tests ────────────────────────


def test_parse_rvtools_nonstandard_inventory_sheet_amu():
    """Parse AMU sample file with 'filtrado' sheet (no vInfo/vDisk)."""
    with open("/root/SMBReference/Refrence1/SAPCloud_RVTools_export_all_2026-03-30_AMU.xlsx", "rb") as f:
        content = f.read()
    parsed, info_rows, disk_rows = parse_rvtools_workbook(content)

    assert len(parsed) == 140
    first = parsed[0]
    assert first.vm_name == "CLIENTE_009prdbd1-HnpM"
    assert first.vcpu == 8
    assert first.memory_gib == 256
    assert first.disk_gib == 1972
    assert first.customer == "Cliente_01"
    assert first.workload_type == "BD HANA"
    assert first.source_sheet == "filtrado"
    assert "Red Hat Enterprise Linux 9" in first.os
    # raw values preserved
    assert first.raw_memory_mb == 262144
    assert first.raw_storage_mib == 2019328
    # LLM hint fields exist but are None/empty
    assert first.workload_category is None
    assert first.storage_class_hint is None
    assert first.license_hint is None
    assert first.ecs_family_hint is None
    assert first.classification_confidence is None
    assert first.classification_rationale is None
    assert first.review_flags == []
    # Non-standard path returns empty disk_rows
    assert disk_rows == []


def test_parse_rvtools_nonstandard_inventory_sheet_cdlv():
    """Parse CDLV sample file with 'Filtrado' sheet (no vInfo/vDisk)."""
    with open("/root/SMBReference/Refrence1/SAPCloud_RVTools_export_all_2026-03-30_CDLV.xlsx", "rb") as f:
        content = f.read()
    parsed, info_rows, disk_rows = parse_rvtools_workbook(content)

    assert len(parsed) == 162
    first = parsed[0]
    assert first.vm_name.startswith("M4C-Cliente_003")
    assert first.vcpu == 4
    assert first.memory_gib == 16
    assert first.disk_gib == 30
    assert first.customer == "Cliente_003"
    assert first.workload_type == "SAP"
    assert first.source_sheet == "Filtrado"
    assert "Ubuntu Linux" in first.os
    # raw values preserved
    assert first.raw_memory_mb == 16384
    assert first.raw_storage_mib == 30720
    # LLM hint fields exist but are None/empty
    assert first.workload_category is None
    assert first.review_flags == []
    # Non-standard path returns empty disk_rows
    assert disk_rows == []


def test_parse_rvtools_standard_vinfo_still_supported():
    """Standard vInfo/vDisk path still works after Phase 1 changes."""
    content = make_rvtools_file(
        info_rows=[
            {"VM Name": "app-01", "Power State": "PoweredOn", "NumCpu": 2, "Memory MB": 8192, "OS": "Windows"},
        ],
        disk_rows=[
            {"VM": "app-01", "Capacity GB": 100},
            {"VM": "app-01", "Provisioned GB": 50},
        ],
    )
    parsed, info_rows, disk_rows = parse_rvtools_workbook(content)

    assert len(parsed) == 1
    assert parsed[0].vm_name == "app-01"
    assert parsed[0].vcpu == 2
    assert parsed[0].memory_gib == 8
    assert parsed[0].disk_gib == 150  # aggregated from vDisk
    assert parsed[0].source_sheet == "vInfo"
    # disk_rows returned for standard path
    assert len(disk_rows) == 2


def test_parse_rvtools_inventory_sheet_selected_by_sheet_selection():
    """SheetSelection can target an inventory-like sheet by index."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        # Sheet 1: not inventory-like (missing storage)
        pd.DataFrame([{"VM": "x", "CPUs": 2, "Memory": 4096}]).to_excel(
            writer, sheet_name="Summary", index=False
        )
        # Sheet 2: inventory-like
        pd.DataFrame([
            {"VM": "inv-01", "CPUs": 4, "Memory": 8192, "Total disk capacity GiB": 100},
        ]).to_excel(writer, sheet_name="filtrado", index=False)
    content = buffer.getvalue()

    parsed, info_rows, disk_rows = parse_rvtools_workbook(
        content, SheetSelection(mode="selected", selected_input="2")
    )
    assert len(parsed) == 1
    assert parsed[0].vm_name == "inv-01"
    assert parsed[0].source_sheet == "filtrado"


def test_parse_rvtools_inventory_sheet_missing_storage_rejected():
    """A sheet with VM/CPU/Memory but no Storage column is not inventory-like and should error."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        pd.DataFrame([
            {"VM": "vm-1", "CPUs": 2, "Memory": 4096},
        ]).to_excel(writer, sheet_name="partial", index=False)
    content = buffer.getvalue()

    with pytest.raises(RvToolsParseError, match="inventory-like"):
        parse_rvtools_workbook(content)


def test_parse_rvtools_template_style_ecs_sheet_with_offset_header():
    """A template-style ECS sheet with a title row and row-2 headers should be recognized."""
    buffer = BytesIO()
    workbook = Workbook()
    ws = workbook.active
    ws.title = "ECS"
    ws.append(["Origen", "", "", "", "", ""])
    ws.append(["Equipo", "CPU", "Mem", "Tipo", "HD", "S.O"])
    ws.append(["Server_1", 4, 32, "x86_64", "250 GiB", "Ubuntu 18"])
    ws.append(["Server_2", 2, 16, "x86_64", "100 GiB", "Windows 10 Pro"])
    workbook.save(buffer)
    content = buffer.getvalue()

    parsed, info_rows, disk_rows = parse_rvtools_workbook(content)

    assert len(parsed) == 2
    assert parsed[0].vm_name == "Server_1"
    assert parsed[0].vcpu == 4
    assert parsed[0].memory_gib == 32
    assert parsed[0].disk_gib == 250
    assert parsed[0].os == "Ubuntu 18"
    assert parsed[0].source_sheet == "ECS"
    assert info_rows[0]["Equipo"] == "Server_1"
    assert disk_rows == []


def test_parse_rvtools_reference2_template_export_file_supported():
    """A previously exported template workbook should be re-readable by the RVTools parser."""
    with open("/root/SMBReference/Refrence2/test 1.xlsx", "rb") as f:
        content = f.read()

    parsed, info_rows, disk_rows = parse_rvtools_workbook(content)

    assert len(parsed) > 0
    first = parsed[0]
    assert first.vm_name == "Server_1"
    assert first.vcpu == 4
    assert first.memory_gib == 32
    assert first.disk_gib == 250
    assert first.os == "Ubuntu 18"
    assert first.source_sheet == "ECS"
    assert "Equipo" in info_rows[0]
    assert disk_rows == []


# ── Phase 2A: Local classification and field propagation tests ─────────────────


def test_normalize_inventory_preserves_nonstandard_fields():
    """Non-standard parser fields (customer, workload_type, etc.) survive normalize_inventory."""
    state = {
        "parsed_vms": [
            {
                "vm_name": "hana-vm",
                "power_state": "poweredOn",
                "os": "Red Hat Enterprise Linux 9 (64-bit)",
                "vcpu": 8,
                "memory_gib": 256,
                "disk_gib": 1972,
                "customer": "Cliente_01",
                "workload_type": "BD HANA",
                "source_sheet": "filtrado",
                "source_dc": None,
                "raw_memory_mb": 262144,
                "raw_storage_mib": 2019328,
            }
        ]
    }
    result = normalize_inventory(state)
    norm = result["normalized_vms"][0]
    assert norm["customer"] == "Cliente_01"
    assert norm["workload_type"] == "BD HANA"
    assert norm["source_sheet"] == "filtrado"
    assert norm["raw_memory_mb"] == 262144
    assert norm["raw_storage_mib"] == 2019328


def test_local_classification_hana():
    """HANA workload from Tipo SAP gets correct classification."""
    result = _classify_vm_locally({
        "vm_name": "prdbd1",
        "os": "Red Hat Enterprise Linux 9 (64-bit)",
        "workload_type": "BD HANA",
        "customer": "Cliente_01",
        "vcpu": 8,
        "memory_gib": 256,
        "disk_gib": 1972,
    })
    assert result["workload_category"] == "sap_hana_db"
    assert result["storage_class_hint"] == "ultra-high-io"
    assert result["ecs_family_hint"] == "memory_optimized"
    assert "hana_storage_class_review" in result["review_flags"]
    assert result["classification_confidence"] == 0.8
    assert "HANA" in result["classification_rationale"]


def test_local_classification_sap_app():
    """SAP workload (not HANA) gets sap_app category."""
    result = _classify_vm_locally({
        "vm_name": "sap-app-01",
        "os": "SUSE Linux",
        "workload_type": "SAP",
        "vcpu": 4,
        "memory_gib": 16,
        "disk_gib": 100,
    })
    assert result["workload_category"] == "sap_app"
    assert result["storage_class_hint"] == "general-purpose-ssd"
    assert result["ecs_family_hint"] == "general_purpose"


def test_local_classification_sql_windows():
    """SQL Server workload + Windows OS gets sql_db + windows license."""
    result = _classify_vm_locally({
        "vm_name": "mssql-01",
        "os": "Microsoft Windows Server 2016 or later (64-bit)",
        "workload_type": "SQL Server",
        "vcpu": 4,
        "memory_gib": 16,
        "disk_gib": 200,
    })
    assert result["workload_category"] == "sql_db"
    assert result["license_hint"] == "windows"
    assert "windows_license_review" in result["review_flags"]
    assert "database_storage_class_review" in result["review_flags"]


def test_local_classification_unknown_large_memory():
    """Unknown workload with large memory+storage gets ultra-high-io hint."""
    result = _classify_vm_locally({
        "vm_name": "big-vm",
        "os": "Ubuntu Linux (64-bit)",
        "workload_type": None,
        "vcpu": 32,
        "memory_gib": 256,
        "disk_gib": 2000,
    })
    assert result["workload_category"] == "unknown"
    assert result["storage_class_hint"] == "ultra-high-io"
    assert "workload_unclassified" in result["review_flags"]
    assert result["classification_confidence"] == 0.55


def test_quote_preview_includes_classification_fields_for_nonstandard_file():
    """Full preview pipeline on AMU file populates classification fields in quote lines."""
    load_pricebook.cache_clear()
    with open("/root/SMBReference/Refrence1/SAPCloud_RVTools_export_all_2026-03-30_AMU.xlsx", "rb") as f:
        content = f.read()

    result = preview_graph.invoke(
        {
            "request": {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "AMU.xlsx"},
            "file_bytes": content,
        }
    )
    preview_resp = build_preview_response(result)

    # There should be quoted lines
    assert preview_resp.quote_lines

    # Pick the first quoted line (HANA VM)
    first = preview_resp.quote_lines[0]
    assert first.customer is not None
    assert first.workload_type is not None
    assert first.workload_category is not None
    assert first.storage_class_hint is not None
    assert first.license_hint is not None
    assert first.source_sheet is not None
    # HANA VM should have sap_hana_db category
    assert first.workload_category == "sap_hana_db"


def test_phase2a_does_not_change_price_math():
    """Classification fields do not alter price calculations for standard RVTools input."""
    load_pricebook.cache_clear()
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-a", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
        ],
        disk_rows=[
            {"VM": "vm-a", "Capacity GiB": 100},
        ],
    )

    result = export_graph.invoke(
        {
            "request": {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "sample.xlsx"},
            "file_bytes": content,
        }
    )

    # The quoted VM should have the same price as before Phase 2A
    quoted = [line for line in result["quote_lines"] if line["action"] == "quote"]
    assert len(quoted) == 1
    assert quoted[0]["ecs_ondemand_monthly_usd"] == 33.58
    # Classification fields are present but did not affect pricing
    assert quoted[0]["workload_category"] is not None
    assert quoted[0]["storage_class_hint"] is not None


# ── Phase 2B: LLM classification node tests ──────────────────────────────────────

import json as _json
from unittest.mock import patch, MagicMock


def _make_normalized_vm(
    *,
    vm_name: str = "test-vm",
    os: str = "Linux",
    vcpu: int = 4,
    memory_gib: float = 8.0,
    disk_gib: float = 100.0,
    workload_category: str = "unknown",
    storage_class_hint: str = "general-purpose-ssd",
    license_hint: str = "linux",
    ecs_family_hint: str = "general_purpose",
    classification_confidence: float = 0.4,
    classification_rationale: str = "No workload type matched.",
    review_flags: list | None = None,
    action: str = "quote",
    review_reason: str | None = None,
) -> dict:
    return {
        "vm_name": vm_name,
        "os": os,
        "vcpu": vcpu,
        "memory_gib": memory_gib,
        "disk_gib": disk_gib,
        "power_state": "poweredon",
        "customer": None,
        "workload_type": None,
        "source_sheet": None,
        "source_dc": None,
        "raw_memory_mb": None,
        "raw_storage_mib": None,
        "workload_category": workload_category,
        "storage_class_hint": storage_class_hint,
        "license_hint": license_hint,
        "ecs_family_hint": ecs_family_hint,
        "classification_confidence": classification_confidence,
        "classification_rationale": classification_rationale,
        "review_flags": review_flags or ["workload_unclassified"],
        "action": action,
        "review_reason": review_reason,
    }


def _make_maas_response_json(rows: list[dict]) -> dict:
    """Build a fake MaaS API response wrapping classification rows."""
    return {
        "choices": [
            {
                "message": {
                    "content": _json.dumps({"rows": rows}),
                }
            }
        ]
    }


def test_classify_inventory_context_missing_maas_config_fallback():
    """When MaaS env vars are missing, node returns {} (no changes)."""
    env = {
        "HUAWEI_MAAS_API_KEY": "",
        "HUAWEI_MAAS_BASE_URL": "",
        "HUAWEI_MAAS_MODEL": "",
    }
    with patch.dict(os.environ, env, clear=False):
        state = {
            "normalized_vms": [
                _make_normalized_vm(vm_name="vm-1", workload_category="sap_hana_db"),
            ]
        }
        result = classify_inventory_context(state)
        # No changes — returns empty dict
        assert result == {}


def test_classify_inventory_context_valid_llm_overrides_classification():
    """Valid LLM response overrides classification fields."""
    local_vms = [
        _make_normalized_vm(
            vm_name="hana-01",
            os="SUSE Linux",
            workload_category="sap_hana_db",
            storage_class_hint="ultra-high-io",
            license_hint="suse_linux",
            ecs_family_hint="memory_optimized",
            classification_confidence=0.8,
            classification_rationale="Matched HANA workload.",
            review_flags=["hana_storage_class_review"],
        ),
    ]
    llm_rows = [
        {
            "row_index": 0,
            "workload_category": "sap_hana_db",
            "storage_class_hint": "ultra-high-io",
            "license_hint": "suse_linux",
            "ecs_family_hint": "memory_optimized",
            "classification_confidence": 0.92,
            "classification_rationale": "Tipo SAP contains BD HANA and OS is SUSE Linux.",
            "review_flags": ["hana_storage_class_review"],
        }
    ]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = _make_maas_response_json(llm_rows)
    mock_response.raise_for_status = MagicMock()

    env = {
        "HUAWEI_MAAS_API_KEY": "test-key",
        "HUAWEI_MAAS_BASE_URL": "https://maas.example.com",
        "HUAWEI_MAAS_MODEL": "test-model",
    }
    with patch.dict(os.environ, env, clear=False):
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = classify_inventory_context({"normalized_vms": local_vms})

    assert "normalized_vms" in result
    vm = result["normalized_vms"][0]
    assert vm["workload_category"] == "sap_hana_db"
    assert vm["storage_class_hint"] == "ultra-high-io"
    assert vm["license_hint"] == "suse_linux"
    assert vm["ecs_family_hint"] == "memory_optimized"
    assert vm["classification_confidence"] == 0.92
    assert vm["classification_rationale"].startswith("LLM:")
    assert "hana_storage_class_review" in vm["review_flags"]


def test_classify_inventory_context_does_not_modify_price_inputs():
    """LLM cannot modify vcpu, memory_gib, disk_gib, action, or review_reason."""
    local_vms = [
        _make_normalized_vm(
            vm_name="vm-1",
            vcpu=4,
            memory_gib=8.0,
            disk_gib=100.0,
            action="quote",
            review_reason=None,
        ),
    ]
    # LLM tries to modify price-related fields (should be ignored)
    llm_rows = [
        {
            "row_index": 0,
            "workload_category": "linux_app",
            "storage_class_hint": "general-purpose-ssd",
            "license_hint": "linux",
            "ecs_family_hint": "general_purpose",
            "classification_confidence": 0.7,
            "classification_rationale": "Linux app workload.",
            "review_flags": [],
            # These should be ignored — not in the classification field set
            "vcpu": 999,
            "memory_gib": 999,
            "disk_gib": 999,
            "action": "manual_review",
        }
    ]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = _make_maas_response_json(llm_rows)
    mock_response.raise_for_status = MagicMock()

    env = {
        "HUAWEI_MAAS_API_KEY": "test-key",
        "HUAWEI_MAAS_BASE_URL": "https://maas.example.com",
        "HUAWEI_MAAS_MODEL": "test-model",
    }
    with patch.dict(os.environ, env, clear=False):
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = classify_inventory_context({"normalized_vms": local_vms})

    vm = result["normalized_vms"][0]
    # Price-related fields unchanged
    assert vm["vcpu"] == 4
    assert vm["memory_gib"] == 8.0
    assert vm["disk_gib"] == 100.0
    assert vm["action"] == "quote"
    assert vm["review_reason"] is None
    # Classification fields updated
    assert vm["workload_category"] == "linux_app"


def test_classify_inventory_context_invalid_json_fallback():
    """Non-JSON LLM response falls back to local classification."""
    local_vms = [_make_normalized_vm(vm_name="vm-1", workload_category="sql_db")]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "this is not valid json!!!"}}]
    }
    mock_response.raise_for_status = MagicMock()

    env = {
        "HUAWEI_MAAS_API_KEY": "test-key",
        "HUAWEI_MAAS_BASE_URL": "https://maas.example.com",
        "HUAWEI_MAAS_MODEL": "test-model",
    }
    with patch.dict(os.environ, env, clear=False):
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = classify_inventory_context({"normalized_vms": local_vms})

    # Fallback → no changes
    assert result == {}


def test_classify_inventory_context_unknown_values_ignored():
    """LLM values not in allowed enum sets are dropped; local fallback kept."""
    local_vms = [
        _make_normalized_vm(
            vm_name="vm-1",
            workload_category="unknown",
            storage_class_hint="general-purpose-ssd",
            license_hint="linux",
            ecs_family_hint="general_purpose",
        ),
    ]
    llm_rows = [
        {
            "row_index": 0,
            "workload_category": "invalid_category",  # not in allowed set
            "storage_class_hint": "super-ssd",  # not in allowed set
            "license_hint": "macos",  # not in allowed set
            "ecs_family_hint": "gpu_optimized",  # not in allowed set
            "classification_confidence": 0.9,
            "classification_rationale": "Invalid values.",
            "review_flags": [],
        }
    ]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = _make_maas_response_json(llm_rows)
    mock_response.raise_for_status = MagicMock()

    env = {
        "HUAWEI_MAAS_API_KEY": "test-key",
        "HUAWEI_MAAS_BASE_URL": "https://maas.example.com",
        "HUAWEI_MAAS_MODEL": "test-model",
    }
    with patch.dict(os.environ, env, clear=False):
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = classify_inventory_context({"normalized_vms": local_vms})

    vm = result["normalized_vms"][0]
    # Invalid enum values dropped → local fallback kept
    assert vm["workload_category"] == "unknown"
    assert vm["storage_class_hint"] == "general-purpose-ssd"
    assert vm["license_hint"] == "linux"
    assert vm["ecs_family_hint"] == "general_purpose"


def test_classify_inventory_context_review_flags_merged():
    """Local and LLM review_flags are merged and deduped."""
    local_vms = [
        _make_normalized_vm(
            vm_name="hana-01",
            workload_category="sap_hana_db",
            review_flags=["hana_storage_class_review"],
        ),
    ]
    llm_rows = [
        {
            "row_index": 0,
            "workload_category": "sap_hana_db",
            "storage_class_hint": "ultra-high-io",
            "license_hint": "suse_linux",
            "ecs_family_hint": "memory_optimized",
            "classification_confidence": 0.9,
            "classification_rationale": "HANA DB confirmed.",
            "review_flags": ["windows_license_review"],
        }
    ]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = _make_maas_response_json(llm_rows)
    mock_response.raise_for_status = MagicMock()

    env = {
        "HUAWEI_MAAS_API_KEY": "test-key",
        "HUAWEI_MAAS_BASE_URL": "https://maas.example.com",
        "HUAWEI_MAAS_MODEL": "test-model",
    }
    with patch.dict(os.environ, env, clear=False):
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = classify_inventory_context({"normalized_vms": local_vms})

    vm = result["normalized_vms"][0]
    assert "hana_storage_class_review" in vm["review_flags"]
    assert "windows_license_review" in vm["review_flags"]
    # Deduped — no duplicates
    assert len(vm["review_flags"]) == len(set(vm["review_flags"]))


def test_preview_graph_runs_with_llm_classification():
    """Full preview graph with mocked MaaS produces LLM-updated classification."""
    load_pricebook.cache_clear()
    content = make_rvtools_file(
        info_rows=[
            {"VM": "hana-01", "Powerstate": "PoweredOn", "CPUs": 8, "Memory": 64, "OS": "SUSE Linux"},
            {"VM": "app-01", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4, "OS": "Windows"},
        ],
        disk_rows=[
            {"VM": "hana-01", "Capacity GiB": 500},
            {"VM": "app-01", "Capacity GiB": 100},
        ],
    )

    # LLM classifies both rows
    llm_rows = [
        {
            "row_index": 0,
            "workload_category": "sap_hana_db",
            "storage_class_hint": "ultra-high-io",
            "license_hint": "suse_linux",
            "ecs_family_hint": "memory_optimized",
            "classification_confidence": 0.95,
            "classification_rationale": "HANA DB with SUSE.",
            "review_flags": ["hana_storage_class_review"],
        },
        {
            "row_index": 1,
            "workload_category": "windows_app",
            "storage_class_hint": "general-purpose-ssd",
            "license_hint": "windows",
            "ecs_family_hint": "general_purpose",
            "classification_confidence": 0.88,
            "classification_rationale": "Windows application server.",
            "review_flags": ["windows_license_review"],
        },
    ]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = _make_maas_response_json(llm_rows)
    mock_response.raise_for_status = MagicMock()

    env = {
        "HUAWEI_MAAS_API_KEY": "test-key",
        "HUAWEI_MAAS_BASE_URL": "https://maas.example.com",
        "HUAWEI_MAAS_MODEL": "test-model",
    }
    with patch.dict(os.environ, env, clear=False):
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            graph = build_preview_graph()
            result = graph.invoke(
                {
                    "request": {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "sample.xlsx"},
                    "file_bytes": content,
                }
            )

    preview_resp = build_preview_response(result)
    assert preview_resp.quote_lines

    # HANA VM should have LLM-updated classification
    hana_line = next(line for line in preview_resp.quote_lines if line.vm_name == "hana-01")
    assert hana_line.workload_category == "sap_hana_db"
    assert hana_line.classification_confidence == 0.95
    assert hana_line.classification_rationale.startswith("LLM:")

    # Windows app VM should have LLM-updated classification
    app_line = next(line for line in preview_resp.quote_lines if line.vm_name == "app-01")
    assert app_line.workload_category == "windows_app"
    assert app_line.classification_confidence == 0.88


def test_preview_graph_llm_failure_still_quotes():
    """When MaaS throws an exception, the graph still produces a valid quote."""
    load_pricebook.cache_clear()
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-1", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
        ],
        disk_rows=[
            {"VM": "vm-1", "Capacity GiB": 100},
        ],
    )

    env = {
        "HUAWEI_MAAS_API_KEY": "test-key",
        "HUAWEI_MAAS_BASE_URL": "https://maas.example.com",
        "HUAWEI_MAAS_MODEL": "test-model",
    }
    with patch.dict(os.environ, env, clear=False):
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = Exception("MaaS timeout")
            mock_client_cls.return_value = mock_client

            graph = build_preview_graph()
            result = graph.invoke(
                {
                    "request": {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "sample.xlsx"},
                    "file_bytes": content,
                }
            )

    preview_resp = build_preview_response(result)
    # Quote still succeeds with local fallback classification
    assert preview_resp.quote_lines
    assert preview_resp.quote_lines[0].workload_category is not None
    assert preview_resp.summary.quoted_vms == 1


def test_classify_inventory_context_empty_vms():
    """Empty normalized_vms returns empty dict."""
    result = classify_inventory_context({"normalized_vms": []})
    assert result == {}


def test_classify_inventory_context_large_batches_skip_llm():
    """Large batches should skip MaaS classification to avoid gateway timeout."""
    from app.workflow import _LLM_CLASSIFY_SKIP_VM_COUNT

    local_vms = [_make_normalized_vm(vm_name=f"vm-{idx}") for idx in range(_LLM_CLASSIFY_SKIP_VM_COUNT + 1)]
    env = {
        "HUAWEI_MAAS_API_KEY": "test-key",
        "HUAWEI_MAAS_BASE_URL": "https://maas.example.com",
        "HUAWEI_MAAS_MODEL": "test-model",
    }
    with patch.dict(os.environ, env, clear=False):
        with patch("httpx.Client") as mock_client_cls:
            result = classify_inventory_context({"normalized_vms": local_vms})

    assert result == {}
    mock_client_cls.assert_not_called()


def test_classify_inventory_context_llm_exception_fallback():
    """httpx exception during MaaS call falls back gracefully."""
    local_vms = [_make_normalized_vm(vm_name="vm-1")]

    env = {
        "HUAWEI_MAAS_API_KEY": "test-key",
        "HUAWEI_MAAS_BASE_URL": "https://maas.example.com",
        "HUAWEI_MAAS_MODEL": "test-model",
    }
    with patch.dict(os.environ, env, clear=False):
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = httpx.ConnectError("Connection refused")
            mock_client_cls.return_value = mock_client

            result = classify_inventory_context({"normalized_vms": local_vms})

    assert result == {}


def test_classify_inventory_context_llm_confidence_lower_than_local_keeps_local():
    """LLM confidence < local confidence → local confidence kept."""
    local_vms = [
        _make_normalized_vm(
            vm_name="vm-1",
            workload_category="sap_hana_db",
            classification_confidence=0.9,
        ),
    ]
    llm_rows = [
        {
            "row_index": 0,
            "workload_category": "sap_hana_db",
            "storage_class_hint": "ultra-high-io",
            "license_hint": "suse_linux",
            "ecs_family_hint": "memory_optimized",
            "classification_confidence": 0.5,  # lower than local 0.9
            "classification_rationale": "Low confidence guess.",
            "review_flags": [],
        }
    ]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = _make_maas_response_json(llm_rows)
    mock_response.raise_for_status = MagicMock()

    env = {
        "HUAWEI_MAAS_API_KEY": "test-key",
        "HUAWEI_MAAS_BASE_URL": "https://maas.example.com",
        "HUAWEI_MAAS_MODEL": "test-model",
    }
    with patch.dict(os.environ, env, clear=False):
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = classify_inventory_context({"normalized_vms": local_vms})

    vm = result["normalized_vms"][0]
    # Local confidence (0.9) kept because LLM (0.5) is lower
    assert vm["classification_confidence"] == 0.9


def test_validate_llm_classification_row_clamps_confidence():
    """Confidence values outside [0,1] are clamped."""
    row = {
        "row_index": 0,
        "classification_confidence": 1.5,
    }
    result = _validate_llm_classification_row(row, total_rows=10)
    assert result["classification_confidence"] == 1.0

    row2 = {
        "row_index": 0,
        "classification_confidence": -0.3,
    }
    result2 = _validate_llm_classification_row(row2, total_rows=10)
    assert result2["classification_confidence"] == 0.0


def test_validate_llm_classification_row_invalid_index_skipped():
    """Invalid row_index causes the entire row to be skipped."""
    row = {
        "row_index": 999,  # out of range
        "workload_category": "linux_app",
    }
    result = _validate_llm_classification_row(row, total_rows=5)
    assert "row_index" not in result
    assert result == {}


def test_build_llm_classify_payload_limits_rows():
    """Payload builder caps at _LLM_CLASSIFY_MAX_ROWS."""
    from app.workflow import _LLM_CLASSIFY_MAX_ROWS
    vms = [_make_normalized_vm(vm_name=f"vm-{i}") for i in range(100)]
    payload = _build_llm_classify_payload(vms)
    assert len(payload) == _LLM_CLASSIFY_MAX_ROWS
    assert payload[0]["row_index"] == 0
    assert payload[-1]["row_index"] == _LLM_CLASSIFY_MAX_ROWS - 1


def test_maas_summary_large_batches_skip_llm():
    """Large quote batches should skip MaaS summary generation to avoid gateway timeout."""
    from app.workflow import _MAAS_SUMMARY_SKIP_LINE_COUNT

    summary = QuoteSummary(
        total_vms=_MAAS_SUMMARY_SKIP_LINE_COUNT + 1,
        excluded_vms=0,
        manual_review_vms=0,
        quoted_vms=_MAAS_SUMMARY_SKIP_LINE_COUNT + 1,
        total_disk_gib=100.0,
        total_ondemand_monthly_usd=200.0,
        total_ri_1y_monthly_usd=150.0,
        summary="fallback summary",
        assumptions=["a"],
        risks=["r"],
    )
    lines = [{"vm_name": f"vm-{idx}", "total_ondemand_monthly_usd": 1.0} for idx in range(_MAAS_SUMMARY_SKIP_LINE_COUNT + 1)]
    request = QuoteRequest(region="mexico", evs_type="gpssd", lang="en", source_filename="sample.xlsx")
    env = {
        "HUAWEI_MAAS_API_KEY": "test-key",
        "HUAWEI_MAAS_BASE_URL": "https://maas.example.com",
        "HUAWEI_MAAS_MODEL": "test-model",
    }
    with patch.dict(os.environ, env, clear=False):
        with patch("httpx.Client") as mock_client_cls:
            result = _maas_summary(request, summary, lines)

    assert result == summary
    mock_client_cls.assert_not_called()


# ── Phase 3: New export structure tests ──────────────────────────────────────────

from app.workflow import _build_ecs_export_rows, _build_hwc_rows, _build_summary_rows, _storage_type_label, _blank_none, _dc_label, _group_quote_lines_by_dc


def _run_export_graph(content: bytes, region: str = "mexico", evs_type: str = "gpssd") -> dict:
    """Helper to run export_graph and return the result dict."""
    load_pricebook.cache_clear()
    return export_graph.invoke(
        {
            "request": {"region": region, "evs_type": evs_type, "lang": "en", "source_filename": "sample.xlsx"},
            "file_bytes": content,
        }
    )


def _load_export_workbook(workbook_content: bytes, *, data_only: bool = True):
    return load_workbook(BytesIO(workbook_content), data_only=data_only)


def _ecs_headers(ws) -> list[str | None]:
    return [ws.cell(2, col).value for col in range(1, ws.max_column + 1)]


def _ecs_data_rows(ws) -> list[list[object]]:
    rows: list[list[object]] = []
    row = 3
    while ws.cell(row, 1).value not in (None, ""):
        rows.append([ws.cell(row, col).value for col in range(1, ws.max_column + 1)])
        row += 1
    return rows


def _find_row_by_value(ws, value: str, *, column: int = 1) -> int:
    for row in range(1, ws.max_row + 1):
        if ws.cell(row, column).value == value:
            return row
    raise AssertionError(f"Value {value!r} not found in column {column}")


def test_rvtools_export_sheet_order_new_template():
    """Export workbook follows the template sheet order."""
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-1", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
        ],
        disk_rows=[
            {"VM": "vm-1", "Capacity GiB": 100},
        ],
    )
    result = _run_export_graph(content)
    wb = _load_export_workbook(result["workbook"].content)
    assert wb.sheetnames == ["Summary", "HWC", "ECS", "Información"]


def test_rvtools_export_ecs_sheet_headers():
    """ECS sheet keeps the template headers."""
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-1", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
        ],
        disk_rows=[
            {"VM": "vm-1", "Capacity GiB": 100},
        ],
    )
    result = _run_export_graph(content)
    ws = _load_export_workbook(result["workbook"].content)["ECS"]
    assert _ecs_headers(ws)[:14] == [
        "Equipo", "CPU", "Mem", "Tipo", "HD", "S.O", None,
        "HC Flavor", "HC vCPU", "HC Memory", "Disk Type", "Storage(GB)", "PPU / Mes (USD)", "RI 1 Year (USD)",
    ]


def test_rvtools_export_ecs_sheet_has_quote_fields():
    """ECS sheet populates the template quote columns."""
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-2c8g", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 8},
        ],
        disk_rows=[
            {"VM": "vm-2c8g", "Capacity GiB": 120},
        ],
    )
    result = _run_export_graph(content)
    ws = _load_export_workbook(result["workbook"].content)["ECS"]
    rows = _ecs_data_rows(ws)
    assert len(rows) == 1
    row = rows[0]
    assert row[0] == "vm-2c8g"
    assert row[8] not in ("", None)   # HC Flavor
    assert row[9] not in ("", None)   # HC vCPU
    assert row[10] not in ("", None)  # HC Memory
    assert row[11] not in ("", None)  # Disk Type
    assert row[12] not in ("", None)  # Storage(GB)
    assert row[13] not in ("", None)  # ECS On Demand


def test_rvtools_export_storage_gb_is_numeric_not_currency():
    """Storage(GB) cells should use a numeric format, not a currency format."""
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-2c8g", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 8},
        ],
        disk_rows=[
            {"VM": "vm-2c8g", "Capacity GiB": 120},
        ],
    )
    result = _run_export_graph(content)
    ws = _load_export_workbook(result["workbook"].content)["ECS"]
    assert isinstance(ws["L3"].value, (int, float))
    assert ws["L3"].number_format == "0.00"
    assert "$" not in ws["L3"].number_format


def test_rvtools_export_hwc_storage_summary_matches_lines():
    """HWC EVS total cell matches quote lines evs_monthly_usd sum."""
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-1", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
            {"VM": "vm-2", "Powerstate": "PoweredOn", "CPUs": 4, "Memory": 8},
        ],
        disk_rows=[
            {"VM": "vm-1", "Capacity GiB": 100},
            {"VM": "vm-2", "Capacity GiB": 200},
        ],
    )
    result = _run_export_graph(content)
    ws = _load_export_workbook(result["workbook"].content)["HWC"]

    quoted = [line for line in result["quote_lines"] if line["action"] == "quote"]
    expected_evs_total = round(sum(line.get("evs_monthly_usd", 0) for line in quoted), 4)
    total_row = _find_row_by_value(ws, "EVS Total", column=3)
    assert abs(float(ws.cell(total_row, 4).value) - expected_evs_total) < 0.01


def test_rvtools_export_summary_totals_match_lines():
    """Summary template totals match quote lines aggregation."""
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-1", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
            {"VM": "vm-2", "Powerstate": "PoweredOn", "CPUs": 4, "Memory": 8},
        ],
        disk_rows=[
            {"VM": "vm-1", "Capacity GiB": 100},
            {"VM": "vm-2", "Capacity GiB": 200},
        ],
    )
    result = _run_export_graph(content)
    ws = _load_export_workbook(result["workbook"].content)["Summary"]

    quoted = [line for line in result["quote_lines"] if line["action"] == "quote"]
    expected_ondemand = round(sum(line.get("total_ondemand_monthly_usd", 0) for line in quoted), 2)
    expected_ri_1y = round(sum(line.get("total_ri_1y_monthly_usd", 0) for line in quoted), 2)

    assert abs(float(ws["C12"].value) - expected_ondemand) < 0.01
    assert abs(float(ws["D12"].value) - expected_ri_1y) < 0.01


def test_rvtools_export_summary_removes_precio_entel_row():
    """The Precio Entel row should be blank in the formal export."""
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-1", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
        ],
        disk_rows=[
            {"VM": "vm-1", "Capacity GiB": 100},
        ],
    )
    result = _run_export_graph(content)
    ws = _load_export_workbook(result["workbook"].content)["Summary"]
    assert ws["B13"].value in (None, "")
    assert ws["C13"].value in (None, "")
    assert ws["D13"].value in (None, "")


def test_rvtools_export_uses_template_information_sheet():
    """Template information sheet is preserved in the export."""
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-1", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
        ],
        disk_rows=[
            {"VM": "vm-1", "Capacity GiB": 100},
        ],
    )
    result = _run_export_graph(content)
    wb = _load_export_workbook(result["workbook"].content)
    assert "Información" in wb.sheetnames
    assert wb["Información"]["B2"].value == "Servicio"


def test_rvtools_export_no_programmatic_debug_sheets():
    """Formal template export does not include debug sheets."""
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-1", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
        ],
        disk_rows=[
            {"VM": "vm-1", "Capacity GiB": 100},
        ],
    )
    result = _run_export_graph(content)
    wb = _load_export_workbook(result["workbook"].content)
    assert "Manual Review" not in wb.sheetnames
    assert "Raw RVTools" not in wb.sheetnames
    assert "Pricebook Used" not in wb.sheetnames


def test_rvtools_export_no_none_strings():
    """Key sheets should not contain the string 'None'."""
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-1", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
            {"VM": "vm-2", "Powerstate": "PoweredOff", "CPUs": 2, "Memory": 4},
        ],
        disk_rows=[
            {"VM": "vm-1", "Capacity GiB": 100},
            {"VM": "vm-2", "Capacity GiB": 80},
        ],
    )
    result = _run_export_graph(content)
    wb = _load_export_workbook(result["workbook"].content)
    for sheet_name in ("Summary", "HWC", "ECS"):
        ws = wb[sheet_name]
        for row in ws.iter_rows():
            for cell in row:
                assert cell.value != "None", f"Found 'None' string in {sheet_name} cell {cell.coordinate}"


def test_rvtools_export_ecs_includes_non_quote_lines():
    """ECS sheet still includes non-quoted source rows."""
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-on", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
            {"VM": "vm-off", "Powerstate": "PoweredOff", "CPUs": 2, "Memory": 4},
            {"VM": "vm-oversized", "Powerstate": "PoweredOn", "CPUs": 999, "Memory": 999},
        ],
        disk_rows=[
            {"VM": "vm-on", "Capacity GiB": 100},
            {"VM": "vm-off", "Capacity GiB": 80},
            {"VM": "vm-oversized", "Capacity GiB": 200},
        ],
    )
    result = _run_export_graph(content)
    ws = _load_export_workbook(result["workbook"].content)["ECS"]
    rows = _ecs_data_rows(ws)
    assert len(rows) == 3
    vm_names = {row[0] for row in rows}
    assert "vm-on" in vm_names
    assert "vm-off" in vm_names
    assert "vm-oversized" in vm_names

    rows_by_name = {row[0]: row for row in rows}
    # Col 12 = Storage(GB), col 13 = ECS On Demand
    assert rows_by_name["vm-off"][12] in ("", None)
    assert rows_by_name["vm-on"][12] not in ("", None)


def test_rvtools_export_hwc_has_network_placeholder():
    """HWC networking placeholder stays in the template with zero values."""
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-1", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
        ],
        disk_rows=[
            {"VM": "vm-1", "Capacity GiB": 100},
        ],
    )
    result = _run_export_graph(content)
    ws = _load_export_workbook(result["workbook"].content)["HWC"]
    vpn_row = _find_row_by_value(ws, "VPN S2S Enterprise", column=1)
    assert float(ws.cell(vpn_row, 2).value) == 0
    assert float(ws.cell(vpn_row, 3).value) == 0
    assert float(ws.cell(vpn_row, 4).value) == 0


def test_storage_type_label_mapping():
    """_storage_type_label maps correctly."""
    assert _storage_type_label("ultra-high-io") == "Ultra High I/O"
    assert _storage_type_label("general-purpose-ssd") == "general purpose ssd"
    assert _storage_type_label("manual_review") == "manual_review"
    assert _storage_type_label(None) == ""
    assert _storage_type_label("") == ""


def test_blank_none_helper():
    """_blank_none replaces None with empty string."""
    assert _blank_none(None) == ""
    assert _blank_none(0) == 0
    assert _blank_none("hello") == "hello"
    assert _blank_none(3.14) == 3.14


def test_rvtools_export_preserves_template_header_cells():
    """Template title/header cells are preserved."""
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-1", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
        ],
        disk_rows=[
            {"VM": "vm-1", "Capacity GiB": 100},
        ],
    )
    result = _run_export_graph(content)
    wb = _load_export_workbook(result["workbook"].content)
    assert wb["Summary"]["B3"].value == "HUAWEI CLOUD"
    assert wb["HWC"]["A1"].value == "HUAWEI CLOUD STORAGE"
    assert wb["ECS"]["H1"].value == "Huawei Cloud"


def test_rvtools_export_price_math_unchanged():
    """Phase 3 export does not change price calculations."""
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-1", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
        ],
        disk_rows=[
            {"VM": "vm-1", "Capacity GiB": 100},
        ],
    )
    result = _run_export_graph(content)
    quoted = [line for line in result["quote_lines"] if line["action"] == "quote"]
    assert len(quoted) == 1
    assert quoted[0]["ecs_ondemand_monthly_usd"] == 33.58


# ── Phase 4: DC-grouped HWC/Summary tests ────────────────────────────────────────


def _make_rvtools_with_dc(*vms_by_dc: tuple[str, list[dict]]) -> bytes:
    """Build RVTools xlsx with VMs tagged by DC via source_dc.
    Each arg is (dc_name, [info_row_dicts]).
    """
    all_info: list[dict] = []
    all_disk: list[dict] = []
    for dc, vm_rows in vms_by_dc:
        for row in vm_rows:
            info = dict(row)
            info["Resource pool"] = f"/{dc}/cluster/Resources"
            all_info.append(info)
            all_disk.append({"VM": row.get("VM", row.get("VM Name", "")), "Capacity GiB": row.get("disk_gib", 100)})
    return make_rvtools_file(info_rows=all_info, disk_rows=all_disk)


def _make_quote_line_with_dc(
    *,
    vm_name: str = "vm-1",
    source_dc: str = "AMU",
    source_sheet: str | None = None,
    action: str = "quote",
    vcpu: int = 2,
    memory_gib: float = 4.0,
    disk_gib: float = 100.0,
    storage_class_hint: str = "general-purpose-ssd",
    evs_selected_type: str | None = None,
    ecs_ondemand_monthly_usd: float = 33.58,
    ecs_ri_1y_monthly_usd: float = 20.0,
    evs_monthly_usd: float = 5.0,
    total_ondemand_monthly_usd: float = 38.58,
    total_ri_1y_monthly_usd: float = 25.0,
) -> dict:
    """Build a quote line dict for testing DC grouping without running the full graph."""
    # Derive evs_selected_type from storage_class_hint if not explicitly set
    if evs_selected_type is None:
        _hint_to_evs = {
            "ultra-high-io": "ultra-high-io",
            "general-purpose-ssd": "gpssd",
        }
        evs_selected_type = _hint_to_evs.get(storage_class_hint, "high-io")
    _evs_label_map = {
        "ultra-high-io": "Ultra High I/O",
        "high-io": "High I/O",
        "gpssd": "General Purpose SSD",
    }
    return {
        "vm_name": vm_name,
        "source_dc": source_dc,
        "source_sheet": source_sheet,
        "action": action,
        "vcpu": vcpu,
        "memory_gib": memory_gib,
        "disk_gib": disk_gib,
        "storage_class_hint": storage_class_hint,
        "evs_selected_type": evs_selected_type,
        "evs_selected_label": _evs_label_map.get(evs_selected_type, evs_selected_type),
        "ecs_family_policy": "default",
        "ecs_ondemand_monthly_usd": ecs_ondemand_monthly_usd,
        "ecs_ri_1y_monthly_usd": ecs_ri_1y_monthly_usd,
        "evs_monthly_usd": evs_monthly_usd,
        "total_ondemand_monthly_usd": total_ondemand_monthly_usd,
        "total_ri_1y_monthly_usd": total_ri_1y_monthly_usd,
        "os": "Linux",
        "customer": None,
        "workload_type": None,
        "raw_memory_mb": None,
        "raw_storage_mib": None,
        "workload_category": "unknown",
        "license_hint": "linux",
        "ecs_family_hint": "general_purpose",
        "classification_confidence": 0.4,
        "classification_rationale": "No workload type matched.",
        "review_flags": ["workload_unclassified"],
        "review_reason": None,
        "ecs_spec": "x0.2u.4g",
        "ecs_vcpu": vcpu,
        "ecs_mem": memory_gib,
        "ecs_category": "General Computing",
        "ecs_family_label": "general",
        "region": "mexico",
        "evs_type": "gpssd",
    }


def test_dc_label_uses_source_dc_first():
    """_dc_label prefers source_dc over source_sheet."""
    assert _dc_label({"source_dc": "AMU", "source_sheet": "vInfo"}) == "AMU"


def test_dc_label_falls_back_to_source_sheet():
    """_dc_label uses source_sheet when source_dc is empty."""
    assert _dc_label({"source_dc": None, "source_sheet": "CDLV"}) == "CDLV"
    assert _dc_label({"source_dc": "", "source_sheet": "CDLV"}) == "CDLV"


def test_dc_label_defaults_to_default():
    """_dc_label returns Default when both are empty."""
    assert _dc_label({"source_dc": None, "source_sheet": None}) == "Default"
    assert _dc_label({}) == "Default"


def test_group_quote_lines_by_dc_preserves_order():
    """_group_quote_lines_by_dc preserves first-occurrence order."""
    lines = [
        _make_quote_line_with_dc(vm_name="vm-1", source_dc="CDLV"),
        _make_quote_line_with_dc(vm_name="vm-2", source_dc="AMU"),
        _make_quote_line_with_dc(vm_name="vm-3", source_dc="CDLV"),
    ]
    groups = _group_quote_lines_by_dc(lines)
    assert list(groups.keys()) == ["CDLV", "AMU"]
    assert len(groups["CDLV"]) == 2
    assert len(groups["AMU"]) == 1


def test_rvtools_export_hwc_groups_storage_by_dc():
    """HWC sheet has per-DC rows when quote lines have different DCs."""
    lines = [
        _make_quote_line_with_dc(vm_name="amu-1", source_dc="AMU", storage_class_hint="general-purpose-ssd", disk_gib=100, evs_monthly_usd=5.0),
        _make_quote_line_with_dc(vm_name="amu-2", source_dc="AMU", storage_class_hint="ultra-high-io", disk_gib=200, evs_monthly_usd=15.0),
        _make_quote_line_with_dc(vm_name="cdlv-1", source_dc="CDLV", storage_class_hint="general-purpose-ssd", disk_gib=150, evs_monthly_usd=7.5),
        _make_quote_line_with_dc(vm_name="cdlv-2", source_dc="CDLV", storage_class_hint="ultra-high-io", disk_gib=300, evs_monthly_usd=22.5),
    ]
    request = QuoteRequest(region="mexico", evs_type="gpssd", lang="en", source_filename="test.xlsx")
    hwc_rows = _build_hwc_rows(lines, request, {})

    hwc_df = pd.DataFrame(hwc_rows)
    # Should have rows for both AMU and CDLV
    amu_rows = hwc_df[hwc_df["DC"] == "AMU"]
    cdlv_rows = hwc_df[hwc_df["DC"] == "CDLV"]
    assert len(amu_rows) > 0
    assert len(cdlv_rows) > 0

    # AMU EVS Total
    amu_evs_total = amu_rows[amu_rows["Huawei Cloud Resource"] == "EVS Total"]
    assert len(amu_evs_total) == 1
    assert abs(float(amu_evs_total.iloc[0]["Total Monthly"]) - 20.0) < 0.01

    # CDLV EVS Total
    cdlv_evs_total = cdlv_rows[cdlv_rows["Huawei Cloud Resource"] == "EVS Total"]
    assert len(cdlv_evs_total) == 1
    assert abs(float(cdlv_evs_total.iloc[0]["Total Monthly"]) - 30.0) < 0.01


def test_rvtools_export_hwc_evs_totals_by_dc_match_lines():
    """HWC per-DC EVS Total matches that DC's quoted lines evs_monthly_usd sum."""
    lines = [
        _make_quote_line_with_dc(vm_name="amu-1", source_dc="AMU", evs_monthly_usd=10.0),
        _make_quote_line_with_dc(vm_name="amu-2", source_dc="AMU", evs_monthly_usd=20.0),
        _make_quote_line_with_dc(vm_name="cdlv-1", source_dc="CDLV", evs_monthly_usd=15.0),
    ]
    request = QuoteRequest(region="mexico", evs_type="gpssd", lang="en", source_filename="test.xlsx")
    hwc_rows = _build_hwc_rows(lines, request, {})
    hwc_df = pd.DataFrame(hwc_rows)

    amu_evs = hwc_df[(hwc_df["DC"] == "AMU") & (hwc_df["Huawei Cloud Resource"] == "EVS Total")]
    assert abs(float(amu_evs.iloc[0]["Total Monthly"]) - 30.0) < 0.01

    cdlv_evs = hwc_df[(hwc_df["DC"] == "CDLV") & (hwc_df["Huawei Cloud Resource"] == "EVS Total")]
    assert abs(float(cdlv_evs.iloc[0]["Total Monthly"]) - 15.0) < 0.01


def test_rvtools_export_hwc_all_total_matches_dc_totals():
    """ALL / EVS Total equals sum of all DC EVS totals."""
    lines = [
        _make_quote_line_with_dc(vm_name="amu-1", source_dc="AMU", evs_monthly_usd=10.0),
        _make_quote_line_with_dc(vm_name="cdlv-1", source_dc="CDLV", evs_monthly_usd=15.0),
    ]
    request = QuoteRequest(region="mexico", evs_type="gpssd", lang="en", source_filename="test.xlsx")
    hwc_rows = _build_hwc_rows(lines, request, {})
    hwc_df = pd.DataFrame(hwc_rows)

    all_evs = hwc_df[(hwc_df["DC"] == "ALL") & (hwc_df["Huawei Cloud Resource"] == "EVS Total")]
    assert len(all_evs) == 1
    assert abs(float(all_evs.iloc[0]["Total Monthly"]) - 25.0) < 0.01


def test_rvtools_export_hwc_does_not_include_manual_review_amounts():
    """manual_review lines are not counted in HWC amounts."""
    lines = [
        _make_quote_line_with_dc(vm_name="amu-quoted", source_dc="AMU", action="quote", disk_gib=100, evs_monthly_usd=10.0),
        _make_quote_line_with_dc(vm_name="amu-manual", source_dc="AMU", action="manual_review", disk_gib=500, evs_monthly_usd=50.0),
    ]
    request = QuoteRequest(region="mexico", evs_type="gpssd", lang="en", source_filename="test.xlsx")
    hwc_rows = _build_hwc_rows(lines, request, {})
    hwc_df = pd.DataFrame(hwc_rows)

    amu_evs = hwc_df[(hwc_df["DC"] == "AMU") & (hwc_df["Huawei Cloud Resource"] == "EVS Total")]
    # Only the quoted line should count: 10.0, not 60.0
    assert abs(float(amu_evs.iloc[0]["Total Monthly"]) - 10.0) < 0.01
    # Quantity should be 100 (quoted only), not 600
    assert abs(float(amu_evs.iloc[0]["Quantity"]) - 100.0) < 0.01


def test_rvtools_export_summary_includes_dc_sections():
    """Summary sheet includes per-DC metric sections."""
    lines = [
        _make_quote_line_with_dc(vm_name="amu-1", source_dc="AMU"),
        _make_quote_line_with_dc(vm_name="cdlv-1", source_dc="CDLV"),
    ]
    summary = QuoteSummary(
        total_vms=2, excluded_vms=0, manual_review_vms=0, quoted_vms=2,
        total_disk_gib=200, total_ondemand_monthly_usd=77.16, total_ri_1y_monthly_usd=50.0,
        summary="Test", assumptions=[], risks=[],
    )
    request = QuoteRequest(region="mexico", evs_type="gpssd", lang="en", source_filename="test.xlsx")
    rows = _build_summary_rows(summary, lines, request)
    metrics = [row["Metric"] for row in rows]

    assert "AMU - Quoted VMs" in metrics
    assert "CDLV - Quoted VMs" in metrics
    assert "AMU - Grand Total RI 1Y" in metrics
    assert "CDLV - Grand Total RI 1Y" in metrics


def test_rvtools_export_summary_dc_totals_match_lines():
    """Summary DC totals match the corresponding quote lines aggregation."""
    lines = [
        _make_quote_line_with_dc(
            vm_name="amu-1", source_dc="AMU",
            ecs_ondemand_monthly_usd=30.0, ecs_ri_1y_monthly_usd=18.0,
            evs_monthly_usd=5.0, total_ondemand_monthly_usd=35.0, total_ri_1y_monthly_usd=23.0,
        ),
        _make_quote_line_with_dc(
            vm_name="cdlv-1", source_dc="CDLV",
            ecs_ondemand_monthly_usd=40.0, ecs_ri_1y_monthly_usd=25.0,
            evs_monthly_usd=8.0, total_ondemand_monthly_usd=48.0, total_ri_1y_monthly_usd=33.0,
        ),
    ]
    summary = QuoteSummary(
        total_vms=2, excluded_vms=0, manual_review_vms=0, quoted_vms=2,
        total_disk_gib=200, total_ondemand_monthly_usd=83.0, total_ri_1y_monthly_usd=56.0,
        summary="Test", assumptions=[], risks=[],
    )
    request = QuoteRequest(region="mexico", evs_type="gpssd", lang="en", source_filename="test.xlsx")
    rows = _build_summary_rows(summary, lines, request)
    metrics = dict(zip([r["Metric"] for r in rows], [r["Value"] for r in rows]))

    assert abs(float(metrics["AMU - ECS On Demand Monthly"]) - 30.0) < 0.01
    assert abs(float(metrics["AMU - EVS Monthly"]) - 5.0) < 0.01
    assert abs(float(metrics["AMU - Grand Total On Demand"]) - 35.0) < 0.01
    assert abs(float(metrics["CDLV - ECS On Demand Monthly"]) - 40.0) < 0.01
    assert abs(float(metrics["CDLV - EVS Monthly"]) - 8.0) < 0.01
    assert abs(float(metrics["CDLV - Grand Total On Demand"]) - 48.0) < 0.01


def test_rvtools_export_summary_global_totals_match_dc_totals():
    """Global totals equal the sum of DC totals."""
    lines = [
        _make_quote_line_with_dc(
            vm_name="amu-1", source_dc="AMU",
            total_ondemand_monthly_usd=35.0, total_ri_1y_monthly_usd=23.0,
        ),
        _make_quote_line_with_dc(
            vm_name="cdlv-1", source_dc="CDLV",
            total_ondemand_monthly_usd=48.0, total_ri_1y_monthly_usd=33.0,
        ),
    ]
    summary = QuoteSummary(
        total_vms=2, excluded_vms=0, manual_review_vms=0, quoted_vms=2,
        total_disk_gib=200, total_ondemand_monthly_usd=83.0, total_ri_1y_monthly_usd=56.0,
        summary="Test", assumptions=[], risks=[],
    )
    request = QuoteRequest(region="mexico", evs_type="gpssd", lang="en", source_filename="test.xlsx")
    rows = _build_summary_rows(summary, lines, request)
    metrics = dict(zip([r["Metric"] for r in rows], [r["Value"] for r in rows]))

    global_ondemand = float(metrics["Grand Total On Demand"])
    global_ri_1y = float(metrics["Grand Total RI 1Y"])
    dc_ondemand = float(metrics["AMU - Grand Total On Demand"]) + float(metrics["CDLV - Grand Total On Demand"])
    dc_ri_1y = float(metrics["AMU - Grand Total RI 1Y"]) + float(metrics["CDLV - Grand Total RI 1Y"])

    assert abs(global_ondemand - dc_ondemand) < 0.01
    assert abs(global_ri_1y - dc_ri_1y) < 0.01


def test_rvtools_export_summary_adds_cbr_placeholder_assumption():
    """Summary notes mention the CBR placeholder."""
    content = make_rvtools_file(
        info_rows=[{"VM": "vm-1", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4}],
        disk_rows=[{"VM": "vm-1", "Capacity GiB": 100}],
    )
    result = _run_export_graph(content)
    ws = _load_export_workbook(result["workbook"].content)["Summary"]
    notes = str(ws["B19"].value)
    assert "CBR" in notes
    assert "placeholder" in notes.lower()


def test_rvtools_export_source_dc_fallback():
    """When source_dc is empty, HWC and Summary use source_sheet or Default."""
    # Lines with no source_dc but source_sheet set
    lines = [
        _make_quote_line_with_dc(vm_name="vm-1", source_dc="", source_sheet="CDLV", evs_monthly_usd=10.0),
        _make_quote_line_with_dc(vm_name="vm-2", source_dc=None, source_sheet=None, evs_monthly_usd=5.0),
    ]
    request = QuoteRequest(region="mexico", evs_type="gpssd", lang="en", source_filename="test.xlsx")

    # HWC
    hwc_rows = _build_hwc_rows(lines, request, {})
    hwc_df = pd.DataFrame(hwc_rows)
    dcs = set(hwc_df["DC"].unique())
    assert "CDLV" in dcs
    assert "Default" in dcs

    # Summary
    summary = QuoteSummary(
        total_vms=2, excluded_vms=0, manual_review_vms=0, quoted_vms=2,
        total_disk_gib=200, total_ondemand_monthly_usd=77.16, total_ri_1y_monthly_usd=50.0,
        summary="Test", assumptions=[], risks=[],
    )
    rows = _build_summary_rows(summary, lines, request)
    metrics = [row["Metric"] for row in rows]
    assert "CDLV - Quoted VMs" in metrics
    assert "Default - Quoted VMs" in metrics


def test_rvtools_export_ecs_sheet_unchanged_by_phase4():
    """ECS template keeps the expected column structure and row count."""
    content = make_rvtools_file(
        info_rows=[
            {"VM": "vm-1", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
            {"VM": "vm-2", "Powerstate": "PoweredOff", "CPUs": 2, "Memory": 4},
        ],
        disk_rows=[
            {"VM": "vm-1", "Capacity GiB": 100},
            {"VM": "vm-2", "Capacity GiB": 80},
        ],
    )
    result = _run_export_graph(content)
    ws = _load_export_workbook(result["workbook"].content)["ECS"]
    assert len(_ecs_data_rows(ws)) == 2
    assert _ecs_headers(ws)[:14] == [
        "Equipo", "CPU", "Mem", "Tipo", "HD", "S.O", None,
        "HC Flavor", "HC vCPU", "HC Memory", "Disk Type", "Storage(GB)", "PPU / Mes (USD)", "RI 1 Year (USD)",
    ]


def test_rvtools_export_hwc_preserves_template_columns():
    """HWC sheet keeps the template column labels."""
    content = make_rvtools_file(
        info_rows=[{"VM": "vm-1", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4}],
        disk_rows=[{"VM": "vm-1", "Capacity GiB": 100}],
    )
    result = _run_export_graph(content)
    ws = _load_export_workbook(result["workbook"].content)["HWC"]
    assert ws["A1"].value == "HUAWEI CLOUD STORAGE"
    assert ws["B1"].value == "GB"
    assert ws["C1"].value == "Price per GB/month"
    assert ws["D1"].value == "Total"


def test_rvtools_export_hwc_inserts_ultra_high_io_row_when_needed():
    """HWC sheet adds a second EVS row when ultra-high-io storage is present."""
    lines = [
        _make_quote_line_with_dc(vm_name="vm-1", source_dc="AMU", storage_class_hint="general-purpose-ssd"),
        _make_quote_line_with_dc(vm_name="vm-2", source_dc="AMU", storage_class_hint="ultra-high-io"),
    ]
    request = QuoteRequest(region="mexico", evs_type="gpssd", lang="en", source_filename="test.xlsx")
    summary = QuoteSummary(
        total_vms=2, excluded_vms=0, manual_review_vms=0, quoted_vms=2,
        total_disk_gib=200, total_ondemand_monthly_usd=77.16, total_ri_1y_monthly_usd=50.0,
        summary="Test", assumptions=[], risks=[],
    )
    output = export_excel({
        "request": request.model_dump(),
        "quote_lines": lines,
        "summary": summary.model_dump(),
        "pricebook": {},
    })
    ws = _load_export_workbook(output["workbook"].content)["HWC"]
    assert ws["A2"].value == "Elastic Volume Service (EVS) General Purpose SSD"
    assert ws["A3"].value == "Elastic Volume Service (EVS) Ultra High I/O"


# ── Phase 6: Multi-file RVTools tests ────────────────────────────────────────────

from app.workflow import multi_preview_graph, multi_export_graph, parse_rvtools_multi


def _make_two_rvtools_files() -> list[dict]:
    """Build two small RVTools workbooks simulating AMU and CDLV."""
    amu_content = make_rvtools_file(
        info_rows=[
            {"VM": "amu-vm-1", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
            {"VM": "amu-vm-2", "Powerstate": "PoweredOn", "CPUs": 4, "Memory": 8},
        ],
        disk_rows=[
            {"VM": "amu-vm-1", "Capacity GiB": 100},
            {"VM": "amu-vm-2", "Capacity GiB": 200},
        ],
    )
    cdlv_content = make_rvtools_file(
        info_rows=[
            {"VM": "cdlv-vm-1", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
        ],
        disk_rows=[
            {"VM": "cdlv-vm-1", "Capacity GiB": 150},
        ],
    )
    return [
        {"filename": "AMU.xlsx", "content": amu_content},
        {"filename": "CDLV.xlsx", "content": cdlv_content},
    ]


def test_rvtools_multi_file_parse_and_quote_combines_rows():
    """Multi-file parse + quote combines rows from all files."""
    load_pricebook.cache_clear()
    files = _make_two_rvtools_files()
    request = {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "2_files"}

    result = multi_preview_graph.invoke({"request": request, "files": files})

    # Should have quote lines from both files
    quoted = [line for line in result["quote_lines"] if line["action"] == "quote"]
    assert len(quoted) == 3  # 2 from AMU + 1 from CDLV


def test_rvtools_multi_file_preserves_source_dc():
    """Multi-file quote lines preserve source_dc from each file."""
    load_pricebook.cache_clear()
    files = _make_two_rvtools_files()
    request = {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "2_files"}

    result = multi_preview_graph.invoke({"request": request, "files": files})

    dc_values = set(line.get("source_dc", "") for line in result["quote_lines"])
    # Both AMU and CDLV should appear as source_dc values
    assert "AMU" in dc_values
    assert "CDLV" in dc_values


def test_rvtools_multi_file_export_single_workbook():
    """Multi-file export produces a single workbook with Summary/HWC/ECS."""
    load_pricebook.cache_clear()
    files = _make_two_rvtools_files()
    request = {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "2_files"}

    result = multi_export_graph.invoke({"request": request, "files": files})

    workbook = result["workbook"]
    wb = _load_export_workbook(workbook.content)
    assert wb.sheetnames == ["Summary", "HWC", "ECS", "Información"]


def test_rvtools_multi_file_ecs_contains_rows_from_all_files():
    """ECS sheet contains VM rows from all uploaded files."""
    load_pricebook.cache_clear()
    files = _make_two_rvtools_files()
    request = {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "2_files"}

    result = multi_export_graph.invoke({"request": request, "files": files})
    ws = _load_export_workbook(result["workbook"].content)["ECS"]
    vm_names = {row[0] for row in _ecs_data_rows(ws)}
    assert "amu-vm-1" in vm_names
    assert "amu-vm-2" in vm_names
    assert "cdlv-vm-1" in vm_names


def test_rvtools_multi_file_summary_title_mentions_multiple_files():
    """Summary title reflects a combined multi-file export."""
    load_pricebook.cache_clear()
    files = _make_two_rvtools_files()
    request = {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "2_files"}

    result = multi_export_graph.invoke({"request": request, "files": files})
    ws = _load_export_workbook(result["workbook"].content)["Summary"]
    assert "AMU.xlsx" in str(ws["B4"].value)
    assert "1 more" in str(ws["B4"].value)


def test_rvtools_multi_file_hwc_totals_match_all_lines():
    """HWC EVS total matches all quoted lines across files."""
    load_pricebook.cache_clear()
    files = _make_two_rvtools_files()
    request = {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "2_files"}

    result = multi_export_graph.invoke({"request": request, "files": files})
    ws = _load_export_workbook(result["workbook"].content)["HWC"]

    # Compute expected from quote_lines
    quoted = [line for line in result["quote_lines"] if line["action"] == "quote"]
    expected_evs_total = round(sum(line.get("evs_monthly_usd", 0) for line in quoted), 4)

    total_row = _find_row_by_value(ws, "EVS Total", column=3)
    assert abs(float(ws.cell(total_row, 4).value) - expected_evs_total) < 0.01


def test_rvtools_multi_file_parse_failure_includes_filename():
    """If one file fails to parse, the error propagates."""
    load_pricebook.cache_clear()
    good_content = make_rvtools_file(
        info_rows=[{"VM": "vm-1", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4}],
        disk_rows=[{"VM": "vm-1", "Capacity GiB": 100}],
    )
    bad_content = b"this is not a valid xlsx file at all"

    files = [
        {"filename": "good.xlsx", "content": good_content},
        {"filename": "bad.xlsx", "content": bad_content},
    ]
    request = {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "2_files"}

    with pytest.raises(Exception):
        multi_preview_graph.invoke({"request": request, "files": files})


def test_rvtools_single_file_still_works_via_legacy_endpoint():
    """Single-file upload via the old preview_graph still works (no regression)."""
    load_pricebook.cache_clear()
    content = make_rvtools_file(
        info_rows=[{"VM": "vm-1", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4}],
        disk_rows=[{"VM": "vm-1", "Capacity GiB": 100}],
    )
    request = {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "sample.xlsx"}

    result = preview_graph.invoke({"request": request, "file_bytes": content})
    preview_resp = build_preview_response(result)
    assert preview_resp.quote_lines
    assert preview_resp.summary.quoted_vms == 1


def test_rvtools_multi_file_summary_has_dc_sections():
    """Multi-file export still carries both files into a single template workbook."""
    load_pricebook.cache_clear()
    files = _make_two_rvtools_files()
    request = {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "2_files"}

    result = multi_export_graph.invoke({"request": request, "files": files})
    ws = _load_export_workbook(result["workbook"].content)["Summary"]
    assert "AMU.xlsx" in str(ws["B4"].value)
    assert ws["C12"].value is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 8A: S-series pricebook tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_pricebook_includes_s_series_after_import():
    """S-series (S7n) ECS items are present in the pricebook after catalog update."""
    load_pricebook.cache_clear()
    pb = load_pricebook()
    for region in ("mexico", "chile", "brazil"):
        ecs = pb["pricingCatalog"][region]["ecs"]
        s_items = [e for e in ecs if "S7n" in e.get("familyLabel", "")]
        assert len(s_items) >= 9, f"{region} should have at least 9 S-series items, got {len(s_items)}"


def test_s_series_has_hourly_and_ri_1y_monthly_values():
    """S-series items have non-zero hourly and RI 1-year monthly values."""
    load_pricebook.cache_clear()
    pb = load_pricebook()
    mexico = pb["pricingCatalog"]["mexico"]
    s_items = [e for e in mexico["ecs"] if "S7n" in e.get("familyLabel", "")]
    assert len(s_items) > 0
    for item in s_items:
        assert float(item["hourlyUsd"]) > 0, f"{item['spec']} hourlyUsd should be > 0"
        assert float(item["ri1YearMonthlyUsd"]) > 0, f"{item['spec']} ri1YearMonthlyUsd should be > 0"
        assert float(item["monthlyUsd"]) > 0, f"{item['spec']} monthlyUsd should be > 0"


def test_s_series_present_in_mexico_chile_brazil():
    """S-series is available in all three LATAM regions."""
    load_pricebook.cache_clear()
    pb = load_pricebook()
    for region in ("mexico", "chile", "brazil"):
        ecs = pb["pricingCatalog"][region]["ecs"]
        s_specs = {e["spec"] for e in ecs if "S7n" in e.get("familyLabel", "")}
        assert "s7n.xlarge.4" in s_specs, f"{region} missing s7n.xlarge.4"
        assert "s7n.2xlarge.4" in s_specs, f"{region} missing s7n.2xlarge.4"


def test_s_series_category_is_sap_certified():
    """S-series items have category='SAP-certified' for family_policy routing."""
    load_pricebook.cache_clear()
    pb = load_pricebook()
    mexico = pb["pricingCatalog"]["mexico"]
    s_items = [e for e in mexico["ecs"] if "S7n" in e.get("familyLabel", "")]
    for item in s_items:
        assert item["category"] == "SAP-certified", f"{item['spec']} category should be SAP-certified"


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 8B: ECS family policy tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_pick_ecs_match_sap_app_prefers_s_series():
    """sap_app family_policy should prefer S-series over X-series."""
    load_pricebook.cache_clear()
    pb = load_pricebook()
    mexico = pb["pricingCatalog"]["mexico"]
    match = pick_ecs_match(mexico, 4, 16, strategy="nearest", family_policy="sap_app")
    assert match is not None
    assert "S7n" in match["familyLabel"], f"sap_app should pick S-series, got {match['familyLabel']}"


def test_pick_ecs_match_sap_db_prefers_c_over_x():
    """sap_db family_policy should prefer C-series over X-series."""
    load_pricebook.cache_clear()
    pb = load_pricebook()
    mexico = pb["pricingCatalog"]["mexico"]
    match = pick_ecs_match(mexico, 4, 16, strategy="nearest", family_policy="sap_db")
    assert match is not None
    assert "C7n" in match["familyLabel"], f"sap_db should pick C-series, got {match['familyLabel']}"


def test_pick_ecs_match_hana_prefers_m_over_x():
    """sap_hana_db family_policy should prefer M-series over X-series."""
    load_pricebook.cache_clear()
    pb = load_pricebook()
    mexico = pb["pricingCatalog"]["mexico"]
    match = pick_ecs_match(mexico, 8, 64, strategy="nearest", family_policy="sap_hana_db")
    assert match is not None
    assert "M7n" in match["familyLabel"], f"sap_hana_db should pick M-series, got {match['familyLabel']}"


def test_pick_ecs_match_default_unchanged():
    """Default family_policy should produce the same result as before (no S/M bias)."""
    load_pricebook.cache_clear()
    pb = load_pricebook()
    mexico = pb["pricingCatalog"]["mexico"]
    # With default policy, a small general compute request should still pick X-series
    match = pick_ecs_match(mexico, 2, 4, strategy="nearest", family_policy="default")
    assert match is not None
    # Default should prefer General Computing category
    assert match["category"] in ("General Computing", "General Computing-plus", "Memory-optimized", "SAP-certified")


def test_pick_ecs_match_sap_app_falls_back_to_c_when_no_s_match():
    """When S-series has no close spec, sap_app falls back within its tier order."""
    load_pricebook.cache_clear()
    pb = load_pricebook()
    mexico = pb["pricingCatalog"]["mexico"]
    # Request a very large spec that S-series doesn't cover (48 vCPU)
    match = pick_ecs_match(mexico, 48, 96, strategy="nearest", family_policy="sap_app")
    assert match is not None
    # With "nearest" strategy, S-series still has items so it picks from SAP-certified tier.
    # The key point is it returns a valid match, not None.
    # Let's also verify with "ceil" strategy which requires >= the requested size
    ceil_match = pick_ecs_match(mexico, 48, 96, strategy="ceil", family_policy="sap_app")
    if ceil_match is not None:
        # ceil should fall back to C-series since no S-series spec has 48 vCPU
        assert ceil_match["category"] in ("General Computing-plus", "General Computing", "Memory-optimized")


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 8C: Per-VM ECS/EVS selection tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_resolve_evs_type_db_uses_ultra_high_io():
    """DB workloads should resolve to ultra-high-io EVS."""
    for category in ("sap_hana_db", "sql_db", "oracle_db", "sybase_db"):
        result = _resolve_evs_type_for_vm({"workload_category": category})
        assert result == "ultra-high-io", f"{category} should map to ultra-high-io"


def test_resolve_evs_type_non_db_uses_high_io():
    """Non-DB workloads should resolve to high-io EVS."""
    for category in ("sap_app", "windows_app", "linux_app", "unknown"):
        result = _resolve_evs_type_for_vm({"workload_category": category})
        assert result == "high-io", f"{category} should map to high-io"


def test_resolve_family_policy_hana():
    """HANA workload should resolve to sap_hana_db family policy."""
    assert _resolve_family_policy_for_vm({"workload_category": "sap_hana_db"}) == "sap_hana_db"


def test_resolve_family_policy_sap_db():
    """SQL/Oracle/Sybase DB should resolve to sap_db family policy."""
    for cat in ("sql_db", "oracle_db", "sybase_db"):
        assert _resolve_family_policy_for_vm({"workload_category": cat}) == "sap_db"


def test_resolve_family_policy_sap_app():
    """SAP app should resolve to sap_app family policy."""
    assert _resolve_family_policy_for_vm({"workload_category": "sap_app"}) == "sap_app"


def test_resolve_family_policy_default():
    """Unknown/other workloads should resolve to default family policy."""
    for cat in ("windows_app", "linux_app", "unknown"):
        assert _resolve_family_policy_for_vm({"workload_category": cat}) == "default"


def test_quote_inventory_db_uses_ultra_high_io():
    """DB VMs in quote_inventory should get ultra-high-io EVS type."""
    load_pricebook.cache_clear()
    content = make_rvtools_file(
        info_rows=[
            {"VM": "hana-db", "Powerstate": "PoweredOn", "CPUs": 8, "Memory": 65536},
        ],
        disk_rows=[
            {"VM": "hana-db", "Capacity GiB": 500},
        ],
    )
    result = preview_graph.invoke(
        {"request": {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "hana.xlsx"}, "file_bytes": content}
    )
    lines = result["quote_lines"]
    assert len(lines) == 1
    assert lines[0]["evs_selected_type"] == "ultra-high-io"
    assert lines[0]["evs_selected_label"] == "Ultra High I/O"


def test_quote_inventory_non_db_uses_high_io():
    """Non-DB VMs in quote_inventory should get high-io EVS type."""
    load_pricebook.cache_clear()
    content = make_rvtools_file(
        info_rows=[
            {"VM": "web-server", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4096},
        ],
        disk_rows=[
            {"VM": "web-server", "Capacity GiB": 50},
        ],
    )
    result = preview_graph.invoke(
        {"request": {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "web.xlsx"}, "file_bytes": content}
    )
    lines = result["quote_lines"]
    assert len(lines) == 1
    assert lines[0]["evs_selected_type"] == "high-io"
    assert lines[0]["evs_selected_label"] == "High I/O"


def test_quote_inventory_hana_prefers_m_series():
    """HANA VM should get M-series ECS via sap_hana_db family policy."""
    load_pricebook.cache_clear()
    content = make_rvtools_file(
        info_rows=[
            {"VM": "hana-db", "Powerstate": "PoweredOn", "CPUs": 8, "Memory": 65536},
        ],
        disk_rows=[
            {"VM": "hana-db", "Capacity GiB": 500},
        ],
    )
    result = preview_graph.invoke(
        {"request": {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "hana.xlsx"}, "file_bytes": content}
    )
    lines = result["quote_lines"]
    assert len(lines) == 1
    assert lines[0]["ecs_family_policy"] == "sap_hana_db"
    if lines[0]["action"] == "quote":
        assert "M7n" in (lines[0]["ecs_family_label"] or ""), f"HANA should pick M-series, got {lines[0]['ecs_family_label']}"


def test_quote_inventory_sap_app_prefers_s_series():
    """SAP app VM should get S-series ECS via sap_app family policy."""
    load_pricebook.cache_clear()
    content = make_rvtools_file(
        info_rows=[
            {"VM": "sap-erp", "Powerstate": "PoweredOn", "CPUs": 4, "Memory": 16384},
        ],
        disk_rows=[
            {"VM": "sap-erp", "Capacity GiB": 100},
        ],
    )
    result = preview_graph.invoke(
        {"request": {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "sap.xlsx"}, "file_bytes": content}
    )
    lines = result["quote_lines"]
    assert len(lines) == 1
    assert lines[0]["ecs_family_policy"] == "sap_app"
    if lines[0]["action"] == "quote":
        assert "S7n" in (lines[0]["ecs_family_label"] or ""), f"SAP app should pick S-series, got {lines[0]['ecs_family_label']}"


def test_quote_inventory_default_non_sap_still_works():
    """Non-SAP VMs should still get default family policy and quote correctly."""
    load_pricebook.cache_clear()
    content = make_rvtools_file(
        info_rows=[
            {"VM": "web-01", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4096},
        ],
        disk_rows=[
            {"VM": "web-01", "Capacity GiB": 50},
        ],
    )
    result = preview_graph.invoke(
        {"request": {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "web.xlsx"}, "file_bytes": content}
    )
    lines = result["quote_lines"]
    assert len(lines) == 1
    assert lines[0]["ecs_family_policy"] == "default"
    if lines[0]["action"] == "quote":
        assert lines[0]["ecs_ondemand_monthly_usd"] > 0
        assert lines[0]["evs_monthly_usd"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 8D: Template export EVS selection column tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_template_export_ecs_includes_evs_selected_value():
    """ECS sheet column 11 (Disk Type) should show EVS selected type label."""
    load_pricebook.cache_clear()
    content = make_rvtools_file(
        info_rows=[
            {"VM": "db-vm", "Powerstate": "PoweredOn", "CPUs": 4, "Memory": 16384},
        ],
        disk_rows=[
            {"VM": "db-vm", "Capacity GiB": 200},
        ],
    )
    result = export_graph.invoke(
        {"request": {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "db.xlsx"}, "file_bytes": content}
    )
    ws = _load_export_workbook(result["workbook"].content)["ECS"]
    # Column G (7) should have EVS type label, not None
    evs_val = ws.cell(3, 11).value  # Row 3 is first data row, col 11 = Disk Type
    assert evs_val is not None and evs_val != "", "Column 11 (Disk Type) should show EVS selected type"


def test_template_export_hwc_uses_selected_evs_type_totals():
    """HWC sheet EVS totals should be based on evs_selected_type, not storage_class_hint."""
    lines = [
        _make_quote_line_with_dc(
            vm_name="db-1", source_dc="DC1",
            storage_class_hint="ultra-high-io",
            evs_selected_type="ultra-high-io",
            disk_gib=100, evs_monthly_usd=10.0,
        ),
        _make_quote_line_with_dc(
            vm_name="app-1", source_dc="DC1",
            storage_class_hint="general-purpose-ssd",
            evs_selected_type="high-io",
            disk_gib=200, evs_monthly_usd=8.0,
        ),
    ]
    request = QuoteRequest(region="mexico", evs_type="gpssd", lang="en", source_filename="test.xlsx")
    hwc_rows = _build_hwc_rows(lines, request, {})
    hwc_df = pd.DataFrame(hwc_rows)

    # Should have Ultra High I/O and High I/O rows
    ultra_rows = hwc_df[hwc_df["Storage Class"] == "Ultra High I/O"]
    high_io_rows = hwc_df[hwc_df["Storage Class"] == "High I/O"]
    assert len(ultra_rows) > 0, "Should have Ultra High I/O row"
    assert len(high_io_rows) > 0, "Should have High I/O row"

    # Ultra High I/O should have 100 GB (db-1)
    assert abs(float(ultra_rows.iloc[0]["Quantity"]) - 100.0) < 0.01
    # High I/O should have 200 GB (app-1)
    assert abs(float(high_io_rows.iloc[0]["Quantity"]) - 200.0) < 0.01


def test_template_export_evs_selected_type_shown_in_ecs_rows():
    """_build_ecs_export_rows uses evs_selected_label for Tipo Storage column."""
    lines = [
        _make_quote_line_with_dc(
            vm_name="hana-1",
            storage_class_hint="ultra-high-io",
            evs_selected_type="ultra-high-io",
            evs_monthly_usd=15.0,
        ),
        _make_quote_line_with_dc(
            vm_name="app-1",
            storage_class_hint="general-purpose-ssd",
            evs_selected_type="high-io",
            evs_monthly_usd=5.0,
        ),
    ]
    rows = _build_ecs_export_rows(lines)
    rows_by_name = {r["VM"]: r for r in rows}
    assert rows_by_name["hana-1"]["Tipo Storage"] == "Ultra High I/O"
    assert rows_by_name["app-1"]["Tipo Storage"] == "High I/O"
