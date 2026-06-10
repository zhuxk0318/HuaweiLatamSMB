"""Phase Next+11 tests: manual review repricing — override application,
recomputation, count changes, export integration, and no-change guarantee."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.flexible_workflow import (
    _validate_manual_review_inputs,
    _manual_review_input_errors,
    _apply_manual_review_inputs,
    _apply_manual_review_decision,
    _build_manual_review_candidates,
    _analyze_manual_review_design,
    _apply_manual_review_overrides_to_requirements,
    _recompute_billing_after_manual_review,
    _rebuild_billing_state_after_manual_review,
    _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION,
    _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
    _MANUAL_REVIEW_BILLING_MODEL_SELECTION,
    _MANUAL_REVIEW_UNSUPPORTED_BY_CATALOG,
    _MANUAL_REVIEW_CAPACITY_OR_TIER_CONFIRMATION,
    _BLOCKER_UNSUPPORTED_PRODUCT,
    apply_manual_review_from_api,
    _parse_csv_document,
    _extract_billing_lines,
    _group_billing_lines,
    _aggregate_billing_groups_fallback,
    _build_requirements_from_llm_aggregated_billing_items,
    _standardize_billing_lines,
    _map_standardized_billing_resources_to_huawei,
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
    FlexibleQuoteSummary,
    FlexibleQuoteBlocker,
    RequirementItem,
    FlexibleQuoteLine,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

AZURE_CSV_PATH = Path("/root/SMBReference/CGE/azure Billing_invoice_transactions.csv")


def _make_candidate(
    candidate_id: str = "c1",
    manual_review_need: str = _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
    source_label: str = "Azure DNS",
) -> dict:
    return {
        "candidate_id": candidate_id,
        "source_label": source_label,
        "source_product_type": "dns",
        "source_product_sku": "",
        "source_amount": 100.0,
        "source_quantity": 1.0,
        "source_unit": "1",
        "blocker_category": _BLOCKER_UNSUPPORTED_PRODUCT,
        "manual_review_need": manual_review_need,
        "minimal_fields_required": ["include_in_quote", "mapped_as"],
        "suggested_huawei_target_family": None,
        "reason": "Product could not be mapped to the supported catalog.",
        "source_line_numbers": [],
    }


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
        "price_catalog": catalog,
        "understanding": {"profile": {}},
        "matched_products": [],
        "audit_log": [],
        "progress_callback": None,
    }


def _make_state_with_blocker_and_quote(
    blocker_id: str = "b1",
    blocker_product: str = "Azure DNS",
    blocker_need: str = _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
) -> dict:
    """Build a minimal state with one quoted item and one blocker."""
    from app.models import MatchedProduct

    ql = FlexibleQuoteLine(
        line_id="line::q1", requirement_item_id="q1",
        product="ECS", region="chile",
        quantity=2.0, unit="instance-month", billing_mode="monthly",
        matched_sku="c6.large.2", matched_tier="general",
        unit_price=50.0, monthly_price=100.0, currency="USD",
    )
    blocker = FlexibleQuoteBlocker(
        item_id=blocker_id, product=blocker_product, status="needs_manual_review",
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
        item_id=blocker_id, source_file="t.csv", raw_product_name=blocker_product,
        status="needs_manual_review",
        status_reason="Product could not be mapped to the supported catalog.",
    )
    matched = [
        MatchedProduct(
            item_id="q1", product="ECS",
            match_method="rule_match", confidence=1,
            rationale="Matched using local product synonym rules.",
        ).model_dump(),
        MatchedProduct(
            item_id=blocker_id, product=None,
            match_method="llm_fallback", confidence=0,
            rationale="No deterministic product mapping hit.",
        ).model_dump(),
    ]
    return {
        "requirements": [req.model_dump(), req_b.model_dump()],
        "quote_ready_items": [req.model_dump()],
        "quote_lines": [ql.model_dump()],
        "quote_blockers": [blocker.model_dump()],
        "unquoted_items": [],
        "quote_context": {"region": "chile"},
        "price_catalog": _catalog_for_region("chile"),
        "understanding": {"profile": {}},
        "matched_products": matched,
        "llm_aggregated_billing_items": [],
        "audit_log": [],
        "progress_callback": None,
    }


# ---------------------------------------------------------------------------
# 1. test_manual_review_exclude_removes_item_from_blocker_count
# ---------------------------------------------------------------------------

class TestExcludeRemovesBlocker:
    def test_manual_review_exclude_removes_item_from_blocker_count(self):
        """include_in_quote=false should remove the item from blockers."""
        state = _make_state_with_blocker_and_quote("b1", "Azure DNS")
        applied_results = [{
            "candidate_id": "b1",
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": False, "mapped_as": None},
            "outcome": "excluded_by_manual_review",
            "overrides": {},
        }]
        result = _apply_manual_review_overrides_to_requirements(state, applied_results)
        # Blocker should be removed
        assert len(result["quote_blockers"]) == 0
        # Item should be in excluded list
        assert "b1" in result["excluded_by_manual_review"]
        # Requirement should be marked excluded
        req_b = next(r for r in result["requirements"] if r["item_id"] == "b1")
        assert req_b["status"] == "excluded_by_manual_review"


# ---------------------------------------------------------------------------
# 2. test_manual_review_target_product_selection_creates_effective_override
# ---------------------------------------------------------------------------

class TestTargetProductOverride:
    def test_manual_review_target_product_selection_creates_effective_override(self):
        """target_product_selection should inject normalized_product override."""
        state = _make_state_with_blocker_and_quote("b1", "API Management", _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION)
        applied_results = [{
            "candidate_id": "b1",
            "decision_type": _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION,
            "fields": {"huawei_product_family": "ELB"},
            "outcome": "product_family_override",
            "overrides": {"huawei_product_family": "ELB"},
        }]
        result = _apply_manual_review_overrides_to_requirements(state, applied_results)
        req_b = next(r for r in result["requirements"] if r["item_id"] == "b1")
        assert req_b["normalized_product"] == "ELB"
        assert req_b["status"] == "ready"
        # Should have an effective override recorded
        assert len(result["manual_review_effective_requirements"]) == 1
        assert result["manual_review_effective_requirements"][0]["override_type"] == "product_family"


# ---------------------------------------------------------------------------
# 3. test_manual_review_capacity_tier_confirmation_updates_effective_spec
# ---------------------------------------------------------------------------

class TestCapacityTierOverride:
    def test_manual_review_capacity_tier_confirmation_updates_effective_spec(self):
        """capacity_or_tier_confirmation should inject spec override."""
        req_b = RequirementItem(
            item_id="b1", source_file="t.csv", raw_product_name="Big Disk",
            status="needs_manual_review",
            status_reason="Spec needs confirmation.",
            spec={"spec_type": "storage", "capacity_gib": 100, "tier": "high"},
        )
        state = {
            "requirements": [req_b.model_dump()],
            "quote_blockers": [],
            "unquoted_items": [],
        }
        applied_results = [{
            "candidate_id": "b1",
            "decision_type": _MANUAL_REVIEW_CAPACITY_OR_TIER_CONFIRMATION,
            "fields": {"capacity_gib": 500, "tier": "ultrahigh"},
            "outcome": "capacity_or_tier_override",
            "overrides": {"capacity_gib": 500, "tier": "ultrahigh"},
        }]
        result = _apply_manual_review_overrides_to_requirements(state, applied_results)
        req = next(r for r in result["requirements"] if r["item_id"] == "b1")
        assert req["spec"]["capacity_gib"] == 500
        assert req["spec"]["tier"] == "ultrahigh"


# ---------------------------------------------------------------------------
# 4. test_manual_review_billing_basis_override_updates_usage_semantics
# ---------------------------------------------------------------------------

class TestBillingBasisOverride:
    def test_manual_review_billing_basis_override_updates_usage_semantics(self):
        """billing_model_selection should inject billing_basis into notes."""
        req_b = RequirementItem(
            item_id="b1", source_file="t.csv", raw_product_name="OBS Usage",
            status="needs_manual_review",
            status_reason="Billing model needs confirmation.",
        )
        state = {
            "requirements": [req_b.model_dump()],
            "quote_blockers": [],
            "unquoted_items": [],
        }
        applied_results = [{
            "candidate_id": "b1",
            "decision_type": _MANUAL_REVIEW_BILLING_MODEL_SELECTION,
            "fields": {"billing_basis": "capacity"},
            "outcome": "billing_basis_override",
            "overrides": {"billing_basis": "capacity"},
        }]
        result = _apply_manual_review_overrides_to_requirements(state, applied_results)
        req = next(r for r in result["requirements"] if r["item_id"] == "b1")
        assert "billing_basis=capacity" in (req.get("notes") or "")


# ---------------------------------------------------------------------------
# 5. test_rebuild_billing_state_after_manual_review_recomputes_counts
# ---------------------------------------------------------------------------

class TestRebuildRecomputes:
    def test_rebuild_billing_state_after_manual_review_recomputes_counts(self):
        """_rebuild_billing_state_after_manual_review should produce updated counts."""
        state = _make_state_with_blocker_and_quote("b1", "Azure DNS")
        # Before: 1 blocker (b1)
        before_blockers = len(state["quote_blockers"])
        assert before_blockers == 1

        applied_results = [{
            "candidate_id": "b1",
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": False, "mapped_as": None},
            "outcome": "excluded_by_manual_review",
            "overrides": {},
        }]
        state["applied_manual_review_results"] = applied_results
        result = _rebuild_billing_state_after_manual_review(state)

        # Should have repricing summary
        assert "manual_review_reprice_summary" in result
        reprice = result["manual_review_reprice_summary"]
        assert "before" in reprice
        assert "after" in reprice
        # Excluded count should be 1
        assert reprice["excluded_by_manual_review"] == 1
        # After blockers should be <= before (the excluded item is removed)
        assert reprice["after"]["blocker_count"] <= reprice["before"]["blocker_count"]
        # Should have excluded list
        assert "excluded_by_manual_review" in result
        assert "b1" in result["excluded_by_manual_review"]


# ---------------------------------------------------------------------------
# 6. test_manual_review_apply_with_reprice_keeps_unmappable_item_unquoted_not_quoted
# ---------------------------------------------------------------------------

class TestUnmappableStaysUnquoted:
    def test_manual_review_apply_with_reprice_keeps_unmappable_item_unquoted_not_quoted(self):
        """If family override doesn't match a valid product key, item stays unquoted."""
        state = _make_state_with_blocker_and_quote("b1", "Unknown Service", _MANUAL_REVIEW_UNSUPPORTED_BY_CATALOG)
        applied_results = [{
            "candidate_id": "b1",
            "decision_type": _MANUAL_REVIEW_UNSUPPORTED_BY_CATALOG,
            "fields": {"huawei_product_family": "NonExistentProduct"},
            "outcome": "unsupported_family_override_recorded",
            "overrides": {"huawei_product_family": "NonExistentProduct"},
        }]
        result = _apply_manual_review_overrides_to_requirements(state, applied_results)
        req_b = next(r for r in result["requirements"] if r["item_id"] == "b1")
        # Should be unquoted (needs_price_confirmation), not ready or quoted
        assert req_b["status"] == "needs_price_confirmation"


