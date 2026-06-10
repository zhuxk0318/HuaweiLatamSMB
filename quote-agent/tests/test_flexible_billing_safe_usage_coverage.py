"""Tests for safe usage coverage (Phase Next+6): OBS/SFS/RDS/CBR capacity
usage items with explicit evidence can be safely quoted; non-capacity usage
remains unquoted; reconciliation guard is never bypassed."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.flexible_workflow import (
    _billing_requirement_price_semantic,
    _billing_can_price_requirement,
    _billing_has_capacity_evidence,
    _billing_usage_semantic,
    _candidate_usage_components_for_requirement,
    _match_obs_usage_component,
    _match_sfs_usage_component,
    _match_rds_storage_component,
    _match_cbr_storage_component,
    _is_safe_usage_quote,
    _stable_unquoted_reason,
    _classify_unquoted_reason,
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
# 1. test_obs_capacity_usage_with_capacity_evidence_can_quote_gb_month
# ---------------------------------------------------------------------------

class TestObsCapacityEvidence:
    def test_obs_capacity_usage_with_capacity_evidence_can_quote_gb_month(self):
        req = _make_req({
            "normalized_product": "OBS",
            "unit": "capacity gib month",
            "spec": StorageSpec(tier="standard", capacity_gib=100.0).model_dump(),
            "notes": "unit=Datos almacenados (GB/mes)",
        })
        candidates = [_make_component("OBS", "GB-month", "obs-standard", 0.102)]
        matched = _match_obs_usage_component(req, candidates)
        assert matched is not None
        assert "gb-month" in matched.unit.lower()

    def test_obs_capacity_evidence_from_notes(self):
        """OBS with unknown unit but capacity evidence in notes can quote."""
        req = _make_req({
            "normalized_product": "OBS",
            "unit": "unknown",
            "notes": "unit=Datos almacenados (GB/mes)",
        })
        assert _billing_has_capacity_evidence(req) is True
        assert _billing_usage_semantic(req) == "capacity_gib_month"

    def test_obs_capacity_evidence_from_spec(self):
        """OBS with spec capacity_gib has capacity evidence."""
        req = _make_req({
            "normalized_product": "OBS",
            "unit": "unknown",
            "spec": StorageSpec(tier="standard", capacity_gib=572.75).model_dump(),
        })
        assert _billing_has_capacity_evidence(req) is True


# ---------------------------------------------------------------------------
# 2. test_obs_ops_usage_stays_unquoted_even_if_obs_gb_month_exists
# ---------------------------------------------------------------------------

class TestObsOpsUsage:
    def test_obs_ops_usage_stays_unquoted_even_if_obs_gb_month_exists(self):
        req = _make_req({
            "normalized_product": "OBS",
            "unit": "ops 10k",
            "quantity": 17.87,
        })
        candidates = [_make_component("OBS", "GB-month", "obs-standard", 0.102)]
        matched = _match_obs_usage_component(req, candidates)
        assert matched is None

    def test_obs_ops_usage_semantic_is_ops(self):
        req = _make_req({
            "normalized_product": "OBS",
            "unit": "ops 10k",
        })
        assert _billing_usage_semantic(req) == "ops_10k"


# ---------------------------------------------------------------------------
# 3. test_obs_unknown_without_capacity_evidence_stays_unquoted
# ---------------------------------------------------------------------------

class TestObsUnknown:
    def test_obs_unknown_without_capacity_evidence_stays_unquoted(self):
        req = _make_req({
            "normalized_product": "OBS",
            "unit": "unknown",
            "spec": None,
            "notes": "unit=10 000 operaciones de escritura",
        })
        candidates = [_make_component("OBS", "GB-month", "obs-standard", 0.102)]
        matched = _match_obs_usage_component(req, candidates)
        assert matched is None

    def test_obs_unknown_without_evidence_no_capacity(self):
        req = _make_req({
            "normalized_product": "OBS",
            "unit": "unknown",
            "spec": None,
            "raw_product_name": "OBS | Operations",
        })
        assert _billing_has_capacity_evidence(req) is False
        assert _billing_usage_semantic(req) == "unknown"


# ---------------------------------------------------------------------------
# 4. test_sfs_capacity_usage_with_datos_almacenados_can_quote_gb_month
# ---------------------------------------------------------------------------

class TestSfsCapacityEvidence:
    def test_sfs_capacity_usage_with_datos_almacenados_can_quote_gb_month(self):
        req = _make_req({
            "normalized_product": "SFS Turbo",
            "unit": "capacity gib month",
            "raw_product_name": "SFS Turbo | Archivos v2 - Frecuente LRS",
            "spec": StorageSpec(tier="standard", capacity_gib=162.97).model_dump(),
            "quantity": 162.97,
            "notes": "unit=Datos almacenados (GB/mes)",
        })
        candidates = [_make_component("SFS Turbo", "GB-month", "sfs-turbo-standard", 0.169)]
        matched = _match_sfs_usage_component(req, candidates)
        assert matched is not None
        assert "gb-month" in matched.unit.lower()

    def test_sfs_capacity_evidence_from_spec(self):
        req = _make_req({
            "normalized_product": "SFS Turbo",
            "unit": "unknown",
            "spec": StorageSpec(tier="standard", capacity_gib=100.0).model_dump(),
        })
        assert _billing_has_capacity_evidence(req) is True


# ---------------------------------------------------------------------------
# 5. test_sfs_metadata_usage_does_not_quote_as_capacity
# ---------------------------------------------------------------------------

class TestSfsMetadata:
    def test_sfs_metadata_usage_does_not_quote_as_capacity(self):
        req = _make_req({
            "normalized_product": "SFS Turbo",
            "unit": "unknown",
            "notes": "unit=Metadatos de archivo (GB/mes)",
            "raw_product_name": "SFS Turbo | Archivos - LRS",
        })
        candidates = [_make_component("SFS Turbo", "GB-month", "sfs-turbo-standard", 0.169)]
        matched = _match_sfs_usage_component(req, candidates)
        assert matched is None

    def test_sfs_list_operations_does_not_quote_as_capacity(self):
        """SFS Turbo with 'operaciones de lista' in notes must NOT match capacity."""
        req = _make_req({
            "normalized_product": "SFS Turbo",
            "unit": "unknown",
            "notes": "unit=10 000 operaciones de lista",
            "raw_product_name": "SFS Turbo | Archivos - LRS",
        })
        candidates = [_make_component("SFS Turbo", "GB-month", "sfs-turbo-standard", 0.169)]
        matched = _match_sfs_usage_component(req, candidates)
        assert matched is None


# ---------------------------------------------------------------------------
# 6. test_sfs_ops_usage_does_not_quote_as_capacity
# ---------------------------------------------------------------------------

class TestSfsOpsUsage:
    def test_sfs_ops_usage_does_not_quote_as_capacity(self):
        req = _make_req({
            "normalized_product": "SFS Turbo",
            "unit": "ops 10k",
            "raw_product_name": "SFS Turbo | Archivos v2 - Frecuente LRS",
            "quantity": 267.56,
        })
        candidates = [_make_component("SFS Turbo", "GB-month", "sfs-turbo-standard", 0.169)]
        matched = _match_sfs_usage_component(req, candidates)
        assert matched is None

    def test_sfs_ops_semantic(self):
        req = _make_req({
            "normalized_product": "SFS Turbo",
            "unit": "ops 10k",
        })
        assert _billing_usage_semantic(req) == "ops_10k"


# ---------------------------------------------------------------------------
# 7. test_rds_storage_usage_only_quotes_when_storage_gb_month_component_exists
# ---------------------------------------------------------------------------

class TestRdsStorage:
    def test_rds_storage_usage_only_quotes_when_storage_gb_month_component_exists(self):
        """RDS capacity_gib_month can quote IF catalog has GB-month component."""
        req = _make_req({
            "normalized_product": "RDS",
            "unit": "capacity gib month",
            "raw_product_name": "RDS | MySQL Storage - Almacenamiento",
            "quantity": 2296.0,
            "notes": "unit=Datos almacenados (GB/mes)",
        })
        # With GB-month component — should match
        candidates = [_make_component("RDS", "GB-month", "mysql-storage", 0.15)]
        matched = _match_rds_storage_component(req, candidates)
        assert matched is not None

    def test_rds_storage_no_gb_month_stays_unquoted(self):
        """RDS capacity_gib_month stays unquoted if catalog only has instance-month."""
        req = _make_req({
            "normalized_product": "RDS",
            "unit": "capacity gib month",
            "raw_product_name": "RDS | MySQL Storage",
            "quantity": 2296.0,
            "notes": "unit=Datos almacenados (GB/mes)",
        })
        # Only instance-month — should NOT match
        candidates = [_make_component("RDS", "instance-month", "mysql.s2.medium", 39.5)]
        matched = _match_rds_storage_component(req, candidates)
        assert matched is None

    def test_rds_storage_has_capacity_evidence(self):
        """RDS storage with 'Almacenamiento' in raw name has capacity evidence."""
        req = _make_req({
            "normalized_product": "RDS",
            "unit": "capacity gib month",
            "raw_product_name": "RDS | MySQL Flexible Server Storage - Almacenamiento",
            "notes": "unit=Datos almacenados (GB/mes)",
        })
        assert _billing_has_capacity_evidence(req) is True


# ---------------------------------------------------------------------------
# 8. test_rds_paid_io_stays_unquoted
# ---------------------------------------------------------------------------

class TestRdsPaidIo:
    def test_rds_paid_io_stays_unquoted(self):
        req = _make_req({
            "normalized_product": "RDS",
            "unit": "ops 10k",
            "raw_product_name": "RDS | MySQL Paid IO",
            "quantity": 500.0,
        })
        candidates = [_make_component("RDS", "instance-month", "mysql.s2.medium", 39.5)]
        matched = _match_rds_storage_component(req, candidates)
        assert matched is None

    def test_rds_paid_io_usage_semantic(self):
        req = _make_req({
            "normalized_product": "RDS",
            "unit": "ops 10k",
        })
        assert _billing_usage_semantic(req) == "ops_10k"


# ---------------------------------------------------------------------------
# 9. test_rds_user_month_stays_unquoted
# ---------------------------------------------------------------------------

class TestRdsUserMonth:
    def test_rds_user_month_stays_unquoted(self):
        req = _make_req({
            "normalized_product": "RDS",
            "unit": "user month",
            "raw_product_name": "RDS | Azure Repos",
            "quantity": 4.0,
        })
        candidates = [_make_component("RDS", "instance-month", "mysql.s2.medium", 39.5)]
        matched = _match_rds_storage_component(req, candidates)
        assert matched is None

    def test_rds_user_month_usage_semantic(self):
        req = _make_req({
            "normalized_product": "RDS",
            "unit": "user month",
        })
        assert _billing_usage_semantic(req) == "request_usage"

    def test_rds_user_month_classified_as_usage_unsupported(self):
        """RDS user-month should be classified as usage_not_supported_yet, not unknown."""
        req = _make_req({
            "normalized_product": "RDS",
            "unit": "user month",
            "status": "needs_price_confirmation",
            "status_reason": "RDS user-month is not a standard Huawei Cloud billing model.",
        })
        assert _classify_unquoted_reason(req) == "usage_not_supported_yet"


# ---------------------------------------------------------------------------
# 10. test_cbr_backup_storage_only_quotes_with_storage_component
# ---------------------------------------------------------------------------

class TestCbrStorage:
    def test_cbr_backup_storage_only_quotes_with_storage_component(self):
        """CBR capacity_gib_month can quote IF catalog has GB-month component."""
        req = _make_req({
            "normalized_product": "CBR",
            "unit": "capacity gib month",
            "raw_product_name": "CBR | Backup - Estándar",
            "quantity": 244.65,
            "notes": "unit=Datos almacenados GRS (GB/mes)",
        })
        # With GB-month component — should match
        candidates = [_make_component("CBR", "GB-month", "cbr-storage", 0.10)]
        matched = _match_cbr_storage_component(req, candidates)
        assert matched is not None

    def test_cbr_backup_storage_no_gb_month_stays_unquoted(self):
        """CBR capacity_gib_month stays unquoted if catalog only has protected-server-month."""
        req = _make_req({
            "normalized_product": "CBR",
            "unit": "capacity gib month",
            "raw_product_name": "CBR | Backup Storage",
            "quantity": 244.65,
            "notes": "unit=Datos almacenados GRS (GB/mes)",
        })
        # Only protected-server-month — should NOT match
        candidates = [_make_component("CBR", "protected-server-month", "cbr-basic", 12.8)]
        matched = _match_cbr_storage_component(req, candidates)
        assert matched is None

    def test_cbr_backup_storage_has_capacity_evidence(self):
        req = _make_req({
            "normalized_product": "CBR",
            "unit": "capacity gib month",
            "notes": "unit=Datos almacenados GRS (GB/mes)",
        })
        assert _billing_has_capacity_evidence(req) is True


# ---------------------------------------------------------------------------
# 11. test_safe_usage_quote_does_not_bypass_reconciliation_guard
# ---------------------------------------------------------------------------

class TestSafeUsageReconciliationGuard:
    def test_safe_usage_quote_does_not_bypass_reconciliation_guard(self):
        """_is_safe_usage_quote must enforce billing semantics check."""
        req = _make_req({
            "normalized_product": "OBS",
            "unit": "ops 10k",  # incompatible with GB-month
            "quantity": 17.87,
        })
        comp = _make_component("OBS", "GB-month", "obs-standard", 0.102)
        is_safe, reason = _is_safe_usage_quote(req, comp)
        assert is_safe is False
        assert reason is not None

    def test_safe_usage_quote_requires_capacity_evidence(self):
        """_is_safe_usage_quote must require capacity evidence."""
        req = _make_req({
            "normalized_product": "OBS",
            "unit": "unknown",  # no evidence
        })
        comp = _make_component("OBS", "GB-month", "obs-standard", 0.102)
        is_safe, reason = _is_safe_usage_quote(req, comp)
        assert is_safe is False

    def test_safe_usage_quote_requires_gb_month_catalog(self):
        """_is_safe_usage_quote must require GB-month catalog unit."""
        req = _make_req({
            "normalized_product": "OBS",
            "unit": "capacity gib month",
            "spec": StorageSpec(tier="standard", capacity_gib=100.0).model_dump(),
        })
        comp = _make_component("OBS", "instance-month", "obs-instance", 10.0)
        is_safe, reason = _is_safe_usage_quote(req, comp)
        assert is_safe is False

    def test_safe_usage_quote_passes_for_valid_capacity(self):
        """_is_safe_usage_quote passes for valid capacity requirement + GB-month catalog."""
        req = _make_req({
            "normalized_product": "OBS",
            "unit": "capacity gib month",
            "spec": StorageSpec(tier="standard", capacity_gib=100.0).model_dump(),
        })
        comp = _make_component("OBS", "GB-month", "obs-standard", 0.102)
        is_safe, reason = _is_safe_usage_quote(req, comp)
        assert is_safe is True


# ---------------------------------------------------------------------------
# 12. test_real_billing_total_increases_modestly_without_reintroducing_suspicious_overstatement
# ---------------------------------------------------------------------------

class TestRealAzureSafeUsage:
    def test_real_billing_total_increases_modestly_without_reintroducing_suspicious_overstatement(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Real Azure: total should be >= $7,635 and no suspicious overstatement."""
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

        sum_state = {"requirements": norm_result["requirements"], "quote_ready_items": val_result["quote_ready_items"], "quote_lines": quote_result["quote_lines"], "quote_blockers": val_result["quote_blockers"], "unquoted_items": res_result["unquoted_items"], "quote_context": {"region": "chile"}, "llm_aggregated_billing_items": agg_items, "safe_usage_quoted_count": res_result.get("safe_usage_quoted_count", 0), "audit_log": [], "progress_callback": None}
        sum_result = summarize_quote(sum_state)
        total = sum_result["summary"]["total_monthly_price"]

        # Total should be at least the current baseline
        assert total >= 7635, f"Total ${total:,.2f} should be >= $7,635 baseline"

        # No runaway overpricing
        assert total < 50000, f"Total ${total:,.2f} is suspiciously high — usage mispricing?"

        # SFS Turbo should not be inflated by metadata/ops
        sfs_lines = [ql for ql in quote_result["quote_lines"] if ql.get("product") == "SFS Turbo"]
        sfs_total = sum(ql.get("monthly_price", 0) for ql in sfs_lines)
        # SFS Turbo total should not exceed a reasonable bound
        # (previous baseline was ~$5,272; if metadata/ops were mispriced it would be much higher)
        assert sfs_total < 10000, f"SFS Turbo total ${sfs_total:,.2f} is suspiciously high — metadata/ops mispricing?"

        # No unknown unquoted reasons
        from app.models import RequirementItem
        unquoted = [RequirementItem.model_validate(i) for i in res_result["unquoted_items"]]
        unknown_reasons = sum(1 for i in unquoted if _classify_unquoted_reason(i) == "unknown")
        assert unknown_reasons == 0, f"Found {unknown_reasons} items with 'unknown' unquoted reason"

        # Reconciliation should show no new suspicious items
        recon = sum_result.get("billing_reconciliation", {})
        # Suspicious count should not increase dramatically from baseline
        assert recon.get("suspicious_count", 0) <= 10, "Too many suspicious items in reconciliation"


