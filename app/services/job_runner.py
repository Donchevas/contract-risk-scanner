from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from app.config import get_settings
from app.services.firestore import get_contract, get_job, update_job
from app.services.storage import (
    download_bytes_from_gcs,
    gcs_blob_exists,
    upload_json_to_gcs,
    upload_text_to_gcs,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_pdf_text_selectable(pdf_bytes: bytes) -> str:
    """
    Extrae texto de PDF seleccionable (sin OCR).
    Requiere pypdf.
    """
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Falta dependencia para leer PDFs. Instala: pip install pypdf"
        ) from e

    reader = PdfReader(BytesIO(pdf_bytes))
    parts: list[str] = []
    for page in reader.pages:
        txt = page.extract_text() or ""
        if txt.strip():
            parts.append(txt)
    return "\n\n".join(parts).strip()


def run_job_sync(job_id: str) -> dict[str, Any]:
    """
    Runner síncrono (ideal para BackgroundTasks en local).
    Más adelante lo movemos a Cloud Tasks/worker sin cambiar contratos.
    """
    settings = get_settings()

    job = get_job(job_id)
    if not job:
        raise RuntimeError("Job not found")

    contract_id = job.get("contract_id")
    if not contract_id:
        raise RuntimeError("Job missing contract_id")

    contract = get_contract(contract_id)
    if not contract:
        raise RuntimeError("Contract not found")

    # RUNNING
    update_job(
        job_id=job_id,
        patch={
            "status": "RUNNING",
            "started_at": _utc_now_iso(),
            "finished_at": None,
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

        pdf_bytes = download_bytes_from_gcs(gcs_pdf_path)
        update_job(job_id=job_id, patch={"progress": 45})

        # Texto completo (sin OCR)
        text = _extract_pdf_text_selectable(pdf_bytes)
        if not text.strip():
            raise RuntimeError("No se pudo extraer texto del PDF (¿está escaneado?)")

        update_job(job_id=job_id, patch={"progress": 65})

        # Guardamos TXT completo en GCS
        result_txt_path = (
            f"gs://{settings.gcs_bucket_name}/results/"
            f"{contract_id}/{job_id}/result.txt"
        )
        upload_text_to_gcs(result_txt_path, text)

        update_job(job_id=job_id, patch={"progress": 80})

        # Resultado JSON (por ahora simple; luego metemos extracción IA + reglas)
        result = {
            "contract_id": contract_id,
            "job_id": job_id,
            "source_pdf": gcs_pdf_path,
            "mode": "PHASE1_TEXT_OK",
            "analysis": {
                "message": "Texto extraído y guardado en GCS correctamente.",
                "text_chars": len(text),
            },
            "created_at": _utc_now_iso(),
        }

        result_json_path = (
            f"gs://{settings.gcs_bucket_name}/results/"
            f"{contract_id}/{job_id}/result.json"
        )
        upload_json_to_gcs(result_json_path, result)

        # DONE
        update_job(
            job_id=job_id,
            patch={
                "status": "DONE",
                "progress": 100,
                "finished_at": _utc_now_iso(),
                "result_gcs_json_path": result_json_path,
                "result_gcs_txt_path": result_txt_path,
            },
        )

        return {
            "ok": True,
            "job_id": job_id,
            "result_gcs_json_path": result_json_path,
            "result_gcs_txt_path": result_txt_path,
            "mode": "PHASE1_TEXT_OK",
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