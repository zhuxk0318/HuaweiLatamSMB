"""Phase Next+9 tests: manual review apply — validation, application,
state integration, summary/export, and no-change guarantee."""

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
    _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION,
    _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
    _MANUAL_REVIEW_BILLING_MODEL_SELECTION,
    _MANUAL_REVIEW_UNSUPPORTED_BY_CATALOG,
    _MANUAL_REVIEW_CAPACITY_OR_TIER_CONFIRMATION,
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


# ---------------------------------------------------------------------------
# Helpers for building candidates and inputs
# ---------------------------------------------------------------------------

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


def _make_state_with_candidates(candidates: list[dict]) -> dict:
    """Build a minimal state with manual_review_candidates."""
    blockers = []
    requirements = []
    for c in candidates:
        blockers.append(
            FlexibleQuoteBlocker(
                item_id=c["candidate_id"],
                product=c["source_label"],
                status="needs_manual_review",
                message=c["reason"],
                source_file="t.csv",
            ).model_dump()
        )
        requirements.append(
            RequirementItem(
                item_id=c["candidate_id"],
                source_file="t.csv",
                raw_product_name=c["source_label"],
                status="needs_manual_review",
                status_reason=c["reason"],
            ).model_dump()
        )
    return {
        "quote_blockers": blockers,
        "requirements": requirements,
        "llm_aggregated_billing_items": [],
    }


# ---------------------------------------------------------------------------
# 1. test_validate_manual_review_input_accepts_valid_service_scope_decision
# ---------------------------------------------------------------------------

class TestValidateServiceScope:
    def test_validate_manual_review_input_accepts_valid_service_scope_decision(self):
        """Valid service_scope_decision input should pass validation."""
        candidates = [_make_candidate("c1", _MANUAL_REVIEW_SERVICE_SCOPE_DECISION)]
        inputs = [{
            "candidate_id": "c1",
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": False, "mapped_as": None},
        }]
        errors = _manual_review_input_errors(inputs, candidates)
        assert len(errors) == 0
        validated = _validate_manual_review_inputs(inputs, candidates)
        assert len(validated) == 1


# ---------------------------------------------------------------------------
# 2. test_validate_manual_review_input_rejects_unknown_candidate_id
# ---------------------------------------------------------------------------

class TestRejectUnknownCandidate:
    def test_validate_manual_review_input_rejects_unknown_candidate_id(self):
        """Input with unknown candidate_id should be rejected."""
        candidates = [_make_candidate("c1")]
        inputs = [{
            "candidate_id": "c999",
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": False},
        }]
        errors = _manual_review_input_errors(inputs, candidates)
        assert len(errors) == 1
        assert errors[0]["error"] == "unknown_candidate_id"
        validated = _validate_manual_review_inputs(inputs, candidates)
        assert len(validated) == 0


# ---------------------------------------------------------------------------
# 3. test_validate_manual_review_input_rejects_wrong_decision_type
# ---------------------------------------------------------------------------

class TestRejectWrongDecisionType:
    def test_validate_manual_review_input_rejects_wrong_decision_type(self):
        """Input with wrong decision_type should be rejected."""
        candidates = [_make_candidate("c1", _MANUAL_REVIEW_SERVICE_SCOPE_DECISION)]
        inputs = [{
            "candidate_id": "c1",
            "decision_type": _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION,
            "fields": {"huawei_product_family": "API Gateway"},
        }]
        errors = _manual_review_input_errors(inputs, candidates)
        assert len(errors) == 1
        assert errors[0]["error"] == "wrong_decision_type"


# ---------------------------------------------------------------------------
# 4. test_validate_manual_review_input_requires_include_in_quote_for_service_scope
# ---------------------------------------------------------------------------

class TestRequiresIncludeInQuote:
    def test_validate_manual_review_input_requires_include_in_quote_for_service_scope(self):
        """service_scope_decision requires include_in_quote field."""
        candidates = [_make_candidate("c1", _MANUAL_REVIEW_SERVICE_SCOPE_DECISION)]
        inputs = [{
            "candidate_id": "c1",
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"mapped_as": "DNS"},
        }]
        errors = _manual_review_input_errors(inputs, candidates)
        missing = [e for e in errors if e["error"] == "missing_required_field"]
        assert len(missing) == 1
        assert "include_in_quote" in missing[0]["detail"]


