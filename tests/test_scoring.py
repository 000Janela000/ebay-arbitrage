from datetime import datetime, timedelta

from backend.services.opportunity_scorer import score_opportunity


def test_score_increases_with_higher_net_revenue():
    ends_at = datetime.utcnow() + timedelta(hours=4)
    base = score_opportunity(
        estimated_final_usd=100,
        total_landed_cost_usd=120,
        georgian_median_usd=130,
        bid_count=3,
        confidence_score=0.8,
        ends_at=ends_at,
        georgian_listing_count=3,
    )
    better = score_opportunity(
        estimated_final_usd=100,
        total_landed_cost_usd=120,
        georgian_median_usd=180,
        bid_count=3,
        confidence_score=0.8,
        ends_at=ends_at,
        georgian_listing_count=3,
    )
    assert better["opportunity_score"] > base["opportunity_score"]


def test_no_comparables_penalizes_confidence():
    ends_at = datetime.utcnow() + timedelta(hours=4)
    no_comps = score_opportunity(
        estimated_final_usd=100,
        total_landed_cost_usd=120,
        georgian_median_usd=None,
        bid_count=3,
        confidence_score=0.8,
        ends_at=ends_at,
        georgian_listing_count=0,
    )
    with_comps = score_opportunity(
        estimated_final_usd=100,
        total_landed_cost_usd=120,
        georgian_median_usd=150,
        bid_count=3,
        confidence_score=0.8,
        ends_at=ends_at,
        georgian_listing_count=3,
    )
    assert no_comps["confidence_score"] < with_comps["confidence_score"]
