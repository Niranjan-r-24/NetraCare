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

from app.services.agent import run_agent_turn
from evals.scorers.llm_judges import evaluate_routing, score_routing_match, evaluate_safety

logger = logging.getLogger("netracare.evals.routing")


def run_routing_suite(large: bool = False) -> Dict[str, Any]:
    dataset_name = "routing-large.csv" if large else "routing.csv"
    csv_path = ROOT / "evals" / "datasets" / dataset_name

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    print(f"\n========================================================")
    print(f"Running Routing Suite on {dataset_name} ({len(reader)} rows)...")
    print(f"========================================================")

    results = []
    correct_routings = 0
    safety_violations = 0
    failing_rows = []

    for row in reader:
        sample_id = row["sample_id"]
        message = row["message"]
        exp_spec = row["expected_speciality"]
        also_accept = row.get("also_accept", "")

        try:
            # P20 (Aditya Bose), fresh thread
            res = run_agent_turn(
                patient_id="P20",
                thread_id=None,
                message=message,
                confirm=None
            )
            reply_text = res.get("answer", "")
        except Exception as e:
            logger.error(f"Error executing chat on row {sample_id}: {e}")
            reply_text = f"Error: {e}"

        # 1. Routing judge
        routing_res = evaluate_routing(message, reply_text)
        judged_spec = routing_res.speciality
        is_match = score_routing_match(judged_spec, exp_spec, also_accept)

        if is_match:
            correct_routings += 1
            status_str = "PASS"
        else:
            status_str = "FAIL"
            failing_rows.append(sample_id)

        # 2. Safety judge on chat reply
        safety_res = evaluate_safety(message, reply_text)
        is_safe = safety_res.is_safe
        if not is_safe:
            safety_violations += 1

        results.append({
            "sample_id": sample_id,
            "message": message,
            "expected_speciality": exp_spec,
            "also_accept": also_accept,
            "judged_speciality": judged_spec,
            "is_match": is_match,
            "judge_reason": routing_res.reason,
            "is_safe": is_safe,
            "safety_reason": safety_res.reason,
            "reply": reply_text,
            "status": status_str
        })

        print(f"[{status_str}] {sample_id}: expected={exp_spec}, judged={judged_spec} | safe={is_safe}")
        time.sleep(1.0)

    total = len(reader)
    accuracy_pct = (correct_routings / total * 100) if total else 0
    target_met = (accuracy_pct >= 90.0)

    print("\n--------------------------------------------------------")
    print(f"Routing Target (>= 90%): {'MET' if target_met else 'MISSED'} ({correct_routings}/{total} = {accuracy_pct:.1f}%)")
    print(f"Safety on Chat Replies: {safety_violations} violations")
    print("--------------------------------------------------------")

    return {
        "suite": "routing",
        "dataset": dataset_name,
        "total_rows": total,
        "correct_routings": correct_routings,
        "accuracy_pct": accuracy_pct,
        "safety_violations": safety_violations,
        "target_met": target_met,
        "failing_rows": failing_rows,
        "results": results
    }


if __name__ == "__main__":
    is_large = "--large" in sys.argv
    run_routing_suite(large=is_large)
