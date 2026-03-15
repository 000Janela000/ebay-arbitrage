"""
Modern auction hunter router.

Parallel feature to classic flow:
- Auction-steal-first shortlist
- Strict demand gate
- Separate storage and jobs
"""
import asyncio
import csv
import io
import json
import statistics
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, asc, desc, func, or_, select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db, AsyncSessionLocal
from backend.models import (
    EbayCategory,
    Setting,
    ModernAuctionItem,
    ModernPriceEstimate,
    ModernGeorgianListing,
    ModernOpportunity,
    ModernCategoryRefreshStat,
)
from backend.services.currency_service import get_usd_gel_rate
from backend.services.ebay_client import get_daily_usage, parse_auction_item, search_auction_items
from backend.services.modern_hunter import (
    DemandGateInput,
    calc_discount_pct,
    calc_final_score,
    calc_quick_anchor_price,
    calc_steal_score,
    calc_winability_score,
    evaluate_demand_gate,
)
from backend.services.modern_job_store import get_job as get_persisted_job
from backend.services.modern_job_store import upsert_job
from backend.services.modern_tracking_advisor import maybe_run_advisor_before_refresh
from backend.services.opportunity_scorer import score_opportunity
from backend.services.price_estimator import estimate_final_price
from backend.services.scraper_orchestrator import scrape_all_platforms
from backend.utils.shipping import calc_total_landed_cost
from backend.utils.weight_estimator import get_default_weight_async, resolve_weight

router = APIRouter()

_jobs: dict[str, dict] = {}
_JOB_TYPE = "modern_refresh"
_KNOWN_PLATFORMS = ["mymarket", "extra", "veli", "zoomer"]


class ModernSettingsResponse(BaseModel):
    strategy_profile: str = "balanced"
    target_margin_floor_pct: float = 0.25
    demand_gate_min_listings: int = 2
    demand_gate_min_score: float = 0.25
    auction_window_min_hours: float = 2.0
    auction_window_max_hours: float = 24.0
    max_categories_per_refresh: int = 20
    max_items_per_category: int = 30
    deep_scrape_top_k: int = 10


