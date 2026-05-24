import asyncio
import logging
from datetime import datetime, timedelta
from threading import Lock

from app.config import Settings
from app.models import ProcedureGroup
from app.services.supabase_vector_service import SupabaseVectorService
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
            await sync_service.sync_group(
                group=group,
                max_items=None,
                mark_inactive=self.settings.scheduler_mark_inactive,
                progress_every=0,
            )

        vector_service = SupabaseVectorService(self.settings)
        vector_service.sync_embeddings(force=self.settings.scheduler_vector_force)
        logger.info("Scheduled sync finished")
