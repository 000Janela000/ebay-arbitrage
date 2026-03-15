from backend.utils.shipping import calc_total_landed_cost


def test_landed_cost_without_vat():
    out = calc_total_landed_cost(
        estimated_final_usd=100.0,
        weight_kg=2.0,
        rate_per_kg=9.0,
        vat_enabled=False,
        vat_rate=0.18,
    )
    assert out["shipping_cost_usd"] == 18.0
    assert out["vat_usd"] == 0.0
    assert out["total_landed_cost_usd"] == 118.0


def test_landed_cost_with_vat():
    out = calc_total_landed_cost(
        estimated_final_usd=100.0,
        weight_kg=2.0,
        rate_per_kg=9.0,
        vat_enabled=True,
        vat_rate=0.18,
    )
    assert out["shipping_cost_usd"] == 18.0
    assert out["vat_usd"] == 21.24
    assert out["total_landed_cost_usd"] == 139.24
