"""Cloud Billing Quote workflow.

Orchestrates the cloud billing quote pipeline: ingest billing exports (Azure/AWS/GCP),
aggregate billing lines, map to Huawei Cloud products, price, compose final quotation
items, and summarize.

This module owns the graph orchestration. Shared node implementations are imported
from flexible_workflow.py to avoid duplication during the transition period.

Phase 5A: Cloud Billing graph skips understand_input — billing extraction
(_extract_billing_requirement_items) does not depend on state["understanding"].
The pipeline goes directly from parse_documents → extract_requirement_items.

Phase 8B: Added compose_final_billing_quote_items between quote_items and
summarize_quote. This node merges internal quote_lines into customer-readable
CloudBillingFinalQuoteItem entries using unified cross-cloud composition rules.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.flexible_workflow import (
    FlexibleQuoteState,
    ingest_files,
    load_pricebook,
    parse_documents,
    extract_requirement_items,
    normalize_requirements,
    deduplicate_items,
    map_to_huawei_product,
    validate_quote_readiness,
    return_blockers,
    resolve_price_components,
    quote_items,
    summarize_quote,
    incorporate_feedback,
    export_flexible_workbook,
    _route_after_validation,
    build_flexible_preview_response,
    build_flexible_review_state,
    _get_billing_final_composition_timeout_seconds,
    _get_billing_llm_timeout_seconds,
    _to_float,
)
from app.models import (
    CloudBillingFinalCompositionCandidate,
    CloudBillingFinalQuoteItem,
    CloudBillingResourceKind,
    FinalQuoteItemStatus,
    FlexibleQuoteLine,
    RequirementItem,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Unified resource-kind classification (Phase 8C)
# ---------------------------------------------------------------------------

# Mapping from internal resource_kind (used in llm_aggregated_billing_items)
# to the final CloudBillingResourceKind categories.
_RESOURCE_KIND_TO_FINAL: dict[str, CloudBillingResourceKind] = {
    "ecs": "compute_vm",
    "vm": "compute_vm",
    "evs": "block_storage",
    "disk": "block_storage",
    "rds": "managed_database",
    "dds": "managed_database",
    "database": "managed_database",
    "obs": "object_storage",
    "object_storage": "object_storage",
    "sfs_turbo": "shared_file_storage",
    "file_storage": "shared_file_storage",
    "elb": "load_balancing_and_waf",
    "load_balancer": "load_balancing_and_waf",
    "waf": "load_balancing_and_waf",
    "vpn": "vpn_connectivity",
    "vpn_gateway": "vpn_connectivity",
    "eip": "public_ip_or_bandwidth",
    "public_ip": "public_ip_or_bandwidth",
    "cbr": "backup_security_ops",
    "backup": "backup_security_ops",
    "hss": "backup_security_ops",
    "security": "backup_security_ops",
}

# Huawei product → final resource kind (for items that come through
# the quote_lines path rather than llm_aggregated_billing_items).
_HUAWEI_PRODUCT_TO_FINAL: dict[str, CloudBillingResourceKind] = {
    "ECS": "compute_vm",
    "EVS": "block_storage",
    "RDS": "managed_database",
    "DDS": "managed_database",
    "DWS": "managed_database",
    "GaussDB": "managed_database",
    "GeminiDB": "managed_database",
    "OBS": "object_storage",
    "SFS Turbo": "shared_file_storage",
    "ELB": "load_balancing_and_waf",
    "WAF": "load_balancing_and_waf",
    "VPN": "vpn_connectivity",
    "EIP": "public_ip_or_bandwidth",
    "CBR": "backup_security_ops",
    "HSS": "backup_security_ops",
    "CCE": "platform_paas_misc",
    "CCI": "platform_paas_misc",
    "NAT Gateway": "public_ip_or_bandwidth",
    "Direct Connect as a Service": "vpn_connectivity",
    "VPC": "platform_paas_misc",
    "Workspace": "compute_vm",
    "DRS": "platform_paas_misc",
    "CSS": "managed_database",
    "LTS": "platform_paas_misc",
    "DLI": "platform_paas_misc",
    "DCS": "platform_paas_misc",
    "DMS": "platform_paas_misc",
    "DataArts Studio": "platform_paas_misc",
    "Cloud Connect": "vpn_connectivity",
    "DEW": "platform_paas_misc",
    "Anti-DDoS": "platform_paas_misc",
    "CFW": "platform_paas_misc",
    "CES": "platform_paas_misc",
    "ModelArts": "platform_paas_misc",
    "FunctionGraph": "platform_paas_misc",
}

# Vendor name normalization for the three supported clouds
_VENDOR_ALIASES: dict[str, str] = {
    "azure": "Azure",
    "microsoft": "Azure",
    "microsoft azure": "Azure",
    "aws": "AWS",
    "amazon": "AWS",
    "amazon web services": "AWS",
    "gcp": "GCP",
    "google": "GCP",
    "google cloud": "GCP",
    "google cloud platform": "GCP",
}


def _classify_resource_kind(
    resource_kind: str | None,
    huawei_product: str | None,
) -> CloudBillingResourceKind:
    """Classify a billing item into a unified resource kind.

    Tries resource_kind first (from llm_aggregated_billing_items),
    then huawei_product (from quote_lines), else platform_paas_misc.
    """
    if resource_kind:
        mapped = _RESOURCE_KIND_TO_FINAL.get(resource_kind)
        if mapped:
            return mapped
    if huawei_product:
        mapped = _HUAWEI_PRODUCT_TO_FINAL.get(huawei_product)
        if mapped:
            return mapped
    return "platform_paas_misc"


def _normalize_vendor(vendor: str | None) -> str:
    """Normalize vendor name to canonical form (Azure/AWS/GCP)."""
    if not vendor:
        return "Unknown"
    key = vendor.strip().lower()
    return _VENDOR_ALIASES.get(key, vendor.strip().title())


# ---------------------------------------------------------------------------
# Display helpers (Phase 9A)
# ---------------------------------------------------------------------------

# Average hours in a billing month (30.4375 days × 24 hours)
_HOURS_PER_MONTH = 744.0


def _final_display_quantity(
    resource_kind: CloudBillingResourceKind,
    items: list[dict[str, Any]],
    total_source_qty: float,
) -> float:
    """Compute a customer-readable display quantity for the Quotation main table.

    This does NOT affect pricing math — it only determines what appears in
    the source_quantity / huawei_quantity fields of the final quotation item.

    Rules:
    - compute_vm: convert instance-hours to instance count (÷744, round to int)
    - block_storage: use item count (disk count), never disk-month ratios
    - managed_database: instance count (default 1)
    - shared_file_storage / object_storage: 1 (capacity goes in config_summary)
    - vpn / elb / eip / backup / hss: resource count or 1
    - platform_paas_misc: item count
    """
    item_count = len(items)

    if resource_kind == "compute_vm":
        normalized_counts = [
            float(item.get("source_quantity", 0) or 0)
            for item in items
            if (item.get("source_quantity") or 0) > 0
        ]
        units = {
            (item.get("source_pricing_basis") or item.get("source_unit") or "").lower()
            for item in items
        }
        monthlyish = any("month" in unit for unit in units if unit)
        hourlyish = any("hour" in unit for unit in units if unit)

        # Billing aggregates commonly normalize VM source_quantity to business
        # instance counts even if the semantic label still says "instance hours".
        # If the observed quantities are already small counts, do not divide by
        # hours again.
        if normalized_counts:
            max_count = max(normalized_counts)
            if total_source_qty > 0 and total_source_qty <= 50 and max_count <= 50:
                rounded = round(total_source_qty)
                if abs(total_source_qty - rounded) < 0.3 and rounded > 0:
                    return float(rounded)
                return round(total_source_qty, 1)

        # Monthly-style compute quantities are already instance counts.
        if monthlyish and not hourlyish and total_source_qty < (_HOURS_PER_MONTH * 0.75):
            if total_source_qty > 0:
                rounded = round(total_source_qty)
                if abs(total_source_qty - rounded) < 0.3:
                    return float(rounded)
                return round(total_source_qty, 1)
            return float(item_count)

        # If total_source_qty looks like instance-hours (>> item_count),
        # convert to instance count.
        if hourlyish or total_source_qty > item_count * 2:
            # Likely hours — convert to instances
            instances = total_source_qty / _HOURS_PER_MONTH
            rounded = round(instances)
            # If close to an integer (within 0.3), use the integer
            if abs(instances - rounded) < 0.3 and rounded > 0:
                return float(rounded)
            return round(instances, 1)
        # Already instance count
        if total_source_qty > 0:
            rounded = round(total_source_qty)
            if abs(total_source_qty - rounded) < 0.3:
                return float(rounded)
            return round(total_source_qty, 1)
        return float(item_count)

    if resource_kind == "block_storage":
        # Never show disk-month ratios; use disk count
        if total_source_qty > 0 and total_source_qty < item_count * 2:
            # Small numbers — likely disk count already
            rounded = round(total_source_qty)
            if abs(total_source_qty - rounded) < 0.3 and rounded > 0:
                return float(rounded)
        return float(item_count)

    if resource_kind == "managed_database":
        # Default to 1 instance; don't put storage GiB or IO count in quantity
        return 1.0

    if resource_kind in ("shared_file_storage", "object_storage"):
        # Capacity goes in config_summary; quantity is 1
        return 1.0

    if resource_kind in ("vpn_connectivity", "load_balancing_and_waf",
                         "public_ip_or_bandwidth", "backup_security_ops"):
        # Try to infer resource count; fall back to 1
        if total_source_qty > 0 and total_source_qty < 100:
            rounded = round(total_source_qty)
            if abs(total_source_qty - rounded) < 0.3 and rounded > 0:
                return float(rounded)
        return float(item_count) if item_count <= 10 else 1.0

    # platform_paas_misc and default
    return float(item_count)


def _display_billing_basis_for_quotation(basis: str | None) -> str | None:
    """Map internal billing semantics to customer-readable quotation labels."""
    if not basis:
        return basis
    key = basis.strip().lower()
    mapping = {
        "instance hours": "Monthly usage",
        "instance-hour": "Monthly usage",
        "instance-month": "Monthly usage",
        "capacity gib month": "Monthly capacity",
        "gb-month": "Monthly capacity",
        "disk-month": "Monthly capacity",
        "vcore-month": "Monthly capacity",
        "ops 10k": "Operations-based",
        "requests": "Request-based",
        "request": "Request-based",
        "traffic": "Traffic-based",
        "bandwidth": "Traffic-based",
        "unknown": "Monthly usage",
    }
    return mapping.get(key, basis)


def _normalize_final_quote_item_for_export(item: CloudBillingFinalQuoteItem) -> CloudBillingFinalQuoteItem:
    """Apply final sanity and display normalization before export/summary."""
    updates: dict[str, Any] = {
        "source_pricing_basis": _display_billing_basis_for_quotation(item.source_pricing_basis),
    }

    if item.huawei_product and "+" in item.huawei_product:
        updates["huawei_unit_price_usd"] = None
        updates["huawei_billing_basis"] = "composite"
        updates["huawei_quantity"] = None

    if item.resource_kind == "compute_vm" and item.status in ("quoted", "partial"):
        huawei_qty = item.huawei_quantity
        if (huawei_qty is None or huawei_qty <= 0) and item.huawei_monthly_total_usd and item.huawei_unit_price_usd:
            inferred = item.huawei_monthly_total_usd / item.huawei_unit_price_usd
            rounded = round(inferred)
            huawei_qty = float(rounded) if abs(inferred - rounded) < 0.3 and rounded > 0 else round(inferred, 1)
            updates["huawei_quantity"] = huawei_qty
        if (item.source_quantity is None or item.source_quantity <= 0) and huawei_qty and huawei_qty > 0:
            updates["source_quantity"] = huawei_qty

    return item.model_copy(update=updates)


# Customer-readable service name mapping by (resource_kind, vendor)
_DISPLAY_SERVICE_NAMES: dict[tuple[str, str], str] = {
    ("compute_vm", "Azure"): "Azure VM",
    ("compute_vm", "AWS"): "AWS EC2",
    ("compute_vm", "GCP"): "GCP Compute Engine",
    ("block_storage", "Azure"): "Azure Managed Disk",
    ("block_storage", "AWS"): "AWS EBS",
    ("block_storage", "GCP"): "GCP Persistent Disk",
    ("managed_database", "Azure"): "Azure Database",  # engine appended dynamically
    ("managed_database", "AWS"): "AWS RDS",
    ("managed_database", "GCP"): "GCP Cloud SQL",
    ("shared_file_storage", "Azure"): "Azure Files",
    ("shared_file_storage", "AWS"): "AWS EFS",
    ("shared_file_storage", "GCP"): "GCP Filestore",
    ("object_storage", "Azure"): "Azure Blob Storage",
    ("object_storage", "AWS"): "AWS S3",
    ("object_storage", "GCP"): "GCP Cloud Storage",
    ("vpn_connectivity", "Azure"): "Azure VPN Gateway",
    ("vpn_connectivity", "AWS"): "AWS Site-to-Site VPN",
    ("vpn_connectivity", "GCP"): "GCP Cloud VPN",
    ("load_balancing_and_waf", "Azure"): "Azure Application Gateway",
    ("load_balancing_and_waf", "AWS"): "AWS Load Balancer",
    ("load_balancing_and_waf", "GCP"): "GCP Load Balancer",
    ("public_ip_or_bandwidth", "Azure"): "Azure Public IP",
    ("public_ip_or_bandwidth", "AWS"): "AWS Elastic IP",
    ("public_ip_or_bandwidth", "GCP"): "GCP External IP",
    ("backup_security_ops", "Azure"): "Azure Backup & Security",
    ("backup_security_ops", "AWS"): "AWS Backup & Security",
    ("backup_security_ops", "GCP"): "GCP Backup & Security",
}


def _database_service_display_name(vendor: str, items: list[dict[str, Any]]) -> str:
    """Pick the service-level database name, not a sub-item (storage/compute/IO) name.

    Rules:
    1. Look for the most "service-level" name among all sub-items.
    2. Strip sub-component suffixes (Storage, Compute, Paid IO, Almacenamiento).
    3. If the cleaned name is just an engine (e.g. "MySQL"), use the mapped base + engine.
    4. If a mapped base name exists, append engine from source_service_family.
    """
    # Sub-component suffixes to strip from service names
    _SUB_SUFFIXES = (
        " Storage", " Compute", " Paid IO", " I/O",
        " Almacenamiento", " - Almacenamiento",
    )

    # Service-level keywords that indicate a proper DB service name (not a sub-item)
    _SERVICE_KEYWORDS = (
        "flexible server", "database for", "rds", "cloud sql",
        "aurora", "managed database",
    )

    # Pure engine names (without vendor/service prefix) — these are not service-level names
    _PURE_ENGINE_NAMES = (
        "mysql", "postgresql", "postgres", "sql server", "mariadb",
        "oracle", "redis", "mongo", "cassandra",
    )

    # Step 1: try to find the most "service-level" name among items
    best_name = ""
    for item in items:
        sn = item.get("source_service_name", "") or ""
        # Strip internal prefixes like "RDS |"
        if " | " in sn:
            sn = sn.split(" | ")[-1]
        sn_lower = sn.lower()
        # Check if this name looks like a service-level name
        is_service_level = any(kw in sn_lower for kw in _SERVICE_KEYWORDS)
        # Also check: does it NOT end with a sub-component suffix?
        is_not_sub_item = not any(sn_lower.rstrip().endswith(suf.lower()) for suf in _SUB_SUFFIXES)
        if is_service_level and is_not_sub_item:
            best_name = sn
            break
        # If we haven't found anything yet, keep the first cleaned name
        if not best_name:
            # Strip sub-component suffixes
            cleaned = sn
            for suf in _SUB_SUFFIXES:
                if cleaned.lower().endswith(suf.lower()):
                    cleaned = cleaned[: -len(suf)].rstrip(" -")
            best_name = cleaned

    # Step 2: if best_name is just a bare engine name, use the mapped base + engine instead
    mapped = _DISPLAY_SERVICE_NAMES.get(("managed_database", vendor), "Database")
    family = items[0].get("source_service_family", "") if items else ""

    if best_name and best_name.lower().strip() in _PURE_ENGINE_NAMES:
        # "MySQL" alone → "Azure Database for MySQL"
        if family and family.lower() not in mapped.lower():
            return f"{mapped} for {family}"
        return mapped

    # Step 3: if still no good name, use the mapped base + engine
    if not best_name:
        if family and family.lower() not in mapped.lower():
            return f"{mapped} for {family}"
        return mapped

    # Step 4: ensure engine is present in the name
    if family and family.lower() not in best_name.lower():
        # Append engine if not already in the name
        best_name = f"{best_name} for {family}"

    return best_name


def _final_display_service_name(
    resource_kind: CloudBillingResourceKind,
    vendor: str,
    items: list[dict[str, Any]],
) -> str:
    """Compute a customer-readable service name for the Quotation main table.

    Falls back to the first item's source_service_name if no mapping exists.
    For managed_database, uses _database_service_display_name for service-level name.
    For platform_paas_misc, uses the first representative service name.
    """
    key = (resource_kind, vendor)
    mapped = _DISPLAY_SERVICE_NAMES.get(key)
    if mapped:
        # For databases, use the dedicated helper for service-level naming
        if resource_kind == "managed_database":
            return _database_service_display_name(vendor, items)
        return mapped

    # Fallback for platform_paas_misc: use first service name, strip "unsupported |" prefix
    if resource_kind == "platform_paas_misc" and items:
        name = items[0].get("source_service_name", "")
        # Strip internal prefixes like "unsupported |", "ECS |", etc.
        if " | " in name:
            name = name.split(" | ")[-1]
        return name if name else "Platform / PaaS Services"

    # Fallback: use first item's name, strip internal prefix
    if items:
        name = items[0].get("source_service_name", "")
        if " | " in name:
            name = name.split(" | ")[-1]
        return name if name else resource_kind

    return resource_kind


def _database_config_summary(items: list[dict[str, Any]]) -> str | None:
    """Compose a customer-readable database config summary from sub-items.

    Target format: "Memory Optimized, 4 vCore / 32 GiB + 2296 GB storage + paid IO"
    Extracts compute (vCore, memory, instance class), storage (capacity), and IO parts.
    """
    import re

    compute_parts: list[str] = []
    storage_gib: float | None = None
    has_paid_io = False

    for item in items:
        sn = (item.get("source_service_name", "") or "").lower()
        sc = item.get("source_config_summary", "") or ""
        sc_lower = sc.lower()

        # Detect sub-component type
        is_compute = "compute" in sn
        is_storage = "storage" in sn or "almacenamiento" in sn
        is_io = "io" in sn or "i/o" in sn

        if is_io:
            has_paid_io = True
            continue

        if is_compute:
            # Extract instance class/family (e.g. "Memory Optimized", "Burstable B1MS")
            for tier in ("Memory Optimized", "General Purpose", "Burstable",
                         "Business Critical", "Hyperscale", "Critical"):
                if tier.lower() in sc_lower:
                    compute_parts.append(tier)
                    break

            # Extract vCore / vCPU
            vcore_match = re.search(r"(\d+)\s*v[ -]?core", sc_lower)
            if not vcore_match:
                vcore_match = re.search(r"(\d+)\s*vcpu", sc_lower)
            vcore = int(vcore_match.group(1)) if vcore_match else None

            # Extract memory
            mem_match = re.search(r"(\d+(?:\.\d+)?)\s*gib", sc_lower)
            if not mem_match:
                mem_match = re.search(r"(\d+(?:\.\d+)?)\s*gb", sc_lower)
            mem = float(mem_match.group(1)) if mem_match else None

            # Build compute string
            if vcore and mem:
                compute_parts.append(f"{vcore} vCore / {int(mem) if mem == int(mem) else mem} GiB")
            elif vcore:
                compute_parts.append(f"{vcore} vCore")
            elif mem:
                compute_parts.append(f"{int(mem) if mem == int(mem) else mem} GiB")

            # If nothing extracted from config, try huawei_spec_summary
            if not compute_parts:
                hspec = item.get("huawei_spec_summary", "") or ""
                if hspec:
                    compute_parts.append(hspec)

        elif is_storage:
            # Extract storage capacity
            cap_match = re.search(r"(\d+(?:\.\d+)?)\s*gb", sc_lower)
            if cap_match:
                storage_gib = float(cap_match.group(1))
            else:
                cap_match = re.search(r"(\d+(?:\.\d+)?)\s*tb", sc_lower)
                if cap_match:
                    storage_gib = float(cap_match.group(1)) * 1024

    # Compose the summary
    result_parts: list[str] = []

    # Compute section
    if compute_parts:
        result_parts.append(", ".join(compute_parts))

    # Storage section
    if storage_gib is not None:
        if storage_gib >= 1024:
            tb = storage_gib / 1024
            result_parts.append(f"{int(storage_gib)} GB storage" if storage_gib == int(storage_gib) else f"{storage_gib:.0f} GB storage")
        else:
            result_parts.append(f"{int(storage_gib)} GB storage" if storage_gib == int(storage_gib) else f"{storage_gib:.1f} GB storage")

    # IO section
    if has_paid_io:
        result_parts.append("paid IO")

    if not result_parts:
        return None

    # Join: compute + storage + IO
    # e.g. "Memory Optimized, 4 vCore / 32 GiB + 2296 GB storage + paid IO"
    if len(result_parts) == 1:
        return result_parts[0]
    # First part is compute (may contain ", "), rest joined with " + "
    return result_parts[0] + " + " + " + ".join(result_parts[1:])


def _final_display_config_summary(
    resource_kind: CloudBillingResourceKind,
    items: list[dict[str, Any]],
    first_config: str | None,
) -> str | None:
    """Compute a customer-readable config summary.

    Moves spec info out of service name and into config column.
    For databases, uses _database_config_summary for structured compute+storage+IO.
    """
    if resource_kind == "managed_database":
        db_summary = _database_config_summary(items)
        if db_summary:
            return db_summary
        # Fallback: join individual config summaries if structured extraction fails
        if len(items) > 1:
            parts = []
            for item in items:
                sc = item.get("source_config_summary", "")
                if sc:
                    parts.append(sc)
            if parts:
                return "; ".join(parts)

    if resource_kind == "platform_paas_misc":
        # No meaningful config summary for platform items
        return None

    # For VMs, disks, etc: use the first item's config summary
    # but clean up internal prefixes
    if first_config:
        # Strip "ECS |", "EVS |", etc.
        if " | " in first_config:
            return first_config.split(" | ")[-1]
        return first_config

    return None


# ---------------------------------------------------------------------------
# Composition key builders (Phase 8D)
# ---------------------------------------------------------------------------

def _composition_key_compute_vm(item: dict[str, Any]) -> tuple:
    """Build composition key for compute VMs: same vendor + spec + OS."""
    vendor = item.get("vendor", "")
    spec = item.get("source_config_summary", "") or item.get("huawei_spec_summary", "")
    huawei_product = item.get("huawei_product", "")
    return ("compute_vm", vendor, huawei_product, spec)


def _composition_key_block_storage(item: dict[str, Any]) -> tuple:
    """Build composition key for block storage: vendor + tier + capacity class."""
    vendor = item.get("vendor", "")
    huawei_product = item.get("huawei_product", "")
    tier = item.get("source_pricing_basis", "") or ""
    # Use spec summary as capacity/performance class
    spec = item.get("source_config_summary", "") or item.get("huawei_spec_summary", "")
    return ("block_storage", vendor, huawei_product, tier, spec)


def _composition_key_shared_file_storage(item: dict[str, Any]) -> tuple:
    """Build composition key for file storage: vendor + tier."""
    vendor = item.get("vendor", "")
    huawei_product = item.get("huawei_product", "")
    tier = item.get("source_pricing_basis", "") or ""
    return ("shared_file_storage", vendor, huawei_product, tier)


def _composition_key_object_storage(item: dict[str, Any]) -> tuple:
    """Build composition key for object storage: vendor + tier."""
    vendor = item.get("vendor", "")
    huawei_product = item.get("huawei_product", "")
    tier = item.get("source_pricing_basis", "") or ""
    return ("object_storage", vendor, huawei_product, tier)


def _composition_key_managed_database(item: dict[str, Any]) -> tuple:
    """Build composition key for databases: vendor + family + engine + shape hint.

    Database items from different sub-components (compute, storage, IO)
    are grouped by their source_service_family to compose into one final item.
    We also include engine and compute-shape hints so that different DB instances
    (e.g. two MySQL servers with different SKUs) are not over-merged.
    """
    vendor = item.get("vendor", "")
    huawei_product = item.get("huawei_product", "")
    service_family = item.get("source_service_family", "") or ""

    # Normalize engine: extract from service_family or source_service_name
    _DB_ENGINE_KEYWORDS = ("mysql", "postgresql", "postgres", "sql server", "mariadb",
                           "oracle", "aurora", "redis", "mongo", "cassandra")
    engine = ""
    name_lower = (item.get("source_service_name", "") or "").lower()
    family_lower = service_family.lower()
    for kw in _DB_ENGINE_KEYWORDS:
        if kw in family_lower or kw in name_lower:
            engine = kw
            break

    # Compute shape hint: normalize the SKU/class to a family tier
    # e.g. "Memory Optimized", "Burstable", "General Purpose" → keep as-is
    # This distinguishes "MySQL Burstable B1MS" from "MySQL Memory Optimized"
    # IMPORTANT: only use shape_hint from source_service_name for the composition key,
    # because all sub-items (compute/storage/IO) share the same service name prefix.
    # If shape is only in config_summary, it would break grouping (compute has it,
    # storage/IO don't). We only include shape_hint in the key when it comes from
    # the shared service name.
    shape_hint = ""
    for tier in ("memory optimized", "general purpose", "burstable", "business critical",
                 "hyperscale", "critical"):
        if tier in name_lower:
            shape_hint = tier
            break

    if service_family:
        return ("managed_database", vendor, service_family, engine, shape_hint)
    # Fallback: group by product + spec + engine
    spec = item.get("source_config_summary", "") or item.get("huawei_spec_summary", "")
    return ("managed_database", vendor, huawei_product, spec, engine, shape_hint)


def _composition_key_load_balancing_and_waf(item: dict[str, Any]) -> tuple:
    """Build composition key for LB/WAF: vendor + product."""
    vendor = item.get("vendor", "")
    huawei_product = item.get("huawei_product", "")
    return ("load_balancing_and_waf", vendor, huawei_product)


def _composition_key_vpn_connectivity(item: dict[str, Any]) -> tuple:
    """Build composition key for VPN: vendor + product."""
    vendor = item.get("vendor", "")
    huawei_product = item.get("huawei_product", "")
    return ("vpn_connectivity", vendor, huawei_product)


def _composition_key_public_ip_or_bandwidth(item: dict[str, Any]) -> tuple:
    """Build composition key for public IP / bandwidth: vendor + product."""
    vendor = item.get("vendor", "")
    huawei_product = item.get("huawei_product", "")
    return ("public_ip_or_bandwidth", vendor, huawei_product)


def _composition_key_backup_security_ops(item: dict[str, Any]) -> tuple:
    """Build composition key for backup/security: vendor + product."""
    vendor = item.get("vendor", "")
    huawei_product = item.get("huawei_product", "")
    return ("backup_security_ops", vendor, huawei_product)


_COMPOSITION_KEY_BUILDERS: dict[CloudBillingResourceKind, Any] = {
    "compute_vm": _composition_key_compute_vm,
    "block_storage": _composition_key_block_storage,
    "shared_file_storage": _composition_key_shared_file_storage,
    "object_storage": _composition_key_object_storage,
    "managed_database": _composition_key_managed_database,
    "load_balancing_and_waf": _composition_key_load_balancing_and_waf,
    "vpn_connectivity": _composition_key_vpn_connectivity,
    "public_ip_or_bandwidth": _composition_key_public_ip_or_bandwidth,
    "backup_security_ops": _composition_key_backup_security_ops,
}


# ---------------------------------------------------------------------------
# Merge logic per resource kind (Phase 8D)
# ---------------------------------------------------------------------------

def _merge_items_into_final(
    resource_kind: CloudBillingResourceKind,
    items: list[dict[str, Any]],
    counter: int,
) -> CloudBillingFinalQuoteItem:
    """Merge a list of intermediate items into one CloudBillingFinalQuoteItem.

    The merge strategy depends on resource_kind:
    - compute_vm: sum quantities, sum costs, keep common spec
    - block_storage: sum quantities, sum costs, keep tier info
    - managed_database: compose compute+storage+IO into one item
    - platform_paas_misc: merge into one manual_review item
    - others: sum quantities and costs
    """
    first = items[0]
    vendor = first.get("vendor", "Unknown")
    source_service_name = first.get("source_service_name", "")
    source_service_family = first.get("source_service_family")
    source_config_summary = first.get("source_config_summary")
    huawei_product = first.get("huawei_product")
    huawei_spec_summary = first.get("huawei_spec_summary")
    huawei_billing_basis = first.get("huawei_billing_basis")
    source_pricing_basis = first.get("source_pricing_basis")
    source_item_ids: list[str] = []
    composition_notes: list[str] = []

    # Aggregate source amounts
    total_source_qty = 0.0
    total_source_monthly = 0.0
    total_huawei_qty = 0.0
    total_huawei_monthly = 0.0
    huawei_unit_price = first.get("huawei_unit_price_usd")

    # Track statuses to determine final status
    statuses: set[FinalQuoteItemStatus] = set()
    manual_review_reasons: list[str] = []

    for item in items:
        sid = item.get("source_item_id")
        if sid:
            source_item_ids.append(sid)
        sqty = item.get("source_quantity") or 0
        total_source_qty += sqty
        smonthly = item.get("source_monthly_total_usd") or 0
        total_source_monthly += smonthly
        hqty = item.get("huawei_quantity") or 0
        total_huawei_qty += hqty
        hmonthly = item.get("huawei_monthly_total_usd") or 0
        total_huawei_monthly += hmonthly
        st = item.get("status", "unquoted")
        if st in ("quoted", "partial", "manual_review", "unquoted"):
            statuses.add(st)
        if item.get("manual_review_reason"):
            manual_review_reasons.append(item["manual_review_reason"])

    # ── Kind-specific merge logic ──

    if resource_kind == "compute_vm":
        # VMs: sum quantity, keep spec from first, note count
        if len(items) > 1:
            composition_notes.append(
                f"Composed from {len(items)} VM instance(s) with same spec."
            )
        source_quantity = _final_display_quantity(resource_kind, items, total_source_qty)
        huawei_quantity = source_quantity  # Same count for Huawei
        # If huawei_unit_price exists, recalculate total
        if huawei_unit_price and huawei_quantity:
            total_huawei_monthly = round(huawei_unit_price * huawei_quantity, 2)

    elif resource_kind == "block_storage":
        # Disks: sum quantity and cost
        if len(items) > 1:
            composition_notes.append(
                f"Composed from {len(items)} disk item(s) with same tier/capacity."
            )
        source_quantity = _final_display_quantity(resource_kind, items, total_source_qty)
        huawei_quantity = source_quantity
        if huawei_unit_price and huawei_quantity:
            total_huawei_monthly = round(huawei_unit_price * huawei_quantity, 2)

    elif resource_kind == "managed_database":
        # Database: compose compute + storage + IO into one item
        sub_components = set()
        for item in items:
            sn = item.get("source_service_name", "")
            if "compute" in sn.lower():
                sub_components.add("compute")
            elif "storage" in sn.lower():
                sub_components.add("storage")
            elif "io" in sn.lower() or "i/o" in sn.lower():
                sub_components.add("IO")
        if len(items) > 1:
            comp_str = ", ".join(sorted(sub_components)) if sub_components else "multiple sub-items"
            composition_notes.append(
                f"Database composed from {len(items)} sub-item(s): {comp_str}."
            )
        source_quantity = _final_display_quantity(resource_kind, items, total_source_qty)
        huawei_quantity = source_quantity
        # Build a composite config summary for databases
        if len(items) > 1 and not source_config_summary:
            parts = []
            for item in items:
                sn = item.get("source_service_name", "")
                sc = item.get("source_config_summary", "")
                if sc:
                    parts.append(f"{sn}: {sc}" if sn else sc)
            if parts:
                source_config_summary = "; ".join(parts)

    elif resource_kind in ("shared_file_storage", "object_storage"):
        # File/object storage: merge by tier
        if len(items) > 1:
            composition_notes.append(
                f"Composed from {len(items)} storage item(s) with same tier."
            )
        source_quantity = _final_display_quantity(resource_kind, items, total_source_qty)
        huawei_quantity = source_quantity
        if huawei_unit_price and huawei_quantity:
            total_huawei_monthly = round(huawei_unit_price * huawei_quantity, 2)

    elif resource_kind == "platform_paas_misc":
        # Platform/PaaS: merge into one manual_review item
        composition_notes.append(
            f"Platform/PaaS service — {len(items)} item(s) merged for manual review."
        )
        source_quantity = _final_display_quantity(resource_kind, items, total_source_qty)
        huawei_quantity = None
        huawei_unit_price = None
        total_huawei_monthly = None
        huawei_product = None
        huawei_spec_summary = None
        # Build a composite service name for platform items
        if len(items) > 1:
            names = set()
            for item in items:
                sn = item.get("source_service_name", "")
                if sn:
                    names.add(sn)
            if names:
                source_service_name = ", ".join(sorted(names))

    else:
        # Default: sum quantities and costs
        if len(items) > 1:
            composition_notes.append(
                f"Composed from {len(items)} item(s)."
            )
        source_quantity = _final_display_quantity(resource_kind, items, total_source_qty)
        huawei_quantity = source_quantity

    # ── Determine final status ──
    if resource_kind == "platform_paas_misc":
        status: FinalQuoteItemStatus = "manual_review"
        manual_review_reason = "Platform/PaaS service requires manual pricing review."
    elif "quoted" in statuses and len(statuses) == 1:
        status = "quoted"
        manual_review_reason = None
    elif "quoted" in statuses:
        # Mix of quoted and non-quoted → partial
        status = "partial"
        unquoted_parts = [s for s in statuses if s != "quoted"]
        manual_review_reason = f"Partially quoted; {', '.join(unquoted_parts)} item(s) need attention."
    elif "partial" in statuses:
        status = "partial"
        manual_review_reason = manual_review_reasons[0] if manual_review_reasons else None
    elif "manual_review" in statuses:
        status = "manual_review"
        manual_review_reason = manual_review_reasons[0] if manual_review_reasons else "Requires manual review."
    else:
        status = "unquoted"
        manual_review_reason = manual_review_reasons[0] if manual_review_reasons else None

    # ── Apply display naming (Phase 9A.2) ──
    display_name = _final_display_service_name(resource_kind, vendor, items)
    display_config = _final_display_config_summary(resource_kind, items, source_config_summary)

    return CloudBillingFinalQuoteItem(
        item_id=f"fqi-{resource_kind}-{counter}",
        vendor=vendor,
        resource_kind=resource_kind,
        source_service_family=source_service_family,
        source_service_name=display_name,
        source_config_summary=display_config,
        source_quantity=source_quantity,
        source_pricing_basis=source_pricing_basis,
        source_monthly_total_usd=round(total_source_monthly, 2) if total_source_monthly else None,
        huawei_product=huawei_product,
        huawei_spec_summary=huawei_spec_summary,
        huawei_quantity=huawei_quantity,
        huawei_unit_price_usd=huawei_unit_price,
        huawei_billing_basis=huawei_billing_basis,
        huawei_monthly_total_usd=round(total_huawei_monthly, 2) if total_huawei_monthly else None,
        status=status,
        composition_notes=composition_notes,
        source_item_ids=source_item_ids,
        manual_review_reason=manual_review_reason,
    )


# ---------------------------------------------------------------------------
# LLM-First Composition: billing rows → LLM final composition (Phase 14)
# ---------------------------------------------------------------------------


def _build_llm_first_billing_rows(state: FlexibleQuoteState) -> list[dict[str, Any]]:
    """Extract raw billing rows for LLM-first composition input.

    Reads billing_lines (raw extracted rows) first. Falls back to
    llm_aggregated_billing_items if billing_lines is empty.

    Each row gets a stable row_id for traceability.
    No business grouping or mapping is applied — only field normalization.
    """
    billing_lines = state.get("billing_lines", [])
    if billing_lines:
        rows = []
        for bl in billing_lines:
            source_file = bl.get("source_file", "")
            line_number = bl.get("line_number", 0)
            row_id = f"billing-row::{source_file}::{line_number}"
            rows.append({
                "row_id": row_id,
                "vendor": bl.get("vendor", ""),
                "source_file": source_file,
                "source_sheet": bl.get("source_sheet", ""),
                "line_number": line_number,
                "service_period": bl.get("service_period", ""),
                "product_family": bl.get("product_family", ""),
                "product_type": bl.get("product_type", ""),
                "product_sku": bl.get("product_sku", ""),
                "unit_type": bl.get("unit_type", ""),
                "quantity": bl.get("quantity_raw", ""),
                "quantity_numeric": _to_float(bl.get("quantity_raw")),
                "amount": bl.get("amount_raw", ""),
                "amount_numeric": _to_float(bl.get("amount_raw")),
                "region_hint": bl.get("region_hint", ""),
                "transaction_type": bl.get("transaction_type", ""),
            })
        return rows

    # Fallback: use aggregated items
    agg_items = state.get("llm_aggregated_billing_items", [])
    rows = []
    for idx, agg in enumerate(agg_items):
        source_file = agg.get("source_file", "")
        row_id = f"billing-agg::{source_file}::{idx}"
        rows.append({
            "row_id": row_id,
            "vendor": agg.get("vendor", ""),
            "source_file": source_file,
            "source_sheet": agg.get("source_sheet", ""),
            "line_number": idx,
            "service_period": agg.get("service_period", ""),
            "product_family": agg.get("product_family", ""),
            "product_type": agg.get("product_type", ""),
            "product_sku": agg.get("product_sku", ""),
            "unit_type": agg.get("unit_type", agg.get("derived_unit", "")),
            "quantity": agg.get("derived_quantity"),
            "quantity_numeric": _to_float(agg.get("derived_quantity")),
            "amount": agg.get("amount"),
            "amount_numeric": _to_float(agg.get("amount")),
            "region_hint": agg.get("region_hint", ""),
            "transaction_type": agg.get("transaction_type", ""),
        })
    return rows


def _build_llm_first_prompt_rows(
    billing_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return the compact subset of billing rows sent to the LLM."""
    prompt_rows: list[dict[str, Any]] = []
    for row in billing_rows:
        prompt_rows.append({
            "row_id": row.get("row_id", ""),
            "vendor": row.get("vendor", ""),
            "product_family": row.get("product_family", ""),
            "product_type": row.get("product_type", ""),
            "product_sku": row.get("product_sku", ""),
            "unit_type": row.get("unit_type", ""),
            "quantity": row.get("quantity"),
            "amount": row.get("amount"),
            "region_hint": row.get("region_hint", ""),
        })
    return prompt_rows


