from dataclasses import dataclass
from collections.abc import Callable
from traceback import format_exception_only

from app.config import Settings
from app.crawler import ProcedureCrawler
from app.models import ProcedureGroup
from app.services.supabase_repo import SupabaseRepository


@dataclass
class SyncStats:
    seen: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    inactivated: int = 0
    vector_synced: int = 0
    failed: int = 0
    run_id: str | None = None
    errors: list[str] | None = None


class ProcedureSyncService:
    def __init__(self, settings: Settings):
        self.crawler = ProcedureCrawler(settings)
        self.repo = SupabaseRepository(settings)

    async def sync_group(
        self,
        group: ProcedureGroup,
        max_items: int | None = None,
        mark_inactive: bool = False,
        progress_every: int = 25,
        progress_callback: Callable[[SyncStats], None] | None = None,
    ) -> SyncStats:
        stats = SyncStats()
        stats.errors = []
        seen_source_ids: set[str] = set()
        run_id = self.repo.create_crawl_run(
            group.value,
            metadata={
                "max_items": max_items,
                "mark_inactive": mark_inactive,
                "sync_vector": False,
            },
        )
        stats.run_id = run_id

        try:
            async for summary in self.crawler.iter_summaries(group):
                if max_items is not None and stats.seen >= max_items:
                    break

                stats.seen += 1
                seen_source_ids.add(summary.source_id)
                try:
                    detail = await self.crawler.fetch_detail(summary)
                    action, _saved = self.repo.upsert_procedure(detail)
                    if action == "inserted":
                        stats.inserted += 1
                    elif action == "updated":
                        stats.updated += 1
                    else:
                        stats.unchanged += 1
                except Exception as exc:
                    stats.failed += 1
                    if stats.errors is not None and len(stats.errors) < 10:
                        stats.errors.append(
                            f"{summary.procedure_code} ({summary.source_id}): "
                            + "".join(format_exception_only(type(exc), exc)).strip()
                        )

                if progress_callback and progress_every > 0 and stats.seen % progress_every == 0:
                    progress_callback(stats)

            if mark_inactive:
                stats.inactivated = self.repo.mark_inactive_missing(group.value, seen_source_ids)

            self.repo.finish_crawl_run(
                run_id=run_id,
                status="success" if stats.failed == 0 else "failed",
                total_seen=stats.seen,
                inserted_count=stats.inserted,
                updated_count=stats.updated,
                unchanged_count=stats.unchanged,
                inactivated_count=stats.inactivated,
                error_message=None if stats.failed == 0 else f"{stats.failed} procedure(s) failed to sync",
            )
        except Exception as exc:
            self.repo.finish_crawl_run(
                run_id=run_id,
                status="failed",
                total_seen=stats.seen,
                inserted_count=stats.inserted,
                updated_count=stats.updated,
                unchanged_count=stats.unchanged,
                inactivated_count=stats.inactivated,
                error_message="".join(format_exception_only(type(exc), exc)).strip(),
            )
            raise

        return stats

    async def sync_source_ids(self, group: ProcedureGroup, source_ids: list[str]) -> SyncStats:
        stats = SyncStats(errors=[])
        run_id = self.repo.create_crawl_run(
            group.value,
            metadata={
                "source_ids": source_ids,
                "mark_inactive": False,
                "sync_vector": False,
            },
        )
        stats.run_id = run_id

        try:
            summaries = await self.crawler.find_summaries_by_source_ids(group, set(source_ids))
            for source_id in source_ids:
                stats.seen += 1
                summary = summaries.get(source_id)
                if summary is None:
                    stats.failed += 1
                    if stats.errors is not None:
                        stats.errors.append(f"{source_id}: not found in DVCQG search result")
                    continue

                try:
                    detail = await self.crawler.fetch_detail(summary)
                    action, _saved = self.repo.upsert_procedure(detail)
                    if action == "inserted":
                        stats.inserted += 1
                    elif action == "updated":
                        stats.updated += 1
                    else:
                        stats.unchanged += 1
                except Exception as exc:
                    stats.failed += 1
                    if stats.errors is not None and len(stats.errors) < 10:
                        stats.errors.append(
                            f"{summary.procedure_code} ({summary.source_id}): "
                            + "".join(format_exception_only(type(exc), exc)).strip()
                        )

            self.repo.finish_crawl_run(
                run_id=run_id,
                status="success" if stats.failed == 0 else "failed",
                total_seen=stats.seen,
                inserted_count=stats.inserted,
                updated_count=stats.updated,
                unchanged_count=stats.unchanged,
                inactivated_count=0,
                error_message=None if stats.failed == 0 else f"{stats.failed} source_id(s) failed to sync",
            )
        except Exception as exc:
            self.repo.finish_crawl_run(
                run_id=run_id,
                status="failed",
                total_seen=stats.seen,
                inserted_count=stats.inserted,
                updated_count=stats.updated,
                unchanged_count=stats.unchanged,
                inactivated_count=0,
                error_message="".join(format_exception_only(type(exc), exc)).strip(),
            )
            raise

        return stats
