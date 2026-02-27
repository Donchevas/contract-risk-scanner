from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la aplicación cargada desde variables de entorno."""

    gcp_project_id: str = "contract-risk-scanner"
    gcs_bucket_name: str = "contract-risk-scanner-bucket"
    max_upload_mb: int = 20

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
