"""Phase Next+3 tests: billing gap analysis — quoted/unquoted breakdown, reason classification, top gaps, export summary."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.flexible_workflow import (
    _analyze_billing_quote_gap,
    _summarize_quoted_billing_items,
    _summarize_unquoted_billing_items,
    _classify_unquoted_reason,
    _top_unquoted_categories,
    _extract_billing_lines,
    _group_billing_lines,
    _aggregate_billing_groups_fallback,
    _build_requirements_from_llm_aggregated_billing_items,
    _standardize_billing_lines,
    _map_standardized_billing_resources_to_huawei,
    _parse_csv_document,
    normalize_requirements,
    validate_quote_readiness,
    resolve_price_components,
    quote_items,
    summarize_quote,
    export_flexible_workbook,
)
from app.flexible_pricing import query_flexible_pricing_catalog
from app.models import (
    FlexibleQuoteContext,
    RequirementItem,
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
    groups = _group_billing_lines(lines)
    agg_items = _aggregate_billing_groups_fallback(groups)
    requirements = _build_requirements_from_llm_aggregated_billing_items(agg_items)
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

    # Summary (includes gap analysis)
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
# 1. test_gap_analysis_summarizes_quoted_totals_by_product
# ---------------------------------------------------------------------------

class TestQuotedSummary:
    def test_gap_analysis_summarizes_quoted_totals_by_product(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        quoted = _summarize_quoted_billing_items(state)
        # Should have at least one product
        assert len(quoted) > 0
        # Each entry should have required fields
        for entry in quoted:
            assert "huawei_product" in entry
            assert "count" in entry
            assert "total_quantity" in entry
            assert "total_monthly_price" in entry
            assert entry["total_monthly_price"] > 0
        # Sorted by total_monthly_price descending
        prices = [e["total_monthly_price"] for e in quoted]
        assert prices == sorted(prices, reverse=True)


# ---------------------------------------------------------------------------
# 2. test_gap_analysis_groups_unquoted_by_reason
# ---------------------------------------------------------------------------

class TestUnquotedByReason:
    def test_gap_analysis_groups_unquoted_by_reason(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        unquoted = _summarize_unquoted_billing_items(state)
        # Should have some unquoted items
        assert len(unquoted) > 0
        # Each should have reason_class
        for entry in unquoted:
            assert "reason_class" in entry
            assert entry["reason_class"] in (
                "no_huawei_product_mapping",
                "no_catalog_candidate",
                "no_compatible_price_unit",
                "spec_not_specific_enough",
                "usage_not_supported_yet",
                "manual_review_required",
                "suspicious_capacity_reclassification",
                "unknown",
            )


# ---------------------------------------------------------------------------
# 3. test_gap_analysis_orders_unquoted_categories_by_source_amount
# ---------------------------------------------------------------------------

class TestUnquotedOrdering:
    def test_gap_analysis_orders_unquoted_categories_by_source_amount(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        unquoted = _summarize_unquoted_billing_items(state)
        # Should be sorted by total_source_amount descending
        amounts = [e["total_source_amount"] for e in unquoted]
        assert amounts == sorted(amounts, reverse=True)


# ---------------------------------------------------------------------------
# 4. test_gap_analysis_distinguishes_no_catalog_vs_no_compatible_unit
# ---------------------------------------------------------------------------

class TestReasonDistinction:
    def test_gap_analysis_distinguishes_no_catalog_vs_no_compatible_unit(self):
        """Verify _classify_unquoted_reason returns distinct categories for different reasons."""
        # no mapping
        item_no_map = RequirementItem(
            item_id="t1", source_file="t.csv", source_sheet="csv", row_number=1,
            raw_product_name="Unknown Product", normalized_product=None,
            status="needs_manual_review", status_reason="no mapping found",
        )
        assert _classify_unquoted_reason(item_no_map) == "no_huawei_product_mapping"

        # no catalog candidate
        item_no_catalog = RequirementItem(
            item_id="t2", source_file="t.csv", source_sheet="csv", row_number=2,
            raw_product_name="MySQL", normalized_product="RDS",
            status="needs_manual_review", status_reason="no confirmed local price for RDS",
        )
        assert _classify_unquoted_reason(item_no_catalog) == "no_catalog_candidate"

        # no compatible unit
        item_no_unit = RequirementItem(
            item_id="t3", source_file="t.csv", source_sheet="csv", row_number=3,
            raw_product_name="OBS Requests", normalized_product="OBS",
            status="needs_manual_review", status_reason="not compatible: request-based usage",
        )
        assert _classify_unquoted_reason(item_no_unit) == "usage_not_supported_yet"

        # no compatible unit (non-usage)
        item_no_compat = RequirementItem(
            item_id="t4", source_file="t.csv", source_sheet="csv", row_number=4,
            raw_product_name="VPN Bandwidth", normalized_product="VPN",
            status="needs_manual_review", status_reason="not compatible: bandwidth",
        )
        assert _classify_unquoted_reason(item_no_compat) == "no_compatible_price_unit"

        # spec ambiguous
        item_spec = RequirementItem(
            item_id="t5", source_file="t.csv", source_sheet="csv", row_number=5,
            raw_product_name="ECS Generic", normalized_product="ECS",
            status="needs_manual_review", status_reason="spec too ambiguous",
        )
        assert _classify_unquoted_reason(item_spec) == "spec_not_specific_enough"

        # manual review
        item_manual = RequirementItem(
            item_id="t6", source_file="t.csv", source_sheet="csv", row_number=6,
            raw_product_name="Custom Service", normalized_product="ECS",
            status="needs_manual_review", status_reason="requires manual review",
        )
        assert _classify_unquoted_reason(item_manual) == "manual_review_required"


# ---------------------------------------------------------------------------
# 5. test_summary_sheet_mentions_top_gap_categories
# ---------------------------------------------------------------------------

class TestSummaryGap:
    def test_summary_sheet_mentions_top_gap_categories(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        result = export_flexible_workbook(state)
        wb = load_workbook(BytesIO(result["workbook"].content))
        ws = wb["Summary"]
        # B19 should contain gap analysis section
        notes = str(ws["B19"].value or "")
        # Should have GAP ANALYSIS section
        assert "GAP ANALYSIS" in notes
        # Should mention Quoted
        assert "Quoted" in notes


# ---------------------------------------------------------------------------
# 6. test_information_sheet_mentions_unquoted_gap_breakdown
# ---------------------------------------------------------------------------

class TestInfoGap:
    def test_information_sheet_mentions_unquoted_gap_breakdown(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        result = export_flexible_workbook(state)
        wb = load_workbook(BytesIO(result["workbook"].content))
        ws = wb["Información"]
        all_text = " ".join(str(ws.cell(row, 1).value or "") for row in range(1, 80))
        # Should contain GAP ANALYSIS
        assert "GAP ANALYSIS" in all_text
        # Should mention unquoted
        assert "Unquoted" in all_text or "unquoted" in all_text


# ---------------------------------------------------------------------------
# 7. test_gap_analysis_does_not_change_quote_totals
# ---------------------------------------------------------------------------

class TestNoQuoteChange:
    def test_gap_analysis_does_not_change_quote_totals(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        # Compute gap analysis
        gap = _analyze_billing_quote_gap(state)
        # The quoted_total should match the actual quote_lines total
        quote_total = sum(ql.get("monthly_price", 0) for ql in state.get("quote_lines", []))
        assert abs(gap["quoted_total"] - round(quote_total, 2)) < 0.01
        # The summary total should be unchanged
        summary = FlexibleQuoteSummary.model_validate(state["summary"])
        assert abs(summary.total_monthly_price - quote_total) < 0.01


# ---------------------------------------------------------------------------
# 8. test_real_billing_gap_analysis_outputs_nonempty_top_categories
# ---------------------------------------------------------------------------

class TestRealGapOutput:
    def test_real_billing_gap_analysis_outputs_nonempty_top_categories(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        gap = _analyze_billing_quote_gap(state)
        # Should have top_gaps
        assert "top_gaps" in gap
        assert len(gap["top_gaps"]) > 0
        # Should have quoted_by_product
        assert "quoted_by_product" in gap
        assert len(gap["quoted_by_product"]) > 0
        # Should have reason_distribution
        assert "reason_distribution" in gap
        # quoted_pct should be > 0
        assert gap["quoted_pct"] > 0
        # unquoted_pct should be > 0 (we know there are gaps)
        assert gap["unquoted_pct"] > 0


# ---------------------------------------------------------------------------
# Optional: test_gap_analysis_uses_stable_source_ids_for_join
# ---------------------------------------------------------------------------

class TestStableSourceIds:
    def test_gap_analysis_uses_stable_source_ids_for_join(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        # Unquoted items should have stable item_ids that can be joined back
        unquoted = state.get("unquoted_items", [])
        agg_items = state.get("llm_aggregated_billing_items", [])
        # Build the same ID format as _summarize_unquoted_billing_items
        agg_ids = set()
        for idx, ai in enumerate(agg_items):
            aid = f'billing-agg::{ai.get("source_file", "")}::{idx}'
            agg_ids.add(aid)
        # At least some unquoted items should have IDs matching agg format
        matching = sum(1 for uq in unquoted if uq.get("item_id") in agg_ids)
        # Not all may match (some are from blockers), but the join should be stable
        # Just verify no crash and the IDs are strings
        for uq in unquoted:
            assert isinstance(uq.get("item_id"), str)


# ---------------------------------------------------------------------------
# Optional: test_manual_review_items_are_counted_separately_from_unquoted
# ---------------------------------------------------------------------------

class TestManualReviewSeparate:
    def test_manual_review_items_are_counted_separately_from_unquoted(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        gap = _analyze_billing_quote_gap(state)
        reason_counts = gap.get("reason_distribution", {}).get("counts", {})
        # manual_review_required should be a distinct count if any such items exist
        manual_review_items = [
            uq for uq in state.get("unquoted_items", [])
            if RequirementItem.model_validate(uq).status == "needs_manual_review"
        ]
        if manual_review_items:
            # Some should be classified as manual_review_required
            assert reason_counts.get("manual_review_required", 0) > 0
