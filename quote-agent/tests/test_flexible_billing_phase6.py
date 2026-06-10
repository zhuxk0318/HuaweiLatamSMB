"""Phase 6 regression tests for Others Quote row-by-row workflow.

Validates:
- 6A: Others graph is pure row-by-row (uses Others-specific nodes)
- 6B: Others path doesn't depend on billing state
- 6C: Others normalize doesn't trigger billing reclassification
- 6D: Others summary doesn't include billing analysis
- 6E: Billing doc to Others gives clear error/guidance
"""

from __future__ import annotations

import pytest

from app.flexible_workflow import (
    FlexibleQuoteState,
    RequirementItem,
    FlexibleQuoteContext,
    FlexibleWorkflowError,
    normalize_others_requirements,
    normalize_requirements,
    summarize_others_quote,
    extract_others_requirement_items,
    _detect_billing_document,
    _classify_resource_kind_fallback,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 6A: Others graph is pure row-by-row
# ═══════════════════════════════════════════════════════════════════════════════


class TestOthersGraphIsRowByRow:
    """Others graph should use Others-specific node implementations."""

    def test_others_graph_has_understand_input(self):
        """Others graph should still have understand_input (needed for schema understanding)."""
        from app.others_quote_workflow import others_preview_graph
        nodes = set(others_preview_graph.nodes.keys())
        assert "understand_input" in nodes

    def test_others_graph_has_extract_requirement_items(self):
        from app.others_quote_workflow import others_preview_graph
        nodes = set(others_preview_graph.nodes.keys())
        assert "extract_requirement_items" in nodes

    def test_others_graph_has_normalize_requirements(self):
        from app.others_quote_workflow import others_preview_graph
        nodes = set(others_preview_graph.nodes.keys())
        assert "normalize_requirements" in nodes

    def test_others_graph_has_summarize_quote(self):
        from app.others_quote_workflow import others_preview_graph
        nodes = set(others_preview_graph.nodes.keys())
        assert "summarize_quote" in nodes

    def test_others_graph_uses_others_extract_implementation(self):
        """Verify the Others graph uses extract_others_requirement_items."""
        from app.others_quote_workflow import extract_others_requirement_items as others_extract
        from app.flexible_workflow import extract_others_requirement_items as flex_extract
        assert others_extract is flex_extract, (
            "Others graph should use extract_others_requirement_items from flexible_workflow"
        )

    def test_others_graph_uses_others_normalize_implementation(self):
        """Verify the Others graph uses normalize_others_requirements."""
        from app.others_quote_workflow import normalize_others_requirements as others_norm
        from app.flexible_workflow import normalize_others_requirements as flex_norm
        assert others_norm is flex_norm, (
            "Others graph should use normalize_others_requirements from flexible_workflow"
        )

    def test_others_graph_uses_others_summarize_implementation(self):
        """Verify the Others graph uses summarize_others_quote."""
        from app.others_quote_workflow import summarize_others_quote as others_sum
        from app.flexible_workflow import summarize_others_quote as flex_sum
        assert others_sum is flex_sum, (
            "Others graph should use summarize_others_quote from flexible_workflow"
        )

    def test_cloud_billing_graph_uses_different_extract(self):
        """Cloud billing graph should use the standard extract_requirement_items."""
        from app.cloud_billing_workflow import extract_requirement_items as billing_extract
        from app.flexible_workflow import extract_requirement_items as flex_extract
        assert billing_extract is flex_extract, (
            "Cloud billing graph should use standard extract_requirement_items"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 6B: Others path doesn't depend on billing state
# ═══════════════════════════════════════════════════════════════════════════════


class TestOthersStateIsolation:
    """Others path should not depend on billing-specific state fields."""

    def test_others_normalize_ignores_billing_state(self):
        """normalize_others_requirements should work even when billing fields are empty."""
        req = RequirementItem(
            item_id="test::1",
            source_file="test.xlsx",
            source_sheet="Sheet1",
            row_number=1,
            raw_product_name="ECS",
            quantity=2.0,
            quantity_source="source_file",
            unit="item",
            region="mexico",
        )
        state: FlexibleQuoteState = {
            "files": [],
            "quote_context": FlexibleQuoteContext(region="mexico", language="en").model_dump(),
            "parsed_documents": [],
            "understanding": {"schema_mapping": {}, "profile": {}},
            "requirements": [req.model_dump()],
            "matched_products": [],
            "quote_ready_items": [],
            "quote_blockers": [],
            "price_catalog": [],
            "price_components": [],
            "quote_lines": [],
            "unquoted_items": [],
            "summary": {},
            "audit_log": [],
            "progress_callback": None,
            "diagnostics": {},
            # Billing fields are empty — should not affect Others
            "billing_lines": [],
            "billing_groups": [],
            "llm_aggregated_billing_items": [],
            "standardized_billing_resources": [],
            "mapped_billing_resources": [],
        }
        result = normalize_others_requirements(state)
        normalized = RequirementItem.model_validate(result["requirements"][0])
        assert normalized.normalized_product == "ECS"
        # Should NOT have billing_standardized quantity_source
        assert normalized.quantity_source == "source_file"

    def test_others_summarize_ignores_billing_state(self):
        """summarize_others_quote should work without billing fields."""
        state: FlexibleQuoteState = {
            "files": [],
            "quote_context": FlexibleQuoteContext(region="mexico", language="en").model_dump(),
            "parsed_documents": [],
            "understanding": {"schema_mapping": {}, "profile": {}},
            "requirements": [],
            "matched_products": [],
            "quote_ready_items": [],
            "quote_blockers": [],
            "price_catalog": [],
            "price_components": [],
            "quote_lines": [],
            "unquoted_items": [],
            "summary": {},
            "audit_log": [],
            "progress_callback": None,
            "diagnostics": {},
            # Billing fields absent — should not crash
        }
        result = summarize_others_quote(state)
        assert "summary" in result


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 6C: Others normalize doesn't trigger billing reclassification
# ═══════════════════════════════════════════════════════════════════════════════


class TestOthersNormalizeNoBillingReclassify:
    """Others normalize should not trigger billing reclassification logic."""

    def test_others_normalize_doesnt_reclassify_mysql_compute(self):
        """Even with MySQL compute in raw_product_name, Others normalize should
        use standard product normalization, not billing reclassification."""
        req = RequirementItem(
            item_id="test::1",
            source_file="test.xlsx",
            source_sheet="Sheet1",
            row_number=1,
            raw_product_name="Azure Database for MySQL Flexible Server compute",
            quantity=1.0,
            quantity_source="source_file",
            unit="item",
            region="mexico",
        )
        state: FlexibleQuoteState = {
            "files": [],
            "quote_context": FlexibleQuoteContext(region="mexico", language="en").model_dump(),
            "parsed_documents": [],
            "understanding": {"schema_mapping": {}, "profile": {}},
            "requirements": [req.model_dump()],
            "matched_products": [],
            "quote_ready_items": [],
            "quote_blockers": [],
            "price_catalog": [],
            "price_components": [],
            "quote_lines": [],
            "unquoted_items": [],
            "summary": {},
            "audit_log": [],
            "progress_callback": None,
            "diagnostics": {},
        }
        result = normalize_others_requirements(state)
        normalized = RequirementItem.model_validate(result["requirements"][0])
        # Standard normalization: "Azure Database for MySQL..." → RDS via synonym
        # (not via billing reclassification)
        assert normalized.normalized_product in ("RDS", None), (
            f"Others normalize should use standard product normalization, "
            f"got {normalized.normalized_product}"
        )
        # Should NOT have billing_standardized quantity_source
        assert normalized.quantity_source == "source_file"

    def test_others_normalize_doesnt_reclassify_backup(self):
        """Even with Backup in raw_product_name, Others normalize should
        use standard product normalization."""
        req = RequirementItem(
            item_id="test::1",
            source_file="test.xlsx",
            source_sheet="Sheet1",
            row_number=1,
            raw_product_name="Backup - Azure VM",
            quantity=1.0,
            quantity_source="source_file",
            unit="item",
            region="mexico",
        )
        state: FlexibleQuoteState = {
            "files": [],
            "quote_context": FlexibleQuoteContext(region="mexico", language="en").model_dump(),
            "parsed_documents": [],
            "understanding": {"schema_mapping": {}, "profile": {}},
            "requirements": [req.model_dump()],
            "matched_products": [],
            "quote_ready_items": [],
            "quote_blockers": [],
            "price_catalog": [],
            "price_components": [],
            "quote_lines": [],
            "unquoted_items": [],
            "summary": {},
            "audit_log": [],
            "progress_callback": None,
            "diagnostics": {},
        }
        result = normalize_others_requirements(state)
        normalized = RequirementItem.model_validate(result["requirements"][0])
        # Standard normalization: "Backup - Azure VM" → CBR via synonym
        # (not via billing reclassification)
        assert normalized.quantity_source == "source_file"

    def test_billing_normalize_still_reclassifies(self):
        """Billing normalize should still reclassify ECS MySQL → RDS."""
        req = RequirementItem(
            item_id="test::1",
            source_file="test.csv",
            source_sheet="Sheet1",
            row_number=1,
            raw_product_name="Azure Database for MySQL Flexible Server compute",
            normalized_product="ECS",
            quantity=1.0,
            quantity_source="billing_standardized",
            unit="vcore hours",
            region="mexico",
        )
        state: FlexibleQuoteState = {
            "files": [],
            "quote_context": FlexibleQuoteContext(region="mexico", language="en").model_dump(),
            "parsed_documents": [],
            "understanding": {"schema_mapping": {}, "profile": {}},
            "requirements": [req.model_dump()],
            "matched_products": [],
            "quote_ready_items": [],
            "quote_blockers": [],
            "price_catalog": [],
            "price_components": [],
            "quote_lines": [],
            "unquoted_items": [],
            "summary": {},
            "audit_log": [],
            "progress_callback": None,
            "diagnostics": {},
        }
        result = normalize_requirements(state)
        normalized = RequirementItem.model_validate(result["requirements"][0])
        assert normalized.normalized_product == "RDS", (
            f"Billing normalize should reclassify ECS MySQL → RDS, got {normalized.normalized_product}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 6D: Others summary doesn't include billing analysis
# ═══════════════════════════════════════════════════════════════════════════════


class TestOthersSummaryNoBillingAnalysis:
    """Others summary should not include billing gap/reconciliation analysis."""

    def test_others_summary_no_billing_gap_analysis(self):
        """summarize_others_quote should not produce billing_gap_analysis."""
        state: FlexibleQuoteState = {
            "files": [],
            "quote_context": FlexibleQuoteContext(region="mexico", language="en").model_dump(),
            "parsed_documents": [],
            "understanding": {"schema_mapping": {}, "profile": {}},
            "requirements": [],
            "matched_products": [],
            "quote_ready_items": [],
            "quote_blockers": [],
            "price_catalog": [],
            "price_components": [],
            "quote_lines": [],
            "unquoted_items": [],
            "summary": {},
            "audit_log": [],
            "progress_callback": None,
            "diagnostics": {},
        }
        result = summarize_others_quote(state)
        assert "billing_gap_analysis" not in result, (
            "Others summary should not include billing_gap_analysis"
        )

    def test_others_summary_no_billing_reconciliation(self):
        """summarize_others_quote should not produce billing_reconciliation."""
        state: FlexibleQuoteState = {
            "files": [],
            "quote_context": FlexibleQuoteContext(region="mexico", language="en").model_dump(),
            "parsed_documents": [],
            "understanding": {"schema_mapping": {}, "profile": {}},
            "requirements": [],
            "matched_products": [],
            "quote_ready_items": [],
            "quote_blockers": [],
            "price_catalog": [],
            "price_components": [],
            "quote_lines": [],
            "unquoted_items": [],
            "summary": {},
            "audit_log": [],
            "progress_callback": None,
            "diagnostics": {},
        }
        result = summarize_others_quote(state)
        assert "billing_reconciliation" not in result, (
            "Others summary should not include billing_reconciliation"
        )

    def test_others_summary_no_billing_blocker_analysis(self):
        """summarize_others_quote should not produce billing_blocker_analysis."""
        state: FlexibleQuoteState = {
            "files": [],
            "quote_context": FlexibleQuoteContext(region="mexico", language="en").model_dump(),
            "parsed_documents": [],
            "understanding": {"schema_mapping": {}, "profile": {}},
            "requirements": [],
            "matched_products": [],
            "quote_ready_items": [],
            "quote_blockers": [],
            "price_catalog": [],
            "price_components": [],
            "quote_lines": [],
            "unquoted_items": [],
            "summary": {},
            "audit_log": [],
            "progress_callback": None,
            "diagnostics": {},
        }
        result = summarize_others_quote(state)
        assert "billing_blocker_analysis" not in result, (
            "Others summary should not include billing_blocker_analysis"
        )

    def test_others_summary_has_basic_fields(self):
        """summarize_others_quote should produce basic summary fields."""
        state: FlexibleQuoteState = {
            "files": [],
            "quote_context": FlexibleQuoteContext(region="mexico", language="en").model_dump(),
            "parsed_documents": [],
            "understanding": {"schema_mapping": {}, "profile": {}},
            "requirements": [],
            "matched_products": [],
            "quote_ready_items": [],
            "quote_blockers": [],
            "price_catalog": [],
            "price_components": [],
            "quote_lines": [],
            "unquoted_items": [],
            "summary": {},
            "audit_log": [],
            "progress_callback": None,
            "diagnostics": {},
        }
        result = summarize_others_quote(state)
        assert "summary" in result
        assert "audit_log" in result

    def test_others_summary_no_billing_assumptions(self):
        """Others summary assumptions should not contain billing-specific text."""
        from app.flexible_workflow import FlexibleQuoteSummary
        state: FlexibleQuoteState = {
            "files": [],
            "quote_context": FlexibleQuoteContext(region="mexico", language="en").model_dump(),
            "parsed_documents": [],
            "understanding": {"schema_mapping": {}, "profile": {}},
            "requirements": [],
            "matched_products": [],
            "quote_ready_items": [],
            "quote_blockers": [],
            "price_catalog": [],
            "price_components": [],
            "quote_lines": [],
            "unquoted_items": [],
            "summary": {},
            "audit_log": [],
            "progress_callback": None,
            "diagnostics": {},
        }
        result = summarize_others_quote(state)
        summary = FlexibleQuoteSummary.model_validate(result["summary"])
        for assumption in summary.assumptions:
            assert "billing standardization" not in assumption.lower(), (
                f"Others summary should not contain billing standardization assumption: {assumption}"
            )
            assert "PRICING AUDIT" not in assumption, (
                f"Others summary should not contain PRICING AUDIT assumption: {assumption}"
            )
            assert "BLOCKER TRIAGE" not in assumption, (
                f"Others summary should not contain BLOCKER TRIAGE assumption: {assumption}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 6E: Billing doc to Others gives clear error
# ═══════════════════════════════════════════════════════════════════════════════


class TestOthersInputBoundary:
    """Others path should reject billing documents with clear guidance."""

    def test_billing_document_rejected_in_others_extract(self):
        """extract_others_requirement_items should raise error for billing documents."""
        billing_doc = {
            "filename": "azure_billing.csv",
            "sheet": "Sheet1",
            # Use columns that match _BILLING_COLUMN_PATTERNS for Azure
            "columns": ["Product Family", "Product Type", "Product SKU", "Unit Type",
                        "Quantity", "Amount", "Resource Group", "Subscription"],
            "rows": [
                {"Product Family": "Compute", "Product Type": "Virtual Machines",
                 "Product SKU": "D2s_v3", "Unit Type": "Hours",
                 "Quantity": "2", "Amount": "100",
                 "_line_number": 1},
            ],
        }
        state: FlexibleQuoteState = {
            "files": [],
            "quote_context": FlexibleQuoteContext(region="mexico", language="en").model_dump(),
            "parsed_documents": [billing_doc],
            "understanding": {"schema_mapping": {}, "profile": {}},
            "requirements": [],
            "matched_products": [],
            "quote_ready_items": [],
            "quote_blockers": [],
            "price_catalog": [],
            "price_components": [],
            "quote_lines": [],
            "unquoted_items": [],
            "summary": {},
            "audit_log": [],
            "progress_callback": None,
            "diagnostics": {},
        }
        with pytest.raises(FlexibleWorkflowError) as exc_info:
            extract_others_requirement_items(state)
        assert "Billing" in exc_info.value.message or "Cloud Billing" in exc_info.value.message, (
            f"Error should mention billing/Cloud Billing, got: {exc_info.value.message}"
        )
        assert exc_info.value.stage == "extract_others_requirement_items"

    def test_non_billing_document_accepted_in_others_extract(self):
        """extract_others_requirement_items should accept non-billing documents."""
        non_billing_doc = {
            "filename": "requirements.xlsx",
            "sheet": "Sheet1",
            "columns": ["Product", "Quantity", "Region"],
            "rows": [
                {"Product": "ECS", "Quantity": "2", "Region": "mexico",
                 "_line_number": 1},
            ],
        }
        state: FlexibleQuoteState = {
            "files": [],
            "quote_context": FlexibleQuoteContext(region="mexico", language="en").model_dump(),
            "parsed_documents": [non_billing_doc],
            "understanding": {"schema_mapping": {"product": "Product", "quantity": "Quantity", "region": "Region"}, "profile": {}},
            "requirements": [],
            "matched_products": [],
            "quote_ready_items": [],
            "quote_blockers": [],
            "price_catalog": [],
            "price_components": [],
            "quote_lines": [],
            "unquoted_items": [],
            "summary": {},
            "audit_log": [],
            "progress_callback": None,
            "diagnostics": {},
        }
        result = extract_others_requirement_items(state)
        assert "requirements" in result
        assert len(result["requirements"]) > 0

    def test_detect_billing_document_identifies_azure_billing(self):
        """_detect_billing_document should identify Azure billing exports."""
        doc = {
            "columns": ["Product Family", "Product Type", "Product SKU", "Unit Type",
                        "Quantity", "Amount"],
            "rows": [],
        }
        assert _detect_billing_document(doc) is True

    def test_detect_billing_document_rejects_normal_excel(self):
        """_detect_billing_document should not identify normal requirement sheets."""
        doc = {
            "columns": ["Product", "Quantity", "Region", "Spec"],
            "rows": [],
        }
        assert _detect_billing_document(doc) is False
