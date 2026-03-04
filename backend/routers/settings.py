from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Setting
from backend.services.currency_service import get_rate_info
from backend.services.ebay_client import validate_credentials

router = APIRouter()


class SettingsResponse(BaseModel):
    ebay_client_id: str = ""
    ebay_client_secret: str = ""
    ebay_environment: str = "production"
    shipping_rate_per_kg: float = 9.0
    default_weight_kg: float = 0.5
    vat_enabled: bool = False
    vat_rate: float = 0.18


class SettingsUpdate(BaseModel):
    ebay_client_id: Optional[str] = None
    ebay_client_secret: Optional[str] = None
    ebay_environment: Optional[str] = None
    shipping_rate_per_kg: Optional[float] = None
    default_weight_kg: Optional[float] = None
    vat_enabled: Optional[bool] = None
    vat_rate: Optional[float] = None


class ValidateEbayRequest(BaseModel):
    client_id: str
    client_secret: str
    environment: str = "production"


async def _get_all_settings(db: AsyncSession) -> dict[str, str]:
    result = await db.execute(select(Setting))
    return {row.key: row.value for row in result.scalars().all()}


async def _upsert_setting(db: AsyncSession, key: str, value: str):
    result = await db.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value = value
        row.updated_at = datetime.utcnow()
    else:
        db.add(Setting(key=key, value=value, updated_at=datetime.utcnow()))


@router.get("", response_model=SettingsResponse)
async def get_settings(db: AsyncSession = Depends(get_db)):
    s = await _get_all_settings(db)
    return SettingsResponse(
        ebay_client_id=s.get("ebay_client_id", ""),
        ebay_client_secret=s.get("ebay_client_secret", ""),
        ebay_environment=s.get("ebay_environment", "production"),
        shipping_rate_per_kg=float(s.get("shipping_rate_per_kg", "9.0")),
        default_weight_kg=float(s.get("default_weight_kg", "0.5")),
        vat_enabled=s.get("vat_enabled", "false").lower() == "true",
        vat_rate=float(s.get("vat_rate", "0.18")),
    )


@router.put("", response_model=SettingsResponse)
async def update_settings(body: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    updates: dict[str, str] = {}
    if body.ebay_client_id is not None:
        updates["ebay_client_id"] = body.ebay_client_id
    if body.ebay_client_secret is not None:
        updates["ebay_client_secret"] = body.ebay_client_secret
    if body.ebay_environment is not None:
        updates["ebay_environment"] = body.ebay_environment
    if body.shipping_rate_per_kg is not None:
        updates["shipping_rate_per_kg"] = str(body.shipping_rate_per_kg)
    if body.default_weight_kg is not None:
        updates["default_weight_kg"] = str(body.default_weight_kg)
    if body.vat_enabled is not None:
        updates["vat_enabled"] = str(body.vat_enabled).lower()
    if body.vat_rate is not None:
        updates["vat_rate"] = str(body.vat_rate)

    for key, value in updates.items():
        await _upsert_setting(db, key, value)
    await db.commit()

    # Invalidate eBay token if credentials changed
    if "ebay_client_id" in updates or "ebay_client_secret" in updates:
        from backend.services.ebay_client import EbayTokenManager
        EbayTokenManager.invalidate()

    return await get_settings(db)


@router.post("/validate-ebay")
async def validate_ebay(body: ValidateEbayRequest):
    ok = await validate_credentials(body.client_id, body.client_secret, body.environment)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid eBay credentials")
    return {"valid": True}


@router.get("/currency-rate")
async def currency_rate():
    try:
        info = await get_rate_info()
        return {
            "usd_gel": info["rate"],
            "from": "USD",
            "to": "GEL",
            "is_stale": info.get("is_stale", False),
            "is_fallback": info.get("is_fallback", False),
            "fetched_at": info.get("fetched_at"),
            "age_minutes": info.get("age_minutes"),
        }
    except RuntimeError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=str(e))