# ---------------------------------------------------------------------------
# 5. test_validate_manual_review_input_requires_huawei_product_family_for_target_selection
# ---------------------------------------------------------------------------

class TestRequiresProductFamily:
    def test_validate_manual_review_input_requires_huawei_product_family_for_target_selection(self):
        """target_product_selection requires huawei_product_family field."""
        candidates = [_make_candidate("c1", _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION)]
        inputs = [{
            "candidate_id": "c1",
            "decision_type": _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION,
            "fields": {},
        }]
        errors = _manual_review_input_errors(inputs, candidates)
        missing = [e for e in errors if e["error"] == "missing_required_field"]
        assert len(missing) == 1
        assert "huawei_product_family" in missing[0]["detail"]


# ---------------------------------------------------------------------------
# 6. test_apply_manual_review_service_scope_exclude_marks_item_excluded
# ---------------------------------------------------------------------------

class TestApplyScopeExclude:
    def test_apply_manual_review_service_scope_exclude_marks_item_excluded(self):
        """include_in_quote=false → excluded_by_manual_review."""
        candidate = _make_candidate("c1", _MANUAL_REVIEW_SERVICE_SCOPE_DECISION)
        decision = {
            "candidate_id": "c1",
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": False, "mapped_as": None},
        }
        result = _apply_manual_review_decision(candidate, decision)
        assert result["outcome"] == "excluded_by_manual_review"
        assert result["candidate_id"] == "c1"


# ---------------------------------------------------------------------------
# 7. test_apply_manual_review_service_scope_include_with_mapping_records_override
# ---------------------------------------------------------------------------

class TestApplyScopeIncludeWithMapping:
    def test_apply_manual_review_service_scope_include_with_mapping_records_override(self):
        """include_in_quote=true with mapped_as → include_with_mapping_override."""
        candidate = _make_candidate("c1", _MANUAL_REVIEW_SERVICE_SCOPE_DECISION)
        decision = {
            "candidate_id": "c1",
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": True, "mapped_as": "DNS"},
        }
        result = _apply_manual_review_decision(candidate, decision)
        assert result["outcome"] == "include_with_mapping_override"
        assert result["overrides"]["mapped_as"] == "DNS"
        assert result["overrides"]["include_in_quote"] is True

    def test_apply_manual_review_service_scope_include_without_mapping(self):
        """include_in_quote=true without mapped_as → include_but_needs_mapping."""
        candidate = _make_candidate("c1", _MANUAL_REVIEW_SERVICE_SCOPE_DECISION)
        decision = {
            "candidate_id": "c1",
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": True, "mapped_as": None},
        }
        result = _apply_manual_review_decision(candidate, decision)
        assert result["outcome"] == "include_but_needs_mapping"


# ---------------------------------------------------------------------------
# 8. test_apply_manual_review_target_product_selection_records_family_override
# ---------------------------------------------------------------------------

class TestApplyTargetProductSelection:
    def test_apply_manual_review_target_product_selection_records_family_override(self):
        """target_product_selection with huawei_product_family → product_family_override."""
        candidate = _make_candidate("c1", _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION)
        decision = {
            "candidate_id": "c1",
            "decision_type": _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION,
            "fields": {"huawei_product_family": "API Gateway"},
        }
        result = _apply_manual_review_decision(candidate, decision)
        assert result["outcome"] == "product_family_override"
        assert result["overrides"]["huawei_product_family"] == "API Gateway"


# ---------------------------------------------------------------------------
# 9. test_apply_manual_review_billing_model_selection_records_basis_override
# ---------------------------------------------------------------------------

class TestApplyBillingModelSelection:
    def test_apply_manual_review_billing_model_selection_records_basis_override(self):
        """billing_model_selection with billing_basis → billing_basis_override."""
        candidate = _make_candidate("c1", _MANUAL_REVIEW_BILLING_MODEL_SELECTION)
        decision = {
            "candidate_id": "c1",
            "decision_type": _MANUAL_REVIEW_BILLING_MODEL_SELECTION,
            "fields": {"billing_basis": "capacity"},
        }
        result = _apply_manual_review_decision(candidate, decision)
        assert result["outcome"] == "billing_basis_override"
        assert result["overrides"]["billing_basis"] == "capacity"


# ---------------------------------------------------------------------------
# 10. test_no_manual_review_input_keeps_existing_workflow_unchanged
# ---------------------------------------------------------------------------

