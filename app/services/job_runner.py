from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from pypdf import PdfReader

from app.config import get_settings
from app.services.ai_analyzer import analyze_contract_with_ai
from app.services.firestore import get_contract, get_job, update_job
from app.services.rules_v2_services import analyze_services_rules
from app.services.storage import (
    download_bytes_from_gcs,
    gcs_blob_exists,
    upload_json_to_gcs,
    upload_text_to_gcs,
)

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str) -> None:
    print(msg, flush=True)
    logger.info(msg)


def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    parts: list[str] = []
    for page in reader.pages:
        t = page.extract_text() or ""
        if t.strip():
            parts.append(t)
    return "\n\n".join(parts).strip()


def _snippets(text: str, pattern: str, max_snips: int = 6, radius: int = 120) -> list[str]:
    snips: list[str] = []
    for m in re.finditer(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
        start = max(0, m.start() - radius)
        end = min(len(text), m.end() + radius)
        snips.append(text[start:end].replace("\n", " ").strip())
        if len(snips) >= max_snips:
            break
    return snips


def _rules_v1(text: str) -> dict[str, Any]:
    """
    Reglas deterministicas simples (en español) para tu fase 1/2.
    Esto se puede sofisticar luego, pero ya te da señales tipo semaforo.
    """
    findings: list[dict[str, Any]] = []

    rules = [
        ("penalties", r"\bpenalidad(?:es)?\b|\bmulta(?:s)?\b", "HIGH"),
        ("lucro_cesante", r"\blucro\s+cesante\b|\bdaño\s+emergente\b", "HIGH"),
        ("liens_or_mortgage", r"\bhipoteca\b|\bembargo\b|\bgravamen(?:es)?\b|\bcargas\b", "MEDIUM"),
        ("arbitration", r"\barbitraje\b|\bcentro\s+de\s+arbitraje\b", "LOW"),
        ("jurisdiction", r"\bjurisdicci[oó]n\b|\btribunales\b|\bjueces\b", "LOW"),
        ("renewal", r"\brenovaci[oó]n\s+autom[aá]tica\b|\bpr[oó]rroga\b", "MEDIUM"),
        ("termination", r"\bresoluci[oó]n\b|\bterminaci[oó]n\b|\brescisi[oó]n\b", "MEDIUM"),
    ]

    score = 0
    for key, pat, sev in rules:
        snips = _snippets(text, pat)
        if snips:
            findings.append(
                {
                    "rule_id": key,
                    "severity": sev,
                    "count": len(snips),
                    "snippets": snips,
                }
            )
            score += {"LOW": 5, "MEDIUM": 15, "HIGH": 30}[sev]

    score = min(100, score)
    level = "LOW" if score < 20 else "MEDIUM" if score < 60 else "HIGH"

    return {
        "ruleset": "RULES_V1",
        "summary": {
            "total_findings": len(findings),
            "risk_score": score,
            "risk_level": level,
        },
        "findings": findings,
    }


def run_job_logic(job_id: str) -> dict[str, Any]:
    settings = get_settings()

    job = get_job(job_id)
    if not job:
        raise ValueError(f"Job not found: {job_id}")

    contract_id = job.get("contract_id")
    if not contract_id:
        raise ValueError(f"Job missing contract_id: {job_id}")

    contract = get_contract(contract_id)
    if not contract:
        raise ValueError(f"Contract not found: {contract_id}")

    update_job(
        job_id=job_id,
        patch={
            "status": "RUNNING",
            "progress": 10,
            "started_at": _utc_now_iso(),
            "error": None,
        },
    )

    _log(f"[job:{job_id}] Starting execution")

    try:
        gcs_pdf_path = contract.get("gcs_pdf_path")
        if not gcs_pdf_path:
            raise RuntimeError("Contract missing gcs_pdf_path")

        if not gcs_blob_exists(gcs_pdf_path):
            raise RuntimeError(f"PDF not found in GCS: {gcs_pdf_path}")

        update_job(job_id=job_id, patch={"progress": 25})

        pdf_bytes = download_bytes_from_gcs(gcs_pdf_path)
        text = _extract_text_from_pdf_bytes(pdf_bytes)
        if not text.strip():
            raise RuntimeError("No se pudo extraer texto del PDF (texto vacio).")

        # Guardar txt
        result_txt_path = f"gs://{settings.gcs_bucket_name}/results/{contract_id}/{job_id}/result.txt"
        upload_text_to_gcs(result_txt_path, text)

        update_job(job_id=job_id, patch={"progress": 55})

        ruleset = str(job.get("ruleset") or "RULES_V1")
        if ruleset not in {"RULES_V1", "RULES_V2_SERVICES"}:
            _log(f"[job:{job_id}] Unknown ruleset={ruleset}; fallback to RULES_V1")
            ruleset = "RULES_V1"

        _log(f"[job:{job_id}] Using ruleset={ruleset}")

        if ruleset == "RULES_V2_SERVICES":
            rules_result = analyze_services_rules(text)
        else:
            rules_result = _rules_v1(text)

        result = {
            "contract_id": contract_id,
            "job_id": job_id,
            "source_pdf": gcs_pdf_path,
            "mode": ruleset,
            "analysis": rules_result,
            "text_chars": len(text),
            "created_at": _utc_now_iso(),
        }

        result_json_path = f"gs://{settings.gcs_bucket_name}/results/{contract_id}/{job_id}/result.json"
        upload_json_to_gcs(result_json_path, result)

        update_job(job_id=job_id, patch={"progress": 80})

        # IA (opcional): si falla, el job igual queda DONE y solo ai_status=FAILED
        ai_result_json_path: str | None = None
        ai_status = "PENDING"
        ai_error: str | None = None

        excerpt = text
        truncated = False
        max_chars = 12000
        if len(excerpt) > max_chars:
            excerpt = excerpt[:max_chars]
            truncated = True

        try:
            ai_status = "RUNNING"
            update_job(
                job_id=job_id,
                patch={
                    "ai_status": ai_status,
                    "ai_error": None,
                    "ai_model": settings.openai_model,
                },
            )

            _log(f"[job:{job_id}] AI start model={settings.openai_model} truncated={truncated} chars={len(excerpt)}")

            ai_result = analyze_contract_with_ai(
                contract_text=excerpt,
                rules_result=rules_result,
                metadata={
                    "job_id": job_id,
                    "contract_id": contract_id,
                    "source_pdf": gcs_pdf_path,
                    "result_txt_path": result_txt_path,
                    "result_json_path": result_json_path,
                    "truncated": truncated,
                },
            )

            ai_result_json_path = f"gs://{settings.gcs_bucket_name}/results/{contract_id}/{job_id}/ai_result.json"
            upload_json_to_gcs(ai_result_json_path, ai_result)

            ai_status = "DONE"
            update_job(
                job_id=job_id,
                patch={
                    "ai_status": ai_status,
                    "ai_error": None,
                    "ai_result_gcs_json_path": ai_result_json_path,
                    "ai_model": settings.openai_model,
                },
            )

            _log(f"[job:{job_id}] AI done path={ai_result_json_path}")

        except Exception as exc:
            ai_status = "FAILED"
            ai_error = str(exc)
            update_job(
                job_id=job_id,
                patch={
                    "ai_status": ai_status,
                    "ai_error": ai_error,
                    "ai_model": settings.openai_model,
                },
            )
            _log(f"[job:{job_id}] AI failed err={exc}")

        # DONE (job principal)
        update_job(
            job_id=job_id,
            patch={
                "status": "DONE",
                "progress": 100,
                "finished_at": _utc_now_iso(),
                "result_gcs_json_path": result_json_path,
                "result_gcs_txt_path": result_txt_path,
                "ai_result_gcs_json_path": ai_result_json_path,
                "ai_status": ai_status,
                "ai_error": ai_error,
                "ai_model": settings.openai_model,
            },
        )

        _log(
            f"[job:{job_id}] Completed. txt={result_txt_path} json={result_json_path} ai={ai_status}"
        )

        return {
            "ok": True,
            "job_id": job_id,
            "result_gcs_json_path": result_json_path,
            "result_gcs_txt_path": result_txt_path,
            "ai_result_gcs_json_path": ai_result_json_path,
            "ai_status": ai_status,
            "mode": ruleset,
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
        _log(f"[job:{job_id}] Failed err={e}")
        raise


def run_job_sync(job_id: str) -> dict[str, Any]:
    """Compat wrapper."""
    return run_job_logic(job_id)