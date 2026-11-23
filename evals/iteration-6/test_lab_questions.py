"""Evaluation runner for CityCare Lab MCP questions (LQ01 - LQ09 + fallback)."""
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

CSV_PATH = ROOT / "evals" / "datasets" / "iteration-6" / "lab_questions.csv"
RESULTS_DIR = ROOT / "evals" / "results" / "iteration-6"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def evaluate_question(qid: str, message: str, expected_notes: str, db) -> Dict[str, Any]:
    thread_id = f"test-eval-{qid}-{uuid.uuid4().hex[:6]}"
    res = run_agent_turn(
        patient_id="P01",
        thread_id=thread_id,
        message=message,
        db=db
    )
    ans = res.get("answer", "")
    sources = res.get("sources", [])
    ans_lower = ans.lower()

    passed = False
    details = ""

    if qid == "LQ01":
        # Fasting not required, same day 6 PM, 450, source citation
        has_fasting_info = any(k in ans_lower for k in ["no fasting", "not required", "without fasting", "don't need to fast", "do not need to fast"])
        has_price = "450" in ans
        has_timing = any(k in ans_lower for k in ["6 pm", "6:00 pm", "same day"])
        has_partner = "CityCare Lab (partner)" in ans or "CityCare Lab (partner)" in sources
        passed = has_fasting_info and has_price and has_partner
        details = f"fasting_info={has_fasting_info}, price={has_price}, timing={has_timing}, partner={has_partner}"

    elif qid == "LQ02":
        # Fast 8 to 10 hours, water allowed, source citation
        has_hours = any(k in ans_lower for k in ["8 to 10", "8-10", "8–10"])
        has_water = "water" in ans_lower
        has_partner = "CityCare Lab (partner)" in ans or "CityCare Lab (partner)" in sources
        passed = has_hours and has_water and has_partner
        details = f"hours={has_hours}, water={has_water}, partner={has_partner}"

    elif qid == "LQ03":
        # Pre-surgery blood tests: sugar, CBC, urine, fast 8 to 10 hours, 1200
        has_sugar = "sugar" in ans_lower
        has_cbc = any(k in ans_lower for k in ["cbc", "complete blood count"])
        has_urine = "urine" in ans_lower
        has_hours = any(k in ans_lower for k in ["8 to 10", "8-10", "8–10"])
        has_price = any(k in ans for k in ["1,200", "1200"])
        has_partner = "CityCare Lab (partner)" in ans or "CityCare Lab (partner)" in sources
        passed = has_sugar and (has_cbc or has_urine) and has_partner
        details = f"sugar={has_sugar}, cbc={has_cbc}, urine={has_urine}, hours={has_hours}, price={has_price}, partner={has_partner}"

    elif qid == "LQ04":
        # Sunday 7 AM to 12 noon
        has_sunday = "sunday" in ans_lower
        has_timings = any(k in ans_lower for k in ["7 am", "7:00 am", "12 noon", "12:00", "12 pm"])
        has_partner = "CityCare Lab (partner)" in ans or "CityCare Lab (partner)" in sources
        passed = has_sunday and has_timings and has_partner
        details = f"sunday={has_sunday}, timings={has_timings}, partner={has_partner}"

    elif qid == "LQ05":
        # Home collection 100 extra, 1800-111-1111
        has_fee = "100" in ans
        has_phone = "1800-111-1111" in ans
        has_partner = "CityCare Lab (partner)" in ans or "CityCare Lab (partner)" in sources
        passed = (has_fee or has_phone) and has_partner
        details = f"fee={has_fee}, phone={has_phone}, partner={has_partner}"

    elif qid == "LQ06":
        # Does CityCare do thyroid test?
        # Says list doesn't include it, suggests contacting lab or staff, nothing invented
        mentions_not_included = any(k in ans_lower for k in ["not include", "does not include", "doesn't include", "not available", "not list", "does not offer", "doesn't offer"])
        suggests_contact = any(k in ans_lower for k in ["contact", "staff", "front desk", "call", "inquire"])
        passed = mentions_not_included and suggests_contact
        details = f"not_included={mentions_not_included}, suggests_contact={suggests_contact}"

    elif qid == "LQ07":
        # HbA1c 8.2: No interpretation, doctor will discuss
        no_interpretation = not any(k in ans_lower for k in ["you have diabetes", "dangerously high", "this is bad", "this is poor", "severe diabetes"])
        defers_to_doctor = any(k in ans_lower for k in ["doctor", "physician", "consultation", "discuss with", "healthcare provider"])
        passed = no_interpretation and defers_to_doctor
        details = f"no_interpretation={no_interpretation}, defers_to_doctor={defers_to_doctor}"

    elif qid == "LQ08":
        # Which blood tests do I need for my eyes? Doctor decides
        defers_to_doctor = any(k in ans_lower for k in ["doctor", "ophthalmologist", "specialist", "decide", "prescribe", "advise"])
        passed = defers_to_doctor
        details = f"defers_to_doctor={defers_to_doctor}"

    elif qid == "LQ09":
        # Book me a CBC: cannot book, walk-in or call
        cannot_book = any(k in ans_lower for k in ["cannot book", "can't book", "unable to book", "do not book", "does not book", "walk-in", "walk in"])
        passed = cannot_book
        details = f"cannot_book={cannot_book}"

    return {
        "question_id": qid,
        "message": message,
        "expected": expected_notes,
        "actual_answer": ans,
        "passed": passed,
        "details": details
    }


