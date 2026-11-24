from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Keitaro Wrapper"
    app_env: str = "development"
    database_url: str = "sqlite:///./keitaro_wrapper.db"
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000"

    keitaro_base_url: str = ""
    keitaro_api_key: str = ""
    keitaro_api_prefix: str = "/admin_api/v1"
    keitaro_timeout_seconds: float = 20.0
    keitaro_http_redirect_action: str = "http"
    keitaro_offer_flow_action: str = "http"
    keitaro_country_filter_name: str = "country"
    google_redirect_url: str = "https://www.google.com"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
