"""Phase 5 regression tests for Cloud Billing Quote main chain.

Validates:
- 5A: cloud billing graph does not contain understand_input
- 5B: billing main intermediate layer semantics (billing_lines, billing_groups,
      llm_aggregated_billing_items, requirements are the primary chain)
- 5C: normalize preserves protected products (RDS, CBR, OBS, etc.)
- 5D: export/summary prefer aggregated billing items
- 5E: known product misclassification directions fixed
"""

from __future__ import annotations

import pytest

from app.flexible_workflow import (
    FlexibleQuoteState,
    RequirementItem,
    normalize_requirements,
    _reclassify_billing_unit_and_product,
    _classify_resource_kind_fallback,
    _RESOURCE_KIND_KEYWORDS,
    _extract_billing_requirement_items,
    _detect_billing_document,
    _extract_billing_lines,
    _group_billing_lines,
    _normalize_llm_aggregated_billing_items,
    _build_requirements_from_llm_aggregated_billing_items,
    FlexibleQuoteContext,
)
from app.models import ComputeSpec, GenericSpec, StorageSpec


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 5A: cloud billing graph does not contain understand_input
# ═══════════════════════════════════════════════════════════════════════════════


class TestCloudBillingGraphNoUnderstandInput:
    """Cloud billing preview graph should NOT contain understand_input."""

    def test_billing_graph_lacks_understand_input_node(self):
        from app.cloud_billing_workflow import cloud_billing_preview_graph
        nodes = set(cloud_billing_preview_graph.nodes.keys())
        assert "understand_input" not in nodes, (
            f"Cloud billing graph should not contain understand_input node. "
            f"Nodes: {nodes}"
        )

    def test_billing_graph_has_extract_requirement_items(self):
        from app.cloud_billing_workflow import cloud_billing_preview_graph
        nodes = set(cloud_billing_preview_graph.nodes.keys())
        assert "extract_requirement_items" in nodes

    def test_billing_graph_has_parse_documents(self):
        from app.cloud_billing_workflow import cloud_billing_preview_graph
        nodes = set(cloud_billing_preview_graph.nodes.keys())
        assert "parse_documents" in nodes

    def test_flexible_graph_still_has_understand_input(self):
        """Flexible graph should still have understand_input (unchanged)."""
        from app.flexible_workflow import flexible_preview_graph
        nodes = set(flexible_preview_graph.nodes.keys())
        assert "understand_input" in nodes


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 5B: billing main intermediate layer semantics
# ═══════════════════════════════════════════════════════════════════════════════


