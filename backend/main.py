from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.database import create_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await create_tables()
    await _run_schema_migrations()
    await _mark_interrupted_jobs()
    await _seed_default_settings()
    await _maybe_sync_category_tree()
    await _init_playwright()
    yield
    # Shutdown
    await _close_playwright()


async def _run_schema_migrations():
    """Add columns that create_all won't add to existing tables."""
    from sqlalchemy import text
    from backend.database import engine

    migrations = [
        ("georgian_listings", "view_count", "ALTER TABLE georgian_listings ADD COLUMN view_count INTEGER"),
        ("georgian_listings", "order_count", "ALTER TABLE georgian_listings ADD COLUMN order_count INTEGER"),
        ("opportunities", "demand_score", "ALTER TABLE opportunities ADD COLUMN demand_score FLOAT"),
        ("opportunities", "net_revenue_usd", "ALTER TABLE opportunities ADD COLUMN net_revenue_usd FLOAT"),
        ("opportunities", "selling_fees_usd", "ALTER TABLE opportunities ADD COLUMN selling_fees_usd FLOAT"),
        ("ebay_categories", "manual_pin", "ALTER TABLE ebay_categories ADD COLUMN manual_pin BOOLEAN DEFAULT 0"),
        ("ebay_categories", "manual_block", "ALTER TABLE ebay_categories ADD COLUMN manual_block BOOLEAN DEFAULT 0"),
        ("ebay_categories", "track_source", "ALTER TABLE ebay_categories ADD COLUMN track_source VARCHAR DEFAULT 'none'"),
        ("ebay_categories", "auto_track_score", "ALTER TABLE ebay_categories ADD COLUMN auto_track_score FLOAT"),
        ("ebay_categories", "auto_tracked_at", "ALTER TABLE ebay_categories ADD COLUMN auto_tracked_at DATETIME"),
        (
            "modern_category_refresh_stats",
            "categories_with_positive_fetch",
            "ALTER TABLE modern_category_refresh_stats ADD COLUMN categories_with_positive_fetch INTEGER",
        ),
    ]

    async with engine.begin() as conn:
        for table, column, sql in migrations:
            try:
                await conn.execute(text(sql))
                print(f"[migration] Added {table}.{column}")
            except Exception as e:
                # SQLite duplicate-column errors are expected when column already exists.
                if "duplicate column name" in str(e).lower():
                    continue
                raise


async def _mark_interrupted_jobs():
    from backend.services.job_store import mark_running_jobs_interrupted
    await mark_running_jobs_interrupted()
    try:
        from backend.services.modern_job_store import mark_running_jobs_interrupted as mark_modern_interrupted
        await mark_modern_interrupted()
    except Exception as e:
        print(f"[startup] Warning: failed to mark modern interrupted jobs: {e}")


async def _maybe_sync_category_tree():
    """On first startup, fetch the eBay category tree and migrate legacy data."""
    from backend.services.category_tree_service import (
        is_tree_populated, sync_category_tree, migrate_legacy_categories,
    )
    try:
        if not await is_tree_populated():
            print("[startup] Category tree not found — fetching from eBay Taxonomy API...")
            await sync_category_tree()
            await migrate_legacy_categories()
            print("[startup] Category tree synced and legacy data migrated")
        else:
            print("[startup] Category tree already populated")
    except Exception as e:
        print(f"[startup] Warning: Could not sync category tree: {e}")
        print("[startup] The app will work but category browsing won't be available until tree is synced")