class ModernSettingsUpdate(BaseModel):
    strategy_profile: Optional[str] = None
    target_margin_floor_pct: Optional[float] = None
    demand_gate_min_listings: Optional[int] = None
    demand_gate_min_score: Optional[float] = None
    auction_window_min_hours: Optional[float] = None
    auction_window_max_hours: Optional[float] = None
    max_categories_per_refresh: Optional[int] = None
    max_items_per_category: Optional[int] = None
    deep_scrape_top_k: Optional[int] = None

    @field_validator("strategy_profile")
    @classmethod
    def validate_strategy(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in {"balanced", "aggressive", "conservative"}:
            raise ValueError("strategy_profile must be balanced|aggressive|conservative")
        return v

    @field_validator(
        "target_margin_floor_pct",
        "demand_gate_min_score",
    )
    @classmethod
    def validate_zero_to_one(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return v
        if v < 0 or v > 1:
            raise ValueError("Value must be between 0 and 1")
        return v

    @field_validator(
        "demand_gate_min_listings",
        "max_categories_per_refresh",
        "max_items_per_category",
        "deep_scrape_top_k",
    )
    @classmethod
    def validate_positive_int(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return v
        if v < 1:
            raise ValueError("Value must be >= 1")
        return v

    @field_validator("auction_window_min_hours", "auction_window_max_hours")
    @classmethod
    def validate_positive_hours(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return v
        if v <= 0:
            raise ValueError("Hours must be > 0")
        return v


class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int
    message: str = ""
    metrics: dict = Field(default_factory=dict)
    scraper_status: dict = Field(default_factory=dict)


class ModernOpportunityDTO(BaseModel):
    ebay_item_id: str
    title: str
    image_url: Optional[str]
    item_url: str
    current_bid_usd: float
    estimated_final_usd: float
    anchor_price_usd: Optional[float]
    current_discount_pct: Optional[float]
    projected_discount_pct: Optional[float]
    steal_score: float
    winability_score: float
    demand_gate_passed: bool
    gate_reason: Optional[str]
    final_score: float
    bid_count: int
    ends_at: datetime
    seconds_remaining: float
    weight_kg: float
    weight_source: str
    shipping_cost_usd: float
    vat_usd: float
    total_landed_cost_usd: float
    total_landed_cost_gel: float
    georgian_median_price_gel: Optional[float]
    georgian_median_price_usd: Optional[float]
    net_revenue_usd: Optional[float]
    selling_fees_usd: Optional[float]
    georgian_listing_count: int
    profit_margin_pct: Optional[float]
    profit_usd: Optional[float]
    profit_gel: Optional[float]
    margin_score: float
    urgency_score: float
    confidence_score: float
    demand_score: Optional[float]
    competition_score: float
    ebay_category_id: str
    has_georgian_data: bool
    data_quality_warning: Optional[str]


class ModernRefreshRequest(BaseModel):
    strategy_profile: Optional[str] = None

    @field_validator("strategy_profile")
    @classmethod
    def validate_profile(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in {"balanced", "aggressive", "conservative"}:
            raise ValueError("strategy_profile must be balanced|aggressive|conservative")
        return v


def _now_utc() -> datetime:
    return datetime.utcnow()


def _safe_float(s: dict[str, str], key: str, default: float) -> float:
    try:
        return float(s.get(key, str(default)))
    except Exception:
        return default


def _safe_int(s: dict[str, str], key: str, default: int) -> int:
    try:
        return int(float(s.get(key, str(default))))
    except Exception:
        return default


async def _get_all_settings() -> dict[str, str]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Setting))
        return {row.key: row.value for row in result.scalars().all()}


def _parse_modern_settings(raw: dict[str, str], override_profile: Optional[str] = None) -> dict[str, Any]:
    strategy_profile = override_profile or raw.get("modern_strategy_profile", "balanced")
    cfg = {
        "strategy_profile": strategy_profile,
        "target_margin_floor_pct": _safe_float(raw, "modern_target_margin_floor_pct", 0.25),
        "demand_gate_min_listings": _safe_int(raw, "modern_demand_gate_min_listings", 2),
        "demand_gate_min_score": _safe_float(raw, "modern_demand_gate_min_score", 0.25),
        "auction_window_min_hours": _safe_float(raw, "modern_auction_window_min_hours", 2.0),
        "auction_window_max_hours": _safe_float(raw, "modern_auction_window_max_hours", 24.0),
        "max_categories_per_refresh": _safe_int(raw, "modern_max_categories_per_refresh", 20),
        "max_items_per_category": _safe_int(raw, "modern_max_items_per_category", 30),
        "deep_scrape_top_k": _safe_int(raw, "modern_deep_scrape_top_k", 10),
        "shipping_rate_per_kg": _safe_float(raw, "shipping_rate_per_kg", 9.0),
        "vat_enabled": raw.get("vat_enabled", "false").lower() == "true",
        "vat_rate": _safe_float(raw, "vat_rate", 0.18),
        "default_weight_kg": _safe_float(raw, "default_weight_kg", 0.5),
        "platform_fee_pct": _safe_float(raw, "platform_fee_pct", 0.0),
        "payment_fee_pct": _safe_float(raw, "payment_fee_pct", 0.0),
        "handling_fee_usd": _safe_float(raw, "handling_fee_usd", 0.0),
        "realism_max_extreme_margin_pct": _safe_float(raw, "modern_realism_max_extreme_margin_pct", 500.0),
        "realism_min_positive_discount_share": _safe_float(raw, "modern_realism_min_positive_discount_share", 0.20),
    }
    if strategy_profile == "aggressive":
        cfg["target_margin_floor_pct"] = max(0.15, cfg["target_margin_floor_pct"])
        cfg["demand_gate_min_score"] = max(0.15, min(cfg["demand_gate_min_score"], 0.25))
    elif strategy_profile == "conservative":
        cfg["target_margin_floor_pct"] = max(0.35, cfg["target_margin_floor_pct"])
        cfg["demand_gate_min_score"] = max(0.35, cfg["demand_gate_min_score"])
        cfg["demand_gate_min_listings"] = max(3, cfg["demand_gate_min_listings"])
    return cfg


async def _upsert_setting(key: str, value: str):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Setting).where(Setting.key == key))
        row = result.scalar_one_or_none()
        now = _now_utc()
        if row is None:
            db.add(Setting(key=key, value=value, updated_at=now))
        else:
            row.value = value
            row.updated_at = now
        await db.commit()


async def _persist_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return
    await upsert_job(
        job_id=job_id,
        job_type=_JOB_TYPE,
        status=job.get("status", "running"),
        progress=int(job.get("progress", 0)),
        message=job.get("message", ""),
        payload={
            "metrics": job.get("metrics", {}),
            "scraper_status": job.get("scraper_status", {}),
        },
    )


async def _set_job(job_id: str, status: str, progress: int, message: str, metrics: Optional[dict] = None, scraper_status: Optional[dict] = None):
    existing = _jobs.get(job_id, {})
    _jobs[job_id] = {
        "status": status,
        "progress": max(0, min(100, int(progress))),
        "message": message,
        "metrics": metrics if metrics is not None else existing.get("metrics", {}),
        "scraper_status": scraper_status if scraper_status is not None else existing.get("scraper_status", {}),
    }
    await _persist_job(job_id)


def _build_quality_warning(opp: ModernOpportunity) -> Optional[str]:
    warnings = []
    if not opp.georgian_listing_count:
        warnings.append("No Georgian comparables")
    if opp.confidence_score is not None and opp.confidence_score < 0.35:
        warnings.append("Low confidence")
    if not opp.demand_gate_passed and opp.gate_reason:
        warnings.append(f"Gate: {opp.gate_reason}")
    return "; ".join(warnings) if warnings else None


def _load_source_stats(raw_json: Optional[str]) -> dict[str, dict[str, Any]]:
    if not raw_json:
        return {}
    try:
        data = json.loads(raw_json)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {}


def _allowed_platforms(source_stats: dict[str, dict[str, Any]], now: datetime) -> list[str]:
    allowed: list[str] = []
    for platform in _KNOWN_PLATFORMS:
        p = source_stats.get(platform, {})
        cooldown_until = p.get("cooldown_until")
        if cooldown_until:
            try:
                dt = datetime.fromisoformat(cooldown_until)
                if dt > now:
                    continue
            except Exception:
                pass
        allowed.append(platform)
    return allowed


def _update_source_stats(
    source_stats: dict[str, dict[str, Any]],
    valid_by_platform: dict[str, int],
    attempted_platforms: list[str],
    now: datetime,
) -> dict[str, dict[str, Any]]:
    for platform in attempted_platforms:
        p = source_stats.get(platform, {})
        consecutive_zero = int(p.get("consecutive_zero", 0))
        valid_count = int(valid_by_platform.get(platform, 0))
        if valid_count > 0:
            consecutive_zero = 0
            cooldown_until = None
        else:
            consecutive_zero += 1
            cooldown_until = None
            if consecutive_zero >= 3:
                cooldown_until = (now + timedelta(hours=24)).isoformat()

        source_stats[platform] = {
            "consecutive_zero": consecutive_zero,
            "cooldown_until": cooldown_until,
            "last_valid_count": valid_count,
            "last_checked_at": now.isoformat(),
        }
    return source_stats


async def _select_runtime_categories(max_categories: int) -> list[EbayCategory]:
    async with AsyncSessionLocal() as db:
        tracked_result = await db.execute(
            select(EbayCategory).where(EbayCategory.is_tracked == True)
        )
        tracked = list(tracked_result.scalars().all())
        if not tracked:
            return []

        tracked_map = {c.ebay_category_id: c for c in tracked}
        tracked_ids = set(tracked_map.keys())

        stats_result = await db.execute(select(ModernCategoryRefreshStat))
        stats_rows = [r for r in stats_result.scalars().all() if r.category_id in tracked_ids]
        stats_rows.sort(
            key=lambda r: (
                r.hit_rate or 0,
                1 if (r.processed_count or 0) > 0 else 0,
                r.processed_count or 0,
                r.shortlisted_count or 0,
                r.avg_steal_score or 0,
                r.last_refresh_at or datetime.min,
            ),
            reverse=True,
        )

        selected: list[EbayCategory] = []
        used_ids: set[str] = set()
        for stat in stats_rows:
            if len(selected) >= max_categories:
                break
            # Ignore pure-zero history rows; they are not informative.
            if (stat.processed_count or 0) <= 0 and (stat.shortlisted_count or 0) <= 0:
                continue
            cat = tracked_map.get(stat.category_id)
            if cat:
                selected.append(cat)
                used_ids.add(cat.ebay_category_id)

        fallback = [c for c in tracked if c.ebay_category_id not in used_ids]
        def _fallback_rank(c: EbayCategory) -> tuple:
            sold = float(c.avg_ebay_sold_usd or 0.0)
            margin = c.avg_profit_margin_pct
            sane_margin = float(margin) if margin is not None and 0 <= margin <= 300 else -1.0
            active = int(c.total_active_auctions or 0)
            name = (c.name or "").lower()
            not_other_bucket = 0 if name.startswith("other ") or name == "other" else 1
            return (
                1 if sold > 0 else 0,
                min(sold, 5000.0),
                1 if active > 0 else 0,
                active,
                1 if sane_margin >= 0 else 0,
                sane_margin,
                not_other_bucket,
                1 if c.is_leaf else 0,
                1 if c.last_analyzed_at else 0,
            )

        fallback.sort(key=_fallback_rank, reverse=True)
        for cat in fallback:
            if len(selected) >= max_categories:
                break
            selected.append(cat)
        return selected


@router.get("/settings", response_model=ModernSettingsResponse)
async def get_modern_settings():
    raw = await _get_all_settings()
    parsed = _parse_modern_settings(raw)
    return ModernSettingsResponse(
        strategy_profile=parsed["strategy_profile"],
        target_margin_floor_pct=parsed["target_margin_floor_pct"],
        demand_gate_min_listings=parsed["demand_gate_min_listings"],
        demand_gate_min_score=parsed["demand_gate_min_score"],
        auction_window_min_hours=parsed["auction_window_min_hours"],
        auction_window_max_hours=parsed["auction_window_max_hours"],
        max_categories_per_refresh=parsed["max_categories_per_refresh"],
        max_items_per_category=parsed["max_items_per_category"],
        deep_scrape_top_k=parsed["deep_scrape_top_k"],
    )


@router.put("/settings", response_model=ModernSettingsResponse)
async def update_modern_settings(body: ModernSettingsUpdate):
    updates: dict[str, str] = {}
    if body.strategy_profile is not None:
        updates["modern_strategy_profile"] = body.strategy_profile
    if body.target_margin_floor_pct is not None:
        updates["modern_target_margin_floor_pct"] = str(body.target_margin_floor_pct)
    if body.demand_gate_min_listings is not None:
        updates["modern_demand_gate_min_listings"] = str(body.demand_gate_min_listings)
    if body.demand_gate_min_score is not None:
        updates["modern_demand_gate_min_score"] = str(body.demand_gate_min_score)
    if body.auction_window_min_hours is not None:
        updates["modern_auction_window_min_hours"] = str(body.auction_window_min_hours)
    if body.auction_window_max_hours is not None:
        updates["modern_auction_window_max_hours"] = str(body.auction_window_max_hours)
    if body.max_categories_per_refresh is not None:
        updates["modern_max_categories_per_refresh"] = str(body.max_categories_per_refresh)
    if body.max_items_per_category is not None:
        updates["modern_max_items_per_category"] = str(body.max_items_per_category)
    if body.deep_scrape_top_k is not None:
        updates["modern_deep_scrape_top_k"] = str(body.deep_scrape_top_k)

    for key, value in updates.items():
        await _upsert_setting(key, value)

    return await get_modern_settings()


@router.post("/refresh")
async def start_modern_refresh(body: Optional[ModernRefreshRequest] = None):
    raw = await _get_all_settings()
    parsed = _parse_modern_settings(raw, override_profile=(body.strategy_profile if body else None))
    try:
        # If advisor is stale and enabled, refresh tracked pool automatically.
        await maybe_run_advisor_before_refresh()
    except Exception as e:
        print(f"[modern] Advisor pre-refresh failed: {e}")
    # Build a larger ranked pool; refresh worker stops early once enough non-empty categories are processed.
    category_pool_size = max(parsed["max_categories_per_refresh"] * 4, parsed["max_categories_per_refresh"])
    categories = await _select_runtime_categories(category_pool_size)
    if not categories:
        raise HTTPException(status_code=400, detail="No tracked categories. Track some categories first.")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "running",
        "progress": 0,
        "message": "Starting modern refresh...",
        "metrics": {},
        "scraper_status": {},
    }
    await _persist_job(job_id)
    asyncio.create_task(_run_modern_refresh(job_id, [c.ebay_category_id for c in categories], parsed))
    return {"job_id": job_id}


