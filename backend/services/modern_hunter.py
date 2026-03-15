"""
Core scoring helpers for the modern auction hunter flow.
"""
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from backend.services.opportunity_scorer import calc_competition_score, calc_urgency_score


@dataclass
class DemandGateInput:
    comparable_count: int
    demand_score: float
    profit_margin_pct: Optional[float]
    ends_at: datetime
    min_hours: float
    max_hours: float
    min_listings: int
    min_demand_score: float
    min_margin_pct: float


def calc_quick_anchor_price(current_bid_usd: float, bid_count: int) -> float:
    """
    Cheap fallback anchor when category baseline is unavailable.
    """
    base = max(current_bid_usd, 1.0)
    # Slightly increase expected fair value by bid activity.
    multiplier = 1.35 + min(max(bid_count, 0), 15) * 0.02
    return round(base * multiplier, 2)


def calc_discount_pct(anchor_price_usd: Optional[float], reference_price_usd: Optional[float]) -> Optional[float]:
    if not anchor_price_usd or anchor_price_usd <= 0 or reference_price_usd is None:
        return None
    return round((anchor_price_usd - reference_price_usd) / anchor_price_usd, 4)


def calc_seller_quality_score(seller_feedback_pct: Optional[float]) -> float:
    if seller_feedback_pct is None:
        return 0.6
    if seller_feedback_pct >= 98:
        return 1.0
    if seller_feedback_pct >= 95:
        return 0.85
    if seller_feedback_pct >= 90:
        return 0.7
    return 0.45


def calc_winability_score(ends_at: datetime, bid_count: int, seller_feedback_pct: Optional[float]) -> float:
    urgency = calc_urgency_score(ends_at)
    low_competition = calc_competition_score(bid_count)
    seller_quality = calc_seller_quality_score(seller_feedback_pct)
    score = 0.5 * urgency + 0.35 * low_competition + 0.15 * seller_quality
    return round(min(1.0, max(0.0, score)), 4)


def calc_steal_score(current_discount_pct: Optional[float], winability_score: float) -> float:
    """
    Discount-center sigmoid at 40% + winability blend.
    """
    if current_discount_pct is None:
        discount_component = 0.0
    else:
        # Center at 40% discount, moderate slope.
        x = current_discount_pct
        k = 10.0
        x0 = 0.40
        discount_component = 1.0 / (1.0 + math.exp(-k * (x - x0)))
    score = 0.6 * discount_component + 0.4 * winability_score
    return round(min(1.0, max(0.0, score)), 4)


def calc_final_score(steal_score: float, demand_score: float, margin_score: float, gate_passed: bool) -> float:
    raw = 0.45 * steal_score + 0.30 * demand_score + 0.25 * margin_score
    if not gate_passed:
        raw *= 0.2
    return round(raw * 100, 2)


def evaluate_demand_gate(inp: DemandGateInput) -> tuple[bool, Optional[str]]:
    now = datetime.utcnow()
    seconds_remaining = max(0, (inp.ends_at - now).total_seconds())
    hours_remaining = seconds_remaining / 3600.0

    if hours_remaining < inp.min_hours or hours_remaining > inp.max_hours:
        return False, "outside_window"
    if inp.comparable_count < inp.min_listings:
        return False, "low_comparables"
    if inp.demand_score < inp.min_demand_score:
        return False, "low_demand"
    if inp.profit_margin_pct is None or inp.profit_margin_pct < inp.min_margin_pct:
        return False, "low_margin"
    return True, None
