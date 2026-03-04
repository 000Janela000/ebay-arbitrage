"""
Auctions router: search, refresh job, weight override.

Bug fixes applied:
  - Expired auction items + opportunities purged on every refresh
  - PriceEstimate upserted (not inserted) to stop DB bloat
  - _rescore_item now recalculates profit_gel and profit_usd
  - Weight validation: 0.01 – 200 kg
  - scrape_all_platforms returns scraper_status; exposed in job result
  - Calls to get_usd_gel_rate are wrapped to handle RuntimeError
"""
import asyncio
import statistics
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import and_, asc, desc, or_, select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db, AsyncSessionLocal
from backend.models import AuctionItem, GeorgianListing, Opportunity, PriceEstimate, Setting
from backend.services.currency_service import get_usd_gel_rate
from backend.services.ebay_client import (
    CATEGORY_MAP, parse_auction_item, search_auction_items
)
from backend.services.opportunity_scorer import score_opportunity
from backend.services.price_estimator import estimate_final_price
from backend.services.scraper_orchestrator import scrape_all_platforms
from backend.utils.shipping import calc_total_landed_cost
from backend.utils.weight_estimator import resolve_weight

router = APIRouter()

_jobs: dict[str, dict] = {}


class WeightOverride(BaseModel):
    weight_kg: float

    @field_validator("weight_kg")
    @classmethod
    def validate_weight(cls, v: float) -> float:
        if v < 0.01 or v > 200:
            raise ValueError("weight_kg must be between 0.01 and 200 kg")
        return round(v, 3)


class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int
    message: str = ""
    scraper_status: dict = {}


class AuctionOpportunityDTO(BaseModel):
    ebay_item_id: str
    title: str
    image_url: Optional[str]
    item_url: str
    current_bid_usd: float
    estimated_final_usd: float
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
    georgian_listing_count: int
    profit_margin_pct: Optional[float]
    profit_gel: Optional[float]
    opportunity_score: float
    margin_score: float
    urgency_score: float
    confidence_score: float
    competition_score: float
    ebay_category_id: str
    has_georgian_data: bool
    data_quality_warning: Optional[str]


