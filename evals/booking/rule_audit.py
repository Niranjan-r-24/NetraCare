import os
import sys
import argparse
from datetime import datetime, date, time, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
from sqlalchemy.orm import Session

# Add project root and backend to path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from evals.booking.eval_db import EvalSessionLocal, reset_eval_db
from app.models import Appointment, Doctor, DoctorSpeciality, WeeklySchedule, Holiday

CLINIC_NOW = datetime(2026, 11, 2, 10, 0)

DAYS_MAP = {
    0: "Mon",
    1: "Tue",
    2: "Wed",
    3: "Thu",
    4: "Fri",
    5: "Sat",
    6: "Sun"
}

SESSION_TIMES = {
    "AM": (time(9, 0), time(13, 0)),
    "PM": (time(14, 0), time(18, 0))
}


def audit_appointment(
    appt: Appointment,
    db: Session,
    clinic_now: datetime = CLINIC_NOW
) -> List[Dict[str, Any]]:
    """
    Audits a single appointment against the 9 clinic rules independently of API code.
    Returns a list of rule violation dicts (empty if compliant).
    """
    violations = []
    a_id = appt.appointment_id
    a_date = appt.appointment_date
    s_time = appt.start_time
    e_time = appt.end_time
    d_id = appt.doctor_id
    p_id = appt.patient_id
    spec = appt.speciality
    v_type = appt.visit_type

    # Rule 1: 10-minute start mark (:00, :10, :20, :30, :40, :50)
    if s_time.minute % 10 != 0 or s_time.second != 0:
        violations.append({
            "appointment_id": a_id,
            "rule": "RULE_1_SLOT_10MIN_BOUNDARY",
            "details": f"Start time {s_time} is not aligned to a 10-minute boundary."
        })

    # Rule 4: Not on a Sunday or clinic holiday
    weekday_idx = a_date.weekday()
    if weekday_idx == 6:  # Sunday
        violations.append({
            "appointment_id": a_id,
            "rule": "RULE_4_SUNDAY_CLOSED",
            "details": f"Appointment date {a_date} is a Sunday; clinic is closed."
        })
    else:
        holiday = db.query(Holiday).filter(Holiday.holiday_date == a_date).first()
        if holiday:
            violations.append({
                "appointment_id": a_id,
                "rule": "RULE_4_CLINIC_HOLIDAY",
                "details": f"Appointment date {a_date} is a clinic holiday ({holiday.name})."
            })

    # Rule 5: Within 30 days of clinic clock
    clinic_today = clinic_now.date()
    max_date = clinic_today + timedelta(days=30)
    if a_date < clinic_today or a_date > max_date:
        violations.append({
            "appointment_id": a_id,
            "rule": "RULE_5_OUTSIDE_30_DAY_WINDOW",
            "details": f"Appointment date {a_date} is outside the 30-day booking window ({clinic_today} to {max_date})."
        })

    # Determine session from start time
    current_session = None
    if SESSION_TIMES["AM"][0] <= s_time < SESSION_TIMES["AM"][1]:
        current_session = "AM"
    elif SESSION_TIMES["PM"][0] <= s_time < SESSION_TIMES["PM"][1]:
        current_session = "PM"
    else:
        violations.append({
            "appointment_id": a_id,
            "rule": "RULE_2_OUTSIDE_OPD_HOURS",
            "details": f"Start time {s_time} is outside clinic OPD hours (09:00-13:00 or 14:00-18:00)."
        })

    # Rule 2: Inside doctor's weekly OPD session
    day_str = DAYS_MAP.get(weekday_idx)
    if current_session and day_str:
        sched = db.query(WeeklySchedule).filter(
            WeeklySchedule.doctor_id == d_id,
            WeeklySchedule.day == day_str,
            WeeklySchedule.session == current_session,
            WeeklySchedule.status == "OPD"
        ).first()
        if not sched:
            violations.append({
                "appointment_id": a_id,
                "rule": "RULE_2_DOCTOR_NOT_ON_OPD",
                "details": f"Doctor {d_id} does not have an OPD session on {day_str} {current_session}."
            })

    # Rule 3: Session boundaries (20 min for new, 10 min for follow_up; ends by session end: 1 PM or 6 PM)
    if current_session:
        session_end = SESSION_TIMES[current_session][1]
        expected_duration = 20 if (v_type or "").lower() == "new" else 10
        expected_end = (datetime.combine(date.today(), s_time) + timedelta(minutes=expected_duration)).time()
        if e_time != expected_end:
            violations.append({
                "appointment_id": a_id,
                "rule": "RULE_3_INVALID_DURATION",
                "details": f"Appointment duration must be {expected_duration} minutes for {v_type} (start: {s_time}, end: {e_time})."
            })
        if e_time > session_end:
            violations.append({
                "appointment_id": a_id,
                "rule": "RULE_3_EXCEEDS_SESSION_END",
                "details": f"Appointment ends at {e_time}, which exceeds session end {session_end}."
            })

    # Rule 6: Doctor covers the speciality
    doc_spec = db.query(DoctorSpeciality).filter(
        DoctorSpeciality.doctor_id == d_id,
        DoctorSpeciality.speciality == spec
    ).first()
    if not doc_spec:
        violations.append({
            "appointment_id": a_id,
            "rule": "RULE_6_DOCTOR_SPECIALITY_MISMATCH",
            "details": f"Doctor {d_id} does not practice speciality '{spec}'."
        })

    # Rule 7: Doctor has no overlapping active appointment
    overlapping = db.query(Appointment).filter(
        Appointment.doctor_id == d_id,
        Appointment.appointment_date == a_date,
        Appointment.appointment_id != a_id,
        Appointment.status.in_(["booked", "confirmed"]),
        Appointment.start_time < e_time,
        Appointment.end_time > s_time
    ).first()
    if overlapping:
        violations.append({
            "appointment_id": a_id,
            "rule": "RULE_7_DOCTOR_SCHEDULE_OVERLAP",
            "details": f"Doctor {d_id} has overlapping active appointment {overlapping.appointment_id} ({overlapping.start_time}-{overlapping.end_time})."
        })

    # Rule 8: Patient has at most 1 active booking per speciality
    other_active = db.query(Appointment).filter(
        Appointment.patient_id == p_id,
        Appointment.speciality == spec,
        Appointment.appointment_id != a_id,
        Appointment.status.in_(["booked", "confirmed"])
    ).first()
    if other_active:
        violations.append({
            "appointment_id": a_id,
            "rule": "RULE_8_MULTIPLE_ACTIVE_SPECIALITY_BOOKINGS",
            "details": f"Patient {p_id} already has active booking {other_active.appointment_id} for speciality '{spec}'."
        })

    # Rule 9: Follow-up continuity with previously seen doctor
    if v_type == "follow_up":
        # Check past completed visits for this patient in this speciality
        past_completed = db.query(Appointment).filter(
            Appointment.patient_id == p_id,
            Appointment.speciality == spec,
            Appointment.status == "completed"
        ).order_by(Appointment.appointment_date.desc()).first()

        if past_completed and past_completed.doctor_id != d_id:
            violations.append({
                "appointment_id": a_id,
                "rule": "RULE_9_FOLLOW_UP_DOCTOR_CONTINUITY",
                "details": f"Follow-up must be with Dr. {past_completed.doctor_id} who saw patient on {past_completed.appointment_date}, not Dr. {d_id}."
            })

    return violations


