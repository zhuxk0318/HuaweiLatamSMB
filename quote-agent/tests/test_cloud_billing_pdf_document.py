from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from starlette.datastructures import UploadFile

from app.cloud_billing_document import parse_cloud_billing_pdf
from app.cloud_billing_workflow import (
    _apply_mapping_corrections,
    _compose_analyzed_document_final_items,
    deduplicate_cloud_billing_requirements,
    _requirements_from_document_analysis,
    _validate_full_document_analysis,
    cloud_billing_preview_graph,
)
from app.main import _read_billing_file
from app.models import CloudBillingAnalyzedItem, CloudBillingTargetComponent
from app.row_quote_tasks import _quote_summary_from_state


SAMPLE = Path("/root/SMBReference/AWS billing.pdf")


@pytest.mark.skipif(not SAMPLE.exists(), reason="AWS PDF regression sample is not installed")
def test_real_aws_pdf_extracts_complete_text_and_declared_total():
    document = parse_cloud_billing_pdf(SAMPLE.read_bytes(), SAMPLE.name)
    assert document["page_count"] == 5
    assert document["declared_monthly_total"] == pytest.approx(15321.89)
    service_cost_lines = [
        row for row in document["rows"]
        if "0.00 USD" in row["text"] and "15,321.89 USD" not in row["text"]
    ]
    assert len(service_cost_lines) == 37
    assert "Amazon EC2" in document["full_text"]
    assert "Amazon Aurora PostgreSQL" in document["full_text"]


@pytest.mark.skipif(not SAMPLE.exists(), reason="AWS PDF regression sample is not installed")
def test_real_aws_pdf_source_blocks_restore_wrapped_service_names():
    document = parse_cloud_billing_pdf(SAMPLE.read_bytes(), SAMPLE.name)
    refs = [
        row["source_ref"]
        for row in document["rows"]
        if "0.00 USD" in row["text"] and "15,321.89 USD" not in row["text"]
    ]
    items = _validate_full_document_analysis(
        [{"r": ref, "t": []} for ref in refs],
        [document],
        "AWS",
    )
    assert len(items) == 37
    names = {item.source_service_name for item in items}
    assert "Amazon Aurora PostgreSQL Compatible DB" in names
    assert "Amazon Managed Streaming for Apache Kafka (MSK)" in names
    assert "Amazon Simple Storage Service (S3)" in names
    assert all(
        "Monthly cost" not in (item.source_config_summary or "")
        for item in items
    )


def test_invalid_pdf_signature_is_rejected():
    with pytest.raises(ValueError, match="valid PDF signature"):
        parse_cloud_billing_pdf(b"not-a-pdf", "billing.pdf")


@pytest.mark.skipif(not SAMPLE.exists(), reason="AWS PDF regression sample is not installed")
def test_cloud_billing_file_guard_accepts_pdf():
    upload = UploadFile(filename=SAMPLE.name, file=BytesIO(SAMPLE.read_bytes()))
    result = _read_billing_file(upload)
    assert result["filename"] == SAMPLE.name
    assert bytes(result["content"]).startswith(b"%PDF")


def _synthetic_document():
    return {
        "filename": "estimate.pdf",
        "document_type": "cloud_billing_pdf",
        "declared_monthly_total": 300.0,
        "rows": [
            {"source_ref": "pdf-line::1::10", "text": "Cloud VM 0.00 USD 200.00 USD"},
            {"source_ref": "pdf-line::1::20", "text": "Object Storage 0.00 USD 100.00 USD"},
        ],
    }


def test_analysis_recomputes_source_amounts_and_reconciles_total():
    raw = [
        {
            "item_id": "vm",
            "vendor": "AnyCloud",
            "source_refs": ["pdf-line::1::10"],
            "source_service_name": "Cloud VM",
            "source_monthly_total_usd": 999999,
            "target_components": [
                {
                    "component_id": "vm-compute",
                    "huawei_product": "ECS",
                    "quantity": 2,
                    "unit": "instance-month",
                    "vcpu": 4,
                    "memory_gib": 16,
                },
                {
                    "component_id": "vm-disk",
                    "huawei_product": "EVS",
                    "quantity": 400,
                    "unit": "capacity gib month",
                    "capacity_gib": 400,
                },
            ],
        },
        {
            "item_id": "storage",
            "vendor": "AnyCloud",
            "source_refs": ["pdf-line::1::20"],
            "source_service_name": "Object Storage",
            "target_components": [
                {
                    "component_id": "storage-obs",
                    "huawei_product": "OBS",
                    "quantity": 1000,
                    "unit": "capacity gib month",
                }
            ],
        },
    ]
    items = _validate_full_document_analysis(raw, [_synthetic_document()])
    assert [item.source_monthly_total_usd for item in items] == [200.0, 100.0]

    requirements, updated = _requirements_from_document_analysis(items, "estimate.pdf")
    assert len(requirements) == 3
    assert {req["normalized_product"] for req in requirements} == {"ECS", "EVS", "OBS"}
    assert all(component.requirement_item_id for item in updated for component in item.target_components)


def test_analysis_rejects_missing_or_duplicate_source_amount_ownership():
    raw = [
        {
            "item_id": item_id,
            "vendor": "Cloud",
            "source_refs": ["pdf-line::1::10"],
            "source_service_name": item_id,
            "target_components": [],
        }
        for item_id in ("one", "two")
    ]
    assert _validate_full_document_analysis(raw, [_synthetic_document()]) == []


