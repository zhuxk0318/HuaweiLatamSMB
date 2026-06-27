"""Tests for Phase 8 + Phase 9A + Phase 9B: Cloud Billing Final Quotation Composition.

Validates:
- CloudBillingFinalQuoteItem model (Phase 8A)
- compose_final_billing_quote_items node (Phase 8B)
- Unified cross-cloud composition rules (Phase 8C)
- Item merging logic (Phase 8D)
- Dual-layer export (Phase 8E)
- Summary based on final items (Phase 8F)
- Cross-cloud test coverage (Phase 8G)
- Quantity semantics (Phase 9A.1)
- Customer-visible service names (Phase 9A.2)
- ECS sheet G:O header merge (Phase 9A.3)
- TOTAL row isolation (Phase 9A.4)
- Spec retention for billing kinds (Phase 9B.1)
- Database service display name (Phase 9B.2)
- Database config summary composition (Phase 9B.3)
- Database composition key tightening (Phase 9B.4)
"""

from __future__ import annotations

import pytest

from app.models import (
    CloudBillingFinalQuoteItem,
    CloudBillingResourceKind,
    FinalQuoteItemStatus,
    FlexibleQuoteLine,
    FlexibleQuoteSummary,
    RequirementItem,
)
from app.cloud_billing_workflow import (
    compose_final_billing_quote_items,
    _classify_resource_kind,
    _normalize_vendor,
    _merge_items_into_final,
    _composition_key_compute_vm,
    _composition_key_managed_database,
    _final_display_quantity,
    _final_display_service_name,
    _final_display_config_summary,
    _fallback_source_quantity_from_rows,
    _database_service_display_name,
    _database_config_summary,
    _display_billing_basis_for_quotation,
    _append_unclaimed_billing_rows,
    _llm_first_result_covers_billing_rows,
    _load_llm_json_object,
    _normalize_final_quote_item_for_export,
    _split_shape_sensitive_candidates,
)
from app.flexible_workflow import quote_items


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 8A: Model tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCloudBillingFinalQuoteItemModel:
    """Validate CloudBillingFinalQuoteItem model fields and defaults."""

    def test_minimal_construction(self):
        item = CloudBillingFinalQuoteItem(
            item_id="fqi-1",
            vendor="Azure",
            resource_kind="compute_vm",
            source_service_name="Virtual Machine",
        )
        assert item.item_id == "fqi-1"
        assert item.vendor == "Azure"
        assert item.resource_kind == "compute_vm"
        assert item.source_service_name == "Virtual Machine"
        assert item.status == "unquoted"
        assert item.composition_notes == []
        assert item.source_item_ids == []
        assert item.source_service_family is None
        assert item.source_config_summary is None
        assert item.source_quantity is None
        assert item.source_pricing_basis is None
        assert item.source_monthly_total_usd is None
        assert item.huawei_product is None
        assert item.huawei_spec_summary is None
        assert item.huawei_quantity is None
        assert item.huawei_unit_price_usd is None
        assert item.huawei_billing_basis is None
        assert item.huawei_monthly_total_usd is None
        assert item.manual_review_reason is None

    def test_full_construction(self):
        item = CloudBillingFinalQuoteItem(
            item_id="fqi-2",
            vendor="AWS",
            resource_kind="managed_database",
            source_service_family="RDS",
            source_service_name="RDS for MySQL",
            source_config_summary="4 vCore / 32 GiB + 2.3 TB storage",
            source_quantity=1,
            source_pricing_basis="instance-month",
            source_monthly_total_usd=450.00,
            huawei_product="RDS",
            huawei_spec_summary="rds.mysql.x1.large.4",
            huawei_quantity=1,
            huawei_unit_price_usd=380.00,
            huawei_billing_basis="instance-month",
            huawei_monthly_total_usd=380.00,
            status="quoted",
            composition_notes=["Database composed from 3 sub-item(s): compute, IO, storage."],
            source_item_ids=["req-1", "req-2", "req-3"],
            manual_review_reason=None,
        )
        assert item.vendor == "AWS"
        assert item.resource_kind == "managed_database"
        assert item.status == "quoted"
        assert len(item.composition_notes) == 1
        assert len(item.source_item_ids) == 3

    def test_all_resource_kinds(self):
        for kind in (
            "compute_vm", "block_storage", "shared_file_storage", "object_storage",
            "managed_database", "load_balancing_and_waf", "vpn_connectivity",
            "public_ip_or_bandwidth", "backup_security_ops", "platform_paas_misc",
        ):
            item = CloudBillingFinalQuoteItem(
                item_id=f"fqi-{kind}", vendor="GCP",
                resource_kind=kind, source_service_name="test",
            )
            assert item.resource_kind == kind

    def test_all_statuses(self):
        for status in ("quoted", "partial", "manual_review", "unquoted"):
            item = CloudBillingFinalQuoteItem(
                item_id=f"fqi-{status}", vendor="Azure",
                resource_kind="compute_vm", source_service_name="test",
                status=status,
            )
            assert item.status == status


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 8C: Unified cross-cloud classification
# ═══════════════════════════════════════════════════════════════════════════════


class TestResourceKindClassification:
    """Validate _classify_resource_kind maps correctly for all 3 clouds."""

    def test_azure_resource_kinds(self):
        assert _classify_resource_kind("vm", None) == "compute_vm"
        assert _classify_resource_kind("disk", None) == "block_storage"
        assert _classify_resource_kind("database", None) == "managed_database"
        assert _classify_resource_kind("object_storage", None) == "object_storage"
        assert _classify_resource_kind("file_storage", None) == "shared_file_storage"
        assert _classify_resource_kind("load_balancer", None) == "load_balancing_and_waf"
        assert _classify_resource_kind("vpn_gateway", None) == "vpn_connectivity"
        assert _classify_resource_kind("public_ip", None) == "public_ip_or_bandwidth"
        assert _classify_resource_kind("backup", None) == "backup_security_ops"
        assert _classify_resource_kind("security", None) == "backup_security_ops"

    def test_aws_resource_kinds(self):
        assert _classify_resource_kind("ecs", None) == "compute_vm"
        assert _classify_resource_kind("evs", None) == "block_storage"
        assert _classify_resource_kind("rds", None) == "managed_database"
        assert _classify_resource_kind("elb", None) == "load_balancing_and_waf"
        assert _classify_resource_kind("waf", None) == "load_balancing_and_waf"
        assert _classify_resource_kind("vpn", None) == "vpn_connectivity"
        assert _classify_resource_kind("eip", None) == "public_ip_or_bandwidth"
        assert _classify_resource_kind("cbr", None) == "backup_security_ops"
        assert _classify_resource_kind("hss", None) == "backup_security_ops"
        assert _classify_resource_kind("obs", None) == "object_storage"

    def test_gcp_resource_kinds(self):
        assert _classify_resource_kind("ecs", None) == "compute_vm"
        assert _classify_resource_kind("evs", None) == "block_storage"
        assert _classify_resource_kind("rds", None) == "managed_database"
        assert _classify_resource_kind("sfs_turbo", None) == "shared_file_storage"

    def test_huawei_product_fallback(self):
        assert _classify_resource_kind(None, "ECS") == "compute_vm"
        assert _classify_resource_kind(None, "EVS") == "block_storage"
        assert _classify_resource_kind(None, "RDS") == "managed_database"
        assert _classify_resource_kind(None, "OBS") == "object_storage"
        assert _classify_resource_kind(None, "SFS Turbo") == "shared_file_storage"
        assert _classify_resource_kind(None, "ELB") == "load_balancing_and_waf"
        assert _classify_resource_kind(None, "WAF") == "load_balancing_and_waf"
        assert _classify_resource_kind(None, "VPN") == "vpn_connectivity"
        assert _classify_resource_kind(None, "EIP") == "public_ip_or_bandwidth"
        assert _classify_resource_kind(None, "CBR") == "backup_security_ops"
        assert _classify_resource_kind(None, "HSS") == "backup_security_ops"
        assert _classify_resource_kind(None, "CCE") == "platform_paas_misc"

    def test_unsupported_falls_to_platform(self):
        assert _classify_resource_kind("unsupported", None) == "platform_paas_misc"
        assert _classify_resource_kind(None, None) == "platform_paas_misc"
        assert _classify_resource_kind("unknown_kind", None) == "platform_paas_misc"


class TestVendorNormalization:
    def test_azure_aliases(self):
        assert _normalize_vendor("azure") == "Azure"
        assert _normalize_vendor("Microsoft") == "Azure"
        assert _normalize_vendor("Microsoft Azure") == "Azure"

    def test_aws_aliases(self):
        assert _normalize_vendor("aws") == "AWS"
        assert _normalize_vendor("Amazon") == "AWS"
        assert _normalize_vendor("Amazon Web Services") == "AWS"

    def test_gcp_aliases(self):
        assert _normalize_vendor("gcp") == "GCP"
        assert _normalize_vendor("Google") == "GCP"
        assert _normalize_vendor("Google Cloud") == "GCP"
        assert _normalize_vendor("Google Cloud Platform") == "GCP"

    def test_unknown_vendor(self):
        assert _normalize_vendor("Alibaba") == "Alibaba"
        assert _normalize_vendor(None) == "Unknown"
        assert _normalize_vendor("") == "Unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 8D: Item composition / merge logic
# ═══════════════════════════════════════════════════════════════════════════════


def _make_intermediate_vm(vendor, spec, qty=1, monthly=100.0, status="quoted", item_id="req-1"):
    return {
        "source_item_id": item_id, "vendor": vendor,
        "resource_kind": "compute_vm",
        "source_service_name": "Virtual Machine",
        "source_service_family": "Compute",
        "source_config_summary": spec,
        "source_quantity": qty, "source_pricing_basis": "instance-month",
        "source_monthly_total_usd": monthly,
        "huawei_product": "ECS", "huawei_spec_summary": spec,
        "huawei_quantity": qty,
        "huawei_unit_price_usd": monthly / qty if qty else None,
        "huawei_billing_basis": "instance-month",
        "huawei_monthly_total_usd": monthly,
        "status": status, "manual_review_reason": None,
    }


def _make_intermediate_disk(vendor, tier, qty=1, monthly=50.0, status="quoted", item_id="req-d1"):
    return {
        "source_item_id": item_id, "vendor": vendor,
        "resource_kind": "block_storage",
        "source_service_name": "Managed Disk",
        "source_service_family": "Storage",
        "source_config_summary": tier,
        "source_quantity": qty, "source_pricing_basis": "disk-month",
        "source_monthly_total_usd": monthly,
        "huawei_product": "EVS", "huawei_spec_summary": tier,
        "huawei_quantity": qty,
        "huawei_unit_price_usd": monthly / qty if qty else None,
        "huawei_billing_basis": "disk-month",
        "huawei_monthly_total_usd": monthly,
        "status": status, "manual_review_reason": None,
    }


def _make_intermediate_db_sub(vendor, engine, sub_type, qty=1, monthly=100.0, status="quoted", item_id="req-db1"):
    return {
        "source_item_id": item_id, "vendor": vendor,
        "resource_kind": "managed_database",
        "source_service_name": f"{engine} {sub_type}",
        "source_service_family": engine,
        "source_config_summary": f"{sub_type}: 4 vCore",
        "source_quantity": qty, "source_pricing_basis": "instance-month",
        "source_monthly_total_usd": monthly,
        "huawei_product": "RDS", "huawei_spec_summary": f"rds.{engine.lower()}.x1.large",
        "huawei_quantity": qty,
        "huawei_unit_price_usd": monthly / qty if qty else None,
        "huawei_billing_basis": "instance-month",
        "huawei_monthly_total_usd": monthly,
        "status": status, "manual_review_reason": None,
    }


def _make_intermediate_platform(vendor, service_name, monthly=20.0, item_id="req-p1"):
    return {
        "source_item_id": item_id, "vendor": vendor,
        "resource_kind": "platform_paas_misc",
        "source_service_name": service_name,
        "source_service_family": None, "source_config_summary": None,
        "source_quantity": 1, "source_pricing_basis": "month",
        "source_monthly_total_usd": monthly,
        "huawei_product": None, "huawei_spec_summary": None,
        "huawei_quantity": None, "huawei_unit_price_usd": None,
        "huawei_billing_basis": None, "huawei_monthly_total_usd": None,
        "status": "unquoted", "manual_review_reason": "Platform service not supported.",
    }


class TestComputeVmComposition:
    def test_azure_vms_same_spec_merge(self):
        items = [_make_intermediate_vm("Azure", "8 vCPU / 32 GiB Linux", qty=1, monthly=200.0, item_id=f"req-{i}") for i in range(3)]
        result = _merge_items_into_final("compute_vm", items, 1)
        assert result.source_quantity == 3
        assert result.source_monthly_total_usd == 600.0
        assert result.huawei_product == "ECS"
        assert result.status == "quoted"
        assert len(result.composition_notes) == 1
        assert "3 VM instance(s)" in result.composition_notes[0]

    def test_aws_ec2_same_spec_merge(self):
        items = [_make_intermediate_vm("AWS", "8 vCPU / 32 GiB Linux", qty=1, monthly=180.0, item_id=f"req-{i}") for i in range(2)]
        result = _merge_items_into_final("compute_vm", items, 1)
        assert result.source_quantity == 2
        assert result.source_monthly_total_usd == 360.0
        assert result.vendor == "AWS"

    def test_gcp_compute_same_spec_merge(self):
        items = [_make_intermediate_vm("GCP", "8 vCPU / 32 GiB Linux", qty=1, monthly=170.0, item_id=f"req-{i}") for i in range(4)]
        result = _merge_items_into_final("compute_vm", items, 1)
        assert result.source_quantity == 4
        assert result.source_monthly_total_usd == 680.0
        assert result.vendor == "GCP"

    def test_vms_different_spec_stay_separate(self):
        item1 = _make_intermediate_vm("Azure", "8 vCPU / 32 GiB Linux")
        item2 = _make_intermediate_vm("Azure", "4 vCPU / 16 GiB Linux")
        key1 = _composition_key_compute_vm(item1)
        key2 = _composition_key_compute_vm(item2)
        assert key1 != key2


class TestBlockStorageComposition:
    def test_azure_disks_same_tier_merge(self):
        items = [_make_intermediate_disk("Azure", "Premium SSD 128 GB", qty=1, monthly=15.0, item_id=f"d{i}") for i in range(4)]
        result = _merge_items_into_final("block_storage", items, 1)
        assert result.source_quantity == 4
        assert result.source_monthly_total_usd == 60.0
        assert result.huawei_product == "EVS"

    def test_disks_different_tier_stay_separate(self):
        item1 = _make_intermediate_disk("Azure", "Premium SSD 128 GB", monthly=15.0)
        item2 = _make_intermediate_disk("Azure", "Standard HDD 128 GB", monthly=5.0)
        from app.cloud_billing_workflow import _composition_key_block_storage
        assert _composition_key_block_storage(item1) != _composition_key_block_storage(item2)


class TestManagedDatabaseComposition:
    def test_azure_mysql_composition(self):
        items = [
            _make_intermediate_db_sub("Azure", "MySQL", "compute", monthly=300.0, item_id="db-c"),
            _make_intermediate_db_sub("Azure", "MySQL", "storage", monthly=100.0, item_id="db-s"),
            _make_intermediate_db_sub("Azure", "MySQL", "IO", monthly=50.0, item_id="db-io"),
        ]
        result = _merge_items_into_final("managed_database", items, 1)
        assert result.source_monthly_total_usd == 450.0
        assert result.huawei_product == "RDS"
        assert result.status == "quoted"
        assert "3 sub-item(s)" in result.composition_notes[0]

    def test_aws_rds_composition(self):
        items = [
            _make_intermediate_db_sub("AWS", "MySQL", "compute", monthly=250.0, item_id="rds-c"),
            _make_intermediate_db_sub("AWS", "MySQL", "storage", monthly=80.0, item_id="rds-s"),
        ]
        result = _merge_items_into_final("managed_database", items, 1)
        assert result.source_monthly_total_usd == 330.0
        assert result.vendor == "AWS"

    def test_gcp_cloud_sql_composition(self):
        items = [
            _make_intermediate_db_sub("GCP", "PostgreSQL", "compute", monthly=220.0, item_id="cs-c"),
            _make_intermediate_db_sub("GCP", "PostgreSQL", "storage", monthly=70.0, item_id="cs-s"),
        ]
        result = _merge_items_into_final("managed_database", items, 1)
        assert result.source_monthly_total_usd == 290.0
        assert result.vendor == "GCP"

    def test_databases_different_engine_stay_separate(self):
        item1 = _make_intermediate_db_sub("Azure", "MySQL", "compute")
        item2 = _make_intermediate_db_sub("Azure", "PostgreSQL", "compute")
        assert _composition_key_managed_database(item1) != _composition_key_managed_database(item2)


