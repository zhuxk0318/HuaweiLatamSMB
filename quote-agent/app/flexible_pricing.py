from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.models import PriceComponent

FLEXIBLE_PRICING_CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "flexible-pricing-catalog.json"


@lru_cache(maxsize=1)
def load_flexible_pricing_catalog() -> list[PriceComponent]:
    with FLEXIBLE_PRICING_CATALOG_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return [PriceComponent.model_validate(item) for item in payload["items"]]


def query_flexible_pricing_catalog(
    *,
    product: str | None = None,
    region: str | None = None,
    confirmed_only: bool = False,
) -> list[PriceComponent]:
    items = load_flexible_pricing_catalog()
    filtered = [
        item
        for item in items
        if (not product or item.product == product)
        and (not region or item.region == region)
        and (not confirmed_only or (item.confirmed and item.status == "confirmed" and item.price is not None))
    ]
    return filtered
