from typing import Any
from datetime import datetime, timedelta, timezone

from supabase import Client, create_client

from app.config import Settings
from app.models import ProcedureDetail


class SupabaseRepository:
    CHAT_RETENTION_DAYS = 7

    def __init__(self, settings: Settings):
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
        self.client: Client = create_client(settings.supabase_url, settings.supabase_service_role_key)

    def create_crawl_run(self, procedure_group: str, metadata: dict[str, Any] | None = None) -> str:
        response = (
            self.client.table("crawl_runs")
            .insert(
                {
                    "source_name": "dvcqg",
                    "procedure_group": procedure_group,
                    "status": "running",
                    "metadata": metadata or {},
                }
            )
            .execute()
        )
        return response.data[0]["id"]

    def finish_crawl_run(
        self,
        run_id: str,
        status: str,
        total_seen: int,
        inserted_count: int,
        updated_count: int,
        unchanged_count: int,
        inactivated_count: int,
        error_message: str | None = None,
    ) -> None:
        self.client.table("crawl_runs").update(
            {
                "status": status,
                "finished_at": self._now(),
                "total_seen": total_seen,
                "inserted_count": inserted_count,
                "updated_count": updated_count,
                "unchanged_count": unchanged_count,
                "inactivated_count": inactivated_count,
                "error_message": error_message,
            }
        ).eq("id", run_id).execute()

    def get_existing_procedure(self, procedure_code: str, procedure_group: str) -> dict[str, Any] | None:
        response = (
            self.client.table("procedures")
            .select("id,procedure_code,procedure_group,content_hash,is_active")
            .eq("procedure_code", procedure_code)
            .eq("procedure_group", procedure_group)
            .maybe_single()
            .execute()
        )
        return response.data if response is not None else None

    def upsert_procedure(self, procedure: ProcedureDetail) -> tuple[str, dict[str, Any]]:
        existing = self.get_existing_procedure(procedure.procedure_code, procedure.procedure_group.value)
        payload = {
            "source_id": procedure.source_id,
            "procedure_code": procedure.procedure_code,
            "procedure_group": procedure.procedure_group.value,
            "name": procedure.name,
            "target_audience": procedure.target_audience,
            "field_name": procedure.field_name,
            "published_agency": procedure.published_agency,
            "implementation_agency": procedure.implementation_agency,
            "implementation_level": procedure.implementation_level,
            "execution_methods": procedure.execution_methods,
            "execution_steps": procedure.execution_steps,
            "required_documents": procedure.required_documents,
            "processing_time": procedure.processing_time,
            "fees": procedure.fees,
            "requirements": procedure.requirements,
            "legal_basis": procedure.legal_basis,
            "attachments": procedure.attachments,
            "related_procedures": procedure.related_procedures,
            "source_url": procedure.source_url,
            "raw_summary": procedure.raw_summary,
            "raw_detail": procedure.raw_detail,
            "content_hash": procedure.content_hash,
            "is_active": True,
            "last_seen_at": self._now(),
        }
        response = (
            self.client.table("procedures")
            .upsert(payload, on_conflict="procedure_code,procedure_group")
            .execute()
        )
        saved = response.data[0] if response.data else payload

        if existing is None:
            action = "inserted"
            self.insert_procedure_version(saved, procedure)
        elif existing.get("content_hash") != procedure.content_hash or not existing.get("is_active", True):
            action = "updated"
            self.insert_procedure_version(saved, procedure)
        else:
            action = "unchanged"

        return action, saved

    def insert_procedure_version(self, saved: dict[str, Any], procedure: ProcedureDetail) -> None:
        self.client.table("procedure_versions").insert(
            {
                "procedure_id": saved.get("id"),
                "procedure_code": procedure.procedure_code,
                "procedure_group": procedure.procedure_group.value,
                "content_hash": procedure.content_hash,
                "payload": procedure.model_dump(mode="json"),
            }
        ).execute()

    def mark_inactive_missing(self, procedure_group: str, seen_source_ids: set[str]) -> int:
        response = (
            self.client.table("procedures")
            .select("id,source_id")
            .eq("procedure_group", procedure_group)
            .eq("is_active", True)
            .execute()
        )
        rows = response.data or []
        missing_ids = [row["id"] for row in rows if str(row.get("source_id")) not in seen_source_ids]
        if not missing_ids:
            return 0

        self.client.table("procedures").update({"is_active": False}).in_("id", missing_ids).execute()
        return len(missing_ids)

    def count_procedures(self, procedure_group: str | None = None, active_only: bool = True) -> int:
        query = self.client.table("procedures").select("id", count="exact")
        if procedure_group:
            query = query.eq("procedure_group", procedure_group)
        if active_only:
            query = query.eq("is_active", True)
        response = query.execute()
        return response.count or 0

    def list_procedures(
        self,
        page: int = 1,
        page_size: int = 20,
        query_text: str | None = None,
        procedure_group: str | None = None,
        field_name: str | None = None,
        implementation_agency: str | None = None,
        target_audience: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        start = (page - 1) * page_size
        end = start + page_size - 1
        columns = (
            "id,source_id,procedure_code,procedure_group,name,target_audience,field_name,"
            "published_agency,implementation_agency,implementation_level,processing_time,"
            "fees,source_url,updated_at"
        )
        db_query = (
            self.client.table("procedures")
            .select(columns, count="exact")
            .eq("is_active", True)
            .order("updated_at", desc=True)
            .range(start, end)
        )
        db_query = self._apply_procedure_filters(
            db_query,
            query_text=query_text,
            procedure_group=procedure_group,
            field_name=field_name,
            implementation_agency=implementation_agency,
            target_audience=target_audience,
        )
        response = db_query.execute()
        return response.data or [], response.count or 0

    def get_procedure(self, procedure_id: str) -> dict[str, Any] | None:
        response = (
            self.client.table("procedures")
            .select("*")
            .eq("id", procedure_id)
            .eq("is_active", True)
            .maybe_single()
            .execute()
        )
        return response.data if response is not None else None

    def get_procedures_by_ids(self, procedure_ids: list[str]) -> list[dict[str, Any]]:
        if not procedure_ids:
            return []
        response = (
            self.client.table("procedures")
            .select("*")
            .in_("id", procedure_ids)
            .eq("is_active", True)
            .execute()
        )
        rows = response.data or []
        order = {procedure_id: index for index, procedure_id in enumerate(procedure_ids)}
        return sorted(rows, key=lambda row: order.get(row.get("id"), len(order)))

    def get_filter_options(self) -> dict[str, list[str]]:
        rows = self._list_all_active_procedure_rows("field_name,implementation_agency,implementation_level")
        return {
            "fields": self._sorted_unique(row.get("field_name") for row in rows),
            "agencies": self._sorted_unique(row.get("implementation_agency") for row in rows),
            "levels": self._sorted_unique(row.get("implementation_level") for row in rows),
        }

    def stats_overview(self) -> dict[str, Any]:
        rows = self._list_all_active_procedure_rows(
            "id,source_id,procedure_code,procedure_group,name,target_audience,field_name,"
            "published_agency,implementation_agency,implementation_level,processing_time,"
            "fees,source_url,updated_at"
        )
        administrative = sum(1 for row in rows if row.get("procedure_group") == "administrative")
        interlinked = sum(1 for row in rows if row.get("procedure_group") == "interlinked")
        individual = sum(1 for row in rows if self._audience_matches(row.get("target_audience"), "individual"))
        business = sum(1 for row in rows if self._audience_matches(row.get("target_audience"), "business"))
        both_or_unknown = len(rows) - len(
            [
                row
                for row in rows
                if self._audience_matches(row.get("target_audience"), "individual")
                ^ self._audience_matches(row.get("target_audience"), "business")
            ]
        )
        return {
            "total": len(rows),
            "administrative": administrative,
            "interlinked": interlinked,
            "individual": individual,
            "business": business,
            "both_or_unknown": both_or_unknown,
            "by_field": self._top_buckets(rows, "field_name", 12),
            "by_agency": self._top_buckets(rows, "implementation_agency", 12),
            "recently_updated": sorted(rows, key=lambda row: row.get("updated_at") or "", reverse=True)[:8],
        }

    def create_chat_session(
        self,
        user_type: str,
        initial_question: str,
        procedure_context: list[dict[str, Any]],
        user_id: str,
    ) -> str:
        response = (
            self.client.table("chat_sessions")
            .insert(
                {
                    "user_id": user_id,
                    "user_type": user_type,
                    "initial_question": initial_question,
                    "procedure_context": procedure_context,
                }
            )
            .execute()
        )
        return response.data[0]["id"]

    def get_chat_session(self, session_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        self.delete_expired_chat_sessions(user_id)
        query = self.client.table("chat_sessions").select("*").eq("id", session_id)
        if user_id:
            query = query.eq("user_id", user_id)
        response = (
            query
            .maybe_single()
            .execute()
        )
        return self._with_chat_expiry(response.data) if response is not None else None

    def list_chat_sessions(self, limit: int = 30, user_id: str | None = None) -> list[dict[str, Any]]:
        if not user_id:
            return []
        self.delete_expired_chat_sessions(user_id)
        response = (
            self.client.table("chat_sessions")
            .select("id,user_type,initial_question,created_at,updated_at")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [self._with_chat_expiry(row) for row in response.data or []]

    def list_chat_messages(self, session_id: str) -> list[dict[str, Any]]:
        response = (
            self.client.table("chat_messages")
            .select("id,role,content,metadata,created_at")
            .eq("session_id", session_id)
            .order("created_at", desc=False)
            .execute()
        )
        return response.data or []

    def update_chat_context(self, session_id: str, procedure_context: list[dict[str, Any]], user_id: str | None = None) -> None:
        query = self.client.table("chat_sessions").update({"procedure_context": procedure_context}).eq("id", session_id)
        if user_id:
            query = query.eq("user_id", user_id)
        query.execute()

    def add_chat_message(self, session_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        self.client.table("chat_messages").insert(
            {
                "session_id": session_id,
                "role": role,
                "content": content,
                "metadata": metadata or {},
            }
        ).execute()
        self.touch_chat_session(session_id)

    def touch_chat_session(self, session_id: str) -> None:
        self.client.table("chat_sessions").update({"updated_at": self._now()}).eq("id", session_id).execute()

    def delete_expired_chat_sessions(self, user_id: str | None = None) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.CHAT_RETENTION_DAYS)).isoformat()
        query = self.client.table("chat_sessions").delete(count="exact").lt("updated_at", cutoff)
        if user_id:
            query = query.eq("user_id", user_id)
        response = query.execute()
        return response.count or 0

    def _with_chat_expiry(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        updated_at = self._parse_datetime(row.get("updated_at"))
        if updated_at:
            row = {**row, "expires_at": (updated_at + timedelta(days=self.CHAT_RETENTION_DAYS)).isoformat()}
        return row

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _apply_procedure_filters(
        self,
        db_query: Any,
        query_text: str | None,
        procedure_group: str | None,
        field_name: str | None,
        implementation_agency: str | None,
        target_audience: str | None,
    ) -> Any:
        if procedure_group:
            db_query = db_query.eq("procedure_group", procedure_group)
        if field_name:
            db_query = db_query.eq("field_name", field_name)
        if implementation_agency:
            db_query = db_query.eq("implementation_agency", implementation_agency)
        if target_audience:
            db_query = db_query.or_(self._audience_filter(target_audience))
        if query_text:
            safe_text = query_text.replace(",", " ").strip()
            db_query = db_query.or_(f"name.ilike.%{safe_text}%,procedure_code.ilike.%{safe_text}%")
        return db_query

    def _audience_filter(self, target_audience: str) -> str:
        if target_audience == "individual":
            return "target_audience.ilike.%cá nhân%,target_audience.ilike.%ca nhan%"
        if target_audience == "business":
            return (
                "target_audience.ilike.%doanh nghiệp%,target_audience.ilike.%doanh nghiep%,"
                "target_audience.ilike.%tổ chức%,target_audience.ilike.%to chuc%"
            )
        return f"target_audience.ilike.%{target_audience}%"

    def _audience_matches(self, target_audience: str | None, audience: str) -> bool:
        text = (target_audience or "").lower()
        if audience == "individual":
            return "cá nhân" in text or "ca nhan" in text
        if audience == "business":
            return any(token in text for token in ["doanh nghiệp", "doanh nghiep", "tổ chức", "to chuc"])
        return False

    def _top_buckets(self, rows: list[dict[str, Any]], field: str, limit: int) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for row in rows:
            value = (row.get(field) or "Chưa rõ").strip()
            counts[value] = counts.get(value, 0) + 1
        return [
            {"name": name, "count": count}
            for name, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]
        ]

    def _list_all_active_procedure_rows(self, columns: str, page_size: int = 1000) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0

        while True:
            response = (
                self.client.table("procedures")
                .select(columns)
                .eq("is_active", True)
                .order("updated_at", desc=True)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            page_rows = response.data or []
            rows.extend(page_rows)
            if len(page_rows) < page_size:
                break
            offset += page_size

        return rows

    def _sorted_unique(self, values: Any) -> list[str]:
        return sorted({value.strip() for value in values if isinstance(value, str) and value.strip()})

    def list_procedures_for_embedding(
        self,
        procedure_group: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        page_size = 1000
        rows: list[dict[str, Any]] = []
        offset = 0

        while True:
            current_limit = min(page_size, limit - len(rows)) if limit is not None else page_size
            if current_limit <= 0:
                break

            query = (
                self.client.table("procedures")
                .select(
                    "id,source_id,procedure_code,procedure_group,name,target_audience,"
                    "field_name,implementation_agency,source_url,content_hash,is_active"
                )
                .eq("is_active", True)
                .order("updated_at", desc=True)
                .range(offset, offset + current_limit - 1)
            )
            if procedure_group:
                query = query.eq("procedure_group", procedure_group)

            response = query.execute()
            page_rows = response.data or []
            rows.extend(page_rows)

            if len(page_rows) < current_limit:
                break
            offset += current_limit

        return rows

    def get_embedding_by_code(self, procedure_code: str, procedure_group: str) -> dict[str, Any] | None:
        response = (
            self.client.table("procedure_embeddings")
            .select("id,procedure_code,procedure_group,content_hash,is_active")
            .eq("procedure_code", procedure_code)
            .eq("procedure_group", procedure_group)
            .maybe_single()
            .execute()
        )
        return response.data if response is not None else None

    def upsert_procedure_embedding(self, procedure: dict[str, Any], embedding: list[float], embedding_model: str, embedding_dim: int) -> str:
        existing = self.get_embedding_by_code(procedure["procedure_code"], procedure["procedure_group"])
        payload = {
            "procedure_id": procedure["id"],
            "procedure_code": procedure["procedure_code"],
            "procedure_group": procedure["procedure_group"],
            "name": procedure["name"],
            "field_name": procedure.get("field_name"),
            "target_audience": procedure.get("target_audience"),
            "source_url": procedure["source_url"],
            "embedding_model": embedding_model,
            "embedding_dim": embedding_dim,
            "embedding": embedding,
            "content_hash": procedure["content_hash"],
            "is_active": bool(procedure.get("is_active", True)),
        }
        self.client.table("procedure_embeddings").upsert(
            payload,
            on_conflict="procedure_code,procedure_group",
        ).execute()

        if existing is None:
            return "inserted"
        if existing.get("content_hash") != procedure["content_hash"] or not existing.get("is_active", True):
            return "updated"
        return "unchanged"

    def match_procedure_embeddings(
        self,
        query_embedding: list[float],
        match_count: int = 9,
        filter_group: str | None = None,
        filter_target_audience: str | None = None,
    ) -> list[dict[str, Any]]:
        response = self.client.rpc(
            "match_procedure_embeddings",
            {
                "query_embedding": query_embedding,
                "match_count": match_count,
                "filter_group": filter_group,
                "filter_target_audience": filter_target_audience,
            },
        ).execute()
        return response.data or []

    def count_procedure_embeddings(self, procedure_group: str | None = None, active_only: bool = True) -> int:
        query = self.client.table("procedure_embeddings").select("id", count="exact")
        if procedure_group:
            query = query.eq("procedure_group", procedure_group)
        if active_only:
            query = query.eq("is_active", True)
        response = query.execute()
        return response.count or 0

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
