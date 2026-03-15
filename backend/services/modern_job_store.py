"""
Persistent storage for modern background jobs.
"""
import json
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update

from backend.database import AsyncSessionLocal
from backend.models import ModernBackgroundJob


async def upsert_job(
    job_id: str,
    job_type: str,
    status: str,
    progress: int,
    message: str = "",
    payload: Optional[dict] = None,
):
    payload_json = json.dumps(payload) if payload is not None else None
    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ModernBackgroundJob).where(ModernBackgroundJob.job_id == job_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = ModernBackgroundJob(
                job_id=job_id,
                job_type=job_type,
                status=status,
                progress=progress,
                message=message,
                payload_json=payload_json,
                created_at=now,
                updated_at=now,
                finished_at=now if status in {"done", "error"} else None,
            )
            db.add(row)
        else:
            row.job_type = job_type
            row.status = status
            row.progress = progress
            row.message = message
            row.payload_json = payload_json
            row.updated_at = now
            if status in {"done", "error"}:
                row.finished_at = now
        await db.commit()


async def get_job(job_id: str) -> Optional[dict]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ModernBackgroundJob).where(ModernBackgroundJob.job_id == job_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        payload = {}
        if row.payload_json:
            try:
                payload = json.loads(row.payload_json)
            except json.JSONDecodeError:
                payload = {}
        return {
            "job_id": row.job_id,
            "job_type": row.job_type,
            "status": row.status,
            "progress": row.progress,
            "message": row.message or "",
            "payload": payload,
        }


async def mark_running_jobs_interrupted():
    async with AsyncSessionLocal() as db:
        now = datetime.utcnow()
        await db.execute(
            update(ModernBackgroundJob)
            .where(ModernBackgroundJob.status == "running")
            .values(
                status="error",
                message="Job interrupted by server restart",
                progress=0,
                updated_at=now,
                finished_at=now,
            )
        )
        await db.commit()
