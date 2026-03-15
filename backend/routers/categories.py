"""
Category tree browsing and on-demand profitability analysis.
Replaces the old flat 12-category system with eBay's full category hierarchy.
"""
import asyncio
import json
import statistics
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db, AsyncSessionLocal
from backend.models import AuctionItem, EbayCategory, CategoryTreeMeta
from backend.services.category_tree_service import (
    get_children, get_child_counts, get_ancestors, search_categories,
    get_tracked_categories, resolve_mymarket_cats,
    sync_category_tree, get_category_by_id, get_leaf_descendants,
    count_leaf_descendants,
)
from backend.services.currency_service import get_usd_gel_rate
from backend.services.ebay_client import search_bin_prices
from backend.services.job_store import get_job as get_persisted_job
from backend.services.job_store import upsert_job

router = APIRouter()

_jobs: dict[str, dict] = {}
_JOB_TYPE = "categories_analysis"


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
        payload={},
    )


async def _set_job(job_id: str, status: str, progress: int, message: str):
    _jobs[job_id] = {"status": status, "progress": max(0, min(100, int(progress))), "message": message}
    await _persist_job(job_id)


# ---------- DTOs ----------

class CategoryNodeDTO(BaseModel):
    ebay_category_id: str
    name: str
    child_count: int
    is_leaf: bool
    is_tracked: bool
    avg_profit_margin_pct: Optional[float]
    last_analyzed_at: Optional[datetime]


class BreadcrumbDTO(BaseModel):
    ebay_category_id: str
    name: str


class CategorySearchResultDTO(BaseModel):
    ebay_category_id: str
    name: str
    breadcrumb_path: str
    is_leaf: bool
    is_tracked: bool
    avg_profit_margin_pct: Optional[float]


class TrackedCategoryDTO(BaseModel):
    ebay_category_id: str
    name: str
    breadcrumb_path: str
    is_leaf: bool
    avg_ebay_sold_usd: Optional[float]
    avg_georgian_price_usd: Optional[float]
    avg_profit_margin_pct: Optional[float]
    avg_weight_kg: Optional[float]
    total_active_auctions: int
    last_analyzed_at: Optional[datetime]
    manual_pin: bool
    manual_block: bool
    track_source: str
    auto_track_score: Optional[float]
    auto_tracked_at: Optional[datetime]


class TreeMetaDTO(BaseModel):
    tree_version: Optional[str]
    last_fetched_at: Optional[datetime]
    total_categories: Optional[int]


class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int
    message: str = ""


# ---------- Tree browsing endpoints ----------

@router.get("/tree/roots", response_model=list[CategoryNodeDTO])
async def list_root_categories():
    """Get top-level eBay categories."""
    children = await get_children(None)
    counts = await get_child_counts(None)
    return [
        CategoryNodeDTO(
            ebay_category_id=c.ebay_category_id,
            name=c.name,
            child_count=counts.get(c.ebay_category_id, 0),
            is_leaf=c.is_leaf,
            is_tracked=c.is_tracked,
            avg_profit_margin_pct=c.avg_profit_margin_pct,
            last_analyzed_at=c.last_analyzed_at,
        )
        for c in children
    ]


@router.get("/tree/{category_id}/children", response_model=list[CategoryNodeDTO])
async def list_children(category_id: str):
    """Get immediate children of a category."""
    children = await get_children(category_id)
    counts = await get_child_counts(category_id)
    return [
        CategoryNodeDTO(
            ebay_category_id=c.ebay_category_id,
            name=c.name,
            child_count=counts.get(c.ebay_category_id, 0),
            is_leaf=c.is_leaf,
            is_tracked=c.is_tracked,
            avg_profit_margin_pct=c.avg_profit_margin_pct,
            last_analyzed_at=c.last_analyzed_at,
        )
        for c in children
    ]


@router.get("/tree/{category_id}/breadcrumb", response_model=list[BreadcrumbDTO])
async def get_breadcrumb(category_id: str):
    """Get the ancestor chain from root to the given category."""
    ancestors = await get_ancestors(category_id)
    return [BreadcrumbDTO(**a) for a in ancestors]