def audit_database(db: Session, clinic_now: datetime = CLINIC_NOW) -> List[Dict[str, Any]]:
    """
    Audits all active appointments currently in the database.
    Returns list of all rule breaks.
    """
    active_appts = db.query(Appointment).filter(
        Appointment.status.in_(["booked", "confirmed"])
    ).all()

    all_violations = []
    for appt in active_appts:
        v = audit_appointment(appt, db, clinic_now=clinic_now)
        if v:
            all_violations.extend(v)

    return all_violations


def test_broken_booking() -> int:
    """
    Verification test required by Section 10:
    Inserts a booking for Dr. Iyer on Thursday 5 November at 10:00 into eval_netracare.db,
    runs the rule audit, verifies the audit catches it as a rule break, and cleans up.
    """
    print("\n========================================================")
    print("Testing Rule Audit with Deliberately Broken Booking...")
    print("Scenario: Dr. Meera Iyer (D2) booked on Thursday 5 Nov at 10:00 AM")
    print("========================================================")

    reset_eval_db()
    db = EvalSessionLocal()
    test_appt_id = "BROKEN_TEST_APPT"
    try:
        # Dr. Iyer is NOT at the clinic on Thursdays
        broken_appt = Appointment(
            appointment_id=test_appt_id,
            patient_id="P20",
            doctor_id="D2",  # Dr. Meera Iyer
            speciality="Glaucoma",
            visit_type="new",
            appointment_date=date(2026, 11, 5),  # Thursday
            start_time=time(10, 0),
            end_time=time(10, 15),
            status="booked",
            reason="Test broken booking",
            is_urgent=False
        )
        db.add(broken_appt)
        db.commit()

        # Run independent audit
        violations = audit_database(db, clinic_now=CLINIC_NOW)
        broken_caught = [v for v in violations if v["appointment_id"] == test_appt_id]

        print(f"Total violations found: {len(violations)}")
        for v in broken_caught:
            print(f"  ✓ Caught violation: {v['rule']} - {v['details']}")

        if broken_caught and any(v["rule"] == "RULE_2_DOCTOR_NOT_ON_OPD" for v in broken_caught):
            print("\n✓ SUCCESS: Broken booking was properly detected and flagged by the rule audit!")
            return 0
        else:
            print("\n✗ FAILURE: Broken booking was NOT detected by the rule audit!")
            return 1
    finally:
        # Clean up test appointment
        db.query(Appointment).filter(Appointment.appointment_id == test_appt_id).delete()
        db.commit()
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Independent Appointment Rule Audit")
    parser.add_argument("--test-broken", action="store_true", help="Run verification test with deliberately broken booking")
    args = parser.parse_args()

    if args.test_broken:
        sys.exit(test_broken_booking())
    else:
        db = EvalSessionLocal()
        try:
            violations = audit_database(db)
            if violations:
                print(f"Audit FAILED: {len(violations)} rule violations found.")
                for v in violations:
                    print(f"  - Appt {v['appointment_id']}: {v['rule']} | {v['details']}")
                sys.exit(1)
            else:
                print("Audit PASSED: 0 rule violations found.")
                sys.exit(0)
        finally:
            db.close()
