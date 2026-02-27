from __future__ import annotations

from google.cloud import storage

from app.config import get_settings


def get_storage_client() -> storage.Client:
    settings = get_settings()
    return storage.Client(project=settings.gcp_project_id)


def upload_contract_pdf(*, contract_id: str, content: bytes, content_type: str) -> str:
    settings = get_settings()
    blob_path = f"contracts/{contract_id}/original.pdf"

    client = get_storage_client()
    bucket = client.bucket(settings.gcs_bucket_name)
    blob = bucket.blob(blob_path)
    blob.upload_from_string(content, content_type=content_type)

    return f"gs://{settings.gcs_bucket_name}/{blob_path}"