@router.get("/tree/meta", response_model=TreeMetaDTO)
async def get_tree_meta(db: AsyncSession = Depends(get_db)):
    """Get metadata about the category tree."""
    result = await db.execute(select(CategoryTreeMeta).where(CategoryTreeMeta.id == 1))
    meta = result.scalar_one_or_none()
    if meta is None:
        return TreeMetaDTO(tree_version=None, last_fetched_at=None, total_categories=None)
    return TreeMetaDTO(
        tree_version=meta.tree_version,
        last_fetched_at=meta.last_fetched_at,
        total_categories=meta.total_categories,
    )


# ---------- Search ----------

@router.get("/search", response_model=list[CategorySearchResultDTO])
async def search_category_names(q: str = Query(..., min_length=2)):
    """Search category names by keyword."""
    cats = await search_categories(q, limit=50)

    results = []
    for cat in cats:
        ancestors = await get_ancestors(cat.ebay_category_id)
        path = " > ".join(a["name"] for a in ancestors)
        results.append(CategorySearchResultDTO(
            ebay_category_id=cat.ebay_category_id,
            name=cat.name,
            breadcrumb_path=path,
            is_leaf=cat.is_leaf,
            is_tracked=cat.is_tracked,
            avg_profit_margin_pct=cat.avg_profit_margin_pct,
        ))

    return results


# ---------- Tracked categories ----------

@router.get("/tracked", response_model=list[TrackedCategoryDTO])
async def list_tracked():
    """Get all tracked categories with their analysis data."""
    cats = await get_tracked_categories()

    results = []
    for cat in cats:
        ancestors = await get_ancestors(cat.ebay_category_id)
        path = " > ".join(a["name"] for a in ancestors)
        results.append(TrackedCategoryDTO(
            ebay_category_id=cat.ebay_category_id,
            name=cat.name,
            breadcrumb_path=path,
            is_leaf=cat.is_leaf,
            avg_ebay_sold_usd=cat.avg_ebay_sold_usd,
            avg_georgian_price_usd=cat.avg_georgian_price_usd,
            avg_profit_margin_pct=cat.avg_profit_margin_pct,
            avg_weight_kg=cat.avg_weight_kg,
            total_active_auctions=cat.total_active_auctions or 0,
            last_analyzed_at=cat.last_analyzed_at,
            manual_pin=bool(cat.manual_pin),
            manual_block=bool(cat.manual_block),
            track_source=cat.track_source or "none",
            auto_track_score=cat.auto_track_score,
            auto_tracked_at=cat.auto_tracked_at,
        ))

    return results


async def _apply_tracking_override(category_id: str, mode: str) -> bool:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(EbayCategory).where(EbayCategory.ebay_category_id == category_id)
        )
        cat = result.scalar_one_or_none()
        if cat is None:
            return False

        if mode == "pin":
            cat.manual_pin = True
            cat.manual_block = False
            cat.is_tracked = True
            cat.track_source = "manual"
        elif mode == "block":
            cat.manual_pin = False
            cat.manual_block = True
            cat.is_tracked = False
            cat.track_source = "manual"
        elif mode == "clear":
            cat.manual_pin = False
            cat.manual_block = False
            # Do not force is_tracked here; advisor decides when auto mode runs.
            if cat.track_source == "manual":
                cat.track_source = "none"
        else:
            raise ValueError(f"Unknown override mode: {mode}")

        await db.commit()
        return True


@router.post("/{category_id}/track")
async def track_category(category_id: str):
    """Legacy alias: track maps to manual pin."""
    found = await _apply_tracking_override(category_id, "pin")
    if not found:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"ok": True, "mode": "pin"}


@router.delete("/{category_id}/track")
async def untrack_category(category_id: str):
    """Legacy alias: untrack maps to manual block."""
    found = await _apply_tracking_override(category_id, "block")
    if not found:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"ok": True, "mode": "block"}


@router.post("/{category_id}/pin")
async def pin_category(category_id: str):
    found = await _apply_tracking_override(category_id, "pin")
    if not found:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"ok": True}


@router.post("/{category_id}/block")
async def block_category(category_id: str):
    found = await _apply_tracking_override(category_id, "block")
    if not found:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"ok": True}


