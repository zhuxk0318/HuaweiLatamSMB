"""Tests for usage-based billing pricing: OBS/SFS/RDS/CBR usage items with compatible catalog units."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.flexible_workflow import (
    _billing_requirement_price_semantic,
    _billing_can_price_requirement,
    _match_price_component_by_spec,
    _infer_obs_sfs_tier,
    _extract_billing_lines,
    _group_billing_lines,
    _aggregate_billing_groups_fallback,
    _build_requirements_from_llm_aggregated_billing_items,
    normalize_requirements,
    validate_quote_readiness,
    resolve_price_components,
    quote_items,
    summarize_quote,
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


AZURE_CSV_PATH = Path("/root/SMBReference/CGE/azure Billing_invoice_transactions.csv")


def _make_req(overrides: dict | None = None) -> RequirementItem:
    base = RequirementItem(
        item_id="test::obs",
        source_file="test.csv",
        source_sheet="csv",
        row_number=2,
        raw_product_name="OBS | Blob Storage",
        quantity=100.0,
        quantity_source="billing_standardized",
        unit="capacity gib month",
        region="chile",
        normalized_product="OBS",
        spec=StorageSpec(tier="standard", capacity_gib=100.0).model_dump(),
    )
    if overrides:
        base = base.model_copy(update=overrides)
    return base


def _make_component(product: str, unit: str, sku: str | None = None, price: float = 100.0) -> PriceComponent:
    return PriceComponent(
        product=product, region="chile", sku=sku, family=None, tier=None,
        billing_mode="monthly", unit=unit, price=price, currency="USD",
        source_url="https://test", captured_at="2026-01-01",
        confirmed=True, status="confirmed",
    )


# ---------------------------------------------------------------------------
# 1. test_obs_capacity_usage_can_match_gb_month_component
# ---------------------------------------------------------------------------

class TestObsCapacity:
    def test_obs_capacity_usage_can_match_gb_month_component(self):
        req = _make_req({
            "normalized_product": "OBS",
            "unit": "capacity gib month",
            "spec": StorageSpec(tier="standard", capacity_gib=100.0).model_dump(),
        })
        comp = _make_component("OBS", "GB-month", "obs-standard", 0.102)
        can_price, _ = _billing_can_price_requirement(req, comp)
        assert can_price is True

    def test_obs_capacity_matches_standard_tier(self):
        catalog = query_flexible_pricing_catalog(product="OBS", region="chile", confirmed_only=True)
        req = _make_req({
            "normalized_product": "OBS",
            "unit": "capacity gib month",
            "raw_product_name": "OBS | Blob Storage - Frecuente",
            "quantity": 572.75,
        })
        # spec must be a model, not dict
        req = req.model_copy(update={"spec": StorageSpec(tier="standard", capacity_gib=572.75)})
        matched = _match_price_component_by_spec(req, catalog)
        assert matched is not None
        assert "standard" in ((matched.tier or "") + (matched.sku or "")).lower()


# ---------------------------------------------------------------------------
# 2. test_obs_request_usage_only_matches_request_component
# ---------------------------------------------------------------------------

class TestObsRequestUsage:
    def test_obs_request_usage_only_matches_request_component(self):
        """OBS ops_10k can only match a catalog item with request/operation unit."""
        req = _make_req({
            "normalized_product": "OBS",
            "unit": "ops 10k",
            "quantity": 17.87,
        })
        # GB-month component is NOT compatible
        comp_gb = _make_component("OBS", "GB-month", "obs-standard", 0.102)
        can_price, reason = _billing_can_price_requirement(req, comp_gb)
        assert can_price is False

    def test_obs_request_usage_does_not_match_capacity_component(self):
        """Explicit: ops_10k must NOT match GB-month catalog."""
        req = _make_req({
            "normalized_product": "OBS",
            "unit": "ops 10k",
        })
        comp = _make_component("OBS", "GB-month", "obs-standard")
        can_price, _ = _billing_can_price_requirement(req, comp)
        assert can_price is False


# ---------------------------------------------------------------------------
# 3. test_sfs_capacity_usage_can_match_gb_month_component
# ---------------------------------------------------------------------------

class TestSfsCapacity:
    def test_sfs_capacity_usage_can_match_gb_month_component(self):
        req = _make_req({
            "normalized_product": "SFS Turbo",
            "unit": "capacity gib month",
            "raw_product_name": "SFS Turbo | File Storage",
            "spec": StorageSpec(tier="standard", capacity_gib=162.97).model_dump(),
            "quantity": 162.97,
        })
        comp = _make_component("SFS Turbo", "GB-month", "sfs-turbo-standard", 0.169)
        can_price, _ = _billing_can_price_requirement(req, comp)
        assert can_price is True

    def test_sfs_ops_10k_does_not_match_gb_month(self):
        """SFS Turbo ops_10k must NOT match GB-month catalog."""
        req = _make_req({
            "normalized_product": "SFS Turbo",
            "unit": "ops 10k",
            "quantity": 267.56,
        })
        comp = _make_component("SFS Turbo", "GB-month", "sfs-turbo-standard", 0.169)
        can_price, _ = _billing_can_price_requirement(req, comp)
        assert can_price is False


# ---------------------------------------------------------------------------
# 4. test_rds_storage_usage_does_not_match_instance_month_component
# ---------------------------------------------------------------------------

class TestRdsStorageUsage:
    def test_rds_storage_usage_does_not_match_instance_month_component(self):
        """RDS storage GB/month must NOT match RDS instance-month catalog."""
        req = _make_req({
            "normalized_product": "RDS",
            "unit": "capacity gib month",
            "raw_product_name": "RDS | MySQL Storage",
            "quantity": 2296.0,
        })
        comp = _make_component("RDS", "instance-month", "mysql.s2.medium", 39.5)
        can_price, reason = _billing_can_price_requirement(req, comp)
        assert can_price is False
        assert "Storage capacity" in reason or "cannot be priced" in reason

    def test_rds_storage_usage_can_match_storage_gb_month_component(self):
        """RDS storage GB/month CAN match if catalog had a storage GB-month unit."""
        req = _make_req({
            "normalized_product": "RDS",
            "unit": "capacity gib month",
            "raw_product_name": "RDS | MySQL Storage",
            "quantity": 2296.0,
        })
        # Hypothetical RDS storage component with GB-month
        comp = _make_component("RDS", "GB-month", "mysql-storage", 0.15)
        can_price, _ = _billing_can_price_requirement(req, comp)
        # This should be allowed since the units are compatible
        assert can_price is True


# ---------------------------------------------------------------------------
# 5. test_rds_paid_io_only_matches_io_component_when_present
# ---------------------------------------------------------------------------

class TestRdsPaidIo:
    def test_rds_paid_io_does_not_match_instance_month(self):
        """RDS paid IO must NOT match RDS instance-month."""
        req = _make_req({
            "normalized_product": "RDS",
            "unit": "ops 10k",
            "raw_product_name": "RDS | MySQL Paid IO",
            "quantity": 500.0,
        })
        comp = _make_component("RDS", "instance-month", "mysql.s2.medium", 39.5)
        can_price, _ = _billing_can_price_requirement(req, comp)
        assert can_price is False


# ---------------------------------------------------------------------------
# 6. test_cbr_backup_storage_only_matches_storage_component_when_present
# ---------------------------------------------------------------------------

class TestCbrStorageUsage:
    def test_cbr_backup_storage_does_not_match_protected_server_month(self):
        """CBR backup storage GB/month must NOT match CBR protected-server-month."""
        req = _make_req({
            "normalized_product": "CBR",
            "unit": "capacity gib month",
            "raw_product_name": "CBR | Backup Storage",
            "quantity": 244.65,
        })
        comp = _make_component("CBR", "protected-server-month", "cbr-basic", 12.8)
        can_price, reason = _billing_can_price_requirement(req, comp)
        assert can_price is False

    def test_cbr_backup_storage_can_match_storage_gb_month(self):
        """CBR backup storage CAN match if catalog had a storage GB-month unit."""
        req = _make_req({
            "normalized_product": "CBR",
            "unit": "capacity gib month",
            "raw_product_name": "CBR | Backup Storage",
            "quantity": 244.65,
        })
        comp = _make_component("CBR", "GB-month", "cbr-storage", 0.10)
        can_price, _ = _billing_can_price_requirement(req, comp)
        assert can_price is True


# ---------------------------------------------------------------------------
# 7. test_usage_quantity_is_not_reconverted_to_instance_month
# ---------------------------------------------------------------------------

class TestUsageQuantity:
    def test_usage_quantity_is_not_reconverted_to_instance_month(self):
        """Usage quantity must be used as-is, not divided by 744."""
        from app.flexible_workflow import _billing_quote_quantity
        req = _make_req({
            "normalized_product": "OBS",
            "unit": "capacity gib month",
            "quantity": 572.75,
        })
        comp = _make_component("OBS", "GB-month", "obs-standard", 0.102)
        qty = _billing_quote_quantity(req, comp)
        assert qty == 572.75, "Capacity quantity must not be re-converted"

    def test_traffic_quantity_not_reconverted(self):
        from app.flexible_workflow import _billing_quote_quantity
        req = _make_req({
            "normalized_product": "ELB",
            "unit": "traffic gb",
            "quantity": 1833.72,
        })
        comp = _make_component("ELB", "instance-month", "elb-shared", 6.8)
        qty = _billing_quote_quantity(req, comp)
        assert qty == 1833.72, "Traffic quantity must not be re-converted"


# ---------------------------------------------------------------------------
# 8. test_real_billing_total_increases_without_returning_to_runaway_overpricing
# ---------------------------------------------------------------------------

class TestRealAzureUsagePricing:
    def test_real_billing_total_increases_without_returning_to_runaway_overpricing(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Real Azure: total should increase from $2090 but stay < $50k."""
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)

        csv_path = AZURE_CSV_PATH
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

        sum_state = {"requirements": norm_result["requirements"], "quote_ready_items": val_result["quote_ready_items"], "quote_lines": quote_result["quote_lines"], "quote_blockers": val_result["quote_blockers"], "unquoted_items": res_result["unquoted_items"], "quote_context": {"region": "chile"}, "llm_aggregated_billing_items": agg_items, "audit_log": [], "progress_callback": None}
        sum_result = summarize_quote(sum_state)
        total = sum_result["summary"]["total_monthly_price"]

        # Coverage increased
        assert len(quote_result["quote_lines"]) > 14, "Quote lines should increase from 14"
        assert total > 2090, f"Total ${total:,.2f} should exceed $2,090 baseline"

        # No runaway overpricing
        assert total < 50000, f"Total ${total:,.2f} is suspiciously high — usage mispricing?"

        # OBS and SFS Turbo should have quoted lines
        obs_lines = [ql for ql in quote_result["quote_lines"] if ql.get("product") == "OBS"]
        sfs_lines = [ql for ql in quote_result["quote_lines"] if ql.get("product") == "SFS Turbo"]
        assert len(obs_lines) > 0, "OBS should have quoted capacity lines"
        assert len(sfs_lines) > 0, "SFS Turbo should have quoted capacity lines"


