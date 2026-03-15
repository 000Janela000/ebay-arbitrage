import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.database import Base
from backend.models import EbayCategory, ModernCategoryRefreshStat, ModernOpportunity
from backend.routers import categories as categories_router
from backend.services import modern_tracking_advisor as advisor


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


def test_category_track_score_monotonicity():
    low = advisor._calc_category_score(
        liquidity_score=0.1,
        qualification_score=0.1,
        comparables_score=0.1,
        realism_score=0.1,
        stability_score=0.1,
    )
    high = advisor._calc_category_score(
        liquidity_score=0.8,
        qualification_score=0.8,
        comparables_score=0.8,
        realism_score=0.8,
        stability_score=0.8,
    )
    assert high > low


def test_focus_winner_prefers_bucket_with_better_recent_outcomes(monkeypatch, tmp_path):
    async def _run():
        db_file = tmp_path / "focus_winner.db"
        engine, session_factory = _session_factory(str(db_file))
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        monkeypatch.setattr(advisor, "AsyncSessionLocal", session_factory)

        now = datetime.utcnow()
        async with session_factory() as db:
            db.add_all([
                EbayCategory(ebay_category_id="e-1", name="Cell Phones & Smartphones", is_leaf=True),
                EbayCategory(ebay_category_id="a-1", name="Architectural Antiques", is_leaf=True),
            ])

            for i in range(6):
                db.add(ModernOpportunity(
                    auction_item_id=1000 + i,
                    estimated_final_usd=100.0,
                    anchor_price_usd=150.0,
                    current_discount_pct=0.3,
                    projected_discount_pct=0.25,
                    steal_score=0.7,
                    winability_score=0.7,
                    demand_gate_passed=True,
                    gate_reason=None,
                    final_score=80.0,
                    weight_kg=1.0,
                    shipping_cost_usd=9.0,
                    vat_usd=0.0,
                    total_landed_cost_usd=109.0,
                    total_landed_cost_gel=294.3,
                    georgian_median_price_gel=450.0,
                    georgian_median_price_usd=166.0,
                    net_revenue_usd=160.0,
                    selling_fees_usd=6.0,
                    georgian_listing_count=3,
                    profit_usd=51.0,
                    profit_gel=137.7,
                    profit_margin_pct=46.7,
                    margin_score=0.9,
                    urgency_score=0.8,
                    confidence_score=0.8,
                    competition_score=0.7,
                    demand_score=0.6,
                    gel_rate_used=2.7,
                    vat_applied=False,
                    item_title=f"Elec {i}",
                    item_url="https://example.com/e",
                    image_url=None,
                    ends_at=now + timedelta(hours=8),
                    current_bid_usd=90.0,
                    ebay_category_id="e-1",
                    last_scored_at=now - timedelta(days=1),
                ))

            for i in range(2):
                db.add(ModernOpportunity(
                    auction_item_id=2000 + i,
                    estimated_final_usd=100.0,
                    anchor_price_usd=130.0,
                    current_discount_pct=0.1,
                    projected_discount_pct=-0.1,
                    steal_score=0.3,
                    winability_score=0.4,
                    demand_gate_passed=False,
                    gate_reason="low_demand",
                    final_score=25.0,
                    weight_kg=1.0,
                    shipping_cost_usd=9.0,
                    vat_usd=0.0,
                    total_landed_cost_usd=109.0,
                    total_landed_cost_gel=294.3,
                    georgian_median_price_gel=260.0,
                    georgian_median_price_usd=96.0,
                    net_revenue_usd=90.0,
                    selling_fees_usd=4.0,
                    georgian_listing_count=1,
                    profit_usd=-19.0,
                    profit_gel=-51.3,
                    profit_margin_pct=-17.4,
                    margin_score=0.1,
                    urgency_score=0.8,
                    confidence_score=0.5,
                    competition_score=0.5,
                    demand_score=0.1,
                    gel_rate_used=2.7,
                    vat_applied=False,
                    item_title=f"Ant {i}",
                    item_url="https://example.com/a",
                    image_url=None,
                    ends_at=now + timedelta(hours=8),
                    current_bid_usd=90.0,
                    ebay_category_id="a-1",
                    last_scored_at=now - timedelta(days=1),
                ))
            await db.commit()

        cfg = advisor.TrackingConfig(
            focus_policy="weekly_winner",
            focus_bucket="auto",
            focus_last_decided_at="",
            realism_max_extreme_margin_pct=500.0,
        )
        winner, _ = await advisor.choose_focus_bucket(cfg, force_recompute=True)
        assert winner == "electronics_small"

        await engine.dispose()

    asyncio.run(_run())