@router.delete("/{category_id}/override")
async def clear_category_override(category_id: str):
    found = await _apply_tracking_override(category_id, "clear")
    if not found:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"ok": True}


# ---------- On-demand analysis ----------

@router.post("/{category_id}/analyze")
async def analyze_single_category(category_id: str):
    """Analyze a single category's profitability (1 eBay API call)."""
    cat = await get_category_by_id(category_id)
    if cat is None:
        raise HTTPException(status_code=404, detail="Category not found")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "progress": 0, "message": f"Analyzing {cat.name}..."}
    await _persist_job(job_id)
    asyncio.create_task(_run_single_analysis(job_id, category_id, cat.name))
    return {"job_id": job_id}


@router.post("/analyze")
async def analyze_all_tracked():
    """Analyze all tracked categories."""
    cats = await get_tracked_categories()
    if not cats:
        raise HTTPException(status_code=400, detail="No tracked categories. Track some categories first.")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "progress": 0, "message": "Starting analysis..."}
    await _persist_job(job_id)
    asyncio.create_task(_run_batch_analysis(job_id, [(c.ebay_category_id, c.name) for c in cats]))
    return {"job_id": job_id}


@router.get("/analyze/status", response_model=JobStatus)
async def analyze_status(job_id: str = Query(...)):
    job = _jobs.get(job_id)
    if not job:
        persisted = await get_persisted_job(job_id)
        if persisted:
            return JobStatus(
                job_id=job_id,
                status=persisted["status"],
                progress=persisted["progress"],
                message=persisted["message"],
            )
        return JobStatus(job_id=job_id, status="error", progress=0, message="Job not found")
    return JobStatus(job_id=job_id, **job)


# ---------- Auto-discover ----------

@router.get("/{category_id}/discover/preview")
async def discover_preview(category_id: str):
    """Preview how many leaf categories would be discovered and the API budget cost."""
    cat = await get_category_by_id(category_id)
    if cat is None:
        raise HTTPException(status_code=404, detail="Category not found")
    if cat.is_leaf:
        raise HTTPException(status_code=400, detail="Cannot discover under a leaf category")

    leaf_count = await count_leaf_descendants(category_id)
    return {
        "category_id": category_id,
        "category_name": cat.name,
        "leaf_count": leaf_count,
        "api_calls_needed": leaf_count,
        "budget_pct": round(leaf_count / 5000 * 100, 1),
    }


@router.post("/{category_id}/discover")
async def discover_subcategories(
    category_id: str,
    max_categories: int = Query(200, le=500),
):
    """
    Auto-discover: find all leaf categories under a parent, track them,
    and analyze each one. Returns a job ID for progress polling.
    """
    cat = await get_category_by_id(category_id)
    if cat is None:
        raise HTTPException(status_code=404, detail="Category not found")
    if cat.is_leaf:
        raise HTTPException(status_code=400, detail="Cannot discover under a leaf category")

    leaves = await get_leaf_descendants(category_id, limit=max_categories)
    if not leaves:
        raise HTTPException(status_code=400, detail="No leaf subcategories found")

    # Auto-track all discovered leaves
    async with AsyncSessionLocal() as db:
        for leaf in leaves:
            result = await db.execute(
                select(EbayCategory).where(EbayCategory.ebay_category_id == leaf.ebay_category_id)
            )
            cat_row = result.scalar_one_or_none()
            if cat_row:
                cat_row.manual_pin = False
                cat_row.manual_block = False
                cat_row.is_tracked = True
                cat_row.track_source = "auto"
        await db.commit()

    job_id = str(uuid.uuid4())
    cat_pairs = [(l.ebay_category_id, l.name) for l in leaves]
    _jobs[job_id] = {
        "status": "running",
        "progress": 0,
        "message": f"Discovering {len(leaves)} subcategories under {cat.name}...",
    }
    await _persist_job(job_id)
    asyncio.create_task(_run_batch_analysis(job_id, cat_pairs))
    return {"job_id": job_id, "leaf_count": len(leaves)}


# ---------- Tree sync ----------

