"""
Weight estimation with tree-based category fallback.
"""

DEFAULT_WEIGHT_KG = 0.5


async def get_default_weight_async(category_id: str) -> float:
    """Walk up the category tree to find the nearest default weight."""
    try:
        from backend.services.category_tree_service import resolve_default_weight
        weight = await resolve_default_weight(category_id)
        if weight is not None:
            return weight
    except Exception:
        pass
    return DEFAULT_WEIGHT_KG


def resolve_weight(
    item_weight: float | None,
    item_weight_source: str | None,
    category_id: str,
    user_override: float | None = None,
    db_default: float = DEFAULT_WEIGHT_KG,
    category_weight: float | None = None,
) -> tuple[float, str]:
    """
    Returns (weight_kg, source) using fallback chain:
    user_override → ebay_specifics → category_weight → db_default

    category_weight should be pre-resolved by the caller via get_default_weight_async().
    """
    if user_override is not None:
        return user_override, "user_override"
    if item_weight and item_weight_source == "ebay_specifics":
        return item_weight, "ebay_specifics"
    if category_weight is not None:
        return category_weight, "category_default"
    return db_default, "category_default"
