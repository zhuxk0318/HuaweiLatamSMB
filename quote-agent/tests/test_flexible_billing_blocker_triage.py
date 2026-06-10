"""Phase Next+7 tests: blocker triage — classification, downgrade, summary,
export integration, and real Azure file validation."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.flexible_workflow import (
    _classify_billing_blocker,
    _should_downgrade_blocker_to_unquoted,
    _summarize_billing_blockers,
    _top_blocker_categories,
    _analyze_billing_blocker_triage,
    _BLOCKER_UNSUPPORTED_PRODUCT,
    _BLOCKER_SPEC_NOT_SPECIFIC_ENOUGH,
    _BLOCKER_PRICING_BLOCKED_BY_CATALOG_GAP,
    _BLOCKER_SUSPICIOUS_SOURCE_SEMANTICS,
    _BLOCKER_MANUAL_REVIEW_REQUIRED,
    _BLOCKER_MISSING_REGION,
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
    FlexibleQuoteBlocker,
    ComputeSpec,
    StorageSpec,
    GenericSpec,
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

    norm_state = {
        "requirements": requirements,
        "quote_context": {"region": region},
        "audit_log": [],
        "progress_callback": None,
    }
    norm_result = normalize_requirements(norm_state)
    norm_reqs = norm_result["requirements"]

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

    res_state = {
        "quote_ready_items": val_result["quote_ready_items"],
        "price_catalog": catalog,
        "unquoted_items": val_result["unquoted_items"],
        "audit_log": [],
        "progress_callback": None,
    }
    res_result = resolve_price_components(res_state)

    quote_state = {
        "quote_ready_items": val_result["quote_ready_items"],
        "price_components": res_result["price_components"],
        "audit_log": [],
        "progress_callback": None,
    }
    quote_result = quote_items(quote_state)

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
        "billing_blocker_analysis": sum_result.get("billing_blocker_analysis", {}),
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
# Helper to make RequirementItem for blocker tests
# ---------------------------------------------------------------------------

def _make_blocker_item(
    status: str = "needs_manual_review",
    status_reason: str = "Product could not be mapped to the supported catalog.",
    normalized_product: str | None = None,
    quantity_source: str = "billing_standardized",
    quantity: float | None = None,
) -> RequirementItem:
    return RequirementItem(
        item_id="test-blocker-1",
        source_file="test.csv",
        source_sheet="csv",
        row_number=1,
        raw_product_name="Some Product",
        quantity=quantity,
        quantity_source=quantity_source,
        unit="1",
        region="chile",
        normalized_product=normalized_product,
        status=status,
        status_reason=status_reason,
    )


# ---------------------------------------------------------------------------
# 1. test_classify_blocker_as_unsupported_product
# ---------------------------------------------------------------------------

class TestClassifyUnsupportedProduct:
    def test_classify_blocker_as_unsupported_product(self):
        """A blocker with no Huawei product mapping → unsupported_product."""
        item = _make_blocker_item(
            status="needs_manual_review",
            status_reason="Product could not be mapped to the supported catalog.",
            normalized_product=None,
        )
        assert _classify_billing_blocker(item) == _BLOCKER_UNSUPPORTED_PRODUCT

    def test_no_product_mapping_even_with_other_status(self):
        """Any blocker with normalized_product=None is unsupported_product."""
        item = _make_blocker_item(
            status="needs_quantity",
            status_reason="Quantity is missing.",
            normalized_product=None,
        )
        assert _classify_billing_blocker(item) == _BLOCKER_UNSUPPORTED_PRODUCT


# ---------------------------------------------------------------------------
# 2. test_classify_blocker_as_spec_not_specific_enough
# ---------------------------------------------------------------------------

class TestClassifySpecNotSpecificEnough:
    def test_classify_blocker_as_spec_not_specific_enough(self):
        """A blocker with needs_spec status → spec_not_specific_enough."""
        item = _make_blocker_item(
            status="needs_spec",
            status_reason="Specification is missing.",
            normalized_product="ECS",
        )
        assert _classify_billing_blocker(item) == _BLOCKER_SPEC_NOT_SPECIFIC_ENOUGH

    def test_manual_review_with_spec_reason(self):
        """needs_manual_review with spec-related reason → spec_not_specific_enough."""
        item = _make_blocker_item(
            status="needs_manual_review",
            status_reason="Spec is ambiguous for this product.",
            normalized_product="RDS",
        )
        assert _classify_billing_blocker(item) == _BLOCKER_SPEC_NOT_SPECIFIC_ENOUGH


# ---------------------------------------------------------------------------
# 3. test_classify_blocker_as_pricing_blocked_by_catalog_gap
# ---------------------------------------------------------------------------

class TestClassifyPricingBlockedByCatalogGap:
    def test_classify_blocker_as_pricing_blocked_by_catalog_gap(self):
        """needs_price_confirmation blocker → pricing_blocked_by_catalog_gap."""
        item = _make_blocker_item(
            status="needs_price_confirmation",
            status_reason="No locally confirmed price is available.",
            normalized_product="ECS",
        )
        assert _classify_billing_blocker(item) == _BLOCKER_PRICING_BLOCKED_BY_CATALOG_GAP

    def test_manual_review_with_catalog_reason(self):
        """needs_manual_review with catalog/price reason → pricing_blocked_by_catalog_gap."""
        item = _make_blocker_item(
            status="needs_manual_review",
            status_reason="No confirmed price in catalog for this region.",
            normalized_product="EVS",
        )
        assert _classify_billing_blocker(item) == _BLOCKER_PRICING_BLOCKED_BY_CATALOG_GAP


# ---------------------------------------------------------------------------
# 4. test_classify_blocker_as_suspicious_source_semantics
# ---------------------------------------------------------------------------

class TestClassifySuspiciousSourceSemantics:
    def test_classify_blocker_as_suspicious_source_semantics(self):
        """Billing item with suspicious/unsafe reason → suspicious_source_semantics."""
        item = _make_blocker_item(
            status="needs_manual_review",
            status_reason="Source usage could not be safely confirmed as storage capacity.",
            normalized_product="EVS",
            quantity_source="billing_standardized",
        )
        assert _classify_billing_blocker(item) == _BLOCKER_SUSPICIOUS_SOURCE_SEMANTICS

    def test_needs_quantity_billing_item(self):
        """needs_quantity for billing item → suspicious_source_semantics."""
        item = _make_blocker_item(
            status="needs_quantity",
            status_reason="Quantity is missing.",
            normalized_product="ECS",
            quantity_source="billing_standardized",
        )
        assert _classify_billing_blocker(item) == _BLOCKER_SUSPICIOUS_SOURCE_SEMANTICS


# ---------------------------------------------------------------------------
# 5. test_downgrade_catalog_gap_blocker_to_unquoted_when_safe
# ---------------------------------------------------------------------------

class TestDowngradeCatalogGap:
    def test_downgrade_catalog_gap_blocker_to_unquoted_when_safe(self):
        """pricing_blocked_by_catalog_gap blocker should be downgraded to unquoted."""
        item = _make_blocker_item(
            status="needs_price_confirmation",
            status_reason="No locally confirmed price is available.",
            normalized_product="ECS",
        )
        should, reason = _should_downgrade_blocker_to_unquoted(item)
        assert should is True
        assert reason is not None
        assert "Catalog gap" in reason


# ---------------------------------------------------------------------------
# 6. test_do_not_downgrade_true_manual_review_blocker
# ---------------------------------------------------------------------------

class TestNoDowngradeManualReview:
    def test_do_not_downgrade_true_manual_review_blocker(self):
        """manual_review_required blocker should NOT be downgraded."""
        item = _make_blocker_item(
            status="needs_manual_review",
            status_reason="Requires human judgment for product selection.",
            normalized_product="ECS",
            quantity_source="source_file",  # Not billing
        )
        should, reason = _should_downgrade_blocker_to_unquoted(item)
        assert should is False

    def test_do_not_downgrade_unsupported_product(self):
        """unsupported_product blocker should NOT be downgraded."""
        item = _make_blocker_item(
            status="needs_manual_review",
            status_reason="Product could not be mapped to the supported catalog.",
            normalized_product=None,
        )
        should, reason = _should_downgrade_blocker_to_unquoted(item)
        assert should is False

    def test_do_not_downgrade_missing_region(self):
        """missing_region blocker should NOT be downgraded."""
        item = _make_blocker_item(
            status="needs_region",
            status_reason="Region is missing.",
            normalized_product="ECS",
        )
        should, reason = _should_downgrade_blocker_to_unquoted(item)
        assert should is False


# ---------------------------------------------------------------------------
# 7. test_blocker_triage_summary_groups_categories_stably
# ---------------------------------------------------------------------------

class TestBlockerTriageSummary:
    def test_blocker_triage_summary_groups_categories_stably(self):
        """_summarize_billing_blockers should assign stable categories."""
        blockers = [
            FlexibleQuoteBlocker(
                item_id="b1", product="DevOps", status="needs_manual_review",
                message="Product could not be mapped to the supported catalog.",
                source_file="t.csv",
            ).model_dump(),
            FlexibleQuoteBlocker(
                item_id="b2", product="ECS", status="needs_spec",
                message="Specification is missing.",
                source_file="t.csv",
            ).model_dump(),
            FlexibleQuoteBlocker(
                item_id="b3", product="EVS", status="needs_price_confirmation",
                message="No locally confirmed price is available.",
                source_file="t.csv",
            ).model_dump(),
        ]
        # Build matching requirements for classification
        requirements = [
            RequirementItem(
                item_id="b1", source_file="t.csv", raw_product_name="DevOps",
                status="needs_manual_review",
                status_reason="Product could not be mapped to the supported catalog.",
            ).model_dump(),
            RequirementItem(
                item_id="b2", source_file="t.csv", raw_product_name="ECS",
                normalized_product="ECS",
                status="needs_spec",
                status_reason="Specification is missing.",
            ).model_dump(),
            RequirementItem(
                item_id="b3", source_file="t.csv", raw_product_name="EVS",
                normalized_product="EVS",
                status="needs_price_confirmation",
                status_reason="No locally confirmed price is available.",
            ).model_dump(),
        ]
        state = {"quote_blockers": blockers, "requirements": requirements}
        summary = _summarize_billing_blockers(state)
        assert len(summary) == 3
        categories = {entry["category"] for entry in summary}
        assert _BLOCKER_UNSUPPORTED_PRODUCT in categories
        assert _BLOCKER_SPEC_NOT_SPECIFIC_ENOUGH in categories
        assert _BLOCKER_PRICING_BLOCKED_BY_CATALOG_GAP in categories


# ---------------------------------------------------------------------------
# 8. test_summary_mentions_blocker_triage_breakdown
# ---------------------------------------------------------------------------

class TestSummaryMentionsTriage:
    def test_summary_mentions_blocker_triage_breakdown(self):
        """summarize_quote should include blocker triage in assumptions when blockers exist."""
        # Create a minimal state with blockers
        blocker = FlexibleQuoteBlocker(
            item_id="b1", product="DevOps", status="needs_manual_review",
            message="Product could not be mapped to the supported catalog.",
            source_file="t.csv",
        )
        req = RequirementItem(
            item_id="b1", source_file="t.csv", raw_product_name="DevOps",
            status="needs_manual_review",
            status_reason="Product could not be mapped to the supported catalog.",
        )
        state = {
            "requirements": [req.model_dump()],
            "quote_ready_items": [],
            "quote_lines": [],
            "quote_blockers": [blocker.model_dump()],
            "unquoted_items": [],
            "quote_context": {"region": "chile"},
            "audit_log": [],
            "progress_callback": None,
        }
        result = summarize_quote(state)
        summary = FlexibleQuoteSummary.model_validate(result["summary"])
        # Check that BLOCKER TRIAGE appears in assumptions
        triage_assumptions = [a for a in summary.assumptions if "BLOCKER TRIAGE" in a]
        assert len(triage_assumptions) >= 1
        # Check that billing_blocker_analysis is in the result
        assert "billing_blocker_analysis" in result
        analysis = result["billing_blocker_analysis"]
        assert analysis["blocker_total"] == 1
        assert _BLOCKER_UNSUPPORTED_PRODUCT in analysis["blocker_categories"]


# ---------------------------------------------------------------------------
# 9. test_information_sheet_mentions_top_blocker_categories
# ---------------------------------------------------------------------------

class TestExportMentionsTriage:
    def test_information_sheet_mentions_top_blocker_categories(self):
        """Exported Información sheet should contain BLOCKER TRIAGE section."""
        blocker = FlexibleQuoteBlocker(
            item_id="b1", product="DevOps", status="needs_manual_review",
            message="Product could not be mapped to the supported catalog.",
            source_file="t.csv",
        )
        req = RequirementItem(
            item_id="b1", source_file="t.csv", raw_product_name="DevOps",
            status="needs_manual_review",
            status_reason="Product could not be mapped to the supported catalog.",
        )
        blocker_analysis = _analyze_billing_blocker_triage({
            "quote_blockers": [blocker.model_dump()],
            "requirements": [req.model_dump()],
        })
        state = {
            "requirements": [req.model_dump()],
            "quote_ready_items": [],
            "quote_lines": [],
            "quote_blockers": [blocker.model_dump()],
            "unquoted_items": [],
            "quote_context": {"region": "chile"},
            "summary": FlexibleQuoteSummary(
                total_input_items=1,
                blocker_count=1,
            ).model_dump(),
            "billing_gap_analysis": {},
            "billing_reconciliation": {},
            "billing_blocker_analysis": blocker_analysis,
            # mapped_billing_resources triggers the billing template export path
            "mapped_billing_resources": [{"source_file": "t.csv", "vendor": "azure"}],
            "audit_log": [],
            "progress_callback": None,
        }
        result = export_flexible_workbook(state)
        wb = load_workbook(BytesIO(result["workbook"].content))
        info_ws = wb["Información"]
        info_text = "\n".join(
            str(info_ws.cell(row, 1).value or "")
            for row in range(1, info_ws.max_row + 1)
        )
        assert "BLOCKER TRIAGE" in info_text
        assert _BLOCKER_UNSUPPORTED_PRODUCT in info_text


# ---------------------------------------------------------------------------
# 10. test_real_billing_blocker_count_decreases_or_becomes_better_classified
# ---------------------------------------------------------------------------

class TestRealAzureFile:
    @pytest.mark.skipif(not AZURE_CSV_PATH.exists(), reason="Azure CSV not available")
    def test_real_billing_blocker_count_decreases_or_becomes_better_classified(self, azure_document):
        """Real Azure file: blockers should be classified, and some should be downgraded."""
        state = _make_billing_state(azure_document)
        blockers = state["quote_blockers"]
        analysis = state.get("billing_blocker_analysis", {})

        # Blockers should be classified into stable categories
        if blockers:
            assert "blocker_categories" in analysis
            # All categories should be from the known set
            for cat in analysis["blocker_categories"]:
                assert cat in {
                    _BLOCKER_UNSUPPORTED_PRODUCT,
                    _BLOCKER_SPEC_NOT_SPECIFIC_ENOUGH,
                    _BLOCKER_PRICING_BLOCKED_BY_CATALOG_GAP,
                    _BLOCKER_SUSPICIOUS_SOURCE_SEMANTICS,
                    _BLOCKER_MANUAL_REVIEW_REQUIRED,
                    _BLOCKER_MISSING_REGION,
                }, f"Unknown blocker category: {cat}"

        # Downgradable count should be computed
        assert "downgradable_count" in analysis
        assert "remaining_blocker_count" in analysis

        # Remaining blockers should be <= total blockers
        assert analysis["remaining_blocker_count"] <= analysis["blocker_total"]

    @pytest.mark.skipif(not AZURE_CSV_PATH.exists(), reason="Azure CSV not available")
    def test_real_billing_blocker_categories_are_stable(self, azure_document):
        """Real Azure file: all blockers should have a known category (no 'unknown')."""
        state = _make_billing_state(azure_document)
        analysis = state.get("billing_blocker_analysis", {})
        for cat in analysis.get("blocker_categories", {}):
            assert cat != "unknown", f"Blocker category 'unknown' found — triage incomplete"


# ---------------------------------------------------------------------------
# 11. test_gap_reconciliation_and_blocker_triage_sections_coexist
# ---------------------------------------------------------------------------

class TestCoexistence:
    @pytest.mark.skipif(not AZURE_CSV_PATH.exists(), reason="Azure CSV not available")
    def test_gap_reconciliation_and_blocker_triage_sections_coexist(self, azure_document):
        """Export should contain GAP ANALYSIS, RECONCILIATION WARNING, and BLOCKER TRIAGE."""
        state = _make_billing_state(azure_document)
        result = export_flexible_workbook(state)
        wb = load_workbook(BytesIO(result["workbook"].content))

        # Check Summary sheet
        summary_ws = wb["Summary"]
        summary_text = ""
        for row in range(1, summary_ws.max_row + 1):
            for col in range(1, summary_ws.max_column + 1):
                val = summary_ws.cell(row, col).value
                if val:
                    summary_text += str(val) + "\n"

        # GAP ANALYSIS should be present
        assert "GAP ANALYSIS" in summary_text

        # BLOCKER TRIAGE should be present (if there are blockers)
        if state["quote_blockers"]:
            assert "BLOCKER TRIAGE" in summary_text

        # Check Información sheet
        info_ws = wb["Información"]
        info_text = "\n".join(
            str(info_ws.cell(row, 1).value or "")
            for row in range(1, info_ws.max_row + 1)
        )
        assert "GAP ANALYSIS" in info_text
        if state["quote_blockers"]:
            assert "BLOCKER TRIAGE" in info_text


# ---------------------------------------------------------------------------
# 12. test_downgraded_blockers_do_not_change_existing_quote_totals
# ---------------------------------------------------------------------------

class TestDowngradePreservesTotals:
    def test_downgraded_blockers_do_not_change_existing_quote_totals(self):
        """Downgrading blockers to unquoted should not affect quote line totals."""
        # Create a state with a quoted line and a blocker
        from app.models import FlexibleQuoteLine
        ql = FlexibleQuoteLine(
            line_id="line::q1", requirement_item_id="q1",
            product="ECS", region="chile",
            quantity=2.0, unit="instance-month", billing_mode="monthly",
            matched_sku="c6.large.2", matched_tier="general",
            unit_price=50.0, monthly_price=100.0, currency="USD",
        )
        blocker = FlexibleQuoteBlocker(
            item_id="b1", product="EVS", status="needs_price_confirmation",
            message="No locally confirmed price is available.",
            source_file="t.csv",
        )
        req_quoted = RequirementItem(
            item_id="q1", source_file="t.csv", raw_product_name="ECS",
            normalized_product="ECS", quantity=2.0,
            quantity_source="billing_standardized", region="chile",
            status="ready",
        )
        req_blocker = RequirementItem(
            item_id="b1", source_file="t.csv", raw_product_name="EVS",
            normalized_product="EVS", quantity=100.0,
            quantity_source="billing_standardized", region="chile",
            status="needs_price_confirmation",
            status_reason="No locally confirmed price is available.",
        )
        state = {
            "requirements": [req_quoted.model_dump(), req_blocker.model_dump()],
            "quote_ready_items": [req_quoted.model_dump()],
            "quote_lines": [ql.model_dump()],
            "quote_blockers": [blocker.model_dump()],
            "unquoted_items": [],
            "quote_context": {"region": "chile"},
            "audit_log": [],
            "progress_callback": None,
        }
        result = summarize_quote(state)
        summary = FlexibleQuoteSummary.model_validate(result["summary"])
        # Total monthly price should still be $100 (from the quoted line only)
        assert summary.total_monthly_price == 100.0


# ---------------------------------------------------------------------------
# 13. test_no_unknown_blocker_category_after_triage
# ---------------------------------------------------------------------------

class TestNoUnknownCategory:
    def test_no_unknown_blocker_category_after_triage(self):
        """Every blocker should map to a known category — never 'unknown'."""
        # Test all possible status values
        test_cases = [
            ("needs_manual_review", "Product could not be mapped to the supported catalog.", None),
            ("needs_manual_review", "Some unknown reason.", "ECS"),
            ("needs_quantity", "Quantity is missing.", "ECS"),
            ("needs_spec", "Specification is missing.", "ECS"),
            ("needs_region", "Region is missing.", "ECS"),
            ("needs_price_confirmation", "No locally confirmed price is available.", "ECS"),
            ("needs_manual_review", "Spec is ambiguous.", "RDS"),
            ("needs_manual_review", "No confirmed price in catalog.", "EVS"),
        ]
        for status, reason, product in test_cases:
            item = _make_blocker_item(
                status=status,
                status_reason=reason,
                normalized_product=product,
            )
            category = _classify_billing_blocker(item)
            assert category != "unknown", f"Blocker with status={status}, reason={reason} got 'unknown' category"
            assert category in {
                _BLOCKER_UNSUPPORTED_PRODUCT,
                _BLOCKER_SPEC_NOT_SPECIFIC_ENOUGH,
                _BLOCKER_PRICING_BLOCKED_BY_CATALOG_GAP,
                _BLOCKER_SUSPICIOUS_SOURCE_SEMANTICS,
                _BLOCKER_MANUAL_REVIEW_REQUIRED,
                _BLOCKER_MISSING_REGION,
            }


# ---------------------------------------------------------------------------
# 14. test_classify_missing_region
# ---------------------------------------------------------------------------

class TestClassifyMissingRegion:
    def test_classify_missing_region(self):
        """needs_region blocker → missing_region."""
        item = _make_blocker_item(
            status="needs_region",
            status_reason="Region is missing.",
            normalized_product="ECS",
        )
        assert _classify_billing_blocker(item) == _BLOCKER_MISSING_REGION


# ---------------------------------------------------------------------------
# 15. test_top_blocker_categories_sorted_by_count
# ---------------------------------------------------------------------------

class TestTopBlockerCategories:
    def test_top_blocker_categories_sorted_by_count(self):
        """_top_blocker_categories should return categories sorted by count descending."""
        blockers = [
            FlexibleQuoteBlocker(
                item_id=f"b{i}", product="DevOps", status="needs_manual_review",
                message="Product could not be mapped to the supported catalog.",
                source_file="t.csv",
            ).model_dump()
            for i in range(5)
        ]
        blockers.append(
            FlexibleQuoteBlocker(
                item_id="b_spec", product="ECS", status="needs_spec",
                message="Specification is missing.",
                source_file="t.csv",
            ).model_dump()
        )
        requirements = [
            RequirementItem(
                item_id=f"b{i}", source_file="t.csv", raw_product_name="DevOps",
                status="needs_manual_review",
                status_reason="Product could not be mapped to the supported catalog.",
            ).model_dump()
            for i in range(5)
        ]
        requirements.append(
            RequirementItem(
                item_id="b_spec", source_file="t.csv", raw_product_name="ECS",
                normalized_product="ECS",
                status="needs_spec",
                status_reason="Specification is missing.",
            ).model_dump()
        )
        state = {"quote_blockers": blockers, "requirements": requirements}
        top = _top_blocker_categories(state, limit=10)
        assert len(top) == 2
        # unsupported_product (5) should come before spec_not_specific_enough (1)
        assert top[0]["category"] == _BLOCKER_UNSUPPORTED_PRODUCT
        assert top[0]["count"] == 5
        assert top[1]["category"] == _BLOCKER_SPEC_NOT_SPECIFIC_ENOUGH
        assert top[1]["count"] == 1
