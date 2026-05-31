import time
from typing import Any

from app.config import Settings
from app.services.bm25_service import BM25Service
from app.services.pinecone_vector_service import PineconeVectorService
from app.services.rerank_service import RerankService
from app.services.supabase_repo import SupabaseRepository


class HybridRetrievalService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.repo = SupabaseRepository(settings)
        self.bm25 = BM25Service(settings)
        self.dense = PineconeVectorService(settings)
        self.reranker = RerankService(settings)

    def search(self, query: str, final_top_k: int | None = None) -> list[dict[str, Any]]:
        started = time.perf_counter()
        bm25_results = self.bm25.search(query, self.settings.retrieval_bm25_top_n)
        after_bm25 = time.perf_counter()
        dense_results = self.dense.search(query, self.settings.retrieval_dense_top_n)
        after_dense = time.perf_counter()
        fused = self._rrf([bm25_results, dense_results])
        chunk_ids = [item["chunk_id"] for item in fused if item.get("chunk_id")]
        full_chunks = self.repo.get_chunks_by_ids(chunk_ids)
        after_hydrate = time.perf_counter()
        by_id = {chunk["chunk_id"]: chunk for chunk in full_chunks}
        hydrated = [{**by_id[item["chunk_id"]], **item} for item in fused if item.get("chunk_id") in by_id]
        reranked = self.reranker.rerank(query, hydrated, top_n=final_top_k or self.settings.retrieval_final_top_k)
        after_rerank = time.perf_counter()
        print(
            "[retrieval] "
            f"bm25={after_bm25 - started:.2f}s "
            f"dense={after_dense - after_bm25:.2f}s "
            f"hydrate={after_hydrate - after_dense:.2f}s "
            f"rerank={after_rerank - after_hydrate:.2f}s "
            f"total={after_rerank - started:.2f}s "
            f"candidates={len(hydrated)}",
            flush=True,
        )
        return reranked

    def _rrf(self, ranked_lists: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
        scores: dict[str, float] = {}
        merged: dict[str, dict[str, Any]] = {}
        k = self.settings.retrieval_rrf_k
        for ranked in ranked_lists:
            for rank, item in enumerate(ranked, start=1):
                chunk_id = str(item.get("chunk_id") or "")
                if not chunk_id:
                    continue
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
                merged[chunk_id] = {**merged.get(chunk_id, {}), **item}
        return [
            {**merged[chunk_id], "rrf_score": score}
            for chunk_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
        ]
