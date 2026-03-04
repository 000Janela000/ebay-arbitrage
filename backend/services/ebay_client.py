"""
eBay Browse API client with OAuth2 token management and API usage tracking.
"""
import asyncio
import base64
from datetime import datetime, date, timedelta
from typing import Any, Optional

import httpx
from sqlalchemy import select, func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.database import AsyncSessionLocal
from backend.models import ApiUsage, Setting

EBAY_DAILY_LIMIT = 5000
EBAY_WARN_THRESHOLD = 200

# Predefined category mapping: name → eBay category ID
CATEGORY_MAP = {
    "Cell Phones": "9355",
    "Laptops": "177",
    "Tablets": "171485",
    "Game Consoles": "139971",
    "Smartwatches": "178893",
    "Cameras": "625",
    "Consumer Electronics": "293",
    "Clothing": "11450",
    "Home & Garden": "11700",
    "Books": "267",
    "Musical Instruments": "619",
    "Toys": "220",
}


class EbayTokenManager:
    _token: Optional[str] = None
    _expires_at: Optional[datetime] = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_token(cls, client_id: str, client_secret: str, base_url: str) -> str:
        async with cls._lock:
            if cls._token and cls._expires_at and datetime.utcnow() < cls._expires_at:
                return cls._token

            credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{base_url}/identity/v1/oauth2/token",
                    headers={
                        "Authorization": f"Basic {credentials}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
                cls._token = data["access_token"]
                expires_in = int(data.get("expires_in", 7200))
                cls._expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 60)
                return cls._token

    @classmethod
    def invalidate(cls):
        cls._token = None
        cls._expires_at = None


async def _get_credentials() -> tuple[str, str, str]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Setting).where(Setting.key.in_(["ebay_client_id", "ebay_client_secret", "ebay_environment"]))
        )
        rows = {r.key: r.value for r in result.scalars().all()}
    client_id = rows.get("ebay_client_id", "")
    client_secret = rows.get("ebay_client_secret", "")
    environment = rows.get("ebay_environment", "production")
    if environment == "sandbox":
        base_url = "https://api.sandbox.ebay.com"
    else:
        base_url = "https://api.ebay.com"
    return client_id, client_secret, base_url


async def _track_api_call(count: int = 1):
    today = date.today()
    async with AsyncSessionLocal() as session:
        stmt = sqlite_insert(ApiUsage).values(api_name="ebay_browse", date=today, calls_made=count)
        stmt = stmt.on_conflict_do_update(
            index_elements=["api_name", "date"],
            set_={"calls_made": ApiUsage.calls_made + count},
        )
        await session.execute(stmt)
        await session.commit()


async def get_daily_usage() -> dict:
    today = date.today()
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ApiUsage).where(ApiUsage.api_name == "ebay_browse", ApiUsage.date == today)
        )
        row = result.scalar_one_or_none()
        calls_made = row.calls_made if row else 0
    remaining = EBAY_DAILY_LIMIT - calls_made
    return {
        "calls_made": calls_made,
        "remaining": remaining,
        "limit": EBAY_DAILY_LIMIT,
        "warn": remaining < EBAY_WARN_THRESHOLD,
    }


async def browse_search(
    query: str,
    category_id: Optional[str] = None,
    filter_str: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    buying_options: Optional[str] = None,
) -> dict[str, Any]:
    client_id, client_secret, base_url = await _get_credentials()
    if not client_id:
        raise ValueError("eBay API credentials not configured")

    token = await EbayTokenManager.get_token(client_id, client_secret, base_url)

    params: dict[str, Any] = {
        "q": query,
        "limit": limit,
        "offset": offset,
    }
    if category_id:
        params["category_ids"] = category_id
    if buying_options:
        params["filter"] = f"buyingOptions:{{{buying_options}}}"
    if filter_str:
        existing = params.get("filter", "")
        params["filter"] = f"{existing},{filter_str}" if existing else filter_str

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{base_url}/buy/browse/v1/item_summary/search",
            headers={"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
            params=params,
            timeout=20,
        )
        resp.raise_for_status()

    await _track_api_call(1)
    return resp.json()


async def search_auction_items(category_id: str, limit: int = 50) -> list[dict]:
    """Search for active auction items in a category."""
    data = await browse_search(
        query="",
        category_id=category_id,
        buying_options="AUCTION",
        filter_str="conditionIds:{1000|1500|2000|2500|3000}",
        limit=limit,
    )
    return data.get("itemSummaries", [])


async def search_bin_prices(query: str, category_id: Optional[str] = None, limit: int = 20) -> list[float]:
    """Search Buy It Now listings to get price distribution for estimation."""
    try:
        data = await browse_search(
            query=query,
            category_id=category_id,
            buying_options="FIXED_PRICE",
            limit=limit,
        )
        prices = []
        for item in data.get("itemSummaries", []):
            price_data = item.get("price", {})
            if price_data.get("currency") == "USD":
                try:
                    prices.append(float(price_data["value"]))
                except (ValueError, KeyError):
                    pass
        return prices
    except Exception:
        return []


def parse_auction_item(raw: dict) -> dict:
    """Parse eBay item summary into our domain model."""
    price = raw.get("price", {})
    current_bid = float(price.get("value", 0))

    # Parse end time
    end_time_str = raw.get("itemEndDate", "")
    try:
        ends_at = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
    except Exception:
        ends_at = datetime.utcnow() + timedelta(days=7)

    # Extract weight from item specifics
    weight_kg = None
    weight_source = "category_default"
    item_specifics = raw.get("localizedAspects", [])
    for spec in item_specifics:
        name = spec.get("name", "").lower()
        if "weight" in name:
            val_str = spec.get("value", "")
            try:
                val = float("".join(c for c in val_str if c.isdigit() or c == "."))
                if "lb" in val_str.lower():
                    val = val * 0.453592
                weight_kg = val
                weight_source = "ebay_specifics"
            except ValueError:
                pass
            break

    # Seller info
    seller = raw.get("seller", {})
    feedback_pct = None
    try:
        feedback_pct = float(seller.get("feedbackPercentage", 0))
    except (ValueError, TypeError):
        pass

    # Image
    images = raw.get("image", {})
    image_url = images.get("imageUrl")

    return {
        "ebay_item_id": raw.get("itemId", ""),
        "ebay_category_id": raw.get("categoryId", ""),
        "title": raw.get("title", ""),
        "current_bid_usd": current_bid,
        "bid_count": int(raw.get("bidCount", 0)),
        "condition": raw.get("condition"),
        "item_url": raw.get("itemWebUrl", raw.get("itemHref", "")),
        "image_url": image_url,
        "weight_kg": weight_kg,
        "weight_source": weight_source,
        "seller_feedback_pct": feedback_pct,
        "ends_at": ends_at,
        "raw_item_specifics": str(item_specifics),
    }


async def validate_credentials(client_id: str, client_secret: str, environment: str) -> bool:
    base_url = "https://api.sandbox.ebay.com" if environment == "sandbox" else "https://api.ebay.com"
    try:
        EbayTokenManager.invalidate()
        token = await EbayTokenManager.get_token(client_id, client_secret, base_url)
        return bool(token)
    except Exception:
        return False