# ---------------------------------------------------------------------------
# Optional: test_unquoted_reason_prefers_no_compatible_price_unit_over_unknown
# ---------------------------------------------------------------------------

class TestUnquotedReasonStability:
    def test_unquoted_reason_prefers_no_compatible_price_unit_over_unknown(self):
        """RDS storage capacity without GB-month catalog should get no_compatible_price_unit."""
        req = _make_req({
            "normalized_product": "RDS",
            "unit": "capacity gib month",
            "raw_product_name": "RDS | MySQL Storage",
            "notes": "unit=Datos almacenados (GB/mes)",
            "status": "needs_price_confirmation",
            "status_reason": "Storage capacity usage (capacity gib month) cannot be priced with RDS instance-month catalog item. RDS catalog only supports instance-month pricing.",
        })
        classified = _classify_unquoted_reason(req)
        assert classified in ("no_compatible_price_unit", "usage_not_supported_yet"), f"Expected stable reason, got {classified}"

    def test_cbr_storage_reason_is_no_compatible_price_unit(self):
        """CBR storage capacity without GB-month catalog should get no_compatible_price_unit."""
        req = _make_req({
            "normalized_product": "CBR",
            "unit": "capacity gib month",
            "raw_product_name": "CBR | Backup Storage",
            "notes": "unit=Datos almacenados GRS (GB/mes)",
            "status": "needs_price_confirmation",
            "status_reason": "Storage capacity usage (capacity gib month) cannot be priced with CBR protected-server-month catalog item. CBR catalog only supports instance-month pricing.",
        })
        classified = _classify_unquoted_reason(req)
        assert classified in ("no_compatible_price_unit", "usage_not_supported_yet"), f"Expected stable reason, got {classified}"


