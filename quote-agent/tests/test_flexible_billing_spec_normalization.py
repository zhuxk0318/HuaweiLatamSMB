"""Tests for billing spec normalization: Azure shapes -> Huawei Cloud compatible specs."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.flexible_workflow import (
    _extract_azure_vm_shape,
    _extract_azure_disk_shape,
    _extract_azure_mysql_shape,
    _normalize_billing_compute_spec,
    _normalize_billing_storage_spec,
    _normalize_billing_rds_spec,
    _match_price_component_by_spec,
    _billing_can_price_requirement,
    normalize_requirements,
    validate_quote_readiness,
    resolve_price_components,
    quote_items,
    summarize_quote,
    _extract_billing_lines,
    _group_billing_lines,
    _aggregate_billing_groups_fallback,
    _build_requirements_from_llm_aggregated_billing_items,
    _parse_csv_document,
)
from app.flexible_pricing import query_flexible_pricing_catalog
from app.models import (
    FlexibleQuoteContext,
    RequirementItem,
    PriceComponent,
    ComputeSpec,
    StorageSpec,
    GenericSpec,
)


# ---------------------------------------------------------------------------
# 1. test_extract_azure_vm_shape_d8_v3
# ---------------------------------------------------------------------------

class TestAzureVmShape:
    def test_extract_azure_vm_shape_d8_v3(self):
        result = _extract_azure_vm_shape("Virtual Machines serie Dv3 - D8 v3 - Este de EE. UU. 2")
        assert result is not None
        assert result["vcpu"] == 8
        assert result["memory_gib"] == 32.0
        assert result["source_shape"] == "D8 v3"
        assert result["family_hint"] == "general"

    def test_extract_azure_vm_shape_d2_v3(self):
        result = _extract_azure_vm_shape("Virtual Machines serie Dv3 - D2 v3 - Este de EE. UU. 2")
        assert result is not None
        assert result["vcpu"] == 2
        assert result["memory_gib"] == 8.0
        assert result["source_shape"] == "D2 v3"

    def test_extract_azure_vm_shape_f2s_v2(self):
        result = _extract_azure_vm_shape("Virtual Machines serie FSv2 - F2s v2 - Este de EE. UU. 2")
        assert result is not None
        assert result["vcpu"] == 2
        assert result["memory_gib"] == 4.0
        assert result["source_shape"] == "F2s v2"

    def test_extract_azure_vm_shape_b1ms(self):
        result = _extract_azure_vm_shape("MySQL Flexible Server Burstable BS Series Compute - B1MS")
        assert result is not None
        assert result["vcpu"] == 1
        assert result["memory_gib"] == 2.0
        assert result["source_shape"] == "B1MS"

    def test_extract_azure_vm_shape_unknown(self):
        result = _extract_azure_vm_shape("Some unknown VM shape XYZ")
        assert result is None

    def test_extract_azure_vm_shape_windows_variant(self):
        result = _extract_azure_vm_shape("Virtual Machines serie Dv3 de Windows - D2 v3 - Sur de Brasil")
        assert result is not None
        assert result["vcpu"] == 2
        assert result["source_shape"] == "D2 v3"


# ---------------------------------------------------------------------------
# 2. test_extract_azure_disk_shape_p10
# ---------------------------------------------------------------------------

class TestAzureDiskShape:
    def test_extract_azure_disk_shape_p10(self):
        result = _extract_azure_disk_shape("Discos administrados SSD premium - P10 - Este de EE. UU. 2")
        assert result is not None
        assert result["tier_hint"] == "high_io"
        assert result["capacity_gib"] == 128.0
        assert result["source_sku"] == "P10"

    def test_extract_azure_disk_shape_p4(self):
        result = _extract_azure_disk_shape("Discos administrados SSD premium - P4 - Este de EE. UU. 2")
        assert result is not None
        assert result["tier_hint"] == "high_io"
        assert result["capacity_gib"] == 32.0
        assert result["source_sku"] == "P4"

    def test_extract_azure_disk_shape_s10(self):
        result = _extract_azure_disk_shape("Discos administrados HDD estándar - S10 LRS - Sur de Brasil")
        assert result is not None
        assert result["tier_hint"] == "common"
        assert result["capacity_gib"] == 128.0
        assert result["source_sku"] == "S10"

    def test_extract_azure_disk_shape_snapshot_rejected(self):
        """Snapshots must NOT be treated as disk-month items."""
        result = _extract_azure_disk_shape(
            "Discos administrados HDD estándar - Instantáneas LRS - Este de EE. UU. 2",
            notes="vendor=azure",
        )
        assert result is None

    def test_extract_azure_disk_shape_premium_keyword(self):
        """Premium SSD without specific SKU should still get high_io tier."""
        result = _extract_azure_disk_shape("Managed Disk SSD premium")
        assert result is not None
        assert result["tier_hint"] == "high_io"

    def test_extract_azure_disk_shape_unknown(self):
        result = _extract_azure_disk_shape("Some random text without disk info")
        assert result is None


# ---------------------------------------------------------------------------
# 3. test_extract_azure_mysql_shape_1_vcore
# ---------------------------------------------------------------------------

class TestAzureMysqlShape:
    def test_extract_azure_mysql_shape_1_vcore(self):
        result = _extract_azure_mysql_shape(
            "Azure Database for MySQL Flexible Server Burstable BS Series Compute - 1 vCore"
        )
        assert result is not None
        assert result["engine"] == "mysql"
        assert result["vcore"] == 1
        assert result["family_hint"] == "general"

    def test_extract_azure_mysql_shape_b1ms(self):
        result = _extract_azure_mysql_shape(
            "MySQL Flexible Server Burstable BS Series Compute - B1MS"
        )
        assert result is not None
        assert result["engine"] == "mysql"
        assert result["source_shape"] == "B1MS"

    def test_extract_azure_mysql_storage_rejected(self):
        """MySQL storage items must NOT be treated as compute instances."""
        result = _extract_azure_mysql_shape(
            "Azure Database for MySQL Flexible Server Storage - Almacenamiento"
        )
        assert result is None

    def test_extract_azure_mysql_paid_io_rejected(self):
        result = _extract_azure_mysql_shape(
            "Azure Database for MySQL Flexible Server Storage - LRS Paid IO"
        )
        assert result is None

    def test_extract_azure_mysql_non_mysql_rejected(self):
        result = _extract_azure_mysql_shape("Some PostgreSQL compute instance")
        assert result is None


# ---------------------------------------------------------------------------
# 4. test_ecs_price_match_can_use_vcpu_memory_when_sku_string_differs
# ---------------------------------------------------------------------------

class TestEcsVcpuMemoryMatch:
    def test_ecs_price_match_can_use_vcpu_memory_when_sku_string_differs(self):
        """ECS with vcpu=8, memory_gib=32 from Azure D8 v3 should match a Huawei ECS."""
        catalog = query_flexible_pricing_catalog(product="ECS", region="chile", confirmed_only=True)
        if not catalog:
            pytest.skip("No ECS catalog items")

        req = RequirementItem(
            item_id="test::ecs",
            source_file="test.csv",
            source_sheet="csv",
            row_number=2,
            raw_product_name="ECS | D8 v3",
            quantity=6.0,
            quantity_source="billing_standardized",
            unit="instance hours",
            region="chile",
            normalized_product="ECS",
            spec=ComputeSpec(sku="D8 v3", vcpu=8, memory_gib=32.0),
        )
        matched = _match_price_component_by_spec(req, catalog)
        # Should find a match via vcpu+memory even though "D8 v3" != any Huawei SKU
        assert matched is not None, "ECS with vcpu=8, mem=32 should match a Huawei catalog item"

    def test_ecs_d2_v3_matches_via_vcpu_memory(self):
        """ECS with vcpu=2, memory_gib=8 from Azure D2 v3 should match."""
        catalog = query_flexible_pricing_catalog(product="ECS", region="chile", confirmed_only=True)
        if not catalog:
            pytest.skip("No ECS catalog items")

        req = RequirementItem(
            item_id="test::ecs",
            source_file="test.csv",
            source_sheet="csv",
            row_number=2,
            raw_product_name="ECS | D2 v3",
            quantity=1.0,
            quantity_source="billing_standardized",
            unit="instance hours",
            region="chile",
            normalized_product="ECS",
            spec=ComputeSpec(sku="D2 v3", vcpu=2, memory_gib=8.0),
        )
        matched = _match_price_component_by_spec(req, catalog)
        assert matched is not None, "ECS with vcpu=2, mem=8 should match a Huawei catalog item"


# ---------------------------------------------------------------------------
# 5. test_evs_price_match_uses_tier_and_capacity_hint
# ---------------------------------------------------------------------------

class TestEvsTierCapacityMatch:
    def test_evs_price_match_uses_tier_and_capacity_hint(self):
        """EVS with tier=high_io from Azure P10 should match high-io catalog item."""
        catalog = query_flexible_pricing_catalog(product="EVS", region="chile", confirmed_only=True)
        if not catalog:
            pytest.skip("No EVS catalog items")

        req = RequirementItem(
            item_id="test::evs",
            source_file="test.csv",
            source_sheet="csv",
            row_number=2,
            raw_product_name="EVS | P10",
            quantity=128.0,
            quantity_source="billing_standardized",
            unit="capacity gib month",
            region="chile",
            normalized_product="EVS",
            spec=StorageSpec(sku="P10", tier="high_io", capacity_gib=128.0),
        )
        matched = _match_price_component_by_spec(req, catalog)
        assert matched is not None
        assert "high-io" in ((matched.tier or "") + (matched.sku or "")).lower()

    def test_evs_snapshot_does_not_match(self):
        """EVS snapshot must NOT match disk catalog."""
        catalog = query_flexible_pricing_catalog(product="EVS", region="chile", confirmed_only=True)
        req = RequirementItem(
            item_id="test::evs-snap",
            source_file="test.csv",
            source_sheet="csv",
            row_number=2,
            raw_product_name="EVS | Snapshot",
            quantity=38.23,
            quantity_source="billing_standardized",
            unit="capacity gib month",
            region="chile",
            normalized_product="EVS",
            spec=StorageSpec(sku="Instantáneas LRS", tier="common", capacity_gib=38.23),
        )
        matched = _match_price_component_by_spec(req, catalog)
        assert matched is None, "Snapshot should not match EVS disk catalog"


# ---------------------------------------------------------------------------
# 6. test_rds_price_match_requires_mysql_engine
# ---------------------------------------------------------------------------

class TestRdsEngineMatch:
    def test_rds_price_match_requires_mysql_engine(self):
        """RDS with MySQL engine hint should match MySQL catalog item."""
        catalog = query_flexible_pricing_catalog(product="RDS", region="chile", confirmed_only=True)
        if not catalog:
            pytest.skip("No RDS catalog items")

        req = RequirementItem(
            item_id="test::rds",
            source_file="test.csv",
            source_sheet="csv",
            row_number=2,
            raw_product_name="RDS | MySQL 1 vCore",
            quantity=1.0,
            quantity_source="billing_standardized",
            unit="instance hours",
            region="chile",
            normalized_product="RDS",
            spec=GenericSpec(sku="mysql.1vcore", description="engine=mysql | vcore=1 | family=general"),
        )
        matched = _match_price_component_by_spec(req, catalog)
        assert matched is not None, "RDS with MySQL engine hint should match"
        assert "mysql" in ((matched.sku or "") + " " + (matched.family or "")).lower()

    def test_rds_without_engine_stays_unquoted(self):
        """RDS without engine hint must NOT match."""
        catalog = query_flexible_pricing_catalog(product="RDS", region="chile", confirmed_only=True)
        req = RequirementItem(
            item_id="test::rds",
            source_file="test.csv",
            source_sheet="csv",
            row_number=2,
            raw_product_name="RDS | Unknown DB",
            quantity=1.0,
            quantity_source="billing_standardized",
            unit="instance hours",
            region="chile",
            normalized_product="RDS",
            spec=GenericSpec(sku="unknown-db", description="some database"),
        )
        matched = _match_price_component_by_spec(req, catalog)
        assert matched is None, "RDS without engine hint should not match"


# ---------------------------------------------------------------------------
# 7. test_real_billing_quote_lines_increase_without_reintroducing_usage_mispricing
# ---------------------------------------------------------------------------

class TestRealAzureImprovedCoverage:
    def test_real_billing_quote_lines_increase_without_reintroducing_usage_mispricing(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Real Azure file: quote lines should increase from 9, total from $402, but stay < $100k."""
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)

        csv_path = Path("/root/SMBReference/CGE/azure Billing_invoice_transactions.csv")
        doc = _parse_csv_document(csv_path.read_bytes(), "azure_billing.csv")

        lines = _extract_billing_lines(doc)
        groups = _group_billing_lines(lines)
        agg_items = _aggregate_billing_groups_fallback(groups)
        requirements = _build_requirements_from_llm_aggregated_billing_items(agg_items)

        norm_state = {"requirements": requirements, "quote_context": {"region": "chile"}, "audit_log": [], "progress_callback": None}
        norm_result = normalize_requirements(norm_state)

        catalog = [item.model_dump() for item in query_flexible_pricing_catalog(region="chile")]
        val_state = {"requirements": norm_result["requirements"], "quote_context": {"region": "chile"}, "price_catalog": catalog, "matched_products": [], "understanding": {"profile": {}}, "audit_log": [], "progress_callback": None}
        val_result = validate_quote_readiness(val_state)

        res_state = {"quote_ready_items": val_result["quote_ready_items"], "price_catalog": catalog, "unquoted_items": val_result["unquoted_items"], "audit_log": [], "progress_callback": None}
        res_result = resolve_price_components(res_state)

        quote_state = {"quote_ready_items": val_result["quote_ready_items"], "price_components": res_result["price_components"], "audit_log": [], "progress_callback": None}
        quote_result = quote_items(quote_state)

        sum_state = {"requirements": norm_result["requirements"], "quote_ready_items": val_result["quote_ready_items"], "quote_lines": quote_result["quote_lines"], "quote_blockers": val_result["quote_blockers"], "unquoted_items": res_result["unquoted_items"], "quote_context": {"region": "chile"}, "audit_log": [], "progress_callback": None}
        sum_result = summarize_quote(sum_state)
        total = sum_result["summary"]["total_monthly_price"]

        # Coverage should have increased
        assert len(quote_result["quote_lines"]) > 9, "Quote lines should increase from 9 with spec normalization"
        assert total > 402, f"Total ${total:,.2f} should exceed $402.86 baseline"

        # But no massive overstatement
        assert total < 100000, f"Total ${total:,.2f} is suspiciously high — usage mispricing?"

        # ECS should now have quoted lines
        ecs_lines = [ql for ql in quote_result["quote_lines"] if ql.get("product") == "ECS"]
        assert len(ecs_lines) > 0, "ECS should have quoted lines after spec normalization"


