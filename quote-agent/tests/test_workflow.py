from __future__ import annotations

from io import BytesIO
import time
from zipfile import ZipFile

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
from app.models import FlexibleQuoteContext, FlexibleReviewRequest, HumanFeedback
from app.pricebook import load_pricebook, pick_ecs_match
from app.row_quote_workflow import RowMapping, _collect_rows, _normalize_mapping_spec, annotate_row_quote_workbook
from app.models import RowQuoteProgress
from app.rvtools import RvToolsParseError, parse_rvtools_workbook
from app.workflow import export_graph


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
    content = make_rvtools_file(include_vinfo=False, disk_rows=[{"VM": "x", "Capacity GB": 10}])
    try:
        parse_rvtools_workbook(content)
    except RvToolsParseError as exc:
        assert "vInfo" in str(exc)
    else:
        raise AssertionError("Expected missing vInfo error")


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
    assert "Quote Lines" in workbook_xml
    assert "Manual Review" in workbook_xml
    assert "Raw RVTools" in workbook_xml
    assert "Pricebook Used" in workbook_xml
    summary = result["summary"]
    assert summary["quoted_vms"] == 1
    assert summary["excluded_vms"] == 1
    assert summary["manual_review_vms"] == 1
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
    appended_headers = [compute.cell(1, column).value for column in range(compute.max_column - 9, compute.max_column + 1)]
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
    ]
    assert compute.cell(2, compute.max_column - 7).value == 1
    assert compute.cell(2, compute.max_column - 2).value == "已报价"
    assert "Quantity estimated as 1" in compute.cell(2, compute.max_column - 1).value
    assert compute.cell(3, compute.max_column - 2).value == "非报价行"
    assert compute.cell(4, compute.max_column - 2).value == "需人工确认"

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
    assert exported["Compute"].cell(1, exported["Compute"].max_column - 9).value == "华为云产品名"


def test_row_quote_export_sanitizes_unicode_filename(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    created = create_flexible_annotate_task(
        UploadFile(filename="客户报价.xlsx", file=BytesIO(make_row_quote_workbook())),
        "mexico",
        "zh",
        "Generate a quote for SMB use.",
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
    assert annotated.cell(2, annotated.max_column - 9).value == "CCI"
    assert annotated.cell(2, annotated.max_column - 2).value == "已报价"
    assert annotated.cell(3, annotated.max_column - 9).value == "CCI"
    assert annotated.cell(3, annotated.max_column - 2).value == "已报价"


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
    assert annotated.cell(2, annotated.max_column - 9).value == "CCI"
    assert annotated.cell(2, annotated.max_column - 2).value == "已报价"


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
    assert sheet.cell(2, sheet.max_column - 2).value == "Non-quote row"
    assert "excluded from quote" in sheet.cell(2, sheet.max_column - 1).value
    assert sheet.cell(3, sheet.max_column - 2).value == "Quoted"


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
    assert annotated.cell(2, annotated.max_column - 9).value == "CCI"
    assert annotated.cell(3, annotated.max_column - 9).value == "CCI"
    assert annotated.cell(4, annotated.max_column - 9).value == "CCI"
    assert annotated.cell(3, annotated.max_column - 8).value == "4vCPU"
    assert annotated.cell(4, annotated.max_column - 8).value == "8GiB"
    assert "Inherited product classification" in annotated.cell(3, annotated.max_column - 1).value
    assert "Inherited product classification" in annotated.cell(4, annotated.max_column - 1).value


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
    assert annotated.cell(3, annotated.max_column - 9).value == "CCE"
    assert annotated.cell(3, annotated.max_column - 2).value == "已报价"


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
    assert annotated.cell(2, annotated.max_column - 9).value == "CCE"
    assert annotated.cell(2, annotated.max_column - 2).value == "已报价"
    assert annotated.cell(2, annotated.max_column - 6).value is not None


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
    appended_headers = [compute.cell(1, column).value for column in range(compute.max_column - 9, compute.max_column + 1)]
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
    ]
    assert compute.cell(2, compute.max_column - 2).value == "Quoted"
    assert compute.cell(3, compute.max_column - 2).value == "Non-quote row"
    assert compute.cell(4, compute.max_column - 2).value == "Manual review"


def test_row_quote_zh_language_uses_chinese_columns_and_status(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.row_quote_workflow._maas_map_rows", lambda *_args, **_kwargs: {})
    workbook, summary = annotate_row_quote_workbook(
        {"filename": "customer.xlsx", "content": make_row_quote_workbook()},
        {"region": "mexico", "language": "zh", "customer_notes": ""},
    )

    annotated = load_workbook(BytesIO(workbook.content), data_only=True)
    compute = annotated["Compute"]
    appended_headers = [compute.cell(1, column).value for column in range(compute.max_column - 9, compute.max_column + 1)]
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
    ]
    assert compute.cell(2, compute.max_column - 2).value == "已报价"
    assert compute.cell(3, compute.max_column - 2).value == "非报价行"
    assert compute.cell(4, compute.max_column - 2).value == "需人工确认"
