"""
NBG (National Bank of Georgia) currency rate fetcher with DB caching.
Caches rates for 1 hour to avoid excessive API calls.
"""
from datetime import datetime, timedelta
from typing import Optional

import httpx
from sqlalchemy import select, desc

from backend.database import AsyncSessionLocal
from backend.models import CurrencyRate

NBG_API_URL = "https://nbg.gov.ge/gw/api/ct/monetarypolicy/currencies/en/json"
CACHE_TTL_MINUTES = 60
STALE_WARN_MINUTES = 120  # Warn UI if rate is older than 2 hours


async def get_usd_gel_rate() -> float:
    """Return the current USD/GEL exchange rate. Raises if completely unavailable."""
    info = await get_rate_info()
    return info["rate"]


async def get_rate_info() -> dict:
    """
    Return rate + metadata:
      rate: float
      is_stale: bool   — cached but older than CACHE_TTL
      is_fallback: bool — NBG unreachable, using old cached value
      fetched_at: datetime | None
    """
    # 1. Fresh cache
    fresh = await _get_cached_rate("USD", "GEL", ignore_ttl=False)
    if fresh is not None:
        row = await _get_latest_rate_row("USD", "GEL")
        return {"rate": fresh, "is_stale": False, "is_fallback": False, "fetched_at": row.fetched_at if row else None}

    # 2. Try live fetch
    rate = await _fetch_from_nbg()
    if rate:
        await _cache_rate("USD", "GEL", rate)
        return {"rate": rate, "is_stale": False, "is_fallback": False, "fetched_at": datetime.utcnow()}

    # 3. Stale cache fallback (NBG unreachable)
    stale = await _get_cached_rate("USD", "GEL", ignore_ttl=True)
    if stale is not None:
        row = await _get_latest_rate_row("USD", "GEL")
        age_minutes = (datetime.utcnow() - row.fetched_at).total_seconds() / 60 if row else 9999
        return {
            "rate": stale,
            "is_stale": True,
            "is_fallback": True,
            "fetched_at": row.fetched_at if row else None,
            "age_minutes": round(age_minutes),
        }

    # 4. No data at all — raise instead of silently returning a wrong number
    raise RuntimeError(
        "USD/GEL exchange rate unavailable: NBG API unreachable and no cached value found. "
        "Check internet connectivity."
    )


async def _get_latest_rate_row(from_code: str, to_code: str) -> Optional[CurrencyRate]:
    async with AsyncSessionLocal() as session:
        q = select(CurrencyRate).where(
            CurrencyRate.from_code == from_code,
            CurrencyRate.to_code == to_code,
        ).order_by(desc(CurrencyRate.fetched_at)).limit(1)
        result = await session.execute(q)
        return result.scalar_one_or_none()


async def _get_cached_rate(from_code: str, to_code: str, ignore_ttl: bool = False) -> Optional[float]:
    cutoff = datetime.utcnow() - timedelta(minutes=CACHE_TTL_MINUTES)
    async with AsyncSessionLocal() as session:
        q = select(CurrencyRate).where(
            CurrencyRate.from_code == from_code,
            CurrencyRate.to_code == to_code,
        ).order_by(desc(CurrencyRate.fetched_at)).limit(1)
        result = await session.execute(q)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        if not ignore_ttl and row.fetched_at < cutoff:
            return None
        return row.rate


async def _cache_rate(from_code: str, to_code: str, rate: float):
    async with AsyncSessionLocal() as session:
        session.add(CurrencyRate(
            from_code=from_code,
            to_code=to_code,
            rate=rate,
            fetched_at=datetime.utcnow(),
        ))
        await session.commit()


async def _fetch_from_nbg() -> Optional[float]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(NBG_API_URL)
            resp.raise_for_status()
            data = resp.json()

        for entry in data:
            currencies = entry.get("currencies", [])
            for currency in currencies:
                if currency.get("code") == "USD":
                    rate = float(currency.get("rate", 0))
                    quantity = int(currency.get("quantity", 1))
                    if quantity and rate:
                        return rate / quantity
        return None
    except Exception as e:
        print(f"NBG API error: {e}")
        return None
