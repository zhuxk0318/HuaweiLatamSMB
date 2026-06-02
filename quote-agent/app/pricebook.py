from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

UNIFIED_CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "flexible-pricing-catalog.json"
CATEGORY_PRIORITY = [
    "General Computing",
    "General Computing-plus",
    "Memory-optimized",
    "SAP-certified",
]
HOURS_PER_MONTH = 730

# ── Family policy definitions (Phase 8B) ────────────────────────────────────────
# Each policy maps to an ordered list of (preferred_categories, excluded_categories).
# The picker tries each tier in order; if all are empty, it falls back to default
# CATEGORY_PRIORITY with no exclusions.

FAMILY_POLICY_TIERS: dict[str, list[list[str]]] = {
    "default": [
        ["General Computing"],
        ["General Computing-plus"],
        ["Memory-optimized"],
        ["SAP-certified"],
    ],
    "sap_app": [
        ["SAP-certified"],           # S-series first for SAP app
        ["General Computing-plus"],  # C-series fallback
        ["General Computing"],       # X-series last resort
        ["Memory-optimized"],
    ],
    "sap_db": [
        ["General Computing-plus"],  # C-series first for SAP DB
        ["Memory-optimized"],        # M-series second
        ["SAP-certified"],           # S-series fallback
        ["General Computing"],       # X-series last resort
    ],
    "sap_hana_db": [
        ["Memory-optimized"],        # M-series first for HANA
        ["General Computing-plus"],  # C-series second
        ["SAP-certified"],           # S-series fallback
        ["General Computing"],       # X-series last resort
    ],
}


def _rebuild_pricebook_from_catalog(catalog_items: list[dict[str, Any]]) -> dict[str, Any]:
    pricing_catalog: dict[str, dict[str, Any]] = {}
    for item in catalog_items:
        product = item.get("product")
        region = item.get("region")
        if not product or not region:
            continue
        if region not in pricing_catalog:
            pricing_catalog[region] = {"ecs": [], "evs": []}
        attrs = item.get("raw_attributes", {})
        if product == "ECS":
            pricing_catalog[region]["ecs"].append({
                "familyLabel": item.get("family", ""),
                "generation": attrs.get("generation", ""),
                "category": item.get("tier", ""),
                "spec": attrs.get("spec", item.get("sku", "")),
                "resourceSpecCode": attrs.get("resourceSpecCode", ""),
                "vcpu": attrs.get("vcpu", 0),
                "memoryGiB": attrs.get("memoryGiB", 0),
                "image": attrs.get("image", "Linux"),
                "imageSpec": attrs.get("resourceSpecCode", "").split(".linux")[0].rsplit(".", 1)[-1] if ".linux" in attrs.get("resourceSpecCode", "") else "linux",
                "hourlyUsd": attrs.get("hourlyUsd", 0),
                "monthlyUsd": attrs.get("monthlyUsd", 0),
                "yearlyUsd": attrs.get("yearlyUsd", 0),
                "ri1YearMonthlyUsd": attrs.get("ri1YearMonthlyUsd", 0),
                "ri1YearEffectiveHourlyUsd": attrs.get("ri1YearEffectiveHourlyUsd", 0),
                "ondemandProductId": "",
                "riProductId": "",
                "riPlanId": "",
            })
        elif product == "EVS":
            pricing_catalog[region]["evs"].append({
                "key": attrs.get("key", item.get("sku", "")),
                "label": attrs.get("label", ""),
                "resourceSpecCode": attrs.get("resourceSpecCode", ""),
                "volumeType": item.get("family", "SSD"),
                "hourlyUsdPerGb": attrs.get("hourlyUsdPerGb", 0),
                "monthlyUsdPerGb": attrs.get("monthlyUsdPerGb", 0),
                "yearlyUsdPerGb": attrs.get("yearlyUsdPerGb", 0),
                "monthlyEquivalentUsdPerGb": attrs.get("monthlyEquivalentUsdPerGb", 0),
                "ondemandProductId": "",
            })

    region_codes = {"mexico": "la-north-2", "chile": "la-south-2", "brazil": "sa-brazil-1"}
    for region in pricing_catalog:
        pricing_catalog[region]["regionCode"] = region_codes.get(region, region)

    return {
        "pricingCatalog": pricing_catalog,
        "pricingMetadata": {
            "fetchedAt": "",
            "sourcePortal": "unified-flexible-catalog",
            "ecsPricingScope": "all-ecs-from-flexible-catalog",
            "evsPricingScope": "all-evs-from-flexible-catalog",
        },
    }


