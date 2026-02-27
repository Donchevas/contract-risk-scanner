# Contract Risk Scanner - MVP Backend

Backend MVP con **FastAPI + Firestore + GCS** listo para desplegar en **Cloud Run**.

> Estado actual: upload de PDFs a GCS y creación/consulta de jobs en Firestore.

## Requisitos

- Python 3.11+
- Proyecto de GCP con APIs habilitadas:
  - Cloud Firestore
  - Cloud Storage
  - Cloud Run
- `gcloud` CLI instalado (para autenticación y deploy)

## Configuración

Variables de entorno soportadas (con defaults):

- `GCP_PROJECT_ID=contract-risk-scanner`
- `GCS_BUCKET_NAME=contract-risk-scanner-bucket`
- `MAX_UPLOAD_MB=20`

## Instalación local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Autenticación local de GCP (ADC)

Usa Application Default Credentials para que `google-cloud-storage` y `google-cloud-firestore` funcionen localmente:

```bash
gcloud auth application-default login
gcloud config set project contract-risk-scanner
```

Opcionalmente exporta variables:

```bash
export GCP_PROJECT_ID=contract-risk-scanner
export GCS_BUCKET_NAME=contract-risk-scanner-bucket
export MAX_UPLOAD_MB=20
```

## Ejecutar local

```bash
uvicorn app.main:app --reload
```

Endpoints:

- `GET /health`
- `POST /contracts/upload`
- `GET /jobs/{job_id}`

## Smoke test local

Con el servidor corriendo en `http://127.0.0.1:8000`:

```bash
curl -s http://127.0.0.1:8000/health
```

Respuesta esperada:

```json
{"status":"ok"}
```

## Ejemplos con curl

### 1) Upload de contrato PDF

```bash
curl -X POST "http://127.0.0.1:8000/contracts/upload" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@./sample.pdf;type=application/pdf"
```

Respuesta esperada (ejemplo):

```json
{
  "contract_id": "4e9420ad-f50e-4fd1-a239-5f74a2692a6c",
  "job_id": "16a7f5eb-470e-4a14-a8af-01f8f4e4c868",
  "status": "PENDING",
  "gcs_pdf_path": "gs://contract-risk-scanner-bucket/contracts/4e9420ad-f50e-4fd1-a239-5f74a2692a6c/original.pdf"
}
```

### 2) Consulta de job

```bash
curl -s "http://127.0.0.1:8000/jobs/16a7f5eb-470e-4a14-a8af-01f8f4e4c868"
```

## Deploy en Cloud Run

Desde la raíz del repo:

```bash
gcloud run deploy contract-risk-scanner-api \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars GCP_PROJECT_ID=contract-risk-scanner,GCS_BUCKET_NAME=contract-risk-scanner-bucket,MAX_UPLOAD_MB=20
```

## Prueba manual mínima (sin pytest)

1. Levantar API con `uvicorn app.main:app --reload`.
2. Ejecutar `GET /health` y validar `{"status":"ok"}`.
3. Hacer upload de un PDF válido (>1KB y <= `MAX_UPLOAD_MB`).
4. Copiar `job_id` de la respuesta y consultar `GET /jobs/{job_id}`.
5. Verificar en GCS que existe `contracts/{contract_id}/original.pdf`.
6. Verificar en Firestore documentos en colecciones `contracts` y `jobs`.