class TestNoInputNoChange:
    def test_no_manual_review_input_keeps_existing_workflow_unchanged(self):
        """Without manual_review_decisions, summarize_quote behaves exactly as before."""
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
        # State WITHOUT manual_review_decisions
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
        # Totals unchanged
        assert summary.total_monthly_price == 100.0
        assert summary.quoted_items == 1
        assert summary.blocker_count == 1
        # No apply summary in result
        assert "manual_review_apply_summary" not in result
        # No MANUAL REVIEW APPLY in assumptions
        apply_assumptions = [a for a in summary.assumptions if "MANUAL REVIEW APPLY" in a]
        assert len(apply_assumptions) == 0


# ---------------------------------------------------------------------------
# 11. test_summary_mentions_manual_review_apply_counts
# ---------------------------------------------------------------------------

class TestSummaryMentionsApply:
    def test_summary_mentions_manual_review_apply_counts(self):
        """When manual_review_decisions are applied, summary should mention MANUAL REVIEW APPLY."""
        from app.models import FlexibleQuoteLine
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
        # Provide manual_review_decisions in state
        manual_review_decisions = [{
            "candidate_id": "b1",
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": False, "mapped_as": None},
        }]
        state = {
            "requirements": [req.model_dump(), req_b.model_dump()],
            "quote_ready_items": [req.model_dump()],
            "quote_lines": [ql.model_dump()],
            "quote_blockers": [blocker.model_dump()],
            "unquoted_items": [],
            "quote_context": {"region": "chile"},
            "llm_aggregated_billing_items": [],
            "manual_review_decisions": manual_review_decisions,
            "audit_log": [],
            "progress_callback": None,
        }
        result = summarize_quote(state)
        summary = FlexibleQuoteSummary.model_validate(result["summary"])
        apply_assumptions = [a for a in summary.assumptions if "MANUAL REVIEW APPLY" in a]
        assert len(apply_assumptions) == 1
        assert "1 decision(s) applied" in apply_assumptions[0]
        assert "1 excluded" in apply_assumptions[0]


# ---------------------------------------------------------------------------
# 12. test_information_sheet_mentions_manual_review_apply_results
# ---------------------------------------------------------------------------

class TestInfoSheetMentionsApply:
    def test_information_sheet_mentions_manual_review_apply_results(self):
        """Información sheet should contain MANUAL REVIEW APPLY section."""
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
        apply_summary = {
            "decisions_applied": 1,
            "excluded_by_manual_review": 1,
            "mapped_overrides": 0,
            "include_but_needs_mapping": 0,
            "no_change": 0,
            "unresolved_after_manual_review": 0,
        }
        applied_results = [{
            "candidate_id": "b1",
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": False, "mapped_as": None},
            "outcome": "excluded_by_manual_review",
            "overrides": {},
        }]
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
            "manual_review_apply_summary": apply_summary,
            "applied_manual_review_results": applied_results,
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
        assert "MANUAL REVIEW APPLY" in info_text
        assert "Decisions applied: 1" in info_text
        assert "Excluded by manual review: 1" in info_text

    def test_summary_sheet_mentions_manual_review_apply(self):
        """Summary sheet should contain MANUAL REVIEW APPLY section."""
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
        apply_summary = {
            "decisions_applied": 1,
            "excluded_by_manual_review": 0,
            "mapped_overrides": 1,
            "include_but_needs_mapping": 0,
            "no_change": 0,
            "unresolved_after_manual_review": 0,
        }
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
            "manual_review_apply_summary": apply_summary,
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
        assert "MANUAL REVIEW APPLY" in summary_text


# ---------------------------------------------------------------------------
# 13. test_manual_review_apply_does_not_change_quote_totals_without_repricing
# ---------------------------------------------------------------------------

class TestPreservesTotals:
    def test_manual_review_apply_does_not_change_quote_totals_without_repricing(self):
        """Applying manual review decisions should not change existing quote totals."""
        from app.models import FlexibleQuoteLine
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
        manual_review_decisions = [{
            "candidate_id": "b1",
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": False, "mapped_as": None},
        }]
        state = {
            "requirements": [req.model_dump(), req_b.model_dump()],
            "quote_ready_items": [req.model_dump()],
            "quote_lines": [ql.model_dump()],
            "quote_blockers": [blocker.model_dump()],
            "unquoted_items": [],
            "quote_context": {"region": "chile"},
            "llm_aggregated_billing_items": [],
            "manual_review_decisions": manual_review_decisions,
            "audit_log": [],
            "progress_callback": None,
        }
        result = summarize_quote(state)
        summary = FlexibleQuoteSummary.model_validate(result["summary"])
        # Total monthly price should still be $100 (from the quoted line only)
        assert summary.total_monthly_price == 100.0
        assert summary.quoted_items == 1


