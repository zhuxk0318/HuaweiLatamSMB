"""Phase C tests: billing → Huawei product/spec mapping, 1→N support, RequirementItem generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.flexible_workflow import (
    _detect_billing_document,
    _extract_billing_lines,
    _standardize_billing_lines,
    _map_standardized_billing_resources_to_huawei,
    _map_standardized_billing_resource,
    _infer_huawei_product_from_resource_kind,
    _build_huawei_spec_hint,
    _build_requirements_from_mapped_billing_resources,
    _parse_csv_document,
    extract_requirement_items,
)
from app.models import FlexibleQuoteContext, ComputeSpec, StorageSpec, GenericSpec


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


def _make_standardized_resource(overrides: dict | None = None) -> dict:
    """Build a minimal standardized billing resource for testing."""
    base = {
        "resource_kind": "vm",
        "resource_subtype": "Virtual Machines serie Dv3",
        "spec_hint": "D8 v3",
        "quantity_interpretation": "instance_hours",
        "derived_quantity_rule": "hours_div_744",
        "operating_system_hint": None,
        "deployment_model_hint": None,
        "confidence": 0.5,
        "rationale": "fallback keyword classification",
        "needs_manual_review": False,
        "product_family": "Compute",
        "product_type": "Virtual Machines serie Dv3",
        "product_sku": "D8 v3",
        "unit_type": "1 hora de proceso",
        "vendor": "azure",
        "source_file": "test.csv",
        "source_sheet": "csv",
        "source_line_numbers": [2],
        "service_period": "3/1/2026 - 3/31/2026",
        "transaction_types": ["Usage charges"],
        "raw_quantity": 4468.934022,
        "derived_quantity": 6.0039,
        "derived_unit": "instance hours",
        "amount": 1626.77,
        "currency": "USD",
        "region_hint": "",
    }
    if overrides:
        base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. test_vm_standardized_resource_maps_to_ecs
# ---------------------------------------------------------------------------

class TestVmMapping:
    def test_vm_standardized_resource_maps_to_ecs(self):
        res = _make_standardized_resource({"resource_kind": "vm"})
        mapped = _map_standardized_billing_resource(res, 0)
        assert len(mapped) == 1
        assert mapped[0]["huawei_product"] == "ECS"
        assert mapped[0]["mapping_method"] == "direct_kind_map"

        # Build RequirementItem and check
        requirements = _build_requirements_from_mapped_billing_resources(mapped)
        assert len(requirements) == 1
        req = requirements[0]
        assert req["normalized_product"] == "ECS"
        assert req["raw_product_name"].startswith("ECS")
        # spec should be ComputeSpec with sku
        assert "sku" in req["spec"]
        assert req["spec"]["sku"] == "D8 v3"

    def test_vm_with_windows_hint(self):
        res = _make_standardized_resource({
            "resource_kind": "vm",
            "product_type": "Virtual Machines serie Dv3 de Windows",
            "product_sku": "D8 v3",
            "operating_system_hint": "windows",
        })
        mapped = _map_standardized_billing_resource(res, 0)
        assert mapped[0]["huawei_product"] == "ECS"


# ---------------------------------------------------------------------------
# 2. test_mysql_standardized_resource_maps_to_rds
# ---------------------------------------------------------------------------

class TestDatabaseMapping:
    def test_mysql_standardized_resource_maps_to_rds(self):
        res = _make_standardized_resource({
            "resource_kind": "database",
            "resource_subtype": "Azure Database for MySQL Flexible Server",
            "product_type": "Azure Database for MySQL Flexible Server",
            "product_sku": "MySQL Flexible Server Burstable BS Series - 1 vCore",
            "spec_hint": "MySQL Flexible Server Burstable BS Series - 1 vCore",
        })
        mapped = _map_standardized_billing_resource(res, 0)
        assert len(mapped) == 1
        assert mapped[0]["huawei_product"] == "RDS"

        requirements = _build_requirements_from_mapped_billing_resources(mapped)
        req = requirements[0]
        assert req["normalized_product"] == "RDS"
        # spec description should contain MySQL hint
        desc = req["spec"].get("description", "")
        assert "mysql" in desc.lower() or "MySQL" in desc


# ---------------------------------------------------------------------------
# 3. test_blob_or_table_maps_to_obs
# ---------------------------------------------------------------------------

class TestObjectStorageMapping:
    def test_blob_maps_to_obs(self):
        res = _make_standardized_resource({
            "resource_kind": "object_storage",
            "resource_subtype": "Blob Storage",
            "product_type": "Blob Storage",
            "product_sku": "Blob Storage",
            "spec_hint": "Blob Storage",
            "quantity_interpretation": "capacity_gib_month",
        })
        mapped = _map_standardized_billing_resource(res, 0)
        assert mapped[0]["huawei_product"] == "OBS"

    def test_blob_ops_maps_to_obs_generic(self):
        """Non-capacity blob usage should still map to OBS but with GenericSpec."""
        res = _make_standardized_resource({
            "resource_kind": "object_storage",
            "resource_subtype": "Blob Storage",
            "product_type": "Blob Storage",
            "product_sku": "Blob Storage",
            "spec_hint": "Blob Storage",
            "quantity_interpretation": "ops_10k",
        })
        mapped = _map_standardized_billing_resource(res, 0)
        assert mapped[0]["huawei_product"] == "OBS"
        # spec should be GenericSpec (not StorageSpec) for ops
        spec = mapped[0]["huawei_spec_hint"]
        assert "description" in spec  # GenericSpec has description


# ---------------------------------------------------------------------------
# 4. test_backup_maps_to_cbr
# ---------------------------------------------------------------------------

class TestBackupMapping:
    def test_backup_maps_to_cbr(self):
        res = _make_standardized_resource({
            "resource_kind": "backup",
            "resource_subtype": "Backup",
            "product_type": "Backup",
            "product_sku": "Backup - Estándar",
            "spec_hint": "Backup - Estándar",
        })
        mapped = _map_standardized_billing_resource(res, 0)
        assert mapped[0]["huawei_product"] == "CBR"
        assert mapped[0]["mapping_method"] == "direct_kind_map"


# ---------------------------------------------------------------------------
# 5. test_waf_gateway_splits_into_elb_and_waf
# ---------------------------------------------------------------------------

class TestCompositeMapping:
    def test_waf_gateway_splits_into_elb_and_waf(self):
        res = _make_standardized_resource({
            "resource_kind": "load_balancer",
            "resource_subtype": "Application Gateway WAF v2",
            "product_type": "Application Gateway WAF v2",
            "product_sku": "Application Gateway WAF v2",
            "spec_hint": "Application Gateway WAF v2",
        })
        mapped = _map_standardized_billing_resource(res, 0)
        assert len(mapped) == 2, f"Expected 2 mapped resources, got {len(mapped)}"
        products = {m["huawei_product"] for m in mapped}
        assert products == {"ELB", "WAF"}
        assert all(m["mapping_method"] == "composite_split" for m in mapped)

        # Both should produce requirements
        requirements = _build_requirements_from_mapped_billing_resources(mapped)
        assert len(requirements) == 2
        norm_products = {r["normalized_product"] for r in requirements}
        assert norm_products == {"ELB", "WAF"}


# ---------------------------------------------------------------------------
# 6. test_unsupported_resource_remains_unmapped
# ---------------------------------------------------------------------------

class TestUnsupportedMapping:
    def test_developer_tool_remains_unmapped(self):
        res = _make_standardized_resource({
            "resource_kind": "developer_tool",
            "resource_subtype": "API Management",
            "product_type": "API Management",
            "product_sku": "API Management - Desarrollador",
            "spec_hint": "API Management - Desarrollador",
        })
        mapped = _map_standardized_billing_resource(res, 0)
        assert len(mapped) == 1
        assert mapped[0]["huawei_product"] is None
        assert mapped[0]["needs_manual_review"] is True
        assert mapped[0]["mapping_method"] == "unsupported"

        requirements = _build_requirements_from_mapped_billing_resources(mapped)
        req = requirements[0]
        assert req["normalized_product"] is None

    def test_data_resource_remains_unmapped(self):
        res = _make_standardized_resource({
            "resource_kind": "data",
            "resource_subtype": "Fabric Capacity Reservation",
            "product_type": "Fabric Capacity Reservation",
            "product_sku": "Fabric Capacity Reservation",
            "spec_hint": "Fabric Capacity Reservation",
        })
        mapped = _map_standardized_billing_resource(res, 0)
        assert mapped[0]["huawei_product"] is None
        assert mapped[0]["needs_manual_review"] is True


# ---------------------------------------------------------------------------
# 7. test_non_billing_documents_still_unchanged
# ---------------------------------------------------------------------------

class TestNonBillingCompat:
    def test_non_billing_documents_still_unchanged(self):
        """Non-billing documents must not be detected as billing."""
        doc = {
            "filename": "requirements.xlsx",
            "sheet": "Sheet1",
            "columns": ["product", "quantity", "region", "spec"],
            "rows": [{"product": "ECS", "quantity": "2", "region": "mexico", "spec": "4vCPU"}],
        }
        assert _detect_billing_document(doc) is False


# ---------------------------------------------------------------------------
# 8. test_mapped_requirements_preserve_provenance_notes
# ---------------------------------------------------------------------------

class TestProvenance:
    def test_mapped_requirements_preserve_provenance_notes(self):
        res = _make_standardized_resource({"resource_kind": "vm"})
        mapped = _map_standardized_billing_resource(res, 0)
        requirements = _build_requirements_from_mapped_billing_resources(mapped)
        req = requirements[0]
        notes = req["notes"]
        assert "vendor=azure" in notes
        assert "family=Compute" in notes
        assert "lines=[2]" in notes
        assert "mapping=direct_kind_map" in notes
        assert "confidence=" in notes
        assert "src_id=" in notes

    def test_unsupported_preserves_provenance(self):
        res = _make_standardized_resource({"resource_kind": "developer_tool"})
        mapped = _map_standardized_billing_resource(res, 0)
        requirements = _build_requirements_from_mapped_billing_resources(mapped)
        notes = requirements[0]["notes"]
        assert "vendor=azure" in notes
        assert "mapping=unsupported" in notes


# ---------------------------------------------------------------------------
# 9. test_extract_requirement_items_sets_mapped_billing_resources_in_state
# ---------------------------------------------------------------------------

class TestStateIntegration:
    def test_extract_requirement_items_sets_mapped_billing_resources_in_state(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        csv = (
            "SEP=,\r\n"
            "DATE (UTC),PRODUCT FAMILY,PRODUCT TYPE,PRODUCT SKU,UNIT TYPE,QUANTITY,\r\n"
            '"4/3/2026","Compute","Virtual Machines serie Dv3","D8 v3","1 hora","744",\r\n'
        ).encode("utf-8-sig")
        doc = _parse_csv_document(csv, "test.csv")
        state = {
            "parsed_documents": [doc],
            "quote_context": {},
            "audit_log": [],
            "progress_callback": None,
        }
        result = extract_requirement_items(state)
        assert "mapped_billing_resources" in result
        assert "billing_lines" in result
        assert "standardized_billing_resources" in result
        assert len(result["mapped_billing_resources"]) > 0
        assert len(result["requirements"]) > 0
        # The requirement should have normalized_product = ECS
        req = result["requirements"][0]
        assert req["normalized_product"] == "ECS"


# ---------------------------------------------------------------------------
# Direct mapping coverage
# ---------------------------------------------------------------------------

class TestDirectMappings:
    @pytest.mark.parametrize("kind,product", [
        ("vm", "ECS"),
        ("disk", "EVS"),
        ("file_storage", "SFS Turbo"),
        ("object_storage", "OBS"),
        ("database", "RDS"),
        ("vpn_gateway", "VPN"),
        ("public_ip", "EIP"),
        ("load_balancer", "ELB"),
        ("waf", "WAF"),
        ("backup", "CBR"),
        ("security", "HSS"),
    ])
    def test_direct_kind_mapping(self, kind: str, product: str):
        assert _infer_huawei_product_from_resource_kind(kind) == product

    @pytest.mark.parametrize("kind", [
        "developer_tool", "monitoring", "containers", "data",
        "private_link", "unsupported",
    ])
    def test_unsupported_kind_mapping(self, kind: str):
        assert _infer_huawei_product_from_resource_kind(kind) is None


# ---------------------------------------------------------------------------
# Disk tier hint
# ---------------------------------------------------------------------------

class TestDiskTierHint:
    def test_premium_ssd_tier(self):
        from app.flexible_workflow import _infer_disk_tier_hint
        assert _infer_disk_tier_hint("Discos administrados SSD premium") == "high_io"

    def test_standard_hdd_tier(self):
        from app.flexible_workflow import _infer_disk_tier_hint
        assert _infer_disk_tier_hint("Discos administrados HDD estándar") == "common"

    def test_no_tier_match(self):
        from app.flexible_workflow import _infer_disk_tier_hint
        assert _infer_disk_tier_hint("Some random disk") is None


# ---------------------------------------------------------------------------
# Real Azure file: mapping statistics
# ---------------------------------------------------------------------------

class TestRealAzureFileMapping:
    def test_real_azure_file_mapping_stats(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        lines = _extract_billing_lines(azure_document)
        standardized = _standardize_billing_lines(lines, FlexibleQuoteContext())
        mapped = _map_standardized_billing_resources_to_huawei(standardized)
        requirements = _build_requirements_from_mapped_billing_resources(mapped)

        mapped_count = sum(1 for m in mapped if m["huawei_product"] is not None)
        unsupported_count = sum(1 for m in mapped if m["huawei_product"] is None)

        # Must have some successful mappings
        assert mapped_count > 0
        # Must have some unsupported (developer_tool, data, etc.)
        assert unsupported_count > 0
        # Requirements count should match mapped count
        assert len(requirements) == len(mapped)
        # At least one ECS requirement
        ecs_reqs = [r for r in requirements if r["normalized_product"] == "ECS"]
        assert len(ecs_reqs) > 0
