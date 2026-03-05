"""
Composite opportunity scoring formula.

score (0–100) = (margin_score × 0.35) + (urgency_score × 0.20)
              + (demand_score × 0.20) + (confidence_score × 0.15)
              + (competition_score × 0.10)

confidence_score is adjusted before scoring to account for:
  G1: seller feedback quality  (poor sellers reduce confidence)
  G2: Georgian listing count   (sparse data reduces confidence)
"""
import math
from datetime import datetime
from typing import Optional


def calc_margin_score(profit_margin_pct: Optional[float]) -> float:
    """
    Logistic sigmoid centered at 30% margin.
    0 at 0%, ~0.6 at 30%, ~1.0 at 80%+
    """
    if profit_margin_pct is None:
        return 0.0
    # Sigmoid: 1 / (1 + exp(-k*(x - x0)))
    # Tuned: k=0.08, x0=30 → 0.5 at 30%, approaches 1 at 80+
    x = profit_margin_pct
    k = 0.08
    x0 = 30.0
    score = 1.0 / (1.0 + math.exp(-k * (x - x0)))
    return round(min(1.0, max(0.0, score)), 4)


def calc_urgency_score(ends_at: datetime) -> float:
    """
    Log-scale decay based on seconds remaining.
    0.1 at >48h, 0.6 at 6h, 1.0 at <30min
    """
    now = datetime.utcnow()
    # Handle timezone-aware datetimes
    if ends_at.tzinfo is not None:
        from datetime import timezone
        now = datetime.now(timezone.utc)

    seconds_remaining = max(0, (ends_at - now).total_seconds())

    if seconds_remaining <= 0:
        return 0.0

    hours = seconds_remaining / 3600.0

    if hours > 48:
        return 0.1
    elif hours > 6:
        # Interpolate between 0.1 and 0.6 on log scale
        t = math.log(hours / 48.0) / math.log(6.0 / 48.0)
        return round(0.1 + t * 0.5, 4)
    elif hours > 0.5:  # > 30 min
        t = math.log(hours / 6.0) / math.log(0.5 / 6.0)
        return round(0.6 + t * 0.4, 4)
    else:
        return 1.0


def calc_demand_score(
    georgian_listing_count: int,
    avg_view_count: Optional[float] = None,
    avg_order_count: Optional[float] = None,
) -> float:
    """
    Demand score (0-1) based on Georgian market signals.
    More listings, views, and orders = higher demand.
    """
    # Listing count as base signal: 0=0, 1=0.3, 3=0.6, 5=0.8, 10+=1.0
    listing_score = min(1.0, georgian_listing_count / 10.0) if georgian_listing_count > 0 else 0.0

    # View count signal (0-1), normalized: 100+ views = 1.0
    view_score = 0.0
    if avg_view_count is not None and avg_view_count > 0:
        view_score = min(1.0, avg_view_count / 100.0)

    # Order/sold count signal (0-1), normalized: 10+ orders = 1.0
    order_score = 0.0
    if avg_order_count is not None and avg_order_count > 0:
        order_score = min(1.0, avg_order_count / 10.0)

    # Weighted combo — use richer signals if available
    if avg_view_count is not None or avg_order_count is not None:
        return round(0.4 * listing_score + 0.3 * view_score + 0.3 * order_score, 4)
    return round(listing_score, 4)


def calc_competition_score(bid_count: int) -> float:
    """
    exp(-0.15 × bid_count) → 1.0 at 0 bids, ~0.5 at 5 bids
    """
    score = math.exp(-0.15 * bid_count)
    return round(min(1.0, max(0.0, score)), 4)


def calc_opportunity_score(
    margin_score: float,
    urgency_score: float,
    confidence_score: float,
    demand_score: float,
    competition_score: float,
) -> float:
    """
    Composite score 0–100.
    Weights: margin 35%, urgency 20%, demand 20%, confidence 15%, competition 10%.
    """
    raw = (
        margin_score * 0.35
        + urgency_score * 0.20
        + demand_score * 0.20
        + confidence_score * 0.15
        + competition_score * 0.10
    )
    return round(raw * 100, 2)


def _adjust_confidence(
    confidence: float,
    seller_feedback_pct: Optional[float],
    georgian_listing_count: int,
) -> float:
    """
    G1: Adjust confidence based on seller feedback quality.
      ≥98% feedback → no penalty
      90–97%        → 85–99% of original (linear)
      <90%          → 75% of original
      Unknown       → 95% of original (slight penalty for unknown)

    G2: Adjust confidence based on how many Georgian listings exist.
      0 listings → ×0.70  (no comparables, very uncertain)
      1 listing  → ×0.85  (single data point)
      2 listings → ×0.95  (getting reliable)
      3+ listings → ×1.00 (solid median)
    """
    # G1 — seller quality
    if seller_feedback_pct is None:
        seller_factor = 0.95
    elif seller_feedback_pct >= 98:
        seller_factor = 1.0
    elif seller_feedback_pct >= 90:
        seller_factor = 0.85 + (seller_feedback_pct - 90) / 80.0
    else:
        seller_factor = 0.75

    # G2 — Georgian data richness
    listing_factors = [0.70, 0.85, 0.95, 1.00]
    listing_factor = listing_factors[min(georgian_listing_count, 3)]

    return round(min(1.0, confidence * seller_factor * listing_factor), 4)


def score_opportunity(
    estimated_final_usd: float,
    total_landed_cost_usd: float,
    georgian_median_usd: Optional[float],
    bid_count: int,
    confidence_score: float,
    ends_at: datetime,
    seller_feedback_pct: Optional[float] = None,
    georgian_listing_count: int = 0,
    avg_view_count: Optional[float] = None,
    avg_order_count: Optional[float] = None,
) -> dict:
    """
    Compute all sub-scores and composite opportunity score.
    Returns dict with all score fields.
    """
    # Profit margin
    if georgian_median_usd and total_landed_cost_usd > 0:
        profit_margin_pct = (georgian_median_usd - total_landed_cost_usd) / total_landed_cost_usd * 100
    else:
        profit_margin_pct = None

    # Apply G1+G2 confidence adjustments before scoring
    adjusted_confidence = _adjust_confidence(confidence_score, seller_feedback_pct, georgian_listing_count)

    margin_score = calc_margin_score(profit_margin_pct)
    urgency_score = calc_urgency_score(ends_at)
    demand_score = calc_demand_score(georgian_listing_count, avg_view_count, avg_order_count)
    competition_score = calc_competition_score(bid_count)
    opportunity_score = calc_opportunity_score(
        margin_score, urgency_score, adjusted_confidence, demand_score, competition_score,
    )

    return {
        "profit_margin_pct": round(profit_margin_pct, 2) if profit_margin_pct is not None else None,
        "margin_score": margin_score,
        "urgency_score": urgency_score,
        "confidence_score": adjusted_confidence,
        "demand_score": demand_score,
        "competition_score": competition_score,
        "opportunity_score": opportunity_score,
    }
