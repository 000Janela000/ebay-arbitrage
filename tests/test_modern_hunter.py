from datetime import datetime, timedelta

from backend.services.modern_hunter import (
    DemandGateInput,
    calc_final_score,
    calc_steal_score,
    calc_winability_score,
    evaluate_demand_gate,
)


def test_steal_score_monotonic_with_discount():
    w = 0.7
    low = calc_steal_score(0.10, w)
    high = calc_steal_score(0.50, w)
    assert high > low


def test_winability_decreases_with_more_bids_and_worse_timing():
    near_end = datetime.utcnow() + timedelta(hours=3)
    far_end = datetime.utcnow() + timedelta(hours=23)
    a = calc_winability_score(near_end, bid_count=1, seller_feedback_pct=99.0)
    b = calc_winability_score(far_end, bid_count=12, seller_feedback_pct=92.0)
    assert a > b


def test_demand_gate_rejects_low_demand_low_margin():
    ends_at = datetime.utcnow() + timedelta(hours=5)
    ok, reason = evaluate_demand_gate(DemandGateInput(
        comparable_count=1,
        demand_score=0.2,
        profit_margin_pct=15.0,
        ends_at=ends_at,
        min_hours=2,
        max_hours=24,
        min_listings=2,
        min_demand_score=0.25,
        min_margin_pct=25.0,
    ))
    assert not ok
    assert reason in {"low_comparables", "low_demand", "low_margin"}


def test_final_score_penalizes_non_gated():
    gated = calc_final_score(0.9, 0.7, 0.8, gate_passed=True)
    non_gated = calc_final_score(0.9, 0.7, 0.8, gate_passed=False)
    assert gated > non_gated