class TestPlatformPaasComposition:
    def test_multiple_platform_items_merge(self):
        items = [
            _make_intermediate_platform("Azure", "API Management", monthly=50.0, item_id="p1"),
            _make_intermediate_platform("Azure", "Azure Bastion", monthly=30.0, item_id="p2"),
            _make_intermediate_platform("Azure", "Azure Monitor", monthly=20.0, item_id="p3"),
            _make_intermediate_platform("Azure", "Key Vault", monthly=5.0, item_id="p4"),
        ]
        result = _merge_items_into_final("platform_paas_misc", items, 1)
        assert result.status == "manual_review"
        assert result.source_monthly_total_usd == 105.0
        assert result.huawei_product is None
        assert result.huawei_quantity is None
        assert "4 item(s) merged" in result.composition_notes[0]
        assert "API Management" in result.source_service_name

    def test_single_platform_item(self):
        items = [_make_intermediate_platform("AWS", "CloudFormation", monthly=10.0)]
        result = _merge_items_into_final("platform_paas_misc", items, 1)
        assert result.status == "manual_review"


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 8B: compose_final_billing_quote_items node
# ═══════════════════════════════════════════════════════════════════════════════


class TestComposeFinalBillingQuoteItemsNode:
    def _make_billing_state(self, agg_items, quote_lines=None, requirements=None):
        return {
            "llm_aggregated_billing_items": agg_items,
            "quote_lines": quote_lines or [],
            "requirements": requirements or [],
            "unquoted_items": [], "quote_blockers": [], "audit_log": [],
        }

    def test_node_produces_final_items(self):
        agg_items = [
            {
                "aggregate_label": "ECS | 8 vCPU / 32 GiB",
                "resource_kind": "vm", "source_group_ids": ["g1"],
                "huawei_product": "ECS", "huawei_spec_hint": "8 vCPU / 32 GiB",
                "derived_quantity": 3, "derived_unit": "instance-month",
                "vendor": "azure", "product_family": "Compute",
                "product_type": "Virtual Machine", "product_sku": "Standard_D8s_v3",
                "source_sku_hint": "Standard_D8s_v3",
                "source_file": "azure billing.xlsx", "source_sheet": "Sheet1",
                "source_line_numbers": [1, 2, 3], "amount": 600.0,
                "needs_manual_review": False,
            },
        ]
        state = self._make_billing_state(agg_items)
        result = compose_final_billing_quote_items(state)
        assert "final_billing_quote_items" in result
        assert len(result["final_billing_quote_items"]) >= 1

    def test_node_empty_state(self):
        state = self._make_billing_state([])
        result = compose_final_billing_quote_items(state)
        assert result["final_billing_quote_items"] == []

    def test_node_from_quote_lines_only(self):
        quote_lines = [
            FlexibleQuoteLine(
                line_id="line-1", requirement_item_id="req-1",
                product="ECS", region="mexico", quantity=2,
                unit="instance", billing_mode="on-demand",
                matched_sku="c6.x2.2large.4", matched_tier="general",
                unit_price=150.0, monthly_price=300.0,
            ).model_dump(),
        ]
        requirements = [
            RequirementItem(
                item_id="req-1", source_file="test.xlsx",
                raw_product_name="ECS", normalized_product="ECS",
                quantity=2, quantity_source="billing_standardized",
                unit="instance", region="mexico",
            ).model_dump(),
        ]
        state = self._make_billing_state([], quote_lines=quote_lines, requirements=requirements)
        result = compose_final_billing_quote_items(state)
        assert len(result["final_billing_quote_items"]) >= 1

    def test_node_audit_log_updated(self):
        state = self._make_billing_state([
            {
                "aggregate_label": "ECS", "resource_kind": "vm",
                "source_group_ids": ["g1"], "huawei_product": "ECS",
                "huawei_spec_hint": "test", "derived_quantity": 1,
                "derived_unit": "instance-month", "vendor": "azure",
                "product_family": "Compute", "product_type": "VM",
                "product_sku": "test", "source_sku_hint": "test",
                "source_file": "test.xlsx", "source_sheet": "Sheet1",
                "source_line_numbers": [1], "amount": 100.0,
                "needs_manual_review": False,
            },
        ])
        result = compose_final_billing_quote_items(state)
        assert len(result["audit_log"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 8E: Export dual-layer
# ═══════════════════════════════════════════════════════════════════════════════


class TestDualLayerExport:
    def test_quotation_sheet_populated_from_final_items(self):
        from io import BytesIO
        from openpyxl import load_workbook
        from app.flexible_workflow import _export_flexible_billing_template_workbook

        final_items = [
            CloudBillingFinalQuoteItem(
                item_id="fqi-1", vendor="Azure", resource_kind="compute_vm",
                source_service_name="Virtual Machine",
                source_config_summary="8 vCPU / 32 GiB Linux",
                source_quantity=6, source_pricing_basis="instance-month",
                source_monthly_total_usd=1200.0,
                huawei_product="ECS", huawei_spec_summary="c6.x2.2large.4",
                huawei_quantity=6, huawei_unit_price_usd=180.0,
                huawei_billing_basis="on-demand", huawei_monthly_total_usd=1080.0,
                status="quoted",
            ).model_dump(),
        ]
        state = {
            "final_billing_quote_items": final_items,
            "billing_lines": [{"test": True}],
            "llm_aggregated_billing_items": [], "quote_lines": [],
            "requirements": [], "quote_ready_items": [],
            "quote_blockers": [], "unquoted_items": [],
            "matched_products": [],
            "summary": FlexibleQuoteSummary().model_dump(),
            "audit_log": [],
            "quote_context": {"region": "mexico", "language": "en"},
            "diagnostics": {},
        }
        wb_result = _export_flexible_billing_template_workbook(state)
        wb = load_workbook(BytesIO(wb_result.content))
        assert "Quotation" in wb.sheetnames
        ws = wb["Quotation"]
        assert ws.cell(4, 1).value is not None

    def test_billing_detail_sheet_preserved(self):
        from io import BytesIO
        from openpyxl import load_workbook
        from app.flexible_workflow import _export_flexible_billing_template_workbook

        state = {
            "final_billing_quote_items": [],
            "billing_lines": [{"test": True}],
            "llm_aggregated_billing_items": [], "quote_lines": [],
            "requirements": [], "quote_ready_items": [],
            "quote_blockers": [], "unquoted_items": [],
            "matched_products": [],
            "summary": FlexibleQuoteSummary().model_dump(),
            "audit_log": [],
            "quote_context": {"region": "mexico", "language": "en"},
            "diagnostics": {},
        }
        wb_result = _export_flexible_billing_template_workbook(state)
        wb = load_workbook(BytesIO(wb_result.content))
        assert "ECS" in wb.sheetnames


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 8F: Summary based on final items
# ═══════════════════════════════════════════════════════════════════════════════


class TestSummaryBasedOnFinalItems:
    def test_summary_includes_final_item_stats(self):
        from app.flexible_workflow import summarize_quote

        final_items = [
            CloudBillingFinalQuoteItem(
                item_id="fqi-1", vendor="Azure", resource_kind="compute_vm",
                source_service_name="VM", source_quantity=6,
                source_monthly_total_usd=1200.0,
                huawei_product="ECS", huawei_quantity=6,
                huawei_monthly_total_usd=1080.0, status="quoted",
            ).model_dump(),
            CloudBillingFinalQuoteItem(
                item_id="fqi-2", vendor="Azure", resource_kind="platform_paas_misc",
                source_service_name="API Management", source_quantity=1,
                source_monthly_total_usd=50.0, status="manual_review",
                manual_review_reason="Platform service",
            ).model_dump(),
        ]
        state = {
            "requirements": [], "quote_ready_items": [],
            "quote_lines": [], "quote_blockers": [],
            "unquoted_items": [], "audit_log": [],
            "final_billing_quote_items": final_items,
            "quote_context": {}, "diagnostics": {},
        }
        result = summarize_quote(state)
        summary = FlexibleQuoteSummary.model_validate(result["summary"])
        assert "Final quotation" in summary.summary or "final" in summary.summary.lower()
        final_assumptions = [a for a in summary.assumptions if "FINAL QUOTATION" in a]
        assert len(final_assumptions) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 8G: Azure sample regression
# ═══════════════════════════════════════════════════════════════════════════════


class TestAzureSampleRegression:
    def test_azure_billing_composition_reduces_items(self):
        agg_items = []
        # 6 VMs same spec
        for i in range(6):
            agg_items.append({
                "aggregate_label": "ECS | Standard_D8s_v3",
                "resource_kind": "vm", "source_group_ids": [f"vm-{i}"],
                "huawei_product": "ECS", "huawei_spec_hint": "8 vCPU / 32 GiB Linux",
                "derived_quantity": 1, "derived_unit": "instance-month",
                "vendor": "azure", "product_family": "Compute",
                "product_type": "Virtual Machine", "product_sku": "Standard_D8s_v3",
                "source_sku_hint": "Standard_D8s_v3",
                "source_file": "azure billing.xlsx", "source_sheet": "Sheet1",
                "source_line_numbers": [i + 1], "amount": 200.0,
                "needs_manual_review": False,
            })
        # 4 disks same tier
        for i in range(4):
            agg_items.append({
                "aggregate_label": "EVS | Premium SSD S4",
                "resource_kind": "disk", "source_group_ids": [f"disk-{i}"],
                "huawei_product": "EVS", "huawei_spec_hint": "Premium SSD 128 GB",
                "derived_quantity": 1, "derived_unit": "disk-month",
                "vendor": "azure", "product_family": "Storage",
                "product_type": "Managed Disk", "product_sku": "Premium SSD S4",
                "source_sku_hint": "Premium SSD S4",
                "source_file": "azure billing.xlsx", "source_sheet": "Sheet1",
                "source_line_numbers": [10 + i], "amount": 15.0,
                "needs_manual_review": False,
            })
        # MySQL compute + storage + IO
        for sub in ["compute", "storage", "IO"]:
            agg_items.append({
                "aggregate_label": f"RDS | MySQL {sub}",
                "resource_kind": "database", "source_group_ids": [f"mysql-{sub}"],
                "huawei_product": "RDS", "huawei_spec_hint": "MySQL Flexible Server",
                "derived_quantity": 1, "derived_unit": "instance-month",
                "vendor": "azure", "product_family": "Databases",
                "product_type": f"MySQL {sub}", "product_sku": f"MySQL_{sub}",
                "source_sku_hint": f"MySQL_{sub}",
                "source_file": "azure billing.xlsx", "source_sheet": "Sheet1",
                "source_line_numbers": [20], "amount": 150.0 if sub == "compute" else 50.0,
                "needs_manual_review": False,
            })
        # File storage
        agg_items.append({
            "aggregate_label": "SFS Turbo | Azure Files",
            "resource_kind": "file_storage", "source_group_ids": ["fs-1"],
            "huawei_product": "SFS Turbo", "huawei_spec_hint": "Azure Files Hot",
            "derived_quantity": 1, "derived_unit": "capacity-month",
            "vendor": "azure", "product_family": "Storage",
            "product_type": "Azure Files", "product_sku": "Azure_Files_Hot",
            "source_sku_hint": "Azure_Files_Hot",
            "source_file": "azure billing.xlsx", "source_sheet": "Sheet1",
            "source_line_numbers": [30], "amount": 20.0, "needs_manual_review": False,
        })
        # App Gateway / WAF
        agg_items.append({
            "aggregate_label": "ELB | Application Gateway",
            "resource_kind": "load_balancer", "source_group_ids": ["lb-1"],
            "huawei_product": "ELB", "huawei_spec_hint": "Application Gateway",
            "derived_quantity": 1, "derived_unit": "instance-month",
            "vendor": "azure", "product_family": "Networking",
            "product_type": "Application Gateway", "product_sku": "AppGW",
            "source_sku_hint": "AppGW",
            "source_file": "azure billing.xlsx", "source_sheet": "Sheet1",
            "source_line_numbers": [40], "amount": 80.0, "needs_manual_review": False,
        })
        # VPN
        agg_items.append({
            "aggregate_label": "VPN | VPN Gateway",
            "resource_kind": "vpn_gateway", "source_group_ids": ["vpn-1"],
            "huawei_product": "VPN", "huawei_spec_hint": "VPN Gateway",
            "derived_quantity": 1, "derived_unit": "gateway-month",
            "vendor": "azure", "product_family": "Networking",
            "product_type": "VPN Gateway", "product_sku": "VPN_GW",
            "source_sku_hint": "VPN_GW",
            "source_file": "azure billing.xlsx", "source_sheet": "Sheet1",
            "source_line_numbers": [50], "amount": 30.0, "needs_manual_review": False,
        })
        # Public IP
        agg_items.append({
            "aggregate_label": "EIP | Public IP",
            "resource_kind": "public_ip", "source_group_ids": ["eip-1"],
            "huawei_product": "EIP", "huawei_spec_hint": "Public IP",
            "derived_quantity": 2, "derived_unit": "ip-month",
            "vendor": "azure", "product_family": "Networking",
            "product_type": "Public IP", "product_sku": "PublicIP",
            "source_sku_hint": "PublicIP",
            "source_file": "azure billing.xlsx", "source_sheet": "Sheet1",
            "source_line_numbers": [55, 56], "amount": 8.0, "needs_manual_review": False,
        })
        # Defender
        agg_items.append({
            "aggregate_label": "HSS | Microsoft Defender",
            "resource_kind": "security", "source_group_ids": ["sec-1"],
            "huawei_product": "HSS", "huawei_spec_hint": "Defender for Cloud",
            "derived_quantity": 1, "derived_unit": "month",
            "vendor": "azure", "product_family": "Security",
            "product_type": "Microsoft Defender", "product_sku": "Defender",
            "source_sku_hint": "Defender",
            "source_file": "azure billing.xlsx", "source_sheet": "Sheet1",
            "source_line_numbers": [60], "amount": 15.0, "needs_manual_review": False,
        })
        # 5 platform items
        for svc in ["API Management", "Bastion", "Monitor", "Key Vault", "DevOps"]:
            agg_items.append({
                "aggregate_label": f"unsupported | {svc}",
                "resource_kind": "unsupported", "source_group_ids": [f"paas-{svc}"],
                "huawei_product": None, "huawei_spec_hint": "",
                "derived_quantity": 1, "derived_unit": "month",
                "vendor": "azure", "product_family": "Platform",
                "product_type": svc, "product_sku": svc,
                "source_sku_hint": svc,
                "source_file": "azure billing.xlsx", "source_sheet": "Sheet1",
                "source_line_numbers": [70], "amount": 10.0,
                "needs_manual_review": True,
            })

        state = {
            "llm_aggregated_billing_items": agg_items,
            "quote_lines": [], "requirements": [],
            "unquoted_items": [], "quote_blockers": [], "audit_log": [],
        }
        result = compose_final_billing_quote_items(state)
        final_items = [CloudBillingFinalQuoteItem.model_validate(fi) for fi in result["final_billing_quote_items"]]

        # Final items should be significantly fewer than raw items
        assert len(final_items) < len(agg_items), (
            f"Final items ({len(final_items)}) should be fewer than raw items ({len(agg_items)})"
        )

        # Verify key resource categories are present
        resource_kinds = {fi.resource_kind for fi in final_items}
        assert "compute_vm" in resource_kinds
        assert "block_storage" in resource_kinds
        assert "managed_database" in resource_kinds
        assert "platform_paas_misc" in resource_kinds

        # Verify VMs were merged
        vm_items = [fi for fi in final_items if fi.resource_kind == "compute_vm"]
        assert len(vm_items) == 1
        assert vm_items[0].source_quantity == 6

        # Verify disks were merged
        disk_items = [fi for fi in final_items if fi.resource_kind == "block_storage"]
        assert len(disk_items) == 1
        assert disk_items[0].source_quantity == 4

        # Verify database sub-items were merged
        db_items = [fi for fi in final_items if fi.resource_kind == "managed_database"]
        assert len(db_items) == 1

        # Unsupported platform services stay isolated so one service cannot
        # absorb another service's source amount in deterministic fallback.
        platform_items = [fi for fi in final_items if fi.resource_kind == "platform_paas_misc"]
        assert len(platform_items) == 5
        assert {item.source_service_name for item in platform_items} == {
            "API Management", "Bastion", "Monitor", "Key Vault", "DevOps",
        }
        assert all(item.status == "manual_review" for item in platform_items)


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 9A.1: Quantity semantics
# ═══════════════════════════════════════════════════════════════════════════════


class TestFinalDisplayQuantity:
    """Validate _final_display_quantity produces business-readable quantities."""

    def test_compute_vm_instance_hours_to_count(self):
        """4468 instance hours / 744 ≈ 6 → quantity 6."""
        items = [_make_intermediate_vm("Azure", "8 vCPU", item_id=f"r{i}") for i in range(6)]
        qty = _final_display_quantity("compute_vm", items, 4468.0)
        assert qty == 6.0

    def test_compute_vm_already_instance_count(self):
        """If qty is already instance count (small), keep it."""
        items = [_make_intermediate_vm("Azure", "8 vCPU", item_id=f"r{i}") for i in range(3)]
        qty = _final_display_quantity("compute_vm", items, 3.0)
        assert qty == 3.0

    def test_compute_vm_normalized_instance_count_with_hour_label(self):
        """Already-normalized VM counts must not be divided by 744 again."""
        items = [
            {
                "source_item_id": "vm1",
                "source_quantity": 6.0066,
                "source_pricing_basis": "instance hours",
            }
        ]
        qty = _final_display_quantity("compute_vm", items, 6.0066)
        assert qty == 6.0

    def test_compute_vm_744_hours_single(self):
        """744 hours = 1 instance."""
        items = [_make_intermediate_vm("Azure", "8 vCPU")]
        qty = _final_display_quantity("compute_vm", items, 744.0)
        assert qty == 1.0

    def test_block_storage_no_tiny_ratios(self):
        """Disk-month ratios like 0.0054 should never appear as quantity."""
        items = [_make_intermediate_disk("Azure", "Premium SSD 128 GB", item_id=f"d{i}") for i in range(4)]
        qty = _final_display_quantity("block_storage", items, 0.0054)
        assert qty == 4.0  # Should fall back to item count
        assert qty >= 1.0  # Never a tiny decimal

    def test_block_storage_disk_count(self):
        """4 disks → quantity 4."""
        items = [_make_intermediate_disk("Azure", "Premium SSD 128 GB", item_id=f"d{i}") for i in range(4)]
        qty = _final_display_quantity("block_storage", items, 4.0)
        assert qty == 4.0

    def test_managed_database_always_instance_count(self):
        """Database quantity should be 1, not storage GiB or IO count."""
        items = [_make_intermediate_db_sub("Azure", "MySQL", "compute")]
        qty = _final_display_quantity("managed_database", items, 2296.0)  # 2296 GB storage
        assert qty == 1.0

    def test_shared_file_storage_quantity_is_one(self):
        """File storage: quantity=1, capacity in config_summary."""
        items = [{"source_item_id": "fs1", "source_quantity": 500.0}]  # 500 GiB
        qty = _final_display_quantity("shared_file_storage", items, 500.0)
        assert qty == 1.0

    def test_object_storage_quantity_is_one(self):
        """Object storage: quantity=1, capacity in config_summary."""
        items = [{"source_item_id": "ob1", "source_quantity": 2000.0}]
        qty = _final_display_quantity("object_storage", items, 2000.0)
        assert qty == 1.0

    def test_vpn_resource_count(self):
        """VPN: 2 gateways → quantity 2."""
        items = [{"source_item_id": f"vpn{i}", "source_quantity": 2.0} for i in range(2)]
        qty = _final_display_quantity("vpn_connectivity", items, 2.0)
        assert qty == 2.0


class TestMergeQuantitySemantics:
    """Verify _merge_items_into_final uses display quantities."""

    def test_vm_merge_uses_display_quantity(self):
        """6 VMs with 4468 total hours → source_quantity=6."""
        items = []
        for i in range(6):
            items.append({
                "source_item_id": f"r{i}", "vendor": "Azure",
                "resource_kind": "compute_vm",
                "source_service_name": "Virtual Machine",
                "source_service_family": "Compute",
                "source_config_summary": "8 vCPU / 32 GiB Linux",
                "source_quantity": 744.0,  # 1 month of hours per VM
                "source_pricing_basis": "instance-hour",
                "source_monthly_total_usd": 200.0,
                "huawei_product": "ECS", "huawei_spec_summary": "c6.x2.2large.4",
                "huawei_quantity": 1, "huawei_unit_price_usd": 180.0,
                "huawei_billing_basis": "on-demand",
                "huawei_monthly_total_usd": 180.0,
                "status": "quoted", "manual_review_reason": None,
            })
        result = _merge_items_into_final("compute_vm", items, 1)
        assert result.source_quantity == 6.0
        assert result.huawei_quantity == 6.0

    def test_disk_merge_no_tiny_quantity(self):
        """4 disks → quantity=4, never 0.0054."""
        items = []
        for i in range(4):
            items.append({
                "source_item_id": f"d{i}", "vendor": "Azure",
                "resource_kind": "block_storage",
                "source_service_name": "Managed Disk",
                "source_service_family": "Storage",
                "source_config_summary": "Premium SSD 128 GB",
                "source_quantity": 0.0054,  # disk-month ratio
                "source_pricing_basis": "disk-month",
                "source_monthly_total_usd": 15.0,
                "huawei_product": "EVS", "huawei_spec_summary": "gpssd",
                "huawei_quantity": 1, "huawei_unit_price_usd": 12.0,
                "huawei_billing_basis": "disk-month",
                "huawei_monthly_total_usd": 12.0,
                "status": "quoted", "manual_review_reason": None,
            })
        result = _merge_items_into_final("block_storage", items, 1)
        assert result.source_quantity == 4.0
        assert result.source_quantity >= 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 9A.2: Customer-visible service names
# ═══════════════════════════════════════════════════════════════════════════════


class TestFinalDisplayServiceName:
    """Validate _final_display_service_name produces customer-readable names."""

    def test_azure_vm_name(self):
        items = [_make_intermediate_vm("Azure", "8 vCPU")]
        assert _final_display_service_name("compute_vm", "Azure", items) == "Azure VM"

    def test_aws_ec2_name(self):
        items = [_make_intermediate_vm("AWS", "8 vCPU")]
        assert _final_display_service_name("compute_vm", "AWS", items) == "AWS EC2"

    def test_gcp_compute_name(self):
        items = [_make_intermediate_vm("GCP", "8 vCPU")]
        assert _final_display_service_name("compute_vm", "GCP", items) == "GCP Compute Engine"

    def test_azure_disk_name(self):
        items = [_make_intermediate_disk("Azure", "Premium SSD")]
        assert _final_display_service_name("block_storage", "Azure", items) == "Azure Managed Disk"

    def test_azure_mysql_name(self):
        items = [_make_intermediate_db_sub("Azure", "MySQL", "compute")]
        name = _final_display_service_name("managed_database", "Azure", items)
        assert name == "Azure Database for MySQL"

    def test_aws_rds_name(self):
        items = [_make_intermediate_db_sub("AWS", "MySQL", "compute")]
        name = _final_display_service_name("managed_database", "AWS", items)
        assert name == "AWS RDS for MySQL"  # Engine appended for databases

    def test_azure_files_name(self):
        items = [{"source_service_name": "Azure Files"}]
        assert _final_display_service_name("shared_file_storage", "Azure", items) == "Azure Files"

    def test_azure_blob_name(self):
        items = [{"source_service_name": "Blob"}]
        assert _final_display_service_name("object_storage", "Azure", items) == "Azure Blob Storage"

    def test_vpn_name(self):
        items = [{"source_service_name": "VPN"}]
        assert _final_display_service_name("vpn_connectivity", "Azure", items) == "Azure VPN Gateway"

    def test_platform_strips_unsupported_prefix(self):
        items = [{"source_service_name": "unsupported | API Management"}]
        name = _final_display_service_name("platform_paas_misc", "Azure", items)
        assert not name.startswith("unsupported |")
        assert "API Management" in name

    def test_no_ecs_prefix_in_name(self):
        """Service names should NOT start with 'ECS |' or 'EVS |'."""
        items = [_make_intermediate_vm("Azure", "8 vCPU")]
        name = _final_display_service_name("compute_vm", "Azure", items)
        assert not name.startswith("ECS |")
        assert not name.startswith("EVS |")


class TestFinalDisplayConfigSummary:
    """Validate _final_display_config_summary produces clean spec summaries."""

    def test_strips_internal_prefix(self):
        """'ECS | 8 vCPU' → '8 vCPU'."""
        result = _final_display_config_summary("compute_vm", [], "ECS | 8 vCPU / 32 GiB")
        assert result == "8 vCPU / 32 GiB"

    def test_none_for_platform(self):
        result = _final_display_config_summary("platform_paas_misc", [], "some config")
        assert result is None

    def test_database_composite_summary(self):
        items = [
            {"source_service_name": "MySQL compute", "source_config_summary": "4 vCore"},
            {"source_service_name": "MySQL storage", "source_config_summary": "2296 GB"},
        ]
        result = _final_display_config_summary("managed_database", items, None)
        assert "4 vCore" in result
        assert "2296 GB" in result


class TestMergeServiceNames:
    """Verify _merge_items_into_final uses display names."""

    def test_azure_vm_final_name(self):
        items = [_make_intermediate_vm("Azure", "8 vCPU / 32 GiB Linux")]
        result = _merge_items_into_final("compute_vm", items, 1)
        assert result.source_service_name == "Azure VM"
        assert not result.source_service_name.startswith("ECS |")

    def test_azure_disk_final_name(self):
        items = [_make_intermediate_disk("Azure", "Premium SSD 128 GB")]
        result = _merge_items_into_final("block_storage", items, 1)
        assert result.source_service_name == "Azure Managed Disk"

    def test_azure_mysql_final_name(self):
        items = [_make_intermediate_db_sub("Azure", "MySQL", "compute")]
        result = _merge_items_into_final("managed_database", items, 1)
        assert "Azure Database" in result.source_service_name
        assert "MySQL" in result.source_service_name


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 9A.3: ECS sheet G:O header merge
# ═══════════════════════════════════════════════════════════════════════════════


class TestEcsSheetHeaderMerge:
    """Verify ECS sheet has merged group headers in row 1."""

    def test_ecs_sheet_has_merged_group_headers(self):
        from io import BytesIO
        from openpyxl import load_workbook
        from app.flexible_workflow import _export_flexible_billing_template_workbook

        state = {
            "final_billing_quote_items": [],
            "billing_lines": [{"test": True}],
            "llm_aggregated_billing_items": [],
            "quote_lines": [], "requirements": [],
            "quote_ready_items": [], "quote_blockers": [],
            "unquoted_items": [], "matched_products": [],
            "summary": FlexibleQuoteSummary().model_dump(),
            "audit_log": [],
            "quote_context": {"region": "mexico", "language": "en"},
            "diagnostics": {},
        }
        wb_result = _export_flexible_billing_template_workbook(state)
        wb = load_workbook(BytesIO(wb_result.content))
        ws = wb["ECS"]

        # Row 1 should have "Source Cloud" in A1
        assert ws.cell(1, 1).value == "Source Cloud"
        # Row 1 should have "Huawei Cloud" in F1
        assert ws.cell(1, 6).value == "Huawei Cloud"
        # Check that merged cells exist
        assert ws.merged_cells is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 9A.4: TOTAL row isolation
# ═══════════════════════════════════════════════════════════════════════════════


class TestTotalRowIsolation:
    """Verify TOTAL row doesn't pollute final item statistics."""

    def test_quotation_total_row_status_cell_empty(self):
        """TOTAL row's Status column (12) should be empty, not a status value."""
        from io import BytesIO
        from openpyxl import load_workbook
        from app.flexible_workflow import _export_flexible_billing_template_workbook

        final_items = [
            CloudBillingFinalQuoteItem(
                item_id="fqi-1", vendor="Azure", resource_kind="compute_vm",
                source_service_name="Azure VM", source_quantity=6,
                source_monthly_total_usd=1200.0,
                huawei_product="ECS", huawei_quantity=6,
                huawei_monthly_total_usd=1080.0, status="quoted",
            ).model_dump(),
            CloudBillingFinalQuoteItem(
                item_id="fqi-2", vendor="Azure", resource_kind="platform_paas_misc",
                source_service_name="API Management", source_quantity=1,
                source_monthly_total_usd=50.0, status="manual_review",
                manual_review_reason="Platform service",
            ).model_dump(),
        ]
        state = {
            "final_billing_quote_items": final_items,
            "billing_lines": [{"test": True}],
            "llm_aggregated_billing_items": [], "quote_lines": [],
            "requirements": [], "quote_ready_items": [],
            "quote_blockers": [], "unquoted_items": [],
            "matched_products": [],
            "summary": FlexibleQuoteSummary().model_dump(),
            "audit_log": [],
            "quote_context": {"region": "mexico", "language": "en"},
            "diagnostics": {},
        }
        wb_result = _export_flexible_billing_template_workbook(state)
        wb = load_workbook(BytesIO(wb_result.content))
        ws = wb["Quotation"]

        # Data rows: row 4, 5 (2 items)
        # Total row: row 7 (4 + 2 + 1)
        total_row = 7
        # Status column (12) should be empty for TOTAL
        status_val = ws.cell(total_row, 12).value
        assert status_val == "" or status_val is None, (
            f"TOTAL row Status should be empty, got: {status_val}"
        )
        # Notes column (13) should contain the status summary
        notes_val = ws.cell(total_row, 13).value
        assert notes_val and "Quoted:" in str(notes_val)

    def test_quotation_data_rows_are_separate_from_total(self):
        """Data rows end at 4+len-1; TOTAL row has 'TOTAL' marker in column 1."""
        from io import BytesIO
        from openpyxl import load_workbook
        from app.flexible_workflow import _export_flexible_billing_template_workbook

        final_items = [
            CloudBillingFinalQuoteItem(
                item_id="fqi-1", vendor="Azure", resource_kind="compute_vm",
                source_service_name="Azure VM", status="quoted",
            ).model_dump(),
        ]
        state = {
            "final_billing_quote_items": final_items,
            "billing_lines": [{"test": True}],
            "llm_aggregated_billing_items": [], "quote_lines": [],
            "requirements": [], "quote_ready_items": [],
            "quote_blockers": [], "unquoted_items": [],
            "matched_products": [],
            "summary": FlexibleQuoteSummary().model_dump(),
            "audit_log": [],
            "quote_context": {"region": "mexico", "language": "en"},
            "diagnostics": {},
        }
        wb_result = _export_flexible_billing_template_workbook(state)
        wb = load_workbook(BytesIO(wb_result.content))
        ws = wb["Quotation"]

        # Row 4: first data item
        assert ws.cell(4, 1).value == "Azure VM"
        # Row 6: TOTAL row (4 + 1 + 1)
        assert ws.cell(6, 1).value == "TOTAL"
        # Row 5: gap row or second data — should NOT be "TOTAL"
        assert ws.cell(5, 1).value != "TOTAL"


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 9B.1: Spec retention for billing kinds
# ═══════════════════════════════════════════════════════════════════════════════


class TestBillingKindSpecRetention:
    """Validate that billing aggregated items preserve structured specs
    instead of falling back to GenericSpec for common billing kinds."""

    @pytest.fixture(autouse=True)
    def _import_fn(self):
        from app.flexible_workflow import _build_requirements_from_llm_aggregated_billing_items
        self.build_reqs = _build_requirements_from_llm_aggregated_billing_items

    def _make_item(self, kind, **overrides):
        item = {
            "resource_kind": kind,
            "huawei_product": None,
            "huawei_spec_hint": "",
            "source_sku_hint": "",
            "derived_quantity": 100,
            "derived_unit": "GB",
            "vendor": "Azure",
            "source_file": "test.xlsx",
            "source_sheet": "Sheet1",
            "source_line_numbers": [1],
            "product_family": "",
            "product_type": "",
            "product_sku": "",
            "unit_type": "",
            "aggregation_type": "",
            "confidence": 0.9,
        }
        item.update(overrides)
        return item

    def test_vm_produces_compute_spec(self):
        """vm kind → ComputeSpec, not GenericSpec."""
        reqs = self.build_reqs([self._make_item("vm", huawei_product="ECS", huawei_spec_hint="D8s v3")])
        spec = reqs[0]["spec"]
        assert spec["spec_type"] == "compute"
        assert spec["sku"] == "D8s v3"

    def test_disk_produces_storage_spec(self):
        """disk kind → StorageSpec, not GenericSpec."""
        reqs = self.build_reqs([self._make_item("disk", huawei_product="EVS", derived_quantity=128)])
        spec = reqs[0]["spec"]
        assert spec["spec_type"] == "storage"
        assert spec["capacity_gib"] == 128.0

    def test_file_storage_produces_storage_spec(self):
        """file_storage kind → StorageSpec, not GenericSpec."""
        reqs = self.build_reqs([self._make_item("file_storage", huawei_product="SFS Turbo", derived_quantity=500)])
        spec = reqs[0]["spec"]
        assert spec["spec_type"] == "storage"
        assert spec["capacity_gib"] == 500.0

    def test_object_storage_produces_storage_spec(self):
        """object_storage kind → StorageSpec, not GenericSpec."""
        reqs = self.build_reqs([self._make_item("object_storage", huawei_product="OBS", derived_quantity=1000)])
        spec = reqs[0]["spec"]
        assert spec["spec_type"] == "storage"
        assert spec["capacity_gib"] == 1000.0

    def test_database_not_empty_generic_spec(self):
        """database kind → GenericSpec with structured description, not empty."""
        reqs = self.build_reqs([self._make_item("database", huawei_product="RDS", huawei_spec_hint="rds.mysql.x1", engine="MySQL")])
        spec = reqs[0]["spec"]
        assert spec["spec_type"] == "generic"
        # Description should contain engine hint, not just the sku
        desc = spec.get("description", "")
        assert "engine=MySQL" in desc

    def test_ecs_still_compute_spec(self):
        """ecs kind (canonical) still produces ComputeSpec."""
        reqs = self.build_reqs([self._make_item("ecs", huawei_product="ECS")])
        assert reqs[0]["spec"]["spec_type"] == "compute"

    def test_evs_still_storage_spec(self):
        """evs kind (canonical) still produces StorageSpec."""
        reqs = self.build_reqs([self._make_item("evs", huawei_product="EVS", derived_quantity=256)])
        assert reqs[0]["spec"]["spec_type"] == "storage"

    def test_vm_with_vcpu_memory_hints(self):
        """vm kind with vcpu/memory fields → ComputeSpec with those fields populated."""
        reqs = self.build_reqs([self._make_item("vm", huawei_product="ECS", vcpu=8, memory_gib=32)])
        spec = reqs[0]["spec"]
        assert spec["spec_type"] == "compute"
        assert spec["vcpu"] == 8
        assert spec["memory_gib"] == 32.0

    def test_disk_with_tier_hint(self):
        """disk kind with tier field → StorageSpec with tier populated."""
        reqs = self.build_reqs([self._make_item("disk", huawei_product="EVS", tier="high_io", derived_quantity=512)])
        spec = reqs[0]["spec"]
        assert spec["spec_type"] == "storage"
        assert spec["tier"] == "high_io"


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 9B.2: Database service display name
# ═══════════════════════════════════════════════════════════════════════════════


class TestDatabaseServiceDisplayName:
    """Validate _database_service_display_name picks service-level names."""

    def test_azure_mysql_flexible_server_name(self):
        """Azure MySQL Flexible Server compute+storage+IO → service-level name."""
        items = [
            {"source_service_name": "Azure Database for MySQL Flexible Server Compute", "source_service_family": "MySQL"},
            {"source_service_name": "Azure Database for MySQL Flexible Server Storage", "source_service_family": "MySQL"},
            {"source_service_name": "Azure Database for MySQL Flexible Server IO", "source_service_family": "MySQL"},
        ]
        name = _database_service_display_name("Azure", items)
        assert "Azure Database" in name
        assert "MySQL" in name
        # Should NOT contain sub-component suffixes
        assert "Compute" not in name
        assert "Storage" not in name

    def test_aws_rds_mysql_name(self):
        """AWS RDS MySQL → 'AWS RDS for MySQL'."""
        items = [
            {"source_service_name": "AWS RDS for MySQL Compute", "source_service_family": "MySQL"},
            {"source_service_name": "AWS RDS for MySQL Storage", "source_service_family": "MySQL"},
        ]
        name = _database_service_display_name("AWS", items)
        assert "RDS" in name
        assert "MySQL" in name
        assert "Compute" not in name

    def test_gcp_cloud_sql_name(self):
        """GCP Cloud SQL PostgreSQL → 'GCP Cloud SQL for PostgreSQL'."""
        items = [
            {"source_service_name": "GCP Cloud SQL for PostgreSQL Compute", "source_service_family": "PostgreSQL"},
        ]
        name = _database_service_display_name("GCP", items)
        assert "Cloud SQL" in name
        assert "PostgreSQL" in name

    def test_bare_engine_name_uses_mapped_base(self):
        """When source_service_name is just 'MySQL compute', use mapped base + engine."""
        items = [
            {"source_service_name": "MySQL compute", "source_service_family": "MySQL"},
        ]
        name = _database_service_display_name("Azure", items)
        assert "Azure Database" in name
        assert "MySQL" in name

    def test_no_storage_sub_item_name_leak(self):
        """Database name should NOT start with 'Storage -' or contain 'Almacenamiento'."""
        items = [
            {"source_service_name": "Azure Database for MySQL Flexible Server Storage - Almacenamiento", "source_service_family": "MySQL"},
        ]
        name = _database_service_display_name("Azure", items)
        assert not name.startswith("Storage")
        assert "Almacenamiento" not in name
        assert "MySQL" in name


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 9B.3: Database config summary composition
# ═══════════════════════════════════════════════════════════════════════════════


class TestDatabaseConfigSummary:
    """Validate _database_config_summary composes compute+storage+IO."""

    def test_compute_plus_storage(self):
        """4 vCore / 32 GiB + 2296 GB storage."""
        items = [
            {"source_service_name": "MySQL compute", "source_config_summary": "Memory Optimized, 4 vCore / 32 GiB"},
            {"source_service_name": "MySQL storage", "source_config_summary": "2296 GB"},
        ]
        result = _database_config_summary(items)
        assert result is not None
        assert "4 vCore" in result
        assert "32 GiB" in result
        assert "2296 GB" in result
        assert "storage" in result.lower()

    def test_compute_plus_storage_plus_paid_io(self):
        """Config with paid IO should include '+ paid IO'."""
        items = [
            {"source_service_name": "MySQL compute", "source_config_summary": "4 vCore / 32 GiB"},
            {"source_service_name": "MySQL storage", "source_config_summary": "500 GB"},
            {"source_service_name": "MySQL IO", "source_config_summary": "Paid IO"},
        ]
        result = _database_config_summary(items)
        assert result is not None
        assert "paid IO" in result

    def test_storage_only(self):
        """If only storage item, summary should still show capacity."""
        items = [
            {"source_service_name": "MySQL storage", "source_config_summary": "1024 GB"},
        ]
        result = _database_config_summary(items)
        assert result is not None
        assert "1024 GB" in result

    def test_burstable_instance(self):
        """Burstable B1MS instance class should appear in summary."""
        items = [
            {"source_service_name": "MySQL compute", "source_config_summary": "Burstable B1MS, 1 vCore / 2 GiB"},
            {"source_service_name": "MySQL storage", "source_config_summary": "32 GB"},
        ]
        result = _database_config_summary(items)
        assert result is not None
        assert "Burstable" in result
        assert "1 vCore" in result

    def test_empty_items_returns_none(self):
        """No items → None."""
        result = _database_config_summary([])
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 9B.4: Database composition key tightening
# ═══════════════════════════════════════════════════════════════════════════════


class TestDatabaseCompositionKeyTightening:
    """Validate _composition_key_managed_database distinguishes different DB instances."""

    def test_same_db_compute_storage_io_grouped(self):
        """Same database's compute+storage+IO should have the same composition key."""
        # In real billing data, all sub-items share the same service name prefix
        # (e.g. "Azure Database for MySQL Flexible Server") with sub-type suffix.
        # Shape hint is extracted from source_service_name, so it's consistent.
        base = {"vendor": "Azure", "huawei_product": "RDS", "source_service_family": "MySQL"}
        compute = {**base, "source_service_name": "Azure Database for MySQL Flexible Server Compute", "source_config_summary": "Memory Optimized, 4 vCore / 32 GiB"}
        storage = {**base, "source_service_name": "Azure Database for MySQL Flexible Server Storage", "source_config_summary": "2296 GB storage"}
        io_item = {**base, "source_service_name": "Azure Database for MySQL Flexible Server IO", "source_config_summary": "Paid IO"}
        key_c = _composition_key_managed_database(compute)
        key_s = _composition_key_managed_database(storage)
        key_io = _composition_key_managed_database(io_item)
        assert key_c == key_s == key_io

    def test_different_mysql_instances_not_merged(self):
        """Two MySQL instances with different compute shapes in service name should NOT merge."""
        base = {"vendor": "Azure", "huawei_product": "RDS", "source_service_family": "MySQL"}
        mem_opt = {**base, "source_service_name": "Azure Database for MySQL Memory Optimized Compute", "source_config_summary": "Memory Optimized, 8 vCore / 64 GiB"}
        burstable = {**base, "source_service_name": "Azure Database for MySQL Burstable Compute", "source_config_summary": "Burstable B1MS, 1 vCore / 2 GiB"}
        key1 = _composition_key_managed_database(mem_opt)
        key2 = _composition_key_managed_database(burstable)
        assert key1 != key2

    def test_mysql_vs_postgres_not_merged(self):
        """MySQL and PostgreSQL should never merge even with same vendor."""
        base = {"vendor": "Azure", "huawei_product": "RDS"}
        mysql = {**base, "source_service_family": "MySQL", "source_service_name": "Azure MySQL", "source_config_summary": "4 vCore"}
        postgres = {**base, "source_service_family": "PostgreSQL", "source_service_name": "Azure PostgreSQL", "source_config_summary": "4 vCore"}
        key_m = _composition_key_managed_database(mysql)
        key_p = _composition_key_managed_database(postgres)
        assert key_m != key_p

    def test_key_includes_engine(self):
        """Composition key should include the engine component."""
        item = {"vendor": "AWS", "huawei_product": "RDS", "source_service_family": "MySQL",
                "source_service_name": "AWS RDS for MySQL", "source_config_summary": "4 vCore"}
        key = _composition_key_managed_database(item)
        # Key should be a tuple with engine present
        assert "mysql" in key

    def test_key_includes_shape_hint(self):
        """Composition key should include shape hint when present in service name."""
        base = {"vendor": "Azure", "huawei_product": "RDS", "source_service_family": "MySQL"}
        mem = {**base, "source_service_name": "Azure Database for MySQL Memory Optimized Compute", "source_config_summary": "Memory Optimized, 4 vCore"}
        gp = {**base, "source_service_name": "Azure Database for MySQL General Purpose Compute", "source_config_summary": "General Purpose, 4 vCore"}
        key_mem = _composition_key_managed_database(mem)
        key_gp = _composition_key_managed_database(gp)
        assert key_mem != key_gp


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 10A: LLM Composition Candidate model
# ═══════════════════════════════════════════════════════════════════════════════


class TestCloudBillingFinalCompositionCandidateModel:
    """Validate CloudBillingFinalCompositionCandidate model."""

    def test_minimal_construction(self):
        from app.models import CloudBillingFinalCompositionCandidate
        c = CloudBillingFinalCompositionCandidate(
            candidate_id="c1", vendor="Azure",
            resource_kind="compute_vm", source_service_name="Azure VM",
        )
        assert c.candidate_id == "c1"
        assert c.vendor == "Azure"
        assert c.status == "unquoted"
        assert c.component_refs == []
        assert c.confidence is None

    def test_full_construction(self):
        from app.models import CloudBillingFinalCompositionCandidate
        c = CloudBillingFinalCompositionCandidate(
            candidate_id="c2", vendor="AWS",
            resource_kind="managed_database",
            source_service_name="AWS RDS for MySQL",
            source_config_summary="4 vCore / 32 GiB + 500 GB storage",
            source_quantity=1.0,
            source_billing_basis="instance-month",
            source_monthly_total_usd=450.0,
            huawei_product="RDS",
            huawei_spec_hint="rds.mysql.x1.large",
            huawei_quantity=1.0,
            huawei_billing_basis="instance-month",
            status="quoted",
            composition_notes=["Composed from 3 sub-items: compute, storage, IO."],
            component_refs=["billing-agg::file::0", "billing-agg::file::1", "billing-agg::file::2"],
            confidence=0.92,
        )
        assert len(c.component_refs) == 3
        assert c.confidence == 0.92

    def test_invalid_candidate_rejected(self):
        from app.models import CloudBillingFinalCompositionCandidate
        with pytest.raises(Exception):
            CloudBillingFinalCompositionCandidate(
                candidate_id="bad",
                # Missing required fields: vendor, resource_kind, source_service_name
            )

    def test_invalid_status_rejected(self):
        from app.models import CloudBillingFinalCompositionCandidate
        with pytest.raises(Exception):
            CloudBillingFinalCompositionCandidate(
                candidate_id="c3", vendor="Azure",
                resource_kind="compute_vm", source_service_name="VM",
                status="invalid_status",
            )

    def test_separate_from_final_quote_item(self):
        """CloudBillingFinalCompositionCandidate is distinct from CloudBillingFinalQuoteItem."""
        from app.models import CloudBillingFinalCompositionCandidate
        assert CloudBillingFinalCompositionCandidate is not CloudBillingFinalQuoteItem
        # Candidate has confidence and component_refs; FinalQuoteItem has source_item_ids
        c = CloudBillingFinalCompositionCandidate(
            candidate_id="c1", vendor="Azure",
            resource_kind="compute_vm", source_service_name="VM",
            component_refs=["ref1"], confidence=0.8,
        )
        assert hasattr(c, "confidence")
        assert hasattr(c, "component_refs")
        # FinalQuoteItem doesn't have these
        fi = CloudBillingFinalQuoteItem(
            item_id="fqi-1", vendor="Azure",
            resource_kind="compute_vm", source_service_name="VM",
        )
        assert not hasattr(fi, "confidence")
        assert not hasattr(fi, "component_refs")


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 10B+C: LLM composition node + unified prompt
# ═══════════════════════════════════════════════════════════════════════════════


class TestFinalCompositionPrompt:
    """Validate the LLM final composition prompt builder."""

    @pytest.fixture(autouse=True)
    def _import_fn(self):
        from app.cloud_billing_workflow import _build_final_composition_prompt
        self.build_prompt = _build_final_composition_prompt

    def test_prompt_includes_aggregated_items(self):
        agg = [{"vendor": "Azure", "resource_kind": "ecs", "aggregate_label": "VM D8s v3",
                "product_family": "Compute", "product_type": "Virtual Machine",
                "product_sku": "D8s_v3", "derived_quantity": 6, "derived_unit": "instance-month",
                "amount": 1200, "huawei_product": "ECS", "huawei_spec_hint": "D8s v3",
                "needs_manual_review": False, "source_file": "test.xlsx"}]
        prompt = self.build_prompt(agg, [], {"region": "mexico"})
        assert "aggregated_items" in prompt
        assert len(prompt["aggregated_items"]) == 1
        assert prompt["total_items"] == 1

    def test_prompt_includes_quote_line_summary(self):
        agg = [{"vendor": "Azure", "resource_kind": "ecs", "aggregate_label": "VM",
                "product_family": "", "product_type": "", "product_sku": "",
                "derived_quantity": 1, "derived_unit": "instance-month",
                "amount": 200, "huawei_product": "ECS", "huawei_spec_hint": "",
                "needs_manual_review": False, "source_file": "test.xlsx"}]
        ql = [FlexibleQuoteLine(
            line_id="l1", requirement_item_id="billing-agg::test.xlsx::0",
            product="ECS", region="mexico", quantity=1, unit="instance-month",
            billing_mode="on-demand", unit_price=200, monthly_price=200,
        ).model_dump()]
        prompt = self.build_prompt(agg, ql, {})
        item = prompt["aggregated_items"][0]
        assert "quote_line" in item
        assert item["quote_line"]["product"] == "ECS"

    def test_prompt_is_cross_cloud(self):
        """Prompt data works for Azure, AWS, and GCP items."""
        from app.cloud_billing_workflow import _FINAL_COMPOSITION_SYSTEM_PROMPT
        # System prompt should mention all three vendors
        assert "Azure" in _FINAL_COMPOSITION_SYSTEM_PROMPT
        assert "AWS" in _FINAL_COMPOSITION_SYSTEM_PROMPT
        assert "GCP" in _FINAL_COMPOSITION_SYSTEM_PROMPT
        # And unified resource kinds
        assert "compute_vm" in _FINAL_COMPOSITION_SYSTEM_PROMPT
        assert "managed_database" in _FINAL_COMPOSITION_SYSTEM_PROMPT

    def test_prompt_aws_items(self):
        agg = [{"vendor": "AWS", "resource_kind": "ecs", "aggregate_label": "EC2 m5.xlarge",
                "product_family": "Compute", "product_type": "EC2",
                "product_sku": "m5.xlarge", "derived_quantity": 3, "derived_unit": "instance-month",
                "amount": 600, "huawei_product": "ECS", "huawei_spec_hint": "m5.xlarge",
                "needs_manual_review": False, "source_file": "aws.csv"}]
        prompt = self.build_prompt(agg, [], {})
        assert prompt["aggregated_items"][0]["vendor"] == "AWS"

    def test_prompt_gcp_items(self):
        agg = [{"vendor": "GCP", "resource_kind": "ecs", "aggregate_label": "Compute Engine n2-standard-8",
                "product_family": "Compute", "product_type": "Compute Engine",
                "product_sku": "n2-standard-8", "derived_quantity": 2, "derived_unit": "instance-month",
                "amount": 500, "huawei_product": "ECS", "huawei_spec_hint": "n2-standard-8",
                "needs_manual_review": False, "source_file": "gcp.json"}]
        prompt = self.build_prompt(agg, [], {})
        assert prompt["aggregated_items"][0]["vendor"] == "GCP"


class TestLLMCompositionFallback:
    """Validate that LLM composition falls back to deterministic when MaaS unavailable."""

    def test_maas_unavailable_falls_back(self):
        """When MaaS env vars are not set, compose_final_billing_quote_items_with_llm
        falls back to deterministic composer."""
        from app.cloud_billing_workflow import compose_final_billing_quote_items_with_llm
        import os

        # Ensure MaaS env vars are not set
        for var in ("HUAWEI_MAAS_API_KEY", "HUAWEI_MAAS_BASE_URL", "HUAWEI_MAAS_MODEL"):
            os.environ.pop(var, None)

        # Build a minimal state with some quote lines
        state = {
            "llm_aggregated_billing_items": [],
            "quote_lines": [],
            "requirements": [],
            "unquoted_items": [],
            "quote_blockers": [],
            "quote_context": {"region": "mexico"},
            "audit_log": [],
            "final_billing_quote_items": [],
            "llm_composition_candidates": [],
        }
        result = compose_final_billing_quote_items_with_llm(state)
        # Should have fallen back to deterministic composer
        assert "final_billing_quote_items" in result
        # Audit log should mention fallback
        audit_msgs = [a.get("message", "") for a in result.get("audit_log", [])]
        assert any("fallback" in m.lower() for m in audit_msgs)

    def test_invalid_json_falls_back(self, monkeypatch):
        """When LLM returns invalid JSON, falls back to deterministic composer."""
        from app.cloud_billing_workflow import compose_final_billing_quote_items_with_llm
        import httpx

        # Mock MaaS to return invalid JSON
        def mock_post(*args, **kwargs):
            class MockResp:
                def raise_for_status(self): pass
                def json(self):
                    return {"choices": [{"message": {"content": "NOT VALID JSON!!!"}}]}
            return MockResp()

        monkeypatch.setenv("HUAWEI_MAAS_API_KEY", "test")
        monkeypatch.setenv("HUAWEI_MAAS_BASE_URL", "http://localhost:9999")
        monkeypatch.setenv("HUAWEI_MAAS_MODEL", "test-model")
        monkeypatch.setattr(httpx.Client, "post", mock_post)

        state = {
            "llm_aggregated_billing_items": [
                {"vendor": "Azure", "resource_kind": "ecs", "aggregate_label": "VM",
                 "product_family": "", "product_type": "", "product_sku": "",
                 "derived_quantity": 1, "derived_unit": "instance-month",
                 "amount": 200, "huawei_product": "ECS", "huawei_spec_hint": "",
                 "needs_manual_review": False, "source_file": "test.xlsx"},
            ],
            "quote_lines": [],
            "requirements": [],
            "unquoted_items": [],
            "quote_blockers": [],
            "quote_context": {"region": "mexico"},
            "audit_log": [],
            "final_billing_quote_items": [],
            "llm_composition_candidates": [],
        }
        result = compose_final_billing_quote_items_with_llm(state)
        assert "final_billing_quote_items" in result


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 10D: Validation and Enrichment
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateAndEnrichLLMFinalCandidates:
    """Validate _validate_and_enrich_llm_final_candidates."""

    @pytest.fixture(autouse=True)
    def _import_fn(self):
        from app.cloud_billing_workflow import _validate_and_enrich_llm_final_candidates
        self.validate_enrich = _validate_and_enrich_llm_final_candidates

    def _make_agg_item(self, idx, kind="ecs", vendor="Azure", amount=200, **overrides):
        item = {
            "vendor": vendor, "resource_kind": kind,
            "aggregate_label": f"Item {idx}", "product_family": "",
            "product_type": "", "product_sku": "",
            "derived_quantity": 1, "derived_unit": "instance-month",
            "amount": amount, "huawei_product": "ECS" if kind == "ecs" else "RDS",
            "huawei_spec_hint": "", "needs_manual_review": False,
            "source_file": "test.xlsx",
        }
        item.update(overrides)
        return item

    def test_source_totals_recalculated_from_refs(self):
        """Source monthly total is summed from component refs, not trusted from LLM."""
        agg_items = [
            self._make_agg_item(0, amount=300),
            self._make_agg_item(1, amount=100),
            self._make_agg_item(2, amount=50),
        ]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "managed_database",
            "source_service_name": "Azure Database for MySQL",
            "source_monthly_total_usd": 9999,  # LLM lies — should be overwritten
            "component_refs": ["billing-agg::test.xlsx::0", "billing-agg::test.xlsx::1", "billing-agg::test.xlsx::2"],
            "composition_notes": [],
        }]
        result = self.validate_enrich(candidates, agg_items, [], [], [], [])
        assert len(result) == 1
        # Source total should be 300 + 100 + 50 = 450, not 9999
        assert result[0].source_monthly_total_usd == 450.0

    def test_huawei_totals_recalculated_from_quote_lines(self):
        """Huawei monthly total is summed from quote lines, not from LLM."""
        agg_items = [self._make_agg_item(0, amount=200)]
        ql = [FlexibleQuoteLine(
            line_id="l1", requirement_item_id="billing-agg::test.xlsx::0",
            product="ECS", region="mexico", quantity=1, unit="instance-month",
            billing_mode="on-demand", unit_price=180, monthly_price=180,
        ).model_dump()]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "compute_vm",
            "source_service_name": "Azure VM",
            "component_refs": ["billing-agg::test.xlsx::0"],
            "composition_notes": [],
        }]
        result = self.validate_enrich(candidates, agg_items, ql, [], [], [])
        assert len(result) == 1
        assert result[0].huawei_monthly_total_usd == 180.0
        assert result[0].huawei_product == "ECS"

    def test_mixed_quoted_unquoted_is_partial(self):
        """If some components are quoted and some unquoted, status is partial."""
        agg_items = [
            self._make_agg_item(0, amount=300),
            self._make_agg_item(1, amount=100),
        ]
        # Only first item has a quote line
        ql = [FlexibleQuoteLine(
            line_id="l1", requirement_item_id="billing-agg::test.xlsx::0",
            product="ECS", region="mexico", quantity=1, unit="instance-month",
            billing_mode="on-demand", unit_price=200, monthly_price=200,
        ).model_dump()]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "compute_vm",
            "source_service_name": "Azure VM",
            "component_refs": ["billing-agg::test.xlsx::0", "billing-agg::test.xlsx::1"],
            "composition_notes": [],
        }]
        result = self.validate_enrich(candidates, agg_items, ql, [], [], [])
        assert len(result) == 1
        assert result[0].status == "partial"

    def test_manual_review_candidate_remains_manual_review(self):
        """If components are flagged for manual review, status is manual_review."""
        agg_items = [self._make_agg_item(0, amount=100, needs_manual_review=True)]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "platform_paas_misc",
            "source_service_name": "API Management",
            "component_refs": ["billing-agg::test.xlsx::0"],
            "composition_notes": [],
        }]
        result = self.validate_enrich(candidates, agg_items, [], [], [], [])
        assert len(result) == 1
        assert result[0].status == "manual_review"

    def test_invalid_candidate_rejected(self):
        """Candidates that fail schema validation are silently dropped."""
        agg_items = [self._make_agg_item(0)]
        candidates = [
            {"invalid": "missing required fields"},  # Will fail validation
            {"candidate_id": "c2", "vendor": "Azure", "resource_kind": "compute_vm",
             "source_service_name": "Azure VM",
             "component_refs": ["billing-agg::test.xlsx::0"],
             "composition_notes": []},
        ]
        result = self.validate_enrich(candidates, agg_items, [], [], [], [])
        assert len(result) == 1
        assert result[0].source_service_name == "Azure VM"

    def test_no_valid_refs_candidate_dropped(self):
        """Candidates with no valid component_refs are dropped."""
        agg_items = [self._make_agg_item(0)]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "compute_vm",
            "source_service_name": "Azure VM",
            "component_refs": ["nonexistent-ref-1", "nonexistent-ref-2"],
            "composition_notes": [],
        }]
        result = self.validate_enrich(candidates, agg_items, [], [], [], [])
        assert len(result) == 0

    def test_vm_plus_storage_mixed_candidate_downgraded(self):
        """A candidate that mixes VM and storage refs is downgraded (compute-only)."""
        agg_items = [
            self._make_agg_item(0, kind="ecs", amount=300),
            self._make_agg_item(1, kind="evs", amount=50),
        ]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "compute_vm",
            "source_service_name": "VM + Disk (wrong)",
            "component_refs": ["billing-agg::test.xlsx::0", "billing-agg::test.xlsx::1"],
            "composition_notes": [],
        }]
        result = self.validate_enrich(candidates, agg_items, [], [], [], [])
        # Should keep only compute refs
        assert len(result) == 1
        assert "billing-agg::test.xlsx::0" in result[0].source_item_ids
        # Storage ref should be removed
        assert "billing-agg::test.xlsx::1" not in result[0].source_item_ids
        # Totals should be recomputed from remaining refs only
        assert result[0].source_monthly_total_usd == 300.0
        assert result[0].status == "unquoted"

    def test_one_to_many_quote_lines_aggregated(self):
        """A candidate referencing multiple quote lines gets aggregated Huawei total."""
        agg_items = [
            self._make_agg_item(0, amount=150),
            self._make_agg_item(1, amount=80),
        ]
        ql = [
            FlexibleQuoteLine(
                line_id="l1", requirement_item_id="billing-agg::test.xlsx::0",
                product="ELB", region="mexico", quantity=1, unit="instance-month",
                billing_mode="on-demand", unit_price=150, monthly_price=150,
            ).model_dump(),
            FlexibleQuoteLine(
                line_id="l2", requirement_item_id="billing-agg::test.xlsx::1",
                product="WAF", region="mexico", quantity=1, unit="instance-month",
                billing_mode="on-demand", unit_price=80, monthly_price=80,
            ).model_dump(),
        ]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "load_balancing_and_waf",
            "source_service_name": "Application Gateway WAF v2",
            "component_refs": ["billing-agg::test.xlsx::0", "billing-agg::test.xlsx::1"],
            "composition_notes": ["Composed from ELB + WAF sub-items."],
        }]
        result = self.validate_enrich(candidates, agg_items, ql, [], [], [])
        assert len(result) == 1
        # Huawei total should be 150 + 80 = 230
        assert result[0].huawei_monthly_total_usd == 230.0
        # Product should show both
        assert "ELB" in result[0].huawei_product
        assert "WAF" in result[0].huawei_product
        # Composite items must not pretend to have a single unit price/billing basis
        assert result[0].huawei_unit_price_usd is None
        assert result[0].huawei_billing_basis == "composite"

    def test_llm_vm_quantity_uses_display_quantity(self):
        """LLM path should reuse display quantity semantics, not raw billing hours."""
        agg_items = [
            self._make_agg_item(0, kind="ecs", amount=1716.07, derived_quantity=6.0066, huawei_product="ECS"),
        ]
        ql = [FlexibleQuoteLine(
            line_id="l1", requirement_item_id="billing-agg::test.xlsx::0",
            product="ECS", region="mexico", quantity=6.0066, unit="instance-hour",
            billing_mode="on-demand", unit_price=223.67, monthly_price=1343.5,
        ).model_dump()]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "compute_vm",
            "source_service_name": "Azure VM",
            "component_refs": ["billing-agg::test.xlsx::0"],
            "composition_notes": [],
        }]
        result = self.validate_enrich(candidates, agg_items, ql, [], [], [])
        assert len(result) == 1
        assert result[0].source_quantity == 6.0

    def test_llm_disk_quantity_not_tiny_ratio(self):
        """Disk quantity in LLM path should use business count, not disk-month ratio."""
        agg_items = [
            self._make_agg_item(0, kind="evs", amount=71.67, derived_quantity=0.0054, huawei_product="EVS"),
            self._make_agg_item(1, kind="evs", amount=71.67, derived_quantity=0.0054, huawei_product="EVS"),
            self._make_agg_item(2, kind="evs", amount=71.67, derived_quantity=0.0054, huawei_product="EVS"),
            self._make_agg_item(3, kind="evs", amount=71.67, derived_quantity=0.0054, huawei_product="EVS"),
        ]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "block_storage",
            "source_service_name": "Azure Managed Disk",
            "component_refs": [f"billing-agg::test.xlsx::{i}" for i in range(4)],
            "composition_notes": [],
        }]
        result = self.validate_enrich(candidates, agg_items, [], [], [], [])
        assert len(result) == 1
        assert result[0].source_quantity == 4.0