async def _seed_default_settings():
    from backend.database import AsyncSessionLocal
    from backend.models import Setting
    from sqlalchemy import select
    from datetime import datetime

    defaults = {
        "shipping_rate_per_kg": str(settings.shipping_rate_per_kg),
        "vat_enabled": str(settings.vat_enabled).lower(),
        "vat_rate": str(settings.vat_rate),
        "default_weight_kg": str(settings.default_weight_kg),
        "platform_fee_pct": str(settings.platform_fee_pct),
        "payment_fee_pct": str(settings.payment_fee_pct),
        "handling_fee_usd": str(settings.handling_fee_usd),
        "modern_strategy_profile": settings.modern_strategy_profile,
        "modern_target_margin_floor_pct": str(settings.modern_target_margin_floor_pct),
        "modern_demand_gate_min_listings": str(settings.modern_demand_gate_min_listings),
        "modern_demand_gate_min_score": str(settings.modern_demand_gate_min_score),
        "modern_auction_window_min_hours": str(settings.modern_auction_window_min_hours),
        "modern_auction_window_max_hours": str(settings.modern_auction_window_max_hours),
        "modern_max_categories_per_refresh": str(settings.modern_max_categories_per_refresh),
        "modern_max_items_per_category": str(settings.modern_max_items_per_category),
        "modern_deep_scrape_top_k": str(settings.modern_deep_scrape_top_k),
        "modern_tracking_mode": settings.modern_tracking_mode,
        "modern_auto_track_enabled": str(settings.modern_auto_track_enabled).lower(),
        "modern_auto_track_max_categories": str(settings.modern_auto_track_max_categories),
        "modern_auto_track_refresh_hours": str(settings.modern_auto_track_refresh_hours),
        "modern_auto_track_min_liquidity": str(settings.modern_auto_track_min_liquidity),
        "modern_auto_track_min_score": str(settings.modern_auto_track_min_score),
        "modern_focus_policy": settings.modern_focus_policy,
        "modern_focus_bucket": settings.modern_focus_bucket,
        "modern_focus_last_decided_at": settings.modern_focus_last_decided_at,
        "modern_realism_max_extreme_margin_pct": str(settings.modern_realism_max_extreme_margin_pct),
        "modern_realism_min_positive_discount_share": str(settings.modern_realism_min_positive_discount_share),
        "ebay_client_id": settings.ebay_client_id,
        "ebay_client_secret": settings.ebay_client_secret,
        "ebay_environment": settings.ebay_environment,
    }

    async with AsyncSessionLocal() as session:
        for key, value in defaults.items():
            result = await session.execute(select(Setting).where(Setting.key == key))
            existing = result.scalar_one_or_none()
            if existing is None:
                session.add(Setting(key=key, value=value, updated_at=datetime.utcnow()))
        await session.commit()


async def _init_playwright():
    try:
        from backend.scrapers.veli_store_scraper import VeliStoreScraper
        await VeliStoreScraper.start_browser()
    except Exception as e:
        print(f"Warning: Could not start Playwright browser: {e}")


async def _close_playwright():
    try:
        from backend.scrapers.veli_store_scraper import VeliStoreScraper
        await VeliStoreScraper.stop_browser()
    except Exception:
        pass


app = FastAPI(
    title="eBay Arbitrage Analyzer",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from backend.routers import settings as settings_router  # noqa: E402
from backend.routers import categories as categories_router  # noqa: E402
from backend.routers import auctions as auctions_router  # noqa: E402
from backend.routers import opportunities as opportunities_router  # noqa: E402
if settings.modern_hunter_enabled:
    from backend.routers import modern as modern_router  # noqa: E402
    from backend.routers import modern_tracking as modern_tracking_router  # noqa: E402

app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"])
app.include_router(categories_router.router, prefix="/api/categories", tags=["categories"])
app.include_router(auctions_router.router, prefix="/api/auctions", tags=["auctions"])
app.include_router(opportunities_router.router, prefix="/api/opportunities", tags=["opportunities"])
if settings.modern_hunter_enabled:
    app.include_router(modern_router.router, prefix="/api/modern", tags=["modern"])
    app.include_router(modern_tracking_router.router, prefix="/api/modern", tags=["modern-tracking"])


@app.get("/health")
async def health():
    return {"ok": True}
