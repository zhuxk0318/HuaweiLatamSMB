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
]
HOURS_PER_MONTH = 730


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


def pick_ecs_match(region_catalog: dict[str, Any], vcpu: int, memory_gib: float) -> dict[str, Any] | None:
    ecs_items = region_catalog["ecs"]
    candidates = [
        item
        for item in ecs_items
        if int(item["vcpu"]) >= vcpu and float(item["memoryGiB"]) >= memory_gib
    ]
    for category in CATEGORY_PRIORITY:
        tier = [item for item in candidates if item["category"] == category]
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
