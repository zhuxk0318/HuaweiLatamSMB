from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

PRICEBOOK_PATH = Path(__file__).resolve().parent.parent / "data" / "pricing-pricebook.json"
CATEGORY_PRIORITY = [
    "General Computing",
    "General Computing-plus",
    "Memory-optimized",
]
HOURS_PER_MONTH = 730


@lru_cache(maxsize=1)
def load_pricebook() -> dict[str, Any]:
    with PRICEBOOK_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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