@router.post("/sync-tree")
async def trigger_tree_sync():
    """Re-fetch the category tree from eBay Taxonomy API."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "progress": 0, "message": "Fetching category tree..."}
    await _persist_job(job_id)
    asyncio.create_task(_run_tree_sync(job_id))
    return {"job_id": job_id}


# ---------- Legacy compatibility ----------
# The old GET /categories endpoint used by the dashboard FilterBar

class LegacyCategoryDTO(BaseModel):
    ebay_category_id: str
    name: str
    avg_ebay_sold_usd: Optional[float]
    avg_georgian_price_usd: Optional[float]
    avg_profit_margin_pct: Optional[float]
    avg_weight_kg: Optional[float]
    total_active_auctions: int
    last_analyzed_at: Optional[datetime]


@router.get("", response_model=list[LegacyCategoryDTO])
async def list_categories_legacy(
    sort_by: str = Query("avg_profit_margin_pct", pattern="^(avg_profit_margin_pct|name|total_active_auctions)$"),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns tracked categories for backward compatibility with FilterBar dropdown.
    """
    result = await db.execute(
        select(EbayCategory).where(EbayCategory.is_tracked == True)
    )
    cats = list(result.scalars().all())

    reverse = True
    if sort_by == "avg_profit_margin_pct":
        cats.sort(key=lambda c: c.avg_profit_margin_pct or -999, reverse=reverse)
    elif sort_by == "name":
        cats.sort(key=lambda c: c.name or "")
    elif sort_by == "total_active_auctions":
        cats.sort(key=lambda c: c.total_active_auctions or 0, reverse=reverse)

    return [LegacyCategoryDTO(
        ebay_category_id=c.ebay_category_id,
        name=c.name,
        avg_ebay_sold_usd=c.avg_ebay_sold_usd,
        avg_georgian_price_usd=c.avg_georgian_price_usd,
        avg_profit_margin_pct=c.avg_profit_margin_pct,
        avg_weight_kg=c.avg_weight_kg,
        total_active_auctions=c.total_active_auctions or 0,
        last_analyzed_at=c.last_analyzed_at,
    ) for c in cats]


# ---------- Background job implementations ----------

async def _run_single_analysis(job_id: str, category_id: str, category_name: str):
    """Analyze a single category: 1 eBay API call + Georgian scraping."""
    try:
        await _set_job(job_id, "running", 10, f"Fetching eBay prices for {category_name}...")

        # eBay BIN prices — use category name as query
        ebay_prices = await search_bin_prices(category_name, category_id=category_id, limit=20)
        avg_ebay = statistics.median(ebay_prices) if len(ebay_prices) >= 3 else None

        await _set_job(job_id, "running", 40, f"Scraping Georgian prices for {category_name}...")

        # Georgian prices — use inherited mymarket mapping
        geo_prices_gel, usd_gel = await _sample_georgian_prices(category_id, category_name)
        avg_geo_gel = statistics.median(geo_prices_gel) if len(geo_prices_gel) >= 3 else None
        avg_geo_usd = (avg_geo_gel / usd_gel) if avg_geo_gel and usd_gel else None

        margin = None
        if avg_ebay and avg_geo_usd:
            margin = (avg_geo_usd - avg_ebay) / avg_ebay * 100

        await _set_job(job_id, "running", 80, f"Saving analysis for {category_name}...")

        # Save results
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(EbayCategory).where(EbayCategory.ebay_category_id == category_id)
            )
            cat = result.scalar_one_or_none()
            if cat:
                cat.avg_ebay_sold_usd = avg_ebay
                cat.avg_georgian_price_usd = avg_geo_usd
                cat.avg_profit_margin_pct = margin
                cat.last_analyzed_at = datetime.utcnow()

                # Update active auction count
                now = datetime.utcnow()
                count_res = await db.execute(
                    select(func.count()).select_from(AuctionItem).where(
                        AuctionItem.ebay_category_id == category_id,
                        AuctionItem.ends_at > now,
                    )
                )
                cat.total_active_auctions = count_res.scalar_one() or 0

                await db.commit()

        await _set_job(job_id, "done", 100, f"Analysis complete for {category_name}")
    except Exception as e:
        await _set_job(job_id, "error", 0, str(e))