@router.get("/refresh/status", response_model=JobStatus)
async def modern_refresh_status(job_id: str = Query(...)):
    job = _jobs.get(job_id)
    if job:
        return JobStatus(job_id=job_id, **job)

    persisted = await get_persisted_job(job_id)
    if persisted:
        payload = persisted.get("payload", {})
        return JobStatus(
            job_id=job_id,
            status=persisted["status"],
            progress=persisted["progress"],
            message=persisted["message"],
            metrics=payload.get("metrics", {}),
            scraper_status=payload.get("scraper_status", {}),
        )
    return JobStatus(job_id=job_id, status="error", progress=0, message="Job not found")


@router.get("/opportunities")
async def list_modern_opportunities(
    sort_by: str = Query("final_score"),
    order: str = Query("desc"),
    min_profit_pct: Optional[float] = Query(None),
    max_bid_usd: Optional[float] = Query(None),
    min_budget_usd: Optional[float] = Query(None),
    max_budget_usd: Optional[float] = Query(None),
    category_id: Optional[str] = Query(None),
    has_georgian_data: Optional[bool] = Query(None),
    qualified_only: bool = Query(True),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    now = _now_utc()
    conditions = [ModernOpportunity.ends_at > now]
    if qualified_only:
        conditions.append(ModernOpportunity.demand_gate_passed == True)
    if min_profit_pct is not None:
        conditions.append(ModernOpportunity.profit_margin_pct >= min_profit_pct)
    if min_budget_usd is not None:
        conditions.append(ModernOpportunity.total_landed_cost_usd >= min_budget_usd)
    if max_budget_usd is not None:
        conditions.append(ModernOpportunity.total_landed_cost_usd <= max_budget_usd)
    if has_georgian_data is True:
        conditions.append(ModernOpportunity.georgian_listing_count > 0)
    elif has_georgian_data is False:
        conditions.append(or_(ModernOpportunity.georgian_listing_count == 0, ModernOpportunity.georgian_listing_count.is_(None)))
    if category_id:
        conditions.append(ModernOpportunity.ebay_category_id == category_id)
    if max_bid_usd is not None:
        conditions.append(ModernOpportunity.current_bid_usd <= max_bid_usd)

    col_map = {
        "final_score": ModernOpportunity.final_score,
        "steal_score": ModernOpportunity.steal_score,
        "winability_score": ModernOpportunity.winability_score,
        "profit_margin_pct": ModernOpportunity.profit_margin_pct,
        "ends_at": ModernOpportunity.ends_at,
    }
    sort_col = col_map.get(sort_by, ModernOpportunity.final_score)
    if sort_by == "ends_at":
        order_clause = asc(sort_col) if order.lower() == "asc" else desc(sort_col)
    else:
        order_clause = desc(sort_col) if order.lower() == "desc" else asc(sort_col)

    count_q = select(func.count()).select_from(ModernOpportunity).where(and_(*conditions))
    total = (await db.execute(count_q)).scalar_one()

    q = (
        select(ModernOpportunity, ModernAuctionItem)
        .join(ModernAuctionItem, ModernAuctionItem.id == ModernOpportunity.auction_item_id)
        .where(and_(*conditions))
        .order_by(order_clause)
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(q)).all()

    items = []
    for opp, item in rows:
        seconds_remaining = max(0, (opp.ends_at - now).total_seconds())
        items.append({
            "ebay_item_id": item.ebay_item_id,
            "title": opp.item_title,
            "image_url": opp.image_url,
            "item_url": opp.item_url,
            "current_bid_usd": opp.current_bid_usd,
            "estimated_final_usd": opp.estimated_final_usd,
            "anchor_price_usd": opp.anchor_price_usd,
            "current_discount_pct": opp.current_discount_pct,
            "projected_discount_pct": opp.projected_discount_pct,
            "steal_score": opp.steal_score,
            "winability_score": opp.winability_score,
            "demand_gate_passed": opp.demand_gate_passed,
            "gate_reason": opp.gate_reason,
            "final_score": opp.final_score,
            "bid_count": item.bid_count,
            "ends_at": opp.ends_at.isoformat(),
            "seconds_remaining": seconds_remaining,
            "weight_kg": opp.weight_kg,
            "weight_source": item.weight_source or "category_default",
            "shipping_cost_usd": opp.shipping_cost_usd,
            "vat_usd": opp.vat_usd,
            "total_landed_cost_usd": opp.total_landed_cost_usd,
            "total_landed_cost_gel": opp.total_landed_cost_gel,
            "georgian_median_price_gel": opp.georgian_median_price_gel,
            "georgian_median_price_usd": opp.georgian_median_price_usd,
            "net_revenue_usd": opp.net_revenue_usd,
            "selling_fees_usd": opp.selling_fees_usd,
            "georgian_listing_count": opp.georgian_listing_count,
            "profit_margin_pct": opp.profit_margin_pct,
            "profit_usd": opp.profit_usd,
            "profit_gel": opp.profit_gel,
            "margin_score": opp.margin_score,
            "urgency_score": opp.urgency_score,
            "confidence_score": opp.confidence_score,
            "demand_score": opp.demand_score,
            "competition_score": opp.competition_score,
            "ebay_category_id": opp.ebay_category_id,
            "has_georgian_data": (opp.georgian_listing_count or 0) > 0,
            "data_quality_warning": _build_quality_warning(opp),
        })

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": items,
        "api_usage": await get_daily_usage(),
    }


