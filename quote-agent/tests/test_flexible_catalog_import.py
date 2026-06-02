"""Tests for flexible_catalog_import tool.

Tests use row-level dict input (not real xlsx) to keep fixtures lightweight.
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

# Add scripts dir to path so we can import the module
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from flexible_catalog_import import (
    NormalizedRow,
    ImportIssue,
    ImportResult,
    PRODUCT_MAPPING,
    SPEC_MAPPING,
    REGION_MAPPING,
    SUPPORTED_PRODUCTS,
    SUPPORTED_REGIONS,
    _parse_price,
    _parse_price_with_unit,
    _expand_regions,
    normalize_row,
    _validate_result,
    validate_catalog,
    generate_patch,
    patch_dry_run_summary,
)

CATALOG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "flexible-pricing-catalog.json"
)


# ---------------------------------------------------------------------------
# Price parsing tests
# ---------------------------------------------------------------------------

class TestParsePrice:
    def test_usd_number(self):
        price, unit = _parse_price("USD 0.076")
        assert price == 0.076
        assert unit == ""

    def test_usd_large_number(self):
        price, unit = _parse_price("USD 1,656")
        assert price == 1656.0

    def test_free(self):
        price, unit = _parse_price("Free")
        assert price == 0.0
        assert unit == "free"

    def test_dash_unavailable(self):
        price, unit = _parse_price("--")
        assert price is None
        assert unit == "unavailable"

    def test_na(self):
        price, unit = _parse_price("N/A")
        assert price is None

    def test_none(self):
        price, unit = _parse_price(None)
        assert price is None

    def test_empty(self):
        price, unit = _parse_price("")
        assert price is None


class TestParsePriceWithUnit:
    def test_price_per_gb_hour(self):
        price, unit = _parse_price_with_unit("USD 0.000064 Price per GB-hour")
        assert price == 0.000064
        assert unit == "GB-hour"

    def test_price_per_gateway(self):
        price, unit = _parse_price_with_unit("USD 0.33 Price per gateway")
        assert price == 0.33
        assert unit == "gateway"

    def test_price_per_port(self):
        price, unit = _parse_price_with_unit("USD 1,035 Price per port")
        assert price == 1035.0
        assert unit == "port"


# ---------------------------------------------------------------------------
# Region expansion tests
# ---------------------------------------------------------------------------

class TestExpandRegions:
    def test_single_santiago(self):
        regions, warnings = _expand_regions("Santiago")
        assert regions == ["chile"]
        assert warnings == []

    def test_santiago_typo(self):
        regions, warnings = _expand_regions("Satiago")
        assert regions == ["chile"]
        assert warnings == []

    def test_sao_paulo(self):
        regions, warnings = _expand_regions("Sao Paulo")
        assert regions == ["brazil"]
        assert warnings == []

    def test_mexico(self):
        regions, warnings = _expand_regions("Mexico")
        assert regions == ["mexico"]
        assert warnings == []

    def test_multi_santiago_mexico(self):
        regions, warnings = _expand_regions("Santiago&Mexico")
        assert regions == ["chile", "mexico"]
        assert warnings == []

    def test_multi_all_three(self):
        regions, warnings = _expand_regions("Santiago&Mexico&Sao Paulo")
        assert regions == ["chile", "mexico", "brazil"]
        assert warnings == []

    def test_spaces_around_ampersand(self):
        """'Santiago & Mexico' with spaces should expand correctly."""
        regions, warnings = _expand_regions("Santiago & Mexico")
        assert regions == ["chile", "mexico"]
        assert warnings == []

    def test_spaces_all_three(self):
        """'Santiago & Mexico & Sao Paulo' should expand correctly."""
        regions, warnings = _expand_regions("Santiago & Mexico & Sao Paulo")
        assert regions == ["chile", "mexico", "brazil"]
        assert warnings == []

    def test_unknown_token_warning(self):
        """Unknown region token should produce a warning."""
        regions, warnings = _expand_regions("Santiago&Tokyo")
        assert regions == ["chile"]
        assert len(warnings) == 1
        assert "Tokyo" in warnings[0] or "tokyo" in warnings[0]

    def test_empty_input(self):
        regions, warnings = _expand_regions("")
        assert regions == []
        assert warnings == []

    def test_no_duplicate_regions(self):
        """If the same region appears twice after expansion, deduplicate."""
        regions, warnings = _expand_regions("Santiago&Satiago")
        assert regions == ["chile"]
        assert warnings == []


# ---------------------------------------------------------------------------
# Product mapping tests
# ---------------------------------------------------------------------------

class TestProductMapping:
    def test_evs(self):
        assert PRODUCT_MAPPING["Elastic Volume Service(EVS)"] == "EVS"

    def test_obs(self):
        assert PRODUCT_MAPPING["Object Storage Service(OBS)"] == "OBS"

    def test_sfs_turbo(self):
        assert PRODUCT_MAPPING["Scalable File Service Turbo(SFS Turbo)"] == "SFS Turbo"

    def test_vpn(self):
        assert PRODUCT_MAPPING["Virtual Private Network"] == "VPN"

    def test_dc(self):
        assert PRODUCT_MAPPING["Direct Connect As A Service"] == "Direct Connect as a Service"

    def test_rds_compute(self):
        assert PRODUCT_MAPPING["Relational Database Service(RDS)-Compute"] == "RDS"

    def test_rds_storage(self):
        assert PRODUCT_MAPPING["Relational Database Service(RDS)-Storage"] == "RDS"

    def test_dds_compute(self):
        assert PRODUCT_MAPPING["Document Database Service-Compute"] == "DDS"


# ---------------------------------------------------------------------------
# Spec/SKU mapping tests
# ---------------------------------------------------------------------------

class TestSpecMapping:
    def test_evs_high_io(self):
        assert SPEC_MAPPING["EVS"]["High I/O"] == "high-io"

    def test_evs_ultra_high_io(self):
        assert SPEC_MAPPING["EVS"]["Ultra-high I/O"] == "ultra-high-io"

    def test_evs_gpssd_v2(self):
        assert SPEC_MAPPING["EVS"]["General Purpose SSD V2"] == "gpssd-v2"

    def test_evs_gpssd(self):
        assert SPEC_MAPPING["EVS"]["General Purpose SSD"] == "gpssd"

    def test_evs_sas(self):
        assert SPEC_MAPPING["EVS"]["Common I/O"] == "sas"

    def test_obs_standard(self):
        assert SPEC_MAPPING["OBS"]["standard"] == "obs-standard"

    def test_obs_infrequent(self):
        assert SPEC_MAPPING["OBS"]["infrequent-access"] == "obs-infrequent-access"

    def test_sfs_turbo_20(self):
        assert SPEC_MAPPING["SFS Turbo"]["20MB/s/TiB"] == "sfs-turbo-20mbps-per-tib"

    def test_sfs_turbo_40(self):
        assert SPEC_MAPPING["SFS Turbo"]["40MB/s/TiB"] == "sfs-turbo-40mbps-per-tib"

    def test_sfs_turbo_125(self):
        assert SPEC_MAPPING["SFS Turbo"]["125MB/s/TiB"] == "sfs-turbo-125mbps-per-tib"

    def test_sfs_turbo_250(self):
        assert SPEC_MAPPING["SFS Turbo"]["250MB/s/TiB"] == "sfs-turbo-250mbps-per-tib"

    def test_nat_small(self):
        assert SPEC_MAPPING["NAT Gateway"]["Small"] == "nat-small"

    def test_nat_middle(self):
        assert SPEC_MAPPING["NAT Gateway"]["Middle"] == "nat-middle"

    def test_nat_large(self):
        assert SPEC_MAPPING["NAT Gateway"]["Large"] == "nat-large"

    def test_vpn_basic(self):
        assert SPEC_MAPPING["VPN"]["Basic"] == "vpn-basic"

    def test_vpn_professional_1(self):
        assert SPEC_MAPPING["VPN"]["Professional 1"] == "vpn-professional-1"

    def test_vpn_professional_2(self):
        assert SPEC_MAPPING["VPN"]["Professional 2"] == "vpn-professional-2"

    def test_dc_1g(self):
        assert SPEC_MAPPING["Direct Connect as a Service"]["1GE"] == "dcas-1g"

    def test_dc_10g(self):
        assert SPEC_MAPPING["Direct Connect as a Service"]["10GE"] == "dcas-10g"

    def test_dc_100g(self):
        assert SPEC_MAPPING["Direct Connect as a Service"]["100GE"] == "dcas-100g"


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestValidation:
    def test_conflict_detection(self):
        """Same product+sku+region+mode with different prices → error."""
        result = ImportResult()
        result.normalized_rows = [
            normalize_row("EVS", "chile", "Santiago&Mexico", "high-io", "monthly", "GB-month", 0.051),
            normalize_row("EVS", "chile", "Santiago&Mexico", "high-io", "monthly", "GB-month", 0.099),
        ]
        _validate_result(result)
        assert result.has_errors, "Should detect price conflict"
        assert result.has_conflicts

    def test_no_conflict_same_price(self):
        """Same product+sku+region+mode with same price → no error."""
        result = ImportResult()
        result.normalized_rows = [
            normalize_row("EVS", "chile", "Santiago&Mexico", "high-io", "monthly", "GB-month", 0.051),
            normalize_row("EVS", "chile", "Santiago&Mexico", "high-io", "monthly", "GB-month", 0.051),
        ]
        _validate_result(result)
        assert not result.has_errors

    def test_empty_sku_error(self):
        """Empty SKU should be an error."""
        result = ImportResult()
        result.normalized_rows = [
            normalize_row("EVS", "chile", "Santiago&Mexico", "", "monthly", "GB-month", 0.051),
        ]
        _validate_result(result)
        assert result.has_errors

    def test_unsupported_region_warning(self):
        """Unsupported region should be a warning."""
        result = ImportResult()
        result.normalized_rows = [
            normalize_row("EVS", "tokyo", "Tokyo", "high-io", "monthly", "GB-month", 0.051),
        ]
        _validate_result(result)
        assert any(i.severity == "warning" for i in result.issues)


# ---------------------------------------------------------------------------
# Catalog consistency validation tests
# ---------------------------------------------------------------------------

class TestCatalogConsistency:
    def test_valid_catalog(self):
        """Current catalog should pass validation with no errors."""
        issues = validate_catalog(CATALOG_PATH)
        errors = [i for i in issues if i.severity == "error"]
        assert not errors, f"Catalog has errors: {[i.message for i in errors]}"

    def test_missing_sku_warning(self):
        """A catalog missing critical SKUs should produce warnings."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "generated_at": "2026-01-01T00:00:00Z",
                "items": [
                    {"product": "EVS", "region": "chile", "sku": "high-io", "family": "EVS",
                     "tier": "high-io", "billing_mode": "monthly", "unit": "GB-month",
                     "price": 0.051, "currency": "USD"},
                ],
            }, f)
            f.flush()
            issues = validate_catalog(f.name)
        os.unlink(f.name)
        # Should have warnings about missing SKUs for EVS/chile and other products
        warnings = [i for i in issues if i.severity == "warning"]
        assert len(warnings) > 0, "Should warn about missing SKUs"

    def test_critical_products_exist(self):
        """All critical products must be present in the catalog."""
        with open(CATALOG_PATH) as f:
            data = json.load(f)
        products = {item["product"] for item in data["items"]}
        critical = {"EVS", "OBS", "SFS Turbo", "EIP", "ELB", "NAT Gateway", "VPN",
                    "Direct Connect as a Service", "RDS", "DDS", "DWS"}
        missing = critical - products
        assert not missing, f"Missing critical products: {sorted(missing)}"

    def test_critical_skus_per_region(self):
        """Critical SKUs must exist for each supported region."""
        with open(CATALOG_PATH) as f:
            data = json.load(f)
        critical_skus = {
            "EVS": {"gpssd", "gpssd-v2", "high-io", "ultra-high-io", "sas"},
            "OBS": {"obs-standard", "obs-infrequent-access"},
            "SFS Turbo": {"sfs-turbo-20mbps-per-tib", "sfs-turbo-40mbps-per-tib"},
            "NAT Gateway": {"nat-small", "nat-middle", "nat-large"},
            "VPN": {"vpn-basic", "vpn-professional-1", "vpn-professional-2"},
            "Direct Connect as a Service": {"dcas-1g", "dcas-10g", "dcas-100g"},
        }
        by_pr = {}
        for item in data["items"]:
            by_pr.setdefault((item["product"], item["region"]), set()).add(item["sku"])
        missing = []
        for product, skus in critical_skus.items():
            for region in SUPPORTED_REGIONS:
                present = by_pr.get((product, region), set())
                for sku in skus - present:
                    missing.append(f"{product}/{region}/{sku}")
        assert not missing, f"Missing critical SKUs: {missing[:10]}"

    def test_region_coverage(self):
        """All three LATAM regions must have at least some pricing data."""
        with open(CATALOG_PATH) as f:
            data = json.load(f)
        regions = {item["region"] for item in data["items"]}
        for region in SUPPORTED_REGIONS:
            assert region in regions, f"Region '{region}' not found in catalog"