def _get_llm_first_test_families() -> set[str]:
    raw = os.getenv("CLOUD_BILLING_LLM_FIRST_TEST_FAMILIES", "").strip()
    if not raw:
        return set()
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def _filter_billing_rows_for_test_families(
    billing_rows: list[dict[str, Any]],
    families: set[str],
) -> list[dict[str, Any]]:
    if not families:
        return billing_rows
    filtered: list[dict[str, Any]] = []
    for row in billing_rows:
        family = str(row.get("product_family", "")).strip().lower()
        if family in families:
            filtered.append(row)
    return filtered


def extract_cloud_billing_requirement_items(state: FlexibleQuoteState) -> FlexibleQuoteState:
    """Cloud billing extraction wrapper.

    Cloud Billing now prefers LLM-first final composition. To keep the pricing
    pipeline fast and avoid spending two extra MaaS calls before the final
    composition step, the billing extraction stage skips the legacy billing
    aggregation/standardization LLM calls and uses the deterministic extraction
    path for requirements/agg items.
    """
    next_state = dict(state)
    next_state["skip_billing_llm"] = True
    return extract_requirement_items(next_state)


def _parse_billing_row_number(ref: str) -> int | None:
    parts = ref.split("::")
    if len(parts) < 3:
        return None
    return int(parts[2]) if parts[2].isdigit() else None