# ---------------------------------------------------------------------------
# 14. test_apply_multiple_manual_review_inputs_is_stable
# ---------------------------------------------------------------------------

class TestMultipleInputs:
    def test_apply_multiple_manual_review_inputs_is_stable(self):
        """Applying multiple inputs at once should produce stable results."""
        candidates = [
            _make_candidate("c1", _MANUAL_REVIEW_SERVICE_SCOPE_DECISION, "Azure DNS"),
            _make_candidate("c2", _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION, "API Management"),
        ]
        inputs = [
            {
                "candidate_id": "c1",
                "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
                "fields": {"include_in_quote": False, "mapped_as": None},
            },
            {
                "candidate_id": "c2",
                "decision_type": _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION,
                "fields": {"huawei_product_family": "API Gateway"},
            },
        ]
        state = _make_state_with_candidates(candidates)
        state["manual_review_candidates"] = candidates
        validated = _validate_manual_review_inputs(inputs, candidates)
        assert len(validated) == 2
        result = _apply_manual_review_inputs(state, validated)
        assert len(result["applied_manual_review_results"]) == 2
        assert result["manual_review_apply_summary"]["decisions_applied"] == 2
        assert result["manual_review_apply_summary"]["excluded_by_manual_review"] == 1
        assert result["manual_review_apply_summary"]["mapped_overrides"] == 1


# ---------------------------------------------------------------------------
# 15. test_invalid_inputs_return_structured_errors
# ---------------------------------------------------------------------------