@router.get("", response_model=list[AuctionOpportunityDTO])
async def list_auctions(
    category_id: Optional[str] = Query(None),
    sort_by: str = Query("opportunity_score"),
    order: str = Query("desc"),
    min_profit_pct: Optional[float] = Query(None),
    max_bid_usd: Optional[float] = Query(None),
    has_georgian_data: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    # B3: all filtering and sorting done in SQL — no Python-side loops
    now = datetime.utcnow()

    conditions = [Opportunity.ends_at > now]
    if min_profit_pct is not None:
        conditions.append(Opportunity.profit_margin_pct >= min_profit_pct)
    if has_georgian_data is True:
        conditions.append(Opportunity.georgian_listing_count > 0)
    elif has_georgian_data is False:
        conditions.append(
            or_(Opportunity.georgian_listing_count == 0, Opportunity.georgian_listing_count.is_(None))
        )

    col_map = {
        "opportunity_score": Opportunity.opportunity_score,
        "profit_margin_pct": Opportunity.profit_margin_pct,
        "current_bid_usd": Opportunity.current_bid_usd,
        "ends_at": Opportunity.ends_at,
    }
    sort_col = col_map.get(sort_by, Opportunity.opportunity_score)
    if sort_by == "ends_at":
        order_clause = asc(sort_col) if order.lower() == "asc" else desc(sort_col)
    else:
        order_clause = desc(sort_col) if order.lower() == "desc" else asc(sort_col)

    q = (
        select(Opportunity, AuctionItem)
        .join(AuctionItem, Opportunity.auction_item_id == AuctionItem.id)
        .where(and_(*conditions))
    )
    if category_id:
        q = q.where(AuctionItem.ebay_category_id == category_id)
    if max_bid_usd is not None:
        q = q.where(AuctionItem.current_bid_usd <= max_bid_usd)
    q = q.order_by(order_clause)

    result = await db.execute(q)
    rows = result.all()

    dtos = []
    for opp, item in rows:
        seconds_remaining = max(0, (opp.ends_at - now).total_seconds())
        quality_warning = _build_quality_warning(opp)
        has_geo = (opp.georgian_listing_count or 0) > 0

        dtos.append(AuctionOpportunityDTO(
            ebay_item_id=item.ebay_item_id,
            title=opp.item_title,
            image_url=opp.image_url,
            item_url=opp.item_url,
            current_bid_usd=opp.current_bid_usd,
            estimated_final_usd=opp.estimated_final_usd,
            bid_count=item.bid_count,
            ends_at=opp.ends_at,
            seconds_remaining=seconds_remaining,
            weight_kg=opp.weight_kg,
            weight_source=item.weight_source or "category_default",
            shipping_cost_usd=opp.shipping_cost_usd,
            vat_usd=opp.vat_usd,
            total_landed_cost_usd=opp.total_landed_cost_usd,
            total_landed_cost_gel=opp.total_landed_cost_gel,
            georgian_median_price_gel=opp.georgian_median_price_gel,
            georgian_median_price_usd=opp.georgian_median_price_usd,
            georgian_listing_count=opp.georgian_listing_count,
            profit_margin_pct=opp.profit_margin_pct,
            profit_gel=opp.profit_gel,
            opportunity_score=opp.opportunity_score,
            margin_score=opp.margin_score,
            urgency_score=opp.urgency_score,
            confidence_score=opp.confidence_score,
            competition_score=opp.competition_score,
            ebay_category_id=item.ebay_category_id,
            has_georgian_data=has_geo,
            data_quality_warning=quality_warning,
        ))

    return dtos


def _build_quality_warning(opp: Opportunity) -> Optional[str]:
    warnings = []
    if not opp.georgian_listing_count:
        warnings.append("No Georgian listings found")
    if opp.confidence_score is not None and opp.confidence_score < 0.35:
        warnings.append("Low price estimate confidence")
    if opp.profit_margin_pct is not None and opp.profit_margin_pct > 500:
        warnings.append("Unusually high margin — verify match")
    return "; ".join(warnings) if warnings else None


@router.post("/refresh")
async def start_refresh(category_id: Optional[str] = None):
    if category_id is None:
        categories = list(CATEGORY_MAP.values())
    else:
        categories = [category_id]

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "progress": 0, "message": "Starting refresh...", "scraper_status": {}}
    asyncio.create_task(_run_refresh(job_id, categories))
    return {"job_id": job_id}


@router.get("/refresh/status", response_model=JobStatus)
async def refresh_status(job_id: str = Query(...)):
    job = _jobs.get(job_id)
    if not job:
        return JobStatus(job_id=job_id, status="error", progress=0, message="Job not found")
    return JobStatus(job_id=job_id, **job)