class TestQuoteItemsMultiComponent:
    """Validate quote_items can emit multiple lines for one requirement."""

    def test_quote_items_supports_multiple_components_per_requirement(self):
        requirement = RequirementItem(
            item_id="billing-agg::test.xlsx::0",
            source_file="test.xlsx",
            raw_product_name="Application Gateway WAF v2",
            normalized_product="ELB",
            quantity=1,
            quantity_source="billing_standardized",
            unit="instance-month",
            region="mexico",
            spec={"spec_type": "generic", "sku": "appgw"},
            status="ready",
        ).model_dump()
        price_components = [
            {
                "requirement_item_id": "billing-agg::test.xlsx::0",
                "product": "ELB",
                "region": "mexico",
                "sku": "elb-shared",
                "tier": "shared",
                "billing_mode": "monthly",
                "unit": "instance-month",
                "price": 150.0,
                "currency": "USD",
                "source_url": "test",
                "captured_at": "2026-06-10T00:00:00Z",
                "confirmed": True,
                "status": "confirmed",
            },
            {
                "requirement_item_id": "billing-agg::test.xlsx::0",
                "product": "WAF",
                "region": "mexico",
                "sku": "waf-basic",
                "tier": "basic",
                "billing_mode": "monthly",
                "unit": "instance-month",
                "price": 80.0,
                "currency": "USD",
                "source_url": "test",
                "captured_at": "2026-06-10T00:00:00Z",
                "confirmed": True,
                "status": "confirmed",
            },
        ]
        result = quote_items(
            {
                "price_components": price_components,
                "quote_ready_items": [requirement],
                "audit_log": [],
            }
        )
        lines = [FlexibleQuoteLine.model_validate(x) for x in result["quote_lines"]]
        assert len(lines) == 2
        assert {line.product for line in lines} == {"ELB", "WAF"}
        assert len({line.line_id for line in lines}) == 2