@lru_cache(maxsize=1)
def load_pricebook() -> dict[str, Any]:
    with UNIFIED_CATALOG_PATH.open("r", encoding="utf-8") as handle:
        catalog = json.load(handle)
    return _rebuild_pricebook_from_catalog(catalog.get("items", []))


def pick_ecs_match(
    region_catalog: dict[str, Any],
    vcpu: int,
    memory_gib: float,
    strategy: str = "ceil",
    family_policy: str = "default",
) -> dict[str, Any] | None:
    """Pick the best ECS spec for a requested CPU/memory shape.

    Args:
        region_catalog: Region pricebook dict with "ecs" list.
        vcpu: Requested vCPU count.
        memory_gib: Requested memory in GiB.
        strategy: "ceil" (default) selects the smallest spec that is >=
            requested CPU and memory within each category tier. "nearest"
            selects the spec with the smallest combined ratio distance from
            the requested shape, considering all candidates (not just those
            >= the request). Tie-breakers for "nearest":
            1. Lowest score (combined ratio distance).
            2. Prefers spec that does not undersize (cpu >= requested AND mem >= requested).
            3. Lower monthly on-demand price.
            4. Closer vCPU to requested.
            5. Closer memory to requested.
            6. Stable sort by spec name.
        family_policy: Controls category priority order. Supported values:
            "default" — original priority (General Computing → Computing-plus → Memory → SAP).
            "sap_app" — SAP-certified first, then C, then X, then M.
            "sap_db" — C first, then M, then S, then X.
            "sap_hana_db" — M first, then C, then S, then X.
    """
    category_tiers = FAMILY_POLICY_TIERS.get(family_policy, FAMILY_POLICY_TIERS["default"])
    if strategy == "nearest":
        return _pick_ecs_nearest(region_catalog, vcpu, memory_gib, category_tiers=category_tiers)
    # Original "ceil" strategy
    ecs_items = region_catalog["ecs"]
    candidates = [
        item
        for item in ecs_items
        if int(item["vcpu"]) >= vcpu and float(item["memoryGiB"]) >= memory_gib
    ]
    for tier_categories in category_tiers:
        tier = [item for item in candidates if item["category"] in tier_categories]
        if tier:
            return sorted(
                tier,
                key=lambda item: (
                    int(item["vcpu"]),
                    float(item["memoryGiB"]),
                    float(item["hourlyUsd"]) * HOURS_PER_MONTH,
                    str(item["spec"]),
                ),
            )[0]
    return None


def _pick_ecs_nearest(
    region_catalog: dict[str, Any],
    vcpu: int,
    memory_gib: float,
    category_tiers: list[list[str]] | None = None,
) -> dict[str, Any] | None:
    """Pick ECS spec with the smallest combined ratio distance to the requested shape.

    Scoring:
        cpu_ratio_diff = abs(candidate_vcpu - requested_vcpu) / max(requested_vcpu, 1)
        mem_ratio_diff = abs(candidate_mem_gib - requested_mem_gib) / max(requested_mem_gib, 1)
        score = cpu_ratio_diff + mem_ratio_diff

    Tie-breakers (in order):
        1. Lower score.
        2. Prefers spec that does NOT undersize (vcpu >= requested AND mem >= requested).
        3. Lower monthly on-demand price.
        4. Closer vCPU to requested (abs diff).
        5. Closer memory to requested (abs diff).
        6. Stable sort by spec name.
    """
    ecs_items = region_catalog["ecs"]
    if not ecs_items:
        return None

    if category_tiers is None:
        category_tiers = FAMILY_POLICY_TIERS["default"]

    def _sort_key(item: dict[str, Any]) -> tuple:
        cand_vcpu = int(item["vcpu"])
        cand_mem = float(item["memoryGiB"])
        cand_monthly = float(item["hourlyUsd"]) * HOURS_PER_MONTH

        cpu_ratio_diff = abs(cand_vcpu - vcpu) / max(vcpu, 1)
        mem_ratio_diff = abs(cand_mem - memory_gib) / max(memory_gib, 1)
        score = cpu_ratio_diff + mem_ratio_diff

        # Tie-breaker: prefer specs that meet or exceed the request (0 = meets, 1 = undersizes)
        undersizes = 0 if (cand_vcpu >= vcpu and cand_mem >= memory_gib) else 1

        return (
            score,
            undersizes,
            cand_monthly,
            abs(cand_vcpu - vcpu),
            abs(cand_mem - memory_gib),
            str(item["spec"]),
        )

    for tier_categories in category_tiers:
        tier = [item for item in ecs_items if item["category"] in tier_categories]
        if tier:
            return sorted(tier, key=_sort_key)[0]

    # Fallback: any ECS item if no preferred category matches
    return sorted(ecs_items, key=_sort_key)[0]
