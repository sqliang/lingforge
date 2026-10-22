"""Typed runtime configuration; secrets are injected only into trusted services."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration shared by API and Worker, read from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    database_url: str
    model_base_url: str = "https://api.openai.com/v1"
    model_api_key: str
    model_name: str
    platform_origin: str = "http://localhost:3000"
    api_origin: str = "http://localhost:8000"
    preview_origin: str = "http://localhost:8081"
    projects_root: Path = Path("/var/lib/lingforge/projects")
    artifacts_root: Path = Path("/var/lib/lingforge/artifacts")
    projects_volume_name: str = "infra_projects"
    build_runner_image: str = "lingforge-build-runner:local"
    preview_ticket_secret: str


settings = Settings()
