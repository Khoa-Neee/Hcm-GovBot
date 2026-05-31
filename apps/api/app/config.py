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
    embedding_provider: str = "huggingface"
    hf_token: str = ""
    hf_embedding_model: str = "AITeamVN/Vietnamese_Embedding"
    hf_embedding_device: str = "cpu"
    hf_embedding_batch_size: int = 16

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

    vector_store: str = Field(default="pinecone", pattern="^(supabase|pinecone)$")
    python_textract_enabled: bool = True
    chunk_token_limit: int = 512
    chunk_overlap_tokens: int = 50
    pinecone_api_key: str = ""
    pinecone_index_name: str = "hcm-govbot"
    pinecone_namespace: str = "dev"
    pinecone_metric: str = "cosine"
    retrieval_bm25_top_n: int = 30
    retrieval_dense_top_n: int = 30
    retrieval_rrf_k: int = 60
    retrieval_rerank_top_n: int = 8
    retrieval_final_top_k: int = 8
    reranker_enabled: bool = True
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_device: str = "cpu"
    reranker_max_latency_seconds: float = 2.0
    bm25_tokenizer: str = "underthesea"
    bm25_cache_path: str = ".rag_cache/bm25_cache.pkl"
    chat_retrieve_every_turn: bool = True
    chat_rewrite_when_ambiguous: bool = True
    scheduler_enabled: bool = False
    scheduler_interval_hours: int = 24
    scheduler_run_on_startup: bool = True
    scheduler_startup_delay_seconds: int = 5
    scheduler_mark_inactive: bool = True
    scheduler_vector_force: bool = False
    scheduler_rag_sync_enabled: bool = False
    scheduler_pinecone_batch_size: int = 32
    scheduler_rag_progress_every: int = 100

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