# ---------------------------------------------------------------------------
# 8. test_billing_export_detail_rows_show_enriched_spec_hint
# ---------------------------------------------------------------------------

class TestExportEnrichedSpec:
    def test_billing_export_detail_rows_show_enriched_spec_hint(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """After spec normalization, detail rows should show enriched spec hints."""
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)

        from app.flexible_workflow import (
            _build_billing_detail_rows,
            export_flexible_workbook,
        )
        from io import BytesIO
        from openpyxl import load_workbook

        csv_path = Path("/root/SMBReference/CGE/azure Billing_invoice_transactions.csv")
        doc = _parse_csv_document(csv_path.read_bytes(), "azure_billing.csv")

        lines = _extract_billing_lines(doc)
        groups = _group_billing_lines(lines)
        agg_items = _aggregate_billing_groups_fallback(groups)
        requirements = _build_requirements_from_llm_aggregated_billing_items(agg_items)

        norm_state = {"requirements": requirements, "quote_context": {"region": "chile"}, "audit_log": [], "progress_callback": None}
        norm_result = normalize_requirements(norm_state)

        catalog = [item.model_dump() for item in query_flexible_pricing_catalog(region="chile")]
        val_state = {"requirements": norm_result["requirements"], "quote_context": {"region": "chile"}, "price_catalog": catalog, "matched_products": [], "understanding": {"profile": {}}, "audit_log": [], "progress_callback": None}
        val_result = validate_quote_readiness(val_state)

        res_state = {"quote_ready_items": val_result["quote_ready_items"], "price_catalog": catalog, "unquoted_items": val_result["unquoted_items"], "audit_log": [], "progress_callback": None}
        res_result = resolve_price_components(res_state)

        quote_state = {"quote_ready_items": val_result["quote_ready_items"], "price_components": res_result["price_components"], "audit_log": [], "progress_callback": None}
        quote_result = quote_items(quote_state)

        sum_state = {"requirements": norm_result["requirements"], "quote_ready_items": val_result["quote_ready_items"], "quote_lines": quote_result["quote_lines"], "quote_blockers": val_result["quote_blockers"], "unquoted_items": res_result["unquoted_items"], "quote_context": {"region": "chile"}, "audit_log": [], "progress_callback": None}
        sum_result = summarize_quote(sum_state)

        export_state = {"requirements": norm_result["requirements"], "quote_ready_items": val_result["quote_ready_items"], "quote_lines": quote_result["quote_lines"], "quote_blockers": val_result["quote_blockers"], "unquoted_items": res_result["unquoted_items"], "price_components": res_result["price_components"], "summary": sum_result["summary"], "mapped_billing_resources": [], "billing_lines": lines, "standardized_billing_resources": [], "llm_aggregated_billing_items": agg_items, "quote_context": {"region": "chile"}, "audit_log": [], "progress_callback": None}

        detail_rows = _build_billing_detail_rows(export_state)
        # At least some detail rows should have non-empty huawei_spec_hint
        with_spec = [r for r in detail_rows if r.get("huawei_spec_hint")]
        assert len(with_spec) > 0, "Detail rows should have enriched spec hints"