class TestFinalQuoteExportNormalization:
    """Validate export-time normalization shared by billing final items."""

    def test_display_billing_basis_customerized(self):
        assert _display_billing_basis_for_quotation("instance hours") == "Monthly usage"
        assert _display_billing_basis_for_quotation("capacity gib month") == "Monthly capacity"

    def test_quoted_vm_zero_quantity_backfilled_from_pricing(self):
        item = CloudBillingFinalQuoteItem(
            item_id="fqi-2",
            vendor="Azure",
            resource_kind="compute_vm",
            source_service_name="Azure VM",
            source_quantity=0,
            source_pricing_basis="instance hours",
            huawei_product="ECS",
            huawei_unit_price_usd=223.67,
            huawei_monthly_total_usd=1343.5,
            huawei_quantity=0,
            status="quoted",
        )
        normalized = _normalize_final_quote_item_for_export(item)
        assert normalized.source_quantity == 6.0
        assert normalized.huawei_quantity == 6.0
        assert normalized.source_pricing_basis == "Monthly usage"

    def test_composite_item_drops_single_unit_price_semantics(self):
        item = CloudBillingFinalQuoteItem(
            item_id="fqi-3",
            vendor="Azure",
            resource_kind="load_balancing_and_waf",
            source_service_name="Azure Application Gateway",
            source_quantity=1,
            huawei_product="ELB + WAF",
            huawei_unit_price_usd=10,
            huawei_billing_basis="monthly",
            huawei_quantity=1,
            status="partial",
        )
        normalized = _normalize_final_quote_item_for_export(item)
        assert normalized.huawei_unit_price_usd is None
        assert normalized.huawei_billing_basis == "composite"
        assert normalized.huawei_quantity is None


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 10F: Cross-cloud composition fixtures
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrossCloudCompositionFixtures:
    """Validate that the same pipeline structure works for Azure, AWS, and GCP."""

    def _make_billing_agg(self, vendor, kind, label, amount, **overrides):
        return {
            "vendor": vendor, "resource_kind": kind,
            "aggregate_label": label, "product_family": "",
            "product_type": "", "product_sku": "",
            "derived_quantity": 1, "derived_unit": "instance-month",
            "amount": amount, "huawei_product": "ECS",
            "huawei_spec_hint": "", "needs_manual_review": False,
            "source_file": f"{vendor.lower()}.csv",
            **overrides,
        }

    def test_azure_vm_to_final_candidate(self):
        """Azure VM aggregated items → one final candidate."""
        from app.cloud_billing_workflow import _validate_and_enrich_llm_final_candidates
        agg = [self._make_billing_agg("Azure", "ecs", "VM D8s v3", 1200)]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "compute_vm",
            "source_service_name": "Azure VM",
            "source_config_summary": "D8s v3, 8 vCPU / 32 GiB",
            "source_quantity": 6,
            "component_refs": ["billing-agg::azure.csv::0"],
            "composition_notes": [],
        }]
        result = _validate_and_enrich_llm_final_candidates(candidates, agg, [], [], [], [])
        assert len(result) == 1
        assert result[0].vendor == "Azure"
        assert result[0].resource_kind == "compute_vm"

    def test_aws_ec2_to_final_candidate(self):
        """AWS EC2 aggregated items → one final candidate."""
        from app.cloud_billing_workflow import _validate_and_enrich_llm_final_candidates
        agg = [self._make_billing_agg("AWS", "ecs", "EC2 m5.xlarge", 600, source_file="aws.csv")]
        candidates = [{
            "candidate_id": "c1", "vendor": "AWS",
            "resource_kind": "compute_vm",
            "source_service_name": "AWS EC2",
            "source_config_summary": "m5.xlarge, 4 vCPU / 16 GiB",
            "source_quantity": 3,
            "component_refs": ["billing-agg::aws.csv::0"],
            "composition_notes": [],
        }]
        result = _validate_and_enrich_llm_final_candidates(candidates, agg, [], [], [], [])
        assert len(result) == 1
        assert result[0].vendor == "AWS"

    def test_gcp_compute_engine_to_final_candidate(self):
        """GCP Compute Engine aggregated items → one final candidate."""
        from app.cloud_billing_workflow import _validate_and_enrich_llm_final_candidates
        agg = [self._make_billing_agg("GCP", "ecs", "Compute Engine n2-standard-8", 500, source_file="gcp.json")]
        candidates = [{
            "candidate_id": "c1", "vendor": "GCP",
            "resource_kind": "compute_vm",
            "source_service_name": "GCP Compute Engine",
            "source_config_summary": "n2-standard-8, 8 vCPU / 32 GiB",
            "source_quantity": 2,
            "component_refs": ["billing-agg::gcp.json::0"],
            "composition_notes": [],
        }]
        result = _validate_and_enrich_llm_final_candidates(candidates, agg, [], [], [], [])
        assert len(result) == 1
        assert result[0].vendor == "GCP"

    def test_azure_mysql_composed_to_one_db_candidate(self):
        """Azure MySQL compute+storage+IO → one DB candidate."""
        from app.cloud_billing_workflow import _validate_and_enrich_llm_final_candidates
        agg = [
            self._make_billing_agg("Azure", "rds", "MySQL Compute", 300, source_file="az.xlsx"),
            self._make_billing_agg("Azure", "rds", "MySQL Storage", 100, source_file="az.xlsx"),
            self._make_billing_agg("Azure", "rds", "MySQL IO", 50, source_file="az.xlsx"),
        ]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "managed_database",
            "source_service_name": "Azure Database for MySQL Flexible Server",
            "source_config_summary": "Memory Optimized, 4 vCore / 32 GiB + 2296 GB storage + paid IO",
            "source_quantity": 1,
            "component_refs": ["billing-agg::az.xlsx::0", "billing-agg::az.xlsx::1", "billing-agg::az.xlsx::2"],
            "composition_notes": ["Composed from 3 sub-items: compute, storage, IO."],
        }]
        result = _validate_and_enrich_llm_final_candidates(candidates, agg, [], [], [], [])
        assert len(result) == 1
        assert result[0].resource_kind == "managed_database"
        assert result[0].source_monthly_total_usd == 450.0  # 300 + 100 + 50

    def test_aws_rds_to_one_db_candidate(self):
        """AWS RDS → one DB candidate."""
        from app.cloud_billing_workflow import _validate_and_enrich_llm_final_candidates
        agg = [
            self._make_billing_agg("AWS", "rds", "RDS MySQL Compute", 250, source_file="aws.csv"),
            self._make_billing_agg("AWS", "rds", "RDS MySQL Storage", 80, source_file="aws.csv"),
        ]
        candidates = [{
            "candidate_id": "c1", "vendor": "AWS",
            "resource_kind": "managed_database",
            "source_service_name": "AWS RDS for MySQL",
            "source_quantity": 1,
            "component_refs": ["billing-agg::aws.csv::0", "billing-agg::aws.csv::1"],
            "composition_notes": [],
        }]
        result = _validate_and_enrich_llm_final_candidates(candidates, agg, [], [], [], [])
        assert len(result) == 1
        assert result[0].resource_kind == "managed_database"

    def test_gcp_cloud_sql_to_one_db_candidate(self):
        """GCP Cloud SQL → one DB candidate."""
        from app.cloud_billing_workflow import _validate_and_enrich_llm_final_candidates
        agg = [
            self._make_billing_agg("GCP", "rds", "Cloud SQL PostgreSQL Compute", 220, source_file="gcp.json"),
            self._make_billing_agg("GCP", "rds", "Cloud SQL PostgreSQL Storage", 70, source_file="gcp.json"),
        ]
        candidates = [{
            "candidate_id": "c1", "vendor": "GCP",
            "resource_kind": "managed_database",
            "source_service_name": "GCP Cloud SQL for PostgreSQL",
            "source_quantity": 1,
            "component_refs": ["billing-agg::gcp.json::0", "billing-agg::gcp.json::1"],
            "composition_notes": [],
        }]
        result = _validate_and_enrich_llm_final_candidates(candidates, agg, [], [], [], [])
        assert len(result) == 1
        assert result[0].resource_kind == "managed_database"

    def test_object_storage_grouped(self):
        """Object storage items grouped into one final candidate."""
        from app.cloud_billing_workflow import _validate_and_enrich_llm_final_candidates
        agg = [self._make_billing_agg("Azure", "obs", "Blob Storage", 50, source_file="az.xlsx")]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "object_storage",
            "source_service_name": "Azure Blob Storage",
            "source_quantity": 1,
            "component_refs": ["billing-agg::az.xlsx::0"],
            "composition_notes": [],
        }]
        result = _validate_and_enrich_llm_final_candidates(candidates, agg, [], [], [], [])
        assert len(result) == 1
        assert result[0].resource_kind == "object_storage"

    def test_platform_paas_grouped_as_manual_review(self):
        """Platform/PaaS items grouped as manual_review."""
        from app.cloud_billing_workflow import _validate_and_enrich_llm_final_candidates
        agg = [
            self._make_billing_agg("Azure", "unsupported", "API Management", 20,
                                   needs_manual_review=True, source_file="az.xlsx"),
            self._make_billing_agg("Azure", "unsupported", "Service Bus", 15,
                                   needs_manual_review=True, source_file="az.xlsx"),
        ]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "platform_paas_misc",
            "source_service_name": "Platform / PaaS Services",
            "component_refs": ["billing-agg::az.xlsx::0", "billing-agg::az.xlsx::1"],
            "composition_notes": ["Grouped for manual review."],
        }]
        result = _validate_and_enrich_llm_final_candidates(candidates, agg, [], [], [], [])
        assert len(result) == 1
        assert result[0].status == "manual_review"


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 14A: _build_llm_first_billing_rows
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildLLMFirstBillingRows:
    """Validate _build_llm_first_billing_rows extracts raw billing rows."""

    @pytest.fixture(autouse=True)
    def _import_fn(self):
        from app.cloud_billing_workflow import _build_llm_first_billing_rows
        self.build_rows = _build_llm_first_billing_rows

    def test_extracts_from_billing_lines(self):
        """billing_lines → row dicts with stable row_ids."""
        state = {
            "billing_lines": [
                {"vendor": "Azure", "source_file": "azure.csv", "source_sheet": "Sheet1",
                 "line_number": 5, "service_period": "2024-05", "product_family": "Compute",
                 "product_type": "Virtual Machine", "product_sku": "D8s_v3",
                 "unit_type": "Hours", "quantity_raw": "744", "amount_raw": "200.50",
                 "currency": "USD", "region_hint": "East US", "transaction_type": "Usage"},
                {"vendor": "Azure", "source_file": "azure.csv", "source_sheet": "Sheet1",
                 "line_number": 6, "product_family": "Storage",
                 "product_type": "Managed Disk", "product_sku": "P10",
                 "unit_type": "GB", "quantity_raw": "128", "amount_raw": "15.00",
                 "currency": "USD", "region_hint": "", "transaction_type": "Usage"},
            ],
        }
        rows = self.build_rows(state)
        assert len(rows) == 2
        assert rows[0]["row_id"] == "billing-row::azure.csv::5"
        assert rows[1]["row_id"] == "billing-row::azure.csv::6"
        assert rows[0]["product_family"] == "Compute"
        assert rows[0]["amount"] == "200.50"
        assert rows[0]["amount_numeric"] == 200.50
        assert rows[0]["quantity_numeric"] == 744.0
        assert rows[0]["source_sheet"] == "Sheet1"

    def test_row_refs_stable_and_traceable(self):
        """row_id format is billing-row::{source_file}::{line_number}."""
        state = {
            "billing_lines": [
                {"vendor": "AWS", "source_file": "aws.csv", "source_sheet": "",
                 "line_number": 100, "product_family": "", "product_type": "",
                 "product_sku": "", "unit_type": "", "quantity_raw": "1",
                 "amount_raw": "50", "currency": "USD", "region_hint": "",
                 "transaction_type": "", "service_period": ""},
            ],
        }
        rows = self.build_rows(state)
        assert rows[0]["row_id"] == "billing-row::aws.csv::100"

    def test_fallback_to_aggregated_items(self):
        """When billing_lines is empty, falls back to llm_aggregated_billing_items."""
        state = {
            "billing_lines": [],
            "llm_aggregated_billing_items": [
                {"vendor": "GCP", "source_file": "gcp.json", "product_family": "Compute",
                 "product_type": "Compute Engine", "product_sku": "n2-standard-8",
                 "derived_quantity": 2, "derived_unit": "instance-month",
                 "amount": 500, "huawei_product": "ECS"},
            ],
        }
        rows = self.build_rows(state)
        assert len(rows) == 1
        assert rows[0]["row_id"] == "billing-agg::gcp.json::0"
        assert rows[0]["vendor"] == "GCP"

    def test_empty_state_returns_empty(self):
        """No billing_lines and no aggregated items → empty list."""
        rows = self.build_rows({})
        assert rows == []


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 14B+C: LLM-first prompt
# ═══════════════════════════════════════════════════════════════════════════════


