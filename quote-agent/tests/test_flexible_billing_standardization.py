"""Phase B tests: billing document detection, standardization, and RequirementItem generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.flexible_workflow import (
    _detect_billing_document,
    _extract_billing_lines,
    _group_billing_lines,
    _standardize_billing_lines,
    _standardize_billing_group_fallback,
    _build_requirements_from_standardized_billing,
    _classify_resource_kind_fallback,
    _infer_quantity_interpretation_fallback,
    _apply_quantity_rule,
    _infer_region_hint_from_sku,
    _parse_csv_document,
    extract_requirement_items,
)
from app.models import FlexibleQuoteContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

AZURE_CSV_PATH = Path("/root/SMBReference/CGE/azure Billing_invoice_transactions.csv")


@pytest.fixture
def azure_csv_bytes() -> bytes:
    assert AZURE_CSV_PATH.exists(), f"Azure CSV not found at {AZURE_CSV_PATH}"
    return AZURE_CSV_PATH.read_bytes()


@pytest.fixture
def azure_document(azure_csv_bytes: bytes) -> dict:
    return _parse_csv_document(azure_csv_bytes, "azure_billing.csv")


def _minimal_azure_csv() -> bytes:
    return (
        "SEP=,\r\n"
        "DATE (UTC),SERVICE PERIOD (UTC),TRANSACTION TYPE,PRODUCT FAMILY,PRODUCT TYPE,PRODUCT SKU,"
        "INVOICE SECTION,PAYG PRICE CURRENCY,PAYG PRICE,EFFECTIVE PRICE CURRENCY,EFFECTIVE PRICE,"
        "QUANTITY,UNIT TYPE,EXCHANGE RATE,CHARGES/CREDITS CURRENCY,CHARGES/CREDITS,"
        "AZURE CREDITS APPLIED CURRENCY,AZURE CREDITS APPLIED,\r\n"
        '"4/3/2026","3/1/2026 - 3/31/2026","Usage charges - Azure plan","Compute",'
        '"Virtual Machines serie Dv3","D8 v3","Default invoice section","USD","0.364",'
        '"USD","0.364","4468.934022","1 hora de proceso","1","USD","1626.77","USD","0",\r\n'
        '"4/3/2026","3/1/2026 - 3/31/2026","Usage charges - Azure plan","Storage",'
        '"Discos administrados SSD premium","P10 - LRS","Default invoice section","USD","0.142",'
        '"USD","0.142","1","1 disco/mes","1","USD","0.14","USD","0",\r\n'
        '"4/3/2026","3/1/2026 - 3/31/2026","Usage charges - Azure plan","Databases",'
        '"Azure Database for MySQL Flexible Server Burstable BS Series Compute",'
        '"MySQL Flexible Server Burstable BS Series - 1 vCore","Default invoice section",'
        '"USD","0.0215","USD","0.0215","744","1 núcleo virtual/hora","1","USD","15.99",'
        '"USD","0",\r\n'
    ).encode("utf-8-sig")


@pytest.fixture
def minimal_azure_doc() -> dict:
    return _parse_csv_document(_minimal_azure_csv(), "azure_billing.csv")


def _non_billing_document() -> dict:
    """A regular requirement spreadsheet document."""
    return {
        "filename": "requirements.xlsx",
        "sheet": "Sheet1",
        "columns": ["product", "quantity", "region", "spec"],
        "rows": [
            {"product": "ECS", "quantity": "2", "region": "mexico", "spec": "4vCPU 16GB", "_line_number": 2},
            {"product": "EVS", "quantity": "100", "region": "mexico", "spec": "SSD", "_line_number": 3},
        ],
    }


# ---------------------------------------------------------------------------
# 1. test_detect_billing_document_from_azure_columns
# ---------------------------------------------------------------------------

class TestDetectBillingDocument:
    def test_detect_billing_document_from_azure_columns(self, azure_document: dict):
        """Azure CSV document must be detected as a billing document."""
        assert _detect_billing_document(azure_document) is True

    def test_detect_from_document_type_metadata(self):
        doc = {"document_type": "azure_billing_csv", "columns": [], "rows": []}
        assert _detect_billing_document(doc) is True

    def test_detect_from_aws_columns(self):
        doc = {"columns": ["lineItem/LineItemType", "product/ProductFamily", "product/Sku", "lineItem/UsageType"], "rows": []}
        assert _detect_billing_document(doc) is True

    def test_non_billing_document_not_detected(self):
        doc = _non_billing_document()
        assert _detect_billing_document(doc) is False


# ---------------------------------------------------------------------------
# 2. test_extract_billing_lines_from_azure_csv
# ---------------------------------------------------------------------------

class TestExtractBillingLines:
    def test_extract_billing_lines_from_azure_csv(self, minimal_azure_doc: dict):
        lines = _extract_billing_lines(minimal_azure_doc)
        assert len(lines) == 3
        # Check key fields on first line (VM)
        vm_line = lines[0]
        assert vm_line["product_family"] == "Compute"
        assert vm_line["product_type"] == "Virtual Machines serie Dv3"
        assert vm_line["product_sku"] == "D8 v3"
        assert vm_line["unit_type"] == "1 hora de proceso"
        assert vm_line["quantity_raw"] == "4468.934022"
        assert vm_line["amount_raw"] == "1626.77"
        assert vm_line["vendor"] == "azure"
        assert vm_line["currency"] == "USD"

    def test_billing_lines_have_line_numbers(self, minimal_azure_doc: dict):
        lines = _extract_billing_lines(minimal_azure_doc)
        assert lines[0]["line_number"] == 2
        assert lines[1]["line_number"] == 3
        assert lines[2]["line_number"] == 4

    def test_billing_lines_preserve_raw_row(self, minimal_azure_doc: dict):
        lines = _extract_billing_lines(minimal_azure_doc)
        assert "raw_row" in lines[0]
        assert "PRODUCT FAMILY" in lines[0]["raw_row"]


# ---------------------------------------------------------------------------
# 3. test_standardize_billing_lines_fallback_without_llm
# ---------------------------------------------------------------------------

class TestStandardizeBillingFallback:
    def test_standardize_billing_lines_fallback_without_llm(self, minimal_azure_doc: dict, monkeypatch: pytest.MonkeyPatch):
        """When MaaS env vars are missing, fallback must still produce results."""
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        lines = _extract_billing_lines(minimal_azure_doc)
        ctx = FlexibleQuoteContext()
        resources = _standardize_billing_lines(lines, ctx)
        assert len(resources) > 0
        for r in resources:
            assert "resource_kind" in r
            assert "confidence" in r
            assert r["confidence"] > 0

    def test_fallback_classifies_vm(self):
        group = {
            "product_type": "Virtual Machines serie Dv3",
            "product_sku": "D8 v3",
            "unit_type": "1 hora de proceso",
            "product_family": "Compute",
            "vendor": "azure",
            "source_file": "test.csv",
            "source_sheet": "csv",
            "line_numbers": [2],
            "total_quantity": 4468.934022,
            "total_amount": 1626.77,
            "transaction_types": ["Usage charges - Azure plan"],
            "currency": "USD",
            "region_hint": "",
            "service_period": "3/1/2026 - 3/31/2026",
            "sample_rows": [],
        }
        result = _standardize_billing_group_fallback(group)
        assert result["resource_kind"] == "vm"
        assert result["confidence"] == 0.5

    def test_fallback_classifies_database(self):
        group = {
            "product_type": "Azure Database for MySQL Flexible Server",
            "product_sku": "MySQL Flexible Server - 1 vCore",
            "unit_type": "1 núcleo virtual/hora",
            "product_family": "Databases",
            "vendor": "azure",
            "source_file": "test.csv",
            "source_sheet": "csv",
            "line_numbers": [4],
            "total_quantity": 744,
            "total_amount": 15.99,
            "transaction_types": [],
            "currency": "USD",
            "region_hint": "",
            "service_period": "",
            "sample_rows": [],
        }
        result = _standardize_billing_group_fallback(group)
        assert result["resource_kind"] == "database"


# ---------------------------------------------------------------------------
# 4. test_hours_div_744_quantity_rule
# ---------------------------------------------------------------------------

class TestQuantityRules:
    def test_hours_div_744_quantity_rule(self):
        """4468.934022 / 744 must be correctly computed."""
        result = _apply_quantity_rule(4468.934022, "hours_div_744")
        assert abs(result - 6.0039) < 0.01, f"Expected ~6.0039, got {result}"

    def test_keep_raw_capacity(self):
        assert _apply_quantity_rule(244.65, "keep_raw_capacity") == 244.65

    def test_keep_raw_count(self):
        assert _apply_quantity_rule(3.0, "keep_raw_count") == 3.0

    def test_keep_raw_usage(self):
        assert _apply_quantity_rule(717.95, "keep_raw_usage") == 717.95

    def test_vm_hours_gets_hours_div_744(self):
        """VM with instance_hours interpretation should use hours_div_744 rule."""
        from app.flexible_workflow import _infer_derived_quantity_rule
        interp = _infer_quantity_interpretation_fallback("1 hora de proceso")
        rule = _infer_derived_quantity_rule(interp)
        assert rule == "hours_div_744"


# ---------------------------------------------------------------------------
# 5. test_build_requirements_from_standardized_billing_preserves_lineage
# ---------------------------------------------------------------------------

class TestBuildRequirements:
    def test_build_requirements_from_standardized_billing_preserves_lineage(self, minimal_azure_doc: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        lines = _extract_billing_lines(minimal_azure_doc)
        ctx = FlexibleQuoteContext()
        resources = _standardize_billing_lines(lines, ctx)
        requirements = _build_requirements_from_standardized_billing(resources)

        assert len(requirements) > 0
        for req in requirements:
            # notes must contain provenance
            notes = req.get("notes", "")
            assert "vendor=" in notes, f"Missing vendor in notes: {notes}"
            assert "family=" in notes
            assert "lines=" in notes
            assert "confidence=" in notes
            # row_number must be stable (int)
            assert isinstance(req["row_number"], int)
            assert req["row_number"] > 0

    def test_requirement_raw_product_name_format(self, minimal_azure_doc: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        lines = _extract_billing_lines(minimal_azure_doc)
        ctx = FlexibleQuoteContext()
        resources = _standardize_billing_lines(lines, ctx)
        requirements = _build_requirements_from_standardized_billing(resources)
        # VM should have raw_product_name like "vm | Virtual Machines serie Dv3 | D8 v3"
        vm_req = [r for r in requirements if "vm" in r["raw_product_name"].lower()]
        assert len(vm_req) > 0
        assert "Virtual Machines" in vm_req[0]["raw_product_name"]


# ---------------------------------------------------------------------------
# 6. test_non_billing_documents_still_use_existing_path
# ---------------------------------------------------------------------------

class TestNonBillingCompat:
    def test_non_billing_documents_still_use_existing_path(self):
        """A regular requirement spreadsheet must NOT be detected as billing."""
        doc = _non_billing_document()
        assert _detect_billing_document(doc) is False


# ---------------------------------------------------------------------------
# 7. test_llm_output_schema_is_compact_and_validated
# ---------------------------------------------------------------------------

class TestLLMOutputSchema:
    def test_llm_output_schema_is_compact_and_validated(self, minimal_azure_doc: dict, monkeypatch: pytest.MonkeyPatch):
        """When LLM returns valid compact JSON, it must be merged correctly."""
        lines = _extract_billing_lines(minimal_azure_doc)
        groups = _group_billing_lines(lines)

        # Mock the LLM to return valid compact results
        fake_llm_results = []
        for g in groups:
            fake_llm_results.append({
                "resource_kind": "vm",
                "resource_subtype": g["product_type"],
                "spec_hint": g["product_sku"],
                "quantity_interpretation": "instance_hours",
                "derived_quantity_rule": "hours_div_744",
                "operating_system_hint": None,
                "deployment_model_hint": None,
                "confidence": 0.9,
                "rationale": "LLM classified as VM",
                "needs_manual_review": False,
            })

        import app.flexible_workflow as fw_mod
        original = fw_mod._standardize_billing_groups_with_llm

        def mock_llm(groups_arg, ctx):
            return fake_llm_results

        monkeypatch.setattr(fw_mod, "_standardize_billing_groups_with_llm", mock_llm)
        ctx = FlexibleQuoteContext()
        resources = _standardize_billing_lines(lines, ctx)
        assert len(resources) == len(groups)
        for r in resources:
            assert r["confidence"] == 0.9
            assert r["resource_kind"] == "vm"
            assert r["rationale"] == "LLM classified as VM"


# ---------------------------------------------------------------------------
# 8. test_extract_requirement_items_sets_standardized_billing_resources_in_state
# ---------------------------------------------------------------------------

class TestExtractRequirementItemsState:
    def test_extract_requirement_items_sets_standardized_billing_resources_in_state(
        self, minimal_azure_doc: dict, monkeypatch: pytest.MonkeyPatch
    ):
        """When billing documents are present, extract_requirement_items must populate
        billing_lines, billing_groups, llm_aggregated_billing_items, and
        standardized_billing_resources in state."""
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)

        # Build a minimal state that would reach extract_requirement_items
        state = {
            "parsed_documents": [minimal_azure_doc],
            "quote_context": {},
            "audit_log": [],
            "progress_callback": None,
        }

        result = extract_requirement_items(state)

        assert "billing_lines" in result
        assert "billing_groups" in result
        assert "llm_aggregated_billing_items" in result
        assert "standardized_billing_resources" in result
        assert len(result["billing_lines"]) > 0
        assert len(result["billing_groups"]) > 0
        assert len(result["llm_aggregated_billing_items"]) > 0
        assert len(result["standardized_billing_resources"]) > 0
        assert len(result["requirements"]) > 0


# ---------------------------------------------------------------------------
# Region hint extraction
# ---------------------------------------------------------------------------

class TestRegionHint:
    def test_region_hint_from_sku_brasil(self):
        assert _infer_region_hint_from_sku("Backup - Estándar - Sur de Brasil") == "brazil"

    def test_region_hint_from_sku_us_east(self):
        assert _infer_region_hint_from_sku("Fabric Capacity - US East 2") == "us_east"

    def test_region_hint_from_sku_no_match(self):
        assert _infer_region_hint_from_sku("Some Generic SKU") is None


# ---------------------------------------------------------------------------
# Real Azure file: resource group count
# ---------------------------------------------------------------------------

class TestRealAzureFile:
    def test_real_azure_file_resource_group_count(self, azure_document: dict, monkeypatch: pytest.MonkeyPatch):
        """Standardize the real Azure file and count resource groups."""
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        lines = _extract_billing_lines(azure_document)
        groups = _group_billing_lines(lines)
        ctx = FlexibleQuoteContext()
        resources = _standardize_billing_lines(lines, ctx)
        # Must produce at least as many resources as groups
        assert len(resources) == len(groups)
        # All must have required fields
        for r in resources:
            assert "resource_kind" in r
            assert "derived_quantity" in r
            assert "source_line_numbers" in r
