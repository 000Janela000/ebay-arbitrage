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