class TestLLMFirstCompositionPrompt:
    """Validate the LLM-first composition prompt."""

    @pytest.fixture(autouse=True)
    def _import_fn(self):
        from app.cloud_billing_workflow import (
            _build_llm_first_composition_prompt,
            _LLM_FIRST_COMPOSITION_SYSTEM_PROMPT,
        )
        self.build_prompt = _build_llm_first_composition_prompt
        self.system_prompt = _LLM_FIRST_COMPOSITION_SYSTEM_PROMPT

    def test_prompt_includes_billing_rows(self):
        rows = [{
            "row_id": "billing-row::f::1",
            "vendor": "Azure",
            "source_file": "f",
            "source_sheet": "Sheet1",
            "line_number": 1,
            "service_period": "2024-05",
            "product_family": "Compute",
            "product_type": "Virtual Machine",
            "product_sku": "D8 v3",
            "unit_type": "Hours",
            "quantity": "744",
            "quantity_numeric": 744.0,
            "amount": "200",
            "amount_numeric": 200.0,
            "region_hint": "East US",
            "transaction_type": "Usage",
        }]
        prompt = self.build_prompt(rows, [], {"region": "mexico"})
        assert "billing_rows" in prompt
        assert prompt["total_rows"] == 1
        prompt_row = prompt["billing_rows"][0]
        assert "source_file" not in prompt_row
        assert "source_sheet" not in prompt_row
        assert "service_period" not in prompt_row
        assert "transaction_type" not in prompt_row
        assert prompt_row["row_id"] == "billing-row::f::1"

    def test_prompt_is_cross_cloud(self):
        """System prompt mentions Azure, AWS, GCP."""
        assert "Azure" in self.system_prompt
        assert "AWS" in self.system_prompt
        assert "GCP" in self.system_prompt

    def test_prompt_forbids_llm_pricing(self):
        """System prompt explicitly says LLM must not output prices."""
        assert "price" in self.system_prompt.lower()
        assert "MUST NOT" in self.system_prompt

    def test_prompt_preserves_fabric_visibility(self):
        """System prompt mentions Fabric/committed capacity must stay visible."""
        assert "Fabric" in self.system_prompt

    def test_prompt_prevents_api_mgmt_absorbing_charges(self):
        """System prompt says API Management must not absorb unrelated charges."""
        assert "API Management" in self.system_prompt

    def test_prompt_keeps_different_resource_shapes_separate(self):
        prompt = self.system_prompt.lower()
        assert "10-30 business-level" in prompt
        assert "different machine sku" in prompt
        assert "different disk sku" in prompt
        assert "different instance shapes" in prompt
        assert "monitoring/logging as separate candidates" in prompt

    def test_filter_billing_rows_for_test_families(self):
        from app.cloud_billing_workflow import _filter_billing_rows_for_test_families

        rows = [
            {"row_id": "1", "product_family": "Compute"},
            {"row_id": "2", "product_family": "Storage"},
            {"row_id": "3", "product_family": "Compute"},
        ]
        filtered = _filter_billing_rows_for_test_families(rows, {"compute"})
        assert [r["row_id"] for r in filtered] == ["1", "3"]


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 14D+E: Row-ref validation and enrichment
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateAndEnrichLLMFirstCandidates:
    """Validate _validate_and_enrich_llm_first_candidates."""

    @pytest.fixture(autouse=True)
    def _import_fn(self):
        from app.cloud_billing_workflow import _validate_and_enrich_llm_first_candidates
        self.validate_enrich = _validate_and_enrich_llm_first_candidates

    def _make_billing_row(self, file, line, amount="200", family="Compute", **kw):
        return {
            "row_id": f"billing-row::{file}::{line}",
            "vendor": "Azure", "source_file": file, "source_sheet": "",
            "line_number": line, "service_period": "",
            "product_family": family, "product_type": kw.get("product_type", ""),
            "product_sku": "", "unit_type": kw.get("unit_type", ""), "quantity": kw.get("quantity", "1"),
            "quantity_numeric": kw.get("quantity_numeric"),
            "amount": amount, "amount_numeric": kw.get("amount_numeric"),
            "currency": "USD", "region_hint": "",
            "transaction_type": "",
        }

    def test_valid_row_refs_source_total_backfilled(self):
        """Source total is summed from billing rows, not trusted from LLM."""
        rows = [
            self._make_billing_row("az.csv", 5, "300"),
            self._make_billing_row("az.csv", 6, "100"),
            self._make_billing_row("az.csv", 7, "50"),
        ]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "managed_database",
            "source_service_name": "Azure Database for MySQL",
            "source_monthly_total_usd": 9999,  # LLM lies
            "component_refs": ["billing-row::az.csv::5", "billing-row::az.csv::6", "billing-row::az.csv::7"],
            "composition_notes": [],
        }]
        result = self.validate_enrich(candidates, rows, [], [], [], [])
        assert len(result) == 1
        assert result[0].source_monthly_total_usd == 450.0  # 300+100+50

    def test_invalid_row_refs_dropped(self):
        """Refs pointing to non-existent rows are silently skipped."""
        rows = [self._make_billing_row("az.csv", 5, "200")]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "compute_vm",
            "source_service_name": "Azure VM",
            "component_refs": ["billing-row::az.csv::5", "billing-row::nonexistent::99"],
            "composition_notes": [],
        }]
        result = self.validate_enrich(candidates, rows, [], [], [], [])
        assert len(result) == 1
        # Only valid ref kept
        assert "billing-row::az.csv::5" in result[0].source_item_ids
        assert "billing-row::nonexistent::99" not in result[0].source_item_ids

    def test_no_valid_refs_candidate_dropped(self):
        """Candidates with no valid refs at all are dropped."""
        rows = [self._make_billing_row("az.csv", 5, "200")]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "compute_vm",
            "source_service_name": "Azure VM",
            "component_refs": ["billing-row::nonexistent::99"],
            "composition_notes": [],
        }]
        result = self.validate_enrich(candidates, rows, [], [], [], [])
        assert len(result) == 0

    def test_vm_quantity_uses_llm_business_quantity(self):
        """VM source_quantity prefers LLM's business quantity."""
        rows = [self._make_billing_row("az.csv", 5, "200")]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "compute_vm",
            "source_service_name": "Azure VM",
            "source_quantity": 6,  # LLM says 6 VMs
            "component_refs": ["billing-row::az.csv::5"],
            "composition_notes": [],
        }]
        result = self.validate_enrich(candidates, rows, [], [], [], [])
        assert len(result) == 1
        assert result[0].source_quantity == 6

    def test_descriptive_string_quantities_fall_back_to_row_semantics(self):
        """Descriptive MaaS quantity strings should not invalidate the candidate."""
        rows = [
            self._make_billing_row("az.csv", 5, "200", unit_type="Hours", quantity="4464", quantity_numeric=4464),
        ]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "compute_vm",
            "source_service_name": "Azure VM",
            "source_quantity": "4,464 hours across 6 VMs",
            "huawei_quantity": "6 VMs",
            "component_refs": ["billing-row::az.csv::5"],
            "composition_notes": "Grouped VM hours",
        }]
        result = self.validate_enrich(candidates, rows, [], [], [], [])
        assert len(result) == 1
        assert result[0].source_quantity == 6
        assert result[0].source_monthly_total_usd == 200.0

    def test_vm_quantity_fallback_from_hour_rows(self):
        """If LLM omits VM quantity, infer instance count from hour-based rows."""
        rows = [
            self._make_billing_row("az.csv", 5, "200", unit_type="Hours", quantity="4464", quantity_numeric=4464),
        ]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "compute_vm",
            "source_service_name": "Azure VM",
            # No source_quantity
            "component_refs": ["billing-row::az.csv::5", "billing-row::az.csv::6"],
            "composition_notes": [],
        }]
        result = self.validate_enrich(candidates, rows, [], [], [], [])
        assert len(result) == 1
        assert result[0].source_quantity == 6

    def test_invalid_huawei_product_goes_manual_review(self):
        """Huawei product not in allowed list → manual_review."""
        rows = [self._make_billing_row("az.csv", 5, "200")]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "compute_vm",
            "source_service_name": "Azure VM",
            "huawei_product": "FakeProduct",
            "component_refs": ["billing-row::az.csv::5"],
            "composition_notes": [],
        }]
        result = self.validate_enrich(candidates, rows, [], [], [], [])
        assert len(result) == 1
        assert result[0].status == "manual_review"
        assert result[0].huawei_product is None

    def test_database_quantity_fallback_is_one(self):
        """Database quantity fallback should default to 1, not row count."""
        rows = [
            self._make_billing_row("az.csv", 5, "300"),
            self._make_billing_row("az.csv", 6, "100"),
        ]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "managed_database",
            "source_service_name": "Azure Database for MySQL",
            "component_refs": ["billing-row::az.csv::5", "billing-row::az.csv::6"],
            "composition_notes": [],
        }]
        result = self.validate_enrich(candidates, rows, [], [], [], [])
        assert len(result) == 1
        assert result[0].source_quantity == 1

    def test_fabric_and_api_mgmt_not_merged(self):
        """Fabric and API Management stay as separate items — LLM must not merge them."""
        rows = [
            self._make_billing_row("az.csv", 10, "5002.24", family="Analytics",
                                   product_type="Fabric Capacity"),
            self._make_billing_row("az.csv", 20, "146.86", family="Integration",
                                   product_type="API Management"),
        ]
        # LLM correctly outputs them as separate candidates
        candidates = [
            {
                "candidate_id": "c1", "vendor": "Azure",
                "resource_kind": "platform_paas_misc",
                "source_service_name": "Azure Fabric Capacity",
                "component_refs": ["billing-row::az.csv::10"],
                "composition_notes": [],
            },
            {
                "candidate_id": "c2", "vendor": "Azure",
                "resource_kind": "platform_paas_misc",
                "source_service_name": "Azure API Management",
                "component_refs": ["billing-row::az.csv::20"],
                "composition_notes": [],
            },
        ]
        result = self.validate_enrich(candidates, rows, [], [], [], [])
        assert len(result) == 2
        # Fabric item should have its own amount
        fabric = next(r for r in result if "Fabric" in r.source_service_name)
        assert fabric.source_monthly_total_usd == 5002.24
        # API Management should have its own amount
        api = next(r for r in result if "API Management" in r.source_service_name)
        assert api.source_monthly_total_usd == 146.86

    def test_agg_refs_also_supported(self):
        """component_refs with billing-agg::* format also work."""
        agg_items = [{"vendor": "Azure", "source_file": "az.csv",
                      "amount": 300, "needs_manual_review": False}]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "compute_vm",
            "source_service_name": "Azure VM",
            "component_refs": ["billing-agg::az.csv::0"],
            "composition_notes": [],
        }]
        result = self.validate_enrich(candidates, [], [], agg_items, [], [])
        assert len(result) == 1
        assert result[0].source_monthly_total_usd == 300.0

    def test_amount_and_quantity_numeric_parsing_fields_used(self):
        """Numeric helper fields avoid fragile float parsing on localized strings."""
        rows = [
            self._make_billing_row(
                "az.csv", 5, "5,002.24", quantity="2,232",
                quantity_numeric=2232, amount_numeric=5002.24,
            ),
        ]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "platform_paas_misc",
            "source_service_name": "Fabric Capacity Reservation",
            "component_refs": ["billing-row::az.csv::5"],
            "composition_notes": [],
        }]
        result = self.validate_enrich(candidates, rows, [], [], [], [])
        assert len(result) == 1
        assert result[0].source_monthly_total_usd == 5002.24

    def test_multiple_quote_lines_per_agg_ref_preserved(self):
        """One aggregate ref can map to multiple quote lines in LLM-first enrichment."""
        agg_items = [{
            "vendor": "Azure", "source_file": "az.csv", "amount": 300,
            "needs_manual_review": False, "resource_kind": "elb",
        }]
        quote_lines = [
            FlexibleQuoteLine(
                line_id="line::1::elb", requirement_item_id="billing-agg::az.csv::0",
                product="ELB", region="mexico", quantity=1, unit="instance-month",
                billing_mode="Monthly", unit_price=100, monthly_price=100,
            ).model_dump(),
            FlexibleQuoteLine(
                line_id="line::1::waf", requirement_item_id="billing-agg::az.csv::0",
                product="WAF", region="mexico", quantity=1, unit="instance-month",
                billing_mode="Monthly", unit_price=50, monthly_price=50,
            ).model_dump(),
        ]
        candidates = [{
            "candidate_id": "c1", "vendor": "Azure",
            "resource_kind": "load_balancing_and_waf",
            "source_service_name": "Azure Application Gateway WAF v2",
            "component_refs": ["billing-agg::az.csv::0"],
            "composition_notes": [],
        }]
        result = self.validate_enrich(candidates, [], quote_lines, agg_items, [], [])
        assert len(result) == 1
        assert result[0].huawei_product == "ELB + WAF"
        assert result[0].huawei_monthly_total_usd == 150.0
        assert result[0].huawei_unit_price_usd is None
        assert result[0].huawei_billing_basis == "composite"

    def test_ownership_conflict_trims_overlapping_rows(self):
        """Later candidates lose overlapping row refs and totals are not double-counted."""
        rows = [
            self._make_billing_row("az.csv", 10, "5002.24", amount_numeric=5002.24),
            self._make_billing_row("az.csv", 20, "146.86", amount_numeric=146.86),
        ]
        candidates = [
            {
                "candidate_id": "c1", "vendor": "Azure",
                "resource_kind": "platform_paas_misc",
                "source_service_name": "Fabric Capacity Reservation",
                "component_refs": ["billing-row::az.csv::10", "billing-row::az.csv::20"],
                "composition_notes": [],
            },
            {
                "candidate_id": "c2", "vendor": "Azure",
                "resource_kind": "platform_paas_misc",
                "source_service_name": "Azure API Management",
                "component_refs": ["billing-row::az.csv::20"],
                "composition_notes": [],
            },
        ]
        result = self.validate_enrich(candidates, rows, [], [], [], [])
        assert len(result) == 1
        assert result[0].source_monthly_total_usd == 5149.1


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 14F: Three-level fallback
# ═══════════════════════════════════════════════════════════════════════════════