def _dedupe_quote_lines(lines: list[FlexibleQuoteLine]) -> list[FlexibleQuoteLine]:
    deduped: list[FlexibleQuoteLine] = []
    seen: set[str] = set()
    for line in lines:
        key = line.line_id or f"{line.requirement_item_id}:{line.product}:{line.monthly_price}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(line)
    return deduped


def _fallback_source_quantity_from_rows(
    resource_kind: str,
    valid_rows: list[dict[str, Any]],
    valid_aggs: list[dict[str, Any]],
) -> float | int | None:
    if resource_kind == "managed_database":
        return 1
    if resource_kind in {"shared_file_storage", "object_storage"}:
        return 1
    if resource_kind == "platform_paas_misc":
        return 1

    if valid_aggs:
        agg_total_qty = sum(_to_float(agg.get("derived_quantity")) or 0.0 for agg in valid_aggs)
        display_items = _build_display_intermediate_items(
            [
                f"__agg__::{idx}" for idx, _ in enumerate(valid_aggs)
            ],
            {f"__agg__::{idx}": agg for idx, agg in enumerate(valid_aggs)},
        )
        display_qty = _final_display_quantity(resource_kind, display_items, agg_total_qty)
        if display_qty is not None:
            return display_qty

    if resource_kind == "compute_vm":
        hour_based_qty = 0.0
        found_hour = False
        for row in valid_rows:
            qty = row.get("quantity_numeric")
            unit = str(row.get("unit_type", "")).lower()
            if qty is None:
                continue
            if "hour" in unit or unit in {"h", "hrs"}:
                hour_based_qty += qty
                found_hour = True
        if found_hour:
            approx_instances = hour_based_qty / 744.0
            if approx_instances >= 0.5:
                return max(1, round(approx_instances))
        return None

    if resource_kind == "block_storage":
        return max(1, len(valid_aggs)) if valid_aggs else 1

    if resource_kind in {"load_balancing_and_waf", "vpn_connectivity", "public_ip_or_bandwidth", "backup_security_ops"}:
        return max(1, len(valid_aggs) or len(valid_rows) or 1)

    return None


