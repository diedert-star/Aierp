from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIERP_")

    database_url: str = "postgresql+psycopg://aierp:aierp@127.0.0.1:5432/aierp"
    blob_store_root: Path = Path("./blob_data")

    vies_cache_ttl_seconds: int = 3600
    vies_min_interval_seconds: float = 1.0
    vies_request_timeout_seconds: float = 5.0

    fuzzy_name_match_threshold: float = 0.6


settings = Settings()