def test_compact_target_numeric_tier_is_coerced_to_capacity():
    document = {
        "filename": "estimate.pdf",
        "document_type": "cloud_billing_pdf",
        "declared_monthly_total": 200.0,
        "rows": [
            {"source_ref": "pdf-line::1::10", "text": "Cloud DB 0.00 USD 200.00 USD"},
        ],
    }
    items = _validate_full_document_analysis(
        [
            {
                "r": "pdf-line::1::10",
                "t": [["EVS", 3000, "capacity gib month", "SSD", None, None, None, 3000]],
            }
        ],
        [document],
        "AnyCloud",
    )
    assert len(items) == 1
    component = items[0].target_components[0]
    assert component.capacity_gib == 3000
    assert component.tier is None


def test_empty_first_pass_mapping_gets_review_placeholder():
    document = {
        "filename": "estimate.pdf",
        "document_type": "cloud_billing_pdf",
        "declared_monthly_total": 200.0,
        "rows": [
            {"source_ref": "pdf-line::1::10", "text": "Analytics 0.00 USD 200.00 USD"},
        ],
    }
    items = _validate_full_document_analysis(
        [{"r": "pdf-line::1::10", "t": [], "mr": "No confident mapping"}],
        [document],
        "AnyCloud",
    )
    assert len(items[0].target_components) == 1
    placeholder = items[0].target_components[0]
    assert placeholder.huawei_product is None
    assert placeholder.component_id.endswith("review-placeholder")


def test_review_rejects_illegal_product_and_accepts_price_free_quantity_change():
    item = CloudBillingAnalyzedItem(
        item_id="vm",
        vendor="AWS",
        source_refs=["pdf-line::1::10"],
        source_service_name="EC2",
        source_monthly_total_usd=200,
        target_components=[
            CloudBillingTargetComponent(
                component_id="compute",
                huawei_product="ECS",
                quantity=None,
            )
        ],
    )
    updated, accepted = _apply_mapping_corrections(
        [item],
        [
            {"component_id": "compute", "action": "replace_product", "huawei_product": "FakeCloud"},
            {"component_id": "compute", "action": "replace_quantity", "quantity": 3},
        ],
    )
    assert len(accepted) == 1
    assert updated[0].target_components[0].quantity == 3
    assert updated[0].target_components[0].huawei_product == "ECS"


def test_final_composition_counts_source_amount_once_for_multiple_target_components():
    items = [
        CloudBillingAnalyzedItem(
            item_id="vm",
            vendor="AWS",
            source_refs=["pdf-line::1::10"],
            source_service_name="Amazon EC2",
            source_monthly_total_usd=200,
            target_components=[
                CloudBillingTargetComponent(
                    component_id="compute",
                    huawei_product="ECS",
                    quantity=2,
                    requirement_item_id="billing-doc::vm::compute",
                ),
                CloudBillingTargetComponent(
                    component_id="disk",
                    huawei_product="EVS",
                    quantity=400,
                    requirement_item_id="billing-doc::vm::disk",
                ),
            ],
        )
    ]
    state = {
        "cloud_billing_analysis_items": [item.model_dump() for item in items],
        "quote_lines": [
            {
                "line_id": "ecs",
                "requirement_item_id": "billing-doc::vm::compute",
                "product": "ECS",
                "region": "mexico",
                "quantity": 2,
                "unit": "instance-month",
                "billing_mode": "monthly",
                "unit_price": 10,
                "monthly_price": 20,
            },
            {
                "line_id": "evs",
                "requirement_item_id": "billing-doc::vm::disk",
                "product": "EVS",
                "region": "mexico",
                "quantity": 400,
                "unit": "GB-month",
                "billing_mode": "monthly",
                "unit_price": 0.05,
                "monthly_price": 20,
            },
        ],
        "unquoted_items": [],
    }
    result = _compose_analyzed_document_final_items(state)
    assert len(result) == 1
    assert result[0].source_monthly_total_usd == 200
    assert result[0].huawei_monthly_total_usd == 40
    assert result[0].huawei_product == "ECS + EVS"


def test_cloud_billing_graph_contains_mapping_review():
    assert "review_cloud_billing_mapping_with_llm" in cloud_billing_preview_graph.get_graph().nodes


def test_task_summary_uses_final_source_items():
    state = {
        "summary": {"total_monthly_price": 123.0, "currency": "USD"},
        "requirements": [{"item_id": "target-1"}],
        "final_billing_quote_items": [
            {"status": "quoted", "huawei_product": "ECS"},
            {"status": "partial", "huawei_product": "RDS"},
            {"status": "manual_review", "huawei_product": None},
        ],
    }
    summary = _quote_summary_from_state(state)
    assert summary.total_rows == 3
    assert summary.quoted_rows == 1
    assert summary.missing_price_rows == 1
    assert summary.manual_review_rows == 1


def test_complete_document_requirements_are_not_cross_source_deduplicated():
    requirements = [
        {
            "item_id": f"billing-doc::source-{index}::cce",
            "source_file": "estimate.pdf",
            "source_sheet": "PDF",
            "raw_product_name": "CCE | EKS",
            "normalized_product": "CCE",
            "quantity": 4,
            "quantity_source": "source_file",
            "unit": "instance-month",
            "spec": {"spec_type": "generic", "description": "4 clusters"},
        }
        for index in (1, 2)
    ]
    state = {
        "requirements": requirements,
        "cloud_billing_analysis_items": [{"item_id": "source-1"}, {"item_id": "source-2"}],
        "audit_log": [],
    }
    result = deduplicate_cloud_billing_requirements(state)
    assert len(result["requirements"]) == 2
    assert [item["quantity"] for item in result["requirements"]] == [4, 4]
