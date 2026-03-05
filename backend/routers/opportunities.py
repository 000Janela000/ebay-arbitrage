"""
Cross-category ranked opportunities endpoint.
Filtering, sorting, and pagination all done in SQL — no Python-side sorting.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, and_, or_, desc, asc, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import AuctionItem, Opportunity
from backend.services.ebay_client import get_daily_usage

router = APIRouter()


def _sort_column(sort_by: str, order: str):
    """Return a SQLAlchemy order clause for the given field."""
    col_map = {
        "opportunity_score": Opportunity.opportunity_score,
        "profit_margin_pct": Opportunity.profit_margin_pct,
        "demand_score": Opportunity.demand_score,
        "current_bid_usd": Opportunity.current_bid_usd,
        "total_landed_cost_usd": Opportunity.total_landed_cost_usd,
        "ends_at": Opportunity.ends_at,
    }
    col = col_map.get(sort_by, Opportunity.opportunity_score)
    if sort_by == "ends_at":
        # For ends_at, ASC = soonest first (most urgent)
        return asc(col) if order.lower() == "asc" else desc(col)
    return desc(col) if order.lower() == "desc" else asc(col)


@router.get("")
async def list_opportunities(
    sort_by: str = Query("opportunity_score"),
    order: str = Query("desc"),
    min_profit_pct: Optional[float] = Query(None),
    min_profit_usd: Optional[float] = Query(None),
    max_bid_usd: Optional[float] = Query(None),
    min_budget_usd: Optional[float] = Query(None),
    max_budget_usd: Optional[float] = Query(None),
    category_id: Optional[str] = Query(None),
    has_georgian_data: Optional[bool] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.utcnow()

    # Build WHERE clauses
    conditions = [Opportunity.ends_at > now]
    if min_profit_pct is not None:
        conditions.append(Opportunity.profit_margin_pct >= min_profit_pct)
    if min_profit_usd is not None:
        conditions.append(Opportunity.profit_usd >= min_profit_usd)
    if min_budget_usd is not None:
        conditions.append(Opportunity.total_landed_cost_usd >= min_budget_usd)
    if max_budget_usd is not None:
        conditions.append(Opportunity.total_landed_cost_usd <= max_budget_usd)
    if has_georgian_data is True:
        conditions.append(Opportunity.georgian_listing_count > 0)
    elif has_georgian_data is False:
        conditions.append(or_(Opportunity.georgian_listing_count == 0, Opportunity.georgian_listing_count.is_(None)))

    # Count total (for pagination)
    count_q = select(func.count()).select_from(Opportunity).where(and_(*conditions))
    if category_id or max_bid_usd is not None:
        count_q = (
            select(func.count())
            .select_from(Opportunity)
            .join(AuctionItem, Opportunity.auction_item_id == AuctionItem.id)
            .where(and_(*conditions))
        )
        if category_id:
            count_q = count_q.where(AuctionItem.ebay_category_id == category_id)
        if max_bid_usd is not None:
            count_q = count_q.where(AuctionItem.current_bid_usd <= max_bid_usd)

    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    # Main query with JOIN, filter, sort, paginate — all in SQL
    q = (
        select(Opportunity, AuctionItem)
        .join(AuctionItem, Opportunity.auction_item_id == AuctionItem.id)
        .where(and_(*conditions))
    )
    if category_id:
        q = q.where(AuctionItem.ebay_category_id == category_id)
    if max_bid_usd is not None:
        q = q.where(AuctionItem.current_bid_usd <= max_bid_usd)

    q = q.order_by(_sort_column(sort_by, order)).offset(offset).limit(limit)

    result = await db.execute(q)
    rows = result.all()

    items = []
    for opp, item in rows:
        seconds_remaining = max(0, (opp.ends_at - now).total_seconds())
        quality_warning = _build_quality_warning(opp)
        items.append({
            "ebay_item_id": item.ebay_item_id,
            "title": opp.item_title,
            "image_url": opp.image_url,
            "item_url": opp.item_url,
            "current_bid_usd": opp.current_bid_usd,
            "estimated_final_usd": opp.estimated_final_usd,
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
            "georgian_listing_count": opp.georgian_listing_count,
            "profit_margin_pct": opp.profit_margin_pct,
            "profit_usd": opp.profit_usd,
            "profit_gel": opp.profit_gel,
            "opportunity_score": opp.opportunity_score,
            "margin_score": opp.margin_score,
            "urgency_score": opp.urgency_score,
            "confidence_score": opp.confidence_score,
            "demand_score": opp.demand_score,
            "competition_score": opp.competition_score,
            "ebay_category_id": item.ebay_category_id,
            "has_georgian_data": (opp.georgian_listing_count or 0) > 0,
            "data_quality_warning": quality_warning,
        })

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": items,
        "api_usage": await get_daily_usage(),
    }


@router.get("/export.csv")
async def export_opportunities_csv(
    sort_by: str = Query("opportunity_score"),
    order: str = Query("desc"),
    min_profit_pct: Optional[float] = Query(None),
    category_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Export all current opportunities as a CSV file."""
    import csv
    import io

    now = datetime.utcnow()
    conditions = [Opportunity.ends_at > now]
    if min_profit_pct is not None:
        conditions.append(Opportunity.profit_margin_pct >= min_profit_pct)

    q = (
        select(Opportunity, AuctionItem)
        .join(AuctionItem, Opportunity.auction_item_id == AuctionItem.id)
        .where(and_(*conditions))
    )
    if category_id:
        q = q.where(AuctionItem.ebay_category_id == category_id)
    q = q.order_by(_sort_column(sort_by, order))

    result = await db.execute(q)
    rows = result.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Title", "eBay URL", "Category ID",
        "Current Bid ($)", "Est. Final ($)",
        "Weight (kg)", "Shipping ($)", "VAT ($)", "Landed Cost ($)", "Landed Cost (₾)",
        "Georgian Median (₾)", "Georgian Median ($)", "# Georgian Listings",
        "Profit ($)", "Profit (₾)", "Margin %",
        "Opportunity Score", "Margin Score", "Urgency Score", "Confidence Score", "Competition Score",
        "Bid Count", "Ends At", "Weight Source", "Data Quality"
    ])

    for opp, item in rows:
        ends_at_str = opp.ends_at.strftime("%Y-%m-%d %H:%M UTC")
        quality = _build_quality_warning(opp) or ""
        writer.writerow([
            opp.item_title,
            opp.item_url,
            item.ebay_category_id,
            f"{opp.current_bid_usd:.2f}",
            f"{opp.estimated_final_usd:.2f}",
            f"{opp.weight_kg:.3f}",
            f"{opp.shipping_cost_usd:.2f}",
            f"{opp.vat_usd:.2f}",
            f"{opp.total_landed_cost_usd:.2f}",
            f"{opp.total_landed_cost_gel:.2f}",
            f"{opp.georgian_median_price_gel:.2f}" if opp.georgian_median_price_gel else "",
            f"{opp.georgian_median_price_usd:.2f}" if opp.georgian_median_price_usd else "",
            opp.georgian_listing_count or 0,
            f"{opp.profit_usd:.2f}" if opp.profit_usd else "",
            f"{opp.profit_gel:.2f}" if opp.profit_gel else "",
            f"{opp.profit_margin_pct:.1f}" if opp.profit_margin_pct else "",
            f"{opp.opportunity_score:.1f}",
            f"{opp.margin_score:.4f}",
            f"{opp.urgency_score:.4f}",
            f"{opp.confidence_score:.4f}",
            f"{opp.competition_score:.4f}",
            item.bid_count,
            ends_at_str,
            item.weight_source or "category_default",
            quality,
        ])

    output.seek(0)
    filename = f"opportunities_{now.strftime('%Y%m%d_%H%M')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _build_quality_warning(opp: Opportunity) -> Optional[str]:
    warnings = []
    if not opp.georgian_listing_count:
        warnings.append("No Georgian listings")
    if opp.confidence_score is not None and opp.confidence_score < 0.35:
        warnings.append("Low price confidence")
    if opp.profit_margin_pct is not None and opp.profit_margin_pct > 500:
        warnings.append("Verify match (>500% margin)")
    return "; ".join(warnings) if warnings else None