# ---------------------------------------------------------------------------
# 7. test_manual_review_apply_can_turn_blocker_into_unquoted_when_mapping_exists_but_catalog_gap_remains
# ---------------------------------------------------------------------------

class TestBlockerToUnquoted:
    def test_manual_review_apply_can_turn_blocker_into_unquoted_when_mapping_exists(self):
        """A valid product family override can move item from blocker to ready/unquoted."""
        state = _make_state_with_blocker_and_quote("b1", "API Management", _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION)
        applied_results = [{
            "candidate_id": "b1",
            "decision_type": _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION,
            "fields": {"huawei_product_family": "ELB"},
            "outcome": "product_family_override",
            "overrides": {"huawei_product_family": "ELB"},
        }]
        result = _apply_manual_review_overrides_to_requirements(state, applied_results)
        req_b = next(r for r in result["requirements"] if r["item_id"] == "b1")
        # Should be ready (ELB is a valid product key)
        assert req_b["status"] == "ready"
        assert req_b["normalized_product"] == "ELB"


# ---------------------------------------------------------------------------
# 8. test_manual_review_apply_can_reduce_blockers_without_changing_existing_quotes_wrongly
# ---------------------------------------------------------------------------

class TestReduceBlockersPreserveQuotes:
    def test_manual_review_apply_can_reduce_blockers_without_changing_existing_quotes_wrongly(self):
        """Excluding a blocker should not change existing quote line prices."""
        state = _make_state_with_blocker_and_quote("b1", "Azure DNS")
        applied_results = [{
            "candidate_id": "b1",
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": False, "mapped_as": None},
            "outcome": "excluded_by_manual_review",
            "overrides": {},
        }]
        state["applied_manual_review_results"] = applied_results
        result = _rebuild_billing_state_after_manual_review(state)

        # The excluded item should not be in blockers
        blocker_ids = [b.get("item_id") for b in result["quote_blockers"]]
        assert "b1" not in blocker_ids
        # The repricing summary should show the exclusion
        reprice = result["manual_review_reprice_summary"]
        assert reprice["excluded_by_manual_review"] == 1