# ---------------------------------------------------------------------------
# 9. test_infer_obs_sfs_tier
# ---------------------------------------------------------------------------

class TestInferObsSfsTier:
    def test_obs_frecuente_is_standard(self):
        assert _infer_obs_sfs_tier("Blob Storage - Frecuente RA-GRS", "OBS") == "standard"

    def test_obs_cool_is_infrequent(self):
        assert _infer_obs_sfs_tier("Blob Storage - Cool LRS", "OBS") == "infrequent-access"

    def test_obs_default_is_standard(self):
        assert _infer_obs_sfs_tier("Blob en bloques general", "OBS") == "standard"

    def test_sfs_frecuente_is_standard(self):
        assert _infer_obs_sfs_tier("Archivos v2 - Frecuente LRS", "SFS Turbo") == "standard"

    def test_sfs_cool_is_20mbps(self):
        assert _infer_obs_sfs_tier("Archivos v2 - Cool LRS", "SFS Turbo") == "20mbps-per-tib"

    def test_sfs_default_is_standard(self):
        assert _infer_obs_sfs_tier("Archivos - LRS", "SFS Turbo") == "standard"


# ---------------------------------------------------------------------------
# 10. test_export_detail_row_marks_usage_based_quote_with_real_unit
# ---------------------------------------------------------------------------

