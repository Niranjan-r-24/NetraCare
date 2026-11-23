import os
import sys
import csv
import pytest
from datetime import datetime, date, time
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, Appointment
from app.seeder import seed_database
from app.schemas import RoleEnum, VisitTypeEnum, ReasonCodeEnum
from app.services.rules_engine import ClinicRulesEngine

# Test Database and Fixed Clock
TEST_DB_URL = "sqlite:///:memory:"
CLINIC_FIXED_NOW = datetime(2026, 11, 2, 10, 0, 0)

@pytest.fixture
def test_db():
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    # Seed with appointments_seed.csv
    seed_database(db, seed_appointments=True)
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)

def load_rule_tests():
    data_path = Path(__file__).resolve().parent.parent.parent / "docs" / "data" / "rule_tests.csv"
    cases = []
    with open(data_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cases.append(row)
    return cases

@pytest.mark.parametrize("case", load_rule_tests(), ids=[c["test_id"] for c in load_rule_tests()])
def test_rule_case(test_db, case):
    test_id = case["test_id"]
    action = case["action"].strip()
    role = RoleEnum(case["role"].strip())
    acting_patient_id = case["acting_patient_id"].strip() if case["acting_patient_id"] else None
    appointment_id = case["appointment_id"].strip() if case["appointment_id"] else None
    doctor_id = case["doctor_id"].strip() if case["doctor_id"] else None
    speciality = case["speciality"].strip() if case["speciality"] else None
    visit_type = VisitTypeEnum(case["visit_type"].strip()) if case["visit_type"] else None
    
    appt_date = datetime.strptime(case["date"].strip(), "%Y-%m-%d").date() if case["date"] else None
    start_t = datetime.strptime(case["start_time"].strip(), "%H:%M").time() if case["start_time"] else None
    expected = case["expected"].strip()  # allowed, refused, to_staff
    expected_reason = case["reason_code"].strip() if case["reason_code"] else None

    if action == "book":
        res = ClinicRulesEngine.validate_booking(
            db=test_db,
            doctor_id=doctor_id,
            speciality=speciality,
            visit_type=visit_type,
            appt_date=appt_date,
            start_t=start_t,
            patient_id=acting_patient_id,
            role=role,
            clock_override=CLINIC_FIXED_NOW
        )
        assert res.outcome == expected, f"[{test_id}] Expected outcome '{expected}', got '{res.outcome}' ({res.message})"
        if expected_reason:
            assert res.reason_code.value == expected_reason, f"[{test_id}] Expected reason '{expected_reason}', got '{res.reason_code}'"

    elif action == "cancel":
        appt = test_db.query(Appointment).filter(Appointment.appointment_id == appointment_id).first()
        res = ClinicRulesEngine.validate_cancellation(
            db=test_db,
            appointment=appt,
            acting_role=role,
            acting_patient_id=acting_patient_id,
            clock_override=CLINIC_FIXED_NOW
        )
        assert res.outcome == expected, f"[{test_id}] Expected outcome '{expected}', got '{res.outcome}' ({res.message})"
        if expected_reason:
            assert res.reason_code.value == expected_reason, f"[{test_id}] Expected reason '{expected_reason}', got '{res.reason_code}'"

    elif action == "reschedule":
        appt = test_db.query(Appointment).filter(Appointment.appointment_id == appointment_id).first()
        res = ClinicRulesEngine.validate_reschedule(
            db=test_db,
            appointment=appt,
            new_doctor_id=doctor_id,
            new_speciality=speciality,
            new_visit_type=visit_type,
            new_date=appt_date,
            new_start_time=start_t,
            acting_role=role,
            acting_patient_id=acting_patient_id,
            clock_override=CLINIC_FIXED_NOW
        )
        assert res.outcome == expected, f"[{test_id}] Expected outcome '{expected}', got '{res.outcome}' ({res.message})"
        if expected_reason:
            assert res.reason_code.value == expected_reason, f"[{test_id}] Expected reason '{expected_reason}', got '{res.reason_code}'"
