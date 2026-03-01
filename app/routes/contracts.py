from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.config import get_settings
from app.services.firestore import create_contract, create_job
from app.services.gcs import upload_contract_pdf

# ✅ Importa el handler del job (NO run_job_logic)
from app.routes.jobs import run_job

router = APIRouter(prefix="/contracts", tags=["contracts"])


@router.post("/upload")
async def upload_contract(file: UploadFile = File(...)) -> dict[str, str | int | None]:
    settings = get_settings()

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes enviar un archivo con nombre.",
        )

    extension = Path(file.filename).suffix.lower()
    if extension != ".pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo debe tener extensión .pdf.",
        )

    content_type = (file.content_type or "").lower()
    if content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo debe tener content-type application/pdf.",
        )

    content = await file.read()
    size_bytes = len(content)

    if size_bytes <= 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo es demasiado pequeño. Debe ser mayor a 1KB.",
        )

    max_size_bytes = settings.max_upload_mb * 1024 * 1024
    if size_bytes > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"El archivo supera el tamaño máximo permitido de {settings.max_upload_mb}MB."
            ),
        )

    contract_id = str(uuid4())
    job_id = str(uuid4())

    gcs_pdf_path = upload_contract_pdf(
        contract_id=contract_id,
        content=content,
        content_type=content_type,
    )

    create_contract(
        contract_id=contract_id,
        filename=file.filename,
        gcs_pdf_path=gcs_pdf_path,
    )
    create_job(job_id=job_id, contract_id=contract_id)

    # ✅ Auto-run (Plan A)
    auto_run_result = run_job(job_id)

    return {
        "contract_id": contract_id,
        "job_id": job_id,
        "status": "DONE" if auto_run_result.get("ok") else "PENDING",
        "gcs_pdf_path": gcs_pdf_path,
        "auto_run": 1,
    }