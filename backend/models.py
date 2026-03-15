from datetime import datetime
from sqlalchemy import (
    Column, Integer, Float, String, Boolean, DateTime,
    ForeignKey, Text, Date, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from backend.database import Base


class Category(Base):
    """Legacy category model — kept for migration only."""
    __tablename__ = "categories"

    ebay_category_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    avg_ebay_sold_usd = Column(Float)
    avg_georgian_price_usd = Column(Float)
    avg_profit_margin_pct = Column(Float)
    avg_weight_kg = Column(Float)
    total_active_auctions = Column(Integer, default=0)
    last_analyzed_at = Column(DateTime)


class EbayCategory(Base):
    """eBay category tree node. Populated from Taxonomy API."""
    __tablename__ = "ebay_categories"

    ebay_category_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    parent_id = Column(String, nullable=True)
    level = Column(Integer, nullable=False, default=0)
    is_leaf = Column(Boolean, default=False)

    # Analysis data (populated on-demand)
    avg_ebay_sold_usd = Column(Float)
    avg_georgian_price_usd = Column(Float)
    avg_profit_margin_pct = Column(Float)
    avg_weight_kg = Column(Float)
    total_active_auctions = Column(Integer, default=0)
    last_analyzed_at = Column(DateTime)

    # User tracking
    is_tracked = Column(Boolean, default=False)
    manual_pin = Column(Boolean, default=False)
    manual_block = Column(Boolean, default=False)
    track_source = Column(String, default="none")  # manual|auto|none
    auto_track_score = Column(Float, nullable=True)
    auto_tracked_at = Column(DateTime, nullable=True)

    # Mymarket mapping (JSON array string, e.g. "[69, 70]"), nullable — inherits from parent
    mymarket_cat_ids = Column(String, nullable=True)

    # Default weight for this category (nullable — falls back to parent)
    default_weight_kg = Column(Float, nullable=True)

    __table_args__ = (
        Index("idx_ebay_cat_parent", "parent_id"),
        Index("idx_ebay_cat_tracked", "is_tracked"),
    )


class CategoryTreeMeta(Base):
    """Tracks when the category tree was last fetched."""
    __tablename__ = "category_tree_meta"

    id = Column(Integer, primary_key=True, default=1)
    tree_version = Column(String)
    last_fetched_at = Column(DateTime)
    total_categories = Column(Integer)


class AuctionItem(Base):
    __tablename__ = "auction_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ebay_item_id = Column(String, nullable=False, unique=True)
    ebay_category_id = Column(String, nullable=False)
    title = Column(String, nullable=False)
    current_bid_usd = Column(Float, nullable=False)
    bid_count = Column(Integer, default=0)
    condition = Column(String)
    item_url = Column(String, nullable=False)
    image_url = Column(String)
    weight_kg = Column(Float)
    weight_source = Column(String)  # 'ebay_specifics'|'category_default'|'user_override'
    seller_feedback_pct = Column(Float)
    ends_at = Column(DateTime, nullable=False)
    raw_item_specifics = Column(Text)  # JSON blob
    last_fetched_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    price_estimates = relationship("PriceEstimate", back_populates="auction_item", cascade="all, delete-orphan")
    georgian_listings = relationship("GeorgianListing", back_populates="auction_item", cascade="all, delete-orphan")
    opportunity = relationship("Opportunity", back_populates="auction_item", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_auction_ends_at", "ends_at"),
    )


class PriceEstimate(Base):
    __tablename__ = "price_estimates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    auction_item_id = Column(Integer, ForeignKey("auction_items.id", ondelete="CASCADE"), nullable=False)
    estimated_final_usd = Column(Float, nullable=False)
    confidence_score = Column(Float, nullable=False)
    bin_sample_count = Column(Integer, default=0)
    bin_price_median_usd = Column(Float)
    bin_price_min_usd = Column(Float)
    bin_price_max_usd = Column(Float)
    estimation_method = Column(String, nullable=False)  # 'bin_median'|'current_bid_markup'|'category_default'
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    auction_item = relationship("AuctionItem", back_populates="price_estimates")


class GeorgianListing(Base):
    __tablename__ = "georgian_listings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    auction_item_id = Column(Integer, ForeignKey("auction_items.id", ondelete="CASCADE"), nullable=False)
    platform = Column(String, nullable=False)  # 'mymarket'|'veli'|'zoomer'
    title = Column(String, nullable=False)
    price_gel = Column(Float, nullable=False)
    price_usd = Column(Float, nullable=False)
    url = Column(String, nullable=False)
    image_url = Column(String)
    similarity_score = Column(Float)
    price_mismatch = Column(Boolean, default=False)  # True when Georgian price > 5× eBay price
    view_count = Column(Integer, nullable=True)
    order_count = Column(Integer, nullable=True)
    fetched_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    auction_item = relationship("AuctionItem", back_populates="georgian_listings")

    __table_args__ = (
        Index("idx_georgian_item", "auction_item_id"),
    )


class Opportunity(Base):
    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    auction_item_id = Column(Integer, ForeignKey("auction_items.id", ondelete="CASCADE"), nullable=False, unique=True)
    estimated_final_usd = Column(Float, nullable=False)
    weight_kg = Column(Float, nullable=False)
    shipping_cost_usd = Column(Float, nullable=False)
    vat_usd = Column(Float, default=0)
    total_landed_cost_usd = Column(Float, nullable=False)
    total_landed_cost_gel = Column(Float, nullable=False)
    georgian_median_price_gel = Column(Float)
    georgian_median_price_usd = Column(Float)
    net_revenue_usd = Column(Float)
    selling_fees_usd = Column(Float, default=0)
    georgian_listing_count = Column(Integer, default=0)
    profit_usd = Column(Float)
    profit_gel = Column(Float)
    profit_margin_pct = Column(Float)
    margin_score = Column(Float, nullable=False)
    urgency_score = Column(Float, nullable=False)
    confidence_score = Column(Float, nullable=False)
    competition_score = Column(Float, nullable=False)
    demand_score = Column(Float, nullable=True)
    opportunity_score = Column(Float, nullable=False)
    gel_rate_used = Column(Float, nullable=False)
    vat_applied = Column(Boolean, default=False)
    last_scored_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Denormalized for fast reads
    item_title = Column(String, nullable=False)
    item_url = Column(String, nullable=False)
    image_url = Column(String)
    ends_at = Column(DateTime, nullable=False)
    current_bid_usd = Column(Float, nullable=False)

    auction_item = relationship("AuctionItem", back_populates="opportunity")

    __table_args__ = (
        Index("idx_opps_score", "opportunity_score"),
        Index("idx_opps_ends_at", "ends_at"),
    )


class CurrencyRate(Base):
    __tablename__ = "currency_rates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_code = Column(String, nullable=False)
    to_code = Column(String, nullable=False)
    rate = Column(Float, nullable=False)
    fetched_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ApiUsage(Base):
    __tablename__ = "api_usage"

    api_name = Column(String, nullable=False, primary_key=True)
    date = Column(Date, nullable=False, primary_key=True)
    calls_made = Column(Integer, nullable=False, default=0)


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    job_id = Column(String, primary_key=True)
    job_type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    progress = Column(Integer, nullable=False, default=0)
    message = Column(String, default="")
    payload_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_jobs_type_status", "job_type", "status"),
        Index("idx_jobs_updated", "updated_at"),
    )