@router.get("/{ebay_item_id}")
async def get_auction_detail(ebay_item_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AuctionItem).where(AuctionItem.ebay_item_id == ebay_item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Auction item not found")

    listings_result = await db.execute(
        select(GeorgianListing).where(GeorgianListing.auction_item_id == item.id)
    )
    listings = listings_result.scalars().all()

    estimate_result = await db.execute(
        select(PriceEstimate)
        .where(PriceEstimate.auction_item_id == item.id)
        .order_by(PriceEstimate.created_at.desc())
        .limit(1)
    )
    estimate = estimate_result.scalar_one_or_none()

    opp_result = await db.execute(
        select(Opportunity).where(Opportunity.auction_item_id == item.id)
    )
    opp = opp_result.scalar_one_or_none()

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
            "estimated_final_usd": estimate.estimated_final_usd if estimate else None,
            "confidence_score": estimate.confidence_score if estimate else None,
            "estimation_method": estimate.estimation_method if estimate else None,
            "bin_sample_count": estimate.bin_sample_count if estimate else 0,
            "bin_price_median_usd": estimate.bin_price_median_usd if estimate else None,
            "bin_price_min_usd": estimate.bin_price_min_usd if estimate else None,
            "bin_price_max_usd": estimate.bin_price_max_usd if estimate else None,
        } if estimate else None,
        "opportunity": {
            "total_landed_cost_usd": opp.total_landed_cost_usd if opp else None,
            "total_landed_cost_gel": opp.total_landed_cost_gel if opp else None,
            "profit_margin_pct": opp.profit_margin_pct if opp else None,
            "profit_gel": opp.profit_gel if opp else None,
            "profit_usd": opp.profit_usd if opp else None,
            "opportunity_score": opp.opportunity_score if opp else None,
            "margin_score": opp.margin_score if opp else None,
            "urgency_score": opp.urgency_score if opp else None,
            "confidence_score": opp.confidence_score if opp else None,
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


@router.put("/{ebay_item_id}/weight")
async def override_weight(
    ebay_item_id: str,
    body: WeightOverride,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AuctionItem).where(AuctionItem.ebay_item_id == ebay_item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Auction item not found")

    item.weight_kg = body.weight_kg
    item.weight_source = "user_override"
    await db.commit()

    await _rescore_item(item.id)
    return {"ok": True, "weight_kg": body.weight_kg}


async def _get_settings_dict() -> dict:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Setting))
        return {r.key: r.value for r in result.scalars().all()}


async def _purge_expired_items():
    """Delete auction items and their cascaded children that have already ended."""
    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        expired_ids_result = await db.execute(
            select(AuctionItem.id).where(AuctionItem.ends_at < now)
        )
        expired_ids = [row[0] for row in expired_ids_result.all()]
        if expired_ids:
            await db.execute(delete(AuctionItem).where(AuctionItem.id.in_(expired_ids)))
            await db.commit()
            print(f"[refresh] Purged {len(expired_ids)} expired auction items")


async def _upsert_price_estimate(db: AsyncSession, item_id: int, est: dict):
    """Insert or replace the price estimate for an item (one row per item)."""
    res = await db.execute(
        select(PriceEstimate)
        .where(PriceEstimate.auction_item_id == item_id)
        .order_by(PriceEstimate.created_at.desc())
        .limit(1)
    )
    pe = res.scalar_one_or_none()
    if pe is None:
        pe = PriceEstimate(auction_item_id=item_id)
        db.add(pe)
    pe.estimated_final_usd = est["estimated_final_usd"]
    pe.confidence_score = est["confidence_score"]
    pe.bin_sample_count = est["bin_sample_count"]
    pe.bin_price_median_usd = est["bin_price_median_usd"]
    pe.bin_price_min_usd = est["bin_price_min_usd"]
    pe.bin_price_max_usd = est["bin_price_max_usd"]
    pe.estimation_method = est["estimation_method"]
    pe.created_at = datetime.utcnow()
    return pe


