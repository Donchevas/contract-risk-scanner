from fastapi import FastAPI

from app.config import get_settings
from app.routes.contracts import router as contracts_router
from app.routes.jobs import router as jobs_router

app = FastAPI(title="Contract Risk Scanner API", version="0.1.0")


@app.on_event("startup")
def _startup_log() -> None:
    s = get_settings()
    # Ojo: no imprimimos la key, solo su longitud
    print(
        f"[startup] gcp_project_id={s.gcp_project_id} "
        f"gcs_bucket_name={s.gcs_bucket_name} "
        f"openai_model={s.openai_model} "
        f"openai_key_len={len(s.openai_api_key or '')}",
        flush=True,
    )


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(contracts_router)
app.include_router(jobs_router)