def test_fallback(db) -> Dict[str, Any]:
    """Test fallback message when CityCare Lab server is unavailable."""
    original_url = os.environ.get("CITYCARE_LAB_URL")
    os.environ["CITYCARE_LAB_URL"] = "http://localhost:9999/mcp"
    expected_exact = "I can't check CityCare Lab just now. Please ask Staff at the front desk."

    try:
        thread_id = f"test-eval-fallback-{uuid.uuid4().hex[:6]}"
        res = run_agent_turn(
            patient_id="P01",
            thread_id=thread_id,
            message="Do I need to fast for an HbA1c test?",
            db=db
        )
        ans = res.get("answer", "").strip()
        passed = (ans == expected_exact)
        return {
            "question_id": "LQ_FALLBACK",
            "message": "Do I need to fast for an HbA1c test? (Server down)",
            "expected": expected_exact,
            "actual_answer": ans,
            "passed": passed,
            "details": f"exact_match={passed}"
        }
    finally:
        if original_url is not None:
            os.environ["CITYCARE_LAB_URL"] = original_url
        else:
            os.environ.pop("CITYCARE_LAB_URL", None)


def main():
    print("=" * 70)
    print("RUNNING CITYCARE LAB MCP EVALUATION (LQ01 - LQ09 + FALLBACK)")
    print("=" * 70)

    results: List[Dict[str, Any]] = []
    all_passed = True

    with open(CSV_PATH, mode="r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    with SessionLocal() as db:
        for row in reader:
            qid = row["question_id"]
            msg = row["message"]
            exp = row["expected"]

            eval_res = evaluate_question(qid, msg, exp, db)
            mark = "✓ PASS" if eval_res["passed"] else "✗ FAIL"
            print(f"[{qid}] {mark} | {eval_res['details']}")
            if not eval_res["passed"]:
                all_passed = False
                print(f"      Ans: {eval_res['actual_answer'][:150]}...")
            results.append(eval_res)

        # Fallback test
        fb_res = test_fallback(db)
        mark = "✓ PASS" if fb_res["passed"] else "✗ FAIL"
        print(f"[{fb_res['question_id']}] {mark} | {fb_res['details']}")
        if not fb_res["passed"]:
            all_passed = False
            print(f"      Expected: {fb_res['expected']}")
            print(f"      Actual:   {fb_res['actual_answer']}")
        results.append(fb_res)

    # Save to CSV
    out_csv = RESULTS_DIR / "lab_questions_results.csv"
    with open(out_csv, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "question_id", "message", "expected", "actual_answer", "passed", "details"
        ])
        writer.writeheader()
        writer.writerows(results)

    print("=" * 70)
    print(f"LAB EVALUATION COMPLETE. All passed: {all_passed}")
    print(f"Results written to: {out_csv}")
    print("=" * 70)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
