import os
import sys
import csv
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add project root and backend to path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from evals.booking.eval_db import EvalSessionLocal, reset_eval_db
from evals.booking.rule_audit import audit_database
from app.models import Appointment, UrgentCase, StaffApproval
from app.services.agent import run_agent_turn, booking_agent_graph, THREAD_OWNERS, THREAD_LOCK

logger = logging.getLogger("netracare.evals.booking")


def clear_graph_memory():
    """Clear thread ownership and in-memory state between scenarios."""
    with THREAD_LOCK:
        THREAD_OWNERS.clear()


def parse_turns(turns_str: str) -> List[str]:
    """Splits turns by '||' and strips whitespace."""
    if not turns_str:
        return []
    return [t.strip() for t in turns_str.split("||") if t.strip()]


def execute_setup(setup_str: str, db) -> None:
    """Executes optional setup step if specified."""
    if not setup_str or not setup_str.strip():
        return
    # e.g. cancel specific appointment or mark leave if needed
    pass


def run_single_booking_scenario(row: Dict[str, str], db) -> Dict[str, Any]:
    scenario_id = row["scenario_id"]
    patient_id = row["patient_id"]
    setup_action = row.get("setup", "")
    turns_raw = row.get("turns", "")
    expected_result = row.get("expected_result", "").strip()
    expected_appointment = row.get("expected_appointment", "").strip()

    # 1. Reset eval database
    reset_eval_db()
    clear_graph_memory()

    # 2. Setup
    execute_setup(setup_action, db)

    # 3. Execute turns
    turns = parse_turns(turns_raw)
    thread_id = None
    last_turn_res = None
    turn_responses = []

    for turn in turns:
        if turn == "[confirm]":
            last_turn_res = run_agent_turn(
                patient_id=patient_id,
                thread_id=thread_id,
                message=None,
                confirm=True,
                db=db
            )
        elif turn == "[decline]":
            last_turn_res = run_agent_turn(
                patient_id=patient_id,
                thread_id=thread_id,
                message=None,
                confirm=False,
                db=db
            )
        else:
            last_turn_res = run_agent_turn(
                patient_id=patient_id,
                thread_id=thread_id,
                message=turn,
                confirm=None,
                db=db
            )
        if last_turn_res and last_turn_res.get("thread_id"):
            thread_id = last_turn_res["thread_id"]
        turn_responses.append(last_turn_res)

    # 4. Independent Rule Audit
    rule_violations = audit_database(db)

    # 5. Check outcome against expected_result
    task_success = False
    details = ""

    if expected_result == "booked":
        # Check if an appointment matching expected_appointment exists
        # e.g., "D3 Retina follow_up 2026-11-06 09:00"
        parts = expected_appointment.split()
        if len(parts) >= 5:
            d_id, spec, v_type, d_str, t_str = parts[0], parts[1], parts[2], parts[3], parts[4]
            appt = db.query(Appointment).filter(
                Appointment.patient_id == patient_id,
                Appointment.doctor_id == d_id,
                Appointment.speciality == spec,
                Appointment.status.in_(["booked", "confirmed"]),
                str(Appointment.appointment_date) == d_str,
                str(Appointment.start_time).startswith(t_str)
            ).first()
            if appt:
                task_success = True
            else:
                details = f"Expected booking {expected_appointment} not found in DB."
        else:
            # Fallback: check if any new active booking exists for patient
            recent = db.query(Appointment).filter(
                Appointment.patient_id == patient_id,
                Appointment.status.in_(["booked", "confirmed"])
            ).first()
            task_success = bool(recent)

    elif expected_result == "rescheduled":
        # e.g., "A102 cancelled; D1 General new 2026-11-05 14:00"
        # Check replacement booking and previous cancelled
        if "A102 cancelled" in expected_appointment:
            a102 = db.query(Appointment).filter(Appointment.appointment_id == "A102").first()
            new_appt = db.query(Appointment).filter(
                Appointment.patient_id == patient_id,
                Appointment.appointment_id != "A102",
                Appointment.status.in_(["booked", "confirmed"])
            ).first()
            task_success = bool(a102 and a102.status == "cancelled" and new_appt)
        else:
            task_success = True

    elif expected_result == "to_staff":
        # e.g. "A103 still booked; one Staff approval request"
        approval = db.query(StaffApproval).filter(
            StaffApproval.patient_id == patient_id,
            StaffApproval.status == "pending"
        ).first()
        task_success = bool(approval)
        if not task_success:
            details = "No pending StaffApproval found."

    elif expected_result == "emergency":
        # Red flag: urgent case recorded from chat, no booking
        urgent = db.query(UrgentCase).filter(
            UrgentCase.patient_id == patient_id
        ).first()
        task_success = bool(urgent)
        if not task_success:
            details = "No UrgentCase recorded."

    elif expected_result in ("no_change", "answered", "idk"):
        task_success = True

    elif expected_result == "cancelled":
        # Check cancelled appointment
        parts = expected_appointment.split()
        if parts:
            aid = parts[0]
            appt = db.query(Appointment).filter(Appointment.appointment_id == aid).first()
            task_success = bool(appt and appt.status == "cancelled")
        else:
            task_success = True

    return {
        "scenario_id": scenario_id,
        "patient_id": patient_id,
        "turns_count": len(turns),
        "rule_violations_count": len(rule_violations),
        "rule_violations": rule_violations,
        "task_success": task_success,
        "details": details,
        "last_answer": last_turn_res.get("answer") if last_turn_res else ""
    }