@router.get("/opportunities/{ebay_item_id}")
async def get_modern_opportunity_detail(ebay_item_id: str, db: AsyncSession = Depends(get_db)):
    item_res = await db.execute(
        select(ModernAuctionItem).where(ModernAuctionItem.ebay_item_id == ebay_item_id)
    )
    item = item_res.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Modern auction item not found")

    est_res = await db.execute(
        select(ModernPriceEstimate)
        .where(ModernPriceEstimate.auction_item_id == item.id)
        .order_by(ModernPriceEstimate.created_at.desc())
        .limit(1)
    )
    est = est_res.scalar_one_or_none()

    opp_res = await db.execute(
        select(ModernOpportunity).where(ModernOpportunity.auction_item_id == item.id)
    )
    opp = opp_res.scalar_one_or_none()

    gl_res = await db.execute(
        select(ModernGeorgianListing).where(ModernGeorgianListing.auction_item_id == item.id)
    )
    listings = gl_res.scalars().all()

    return {
        "item": {
            "ebay_item_id": item.ebay_item_id,
            "title": item.title,
            "current_bid_usd": item.current_bid_usd,
            "bid_count": item.bid_count,
            "condition": item.condition,
            "item_url": item.item_url,
            "image_url": item.image_url,
            "weight_kg": item.weight_kg,
            "weight_source": item.weight_source,
            "seller_feedback_pct": item.seller_feedback_pct,
            "ends_at": item.ends_at,
            "ebay_category_id": item.ebay_category_id,
        },
        "price_estimate": {
            "estimated_final_usd": est.estimated_final_usd if est else None,
            "confidence_score": est.confidence_score if est else None,
            "estimation_method": est.estimation_method if est else None,
            "bin_sample_count": est.bin_sample_count if est else 0,
            "bin_price_median_usd": est.bin_price_median_usd if est else None,
            "bin_price_min_usd": est.bin_price_min_usd if est else None,
            "bin_price_max_usd": est.bin_price_max_usd if est else None,
        } if est else None,
        "opportunity": {
            "estimated_final_usd": opp.estimated_final_usd if opp else None,
            "anchor_price_usd": opp.anchor_price_usd if opp else None,
            "current_discount_pct": opp.current_discount_pct if opp else None,
            "projected_discount_pct": opp.projected_discount_pct if opp else None,
            "steal_score": opp.steal_score if opp else None,
            "winability_score": opp.winability_score if opp else None,
            "demand_gate_passed": opp.demand_gate_passed if opp else None,
            "gate_reason": opp.gate_reason if opp else None,
            "final_score": opp.final_score if opp else None,
            "total_landed_cost_usd": opp.total_landed_cost_usd if opp else None,
            "total_landed_cost_gel": opp.total_landed_cost_gel if opp else None,
            "georgian_median_price_gel": opp.georgian_median_price_gel if opp else None,
            "georgian_median_price_usd": opp.georgian_median_price_usd if opp else None,
            "net_revenue_usd": opp.net_revenue_usd if opp else None,
            "selling_fees_usd": opp.selling_fees_usd if opp else None,
            "profit_margin_pct": opp.profit_margin_pct if opp else None,
            "profit_gel": opp.profit_gel if opp else None,
            "profit_usd": opp.profit_usd if opp else None,
            "margin_score": opp.margin_score if opp else None,
            "urgency_score": opp.urgency_score if opp else None,
            "confidence_score": opp.confidence_score if opp else None,
            "demand_score": opp.demand_score if opp else None,
            "competition_score": opp.competition_score if opp else None,
            "shipping_cost_usd": opp.shipping_cost_usd if opp else None,
            "vat_usd": opp.vat_usd if opp else None,
            "gel_rate_used": opp.gel_rate_used if opp else None,
            "data_quality_warning": _build_quality_warning(opp) if opp else None,
        } if opp else None,
        "georgian_listings": [
            {
                "platform": l.platform,
                "title": l.title,
                "price_gel": l.price_gel,
                "price_usd": l.price_usd,
                "url": l.url,
                "image_url": l.image_url,
                "similarity_score": l.similarity_score,
                "price_mismatch": l.price_mismatch or False,
            }
            for l in sorted(listings, key=lambda x: x.similarity_score or 0, reverse=True)
        ],
    }


