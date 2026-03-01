from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.services.firestore import get_contract, get_job, update_job
from app.services.storage import upload_json_to_gcs


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_job_sync(job_id: str) -> dict[str, Any]:
    """
    Runner síncrono (para local): actualiza estado, genera un JSON dummy,
    lo sube a GCS y marca el job como DONE.
    Luego, en fase 2, aquí metemos extracción real del PDF.
    """
    settings = get_settings()

    job = get_job(job_id)
    if not job:
        raise ValueError(f"Job not found: {job_id}")

    contract_id = job["contract_id"]
    contract = get_contract(contract_id)
    if not contract:
        raise ValueError(f"Contract not found: {contract_id}")

    # RUNNING
    update_job(
        job_id,
        {
            "status": "RUNNING",
            "progress": 5,
            "started_at": _utc_now_iso(),
            "error": None,
        },
    )

    try:
        # ✅ Placeholder de “extracción”
        # En Fase 2, reemplazamos esto por el extractor real (sin OCR).
        gcs_pdf_path = contract.get("gcs_pdf_path")

        result: dict[str, Any] = {
            "job_id": job_id,
            "contract_id": contract_id,
            "source_pdf": gcs_pdf_path,
            "extraction": {
                "mode": "DUMMY",
                "summary": "Resultado placeholder. En Fase 2 se extrae texto real del PDF.",
            },
            "risks": [],
        }

        update_job(job_id, {"progress": 60})

        # Guardar JSON en GCS
        gs_json_path = f"gs://{settings.gcs_bucket_name}/results/{contract_id}/{job_id}.json"
        upload_json_to_gcs(gs_json_path, result)

        # DONE
        update_job(
            job_id,
            {
                "status": "DONE",
                "progress": 100,
                "finished_at": _utc_now_iso(),
                "result_gcs_json_path": gs_json_path,
            },
        )

        return {"ok": True, "result_gcs_json_path": gs_json_path}

    except Exception as e:
        update_job(
            job_id,
            {
                "status": "FAILED",
                "error": str(e),
                "finished_at": _utc_now_iso(),
            },
        )
        raise