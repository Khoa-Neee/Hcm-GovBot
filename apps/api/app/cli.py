import argparse
import asyncio
import json
import sys

from app.config import get_settings
from app.crawler import ProcedureCrawler
from app.models import ProcedureGroup
from app.services.gemini_client import GeminiModelClient
from app.services.supabase_repo import SupabaseRepository
from app.services.supabase_vector_service import SupabaseVectorService
from app.sync import ProcedureSyncService


async def crawl_preview(args: argparse.Namespace) -> None:
    crawler = ProcedureCrawler(get_settings())
    items, total = await crawler.preview(ProcedureGroup(args.group), args.limit)
    print(json.dumps({"total": total, "items": [item.model_dump(mode="json") for item in items]}, ensure_ascii=False, indent=2))


async def detail_preview(args: argparse.Namespace) -> None:
    crawler = ProcedureCrawler(get_settings())
    group = ProcedureGroup(args.group)
    if args.source_id:
        summary = await crawler.find_summary_by_source_id(group, args.source_id)
    else:
        items, _total = await crawler.preview(group, args.limit)
        summary = items[0]
    if summary is None:
        raise SystemExit(f"Cannot find source_id={args.source_id}")

    detail = await crawler.fetch_detail(summary)
    print(
        json.dumps(
            {
                "source_id": detail.source_id,
                "procedure_code": detail.procedure_code,
                "name": detail.name,
                "execution_methods": detail.execution_methods[:3],
                "execution_steps": detail.execution_steps,
                "required_documents": detail.required_documents,
                "processing_time": detail.processing_time,
                "fees": detail.fees,
                "requirements": detail.requirements,
                "legal_basis": detail.legal_basis,
                "attachments": detail.attachments[:5],
                "raw_detail_keys": list(detail.raw_detail.keys()),
                "content_hash": detail.content_hash,
                "source_url": detail.source_url,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


async def sync_group(args: argparse.Namespace) -> None:
    service = ProcedureSyncService(get_settings())
    max_items = None if args.full else args.max_items

    def progress(stats) -> None:
        print(
            "[sync] "
            f"seen={stats.seen} inserted={stats.inserted} updated={stats.updated} "
            f"unchanged={stats.unchanged} failed={stats.failed}",
            flush=True,
        )

    stats = await service.sync_group(
        ProcedureGroup(args.group),
        max_items,
        mark_inactive=args.mark_inactive,
        progress_every=args.progress_every,
        progress_callback=progress,
    )
    print(json.dumps(stats.__dict__, ensure_ascii=False, indent=2))


async def sync_source_ids(args: argparse.Namespace) -> None:
    service = ProcedureSyncService(get_settings())
    stats = await service.sync_source_ids(ProcedureGroup(args.group), args.source_ids)
    print(json.dumps(stats.__dict__, ensure_ascii=False, indent=2))


async def vector_sync(args: argparse.Namespace) -> None:
    service = SupabaseVectorService(get_settings())
    group = None if args.group == "all" else args.group
    limit = None if args.full else args.limit
    stats = service.sync_embeddings(procedure_group=group, limit=limit, force=args.force)
    print(json.dumps(stats.__dict__, ensure_ascii=False, indent=2))


async def vector_search(args: argparse.Namespace) -> None:
    service = SupabaseVectorService(get_settings())
    group = None if args.group == "all" else args.group
    results = service.search(
        query=args.query,
        match_count=args.limit,
        filter_group=group,
        filter_target_audience=args.target_audience or None,
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))


async def vector_count(args: argparse.Namespace) -> None:
    service = SupabaseVectorService(get_settings())
    group = None if args.group == "all" else args.group
    print(json.dumps({"group": group or "all", "count": service.count(group)}, ensure_ascii=False, indent=2))


async def db_count(args: argparse.Namespace) -> None:
    repo = SupabaseRepository(get_settings())
    group = None if args.group == "all" else args.group
    print(
        json.dumps(
            {
                "group": group or "all",
                "active_only": not args.include_inactive,
                "count": repo.count_procedures(group, active_only=not args.include_inactive),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


async def llm_test(args: argparse.Namespace) -> None:
    settings = get_settings()
    client = GeminiModelClient(settings)
    text = client.generate_text(
        prompt="Trả lời đúng một câu ngắn bằng tiếng Việt: model đã sẵn sàng.",
        model=args.model or settings.gemini_chat_model,
    )
    print(json.dumps({"model": args.model or settings.gemini_chat_model, "response": text}, ensure_ascii=False, indent=2))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="hcm-govbot-api")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preview_parser = subparsers.add_parser("crawl-preview")
    preview_parser.add_argument("--group", choices=[item.value for item in ProcedureGroup], default=ProcedureGroup.administrative.value)
    preview_parser.add_argument("--limit", type=int, default=3)
    preview_parser.set_defaults(func=crawl_preview)

    detail_parser = subparsers.add_parser("detail-preview")
    detail_parser.add_argument("--group", choices=[item.value for item in ProcedureGroup], default=ProcedureGroup.administrative.value)
    detail_parser.add_argument("--source-id", default="")
    detail_parser.add_argument("--limit", type=int, default=3)
    detail_parser.set_defaults(func=detail_preview)

    sync_parser = subparsers.add_parser("sync")
    sync_parser.add_argument("--group", choices=[item.value for item in ProcedureGroup], default=ProcedureGroup.administrative.value)
    sync_parser.add_argument("--max-items", type=int, default=5)
    sync_parser.add_argument("--full", action="store_true")
    sync_parser.add_argument("--mark-inactive", action="store_true")
    sync_parser.add_argument("--skip-chroma", action="store_true", help=argparse.SUPPRESS)
    sync_parser.add_argument("--progress-every", type=int, default=25)
    sync_parser.set_defaults(func=sync_group)

    sync_ids_parser = subparsers.add_parser("sync-source-ids")
    sync_ids_parser.add_argument("--group", choices=[item.value for item in ProcedureGroup], default=ProcedureGroup.administrative.value)
    sync_ids_parser.add_argument("--skip-chroma", action="store_true", help=argparse.SUPPRESS)
    sync_ids_parser.add_argument("source_ids", nargs="+")
    sync_ids_parser.set_defaults(func=sync_source_ids)

    vector_sync_parser = subparsers.add_parser("vector-sync")
    vector_sync_parser.add_argument("--group", choices=["all", *[item.value for item in ProcedureGroup]], default="all")
    vector_sync_parser.add_argument("--limit", type=int, default=20)
    vector_sync_parser.add_argument("--full", action="store_true")
    vector_sync_parser.add_argument("--force", action="store_true")
    vector_sync_parser.set_defaults(func=vector_sync)

    vector_search_parser = subparsers.add_parser("vector-search")
    vector_search_parser.add_argument("query")
    vector_search_parser.add_argument("--group", choices=["all", *[item.value for item in ProcedureGroup]], default="all")
    vector_search_parser.add_argument("--target-audience", default="")
    vector_search_parser.add_argument("--limit", type=int, default=9)
    vector_search_parser.set_defaults(func=vector_search)

    vector_count_parser = subparsers.add_parser("vector-count")
    vector_count_parser.add_argument("--group", choices=["all", *[item.value for item in ProcedureGroup]], default="all")
    vector_count_parser.set_defaults(func=vector_count)

    count_parser = subparsers.add_parser("db-count")
    count_parser.add_argument("--group", choices=["all", *[item.value for item in ProcedureGroup]], default="all")
    count_parser.add_argument("--include-inactive", action="store_true")
    count_parser.set_defaults(func=db_count)

    llm_parser = subparsers.add_parser("llm-test")
    llm_parser.add_argument("--model", default="")
    llm_parser.set_defaults(func=llm_test)

    args = parser.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