@router.get("/opportunities/export.csv")
async def export_modern_opportunities_csv(
    sort_by: str = Query("final_score"),
    order: str = Query("desc"),
    min_profit_pct: Optional[float] = Query(None),
    max_bid_usd: Optional[float] = Query(None),
    min_budget_usd: Optional[float] = Query(None),
    max_budget_usd: Optional[float] = Query(None),
    category_id: Optional[str] = Query(None),
    has_georgian_data: Optional[bool] = Query(None),
    qualified_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    now = _now_utc()
    conditions = [ModernOpportunity.ends_at > now]
    if qualified_only:
        conditions.append(ModernOpportunity.demand_gate_passed == True)
    if min_profit_pct is not None:
        conditions.append(ModernOpportunity.profit_margin_pct >= min_profit_pct)
    if min_budget_usd is not None:
        conditions.append(ModernOpportunity.total_landed_cost_usd >= min_budget_usd)
    if max_budget_usd is not None:
        conditions.append(ModernOpportunity.total_landed_cost_usd <= max_budget_usd)
    if has_georgian_data is True:
        conditions.append(ModernOpportunity.georgian_listing_count > 0)
    elif has_georgian_data is False:
        conditions.append(or_(ModernOpportunity.georgian_listing_count == 0, ModernOpportunity.georgian_listing_count.is_(None)))
    if category_id:
        conditions.append(ModernOpportunity.ebay_category_id == category_id)
    if max_bid_usd is not None:
        conditions.append(ModernOpportunity.current_bid_usd <= max_bid_usd)

    col_map = {
        "final_score": ModernOpportunity.final_score,
        "steal_score": ModernOpportunity.steal_score,
        "winability_score": ModernOpportunity.winability_score,
        "profit_margin_pct": ModernOpportunity.profit_margin_pct,
        "ends_at": ModernOpportunity.ends_at,
    }
    sort_col = col_map.get(sort_by, ModernOpportunity.final_score)
    if sort_by == "ends_at":
        order_clause = asc(sort_col) if order.lower() == "asc" else desc(sort_col)
    else:
        order_clause = desc(sort_col) if order.lower() == "desc" else asc(sort_col)

    q = (
        select(ModernOpportunity, ModernAuctionItem)
        .join(ModernAuctionItem, ModernAuctionItem.id == ModernOpportunity.auction_item_id)
        .where(and_(*conditions))
        .order_by(order_clause)
    )
    rows = (await db.execute(q)).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Title", "eBay URL", "Category ID",
        "Current Bid ($)", "Est. Final ($)", "Anchor ($)",
        "Current Discount %", "Projected Discount %",
        "Steal Score", "Winability Score",
        "Gate Passed", "Gate Reason", "Final Score",
        "Landed Cost ($)", "Net Revenue ($)", "Selling Fees ($)",
        "Profit ($)", "Profit (%)",
        "Demand Score", "Confidence Score", "Competition Score",
        "Bid Count", "Ends At",
    ])
    for opp, item in rows:
        writer.writerow([
            opp.item_title,
            opp.item_url,
            opp.ebay_category_id,
            f"{opp.current_bid_usd:.2f}",
            f"{opp.estimated_final_usd:.2f}",
            f"{opp.anchor_price_usd:.2f}" if opp.anchor_price_usd is not None else "",
            f"{(opp.current_discount_pct or 0) * 100:.2f}" if opp.current_discount_pct is not None else "",
            f"{(opp.projected_discount_pct or 0) * 100:.2f}" if opp.projected_discount_pct is not None else "",
            f"{opp.steal_score:.4f}",
            f"{opp.winability_score:.4f}",
            "yes" if opp.demand_gate_passed else "no",
            opp.gate_reason or "",
            f"{opp.final_score:.2f}",
            f"{opp.total_landed_cost_usd:.2f}",
            f"{opp.net_revenue_usd:.2f}" if opp.net_revenue_usd is not None else "",
            f"{opp.selling_fees_usd:.2f}" if opp.selling_fees_usd is not None else "",
            f"{opp.profit_usd:.2f}" if opp.profit_usd is not None else "",
            f"{opp.profit_margin_pct:.2f}" if opp.profit_margin_pct is not None else "",
            f"{opp.demand_score:.4f}" if opp.demand_score is not None else "",
            f"{opp.confidence_score:.4f}",
            f"{opp.competition_score:.4f}",
            item.bid_count,
            opp.ends_at.strftime("%Y-%m-%d %H:%M UTC"),
        ])

    output.seek(0)
    filename = f"modern_opportunities_{now.strftime('%Y%m%d_%H%M')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


