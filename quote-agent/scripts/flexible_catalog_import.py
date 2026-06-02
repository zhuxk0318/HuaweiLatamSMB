#!/usr/bin/env python3
r"""Flexible pricing catalog import tool.

Reads Huawei Cloud Price.xlsx, normalizes product/spec/region, validates,
and produces either a preview (normalized rows) or a catalog patch JSON.

Usage:
    # Preview normalized rows from Excel
    python3 scripts/flexible_catalog_import.py preview "/root/SMBReference/Huawei Cloud Price.xlsx"

    # Generate catalog patch JSON
    python3 scripts/flexible_catalog_import.py patch "/root/SMBReference/Huawei Cloud Price.xlsx" -o patch.json

    # Validate existing catalog consistency
    python3 scripts/flexible_catalog_import.py validate ../data/flexible-pricing-catalog.json

This is an OFFLINE maintenance tool. It does NOT directly overwrite the
production catalog. The intended workflow is:
    1. Run preview → review
    2. Run patch → review
    3. Manually apply approved patches to the catalog
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Product mapping: Excel product name → internal product key
# ---------------------------------------------------------------------------

PRODUCT_MAPPING: dict[str, str] = {
    "Elastic Volume Service(EVS)": "EVS",
    "Object Storage Service(OBS)": "OBS",
    "Scalable File Service Turbo(SFS Turbo)": "SFS Turbo",
    "Elastic IP(EIP)": "EIP",
    "Elastic Load Balance": "ELB",
    "NAT Gateway": "NAT Gateway",
    "Virtual Private Network": "VPN",
    "Direct Connect As A Service": "Direct Connect as a Service",
    "Relational Database Service(RDS)-Compute": "RDS",
    "Relational Database Service(RDS)-Storage": "RDS",
    "Document Database Service-Compute": "DDS",
    "Document Database Service-Storage": "DDS",
    "Data Warehouse Service(DWS) - Compute": "DWS",
    "Data Warehouse Service(DWS) - Hot Storage": "DWS",
    "Data Warehouse Service(DWS) - Cold Storage": "DWS",
    "DCS (for Redis)": "DCS",
    "Cloud Backup and Recovery": "CBR",
    "Cloud Firewall(CFW)": "CFW",
    "Host Security Service(HSS)": "HSS",
    "Web Application Firewall(WAF)": "WAF",
    "DataArts Studio": "DataArts Studio",
}

# Products we actively handle in flexible quoting
SUPPORTED_PRODUCTS: set[str] = {
    "EVS", "OBS", "SFS Turbo", "EIP", "ELB", "NAT Gateway", "VPN",
    "Direct Connect as a Service", "RDS", "DDS", "DWS", "DCS",
}

# ---------------------------------------------------------------------------
# Spec/SKU mapping: Excel disk-type/sub-product → catalog sku key
# ---------------------------------------------------------------------------

SPEC_MAPPING: dict[str, dict[str, str]] = {
    "EVS": {
        "General Purpose SSD V2": "gpssd-v2",
        "General Purpose SSD": "gpssd",
        "High I/O": "high-io",
        "Ultra-high I/O": "ultra-high-io",
        "Common I/O": "sas",
        "Extreme SSD": "extreme-ssd",
    },
    "OBS": {
        "standard": "obs-standard",
        "infrequent-access": "obs-infrequent-access",
    },
    "SFS Turbo": {
        "20MB/s/TiB": "sfs-turbo-20mbps-per-tib",
        "40MB/s/TiB": "sfs-turbo-40mbps-per-tib",
        "125MB/s/TiB": "sfs-turbo-125mbps-per-tib",
        "250MB/s/TiB": "sfs-turbo-250mbps-per-tib",
    },
    "NAT Gateway": {
        "Small": "nat-small",
        "Middle": "nat-middle",
        "Large": "nat-large",
        "Starter": "nat-small",
    },
    "VPN": {
        "Basic": "vpn-basic",
        "Professional 1": "vpn-professional-1",
        "Professional 2": "vpn-professional-2",
    },
    "Direct Connect as a Service": {
        "1GE": "dcas-1g",
        "10GE": "dcas-10g",
        "40GE": "dcas-40g",
        "100GE": "dcas-100g",
    },
    "EIP": {
        "By Traffic": "eip-by-traffic",
        "Shared": "eip-by-bandwidth-shared",
        "Enhanced 95": "eip-enhanced-95",
    },
    "ELB": {
        "Shared": "elb-shared",
        "Dedicated load balancer": "elb-dedicated",
    },
}

# ---------------------------------------------------------------------------
# Region mapping: Excel region name → internal region key
# ---------------------------------------------------------------------------

REGION_MAPPING: dict[str, str] = {
    "santiago": "chile",
    "satiago": "chile",  # typo in Excel
    "mexico": "mexico",
    "sao paulo": "brazil",
}

SUPPORTED_REGIONS: set[str] = {"chile", "mexico", "brazil"}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class NormalizedRow:
    """A single normalized price row from the Excel source."""
    source_product: str       # Original Excel product name
    product: str             # Internal product key
    sku: str                 # Internal sku key
    region: str              # Internal region key
    regions_from_excel: str  # Original Excel region string (may be multi-region)
    billing_mode: str        # "hourly" | "monthly" | "ri-1y" | "ri-2y" | "ri-3y"
    unit: str                # e.g. "GB-month", "gateway-month", "per-GB"
    price: float             # Numeric price in USD
    currency: str = "USD"
    raw_row: dict = field(default_factory=dict, repr=False)
    notes: str = ""


@dataclass
class ImportIssue:
    """A validation issue found during import."""
    severity: str   # "error" | "warning" | "skip"
    message: str
    row_index: int = -1
    raw_row: dict = field(default_factory=dict, repr=False)


@dataclass
class ImportResult:
    """Result of importing an Excel file."""
    normalized_rows: list[NormalizedRow] = field(default_factory=list)
    issues: list[ImportIssue] = field(default_factory=list)
    skipped_products: set[str] = field(default_factory=set)
    skipped_rows: int = 0

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def has_conflicts(self) -> bool:
        return any("conflict" in i.message.lower() for i in self.issues)


# ---------------------------------------------------------------------------
# Price parsing helpers
# ---------------------------------------------------------------------------

_PRICE_RE = re.compile(
    r"USD\s+"
    r"(?P<value>[\d,]+(?:\.\d+)?)"
    r"(?:\s+Price\s+per\s+(?P<unit_desc>[^.]+))?"
    r"(?:\s+/(?P<per_unit>[^.]+))?"
    r"|"
    r"(?P<free>[Ff]ree)"
)


def _parse_price(text: str | None) -> tuple[float | None, str]:
    """Parse a price cell like 'USD 0.076' or 'USD 0.000064 Price per GB-hour'.

    Returns (numeric_price, unit_description) or (None, "") if unparseable.
    Special: "Free" or "free" → (0.0, "free"), "--" → (None, "unavailable"),
    "N/A" → (None, "n/a").
    """
    if not text:
        return None, ""
    text = str(text).strip()
    if text.lower() in ("free",):
        return 0.0, "free"
    if text in ("--", "N/A", "n/a", ""):
        return None, "unavailable"

    # Try "USD <number>" pattern
    m = re.match(r"USD\s+([\d,]+(?:\.\d+)?)", text)
    if m:
        raw = m.group(1).replace(",", "")
        try:
            return float(raw), ""
        except ValueError:
            return None, f"unparseable: {text}"

    # Try bare number
    try:
        return float(text.replace(",", "")), ""
    except ValueError:
        return None, f"unparseable: {text}"


def _parse_price_with_unit(text: str | None) -> tuple[float | None, str]:
    """Parse price cells that include unit info like 'USD 0.000064 Price per GB-hour'."""
    if not text:
        return None, ""
    text = str(text).strip()
    if text.lower() in ("free",):
        return 0.0, "free"
    if text in ("--", "N/A", "n/a", ""):
        return None, "unavailable"

    # "USD <number> Price per <unit>"
    m = re.match(r"USD\s+([\d,]+(?:\.\d+)?)\s+Price\s+per\s+(.+)", text, re.I)
    if m:
        raw = m.group(1).replace(",", "")
        try:
            return float(raw), m.group(2).strip()
        except ValueError:
            return None, f"unparseable: {text}"

    # "USD <number> /<unit>"
    m = re.match(r"USD\s+([\d,]+(?:\.\d+)?)\s*/(.+)", text, re.I)
    if m:
        raw = m.group(1).replace(",", "")
        try:
            return float(raw), f"per-{m.group(2).strip()}"
        except ValueError:
            return None, f"unparseable: {text}"

    # Plain "USD <number>"
    return _parse_price(text)


# ---------------------------------------------------------------------------
# Region expansion: multi-region rows → individual regions
# ---------------------------------------------------------------------------

def _expand_regions(region_text: str) -> tuple[list[str], list[str]]:
    """Expand Excel region text into a list of internal region keys.

    Multi-region strings like 'Santiago&Mexico' or 'Santiago & Mexico & Sao Paulo'
    are treated as "same price applies to multiple regions" and expanded into
    separate region keys.

    Returns:
        (regions, warnings) where regions is the list of mapped internal keys
        and warnings is a list of messages for any unmapped tokens.
    """
    text = region_text.strip()
    if not text:
        return [], []

    # Normalize: replace ' & ' or '&' with a consistent separator,
    # then split.  This handles both "Santiago&Mexico" and "Santiago & Mexico".
    # First collapse spaces around &
    text = re.sub(r"\s*&\s*", "&", text)
    lowered = text.lower()

    # If the entire string is a single known key, return it directly
    if lowered in REGION_MAPPING:
        return [REGION_MAPPING[lowered]], []

    # Split by & and map each token
    tokens = [t.strip() for t in lowered.split("&") if t.strip()]
    regions: list[str] = []
    warnings: list[str] = []

    for token in tokens:
        mapped = REGION_MAPPING.get(token)
        if mapped:
            if mapped not in regions:
                regions.append(mapped)
        else:
            warnings.append(f"Unknown region token: '{token}' in '{region_text}'")

    return regions, warnings


# ---------------------------------------------------------------------------
# Core normalize function
# ---------------------------------------------------------------------------

def normalize_row(
    product_key: str,
    region: str,
    regions_from_excel: str,
    sku: str,
    billing_mode: str,
    unit: str,
    price: float,
    raw_row: dict | None = None,
    notes: str = "",
) -> NormalizedRow:
    """Create a NormalizedRow with all fields filled."""
    return NormalizedRow(
        source_product=product_key,
        product=product_key,
        sku=sku,
        region=region,
        regions_from_excel=regions_from_excel,
        billing_mode=billing_mode,
        unit=unit,
        price=price,
        raw_row=raw_row or {},
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Excel row parsing — product-specific parsers
# ---------------------------------------------------------------------------

def _parse_evs_row(row_vals: list, region: str, regions_from_excel: str, row_idx: int) -> list[tuple[NormalizedRow, ImportIssue | None]]:
    """Parse EVS rows: Disk Type / Billing Item / ... / Hourly / Monthly / 1Y / 2Y / 3Y."""
    results = []
    disk_type = str(row_vals[2] or "").strip()
    billing_item = str(row_vals[3] or "").strip()

    # Skip header rows
    if disk_type == "Disk Type" or billing_item == "Billing Item":
        return []

    sku = SPEC_MAPPING.get("EVS", {}).get(disk_type)
    if not sku:
        issue = ImportIssue("skip", f"EVS: unknown disk type '{disk_type}'", row_idx)
        return [(NormalizedRow(
            source_product="EVS", product="EVS", sku=disk_type, region=region,
            regions_from_excel=regions_from_excel, billing_mode="", unit="",
            price=0, notes=f"unknown disk type: {disk_type}",
        ), issue)]

    if billing_item != "Capacity":
        # Only import Capacity rows (IOPS/Throughput are extras)
        return []

    # Parse prices: col 6=Hourly, 7=Monthly, 8=1Y, 9=2Y, 10=3Y
    price_cols = [
        (6, "hourly", "GB-hour"),
        (7, "monthly", "GB-month"),
        (8, "ri-1y", "GB-month"),
        (9, "ri-2y", "GB-month"),
        (10, "ri-3y", "GB-month"),
    ]
    for col_idx, mode, unit in price_cols:
        if col_idx >= len(row_vals):
            continue
        price, _ = _parse_price(row_vals[col_idx] if col_idx < len(row_vals) else None)
        if price is not None:
            results.append((normalize_row("EVS", region, regions_from_excel, sku, mode, unit, price), None))

    return results


def _parse_obs_storage_row(row_vals: list, region: str, regions_from_excel: str, row_idx: int) -> list[tuple[NormalizedRow, ImportIssue | None]]:
    """Parse OBS storage rows: Category/Billing Item/Standard/Infrequent Access/Archive."""
    category = str(row_vals[2] or "").strip()
    billing_item = str(row_vals[3] or "").strip()

    if category in ("Category", "Request", "Traffic", "Internet outbound traffic", "Data restoration", "Data processing"):
        return []
    if category != "Storage":
        return []
    if "Data stored" not in billing_item:
        return []

    results = []
    # col 4=Standard price, col 5=Infrequent Access price
    for col_idx, obs_tier in [(4, "standard"), (5, "infrequent-access")]:
        if col_idx >= len(row_vals):
            continue
        price_text = row_vals[col_idx]
        if not price_text:
            continue
        # Extract price from "USD 0.021 /GB per month" format
        m = re.match(r"USD\s+([\d,]+(?:\.\d+)?)\s*/GB\s+per\s+month", str(price_text), re.I)
        if m:
            price = float(m.group(1).replace(",", ""))
            sku = SPEC_MAPPING.get("OBS", {}).get(obs_tier, f"obs-{obs_tier}")
            results.append((normalize_row("OBS", region, regions_from_excel, sku, "monthly", "GB-month", price), None))

    return results


def _parse_sfs_turbo_row(row_vals: list, region: str, regions_from_excel: str, row_idx: int) -> list[tuple[NormalizedRow, ImportIssue | None]]:
    """Parse SFS Turbo rows: spec / Billing Factor / Price."""
    spec = str(row_vals[2] or "").strip()
    billing_factor = str(row_vals[3] or "").strip()

    sku = SPEC_MAPPING.get("SFS Turbo", {}).get(spec)
    if not sku:
        return []
    if billing_factor == "Billing Factor" or billing_factor == "Billing Item":
        return []

    results = []
    # Hourly price column (col 4 for SFS Turbo has "USD <price> Price per GB-hour")
    if "Storage space usage" in billing_factor:
        price, unit_desc = _parse_price_with_unit(row_vals[4] if len(row_vals) > 4 else None)
        if price is not None:
            results.append((normalize_row("SFS Turbo", region, regions_from_excel, sku, "hourly", "GB-hour", price), None))

    # Monthly/RI rows (different layout: col 4=Monthly, 5=1Y, 6=2Y, 7=3Y)
    if billing_factor.startswith("USD"):
        price, _ = _parse_price(billing_factor)
        if price is not None:
            results.append((normalize_row("SFS Turbo", region, regions_from_excel, sku, "monthly", "GB-month", price), None))

    return results


def _parse_nat_vpn_dc_row(product: str, row_vals: list, region: str, regions_from_excel: str, row_idx: int) -> list[tuple[NormalizedRow, ImportIssue | None]]:
    """Parse NAT Gateway / VPN / Direct Connect rows."""
    spec = str(row_vals[2] or "").strip()
    sub_item = str(row_vals[3] or "").strip() if len(row_vals) > 3 else ""

    sku = SPEC_MAPPING.get(product, {}).get(spec)
    if not sku:
        # Try sub_item for VPN
        if product == "VPN":
            sku = SPEC_MAPPING.get("VPN", {}).get(sub_item)
        if not sku:
            return []

    # Skip header/label rows
    if spec in ("Port Speed", "Type", "Edition", "WAF Mode", "Category", "Billing Item"):
        return []
    if sub_item in ("Billing Item", "Hourly", "Monthly", "VPN Connection Groups"):
        return []

    results = []
    # Price layout varies; look for USD price patterns
    for col_idx in range(4, min(len(row_vals), 11)):
        price, unit_desc = _parse_price_with_unit(row_vals[col_idx])
        if price is not None and price > 0:
            # Determine billing mode from column position
            if col_idx == 4:
                mode = "hourly"
            elif col_idx == 5:
                mode = "monthly"
            elif col_idx == 6:
                mode = "ri-1y"
            elif col_idx == 7:
                mode = "ri-2y"
            else:
                mode = "ri-3y"
            unit = "gateway-month" if product in ("VPN", "NAT Gateway") else "port-month"
            if mode == "hourly":
                unit = unit.replace("month", "hour")
            results.append((normalize_row(product, region, regions_from_excel, sku, mode, unit, price), None))
            break  # Take first valid price

    return results


def _parse_eip_row(row_vals: list, region: str, regions_from_excel: str, row_idx: int) -> list[tuple[NormalizedRow, ImportIssue | None]]:
    """Parse EIP rows."""
    spec = str(row_vals[2] or "").strip()
    billing_item = str(row_vals[3] or "").strip() if len(row_vals) > 3 else ""

    sku = SPEC_MAPPING.get("EIP", {}).get(spec)
    if not sku:
        return []
    if billing_item in ("Billing Item",):
        return []

    results = []
    for col_idx in range(4, min(len(row_vals), 11)):
        price, unit_desc = _parse_price_with_unit(row_vals[col_idx])
        if price is not None and price > 0:
            mode = "monthly" if col_idx >= 5 else "hourly"
            unit = "GB" if "traffic" in spec.lower() else "Mbps-month"
            results.append((normalize_row("EIP", region, regions_from_excel, sku, mode, unit, price), None))
            break

    return results


# ---------------------------------------------------------------------------
# Main import function
# ---------------------------------------------------------------------------

def import_excel(xlsx_path: str) -> ImportResult:
    """Import Huawei Cloud Price.xlsx and return normalized rows + issues."""
    from openpyxl import load_workbook

    result = ImportResult()
    wb = load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active

    current_product_key: str | None = None

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        row_vals = list(row) + [None] * 14  # pad to at least 14 cols
        region_text = str(row_vals[0] or "").strip()
        product_text = str(row_vals[1] or "").strip()

        # Skip empty rows
        if not region_text and not product_text:
            continue

        # Track current product context
        if product_text:
            current_product_key = PRODUCT_MAPPING.get(product_text)

        if not current_product_key:
            # Unknown product — skip
            if product_text and product_text not in PRODUCT_MAPPING:
                result.skipped_products.add(product_text)
            continue

        if current_product_key not in SUPPORTED_PRODUCTS:
            result.skipped_products.add(product_text or current_product_key)
            continue

        # Expand regions
        regions, region_warnings = _expand_regions(region_text) if region_text else ([], [])
        for rw in region_warnings:
            result.issues.append(ImportIssue("warning", rw, row_idx))
        if not regions:
            continue

        # Parse product-specific rows
        for region in regions:
            if region not in SUPPORTED_REGIONS:
                continue

            parsed: list[tuple[NormalizedRow, ImportIssue | None]] = []

            if current_product_key == "EVS":
                parsed = _parse_evs_row(row_vals, region, region_text, row_idx)
            elif current_product_key == "OBS":
                parsed = _parse_obs_storage_row(row_vals, region, region_text, row_idx)
            elif current_product_key == "SFS Turbo":
                parsed = _parse_sfs_turbo_row(row_vals, region, region_text, row_idx)
            elif current_product_key in ("NAT Gateway", "VPN", "Direct Connect as a Service"):
                parsed = _parse_nat_vpn_dc_row(current_product_key, row_vals, region, region_text, row_idx)
            elif current_product_key == "EIP":
                parsed = _parse_eip_row(row_vals, region, region_text, row_idx)

            for norm_row, issue in parsed:
                result.normalized_rows.append(norm_row)
                if issue:
                    result.issues.append(issue)

    wb.close()

    # Post-import validation
    _validate_result(result)

    return result


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_result(result: ImportResult) -> None:
    """Run validation checks on the import result."""
    # Check for duplicate/conflicting entries
    seen: dict[tuple[str, str, str, str], float] = {}  # (product, sku, region, billing_mode) → price
    for row in result.normalized_rows:
        key = (row.product, row.sku, row.region, row.billing_mode)
        if key in seen:
            if abs(seen[key] - row.price) > 0.001:
                result.issues.append(ImportIssue(
                    "error",
                    f"Price conflict: {row.product}/{row.sku}/{row.region}/{row.billing_mode}: "
                    f"existing={seen[key]}, new={row.price}",
                ))
        else:
            seen[key] = row.price

    # Check for empty SKUs
    for row in result.normalized_rows:
        if not row.sku:
            result.issues.append(ImportIssue("error", f"Empty SKU for product={row.product} region={row.region}"))

    # Check for unsupported regions
    for row in result.normalized_rows:
        if row.region not in SUPPORTED_REGIONS:
            result.issues.append(ImportIssue("warning", f"Unsupported region: {row.region} for {row.product}/{row.sku}"))


# ---------------------------------------------------------------------------
# Catalog patch generation
# ---------------------------------------------------------------------------

def generate_patch(result: ImportResult) -> dict[str, Any]:
    """Generate a catalog patch JSON from the import result.

    The patch contains only monthly-priced rows (the primary billing mode
    for the flexible catalog). Hourly/RI rows are included as metadata.
    """
    patch_items = []
    for row in result.normalized_rows:
        if row.billing_mode != "monthly":
            continue
        patch_items.append({
            "product": row.product,
            "region": row.region,
            "sku": row.sku,
            "family": row.product,  # simplified
            "tier": row.sku,
            "billing_mode": "monthly",
            "unit": row.unit,
            "price": row.price,
            "currency": row.currency,
            "source": "Huawei Cloud Price.xlsx",
            "imported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    return {
        "patch_metadata": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "Huawei Cloud Price.xlsx",
            "total_items": len(patch_items),
            "issues": len(result.issues),
            "errors": sum(1 for i in result.issues if i.severity == "error"),
            "skipped_products": sorted(result.skipped_products),
        },
        "items": patch_items,
        "issues": [{"severity": i.severity, "message": i.message} for i in result.issues],
    }


def patch_dry_run_summary(patch: dict[str, Any], catalog_path: str) -> dict[str, Any]:
    """Compare a patch against the existing catalog and return a summary.

    Returns counts of: new items, updated items (same key, different price),
    unchanged items, skipped items, conflicts, and warnings.
    """
    with open(catalog_path) as f:
        catalog = json.load(f)

    # Index existing catalog by (product, sku, region, billing_mode)
    existing: dict[tuple, float] = {}
    for item in catalog.get("items", []):
        key = (item.get("product"), item.get("sku"), item.get("region"), item.get("billing_mode"))
        existing[key] = item.get("price", 0)

    new_count = 0
    updated_count = 0
    unchanged_count = 0

    for item in patch.get("items", []):
        key = (item.get("product"), item.get("sku"), item.get("region"), item.get("billing_mode"))
        price = item.get("price", 0)
        if key not in existing:
            new_count += 1
        elif abs(existing[key] - price) > 0.001:
            updated_count += 1
        else:
            unchanged_count += 1

    patch_meta = patch.get("patch_metadata", {})
    return {
        "new_items": new_count,
        "updated_items": updated_count,
        "unchanged_items": unchanged_count,
        "total_patch_items": len(patch.get("items", [])),
        "conflicts": patch_meta.get("errors", 0),
        "warnings": patch_meta.get("issues", 0) - patch_meta.get("errors", 0),
        "skipped_products": patch_meta.get("skipped_products", []),
    }


# ---------------------------------------------------------------------------
# Catalog consistency validation
# ---------------------------------------------------------------------------

def validate_catalog(catalog_path: str) -> list[ImportIssue]:
    """Validate an existing catalog JSON file for consistency.

    Checks:
      - Structural integrity: product/sku/region non-empty, price numeric
      - Critical products exist
      - Critical SKUs exist per region
      - Region coverage for critical products
      - No duplicate entries with conflicting prices
      - No unknown region keys
    """
    issues = []

    with open(catalog_path) as f:
        data = json.load(f)

    items = data.get("items", [])
    if not items:
        issues.append(ImportIssue("error", "Catalog has no items"))
        return issues

    # --- Structural integrity checks ---
    for idx, item in enumerate(items):
        if not item.get("product"):
            issues.append(ImportIssue("error", f"Item {idx}: empty product"))
        if not item.get("sku"):
            issues.append(ImportIssue("error", f"Item {idx}: empty sku (product={item.get('product')})"))
        if not item.get("region"):
            issues.append(ImportIssue("error", f"Item {idx}: empty region (product={item.get('product')}, sku={item.get('sku')})"))
        price = item.get("price")
        if price is None:
            issues.append(ImportIssue("error", f"Item {idx}: missing price (product={item.get('product')}, sku={item.get('sku')})"))
        elif not isinstance(price, (int, float)):
            issues.append(ImportIssue("error", f"Item {idx}: price is not numeric: {price}"))
        region = item.get("region", "")
        if region and region not in SUPPORTED_REGIONS:
            issues.append(ImportIssue("warning", f"Item {idx}: unknown region '{region}' (product={item.get('product')}, sku={item.get('sku')})"))

    # --- Critical products exist ---
    critical_products = {
        "EVS", "OBS", "SFS Turbo", "EIP", "ELB", "NAT Gateway", "VPN",
        "Direct Connect as a Service", "RDS", "DDS", "DWS",
    }
    present_products = {item.get("product", "") for item in items}
    missing_products = critical_products - present_products
    if missing_products:
        issues.append(ImportIssue(
            "error",
            f"Missing critical products in catalog: {sorted(missing_products)}",
        ))

    # --- Critical SKUs exist per region ---
    critical_skus = {
        "EVS": {"gpssd", "gpssd-v2", "high-io", "ultra-high-io", "sas"},
        "OBS": {"obs-standard", "obs-infrequent-access"},
        "SFS Turbo": {"sfs-turbo-20mbps-per-tib", "sfs-turbo-40mbps-per-tib"},
        "NAT Gateway": {"nat-small", "nat-middle", "nat-large"},
        "VPN": {"vpn-basic", "vpn-professional-1", "vpn-professional-2"},
        "Direct Connect as a Service": {"dcas-1g", "dcas-10g", "dcas-100g"},
    }

    # Index by (product, region)
    by_product_region: dict[tuple[str, str], set[str]] = {}
    for item in items:
        key = (item.get("product", ""), item.get("region", ""))
        by_product_region.setdefault(key, set()).add(item.get("sku", ""))

    for product, expected_skus in critical_skus.items():
        for region in SUPPORTED_REGIONS:
            key = (product, region)
            present = by_product_region.get(key, set())
            missing = expected_skus - present
            if missing:
                issues.append(ImportIssue(
                    "warning",
                    f"Missing SKUs for {product}/{region}: {sorted(missing)}",
                ))

    # --- Duplicate entries with conflicting prices ---
    seen: dict[tuple, float] = {}
    for item in items:
        key = (item.get("product"), item.get("sku"), item.get("region"), item.get("billing_mode"))
        price = item.get("price", 0)
        if key in seen and abs(seen[key] - price) > 0.001:
            issues.append(ImportIssue(
                "error",
                f"Duplicate with different price: {key} prices={seen[key]} vs {price}",
            ))
        seen[key] = price

    return issues


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Flexible pricing catalog import tool")
    sub = parser.add_subparsers(dest="command", required=True)

    # preview
    p_preview = sub.add_parser("preview", help="Preview normalized rows from Excel")
    p_preview.add_argument("xlsx_path", help="Path to Huawei Cloud Price.xlsx")

    # patch
    p_patch = sub.add_parser("patch", help="Generate catalog patch JSON")
    p_patch.add_argument("xlsx_path", help="Path to Huawei Cloud Price.xlsx")
    p_patch.add_argument("-o", "--output", help="Output file path (default: stdout)")
    p_patch.add_argument("--dry-run", action="store_true",
                         help="Show dry-run summary against existing catalog instead of writing patch")
    p_patch.add_argument("--catalog", help="Path to existing catalog for dry-run comparison")

    # validate
    p_validate = sub.add_parser("validate", help="Validate existing catalog consistency")
    p_validate.add_argument("catalog_path", help="Path to flexible-pricing-catalog.json")

    args = parser.parse_args()

    if args.command == "preview":
        result = import_excel(args.xlsx_path)
        print(f"=== Import Preview ===")
        print(f"Normalized rows: {len(result.normalized_rows)}")
        print(f"Issues: {len(result.issues)}")
        print(f"Skipped products: {sorted(result.skipped_products)}")
        print()
        for row in result.normalized_rows:
            print(f"  {row.product:30s} {row.sku:30s} {row.region:8s} {row.billing_mode:8s} {row.price:12.6f} {row.unit}")
        if result.issues:
            print()
            print("=== Issues ===")
            for issue in result.issues:
                print(f"  [{issue.severity}] {issue.message}")

    elif args.command == "patch":
        result = import_excel(args.xlsx_path)
        patch = generate_patch(result)
        if args.dry_run:
            catalog_path = args.catalog or os.path.join(
                os.path.dirname(args.xlsx_path), "..", "data", "flexible-pricing-catalog.json"
            )
            if not os.path.exists(catalog_path):
                print(f"Error: catalog not found at {catalog_path}", file=sys.stderr)
                sys.exit(1)
            summary = patch_dry_run_summary(patch, catalog_path)
            print("=== Patch Dry-Run Summary ===")
            print(f"  New items:      {summary['new_items']}")
            print(f"  Updated items:  {summary['updated_items']}")
            print(f"  Unchanged:      {summary['unchanged_items']}")
            print(f"  Total patch:    {summary['total_patch_items']}")
            print(f"  Conflicts:      {summary['conflicts']}")
            print(f"  Warnings:       {summary['warnings']}")
            if summary["skipped_products"]:
                print(f"  Skipped prods:  {summary['skipped_products']}")
        else:
            output = json.dumps(patch, indent=2, ensure_ascii=False)
            if args.output:
                Path(args.output).write_text(output)
                print(f"Patch written to {args.output} ({patch['patch_metadata']['total_items']} items)")
            else:
                print(output)

    elif args.command == "validate":
        issues = validate_catalog(args.catalog_path)
        if not issues:
            print("Catalog validation: OK — no issues found.")
        else:
            print(f"Catalog validation: {len(issues)} issue(s) found.")
            for issue in issues:
                print(f"  [{issue.severity}] {issue.message}")


if __name__ == "__main__":
    main()
