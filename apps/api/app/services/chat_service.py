import json
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.config import Settings
from app.services.gemini_client import GeminiModelClient
from app.services.supabase_repo import SupabaseRepository
from app.services.supabase_vector_service import SupabaseVectorService


class ChatService:
    CONTEXT_LIMIT = 3

    def __init__(self, settings: Settings):
        self.settings = settings
        self.repo = SupabaseRepository(settings)
        self.vector = SupabaseVectorService(settings)
        self.gemini = GeminiModelClient(settings)

    def start_session(self, user_type: str, question: str, user_id: str | None = None) -> dict[str, Any]:
        started_at = time.perf_counter()
        self.repo.delete_expired_chat_sessions(user_id)
        guessed_names = self._guess_procedure_names(user_type, question)
        candidates = self._retrieve_candidates(question, guessed_names)
        details = self.repo.get_procedures_by_ids([item["procedure_id"] for item in candidates])
        summaries = self._summarize_many(user_type, question, details)
        answer = self._compose_initial_answer(user_type, question, summaries)
        inference_seconds = round(time.perf_counter() - started_at, 2)

        expires_at = None
        if user_id:
            session_id = self.repo.create_chat_session(user_type, question, summaries, user_id)
            self.repo.add_chat_message(session_id, "user", question, {"user_type": user_type})
            self.repo.add_chat_message(session_id, "assistant", answer, {"procedures": summaries, "inference_seconds": inference_seconds})
            session = self.repo.get_chat_session(session_id, user_id)
            expires_at = session.get("expires_at") if session else None
        else:
            session_id = f"local:{uuid.uuid4()}"

        return {"session_id": session_id, "answer": answer, "procedures": summaries, "inference_seconds": inference_seconds, "expires_at": expires_at}

    def continue_session(self, session_id: str, message: str, user_id: str | None = None) -> dict[str, Any]:
        started_at = time.perf_counter()
        self.repo.delete_expired_chat_sessions(user_id)
        session = self.repo.get_chat_session(session_id, user_id)
        if session is None:
            raise ValueError("Chat session not found")

        context = (session.get("procedure_context") or [])[: self.CONTEXT_LIMIT]
        answer = self._answer_from_context(
            user_type=session.get("user_type") or "individual",
            initial_question=session.get("initial_question") or "",
            message=message,
            context=context,
        )
        inference_seconds = round(time.perf_counter() - started_at, 2)
        self.repo.add_chat_message(session_id, "user", message)
        self.repo.add_chat_message(session_id, "assistant", answer, {"procedures": context, "inference_seconds": inference_seconds})
        refreshed = self.repo.get_chat_session(session_id, user_id)
        return {
            "session_id": session_id,
            "answer": answer,
            "procedures": context,
            "inference_seconds": inference_seconds,
            "expires_at": refreshed.get("expires_at") if refreshed else None,
        }

    def continue_local_session(
        self,
        user_type: str,
        initial_question: str,
        message: str,
        procedure_context: list[dict[str, Any]],
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        procedure_context = procedure_context[: self.CONTEXT_LIMIT]
        answer = self._answer_from_context(
            user_type=user_type,
            initial_question=initial_question,
            message=message,
            context=procedure_context,
        )
        return {
            "session_id": f"local:{uuid.uuid4()}",
            "answer": answer,
            "procedures": procedure_context,
            "inference_seconds": round(time.perf_counter() - started_at, 2),
            "expires_at": None,
        }

    def summarize_procedure_for_context(self, procedure_id: str, user_type: str, question: str) -> dict[str, Any]:
        procedure = self.repo.get_procedure(procedure_id)
        if procedure is None:
            raise ValueError("Procedure not found")
        try:
            return self._summarize_one(user_type, question, procedure, 0)
        except Exception:
            return self._fallback_summary(procedure)

    def _guess_procedure_names(self, user_type: str, question: str) -> list[str]:
        prompt = f"""
Bạn là trợ lý phân loại thủ tục hành chính cho người dân TP.HCM.
Người dùng là: {self._user_type_label(user_type)}.
Câu hỏi: {question}

Hãy suy luận tối đa 3 tên thủ tục hành chính có khả năng liên quan nhất.
Chỉ trả về JSON array string, không markdown, ví dụ:
["Tên thủ tục 1", "Tên thủ tục 2"]
"""
        try:
            text = self.gemini.generate_text(prompt)
            parsed = self._parse_json_array(text)
            return [item.strip() for item in parsed if isinstance(item, str) and item.strip()][:3]
        except Exception:
            return [question]

    def _retrieve_candidates(self, question: str, guessed_names: list[str]) -> list[dict[str, Any]]:
        candidates_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        queries = guessed_names[:3] if guessed_names else [question]
        max_workers = min(len(queries), max(1, len(self.settings.gemini_api_keys)), 3)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(
                    self.vector.search,
                    f"{guessed_name}\nNgữ cảnh người dùng: {question}",
                    2,
                    None,
                    None,
                    index,
                ): guessed_name
                for index, guessed_name in enumerate(queries)
            }
            for future in as_completed(future_map):
                try:
                    results = future.result()
                except Exception:
                    continue
                for result in results:
                    key = (result["procedure_code"], result["procedure_group"])
                    similarity = float(result.get("similarity") or 0)
                    existing = candidates_by_key.get(key)
                    if existing is not None and float(existing.get("similarity") or 0) >= similarity:
                        continue
                    candidates_by_key[key] = result

        ranked = sorted(
            candidates_by_key.values(),
            key=lambda item: float(item.get("similarity") or 0),
            reverse=True,
        )
        return ranked[: self.CONTEXT_LIMIT]

    def _summarize_many(self, user_type: str, question: str, procedures: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not procedures:
            return []

        summaries: list[dict[str, Any]] = []
        procedures = procedures[: self.CONTEXT_LIMIT]
        max_workers = min(len(procedures), max(1, len(self.settings.gemini_api_keys)), self.CONTEXT_LIMIT)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(self._summarize_one, user_type, question, procedure, index): procedure
                for index, procedure in enumerate(procedures)
            }
            for future in as_completed(future_map):
                procedure = future_map[future]
                try:
                    summary = future.result()
                except Exception:
                    summary = self._fallback_summary(procedure)
                summaries.append(summary)

        order = {procedure["id"]: index for index, procedure in enumerate(procedures)}
        return sorted(summaries, key=lambda item: order.get(item["procedure_id"], len(order)))

    def _summarize_one(self, user_type: str, question: str, procedure: dict[str, Any], key_index: int) -> dict[str, Any]:
        prompt = f"""
Bạn là trợ lý thủ tục hành chính TP.HCM. Đọc thủ tục sau và rút ra phần liên quan trực tiếp đến câu hỏi của người dùng.

Người dùng là: {self._user_type_label(user_type)}
Câu hỏi: {question}

Dữ liệu thủ tục:
{self._procedure_context_text(procedure)}

Yêu cầu:
- Viết tiếng Việt dễ hiểu.
- Không bịa thông tin ngoài dữ liệu.
- Nếu dữ liệu thiếu, nói rõ chưa tìm thấy thông tin chính xác.
- Ưu tiên hồ sơ cần chuẩn bị, nơi nộp/cơ quan thực hiện, thời hạn, phí/lệ phí và cách nộp nếu câu hỏi cần.
- Không dùng tiêu đề markdown cấp lớn. Chỉ trả về các ý ngắn, có mã thủ tục và link nguồn.
"""
        summary = self.gemini.generate_text(prompt, key_index=key_index)
        return {
            "procedure_id": procedure["id"],
            "procedure_code": procedure["procedure_code"],
            "procedure_group": procedure["procedure_group"],
            "name": procedure["name"],
            "source_url": procedure["source_url"],
            "field_name": procedure.get("field_name"),
            "target_audience": procedure.get("target_audience"),
            "summary": summary.strip(),
        }

    def _compose_initial_answer(self, user_type: str, question: str, summaries: list[dict[str, Any]]) -> str:
        if not summaries:
            return (
                "Mình chưa tìm thấy thông tin chính xác về thủ tục phù hợp trong dữ liệu TP.HCM. "
                "Bạn có thể mô tả rõ hơn nhu cầu, ví dụ lĩnh vực, cơ quan thực hiện hoặc kết quả mong muốn."
            )

        context = "\n\n".join(f"- {item['name']} ({item['procedure_code']})\n{item['summary']}" for item in summaries[: self.CONTEXT_LIMIT])
        prompt = f"""
Người dùng là {self._user_type_label(user_type)} và hỏi: {question}

Dưới đây là tối đa 3 thủ tục gần nhất đã được tìm và tóm tắt từ dữ liệu thật:
{context}

Hãy trả lời trực tiếp câu hỏi của người dùng, không liệt kê/tổng hợp toàn bộ thủ tục phù hợp.
Nếu một thủ tục phù hợp rõ nhất, hãy dùng thủ tục đó làm câu trả lời chính.
Nếu dữ liệu cho thấy có thể nhầm giữa nhiều trường hợp, chỉ nhắc ngắn gọn điều kiện phân biệt và hỏi lại đúng một câu.
Format:
- Mở đầu bằng câu trả lời cụ thể.
- Sau đó là các ý cần làm/giấy tờ/thời hạn/phí/cơ quan nếu có.
- Luôn kèm mã thủ tục và link nguồn của thủ tục đang dùng.
- Không bịa thông tin ngoài dữ liệu.
"""
        try:
            return self.gemini.generate_text(prompt).strip()
        except Exception:
            return self._compose_direct_fallback_answer(summaries)

    def _answer_from_context(self, user_type: str, initial_question: str, message: str, context: list[dict[str, Any]]) -> str:
        if not context:
            return (
                "Phiên chat này chưa có thủ tục nào trong context. "
                "Bạn có muốn bắt đầu tìm thủ tục khác bằng cách mô tả lại nhu cầu không?"
            )

        context_text = "\n\n".join(
            f"- {item.get('name')} ({item.get('procedure_code')}): {item.get('summary')}\nNguồn: {item.get('source_url')}"
            for item in context
        )
        prompt = f"""
Bạn là trợ lý thủ tục hành chính TP.HCM.
Người dùng là: {self._user_type_label(user_type)}
Câu hỏi ban đầu: {initial_question}
Câu hỏi mới: {message}

Chỉ dùng context thủ tục dưới đây để trả lời:
{context_text}

Nếu câu hỏi mới vượt khỏi context, hãy nói: "Nội dung này có vẻ nằm ngoài các thủ tục đang xét. Bạn có muốn mình tìm thủ tục khác không?"
Không bịa thông tin. Luôn kèm mã thủ tục và link nguồn nếu trả lời về thủ tục cụ thể.
"""
        try:
            return self.gemini.generate_text(prompt).strip()
        except Exception:
            return self._compose_direct_fallback_answer(context)

    def _procedure_context_text(self, procedure: dict[str, Any]) -> str:
        fields = [
            ("Tên", procedure.get("name")),
            ("Mã thủ tục", procedure.get("procedure_code")),
            ("Nhóm", procedure.get("procedure_group")),
            ("Đối tượng", procedure.get("target_audience")),
            ("Lĩnh vực", procedure.get("field_name")),
            ("Cơ quan thực hiện", procedure.get("implementation_agency")),
            ("Cấp thực hiện", procedure.get("implementation_level")),
            ("Cách thức thực hiện", json.dumps(procedure.get("execution_methods") or [], ensure_ascii=False)),
            ("Thời hạn", procedure.get("processing_time")),
            ("Phí/lệ phí", procedure.get("fees")),
            ("Hồ sơ", procedure.get("required_documents")),
            ("Trình tự", procedure.get("execution_steps")),
            ("Yêu cầu điều kiện", procedure.get("requirements")),
            ("Căn cứ pháp lý", procedure.get("legal_basis")),
            ("Link nguồn", procedure.get("source_url")),
        ]
        text = "\n".join(f"{label}: {value or 'Chưa có dữ liệu'}" for label, value in fields)
        return text[:12000]

    def _fallback_summary(self, procedure: dict[str, Any]) -> dict[str, Any]:
        pieces = [
            f"Mã thủ tục: {procedure.get('procedure_code')}",
            f"Cơ quan thực hiện: {procedure.get('implementation_agency') or 'chưa có dữ liệu'}",
            f"Thời hạn: {procedure.get('processing_time') or 'chưa có dữ liệu'}",
            f"Phí/lệ phí: {procedure.get('fees') or 'chưa có dữ liệu'}",
            f"Nguồn: {procedure.get('source_url')}",
        ]
        return {
            "procedure_id": procedure["id"],
            "procedure_code": procedure["procedure_code"],
            "procedure_group": procedure["procedure_group"],
            "name": procedure["name"],
            "source_url": procedure["source_url"],
            "field_name": procedure.get("field_name"),
            "target_audience": procedure.get("target_audience"),
            "summary": "\n".join(pieces),
        }

    def _compose_fallback_answer(self, summaries: list[dict[str, Any]]) -> str:
        if not summaries:
            return (
                "Mình chưa tìm thấy thông tin chính xác trong dữ liệu hiện có. "
                "Bạn có thể mô tả rõ hơn nhu cầu hoặc thử tìm bằng tên/mã thủ tục."
            )

        lines = [
            "Mình tìm thấy các thủ tục phù hợp nhất:",
        ]
        for index, item in enumerate(summaries[:5], start=1):
            lines.append(
                f"{index}. **{item.get('name')}**\n"
                f"   - Mã thủ tục: {item.get('procedure_code')}\n"
                f"   - Tóm tắt: {item.get('summary')}\n"
                f"   - Link nguồn: {item.get('source_url')}"
            )
        lines.append("Bạn có thể hỏi tiếp về hồ sơ, phí/lệ phí hoặc cách nộp của thủ tục bạn chọn.")
        return "\n\n".join(lines)

    def _compose_direct_fallback_answer(self, summaries: list[dict[str, Any]]) -> str:
        if not summaries:
            return (
                "Mình chưa tìm thấy thông tin chính xác trong dữ liệu hiện có. "
                "Bạn mô tả rõ hơn nhu cầu, lĩnh vực hoặc cơ quan thực hiện để mình tìm đúng thủ tục nhé."
            )

        item = summaries[0]
        return (
            f"Với câu hỏi này, thủ tục phù hợp nhất là **{item.get('name')}**.\n\n"
            f"- Mã thủ tục: {item.get('procedure_code')}\n"
            f"- Thông tin cần chú ý: {item.get('summary')}\n"
            f"- Link nguồn: {item.get('source_url')}"
        )

    def _parse_json_array(self, text: str) -> list[Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        match = re.search(r"\[[\s\S]*\]", cleaned)
        if match:
            cleaned = match.group(0)
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, list) else []

    def _user_type_label(self, user_type: str) -> str:
        return "cá nhân" if user_type == "individual" else "doanh nghiệp/tổ chức"
