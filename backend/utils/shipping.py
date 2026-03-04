"""
Shipping and VAT cost calculator.
"""


def calc_shipping_cost(weight_kg: float, rate_per_kg: float = 9.0) -> float:
    """Calculate shipping cost: weight × rate."""
    return round(weight_kg * rate_per_kg, 2)


def calc_vat(amount_usd: float, vat_rate: float = 0.18) -> float:
    """Calculate VAT on the given amount."""
    return round(amount_usd * vat_rate, 2)


def calc_total_landed_cost(
    estimated_final_usd: float,
    weight_kg: float,
    rate_per_kg: float = 9.0,
    vat_enabled: bool = False,
    vat_rate: float = 0.18,
) -> dict:
    """
    Returns dict with:
      shipping_cost_usd, vat_usd, total_landed_cost_usd
    """
    shipping = calc_shipping_cost(weight_kg, rate_per_kg)
    vat = calc_vat(estimated_final_usd + shipping, vat_rate) if vat_enabled else 0.0
    total = round(estimated_final_usd + shipping + vat, 2)
    return {
        "shipping_cost_usd": shipping,
        "vat_usd": vat,
        "total_landed_cost_usd": total,
    }
