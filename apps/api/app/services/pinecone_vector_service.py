from dataclasses import dataclass
from collections.abc import Callable
from typing import Any

from app.config import Settings
from app.services.huggingface_embedding_service import HuggingFaceEmbeddingService
from app.services.supabase_repo import SupabaseRepository

_PINECONE_INDEX_CACHE = {}


@dataclass
class PineconeSyncStats:
    seen: int = 0
    upserted: int = 0
    failed: int = 0
    embedding_dim: int | None = None
    errors: list[str] | None = None


class PineconeVectorService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.repo = SupabaseRepository(settings)
        self.embedding = HuggingFaceEmbeddingService(settings)
        self._index = None

    @property
    def index(self):
        if self._index is None:
            cache_key = (
                self.settings.pinecone_api_key,
                self.settings.pinecone_index_name,
            )
            if cache_key in _PINECONE_INDEX_CACHE:
                self._index = _PINECONE_INDEX_CACHE[cache_key]
                return self._index
            if not self.settings.pinecone_api_key:
                raise RuntimeError("Missing PINECONE_API_KEY in .env")
            try:
                from pinecone import Pinecone
            except ImportError as exc:
                raise RuntimeError(
                    "Missing pinecone SDK. Install RAG dependencies with: "
                    "pip install -r apps/api/requirements-rag.txt"
                ) from exc
            self._index = Pinecone(api_key=self.settings.pinecone_api_key).Index(self.settings.pinecone_index_name)
            _PINECONE_INDEX_CACHE[cache_key] = self._index
        return self._index

    def sync_chunks(
        self,
        limit: int | None = None,
        batch_size: int = 32,
        progress_callback: Callable[[PineconeSyncStats], None] | None = None,
    ) -> PineconeSyncStats:
        stats = PineconeSyncStats(errors=[])
        chunks = self.repo.list_active_chunks(limit=limit)
        stats.embedding_dim = self.embedding.embedding_dimension()

        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            stats.seen += len(batch)
            try:
                vectors = self.embedding.embed_documents([self._embedding_text(chunk) for chunk in batch])
                payload = [
                    {
                        "id": chunk["chunk_id"],
                        "values": vector,
                        "metadata": self._metadata(chunk),
                    }
                    for chunk, vector in zip(batch, vectors)
                ]
                self.index.upsert(vectors=payload, namespace=self.settings.pinecone_namespace)
                stats.upserted += len(payload)
            except Exception as exc:
                stats.failed += len(batch)
                if stats.errors is not None and len(stats.errors) < 20:
                    stats.errors.append(f"batch {start}: {type(exc).__name__}: {exc}")
            if progress_callback:
                progress_callback(stats)
        return stats

    def search(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        vector = self.embedding.embed_query(query)
        response = self.index.query(
            vector=vector,
            top_k=top_k or self.settings.retrieval_dense_top_n,
            include_metadata=True,
            namespace=self.settings.pinecone_namespace,
        )
        matches = getattr(response, "matches", None)
        if matches is None and isinstance(response, dict):
            matches = response.get("matches", [])
        matches = matches or []
        results: list[dict[str, Any]] = []
        for match in matches:
            metadata = getattr(match, "metadata", None) or match.get("metadata", {})
            score = getattr(match, "score", None) if not isinstance(match, dict) else match.get("score")
            match_id = match.get("id") if isinstance(match, dict) else getattr(match, "id", None)
            results.append({**metadata, "chunk_id": metadata.get("chunk_id") or match_id, "dense_score": float(score or 0)})
        return results

    def _embedding_text(self, chunk: dict[str, Any]) -> str:
        return chunk.get("chunk_markdown") or chunk.get("chunk_text") or ""

    def _metadata(self, chunk: dict[str, Any]) -> dict[str, Any]:
        keys = [
            "chunk_id",
            "procedure_id",
            "procedure_code",
            "procedure_group",
            "name",
            "field_name",
            "target_audience",
            "implementation_agency",
            "section_name",
            "source_url",
            "content_hash",
        ]
        return {key: str(chunk.get(key) or "") for key in keys}