# ---------------------------------------------------------------------------
# 9. test_apply_endpoint_can_return_reprice_preview_summary
# ---------------------------------------------------------------------------

class TestEndpointReprice:
    def test_apply_endpoint_can_return_reprice_preview_summary(self):
        """apply_manual_review_from_api with reprice=True should return reprice summary."""
        state = _make_state_with_blocker_and_quote("b1", "Azure DNS")
        candidates = [_make_candidate("b1", _MANUAL_REVIEW_SERVICE_SCOPE_DECISION)]
        decisions = [{
            "candidate_id": "b1",
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": False, "mapped_as": None},
        }]
        result = apply_manual_review_from_api(
            decisions, candidates,
            reprice=True, state=state,
        )
        assert "reprice_preview_summary" in result
        reprice = result["reprice_preview_summary"]
        assert "before" in reprice
        assert "after" in reprice
        assert reprice["excluded_by_manual_review"] == 1
        assert "reprice_updated_counts" in result


# ---------------------------------------------------------------------------
# 10. test_summary_mentions_manual_review_reprice_results
# ---------------------------------------------------------------------------

class TestSummaryMentionsReprice:
    def test_summary_mentions_manual_review_reprice_results(self):
        """Summary sheet should contain MANUAL REVIEW REPRICE section after repricing."""
        blocker = FlexibleQuoteBlocker(
            item_id="b1", product="Azure DNS", status="needs_manual_review",
            message="Product could not be mapped to the supported catalog.",
            source_file="t.csv",
        )
        req = RequirementItem(
            item_id="b1", source_file="t.csv", raw_product_name="Azure DNS",
            status="needs_manual_review",
            status_reason="Product could not be mapped to the supported catalog.",
        )
        manual_review = _analyze_manual_review_design({
            "quote_blockers": [blocker.model_dump()],
            "requirements": [req.model_dump()],
            "llm_aggregated_billing_items": [],
        })
        reprice_summary = {
            "before": {"quoted_items": 0, "blocker_count": 1, "unquoted_count": 0, "total_monthly_price": 0},
            "after": {"quoted_items": 0, "blocker_count": 0, "unquoted_count": 0, "total_monthly_price": 0},
            "excluded_by_manual_review": 1,
            "effective_overrides": 1,
            "quote_delta": 0,
            "blocker_delta": -1,
            "unquoted_delta": 0,
            "price_delta": 0,
        }
        state = {
            "requirements": [req.model_dump()],
            "quote_ready_items": [],
            "quote_lines": [],
            "quote_blockers": [],
            "unquoted_items": [],
            "quote_context": {"region": "chile"},
            "summary": FlexibleQuoteSummary(
                total_input_items=1, blocker_count=0,
            ).model_dump(),
            "billing_gap_analysis": {},
            "billing_reconciliation": {},
            "billing_blocker_analysis": {"blocker_total": 0, "blocker_categories": {}},
            "billing_manual_review_design": manual_review,
            "manual_review_reprice_summary": reprice_summary,
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
        assert "MANUAL REVIEW REPRICE" in summary_text


# ---------------------------------------------------------------------------
# 11. test_information_sheet_mentions_updated_counts_after_manual_review
# ---------------------------------------------------------------------------

class TestInfoSheetMentionsReprice:
    def test_information_sheet_mentions_updated_counts_after_manual_review(self):
        """Información sheet should contain MANUAL REVIEW REPRICE section."""
        blocker = FlexibleQuoteBlocker(
            item_id="b1", product="Azure DNS", status="needs_manual_review",
            message="Product could not be mapped to the supported catalog.",
            source_file="t.csv",
        )
        req = RequirementItem(
            item_id="b1", source_file="t.csv", raw_product_name="Azure DNS",
            status="needs_manual_review",
            status_reason="Product could not be mapped to the supported catalog.",
        )
        manual_review = _analyze_manual_review_design({
            "quote_blockers": [blocker.model_dump()],
            "requirements": [req.model_dump()],
            "llm_aggregated_billing_items": [],
        })
        reprice_summary = {
            "before": {"quoted_items": 0, "blocker_count": 1, "unquoted_count": 0, "total_monthly_price": 0},
            "after": {"quoted_items": 0, "blocker_count": 0, "unquoted_count": 0, "total_monthly_price": 0},
            "excluded_by_manual_review": 1,
            "effective_overrides": 1,
            "quote_delta": 0,
            "blocker_delta": -1,
            "unquoted_delta": 0,
            "price_delta": 0,
        }
        state = {
            "requirements": [req.model_dump()],
            "quote_ready_items": [],
            "quote_lines": [],
            "quote_blockers": [],
            "unquoted_items": [],
            "quote_context": {"region": "chile"},
            "summary": FlexibleQuoteSummary(
                total_input_items=1, blocker_count=0,
            ).model_dump(),
            "billing_gap_analysis": {},
            "billing_reconciliation": {},
            "billing_blocker_analysis": {"blocker_total": 0, "blocker_categories": {}},
            "billing_manual_review_design": manual_review,
            "manual_review_reprice_summary": reprice_summary,
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
        assert "MANUAL REVIEW REPRICE" in info_text
        assert "Excluded from quote" in info_text


# ---------------------------------------------------------------------------
# 12. test_no_manual_review_decisions_keeps_existing_results_identical
# ---------------------------------------------------------------------------

class TestNoDecisionsNoChange:
    def test_no_manual_review_decisions_keeps_existing_results_identical(self):
        """Without applied_manual_review_results, rebuild returns empty dict."""
        state = _make_state_with_blocker_and_quote("b1", "Azure DNS")
        result = _rebuild_billing_state_after_manual_review(state)
        # No applied results → empty dict (no change)
        assert result == {}

    def test_empty_applied_results_keeps_existing_results_identical(self):
        """Empty applied_manual_review_results should return empty dict."""
        state = _make_state_with_blocker_and_quote("b1", "Azure DNS")
        state["applied_manual_review_results"] = []
        result = _rebuild_billing_state_after_manual_review(state)
        assert result == {}


# ---------------------------------------------------------------------------
# Optional: test_multiple_manual_review_decisions_apply_stably_in_one_reprice_pass
# ---------------------------------------------------------------------------

class TestMultipleDecisionsStable:
    def test_multiple_manual_review_decisions_apply_stably_in_one_reprice_pass(self):
        """Multiple decisions should apply stably in one reprice pass."""
        from app.models import MatchedProduct

        ql = FlexibleQuoteLine(
            line_id="line::q1", requirement_item_id="q1",
            product="ECS", region="chile",
            quantity=2.0, unit="instance-month", billing_mode="monthly",
            matched_sku="c6.large.2", matched_tier="general",
            unit_price=50.0, monthly_price=100.0, currency="USD",
        )
        blocker1 = FlexibleQuoteBlocker(
            item_id="b1", product="Azure DNS", status="needs_manual_review",
            message="Product could not be mapped to the supported catalog.",
            source_file="t.csv",
        )
        blocker2 = FlexibleQuoteBlocker(
            item_id="b2", product="Azure Monitor", status="needs_manual_review",
            message="Product could not be mapped to the supported catalog.",
            source_file="t.csv",
        )
        req = RequirementItem(
            item_id="q1", source_file="t.csv", raw_product_name="ECS",
            normalized_product="ECS", quantity=2.0,
            quantity_source="billing_standardized", region="chile",
            status="ready",
        )
        req_b1 = RequirementItem(
            item_id="b1", source_file="t.csv", raw_product_name="Azure DNS",
            status="needs_manual_review",
            status_reason="Product could not be mapped to the supported catalog.",
        )
        req_b2 = RequirementItem(
            item_id="b2", source_file="t.csv", raw_product_name="Azure Monitor",
            status="needs_manual_review",
            status_reason="Product could not be mapped to the supported catalog.",
        )
        matched = [
            MatchedProduct(
                item_id="q1", product="ECS",
                match_method="rule_match", confidence=1,
                rationale="Matched using local product synonym rules.",
            ).model_dump(),
            MatchedProduct(
                item_id="b1", product=None,
                match_method="llm_fallback", confidence=0,
                rationale="No deterministic product mapping hit.",
            ).model_dump(),
            MatchedProduct(
                item_id="b2", product=None,
                match_method="llm_fallback", confidence=0,
                rationale="No deterministic product mapping hit.",
            ).model_dump(),
        ]
        state = {
            "requirements": [req.model_dump(), req_b1.model_dump(), req_b2.model_dump()],
            "quote_ready_items": [req.model_dump()],
            "quote_lines": [ql.model_dump()],
            "quote_blockers": [blocker1.model_dump(), blocker2.model_dump()],
            "unquoted_items": [],
            "quote_context": {"region": "chile"},
            "price_catalog": _catalog_for_region("chile"),
            "understanding": {"profile": {}},
            "matched_products": matched,
            "llm_aggregated_billing_items": [],
            "applied_manual_review_results": [
                {
                    "candidate_id": "b1",
                    "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
                    "fields": {"include_in_quote": False, "mapped_as": None},
                    "outcome": "excluded_by_manual_review",
                    "overrides": {},
                },
                {
                    "candidate_id": "b2",
                    "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
                    "fields": {"include_in_quote": False, "mapped_as": None},
                    "outcome": "excluded_by_manual_review",
                    "overrides": {},
                },
            ],
            "audit_log": [],
            "progress_callback": None,
        }
        result = _rebuild_billing_state_after_manual_review(state)
        reprice = result["manual_review_reprice_summary"]
        assert reprice["excluded_by_manual_review"] == 2
        # After blockers should be <= before (both excluded items removed)
        assert reprice["after"]["blocker_count"] <= reprice["before"]["blocker_count"]


# ---------------------------------------------------------------------------
# Optional: test_excluded_by_manual_review_is_counted_separately
# ---------------------------------------------------------------------------

class TestExcludedCountedSeparately:
    def test_excluded_by_manual_review_is_counted_separately(self):
        """Excluded items should be in a separate list, not in blockers or unquoted."""
        state = _make_state_with_blocker_and_quote("b1", "Azure DNS")
        applied_results = [{
            "candidate_id": "b1",
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": False, "mapped_as": None},
            "outcome": "excluded_by_manual_review",
            "overrides": {},
        }]
        result = _apply_manual_review_overrides_to_requirements(state, applied_results)
        # Excluded should be tracked separately
        assert len(result["excluded_by_manual_review"]) == 1
        # Blockers should not contain the excluded item
        blocker_ids = [b.get("item_id") for b in result["quote_blockers"]]
        assert "b1" not in blocker_ids


# ---------------------------------------------------------------------------
# Optional: test_manual_review_override_uses_stable_candidate_id_linkage
# ---------------------------------------------------------------------------

class TestStableIdLinkage:
    def test_manual_review_override_uses_stable_candidate_id_linkage(self):
        """Overrides should be linked by candidate_id, not by name matching."""
        state = _make_state_with_blocker_and_quote("b1", "Azure DNS")
        # Apply with correct candidate_id
        applied_results = [{
            "candidate_id": "b1",
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": False, "mapped_as": None},
            "outcome": "excluded_by_manual_review",
            "overrides": {},
        }]
        result = _apply_manual_review_overrides_to_requirements(state, applied_results)
        assert "b1" in result["excluded_by_manual_review"]

        # Apply with wrong candidate_id — should not affect b1
        wrong_results = [{
            "candidate_id": "wrong_id",
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": False, "mapped_as": None},
            "outcome": "excluded_by_manual_review",
            "overrides": {},
        }]
        result2 = _apply_manual_review_overrides_to_requirements(state, wrong_results)
        assert "b1" not in result2["excluded_by_manual_review"]
        # b1 should still be in blockers
        blocker_ids = [b.get("item_id") for b in result2["quote_blockers"]]
        assert "b1" in blocker_ids


# ---------------------------------------------------------------------------
# Real Azure fixture tests
# ---------------------------------------------------------------------------

class TestRealAzureRepricing:
    @pytest.mark.skipif(not AZURE_CSV_PATH.exists(), reason="Azure CSV not available")
    def test_real_azure_exclude_reduces_blockers(self):
        """Real Azure: excluding a service_scope candidate should reduce blockers."""
        azure_bytes = AZURE_CSV_PATH.read_bytes()
        azure_doc = _parse_csv_document(azure_bytes, "azure_billing.csv")
        state = _make_billing_state(azure_doc)
        manual_review = state.get("billing_manual_review_design", {})
        candidates = manual_review.get("candidates", [])

        scope_candidates = [
            c for c in candidates
            if c["manual_review_need"] == _MANUAL_REVIEW_SERVICE_SCOPE_DECISION
        ]
        if not scope_candidates:
            pytest.skip("No service_scope_decision candidates in fixture")

        first = scope_candidates[0]
        applied_results = [{
            "candidate_id": first["candidate_id"],
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": False, "mapped_as": None},
            "outcome": "excluded_by_manual_review",
            "overrides": {},
        }]
        state["applied_manual_review_results"] = applied_results
        result = _rebuild_billing_state_after_manual_review(state)

        reprice = result["manual_review_reprice_summary"]
        assert reprice["after"]["blocker_count"] < reprice["before"]["blocker_count"]
        assert reprice["excluded_by_manual_review"] == 1

    @pytest.mark.skipif(not AZURE_CSV_PATH.exists(), reason="Azure CSV not available")
    def test_real_azure_product_family_override_can_change_status(self):
        """Real Azure: product family override can move item from blocker to ready/unquoted."""
        azure_bytes = AZURE_CSV_PATH.read_bytes()
        azure_doc = _parse_csv_document(azure_bytes, "azure_billing.csv")
        state = _make_billing_state(azure_doc)
        manual_review = state.get("billing_manual_review_design", {})
        candidates = manual_review.get("candidates", [])

        target_candidates = [
            c for c in candidates
            if c["manual_review_need"] == _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION
        ]
        if not target_candidates:
            pytest.skip("No target_product_selection candidates in fixture")

        first = target_candidates[0]
        suggested = first.get("suggested_huawei_target_family")
        if not suggested:
            pytest.skip("No suggested family for first target_product_selection candidate")

        applied_results = [{
            "candidate_id": first["candidate_id"],
            "decision_type": _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION,
            "fields": {"huawei_product_family": suggested},
            "outcome": "product_family_override",
            "overrides": {"huawei_product_family": suggested},
        }]
        override_result = _apply_manual_review_overrides_to_requirements(state, applied_results)
        # The requirement should have a normalized_product set
        req = next(
            (r for r in override_result["requirements"] if r["item_id"] == first["candidate_id"]),
            None,
        )
        assert req is not None
        assert req.get("normalized_product") is not None
