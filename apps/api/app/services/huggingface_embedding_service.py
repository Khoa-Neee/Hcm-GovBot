from functools import cached_property

from app.config import Settings

_MODEL_CACHE = {}


class HuggingFaceEmbeddingService:
    def __init__(self, settings: Settings):
        self.settings = settings

    @cached_property
    def model(self):
        cache_key = (
            self.settings.hf_embedding_model,
            self.settings.hf_embedding_device,
            bool(self.settings.hf_token),
        )
        if cache_key in _MODEL_CACHE:
            return _MODEL_CACHE[cache_key]
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Missing sentence-transformers. Install RAG dependencies with: "
                "pip install -r apps/api/requirements-rag.txt"
            ) from exc

        kwargs = {"device": self.settings.hf_embedding_device}
        if self.settings.hf_token:
            kwargs["token"] = self.settings.hf_token
        model = SentenceTransformer(self.settings.hf_embedding_model, trust_remote_code=True, **kwargs)
        _MODEL_CACHE[cache_key] = model
        return model

    def embed_query(self, text: str) -> list[float]:
        return self._encode([text])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._encode(texts)

    def embedding_dimension(self) -> int:
        return len(self.embed_query("kiem tra kich thuoc vector"))

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(
            texts,
            batch_size=self.settings.hf_embedding_batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [[float(value) for value in vector.tolist()] for vector in vectors]
