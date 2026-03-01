from __future__ import annotations

import json
from typing import Any, Tuple

from google.cloud import storage
from app.config import get_settings


def _parse_gs_path(gs_path: str) -> Tuple[str, str]:
    if not gs_path.startswith("gs://"):
        raise ValueError(f"Invalid GCS path: {gs_path}")

    no_scheme = gs_path[len("gs://") :]
    bucket, _, blob = no_scheme.partition("/")

    if not bucket or not blob:
        raise ValueError(f"Invalid GCS path: {gs_path}")

    return bucket, blob


def _client() -> storage.Client:
    settings = get_settings()
    return storage.Client(project=settings.gcp_project_id)


def gcs_blob_exists(gs_path: str) -> bool:
    bucket_name, blob_name = _parse_gs_path(gs_path)
    client = _client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    return blob.exists(client)


def upload_json_to_gcs(gs_path: str, data: dict[str, Any]) -> None:
    bucket_name, blob_name = _parse_gs_path(gs_path)

    client = _client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    payload = json.dumps(data, ensure_ascii=False, indent=2)
    blob.upload_from_string(payload, content_type="application/json")