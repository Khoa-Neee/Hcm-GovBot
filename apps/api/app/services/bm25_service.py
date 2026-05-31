import re
import time
import pickle
from pathlib import Path
from typing import Any

from app.config import Settings
from app.services.supabase_repo import SupabaseRepository

_BM25_CACHE: dict[str, Any] = {
    "model": None,
    "chunks": [],
    "count": 0,
}


class BM25Service:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.repo = SupabaseRepository(settings)
        self._chunks: list[dict[str, Any]] = []
        self._model = None

    def search(self, query: str, top_n: int | None = None) -> list[dict[str, Any]]:
        self._ensure_index()
        if not self._chunks or self._model is None:
            return []
        tokens = self._tokenize(query)
        scores = self._model.get_scores(tokens)
        ranked = sorted(enumerate(scores), key=lambda item: float(item[1]), reverse=True)[: top_n or self.settings.retrieval_bm25_top_n]
        return [{**self._chunks[index], "bm25_score": float(score)} for index, score in ranked if float(score) > 0]

    def refresh(self) -> None:
        _BM25_CACHE["chunks"] = []
        _BM25_CACHE["model"] = None
        _BM25_CACHE["count"] = 0
        self._ensure_index()

    def build_cache(self) -> dict[str, Any]:
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:
            raise RuntimeError(
                "Missing rank-bm25. Install RAG dependencies with: "
                "pip install -r apps/api/requirements-rag.txt"
            ) from exc

        chunks = self.repo.list_active_chunks()
        started = time.perf_counter()
        tokenized_corpus = [self._tokenize(chunk.get("chunk_text") or chunk.get("chunk_markdown") or "") for chunk in chunks]
        payload = {
            "tokenizer": self.settings.bm25_tokenizer,
            "chunk_count": len(chunks),
            "chunks": chunks,
            "tokenized_corpus": tokenized_corpus,
            "created_at": time.time(),
        }
        path = self._cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
        self._chunks = chunks
        self._model = BM25Okapi(tokenized_corpus) if tokenized_corpus else None
        _BM25_CACHE["chunks"] = self._chunks
        _BM25_CACHE["model"] = self._model
        _BM25_CACHE["count"] = len(self._chunks)
        return {
            "path": str(path),
            "chunk_count": len(chunks),
            "seconds": round(time.perf_counter() - started, 2),
        }

    def _ensure_index(self) -> None:
        if _BM25_CACHE["model"] is not None:
            self._chunks = _BM25_CACHE["chunks"]
            self._model = _BM25_CACHE["model"]
            return
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:
            raise RuntimeError(
                "Missing rank-bm25. Install RAG dependencies with: "
                "pip install -r apps/api/requirements-rag.txt"
            ) from exc
        started = time.perf_counter()
        cached = self._load_cache()
        if cached:
            self._chunks = cached["chunks"]
            corpus = cached["tokenized_corpus"]
            source = "cache"
        else:
            self._chunks = self.repo.list_active_chunks()
            corpus = [self._tokenize(chunk.get("chunk_text") or chunk.get("chunk_markdown") or "") for chunk in self._chunks]
            source = "live"
        self._model = BM25Okapi(corpus) if corpus else None
        _BM25_CACHE["chunks"] = self._chunks
        _BM25_CACHE["model"] = self._model
        _BM25_CACHE["count"] = len(self._chunks)
        print(f"[bm25] indexed {len(self._chunks)} chunks from {source} in {time.perf_counter() - started:.2f}s", flush=True)

    def _tokenize(self, text: str) -> list[str]:
        text = text.lower()
        if self.settings.bm25_tokenizer == "underthesea":
            try:
                from underthesea import word_tokenize

                tokens = word_tokenize(text, format="text").split()
                return [token for token in tokens if token.strip()]
            except ImportError as exc:
                raise RuntimeError(
                    "Missing underthesea. Install RAG dependencies with: "
                    "pip install -r apps/api/requirements-rag.txt"
                ) from exc
        return re.findall(r"[\wÀ-ỹ]+", text, flags=re.UNICODE)

    def _cache_path(self) -> Path:
        path = Path(self.settings.bm25_cache_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        return path

    def _load_cache(self) -> dict[str, Any] | None:
        path = self._cache_path()
        if not path.exists():
            return None
        try:
            with path.open("rb") as handle:
                payload = pickle.load(handle)
        except Exception:
            return None
        if payload.get("tokenizer") != self.settings.bm25_tokenizer:
            return None
        if not payload.get("chunks") or not payload.get("tokenized_corpus"):
            return None
        if len(payload["chunks"]) != len(payload["tokenized_corpus"]):
            return None
        return payload