class ModernAuctionItem(Base):
    __tablename__ = "modern_auction_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ebay_item_id = Column(String, nullable=False, unique=True)
    ebay_category_id = Column(String, nullable=False)
    title = Column(String, nullable=False)
    current_bid_usd = Column(Float, nullable=False)
    bid_count = Column(Integer, default=0)
    condition = Column(String)
    item_url = Column(String, nullable=False)
    image_url = Column(String)
    weight_kg = Column(Float)
    weight_source = Column(String)
    seller_feedback_pct = Column(Float)
    ends_at = Column(DateTime, nullable=False)
    raw_item_specifics = Column(Text)
    last_fetched_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    price_estimates = relationship("ModernPriceEstimate", back_populates="auction_item", cascade="all, delete-orphan")
    georgian_listings = relationship("ModernGeorgianListing", back_populates="auction_item", cascade="all, delete-orphan")
    opportunity = relationship("ModernOpportunity", back_populates="auction_item", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_mod_auction_ends_at", "ends_at"),
        Index("idx_mod_auction_cat", "ebay_category_id"),
    )


class ModernPriceEstimate(Base):
    __tablename__ = "modern_price_estimates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    auction_item_id = Column(Integer, ForeignKey("modern_auction_items.id", ondelete="CASCADE"), nullable=False)
    estimated_final_usd = Column(Float, nullable=False)
    confidence_score = Column(Float, nullable=False)
    bin_sample_count = Column(Integer, default=0)
    bin_price_median_usd = Column(Float)
    bin_price_min_usd = Column(Float)
    bin_price_max_usd = Column(Float)
    estimation_method = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    auction_item = relationship("ModernAuctionItem", back_populates="price_estimates")


