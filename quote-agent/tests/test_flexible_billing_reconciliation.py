"""Phase Next+5 tests: billing reconciliation — source-vs-quoted delta, suspicious reclassification, SFS/OBS/EVS capacity gating, summary audit."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.flexible_workflow import (
    _analyze_billing_quote_reconciliation,
    _source_amount_by_requirement,
    _quoted_vs_source_delta,
    _is_suspicious_billing_quote,
    _should_reclassify_as_non_capacity_usage,
    _has_capacity_evidence,
    _reclassify_billing_unit_and_product,
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
    PriceComponent,
    StorageSpec,
    ComputeSpec,
    GenericSpec,
    FlexibleQuoteLine,
    FlexibleQuoteSummary,
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
# 1. test_reconciliation_flags_quote_line_when_quoted_exceeds_source_amount
# ---------------------------------------------------------------------------

class TestReconciliationFlags:
    def test_reconciliation_flags_quote_line_when_quoted_exceeds_source_amount(self):
        """A quote line with quoted > source * 1.5 should be flagged as suspicious."""
        # Use the billing-agg ID format so _source_amount_by_requirement can find it
        item_id = "billing-agg::t.csv::0"
        req = RequirementItem(
            item_id=item_id, source_file="t.csv", source_sheet="csv", row_number=1,
            raw_product_name="SFS Turbo | Archivos",
            quantity=1000.0, quantity_source="billing_standardized",
            unit="capacity gib month", region="chile", normalized_product="SFS Turbo",
            spec=StorageSpec(tier="standard", capacity_gib=1000.0),
        )
        ql = FlexibleQuoteLine(
            line_id=f"line::{item_id}", requirement_item_id=item_id,
            product="SFS Turbo", region="chile",
            quantity=1000.0, unit="GB-month", billing_mode="monthly",
            matched_sku="sfs-turbo-standard", matched_tier="standard",
            unit_price=0.169, monthly_price=169.0, currency="USD",
            assumption="test",
        )
        # Source amount is $50, but quoted is $169 → ratio 3.38x
        state = {
            "llm_aggregated_billing_items": [
                {"source_file": "t.csv", "amount": 50.0},
            ],
            "quote_ready_items": [req.model_dump()],
            "unquoted_items": [],
        }
        assert _is_suspicious_billing_quote(ql, state)


# ---------------------------------------------------------------------------
# 2. test_sfs_unknown_usage_is_not_auto_reclassified_to_capacity_without_capacity_evidence
# ---------------------------------------------------------------------------

class TestSfsUnknownGating:
    def test_sfs_unknown_usage_is_not_auto_reclassified_to_capacity_without_capacity_evidence(self):
        """SFS Turbo with unknown unit and NO capacity evidence must stay unknown."""
        req = RequirementItem(
            item_id="t2", source_file="t.csv", source_sheet="csv", row_number=2,
            raw_product_name="SFS Turbo | Archivos v2 - Frecuente LRS",
            quantity=1023.0, quantity_source="billing_standardized",
            unit="unknown", region="chile", normalized_product="SFS Turbo",
            spec=GenericSpec(sku="Archivos v2 - Frecuente LRS"),
            notes="vendor=azure | unit=10 000 operaciones de lista",
        )
        product, unit, spec = _reclassify_billing_unit_and_product(req)
        assert unit is None, "SFS Turbo unknown without capacity evidence must NOT be reclassified"

    def test_sfs_unknown_ops_stays_unquoted(self):
        """SFS Turbo unknown with ops in notes → should_reclassify returns True."""
        req = RequirementItem(
            item_id="t2b", source_file="t.csv", source_sheet="csv", row_number=2,
            raw_product_name="SFS Turbo | Archivos v2",
            quantity=1023.0, quantity_source="billing_standardized",
            unit="capacity gib month", region="chile", normalized_product="SFS Turbo",
            spec=GenericSpec(sku="Archivos v2"),
            notes="vendor=azure | unit=10 000 operaciones de lista",
        )
        should_reject, reason = _should_reclassify_as_non_capacity_usage(req)
        assert should_reject is True
        assert "operations" in reason.lower() or "capacity" in reason.lower()


# ---------------------------------------------------------------------------
# 3. test_sfs_capacity_evidence_still_allows_gb_month_quote
# ---------------------------------------------------------------------------

class TestSfsCapacityEvidence:
    def test_sfs_capacity_evidence_still_allows_gb_month_quote(self):
        """SFS Turbo with unknown unit + capacity evidence → reclassified to capacity."""
        req = RequirementItem(
            item_id="t3", source_file="t.csv", source_sheet="csv", row_number=3,
            raw_product_name="SFS Turbo | Archivos - LRS",
            quantity=1023.0, quantity_source="billing_standardized",
            unit="unknown", region="chile", normalized_product="SFS Turbo",
            spec=GenericSpec(sku="Archivos - LRS"),
            notes="vendor=azure | unit=Datos almacenados (GB/mes)",
        )
        product, unit, spec = _reclassify_billing_unit_and_product(req)
        assert unit == "capacity gib month"


# ---------------------------------------------------------------------------
# 4. test_obs_unknown_usage_stays_unquoted_without_capacity_evidence
# ---------------------------------------------------------------------------

class TestObsUnknownGating:
    def test_obs_unknown_usage_stays_unquoted_without_capacity_evidence(self):
        """OBS with unknown unit and NO capacity evidence → stays unquoted."""
        req = RequirementItem(
            item_id="t4", source_file="t.csv", source_sheet="csv", row_number=4,
            raw_product_name="OBS | Blob Storage",
            quantity=572.0, quantity_source="billing_standardized",
            unit="unknown", region="chile", normalized_product="OBS",
            spec=GenericSpec(sku="Blob Storage"),
            notes="vendor=azure | unit=10 000 operaciones de lectura",
        )
        should_reject, reason = _should_reclassify_as_non_capacity_usage(req)
        assert should_reject is True


# ---------------------------------------------------------------------------
# 5. test_evs_instance_hours_without_disk_evidence_stays_unquoted
# ---------------------------------------------------------------------------

class TestEvsInstanceHoursGating:
    def test_evs_instance_hours_without_disk_evidence_stays_unquoted(self):
        """EVS instance hours without disk/capacity evidence → stays unquoted."""
        req = RequirementItem(
            item_id="t5", source_file="t.csv", source_sheet="csv", row_number=5,
            raw_product_name="EVS | Managed Disk",
            quantity=0.5, quantity_source="billing_standardized",
            unit="instance hours", region="chile", normalized_product="EVS",
            spec=GenericSpec(sku="Managed Disk"),
        )
        should_reject, reason = _should_reclassify_as_non_capacity_usage(req)
        assert should_reject is True
        assert "capacity" in reason.lower() or "disk" in reason.lower()


# ---------------------------------------------------------------------------
# 6. test_rds_user_month_stays_unquoted
# ---------------------------------------------------------------------------

class TestRdsUserMonthGating:
    def test_rds_user_month_stays_unquoted(self):
        """RDS user-month is not a standard Huawei billing model → stays unquoted."""
        req = RequirementItem(
            item_id="t6", source_file="t.csv", source_sheet="csv", row_number=6,
            raw_product_name="RDS | MySQL User",
            quantity=10.0, quantity_source="billing_standardized",
            unit="user month", region="chile", normalized_product="RDS",
            spec=GenericSpec(sku="MySQL User"),
        )
        should_reject, reason = _should_reclassify_as_non_capacity_usage(req)
        assert should_reject is True
        assert "user-month" in reason.lower()


# ---------------------------------------------------------------------------
# 7. test_reconciliation_helper_reports_top_positive_deltas
# ---------------------------------------------------------------------------

class TestReconciliationDeltas:
    def test_reconciliation_helper_reports_top_positive_deltas(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        recon = state["billing_reconciliation"]
        # Should have top_positive_deltas
        assert "top_positive_deltas" in recon
        # Should have at least some positive deltas (SFS Turbo is overstated)
        top_deltas = recon["top_positive_deltas"]
        assert len(top_deltas) > 0, "Expected positive deltas from SFS Turbo overstatement"
        # Each delta should have required fields
        for td in top_deltas:
            assert "product" in td
            assert "quoted_amount" in td
            assert "source_amount" in td
            assert "delta" in td
            assert td["delta"] > 0


# ---------------------------------------------------------------------------
# 8. test_summary_mentions_reconciliation_warning_when_suspicious_quotes_exist
# ---------------------------------------------------------------------------

class TestSummaryReconciliation:
    def test_summary_mentions_reconciliation_warning_when_suspicious_quotes_exist(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        summary = FlexibleQuoteSummary.model_validate(state["summary"])
        risks = summary.risks
        # Should have a PRICING AUDIT risk
        audit_risks = [r for r in risks if "PRICING AUDIT" in r]
        assert len(audit_risks) > 0, f"Expected PRICING AUDIT risk, got: {risks}"


# ---------------------------------------------------------------------------
# 9. test_information_sheet_mentions_top_delta_items
# ---------------------------------------------------------------------------

class TestInfoReconciliation:
    def test_information_sheet_mentions_top_delta_items(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        result = export_flexible_workbook(state)
        wb = load_workbook(BytesIO(result["workbook"].content))
        ws = wb["Información"]
        all_text = " ".join(str(ws.cell(row, 1).value or "") for row in range(1, 80))
        # Should contain RECONCILIATION WARNING
        assert "RECONCILIATION" in all_text, "Información should mention RECONCILIATION WARNING"


# ---------------------------------------------------------------------------
# 10. test_real_billing_total_drops_from_overstated_candidate_matching_peak
# ---------------------------------------------------------------------------

class TestTotalDrop:
    def test_real_billing_total_drops_from_overstated_candidate_matching_peak(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        """After reconciliation tightening, total should drop from the overstated $10,870 peak."""
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        summary = FlexibleQuoteSummary.model_validate(state["summary"])
        total = summary.total_monthly_price
        # Total should be < $10,870 (the previous overstated peak)
        assert total < 10870, f"Total ${total:,.2f} should be < $10,870 (previous overstated peak)"
        # But should still be > $5,000 (reasonable coverage)
        assert total > 5000, f"Total ${total:,.2f} should be > $5,000 (reasonable coverage)"
        # SFS Turbo should be significantly lower than $8,263 (previous overstated SFS total)
        sfs_total = sum(ql["monthly_price"] for ql in state["quote_lines"] if ql["product"] == "SFS Turbo")
        assert sfs_total < 8263, f"SFS Turbo total ${sfs_total:,.2f} should be < $8,263 (previous overstated)"


# ---------------------------------------------------------------------------
# Optional: test_suspicious_capacity_reclassification_reason_is_stable
# ---------------------------------------------------------------------------

class TestStableReason:
    def test_suspicious_capacity_reclassification_reason_is_stable(self):
        """The suspicious reclassification reason text should be stable across calls."""
        req = RequirementItem(
            item_id="t_opt1", source_file="t.csv", source_sheet="csv", row_number=1,
            raw_product_name="SFS Turbo | Archivos",
            quantity=1023.0, quantity_source="billing_standardized",
            unit="capacity gib month", region="chile", normalized_product="SFS Turbo",
            spec=GenericSpec(sku="Archivos"),
        )
        _, reason1 = _should_reclassify_as_non_capacity_usage(req)
        _, reason2 = _should_reclassify_as_non_capacity_usage(req)
        assert reason1 == reason2
        assert "storage capacity" in reason1.lower() or "capacity" in reason1.lower()


# ---------------------------------------------------------------------------
# Optional: test_gap_analysis_and_reconciliation_can_coexist_in_export_notes
# ---------------------------------------------------------------------------

class TestCoexistence:
    def test_gap_analysis_and_reconciliation_can_coexist_in_export_notes(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        """Both GAP ANALYSIS and RECONCILIATION WARNING should appear in Summary notes."""
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = _make_billing_state(azure_document)
        result = export_flexible_workbook(state)
        wb = load_workbook(BytesIO(result["workbook"].content))
        ws = wb["Summary"]
        notes = str(ws["B19"].value or "")
        assert "GAP ANALYSIS" in notes, "Summary should still have GAP ANALYSIS"
        assert "RECONCILIATION" in notes, "Summary should also have RECONCILIATION WARNING"


# ---------------------------------------------------------------------------
# Extra: test_has_capacity_evidence_helper
# ---------------------------------------------------------------------------

class TestCapacityEvidence:
    def test_unit_with_gb_month_is_capacity_evidence(self):
        req = RequirementItem(
            item_id="ce1", source_file="t.csv", source_sheet="csv", row_number=1,
            raw_product_name="SFS Turbo", quantity=100, quantity_source="billing_standardized",
            unit="capacity gib month", region="chile", normalized_product="SFS Turbo",
        )
        assert _has_capacity_evidence(req) is True

    def test_unit_with_datos_almacenados_is_capacity_evidence(self):
        req = RequirementItem(
            item_id="ce2", source_file="t.csv", source_sheet="csv", row_number=2,
            raw_product_name="SFS Turbo", quantity=100, quantity_source="billing_standardized",
            unit="unknown", region="chile", normalized_product="SFS Turbo",
            notes="vendor=azure | unit=Datos almacenados (GB/mes)",
        )
        assert _has_capacity_evidence(req) is True

    def test_unit_with_operations_is_not_capacity_evidence(self):
        req = RequirementItem(
            item_id="ce3", source_file="t.csv", source_sheet="csv", row_number=3,
            raw_product_name="SFS Turbo", quantity=100, quantity_source="billing_standardized",
            unit="unknown", region="chile", normalized_product="SFS Turbo",
            notes="vendor=azure | unit=10 000 operaciones de lista",
        )
        assert _has_capacity_evidence(req) is False

    def test_no_unit_no_notes_is_not_capacity_evidence(self):
        req = RequirementItem(
            item_id="ce4", source_file="t.csv", source_sheet="csv", row_number=4,
            raw_product_name="SFS Turbo", quantity=100, quantity_source="billing_standardized",
            unit="unknown", region="chile", normalized_product="SFS Turbo",
        )
        assert _has_capacity_evidence(req) is False
