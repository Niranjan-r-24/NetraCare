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

from evals.booking.eval_db import EvalSessionLocal, reset_eval_db
from app.models import Patient, Doctor, Appointment
from app.services.llm import LLMService
from evals.scorers.code_scorers import score_summary_length
from evals.scorers.llm_judges import evaluate_summary

logger = logging.getLogger("netracare.evals.summary")


def run_summary_suite(large: bool = False) -> Dict[str, Any]:
    dataset_name = "summary_cases-large.csv" if large else "summary_cases.csv"
    csv_path = ROOT / "evals" / "datasets" / dataset_name

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    print(f"\n========================================================")
    print(f"Running Doctor Summary Suite on {dataset_name} ({len(reader)} cases)...")
    print(f"========================================================")

    reset_eval_db()
    db = EvalSessionLocal()
    results = []
    unrecorded_facts_cases = 0
    failing_rows = []

    try:
        for row in reader:
            case_id = row["case_id"]
            patient_id = row["patient_id"]
            todays_reason = row.get("todays_reason", "")
            must_include = row.get("must_include", "")
            must_not_add = row.get("must_not_add", "")

            patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
            if not patient:
                logger.error(f"Patient {patient_id} not found in DB.")
                continue

            age = (2026 - patient.year_of_birth) if patient.year_of_birth else None

            # Completed visits (newest first)
            completed_appts = db.query(Appointment).filter(
                Appointment.patient_id == patient_id,
                Appointment.status == "completed"
            ).order_by(Appointment.appointment_date.desc(), Appointment.start_time.desc()).all()

            visits_list = []
            record_lines = [
                f"Patient Name: {patient.name}",
                f"Age: {age} years",
                f"General Health: {patient.general_health or 'None recorded'}",
                f"Allergies: {patient.allergies or 'None known'}",
                "Past Visits:"
            ]

            for appt in completed_appts:
                doc = db.query(Doctor).filter(Doctor.doctor_id == appt.doctor_id).first()
                doc_name = doc.name if doc else appt.doctor_id
                visits_list.append({
                    "date": str(appt.appointment_date),
                    "doctor_id": appt.doctor_id,
                    "doctor_name": doc_name,
                    "speciality": appt.speciality,
                    "reason": appt.reason,
                    "doctor_note": appt.doctor_note
                })
                record_lines.append(
                    f"- {appt.appointment_date} with Dr. {doc_name} ({appt.speciality}): Note='{appt.doctor_note}' | Reason='{appt.reason}'"
                )

            patient_record_str = "\n".join(record_lines)

            # Generate summary
            summary = LLMService.generate_doctor_summary(
                patient_name=patient.name,
                age=age,
                general_health=patient.general_health or "None recorded",
                allergies=patient.allergies or "None known",
                today_reason=todays_reason,
                completed_visits=visits_list
            )

            # Length check
            length_ok = score_summary_length(summary, max_words=120)

            # Audit summary with Judge
            judge_res = evaluate_summary(
                record=patient_record_str,
                today_reason=todays_reason,
                must_include=must_include,
                must_not_add=must_not_add,
                summary=summary
            )

            has_unrecorded = len(judge_res.unrecorded_facts) > 0
            if has_unrecorded:
                unrecorded_facts_cases += 1
                status_str = "FAIL (Unrecorded Fact)"
                failing_rows.append(case_id)
            else:
                status_str = "PASS"

            results.append({
                "case_id": case_id,
                "patient_id": patient_id,
                "todays_reason": todays_reason,
                "must_include": must_include,
                "must_not_add": must_not_add,
                "summary": summary,
                "length_ok": length_ok,
                "unrecorded_facts": judge_res.unrecorded_facts,
                "missing_must_include": judge_res.missing_must_include,
                "judge_reason": judge_res.reason,
                "status": status_str
            })

            print(f"[{status_str}] {case_id}: unrecorded={len(judge_res.unrecorded_facts)}, missing_include={len(judge_res.missing_must_include)} | length_ok={length_ok}")
            time.sleep(1.0)

        total_cases = len(reader)
        working_bar_met = (unrecorded_facts_cases == 0)

        print("\n--------------------------------------------------------")
        print(f"Summary Working Bar (0 unrecorded facts): {'MET' if working_bar_met else 'MISSED'} ({unrecorded_facts_cases}/{total_cases} cases with unrecorded facts)")
        print("--------------------------------------------------------")

        return {
            "suite": "summary",
            "dataset": dataset_name,
            "total_cases": total_cases,
            "unrecorded_facts_cases": unrecorded_facts_cases,
            "working_bar_met": working_bar_met,
            "failing_rows": failing_rows,
            "results": results
        }
    finally:
        db.close()


if __name__ == "__main__":
    is_large = "--large" in sys.argv
    run_summary_suite(large=is_large)
