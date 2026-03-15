import asyncio
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.database import Base
from backend.models import EbayCategory, ModernAuctionItem, ModernOpportunity
from backend.routers import modern as modern_router
from backend.scrapers.base_scraper import GeorgianListing


def _session_factory(db_path: str):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return engine, session_factory


def test_modern_refresh_shortlist_cap_and_stage_b_only_shortlisted(monkeypatch, tmp_path):
    async def _run():
        db_file = tmp_path / "modern_refresh_test.db"
        engine, session_factory = _session_factory(str(db_file))

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            db.add(EbayCategory(
                ebay_category_id="cat-1",
                name="Test Category",
                is_leaf=True,
                is_tracked=True,
                avg_ebay_sold_usd=100.0,
            ))
            await db.commit()

        monkeypatch.setattr(modern_router, "AsyncSessionLocal", session_factory)

        async def fake_set_job(*_args, **_kwargs):
            return None

        monkeypatch.setattr(modern_router, "_set_job", fake_set_job)

        async def fake_get_rate():
            return 2.7

        monkeypatch.setattr(modern_router, "get_usd_gel_rate", fake_get_rate)

        async def fake_search(_category_id: str, limit: int = 30):
            return [{"idx": i} for i in range(min(limit, 5))]

        monkeypatch.setattr(modern_router, "search_auction_items", fake_search)

        def fake_parse(raw):
            i = raw["idx"]
            bid = 10.0 + i * 10.0
            return {
                "ebay_item_id": f"item-{i}",
                "ebay_category_id": "cat-1",
                "title": f"Mock Item {i}",
                "current_bid_usd": bid,
                "bid_count": i,
                "condition": "Used",
                "item_url": f"https://example.com/item-{i}",
                "image_url": None,
                "weight_kg": 1.0,
                "weight_source": "category_default",
                "seller_feedback_pct": 99.0,
                "ends_at": datetime.utcnow() + timedelta(hours=4),
                "raw_item_specifics": "{}",
            }

        monkeypatch.setattr(modern_router, "parse_auction_item", fake_parse)

        counters = {
            "estimate_calls": 0,
            "scrape_calls": 0,
        }

        async def fake_estimate(title: str, current_bid_usd: float, bid_count: int, category_id=None):
            counters["estimate_calls"] += 1
            return {
                "estimated_final_usd": current_bid_usd + 8.0,
                "confidence_score": 0.8,
                "bin_sample_count": 3,
                "bin_price_median_usd": current_bid_usd + 10.0,
                "bin_price_min_usd": current_bid_usd + 8.0,
                "bin_price_max_usd": current_bid_usd + 15.0,
                "estimation_method": "mock",
            }

        monkeypatch.setattr(modern_router, "estimate_final_price", fake_estimate)

        async def fake_scrape(_query: str, **_kwargs):
            counters["scrape_calls"] += 1
            listings = [
                GeorgianListing(
                    platform="mymarket",
                    title="Comparable A",
                    price_gel=350.0,
                    url="https://example.com/comp-a",
                    similarity_score=0.8,
                ),
                GeorgianListing(
                    platform="extra",
                    title="Comparable B",
                    price_gel=400.0,
                    url="https://example.com/comp-b",
                    similarity_score=0.75,
                ),
            ]
            return listings, 2.7, {"mymarket": True, "extra": True}

        monkeypatch.setattr(modern_router, "scrape_all_platforms", fake_scrape)

        async def fake_default_weight(_category_id: str):
            return 1.0

        monkeypatch.setattr(modern_router, "get_default_weight_async", fake_default_weight)

        def fake_score(*_args, **_kwargs):
            return {
                "profit_margin_pct": 40.0,
                "margin_score": 0.85,
                "urgency_score": 0.8,
                "confidence_score": 0.8,
                "demand_score": 0.55,
                "competition_score": 0.7,
                "opportunity_score": 78.0,
            }

        monkeypatch.setattr(modern_router, "score_opportunity", fake_score)

        cfg = {
            "strategy_profile": "balanced",
            "target_margin_floor_pct": 0.25,
            "demand_gate_min_listings": 2,
            "demand_gate_min_score": 0.25,
            "auction_window_min_hours": 2.0,
            "auction_window_max_hours": 24.0,
            "max_categories_per_refresh": 1,
            "max_items_per_category": 30,
            "deep_scrape_top_k": 2,
            "shipping_rate_per_kg": 9.0,
            "vat_enabled": False,
            "vat_rate": 0.18,
            "default_weight_kg": 0.5,
            "platform_fee_pct": 0.0,
            "payment_fee_pct": 0.0,
            "handling_fee_usd": 0.0,
        }

        await modern_router._run_modern_refresh("job-test", ["cat-1"], cfg)

        async with session_factory() as db:
            item_count = (await db.execute(
                select(func.count()).select_from(ModernAuctionItem)
            )).scalar_one()
            opp_count = (await db.execute(
                select(func.count()).select_from(ModernOpportunity)
            )).scalar_one()

        assert item_count == 5
        assert counters["estimate_calls"] == 2
        assert counters["scrape_calls"] == 2
        assert opp_count == 2

        await engine.dispose()

    asyncio.run(_run())