async def _run_batch_analysis(job_id: str, categories: list[tuple[str, str]]):
    """Analyze all tracked categories."""
    total = len(categories)
    try:
        for i, (cat_id, cat_name) in enumerate(categories):
            pct = int((i / total) * 100)
            await _set_job(job_id, "running", pct, f"[{i+1}/{total}] Analyzing {cat_name}...")
            print(f"[categories] [{i+1}/{total}] Analyzing {cat_name} (cat_id={cat_id})...")

            try:
                ebay_prices = await search_bin_prices(cat_name, category_id=cat_id, limit=20)
                avg_ebay = statistics.median(ebay_prices) if len(ebay_prices) >= 3 else None

                geo_prices_gel, usd_gel = await _sample_georgian_prices(cat_id, cat_name)
                avg_geo_gel = statistics.median(geo_prices_gel) if len(geo_prices_gel) >= 3 else None
                avg_geo_usd = (avg_geo_gel / usd_gel) if avg_geo_gel and usd_gel else None

                margin = None
                if avg_ebay and avg_geo_usd:
                    margin = (avg_geo_usd - avg_ebay) / avg_ebay * 100

                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(EbayCategory).where(EbayCategory.ebay_category_id == cat_id)
                    )
                    cat = result.scalar_one_or_none()
                    if cat:
                        cat.avg_ebay_sold_usd = avg_ebay
                        cat.avg_georgian_price_usd = avg_geo_usd
                        cat.avg_profit_margin_pct = margin
                        cat.last_analyzed_at = datetime.utcnow()

                        now = datetime.utcnow()
                        count_res = await db.execute(
                            select(func.count()).select_from(AuctionItem).where(
                                AuctionItem.ebay_category_id == cat_id,
                                AuctionItem.ends_at > now,
                            )
                        )
                        cat.total_active_auctions = count_res.scalar_one() or 0
                        await db.commit()

            except Exception as e:
                print(f"[categories] Failed to analyze {cat_name}: {e}")

            await asyncio.sleep(0.5)

        await _set_job(job_id, "done", 100, "Analysis complete")
    except Exception as e:
        await _set_job(job_id, "error", 0, str(e))


async def _sample_georgian_prices(category_id: str, category_name: str) -> tuple[list[float], Optional[float]]:
    """
    Scrape Georgian prices for a category using inherited mymarket mapping.
    Two-pass strategy: keyword search, then category browse fallback.
    """
    from backend.scrapers.mymarket_scraper import MymarketScraper
    from backend.services.scraper_orchestrator import scrape_all_platforms

    # Get inherited mymarket mapping
    mymarket_cats = await resolve_mymarket_cats(category_id)
    all_gel_prices: list[float] = []

    try:
        usd_gel: Optional[float] = await get_usd_gel_rate()
    except RuntimeError:
        usd_gel = None

    # Pass 1: keyword search with category filter
    try:
        listings, rate, _ = await scrape_all_platforms(
            category_name, ebay_price_usd=0, mymarket_cat_ids=mymarket_cats,
        )
        usd_gel = rate
        good = [l.price_gel for l in listings if l.similarity_score >= 0.15 and l.price_gel > 0]
        all_gel_prices.extend(good)
    except Exception:
        pass

    # Pass 2: browse category directly if too few results
    if len(all_gel_prices) < 3 and mymarket_cats:
        try:
            scraper = MymarketScraper(mymarket_cat_ids=mymarket_cats)
            browse_results = await scraper.search("")
            browse_prices = [r.price_gel for r in browse_results if r.price_gel > 0]
            all_gel_prices.extend(browse_prices)
        except Exception:
            pass

    return all_gel_prices, usd_gel


async def _run_tree_sync(job_id: str):
    """Background job to sync the category tree."""
    try:
        await _set_job(job_id, "running", 0, "Fetching category tree from eBay...")
        count = await sync_category_tree()
        await _set_job(job_id, "done", 100, f"Synced {count} categories")
    except Exception as e:
        await _set_job(job_id, "error", 0, str(e))
