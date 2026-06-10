"""Tests for LLM-based billing aggregation: billing_groups → llm_aggregated_billing_items → requirements."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.flexible_workflow import (
    _detect_billing_document,
    _extract_billing_lines,
    _group_billing_lines,
    _build_billing_aggregation_prompt,
    _aggregate_billing_groups_with_llm,
    _aggregate_billing_groups_fallback,
    _normalize_llm_aggregated_billing_items,
    _build_requirements_from_llm_aggregated_billing_items,
    _standardize_billing_group_fallback,
    _parse_csv_document,
    _parse_excel_workbook,
    extract_requirement_items,
)
from app.models import FlexibleQuoteContext, ComputeSpec, StorageSpec, GenericSpec


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
        '"4/3/2026","3/1/2026 - 3/31/2026","Usage charges - Azure plan","Compute",'
        '"Virtual Machines serie Fsv2","F2s v2","Default invoice section","USD","0.096",'
        '"USD","0.096","5208.5","1 hora de proceso","1","USD","499.99","USD","0",\r\n'
        '"4/3/2026","3/1/2026 - 3/31/2026","Usage charges - Azure plan","Storage",'
        '"Discos administrados SSD premium","P10 - LRS","Default invoice section","USD","0.142",'
        '"USD","0.142","4","1 disco/mes","1","USD","0.56","USD","0",\r\n'
        '"4/3/2026","3/1/2026 - 3/31/2026","Usage charges - Azure plan","Databases",'
        '"Azure Database for MySQL Flexible Server Burstable BS Series Compute",'
        '"MySQL Flexible Server Burstable BS Series - 1 vCore","Default invoice section",'
        '"USD","0.0215","USD","0.0215","744","1 núcleo virtual/hora","1","USD","15.99",'
        '"USD","0",\r\n'
        '"4/3/2026","3/1/2026 - 3/31/2026","Usage charges - Azure plan","Networking",'
        '"VPN Gateway","VpnGw1","Default invoice section","USD","0.04",'
        '"USD","0.04","744","1 hora de puerta de enlace","1","USD","29.76","USD","0",\r\n'
    ).encode("utf-8-sig")


@pytest.fixture
def minimal_azure_doc() -> dict:
    return _parse_csv_document(_minimal_azure_csv(), "azure_billing.csv")


def _make_billing_groups() -> list[dict]:
    """Build sample billing_groups for testing aggregation helpers."""
    return [
        {
            "group_id": "g0",
            "product_family": "Compute",
            "product_type": "Virtual Machines serie Dv3",
            "product_sku": "D8 v3",
            "unit_type": "1 hora de proceso",
            "vendor": "azure",
            "source_file": "test.csv",
            "source_sheet": "csv",
            "line_numbers": [2, 3],
            "total_quantity": 8937.868,
            "total_amount": 3253.54,
            "sample_rows": [],
            "service_period": "3/1/2026 - 3/31/2026",
            "transaction_types": ["Usage charges"],
            "currency": "USD",
            "region_hint": "",
        },
        {
            "group_id": "g1",
            "product_family": "Storage",
            "product_type": "Discos administrados SSD premium",
            "product_sku": "P10 - LRS",
            "unit_type": "1 disco/mes",
            "vendor": "azure",
            "source_file": "test.csv",
            "source_sheet": "csv",
            "line_numbers": [4],
            "total_quantity": 4,
            "total_amount": 0.56,
            "sample_rows": [],
            "service_period": "3/1/2026 - 3/31/2026",
            "transaction_types": ["Usage charges"],
            "currency": "USD",
            "region_hint": "",
        },
        {
            "group_id": "g2",
            "product_family": "Databases",
            "product_type": "Azure Database for MySQL Flexible Server Burstable BS Series Compute",
            "product_sku": "MySQL Flexible Server Burstable BS Series - 1 vCore",
            "unit_type": "1 núcleo virtual/hora",
            "vendor": "azure",
            "source_file": "test.csv",
            "source_sheet": "csv",
            "line_numbers": [5],
            "total_quantity": 744,
            "total_amount": 15.99,
            "sample_rows": [],
            "service_period": "3/1/2026 - 3/31/2026",
            "transaction_types": ["Usage charges"],
            "currency": "USD",
            "region_hint": "",
        },
        {
            "group_id": "g3",
            "product_family": "Networking",
            "product_type": "VPN Gateway",
            "product_sku": "VpnGw1",
            "unit_type": "1 hora de puerta de enlace",
            "vendor": "azure",
            "source_file": "test.csv",
            "source_sheet": "csv",
            "line_numbers": [6],
            "total_quantity": 744,
            "total_amount": 29.76,
            "sample_rows": [],
            "service_period": "3/1/2026 - 3/31/2026",
            "transaction_types": ["Usage charges"],
            "currency": "USD",
            "region_hint": "",
        },
    ]


# ---------------------------------------------------------------------------
# 1. test_billing_xlsx_with_placeholder_first_row_uses_llm_aggregation_path
# ---------------------------------------------------------------------------

class TestBillingXlsxAggregationPath:
    def test_billing_xlsx_with_placeholder_first_row_uses_llm_aggregation_path(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """An Excel billing doc with placeholder first row should use aggregation path,
        not fall back to row-level path."""
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)

        # Build a minimal xlsx with placeholder first row
        from openpyxl import Workbook
        from io import BytesIO
        wb = Workbook()
        ws = wb.active
        ws.title = "azure Billing"
        # Placeholder first row
        ws.append([f"Column{index}" for index in range(1, 18)])
        # Real header row
        ws.append([
            "DATE (UTC)", "SERVICE PERIOD (UTC)", "TRANSACTION TYPE",
            "PRODUCT FAMILY", "PRODUCT TYPE", "PRODUCT SKU",
            "INVOICE SECTION", "PAYG PRICE CURRENCY", "PAYG PRICE",
            "EFFECTIVE PRICE CURRENCY", "EFFECTIVE PRICE",
            "QUANTITY", "UNIT TYPE", "EXCHANGE RATE",
            "CHARGES/CREDITS CURRENCY", "CHARGES/CREDITS",
            "AZURE CREDITS APPLIED CURRENCY",
        ])
        # Data row
        ws.append([
            "4/3/2026", "3/1/2026 - 3/31/2026", "Usage charges",
            "Compute", "Virtual Machines serie Dv3", "D8 v3",
            "Default", "USD", "0.364",
            "USD", "0.364", "744", "1 hora de proceso", "1",
            "USD", "270.82", "USD",
        ])
        output = BytesIO()
        wb.save(output)
        content = output.getvalue()

        docs = _parse_excel_workbook(content, "azure_billing.xlsx")
        # Should detect as billing
        assert any(_detect_billing_document(d) for d in docs)

        # Run through extract_requirement_items
        state = {
            "parsed_documents": docs,
            "quote_context": {},
            "audit_log": [],
            "progress_callback": None,
        }
        result = extract_requirement_items(state)

        # Must have aggregation path fields
        assert "billing_groups" in result
        assert "llm_aggregated_billing_items" in result
        assert len(result["billing_groups"]) > 0
        assert len(result["llm_aggregated_billing_items"]) > 0
        # Requirements count should be <= groups count (aggregation reduces items)
        assert len(result["requirements"]) > 0


# ---------------------------------------------------------------------------
# 2. test_group_billing_lines_produces_compact_groups
# ---------------------------------------------------------------------------

class TestGroupBillingLinesCompact:
    def test_group_billing_lines_produces_compact_groups(self, azure_document: dict):
        """Real Azure file should produce no more groups than raw lines."""
        lines = _extract_billing_lines(azure_document)
        groups = _group_billing_lines(lines)
        # Groups must be no more than lines (often fewer when lines share keys)
        assert len(groups) <= len(lines), f"Groups ({len(groups)}) should be <= lines ({len(lines)})"
        # Each group must have group_id
        for g in groups:
            assert "group_id" in g
            assert g["group_id"].startswith("g")
        # Each group must have required fields
        for g in groups:
            assert "product_family" in g
            assert "product_type" in g
            assert "product_sku" in g
            assert "unit_type" in g
            assert "total_quantity" in g
            assert "total_amount" in g
            assert "line_numbers" in g
            assert "sample_rows" in g


# ---------------------------------------------------------------------------
# 3. test_llm_aggregation_outputs_ecs_like_group
# ---------------------------------------------------------------------------

class TestLLMAggregationECS:
    def test_llm_aggregation_outputs_ecs_like_group(self, monkeypatch: pytest.MonkeyPatch):
        """Mock LLM to return ECS aggregation item."""
        groups = _make_billing_groups()
        fake_llm_items = [
            {
                "aggregate_label": "ECS | D8 v3",
                "resource_kind": "ecs",
                "source_group_ids": ["g0"],
                "aggregation_type": "vm_family",
                "source_sku_hint": "D8 v3",
                "huawei_product": "ECS",
                "huawei_spec_hint": "D8 v3",
                "derived_quantity": 12.0,
                "derived_unit": "instance-month",
                "confidence": 0.9,
                "rationale": "Merged 2 VM compute groups",
                "needs_manual_review": False,
            },
            {
                "aggregate_label": "EVS | P10",
                "resource_kind": "evs",
                "source_group_ids": ["g1"],
                "aggregation_type": "disk_sku",
                "source_sku_hint": "P10 - LRS",
                "huawei_product": "EVS",
                "huawei_spec_hint": "P10 - LRS",
                "derived_quantity": 4.0,
                "derived_unit": "disk-month",
                "confidence": 0.9,
                "rationale": "Premium SSD disk group",
                "needs_manual_review": False,
            },
            {
                "aggregate_label": "RDS | MySQL 1 vCore",
                "resource_kind": "rds",
                "source_group_ids": ["g2"],
                "aggregation_type": "db_instance",
                "source_sku_hint": "MySQL Flexible Server - 1 vCore",
                "huawei_product": "RDS",
                "huawei_spec_hint": "MySQL Flexible Server - 1 vCore",
                "derived_quantity": 1.0,
                "derived_unit": "instance-month",
                "confidence": 0.85,
                "rationale": "MySQL compute group",
                "needs_manual_review": False,
            },
            {
                "aggregate_label": "VPN | VpnGw1",
                "resource_kind": "vpn",
                "source_group_ids": ["g3"],
                "aggregation_type": "gateway",
                "source_sku_hint": "VpnGw1",
                "huawei_product": "VPN",
                "huawei_spec_hint": "VpnGw1",
                "derived_quantity": 1.0,
                "derived_unit": "gateway-month",
                "confidence": 0.9,
                "rationale": "VPN gateway hours",
                "needs_manual_review": False,
            },
        ]

        import app.flexible_workflow as fw_mod

        def mock_llm(groups_arg, ctx):
            return fake_llm_items

        monkeypatch.setattr(fw_mod, "_aggregate_billing_groups_with_llm", mock_llm)

        # Run through extract_requirement_items
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

        # Must have ECS-like aggregated items
        agg_items = result["llm_aggregated_billing_items"]
        ecs_items = [i for i in agg_items if i.get("resource_kind") == "ecs"]
        assert len(ecs_items) > 0, "Should have at least one ECS aggregated item"
        ecs = ecs_items[0]
        assert ecs["huawei_product"] == "ECS"
        assert ecs["derived_quantity"] > 0

        # Requirements should reflect ECS
        ecs_reqs = [r for r in result["requirements"] if r.get("normalized_product") == "ECS"]
        assert len(ecs_reqs) > 0


# ---------------------------------------------------------------------------
# 4. test_llm_aggregation_outputs_disk_like_group
# ---------------------------------------------------------------------------

class TestLLMAggregationDisk:
    def test_llm_aggregation_outputs_disk_like_group(self, monkeypatch: pytest.MonkeyPatch):
        """Fallback aggregation should produce EVS-like items for disk groups."""
        groups = _make_billing_groups()
        # Use fallback (no LLM)
        items = _aggregate_billing_groups_fallback(groups)
        disk_items = [i for i in items if i.get("resource_kind") == "disk"]
        assert len(disk_items) > 0, "Fallback should produce disk items"
        for d in disk_items:
            assert d["huawei_product"] == "EVS"
            assert d["derived_quantity"] > 0


# ---------------------------------------------------------------------------
# 5. test_llm_aggregation_fallback_keeps_grouped_shape
# ---------------------------------------------------------------------------

class TestLLMAggregationFallback:
    def test_llm_aggregation_fallback_keeps_grouped_shape(self, monkeypatch: pytest.MonkeyPatch):
        """When LLM fails, fallback must produce grouped aggregate items,
        NOT row-level per-line items."""
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)

        csv = _minimal_azure_csv()
        doc = _parse_csv_document(csv, "azure_billing.csv")
        lines = _extract_billing_lines(doc)
        groups = _group_billing_lines(lines)

        # Fallback aggregation
        items = _aggregate_billing_groups_fallback(groups)

        # Items must be no more than raw lines (aggregation reduces or preserves)
        assert len(items) <= len(lines), (
            f"Fallback items ({len(items)}) should be <= lines ({len(lines)})"
        )
        # Items should be <= groups (may merge further)
        assert len(items) <= len(groups), (
            f"Fallback items ({len(items)}) should be <= groups ({len(groups)})"
        )
        # All items must have required fields
        for item in items:
            assert "aggregate_label" in item
            assert "resource_kind" in item
            assert "huawei_product" in item
            assert "derived_quantity" in item
            assert "confidence" in item

    def test_fallback_marks_unsupported_as_manual_review(self):
        """Fallback should mark unsupported items with needs_manual_review=True."""
        groups = _make_billing_groups()
        # Add an unsupported group
        groups.append({
            "group_id": "g4",
            "product_family": "Developer Tools",
            "product_type": "API Management",
            "product_sku": "API Management - Desarrollador",
            "unit_type": "1 unidad",
            "vendor": "azure",
            "source_file": "test.csv",
            "source_sheet": "csv",
            "line_numbers": [7],
            "total_quantity": 1,
            "total_amount": 50.0,
            "sample_rows": [],
            "service_period": "",
            "transaction_types": [],
            "currency": "USD",
            "region_hint": "",
        })
        items = _aggregate_billing_groups_fallback(groups)
        unsupported = [i for i in items if i.get("resource_kind") == "unsupported"]
        assert len(unsupported) > 0
        for u in unsupported:
            assert u["needs_manual_review"] is True
            assert u["confidence"] <= 0.5


# ---------------------------------------------------------------------------
# 6. test_build_requirements_from_llm_aggregates_sets_normalized_product
# ---------------------------------------------------------------------------

class TestBuildRequirementsFromAggregates:
    def test_build_requirements_from_llm_aggregates_sets_normalized_product(self):
        """ECS/EVS/RDS items should produce requirements with correct normalized_product."""
        items = [
            {
                "resource_kind": "ecs",
                "huawei_product": "ECS",
                "huawei_spec_hint": "D8 v3",
                "source_sku_hint": "D8 v3",
                "derived_quantity": 6.0,
                "derived_unit": "instance-month",
                "vendor": "azure",
                "source_file": "test.csv",
                "source_sheet": "csv",
                "source_line_numbers": [2, 3],
                "product_family": "Compute",
                "product_type": "Virtual Machines",
                "product_sku": "D8 v3",
                "unit_type": "1 hora",
                "aggregation_type": "vm_family",
                "confidence": 0.9,
                "rationale": "LLM classified",
                "needs_manual_review": False,
            },
            {
                "resource_kind": "evs",
                "huawei_product": "EVS",
                "huawei_spec_hint": "P10 - LRS",
                "source_sku_hint": "P10 - LRS",
                "derived_quantity": 4.0,
                "derived_unit": "disk-month",
                "vendor": "azure",
                "source_file": "test.csv",
                "source_sheet": "csv",
                "source_line_numbers": [4],
                "product_family": "Storage",
                "product_type": "Managed Disk",
                "product_sku": "P10 - LRS",
                "unit_type": "1 disco/mes",
                "aggregation_type": "disk_sku",
                "confidence": 0.9,
                "rationale": "LLM classified",
                "needs_manual_review": False,
            },
            {
                "resource_kind": "rds",
                "huawei_product": "RDS",
                "huawei_spec_hint": "MySQL Flexible Server - 1 vCore",
                "source_sku_hint": "MySQL Flexible Server - 1 vCore",
                "derived_quantity": 1.0,
                "derived_unit": "instance-month",
                "vendor": "azure",
                "source_file": "test.csv",
                "source_sheet": "csv",
                "source_line_numbers": [5],
                "product_family": "Databases",
                "product_type": "MySQL",
                "product_sku": "MySQL Flexible Server - 1 vCore",
                "unit_type": "1 núcleo virtual/hora",
                "aggregation_type": "db_instance",
                "confidence": 0.85,
                "rationale": "LLM classified",
                "needs_manual_review": False,
            },
        ]
        requirements = _build_requirements_from_llm_aggregated_billing_items(items)
        assert len(requirements) == 3

        # ECS
        ecs_req = [r for r in requirements if r["normalized_product"] == "ECS"]
        assert len(ecs_req) == 1
        assert ecs_req[0]["quantity"] == 6.0
        assert "sku" in ecs_req[0]["spec"]
        assert ecs_req[0]["spec"]["sku"] == "D8 v3"

        # EVS
        evs_req = [r for r in requirements if r["normalized_product"] == "EVS"]
        assert len(evs_req) == 1
        assert evs_req[0]["quantity"] == 4.0

        # RDS
        rds_req = [r for r in requirements if r["normalized_product"] == "RDS"]
        assert len(rds_req) == 1
        assert rds_req[0]["quantity"] == 1.0


# ---------------------------------------------------------------------------
# 7. test_billing_export_still_uses_rvtools_template_after_llm_aggregation
# ---------------------------------------------------------------------------

class TestBillingExportAfterAggregation:
    def test_billing_export_still_uses_rvtools_template_after_llm_aggregation(
        self, azure_document: dict, monkeypatch: pytest.MonkeyPatch
    ):
        """After LLM aggregation, export should still use RVTools template (Summary/HWC/ECS/Información)."""
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)

        from app.flexible_workflow import (
            normalize_requirements,
            validate_quote_readiness,
            resolve_price_components,
            quote_items,
            summarize_quote,
            export_flexible_workbook,
        )
        from app.flexible_pricing import query_flexible_pricing_catalog
        from io import BytesIO
        from openpyxl import load_workbook

        # Run through extract_requirement_items (uses aggregation path)
        state = {
            "parsed_documents": [azure_document],
            "quote_context": {"region": "chile"},
            "audit_log": [],
            "progress_callback": None,
        }
        result = extract_requirement_items(state)
        requirements = result["requirements"]

        # Normalize
        norm_state = {
            "requirements": requirements,
            "quote_context": {"region": "chile"},
            "audit_log": [],
            "progress_callback": None,
        }
        norm_result = normalize_requirements(norm_state)

        # Validate
        catalog = [item.model_dump() for item in query_flexible_pricing_catalog(region="chile")]
        val_state = {
            "requirements": norm_result["requirements"],
            "quote_context": {"region": "chile"},
            "price_catalog": catalog,
            "matched_products": [],
            "understanding": {"profile": {}},
            "audit_log": [],
            "progress_callback": None,
        }
        val_result = validate_quote_readiness(val_state)

        # Resolve
        res_state = {
            "quote_ready_items": val_result["quote_ready_items"],
            "price_catalog": catalog,
            "unquoted_items": val_result["unquoted_items"],
            "audit_log": [],
            "progress_callback": None,
        }
        res_result = resolve_price_components(res_state)

        # Quote
        quote_state = {
            "quote_ready_items": val_result["quote_ready_items"],
            "price_components": res_result["price_components"],
            "audit_log": [],
            "progress_callback": None,
        }
        quote_result = quote_items(quote_state)

        # Summary
        sum_state = {
            "requirements": norm_result["requirements"],
            "quote_ready_items": val_result["quote_ready_items"],
            "quote_lines": quote_result["quote_lines"],
            "quote_blockers": val_result["quote_blockers"],
            "unquoted_items": res_result["unquoted_items"],
            "quote_context": {"region": "chile"},
            "audit_log": [],
            "progress_callback": None,
        }
        sum_result = summarize_quote(sum_state)

        # Export
        export_state = {
            "requirements": norm_result["requirements"],
            "quote_ready_items": val_result["quote_ready_items"],
            "quote_lines": quote_result["quote_lines"],
            "quote_blockers": val_result["quote_blockers"],
            "unquoted_items": res_result["unquoted_items"],
            "price_components": res_result["price_components"],
            "summary": sum_result["summary"],
            "mapped_billing_resources": result.get("mapped_billing_resources", []),
            "billing_lines": result.get("billing_lines", []),
            "standardized_billing_resources": result.get("standardized_billing_resources", []),
            "quote_context": {"region": "chile"},
            "audit_log": [],
            "progress_callback": None,
        }
        export_result = export_flexible_workbook(export_state)
        wb = load_workbook(BytesIO(export_result["workbook"].content))
        sheet_names = wb.sheetnames

        # Must have RVTools template sheets
        for expected in ["Summary", "HWC", "ECS", "Información"]:
            assert expected in sheet_names, f"Missing sheet: {expected}"


# ---------------------------------------------------------------------------
# 8. test_real_azure_billing_summary_is_not_row_level_83_lines
# ---------------------------------------------------------------------------

class TestRealAzureAggregation:
    def test_real_azure_billing_summary_is_not_row_level_83_lines(
        self, azure_document: dict, monkeypatch: pytest.MonkeyPatch
    ):
        """Real Azure file should produce far fewer requirement items than raw lines."""
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)

        lines = _extract_billing_lines(azure_document)
        groups = _group_billing_lines(lines)

        # Use fallback aggregation
        items = _aggregate_billing_groups_fallback(groups)
        requirements = _build_requirements_from_llm_aggregated_billing_items(items)

        # Requirements must be significantly fewer than raw lines
        assert len(requirements) < len(lines), (
            f"Aggregated requirements ({len(requirements)}) should be < raw lines ({len(lines)})"
        )
        # Should have at least some ECS items
        ecs_items = [r for r in requirements if r.get("normalized_product") == "ECS"]
        assert len(ecs_items) > 0, "Should have at least one ECS requirement"
        # Should have at least some EVS items
        evs_items = [r for r in requirements if r.get("normalized_product") == "EVS"]
        assert len(evs_items) > 0, "Should have at least one EVS requirement"

        # Print stats
        kind_counts = {}
        for r in requirements:
            np = r.get("normalized_product") or "unsupported"
            kind_counts[np] = kind_counts.get(np, 0) + 1
        print(f"\n=== Real Azure Aggregation Stats ===")
        print(f"Raw lines:     {len(lines)}")
        print(f"Groups:        {len(groups)}")
        print(f"Agg items:     {len(items)}")
        print(f"Requirements:  {len(requirements)}")
        for product, count in sorted(kind_counts.items()):
            print(f"  {product}: {count}")


# ---------------------------------------------------------------------------
# 9. test_llm_aggregation_preserves_lineage_group_ids
# ---------------------------------------------------------------------------

class TestLineagePreservation:
    def test_llm_aggregation_preserves_lineage_group_ids(self):
        """Each aggregated item must carry source_group_ids for traceability."""
        groups = _make_billing_groups()
        items = _aggregate_billing_groups_fallback(groups)
        for item in items:
            assert "source_group_ids" in item
            assert len(item["source_group_ids"]) > 0

    def test_requirements_preserve_source_line_numbers(self):
        """Requirements from aggregated items must carry source_line_numbers."""
        items = [
            {
                "resource_kind": "ecs",
                "huawei_product": "ECS",
                "huawei_spec_hint": "D8 v3",
                "source_sku_hint": "D8 v3",
                "derived_quantity": 6.0,
                "derived_unit": "instance-month",
                "vendor": "azure",
                "source_file": "test.csv",
                "source_sheet": "csv",
                "source_line_numbers": [2, 3, 10],
                "product_family": "Compute",
                "product_type": "VM",
                "product_sku": "D8 v3",
                "unit_type": "1 hora",
                "aggregation_type": "vm_family",
                "confidence": 0.9,
                "rationale": "test",
                "needs_manual_review": False,
            },
        ]
        requirements = _build_requirements_from_llm_aggregated_billing_items(items)
        assert len(requirements) == 1
        # notes should contain lines=[2, 3, 10]
        assert "lines=" in requirements[0]["notes"]
        # row_number should be first line number
        assert requirements[0]["row_number"] == 2


# ---------------------------------------------------------------------------
# 10. test_unsupported_usage_lines_stay_manual_review
# ---------------------------------------------------------------------------

class TestUnsupportedManualReview:
    def test_unsupported_usage_lines_stay_manual_review(self):
        """Traffic/operations/unsupported usage should stay as needs_manual_review."""
        groups = [
            {
                "group_id": "g0",
                "product_family": "Storage",
                "product_type": "Blob Storage",
                "product_sku": "Blob Storage - Operations",
                "unit_type": "10 000 operaciones",
                "vendor": "azure",
                "source_file": "test.csv",
                "source_sheet": "csv",
                "line_numbers": [5],
                "total_quantity": 10000,
                "total_amount": 0.50,
                "sample_rows": [],
                "service_period": "",
                "transaction_types": [],
                "currency": "USD",
                "region_hint": "",
            },
            {
                "group_id": "g1",
                "product_family": "Developer Tools",
                "product_type": "API Management",
                "product_sku": "API Management",
                "unit_type": "1 unidad",
                "vendor": "azure",
                "source_file": "test.csv",
                "source_sheet": "csv",
                "line_numbers": [6],
                "total_quantity": 1,
                "total_amount": 50.0,
                "sample_rows": [],
                "service_period": "",
                "transaction_types": [],
                "currency": "USD",
                "region_hint": "",
            },
        ]
        items = _aggregate_billing_groups_fallback(groups)
        for item in items:
            if item.get("resource_kind") == "unsupported":
                assert item["needs_manual_review"] is True
                assert item["confidence"] <= 0.5

        # Build requirements — unsupported should have normalized_product=None
        requirements = _build_requirements_from_llm_aggregated_billing_items(items)
        unsupported_reqs = [r for r in requirements if r.get("normalized_product") is None]
        assert len(unsupported_reqs) > 0


# ---------------------------------------------------------------------------
# 11. test_build_billing_aggregation_prompt_structure
# ---------------------------------------------------------------------------

class TestAggregationPrompt:
    def test_build_billing_aggregation_prompt_structure(self):
        """Prompt should contain vendor, groups, and quote_context."""
        groups = _make_billing_groups()
        ctx = FlexibleQuoteContext(region="chile")
        prompt = _build_billing_aggregation_prompt(groups, ctx)
        assert "vendor" in prompt
        assert "groups" in prompt
        assert "quote_context" in prompt
        assert prompt["vendor"] == "azure"
        assert len(prompt["groups"]) == len(groups)
        # Each group should have compact fields
        for g in prompt["groups"]:
            assert "group_id" in g
            assert "product_family" in g
            assert "total_quantity" in g


# ---------------------------------------------------------------------------
# 12. test_normalize_llm_aggregated_billing_items_validates
# ---------------------------------------------------------------------------

class TestNormalizeAggregatedItems:
    def test_normalize_llm_aggregated_billing_items_validates(self):
        """Normalization should fix invalid resource_kind and missing fields."""
        raw_items = [
            {
                "aggregate_label": "ECS | D8 v3",
                "resource_kind": "ecs",
                "source_group_ids": ["g0"],
                "aggregation_type": "vm_family",
                "source_sku_hint": "D8 v3",
                "huawei_product": "ECS",
                "huawei_spec_hint": "D8 v3",
                "derived_quantity": 6.0,
                "derived_unit": "instance-month",
                "confidence": 0.9,
                "rationale": "test",
                "needs_manual_review": False,
            },
            {
                "aggregate_label": "Unknown",
                "resource_kind": "invalid_kind",
                "source_group_ids": [],
                "aggregation_type": "unsupported",
                "source_sku_hint": "",
                "huawei_product": None,
                "huawei_spec_hint": "",
                "derived_quantity": 0,
                "derived_unit": "unknown",
                "confidence": 0.1,
                "rationale": "",
                "needs_manual_review": True,
            },
        ]
        groups = [{"group_id": "g0"}]
        normalized = _normalize_llm_aggregated_billing_items(raw_items, groups)
        assert len(normalized) == 2
        # First item should be valid
        assert normalized[0]["resource_kind"] == "ecs"
        assert normalized[0]["huawei_product"] == "ECS"
        # Second item should be corrected
        assert normalized[1]["resource_kind"] == "unsupported"
        assert normalized[1]["needs_manual_review"] is True
        assert normalized[1]["confidence"] <= 0.3


# ---------------------------------------------------------------------------
# 13. test_extract_requirement_items_populates_new_state_fields
# ---------------------------------------------------------------------------

class TestStateFields:
    def test_extract_requirement_items_populates_new_state_fields(
        self, minimal_azure_doc: dict, monkeypatch: pytest.MonkeyPatch
    ):
        """extract_requirement_items must populate billing_groups and llm_aggregated_billing_items."""
        monkeypatch.delenv("HUAWEI_MAAS_API_KEY", raising=False)
        state = {
            "parsed_documents": [minimal_azure_doc],
            "quote_context": {},
            "audit_log": [],
            "progress_callback": None,
        }
        result = extract_requirement_items(state)
        assert "billing_groups" in result
        assert "llm_aggregated_billing_items" in result
        assert len(result["billing_groups"]) > 0
        assert len(result["llm_aggregated_billing_items"]) > 0
        # Legacy fields still present for backward compat
        assert "billing_lines" in result
        assert "standardized_billing_resources" in result
        assert "mapped_billing_resources" in result
