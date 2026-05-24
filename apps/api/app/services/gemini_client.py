from google import genai
from google.genai import types

from app.config import Settings


class GeminiModelError(RuntimeError):
    pass


class GeminiModelClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_keys = settings.gemini_api_keys
        if not self.api_keys:
            raise ValueError("Missing GEMINI_API_KEY_1..10")

    def generate_text(self, prompt: str, model: str | None = None, key_index: int = 0) -> str:
        target_model = model or self.settings.gemini_chat_model
        errors: list[str] = []

        for offset in range(len(self.api_keys)):
            api_key = self.api_keys[(key_index + offset) % len(self.api_keys)]
            try:
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=target_model,
                    contents=prompt,
                )
                text = response.text or ""
                if text.strip():
                    return text
                errors.append(f"key#{offset + 1}: empty response")
            except Exception as exc:
                errors.append(f"key#{offset + 1}: {type(exc).__name__}: {exc}")

        raise GeminiModelError(f"All Gemini API keys failed for model {target_model}. " + " | ".join(errors))

    def embed_text(
        self,
        text: str,
        task_type: str = "RETRIEVAL_DOCUMENT",
        title: str | None = None,
        key_index: int = 0,
    ) -> list[float]:
        errors: list[str] = []

        for offset in range(len(self.api_keys)):
            api_key = self.api_keys[(key_index + offset) % len(self.api_keys)]
            try:
                client = genai.Client(api_key=api_key)
                response = client.models.embed_content(
                    model=self.settings.gemini_embedding_model,
                    contents=text,
                    config=types.EmbedContentConfig(
                        task_type=task_type,
                        title=title,
                        output_dimensionality=self.settings.embedding_dimensions,
                    ),
                )
                if not response.embeddings:
                    errors.append(f"key#{offset + 1}: empty embedding response")
                    continue

                values = response.embeddings[0].values
                if values:
                    return [float(value) for value in values]
                errors.append(f"key#{offset + 1}: empty embedding values")
            except Exception as exc:
                errors.append(f"key#{offset + 1}: {type(exc).__name__}: {exc}")

        raise GeminiModelError(
            f"All Gemini API keys failed for embedding model {self.settings.gemini_embedding_model}. "
            + " | ".join(errors)
        )
