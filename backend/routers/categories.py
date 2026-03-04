"""
Category profitability analysis router.
Uses background jobs with polling.

Improvement: category analysis now uses multiple representative product queries
per category (not just the category name) to get a realistic price distribution.
"""
import asyncio
import statistics
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db, AsyncSessionLocal
from backend.models import AuctionItem, Category
from backend.services.currency_service import get_usd_gel_rate
from backend.services.ebay_client import CATEGORY_MAP, search_bin_prices
from backend.services.scraper_orchestrator import scrape_all_platforms
from backend.utils.weight_estimator import CATEGORY_DEFAULT_WEIGHTS

router = APIRouter()

_jobs: dict[str, dict] = {}

# Representative search terms per category — used instead of the generic category name.
# Multiple terms → more representative price sampling.
CATEGORY_SAMPLE_QUERIES: dict[str, list[str]] = {
    "9355":   ["iPhone 13", "Samsung Galaxy S22", "iPhone 12"],
    "177":    ["Dell laptop i5", "MacBook Air", "HP laptop 15"],
    "171485": ["iPad 9th generation", "Samsung Galaxy Tab", "iPad Air"],
    "139971": ["PlayStation 4", "Xbox One S", "Nintendo Switch"],
    "178893": ["Apple Watch Series 6", "Samsung Galaxy Watch", "Fitbit Versa"],
    "625":    ["Canon EOS camera", "Sony a6000", "Nikon D3500"],
    "293":    ["wireless earbuds", "portable speaker bluetooth", "USB hub"],
    "11450":  ["Nike sneakers men", "Levi jeans", "Adidas hoodie"],
    "11700":  ["Keurig coffee maker", "Instant Pot", "LED floor lamp"],
    "267":    ["Harry Potter book set", "Stephen King novel", "programming Python book"],
    "619":    ["Yamaha acoustic guitar", "Roland keyboard", "Shure microphone SM"],
    "220":    ["LEGO set", "Barbie doll", "Hot Wheels collection"],
}


class CategoryDTO(BaseModel):
    ebay_category_id: str
    name: str
    avg_ebay_sold_usd: Optional[float]
    avg_georgian_price_usd: Optional[float]
    avg_profit_margin_pct: Optional[float]
    avg_weight_kg: Optional[float]
    total_active_auctions: int
    last_analyzed_at: Optional[datetime]


class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int
    message: str = ""


@router.get("", response_model=list[CategoryDTO])
async def list_categories(
    sort_by: str = Query("avg_profit_margin_pct", regex="^(avg_profit_margin_pct|name|total_active_auctions)$"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Category))
    cats = result.scalars().all()

    analyzed_ids = {c.ebay_category_id for c in cats}
    for name, cat_id in CATEGORY_MAP.items():
        if cat_id not in analyzed_ids:
            cats.append(Category(
                ebay_category_id=cat_id,
                name=name,
                avg_weight_kg=CATEGORY_DEFAULT_WEIGHTS.get(cat_id),
                total_active_auctions=0,
            ))

    reverse = True
    if sort_by == "avg_profit_margin_pct":
        cats.sort(key=lambda c: c.avg_profit_margin_pct or -999, reverse=reverse)
    elif sort_by == "name":
        cats.sort(key=lambda c: c.name or "")
    elif sort_by == "total_active_auctions":
        cats.sort(key=lambda c: c.total_active_auctions or 0, reverse=reverse)

    return [CategoryDTO(
        ebay_category_id=c.ebay_category_id,
        name=c.name,
        avg_ebay_sold_usd=c.avg_ebay_sold_usd,
        avg_georgian_price_usd=c.avg_georgian_price_usd,
        avg_profit_margin_pct=c.avg_profit_margin_pct,
        avg_weight_kg=c.avg_weight_kg,
        total_active_auctions=c.total_active_auctions or 0,
        last_analyzed_at=c.last_analyzed_at,
    ) for c in cats]


@router.post("/analyze")
async def start_analyze_job():
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "progress": 0, "message": "Starting..."}
    asyncio.create_task(_run_analysis(job_id))
    return {"job_id": job_id}


