from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pypdf import PdfReader

from app.services.storage import download_bytes_from_gcs


@dataclass
class ExtractedText:
    text: str
    pages: int


def extract_text_from_gcs_pdf(gs_pdf_path: str) -> ExtractedText:
    """
    Extrae texto de un PDF (texto seleccionable) guardado en GCS.
    No usa OCR.
    """
    pdf_bytes = download_bytes_from_gcs(gs_pdf_path)

    reader = PdfReader(io_bytes := _BytesIO(pdf_bytes))
    texts: list[str] = []

    for page in reader.pages:
        t = page.extract_text() or ""
        # Limpieza mínima
        t = t.replace("\u00a0", " ").strip()
        texts.append(t)

    full_text = "\n\n".join([t for t in texts if t])

    return ExtractedText(
        text=full_text,
        pages=len(reader.pages),
    )


class _BytesIO:
    """Pequeño wrapper para evitar importar io en varios sitios."""
    def __init__(self, data: bytes):
        import io
        self._bio = io.BytesIO(data)

    def __getattr__(self, name: str):
        return getattr(self._bio, name)