async def _run_refresh(job_id: str, category_ids: list[str]):
    total_cats = len(category_ids)
    processed = 0
    cumulative_scraper_status: dict[str, list[bool]] = {}

    try:
        s = await _get_settings_dict()
        shipping_rate = float(s.get("shipping_rate_per_kg", "9.0"))
        vat_enabled = s.get("vat_enabled", "false").lower() == "true"
        vat_rate = float(s.get("vat_rate", "0.18"))
        default_weight = float(s.get("default_weight_kg", "0.5"))

        # Purge expired items before fetching new data
        await _purge_expired_items()

        try:
            usd_gel = await get_usd_gel_rate()
        except RuntimeError as e:
            _jobs[job_id] = {"status": "error", "progress": 0, "message": str(e), "scraper_status": {}}
            return

        cat_names = {v: k for k, v in CATEGORY_MAP.items()}
        for cat_idx, cat_id in enumerate(category_ids):
            cat_name = cat_names.get(cat_id, cat_id)
            _jobs[job_id]["message"] = f"[{cat_idx+1}/{total_cats}] Fetching eBay auctions for {cat_name}..."
            _jobs[job_id]["progress"] = int((processed / max(total_cats * 3, 1)) * 100)
            print(f"[refresh] [{cat_idx+1}/{total_cats}] Fetching eBay auctions for {cat_name} (cat_id={cat_id})...")

            try:
                raw_items = await search_auction_items(cat_id, limit=50)
                print(f"[refresh]   Found {len(raw_items)} raw auction items")
            except Exception as e:
                print(f"[refresh] eBay fetch failed for {cat_name}: {e}")
                processed += 3
                continue

            # Filter expired items (timezone-aware handling)
            now = datetime.utcnow()
            valid_items = []
            for raw in raw_items:
                parsed = parse_auction_item(raw)
                ends_at = parsed["ends_at"]
                ends_naive = ends_at.replace(tzinfo=None) if ends_at.tzinfo else ends_at
                if ends_naive > now:
                    valid_items.append(parsed)

            print(f"[refresh]   {len(valid_items)} items still active (not expired)")
            processed += 1
            _jobs[job_id]["progress"] = int((processed / max(total_cats * 3, 1)) * 100)

            # Upsert auction items
            async with AsyncSessionLocal() as db:
                item_objs = []
                for parsed in valid_items:
                    res = await db.execute(
                        select(AuctionItem).where(AuctionItem.ebay_item_id == parsed["ebay_item_id"])
                    )
                    item = res.scalar_one_or_none()
                    if item is None:
                        item = AuctionItem(**parsed, last_fetched_at=datetime.utcnow())
                        db.add(item)
                    else:
                        item.current_bid_usd = parsed["current_bid_usd"]
                        item.bid_count = parsed["bid_count"]
                        item.ends_at = parsed["ends_at"]
                        item.last_fetched_at = datetime.utcnow()
                        if item.weight_source != "user_override":
                            item.weight_kg = parsed["weight_kg"]
                            item.weight_source = parsed["weight_source"]
                    item_objs.append((item, parsed))
                await db.commit()
                for item, _ in item_objs:
                    await db.refresh(item)

            print(f"[refresh]   Saved {len(valid_items)} auction items to DB")
            processed += 1
            _jobs[job_id]["progress"] = int((processed / max(total_cats * 3, 1)) * 100)
            _jobs[job_id]["message"] = f"[{cat_idx+1}/{total_cats}] Estimating prices & scraping Georgian data for {len(valid_items)} items..."
            print(f"[refresh]   Estimating prices & scraping Georgian data for {len(valid_items)} items...")

            items_with_geo = 0
            for item_idx, parsed in enumerate(valid_items):
                try:
                    async with AsyncSessionLocal() as db:
                        res = await db.execute(
                            select(AuctionItem).where(AuctionItem.ebay_item_id == parsed["ebay_item_id"])
                        )
                        item = res.scalar_one_or_none()
                        if not item:
                            continue

                        # Price estimate (upsert — no accumulation)
                        est = await estimate_final_price(
                            item.title, item.current_bid_usd, item.bid_count, category_id=cat_id,
                        )
                        await _upsert_price_estimate(db, item.id, est)

                        # Georgian scraping
                        geo_query = " ".join(item.title.split()[:5])
                        geo_listings, usd_gel, scraper_status = await scrape_all_platforms(
                            geo_query, ebay_price_usd=item.current_bid_usd,
                            ebay_category_id=cat_id,
                        )

                        # Track scraper health
                        for platform, ok in scraper_status.items():
                            cumulative_scraper_status.setdefault(platform, []).append(ok)

                        # Replace Georgian listings
                        await db.execute(
                            delete(GeorgianListing).where(GeorgianListing.auction_item_id == item.id)
                        )
                        for gl in geo_listings[:15]:
                            price_usd = gl.price_gel / usd_gel if usd_gel else 0
                            db.add(GeorgianListing(
                                auction_item_id=item.id,
                                platform=gl.platform,
                                title=gl.title,
                                price_gel=gl.price_gel,
                                price_usd=price_usd,
                                url=gl.url,
                                image_url=gl.image_url,
                                similarity_score=gl.similarity_score,
                                price_mismatch=gl.price_mismatch,
                            ))

                        # Scoring
                        weight_kg, _ = resolve_weight(
                            item.weight_kg, item.weight_source, cat_id, db_default=default_weight,
                        )
                        landed = calc_total_landed_cost(
                            est["estimated_final_usd"], weight_kg, shipping_rate, vat_enabled, vat_rate,
                        )

                        good_listings = [gl for gl in geo_listings if gl.similarity_score >= 0.3]
                        if good_listings:
                            items_with_geo += 1
                        geo_prices_gel = [gl.price_gel for gl in good_listings]
                        geo_median_gel = statistics.median(geo_prices_gel) if geo_prices_gel else None
                        geo_median_usd = (geo_median_gel / usd_gel) if geo_median_gel and usd_gel else None

                        scores = score_opportunity(
                            est["estimated_final_usd"], landed["total_landed_cost_usd"],
                            geo_median_usd, item.bid_count, est["confidence_score"], item.ends_at,
                            seller_feedback_pct=item.seller_feedback_pct,
                            georgian_listing_count=len(geo_listings),
                        )

                        profit_gel = None
                        profit_usd = None
                        if geo_median_gel is not None and geo_median_usd is not None:
                            profit_usd = geo_median_usd - landed["total_landed_cost_usd"]
                            profit_gel = geo_median_gel - (landed["total_landed_cost_usd"] * usd_gel)

                        # Upsert opportunity
                        opp_res = await db.execute(
                            select(Opportunity).where(Opportunity.auction_item_id == item.id)
                        )
                        opp = opp_res.scalar_one_or_none()
                        if opp is None:
                            opp = Opportunity(auction_item_id=item.id)
                            db.add(opp)

                        opp.estimated_final_usd = est["estimated_final_usd"]
                        opp.weight_kg = weight_kg
                        opp.shipping_cost_usd = landed["shipping_cost_usd"]
                        opp.vat_usd = landed["vat_usd"]
                        opp.total_landed_cost_usd = landed["total_landed_cost_usd"]
                        opp.total_landed_cost_gel = landed["total_landed_cost_usd"] * usd_gel
                        opp.georgian_median_price_gel = geo_median_gel
                        opp.georgian_median_price_usd = geo_median_usd
                        opp.georgian_listing_count = len(geo_listings)
                        opp.profit_usd = profit_usd
                        opp.profit_gel = profit_gel
                        opp.profit_margin_pct = scores["profit_margin_pct"]
                        opp.margin_score = scores["margin_score"]
                        opp.urgency_score = scores["urgency_score"]
                        opp.confidence_score = scores["confidence_score"]
                        opp.competition_score = scores["competition_score"]
                        opp.opportunity_score = scores["opportunity_score"]
                        opp.gel_rate_used = usd_gel
                        opp.vat_applied = vat_enabled
                        opp.last_scored_at = datetime.utcnow()
                        opp.item_title = item.title
                        opp.item_url = item.item_url
                        opp.image_url = item.image_url
                        opp.ends_at = item.ends_at
                        opp.current_bid_usd = item.current_bid_usd

                        await db.commit()
                except Exception as e:
                    print(f"[refresh] Item processing failed ({parsed.get('title', '?')[:40]}): {e}")

            print(f"[refresh]   Done with {cat_name}: {len(valid_items)} items processed, {items_with_geo} with Georgian price data")
            processed += 1
            _jobs[job_id]["progress"] = int((processed / max(total_cats * 3, 1)) * 100)

        # Summarise scraper health
        final_scraper_status = {
            p: (sum(results) / len(results) >= 0.5) if results else False
            for p, results in cumulative_scraper_status.items()
        }
        _jobs[job_id] = {
            "status": "done",
            "progress": 100,
            "message": "Refresh complete",
            "scraper_status": final_scraper_status,
        }
    except Exception as e:
        _jobs[job_id] = {"status": "error", "progress": 0, "message": str(e), "scraper_status": {}}