@router.get("/analyze/status", response_model=JobStatus)
async def analyze_status(job_id: str = Query(...)):
    job = _jobs.get(job_id)
    if not job:
        return JobStatus(job_id=job_id, status="error", progress=0, message="Job not found")
    return JobStatus(job_id=job_id, **job)


async def _sample_ebay_prices_for_category(cat_id: str, cat_name: str) -> list[float]:
    """
    Search multiple representative queries for a category and pool the BIN prices.
    This gives a far more representative median than a single generic query.
    """
    queries = CATEGORY_SAMPLE_QUERIES.get(cat_id, [cat_name])
    all_prices: list[float] = []
    for q in queries:
        try:
            prices = await search_bin_prices(q, category_id=cat_id, limit=10)
            all_prices.extend(prices)
        except Exception:
            pass
        await asyncio.sleep(0.3)  # gentle throttle between queries
    return all_prices


async def _sample_georgian_prices_for_category(cat_id: str) -> tuple[list[float], Optional[float]]:
    """
    Scrape a sample of Georgian listings using category representative queries.
    Returns (gel_prices, usd_gel_rate).  Rate may be None if unavailable.
    """
    queries = CATEGORY_SAMPLE_QUERIES.get(cat_id, [])[:2]  # limit Georgian scrapes
    all_gel_prices: list[float] = []

    # Fetch rate upfront — no hardcoded fallback
    try:
        usd_gel: Optional[float] = await get_usd_gel_rate()
    except RuntimeError:
        usd_gel = None

    for q in queries:
        try:
            listings, rate, _ = await scrape_all_platforms(q, ebay_price_usd=0)
            usd_gel = rate  # use freshest rate from scraper
            good = [l.price_gel for l in listings if l.similarity_score >= 0.3 and l.price_gel > 0]
            all_gel_prices.extend(good)
        except Exception:
            pass
    return all_gel_prices, usd_gel


async def _run_analysis(job_id: str):
    categories = list(CATEGORY_MAP.items())
    total = len(categories)

    try:
        for i, (name, cat_id) in enumerate(categories):
            _jobs[job_id]["message"] = f"Analyzing {name}..."
            _jobs[job_id]["progress"] = int((i / total) * 100)

            try:
                ebay_prices = await _sample_ebay_prices_for_category(cat_id, name)
                avg_ebay = statistics.median(ebay_prices) if len(ebay_prices) >= 3 else None

                geo_prices_gel, usd_gel = await _sample_georgian_prices_for_category(cat_id)
                avg_geo_gel = statistics.median(geo_prices_gel) if len(geo_prices_gel) >= 3 else None
                avg_geo_usd = (avg_geo_gel / usd_gel) if avg_geo_gel and usd_gel else None

                margin = None
                if avg_ebay and avg_geo_usd:
                    margin = (avg_geo_usd - avg_ebay) / avg_ebay * 100

                async with AsyncSessionLocal() as db:
                    res = await db.execute(select(Category).where(Category.ebay_category_id == cat_id))
                    cat = res.scalar_one_or_none()
                    if cat is None:
                        cat = Category(ebay_category_id=cat_id, name=name)
                        db.add(cat)
                    cat.avg_ebay_sold_usd = avg_ebay
                    cat.avg_georgian_price_usd = avg_geo_usd
                    cat.avg_profit_margin_pct = margin
                    cat.avg_weight_kg = CATEGORY_DEFAULT_WEIGHTS.get(cat_id)
                    cat.last_analyzed_at = datetime.utcnow()

                    # B4: update active auction count from DB (was always 0 before)
                    now_ts = datetime.utcnow()
                    count_res = await db.execute(
                        select(func.count()).select_from(AuctionItem).where(
                            AuctionItem.ebay_category_id == cat_id,
                            AuctionItem.ends_at > now_ts,
                        )
                    )
                    cat.total_active_auctions = count_res.scalar_one() or 0

                    await db.commit()

            except Exception as e:
                print(f"[categories] Failed to analyze {name}: {e}")

            await asyncio.sleep(0.5)

        _jobs[job_id] = {"status": "done", "progress": 100, "message": "Analysis complete"}
    except Exception as e:
        _jobs[job_id] = {"status": "error", "progress": 0, "message": str(e)}
