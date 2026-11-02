from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root is two levels above this file: backend/app/config.py -> repo root
ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    llm_provider: str = "gemini"  # "gemini" or "claude"
    llm_api_key: str = ""
    llm_fast_model: str = ""      # cheap and quick, used for haggling
    llm_strong_model: str = ""    # stronger, used for the final itinerary

    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")


settings = Settings()