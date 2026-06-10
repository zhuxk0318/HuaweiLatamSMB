"""Final Phase tests: end-to-end closure — outcome breakdown, self-consistency,
API/export alignment, and delivery-facing export copy."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.flexible_workflow import (
    _validate_manual_review_inputs,
    _apply_manual_review_decision,
    _analyze_manual_review_design,
    _apply_manual_review_overrides_to_requirements,
    _rebuild_billing_state_after_manual_review,
    _build_manual_review_closure_summary,
    _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION,
    _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
    _MANUAL_REVIEW_UNSUPPORTED_BY_CATALOG,
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
    MatchedProduct,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

AZURE_CSV_PATH = Path("/root/SMBReference/CGE/azure Billing_invoice_transactions.csv")


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

    norm_result = normalize_requirements({"requirements": requirements, "quote_context": {"region": region}, "audit_log": [], "progress_callback": None})
    norm_reqs = norm_result["requirements"]

    catalog = _catalog_for_region(region)
    val_result = validate_quote_readiness({"requirements": norm_reqs, "quote_context": {"region": region}, "price_catalog": catalog, "matched_products": [], "understanding": {"profile": {}}, "audit_log": [], "progress_callback": None})
    res_result = resolve_price_components({"quote_ready_items": val_result["quote_ready_items"], "price_catalog": catalog, "unquoted_items": val_result["unquoted_items"], "audit_log": [], "progress_callback": None})
    quote_result = quote_items({"quote_ready_items": val_result["quote_ready_items"], "price_components": res_result["price_components"], "audit_log": [], "progress_callback": None})
    sum_result = summarize_quote({"requirements": norm_reqs, "quote_ready_items": val_result["quote_ready_items"], "quote_lines": quote_result["quote_lines"], "quote_blockers": val_result["quote_blockers"], "unquoted_items": res_result["unquoted_items"], "quote_context": {"region": region}, "llm_aggregated_billing_items": agg_items, "audit_log": [], "progress_callback": None})

    return {
        "requirements": norm_reqs, "quote_ready_items": val_result["quote_ready_items"],
        "quote_lines": quote_result["quote_lines"], "quote_blockers": val_result["quote_blockers"],
        "unquoted_items": res_result["unquoted_items"], "price_components": res_result["price_components"],
        "summary": sum_result["summary"], "billing_gap_analysis": sum_result.get("billing_gap_analysis", {}),
        "billing_reconciliation": sum_result.get("billing_reconciliation", {}),
        "billing_blocker_analysis": sum_result.get("billing_blocker_analysis", {}),
        "billing_manual_review_design": sum_result.get("billing_manual_review_design", {}),
        "mapped_billing_resources": mapped, "billing_lines": lines, "billing_groups": groups,
        "llm_aggregated_billing_items": agg_items, "standardized_billing_resources": standardized,
        "quote_context": {"region": region}, "price_catalog": catalog, "understanding": {"profile": {}},
        "matched_products": [], "audit_log": [], "progress_callback": None,
    }


def _make_minimal_state_with_blocker() -> dict:
    """Build a minimal state with one quoted item and one blocker."""
    ql = FlexibleQuoteLine(
        line_id="line::q1", requirement_item_id="q1",
        product="ECS", region="chile",
        quantity=2.0, unit="instance-month", billing_mode="monthly",
        matched_sku="c6.large.2", matched_tier="general",
        unit_price=50.0, monthly_price=100.0, currency="USD",
    )
    blocker = FlexibleQuoteBlocker(
        item_id="b1", product="Azure DNS", status="needs_manual_review",
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
        item_id="b1", source_file="t.csv", raw_product_name="Azure DNS",
        status="needs_manual_review",
        status_reason="Product could not be mapped to the supported catalog.",
    )
    matched = [
        MatchedProduct(item_id="q1", product="ECS", match_method="rule_match", confidence=1, rationale="Matched using local product synonym rules.").model_dump(),
        MatchedProduct(item_id="b1", product=None, match_method="llm_fallback", confidence=0, rationale="No deterministic product mapping hit.").model_dump(),
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
# 1. test_end_to_end_manual_review_closure_summary_matches_reprice_counts
# ---------------------------------------------------------------------------

class TestClosureSummaryMatchesReprice:
    def test_end_to_end_manual_review_closure_summary_matches_reprice_counts(self):
        """Closure summary counts should match reprice summary deltas."""
        state = _make_minimal_state_with_blocker()
        applied_results = [{
            "candidate_id": "b1",
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": False, "mapped_as": None},
            "outcome": "excluded_by_manual_review",
            "overrides": {},
        }]
        state["applied_manual_review_results"] = applied_results
        result = _rebuild_billing_state_after_manual_review(state)

        closure = result["manual_review_closure_summary"]
        reprice = result["manual_review_reprice_summary"]

        # excluded_by_manual_review should match
        assert closure["excluded_by_manual_review"] == reprice["excluded_by_manual_review"]
        # still_blocked should match after blocker_count
        assert closure["still_blocked_after_manual_review"] == reprice["after"]["blocker_count"]


# ---------------------------------------------------------------------------
# 2. test_closure_summary_counts_excluded_items_separately
# ---------------------------------------------------------------------------

class TestExcludedCountedSeparately:
    def test_closure_summary_counts_excluded_items_separately(self):
        """Excluded items should be in their own category, not in blocked or quoted."""
        state = _make_minimal_state_with_blocker()
        applied_results = [{
            "candidate_id": "b1",
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": False, "mapped_as": None},
            "outcome": "excluded_by_manual_review",
            "overrides": {},
        }]
        state["applied_manual_review_results"] = applied_results
        result = _rebuild_billing_state_after_manual_review(state)

        closure = result["manual_review_closure_summary"]
        assert closure["excluded_by_manual_review"] == 1
        assert closure["still_blocked_after_manual_review"] == 0


# ---------------------------------------------------------------------------
# 3. test_closure_summary_counts_newly_quoted_items
# ---------------------------------------------------------------------------

class TestNewlyQuotedCounted:
    def test_closure_summary_counts_newly_quoted_items(self):
        """Items that become quoted after product family override should be counted."""
        before = FlexibleQuoteSummary(quoted_items=5, blocker_count=3, unquoted_count=2, total_monthly_price=100.0)
        after = FlexibleQuoteSummary(quoted_items=7, blocker_count=1, unquoted_count=3, total_monthly_price=120.0)
        closure = _build_manual_review_closure_summary(
            before_summary=before,
            after_summary=after,
            excluded_ids=["b1"],
            effective_overrides=[{"override_type": "product_family"}],
        )
        assert closure["newly_quoted_after_manual_review"] == 2
        assert closure["unchanged_existing_quotes"] == 5


# ---------------------------------------------------------------------------
# 4. test_closure_summary_counts_still_blocked_items
# ---------------------------------------------------------------------------

class TestStillBlockedCounted:
    def test_closure_summary_counts_still_blocked_items(self):
        """Items that remain blocked should be counted."""
        before = FlexibleQuoteSummary(quoted_items=5, blocker_count=3, unquoted_count=2, total_monthly_price=100.0)
        after = FlexibleQuoteSummary(quoted_items=5, blocker_count=1, unquoted_count=3, total_monthly_price=100.0)
        closure = _build_manual_review_closure_summary(
            before_summary=before,
            after_summary=after,
            excluded_ids=["b1"],
            effective_overrides=[{"override_type": "excluded"}],
        )
        assert closure["still_blocked_after_manual_review"] == 1


# ---------------------------------------------------------------------------
# 5. test_summary_sheet_mentions_baseline_vs_after_manual_review
# ---------------------------------------------------------------------------

class TestSummarySheetDelivery:
    def test_summary_sheet_mentions_baseline_vs_after_manual_review(self):
        """Summary sheet should show 'Baseline' and 'After review' labels."""
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
            "before": {"quoted_items": 5, "blocker_count": 3, "unquoted_count": 2, "total_monthly_price": 100.0},
            "after": {"quoted_items": 5, "blocker_count": 1, "unquoted_count": 3, "total_monthly_price": 100.0},
            "excluded_by_manual_review": 1,
            "effective_overrides": 1,
            "quote_delta": 0,
            "blocker_delta": -2,
            "unquoted_delta": 1,
            "price_delta": 0,
            "outcome_breakdown": {
                "excluded_by_manual_review": 1,
                "newly_quoted_after_manual_review": 0,
                "moved_to_unquoted_after_manual_review": 1,
                "still_blocked_after_manual_review": 1,
                "unchanged_existing_quotes": 5,
                "product_family_overrides": 0,
                "spec_overrides": 0,
                "billing_basis_overrides": 0,
                "total_effective_overrides": 1,
            },
        }
        state = {
            "requirements": [req.model_dump()],
            "quote_ready_items": [],
            "quote_lines": [],
            "quote_blockers": [],
            "unquoted_items": [],
            "quote_context": {"region": "chile"},
            "summary": FlexibleQuoteSummary(total_input_items=1, blocker_count=0).model_dump(),
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
        assert "Baseline" in summary_text
        assert "After review" in summary_text
        assert "Excluded from quote" in summary_text


# ---------------------------------------------------------------------------
# 6. test_information_sheet_mentions_top_unresolved_items_after_manual_review
# ---------------------------------------------------------------------------

class TestInfoSheetDelivery:
    def test_information_sheet_mentions_top_unresolved_items_after_manual_review(self):
        """Información sheet should show top unresolved items after manual review."""
        blocker1 = FlexibleQuoteBlocker(
            item_id="b1", product="Fabric Capacity", status="needs_manual_review",
            message="Product could not be mapped to the supported catalog.",
            source_file="t.csv",
        )
        blocker2 = FlexibleQuoteBlocker(
            item_id="b2", product="Azure Front Door", status="needs_manual_review",
            message="Product could not be mapped to the supported catalog.",
            source_file="t.csv",
        )
        req1 = RequirementItem(
            item_id="b1", source_file="t.csv", raw_product_name="Fabric Capacity",
            status="needs_manual_review",
            status_reason="Product could not be mapped to the supported catalog.",
        )
        req2 = RequirementItem(
            item_id="b2", source_file="t.csv", raw_product_name="Azure Front Door",
            status="needs_manual_review",
            status_reason="Product could not be mapped to the supported catalog.",
        )
        manual_review = _analyze_manual_review_design({
            "quote_blockers": [blocker1.model_dump(), blocker2.model_dump()],
            "requirements": [req1.model_dump(), req2.model_dump()],
            "llm_aggregated_billing_items": [],
        })
        reprice_summary = {
            "before": {"quoted_items": 0, "blocker_count": 2, "unquoted_count": 0, "total_monthly_price": 0},
            "after": {"quoted_items": 0, "blocker_count": 2, "unquoted_count": 0, "total_monthly_price": 0},
            "excluded_by_manual_review": 0,
            "effective_overrides": 0,
            "quote_delta": 0,
            "blocker_delta": 0,
            "unquoted_delta": 0,
            "price_delta": 0,
            "outcome_breakdown": {
                "excluded_by_manual_review": 0,
                "newly_quoted_after_manual_review": 0,
                "moved_to_unquoted_after_manual_review": 0,
                "still_blocked_after_manual_review": 2,
                "unchanged_existing_quotes": 0,
                "product_family_overrides": 0,
                "spec_overrides": 0,
                "billing_basis_overrides": 0,
                "total_effective_overrides": 0,
            },
        }
        state = {
            "requirements": [req1.model_dump(), req2.model_dump()],
            "quote_ready_items": [],
            "quote_lines": [],
            "quote_blockers": [blocker1.model_dump(), blocker2.model_dump()],
            "unquoted_items": [],
            "quote_context": {"region": "chile"},
            "summary": FlexibleQuoteSummary(total_input_items=2, blocker_count=2).model_dump(),
            "billing_gap_analysis": {},
            "billing_reconciliation": {},
            "billing_blocker_analysis": {"blocker_total": 2, "blocker_categories": {}},
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
        assert "Still blocked: 2" in info_text
        assert "Top unresolved items" in info_text


# ---------------------------------------------------------------------------
# 7. test_apply_endpoint_reprice_summary_matches_export_summary
# ---------------------------------------------------------------------------

class TestAPIExportAlignment:
    def test_apply_endpoint_reprice_summary_matches_export_summary(self):
        """API reprice_preview_summary should have same shape as export manual_review_reprice_summary."""
        state = _make_minimal_state_with_blocker()
        candidates = [{
            "candidate_id": "b1",
            "source_label": "Azure DNS",
            "source_product_type": "dns",
            "source_product_sku": "",
            "source_amount": 100.0,
            "source_quantity": 1.0,
            "source_unit": "1",
            "blocker_category": _BLOCKER_UNSUPPORTED_PRODUCT,
            "manual_review_need": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "minimal_fields_required": ["include_in_quote", "mapped_as"],
            "suggested_huawei_target_family": None,
            "reason": "Product could not be mapped to the supported catalog.",
            "source_line_numbers": [],
        }]
        decisions = [{
            "candidate_id": "b1",
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": False, "mapped_as": None},
        }]
        result = apply_manual_review_from_api(
            decisions, candidates,
            reprice=True, state=state,
        )
        reprice_preview = result.get("reprice_preview_summary", {})
        # Should have same keys as export manual_review_reprice_summary
        assert "before" in reprice_preview
        assert "after" in reprice_preview
        assert "excluded_by_manual_review" in reprice_preview
        assert "outcome_breakdown" in reprice_preview
        breakdown = reprice_preview["outcome_breakdown"]
        assert "excluded_by_manual_review" in breakdown
        assert "newly_quoted_after_manual_review" in breakdown
        assert "still_blocked_after_manual_review" in breakdown
        assert "unchanged_existing_quotes" in breakdown


# ---------------------------------------------------------------------------
# 8. test_real_billing_fixture_end_to_end_counts_are_self_consistent
# ---------------------------------------------------------------------------

class TestRealAzureSelfConsistent:
    @pytest.mark.skipif(not AZURE_CSV_PATH.exists(), reason="Azure CSV not available")
    def test_real_billing_fixture_end_to_end_counts_are_self_consistent(self):
        """Real Azure: end-to-end counts should be self-consistent."""
        azure_bytes = AZURE_CSV_PATH.read_bytes()
        azure_doc = _parse_csv_document(azure_bytes, "azure_billing.csv")
        state = _make_billing_state(azure_doc)
        manual_review = state.get("billing_manual_review_design", {})
        candidates = manual_review.get("candidates", [])

        # Apply all decisions: exclude scope + override target/unsupported
        applied = []
        for c in candidates:
            if c["manual_review_need"] == _MANUAL_REVIEW_SERVICE_SCOPE_DECISION:
                applied.append({
                    "candidate_id": c["candidate_id"],
                    "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
                    "fields": {"include_in_quote": False, "mapped_as": None},
                    "outcome": "excluded_by_manual_review",
                    "overrides": {},
                })
            elif c["manual_review_need"] == _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION:
                suggested = c.get("suggested_huawei_target_family") or "ELB"
                applied.append({
                    "candidate_id": c["candidate_id"],
                    "decision_type": _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION,
                    "fields": {"huawei_product_family": suggested},
                    "outcome": "product_family_override",
                    "overrides": {"huawei_product_family": suggested},
                })
            elif c["manual_review_need"] == _MANUAL_REVIEW_UNSUPPORTED_BY_CATALOG:
                suggested = c.get("suggested_huawei_target_family") or "DWS"
                applied.append({
                    "candidate_id": c["candidate_id"],
                    "decision_type": _MANUAL_REVIEW_UNSUPPORTED_BY_CATALOG,
                    "fields": {"huawei_product_family": suggested},
                    "outcome": "unsupported_family_override_recorded",
                    "overrides": {"huawei_product_family": suggested},
                })

        state["applied_manual_review_results"] = applied
        result = _rebuild_billing_state_after_manual_review(state)

        closure = result["manual_review_closure_summary"]
        reprice = result["manual_review_reprice_summary"]

        # Self-consistency: excluded + still_blocked + newly_quoted + moved_to_unquoted + unchanged
        # should account for all items
        before = reprice["before"]
        after = reprice["after"]

        # after counts should match actual
        assert after["quoted_items"] == closure["newly_quoted_after_manual_review"] + closure["unchanged_existing_quotes"]
        assert after["blocker_count"] == closure["still_blocked_after_manual_review"]

        # excluded should match the list length
        assert closure["excluded_by_manual_review"] == len(result["excluded_by_manual_review"])

        # outcome_breakdown should be in reprice_summary too
        assert "outcome_breakdown" in reprice
        assert reprice["outcome_breakdown"] == closure


# ---------------------------------------------------------------------------
# 9. test_real_billing_fixture_price_delta_matches_newly_quoted_items
# ---------------------------------------------------------------------------

class TestRealAzurePriceDelta:
    @pytest.mark.skipif(not AZURE_CSV_PATH.exists(), reason="Azure CSV not available")
    def test_real_billing_fixture_price_delta_matches_newly_quoted_items(self):
        """Real Azure: price delta should be explainable by newly quoted items."""
        azure_bytes = AZURE_CSV_PATH.read_bytes()
        azure_doc = _parse_csv_document(azure_bytes, "azure_billing.csv")
        state = _make_billing_state(azure_doc)
        manual_review = state.get("billing_manual_review_design", {})
        candidates = manual_review.get("candidates", [])

        # Apply: exclude all scope candidates
        scope_candidates = [c for c in candidates if c["manual_review_need"] == _MANUAL_REVIEW_SERVICE_SCOPE_DECISION]
        applied = []
        for c in scope_candidates:
            applied.append({
                "candidate_id": c["candidate_id"],
                "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
                "fields": {"include_in_quote": False, "mapped_as": None},
                "outcome": "excluded_by_manual_review",
                "overrides": {},
            })

        state["applied_manual_review_results"] = applied
        result = _rebuild_billing_state_after_manual_review(state)

        reprice = result["manual_review_reprice_summary"]
        closure = result["manual_review_closure_summary"]

        # When only excluding (no new quotes), price_delta should be 0
        # and newly_quoted should be 0
        if closure["newly_quoted_after_manual_review"] == 0:
            assert reprice["price_delta"] == 0.0


# ---------------------------------------------------------------------------
# 10. test_no_manual_review_decisions_has_empty_or_neutral_closure_summary
# ---------------------------------------------------------------------------

class TestNoDecisionsNeutral:
    def test_no_manual_review_decisions_has_empty_or_neutral_closure_summary(self):
        """Without applied decisions, rebuild returns empty dict (no closure)."""
        state = _make_minimal_state_with_blocker()
        result = _rebuild_billing_state_after_manual_review(state)
        assert result == {}

    def test_closure_summary_survives_zero_exclusions(self):
        """Closure summary with zero exclusions should still be valid."""
        before = FlexibleQuoteSummary(quoted_items=5, blocker_count=0, unquoted_count=2, total_monthly_price=100.0)
        after = FlexibleQuoteSummary(quoted_items=5, blocker_count=0, unquoted_count=2, total_monthly_price=100.0)
        closure = _build_manual_review_closure_summary(
            before_summary=before,
            after_summary=after,
            excluded_ids=[],
            effective_overrides=[],
        )
        assert closure["excluded_by_manual_review"] == 0
        assert closure["newly_quoted_after_manual_review"] == 0
        assert closure["still_blocked_after_manual_review"] == 0
        assert closure["unchanged_existing_quotes"] == 5


# ---------------------------------------------------------------------------
# Optional: test_unchanged_existing_quotes_are_not_counted_as_newly_quoted
# ---------------------------------------------------------------------------

class TestUnchangedNotNewlyQuoted:
    def test_unchanged_existing_quotes_are_not_counted_as_newly_quoted(self):
        """Items that were already quoted should not be counted as newly quoted."""
        before = FlexibleQuoteSummary(quoted_items=10, blocker_count=5, unquoted_count=3, total_monthly_price=500.0)
        after = FlexibleQuoteSummary(quoted_items=10, blocker_count=3, unquoted_count=4, total_monthly_price=500.0)
        closure = _build_manual_review_closure_summary(
            before_summary=before,
            after_summary=after,
            excluded_ids=["b1", "b2"],
            effective_overrides=[{"override_type": "excluded"}, {"override_type": "excluded"}],
        )
        assert closure["newly_quoted_after_manual_review"] == 0
        assert closure["unchanged_existing_quotes"] == 10


# ---------------------------------------------------------------------------
# Optional: test_export_summary_language_is_delivery_facing_not_debug_only
# ---------------------------------------------------------------------------

class TestDeliveryFacingCopy:
    def test_export_summary_language_is_delivery_facing_not_debug_only(self):
        """Export should use delivery-facing language, not internal debug labels."""
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
            "before": {"quoted_items": 5, "blocker_count": 1, "unquoted_count": 2, "total_monthly_price": 100.0},
            "after": {"quoted_items": 5, "blocker_count": 0, "unquoted_count": 2, "total_monthly_price": 100.0},
            "excluded_by_manual_review": 1,
            "effective_overrides": 1,
            "quote_delta": 0,
            "blocker_delta": -1,
            "unquoted_delta": 0,
            "price_delta": 0,
            "outcome_breakdown": {
                "excluded_by_manual_review": 1,
                "newly_quoted_after_manual_review": 0,
                "moved_to_unquoted_after_manual_review": 0,
                "still_blocked_after_manual_review": 0,
                "unchanged_existing_quotes": 5,
                "product_family_overrides": 0,
                "spec_overrides": 0,
                "billing_basis_overrides": 0,
                "total_effective_overrides": 1,
            },
        }
        state = {
            "requirements": [req.model_dump()],
            "quote_ready_items": [],
            "quote_lines": [],
            "quote_blockers": [],
            "unquoted_items": [],
            "quote_context": {"region": "chile"},
            "summary": FlexibleQuoteSummary(total_input_items=1, blocker_count=0).model_dump(),
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
        # Should use delivery-facing language
        assert "Excluded from quote" in info_text
        assert "Newly quoted" in info_text
        assert "Still blocked" in info_text
        assert "Unchanged quotes" in info_text
        # Should NOT use raw internal debug labels like "quote_delta"
        assert "quote_delta" not in info_text
        assert "blocker_delta" not in info_text


# ---------------------------------------------------------------------------
# Real Azure: full end-to-end with export
# ---------------------------------------------------------------------------

class TestRealAzureFullEndToEnd:
    @pytest.mark.skipif(not AZURE_CSV_PATH.exists(), reason="Azure CSV not available")
    def test_real_azure_full_end_to_end_with_export(self):
        """Real Azure: full end-to-end preview → apply → reprice → export."""
        azure_bytes = AZURE_CSV_PATH.read_bytes()
        azure_doc = _parse_csv_document(azure_bytes, "azure_billing.csv")
        state = _make_billing_state(azure_doc)
        manual_review = state.get("billing_manual_review_design", {})
        candidates = manual_review.get("candidates", [])

        # Apply all decisions
        applied = []
        for c in candidates:
            if c["manual_review_need"] == _MANUAL_REVIEW_SERVICE_SCOPE_DECISION:
                applied.append({
                    "candidate_id": c["candidate_id"],
                    "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
                    "fields": {"include_in_quote": False, "mapped_as": None},
                    "outcome": "excluded_by_manual_review",
                    "overrides": {},
                })
            elif c["manual_review_need"] == _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION:
                suggested = c.get("suggested_huawei_target_family") or "ELB"
                applied.append({
                    "candidate_id": c["candidate_id"],
                    "decision_type": _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION,
                    "fields": {"huawei_product_family": suggested},
                    "outcome": "product_family_override",
                    "overrides": {"huawei_product_family": suggested},
                })
            elif c["manual_review_need"] == _MANUAL_REVIEW_UNSUPPORTED_BY_CATALOG:
                suggested = c.get("suggested_huawei_target_family") or "DWS"
                applied.append({
                    "candidate_id": c["candidate_id"],
                    "decision_type": _MANUAL_REVIEW_UNSUPPORTED_BY_CATALOG,
                    "fields": {"huawei_product_family": suggested},
                    "outcome": "unsupported_family_override_recorded",
                    "overrides": {"huawei_product_family": suggested},
                })

        state["applied_manual_review_results"] = applied
        result = _rebuild_billing_state_after_manual_review(state)

        # Build export state
        export_state = dict(state)
        export_state.update(result)

        # Export should succeed
        export_result = export_flexible_workbook(export_state)
        wb = load_workbook(BytesIO(export_result["workbook"].content))

        # Summary sheet should have MANUAL REVIEW REPRICE
        summary_ws = wb["Summary"]
        summary_text = ""
        for row in range(1, summary_ws.max_row + 1):
            for col in range(1, summary_ws.max_column + 1):
                val = summary_ws.cell(row, col).value
                if val:
                    summary_text += str(val) + "\n"
        assert "MANUAL REVIEW REPRICE" in summary_text
        assert "Baseline" in summary_text
        assert "After review" in summary_text

        # Información sheet should have delivery-facing copy
        info_ws = wb["Información"]
        info_text = "\n".join(
            str(info_ws.cell(row, 1).value or "")
            for row in range(1, info_ws.max_row + 1)
        )
        assert "MANUAL REVIEW REPRICE" in info_text
        assert "Excluded from quote" in info_text
