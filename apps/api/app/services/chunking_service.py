import hashlib
import re
from dataclasses import dataclass
from typing import Any

from app.config import Settings


@dataclass
class ProcedureChunk:
    chunk_id: str
    procedure_id: str
    document_id: str | None
    procedure_code: str
    procedure_group: str
    name: str
    field_name: str | None
    target_audience: str | None
    implementation_agency: str | None
    section_name: str
    chunk_index: int
    chunk_text: str
    chunk_markdown: str
    token_count: int
    source_url: str
    content_hash: str
    metadata: dict[str, Any]
    is_active: bool = True


class ChunkingService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def chunk_document(self, procedure: dict[str, Any], document: dict[str, Any]) -> list[ProcedureChunk]:
        markdown = document.get("normalized_markdown") or ""
        sections = self._split_sections(markdown)
        chunks: list[ProcedureChunk] = []
        chunk_index = 0

        for section_name, section_markdown in sections:
            header = self._context_header(procedure, section_name)
            body_chunks = self._split_by_tokens(section_markdown, self.settings.chunk_token_limit, self.settings.chunk_overlap_tokens)
            for body in body_chunks:
                chunk_markdown = f"{header}\n\n{body.strip()}".strip()
                token_count = len(self._tokens(chunk_markdown))
                chunk_id = self._chunk_id(procedure["id"], chunk_index)
                chunks.append(
                    ProcedureChunk(
                        chunk_id=chunk_id,
                        procedure_id=procedure["id"],
                        document_id=document.get("id"),
                        procedure_code=procedure["procedure_code"],
                        procedure_group=procedure["procedure_group"],
                        name=procedure["name"],
                        field_name=procedure.get("field_name"),
                        target_audience=procedure.get("target_audience"),
                        implementation_agency=procedure.get("implementation_agency"),
                        section_name=section_name,
                        chunk_index=chunk_index,
                        chunk_text=self._plain_text(chunk_markdown),
                        chunk_markdown=chunk_markdown,
                        token_count=token_count,
                        source_url=procedure.get("source_url") or "",
                        content_hash=self._hash_text(chunk_markdown),
                        metadata={
                            "document_content_hash": document.get("content_hash"),
                            "token_limit": self.settings.chunk_token_limit,
                            "overlap_tokens": self.settings.chunk_overlap_tokens,
                        },
                    )
                )
                chunk_index += 1

        return chunks

    def to_row(self, chunk: ProcedureChunk) -> dict[str, Any]:
        return {
            "chunk_id": chunk.chunk_id,
            "procedure_id": chunk.procedure_id,
            "document_id": chunk.document_id,
            "procedure_code": chunk.procedure_code,
            "procedure_group": chunk.procedure_group,
            "name": chunk.name,
            "field_name": chunk.field_name,
            "target_audience": chunk.target_audience,
            "implementation_agency": chunk.implementation_agency,
            "section_name": chunk.section_name,
            "chunk_index": chunk.chunk_index,
            "chunk_text": chunk.chunk_text,
            "chunk_markdown": chunk.chunk_markdown,
            "token_count": chunk.token_count,
            "source_url": chunk.source_url,
            "content_hash": chunk.content_hash,
            "metadata": chunk.metadata,
            "is_active": chunk.is_active,
        }

    def _split_sections(self, markdown: str) -> list[tuple[str, str]]:
        parts = re.split(r"(?m)^##\s+", markdown)
        if len(parts) == 1:
            return [("Toan bo thu tuc", markdown)]

        first = parts[0].strip()
        sections: list[tuple[str, str]] = []
        if first:
            sections.append(("Thong tin chung", first))

        for part in parts[1:]:
            lines = part.splitlines()
            if not lines:
                continue
            title = lines[0].strip() or "Noi dung"
            content = "\n".join(lines[1:]).strip()
            if content:
                sections.append((title[:120], f"## {title}\n\n{content}"))
        return sections

    def _split_by_tokens(self, text: str, limit: int, overlap: int) -> list[str]:
        tokens = self._tokens(text)
        if len(tokens) <= limit:
            return [text]

        chunks: list[str] = []
        start = 0
        overlap = max(0, min(overlap, limit - 1))
        while start < len(tokens):
            end = min(len(tokens), start + limit)
            chunks.append(" ".join(tokens[start:end]))
            if end >= len(tokens):
                break
            start = end - overlap
        return chunks

    def _context_header(self, procedure: dict[str, Any], section_name: str) -> str:
        return "\n".join(
            [
                f"Thu tuc: {procedure.get('name') or ''}",
                f"Ma thu tuc: {procedure.get('procedure_code') or ''}",
                f"Linh vuc: {procedure.get('field_name') or 'Chua ro'}",
                f"Co quan thuc hien: {procedure.get('implementation_agency') or 'Chua ro'}",
                f"Muc: {section_name}",
            ]
        )

    def _tokens(self, text: str) -> list[str]:
        return re.findall(r"\S+", text)

    def _plain_text(self, markdown: str) -> str:
        text = re.sub(r"\|", " ", markdown)
        text = re.sub(r"[*_`#>\[\]()]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _chunk_id(self, procedure_id: str, chunk_index: int) -> str:
        return f"{procedure_id}:{chunk_index:04d}"

    def _hash_text(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