# ---------------------------------------------------------------------------
# Catalog schema integrity tests
# ---------------------------------------------------------------------------

class TestCatalogSchema:
    def test_all_items_have_required_fields(self):
        """Every catalog item must have product, sku, region, price."""
        with open(CATALOG_PATH) as f:
            data = json.load(f)
        for idx, item in enumerate(data["items"]):
            assert item.get("product"), f"Item {idx}: missing product"
            assert item.get("sku"), f"Item {idx}: missing sku"
            assert item.get("region"), f"Item {idx}: missing region"
            assert "price" in item, f"Item {idx}: missing price"
            assert isinstance(item["price"], (int, float)), f"Item {idx}: price not numeric"

    def test_no_unknown_regions(self):
        """All region values must be in SUPPORTED_REGIONS."""
        with open(CATALOG_PATH) as f:
            data = json.load(f)
        for item in data["items"]:
            assert item["region"] in SUPPORTED_REGIONS, \
                f"Unknown region '{item['region']}' for {item['product']}/{item['sku']}"

    def test_no_duplicate_conflicts(self):
        """No two items with same (product, sku, region, billing_mode) should
        have different prices."""
        with open(CATALOG_PATH) as f:
            data = json.load(f)
        seen: dict[tuple, float] = {}
        for item in data["items"]:
            key = (item["product"], item["sku"], item["region"], item.get("billing_mode"))
            price = item["price"]
            if key in seen:
                assert abs(seen[key] - price) < 0.001, \
                    f"Price conflict at {key}: {seen[key]} vs {price}"
            seen[key] = price

    def test_catalog_has_items(self):
        """Catalog must not be empty."""
        with open(CATALOG_PATH) as f:
            data = json.load(f)
        assert len(data.get("items", [])) > 0, "Catalog has no items"


