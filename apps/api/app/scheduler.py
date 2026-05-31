import asyncio
import logging
from datetime import datetime, timedelta
from threading import Lock

from app.config import Settings
from app.models import ProcedureGroup
from app.services.bm25_service import BM25Service
from app.services.pinecone_vector_service import PineconeVectorService
from app.services.rag_build_service import RagBuildService
from app.sync import ProcedureSyncService

logger = logging.getLogger(__name__)


class AppScheduler:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.scheduler = None
        self._run_lock = Lock()

    def start(self) -> None:
        if not self.settings.scheduler_enabled:
            return
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
        except ModuleNotFoundError as exc:
            raise RuntimeError("SCHEDULER_ENABLED=true requires apscheduler. Run: pip install -r requirements.txt") from exc

        self.scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
        self.scheduler.add_job(
            self.run_pipeline,
            trigger="interval",
            hours=self.settings.scheduler_interval_hours,
            id="dvcqg_24h_sync",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        if self.settings.scheduler_run_on_startup:
            self.scheduler.add_job(
                self.run_pipeline,
                trigger="date",
                run_date=datetime.now() + timedelta(seconds=max(0, self.settings.scheduler_startup_delay_seconds)),
                id="dvcqg_startup_sync",
                replace_existing=True,
                max_instances=1,
            )
        self.scheduler.start()
        logger.info(
            "Scheduler started: every %s hour(s), run_on_startup=%s",
            self.settings.scheduler_interval_hours,
            self.settings.scheduler_run_on_startup,
        )

    def shutdown(self) -> None:
        if self.scheduler is not None and self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def run_pipeline(self) -> None:
        if not self._run_lock.acquire(blocking=False):
            logger.info("Scheduled sync skipped because a previous sync is still running")
            return
        try:
            asyncio.run(self._run_pipeline_async())
        except Exception:
            logger.exception("Scheduled sync failed")
        finally:
            self._run_lock.release()

    async def _run_pipeline_async(self) -> None:
        logger.info("Scheduled sync started")
        sync_service = ProcedureSyncService(self.settings)
        sync_service.repo.delete_expired_chat_sessions()
        for group in [ProcedureGroup.administrative, ProcedureGroup.interlinked]:
            stats = await sync_service.sync_group(
                group=group,
                max_items=None,
                mark_inactive=self.settings.scheduler_mark_inactive,
                progress_every=0,
            )
            logger.info(
                "Scheduled crawl %s finished: seen=%s inserted=%s updated=%s unchanged=%s failed=%s",
                group.value,
                stats.seen,
                stats.inserted,
                stats.updated,
                stats.unchanged,
                stats.failed,
            )

        if self.settings.scheduler_rag_sync_enabled:
            rag_service = RagBuildService(self.settings)
            rag_stats = rag_service.build_documents_and_chunks(
                force=self.settings.scheduler_vector_force,
                progress_every=self.settings.scheduler_rag_progress_every,
                progress_callback=lambda stats: logger.info(
                    "Scheduled rag-build progress: seen=%s documents=%s chunks=%s skipped=%s failed=%s",
                    stats.seen,
                    stats.documents_upserted,
                    stats.chunks_upserted,
                    stats.skipped,
                    stats.failed,
                ),
            )
            logger.info(
                "Scheduled rag-build finished: seen=%s documents=%s chunks=%s skipped=%s failed=%s",
                rag_stats.seen,
                rag_stats.documents_upserted,
                rag_stats.chunks_upserted,
                rag_stats.skipped,
                rag_stats.failed,
            )

            pinecone_service = PineconeVectorService(self.settings)
            pinecone_stats = pinecone_service.sync_chunks(
                batch_size=self.settings.scheduler_pinecone_batch_size,
                progress_callback=lambda stats: logger.info(
                    "Scheduled pinecone-sync progress: seen=%s upserted=%s failed=%s embedding_dim=%s",
                    stats.seen,
                    stats.upserted,
                    stats.failed,
                    stats.embedding_dim,
                ),
            )
            logger.info(
                "Scheduled pinecone-sync finished: seen=%s upserted=%s failed=%s embedding_dim=%s",
                pinecone_stats.seen,
                pinecone_stats.upserted,
                pinecone_stats.failed,
                pinecone_stats.embedding_dim,
            )

            if self.settings.scheduler_bm25_sync_enabled:
                bm25_stats = BM25Service(self.settings).build_cache()
                logger.info(
                    "Scheduled bm25 cache rebuilt: chunks=%s seconds=%s path=%s",
                    bm25_stats["chunk_count"],
                    bm25_stats["seconds"],
                    bm25_stats["path"],
                )
            else:
                logger.info("Scheduled BM25 cache rebuild skipped because SCHEDULER_BM25_SYNC_ENABLED=false")
        else:
            logger.info("Scheduled RAG/Pinecone/BM25 sync skipped because SCHEDULER_RAG_SYNC_ENABLED=false")
        logger.info("Scheduled sync finished")
