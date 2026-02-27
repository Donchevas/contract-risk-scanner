from fastapi import FastAPI

from app.routes.contracts import router as contracts_router
from app.routes.jobs import router as jobs_router

app = FastAPI(title="Contract Risk Scanner API", version="0.1.0")


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(contracts_router)
app.include_router(jobs_router)