def test_advisor_respects_manual_pin_block_and_auto_limit(monkeypatch, tmp_path):
    async def _run():
        db_file = tmp_path / "advisor_apply.db"
        engine, session_factory = _session_factory(str(db_file))
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        monkeypatch.setattr(advisor, "AsyncSessionLocal", session_factory)
        monkeypatch.setattr(categories_router, "AsyncSessionLocal", session_factory)

        async with session_factory() as db:
            db.add_all([
                EbayCategory(ebay_category_id="p", name="Pinned Category", is_leaf=True),
                EbayCategory(ebay_category_id="b", name="Blocked Category", is_leaf=True),
                EbayCategory(ebay_category_id="a1", name="Cell Phones", is_leaf=True),
                EbayCategory(ebay_category_id="a2", name="Cameras", is_leaf=True),
            ])
            await db.commit()

        assert await categories_router._apply_tracking_override("p", "pin")
        assert await categories_router._apply_tracking_override("b", "block")

        now = datetime.utcnow()
        async with session_factory() as db:
            db.add_all([
                ModernCategoryRefreshStat(category_id="a1", processed_count=30, shortlisted_count=10, qualified_count=5, hit_rate=0.5, avg_steal_score=0.7),
                ModernCategoryRefreshStat(category_id="a2", processed_count=25, shortlisted_count=10, qualified_count=5, hit_rate=0.5, avg_steal_score=0.6),
                ModernCategoryRefreshStat(category_id="p", processed_count=0, shortlisted_count=0, qualified_count=0, hit_rate=0.0, avg_steal_score=0.0),
                ModernCategoryRefreshStat(category_id="b", processed_count=30, shortlisted_count=10, qualified_count=5, hit_rate=0.5, avg_steal_score=0.7),
            ])
            for cid in ["a1", "a2"]:
                db.add(ModernOpportunity(
                    auction_item_id=3000 + (1 if cid == "a1" else 2),
                    estimated_final_usd=100.0,
                    anchor_price_usd=150.0,
                    current_discount_pct=0.3,
                    projected_discount_pct=0.2,
                    steal_score=0.7,
                    winability_score=0.7,
                    demand_gate_passed=True,
                    gate_reason=None,
                    final_score=75.0,
                    weight_kg=1.0,
                    shipping_cost_usd=9.0,
                    vat_usd=0.0,
                    total_landed_cost_usd=109.0,
                    total_landed_cost_gel=294.3,
                    georgian_median_price_gel=430.0,
                    georgian_median_price_usd=159.0,
                    net_revenue_usd=150.0,
                    selling_fees_usd=5.0,
                    georgian_listing_count=3,
                    profit_usd=41.0,
                    profit_gel=110.7,
                    profit_margin_pct=37.6,
                    margin_score=0.8,
                    urgency_score=0.7,
                    confidence_score=0.8,
                    competition_score=0.7,
                    demand_score=0.6,
                    gel_rate_used=2.7,
                    vat_applied=False,
                    item_title=f"{cid} item",
                    item_url="https://example.com",
                    image_url=None,
                    ends_at=now + timedelta(hours=10),
                    current_bid_usd=80.0,
                    ebay_category_id=cid,
                    last_scored_at=now,
                ))
            await db.commit()

        cfg = advisor.TrackingConfig(
            tracking_mode="hybrid_auto_manual",
            auto_track_enabled=True,
            auto_track_max_categories=1,
            auto_track_refresh_hours=24,
            auto_track_min_liquidity=0.1,
            auto_track_min_score=0.35,
            focus_policy="mixed_fixed",
            focus_bucket="mixed",
            realism_max_extreme_margin_pct=500.0,
            realism_min_positive_discount_share=0.2,
        )

        result = await advisor.build_tracking_recommendations(cfg, force_focus_recompute=False)
        apply_metrics = await advisor.apply_tracking_recommendations(cfg, result["recommendations"], result["focus_bucket"])
        assert apply_metrics["scanned"] >= 4

        async with session_factory() as db:
            rows = (await db.execute(select(EbayCategory))).scalars().all()
            by_id = {r.ebay_category_id: r for r in rows}

        assert by_id["p"].is_tracked is True and by_id["p"].manual_pin is True
        assert by_id["b"].is_tracked is False and by_id["b"].manual_block is True
        auto_tracked = [c for c in [by_id["a1"], by_id["a2"]] if c.is_tracked and c.track_source == "auto"]
        assert len(auto_tracked) == 1

        await engine.dispose()

    asyncio.run(_run())
