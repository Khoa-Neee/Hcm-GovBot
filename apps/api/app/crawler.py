import asyncio
from collections.abc import AsyncIterator

from app.config import Settings
from app.models import ProcedureDetail, ProcedureGroup, ProcedureSummary
from app.services.dvc_client import DvcClient


class ProcedureCrawler:
    def __init__(self, settings: Settings):
        self.client = DvcClient(settings)

    async def preview(self, group: ProcedureGroup, limit: int = 5) -> tuple[list[ProcedureSummary], int]:
        items, total = await self.client.search_procedures(group=group, page_index=1, record_per_page=limit)
        return items[:limit], total

    async def iter_summaries(
        self,
        group: ProcedureGroup,
        page_size: int = 100,
    ) -> AsyncIterator[ProcedureSummary]:
        page = 1
        yielded = 0
        total: int | None = None

        while total is None or yielded < total:
            items, total_found = await self.client.search_procedures(group=group, page_index=page, record_per_page=page_size)
            total = total_found
            if not items:
                break

            for item in items:
                yielded += 1
                yield item

            page += 1
            await asyncio.sleep(self.client.settings.dvc_page_delay_seconds)

    async def find_summary_by_source_id(self, group: ProcedureGroup, source_id: str) -> ProcedureSummary | None:
        async for summary in self.iter_summaries(group):
            if summary.source_id == source_id:
                return summary
        return None

    async def find_summaries_by_source_ids(
        self,
        group: ProcedureGroup,
        source_ids: set[str],
    ) -> dict[str, ProcedureSummary]:
        found: dict[str, ProcedureSummary] = {}
        async for summary in self.iter_summaries(group):
            if summary.source_id in source_ids:
                found[summary.source_id] = summary
                if len(found) == len(source_ids):
                    break
        return found

    async def fetch_detail(self, summary: ProcedureSummary) -> ProcedureDetail:
        return await self.client.fetch_detail(summary)
