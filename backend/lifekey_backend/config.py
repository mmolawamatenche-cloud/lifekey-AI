from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LIFEKEY_",
        env_file=BACKEND_DIR / ".env",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8000
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"
    ollama_think: bool = False
    request_timeout_s: float = 120.0
    approval_ttl_s: int = 300
    approval_log_path: str = ""
