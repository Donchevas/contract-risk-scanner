from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.services.firestore import get_job
from app.services.job_runner import run_job_sync

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
def read_job(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/run")
def run_job(job_id: str) -> dict[str, Any]:
    # Ejecuta la lógica real
    try:
        return run_job_sync(job_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e