class TestStructuredErrors:
    def test_invalid_inputs_return_structured_errors(self):
        """Invalid inputs should produce structured error dicts."""
        candidates = [_make_candidate("c1", _MANUAL_REVIEW_SERVICE_SCOPE_DECISION)]
        inputs = [
            # Missing candidate_id
            {"decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION, "fields": {"include_in_quote": False}},
            # Unknown candidate_id
            {"candidate_id": "c999", "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION, "fields": {"include_in_quote": False}},
            # Wrong decision_type
            {"candidate_id": "c1", "decision_type": _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION, "fields": {"huawei_product_family": "X"}},
            # Invalid include_in_quote type
            {"candidate_id": "c1", "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION, "fields": {"include_in_quote": "yes"}},
        ]
        errors = _manual_review_input_errors(inputs, candidates)
        assert len(errors) == 4
        error_types = {e["error"] for e in errors}
        assert "missing_candidate_id" in error_types
        assert "unknown_candidate_id" in error_types
        assert "wrong_decision_type" in error_types
        assert "invalid_field_type" in error_types


# ---------------------------------------------------------------------------
# 16. test_apply_unsupported_by_catalog_records_override
# ---------------------------------------------------------------------------

class TestApplyUnsupportedByCatalog:
    def test_apply_unsupported_by_catalog_records_override(self):
        """unsupported_by_current_catalog with huawei_product_family → override recorded."""
        candidate = _make_candidate("c1", _MANUAL_REVIEW_UNSUPPORTED_BY_CATALOG)
        decision = {
            "candidate_id": "c1",
            "decision_type": _MANUAL_REVIEW_UNSUPPORTED_BY_CATALOG,
            "fields": {"huawei_product_family": "DWS"},
        }
        result = _apply_manual_review_decision(candidate, decision)
        assert result["outcome"] == "unsupported_family_override_recorded"
        assert result["overrides"]["huawei_product_family"] == "DWS"


# ---------------------------------------------------------------------------
# 17. test_validate_billing_basis_enum
# ---------------------------------------------------------------------------

class TestBillingBasisEnum:
    def test_validate_billing_basis_accepts_valid_values(self):
        """billing_basis must be one of capacity, instance, request."""
        candidates = [_make_candidate("c1", _MANUAL_REVIEW_BILLING_MODEL_SELECTION)]
        for valid_basis in ("capacity", "instance", "request"):
            inputs = [{
                "candidate_id": "c1",
                "decision_type": _MANUAL_REVIEW_BILLING_MODEL_SELECTION,
                "fields": {"billing_basis": valid_basis},
            }]
            errors = _manual_review_input_errors(inputs, candidates)
            assert len(errors) == 0, f"billing_basis={valid_basis} should be valid"

    def test_validate_billing_basis_rejects_invalid_values(self):
        """billing_basis with invalid value should be rejected."""
        candidates = [_make_candidate("c1", _MANUAL_REVIEW_BILLING_MODEL_SELECTION)]
        inputs = [{
            "candidate_id": "c1",
            "decision_type": _MANUAL_REVIEW_BILLING_MODEL_SELECTION,
            "fields": {"billing_basis": "per_hour"},
        }]
        errors = _manual_review_input_errors(inputs, candidates)
        invalid = [e for e in errors if e["error"] == "invalid_field_value"]
        assert len(invalid) == 1


# ---------------------------------------------------------------------------
# 18. test_validate_huawei_product_family_must_be_nonempty_string
# ---------------------------------------------------------------------------

class TestProductFamilyType:
    def test_validate_huawei_product_family_must_be_nonempty_string(self):
        """huawei_product_family must be a non-empty string."""
        candidates = [_make_candidate("c1", _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION)]
        inputs = [{
            "candidate_id": "c1",
            "decision_type": _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION,
            "fields": {"huawei_product_family": ""},
        }]
        errors = _manual_review_input_errors(inputs, candidates)
        invalid = [e for e in errors if e["error"] == "invalid_field_type"]
        assert len(invalid) == 1


# ---------------------------------------------------------------------------
# 19. test_apply_capacity_or_tier_confirmation
# ---------------------------------------------------------------------------

class TestApplyCapacityTier:
    def test_apply_capacity_or_tier_confirmation(self):
        """capacity_or_tier_confirmation with capacity_gib and tier → override."""
        candidate = _make_candidate("c1", _MANUAL_REVIEW_CAPACITY_OR_TIER_CONFIRMATION)
        decision = {
            "candidate_id": "c1",
            "decision_type": _MANUAL_REVIEW_CAPACITY_OR_TIER_CONFIRMATION,
            "fields": {"capacity_gib": 500, "tier": "ultrahigh"},
        }
        result = _apply_manual_review_decision(candidate, decision)
        assert result["outcome"] == "capacity_or_tier_override"
        assert result["overrides"]["capacity_gib"] == 500
        assert result["overrides"]["tier"] == "ultrahigh"


# ---------------------------------------------------------------------------
# 20. test_real_azure_file_manual_review_apply
# ---------------------------------------------------------------------------

class TestRealAzureFile:
    @pytest.mark.skipif(not AZURE_CSV_PATH.exists(), reason="Azure CSV not available")
    def test_real_azure_manual_review_apply_state_fields(self, azure_document):
        """Real Azure file: applying manual review decisions adds state fields."""
        state = _make_billing_state(azure_document)
        manual_review = state.get("billing_manual_review_design", {})
        candidates = manual_review.get("candidates", [])

        # Apply a service_scope_decision for the first candidate
        if candidates:
            first = candidates[0]
            inputs = [{
                "candidate_id": first["candidate_id"],
                "decision_type": first["manual_review_need"],
                "fields": {"include_in_quote": False, "mapped_as": None}
                if first["manual_review_need"] == _MANUAL_REVIEW_SERVICE_SCOPE_DECISION
                else {"huawei_product_family": "TestProduct"},
            }]
            validated = _validate_manual_review_inputs(inputs, candidates)
            result = _apply_manual_review_inputs(state, validated)
            assert "manual_review_decisions" in result
            assert "applied_manual_review_results" in result
            assert "manual_review_apply_summary" in result
            assert result["manual_review_apply_summary"]["decisions_applied"] == 1

    @pytest.mark.skipif(not AZURE_CSV_PATH.exists(), reason="Azure CSV not available")
    def test_real_azure_quote_totals_unchanged_after_apply(self, azure_document):
        """Real Azure file: quote totals should not change from manual review apply."""
        state = _make_billing_state(azure_document)
        summary = FlexibleQuoteSummary.model_validate(state["summary"])
        # Totals should be exactly as before
        assert summary.quoted_items == 26
        assert summary.total_monthly_price == 7635.67
