from dataclasses import dataclass
from collections.abc import Callable
from traceback import format_exception_only

from app.config import Settings
from app.services.chunking_service import ChunkingService
from app.services.document_extraction_service import DocumentExtractionService
from app.services.supabase_repo import SupabaseRepository


@dataclass
class RagBuildStats:
    seen: int = 0
    documents_upserted: int = 0
    chunks_upserted: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] | None = None


class RagBuildService:
    def __init__(self, settings: Settings):
        self.repo = SupabaseRepository(settings)
        self.extractor = DocumentExtractionService(settings)
        self.chunker = ChunkingService(settings)

    def build_documents_and_chunks(
        self,
        procedure_group: str | None = None,
        limit: int | None = None,
        force: bool = False,
        progress_every: int = 25,
        progress_callback: Callable[[RagBuildStats], None] | None = None,
    ) -> RagBuildStats:
        stats = RagBuildStats(errors=[])
        procedures = self.repo.list_procedures_for_documents(procedure_group=procedure_group, limit=limit)

        for procedure in procedures:
            stats.seen += 1
            try:
                extracted = self.extractor.extract(procedure)
                existing = self.repo.get_procedure_document(procedure["id"], extracted.source_type)
                if not force and existing and existing.get("content_hash") == extracted.content_hash:
                    stats.skipped += 1
                    continue

                document = self.repo.upsert_procedure_document(extracted.__dict__)
                chunks = self.chunker.chunk_document(procedure, document)
                self.repo.replace_procedure_chunks(procedure["id"], [self.chunker.to_row(chunk) for chunk in chunks])
                stats.documents_upserted += 1
                stats.chunks_upserted += len(chunks)
            except Exception as exc:
                stats.failed += 1
                if stats.errors is not None and len(stats.errors) < 20:
                    stats.errors.append(
                        f"{procedure.get('procedure_code')}: "
                        + "".join(format_exception_only(type(exc), exc)).strip()
                    )
            if progress_callback and progress_every > 0 and stats.seen % progress_every == 0:
                progress_callback(stats)

        return stats
