import json
import re
from typing import Any

from app.config import Settings
from app.services.gemini_client import GeminiModelClient


class ChatRoutingService:
    FOLLOW_UP_HINTS = {
        "phi",
        "le phi",
        "bao nhieu",
        "giay to",
        "ho so",
        "nop o dau",
        "thoi han",
        "mat bao lau",
        "can gi",
        "co quan",
        "dieu kien",
    }

    def __init__(self, settings: Settings):
        self.settings = settings
        self.gemini = GeminiModelClient(settings)

    def route(self, question: str, history: list[dict[str, Any]], previous_sources: list[dict[str, Any]]) -> dict[str, str]:
        if not history:
            return {"route": "new_topic", "query": question, "reason": "first_message"}

        if not self.settings.chat_rewrite_when_ambiguous:
            return {"route": "new_topic", "query": question, "reason": "rewrite_disabled"}

        if self._looks_like_follow_up(question):
            return {"route": "follow_up", "query": self._rewrite(question, history, previous_sources), "reason": "heuristic"}

        try:
            prompt = self._route_prompt(question, history, previous_sources)
            text = self.gemini.generate_text(prompt)
            parsed = self._parse_json(text)
            route = parsed.get("route") if parsed.get("route") in {"follow_up", "new_topic"} else "new_topic"
            query = str(parsed.get("query") or question).strip()
            return {"route": route, "query": query or question, "reason": "llm"}
        except Exception:
            return {"route": "new_topic", "query": question, "reason": "fallback"}

    def short_history(self, messages: list[dict[str, Any]], limit: int = 6) -> str:
        recent = messages[-limit:]
        return "\n".join(f"{item.get('role')}: {item.get('content')}" for item in recent)

    def _looks_like_follow_up(self, question: str) -> bool:
        normalized = self._normalize(question)
        if len(normalized.split()) <= 6:
            return True
        return any(hint in normalized for hint in self.FOLLOW_UP_HINTS)

    def _rewrite(self, question: str, history: list[dict[str, Any]], previous_sources: list[dict[str, Any]]) -> str:
        source_names = ", ".join({source.get("name", "") for source in previous_sources if source.get("name")})
        prompt = f"""
Viet lai cau hoi tiep theo thanh mot truy van tim kiem day du bang tieng Viet.

Lich su ngan:
{self.short_history(history)}

Nguon/thu tuc dang noi toi: {source_names or "chua ro"}
Cau hoi moi: {question}

Chi tra ve mot cau truy van, khong markdown.
"""
        try:
            return self.gemini.generate_text(prompt).strip() or question
        except Exception:
            return question

    def _route_prompt(self, question: str, history: list[dict[str, Any]], previous_sources: list[dict[str, Any]]) -> str:
        source_names = ", ".join({source.get("name", "") for source in previous_sources if source.get("name")})
        return f"""
Phan loai cau hoi moi trong chatbot thu tuc hanh chinh.

Lich su ngan:
{self.short_history(history)}

Thu tuc/context truoc: {source_names or "chua co"}
Cau hoi moi: {question}

Neu cau hoi phu thuoc ngu canh truoc, route = "follow_up" va viet lai query day du.
Neu nguoi dung doi sang nhu cau/thu tuc khac, route = "new_topic" va query la cau hoi moi.

Chi tra JSON:
{{"route":"follow_up|new_topic","query":"..."}}
"""

    def _parse_json(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        match = re.search(r"\{[\s\S]*\}", cleaned)
        return json.loads(match.group(0) if match else cleaned)

    def _normalize(self, text: str) -> str:
        text = text.lower()
        replacements = {
            "ệ": "e",
            "í": "i",
            "ờ": "o",
            "ồ": "o",
            "ắ": "a",
            "ầ": "a",
            "ộ": "o",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text
