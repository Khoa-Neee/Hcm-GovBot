import time
import uuid
from typing import Any

from app.config import Settings
from app.services.chat_routing_service import ChatRoutingService
from app.services.context_packing_service import ContextPackingService
from app.services.gemini_client import GeminiModelClient
from app.services.hybrid_retrieval_service import HybridRetrievalService
from app.services.supabase_repo import SupabaseRepository


class ChatService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.repo = SupabaseRepository(settings)
        self.retrieval = HybridRetrievalService(settings)
        self.router = ChatRoutingService(settings)
        self.packer = ContextPackingService()
        self.gemini = GeminiModelClient(settings)

    def start_session(self, user_type: str, question: str, user_id: str | None = None) -> dict[str, Any]:
        started_at = time.perf_counter()
        self.repo.delete_expired_chat_sessions(user_id)
        result = self._answer_with_retrieval(user_type=user_type, question=question, history=[], previous_sources=[])
        inference_seconds = round(time.perf_counter() - started_at, 2)

        expires_at = None
        if user_id:
            session_id = self.repo.create_chat_session(
                user_type,
                question,
                result["procedures"],
                user_id,
                source_context=result["sources"],
            )
            self.repo.add_chat_message(session_id, "user", question, {"user_type": user_type})
            self.repo.add_chat_message(
                session_id,
                "assistant",
                result["answer"],
                {
                    "procedures": result["procedures"],
                    "sources": result["sources"],
                    "route": result["route"],
                    "query": result["query"],
                    "inference_seconds": inference_seconds,
                },
            )
            session = self.repo.get_chat_session(session_id, user_id)
            expires_at = session.get("expires_at") if session else None
        else:
            session_id = f"local:{uuid.uuid4()}"

        return {
            "session_id": session_id,
            "answer": result["answer"],
            "procedures": result["procedures"],
            "sources": result["sources"],
            "inference_seconds": inference_seconds,
            "expires_at": expires_at,
        }

    def continue_session(self, session_id: str, message: str, user_id: str | None = None) -> dict[str, Any]:
        started_at = time.perf_counter()
        self.repo.delete_expired_chat_sessions(user_id)
        session = self.repo.get_chat_session(session_id, user_id)
        if session is None:
            raise ValueError("Chat session not found")

        messages = self.repo.list_chat_messages(session_id)
        history = [
            {"role": item.get("role"), "content": item.get("content")}
            for item in messages
            if item.get("role") in {"user", "assistant"}
        ]
        result = self._answer_with_retrieval(
            user_type=session.get("user_type") or "individual",
            question=message,
            history=history,
            previous_sources=session.get("source_context") or [],
        )
        inference_seconds = round(time.perf_counter() - started_at, 2)
        self.repo.update_chat_contexts(session_id, result["procedures"], result["sources"], user_id)
        self.repo.add_chat_message(session_id, "user", message)
        self.repo.add_chat_message(
            session_id,
            "assistant",
            result["answer"],
            {
                "procedures": result["procedures"],
                "sources": result["sources"],
                "route": result["route"],
                "query": result["query"],
                "inference_seconds": inference_seconds,
            },
        )
        refreshed = self.repo.get_chat_session(session_id, user_id)
        return {
            "session_id": session_id,
            "answer": result["answer"],
            "procedures": result["procedures"],
            "sources": result["sources"],
            "inference_seconds": inference_seconds,
            "expires_at": refreshed.get("expires_at") if refreshed else None,
        }

    def continue_local_session(
        self,
        user_type: str,
        initial_question: str,
        message: str,
        procedure_context: list[dict[str, Any]],
        source_context: list[dict[str, Any]] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        chat_history = history or [{"role": "user", "content": initial_question}]
        result = self._answer_with_retrieval(
            user_type=user_type,
            question=message,
            history=chat_history,
            previous_sources=source_context or [],
        )
        return {
            "session_id": f"local:{uuid.uuid4()}",
            "answer": result["answer"],
            "procedures": result["procedures"],
            "sources": result["sources"],
            "inference_seconds": round(time.perf_counter() - started_at, 2),
            "expires_at": None,
        }

    def summarize_procedure_for_context(self, procedure_id: str, user_type: str, question: str) -> dict[str, Any]:
        procedure = self.repo.get_procedure(procedure_id)
        if procedure is None:
            raise ValueError("Procedure not found")
        return {
            "procedure_id": procedure["id"],
            "procedure_code": procedure["procedure_code"],
            "procedure_group": procedure["procedure_group"],
            "name": procedure["name"],
            "source_url": procedure["source_url"],
            "field_name": procedure.get("field_name"),
            "target_audience": procedure.get("target_audience"),
            "summary": self._procedure_summary_text(procedure),
        }

    def _answer_with_retrieval(
        self,
        user_type: str,
        question: str,
        history: list[dict[str, Any]],
        previous_sources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        route = self.router.route(question, history, previous_sources)
        query = route["query"]
        chunks = self.retrieval.search(query, self.settings.retrieval_final_top_k)
        if not chunks:
            return {
                "answer": (
                    "Mình chưa tìm thấy đoạn dữ liệu phù hợp trong kho thủ tục. "
                    "Bạn có thể mô tả rõ hơn nhu cầu hoặc kiểm tra lại bước build chunks/Pinecone."
                ),
                "procedures": [],
                "sources": [],
                "route": route["route"],
                "query": query,
            }

        context_text, sources = self.packer.pack(chunks)
        procedures = self.packer.procedures_from_sources(sources)
        answer = self._compose_answer(user_type, question, query, history, context_text, route)
        return {
            "answer": answer,
            "procedures": procedures,
            "sources": sources,
            "route": route["route"],
            "query": query,
        }

    def _compose_answer(
        self,
        user_type: str,
        question: str,
        query: str,
        history: list[dict[str, Any]],
        context_text: str,
        route: dict[str, str],
    ) -> str:
        history_text = self.router.short_history(history)
        prompt = f"""
Ban la tro ly thu tuc hanh chinh TP.HCM.
Nguoi dung la: {self._user_type_label(user_type)}
Cau hoi moi: {question}
Truy van retrieval da dung: {query}
Loai cau hoi: {route.get("route")}

Lich su ngan:
{history_text or "Chua co"}

Context da retrieve va rerank:
{context_text}

Yeu cau:
- Chi tra loi dua tren context, khong bia them.
- Tra loi truc tiep dung pham vi cau hoi; khong tom tat/toan bo thu tuc neu nguoi dung chi hoi mot muc.
- Neu thieu thong tin, noi ro du lieu hien co chua thay.
- Khi dung thong tin tu context, dan citation dang [C1], [C2].
- Neu context co bang markdown va can thiet, co the giu bang markdown trong cau tra loi.
- Luon neu ma thu tuc va nguon khi tra loi ve thu tuc cu the.
"""
        return self.gemini.generate_text(prompt).strip()

    def _procedure_summary_text(self, procedure: dict[str, Any]) -> str:
        pieces = [
            f"Co quan thuc hien: {procedure.get('implementation_agency') or 'chua co du lieu'}",
            f"Thoi han: {procedure.get('processing_time') or 'chua co du lieu'}",
            f"Phi/le phi: {procedure.get('fees') or 'chua co du lieu'}",
            f"Nguon: {procedure.get('source_url')}",
        ]
        return "\n".join(pieces)

    def _user_type_label(self, user_type: str) -> str:
        return "ca nhan" if user_type == "individual" else "doanh nghiep/to chuc"