def test_modern_opportunities_qualified_only_filter(monkeypatch, tmp_path):
    async def _run():
        db_file = tmp_path / "modern_filter_test.db"
        engine, session_factory = _session_factory(str(db_file))

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        ends_at = datetime.utcnow() + timedelta(hours=6)

        async with session_factory() as db:
            pass_item = ModernAuctionItem(
                ebay_item_id="pass-item",
                ebay_category_id="cat-1",
                title="Pass Item",
                current_bid_usd=50.0,
                bid_count=2,
                condition="Used",
                item_url="https://example.com/pass",
                image_url=None,
                weight_kg=1.0,
                weight_source="category_default",
                seller_feedback_pct=99.0,
                ends_at=ends_at,
                raw_item_specifics="{}",
            )
            fail_item = ModernAuctionItem(
                ebay_item_id="fail-item",
                ebay_category_id="cat-1",
                title="Fail Item",
                current_bid_usd=70.0,
                bid_count=3,
                condition="Used",
                item_url="https://example.com/fail",
                image_url=None,
                weight_kg=1.0,
                weight_source="category_default",
                seller_feedback_pct=99.0,
                ends_at=ends_at,
                raw_item_specifics="{}",
            )
            db.add_all([pass_item, fail_item])
            await db.flush()

            db.add_all([
                ModernOpportunity(
                    auction_item_id=pass_item.id,
                    estimated_final_usd=80.0,
                    anchor_price_usd=130.0,
                    current_discount_pct=0.6,
                    projected_discount_pct=0.4,
                    steal_score=0.8,
                    winability_score=0.7,
                    demand_gate_passed=True,
                    gate_reason=None,
                    final_score=85.0,
                    weight_kg=1.0,
                    shipping_cost_usd=9.0,
                    vat_usd=0.0,
                    total_landed_cost_usd=89.0,
                    total_landed_cost_gel=240.3,
                    georgian_median_price_gel=400.0,
                    georgian_median_price_usd=148.1,
                    net_revenue_usd=145.0,
                    selling_fees_usd=3.1,
                    georgian_listing_count=3,
                    profit_usd=56.0,
                    profit_gel=151.2,
                    profit_margin_pct=62.9,
                    margin_score=0.9,
                    urgency_score=0.8,
                    confidence_score=0.8,
                    competition_score=0.7,
                    demand_score=0.6,
                    gel_rate_used=2.7,
                    vat_applied=False,
                    item_title=pass_item.title,
                    item_url=pass_item.item_url,
                    image_url=None,
                    ends_at=ends_at,
                    current_bid_usd=pass_item.current_bid_usd,
                    ebay_category_id="cat-1",
                ),
                ModernOpportunity(
                    auction_item_id=fail_item.id,
                    estimated_final_usd=90.0,
                    anchor_price_usd=120.0,
                    current_discount_pct=0.3,
                    projected_discount_pct=0.2,
                    steal_score=0.5,
                    winability_score=0.5,
                    demand_gate_passed=False,
                    gate_reason="low_demand",
                    final_score=20.0,
                    weight_kg=1.0,
                    shipping_cost_usd=9.0,
                    vat_usd=0.0,
                    total_landed_cost_usd=99.0,
                    total_landed_cost_gel=267.3,
                    georgian_median_price_gel=280.0,
                    georgian_median_price_usd=103.7,
                    net_revenue_usd=100.0,
                    selling_fees_usd=3.7,
                    georgian_listing_count=1,
                    profit_usd=1.0,
                    profit_gel=2.7,
                    profit_margin_pct=1.0,
                    margin_score=0.1,
                    urgency_score=0.8,
                    confidence_score=0.6,
                    competition_score=0.6,
                    demand_score=0.1,
                    gel_rate_used=2.7,
                    vat_applied=False,
                    item_title=fail_item.title,
                    item_url=fail_item.item_url,
                    image_url=None,
                    ends_at=ends_at,
                    current_bid_usd=fail_item.current_bid_usd,
                    ebay_category_id="cat-1",
                ),
            ])
            await db.commit()

        async def fake_usage():
            return {"calls_made": 0, "remaining": 5000, "limit": 5000, "warn": False}

        monkeypatch.setattr(modern_router, "get_daily_usage", fake_usage)

        async with session_factory() as db:
            filtered = await modern_router.list_modern_opportunities(
                sort_by="final_score",
                order="desc",
                min_profit_pct=None,
                max_bid_usd=None,
                min_budget_usd=None,
                max_budget_usd=None,
                category_id=None,
                has_georgian_data=None,
                qualified_only=True,
                limit=100,
                offset=0,
                db=db,
            )
            all_rows = await modern_router.list_modern_opportunities(
                sort_by="final_score",
                order="desc",
                min_profit_pct=None,
                max_bid_usd=None,
                min_budget_usd=None,
                max_budget_usd=None,
                category_id=None,
                has_georgian_data=None,
                qualified_only=False,
                limit=100,
                offset=0,
                db=db,
            )

        assert filtered["total"] == 1
        assert len(filtered["items"]) == 1
        assert filtered["items"][0]["ebay_item_id"] == "pass-item"

        assert all_rows["total"] == 2
        assert len(all_rows["items"]) == 2

        await engine.dispose()

    asyncio.run(_run())
