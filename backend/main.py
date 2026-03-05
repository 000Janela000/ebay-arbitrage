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
    ]

    async with engine.begin() as conn:
        for table, column, sql in migrations:
            try:
                await conn.execute(text(sql))
                print(f"[migration] Added {table}.{column}")
            except Exception:
                pass  # Column already exists


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

app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"])
app.include_router(categories_router.router, prefix="/api/categories", tags=["categories"])
app.include_router(auctions_router.router, prefix="/api/auctions", tags=["auctions"])
app.include_router(opportunities_router.router, prefix="/api/opportunities", tags=["opportunities"])


@app.get("/health")
async def health():
    return {"ok": True}