# ---------------------------------------------------------------------------
# 9. test_unknown_vm_shape_stays_manual_review
# ---------------------------------------------------------------------------

class TestUnknownVmShape:
    def test_unknown_vm_shape_stays_manual_review(self):
        """VM with unrecognized shape should not get a spec and remain unquoted."""
        req = RequirementItem(
            item_id="test::ecs",
            source_file="test.csv",
            source_sheet="csv",
            row_number=2,
            raw_product_name="ECS | Unknown Shape XYZ",
            quantity=1.0,
            quantity_source="billing_standardized",
            unit="instance hours",
            region="chile",
            normalized_product="ECS",
            spec=ComputeSpec(sku="Unknown Shape XYZ"),
        )
        result = _normalize_billing_compute_spec(req)
        # Should return None since shape is unknown
        assert result is None


# ---------------------------------------------------------------------------
# 10. test_mysql_storage_usage_remains_unquoted_after_spec_normalization
# ---------------------------------------------------------------------------

class TestMysqlStorageStillUnquoted:
    def test_mysql_storage_usage_remains_unquoted_after_spec_normalization(self):
        """MySQL storage GB/month must remain unquoted even after spec normalization."""
        req = RequirementItem(
            item_id="test::rds-storage",
            source_file="test.csv",
            source_sheet="csv",
            row_number=2,
            raw_product_name="RDS | MySQL Storage",
            quantity=2296.0,
            quantity_source="billing_standardized",
            unit="capacity gib month",
            region="chile",
            normalized_product="RDS",
            spec=GenericSpec(sku="MySQL Storage", description="MySQL Flexible Server Storage"),
        )
        comp = PriceComponent(
            product="RDS", region="chile", sku="mysql.s2.medium", family="MySQL",
            tier=None, billing_mode="monthly", unit="instance-month",
            price=39.5, currency="USD", source_url="https://test",
            captured_at="2026-01-01", confirmed=True, status="confirmed",
        )
        can_price, reason = _billing_can_price_requirement(req, comp)
        assert can_price is False, "MySQL storage GB/month must not price against RDS instance-month"
