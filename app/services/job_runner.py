from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)

def _log(message: str) -> None:
    print(message, flush=True)
    logger.info(message)


RULES_V1: list[dict[str, str]] = [
    {
        "id": "AUTO_RENEWAL",
        "severity": "high",
        "pattern": "automatic renewal",
        "description": "El contrato menciona renovación automática.",
    },
    {
        "id": "UNILATERAL_TERMINATION",
        "severity": "high",
        "pattern": "sole discretion",
        "description": "Existe terminación o modificación unilateral.",
    },
    {
        "id": "LIABILITY_LIMITATION",
        "severity": "medium",
        "pattern": "limitation of liability",
        "description": "Se detecta cláusula de limitación de responsabilidad.",
    },
    {
        "id": "CONFIDENTIALITY",
        "severity": "low",
        "pattern": "confidential",
        "description": "Se detecta cláusula de confidencialidad.",
    },
]


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


def _run_rules_v1(text: str) -> dict[str, Any]:
    text_lower = text.lower()
    findings: list[dict[str, str]] = []
    for rule in RULES_V1:
        if rule["pattern"] in text_lower:
            findings.append(
                {
                    "rule_id": rule["id"],
                    "severity": rule["severity"],
                    "description": rule["description"],
                    "pattern": rule["pattern"],
                }
            )

    risk_score = min(100, len(findings) * 25)
    risk_level = "LOW"
    if risk_score >= 75:
        risk_level = "HIGH"
    elif risk_score >= 40:
        risk_level = "MEDIUM"

    return {
        "ruleset": "RULES_V1",
        "summary": {
            "total_findings": len(findings),
            "risk_score": risk_score,
            "risk_level": risk_level,
        },
        "findings": findings,
    }


def run_job_logic(job_id: str) -> dict[str, Any]:
    """
    Runner síncrono (ideal para BackgroundTasks en local).
    Más adelante lo movemos a Cloud Tasks/worker sin cambiar contratos.
    """
    settings = get_settings()

    _log(f"[job:{job_id}] Starting execution")

    job = get_job(job_id)
    if not job:
        _log(f"[job:{job_id}] Job not found")
        raise RuntimeError("Job not found")

    contract_id = job.get("contract_id")
    if not contract_id:
        _log(f"[job:{job_id}] Missing contract_id")
        raise RuntimeError("Job missing contract_id")

    contract = get_contract(contract_id)
    if not contract:
        _log(f"[job:{job_id}] Contract {contract_id} not found")
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
            _log(f"[job:{job_id}] Contract {contract_id} missing gcs_pdf_path")
            raise RuntimeError("Contract missing gcs_pdf_path")

        if not gcs_blob_exists(gcs_pdf_path):
            _log(f"[job:{job_id}] PDF not found in GCS: {gcs_pdf_path}")
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

        rules_result = _run_rules_v1(text)

        result = {
            "contract_id": contract_id,
            "job_id": job_id,
            "source_pdf": gcs_pdf_path,
            "mode": "RULES_V1",
            "analysis": rules_result,
            "text_chars": len(text),
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

        _log(f"[job:{job_id}] Completed successfully. txt={result_txt_path} json={result_json_path}")

        return {
            "ok": True,
            "job_id": job_id,
            "result_gcs_json_path": result_json_path,
            "result_gcs_txt_path": result_txt_path,
            "mode": "RULES_V1",
        }

    except Exception as e:
        logger.exception("[job:%s] Failed with error: %s", job_id, e)
        _log(f"[job:{job_id}] Failed with error: {e}")
        update_job(
            job_id=job_id,
            patch={
                "status": "FAILED",
                "error": str(e),
                "finished_at": _utc_now_iso(),
            },
        )
        raise


def run_job_sync(job_id: str) -> dict[str, Any]:
    """Compat wrapper."""
    return run_job_logic(job_id)