_LLM_FIRST_COMPOSITION_SYSTEM_PROMPT = (
    "You are a cloud billing quotation composer. Aggregate complete Azure/AWS/GCP "
    "billing rows into 10-30 business-level final quotation items.\n\n"
    "Do:\n"
    "- group rows that belong to the same business resource;\n"
    "- return customer-readable service names and concise config summaries;\n"
    "- suggest one Huawei Cloud product direction per final item;\n"
    "- preserve traceability with source row refs.\n\n"
    "You MUST NOT:\n"
    "- output prices;\n"
    "- invent SKUs or Huawei products;\n"
    "- merge fundamentally different resources (VM+storage, API Management+Fabric);\n"
    "- hide large committed-cost services such as Fabric Capacity Reservation.\n\n"
    "Grouping rules:\n"
    "- VM/EC2/Compute Engine -> compute_vm\n"
    "- Managed Disk/EBS/Persistent Disk -> block_storage\n"
    "- Database compute+storage+IO -> managed_database\n"
    "- Blob/S3/GCS -> object_storage\n"
    "- Azure Files/EFS/Filestore -> shared_file_storage\n"
    "- LB/WAF -> load_balancing_and_waf\n"
    "- VPN/gateway -> vpn_connectivity\n"
    "- Public IP/bandwidth -> public_ip_or_bandwidth\n"
    "- Backup/security/monitoring -> backup_security_ops\n"
    "- Platform/PaaS/misc -> platform_paas_misc manual_review\n\n"
    "Return strict JSON only.\n"
    '{"candidate_id","vendor","resource_kind","source_service_name",'
    '"source_config_summary","source_quantity","source_billing_basis",'
    '"huawei_product","huawei_spec_hint","huawei_quantity","huawei_billing_basis",'
    '"status","manual_review_reason","composition_notes","component_refs","confidence"}\n\n'
    "resource_kind ∈ {compute_vm, block_storage, shared_file_storage, object_storage, "
    "managed_database, load_balancing_and_waf, vpn_connectivity, "
    "public_ip_or_bandwidth, backup_security_ops, platform_paas_misc}\n"
    "status ∈ {quoted, partial, manual_review, unquoted}\n"
    "confidence ∈ [0, 1]\n\n"
    "Return a JSON object with key \"candidates\" containing an array."
)


def _build_llm_first_composition_prompt(
    billing_rows: list[dict[str, Any]],
    quote_lines: list[dict[str, Any]],
    quote_context: dict[str, Any],
) -> dict[str, Any]:
    """Build the prompt for LLM-first composition from raw billing rows.

    Compact: only essential fields to minimize token count while preserving
    traceability and pricing hints.
    """
    # Compact quote line summaries — only what LLM needs for composition
    ql_summaries = []
    for ql in quote_lines:
        summary = {
            "id": ql.get("requirement_item_id", ""),
            "product": ql.get("product", ""),
            "monthly_price": ql.get("monthly_price"),
        }
        ql_summaries.append(summary)

    prompt_rows = _build_llm_first_prompt_rows(billing_rows)

    prompt_context = {
        "region": quote_context.get("region"),
        "language": quote_context.get("language"),
    }
    customer_notes = (quote_context.get("customer_notes") or "").strip()
    if customer_notes:
        prompt_context["customer_notes"] = customer_notes[:300]

    return {
        "quote_context": prompt_context,
        "billing_rows": prompt_rows,
        "total_rows": len(prompt_rows),
        "priced_items": ql_summaries,
    }


def _estimate_llm_first_prompt_chars(
    billing_rows: list[dict[str, Any]],
    quote_lines: list[dict[str, Any]],
    quote_context: dict[str, Any],
) -> int:
    import json

    prompt_data = _build_llm_first_composition_prompt(billing_rows, quote_lines, quote_context)
    return len(json.dumps(prompt_data, ensure_ascii=False))


def _is_agg_llm_fallback_enabled() -> bool:
    return os.getenv("CLOUD_BILLING_ENABLE_AGG_LLM_FALLBACK", "").strip().lower() in {"1", "true", "yes", "on"}


def _extract_json_payload_text(content: Any) -> str | None:
    """Best-effort extraction of JSON text from LLM content.

    MaaS models sometimes wrap JSON in markdown fences or return structured content
    blocks. We normalize those variants here before calling json.loads().
    """
    text = ""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                block_text = block.get("text")
                if block_text is not None:
                    parts.append(str(block_text))
            elif isinstance(block, str):
                parts.append(block)
        text = "\n".join(parts)
    elif content is not None:
        text = str(content)

    text = text.strip()
    if not text:
        return None

    fence_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    if text.startswith("{") and text.endswith("}"):
        return text

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace:last_brace + 1]
    return text


def _coerce_llm_candidate_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    """Coerce common MaaS output quirks into the candidate schema shape.

    In practice some models emit descriptive strings for quantity fields or
    a single string for notes/refs. We keep the useful parts and let the
    downstream deterministic logic fill the rest.
    """
    normalized = dict(candidate)
    for field in ("source_quantity", "huawei_quantity", "confidence"):
        value = normalized.get(field)
        if isinstance(value, str):
            cleaned = value.strip()
            numeric_like = bool(re.fullmatch(r"[+-]?\d[\d,\.\s]*", cleaned))
            parsed = _to_float(cleaned) if numeric_like else None
            normalized[field] = parsed

    notes = normalized.get("composition_notes")
    if isinstance(notes, str):
        normalized["composition_notes"] = [notes] if notes.strip() else []
    elif notes is None:
        normalized["composition_notes"] = []

    refs = normalized.get("component_refs")
    if isinstance(refs, str):
        normalized["component_refs"] = [refs] if refs.strip() else []
    elif refs is None:
        normalized["component_refs"] = []
    return normalized


def _compose_final_billing_llm_first(
    billing_rows: list[dict[str, Any]],
    quote_lines: list[dict[str, Any]],
    quote_context: dict[str, Any],
) -> list[dict[str, Any]] | None:
    """Call MaaS LLM with raw billing rows for LLM-first final composition.

    Returns list of candidate dicts on success, None on failure.
    """
    import json
    import os

    import httpx

    api_key = os.getenv("HUAWEI_MAAS_API_KEY")
    base_url = os.getenv("HUAWEI_MAAS_BASE_URL")
    model = os.getenv("HUAWEI_MAAS_MODEL")
    if not api_key or not base_url or not model:
        return None

    prompt_data = _build_llm_first_composition_prompt(
        billing_rows, quote_lines, quote_context,
    )

    try:
        with httpx.Client(timeout=_get_billing_final_composition_timeout_seconds()) as client:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _LLM_FIRST_COMPOSITION_SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(prompt_data, ensure_ascii=False)},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            json_text = _extract_json_payload_text(content)
            if not json_text:
                logger.warning("LLM-first composition returned empty content — falling back")
                return None
            parsed = json.loads(json_text)
            candidates = parsed.get("candidates", [])
            if not candidates:
                logger.warning("LLM-first composition returned 0 candidates — falling back")
                return None
            return candidates
    except Exception as exc:
        logger.warning("LLM-first composition failed: %s", exc)
        return None


