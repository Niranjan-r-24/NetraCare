import os
import sys
import pytest
from datetime import datetime, date, time
from unittest.mock import patch, MagicMock

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, Base, engine, ensure_schema_updates
from app.models import Patient, Appointment, Doctor, UrgentCase
from app.seeder import seed_database
from app.services.llm import LLMService, RedFlagOutput, EMERGENCY_RESPONSE_TEXT, FALLBACK_FACT, CAVEAT_TEXT, SUMMARY_DISCLAIMER_TEXT
from app.services.rules_engine import ClinicRulesEngine
from app.schemas import VisitTypeEnum

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    ensure_schema_updates(engine)
    db = SessionLocal()
    db.query(UrgentCase).delete()
    db.commit()
    seed_database(db, seed_appointments=True)
    db.close()
    yield

def patient_auth(p_id="P01", name="Asha Verma"):
    return {"X-Role": "patient", "X-User-Id": p_id, "X-User-Name": name}

def doctor_auth(d_id="D3", name="Dr. Shah"):
    return {"X-Role": "doctor", "X-User-Id": d_id, "X-User-Name": name}

staff_auth = {"X-Role": "staff", "X-User-Id": "STAFF_01", "X-User-Name": "Receptionist"}

# ============================================================================
# R1 Tests: Data Pack 2 Ingestion & Follow-up Eligibility
# ============================================================================
def test_r1_data_pack_2_ingested():
    db = SessionLocal()
    try:
        # Check patient profiles populated
        p1 = db.query(Patient).filter(Patient.patient_id == "P01").first()
        assert p1 is not None
        assert "Type 2 diabetes" in p1.general_health
        assert p1.allergies == "None known"

        p3 = db.query(Patient).filter(Patient.patient_id == "P03").first()
        assert p3 is not None
        assert "High blood pressure" in p3.general_health
        assert "Sulfa" in p3.allergies

        # Check Asha Verma (P01) past visits (V001, V002, V003)
        past_v = db.query(Appointment).filter(
            Appointment.patient_id == "P01",
            Appointment.status == "completed"
        ).all()
        assert len(past_v) >= 3

        # Verify Asha Verma can book a Retina follow-up with Dr. Shah (D3)
        val = ClinicRulesEngine.validate_booking(
            db=db,
            doctor_id="D3",
            speciality="Retina",
            visit_type=VisitTypeEnum.follow_up,
            appt_date=date(2026, 11, 23), # A Monday AM session
            start_t=time(10, 0),
            patient_id="P01",
            clock_override=datetime(2026, 11, 2, 10, 0, 0)
        )
        assert val.allowed is True, f"Asha Verma should be eligible for Retina follow-up with Dr. Shah: {val.message}"
    finally:
        db.close()

# ============================================================================
# R2 Tests: Doctor Notes Required for Completion
# ============================================================================
def test_r2_doctor_note_required():
    db = SessionLocal()
    try:
        # Book an appointment for test
        appt = Appointment(
            appointment_id="TEST_COMP_01",
            patient_id="P04",
            doctor_id="D3",
            speciality="Retina",
            visit_type="new",
            appointment_date=date(2026, 11, 23),
            start_time=time(11, 0),
            end_time=time(11, 20),
            status="booked",
            reason="Follow-up diabetic scan"
        )
        db.merge(appt)
        db.commit()

        # 1. Attempt completion with empty note -> Refused 400
        res_empty = client.post(
            "/api/v1/appointments/TEST_COMP_01/complete",
            headers=doctor_auth("D3"),
            json={"doctor_note": "   "}
        )
        assert res_empty.status_code == 400

        # 2. Complete with clinical note -> Success
        res_ok = client.post(
            "/api/v1/appointments/TEST_COMP_01/complete",
            headers=doctor_auth("D3"),
            json={"doctor_note": "Fundus examination normal. VA 6/6 OU. Follow-up in 12 months."}
        )
        assert res_ok.status_code == 200
        data = res_ok.json()
        assert data["status"] == "completed"
        assert data["doctor_note"] == "Fundus examination normal. VA 6/6 OU. Follow-up in 12 months."
    finally:
        db.close()

# ============================================================================
# R3 Tests: Required Appointment Reason
# ============================================================================
def test_r3_appointment_reason_required():
    # 1. Booking without reason is refused 400
    res_no_reason = client.post(
        "/api/v1/appointments",
        headers=patient_auth("P04"),
        json={
            "doctor_id": "D3",
            "speciality": "Retina",
            "visit_type": "new",
            "date": "2026-11-23",
            "start_time": "11:20",
            "reason": ""
        }
    )
    assert res_no_reason.status_code == 400

    # 2. Booking with reason over 300 characters is refused (422 Pydantic schema validation or 400)
    long_reason = "A" * 305
    res_long = client.post(
        "/api/v1/appointments",
        headers=patient_auth("P04"),
        json={
            "doctor_id": "D3",
            "speciality": "Retina",
            "visit_type": "new",
            "date": "2026-11-23",
            "start_time": "11:20",
            "reason": long_reason
        }
    )
    assert res_long.status_code in (400, 422)

