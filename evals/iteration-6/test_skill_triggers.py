"""Evaluation runner for Agent Skill Triggers (T01 - T16)."""
import csv
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Dict, Any, List

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

# Force evaluation database isolation
os.environ["DATABASE_URL"] = f"sqlite:///{(ROOT / 'evals' / 'eval_netracare.db').resolve()}"

from app.database import SessionLocal
from app.services.agent import run_agent_turn

CSV_PATH = ROOT / "evals" / "datasets" / "iteration-6" / "skill_triggers.csv"
RESULTS_DIR = ROOT / "evals" / "results" / "iteration-6"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def evaluate_trigger(row: Dict[str, str], db) -> Dict[str, Any]:
    tid = row["trigger_id"]
    pid = row["patient_id"]
    msg = row["message"]
    exp_skill = row["expected_skill"].strip()
    alt_skill = row.get("also_acceptable", "").strip()

    thread_id = f"test-trigger-{tid}-{uuid.uuid4().hex[:6]}"
    res = run_agent_turn(
        patient_id=pid,
        thread_id=thread_id,
        message=msg,
        db=db
    )
    ans = res.get("answer", "")
    sources = res.get("sources", [])
    is_emergency = res.get("is_emergency", False)

    # Detect which skill was used from sources / answer
    detected_skills = []
    for s in sources:
        if s.startswith("Skill: "):
            detected_skills.append(s.replace("Skill: ", "").strip())

    if not detected_skills:
        for sk in ["cataract-surgery-care", "lasik-suitability-intake", "prepare-for-visit", "children-visit"]:
            if f"Skill: {sk}" in ans:
                detected_skills.append(sk)

    actual_skill = detected_skills[0] if detected_skills else "none"

    if exp_skill == "none":
        passed = (actual_skill == "none") or (alt_skill and actual_skill == alt_skill)
    else:
        passed = (actual_skill == exp_skill) or (alt_skill and actual_skill == alt_skill)

    # Special check for T16 (Red flag: must trigger emergency and NO skill)
    if tid == "T16":
        passed = is_emergency and (actual_skill == "none")

    return {
        "trigger_id": tid,
        "patient_id": pid,
        "message": msg,
        "expected_skill": exp_skill,
        "also_acceptable": alt_skill,
        "actual_skill": actual_skill,
        "is_emergency": is_emergency,
        "passed": passed,
        "answer_preview": ans[:120].replace("\n", " ")
    }


def main():
    print("=" * 70)
    print("RUNNING AGENT SKILL TRIGGERS EVALUATION (T01 - T16)")
    print("=" * 70)

    results: List[Dict[str, Any]] = []
    passed_count = 0

    with open(CSV_PATH, mode="r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    with SessionLocal() as db:
        for row in reader:
            res = evaluate_trigger(row, db)
            if res["passed"]:
                passed_count += 1
            mark = "✓ PASS" if res["passed"] else "✗ FAIL"
            exp_disp = res["expected_skill"]
            if res["also_acceptable"]:
                exp_disp += f" (or {res['also_acceptable']})"
            print(f"[{res['trigger_id']}] {mark} | Expected: {exp_disp} | Actual: {res['actual_skill']} | Emergency: {res['is_emergency']}")
            if not res["passed"]:
                print(f"      Ans: {res['answer_preview']}...")
            results.append(res)

    # Save to CSV
    out_csv = RESULTS_DIR / "skill_triggers_results.csv"
    with open(out_csv, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "trigger_id", "patient_id", "message", "expected_skill", "also_acceptable",
            "actual_skill", "is_emergency", "passed", "answer_preview"
        ])
        writer.writeheader()
        writer.writerows(results)

    print("=" * 70)
    print(f"SKILL TRIGGERS EVALUATION COMPLETE. Passed: {passed_count}/{len(reader)} ({passed_count/len(reader)*100:.1f}%)")
    print(f"Results written to: {out_csv}")
    print("=" * 70)
    sys.exit(0 if passed_count >= 14 else 1)


if __name__ == "__main__":
    main()