# Allowed Huawei product set for validation
_ALLOWED_HUAWEI_PRODUCTS = frozenset({
    "ECS", "EVS", "OBS", "SFS Turbo", "RDS", "DDS", "DWS", "ELB", "WAF",
    "VPN", "EIP", "CBR", "HSS", "NAT Gateway", "Direct Connect as a Service",
    "CCE", "CCI", "VPC", "Workspace", "DRS", "CSS", "LTS", "DLI", "DCS",
    "GeminiDB", "DMS", "DataArts Studio", "Cloud Connect", "DEW",
    "Anti-DDoS", "CFW", "CES", "ModelArts", "FunctionGraph", "GaussDB",
})


def _validate_and_enrich_llm_first_candidates(
    candidates_raw: list[dict[str, Any]],
    billing_rows: list[dict[str, Any]],
    quote_lines: list[dict[str, Any]],
    agg_items: list[dict[str, Any]],
    unquoted_items: list[dict[str, Any]],
    blocker_items: list[dict[str, Any]],
) -> list[CloudBillingFinalQuoteItem]:
    """Validate LLM-first candidates and enrich with deterministic pricing.

    Uses row-level refs (billing-row::*) for source amount backfill.
    Falls back to aggregated item refs (billing-agg::*) for quote line lookup.
    """
    from app.models import CloudBillingFinalCompositionCandidate

    # Build lookup: row_id → billing row
    row_by_id: dict[str, dict[str, Any]] = {}
    for row in billing_rows:
        row_by_id[row["row_id"]] = row

    # Build lookup: agg item_id → agg item (for quote line mapping)
    agg_by_id: dict[str, dict[str, Any]] = {}
    for idx, agg in enumerate(agg_items):
        source_file = agg.get("source_file", "")
        req_item_id = f"billing-agg::{source_file}::{idx}"
        agg_by_id[req_item_id] = agg

    # Build lookup: requirement_item_id → list[FlexibleQuoteLine]
    qls_by_req_id: dict[str, list[FlexibleQuoteLine]] = {}
    for ql in quote_lines:
        try:
            line = FlexibleQuoteLine.model_validate(ql)
            qls_by_req_id.setdefault(line.requirement_item_id, []).append(line)
        except Exception:
            pass

    # Collect unquoted/blocker IDs
    unquoted_ids: set[str] = set()
    for uq in unquoted_items:
        unquoted_ids.add(uq.get("item_id", ""))
    blocker_ids: set[str] = set()
    for blk in blocker_items:
        blocker_ids.add(blk.get("item_id", ""))

    # Track claimed rows for ownership
    claimed_row_ids: set[str] = set()

    final_items: list[CloudBillingFinalQuoteItem] = []
    counter = 0

    for cand_raw in candidates_raw:
        # Schema validation
        try:
            cand = CloudBillingFinalCompositionCandidate.model_validate(
                _coerce_llm_candidate_payload(cand_raw)
            )
        except Exception as exc:
            logger.warning("Invalid LLM-first candidate rejected: %s", exc)
            continue

        # component_refs validation — support both billing-row::* and billing-agg::*
        valid_row_refs: list[str] = []
        valid_agg_refs: list[str] = []
        for ref in cand.component_refs:
            if ref.startswith("billing-row::") and ref in row_by_id:
                valid_row_refs.append(ref)
            elif ref.startswith("billing-agg::") and ref in agg_by_id:
                valid_agg_refs.append(ref)

        if not valid_row_refs and not valid_agg_refs:
            logger.warning("Candidate %s has no valid refs — skipping", cand.candidate_id)
            continue

        # Enforce row ownership: later candidates give up overlapping refs
        already_claimed = [r for r in valid_row_refs if r in claimed_row_ids]
        if already_claimed:
            valid_row_refs = [r for r in valid_row_refs if r not in claimed_row_ids]
            if valid_row_refs:
                notes = list(cand.composition_notes)
                notes.append("Ownership conflict trimmed overlapping row refs.")
                cand = cand.model_copy(update={"composition_notes": notes})
        if not valid_row_refs and not valid_agg_refs:
            continue
        claimed_row_ids.update(valid_row_refs)

        # Source amount backfill from billing rows (don't trust LLM)
        source_monthly_total = 0.0
        for ref in valid_row_refs:
            row = row_by_id[ref]
            source_monthly_total += abs(row.get("amount_numeric") or _to_float(row.get("amount")) or 0.0)
        # If no row refs, sum from agg refs
        if not valid_row_refs:
            for ref in valid_agg_refs:
                agg = agg_by_id[ref]
                source_monthly_total += _to_float(agg.get("amount")) or 0.0

        # Source quantity: prefer LLM's business quantity
        source_quantity = cand.source_quantity
        if source_quantity is None:
            valid_rows = [row_by_id[ref] for ref in valid_row_refs if ref in row_by_id]
            valid_aggs = [agg_by_id[ref] for ref in valid_agg_refs if ref in agg_by_id]
            source_quantity = _fallback_source_quantity_from_rows(cand.resource_kind, valid_rows, valid_aggs)

        # Huawei product validation
        huawei_product = cand.huawei_product
        if huawei_product and huawei_product not in _ALLOWED_HUAWEI_PRODUCTS:
            # Invalid product → manual_review
            huawei_product = None
            cand.status = "manual_review"
            cand.manual_review_reason = f"LLM suggested invalid Huawei product: {cand.huawei_product}"

        # Huawei pricing backfill from quote_lines via agg refs
        huawei_spec_summary = cand.huawei_spec_hint
        huawei_quantity = None
        huawei_unit_price_usd = None
        huawei_billing_basis = cand.huawei_billing_basis
        huawei_monthly_total_usd = None
        quoted_count = 0
        unquoted_count = 0
        manual_review_count = 0

        candidate_qls: list[FlexibleQuoteLine] = []
        for ref in valid_agg_refs:
            ref_qls = qls_by_req_id.get(ref, [])
            if ref_qls:
                candidate_qls.extend(ref_qls)
                quoted_count += 1
            elif ref in unquoted_ids:
                unquoted_count += 1
            elif ref in blocker_ids:
                manual_review_count += 1
            else:
                agg = agg_by_id.get(ref, {})
                if agg.get("needs_manual_review"):
                    manual_review_count += 1
                else:
                    unquoted_count += 1

        # Also try to find quote lines by matching row refs to requirement IDs
        # (billing-row::file::line → billing-agg::file::idx pattern)
        if not candidate_qls and valid_row_refs:
            for ref in valid_row_refs:
                # Try to find a matching quote line through the agg items
                for agg_id, agg in agg_by_id.items():
                    agg_file = agg.get("source_file", "")
                    agg_lines = agg.get("source_line_numbers", [])
                    row_no = _parse_billing_row_number(ref)
                    parts = ref.split("::")
                    if len(parts) >= 3 and parts[1] == agg_file and row_no is not None:
                        try:
                            if row_no in agg_lines:
                                ref_qls = qls_by_req_id.get(agg_id, [])
                                if ref_qls:
                                    candidate_qls.extend(ref_qls)
                                    quoted_count += 1
                        except (ValueError, TypeError):
                            pass

        candidate_qls = _dedupe_quote_lines(candidate_qls)
        if candidate_qls:
            quoted_count = len(candidate_qls)

        if candidate_qls:
            huawei_monthly_total_usd = sum(ql.monthly_price for ql in candidate_qls)
            primary_ql = candidate_qls[0]
            if not huawei_product:
                huawei_product = primary_ql.product
            if len(candidate_qls) > 1:
                products = set(ql.product for ql in candidate_qls)
                if len(products) > 1:
                    huawei_product = " + ".join(sorted(products))
                    huawei_quantity = None
                    huawei_unit_price_usd = None
                    huawei_billing_basis = "composite"
                    huawei_spec_summary = " | ".join(
                        f"{ql.product}: {ql.matched_sku or ql.matched_tier or ql.billing_mode}"
                        for ql in candidate_qls
                    )
                else:
                    huawei_quantity = sum(ql.quantity for ql in candidate_qls)
                    huawei_spec_summary = primary_ql.matched_sku or primary_ql.matched_tier
                    huawei_unit_price_usd = primary_ql.unit_price
                    huawei_billing_basis = primary_ql.billing_mode
            else:
                huawei_quantity = sum(ql.quantity for ql in candidate_qls)
                huawei_spec_summary = primary_ql.matched_sku or primary_ql.matched_tier
                huawei_unit_price_usd = primary_ql.unit_price
                huawei_billing_basis = primary_ql.billing_mode
        
        # Status correction
        total_components = quoted_count + unquoted_count + manual_review_count
        if total_components == 0:
            total_components = 1

        if quoted_count == total_components and candidate_qls:
            status: FinalQuoteItemStatus = "quoted"
            manual_review_reason = None
        elif quoted_count > 0:
            status = "partial"
            manual_review_reason = f"Partially quoted: {quoted_count}/{total_components} component(s) priced."
        elif manual_review_count > 0 or cand.status == "manual_review":
            status = "manual_review"
            manual_review_reason = cand.manual_review_reason or "Components require manual review."
        else:
            status = "unquoted"
            manual_review_reason = "No pricing available for components."

        # Resource kind normalization
        resource_kind = cand.resource_kind
        valid_kinds = {
            "compute_vm", "block_storage", "shared_file_storage", "object_storage",
            "managed_database", "load_balancing_and_waf", "vpn_connectivity",
            "public_ip_or_bandwidth", "backup_security_ops", "platform_paas_misc",
        }
        if resource_kind not in valid_kinds:
            resource_kind = "platform_paas_misc"

        counter += 1
        all_refs = valid_row_refs + valid_agg_refs
        final_items.append(CloudBillingFinalQuoteItem(
            item_id=f"fqi-llm1-{counter}",
            vendor=cand.vendor,
            resource_kind=resource_kind,
            source_service_family=cand_raw.get("source_service_family"),
            source_service_name=cand.source_service_name,
            source_config_summary=cand.source_config_summary,
            source_quantity=source_quantity,
            source_pricing_basis=cand.source_billing_basis,
            source_monthly_total_usd=round(source_monthly_total, 2) if source_monthly_total else None,
            huawei_product=huawei_product,
            huawei_spec_summary=huawei_spec_summary,
            huawei_quantity=huawei_quantity,
            huawei_unit_price_usd=huawei_unit_price_usd,
            huawei_billing_basis=huawei_billing_basis,
            huawei_monthly_total_usd=round(huawei_monthly_total_usd, 2) if huawei_monthly_total_usd else None,
            status=status,
            composition_notes=list(cand.composition_notes),
            source_item_ids=all_refs,
            manual_review_reason=manual_review_reason,
        ))

    return final_items


# ---------------------------------------------------------------------------
# LLM-driven Final Composition (Phase 10B+C)
# ---------------------------------------------------------------------------

_FINAL_COMPOSITION_SYSTEM_PROMPT = (
    "You are a cloud billing quotation composer. Given AGGREGATED billing items "
    "from a cloud invoice (Azure, AWS, or GCP), compose them into BUSINESS-LEVEL "
    "final quotation items suitable for a customer-facing quotation table.\n\n"
    "YOUR ROLE:\n"
    "- You compose business-level quotation items by merging related aggregates.\n"
    "- You choose service names, config summaries, and grouping.\n"
    "- You mark items that need manual review.\n\n"
    "YOU MUST NOT:\n"
    "- Invent prices — all pricing is handled by deterministic rules.\n"
    "- Invent Huawei SKUs that are not in the input data.\n"
    "- Choose Huawei products not already suggested in the input.\n"
    "- Drop traceability — every final item must reference its source items.\n\n"
    "CROSS-CLOUD RULES (apply to Azure, AWS, and GCP equally):\n"
    "- Merge multiple VM/EC2/Compute Engine instances with the same spec into ONE final item.\n"
    "- Merge multiple disk/EBS/Persistent Disk items with the same tier into ONE final item.\n"
    "- Compose database compute + storage + IO sub-items into ONE final database item.\n"
    "- Merge file storage / object storage items by tier.\n"
    "- Group VPN/gateway items by type.\n"
    "- Group load balancer / WAF items.\n"
    "- Group public IP / bandwidth items.\n"
    "- Group backup / security / monitoring items.\n"
    "- Group platform / PaaS / misc items as manual_review.\n\n"
    "OUTPUT REQUIREMENTS:\n"
    "- Produce 10-30 business-level final items (NOT 70+ internal items).\n"
    "- Each item must have component_refs pointing to source item_ids.\n"
    "- Use customer-readable service names (e.g. 'Azure VM', 'AWS RDS for MySQL', "
    "'GCP Cloud SQL for PostgreSQL').\n"
    "- Config summaries should be concise (e.g. '4 vCore / 32 GiB + 500 GB storage').\n"
    "- Mark complex/uncertain items as partial or manual_review.\n\n"
    "Output JSON schema per item:\n"
    '{"candidate_id","vendor","resource_kind","source_service_name",'
    '"source_config_summary","source_quantity","source_billing_basis",'
    '"huawei_product","huawei_spec_hint","huawei_quantity","huawei_billing_basis",'
    '"status","manual_review_reason","composition_notes","component_refs","confidence"}\n\n'
    "resource_kind ∈ {compute_vm, block_storage, shared_file_storage, object_storage, "
    "managed_database, load_balancing_and_waf, vpn_connectivity, "
    "public_ip_or_bandwidth, backup_security_ops, platform_paas_misc}\n"
    "status ∈ {quoted, partial, manual_review, unquoted}\n"
    "confidence ∈ [0, 1]\n\n"
    "Return a JSON object with key \"candidates\" containing an array of final composition candidates."
)


