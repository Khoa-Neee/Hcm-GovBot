import asyncio
import hashlib
import json
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.config import Settings
from app.models import ProcedureDetail, ProcedureGroup, ProcedureSummary


class DvcClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.rest_url = urljoin(settings.dvc_base_url, settings.dvc_rest_path)
        self._download_base_url: str | None = None
        self.headers = {
            "User-Agent": "Mozilla/5.0 HCM-GovBot/0.1 (+local crawler)",
            "Accept": "application/json,text/html,*/*",
        }

    async def post_rest(self, payload: dict[str, Any]) -> Any:
        response = await self._request_with_retries(
            "POST",
            self.rest_url,
            data={"params": json.dumps(payload, ensure_ascii=False)},
        )
        return response.json()

    async def search_procedures(
        self,
        group: ProcedureGroup,
        page_index: int = 1,
        record_per_page: int = 100,
    ) -> tuple[list[ProcedureSummary], int]:
        payload = {
            "service": "procedure_advanced_search_service_v2",
            "provider": "dvcquocgia",
            "type": "ref",
            "recordPerPage": record_per_page,
            "pageIndex": page_index,
            "is_connected": 1 if group == ProcedureGroup.interlinked else 0,
            "keyword": "",
            "agency_type": "1",
            "impl_agency_id": self.settings.dvc_hcmc_agency_id,
            "object_id": "-1",
            "field_id": "-1",
            "impl_level_id": "-1",
        }
        rows = await self.post_rest(payload)
        if not rows:
            return [], 0

        total = int(rows[0].get("AMOUNT") or 0)
        items = [self._summary_from_row(row, group) for row in rows]
        return items, total

    async def fetch_detail(self, summary: ProcedureSummary) -> ProcedureDetail:
        html = await self._fetch_detail_html(summary)
        soup = BeautifulSoup(html, "html.parser")

        execution_methods = self._parse_execution_methods(soup)
        detail_text = self._parse_detail_modal(soup)
        modal_fields = self._parse_modal_fields(soup)
        parent_id = self._parse_parent_id(html)
        impl_orders = await self._fetch_impl_orders(summary.source_id, parent_id)
        requires = await self._fetch_requires(summary.source_id, parent_id)
        related = await self._fetch_related(summary.source_id)
        download_base_url = await self._fetch_download_base_url()
        documents = self._parse_required_documents(soup, download_base_url)
        attachments = self._attachments_from_documents(documents)
        export_url = self._parse_export_url(soup)
        if export_url:
            attachments.append(
                {
                    "title": "Tải xuống chi tiết thủ tục",
                    "file_url": export_url,
                    "file_type": "word",
                    "source_payload": {"kind": "procedure_detail_export"},
                }
            )

        raw_detail = {
            "detail_text": detail_text,
            "modal_fields": modal_fields,
            "execution_methods": execution_methods,
            "parent_id": parent_id,
            "impl_orders": impl_orders,
            "requires": requires,
            "documents": documents,
        }
        content_hash = self._hash_payload(
            {
                "summary": summary.model_dump(mode="json"),
                "detail": raw_detail,
                "related": related,
            }
        )

        return ProcedureDetail(
            **summary.model_dump(),
            target_audience=modal_fields.get("Đối tượng thực hiện"),
            implementation_level=modal_fields.get("Cấp thực hiện"),
            execution_methods=execution_methods,
            execution_steps=self._format_impl_orders(impl_orders) or modal_fields.get("Trình tự thực hiện"),
            required_documents=self._format_required_documents(documents) or modal_fields.get("Thành phần hồ sơ"),
            processing_time=self._summarize_column(execution_methods, "processing_time"),
            fees=self._summarize_column(execution_methods, "fees"),
            requirements=self._format_requires(requires) or modal_fields.get("Yêu cầu, điều kiện thực hiện") or modal_fields.get("Yêu cầu, điều kiện"),
            legal_basis=modal_fields.get("Căn cứ pháp lý"),
            attachments=attachments,
            related_procedures=related,
            raw_detail=raw_detail,
            content_hash=content_hash,
        )

    async def _fetch_detail_html(self, summary: ProcedureSummary) -> str:
        if summary.procedure_group == ProcedureGroup.interlinked:
            path = f"/p/home/dvc-tthc-thu-tuc-hanh-chinh-lien-thong-chi-tiet.html?ma_thu_tuc={summary.source_id}"
        else:
            path = f"/p/home/dvc-tthc-thu-tuc-hanh-chinh-chi-tiet.html?ma_thu_tuc={summary.source_id}"

        response = await self._request_with_retries("GET", urljoin(self.settings.dvc_base_url, path))
        return response.text

    async def _fetch_related(self, source_id: str) -> list[dict[str, Any]]:
        payload = {
            "service": "procedure_get_related_procedures_service_v2",
            "provider": "dvcquocgia",
            "type": "ref",
            "id": source_id,
        }
        try:
            result = await self.post_rest(payload)
        except httpx.HTTPError:
            return []
        return result if isinstance(result, list) else []

    async def _fetch_impl_orders(self, source_id: str, parent_id: str | None) -> list[dict[str, Any]]:
        if not parent_id:
            return []
        payload = {
            "service": "procedure_get_impl_orders_by_proc_id_service_v2",
            "provider": "dvcquocgia",
            "type": "ref",
            "id": source_id,
            "parent_id": parent_id,
        }
        try:
            result = await self.post_rest(payload)
        except httpx.HTTPError:
            return []
        return result if isinstance(result, list) else []

    async def _fetch_requires(self, source_id: str, parent_id: str | None) -> list[dict[str, Any]]:
        if not parent_id:
            return []
        payload = {
            "service": "procedure_get_requires_by_procedure_id_service_v2",
            "provider": "dvcquocgia",
            "type": "ref",
            "id": source_id,
            "parent_id": parent_id,
        }
        try:
            result = await self.post_rest(payload)
        except httpx.HTTPError:
            return []
        return result if isinstance(result, list) else []

    async def _fetch_download_base_url(self) -> str | None:
        if self._download_base_url is not None:
            return self._download_base_url

        payload = {
            "service": "get_url_downfile",
            "provider": "dvcquocgia",
            "type": "ref",
        }
        try:
            result = await self.post_rest(payload)
        except httpx.HTTPError:
            return None
        if isinstance(result, list) and result:
            url = result[0].get("URL_DOWNLOAD")
            self._download_base_url = str(url) if url else None
            return self._download_base_url
        return None

    async def _request_with_retries(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        timeout = httpx.Timeout(self.settings.dvc_request_timeout_seconds)

        for attempt in range(1, self.settings.dvc_max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout, headers=self.headers, follow_redirects=True) as client:
                    response = await client.request(method, url, **kwargs)
                    if response.status_code in {429, 500, 502, 503, 504}:
                        raise httpx.HTTPStatusError(
                            f"retryable status {response.status_code}",
                            request=response.request,
                            response=response,
                        )
                    response.raise_for_status()
                    return response
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt >= self.settings.dvc_max_retries:
                    break
                await asyncio.sleep(self.settings.dvc_retry_backoff_seconds * attempt)

        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Cannot fetch {url}")

    def _summary_from_row(self, row: dict[str, Any], group: ProcedureGroup) -> ProcedureSummary:
        source_id = str(row.get("ID") or "")
        detail_slug = (
            "dvc-tthc-thu-tuc-hanh-chinh-lien-thong-chi-tiet.html"
            if group == ProcedureGroup.interlinked
            else "dvc-tthc-thu-tuc-hanh-chinh-chi-tiet.html"
        )
        return ProcedureSummary(
            source_id=source_id,
            procedure_code=str(row.get("PROCEDURE_CODE") or ""),
            procedure_group=group,
            name=str(row.get("PROCEDURE_NAME") or ""),
            field_name=row.get("FIELD_NAME"),
            published_agency=row.get("PUBLISHED_AGENCY"),
            implementation_agency=self._dedupe_semicolon_list(row.get("IMPLEMENTATION_AGENCY")),
            source_url=urljoin(
                self.settings.dvc_base_url,
                f"/p/home/{detail_slug}?ma_thu_tuc={source_id}",
            ),
            raw_summary=row,
        )

    def _parse_execution_methods(self, soup: BeautifulSoup) -> list[dict[str, str]]:
        tables = soup.select("table")
        for table in tables:
            headers = [self._clean_text(cell.get_text(" ")) for cell in table.select("thead th")]
            if not headers or "Hình thức nộp" not in " ".join(headers):
                continue

            methods: list[dict[str, str]] = []
            for row in table.select("tbody tr"):
                cells = [self._clean_text(cell.get_text(" ")) for cell in row.select("td")]
                if not cells:
                    continue
                methods.append(
                    {
                        "submission_method": cells[0] if len(cells) > 0 else "",
                        "processing_time": cells[1] if len(cells) > 1 else "",
                        "fees": cells[2] if len(cells) > 2 else "",
                        "description": cells[3] if len(cells) > 3 else "",
                    }
                )
            return methods
        return []

    def _parse_parent_id(self, html: str) -> str | None:
        match = re.search(r"obj\.parent_id\s*=\s*['\"]([^'\"]+)['\"]", html)
        return match.group(1) if match else None

    def _parse_export_url(self, soup: BeautifulSoup) -> str | None:
        link = soup.select_one('a[href*="export_word_detail_tthc.jsp"]')
        if not link:
            return None
        href = str(link.get("href") or "")
        return urljoin(self.settings.dvc_base_url, href) if href else None

    def _parse_required_documents(self, soup: BeautifulSoup, download_base_url: str | None) -> list[dict[str, Any]]:
        tables = soup.select("table.tphs") or [
            table
            for table in soup.select("table")
            if "Loại giấy tờ" in self._clean_text(table.get_text(" ")) and "Bản chính" in self._clean_text(table.get_text(" "))
        ]
        if not tables:
            return []

        documents: list[dict[str, Any]] = []
        for table in tables:
            for row in table.select("tbody tr"):
                cells = row.select("td")
                if len(cells) < 3:
                    continue
                forms = self._parse_document_forms(cells[3] if len(cells) > 3 else None, download_base_url)
                document = {
                    "name": self._clean_text(cells[0].get_text(" ")),
                    "original_count": self._clean_text(cells[1].get_text(" ")) if len(cells) > 1 else "",
                    "copy_count": self._clean_text(cells[2].get_text(" ")) if len(cells) > 2 else "",
                    "forms": forms,
                }
                if any(document.values()):
                    documents.append(document)
            if documents:
                break
        return documents

    def _parse_document_forms(self, cell: Any, download_base_url: str | None) -> list[dict[str, str]]:
        if cell is None:
            return []

        forms: list[dict[str, str]] = []
        for element in cell.select("[onclick]"):
            onclick = str(element.get("onclick") or "")
            match = re.search(r"downloadMaudon\(['\"]([^'\"]+)['\"]\)", onclick)
            file_code = match.group(1) if match else ""
            title = self._clean_text(element.get_text(" "))
            if not title and not file_code:
                continue
            forms.append(
                {
                    "title": title,
                    "file_code": file_code,
                    "file_url": f"{download_base_url}?ma={file_code}" if download_base_url and file_code else "",
                }
            )
        return forms

    def _attachments_from_documents(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        attachments: list[dict[str, Any]] = []
        for document in documents:
            for form in document.get("forms") or []:
                title = form.get("title") or "Mẫu đơn, tờ khai"
                attachments.append(
                    {
                        "title": title,
                        "file_url": form.get("file_url") or None,
                        "file_type": self._guess_file_type(title),
                        "source_payload": {
                            "kind": "document_form",
                            "file_code": form.get("file_code"),
                            "document_name": document.get("name"),
                        },
                    }
                )
        return attachments

    def _parse_detail_modal(self, soup: BeautifulSoup) -> str:
        modal = soup.select_one("#popupChitietTTHC")
        source = modal if modal else soup
        return self._clean_text(source.get_text("\n"))

    def _parse_modal_fields(self, soup: BeautifulSoup) -> dict[str, str]:
        modal = soup.select_one("#popupChitietTTHC")
        if not modal:
            return {}

        fields: dict[str, str] = {}
        for row in modal.select(".info-row"):
            direct_children = row.find_all("div", recursive=False)
            if len(direct_children) < 2:
                continue
            label = self._normalize_label(direct_children[0].get_text(" "))
            value = self._clean_text(direct_children[1].get_text(" "))
            if label:
                fields[label] = value
        return fields

    def _format_impl_orders(self, rows: list[dict[str, Any]]) -> str | None:
        if not rows:
            return None

        grouped: dict[str, list[str]] = {}
        ungrouped: list[str] = []
        for row in rows:
            content = self._clean_html(row.get("CONTENT") or "")
            if not content:
                continue
            scenario = self._clean_text(str(row.get("SCENARIO") or ""))
            if scenario:
                grouped.setdefault(scenario, []).append(content)
            else:
                ungrouped.append(content)

        parts: list[str] = []
        parts.extend(ungrouped)
        for scenario, contents in grouped.items():
            parts.append(f"{scenario}:\n" + "\n".join(contents))
        return "\n\n".join(parts) if parts else None

    def _format_requires(self, rows: list[dict[str, Any]]) -> str | None:
        values = [self._clean_html(row.get("REQUIRE_NAME") or "") for row in rows]
        values = [value for value in values if value]
        return "\n".join(values) if values else None

    def _format_required_documents(self, documents: list[dict[str, Any]]) -> str | None:
        if not documents:
            return None

        lines = ["Bao gồm"]
        for document in documents:
            line = document.get("name") or "Giấy tờ"
            counts = []
            if document.get("original_count"):
                counts.append(f"Bản chính: {document['original_count']}")
            if document.get("copy_count"):
                counts.append(f"Bản sao: {document['copy_count']}")
            if counts:
                line += f" ({', '.join(counts)})"
            forms = document.get("forms") or []
            if forms:
                form_titles = [form.get("title") for form in forms if form.get("title")]
                if form_titles:
                    line += f" - Mẫu đơn/tờ khai: {', '.join(form_titles)}"
            lines.append(f"- {line}")
        return "\n".join(lines)

    def _summarize_column(self, rows: list[dict[str, str]], key: str) -> str | None:
        values = []
        for row in rows:
            value = self._clean_text(row.get(key, ""))
            if value and value not in values:
                values.append(value)
        return "; ".join(values) if values else None

    def _normalize_label(self, value: str) -> str:
        return self._clean_text(value).rstrip(":")

    def _clean_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", unescape(value)).strip()

    def _dedupe_semicolon_list(self, value: Any) -> str | None:
        if value is None:
            return None

        parts = [self._clean_text(part) for part in str(value).split(";")]
        unique_parts: list[str] = []
        seen: set[str] = set()
        for part in parts:
            if not part:
                continue
            key = re.sub(r"\s*-\s*", " - ", part).casefold()
            if key in seen:
                continue
            seen.add(key)
            unique_parts.append(part)

        return "; ".join(unique_parts) if unique_parts else None

    def _clean_html(self, value: str) -> str:
        soup = BeautifulSoup(str(value), "html.parser")
        return self._clean_text(soup.get_text("\n"))

    def _guess_file_type(self, title: str) -> str | None:
        match = re.search(r"\.([a-zA-Z0-9]+)$", title.strip())
        return match.group(1).lower() if match else None

    def _hash_payload(self, payload: dict[str, Any]) -> str:
        normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
