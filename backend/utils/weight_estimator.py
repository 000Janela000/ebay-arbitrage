"""
Default weight estimates (kg) per eBay category ID.
Used when eBay item specifics don't include weight.
"""

CATEGORY_DEFAULT_WEIGHTS: dict[str, float] = {
    "9355": 0.2,    # Cell Phones
    "177": 2.0,     # Laptops
    "171485": 0.6,  # Tablets
    "139971": 0.5,  # Game Consoles
    "178893": 0.1,  # Smartwatches
    "625": 0.8,     # Cameras
    "293": 1.0,     # Consumer Electronics (generic)
    "11450": 0.4,   # Clothing
    "11700": 1.5,   # Home & Garden
    "267": 0.3,     # Books
    "619": 3.0,     # Musical Instruments
    "220": 0.8,     # Toys
}

DEFAULT_WEIGHT_KG = 0.5


def get_default_weight(category_id: str) -> float:
    return CATEGORY_DEFAULT_WEIGHTS.get(category_id, DEFAULT_WEIGHT_KG)


def resolve_weight(
    item_weight: float | None,
    item_weight_source: str | None,
    category_id: str,
    user_override: float | None = None,
    db_default: float = DEFAULT_WEIGHT_KG,
) -> tuple[float, str]:
    """
    Returns (weight_kg, source) using fallback chain:
    user_override → ebay_specifics → category_default → db_default
    """
    if user_override is not None:
        return user_override, "user_override"
    if item_weight and item_weight_source == "ebay_specifics":
        return item_weight, "ebay_specifics"
    cat_weight = CATEGORY_DEFAULT_WEIGHTS.get(category_id)
    if cat_weight:
        return cat_weight, "category_default"
    return db_default, "category_default"
