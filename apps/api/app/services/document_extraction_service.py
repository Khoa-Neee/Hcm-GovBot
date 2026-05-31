import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from html import unescape
from typing import Any

from bs4 import BeautifulSoup

from app.config import Settings


@dataclass
class ExtractedDocument:
    procedure_id: str
    source_type: str
    source_url: str
    normalized_markdown: str
    extraction_method: str
    raw_extracted_payload: dict[str, Any]
    extraction_metadata: dict[str, Any]
    content_hash: str


class DocumentExtractionService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def extract(self, procedure: dict[str, Any]) -> ExtractedDocument:
        raw_detail = procedure.get("raw_detail") or {}
        html = raw_detail.get("detail_html") if isinstance(raw_detail, dict) else None
        markdown_parts = [self._metadata_markdown(procedure)]
        extraction_method = "structured_fields"
        raw_payload: dict[str, Any] = {"source": "procedure_fields"}

        if isinstance(html, str) and html.strip():
            table_markdown = self._html_tables_to_markdown(html)
            if table_markdown:
                markdown_parts.append("## Bang du lieu trich xuat tu HTML\n\n" + table_markdown)
                extraction_method = "html_parser"
                raw_payload["html_table_count"] = table_markdown.count("\n|")
            textract_text = self._python_textract_html(html)
            if textract_text:
                raw_payload["python_textract_text_preview"] = textract_text[:1000]

        markdown_parts.extend(self._structured_sections(procedure))
        markdown = "\n\n".join(part for part in markdown_parts if part.strip())
        markdown = self._normalize_markdown(markdown)
        payload = {
            "procedure_id": procedure["id"],
            "source_url": procedure.get("source_url") or "",
            "markdown": markdown,
            "raw_detail_hash": self._hash_payload(raw_detail),
        }

        return ExtractedDocument(
            procedure_id=procedure["id"],
            source_type="html",
            source_url=procedure.get("source_url") or "",
            normalized_markdown=markdown,
            extraction_method=extraction_method,
            raw_extracted_payload=raw_payload,
            extraction_metadata={
                "python_textract_enabled": self.settings.python_textract_enabled,
                "html_only": True,
            },
            content_hash=self._hash_payload(payload),
        )

    def _metadata_markdown(self, procedure: dict[str, Any]) -> str:
        rows = [
            ("Ten thu tuc", procedure.get("name")),
            ("Ma thu tuc", procedure.get("procedure_code")),
            ("Nhom thu tuc", procedure.get("procedure_group")),
            ("Linh vuc", procedure.get("field_name")),
            ("Doi tuong", procedure.get("target_audience")),
            ("Co quan thuc hien", procedure.get("implementation_agency")),
            ("Cap thuc hien", procedure.get("implementation_level")),
            ("Nguon", procedure.get("source_url")),
        ]
        lines = ["# " + str(procedure.get("name") or "Thu tuc"), ""]
        lines.extend(f"- {label}: {self._clean(value) or 'Chua co du lieu'}" for label, value in rows)
        return "\n".join(lines)

    def _structured_sections(self, procedure: dict[str, Any]) -> list[str]:
        sections: list[tuple[str, Any]] = [
            ("Cach thuc thuc hien", self._execution_methods_markdown(procedure.get("execution_methods") or [])),
            ("Thoi han giai quyet", procedure.get("processing_time")),
            ("Phi le phi", procedure.get("fees")),
            ("Thanh phan ho so", procedure.get("required_documents")),
            ("Trinh tu thuc hien", procedure.get("execution_steps")),
            ("Yeu cau dieu kien", procedure.get("requirements")),
            ("Can cu phap ly", procedure.get("legal_basis")),
            ("Bieu mau tep dinh kem", self._attachments_markdown(procedure.get("attachments") or [])),
        ]
        return [f"## {title}\n\n{self._clean(value)}" for title, value in sections if self._clean(value)]

    def _execution_methods_markdown(self, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return ""
        table_rows = [["Hinh thuc nop", "Thoi han", "Phi le phi", "Mo ta"]]
        for row in rows:
            table_rows.append(
                [
                    self._clean(row.get("submission_method")),
                    self._clean(row.get("processing_time")),
                    self._clean(row.get("fees")),
                    self._clean(row.get("description")),
                ]
            )
        return self._markdown_table(table_rows)

    def _attachments_markdown(self, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return ""
        lines = []
        for row in rows:
            title = self._clean(row.get("title")) or "Tep dinh kem"
            url = self._clean(row.get("file_url"))
            lines.append(f"- {title}" + (f": {url}" if url else ""))
        return "\n".join(lines)

    def _html_tables_to_markdown(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        tables: list[str] = []
        for table in soup.select("table"):
            rows: list[list[str]] = []
            for tr in table.select("tr"):
                cells = tr.find_all(["th", "td"], recursive=False)
                if not cells:
                    cells = tr.find_all(["th", "td"])
                row = [self._clean(cell.get_text(" ")) for cell in cells]
                if any(row):
                    rows.append(row)
            if rows:
                tables.append(self._markdown_table(rows))
        return "\n\n".join(tables)

    def _markdown_table(self, rows: list[list[str]]) -> str:
        if not rows:
            return ""
        width = max(len(row) for row in rows)
        normalized = [row + [""] * (width - len(row)) for row in rows]
        header = normalized[0]
        separator = ["---"] * width
        body = normalized[1:]
        all_rows = [header, separator, *body]
        return "\n".join("| " + " | ".join(self._escape_cell(cell) for cell in row) + " |" for row in all_rows)

    def _escape_cell(self, value: str) -> str:
        return value.replace("|", "\\|").replace("\n", "<br>")

    def _clean(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        text = unescape(str(value))
        return re.sub(r"[ \t\r\f\v]+", " ", text).strip()

    def _normalize_markdown(self, markdown: str) -> str:
        markdown = re.sub(r"\n{3,}", "\n\n", markdown)
        return markdown.strip()

    def _python_textract_html(self, html: str) -> str:
        if not self.settings.python_textract_enabled:
            return ""
        try:
            import textract
        except ImportError:
            return ""

        path = ""
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as handle:
                path = handle.name
                handle.write(html)
            output = textract.process(path)
            return self._clean(output.decode("utf-8", errors="ignore"))
        except Exception:
            return ""
        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass

    def _hash_payload(self, payload: Any) -> str:
        normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