def _build_final_composition_prompt(
    agg_items: list[dict[str, Any]],
    quote_lines: list[dict[str, Any]],
    quote_context: dict[str, Any],
) -> dict[str, Any]:
    """Build the compact JSON prompt for the LLM final composition call.

    Sends aggregated items (not raw lines) to keep token count manageable.
    Includes quote line summaries so the LLM knows what's already priced.
    """
    # Build a lookup: requirement_item_id → quote line summary
    ql_summary_by_req: dict[str, dict[str, Any]] = {}
    for ql in quote_lines:
        try:
            line = FlexibleQuoteLine.model_validate(ql)
            ql_summary_by_req[line.requirement_item_id] = {
                "product": line.product,
                "matched_sku": line.matched_sku,
                "matched_tier": line.matched_tier,
                "unit_price": line.unit_price,
                "monthly_price": line.monthly_price,
            }
        except Exception:
            pass

    # Build compact aggregated items for the prompt
    compact_items = []
    for idx, agg in enumerate(agg_items):
        source_file = agg.get("source_file", "")
        req_item_id = f"billing-agg::{source_file}::{idx}"

        compact: dict[str, Any] = {
            "item_id": req_item_id,
            "vendor": agg.get("vendor", ""),
            "resource_kind": agg.get("resource_kind", "unsupported"),
            "aggregate_label": agg.get("aggregate_label", ""),
            "product_family": agg.get("product_family", ""),
            "product_type": agg.get("product_type", ""),
            "product_sku": agg.get("product_sku", ""),
            "derived_quantity": agg.get("derived_quantity"),
            "derived_unit": agg.get("derived_unit", ""),
            "amount": agg.get("amount"),
            "huawei_product": agg.get("huawei_product"),
            "huawei_spec_hint": agg.get("huawei_spec_hint", ""),
            "needs_manual_review": agg.get("needs_manual_review", False),
        }

        # Attach quote line summary if available
        ql_sum = ql_summary_by_req.get(req_item_id)
        if ql_sum:
            compact["quote_line"] = ql_sum

        compact_items.append(compact)

    return {
        "quote_context": quote_context,
        "aggregated_items": compact_items,
        "total_items": len(compact_items),
    }


