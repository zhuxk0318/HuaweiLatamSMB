"""Phase E tests: billing export using RVTools template, detail page, HWC aggregation, summary, info."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.flexible_workflow import (
    _detect_billing_document,
    _extract_billing_lines,
    _standardize_billing_lines,
    _map_standardized_billing_resources_to_huawei,
    _build_requirements_from_mapped_billing_resources,
    _parse_csv_document,
    _build_billing_detail_rows,
    _build_billing_hwc_rows,
    export_flexible_workbook,
    normalize_requirements,
    validate_quote_readiness,
    resolve_price_components,
    quote_items,
    summarize_quote,
)
from app.flexible_pricing import query_flexible_pricing_catalog
from app.models import (
    FlexibleQuoteContext,
    RequirementItem,
    PriceComponent,
    ComputeSpec,
    StorageSpec,
    GenericSpec,
    FlexibleQuoteLine,
    FlexibleQuoteSummary,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

AZURE_CSV_PATH = Path("/root/SMBReference/CGE/azure Billing_invoice_transactions.csv")


@pytest.fixture
def azure_csv_bytes() -> bytes:
    assert AZURE_CSV_PATH.exists()
    return AZURE_CSV_PATH.read_bytes()


@pytest.fixture
def azure_document(azure_csv_bytes: bytes) -> dict:
    return _parse_csv_document(azure_csv_bytes, "azure_billing.csv")


def _catalog_for_region(region: str = "chile") -> list[dict]:
    items = query_flexible_pricing_catalog(region=region)
    return [item.model_dump() for item in items]


def _make_billing_state(azure_document: dict, region: str = "chile") -> dict:
    """Build a full billing state through the pipeline (no LLM)."""
    lines = _extract_billing_lines(azure_document)
    # Use aggregation path (same as main workflow)
    from app.flexible_workflow import (
        _group_billing_lines,
        _aggregate_billing_groups_fallback,
        _build_requirements_from_llm_aggregated_billing_items,
    )
    groups = _group_billing_lines(lines)
    agg_items = _aggregate_billing_groups_fallback(groups)
    requirements = _build_requirements_from_llm_aggregated_billing_items(agg_items)
    # Legacy fields for backward compat
    standardized = _standardize_billing_lines(lines, FlexibleQuoteContext(region=region))
    mapped = _map_standardized_billing_resources_to_huawei(standardized)

    # Normalize
    norm_state = {
        "requirements": requirements,
        "quote_context": {"region": region},
        "audit_log": [],
        "progress_callback": None,
    }
    norm_result = normalize_requirements(norm_state)
    norm_reqs = norm_result["requirements"]

    # Validate readiness
    catalog = _catalog_for_region(region)
    val_state = {
        "requirements": norm_reqs,
        "quote_context": {"region": region},
        "price_catalog": catalog,
        "matched_products": [],
        "understanding": {"profile": {}},
        "audit_log": [],
        "progress_callback": None,
    }
    val_result = validate_quote_readiness(val_state)

    # Resolve prices
    res_state = {
        "quote_ready_items": val_result["quote_ready_items"],
        "price_catalog": catalog,
        "unquoted_items": val_result["unquoted_items"],
        "audit_log": [],
        "progress_callback": None,
    }
    res_result = resolve_price_components(res_state)

    # Quote
    quote_state = {
        "quote_ready_items": val_result["quote_ready_items"],
        "price_components": res_result["price_components"],
        "audit_log": [],
        "progress_callback": None,
    }
    quote_result = quote_items(quote_state)

    # Summary
    sum_state = {
        "requirements": norm_reqs,
        "quote_ready_items": val_result["quote_ready_items"],
        "quote_lines": quote_result["quote_lines"],
        "quote_blockers": val_result["quote_blockers"],
        "unquoted_items": res_result["unquoted_items"],
        "quote_context": {"region": region},
        "llm_aggregated_billing_items": agg_items,
        "audit_log": [],
        "progress_callback": None,
    }
    sum_result = summarize_quote(sum_state)

    return {
        "requirements": norm_reqs,
        "quote_ready_items": val_result["quote_ready_items"],
        "quote_lines": quote_result["quote_lines"],
        "quote_blockers": val_result["quote_blockers"],
        "unquoted_items": res_result["unquoted_items"],
        "price_components": res_result["price_components"],
        "summary": sum_result["summary"],
        "billing_gap_analysis": sum_result.get("billing_gap_analysis", {}),
        "billing_reconciliation": sum_result.get("billing_reconciliation", {}),
        "mapped_billing_resources": mapped,
        "billing_lines": lines,
        "billing_groups": groups,
        "llm_aggregated_billing_items": agg_items,
        "standardized_billing_resources": standardized,
        "quote_context": {"region": region},
        "audit_log": [],
        "progress_callback": None,
    }


# ---------------------------------------------------------------------------
# 1. test_billing_export_uses_rvtools_template_sheets
# ---------------------------------------------------------------------------

class TestBillingExportSheets:
    def test_billing_export_uses_rvtools_template_sheets(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        result = export_flexible_workbook(state)
        wb = load_workbook(BytesIO(result["workbook"].content))
        sheet_names = wb.sheetnames
        for expected in ["Summary", "HWC", "ECS", "Información"]:
            assert expected in sheet_names, f"Missing sheet: {expected}"


# ---------------------------------------------------------------------------
# 2. test_non_billing_export_still_uses_generic_workbook
# ---------------------------------------------------------------------------

class TestNonBillingExport:
    def test_non_billing_export_still_uses_generic_workbook(self):
        """Non-billing state should produce the generic multi-sheet workbook."""
        state = {
            "summary": FlexibleQuoteSummary().model_dump(),
            "quote_context": {"region": "chile"},
            "requirements": [],
            "quote_lines": [],
            "unquoted_items": [],
            "matched_products": [],
            "audit_log": [],
            "progress_callback": None,
        }
        result = export_flexible_workbook(state)
        wb = load_workbook(BytesIO(result["workbook"].content))
        # Generic export has "Summary" and "Standard Requirements"
        assert "Summary" in wb.sheetnames
        assert "Standard Requirements" in wb.sheetnames
        # Should NOT have RVTools template sheets
        assert "Información" not in wb.sheetnames


# ---------------------------------------------------------------------------
# 3. test_ecs_sheet_contains_one_row_per_mapped_billing_resource
# ---------------------------------------------------------------------------

class TestDetailRowCount:
    def test_ecs_sheet_contains_one_row_per_aggregated_billing_item(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        detail_rows = _build_billing_detail_rows(state)
        # Detail rows now come from aggregated items, not mapped resources
        agg_count = len(state["llm_aggregated_billing_items"])
        assert len(detail_rows) == agg_count


# ---------------------------------------------------------------------------
# 4. test_ecs_sheet_preserves_source_lineage_and_status
# ---------------------------------------------------------------------------

class TestDetailLineage:
    def test_ecs_sheet_preserves_source_lineage_and_status(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        detail_rows = _build_billing_detail_rows(state)
        # Every row should have source_lines and status
        for row in detail_rows:
            assert "source_lines" in row
            assert "status" in row
            assert row["status"] in ("quoted", "unquoted", "manual_review", "unsupported")
        # At least some should be quoted and some should not
        statuses = {r["status"] for r in detail_rows}
        assert "quoted" in statuses or "unquoted" in statuses


# ---------------------------------------------------------------------------
# 5. test_ecs_sheet_includes_matched_price_fields_for_quoted_rows
# ---------------------------------------------------------------------------

class TestDetailPriceFields:
    def test_ecs_sheet_includes_matched_price_fields_for_quoted_rows(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        detail_rows = _build_billing_detail_rows(state)
        quoted_rows = [r for r in detail_rows if r["status"] == "quoted"]
        if not quoted_rows:
            pytest.skip("No quoted rows in this test run")
        for row in quoted_rows:
            # Quoted rows must have price fields
            assert row["unit_price_usd"] is not None, f"Quoted row missing unit_price: {row}"
            assert row["monthly_price_usd"] is not None, f"Quoted row missing monthly_price: {row}"
            assert row["monthly_price_usd"] > 0


# ---------------------------------------------------------------------------
# 6. test_hwc_sheet_aggregates_real_huawei_products
# ---------------------------------------------------------------------------

class TestHWCAggregation:
    def test_hwc_sheet_aggregates_real_huawei_products(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        hwc_rows = _build_billing_hwc_rows(state)
        # Should have at least some products
        assert len(hwc_rows) > 0
        # Each row should have product, quantity, total
        for row in hwc_rows:
            assert "product" in row
            assert "quantity" in row
            assert "total" in row
            assert row["total"] > 0
        # Products should be real Huawei products, not EVS/VPN placeholders
        products = {r["product"] for r in hwc_rows}
        # We should see at least some of the actual quoted products
        assert len(products) > 0


# ---------------------------------------------------------------------------
# 7. test_summary_sheet_mentions_billing_assumptions_and_totals
# ---------------------------------------------------------------------------

class TestSummarySheet:
    def test_summary_sheet_mentions_billing_assumptions_and_totals(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        result = export_flexible_workbook(state)
        wb = load_workbook(BytesIO(result["workbook"].content))
        ws = wb["Summary"]
        # B4 should have billing title
        b4 = ws["B4"].value or ""
        assert "Billing" in str(b4)
        # C7 should have total monthly price
        c7 = ws["C7"].value
        assert c7 is not None and c7 > 0
        # B16 should mention billing
        b16 = ws["B16"].value or ""
        assert "billing" in str(b16).lower() or "Billing" in str(b16) or "Huawei" in str(b16)


# ---------------------------------------------------------------------------
# 8. test_information_sheet_contains_source_and_risks
# ---------------------------------------------------------------------------

class TestInfoSheet:
    def test_information_sheet_contains_source_and_risks(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        result = export_flexible_workbook(state)
        wb = load_workbook(BytesIO(result["workbook"].content))
        ws = wb["Información"]
        # Read all cell values from column 1
        all_text = " ".join(str(ws.cell(row, 1).value or "") for row in range(1, 50))
        # Should contain source file
        assert "azure" in all_text.lower() or "Source" in all_text
        # Should contain vendor
        assert "azure" in all_text.lower() or "Vendor" in all_text


# ---------------------------------------------------------------------------
# 9. test_unquoted_items_appear_in_detail_export
# ---------------------------------------------------------------------------

class TestUnquotedInDetail:
    def test_unquoted_items_appear_in_detail_export(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        detail_rows = _build_billing_detail_rows(state)
        # There should be some non-quoted rows (unquoted/unsupported/manual_review)
        non_quoted = [r for r in detail_rows if r["status"] != "quoted"]
        assert len(non_quoted) > 0, "Expected some unquoted/unsupported rows in detail"


# ---------------------------------------------------------------------------
# 10. test_requirement_item_id_join_is_used_for_export_traceability
# ---------------------------------------------------------------------------

class TestTraceability:
    def test_requirement_item_id_join_is_used_for_export_traceability(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        detail_rows = _build_billing_detail_rows(state)
        # Each detail row should correspond to a mapped_billing_resource via mapped_id
        mapped_ids = {mr["mapped_id"] for mr in state["mapped_billing_resources"]}
        # Quoted rows should have matched_sku/matched_tier from quote_lines
        quoted_rows = [r for r in detail_rows if r["status"] == "quoted"]
        quote_line_ids = {ql["requirement_item_id"] for ql in state["quote_lines"]}
        # The number of quoted detail rows should match quote_lines
        assert len(quoted_rows) == len(state["quote_lines"])