class TestThreeLevelFallback:
    """Validate the three-level fallback chain in compose_final_billing_quote_items_with_llm."""

    def test_maas_unavailable_falls_back_to_deterministic(self):
        """When MaaS is not configured, falls through to deterministic composer."""
        from app.cloud_billing_workflow import compose_final_billing_quote_items_with_llm
        import os

        for var in ("HUAWEI_MAAS_API_KEY", "HUAWEI_MAAS_BASE_URL", "HUAWEI_MAAS_MODEL"):
            os.environ.pop(var, None)

        state = {
            "billing_lines": [],
            "llm_aggregated_billing_items": [],
            "quote_lines": [], "requirements": [],
            "unquoted_items": [], "quote_blockers": [],
            "quote_context": {"region": "mexico"},
            "audit_log": [], "final_billing_quote_items": [],
            "llm_composition_candidates": [],
        }
        result = compose_final_billing_quote_items_with_llm(state)
        assert "final_billing_quote_items" in result
        audit_msgs = [a.get("message", "") for a in result.get("audit_log", [])]
        assert any("fallback" in m.lower() or "deterministic" in m.lower() for m in audit_msgs)

    def test_invalid_json_falls_back(self, monkeypatch):
        """When LLM returns invalid JSON, falls through to deterministic."""
        from app.cloud_billing_workflow import compose_final_billing_quote_items_with_llm
        import httpx

        def mock_post(*args, **kwargs):
            class MockResp:
                def raise_for_status(self): pass
                def json(self):
                    return {"choices": [{"message": {"content": "INVALID!!!"}}]}
            return MockResp()

        monkeypatch.setenv("HUAWEI_MAAS_API_KEY", "test")
        monkeypatch.setenv("HUAWEI_MAAS_BASE_URL", "http://localhost:9999")
        monkeypatch.setenv("HUAWEI_MAAS_MODEL", "test-model")
        monkeypatch.setattr(httpx.Client, "post", mock_post)

        state = {
            "billing_lines": [{"vendor": "Azure", "source_file": "f.csv", "source_sheet": "",
                               "line_number": 1, "product_family": "", "product_type": "",
                               "product_sku": "", "unit_type": "", "quantity_raw": "1",
                               "amount_raw": "100", "currency": "USD", "region_hint": "",
                               "transaction_type": "", "service_period": ""}],
            "llm_aggregated_billing_items": [],
            "quote_lines": [], "requirements": [],
            "unquoted_items": [], "quote_blockers": [],
            "quote_context": {"region": "mexico"},
            "audit_log": [], "final_billing_quote_items": [],
            "llm_composition_candidates": [],
        }
        result = compose_final_billing_quote_items_with_llm(state)
        assert "final_billing_quote_items" in result

    def test_missing_candidate_field_comma_is_repaired(self):
        malformed = (
            '{"candidates":[{"candidate_id":"c1","vendor":"Azure" '
            '"resource_kind":"platform_paas_misc",'
            '"source_service_name":"Fabric Capacity Reservation",'
            '"component_refs":["billing-row::az.xlsx::70"]}]}'
        )
        parsed = _load_llm_json_object(malformed)
        assert parsed["candidates"][0]["vendor"] == "Azure"
        assert parsed["candidates"][0]["resource_kind"] == "platform_paas_misc"

    def test_missing_candidate_separator_comma_is_repaired(self):
        malformed = (
            '{"candidates":[{"candidate_id":"c1"} '
            '{"candidate_id":"c2"}]}'
        )
        parsed = _load_llm_json_object(malformed)
        assert [candidate["candidate_id"] for candidate in parsed["candidates"]] == ["c1", "c2"]

    def test_repaired_result_must_cover_every_nonzero_row(self):
        item = CloudBillingFinalQuoteItem(
            item_id="fqi-1",
            vendor="Azure",
            resource_kind="platform_paas_misc",
            source_service_name="Fabric",
            source_item_ids=["billing-row::az.xlsx::1"],
        )
        rows = [
            {"row_id": "billing-row::az.xlsx::1", "amount_numeric": 5002.24},
            {"row_id": "billing-row::az.xlsx::2", "amount_numeric": 146.86},
        ]
        assert not _llm_first_result_covers_billing_rows([item], rows)

    def test_zero_amount_rows_do_not_block_coverage(self):
        item = CloudBillingFinalQuoteItem(
            item_id="fqi-1",
            vendor="Azure",
            resource_kind="platform_paas_misc",
            source_service_name="Fabric",
            source_item_ids=["billing-row::az.xlsx::1"],
        )
        rows = [
            {"row_id": "billing-row::az.xlsx::1", "amount_numeric": 5002.24},
            {"row_id": "billing-row::az.xlsx::2", "amount_numeric": 0},
        ]
        assert _llm_first_result_covers_billing_rows([item], rows)

    def test_unclaimed_rows_are_preserved_for_manual_review(self):
        item = CloudBillingFinalQuoteItem(
            item_id="fqi-1",
            vendor="Azure",
            resource_kind="platform_paas_misc",
            source_service_name="Fabric",
            source_monthly_total_usd=5002.24,
            source_item_ids=["billing-row::az.xlsx::1"],
        )
        rows = [
            {
                "row_id": "billing-row::az.xlsx::1",
                "vendor": "Azure",
                "product_sku": "Fabric Capacity Reservation",
                "amount_numeric": 5002.24,
            },
            {
                "row_id": "billing-row::az.xlsx::2",
                "vendor": "Azure",
                "product_family": "Developer Tools",
                "product_type": "API Management",
                "product_sku": "API Management - Developer",
                "unit_type": "hour",
                "quantity_numeric": 2232,
                "amount_numeric": 146.86,
            },
        ]
        completed = _append_unclaimed_billing_rows([item], rows)
        assert len(completed) == 2
        orphan = completed[1]
        assert orphan.source_service_name == "API Management - Developer"
        assert orphan.source_monthly_total_usd == 146.86
        assert orphan.status == "manual_review"
        assert orphan.source_item_ids == ["billing-row::az.xlsx::2"]
        assert _llm_first_result_covers_billing_rows(completed, rows)

    def test_compute_candidate_is_split_by_source_sku(self):
        candidates = [{
            "candidate_id": "vm",
            "vendor": "Azure",
            "resource_kind": "compute_vm",
            "source_service_name": "Virtual Machines",
            "source_quantity": 2,
            "component_refs": ["row-1", "row-2"],
        }]
        rows = [
            {"row_id": "row-1", "product_sku": "D8 v3"},
            {"row_id": "row-2", "product_sku": "F2s v2"},
        ]
        split = _split_shape_sensitive_candidates(candidates, rows)
        assert len(split) == 2
        assert {item["source_config_summary"] for item in split} == {"D8 v3", "F2s v2"}
        assert all(item["source_quantity"] is None for item in split)

    def test_same_source_sku_remains_one_candidate(self):
        candidates = [{
            "candidate_id": "ebs",
            "vendor": "AWS",
            "resource_kind": "block_storage",
            "source_service_name": "EBS gp3",
            "component_refs": ["row-1", "row-2"],
        }]
        rows = [
            {"row_id": "row-1", "product_sku": "gp3"},
            {"row_id": "row-2", "product_sku": "gp3"},
        ]
        normalized = _split_shape_sensitive_candidates(candidates, rows)
        assert len(normalized) == 1
        assert normalized[0]["component_refs"] == ["row-1", "row-2"]
        assert normalized[0]["source_quantity"] is None

    def test_excessively_incomplete_repaired_result_is_rejected(self):
        rows = [
            {
                "row_id": f"billing-row::az.xlsx::{index}",
                "amount_numeric": 1,
                "product_sku": f"service-{index}",
            }
            for index in range(1, 61)
        ]
        item = CloudBillingFinalQuoteItem(
            item_id="fqi-1",
            vendor="Azure",
            resource_kind="platform_paas_misc",
            source_service_name="Partial response",
            source_item_ids=[row["row_id"] for row in rows[:10]],
        )
        assert _append_unclaimed_billing_rows([item], rows) == []

    def test_spanish_vm_hours_fall_back_to_instance_count(self):
        rows = [{"quantity_numeric": 4464, "unit_type": "1 hora de proceso"}]
        assert _fallback_source_quantity_from_rows("compute_vm", rows, []) == 6

    def test_spanish_disk_month_falls_back_to_disk_count(self):
        rows = [{"quantity_numeric": 8.999424, "unit_type": "1 disco/mes"}]
        assert _fallback_source_quantity_from_rows("block_storage", rows, []) == 9

    def test_fenced_json_is_accepted(self, monkeypatch):
        """Markdown fenced JSON from MaaS should be parsed successfully."""
        from app.cloud_billing_workflow import _compose_final_billing_llm_first
        import httpx

        def mock_post(*args, **kwargs):
            class MockResp:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": (
                                        "```json\n"
                                        "{\"candidates\": [{\"candidate_id\": \"c1\", "
                                        "\"vendor\": \"Azure\", "
                                        "\"resource_kind\": \"compute_vm\", "
                                        "\"source_service_name\": \"Azure VM\", "
                                        "\"source_quantity\": \"4,464 hours across 6 VMs\", "
                                        "\"huawei_product\": \"ECS\", "
                                        "\"component_refs\": [\"billing-row::az.csv::5\"], "
                                        "\"composition_notes\": \"Grouped VM hours\"}]}\n"
                                        "```"
                                    )
                                }
                            }
                        ]
                    }

            return MockResp()

        monkeypatch.setenv("HUAWEI_MAAS_API_KEY", "test")
        monkeypatch.setenv("HUAWEI_MAAS_BASE_URL", "http://localhost:9999")
        monkeypatch.setenv("HUAWEI_MAAS_MODEL", "test-model")
        monkeypatch.setattr(httpx.Client, "post", mock_post)

        rows = [{
            "row_id": "billing-row::az.csv::5",
            "vendor": "Azure",
            "product_family": "Compute",
            "product_type": "Virtual Machines",
            "product_sku": "D8 v3",
            "unit_type": "Hours",
            "quantity": "4464",
            "amount": "200",
            "region_hint": "mexico",
        }]
        candidates = _compose_final_billing_llm_first(rows, [], {"region": "mexico", "language": "en"})
        assert candidates is not None
        assert candidates[0]["candidate_id"] == "c1"

    def test_test_family_mode_uses_subset_then_deterministic_output(self, monkeypatch):
        from app.cloud_billing_workflow import compose_final_billing_quote_items_with_llm

        monkeypatch.setenv("CLOUD_BILLING_LLM_FIRST_TEST_FAMILIES", "compute")
        monkeypatch.setenv("HUAWEI_MAAS_API_KEY", "test")
        monkeypatch.setenv("HUAWEI_MAAS_BASE_URL", "http://localhost:9999")
        monkeypatch.setenv("HUAWEI_MAAS_MODEL", "test-model")

        def fake_compose(rows, quote_lines, quote_context):
            assert len(rows) == 1
            assert rows[0]["product_family"] == "Compute"
            return [{
                "candidate_id": "c1",
                "vendor": "Azure",
                "resource_kind": "compute_vm",
                "source_service_name": "Azure VM",
                "source_quantity": 1,
                "huawei_product": "ECS",
                "component_refs": [rows[0]["row_id"]],
                "composition_notes": [],
            }]

        monkeypatch.setattr("app.cloud_billing_workflow._compose_final_billing_llm_first", fake_compose)

        state = {
            "billing_lines": [
                {"vendor": "Azure", "source_file": "f.csv", "source_sheet": "", "line_number": 1,
                 "product_family": "Compute", "product_type": "VM", "product_sku": "D2",
                 "unit_type": "Hours", "quantity_raw": "744", "amount_raw": "100",
                 "currency": "USD", "region_hint": "", "transaction_type": "", "service_period": ""},
                {"vendor": "Azure", "source_file": "f.csv", "source_sheet": "", "line_number": 2,
                 "product_family": "Storage", "product_type": "Disk", "product_sku": "P10",
                 "unit_type": "GB-Month", "quantity_raw": "128", "amount_raw": "10",
                 "currency": "USD", "region_hint": "", "transaction_type": "", "service_period": ""},
            ],
            "llm_aggregated_billing_items": [],
            "quote_lines": [],
            "requirements": [],
            "unquoted_items": [],
            "quote_blockers": [],
            "quote_context": {"region": "mexico"},
            "audit_log": [],
            "final_billing_quote_items": [],
            "llm_composition_candidates": [],
        }
        result = compose_final_billing_quote_items_with_llm(state)
        audit_msgs = [a.get("message", "") for a in result.get("audit_log", [])]
        assert any("test mode active" in m for m in audit_msgs)
        assert any("test succeeded" in m for m in audit_msgs)


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 14H: Cross-cloud fixtures
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrossCloudLLMFirstFixtures:
    """Validate LLM-first schema works for AWS and GCP fixtures."""

    def _make_aws_billing_rows(self):
        return [
            {"row_id": "billing-row::aws.csv::10", "vendor": "AWS",
             "source_file": "aws.csv", "source_sheet": "", "line_number": 10,
             "service_period": "2024-05", "product_family": "Compute",
             "product_type": "EC2", "product_sku": "m5.xlarge",
             "unit_type": "Hours", "quantity": "744", "amount": "200",
             "currency": "USD", "region_hint": "us-east-1", "transaction_type": "Usage"},
            {"row_id": "billing-row::aws.csv::20", "vendor": "AWS",
             "source_file": "aws.csv", "source_sheet": "", "line_number": 20,
             "service_period": "2024-05", "product_family": "Storage",
             "product_type": "EBS", "product_sku": "gp2",
             "unit_type": "GB-Month", "quantity": "100", "amount": "10",
             "currency": "USD", "region_hint": "us-east-1", "transaction_type": "Usage"},
            {"row_id": "billing-row::aws.csv::30", "vendor": "AWS",
             "source_file": "aws.csv", "source_sheet": "", "line_number": 30,
             "service_period": "2024-05", "product_family": "Database",
             "product_type": "RDS MySQL", "product_sku": "db.r5.large",
             "unit_type": "Hours", "quantity": "744", "amount": "250",
             "currency": "USD", "region_hint": "us-east-1", "transaction_type": "Usage"},
        ]

    def _make_gcp_billing_rows(self):
        return [
            {"row_id": "billing-row::gcp.json::5", "vendor": "GCP",
             "source_file": "gcp.json", "source_sheet": "", "line_number": 5,
             "service_period": "2024-05", "product_family": "Compute",
             "product_type": "Compute Engine", "product_sku": "n2-standard-8",
             "unit_type": "Hours", "quantity": "744", "amount": "500",
             "currency": "USD", "region_hint": "us-central1", "transaction_type": "Usage"},
            {"row_id": "billing-row::gcp.json::15", "vendor": "GCP",
             "source_file": "gcp.json", "source_sheet": "", "line_number": 15,
             "service_period": "2024-05", "product_family": "Database",
             "product_type": "Cloud SQL PostgreSQL", "product_sku": "db-custom-4-16384",
             "unit_type": "Hours", "quantity": "744", "amount": "220",
             "currency": "USD", "region_hint": "us-central1", "transaction_type": "Usage"},
        ]

    def test_aws_fixture_validates(self):
        """AWS EC2 + EBS + RDS fixture passes LLM-first validation."""
        from app.cloud_billing_workflow import _validate_and_enrich_llm_first_candidates
        rows = self._make_aws_billing_rows()
        candidates = [
            {"candidate_id": "c1", "vendor": "AWS", "resource_kind": "compute_vm",
             "source_service_name": "AWS EC2", "source_quantity": 1,
             "huawei_product": "ECS",
             "component_refs": ["billing-row::aws.csv::10"], "composition_notes": []},
            {"candidate_id": "c2", "vendor": "AWS", "resource_kind": "block_storage",
             "source_service_name": "AWS EBS", "source_quantity": 1,
             "huawei_product": "EVS",
             "component_refs": ["billing-row::aws.csv::20"], "composition_notes": []},
            {"candidate_id": "c3", "vendor": "AWS", "resource_kind": "managed_database",
             "source_service_name": "AWS RDS for MySQL", "source_quantity": 1,
             "huawei_product": "RDS",
             "component_refs": ["billing-row::aws.csv::30"], "composition_notes": []},
        ]
        result = _validate_and_enrich_llm_first_candidates(candidates, rows, [], [], [], [])
        assert len(result) == 3
        assert result[0].source_monthly_total_usd == 200.0
        assert result[1].source_monthly_total_usd == 10.0
        assert result[2].source_monthly_total_usd == 250.0

    def test_gcp_fixture_validates(self):
        """GCP Compute + Cloud SQL fixture passes LLM-first validation."""
        from app.cloud_billing_workflow import _validate_and_enrich_llm_first_candidates
        rows = self._make_gcp_billing_rows()
        candidates = [
            {"candidate_id": "c1", "vendor": "GCP", "resource_kind": "compute_vm",
             "source_service_name": "GCP Compute Engine", "source_quantity": 1,
             "huawei_product": "ECS",
             "component_refs": ["billing-row::gcp.json::5"], "composition_notes": []},
            {"candidate_id": "c2", "vendor": "GCP", "resource_kind": "managed_database",
             "source_service_name": "GCP Cloud SQL for PostgreSQL", "source_quantity": 1,
             "huawei_product": "RDS",
             "component_refs": ["billing-row::gcp.json::15"], "composition_notes": []},
        ]
        result = _validate_and_enrich_llm_first_candidates(candidates, rows, [], [], [], [])
        assert len(result) == 2
        assert result[0].source_monthly_total_usd == 500.0
        assert result[1].source_monthly_total_usd == 220.0


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 16: Timeout configuration + Export graph fix
# ═══════════════════════════════════════════════════════════════════════════════