class ModernGeorgianListing(Base):
    __tablename__ = "modern_georgian_listings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    auction_item_id = Column(Integer, ForeignKey("modern_auction_items.id", ondelete="CASCADE"), nullable=False)
    platform = Column(String, nullable=False)
    title = Column(String, nullable=False)
    price_gel = Column(Float, nullable=False)
    price_usd = Column(Float, nullable=False)
    url = Column(String, nullable=False)
    image_url = Column(String)
    similarity_score = Column(Float)
    price_mismatch = Column(Boolean, default=False)
    view_count = Column(Integer, nullable=True)
    order_count = Column(Integer, nullable=True)
    fetched_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    auction_item = relationship("ModernAuctionItem", back_populates="georgian_listings")

    __table_args__ = (
        Index("idx_mod_geo_item", "auction_item_id"),
        Index("idx_mod_geo_platform", "platform"),
    )


class ModernOpportunity(Base):
    __tablename__ = "modern_opportunities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    auction_item_id = Column(Integer, ForeignKey("modern_auction_items.id", ondelete="CASCADE"), nullable=False, unique=True)

    estimated_final_usd = Column(Float, nullable=False)
    anchor_price_usd = Column(Float, nullable=True)
    current_discount_pct = Column(Float, nullable=True)
    projected_discount_pct = Column(Float, nullable=True)
    steal_score = Column(Float, nullable=False)
    winability_score = Column(Float, nullable=False)
    demand_gate_passed = Column(Boolean, default=False)
    gate_reason = Column(String, nullable=True)
    final_score = Column(Float, nullable=False)

    weight_kg = Column(Float, nullable=False)
    shipping_cost_usd = Column(Float, nullable=False)
    vat_usd = Column(Float, default=0)
    total_landed_cost_usd = Column(Float, nullable=False)
    total_landed_cost_gel = Column(Float, nullable=False)
    georgian_median_price_gel = Column(Float)
    georgian_median_price_usd = Column(Float)
    net_revenue_usd = Column(Float)
    selling_fees_usd = Column(Float, default=0)
    georgian_listing_count = Column(Integer, default=0)
    profit_usd = Column(Float)
    profit_gel = Column(Float)
    profit_margin_pct = Column(Float)
    margin_score = Column(Float, nullable=False)
    urgency_score = Column(Float, nullable=False)
    confidence_score = Column(Float, nullable=False)
    competition_score = Column(Float, nullable=False)
    demand_score = Column(Float, nullable=True)
    gel_rate_used = Column(Float, nullable=False)
    vat_applied = Column(Boolean, default=False)
    last_scored_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    item_title = Column(String, nullable=False)
    item_url = Column(String, nullable=False)
    image_url = Column(String)
    ends_at = Column(DateTime, nullable=False)
    current_bid_usd = Column(Float, nullable=False)
    ebay_category_id = Column(String, nullable=False)

    auction_item = relationship("ModernAuctionItem", back_populates="opportunity")

    __table_args__ = (
        Index("idx_mod_opps_final_score", "final_score"),
        Index("idx_mod_opps_ends_at", "ends_at"),
        Index("idx_mod_opps_gate", "demand_gate_passed"),
        Index("idx_mod_opps_cat", "ebay_category_id"),
    )


class ModernBackgroundJob(Base):
    __tablename__ = "modern_background_jobs"

    job_id = Column(String, primary_key=True)
    job_type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    progress = Column(Integer, nullable=False, default=0)
    message = Column(String, default="")
    payload_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_mod_jobs_type_status", "job_type", "status"),
        Index("idx_mod_jobs_updated", "updated_at"),
    )


class ModernCategoryRefreshStat(Base):
    __tablename__ = "modern_category_refresh_stats"

    category_id = Column(String, primary_key=True)
    last_refresh_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    processed_count = Column(Integer, nullable=False, default=0)
    shortlisted_count = Column(Integer, nullable=False, default=0)
    qualified_count = Column(Integer, nullable=False, default=0)
    categories_with_positive_fetch = Column(Integer, nullable=True)
    hit_rate = Column(Float, nullable=False, default=0)
    avg_steal_score = Column(Float, nullable=False, default=0)
    source_stats_json = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_mod_cat_stats_hit_rate", "hit_rate"),
        Index("idx_mod_cat_stats_refresh_at", "last_refresh_at"),
    )


class ModernTrackingAudit(Base):
    __tablename__ = "modern_tracking_audit"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    focus_bucket = Column(String, nullable=False, default="mixed")
    category_id = Column(String, nullable=False)
    score = Column(Float, nullable=True)
    decision = Column(String, nullable=False)  # added|kept|removed|skipped_manual
    reasons_json = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_mod_tracking_audit_run_at", "run_at"),
        Index("idx_mod_tracking_audit_category", "category_id"),
        Index("idx_mod_tracking_audit_decision", "decision"),
    )
