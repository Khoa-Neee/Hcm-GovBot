import math
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.services.hybrid_retrieval_service import HybridRetrievalService
from app.services.supabase_repo import SupabaseRepository


@dataclass
class RetrievalEvalStats:
    questions: int = 0
    precision_at_k: float = 0.0
    recall_at_k: float = 0.0
    mrr: float = 0.0
    ndcg_at_k: float = 0.0


class RetrievalEvaluator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.repo = SupabaseRepository(settings)
        self.retrieval = HybridRetrievalService(settings)

    def run(self, run_name: str, k: int, limit: int | None = None, reviewed_only: bool = True, save: bool = False) -> RetrievalEvalStats:
        questions = self.repo.list_eval_questions(reviewed_only=reviewed_only, limit=limit)
        rows: list[dict[str, float]] = []
        for question in questions:
            retrieved = self.retrieval.search(question["question"], k)
            retrieved_ids = [item["chunk_id"] for item in retrieved]
            relevant = set(question.get("relevant_chunk_ids") or [])
            metrics = self._metrics(retrieved_ids, relevant, k)
            rows.append(metrics)
            if save:
                self.repo.insert_retrieval_eval_result(
                    {
                        "eval_question_id": question.get("id"),
                        "question": question["question"],
                        "run_name": run_name,
                        "k": k,
                        "precision_at_k": metrics["precision_at_k"],
                        "recall_at_k": metrics["recall_at_k"],
                        "mrr": metrics["mrr"],
                        "ndcg_at_k": metrics["ndcg_at_k"],
                        "retrieved_chunk_ids": retrieved_ids,
                        "metadata": {"reviewed_only": reviewed_only},
                    }
                )
        if not rows:
            return RetrievalEvalStats()
        return RetrievalEvalStats(
            questions=len(rows),
            precision_at_k=sum(row["precision_at_k"] for row in rows) / len(rows),
            recall_at_k=sum(row["recall_at_k"] for row in rows) / len(rows),
            mrr=sum(row["mrr"] for row in rows) / len(rows),
            ndcg_at_k=sum(row["ndcg_at_k"] for row in rows) / len(rows),
        )

    def _metrics(self, retrieved: list[str], relevant: set[str], k: int) -> dict[str, float]:
        top_k = retrieved[:k]
        if not relevant:
            return {"precision_at_k": 0.0, "recall_at_k": 0.0, "mrr": 0.0, "ndcg_at_k": 0.0}
        hits = [1 if chunk_id in relevant else 0 for chunk_id in top_k]
        hit_count = sum(hits)
        precision = hit_count / max(k, 1)
        recall = hit_count / len(relevant)
        mrr = 0.0
        for index, hit in enumerate(hits, start=1):
            if hit:
                mrr = 1.0 / index
                break
        dcg = sum(hit / math.log2(index + 2) for index, hit in enumerate(hits))
        ideal_hits = [1] * min(len(relevant), k)
        idcg = sum(hit / math.log2(index + 2) for index, hit in enumerate(ideal_hits))
        ndcg = dcg / idcg if idcg else 0.0
        return {"precision_at_k": precision, "recall_at_k": recall, "mrr": mrr, "ndcg_at_k": ndcg}
