from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    gemini_api_key_1: str = ""
    gemini_api_key_2: str = ""
    gemini_api_key_3: str = ""
    gemini_api_key_4: str = ""
    gemini_api_key_5: str = ""
    gemini_api_key_6: str = ""
    gemini_api_key_7: str = ""
    gemini_api_key_8: str = ""
    gemini_api_key_9: str = ""
    gemini_api_key_10: str = ""
    gemini_chat_model: str = "gemma-4-31b-it"
    gemini_embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 768

    dvc_base_url: str = "https://thutuc.dichvucong.gov.vn"
    dvc_rest_path: str = "/jsp/rest.jsp"
    dvc_hcmc_agency_id: str = "411312"
    dvc_hcmc_agency_name: str = "UBND Thành phố Hồ Chí Minh"
    dvc_hcmc_agency_code: str = "H29"
    dvc_request_timeout_seconds: float = 60.0
    dvc_max_retries: int = 5
    dvc_retry_backoff_seconds: float = 1.5
    dvc_page_delay_seconds: float = 0.5

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_reload: bool = False
    backend_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    vector_store: str = Field(default="supabase", pattern="^supabase$")
    scheduler_enabled: bool = False
    scheduler_interval_hours: int = 24
    scheduler_run_on_startup: bool = True
    scheduler_startup_delay_seconds: int = 5
    scheduler_mark_inactive: bool = True
    scheduler_vector_force: bool = False

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.backend_cors_origins.split(",") if item.strip()]

    @property
    def gemini_api_keys(self) -> list[str]:
        return [
            key
            for key in [
                self.gemini_api_key_1,
                self.gemini_api_key_2,
                self.gemini_api_key_3,
                self.gemini_api_key_4,
                self.gemini_api_key_5,
                self.gemini_api_key_6,
                self.gemini_api_key_7,
                self.gemini_api_key_8,
                self.gemini_api_key_9,
                self.gemini_api_key_10,
            ]
            if key
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
