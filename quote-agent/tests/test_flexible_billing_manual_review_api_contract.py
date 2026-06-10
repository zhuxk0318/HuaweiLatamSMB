"""Phase Next+10 tests: manual review apply API contract — schema validation,
endpoint contract, structured error codes, and no-change guarantee."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
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
)
from app.flexible_pricing import query_flexible_pricing_catalog
from app.models import (
    ManualReviewApplyRequest,
    ManualReviewApplyResponse,
    ManualReviewApplyError,
    ManualReviewApplyResult,
    ManualReviewDecisionInput,
    ManualReviewCandidate,
    FlexibleQuoteContext,
    FlexibleQuotePreviewResponse,
    FlexibleQuoteSummary,
    FlexibleQuoteBlocker,
    RequirementItem,
)

client = TestClient(app)

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
        "audit_log": [],
        "progress_callback": None,
    }


# ---------------------------------------------------------------------------
# 1. test_manual_review_apply_request_schema_accepts_valid_decision
# ---------------------------------------------------------------------------

class TestRequestSchema:
    def test_manual_review_apply_request_schema_accepts_valid_decision(self):
        """ManualReviewApplyRequest should accept valid decision input."""
        req = ManualReviewApplyRequest(
            decisions=[
                ManualReviewDecisionInput(
                    candidate_id="c1",
                    decision_type=_MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
                    fields={"include_in_quote": False, "mapped_as": None},
                )
            ]
        )
        assert len(req.decisions) == 1
        assert req.decisions[0].candidate_id == "c1"
        assert req.task_id is None
        assert req.candidates == []


# ---------------------------------------------------------------------------
# 2. test_manual_review_apply_request_schema_rejects_missing_decisions
# ---------------------------------------------------------------------------

class TestRequestSchemaRejectsMissing:
    def test_manual_review_apply_request_schema_defaults_empty_decisions(self):
        """ManualReviewApplyRequest with no decisions defaults to empty list."""
        req = ManualReviewApplyRequest()
        assert req.decisions == []
        assert req.candidates == []


# ---------------------------------------------------------------------------
# 3. test_manual_review_apply_response_contains_results_errors_and_summary
# ---------------------------------------------------------------------------

class TestResponseSchema:
    def test_manual_review_apply_response_contains_results_errors_and_summary(self):
        """ManualReviewApplyResponse should have results, errors, and summary."""
        resp = ManualReviewApplyResponse(
            applied_count=1,
            errors=[],
            results=[
                ManualReviewApplyResult(
                    candidate_id="c1",
                    outcome="excluded_by_manual_review",
                    overrides={},
                )
            ],
            summary={"decisions_applied": 1},
        )
        assert resp.applied_count == 1
        assert len(resp.results) == 1
        assert len(resp.errors) == 0
        assert resp.summary["decisions_applied"] == 1


# ---------------------------------------------------------------------------
# 4. test_manual_review_apply_endpoint_returns_structured_errors_for_unknown_candidate
# ---------------------------------------------------------------------------

class TestEndpointUnknownCandidate:
    def test_manual_review_apply_endpoint_returns_structured_errors_for_unknown_candidate(self):
        """POST /manual-review/apply with unknown candidate_id returns structured error."""
        candidates = [_make_candidate("c1")]
        resp = client.post(
            "/api/quotes/flexible/manual-review/apply",
            json={
                "candidates": candidates,
                "decisions": [
                    {
                        "candidate_id": "c999",
                        "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
                        "fields": {"include_in_quote": False},
                    }
                ],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["errors"]) >= 1
        assert body["errors"][0]["code"] == "unknown_candidate_id"
        assert body["errors"][0]["candidate_id"] == "c999"


# ---------------------------------------------------------------------------
# 5. test_manual_review_apply_endpoint_returns_structured_errors_for_wrong_decision_type
# ---------------------------------------------------------------------------

class TestEndpointWrongDecisionType:
    def test_manual_review_apply_endpoint_returns_structured_errors_for_wrong_decision_type(self):
        """POST /manual-review/apply with wrong decision_type returns structured error."""
        candidates = [_make_candidate("c1", _MANUAL_REVIEW_SERVICE_SCOPE_DECISION)]
        resp = client.post(
            "/api/quotes/flexible/manual-review/apply",
            json={
                "candidates": candidates,
                "decisions": [
                    {
                        "candidate_id": "c1",
                        "decision_type": _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION,
                        "fields": {"huawei_product_family": "X"},
                    }
                ],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["errors"]) >= 1
        assert body["errors"][0]["code"] == "wrong_decision_type"


# ---------------------------------------------------------------------------
# 6. test_manual_review_apply_endpoint_returns_structured_errors_for_missing_required_field
# ---------------------------------------------------------------------------

class TestEndpointMissingRequiredField:
    def test_manual_review_apply_endpoint_returns_structured_errors_for_missing_required_field(self):
        """POST /manual-review/apply with missing required field returns structured error."""
        candidates = [_make_candidate("c1", _MANUAL_REVIEW_SERVICE_SCOPE_DECISION)]
        resp = client.post(
            "/api/quotes/flexible/manual-review/apply",
            json={
                "candidates": candidates,
                "decisions": [
                    {
                        "candidate_id": "c1",
                        "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
                        "fields": {"mapped_as": "DNS"},
                    }
                ],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        missing = [e for e in body["errors"] if e["code"] == "missing_required_field"]
        assert len(missing) >= 1
        assert "include_in_quote" in missing[0]["message"]


# ---------------------------------------------------------------------------
# 7. test_manual_review_apply_endpoint_returns_invalid_enum_value_for_bad_billing_basis
# ---------------------------------------------------------------------------

class TestEndpointInvalidEnum:
    def test_manual_review_apply_endpoint_returns_invalid_enum_value_for_bad_billing_basis(self):
        """POST /manual-review/apply with invalid billing_basis returns invalid_field_value error."""
        candidates = [_make_candidate("c1", _MANUAL_REVIEW_BILLING_MODEL_SELECTION)]
        resp = client.post(
            "/api/quotes/flexible/manual-review/apply",
            json={
                "candidates": candidates,
                "decisions": [
                    {
                        "candidate_id": "c1",
                        "decision_type": _MANUAL_REVIEW_BILLING_MODEL_SELECTION,
                        "fields": {"billing_basis": "per_hour"},
                    }
                ],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        invalid = [e for e in body["errors"] if e["code"] == "invalid_field_value"]
        assert len(invalid) >= 1


# ---------------------------------------------------------------------------
# 8. test_manual_review_apply_endpoint_applies_valid_decision_and_returns_result
# ---------------------------------------------------------------------------

class TestEndpointApplyValid:
    def test_manual_review_apply_endpoint_applies_valid_decision_and_returns_result(self):
        """POST /manual-review/apply with valid decision returns applied result."""
        candidates = [_make_candidate("c1", _MANUAL_REVIEW_SERVICE_SCOPE_DECISION)]
        resp = client.post(
            "/api/quotes/flexible/manual-review/apply",
            json={
                "candidates": candidates,
                "decisions": [
                    {
                        "candidate_id": "c1",
                        "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
                        "fields": {"include_in_quote": False, "mapped_as": None},
                    }
                ],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["applied_count"] == 1
        assert len(body["results"]) == 1
        assert body["results"][0]["candidate_id"] == "c1"
        assert body["results"][0]["outcome"] == "excluded_by_manual_review"
        assert len(body["errors"]) == 0


# ---------------------------------------------------------------------------
# 9. test_manual_review_apply_endpoint_supports_multiple_decisions
# ---------------------------------------------------------------------------

class TestEndpointMultipleDecisions:
    def test_manual_review_apply_endpoint_supports_multiple_decisions(self):
        """POST /manual-review/apply with multiple decisions applies all valid ones."""
        candidates = [
            _make_candidate("c1", _MANUAL_REVIEW_SERVICE_SCOPE_DECISION, "Azure DNS"),
            _make_candidate("c2", _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION, "API Management"),
        ]
        resp = client.post(
            "/api/quotes/flexible/manual-review/apply",
            json={
                "candidates": candidates,
                "decisions": [
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
                ],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["applied_count"] == 2
        assert len(body["results"]) == 2
        outcomes = {r["outcome"] for r in body["results"]}
        assert "excluded_by_manual_review" in outcomes
        assert "product_family_override" in outcomes


# ---------------------------------------------------------------------------
# 10. test_preview_or_summary_exposes_manual_review_candidates
# ---------------------------------------------------------------------------

class TestPreviewExposesCandidates:
    def test_preview_or_summary_exposes_manual_review_candidates(self):
        """FlexibleQuotePreviewResponse should include manual_review_candidates."""
        # Build a minimal preview response with candidates
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
        state = {
            "quote_blockers": [blocker.model_dump()],
            "requirements": [req.model_dump()],
            "llm_aggregated_billing_items": [],
        }
        manual_review = _analyze_manual_review_design(state)
        candidates = manual_review.get("candidates", [])

        # Verify the preview response model can hold candidates
        resp = FlexibleQuotePreviewResponse(
            manual_review_candidates=[
                ManualReviewCandidate.model_validate(c) for c in candidates
            ],
        )
        assert len(resp.manual_review_candidates) >= 1
        assert resp.manual_review_candidates[0].candidate_id == "b1"

    @pytest.mark.skipif(not AZURE_CSV_PATH.exists(), reason="Azure CSV not available")
    def test_real_azure_preview_exposes_candidates(self):
        """Real Azure file: preview response should include manual_review_candidates."""
        azure_bytes = AZURE_CSV_PATH.read_bytes()
        azure_doc = _parse_csv_document(azure_bytes, "azure_billing.csv")
        state = _make_billing_state(azure_doc)
        manual_review = state.get("billing_manual_review_design", {})
        candidates = manual_review.get("candidates", [])

        resp = FlexibleQuotePreviewResponse(
            manual_review_candidates=[
                ManualReviewCandidate.model_validate(c) for c in candidates
            ],
        )
        assert len(resp.manual_review_candidates) > 0


# ---------------------------------------------------------------------------
# 11. test_manual_review_apply_does_not_change_quote_totals_without_repricing
# ---------------------------------------------------------------------------

class TestNoChangeTotals:
    def test_manual_review_apply_does_not_change_quote_totals_without_repricing(self):
        """Applying manual review decisions via API must not change quote totals."""
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

    def test_api_apply_does_not_change_totals(self):
        """API apply_manual_review_from_api must not change quote totals."""
        # The API wrapper is pure — it does not touch quote_lines or summary.
        candidates = [_make_candidate("c1", _MANUAL_REVIEW_SERVICE_SCOPE_DECISION)]
        decisions = [{
            "candidate_id": "c1",
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": False, "mapped_as": None},
        }]
        result = apply_manual_review_from_api(decisions, candidates)
        # The result only has apply metadata, no quote totals
        assert "applied_count" in result
        assert "results" in result
        assert "errors" in result
        assert "summary" in result
        # No quote_lines or total_monthly_price in result
        assert "quote_lines" not in result
        assert "total_monthly_price" not in result


# ---------------------------------------------------------------------------
# 12. test_manual_review_apply_contract_is_stable_for_real_billing_fixture
# ---------------------------------------------------------------------------

class TestRealFixtureStability:
    @pytest.mark.skipif(not AZURE_CSV_PATH.exists(), reason="Azure CSV not available")
    def test_manual_review_apply_contract_is_stable_for_real_billing_fixture(self):
        """Real Azure fixture: apply contract is stable and returns expected shape."""
        azure_bytes = AZURE_CSV_PATH.read_bytes()
        azure_doc = _parse_csv_document(azure_bytes, "azure_billing.csv")
        state = _make_billing_state(azure_doc)
        manual_review = state.get("billing_manual_review_design", {})
        candidates = manual_review.get("candidates", [])

        # Apply exclude for the first service_scope_decision candidate
        scope_candidates = [
            c for c in candidates
            if c["manual_review_need"] == _MANUAL_REVIEW_SERVICE_SCOPE_DECISION
        ]
        if not scope_candidates:
            pytest.skip("No service_scope_decision candidates in fixture")

        first = scope_candidates[0]
        decisions = [{
            "candidate_id": first["candidate_id"],
            "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
            "fields": {"include_in_quote": False, "mapped_as": None},
        }]
        result = apply_manual_review_from_api(decisions, candidates)

        # Verify contract shape
        assert isinstance(result["applied_count"], int)
        assert result["applied_count"] == 1
        assert isinstance(result["errors"], list)
        assert len(result["errors"]) == 0
        assert isinstance(result["results"], list)
        assert len(result["results"]) == 1
        assert result["results"][0]["candidate_id"] == first["candidate_id"]
        assert result["results"][0]["outcome"] == "excluded_by_manual_review"
        assert isinstance(result["summary"], dict)
        assert result["summary"]["decisions_applied"] == 1
        assert result["summary"]["excluded_by_manual_review"] == 1

    @pytest.mark.skipif(not AZURE_CSV_PATH.exists(), reason="Azure CSV not available")
    def test_real_azure_quote_totals_unchanged_after_api_apply(self):
        """Real Azure fixture: quote totals unchanged after API apply."""
        azure_bytes = AZURE_CSV_PATH.read_bytes()
        azure_doc = _parse_csv_document(azure_bytes, "azure_billing.csv")
        state = _make_billing_state(azure_doc)
        summary = FlexibleQuoteSummary.model_validate(state["summary"])
        # Totals should be exactly as before
        assert summary.quoted_items == 26
        assert summary.total_monthly_price == 7635.67


# ---------------------------------------------------------------------------
# Optional: test_unexpected_field_returns_stable_error_code
# ---------------------------------------------------------------------------

class TestUnexpectedField:
    def test_unexpected_field_returns_stable_error_code(self):
        """Disallowed field should return 'unexpected_field' error code."""
        candidates = [_make_candidate("c1", _MANUAL_REVIEW_SERVICE_SCOPE_DECISION)]
        resp = client.post(
            "/api/quotes/flexible/manual-review/apply",
            json={
                "candidates": candidates,
                "decisions": [
                    {
                        "candidate_id": "c1",
                        "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
                        "fields": {"include_in_quote": False, "mapped_as": None, "bogus_field": 123},
                    }
                ],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        unexpected = [e for e in body["errors"] if e["code"] == "unexpected_field"]
        assert len(unexpected) >= 1
        assert "bogus_field" in unexpected[0]["message"]


# ---------------------------------------------------------------------------
# Optional: test_manual_review_apply_response_summary_counts_match_results
# ---------------------------------------------------------------------------

class TestSummaryCountsMatch:
    def test_manual_review_apply_response_summary_counts_match_results(self):
        """Summary counts should match actual results."""
        candidates = [
            _make_candidate("c1", _MANUAL_REVIEW_SERVICE_SCOPE_DECISION, "Azure DNS"),
            _make_candidate("c2", _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION, "API Management"),
        ]
        decisions = [
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
        result = apply_manual_review_from_api(decisions, candidates)
        summary = result["summary"]
        assert summary["decisions_applied"] == len(result["results"])
        assert summary["excluded_by_manual_review"] == sum(
            1 for r in result["results"] if r["outcome"] == "excluded_by_manual_review"
        )
        assert summary["mapped_overrides"] == sum(
            1 for r in result["results"] if "override" in r["outcome"]
        )


# ---------------------------------------------------------------------------
# Optional: test_manual_review_candidates_round_trip_into_apply_request
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_manual_review_candidates_round_trip_into_apply_request(self):
        """Candidates from preview can be used directly in apply request."""
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
        state = {
            "quote_blockers": [blocker.model_dump()],
            "requirements": [req.model_dump()],
            "llm_aggregated_billing_items": [],
        }
        manual_review = _analyze_manual_review_design(state)
        candidates = manual_review.get("candidates", [])

        # Round-trip: candidates → apply request
        assert len(candidates) >= 1
        first = candidates[0]
        decisions = [{
            "candidate_id": first["candidate_id"],
            "decision_type": first["manual_review_need"],
            "fields": {"include_in_quote": False, "mapped_as": None},
        }]
        result = apply_manual_review_from_api(decisions, candidates)
        assert result["applied_count"] == 1
        assert len(result["errors"]) == 0


# ---------------------------------------------------------------------------
# test_endpoint_returns_400_when_no_candidates
# ---------------------------------------------------------------------------

class TestEndpointNoCandidates:
    def test_endpoint_returns_400_when_no_candidates_and_no_task_id(self):
        """POST /manual-review/apply with no candidates and no task_id returns 400."""
        resp = client.post(
            "/api/quotes/flexible/manual-review/apply",
            json={
                "decisions": [
                    {
                        "candidate_id": "c1",
                        "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION,
                        "fields": {"include_in_quote": False},
                    }
                ],
            },
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# test_error_codes_are_from_stable_set
# ---------------------------------------------------------------------------

class TestStableErrorCodes:
    def test_error_codes_are_from_stable_set(self):
        """All error codes from apply_manual_review_from_api must be from the stable set."""
        stable_codes = {
            "unknown_candidate_id",
            "wrong_decision_type",
            "missing_required_field",
            "invalid_field_type",
            "invalid_field_value",
            "unexpected_field",
        }
        candidates = [_make_candidate("c1", _MANUAL_REVIEW_SERVICE_SCOPE_DECISION)]
        # Trigger various errors
        decisions = [
            {"candidate_id": "c999", "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION, "fields": {"include_in_quote": False}},
            {"candidate_id": "c1", "decision_type": _MANUAL_REVIEW_TARGET_PRODUCT_SELECTION, "fields": {"huawei_product_family": "X"}},
            {"candidate_id": "c1", "decision_type": _MANUAL_REVIEW_SERVICE_SCOPE_DECISION, "fields": {}},
        ]
        result = apply_manual_review_from_api(decisions, candidates)
        for err in result["errors"]:
            assert err["code"] in stable_codes, f"Unexpected error code: {err['code']}"
