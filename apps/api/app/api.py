import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_optional_user_id
from app.config import get_settings
from app.crawler import ProcedureCrawler
from app.models import (
    ChatMessageRequest,
    ChatContextSummarizeRequest,
    ChatContextUpdateRequest,
    ChatResponse,
    ChatSessionDetail,
    ChatSessionListItem,
    ChatStartRequest,
    CrawlPreviewResponse,
    FilterOptionsResponse,
    LocalChatMessageRequest,
    ProcedureGroup,
    ProcedureListResponse,
    ProcedureRecord,
    StatsOverviewResponse,
    VectorSearchRequest,
    VectorSearchResponse,
)
from app.services.chat_service import ChatService
from app.services.hybrid_retrieval_service import HybridRetrievalService
from app.services.supabase_repo import SupabaseRepository

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/auth/supabase-config")
async def supabase_auth_config() -> dict[str, str]:
    settings = get_settings()
    return {
        "supabase_url": settings.supabase_url,
        "supabase_anon_key": settings.supabase_anon_key,
    }


@router.get("/crawler/preview", response_model=CrawlPreviewResponse)
async def crawler_preview(
    group: ProcedureGroup = Query(default=ProcedureGroup.administrative),
    limit: int = Query(default=5, ge=1, le=20),
) -> CrawlPreviewResponse:
    crawler = ProcedureCrawler(get_settings())
    try:
        items, total = await crawler.preview(group=group, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Cannot fetch DVCQG source: {exc}") from exc
    return CrawlPreviewResponse(group=group, total=total, items=items)


@router.get("/procedures", response_model=ProcedureListResponse)
async def list_procedures(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    group: ProcedureGroup | None = Query(default=None),
    field: str | None = Query(default=None),
    agency: str | None = Query(default=None),
    audience: str | None = Query(default=None, pattern="^(individual|business)?$"),
) -> ProcedureListResponse:
    repo = SupabaseRepository(get_settings())
    try:
        rows, total = await asyncio.to_thread(
            repo.list_procedures,
            page,
            page_size,
            q,
            group.value if group else None,
            field,
            agency,
            audience,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Cannot query Supabase procedures: {exc}") from exc
    return ProcedureListResponse(items=rows, total=total, page=page, page_size=page_size)


@router.get("/procedures/{procedure_id}", response_model=ProcedureRecord)
async def get_procedure(procedure_id: str) -> dict:
    repo = SupabaseRepository(get_settings())
    try:
        row = await asyncio.to_thread(repo.get_procedure, procedure_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Cannot query Supabase procedure detail: {exc}") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Procedure not found")
    return row


@router.get("/filters", response_model=FilterOptionsResponse)
async def get_filters() -> dict:
    repo = SupabaseRepository(get_settings())
    try:
        return await asyncio.to_thread(repo.get_filter_options)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Cannot query Supabase filters: {exc}") from exc


@router.get("/stats/overview", response_model=StatsOverviewResponse)
async def stats_overview() -> dict:
    repo = SupabaseRepository(get_settings())
    try:
        return await asyncio.to_thread(repo.stats_overview)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Cannot query Supabase stats: {exc}") from exc


@router.post("/search/vector", response_model=VectorSearchResponse)
async def vector_search(payload: VectorSearchRequest) -> dict:
    service = HybridRetrievalService(get_settings())
    try:
        chunks = await asyncio.to_thread(service.search, payload.query, payload.limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Hybrid search failed: {exc}") from exc
    by_procedure: dict[str, dict] = {}
    for chunk in chunks:
        procedure_id = chunk["procedure_id"]
        if procedure_id in by_procedure:
            continue
        by_procedure[procedure_id] = {
            "procedure_id": procedure_id,
            "procedure_code": chunk["procedure_code"],
            "procedure_group": chunk["procedure_group"],
            "name": chunk["name"],
            "field_name": chunk.get("field_name"),
            "target_audience": chunk.get("target_audience"),
            "source_url": chunk["source_url"],
            "similarity": float(chunk.get("rerank_score") or chunk.get("rrf_score") or chunk.get("dense_score") or 0),
        }
        if len(by_procedure) >= payload.limit:
            break
    items = list(by_procedure.values())
    return {"items": items}


@router.post("/chat/sessions", response_model=ChatResponse)
async def start_chat(payload: ChatStartRequest, user_id: str | None = Depends(get_optional_user_id)) -> dict:
    service = ChatService(get_settings())
    try:
        return await asyncio.to_thread(service.start_session, payload.user_type, payload.question, user_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Chat failed: {exc}") from exc


@router.get("/chat/sessions", response_model=list[ChatSessionListItem])
async def list_chat_sessions(
    limit: int = Query(default=30, ge=1, le=100),
    user_id: str | None = Depends(get_optional_user_id),
) -> list[dict]:
    repo = SupabaseRepository(get_settings())
    try:
        return await asyncio.to_thread(repo.list_chat_sessions, limit, user_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Cannot query chat sessions: {exc}") from exc


@router.get("/chat/sessions/{session_id}", response_model=ChatSessionDetail)
async def get_chat_session(session_id: str, user_id: str | None = Depends(get_optional_user_id)) -> dict:
    if not user_id:
        raise HTTPException(status_code=401, detail="Login required to read saved chat sessions")
    repo = SupabaseRepository(get_settings())
    try:
        session = await asyncio.to_thread(repo.get_chat_session, session_id, user_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Chat session not found")
        messages = await asyncio.to_thread(repo.list_chat_messages, session_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Cannot query chat session: {exc}") from exc
    return {**session, "messages": messages}


@router.post("/chat/sessions/{session_id}/messages", response_model=ChatResponse)
async def continue_chat(
    session_id: str,
    payload: ChatMessageRequest,
    user_id: str | None = Depends(get_optional_user_id),
) -> dict:
    if not user_id:
        raise HTTPException(status_code=401, detail="Login required to continue saved chat sessions")
    service = ChatService(get_settings())
    try:
        return await asyncio.to_thread(service.continue_session, session_id, payload.message, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Chat failed: {exc}") from exc


@router.patch("/chat/sessions/{session_id}/context", response_model=list)
async def update_chat_context(
    session_id: str,
    payload: ChatContextUpdateRequest,
    user_id: str | None = Depends(get_optional_user_id),
) -> list[dict]:
    if not user_id:
        raise HTTPException(status_code=401, detail="Login required to update saved chat context")
    repo = SupabaseRepository(get_settings())
    try:
        await asyncio.to_thread(repo.delete_expired_chat_sessions, user_id)
        await asyncio.to_thread(repo.update_chat_contexts, session_id, payload.procedure_context, payload.source_context, user_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Cannot update chat context: {exc}") from exc
    return payload.procedure_context


@router.post("/chat/context/summarize", response_model=dict)
async def summarize_context_procedure(payload: ChatContextSummarizeRequest) -> dict:
    service = ChatService(get_settings())
    try:
        return await asyncio.to_thread(
            service.summarize_procedure_for_context,
            payload.procedure_id,
            payload.user_type,
            payload.question,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Cannot summarize procedure: {exc}") from exc


@router.post("/chat/local/messages", response_model=ChatResponse)
async def continue_local_chat(payload: LocalChatMessageRequest) -> dict:
    service = ChatService(get_settings())
    try:
        return await asyncio.to_thread(
            service.continue_local_session,
            payload.user_type,
            payload.initial_question,
            payload.message,
            payload.procedure_context,
            payload.source_context,
            payload.history,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Chat failed: {exc}") from exc