def _compose_final_billing_with_llm(
    agg_items: list[dict[str, Any]],
    quote_lines: list[dict[str, Any]],
    quote_context: dict[str, Any],
) -> list[dict[str, Any]] | None:
    """Call MaaS LLM to compose final billing quotation items.

    Returns list of candidate dicts on success, None on failure.
    """
    import json
    import os

    import httpx

    api_key = os.getenv("HUAWEI_MAAS_API_KEY")
    base_url = os.getenv("HUAWEI_MAAS_BASE_URL")
    model = os.getenv("HUAWEI_MAAS_MODEL")
    if not api_key or not base_url or not model:
        return None

    prompt_data = _build_final_composition_prompt(agg_items, quote_lines, quote_context)

    try:
        with httpx.Client(timeout=_get_billing_llm_timeout_seconds()) as client:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _FINAL_COMPOSITION_SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(prompt_data, ensure_ascii=False)},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            json_text = _extract_json_payload_text(content)
            if not json_text:
                logger.warning("LLM final composition returned empty content — falling back")
                return None
            parsed = json.loads(json_text)
            candidates = parsed.get("candidates", [])
            if not candidates:
                logger.warning("LLM final composition returned 0 candidates — falling back")
                return None
            return candidates
    except Exception as exc:
        logger.warning("LLM final composition failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Validation & Enrichment (Phase 10D)
# ---------------------------------------------------------------------------


def _build_display_intermediate_items(
    refs: list[str],
    agg_by_id: dict[str, dict[str, Any]],
    huawei_product_hint: str | None = None,
) -> list[dict[str, Any]]:
    """Build intermediate-like items from aggregate refs for display helpers.

    This keeps the LLM success path aligned with the deterministic composer by
    reusing the same quantity/name/config normalization helpers.
    """
    items: list[dict[str, Any]] = []
    for ref in refs:
        agg = agg_by_id.get(ref, {})
        if not agg:
            continue
        kind_raw = agg.get("resource_kind", "unsupported")
        huawei_product = agg.get("huawei_product") or huawei_product_hint
        items.append(
            {
                "source_item_id": ref,
                "vendor": _normalize_vendor(agg.get("vendor")),
                "resource_kind": _classify_resource_kind(kind_raw, huawei_product),
                "source_service_name": agg.get("aggregate_label", "") or agg.get("product_type", ""),
                "source_service_family": agg.get("product_family"),
                "source_config_summary": agg.get("huawei_spec_hint") or agg.get("source_sku_hint", ""),
                "source_quantity": agg.get("derived_quantity"),
                "source_pricing_basis": agg.get("derived_unit"),
                "source_monthly_total_usd": agg.get("amount"),
                "huawei_product": huawei_product,
            }
        )
    return items


def _recompute_candidate_from_refs(
    cand: CloudBillingFinalCompositionCandidate,
    valid_refs: list[str],
    agg_by_id: dict[str, dict[str, Any]],
    qls_by_req_id: dict[str, list[FlexibleQuoteLine]],
    unquoted_ids: set[str],
    blocker_ids: set[str],
) -> tuple[
    CloudBillingResourceKind,
    list[dict[str, Any]],
    float | None,
    str | None,
    str,
    float | None,
    str | None,
    float | None,
    str | None,
    float | None,
    FinalQuoteItemStatus,
    str | None,
    list[str],
]:
    """Recompute all exported fields from the final validated refs.

    This is called after any ref filtering/downgrade so the exported totals,
    pricing and status always match the final `source_item_ids`.
    """
    ref_kinds = {agg_by_id.get(ref, {}).get("resource_kind", "unsupported") for ref in valid_refs}
    compute_kinds = {"ecs", "vm", "compute_vm"}
    storage_kinds = {"evs", "disk", "block_storage", "sfs_turbo", "file_storage", "shared_file_storage"}
    db_kinds = {"rds", "database", "managed_database"}

    has_compute = bool(ref_kinds & compute_kinds)
    has_storage = bool(ref_kinds & storage_kinds)
    has_db = bool(ref_kinds & db_kinds)

    resource_kind = cand.resource_kind
    if resource_kind not in {
        "compute_vm", "block_storage", "shared_file_storage", "object_storage",
        "managed_database", "load_balancing_and_waf", "vpn_connectivity",
        "public_ip_or_bandwidth", "backup_security_ops", "platform_paas_misc",
    }:
        if has_db:
            resource_kind = "managed_database"
        elif has_compute:
            resource_kind = "compute_vm"
        elif has_storage:
            resource_kind = "block_storage"
        else:
            resource_kind = "platform_paas_misc"

    source_monthly_total = 0.0
    raw_source_quantity = 0.0
    for ref in valid_refs:
        agg = agg_by_id[ref]
        source_monthly_total += float(agg.get("amount", 0) or 0)
        raw_source_quantity += float(agg.get("derived_quantity", 0) or 0)

    display_items = _build_display_intermediate_items(valid_refs, agg_by_id, cand.huawei_product)
    display_vendor = display_items[0]["vendor"] if display_items else cand.vendor
    display_name = _final_display_service_name(resource_kind, display_vendor, display_items) if display_items else cand.source_service_name
    display_config = _final_display_config_summary(resource_kind, display_items, cand.source_config_summary)
    display_qty = _final_display_quantity(resource_kind, display_items, raw_source_quantity) if display_items else cand.source_quantity
    display_pricing_basis = cand.source_billing_basis or (display_items[0].get("source_pricing_basis") if display_items else None)

    candidate_qls: list[FlexibleQuoteLine] = []
    quoted_count = 0
    unquoted_count = 0
    manual_review_count = 0
    for ref in valid_refs:
        ref_qls = qls_by_req_id.get(ref, [])
        if ref_qls:
            candidate_qls.extend(ref_qls)
            quoted_count += 1
        elif ref in unquoted_ids:
            unquoted_count += 1
        elif ref in blocker_ids:
            manual_review_count += 1
        else:
            agg = agg_by_id.get(ref, {})
            if agg.get("needs_manual_review"):
                manual_review_count += 1
            else:
                unquoted_count += 1

    huawei_product = cand.huawei_product
    huawei_spec_summary = cand.huawei_spec_hint
    huawei_quantity = None
    huawei_unit_price_usd = None
    huawei_billing_basis = cand.huawei_billing_basis
    huawei_monthly_total_usd = None
    composition_notes = list(cand.composition_notes)

    if candidate_qls:
        huawei_monthly_total_usd = sum(ql.monthly_price for ql in candidate_qls)
        products = {ql.product for ql in candidate_qls}
        if len(products) > 1:
            huawei_product = " + ".join(sorted(products))
            huawei_quantity = None
            huawei_unit_price_usd = None
            huawei_billing_basis = "composite"
            spec_parts = []
            for ql in candidate_qls:
                part = ql.product
                detail = ql.matched_sku or ql.matched_tier
                if detail:
                    part = f"{part}: {detail}"
                spec_parts.append(part)
            huawei_spec_summary = " | ".join(spec_parts)
        else:
            primary_ql = candidate_qls[0]
            huawei_product = primary_ql.product
            huawei_spec_summary = primary_ql.matched_sku or primary_ql.matched_tier
            huawei_quantity = sum(ql.quantity for ql in candidate_qls)
            huawei_unit_price_usd = primary_ql.unit_price
            huawei_billing_basis = primary_ql.billing_mode

    total_components = quoted_count + unquoted_count + manual_review_count
    if total_components == 0:
        total_components = 1

    if quoted_count == total_components and candidate_qls:
        status: FinalQuoteItemStatus = "quoted"
        manual_review_reason = None
    elif quoted_count > 0:
        status = "partial"
        manual_review_reason = f"Partially quoted: {quoted_count}/{total_components} component(s) priced."
    elif manual_review_count > 0:
        status = "manual_review"
        manual_review_reason = "Components require manual review."
    else:
        status = "unquoted"
        manual_review_reason = "No pricing available for components."

    return (
        resource_kind,
        display_items,
        round(source_monthly_total, 2) if source_monthly_total else None,
        display_name,
        display_vendor,
        display_qty,
        display_pricing_basis,
        round(huawei_monthly_total_usd, 2) if huawei_monthly_total_usd else None,
        huawei_product,
        huawei_quantity,
        status,
        manual_review_reason,
        composition_notes,
        huawei_spec_summary,
        huawei_unit_price_usd,
        huawei_billing_basis,
        display_config,
    )


def _validate_and_enrich_llm_final_candidates(
    candidates_raw: list[dict[str, Any]],
    agg_items: list[dict[str, Any]],
    quote_lines: list[dict[str, Any]],
    requirements_raw: list[dict[str, Any]],
    unquoted_items: list[dict[str, Any]],
    blocker_items: list[dict[str, Any]],
) -> list[CloudBillingFinalQuoteItem]:
    """Validate LLM composition candidates and enrich with deterministic pricing.

    Steps:
    1. Schema validation — parse each candidate, reject invalid ones.
    2. component_refs validation — each ref must point to a real aggregated item.
    3. Source amount backfill — sum from component_refs, don't trust LLM.
    4. Huawei pricing backfill — from quote_lines via component_refs.
    5. Status correction — based on actual pricing state of components.
    6. Invalid candidate downgrade — reject obviously wrong compositions.
    """
    from app.models import CloudBillingFinalCompositionCandidate

    # Build lookup: agg item_id → agg item
    agg_by_id: dict[str, dict[str, Any]] = {}
    for idx, agg in enumerate(agg_items):
        source_file = agg.get("source_file", "")
        req_item_id = f"billing-agg::{source_file}::{idx}"
        agg_by_id[req_item_id] = agg

    # Build lookup: requirement_item_id → list[FlexibleQuoteLine]
    qls_by_req_id: dict[str, list[FlexibleQuoteLine]] = {}
    for ql in quote_lines:
        try:
            line = FlexibleQuoteLine.model_validate(ql)
            qls_by_req_id.setdefault(line.requirement_item_id, []).append(line)
        except Exception:
            pass

    # Collect unquoted and blocker IDs
    unquoted_ids: set[str] = set()
    for uq in unquoted_items:
        unquoted_ids.add(uq.get("item_id", ""))
    blocker_ids: set[str] = set()
    for blk in blocker_items:
        blocker_ids.add(blk.get("item_id", ""))

    # Track which agg items have been claimed (for 1:1 ownership check)
    claimed_agg_ids: set[str] = set()

    final_items: list[CloudBillingFinalQuoteItem] = []
    counter = 0

    for cand_raw in candidates_raw:
        # Step 1: Schema validation
        try:
            cand = CloudBillingFinalCompositionCandidate.model_validate(
                _coerce_llm_candidate_payload(cand_raw)
            )
        except Exception as exc:
            logger.warning("Invalid LLM candidate rejected: %s", exc)
            continue

        # Step 2: component_refs validation
        valid_refs: list[str] = []
        for ref in cand.component_refs:
            if ref in agg_by_id:
                valid_refs.append(ref)
            # Silently skip refs that don't exist
        if not valid_refs:
            # Candidate with no valid refs is useless — downgrade to manual_review
            logger.warning("Candidate %s has no valid component_refs — skipping", cand.candidate_id)
            continue

        # Check for ownership conflicts (1:1 preferred)
        already_claimed = [r for r in valid_refs if r in claimed_agg_ids]
        if already_claimed:
            # Some refs already claimed by another candidate — allow sharing
            # but note it in composition_notes
            pass
        claimed_agg_ids.update(valid_refs)

        # Step 3: Invalid candidate downgrade / ref filtering
        # Reject candidates that mix fundamentally different resource kinds
        # (e.g. VM + Storage in one item, or two different databases)
        ref_kinds = set()
        for ref in valid_refs:
            agg = agg_by_id.get(ref, {})
            kind = agg.get("resource_kind", "unsupported")
            ref_kinds.add(kind)

        # Normalize kinds for cross-kind check
        _COMPUTE_KINDS = {"ecs", "vm", "compute_vm"}
        _STORAGE_KINDS = {"evs", "disk", "block_storage", "sfs_turbo", "file_storage", "shared_file_storage"}
        _DB_KINDS = {"rds", "database", "managed_database"}

        has_compute = bool(ref_kinds & _COMPUTE_KINDS)
        has_storage = bool(ref_kinds & _STORAGE_KINDS)
        has_db = bool(ref_kinds & _DB_KINDS)

        # VM + disk in one item is wrong (they're separate business items)
        if has_compute and has_storage and not has_db:
            # Split: keep as compute, note the storage was separated
            downgraded_notes = list(cand.composition_notes)
            downgraded_notes.append("Downgraded: VM+storage mixed — keeping compute only.")
            cand = cand.model_copy(update={"composition_notes": downgraded_notes})
            # Filter refs to compute-only
            valid_refs = [r for r in valid_refs if agg_by_id.get(r, {}).get("resource_kind", "") in _COMPUTE_KINDS]
            if not valid_refs:
                continue  # Drop this candidate entirely

        # Step 4+: recompute every exported field from the final refs so the
        # final item stays consistent after any filtering/downgrade.
        (
            resource_kind,
            _display_items,
            source_monthly_total,
            source_service_name,
            display_vendor,
            source_quantity,
            source_pricing_basis,
            huawei_monthly_total_usd,
            huawei_product,
            huawei_quantity,
            status,
            manual_review_reason,
            composition_notes,
            huawei_spec_summary,
            huawei_unit_price_usd,
            huawei_billing_basis,
            source_config_summary,
        ) = _recompute_candidate_from_refs(
            cand,
            valid_refs,
            agg_by_id,
            qls_by_req_id,
            unquoted_ids,
            blocker_ids,
        )

        counter += 1
        final_items.append(_normalize_final_quote_item_for_export(CloudBillingFinalQuoteItem(
            item_id=f"fqi-llm-{counter}",
            vendor=display_vendor,
            resource_kind=resource_kind,
            source_service_family=cand_raw.get("source_service_family"),
            source_service_name=source_service_name,
            source_config_summary=source_config_summary,
            source_quantity=source_quantity,
            source_pricing_basis=source_pricing_basis,
            source_monthly_total_usd=source_monthly_total,
            huawei_product=huawei_product,
            huawei_spec_summary=huawei_spec_summary,
            huawei_quantity=huawei_quantity,
            huawei_unit_price_usd=huawei_unit_price_usd,
            huawei_billing_basis=huawei_billing_basis,
            huawei_monthly_total_usd=huawei_monthly_total_usd,
            status=status,
            composition_notes=composition_notes,
            source_item_ids=valid_refs,
            manual_review_reason=manual_review_reason,
        )))

    return final_items


# ---------------------------------------------------------------------------
# LLM composition node (Phase 10B)
# ---------------------------------------------------------------------------


def compose_final_billing_quote_items_with_llm(state: FlexibleQuoteState) -> FlexibleQuoteState:
    """Compose final billing quotation items with LLM-first + deterministic fallback.

    Level 1 (primary): LLM-first composition from raw billing rows.
    Level 2 (optional fallback): Phase 10 aggregated-item LLM composition.
    Level 3 (fallback): Deterministic rule-based composer.

    The LLM decides grouping and naming; deterministic rules validate,
    price, and correct the output.
    """
    from app.flexible_workflow import _append_audit, _report_progress

    _report_progress(state, "compose_final_billing_quote_items_with_llm", "running",
                     "Composing final quotation items (LLM-first).")

    agg_items = state.get("llm_aggregated_billing_items", [])
    quote_lines_raw = state.get("quote_lines", [])
    requirements_raw = state.get("requirements", [])
    quote_context = state.get("quote_context", {})

    # ── Level 1: LLM-first from raw billing rows ──
    billing_rows = _build_llm_first_billing_rows(state)
    if billing_rows:
        test_families = _get_llm_first_test_families()
        llm_rows = _filter_billing_rows_for_test_families(billing_rows, test_families)
        if test_families:
            state["audit_log"] = _append_audit(
                state,
                "compose_final_billing_quote_items_with_llm",
                f"LLM-first test mode active for families={sorted(test_families)}: {len(llm_rows)}/{len(billing_rows)} rows selected.",
            )
        else:
            llm_rows = billing_rows

        if not llm_rows:
            state["audit_log"] = _append_audit(
                state,
                "compose_final_billing_quote_items_with_llm",
                "LLM-first test mode selected 0 rows — using deterministic fallback.",
            )
            return compose_final_billing_quote_items(state)

        prompt_chars = _estimate_llm_first_prompt_chars(llm_rows, quote_lines_raw, quote_context)
        timeout_seconds = _get_billing_final_composition_timeout_seconds()
        state["audit_log"] = _append_audit(
            state,
            "compose_final_billing_quote_items_with_llm",
            f"LLM-first request: {len(llm_rows)} rows, {len(quote_lines_raw)} quote lines, ~{prompt_chars} chars, timeout={timeout_seconds}s.",
        )
        candidates_raw = _compose_final_billing_llm_first(
            llm_rows, quote_lines_raw, quote_context,
        )
        if candidates_raw is not None:
            final_items = _validate_and_enrich_llm_first_candidates(
                candidates_raw,
                llm_rows,
                quote_lines_raw,
                agg_items,
                state.get("unquoted_items", []),
                state.get("quote_blockers", []),
            )
            if final_items:
                if test_families:
                    state["audit_log"] = _append_audit(
                        state,
                        "compose_final_billing_quote_items_with_llm",
                        f"LLM-first test succeeded for families={sorted(test_families)}: {len(candidates_raw)} candidates → {len(final_items)} final items. Using deterministic full output for the complete invoice.",
                    )
                    return compose_final_billing_quote_items(state)
                state["llm_composition_candidates"] = candidates_raw
                state["final_billing_quote_items"] = [fi.model_dump() for fi in final_items]
                state["audit_log"] = _append_audit(state, "compose_final_billing_quote_items_with_llm",
                    f"LLM-first composition: {len(candidates_raw)} candidates → {len(final_items)} final items.")
                # Audit: run deterministic for comparison
                det_state = compose_final_billing_quote_items(dict(state))
                det_items = det_state.get("final_billing_quote_items", [])
                if det_items:
                    state["audit_log"] = _append_audit(state, "compose_final_billing_quote_items_with_llm",
                        f"Deterministic comparison: {len(det_items)} items.")
                return state

        if not _is_agg_llm_fallback_enabled():
            state["audit_log"] = _append_audit(
                state,
                "compose_final_billing_quote_items_with_llm",
                "LLM-first composition failed — skipping aggregated-item LLM and using deterministic fallback.",
            )
            state["audit_log"] = _append_audit(state, "compose_final_billing_quote_items_with_llm",
                "LLM composition failed — using deterministic fallback.")
            return compose_final_billing_quote_items(state)

        state["audit_log"] = _append_audit(state, "compose_final_billing_quote_items_with_llm",
            "LLM-first composition failed — trying aggregated-item LLM.")

    # ── Level 2: Phase 10 aggregated-item LLM composition ──
    candidates_raw = _compose_final_billing_with_llm(
        agg_items, quote_lines_raw, quote_context,
    )
    if candidates_raw is not None:
        final_items = _validate_and_enrich_llm_final_candidates(
            candidates_raw,
            agg_items,
            quote_lines_raw,
            requirements_raw,
            state.get("unquoted_items", []),
            state.get("quote_blockers", []),
        )
        if final_items:
            state["llm_composition_candidates"] = candidates_raw
            state["final_billing_quote_items"] = [fi.model_dump() for fi in final_items]
            state["audit_log"] = _append_audit(state, "compose_final_billing_quote_items_with_llm",
                f"Aggregated-item LLM composition: {len(candidates_raw)} candidates → {len(final_items)} final items.")
            return state

    # ── Level 3: Deterministic fallback ──
    state["audit_log"] = _append_audit(state, "compose_final_billing_quote_items_with_llm",
        "LLM composition failed — using deterministic fallback.")

    det_state = compose_final_billing_quote_items(state)
    state["final_billing_quote_items"] = det_state.get("final_billing_quote_items", [])
    state["llm_composition_candidates"] = []
    return state


# ---------------------------------------------------------------------------
# Main composition node (Phase 8B)
# ---------------------------------------------------------------------------

def compose_final_billing_quote_items(state: FlexibleQuoteState) -> FlexibleQuoteState:
    """Compose internal quote_lines into customer-readable final quotation items.

    This is the third layer in the Cloud Billing pipeline:
      1. Raw billing lines
      2. Aggregated billing items → quote_lines
      3. Final quotation items  ← this function

    The composition uses unified cross-cloud rules based on resource_kind,
    not vendor-specific SKUs. Azure/AWS/GCP all walk the same logic;
    only the input field names differ.
    """
    from app.flexible_workflow import _append_audit, _report_progress

    _report_progress(state, "compose_final_billing_quote_items", "running",
                     "Composing final billing quotation items.")

    agg_items = state.get("llm_aggregated_billing_items", [])
    quote_lines_raw = state.get("quote_lines", [])
    requirements_raw = state.get("requirements", [])

    # Build a lookup from requirement_item_id → RequirementItem
    req_by_id: dict[str, RequirementItem] = {}
    for r in requirements_raw:
        try:
            ri = RequirementItem.model_validate(r)
            req_by_id[ri.item_id] = ri
        except Exception:
            pass

    # Build a lookup from requirement_item_id → FlexibleQuoteLine
    ql_by_req_id: dict[str, FlexibleQuoteLine] = {}
    for ql in quote_lines_raw:
        try:
            line = FlexibleQuoteLine.model_validate(ql)
            ql_by_req_id[line.requirement_item_id] = line
        except Exception:
            pass

    # Collect unquoted and blocker IDs
    unquoted_ids: set[str] = set()
    for uq in state.get("unquoted_items", []):
        unquoted_ids.add(uq.get("item_id", ""))

    blocker_ids: set[str] = set()
    for blk in state.get("quote_blockers", []):
        blocker_ids.add(blk.get("item_id", ""))

    # ── Step 1: Build intermediate items from llm_aggregated_billing_items ──
    # Each aggregated billing item becomes one intermediate item with
    # source and Huawei fields populated from both the aggregation and
    # the corresponding quote_line (if priced).
    intermediate_items: list[dict[str, Any]] = []

    for idx, agg in enumerate(agg_items):
        item_id = agg.get("source_group_ids", [f"agg-{idx}"])
        if isinstance(item_id, list):
            item_id = item_id[0] if item_id else f"agg-{idx}"

        kind_raw = agg.get("resource_kind", "unsupported")
        huawei_product = agg.get("huawei_product")
        vendor = _normalize_vendor(agg.get("vendor"))
        resource_kind = _classify_resource_kind(kind_raw, huawei_product)

        # Source fields
        source_service_name = agg.get("aggregate_label", "") or agg.get("product_type", "")
        source_service_family = agg.get("product_family")
        source_sku_hint = agg.get("source_sku_hint", "")
        spec_hint = agg.get("huawei_spec_hint", "") or source_sku_hint
        source_config_summary = spec_hint if spec_hint else None
        source_quantity = agg.get("derived_quantity")
        source_pricing_basis = agg.get("derived_unit")
        source_monthly_total = agg.get("amount")

        # Find corresponding quote line via requirement item
        # The requirement item_id for aggregated items follows the pattern
        # "billing-agg::{source_file}::{idx}" (see _build_billing_detail_rows)
        source_file = agg.get("source_file", "")
        req_item_id = f"billing-agg::{source_file}::{idx}"
        ql = ql_by_req_id.get(req_item_id)

        # Huawei fields from quote line if available
        huawei_spec_summary = None
        huawei_quantity = None
        huawei_unit_price_usd = None
        huawei_billing_basis = None
        huawei_monthly_total_usd = None
        status: FinalQuoteItemStatus = "unquoted"
        manual_review_reason = None

        if ql:
            huawei_product = ql.product
            huawei_spec_summary = ql.matched_sku or ql.matched_tier
            huawei_quantity = ql.quantity
            huawei_unit_price_usd = ql.unit_price
            huawei_billing_basis = ql.billing_mode
            huawei_monthly_total_usd = ql.monthly_price
            status = "quoted"
        elif agg.get("needs_manual_review"):
            status = "manual_review"
            manual_review_reason = "Aggregated item flagged for manual review."
        elif req_item_id in blocker_ids:
            status = "manual_review"
            manual_review_reason = "Item is a quote blocker."

        intermediate_items.append({
            "source_item_id": req_item_id,
            "vendor": vendor,
            "resource_kind": resource_kind,
            "source_service_name": source_service_name,
            "source_service_family": source_service_family,
            "source_config_summary": source_config_summary,
            "source_quantity": source_quantity,
            "source_pricing_basis": source_pricing_basis,
            "source_monthly_total_usd": source_monthly_total,
            "huawei_product": huawei_product,
            "huawei_spec_summary": huawei_spec_summary,
            "huawei_quantity": huawei_quantity,
            "huawei_unit_price_usd": huawei_unit_price_usd,
            "huawei_billing_basis": huawei_billing_basis,
            "huawei_monthly_total_usd": huawei_monthly_total_usd,
            "status": status,
            "manual_review_reason": manual_review_reason,
        })

    # ── Step 2: If no aggregated items, build from quote_lines directly ──
    if not intermediate_items and quote_lines_raw:
        for ql in quote_lines_raw:
            try:
                line = FlexibleQuoteLine.model_validate(ql)
            except Exception:
                continue
            req = req_by_id.get(line.requirement_item_id)
            vendor = "Unknown"
            source_service_name = req.raw_product_name if req else line.product
            source_service_family = None
            source_config_summary = None
            resource_kind = _classify_resource_kind(None, line.product)

            if req:
                if req.spec and hasattr(req.spec, "sku") and req.spec.sku:
                    source_config_summary = req.spec.sku

            intermediate_items.append({
                "source_item_id": line.requirement_item_id,
                "vendor": vendor,
                "resource_kind": resource_kind,
                "source_service_name": source_service_name,
                "source_service_family": source_service_family,
                "source_config_summary": source_config_summary,
                "source_quantity": line.quantity,
                "source_pricing_basis": line.billing_mode,
                "source_monthly_total_usd": None,
                "huawei_product": line.product,
                "huawei_spec_summary": line.matched_sku or line.matched_tier,
                "huawei_quantity": line.quantity,
                "huawei_unit_price_usd": line.unit_price,
                "huawei_billing_basis": line.billing_mode,
                "huawei_monthly_total_usd": line.monthly_price,
                "status": "quoted",
                "manual_review_reason": None,
            })

    # ── Step 3: Group by resource_kind, then by composition key ──
    grouped: dict[CloudBillingResourceKind, dict[tuple, list[dict[str, Any]]]] = {}
    for item in intermediate_items:
        rk = item["resource_kind"]
        if rk not in grouped:
            grouped[rk] = {}

        if rk == "platform_paas_misc":
            # All platform items merge into one per vendor
            key = ("platform_paas_misc", item.get("vendor", "Unknown"))
        else:
            builder = _COMPOSITION_KEY_BUILDERS.get(rk)
            if builder:
                key = builder(item)
            else:
                # Fallback: each item stays separate
                key = (rk, item.get("source_item_id", ""))

        if key not in grouped[rk]:
            grouped[rk][key] = []
        grouped[rk][key].append(item)

    # ── Step 4: Merge each group into a final item ──
    final_items: list[CloudBillingFinalQuoteItem] = []
    counter = 0
    for rk in sorted(grouped.keys()):
        for key in sorted(grouped[rk].keys(), key=str):
            items = grouped[rk][key]
            counter += 1
            final_item = _normalize_final_quote_item_for_export(_merge_items_into_final(rk, items, counter))
            final_items.append(final_item)

    message = (
        f"Composed {len(intermediate_items)} intermediate item(s) into "
        f"{len(final_items)} final quotation item(s)."
    )
    _report_progress(state, "compose_final_billing_quote_items", "completed", message)

    return {
        "final_billing_quote_items": [fi.model_dump() for fi in final_items],
        "audit_log": _append_audit(state, "compose_final_billing_quote_items", message),
    }


# ── Cloud Billing preview graph ─────────────────────────────────────────────────


def build_cloud_billing_preview_graph():
    """Build the cloud billing quote preview pipeline.

    Pipeline: ingest → load_pricebook → parse → extract →
              normalize → deduplicate → map → validate → price → quote →
              compose_final_billing_quote_items_with_llm → summarize

    Phase 5A: understand_input is intentionally omitted — billing extraction
    uses _extract_billing_requirement_items which does not need schema understanding.

    Phase 8B: compose_final_billing_quote_items added between quote_items
    and summarize_quote to produce customer-readable final quotation items.

    Phase 10B: compose_final_billing_quote_items_with_llm replaces
    compose_final_billing_quote_items as the primary path, with deterministic
    composer kept as fallback inside the LLM node.
    """
    graph = StateGraph(FlexibleQuoteState)
    graph.add_node("ingest_files", ingest_files)
    graph.add_node("load_pricebook", load_pricebook)
    graph.add_node("parse_documents", parse_documents)
    graph.add_node("extract_requirement_items", extract_cloud_billing_requirement_items)
    graph.add_node("normalize_requirements", normalize_requirements)
    graph.add_node("deduplicate_items", deduplicate_items)
    graph.add_node("map_to_huawei_product", map_to_huawei_product)
    graph.add_node("validate_quote_readiness", validate_quote_readiness)
    graph.add_node("return_blockers", return_blockers)
    graph.add_node("resolve_price_components", resolve_price_components)
    graph.add_node("quote_items", quote_items)
    graph.add_node("compose_final_billing_quote_items_with_llm", compose_final_billing_quote_items_with_llm)
    graph.add_node("summarize_quote", summarize_quote)

    graph.add_edge(START, "ingest_files")
    graph.add_edge("ingest_files", "load_pricebook")
    graph.add_edge("load_pricebook", "parse_documents")
    graph.add_edge("parse_documents", "extract_requirement_items")
    graph.add_edge("extract_requirement_items", "normalize_requirements")
    graph.add_edge("normalize_requirements", "deduplicate_items")
    graph.add_edge("deduplicate_items", "map_to_huawei_product")
    graph.add_edge("map_to_huawei_product", "validate_quote_readiness")
    graph.add_conditional_edges("validate_quote_readiness", _route_after_validation, {"needs_input": "return_blockers", "ready": "resolve_price_components"})
    graph.add_edge("return_blockers", "summarize_quote")
    graph.add_edge("resolve_price_components", "quote_items")
    graph.add_edge("quote_items", "compose_final_billing_quote_items_with_llm")
    graph.add_edge("compose_final_billing_quote_items_with_llm", "summarize_quote")
    graph.add_edge("summarize_quote", END)
    return graph.compile()


# ── Cloud Billing review graph ──────────────────────────────────────────────────


def build_cloud_billing_review_graph():
    """Build the cloud billing quote review pipeline (after manual feedback)."""
    graph = StateGraph(FlexibleQuoteState)
    graph.add_node("incorporate_feedback", incorporate_feedback)
    graph.add_node("validate_quote_readiness", validate_quote_readiness)
    graph.add_node("return_blockers", return_blockers)
    graph.add_node("resolve_price_components", resolve_price_components)
    graph.add_node("quote_items", quote_items)
    graph.add_node("compose_final_billing_quote_items_with_llm", compose_final_billing_quote_items_with_llm)
    graph.add_node("summarize_quote", summarize_quote)

    graph.add_edge(START, "incorporate_feedback")
    graph.add_edge("incorporate_feedback", "validate_quote_readiness")
    graph.add_conditional_edges("validate_quote_readiness", _route_after_validation, {"needs_input": "return_blockers", "ready": "resolve_price_components"})
    graph.add_edge("return_blockers", "summarize_quote")
    graph.add_edge("resolve_price_components", "quote_items")
    graph.add_edge("quote_items", "compose_final_billing_quote_items_with_llm")
    graph.add_edge("compose_final_billing_quote_items_with_llm", "summarize_quote")
    graph.add_edge("summarize_quote", END)
    return graph.compile()


# ── Cloud Billing export graph ──────────────────────────────────────────────────


def build_cloud_billing_export_graph():
    """Build the cloud billing quote export pipeline (review → export workbook).

    Uses the billing-specific export template (Quotation, Summary, HWC,
    ECS, Información) and LLM-driven composition.
    """
    graph = StateGraph(FlexibleQuoteState)
    graph.add_node("incorporate_feedback", incorporate_feedback)
    graph.add_node("validate_quote_readiness", validate_quote_readiness)
    graph.add_node("return_blockers", return_blockers)
    graph.add_node("resolve_price_components", resolve_price_components)
    graph.add_node("quote_items", quote_items)
    graph.add_node("compose_final_billing_quote_items_with_llm", compose_final_billing_quote_items_with_llm)
    graph.add_node("summarize_quote", summarize_quote)
    graph.add_node("export_cloud_billing_workbook", export_cloud_billing_workbook)

    graph.add_edge(START, "incorporate_feedback")
    graph.add_edge("incorporate_feedback", "validate_quote_readiness")
    graph.add_conditional_edges("validate_quote_readiness", _route_after_validation, {"needs_input": "return_blockers", "ready": "resolve_price_components"})
    graph.add_edge("return_blockers", "summarize_quote")
    graph.add_edge("resolve_price_components", "quote_items")
    graph.add_edge("quote_items", "compose_final_billing_quote_items_with_llm")
    graph.add_edge("compose_final_billing_quote_items_with_llm", "summarize_quote")
    graph.add_edge("summarize_quote", "export_cloud_billing_workbook")
    graph.add_edge("export_cloud_billing_workbook", END)
    return graph.compile()


def export_cloud_billing_workbook(state: FlexibleQuoteState) -> FlexibleQuoteState:
    """Export a cloud billing workbook using the billing-specific template.

    This always uses the billing template export (Quotation, Summary, HWC,
    ECS, Información sheets), never the generic flexible export.
    """
    from app.flexible_workflow import _export_flexible_billing_template_workbook

    has_billing_state = bool(
        state.get("billing_lines")
        or state.get("llm_aggregated_billing_items")
        or state.get("mapped_billing_resources")
    )
    if not has_billing_state:
        raise ValueError("Cloud billing export requires billing-specific state from preview/review.")

    wb = _export_flexible_billing_template_workbook(state)
    return {"workbook": wb}


# ── Compiled graph instances ────────────────────────────────────────────────────

cloud_billing_preview_graph = build_cloud_billing_preview_graph()
cloud_billing_review_graph = build_cloud_billing_review_graph()
cloud_billing_export_graph = build_cloud_billing_export_graph()
