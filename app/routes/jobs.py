from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.services.firestore import get_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
def read_job(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró el job con id '{job_id}'.",
        )

    return job