# ---------------------------------------------------------------------------
# Optional: test_summary_mentions_safe_storage_usage_quote_when_present
# ---------------------------------------------------------------------------

class TestSummarySafeUsageMention:
    def test_summary_mentions_safe_storage_usage_quote_when_present(self):
        """When safe_usage_quoted_count > 0, summary should mention it."""
        state = {
            "requirements": [],
            "quote_ready_items": [],
            "quote_lines": [],
            "quote_blockers": [],
            "unquoted_items": [],
            "safe_usage_quoted_count": 2,
            "audit_log": [],
            "progress_callback": None,
            "quote_context": {"region": "chile"},
        }
        result = summarize_quote(state)
        assumptions = result["summary"].get("assumptions", [])
        safe_assumptions = [a for a in assumptions if "safe" in a.lower() and "storage-capacity" in a.lower()]
        assert len(safe_assumptions) > 0, f"Expected safe storage-capacity assumption, got: {assumptions}"

    def test_summary_no_mention_when_zero_safe_usage(self):
        """When safe_usage_quoted_count = 0, no safe usage assumption."""
        state = {
            "requirements": [],
            "quote_ready_items": [],
            "quote_lines": [],
            "quote_blockers": [],
            "unquoted_items": [],
            "safe_usage_quoted_count": 0,
            "audit_log": [],
            "progress_callback": None,
            "quote_context": {"region": "chile"},
        }
        result = summarize_quote(state)
        assumptions = result["summary"].get("assumptions", [])
        safe_assumptions = [a for a in assumptions if "safe" in a.lower() and "storage-capacity" in a.lower()]
        assert len(safe_assumptions) == 0


