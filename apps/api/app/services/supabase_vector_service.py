from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.services.gemini_client import GeminiModelClient
from app.services.supabase_repo import SupabaseRepository


@dataclass
class VectorSyncStats:
    seen: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: int = 0
    errors: list[str] | None = None


class SupabaseVectorService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.repo = SupabaseRepository(settings)
        self.gemini = GeminiModelClient(settings)

    def sync_embeddings(
        self,
        procedure_group: str | None = None,
        limit: int | None = None,
        force: bool = False,
    ) -> VectorSyncStats:
        stats = VectorSyncStats(errors=[])
        procedures = self.repo.list_procedures_for_embedding(procedure_group=procedure_group, limit=limit)

        for index, procedure in enumerate(procedures):
            stats.seen += 1
            try:
                existing = self.repo.get_embedding_by_code(procedure["procedure_code"], procedure["procedure_group"])
                if (
                    not force
                    and existing is not None
                    and existing.get("content_hash") == procedure["content_hash"]
                    and existing.get("is_active", True)
                ):
                    stats.unchanged += 1
                    continue

                text = self._embedding_text(procedure)
                embedding = self.gemini.embed_text(
                    text=text,
                    task_type="RETRIEVAL_DOCUMENT",
                    title=procedure["name"],
                    key_index=index,
                )
                action = self.repo.upsert_procedure_embedding(
                    procedure=procedure,
                    embedding=embedding,
                    embedding_model=self.settings.gemini_embedding_model,
                    embedding_dim=self.settings.embedding_dimensions,
                )
                if action == "inserted":
                    stats.inserted += 1
                elif action == "updated":
                    stats.updated += 1
                else:
                    stats.unchanged += 1
            except Exception as exc:
                stats.failed += 1
                if stats.errors is not None and len(stats.errors) < 10:
                    stats.errors.append(f"{procedure.get('procedure_code')}: {type(exc).__name__}: {exc}")

        return stats

    def search(
        self,
        query: str,
        match_count: int = 9,
        filter_group: str | None = None,
        filter_target_audience: str | None = None,
        key_index: int = 0,
    ) -> list[dict[str, Any]]:
        query_embedding = self.gemini.embed_text(
            text=query,
            task_type="RETRIEVAL_QUERY",
            title=None,
            key_index=key_index,
        )
        return self.repo.match_procedure_embeddings(
            query_embedding=query_embedding,
            match_count=match_count,
            filter_group=filter_group,
            filter_target_audience=filter_target_audience,
        )

    def count(self, procedure_group: str | None = None) -> int:
        return self.repo.count_procedure_embeddings(procedure_group=procedure_group)

    def _embedding_text(self, procedure: dict[str, Any]) -> str:
        parts = [
            f"Tên thủ tục: {procedure.get('name') or ''}",
            f"Mã thủ tục: {procedure.get('procedure_code') or ''}",
            f"Nhóm thủ tục: {procedure.get('procedure_group') or ''}",
            f"Lĩnh vực: {procedure.get('field_name') or ''}",
            f"Đối tượng: {procedure.get('target_audience') or ''}",
            f"Cơ quan thực hiện: {procedure.get('implementation_agency') or ''}",
        ]
        return "\n".join(parts)