async def _rescore_item(item_id: int):
    """Re-score a single item's opportunity after weight override."""
    try:
        s = await _get_settings_dict()
        shipping_rate = float(s.get("shipping_rate_per_kg", "9.0"))
        vat_enabled = s.get("vat_enabled", "false").lower() == "true"
        vat_rate = float(s.get("vat_rate", "0.18"))

        try:
            usd_gel = await get_usd_gel_rate()
        except RuntimeError:
            return  # Can't rescore without a valid rate

        async with AsyncSessionLocal() as db:
            item_res = await db.execute(select(AuctionItem).where(AuctionItem.id == item_id))
            item = item_res.scalar_one_or_none()
            if not item:
                return

            est_res = await db.execute(
                select(PriceEstimate)
                .where(PriceEstimate.auction_item_id == item_id)
                .order_by(PriceEstimate.created_at.desc())
                .limit(1)
            )
            est = est_res.scalar_one_or_none()
            if not est:
                return

            opp_res = await db.execute(
                select(Opportunity).where(Opportunity.auction_item_id == item_id)
            )
            opp = opp_res.scalar_one_or_none()
            if not opp:
                return

            geo_res = await db.execute(
                select(GeorgianListing).where(GeorgianListing.auction_item_id == item_id)
            )
            geo_listings = geo_res.scalars().all()
            good = [gl for gl in geo_listings if (gl.similarity_score or 0) >= 0.3]
            geo_prices_gel = [gl.price_gel for gl in good]
            geo_median_gel = statistics.median(geo_prices_gel) if geo_prices_gel else None
            geo_median_usd = (geo_median_gel / usd_gel) if geo_median_gel and usd_gel else None

            landed = calc_total_landed_cost(
                est.estimated_final_usd, item.weight_kg, shipping_rate, vat_enabled, vat_rate,
            )
            scores = score_opportunity(
                est.estimated_final_usd, landed["total_landed_cost_usd"],
                geo_median_usd, item.bid_count, est.confidence_score, item.ends_at,
                seller_feedback_pct=item.seller_feedback_pct,
                georgian_listing_count=len(geo_listings),
            )

            # Recalculate profit in both currencies (was missing before)
            profit_usd = None
            profit_gel = None
            if geo_median_usd is not None and geo_median_gel is not None:
                profit_usd = geo_median_usd - landed["total_landed_cost_usd"]
                profit_gel = geo_median_gel - (landed["total_landed_cost_usd"] * usd_gel)

            opp.weight_kg = item.weight_kg
            opp.shipping_cost_usd = landed["shipping_cost_usd"]
            opp.vat_usd = landed["vat_usd"]
            opp.total_landed_cost_usd = landed["total_landed_cost_usd"]
            opp.total_landed_cost_gel = landed["total_landed_cost_usd"] * usd_gel
            opp.georgian_median_price_usd = geo_median_usd
            opp.profit_usd = profit_usd
            opp.profit_gel = profit_gel
            opp.profit_margin_pct = scores["profit_margin_pct"]
            opp.margin_score = scores["margin_score"]
            opp.urgency_score = scores["urgency_score"]
            opp.confidence_score = scores["confidence_score"]
            opp.competition_score = scores["competition_score"]
            opp.opportunity_score = scores["opportunity_score"]
            opp.gel_rate_used = usd_gel
            opp.last_scored_at = datetime.utcnow()
            await db.commit()
    except Exception as e:
        print(f"[rescore] Failed: {e}")
