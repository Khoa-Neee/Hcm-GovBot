import time
from functools import cached_property
from typing import Any

from app.config import Settings

_RERANKER_CACHE = {}


class RerankService:
    def __init__(self, settings: Settings):
        self.settings = settings

    @cached_property
    def model(self):
        cache_key = (self.settings.reranker_model, self.settings.reranker_device)
        if cache_key in _RERANKER_CACHE:
            return _RERANKER_CACHE[cache_key]
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError(
                "Missing sentence-transformers. Install RAG dependencies with: "
                "pip install -r apps/api/requirements-rag.txt"
            ) from exc
        model = CrossEncoder(self.settings.reranker_model, device=self.settings.reranker_device, trust_remote_code=True)
        _RERANKER_CACHE[cache_key] = model
        return model

    def rerank(self, query: str, candidates: list[dict[str, Any]], top_n: int | None = None) -> list[dict[str, Any]]:
        if not self.settings.reranker_enabled or not candidates:
            return candidates[: top_n or len(candidates)]
        started = time.perf_counter()
        limit = min(len(candidates), self.settings.retrieval_rerank_top_n)
        selected = candidates[:limit]
        pairs = [(query, item.get("chunk_text") or item.get("chunk_markdown") or "") for item in selected]
        scores = self.model.predict(pairs)
        scored = [{**item, "rerank_score": float(score)} for item, score in zip(selected, scores)]
        ranked = sorted(scored, key=lambda item: item["rerank_score"], reverse=True)
        if time.perf_counter() - started > self.settings.reranker_max_latency_seconds:
            ranked = ranked[: max(1, top_n or self.settings.retrieval_final_top_k)]
        return ranked[: top_n or self.settings.retrieval_final_top_k]
