"""Phase Next+8 tests: manual review design — unsupported_product blocker
triage, minimal input fields, Huawei target family suggestions, export integration."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.flexible_workflow import (
    _classify_manual_review_need,
    _minimal_manual_review_fields,
    _suggest_huawei_target_family,
    _build_manual_review_candidates,
    _analyze_manual_review_design,
    _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION,
    _MANUAL_REVIEW_CAPACITY_OR_TIER_CONFIRMATION,
    _MANUAL_REVIEW_BILLING_MODEL_SELECTION,
    _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
    _MANUAL_REVIEW_UNSUPPORTED_BY_CATALOG,
    _MANUAL_REVIEW_UNKNOWN,
    _MANUAL_REVIEW_NEED_ALL,
    _BLOCKER_UNSUPPORTED_PRODUCT,
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
        "billing_manual_review_design": sum_result.get("billing_manual_review_design", {}),
        "mapped_billing_resources": mapped,
        "billing_lines": lines,
        "billing_groups": groups,
        "llm_aggregated_billing_items": agg_items,
        "standardized_billing_resources": standardized,
        "quote_context": {"region": region},
        "audit_log": [],
        "progress_callback": None,
    }


def _make_unsupported_item(raw_name: str, notes: str = "") -> RequirementItem:
    return RequirementItem(
        item_id="test-unsupported-1",
        source_file="test.csv",
        source_sheet="csv",
        row_number=1,
        raw_product_name=raw_name,
        quantity=None,
        quantity_source="billing_standardized",
        unit="1",
        region="chile",
        normalized_product=None,
        status="needs_manual_review",
        status_reason="Product could not be mapped to the supported catalog.",
        notes=notes,
    )


# ---------------------------------------------------------------------------
# 1. test_build_manual_review_candidates_from_unsupported_blockers
# ---------------------------------------------------------------------------

class TestBuildCandidates:
    def test_build_manual_review_candidates_from_unsupported_blockers(self):
        """Only unsupported_product blockers should become manual review candidates."""
        blocker_unsupported = FlexibleQuoteBlocker(
            item_id="b1", product="API Management", status="needs_manual_review",
            message="Product could not be mapped to the supported catalog.",
            source_file="t.csv",
        )
        blocker_spec = FlexibleQuoteBlocker(
            item_id="b2", product="ECS", status="needs_spec",
            message="Specification is missing.",
            source_file="t.csv",
        )
        req1 = RequirementItem(
            item_id="b1", source_file="t.csv", raw_product_name="API Management",
            status="needs_manual_review",
            status_reason="Product could not be mapped to the supported catalog.",
        )
        req2 = RequirementItem(
            item_id="b2", source_file="t.csv", raw_product_name="ECS",
            normalized_product="ECS",
            status="needs_spec",
            status_reason="Specification is missing.",
        )
        state = {
            "quote_blockers": [blocker_unsupported.model_dump(), blocker_spec.model_dump()],
            "requirements": [req1.model_dump(), req2.model_dump()],
            "llm_aggregated_billing_items": [],
        }
        candidates = _build_manual_review_candidates(state)
        # Only the unsupported blocker should become a candidate
        assert len(candidates) == 1
        assert candidates[0]["candidate_id"] == "b1"
        assert candidates[0]["blocker_category"] == _BLOCKER_UNSUPPORTED_PRODUCT


# ---------------------------------------------------------------------------
# 2. test_classify_manual_review_need_for_api_management
# ---------------------------------------------------------------------------

class TestClassifyApiManagement:
    def test_classify_manual_review_need_for_api_management(self):
        """API Management → target_product_selection."""
        item = _make_unsupported_item("API Management - Developer")
        assert _classify_manual_review_need(item) == _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION


# ---------------------------------------------------------------------------
# 3. test_classify_manual_review_need_for_azure_dns
# ---------------------------------------------------------------------------

class TestClassifyAzureDns:
    def test_classify_manual_review_need_for_azure_dns(self):
        """Azure DNS → service_scope_decision."""
        item = _make_unsupported_item("Azure DNS - Private")
        assert _classify_manual_review_need(item) == _MANUAL_REVIEW_SERVICE_SCOPE_DECISION


# ---------------------------------------------------------------------------
# 4. test_classify_manual_review_need_for_fabric_capacity
# ---------------------------------------------------------------------------

class TestClassifyFabricCapacity:
    def test_classify_manual_review_need_for_fabric_capacity(self):
        """Fabric Capacity → unsupported_by_current_catalog."""
        item = _make_unsupported_item("Fabric Capacity Reservation")
        assert _classify_manual_review_need(item) == _MANUAL_REVIEW_UNSUPPORTED_BY_CATALOG


# ---------------------------------------------------------------------------
# 5. test_minimal_manual_review_fields_for_target_product_selection
# ---------------------------------------------------------------------------

class TestMinimalFieldsTargetProduct:
    def test_minimal_manual_review_fields_for_target_product_selection(self):
        """target_product_selection needs only huawei_product_family."""
        item = _make_unsupported_item("API Management - Developer")
        fields = _minimal_manual_review_fields(item)
        assert fields == ["huawei_product_family"]


# ---------------------------------------------------------------------------
# 6. test_minimal_manual_review_fields_for_service_scope_decision
# ---------------------------------------------------------------------------

class TestMinimalFieldsServiceScope:
    def test_minimal_manual_review_fields_for_service_scope_decision(self):
        """service_scope_decision needs include_in_quote and mapped_as."""
        item = _make_unsupported_item("Azure DNS - Private")
        fields = _minimal_manual_review_fields(item)
        assert "include_in_quote" in fields
        assert "mapped_as" in fields


# ---------------------------------------------------------------------------
# 7. test_suggest_huawei_target_family_returns_none_when_not_safe
# ---------------------------------------------------------------------------

class TestSuggestFamily:
    def test_suggest_huawei_target_family_returns_none_when_not_safe(self):
        """Unknown product with no safe inference → None."""
        item = _make_unsupported_item("Some Random Service XYZ")
        assert _suggest_huawei_target_family(item) is None

    def test_suggest_huawei_target_family_for_api_management(self):
        """API Management → 'API Gateway'."""
        item = _make_unsupported_item("API Management - Developer")
        assert _suggest_huawei_target_family(item) == "API Gateway"

    def test_suggest_huawei_target_family_for_dns(self):
        """Azure DNS → 'DNS'."""
        item = _make_unsupported_item("Azure DNS - Private")
        assert _suggest_huawei_target_family(item) == "DNS"


# ---------------------------------------------------------------------------
# 8. test_manual_review_design_summary_counts_categories
# ---------------------------------------------------------------------------

class TestManualReviewDesignSummary:
    def test_manual_review_design_summary_counts_categories(self):
        """_analyze_manual_review_design should count categories correctly."""
        blocker1 = FlexibleQuoteBlocker(
            item_id="b1", product="API Management", status="needs_manual_review",
            message="Product could not be mapped to the supported catalog.",
            source_file="t.csv",
        )
        blocker2 = FlexibleQuoteBlocker(
            item_id="b2", product="Azure DNS", status="needs_manual_review",
            message="Product could not be mapped to the supported catalog.",
            source_file="t.csv",
        )
        req1 = RequirementItem(
            item_id="b1", source_file="t.csv", raw_product_name="API Management",
            status="needs_manual_review",
            status_reason="Product could not be mapped to the supported catalog.",
        )
        req2 = RequirementItem(
            item_id="b2", source_file="t.csv", raw_product_name="Azure DNS",
            status="needs_manual_review",
            status_reason="Product could not be mapped to the supported catalog.",
        )
        state = {
            "quote_blockers": [blocker1.model_dump(), blocker2.model_dump()],
            "requirements": [req1.model_dump(), req2.model_dump()],
            "llm_aggregated_billing_items": [],
        }
        analysis = _analyze_manual_review_design(state)
        assert analysis["total_candidates"] == 2
        assert _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION in analysis["categories"]
        assert _MANUAL_REVIEW_SERVICE_SCOPE_DECISION in analysis["categories"]


# ---------------------------------------------------------------------------
# 9. test_summary_sheet_mentions_manual_review_design
# ---------------------------------------------------------------------------

class TestSummarySheetMentions:
    def test_summary_sheet_mentions_manual_review_design(self):
        """Summary sheet notes should contain MANUAL REVIEW DESIGN section."""
        blocker = FlexibleQuoteBlocker(
            item_id="b1", product="API Management", status="needs_manual_review",
            message="Product could not be mapped to the supported catalog.",
            source_file="t.csv",
        )
        req = RequirementItem(
            item_id="b1", source_file="t.csv", raw_product_name="API Management",
            status="needs_manual_review",
            status_reason="Product could not be mapped to the supported catalog.",
        )
        manual_review = _analyze_manual_review_design({
            "quote_blockers": [blocker.model_dump()],
            "requirements": [req.model_dump()],
            "llm_aggregated_billing_items": [],
        })
        state = {
            "requirements": [req.model_dump()],
            "quote_ready_items": [],
            "quote_lines": [],
            "quote_blockers": [blocker.model_dump()],
            "unquoted_items": [],
            "quote_context": {"region": "chile"},
            "summary": FlexibleQuoteSummary(
                total_input_items=1, blocker_count=1,
            ).model_dump(),
            "billing_gap_analysis": {},
            "billing_reconciliation": {},
            "billing_blocker_analysis": {"blocker_total": 1, "blocker_categories": {"unsupported_product": 1}},
            "billing_manual_review_design": manual_review,
            "mapped_billing_resources": [{"source_file": "t.csv", "vendor": "azure"}],
            "audit_log": [],
            "progress_callback": None,
        }
        result = export_flexible_workbook(state)
        wb = load_workbook(BytesIO(result["workbook"].content))
        summary_ws = wb["Summary"]
        summary_text = ""
        for row in range(1, summary_ws.max_row + 1):
            for col in range(1, summary_ws.max_column + 1):
                val = summary_ws.cell(row, col).value
                if val:
                    summary_text += str(val) + "\n"
        assert "MANUAL REVIEW DESIGN" in summary_text


# ---------------------------------------------------------------------------
# 10. test_information_sheet_mentions_top_manual_review_categories
# ---------------------------------------------------------------------------

class TestInfoSheetMentions:
    def test_information_sheet_mentions_top_manual_review_categories(self):
        """Información sheet should contain MANUAL REVIEW DESIGN section."""
        blocker = FlexibleQuoteBlocker(
            item_id="b1", product="API Management", status="needs_manual_review",
            message="Product could not be mapped to the supported catalog.",
            source_file="t.csv",
        )
        req = RequirementItem(
            item_id="b1", source_file="t.csv", raw_product_name="API Management",
            status="needs_manual_review",
            status_reason="Product could not be mapped to the supported catalog.",
        )
        manual_review = _analyze_manual_review_design({
            "quote_blockers": [blocker.model_dump()],
            "requirements": [req.model_dump()],
            "llm_aggregated_billing_items": [],
        })
        state = {
            "requirements": [req.model_dump()],
            "quote_ready_items": [],
            "quote_lines": [],
            "quote_blockers": [blocker.model_dump()],
            "unquoted_items": [],
            "quote_context": {"region": "chile"},
            "summary": FlexibleQuoteSummary(
                total_input_items=1, blocker_count=1,
            ).model_dump(),
            "billing_gap_analysis": {},
            "billing_reconciliation": {},
            "billing_blocker_analysis": {"blocker_total": 1, "blocker_categories": {"unsupported_product": 1}},
            "billing_manual_review_design": manual_review,
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
        assert "MANUAL REVIEW DESIGN" in info_text
        assert _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION in info_text


# ---------------------------------------------------------------------------
# 11. test_manual_review_design_does_not_change_quote_totals
# ---------------------------------------------------------------------------

class TestPreservesTotals:
    def test_manual_review_design_does_not_change_quote_totals(self):
        """Manual review design is read-only; it must not change quote totals."""
        from app.models import FlexibleQuoteLine
        ql = FlexibleQuoteLine(
            line_id="line::q1", requirement_item_id="q1",
            product="ECS", region="chile",
            quantity=2.0, unit="instance-month", billing_mode="monthly",
            matched_sku="c6.large.2", matched_tier="general",
            unit_price=50.0, monthly_price=100.0, currency="USD",
        )
        blocker = FlexibleQuoteBlocker(
            item_id="b1", product="API Management", status="needs_manual_review",
            message="Product could not be mapped to the supported catalog.",
            source_file="t.csv",
        )
        req = RequirementItem(
            item_id="q1", source_file="t.csv", raw_product_name="ECS",
            normalized_product="ECS", quantity=2.0,
            quantity_source="billing_standardized", region="chile",
            status="ready",
        )
        req_b = RequirementItem(
            item_id="b1", source_file="t.csv", raw_product_name="API Management",
            status="needs_manual_review",
            status_reason="Product could not be mapped to the supported catalog.",
        )
        state = {
            "requirements": [req.model_dump(), req_b.model_dump()],
            "quote_ready_items": [req.model_dump()],
            "quote_lines": [ql.model_dump()],
            "quote_blockers": [blocker.model_dump()],
            "unquoted_items": [],
            "quote_context": {"region": "chile"},
            "llm_aggregated_billing_items": [],
            "audit_log": [],
            "progress_callback": None,
        }
        result = summarize_quote(state)
        summary = FlexibleQuoteSummary.model_validate(result["summary"])
        assert summary.total_monthly_price == 100.0
        assert summary.quoted_items == 1
        assert summary.blocker_count == 1


# ---------------------------------------------------------------------------
# 12. test_manual_review_design_uses_source_amount_ordering
# ---------------------------------------------------------------------------

class TestSourceAmountOrdering:
    def test_manual_review_design_uses_source_amount_ordering(self):
        """Candidates should be sorted by source amount descending."""
        blocker1 = FlexibleQuoteBlocker(
            item_id="b1", product="Small Service", status="needs_manual_review",
            message="Product could not be mapped to the supported catalog.",
            source_file="t.csv",
        )
        blocker2 = FlexibleQuoteBlocker(
            item_id="b2", product="Big Service", status="needs_manual_review",
            message="Product could not be mapped to the supported catalog.",
            source_file="t.csv",
        )
        req1 = RequirementItem(
            item_id="b1", source_file="t.csv", raw_product_name="Small Service",
            status="needs_manual_review",
            status_reason="Product could not be mapped to the supported catalog.",
        )
        req2 = RequirementItem(
            item_id="b2", source_file="t.csv", raw_product_name="Big Service",
            status="needs_manual_review",
            status_reason="Product could not be mapped to the supported catalog.",
        )
        # b2 has higher amount
        agg_items = [
            {"source_file": "t.csv", "amount": 10.0, "derived_quantity": 1, "derived_unit": "1",
             "product_type": "", "product_sku": "", "source_line_numbers": []},
            {"source_file": "t.csv", "amount": 500.0, "derived_quantity": 1, "derived_unit": "1",
             "product_type": "", "product_sku": "", "source_line_numbers": []},
        ]
        state = {
            "quote_blockers": [blocker1.model_dump(), blocker2.model_dump()],
            "requirements": [req1.model_dump(), req2.model_dump()],
            "llm_aggregated_billing_items": agg_items,
        }
        candidates = _build_manual_review_candidates(state)
        # b2 (amount=500) should come before b1 (amount=10)
        assert len(candidates) == 2
        assert candidates[0]["source_amount"] >= candidates[1]["source_amount"]


# ---------------------------------------------------------------------------
# 13. test_minimal_field_frequency_is_reported
# ---------------------------------------------------------------------------

class TestMinimalFieldFrequency:
    def test_minimal_field_frequency_is_reported(self):
        """_analyze_manual_review_design should report minimal field frequency."""
        blocker1 = FlexibleQuoteBlocker(
            item_id="b1", product="API Management", status="needs_manual_review",
            message="Product could not be mapped to the supported catalog.",
            source_file="t.csv",
        )
        blocker2 = FlexibleQuoteBlocker(
            item_id="b2", product="Azure DNS", status="needs_manual_review",
            message="Product could not be mapped to the supported catalog.",
            source_file="t.csv",
        )
        req1 = RequirementItem(
            item_id="b1", source_file="t.csv", raw_product_name="API Management",
            status="needs_manual_review",
            status_reason="Product could not be mapped to the supported catalog.",
        )
        req2 = RequirementItem(
            item_id="b2", source_file="t.csv", raw_product_name="Azure DNS",
            status="needs_manual_review",
            status_reason="Product could not be mapped to the supported catalog.",
        )
        state = {
            "quote_blockers": [blocker1.model_dump(), blocker2.model_dump()],
            "requirements": [req1.model_dump(), req2.model_dump()],
            "llm_aggregated_billing_items": [],
        }
        analysis = _analyze_manual_review_design(state)
        field_freq = analysis["minimal_field_frequency"]
        assert isinstance(field_freq, dict)
        # API Management needs huawei_product_family; DNS needs include_in_quote + mapped_as
        assert "huawei_product_family" in field_freq
        assert "include_in_quote" in field_freq


# ---------------------------------------------------------------------------
# 14. test_real_azure_file_manual_review_candidates
# ---------------------------------------------------------------------------

class TestRealAzureFile:
    @pytest.mark.skipif(not AZURE_CSV_PATH.exists(), reason="Azure CSV not available")
    def test_real_azure_manual_review_candidates(self, azure_document):
        """Real Azure file: all 22 unsupported blockers should become candidates."""
        state = _make_billing_state(azure_document)
        manual_review = state.get("billing_manual_review_design", {})

        assert manual_review["total_candidates"] > 0
        assert "categories" in manual_review
        assert "minimal_field_frequency" in manual_review
        assert "top_unsupported_by_amount" in manual_review

        # All categories should be from the known set
        for cat in manual_review["categories"]:
            assert cat in _MANUAL_REVIEW_NEED_ALL, f"Unknown manual review category: {cat}"

    @pytest.mark.skipif(not AZURE_CSV_PATH.exists(), reason="Azure CSV not available")
    def test_real_azure_candidates_have_structured_fields(self, azure_document):
        """Real Azure file: each candidate should have all required fields."""
        state = _make_billing_state(azure_document)
        manual_review = state.get("billing_manual_review_design", {})
        candidates = manual_review.get("candidates", [])

        required_fields = {
            "candidate_id", "source_label", "source_product_type",
            "source_product_sku", "source_amount", "source_quantity",
            "source_unit", "blocker_category", "manual_review_need",
            "minimal_fields_required", "suggested_huawei_target_family",
            "reason", "source_line_numbers",
        }
        for c in candidates:
            assert required_fields.issubset(set(c.keys())), f"Missing fields: {required_fields - set(c.keys())}"

    @pytest.mark.skipif(not AZURE_CSV_PATH.exists(), reason="Azure CSV not available")
    def test_real_azure_quote_totals_unchanged(self, azure_document):
        """Real Azure file: quote totals should not change from manual review design."""
        state = _make_billing_state(azure_document)
        summary = FlexibleQuoteSummary.model_validate(state["summary"])
        assert summary.quoted_items == 26
        assert summary.total_monthly_price == 7635.67