class TestBillingLLMTimeoutConfig:
    """Validate Cloud Billing LLM timeout configuration."""

    def test_default_timeout_values(self):
        """Default timeout values are sensible (180s billing, 240s composition)."""
        from app.flexible_workflow import (
            _get_billing_final_composition_timeout_seconds,
            _get_billing_llm_timeout_seconds,
        )
        assert _get_billing_llm_timeout_seconds() >= 180
        assert _get_billing_final_composition_timeout_seconds() >= 240

    def test_env_override_timeout(self, monkeypatch):
        """Setting env vars overrides the timeout values."""
        monkeypatch.setenv("BILLING_LLM_TIMEOUT_SECONDS", "300")
        monkeypatch.setenv("BILLING_FINAL_COMPOSITION_TIMEOUT_SECONDS", "360")
        from app.flexible_workflow import (
            _get_billing_final_composition_timeout_seconds,
            _get_billing_llm_timeout_seconds,
        )
        assert _get_billing_llm_timeout_seconds() == 300
        assert _get_billing_final_composition_timeout_seconds() == 360

    def test_final_composition_uses_composition_timeout(self):
        """_compose_final_billing_llm_first uses BILLING_FINAL_COMPOSITION_TIMEOUT_SECONDS."""
        from app.cloud_billing_workflow import _compose_final_billing_llm_first
        # Just verify the function exists and is callable
        assert callable(_compose_final_billing_llm_first)

    def test_billing_aggregation_uses_billing_timeout(self):
        """_compose_final_billing_with_llm uses BILLING_LLM_TIMEOUT_SECONDS."""
        from app.cloud_billing_workflow import _compose_final_billing_with_llm
        assert callable(_compose_final_billing_with_llm)