# ============================================================================
# R4 Tests: Red-Flag Check & Emergency Response & Urgent Cases
# ============================================================================
@patch.object(LLMService, "check_red_flags")
def test_r4_red_flag_booking_success(mock_red_flag):
    # Mock LLM detecting severe pain
    mock_red_flag.return_value = RedFlagOutput(
        red_flag=True,
        category="severe_pain_headache_haloes",
        why="Severe throbbing eye pain with nausea"
    )

    db = SessionLocal()
    # Ensure P11 has no active booked appointments in Retina
    db.query(Appointment).filter(
        Appointment.patient_id == "P11",
        Appointment.speciality == "Retina",
        Appointment.status == "booked"
    ).delete()
    # Ensure slot is free
    db.query(Appointment).filter(
        Appointment.doctor_id == "D3",
        Appointment.appointment_date == date(2026, 11, 25),
        Appointment.start_time == time(10, 20)
    ).delete()
    db.commit()
    db.close()

    res = client.post(
        "/api/v1/appointments",
        headers=patient_auth("P11"),
        json={
            "doctor_id": "D3",
            "speciality": "Retina",
            "visit_type": "new",
            "date": "2026-11-25",
            "start_time": "10:20",
            "reason": "Severe eye pain with headache and I feel sick"
        }
    )
    assert res.status_code == 201, f"Expected 201 Created, got {res.status_code}: {res.text}"
    data = res.json()
    assert data["is_urgent"] is True
    assert data["emergency_message"] == EMERGENCY_RESPONSE_TEXT

    # Check urgent case was persisted in DB
    db = SessionLocal()
    try:
        uc = db.query(UrgentCase).filter(UrgentCase.patient_id == "P11", UrgentCase.is_seen == False).first()
        assert uc is not None
        assert uc.category == "severe_pain_headache_haloes"
    finally:
        db.close()

@patch.object(LLMService, "check_red_flags")
def test_r4_red_flag_retained_when_booking_refused(mock_red_flag):
    # Book with Dr. Rao on Thursday morning (Surgery Session -> Refused)
    mock_red_flag.return_value = RedFlagOutput(
        red_flag=True,
        category="sudden_vision_loss",
        why="Sudden darkness in left eye"
    )

    res = client.post(
        "/api/v1/appointments",
        headers=patient_auth("P08"),
        json={
            "doctor_id": "D1", # Dr. Rao
            "speciality": "Cataract",
            "visit_type": "new",
            "date": "2026-11-26", # Thursday AM
            "start_time": "10:00",
            "reason": "Everything went dark in my right eye an hour ago"
        }
    )
    # Booking must be refused due to SURGERY_SESSION
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert detail["reason_code"] == "SURGERY_SESSION"
    assert detail["emergency_message"] == EMERGENCY_RESPONSE_TEXT

    # CRITICAL: Urgent case must STILL be recorded in DB!
    db = SessionLocal()
    try:
        uc = db.query(UrgentCase).filter(UrgentCase.patient_id == "P08", UrgentCase.is_seen == False).order_by(UrgentCase.id.desc()).first()
        assert uc is not None
        assert uc.category == "sudden_vision_loss"
    finally:
        db.close()

def test_r4_staff_view_and_mark_seen():
    # Staff can list urgent cases
    res = client.get("/api/v1/urgent-cases", headers=staff_auth)
    assert res.status_code == 200
    cases = res.json()
    assert len(cases) > 0
    first_id = cases[0]["id"]

    # Mark as seen
    res_seen = client.post(f"/api/v1/urgent-cases/{first_id}/seen", headers=staff_auth)
    assert res_seen.status_code == 200
    assert res_seen.json()["is_seen"] is True

# ============================================================================
# R5 Tests: Fact of the Day
# ============================================================================
def test_r5_fact_of_the_day():
    res = client.get("/api/v1/fact-of-the-day")
    assert res.status_code == 200
    data = res.json()
    assert "fact" in data and len(data["fact"]) > 10
    assert data["caveat"] == CAVEAT_TEXT

    # Refresh test with previous param
    res_refresh = client.get(f"/api/v1/fact-of-the-day?previous={data['fact']}")
    assert res_refresh.status_code == 200
    assert res_refresh.json()["caveat"] == CAVEAT_TEXT

# ============================================================================
# R6 Tests: Doctor Clinical Summary & RBAC
# ============================================================================
def test_r6_patient_cannot_access_summary():
    # Patients cannot access summary endpoint (403)
    res = client.get("/api/v1/doctor/patients/P03/summary", headers=patient_auth("P03"))
    assert res.status_code == 403

def test_r6_doctor_summary_structure():
    # Doctor accessing Lakshmi Nair (P03)
    res = client.get("/api/v1/doctor/patients/P03/summary", headers=doctor_auth("D2"))
    assert res.status_code == 200
    data = res.json()
    assert data["patient_id"] == "P03"
    assert data["patient_name"] == "Lakshmi Nair"
    assert data["allergies"] == "Sulfa drugs"
    assert data["disclaimer"] == SUMMARY_DISCLAIMER_TEXT
    assert "past_notes" in data
    assert len(data["past_notes"]) >= 3
    # Ensure notes are present below summary
    notes_docs = [n["doctor_id"] for n in data["past_notes"]]
    assert "D2" in notes_docs and "D1" in notes_docs

def test_r6_patient_with_no_past_visits():
    # Aditya Bose (P20) has no previous visits in data pack 2
    res = client.get("/api/v1/doctor/patients/P20/summary", headers=doctor_auth("D1"))
    assert res.status_code == 200
    data = res.json()
    assert data["patient_id"] == "P20"
    assert len(data["past_notes"]) == 0
