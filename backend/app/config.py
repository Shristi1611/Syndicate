from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root is two levels above this file: backend/app/config.py -> repo root
ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    llm_provider: str = "gemini"  # "gemini", "claude" or "mock"
    llm_api_key: str = ""
    llm_fast_model: str = ""      # cheap and quick, used for haggling
    llm_strong_model: str = ""    # stronger, used for the final itinerary

    llm_timeout_seconds: float = 20.0  # give up on a live call after this long
    llm_cache: bool = True             # replay identical prompts from the local cache
    llm_fallback: bool = True          # use the offline mock when the live model fails

    # Folder holding suppliers, hotels, activities and personas (JSON).
    # Empty means the repo's data/ folder. The tests point this at tests/fixtures.
    catalogue_dir: str = ""

    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")


settings = Settings()

CATALOGUE_DIR = Path(settings.catalogue_dir) if settings.catalogue_dir else ROOT_DIR / "data"