# ---------------------------------------------------------------------------
# Import workflow stability tests
# ---------------------------------------------------------------------------

class TestImportWorkflow:
    def test_validate_passes_current_catalog(self):
        """validate command should pass on the current catalog."""
        issues = validate_catalog(CATALOG_PATH)
        errors = [i for i in issues if i.severity == "error"]
        assert not errors

    def test_validate_catches_empty_product(self):
        """validate should catch items with empty product."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "items": [{"product": "", "sku": "x", "region": "chile",
                           "billing_mode": "monthly", "price": 1.0}],
            }, f)
            f.flush()
            issues = validate_catalog(f.name)
        os.unlink(f.name)
        assert any(i.severity == "error" and "product" in i.message.lower() for i in issues)

    def test_validate_catches_non_numeric_price(self):
        """validate should catch items with non-numeric price."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "items": [{"product": "EVS", "sku": "x", "region": "chile",
                           "billing_mode": "monthly", "price": "not-a-number"}],
            }, f)
            f.flush()
            issues = validate_catalog(f.name)
        os.unlink(f.name)
        assert any(i.severity == "error" and "numeric" in i.message.lower() for i in issues)

    def test_validate_catches_missing_critical_product(self):
        """validate should catch missing critical products."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "items": [{"product": "EVS", "sku": "high-io", "region": "chile",
                           "billing_mode": "monthly", "price": 0.051}],
            }, f)
            f.flush()
            issues = validate_catalog(f.name)
        os.unlink(f.name)
        assert any(i.severity == "error" and "product" in i.message.lower() for i in issues)

    def test_patch_dry_run_summary(self):
        """patch_dry_run_summary should classify items correctly."""
        # Create a minimal catalog
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "items": [
                    {"product": "EVS", "sku": "high-io", "region": "chile",
                     "billing_mode": "monthly", "price": 0.051},
                ],
            }, f)
            f.flush()
            catalog_path = f.name

        # Create a patch with: 1 unchanged, 1 updated, 1 new
        patch = {
            "patch_metadata": {"errors": 0, "issues": 1, "skipped_products": []},
            "items": [
                {"product": "EVS", "sku": "high-io", "region": "chile",
                 "billing_mode": "monthly", "price": 0.051},  # unchanged
                {"product": "EVS", "sku": "high-io", "region": "chile",
                 "billing_mode": "monthly", "price": 0.099},  # updated (same key, diff price)
                {"product": "OBS", "sku": "obs-standard", "region": "chile",
                 "billing_mode": "monthly", "price": 0.021},  # new
            ],
        }
        summary = patch_dry_run_summary(patch, catalog_path)
        os.unlink(catalog_path)
        assert summary["unchanged_items"] == 1
        assert summary["updated_items"] == 1
        assert summary["new_items"] == 1
        assert summary["total_patch_items"] == 3


# ---------------------------------------------------------------------------
# Patch generation tests
# ---------------------------------------------------------------------------

class TestPatchGeneration:
    def test_patch_only_monthly(self):
        """Patch should only include monthly-priced rows."""
        result = ImportResult()
        result.normalized_rows = [
            normalize_row("EVS", "chile", "Santiago&Mexico", "high-io", "hourly", "GB-hour", 0.00007),
            normalize_row("EVS", "chile", "Santiago&Mexico", "high-io", "monthly", "GB-month", 0.051),
            normalize_row("EVS", "chile", "Santiago&Mexico", "high-io", "ri-1y", "GB-month", 0.51),
        ]
        patch = generate_patch(result)
        assert patch["patch_metadata"]["total_items"] == 1
        assert patch["items"][0]["billing_mode"] == "monthly"
        assert patch["items"][0]["price"] == 0.051

    def test_patch_metadata(self):
        """Patch should have correct metadata."""
        result = ImportResult()
        result.normalized_rows = [
            normalize_row("EVS", "chile", "Santiago&Mexico", "high-io", "monthly", "GB-month", 0.051),
        ]
        patch = generate_patch(result)
        assert patch["patch_metadata"]["total_items"] == 1
        assert patch["patch_metadata"]["errors"] == 0
        assert "generated_at" in patch["patch_metadata"]


# ---------------------------------------------------------------------------
# Illegal input tests
# ---------------------------------------------------------------------------

class TestIllegalInput:
    def test_unknown_product_skipped(self):
        """Unknown products should not be in PRODUCT_MAPPING."""
        assert "Unknown Product" not in PRODUCT_MAPPING

    def test_unknown_region_not_in_supported(self):
        """Regions not in SUPPORTED_REGIONS should not pass validation."""
        assert "tokyo" not in SUPPORTED_REGIONS
        assert "us-east" not in SUPPORTED_REGIONS

    def test_supported_products_complete(self):
        """All required products should be in SUPPORTED_PRODUCTS."""
        required = {"EVS", "OBS", "SFS Turbo", "EIP", "ELB", "NAT Gateway", "VPN",
                    "Direct Connect as a Service", "RDS", "DDS", "DWS"}
        assert required.issubset(SUPPORTED_PRODUCTS)

    def test_supported_regions_complete(self):
        """All required regions should be in SUPPORTED_REGIONS."""
        required = {"chile", "mexico", "brazil"}
        assert required == SUPPORTED_REGIONS


# ---------------------------------------------------------------------------
# Multi-region row expansion tests
# ---------------------------------------------------------------------------

class TestMultiRegionExpansion:
    """Tests that a single Excel row with multi-region text produces
    multiple normalized rows (one per region), and that patch generation
    includes all of them."""

    def test_multi_region_produces_multiple_rows(self):
        """A row with Santiago&Mexico should produce rows for both chile and mexico."""
        rows = [
            normalize_row("EVS", "chile", "Santiago&Mexico", "high-io", "monthly", "GB-month", 0.051),
            normalize_row("EVS", "mexico", "Santiago&Mexico", "high-io", "monthly", "GB-month", 0.051),
        ]
        # Both rows have same price but different regions → no conflict
        result = ImportResult(normalized_rows=rows)
        _validate_result(result)
        assert not result.has_errors

    def test_patch_includes_all_regions(self):
        """Patch generation should include items for all expanded regions."""
        result = ImportResult(normalized_rows=[
            normalize_row("EVS", "chile", "Santiago&Mexico", "high-io", "monthly", "GB-month", 0.051),
            normalize_row("EVS", "mexico", "Santiago&Mexico", "high-io", "monthly", "GB-month", 0.051),
        ])
        patch = generate_patch(result)
        assert patch["patch_metadata"]["total_items"] == 2
        regions_in_patch = {item["region"] for item in patch["items"]}
        assert regions_in_patch == {"chile", "mexico"}

    def test_three_region_expansion_no_conflict(self):
        """Santiago&Mexico&Sao Paulo → chile, mexico, brazil with same price → no conflict."""
        rows = [
            normalize_row("EVS", "chile", "Santiago&Mexico&Sao Paulo", "high-io", "monthly", "GB-month", 0.051),
            normalize_row("EVS", "mexico", "Santiago&Mexico&Sao Paulo", "high-io", "monthly", "GB-month", 0.051),
            normalize_row("EVS", "brazil", "Santiago&Mexico&Sao Paulo", "high-io", "monthly", "GB-month", 0.051),
        ]
        result = ImportResult(normalized_rows=rows)
        _validate_result(result)
        assert not result.has_errors

    def test_expanded_same_price_same_region_no_conflict(self):
        """After expansion, if two source rows map to the same region with the
        same price, they should not conflict (e.g., single-AZ and multi-AZ OBS
        both at the same price)."""
        rows = [
            normalize_row("OBS", "chile", "Santiago", "obs-standard", "monthly", "GB-month", 0.021),
            normalize_row("OBS", "chile", "Santiago", "obs-standard", "monthly", "GB-month", 0.021),
        ]
        result = ImportResult(normalized_rows=rows)
        _validate_result(result)
        assert not result.has_errors

    def test_expanded_different_price_same_key_conflict(self):
        """After expansion, if two rows have the same product+sku+region+mode
        but different prices, that IS a conflict."""
        rows = [
            normalize_row("OBS", "chile", "Santiago", "obs-standard", "monthly", "GB-month", 0.021),
            normalize_row("OBS", "chile", "Santiago", "obs-standard", "monthly", "GB-month", 0.023),
        ]
        result = ImportResult(normalized_rows=rows)
        _validate_result(result)
        assert result.has_errors
        assert result.has_conflicts
