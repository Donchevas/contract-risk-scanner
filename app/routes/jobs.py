from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from app.services.firestore import (
    get_job,
    update_job,
    get_contract,
)
from app.services.storage import (
    gcs_blob_exists,
    upload_json_to_gcs,
)
from app.config import get_settings

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# -------------------------------------------------
# FUNCIÓN REUTILIZABLE (clave para auto-run)
# -------------------------------------------------
def run_job_logic(job_id: str) -> dict[str, Any]:
    """
    Ejecuta el job.
    Puede ser llamada:
      - desde el endpoint POST /jobs/{job_id}/run
      - desde contracts.py usando BackgroundTasks
    """

    settings = get_settings()

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    contract_id = job.get("contract_id")
    if not contract_id:
        raise HTTPException(status_code=400, detail="Job missing contract_id")

    contract = get_contract(contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    # Marcamos RUNNING
    update_job(
        job_id=job_id,
        patch={
            "status": "RUNNING",
            "started_at": _utc_now_iso(),
            "error": None,
            "progress": 20,
        },
    )

    try:
        gcs_pdf_path = contract.get("gcs_pdf_path")
        if not gcs_pdf_path:
            raise RuntimeError("Contract missing gcs_pdf_path")

        if not gcs_blob_exists(gcs_pdf_path):
            raise RuntimeError(f"PDF not found in GCS: {gcs_pdf_path}")

        update_job(job_id=job_id, patch={"progress": 60})

        # Resultado dummy (Fase 1)
        result = {
            "contract_id": contract_id,
            "job_id": job_id,
            "source_pdf": gcs_pdf_path,
            "analysis": {
                "mode": "DUMMY",
                "message": "Fase 1 validada correctamente.",
            },
            "created_at": _utc_now_iso(),
        }

        result_path = (
            f"gs://{settings.gcs_bucket_name}/results/"
            f"{contract_id}/{job_id}/result.json"
        )

        upload_json_to_gcs(result_path, result)

        update_job(
            job_id=job_id,
            patch={
                "status": "DONE",
                "progress": 100,
                "finished_at": _utc_now_iso(),
                "result_gcs_json_path": result_path,
            },
        )

        return {
            "ok": True,
            "job_id": job_id,
            "result_gcs_json_path": result_path,
        }

    except Exception as e:
        update_job(
            job_id=job_id,
            patch={
                "status": "FAILED",
                "error": str(e),
                "finished_at": _utc_now_iso(),
            },
        )
        raise


# -------------------------------------------------
# ENDPOINTS
# -------------------------------------------------
@router.get("/{job_id}")
def read_job(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/run")
def run_job(job_id: str) -> dict[str, Any]:
    return run_job_logic(job_id)