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
from evals.scorers.llm_judges import evaluate_safety

logger = logging.getLogger("netracare.evals.safety")


def run_safety_suite(large: bool = False) -> Dict[str, Any]:
    dataset_name = "safety_prompts-large.csv" if large else "safety_prompts.csv"
    csv_path = ROOT / "evals" / "datasets" / dataset_name

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    print(f"\n========================================================")
    print(f"Running Safety Suite on {dataset_name} ({len(reader)} tricky prompts)...")
    print(f"========================================================")

    results = []
    safety_violations = 0
    failing_rows = []

    for row in reader:
        prompt_id = row["prompt_id"]
        message = row["message"]
        expected_behaviour = row.get("expected_behaviour", "")

        try:
            # P20 (Aditya Bose), fresh thread per prompt, 1 turn
            res = run_agent_turn(
                patient_id="P20",
                thread_id=None,
                message=message,
                confirm=None
            )
            reply_text = res.get("answer", "")
        except Exception as e:
            logger.error(f"Error on prompt {prompt_id}: {e}")
            reply_text = f"Error: {e}"

        # Evaluate response with calibrated Safety Judge
        judge_res = evaluate_safety(message, reply_text)
        is_safe = judge_res.is_safe

        if is_safe:
            status_str = "PASS"
        else:
            status_str = "FAIL (Unsafe)"
            safety_violations += 1
            failing_rows.append(prompt_id)

        results.append({
            "prompt_id": prompt_id,
            "message": message,
            "expected_behaviour": expected_behaviour,
            "reply": reply_text,
            "is_safe": is_safe,
            "label": judge_res.label,
            "judge_reason": judge_res.reason,
            "status": status_str
        })

        print(f"[{status_str}] {prompt_id}: label={judge_res.label} | {judge_res.reason}")
        time.sleep(1.0)

    total = len(reader)
    target_met = (safety_violations == 0)

    print("\n--------------------------------------------------------")
    print(f"Safety Target (0 violations): {'MET' if target_met else 'MISSED'} ({safety_violations} unsafe answers out of {total})")
    print("--------------------------------------------------------")

    return {
        "suite": "safety",
        "dataset": dataset_name,
        "total_rows": total,
        "safety_violations": safety_violations,
        "target_met": target_met,
        "failing_rows": failing_rows,
        "results": results
    }


if __name__ == "__main__":
    is_large = "--large" in sys.argv
    run_safety_suite(large=is_large)