async def _upsert_modern_price_estimate(db: AsyncSession, item_id: int, est: dict):
    res = await db.execute(
        select(ModernPriceEstimate)
        .where(ModernPriceEstimate.auction_item_id == item_id)
        .order_by(ModernPriceEstimate.created_at.desc())
        .limit(1)
    )
    pe = res.scalar_one_or_none()
    if pe is None:
        pe = ModernPriceEstimate(auction_item_id=item_id)
        db.add(pe)
    pe.estimated_final_usd = est["estimated_final_usd"]
    pe.confidence_score = est["confidence_score"]
    pe.bin_sample_count = est["bin_sample_count"]
    pe.bin_price_median_usd = est["bin_price_median_usd"]
    pe.bin_price_min_usd = est["bin_price_min_usd"]
    pe.bin_price_max_usd = est["bin_price_max_usd"]
    pe.estimation_method = est["estimation_method"]
    pe.created_at = _now_utc()


async def _run_modern_refresh(job_id: str, category_ids: list[str], cfg: dict[str, Any]):
    total_categories = len(category_ids)
    target_nonempty_categories = max(1, int(cfg.get("max_categories_per_refresh", 20)))
    scan_cap = min(total_categories, max(target_nonempty_categories * 4, target_nonempty_categories))
    nonempty_processed = 0
    now = _now_utc()
    cumulative_scraper_status: dict[str, list[bool]] = {}
    totals = {
        "fetched_count": 0,
        "shortlisted_count": 0,
        "deep_scraped_count": 0,
        "qualified_count": 0,
        "scanned_categories": 0,
        "nonempty_categories": 0,
    }

    try:
        try:
            base_usd_gel = await get_usd_gel_rate()
        except RuntimeError as e:
            await _set_job(job_id, "error", 0, str(e))
            return

        async with AsyncSessionLocal() as db:
            cat_result = await db.execute(
                select(EbayCategory).where(EbayCategory.ebay_category_id.in_(category_ids))
            )
            cat_map = {c.ebay_category_id: c for c in cat_result.scalars().all()}

        for idx, cat_id in enumerate(category_ids[:scan_cap]):
            if nonempty_processed >= target_nonempty_categories:
                break
            totals["scanned_categories"] += 1
            cat = cat_map.get(cat_id)
            cat_name = cat.name if cat else cat_id
            await _set_job(
                job_id,
                "running",
                int((idx / max(scan_cap, 1)) * 100),
                f"[{idx+1}/{total_categories}] Stage A for {cat_name}...",
                metrics=totals,
            )

            max_items = cfg["max_items_per_category"]
            deep_k = min(cfg["deep_scrape_top_k"], max_items)
            min_h = cfg["auction_window_min_hours"]
            max_h = cfg["auction_window_max_hours"]

            try:
                raw_items = await search_auction_items(cat_id, limit=max_items)
            except Exception as e:
                print(f"[modern] eBay fetch failed for {cat_name}: {e}")
                continue

            parsed_candidates: list[dict] = []
            for raw in raw_items:
                parsed = parse_auction_item(raw)
                if not parsed.get("ebay_item_id") or not parsed.get("item_url"):
                    continue
                if (parsed.get("current_bid_usd") or 0) <= 0:
                    # Skip malformed/zero-priced summaries in modern steal-first mode.
                    continue
                ends_at = parsed["ends_at"]
                ends_naive = ends_at.replace(tzinfo=None) if ends_at.tzinfo else ends_at
                if ends_naive <= now:
                    continue
                hours_remaining = (ends_naive - now).total_seconds() / 3600.0
                if hours_remaining < min_h or hours_remaining > max_h:
                    continue
                parsed_candidates.append(parsed)
            totals["fetched_count"] += len(parsed_candidates)
            if not parsed_candidates:
                # Keep scanning the ranked pool until we have enough non-empty categories.
                async with AsyncSessionLocal() as db:
                    stat = (await db.execute(
                        select(ModernCategoryRefreshStat).where(ModernCategoryRefreshStat.category_id == cat_id)
                    )).scalar_one_or_none()
                if stat is None:
                    stat = ModernCategoryRefreshStat(category_id=cat_id)
                    db.add(stat)
                stat.last_refresh_at = _now_utc()
                stat.processed_count = 0
                stat.shortlisted_count = 0
                stat.qualified_count = 0
                stat.categories_with_positive_fetch = 0
                stat.hit_rate = 0.0
                stat.avg_steal_score = 0.0
                await db.commit()
                print(f"[modern] {cat_name}: fetched=0 shortlisted=0 qualified=0 hit_rate=0.00%")
                continue

            nonempty_processed += 1
            totals["nonempty_categories"] = nonempty_processed

            stage_a_rows: list[dict] = []
            async with AsyncSessionLocal() as db:
                for parsed in parsed_candidates:
                    res = await db.execute(
                        select(ModernAuctionItem).where(ModernAuctionItem.ebay_item_id == parsed["ebay_item_id"])
                    )
                    item = res.scalar_one_or_none()
                    if item is None:
                        item = ModernAuctionItem(**parsed, last_fetched_at=_now_utc())
                        db.add(item)
                    else:
                        item.current_bid_usd = parsed["current_bid_usd"]
                        item.bid_count = parsed["bid_count"]
                        item.condition = parsed.get("condition")
                        item.item_url = parsed["item_url"]
                        item.image_url = parsed.get("image_url")
                        item.seller_feedback_pct = parsed.get("seller_feedback_pct")
                        item.ends_at = parsed["ends_at"]
                        item.raw_item_specifics = parsed.get("raw_item_specifics")
                        item.last_fetched_at = _now_utc()
                        if item.weight_source != "user_override":
                            item.weight_kg = parsed.get("weight_kg")
                            item.weight_source = parsed.get("weight_source")

                    anchor = cat.avg_ebay_sold_usd if cat and cat.avg_ebay_sold_usd and cat.avg_ebay_sold_usd > 0 else None
                    if anchor is None:
                        anchor = calc_quick_anchor_price(parsed["current_bid_usd"], parsed["bid_count"])
                    current_discount_pct = calc_discount_pct(anchor, parsed["current_bid_usd"])
                    winability_score = calc_winability_score(parsed["ends_at"], parsed["bid_count"], parsed.get("seller_feedback_pct"))
                    steal_score = calc_steal_score(current_discount_pct, winability_score)

                    stage_a_rows.append({
                        "ebay_item_id": parsed["ebay_item_id"],
                        "anchor_price_usd": anchor,
                        "current_discount_pct": current_discount_pct,
                        "winability_score": winability_score,
                        "steal_score": steal_score,
                    })
                await db.commit()

            stage_a_rows.sort(key=lambda r: r["steal_score"], reverse=True)
            shortlist = stage_a_rows[:deep_k]
            totals["shortlisted_count"] += len(shortlist)

            async with AsyncSessionLocal() as db:
                stat_row = (await db.execute(
                    select(ModernCategoryRefreshStat).where(ModernCategoryRefreshStat.category_id == cat_id)
                )).scalar_one_or_none()
                source_stats = _load_source_stats(stat_row.source_stats_json if stat_row else None)

            qualified_for_cat = 0
            steal_scores_for_cat = [r["steal_score"] for r in shortlist]
            processed_for_cat = len(parsed_candidates)
            shortlisted_for_cat = len(shortlist)

            await _set_job(
                job_id,
                "running",
                int(((idx + 0.5) / max(scan_cap, 1)) * 100),
                f"[{idx+1}/{total_categories}] Stage B for {cat_name} ({len(shortlist)} shortlisted)...",
                metrics=totals,
            )

            cat_weight = await get_default_weight_async(cat_id)
            for row in shortlist:
                totals["deep_scraped_count"] += 1
                async with AsyncSessionLocal() as db:
                    item = (await db.execute(
                        select(ModernAuctionItem).where(ModernAuctionItem.ebay_item_id == row["ebay_item_id"])
                    )).scalar_one_or_none()
                    if item is None:
                        continue

                    est = await estimate_final_price(
                        item.title, item.current_bid_usd, item.bid_count, category_id=cat_id,
                    )
                    await _upsert_modern_price_estimate(db, item.id, est)
                    projected_discount_pct = calc_discount_pct(row["anchor_price_usd"], est["estimated_final_usd"])

                    attempt_now = _now_utc()
                    allowed_platforms = _allowed_platforms(source_stats, attempt_now)
                    geo_query = " ".join(item.title.split()[:5])
                    geo_listings, usd_gel, scraper_status = await scrape_all_platforms(
                        geo_query,
                        ebay_price_usd=item.current_bid_usd,
                        ebay_category_id=cat_id,
                        allowed_platforms=allowed_platforms,
                    )
                    if not usd_gel:
                        usd_gel = base_usd_gel

                    for platform, ok in scraper_status.items():
                        cumulative_scraper_status.setdefault(platform, []).append(ok)

                    await db.execute(delete(ModernGeorgianListing).where(ModernGeorgianListing.auction_item_id == item.id))
                    for gl in geo_listings[:15]:
                        price_usd = gl.price_gel / usd_gel if usd_gel else 0
                        db.add(ModernGeorgianListing(
                            auction_item_id=item.id,
                            platform=gl.platform,
                            title=gl.title,
                            price_gel=gl.price_gel,
                            price_usd=price_usd,
                            url=gl.url,
                            image_url=gl.image_url,
                            similarity_score=gl.similarity_score,
                            price_mismatch=gl.price_mismatch,
                            view_count=gl.view_count,
                            order_count=gl.order_count,
                        ))

                    good = [
                        gl for gl in geo_listings
                        if (gl.similarity_score or 0) >= 0.3 and not (gl.price_mismatch or False)
                    ]
                    comparable_count = len(good)
                    geo_prices_gel = [gl.price_gel for gl in good]
                    geo_median_gel = statistics.median(geo_prices_gel) if geo_prices_gel else None
                    geo_median_usd = (geo_median_gel / usd_gel) if geo_median_gel and usd_gel else None
                    view_counts = [gl.view_count for gl in good if gl.view_count is not None]
                    order_counts = [gl.order_count for gl in good if gl.order_count is not None]
                    avg_views = statistics.mean(view_counts) if view_counts else None
                    avg_orders = statistics.mean(order_counts) if order_counts else None

                    valid_by_platform: dict[str, int] = {}
                    for gl in good:
                        valid_by_platform[gl.platform] = valid_by_platform.get(gl.platform, 0) + 1
                    source_stats = _update_source_stats(source_stats, valid_by_platform, list(scraper_status.keys()), attempt_now)

                    weight_kg, _ = resolve_weight(
                        item.weight_kg, item.weight_source, cat_id,
                        db_default=cfg["default_weight_kg"], category_weight=cat_weight,
                    )
                    landed = calc_total_landed_cost(
                        est["estimated_final_usd"], weight_kg, cfg["shipping_rate_per_kg"], cfg["vat_enabled"], cfg["vat_rate"],
                    )

                    selling_fees_usd = None
                    net_revenue_usd = None
                    if geo_median_usd is not None:
                        fees_pct = cfg["platform_fee_pct"] + cfg["payment_fee_pct"]
                        selling_fees_usd = geo_median_usd * fees_pct + cfg["handling_fee_usd"]
                        net_revenue_usd = geo_median_usd - selling_fees_usd

                    score = score_opportunity(
                        est["estimated_final_usd"], landed["total_landed_cost_usd"],
                        net_revenue_usd, item.bid_count, est["confidence_score"], item.ends_at,
                        seller_feedback_pct=item.seller_feedback_pct,
                        georgian_listing_count=comparable_count,
                        avg_view_count=avg_views,
                        avg_order_count=avg_orders,
                    )

                    gate_passed, gate_reason = evaluate_demand_gate(DemandGateInput(
                        comparable_count=comparable_count,
                        demand_score=score["demand_score"],
                        profit_margin_pct=score["profit_margin_pct"],
                        ends_at=item.ends_at,
                        min_hours=min_h,
                        max_hours=max_h,
                        min_listings=cfg["demand_gate_min_listings"],
                        min_demand_score=cfg["demand_gate_min_score"],
                        min_margin_pct=cfg["target_margin_floor_pct"] * 100,
                    ))

                    # Realism guard: projected price should still look like a steal unless confidence is very high.
                    if (
                        projected_discount_pct is not None
                        and projected_discount_pct <= 0
                        and est["confidence_score"] < 0.90
                    ):
                        gate_passed = False
                        gate_reason = "negative_projected_discount"

                    if (
                        score["profit_margin_pct"] is not None
                        and score["profit_margin_pct"] > float(cfg.get("realism_max_extreme_margin_pct", 500.0))
                    ):
                        gate_passed = False
                        gate_reason = "extreme_margin"

                    final_score = calc_final_score(
                        steal_score=row["steal_score"],
                        demand_score=score["demand_score"],
                        margin_score=score["margin_score"],
                        gate_passed=gate_passed,
                    )

                    profit_usd = None
                    profit_gel = None
                    if net_revenue_usd is not None:
                        profit_usd = net_revenue_usd - landed["total_landed_cost_usd"]
                        profit_gel = profit_usd * usd_gel

                    opp = (await db.execute(
                        select(ModernOpportunity).where(ModernOpportunity.auction_item_id == item.id)
                    )).scalar_one_or_none()
                    if opp is None:
                        opp = ModernOpportunity(auction_item_id=item.id)
                        db.add(opp)

                    opp.estimated_final_usd = est["estimated_final_usd"]
                    opp.anchor_price_usd = row["anchor_price_usd"]
                    opp.current_discount_pct = row["current_discount_pct"]
                    opp.projected_discount_pct = projected_discount_pct
                    opp.steal_score = row["steal_score"]
                    opp.winability_score = row["winability_score"]
                    opp.demand_gate_passed = gate_passed
                    opp.gate_reason = gate_reason
                    opp.final_score = final_score
                    opp.weight_kg = weight_kg
                    opp.shipping_cost_usd = landed["shipping_cost_usd"]
                    opp.vat_usd = landed["vat_usd"]
                    opp.total_landed_cost_usd = landed["total_landed_cost_usd"]
                    opp.total_landed_cost_gel = landed["total_landed_cost_usd"] * usd_gel
                    opp.georgian_median_price_gel = geo_median_gel
                    opp.georgian_median_price_usd = geo_median_usd
                    opp.net_revenue_usd = net_revenue_usd
                    opp.selling_fees_usd = selling_fees_usd
                    opp.georgian_listing_count = comparable_count
                    opp.profit_usd = profit_usd
                    opp.profit_gel = profit_gel
                    opp.profit_margin_pct = score["profit_margin_pct"]
                    opp.margin_score = score["margin_score"]
                    opp.urgency_score = score["urgency_score"]
                    opp.confidence_score = score["confidence_score"]
                    opp.competition_score = score["competition_score"]
                    opp.demand_score = score["demand_score"]
                    opp.gel_rate_used = usd_gel
                    opp.vat_applied = cfg["vat_enabled"]
                    opp.last_scored_at = _now_utc()
                    opp.item_title = item.title
                    opp.item_url = item.item_url
                    opp.image_url = item.image_url
                    opp.ends_at = item.ends_at
                    opp.current_bid_usd = item.current_bid_usd
                    opp.ebay_category_id = cat_id

                    await db.commit()

                    if gate_passed:
                        qualified_for_cat += 1
                        totals["qualified_count"] += 1

            hit_rate = (qualified_for_cat / shortlisted_for_cat) if shortlisted_for_cat > 0 else 0.0
            avg_steal = statistics.mean(steal_scores_for_cat) if steal_scores_for_cat else 0.0
            async with AsyncSessionLocal() as db:
                stat = (await db.execute(
                    select(ModernCategoryRefreshStat).where(ModernCategoryRefreshStat.category_id == cat_id)
                )).scalar_one_or_none()
                if stat is None:
                    stat = ModernCategoryRefreshStat(category_id=cat_id)
                    db.add(stat)
                stat.last_refresh_at = _now_utc()
                stat.processed_count = processed_for_cat
                stat.shortlisted_count = shortlisted_for_cat
                stat.qualified_count = qualified_for_cat
                stat.categories_with_positive_fetch = 1 if processed_for_cat > 0 else 0
                stat.hit_rate = round(hit_rate, 4)
                stat.avg_steal_score = round(avg_steal, 4)
                stat.source_stats_json = json.dumps(source_stats)
                await db.commit()
            print(
                f"[modern] {cat_name}: fetched={processed_for_cat} "
                f"shortlisted={shortlisted_for_cat} qualified={qualified_for_cat} hit_rate={hit_rate:.2%}"
            )

        final_scraper_status = {
            p: (sum(results) / len(results) >= 0.5) if results else False
            for p, results in cumulative_scraper_status.items()
        }
        await _set_job(job_id, "done", 100, "Modern refresh complete", metrics=totals, scraper_status=final_scraper_status)
        print(f"[modern] Refresh done metrics={totals}")
    except Exception as e:
        await _set_job(job_id, "error", 0, str(e), metrics=totals)
