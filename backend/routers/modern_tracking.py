"""
Modern tracking advisor API namespace.
"""
import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from backend.config import settings
from backend.services.modern_job_store import get_job as get_persisted_job
from backend.services.modern_job_store import upsert_job
from backend.services.modern_tracking_advisor import (
    TrackingConfig,
    build_tracking_recommendations,
    get_tracking_config,
    list_recent_audit,
    run_tracking_advisor,
)

router = APIRouter()

_jobs: dict[str, dict] = {}
_JOB_TYPE = "modern_tracking_refresh"


class TrackingSettingsResponse(BaseModel):
    tracking_mode: str
    auto_track_enabled: bool
    auto_track_max_categories: int
    auto_track_refresh_hours: int
    auto_track_min_liquidity: float
    auto_track_min_score: float
    focus_policy: str
    focus_bucket: str
    focus_last_decided_at: str
    realism_max_extreme_margin_pct: float
    realism_min_positive_discount_share: float


class TrackingSettingsUpdate(BaseModel):
    tracking_mode: Optional[str] = None
    auto_track_enabled: Optional[bool] = None
    auto_track_max_categories: Optional[int] = None
    auto_track_refresh_hours: Optional[int] = None
    auto_track_min_liquidity: Optional[float] = None
    auto_track_min_score: Optional[float] = None
    focus_policy: Optional[str] = None
    focus_bucket: Optional[str] = None
    realism_max_extreme_margin_pct: Optional[float] = None
    realism_min_positive_discount_share: Optional[float] = None

    @field_validator("tracking_mode")
    @classmethod
    def validate_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in {"hybrid_auto_manual", "auto_only", "manual_only"}:
            raise ValueError("tracking_mode must be hybrid_auto_manual|auto_only|manual_only")
        return v

    @field_validator("focus_policy")
    @classmethod
    def validate_focus_policy(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in {"weekly_winner", "per_refresh_winner", "mixed_fixed"}:
            raise ValueError("focus_policy must be weekly_winner|per_refresh_winner|mixed_fixed")
        return v

    @field_validator("focus_bucket")
    @classmethod
    def validate_focus_bucket(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in {"auto", "electronics_small", "antiques_decor", "mixed"}:
            raise ValueError("focus_bucket must be auto|electronics_small|antiques_decor|mixed")
        return v


class TrackingRefreshRequest(BaseModel):
    apply_changes: Optional[bool] = None
    force_focus_recompute: bool = False


class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int
    message: str = ""
    metrics: dict = Field(default_factory=dict)


async def _persist_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return
    await upsert_job(
        job_id=job_id,
        job_type=_JOB_TYPE,
        status=job.get("status", "running"),
        progress=int(job.get("progress", 0)),
        message=job.get("message", ""),
        payload={"metrics": job.get("metrics", {})},
    )


async def _set_job(job_id: str, status: str, progress: int, message: str, metrics: Optional[dict] = None):
    _jobs[job_id] = {
        "status": status,
        "progress": max(0, min(100, int(progress))),
        "message": message,
        "metrics": metrics or {},
    }
    await _persist_job(job_id)


def _cfg_to_response(cfg: TrackingConfig) -> TrackingSettingsResponse:
    return TrackingSettingsResponse(
        tracking_mode=cfg.tracking_mode,
        auto_track_enabled=cfg.auto_track_enabled,
        auto_track_max_categories=cfg.auto_track_max_categories,
        auto_track_refresh_hours=cfg.auto_track_refresh_hours,
        auto_track_min_liquidity=cfg.auto_track_min_liquidity,
        auto_track_min_score=cfg.auto_track_min_score,
        focus_policy=cfg.focus_policy,
        focus_bucket=cfg.focus_bucket,
        focus_last_decided_at=cfg.focus_last_decided_at,
        realism_max_extreme_margin_pct=cfg.realism_max_extreme_margin_pct,
        realism_min_positive_discount_share=cfg.realism_min_positive_discount_share,
    )


@router.get("/tracking/settings", response_model=TrackingSettingsResponse)
async def get_tracking_settings():
    cfg = await get_tracking_config()
    return _cfg_to_response(cfg)


@router.put("/tracking/settings", response_model=TrackingSettingsResponse)
async def update_tracking_settings(body: TrackingSettingsUpdate):
    from backend.database import AsyncSessionLocal
    from backend.models import Setting
    from sqlalchemy import select
    from datetime import datetime

    updates: dict[str, str] = {}
    for key in [
        "tracking_mode", "auto_track_enabled", "auto_track_max_categories", "auto_track_refresh_hours",
        "auto_track_min_liquidity", "auto_track_min_score", "focus_policy", "focus_bucket",
        "realism_max_extreme_margin_pct", "realism_min_positive_discount_share",
    ]:
        value = getattr(body, key)
        if value is not None:
            updates[f"modern_{key}"] = str(value).lower() if isinstance(value, bool) else str(value)

    if updates:
        async with AsyncSessionLocal() as db:
            now = datetime.utcnow()
            existing = (await db.execute(select(Setting).where(Setting.key.in_(list(updates.keys()))))).scalars().all()
            by_key = {s.key: s for s in existing}
            for key, value in updates.items():
                row = by_key.get(key)
                if row is None:
                    db.add(Setting(key=key, value=value, updated_at=now))
                else:
                    row.value = value
                    row.updated_at = now
            await db.commit()

    cfg = await get_tracking_config()
    return _cfg_to_response(cfg)


@router.post("/tracking/refresh")
async def start_tracking_refresh(body: Optional[TrackingRefreshRequest] = None):
    if not settings.modern_tracking_advisor_enabled:
        raise HTTPException(status_code=503, detail="Tracking advisor is disabled")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "running",
        "progress": 0,
        "message": "Starting tracking advisor...",
        "metrics": {},
    }
    await _persist_job(job_id)

    apply_changes = body.apply_changes if body and body.apply_changes is not None else True
    force_focus_recompute = body.force_focus_recompute if body else False
    asyncio.create_task(_run_tracking_refresh(job_id, apply_changes=apply_changes, force_focus_recompute=force_focus_recompute))
    return {"job_id": job_id}


@router.get("/tracking/refresh/status", response_model=JobStatus)
async def tracking_refresh_status(job_id: str = Query(...)):
    job = _jobs.get(job_id)
    if job:
        return JobStatus(job_id=job_id, **job)

    persisted = await get_persisted_job(job_id)
    if persisted:
        payload = persisted.get("payload", {})
        return JobStatus(
            job_id=job_id,
            status=persisted["status"],
            progress=persisted["progress"],
            message=persisted["message"],
            metrics=payload.get("metrics", {}),
        )
    return JobStatus(job_id=job_id, status="error", progress=0, message="Job not found", metrics={})


@router.get("/tracking/recommendations")
async def tracking_recommendations(limit: int = Query(200, ge=1, le=1000), force_focus_recompute: bool = Query(False)):
    cfg = await get_tracking_config()
    result = await build_tracking_recommendations(cfg, force_focus_recompute=force_focus_recompute)
    recs = result["recommendations"][:limit]
    return {
        "focus_bucket": result["focus_bucket"],
        "focus_metrics": result["focus_metrics"],
        "total": len(result["recommendations"]),
        "items": recs,
    }


@router.get("/tracking/audit")
async def tracking_audit(limit: int = Query(200, ge=1, le=2000)):
    rows = await list_recent_audit(limit=limit)
    return {"total": len(rows), "items": rows}


async def _run_tracking_refresh(job_id: str, *, apply_changes: bool, force_focus_recompute: bool):
    try:
        await _set_job(job_id, "running", 10, "Computing tracking recommendations...")
        result = await run_tracking_advisor(
            apply_changes=apply_changes,
            force_focus_recompute=force_focus_recompute,
        )
        recs = result["recommendations"]
        metrics = result.get("apply_metrics", {})
        metrics.update({
            "focus_bucket": result.get("focus_bucket", "mixed"),
            "recommended_count": len(recs),
        })
        await _set_job(job_id, "done", 100, "Tracking advisor complete", metrics=metrics)
    except Exception as e:
        await _set_job(job_id, "error", 0, str(e), metrics={})