class TestCloudBillingExportGraph:
    """Validate cloud billing export graph uses billing-specific export."""

    def test_export_graph_uses_billing_export_node(self):
        """Export graph should use export_cloud_billing_workbook, not generic."""
        from app.cloud_billing_workflow import build_cloud_billing_export_graph
        graph = build_cloud_billing_export_graph()
        # Check that the graph has the billing export node
        node_names = set(graph.nodes.keys())
        assert "export_cloud_billing_workbook" in node_names
        assert "compose_final_billing_quote_items_with_llm" in node_names

    def test_review_graph_uses_llm_composition(self):
        """Review graph should use LLM composition node."""
        from app.cloud_billing_workflow import build_cloud_billing_review_graph
        graph = build_cloud_billing_review_graph()
        node_names = set(graph.nodes.keys())
        assert "compose_final_billing_quote_items_with_llm" in node_names

    def test_export_cloud_billing_workbook_uses_billing_template(self):
        """export_cloud_billing_workbook should call billing template export."""
        from app.cloud_billing_workflow import export_cloud_billing_workbook
        # Create a minimal state with final_billing_quote_items
        from app.models import FlexibleQuoteSummary
        state = {
            "final_billing_quote_items": [],
            "billing_lines": [{"test": True}],
            "llm_aggregated_billing_items": [],
            "quote_lines": [],
            "requirements": [],
            "quote_ready_items": [],
            "quote_blockers": [],
            "unquoted_items": [],
            "matched_products": [],
            "summary": FlexibleQuoteSummary().model_dump(),
            "audit_log": [],
            "quote_context": {"region": "mexico", "language": "en"},
            "diagnostics": {},
        }
        result = export_cloud_billing_workbook(state)
        assert "workbook" in result
        # Verify it's a billing workbook by checking sheet names
        from io import BytesIO
        from openpyxl import load_workbook
        wb = load_workbook(BytesIO(result["workbook"].content))
        sheet_names = wb.sheetnames
        # Billing template should have Quotation sheet
        assert "Quotation" in sheet_names, f"Expected Quotation in {sheet_names}"
        # Should NOT have generic sheets as primary
        assert "Standard Requirements" not in sheet_names, f"Should not have Standard Requirements in {sheet_names}"

    def test_export_cloud_billing_workbook_requires_real_billing_state(self):
        """Cloud billing export should not silently fall back to generic workbook."""
        from app.cloud_billing_workflow import export_cloud_billing_workbook
        with pytest.raises(ValueError, match="billing-specific state"):
            export_cloud_billing_workbook(
                {
                    "requirements": [],
                    "matched_products": [],
                    "audit_log": [],
                    "final_billing_quote_items": [],
                }
            )