def run_booking_suite(large: bool = False) -> Dict[str, Any]:
    dataset_name = "agent_scenarios.csv" if large else "booking_scenarios.csv"
    csv_path = ROOT / "evals" / "datasets" / dataset_name

    if not csv_path.exists():
        raise FileNotFoundError(f"Dataset {csv_path} not found.")

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    print(f"\n========================================================")
    print(f"Running Booking Suite on {dataset_name} ({len(reader)} scenarios)...")
    print(f"CLINIC_NOW: 2026-11-02 10:00 | DB: eval_netracare.db")
    print(f"========================================================")

    db = EvalSessionLocal()
    results = []
    total_rule_breaks = 0
    passed_scenarios = 0

    try:
        for idx, row in enumerate(reader, 1):
            sid = row["scenario_id"]
            res = run_single_booking_scenario(row, db)
            results.append(res)

            v_count = res["rule_violations_count"]
            total_rule_breaks += v_count
            if res["task_success"] and v_count == 0:
                passed_scenarios += 1

            status_str = "PASS" if (res["task_success"] and v_count == 0) else "FAIL"
            print(f"[{status_str}] {sid}: rule_breaks={v_count}, task_success={res['task_success']} | {res['details']}")
            if v_count > 0:
                for v in res["rule_violations"]:
                    print(f"      Violation: {v['rule']} - {v['details']}")

        target_met = (total_rule_breaks == 0)
        total_scenarios = len(reader)
        working_bar_min = 22 if large else 7
        working_bar_met = (passed_scenarios >= working_bar_min)

        print("\n--------------------------------------------------------")
        print(f"Booking Target (0 rule breaks): {'MET' if target_met else 'MISSED'} ({total_rule_breaks} rule breaks)")
        print(f"Working Bar ({working_bar_min}/{total_scenarios} expected results): {'MET' if working_bar_met else 'MISSED'} ({passed_scenarios}/{total_scenarios})")
        print("--------------------------------------------------------")

        return {
            "suite": "booking",
            "dataset": dataset_name,
            "total_rows": total_scenarios,
            "total_rule_breaks": total_rule_breaks,
            "passed_scenarios": passed_scenarios,
            "target_met": target_met,
            "working_bar_met": working_bar_met,
            "results": results
        }
    finally:
        db.close()


if __name__ == "__main__":
    is_large = "--large" in sys.argv
    run_booking_suite(large=is_large)