class TestExportUsageRows:
    def test_export_detail_row_marks_usage_based_quote_with_real_unit(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Detail rows for OBS/SFS capacity should show real unit, not instance-month."""
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)

        from app.flexible_workflow import (
            _build_billing_detail_rows,
            export_flexible_workbook,
        )
        from io import BytesIO
        from openpyxl import load_workbook

        csv_path = AZURE_CSV_PATH
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

        sum_state = {"requirements": norm_result["requirements"], "quote_ready_items": val_result["quote_ready_items"], "quote_lines": quote_result["quote_lines"], "quote_blockers": val_result["quote_blockers"], "unquoted_items": res_result["unquoted_items"], "quote_context": {"region": "chile"}, "llm_aggregated_billing_items": agg_items, "audit_log": [], "progress_callback": None}
        sum_result = summarize_quote(sum_state)

        export_state = {"requirements": norm_result["requirements"], "quote_ready_items": val_result["quote_ready_items"], "quote_lines": quote_result["quote_lines"], "quote_blockers": val_result["quote_blockers"], "unquoted_items": res_result["unquoted_items"], "price_components": res_result["price_components"], "summary": sum_result["summary"], "mapped_billing_resources": [], "billing_lines": lines, "standardized_billing_resources": [], "llm_aggregated_billing_items": agg_items, "billing_reconciliation": sum_result.get("billing_reconciliation", {}), "billing_gap_analysis": sum_result.get("billing_gap_analysis", {}), "quote_context": {"region": "chile"}, "audit_log": [], "progress_callback": None}

        detail_rows = _build_billing_detail_rows(export_state)
        # Find OBS quoted rows
        obs_quoted = [r for r in detail_rows if r.get("huawei_product") == "OBS" and r.get("status") == "quoted"]
        assert len(obs_quoted) > 0, "Should have quoted OBS rows"
        # Target unit should show GB-month, not instance-month
        for r in obs_quoted:
            assert "instance" not in (r.get("target_unit") or "").lower(), \
                f"OBS capacity row should not show instance-month: {r}"


# ---------------------------------------------------------------------------
# 11. test_summary_mentions_only_compatible_usage_units_were_quoted
# ---------------------------------------------------------------------------

class TestSummaryUsageMention:
    def test_summary_mentions_usage_based_unquoted(self):
        """Summary should mention usage-based items remain unquoted."""
        req = _make_req({
            "normalized_product": "OBS",
            "unit": "ops 10k",
        })
        state = {
            "requirements": [req.model_dump()],
            "quote_ready_items": [],
            "quote_lines": [],
            "quote_blockers": [],
            "unquoted_items": [req.model_copy(update={"status": "needs_price_confirmation", "status_reason": "Request/operation usage cannot be priced"}).model_dump()],
            "audit_log": [],
            "progress_callback": None,
            "quote_context": {"region": "chile"},
        }
        result = summarize_quote(state)
        assumptions = result["summary"].get("assumptions", [])
        usage_assumptions = [a for a in assumptions if "usage" in a.lower() and "unquoted" in a.lower()]
        assert len(usage_assumptions) > 0, f"Expected usage-based assumption, got: {assumptions}"
