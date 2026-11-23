import os
import sys
import csv
import time
import logging
from pathlib import Path
from typing import Dict, Any, List

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.services.rag import RAGService, I_DONT_KNOW_RESPONSE
from evals.scorers.code_scorers import score_sources_present, score_sources_match, score_idk
from evals.scorers.llm_judges import evaluate_safety
from evals.scorers.ragas_eval import score_ragas_metrics

logger = logging.getLogger("netracare.evals.policy")


def run_policy_suite(large: bool = False) -> Dict[str, Any]:
    dataset_name = "policy_questions-large.csv" if large else "policy_questions.csv"
    csv_path = ROOT / "evals" / "datasets" / dataset_name

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    print(f"\n========================================================")
    print(f"Running Policy Suite on {dataset_name} ({len(reader)} questions)...")
    print(f"========================================================")

    results = []
    answered_count = 0
    sources_cited_count = 0
    section_matched_count = 0
    idk_expected_count = 0
    idk_passed_count = 0
    safety_violations = 0
    failing_rows = []

    faithfulness_scores = []
    context_recall_scores = []
    response_relevancy_scores = []
    context_precision_scores = []

    for row in reader:
        qid = row["question_id"]
        question = row["question"]
        expected_ans = row["expected_answer"]
        expected_src = row.get("expected_source", "")

        is_idk_expected = (expected_ans.strip().lower() == "i don't know" or expected_src.strip().lower() == "none")

        try:
            # Direct Iteration 3 RAG search & grounded answer
            search_res = RAGService.hybrid_search(question, top_k=4)
            retrieved_chunks = search_res.get("hybrid", [])
            answer_res = RAGService.generate_grounded_answer(question, retrieved_chunks)

            answer = answer_res.get("answer", "")
            sources = answer_res.get("sources", [])
        except Exception as e:
            logger.error(f"Error on question {qid}: {e}")
            answer = f"Error: {e}"
            sources = []
            retrieved_chunks = []

        # Safety check on answer
        safety_res = evaluate_safety(question, answer)
        is_safe = safety_res.is_safe
        if not is_safe:
            safety_violations += 1

        ragas_data = {}
        if is_idk_expected:
            idk_expected_count += 1
            is_idk_pass = score_idk(answer)
            if is_idk_pass:
                idk_passed_count += 1
                status_str = "PASS"
            else:
                status_str = "FAIL (Expected IDK)"
                failing_rows.append(qid)

            row_result = {
                "question_id": qid,
                "question": question,
                "expected_answer": expected_ans,
                "expected_source": expected_src,
                "answer": answer,
                "sources": sources,
                "is_idk_pass": is_idk_pass,
                "has_sources": False,
                "matches_section": True,
                "is_safe": is_safe,
                "status": status_str
            }
        else:
            answered_count += 1
            has_sources = score_sources_present(sources)
            matches_section = score_sources_match(sources, expected_src)

            if has_sources:
                sources_cited_count += 1
            else:
                failing_rows.append(qid)

            if matches_section:
                section_matched_count += 1

            status_str = "PASS" if has_sources else "FAIL (No sources cited)"

            # RAGAS metrics on answered row
            ragas_metrics = score_ragas_metrics(question, answer, expected_ans, retrieved_chunks)
            faithfulness_scores.append(ragas_metrics["faithfulness"])
            context_recall_scores.append(ragas_metrics["context_recall"])
            response_relevancy_scores.append(ragas_metrics["response_relevancy"])
            context_precision_scores.append(ragas_metrics["context_precision"])

            row_result = {
                "question_id": qid,
                "question": question,
                "expected_answer": expected_ans,
                "expected_source": expected_src,
                "answer": answer,
                "sources": sources,
                "has_sources": has_sources,
                "matches_section": matches_section,
                "faithfulness": ragas_metrics["faithfulness"],
                "context_recall": ragas_metrics["context_recall"],
                "response_relevancy": ragas_metrics["response_relevancy"],
                "context_precision": ragas_metrics["context_precision"],
                "is_safe": is_safe,
                "status": status_str
            }

        results.append(row_result)
        print(f"[{status_str}] {qid}: sources={len(sources)} | safe={is_safe}")
        time.sleep(2.0)

    # Target: 100% of answered policy questions cite a document
    sources_pct = (sources_cited_count / answered_count * 100) if answered_count else 0
    target_met = (sources_cited_count == answered_count)

    # Working bars
    section_pct = (section_matched_count / answered_count * 100) if answered_count else 0
    section_bar_met = (section_pct >= 90.0)

    idk_bar_met = (idk_passed_count == idk_expected_count)

    avg_faithfulness = sum(faithfulness_scores) / len(faithfulness_scores) if faithfulness_scores else 0.0
    avg_recall = sum(context_recall_scores) / len(context_recall_scores) if context_recall_scores else 0.0
    avg_relevancy = sum(response_relevancy_scores) / len(response_relevancy_scores) if response_relevancy_scores else 0.0
    avg_precision = sum(context_precision_scores) / len(context_precision_scores) if context_precision_scores else 0.0

    ragas_faithfulness_met = (avg_faithfulness >= 0.85)
    ragas_recall_met = (avg_recall >= 0.80)

    print("\n--------------------------------------------------------")
    print(f"Policy Target (100% cite document): {'MET' if target_met else 'MISSED'} ({sources_cited_count}/{answered_count} = {sources_pct:.1f}%)")
    print(f"Working Bar (Expected section >= 90%): {'MET' if section_bar_met else 'MISSED'} ({section_matched_count}/{answered_count} = {section_pct:.1f}%)")
    print(f"Working Bar (IDK answers): {'MET' if idk_bar_met else 'MISSED'} ({idk_passed_count}/{idk_expected_count})")
    print(f"RAGAS Averages:")
    print(f"  - Faithfulness: {avg_faithfulness:.4f} (Target: >= 0.85) -> {'MET' if ragas_faithfulness_met else 'MISSED'}")
    print(f"  - Context Recall: {avg_recall:.4f} (Target: >= 0.80) -> {'MET' if ragas_recall_met else 'MISSED'}")
    print(f"  - Response Relevancy: {avg_relevancy:.4f}")
    print(f"  - Context Precision: {avg_precision:.4f}")
    print(f"Safety on Policy Replies: {safety_violations} violations")
    print("--------------------------------------------------------")

    return {
        "suite": "policy",
        "dataset": dataset_name,
        "total_rows": len(reader),
        "answered_count": answered_count,
        "sources_cited_count": sources_cited_count,
        "section_matched_count": section_matched_count,
        "idk_expected_count": idk_expected_count,
        "idk_passed_count": idk_passed_count,
        "target_met": target_met,
        "section_bar_met": section_bar_met,
        "idk_bar_met": idk_bar_met,
        "ragas": {
            "avg_faithfulness": avg_faithfulness,
            "avg_context_recall": avg_recall,
            "avg_response_relevancy": avg_relevancy,
            "avg_context_precision": avg_precision,
            "faithfulness_met": ragas_faithfulness_met,
            "recall_met": ragas_recall_met
        },
        "safety_violations": safety_violations,
        "failing_rows": failing_rows,
        "results": results
    }


if __name__ == "__main__":
    is_large = "--large" in sys.argv
    run_policy_suite(large=is_large)
