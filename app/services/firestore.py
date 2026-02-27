from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

from app.config import get_settings


def get_firestore_client() -> firestore.Client:
    settings = get_settings()
    return firestore.Client(project=settings.gcp_project_id)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_contract(
    *,
    contract_id: str,
    filename: str,
    gcs_pdf_path: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "filename": filename,
        "gcs_pdf_path": gcs_pdf_path,
        "created_at": _utc_now_iso(),
    }
    client = get_firestore_client()
    client.collection("contracts").document(contract_id).set(payload)
    return payload


def create_job(*, job_id: str, contract_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract_id": contract_id,
        "status": "PENDING",
        "progress": 0,
        "error": None,
        "created_at": _utc_now_iso(),
        "started_at": None,
        "finished_at": None,
        "result_gcs_json_path": None,
        "report_gcs_pdf_path": None,
    }
    client = get_firestore_client()
    client.collection("jobs").document(job_id).set(payload)
    return payload


def get_job(job_id: str) -> dict[str, Any] | None:
    client = get_firestore_client()
    snapshot = client.collection("jobs").document(job_id).get()

    if not snapshot.exists:
        return None

    data = snapshot.to_dict() or {}
    data["job_id"] = job_id
    return data
