from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    ebay_client_id: str = ""
    ebay_client_secret: str = ""
    ebay_environment: str = "production"

    shipping_rate_per_kg: float = 9.00
    default_weight_kg: float = 0.5

    vat_enabled: bool = False
    vat_rate: float = 0.18

    # Selling-side fees on the Georgian marketplace (affect net profit only)
    platform_fee_pct: float = 0.0
    payment_fee_pct: float = 0.0
    handling_fee_usd: float = 0.0

    # Modern hunter feature flag + defaults
    modern_hunter_enabled: bool = True
    modern_strategy_profile: str = "balanced"
    modern_target_margin_floor_pct: float = 0.25
    modern_demand_gate_min_listings: int = 2
    modern_demand_gate_min_score: float = 0.25
    modern_auction_window_min_hours: float = 2.0
    modern_auction_window_max_hours: float = 24.0
    modern_max_categories_per_refresh: int = 20
    modern_max_items_per_category: int = 30
    modern_deep_scrape_top_k: int = 10
    modern_tracking_advisor_enabled: bool = True
    modern_tracking_mode: str = "hybrid_auto_manual"
    modern_auto_track_enabled: bool = True
    modern_auto_track_max_categories: int = 40
    modern_auto_track_refresh_hours: int = 24
    modern_auto_track_min_liquidity: float = 0.10
    modern_auto_track_min_score: float = 0.35
    modern_focus_policy: str = "weekly_winner"
    modern_focus_bucket: str = "auto"
    modern_focus_last_decided_at: str = ""
    modern_realism_max_extreme_margin_pct: float = 500.0
    modern_realism_min_positive_discount_share: float = 0.20

    database_url: str = "sqlite+aiosqlite:///./ebay_arbitrage.db"
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def origins_list(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    @property
    def ebay_api_base(self) -> str:
        if self.ebay_environment == "sandbox":
            return "https://api.sandbox.ebay.com"
        return "https://api.ebay.com"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