class TestBillingMainIntermediateLayer:
    """Billing path outputs the primary chain: billing_lines → billing_groups →
    llm_aggregated_billing_items → requirements."""

    @pytest.fixture
    def billing_state_with_mock_llm(self, monkeypatch):
        """Create a billing state with mock LLM aggregation that returns
        a simple aggregated item."""
        # Mock LLM to return a deterministic aggregated item
        def mock_aggregate(groups, quote_context):
            return [
                {
                    "aggregate_label": "Virtual Machines",
                    "resource_kind": "ecs",
                    "source_group_ids": [g.get("group_id", "g0") for g in groups],
                    "aggregation_type": "sum",
                    "source_sku_hint": "Standard_D2s_v3",
                    "huawei_product": "ECS",
                    "huawei_spec_hint": "s6.2xlarge.2",
                    "derived_quantity": 2.0,
                    "derived_unit": "instance hours",
                    "confidence": 0.9,
                    "rationale": "test",
                    "needs_manual_review": False,
                    "product_family": "Compute",
                    "product_type": "Virtual Machines",
                    "product_sku": "Standard_D2s_v3",
                    "unit_type": "Hours",
                    "vendor": "azure",
                    "source_file": "test.csv",
                    "source_sheet": "Sheet1",
                    "source_line_numbers": [1, 2],
                    "amount": 100.0,
                    "currency": "USD",
                }
            ]

        monkeypatch.setattr(
            "app.flexible_workflow._aggregate_billing_groups_with_llm",
            mock_aggregate,
        )

        # Create a minimal billing document
        doc = {
            "filename": "test.csv",
            "sheet": "Sheet1",
            "columns": ["Product", "SKU", "Quantity", "Unit", "Amount"],
            "rows": [
                {"Product": "Virtual Machines", "SKU": "Standard_D2s_v3",
                 "Quantity": "2", "Unit": "Hours", "Amount": "100",
                 "_line_number": 1},
            ],
            "is_billing": True,
            "vendor": "azure",
        }

        state: FlexibleQuoteState = {
            "files": [],
            "quote_context": FlexibleQuoteContext(region="mexico", language="en").model_dump(),
            "parsed_documents": [doc],
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
        return state

    def test_billing_path_outputs_billing_lines(self, billing_state_with_mock_llm):
        result = _extract_billing_requirement_items(
            billing_state_with_mock_llm,
            [billing_state_with_mock_llm["parsed_documents"][0]],
            billing_state_with_mock_llm["parsed_documents"],
        )
        assert "billing_lines" in result
        assert len(result["billing_lines"]) > 0

    def test_billing_path_outputs_billing_groups(self, billing_state_with_mock_llm):
        result = _extract_billing_requirement_items(
            billing_state_with_mock_llm,
            [billing_state_with_mock_llm["parsed_documents"][0]],
            billing_state_with_mock_llm["parsed_documents"],
        )
        assert "billing_groups" in result
        assert len(result["billing_groups"]) > 0

    def test_billing_path_outputs_llm_aggregated_items(self, billing_state_with_mock_llm):
        result = _extract_billing_requirement_items(
            billing_state_with_mock_llm,
            [billing_state_with_mock_llm["parsed_documents"][0]],
            billing_state_with_mock_llm["parsed_documents"],
        )
        assert "llm_aggregated_billing_items" in result
        assert len(result["llm_aggregated_billing_items"]) > 0

    def test_billing_path_outputs_requirements(self, billing_state_with_mock_llm):
        result = _extract_billing_requirement_items(
            billing_state_with_mock_llm,
            [billing_state_with_mock_llm["parsed_documents"][0]],
            billing_state_with_mock_llm["parsed_documents"],
        )
        assert "requirements" in result
        assert len(result["requirements"]) > 0

    def test_billing_path_outputs_legacy_compat_fields(self, billing_state_with_mock_llm):
        """Legacy compat fields should still be produced for backward compat."""
        result = _extract_billing_requirement_items(
            billing_state_with_mock_llm,
            [billing_state_with_mock_llm["parsed_documents"][0]],
            billing_state_with_mock_llm["parsed_documents"],
        )
        assert "standardized_billing_resources" in result
        assert "mapped_billing_resources" in result

    def test_requirements_quantity_source_is_billing_standardized(self, billing_state_with_mock_llm):
        result = _extract_billing_requirement_items(
            billing_state_with_mock_llm,
            [billing_state_with_mock_llm["parsed_documents"][0]],
            billing_state_with_mock_llm["parsed_documents"],
        )
        for req_data in result["requirements"]:
            req = RequirementItem.model_validate(req_data)
            assert req.quantity_source == "billing_standardized"


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 5C: normalize preserves protected products
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalizePreservesProtectedProducts:
    """Normalize should not redirect protected products (RDS, CBR, OBS, etc.)."""

    def _make_billing_requirement(self, product, raw_name=None, unit="instance hours"):
        return RequirementItem(
            item_id="test::1",
            source_file="test.csv",
            source_sheet="Sheet1",
            row_number=1,
            raw_product_name=raw_name or product,
            normalized_product=product,
            quantity=1.0,
            quantity_source="billing_standardized",
            unit=unit,
            region="mexico",
        )

    def test_normalize_preserves_rds_product(self):
        req = self._make_billing_requirement("RDS", "Azure Database for MySQL")
        reclass_product, reclass_unit, reclass_spec = _reclassify_billing_unit_and_product(req)
        # RDS is protected — product should NOT be redirected
        assert reclass_product is None, "RDS product should not be reclassified"

    def test_normalize_preserves_cbr_product(self):
        req = self._make_billing_requirement("CBR", "Backup - Azure VM")
        reclass_product, reclass_unit, reclass_spec = _reclassify_billing_unit_and_product(req)
        assert reclass_product is None, "CBR product should not be reclassified"

    def test_normalize_preserves_obs_product(self):
        req = self._make_billing_requirement("OBS", "Blob Storage", unit="capacity gib month")
        reclass_product, reclass_unit, reclass_spec = _reclassify_billing_unit_and_product(req)
        assert reclass_product is None, "OBS product should not be reclassified"

    def test_normalize_preserves_vpn_product(self):
        req = self._make_billing_requirement("VPN", "VPN Gateway")
        reclass_product, reclass_unit, reclass_spec = _reclassify_billing_unit_and_product(req)
        assert reclass_product is None, "VPN product should not be reclassified"

    def test_normalize_preserves_elb_product(self):
        req = self._make_billing_requirement("ELB", "Load Balancer")
        reclass_product, reclass_unit, reclass_spec = _reclassify_billing_unit_and_product(req)
        assert reclass_product is None, "ELB product should not be reclassified"

    def test_normalize_preserves_eip_product(self):
        req = self._make_billing_requirement("EIP", "Public IP Address")
        reclass_product, reclass_unit, reclass_spec = _reclassify_billing_unit_and_product(req)
        assert reclass_product is None, "EIP product should not be reclassified"

    def test_normalize_preserves_hss_product(self):
        req = self._make_billing_requirement("HSS", "Microsoft Defender")
        reclass_product, reclass_unit, reclass_spec = _reclassify_billing_unit_and_product(req)
        assert reclass_product is None, "HSS product should not be reclassified"

    def test_normalize_full_pipeline_preserves_rds(self):
        """Full normalize_requirements pipeline preserves RDS for billing items."""
        req = self._make_billing_requirement("RDS", "Azure Database for MySQL")
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
        normalized_req = RequirementItem.model_validate(result["requirements"][0])
        assert normalized_req.normalized_product == "RDS", (
            f"RDS product should be preserved after normalize, got {normalized_req.normalized_product}"
        )

    def test_normalize_full_pipeline_preserves_cbr(self):
        """Full normalize_requirements pipeline preserves CBR for billing items."""
        req = self._make_billing_requirement("CBR", "Backup - Azure VM")
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
        normalized_req = RequirementItem.model_validate(result["requirements"][0])
        assert normalized_req.normalized_product == "CBR", (
            f"CBR product should be preserved after normalize, got {normalized_req.normalized_product}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 5E: known product misclassification directions fixed
# ═══════════════════════════════════════════════════════════════════════════════


class TestProductMisclassificationFixed:
    """Fix known misclassification directions in the billing pipeline."""

    def test_azure_mysql_compute_classified_as_database_not_vm(self):
        """Azure MySQL compute should be classified as database, not vm."""
        kind = _classify_resource_kind_fallback(
            "Azure Database for MySQL", "MySQL Flexible Server", "Compute Hours"
        )
        assert kind == "database", (
            f"Azure MySQL compute should be 'database', got '{kind}'"
        )

    def test_azure_mysql_compute_in_product_type(self):
        """Azure MySQL in product_type should be classified as database."""
        kind = _classify_resource_kind_fallback(
            "Azure Database for MySQL", "", ""
        )
        assert kind == "database"

    def test_azure_vm_backup_classified_as_backup_not_vm(self):
        """Azure VM Backup should be classified as backup, not vm."""
        kind = _classify_resource_kind_fallback(
            "Backup", "Azure VM Backup", "1"
        )
        assert kind == "backup", (
            f"Azure VM Backup should be 'backup', got '{kind}'"
        )

    def test_azure_backup_in_product_type(self):
        """Backup in product_type should be classified as backup."""
        kind = _classify_resource_kind_fallback(
            "Backup", "", ""
        )
        assert kind == "backup"

    def test_unsupported_paas_classified_as_unsupported(self):
        """Azure Pipelines should be classified as developer_tool (→ unsupported → manual_review)."""
        kind = _classify_resource_kind_fallback(
            "Azure DevOps", "Azure Pipelines", "1"
        )
        # developer_tool is not in _DIRECT_KIND_TO_HUAWEI, so it becomes
        # unsupported → needs_manual_review, which is correct
        assert kind in ("developer_tool", "unsupported"), (
            f"Azure Pipelines should be developer_tool or unsupported, got '{kind}'"
        )

    def test_ecs_mysql_reclassified_to_rds(self):
        """ECS item with MySQL compute in raw_product_name should be reclassified to RDS."""
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
        reclass_product, reclass_unit, reclass_spec = _reclassify_billing_unit_and_product(req)
        assert reclass_product == "RDS", (
            f"ECS MySQL compute should be reclassified to RDS, got {reclass_product}"
        )

    def test_ecs_backup_reclassified_to_cbr(self):
        """ECS item with Backup - Azure VM in raw_product_name should be reclassified to CBR."""
        req = RequirementItem(
            item_id="test::1",
            source_file="test.csv",
            source_sheet="Sheet1",
            row_number=1,
            raw_product_name="Backup - Azure VM",
            normalized_product="ECS",
            quantity=1.0,
            quantity_source="billing_standardized",
            unit="instance hours",
            region="mexico",
        )
        reclass_product, reclass_unit, reclass_spec = _reclassify_billing_unit_and_product(req)
        assert reclass_product == "CBR", (
            f"ECS Backup should be reclassified to CBR, got {reclass_product}"
        )

    def test_resource_kind_keywords_database_before_vm(self):
        """database keywords should be checked before vm keywords (Phase 5E)."""
        # Find the position of "database" and "vm" in _RESOURCE_KIND_KEYWORDS
        kinds_order = [kind for kind, _ in _RESOURCE_KIND_KEYWORDS]
        db_idx = kinds_order.index("database")
        vm_idx = kinds_order.index("vm")
        assert db_idx < vm_idx, (
            f"database (index {db_idx}) should come before vm (index {vm_idx}) "
            f"in _RESOURCE_KIND_KEYWORDS to prevent MySQL compute → vm misclassification"
        )

    def test_resource_kind_keywords_backup_before_vm(self):
        """backup keywords should be checked before vm keywords (Phase 5E)."""
        kinds_order = [kind for kind, _ in _RESOURCE_KIND_KEYWORDS]
        backup_idx = kinds_order.index("backup")
        vm_idx = kinds_order.index("vm")
        assert backup_idx < vm_idx, (
            f"backup (index {backup_idx}) should come before vm (index {vm_idx}) "
            f"in _RESOURCE_KIND_KEYWORDS to prevent Backup VM → vm misclassification"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 5D: export/summary prefer aggregated billing items
# ═══════════════════════════════════════════════════════════════════════════════


class TestExportPrefersAggregatedItems:
    """Export and summary functions should prefer aggregated billing items
    over legacy mapped_billing_resources."""

    def test_detail_rows_prefers_aggregated_items(self):
        """_build_billing_detail_rows should use llm_aggregated_billing_items
        when available, producing rows with correct source_resource."""
        from app.flexible_workflow import _build_billing_detail_rows

        state: FlexibleQuoteState = {
            "llm_aggregated_billing_items": [
                {
                    "source_file": "test.csv",
                    "product_type": "Virtual Machines",
                    "product_sku": "D2s_v3",
                    "huawei_product": "ECS",
                    "huawei_spec_hint": "s6.2xlarge.2",
                    "derived_quantity": 2.0,
                    "derived_unit": "instance hours",
                    "source_line_numbers": [1],
                    "needs_manual_review": False,
                },
            ],
            "mapped_billing_resources": [
                {
                    "mapped_id": "billing-map::test.csv::0::ECS",
                    "product_type": "Virtual Machines",
                    "product_sku": "D2s_v3",
                    "huawei_product": "ECS",
                    "huawei_spec_hint": {},
                    "quantity": 2.0,
                    "unit_type": "Hours",
                    "unit": "instance hours",
                    "source_line_numbers": [1],
                    "needs_manual_review": False,
                },
            ],
            "quote_lines": [],
            "unquoted_items": [],
            "quote_blockers": [],
        }
        rows = _build_billing_detail_rows(state)
        # Should produce rows using aggregated items (not empty)
        assert len(rows) > 0
        # The huawei_product should come from aggregated items
        assert rows[0]["huawei_product"] == "ECS"
        # The spec hint should come from aggregated items (string, not dict)
        assert rows[0]["huawei_spec_hint"] == "s6.2xlarge.2"

    def test_detail_rows_falls_back_to_mapped_when_no_aggregated(self):
        """_build_billing_detail_rows should fall back to mapped_billing_resources
        when llm_aggregated_billing_items is empty."""
        from app.flexible_workflow import _build_billing_detail_rows

        state: FlexibleQuoteState = {
            "llm_aggregated_billing_items": [],
            "mapped_billing_resources": [
                {
                    "mapped_id": "billing-map::test.csv::0::ECS",
                    "product_type": "Virtual Machines",
                    "product_sku": "D2s_v3",
                    "huawei_product": "ECS",
                    "huawei_spec_hint": {},
                    "quantity": 2.0,
                    "unit_type": "Hours",
                    "unit": "instance hours",
                    "source_line_numbers": [1],
                    "needs_manual_review": False,
                },
            ],
            "quote_lines": [],
            "unquoted_items": [],
            "quote_blockers": [],
        }
        rows = _build_billing_detail_rows(state)
        assert len(rows) > 0
        # The huawei_product should come from mapped resources as fallback
        assert rows[0]["huawei_product"] == "ECS"