# ---------------------------------------------------------------------------
# Optional: test_information_sheet_keeps_gap_and_reconciliation_sections
# ---------------------------------------------------------------------------

class TestInformationSheetPreserved:
    def test_information_sheet_keeps_gap_and_reconciliation_sections_after_safe_usage_quote(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Export should still have gap and reconciliation sections."""
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

        sum_state = {"requirements": norm_result["requirements"], "quote_ready_items": val_result["quote_ready_items"], "quote_lines": quote_result["quote_lines"], "quote_blockers": val_result["quote_blockers"], "unquoted_items": res_result["unquoted_items"], "quote_context": {"region": "chile"}, "llm_aggregated_billing_items": agg_items, "safe_usage_quoted_count": res_result.get("safe_usage_quoted_count", 0), "audit_log": [], "progress_callback": None}
        sum_result = summarize_quote(sum_state)

        export_state = {"requirements": norm_result["requirements"], "quote_ready_items": val_result["quote_ready_items"], "quote_lines": quote_result["quote_lines"], "quote_blockers": val_result["quote_blockers"], "unquoted_items": res_result["unquoted_items"], "price_components": res_result["price_components"], "summary": sum_result["summary"], "mapped_billing_resources": [], "billing_lines": lines, "standardized_billing_resources": [], "llm_aggregated_billing_items": agg_items, "billing_reconciliation": sum_result.get("billing_reconciliation", {}), "billing_gap_analysis": sum_result.get("billing_gap_analysis", {}), "quote_context": {"region": "chile"}, "audit_log": [], "progress_callback": None}

        export_result = export_flexible_workbook(export_state)
        wb_data = export_result.get("workbook")
        assert wb_data is not None, "Export should return workbook"
        wb = load_workbook(BytesIO(wb_data.content))
        assert "Información" in wb.sheetnames, "Información sheet must exist"
        info_sheet = wb["Información"]
        # Check that reconciliation and gap sections exist
        all_values = [str(cell.value or "") for row in info_sheet.iter_rows() for cell in row]
        has_recon = any("reconcil" in v.lower() or "audit" in v.lower() for v in all_values)
        has_gap = any("gap" in v.lower() or "brecha" in v.lower() for v in all_values)
        assert has_recon, "Información sheet should have reconciliation/audit section"
        assert has_gap, "Información sheet should have gap/brecha section"
