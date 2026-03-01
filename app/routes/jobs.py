from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.services.firestore import get_contract, get_job, update_job
from app.services.pdf_text import extract_text_from_gcs_pdf
from app.services.storage import gcs_blob_exists, upload_json_to_gcs, upload_text_to_gcs

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/{job_id}")
def read_job(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/run")
def run_job(job_id: str) -> dict[str, Any]:
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

    # RUNNING
    update_job(
        job_id=job_id,
        patch={
            "status": "RUNNING",
            "started_at": _utc_now_iso(),
            "error": None,
            "progress": 10,
        },
    )

    try:
        gcs_pdf_path = contract.get("gcs_pdf_path")
        if not gcs_pdf_path:
            raise RuntimeError("Contract missing gcs_pdf_path")

        if not gcs_blob_exists(gcs_pdf_path):
            raise RuntimeError(f"PDF not found in GCS: {gcs_pdf_path}")

        update_job(job_id=job_id, patch={"progress": 25})

        # 1) Extraemos texto real (sin OCR)
        extracted = extract_text_from_gcs_pdf(gcs_pdf_path)
        text = extracted.text or ""

        if len(text.strip()) < 20:
            raise RuntimeError(
                "No se pudo extraer texto suficiente del PDF. "
                "Verifica que sea texto seleccionable (no escaneado)."
            )

        update_job(job_id=job_id, patch={"progress": 70})

        # 2) Guardamos texto completo en GCS
        text_path = (
            f"gs://{settings.gcs_bucket_name}/results/"
            f"{contract_id}/{job_id}/result.txt"
        )
        upload_text_to_gcs(text_path, text)

        # 3) Guardamos result.json (metadata + preview)
        preview = text[:1500]
        result = {
            "contract_id": contract_id,
            "job_id": job_id,
            "source_pdf": gcs_pdf_path,
            "extraction": {
                "mode": "PDF_TEXT_NO_OCR",
                "pages": extracted.pages,
                "chars": len(text),
                "preview": preview,
                "text_gcs_path": text_path,
            },
            "created_at": _utc_now_iso(),
        }

        result_json_path = (
            f"gs://{settings.gcs_bucket_name}/results/"
            f"{contract_id}/{job_id}/result.json"
        )
        upload_json_to_gcs(result_json_path, result)

        update_job(
            job_id=job_id,
            patch={
                "status": "DONE",
                "progress": 100,
                "finished_at": _utc_now_iso(),
                "result_gcs_json_path": result_json_path,
                "result_gcs_txt_path": text_path,
            },
        )

        return {
            "ok": True,
            "job_id": job_id,
            "result_gcs_json_path": result_json_path,
            "result_gcs_txt_path": text_path,
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