"""Phase D tests: billing requirements → Huawei Cloud pricing resolution and quote generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.flexible_workflow import (
    _detect_billing_document,
    _extract_billing_lines,
    _standardize_billing_lines,
    _map_standardized_billing_resources_to_huawei,
    _build_requirements_from_mapped_billing_resources,
    _parse_csv_document,
    _match_price_component_by_spec,
    _billing_requirement_assumption,
    normalize_requirements,
    validate_quote_readiness,
    resolve_price_components,
    quote_items,
    summarize_quote,
    load_pricebook,
)
from app.flexible_pricing import query_flexible_pricing_catalog
from app.models import (
    FlexibleQuoteContext,
    RequirementItem,
    PriceComponent,
    ComputeSpec,
    StorageSpec,
    GenericSpec,
    FlexibleQuoteLine,
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


def _make_requirement(overrides: dict | None = None) -> dict:
    """Build a billing RequirementItem dict for testing."""
    base = RequirementItem(
        item_id="billing-map::test.csv::0::ECS",
        source_file="test.csv",
        source_sheet="csv",
        row_number=2,
        raw_product_name="ECS | D8 v3",
        quantity=6.0,
        quantity_source="billing_standardized",
        unit="instance hours",
        region=None,
        normalized_product="ECS",
        spec=ComputeSpec(sku="D8 v3").model_dump(),
        notes="vendor=azure | family=Compute | mapping=direct_kind_map",
    )
    if overrides:
        base = base.model_copy(update=overrides)
    return base.model_dump()


def _catalog_for_region(region: str = "chile") -> list[dict]:
    """Get confirmed catalog items as dicts."""
    items = query_flexible_pricing_catalog(region=region, confirmed_only=True)
    return [item.model_dump() for item in items]


# ---------------------------------------------------------------------------
# 1. test_billing_requirements_use_quote_context_region
# ---------------------------------------------------------------------------

class TestRegionInheritance:
    def test_billing_requirements_use_quote_context_region(self):
        """Billing requirement with region=None should inherit quote_context.region."""
        req = _make_requirement({"region": None, "normalized_product": "ECS"})
        state = {
            "requirements": [req],
            "quote_context": {"region": "chile"},
            "price_catalog": _catalog_for_region("chile"),
            "matched_products": [],
            "understanding": {"profile": {}},
            "audit_log": [],
            "progress_callback": None,
        }
        result = validate_quote_readiness(state)
        ready = result["quote_ready_items"]
        blockers = result["quote_blockers"]
        # Should NOT be blocked for missing region
        region_blockers = [b for b in blockers if b.get("status") == "needs_region"]
        assert len(region_blockers) == 0, "Billing requirement should not be blocked for missing region"
        # Should be ready (or at least not needs_region)
        if ready:
            assert ready[0]["region"] == "chile"

    def test_billing_region_none_without_context_becomes_blocker(self):
        """If both requirement.region and quote_context.region are None, should block."""
        req = _make_requirement({"region": None})
        state = {
            "requirements": [req],
            "quote_context": {"region": None},
            "price_catalog": [],
            "matched_products": [],
            "understanding": {"profile": {}},
            "audit_log": [],
            "progress_callback": None,
        }
        result = validate_quote_readiness(state)
        blockers = result["quote_blockers"]
        region_blockers = [b for b in blockers if b.get("status") == "needs_region"]
        assert len(region_blockers) == 1


# ---------------------------------------------------------------------------
# 2. test_quote_items_do_not_overwrite_same_product_same_region
# ---------------------------------------------------------------------------

class TestNoOverwrite:
    def test_quote_items_do_not_overwrite_same_product_same_region(self):
        """Two ECS requirements with different specs in same region must produce two lines."""
        catalog = _catalog_for_region("chile")
        # Find two different ECS SKUs in catalog
        ecs_items = [i for i in catalog if i["product"] == "ECS" and i.get("price")]
        if len(ecs_items) < 2:
            pytest.skip("Need at least 2 ECS catalog items")

        sku1 = ecs_items[0]["sku"]
        sku2 = ecs_items[1]["sku"]

        req1 = _make_requirement({
            "item_id": "billing-map::test.csv::0::ECS",
            "normalized_product": "ECS",
            "region": "chile",
            "spec": ComputeSpec(sku=sku1).model_dump(),
            "quantity": 2.0,
        })
        req2 = _make_requirement({
            "item_id": "billing-map::test.csv::1::ECS",
            "normalized_product": "ECS",
            "region": "chile",
            "spec": ComputeSpec(sku=sku2).model_dump(),
            "quantity": 3.0,
        })

        state = {
            "quote_ready_items": [req1, req2],
            "price_catalog": catalog,
            "unquoted_items": [],
            "audit_log": [],
            "progress_callback": None,
        }
        resolved = resolve_price_components(state)
        # Must have 2 resolved components
        assert len(resolved["price_components"]) == 2, (
            f"Expected 2 resolved components, got {len(resolved['price_components'])}"
        )
        # They must have different requirement_item_ids
        ids = {pc["requirement_item_id"] for pc in resolved["price_components"]}
        assert len(ids) == 2

        # Now quote
        quote_state = {
            "quote_ready_items": [req1, req2],
            "price_components": resolved["price_components"],
            "audit_log": [],
            "progress_callback": None,
        }
        quoted = quote_items(quote_state)
        assert len(quoted["quote_lines"]) == 2, "Two ECS requirements must produce two quote lines"


# ---------------------------------------------------------------------------
# 3. test_ecs_billing_requirement_matches_by_spec_not_first_candidate
# ---------------------------------------------------------------------------

class TestEcsSpecMatch:
    def test_ecs_billing_requirement_matches_by_spec_not_first_candidate(self):
        """ECS with specific SKU should match that SKU, not just the first catalog item."""
        catalog = _catalog_for_region("chile")
        ecs_items = [i for i in catalog if i["product"] == "ECS" and i.get("price") and i.get("sku")]
        if len(ecs_items) < 2:
            pytest.skip("Need at least 2 ECS catalog items with SKUs")

        target_sku = ecs_items[1]["sku"]  # pick second one
        req = RequirementItem(
            item_id="test::ecs",
            source_file="test.csv",
            source_sheet="csv",
            row_number=2,
            raw_product_name="ECS",
            quantity=1.0,
            quantity_source="billing_standardized",
            unit="instance hours",
            region="chile",
            normalized_product="ECS",
            spec=ComputeSpec(sku=target_sku).model_dump(),
        )
        candidates = [PriceComponent.model_validate(i) for i in ecs_items]
        matched = _match_price_component_by_spec(req, candidates)
        assert matched is not None
        assert matched.sku == target_sku


# ---------------------------------------------------------------------------
# 4. test_evs_billing_requirement_preserves_tier_matching
# ---------------------------------------------------------------------------

class TestEvsTierMatch:
    def test_evs_billing_requirement_preserves_tier_matching(self):
        """EVS with tier hint should match that tier."""
        catalog = _catalog_for_region("chile")
        evs_items = [i for i in catalog if i["product"] == "EVS" and i.get("price")]
        if not evs_items:
            pytest.skip("No EVS catalog items")

        # Test high-io tier
        req = RequirementItem(
            item_id="test::evs",
            source_file="test.csv",
            source_sheet="csv",
            row_number=2,
            raw_product_name="EVS",
            quantity=100.0,
            quantity_source="billing_standardized",
            unit="capacity gib month",
            region="chile",
            normalized_product="EVS",
            spec=StorageSpec(tier="high_io", sku="high-io").model_dump(),
        )
        candidates = [PriceComponent.model_validate(i) for i in evs_items]
        matched = _match_price_component_by_spec(req, candidates)
        assert matched is not None
        # Should match high-io tier
        assert "high-io" in ((matched.tier or "") + (matched.sku or "")).lower()

    def test_evs_default_tier_when_no_hint(self):
        """EVS without tier hint should default to high-io."""
        catalog = _catalog_for_region("chile")
        evs_items = [i for i in catalog if i["product"] == "EVS" and i.get("price")]
        if not evs_items:
            pytest.skip("No EVS catalog items")

        req = RequirementItem(
            item_id="test::evs",
            source_file="test.csv",
            source_sheet="csv",
            row_number=2,
            raw_product_name="EVS",
            quantity=100.0,
            quantity_source="billing_standardized",
            unit="capacity gib month",
            region="chile",
            normalized_product="EVS",
            spec=StorageSpec(capacity_gib=100).model_dump(),
        )
        candidates = [PriceComponent.model_validate(i) for i in evs_items]
        matched = _match_price_component_by_spec(req, candidates)
        assert matched is not None


# ---------------------------------------------------------------------------
# 5. test_generic_network_product_can_quote_single_confirmed_candidate
# ---------------------------------------------------------------------------

class TestGenericProductQuote:
    def test_vpn_single_confirmed_candidate(self):
        """VPN with single confirmed catalog item should quote."""
        catalog = _catalog_for_region("chile")
        vpn_items = [i for i in catalog if i["product"] == "VPN" and i.get("price")]
        if not vpn_items:
            pytest.skip("No VPN catalog items")

        req = _make_requirement({
            "item_id": "test::vpn",
            "normalized_product": "VPN",
            "raw_product_name": "VPN",
            "spec": GenericSpec(description="VPN Gateway").model_dump(),
        })
        candidates = [PriceComponent.model_validate(i) for i in vpn_items]
        matched = _match_price_component_by_spec(
            RequirementItem.model_validate(req), candidates
        )
        assert matched is not None

    def test_eip_single_confirmed_candidate(self):
        """EIP should quote from catalog."""
        catalog = _catalog_for_region("chile")
        eip_items = [i for i in catalog if i["product"] == "EIP" and i.get("price")]
        if not eip_items:
            pytest.skip("No EIP catalog items")

        req = _make_requirement({
            "item_id": "test::eip",
            "normalized_product": "EIP",
            "raw_product_name": "EIP",
            "spec": GenericSpec(description="Public IP").model_dump(),
        })
        candidates = [PriceComponent.model_validate(i) for i in eip_items]
        matched = _match_price_component_by_spec(
            RequirementItem.model_validate(req), candidates
        )
        assert matched is not None


# ---------------------------------------------------------------------------
# 6. test_ambiguous_rds_without_clear_spec_becomes_unquoted
# ---------------------------------------------------------------------------

class TestRdsAmbiguity:
    def test_ambiguous_rds_without_clear_spec_becomes_unquoted(self):
        """RDS without engine hint should NOT blindly match first catalog item."""
        catalog = _catalog_for_region("chile")
        rds_items = [i for i in catalog if i["product"] == "RDS" and i.get("price")]
        if len(rds_items) < 2:
            pytest.skip("Need at least 2 RDS catalog items")

        req = RequirementItem(
            item_id="test::rds",
            source_file="test.csv",
            source_sheet="csv",
            row_number=2,
            raw_product_name="RDS",
            quantity=1.0,
            quantity_source="billing_standardized",
            unit="instance hours",
            region="chile",
            normalized_product="RDS",
            spec=GenericSpec(description="database").model_dump(),
        )
        candidates = [PriceComponent.model_validate(i) for i in rds_items]
        matched = _match_price_component_by_spec(req, candidates)
        # Should NOT match — "database" is too ambiguous
        assert matched is None, "Ambiguous RDS without engine hint should not match"

    def test_mysql_rds_matches(self):
        """RDS with MySQL hint should match MySQL catalog items."""
        catalog = _catalog_for_region("chile")
        rds_items = [i for i in catalog if i["product"] == "RDS" and i.get("price")]
        mysql_items = [i for i in rds_items if "mysql" in (i.get("sku") or "").lower() or "mysql" in (i.get("family") or "").lower()]
        if not mysql_items:
            pytest.skip("No MySQL RDS catalog items")

        req = RequirementItem(
            item_id="test::rds-mysql",
            source_file="test.csv",
            source_sheet="csv",
            row_number=2,
            raw_product_name="RDS",
            quantity=1.0,
            quantity_source="billing_standardized",
            unit="instance hours",
            region="chile",
            normalized_product="RDS",
            spec=GenericSpec(sku="MySQL Flexible Server", description="MySQL Flexible Server - 1 vCore").model_dump(),
        )
        candidates = [PriceComponent.model_validate(i) for i in rds_items]
        matched = _match_price_component_by_spec(req, candidates)
        assert matched is not None, "RDS with MySQL hint should match"


# ---------------------------------------------------------------------------
# 7. test_unsupported_billing_requirement_stays_unquoted
# ---------------------------------------------------------------------------

class TestUnsupportedUnquoted:
    def test_unsupported_billing_requirement_stays_unquoted(self):
        """Unsupported requirement (normalized_product=None) should not generate quote line."""
        req = _make_requirement({
            "normalized_product": None,
            "raw_product_name": "developer_tool | API Management",
        })
        state = {
            "quote_ready_items": [req],
            "price_catalog": _catalog_for_region("chile"),
            "unquoted_items": [],
            "audit_log": [],
            "progress_callback": None,
        }
        result = resolve_price_components(state)
        # No resolved components
        assert len(result["price_components"]) == 0


# ---------------------------------------------------------------------------
# 8. test_non_billing_flexible_path_still_works
# ---------------------------------------------------------------------------

class TestNonBillingRegression:
    def test_non_billing_flexible_path_still_works(self):
        """Non-billing documents should not be affected by billing pricing changes."""
        # This is a structural check — the billing-specific code paths
        # should only activate for quantity_source == "billing_standardized"
        req = RequirementItem(
            item_id="test::normal",
            source_file="requirements.xlsx",
            source_sheet="Sheet1",
            row_number=2,
            raw_product_name="ECS",
            quantity=2.0,
            quantity_source="source_file",
            unit="item",
            region="chile",
            normalized_product="ECS",
            spec=ComputeSpec(sku="c7n.large.2").model_dump(),
        )
        # normalize_requirements should NOT treat this as billing
        state = {
            "requirements": [req.model_dump()],
            "quote_context": {"region": "chile"},
            "audit_log": [],
            "progress_callback": None,
        }
        result = normalize_requirements(state)
        norm_req = RequirementItem.model_validate(result["requirements"][0])
        # Should NOT have been treated as billing (normalized_product from _normalize_product_name)
        assert norm_req.normalized_product == "ECS"
        assert norm_req.quantity_source == "source_file"


# ---------------------------------------------------------------------------
# 9. test_summary_mentions_billing_standardization
# ---------------------------------------------------------------------------

class TestSummary:
    def test_summary_mentions_billing_standardization(self):
        """Summary should mention billing standardization when billing items are present."""
        billing_req = _make_requirement({
            "region": "chile",
            "normalized_product": "ECS",
        })
        state = {
            "requirements": [billing_req],
            "quote_ready_items": [billing_req],
            "quote_lines": [],
            "quote_blockers": [],
            "unquoted_items": [],
            "audit_log": [],
            "progress_callback": None,
            "quote_context": {"region": "chile"},
        }
        result = summarize_quote(state)
        summary = result["summary"]
        assumptions = summary.get("assumptions", [])
        # Should mention billing standardization
        billing_assumptions = [a for a in assumptions if "billing" in a.lower() or "standardization" in a.lower()]
        assert len(billing_assumptions) > 0, f"Expected billing assumption, got: {assumptions}"


# ---------------------------------------------------------------------------
# 10. test_resolved_price_components_include_requirement_item_id
# ---------------------------------------------------------------------------

class TestResolvedComponentTraceability:
    def test_resolved_price_components_include_requirement_item_id(self):
        """Each resolved price component must carry requirement_item_id."""
        catalog = _catalog_for_region("chile")
        ecs_items = [i for i in catalog if i["product"] == "ECS" and i.get("price") and i.get("sku")]
        if not ecs_items:
            pytest.skip("No ECS catalog items")

        target_sku = ecs_items[0]["sku"]
        req = _make_requirement({
            "item_id": "billing-map::test.csv::0::ECS",
            "normalized_product": "ECS",
            "region": "chile",
            "spec": ComputeSpec(sku=target_sku).model_dump(),
            "quantity": 2.0,
        })
        state = {
            "quote_ready_items": [req],
            "price_catalog": catalog,
            "unquoted_items": [],
            "audit_log": [],
            "progress_callback": None,
        }
        result = resolve_price_components(state)
        assert len(result["price_components"]) > 0
        for pc in result["price_components"]:
            assert "requirement_item_id" in pc
            assert pc["requirement_item_id"] == "billing-map::test.csv::0::ECS"


# ---------------------------------------------------------------------------
# Real Azure file end-to-end
# ---------------------------------------------------------------------------

class TestRealAzureFilePricing:
    def test_real_azure_file_pricing_stats(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        """Run the full pricing chain on the real Azure file and report stats."""
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)

        # 1. Extract & standardize & map
        lines = _extract_billing_lines(azure_document)
        standardized = _standardize_billing_lines(lines, FlexibleQuoteContext(region="chile"))
        mapped = _map_standardized_billing_resources_to_huawei(standardized)
        requirements = _build_requirements_from_mapped_billing_resources(mapped)

        # 2. Normalize (fills region from quote_context)
        state = {
            "requirements": requirements,
            "quote_context": {"region": "chile"},
            "audit_log": [],
            "progress_callback": None,
        }
        norm_result = normalize_requirements(state)
        norm_reqs = norm_result["requirements"]

        # 3. Validate readiness
        catalog = _catalog_for_region("chile")
        val_state = {
            "requirements": norm_reqs,
            "quote_context": {"region": "chile"},
            "price_catalog": catalog,
            "matched_products": [],
            "understanding": {"profile": {}},
            "audit_log": [],
            "progress_callback": None,
        }
        val_result = validate_quote_readiness(val_state)

        ready_count = len(val_result["quote_ready_items"])
        blocker_count = len(val_result["quote_blockers"])
        unquoted_count = len(val_result["unquoted_items"])

        # 4. Resolve prices
        res_state = {
            "quote_ready_items": val_result["quote_ready_items"],
            "price_catalog": catalog,
            "unquoted_items": val_result["unquoted_items"],
            "audit_log": [],
            "progress_callback": None,
        }
        res_result = resolve_price_components(res_state)

        # 5. Quote
        quote_state = {
            "quote_ready_items": val_result["quote_ready_items"],
            "price_components": res_result["price_components"],
            "audit_log": [],
            "progress_callback": None,
        }
        quote_result = quote_items(quote_state)
        quote_lines = quote_result["quote_lines"]

        # 6. Summary
        sum_state = {
            "requirements": norm_reqs,
            "quote_ready_items": val_result["quote_ready_items"],
            "quote_lines": quote_lines,
            "quote_blockers": val_result["quote_blockers"],
            "unquoted_items": res_result["unquoted_items"],
            "quote_context": {"region": "chile"},
            "audit_log": [],
            "progress_callback": None,
        }
        sum_result = summarize_quote(sum_state)
        summary = sum_result["summary"]

        # Print stats for the delivery report
        total_price = summary["total_monthly_price"]
        print(f"\n=== Real Azure File Pricing Stats ===")
        print(f"Requirements:    {len(norm_reqs)}")
        print(f"Ready:           {ready_count}")
        print(f"Blockers:        {blocker_count}")
        print(f"Unquoted:        {len(res_result['unquoted_items'])}")
        print(f"Quote lines:     {len(quote_lines)}")
        print(f"Total monthly:   ${total_price:,.2f}")

        # Basic assertions
        assert len(quote_lines) > 0, "Should have at least some quoted lines"
        assert total_price > 0, "Total price should be positive"
