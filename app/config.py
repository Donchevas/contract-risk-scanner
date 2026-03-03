from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la aplicación cargada desde variables de entorno."""

    gcp_project_id: str = "contract-risk-scanner-488718"
    gcs_bucket_name: str = "contract-risk-scanner-bucket"
    
    max_upload_mb: int = 20

    # OpenAI
    openai_api_key: str = ""          # Se debe definir como variable de entorno
    openai_model: str = "gpt-4o-mini"
    openai_max_input_chars: int = 40000  # Controla cuánto texto mandamos a la IA

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

