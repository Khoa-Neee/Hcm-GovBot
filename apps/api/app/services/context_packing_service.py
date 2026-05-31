from typing import Any


class ContextPackingService:
    def pack(self, chunks: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        ordered = self._edge_order(chunks)
        sources: list[dict[str, Any]] = []
        blocks: list[str] = []
        for index, chunk in enumerate(ordered, start=1):
            citation = f"C{index}"
            source = {
                "chunk_id": chunk["chunk_id"],
                "citation": citation,
                "procedure_id": chunk["procedure_id"],
                "procedure_code": chunk["procedure_code"],
                "procedure_group": chunk["procedure_group"],
                "name": chunk["name"],
                "field_name": chunk.get("field_name"),
                "target_audience": chunk.get("target_audience"),
                "implementation_agency": chunk.get("implementation_agency"),
                "section_name": chunk.get("section_name") or "Noi dung",
                "source_url": chunk["source_url"],
                "score": self._score(chunk),
                "text": chunk.get("chunk_markdown") or chunk.get("chunk_text") or "",
            }
            sources.append(source)
            blocks.append(
                "\n".join(
                    [
                        f"[{citation}]",
                        f"Thu tuc: {source['name']}",
                        f"Ma thu tuc: {source['procedure_code']}",
                        f"Muc: {source['section_name']}",
                        f"Nguon: {source['source_url']}",
                        "Noi dung:",
                        source["text"],
                    ]
                )
            )
        return "\n\n---\n\n".join(blocks), sources

    def procedures_from_sources(self, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id: dict[str, dict[str, Any]] = {}
        for source in sources:
            procedure_id = source["procedure_id"]
            if procedure_id in by_id:
                by_id[procedure_id]["summary"] += f"\n- [{source['citation']}] {source['section_name']}"
                continue
            by_id[procedure_id] = {
                "procedure_id": procedure_id,
                "procedure_code": source["procedure_code"],
                "procedure_group": source["procedure_group"],
                "name": source["name"],
                "source_url": source["source_url"],
                "field_name": source.get("field_name"),
                "target_audience": source.get("target_audience"),
                "summary": f"- [{source['citation']}] {source['section_name']}",
            }
        return list(by_id.values())

    def _edge_order(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ordered: list[dict[str, Any] | None] = [None] * len(chunks)
        left = 0
        right = len(chunks) - 1
        for index, chunk in enumerate(chunks):
            if index % 2 == 0:
                ordered[left] = chunk
                left += 1
            else:
                ordered[right] = chunk
                right -= 1
        return [chunk for chunk in ordered if chunk is not None]

    def _score(self, chunk: dict[str, Any]) -> float | None:
        for key in ["rerank_score", "rrf_score", "dense_score", "bm25_score"]:
            if key in chunk:
                return float(chunk[key])
        return None
