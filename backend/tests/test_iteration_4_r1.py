import sys
import os
import pytest
from datetime import datetime, date, time, timedelta

sys.path.insert(0, os.path.abspath("backend"))

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import get_db, SessionLocal
from app.models import Appointment, Patient, Doctor, StaffApproval
from app.services.clock import ClockService

client = TestClient(app)

def get_auth_headers(user_id: str, role: str, name: str = "Test User"):
    return {
        "X-User-Id": user_id,
        "X-Role": role,
        "X-User-Name": name
    }

@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_r1_late_cancel_creates_staff_approval(db_session: Session):
    """
    R1: Patient cancelling inside 2 hours creates StaffApproval and returns outcome='to_staff'.
    Appointment remains 'booked'.
    """
    # Create test appointment starting in 1 hour
    now = datetime.now()
    appt_date = now.date()
    start_t = (now + timedelta(hours=1)).time().replace(second=0, microsecond=0)
    end_t = (now + timedelta(hours=1, minutes=20)).time().replace(second=0, microsecond=0)

    test_appt = Appointment(
        appointment_id="TEST_LATE_01",
        patient_id="P01",
        doctor_id="D1",
        speciality="Cataract",
        visit_type="new",
        appointment_date=appt_date,
        start_time=start_t,
        end_time=end_t,
        status="booked",
        reason="Check blurry vision"
    )
    db_session.merge(test_appt)
    db_session.commit()

    # Cancel as patient
    headers = get_auth_headers("P01", "patient", "Asha Verma")
    res = client.post("/api/v1/appointments/TEST_LATE_01/cancel", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["outcome"] == "to_staff"
    assert data["approval_status"] == "cancel_pending"
    assert data["status"] == "booked"

    # Verify database state
    db_session.expire_all()
    reloaded_appt = db_session.query(Appointment).filter(Appointment.appointment_id == "TEST_LATE_01").first()
    assert reloaded_appt.status == "booked", "Appointment must remain booked until Staff approves"

    approval = db_session.query(StaffApproval).filter(
        StaffApproval.appointment_id == "TEST_LATE_01",
        StaffApproval.status == "pending"
    ).first()
    assert approval is not None
    assert approval.action_type == "cancel"
    assert approval.patient_id == "P01"

def test_r1_staff_approvals_rbac_and_listing(db_session: Session):
    """
    R1: Only Staff can list approval requests. Patients are rejected with HTTP 403.
    """
    # Patient attempt
    pat_headers = get_auth_headers("P01", "patient", "Asha Verma")
    res_pat = client.get("/api/v1/staff/approvals", headers=pat_headers)
    assert res_pat.status_code == 403

    # Staff attempt
    staff_headers = get_auth_headers("S01", "staff", "Clinic Reception")
    res_staff = client.get("/api/v1/staff/approvals?status=pending", headers=staff_headers)
    assert res_staff.status_code == 200
    approvals = res_staff.json()
    assert isinstance(approvals, list)
    assert any(a["appointment_id"] == "TEST_LATE_01" for a in approvals)

def test_r1_staff_approve_cancellation_idempotent(db_session: Session):
    """
    R1: Staff approves cancellation; appointment status becomes 'cancelled'.
    Repeat approval calls are idempotent and return HTTP 200.
    """
    staff_headers = get_auth_headers("S01", "staff", "Clinic Reception")
    approval = db_session.query(StaffApproval).filter(
        StaffApproval.appointment_id == "TEST_LATE_01",
        StaffApproval.status == "pending"
    ).first()
    assert approval is not None

    # First approve call
    res = client.post(f"/api/v1/staff/approvals/{approval.id}/approve", headers=staff_headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "approved"
    assert data["appointment"]["status"] == "cancelled"

    # Verify DB
    db_session.expire_all()
    appt = db_session.query(Appointment).filter(Appointment.appointment_id == "TEST_LATE_01").first()
    assert appt.status == "cancelled"

    # Idempotent second approve call
    res_repeat = client.post(f"/api/v1/staff/approvals/{approval.id}/approve", headers=staff_headers)
    assert res_repeat.status_code == 200
    assert res_repeat.json()["status"] == "approved"

def test_r1_late_reschedule_and_staff_approval(db_session: Session):
    """
    R1: Patient reschedules inside 2 hours -> creates StaffApproval(reschedule) with outcome='to_staff'.
    Staff approves -> appointment is atomically rescheduled to new slot.
    """
    now = datetime.now()
    appt_date = now.date()
    start_t = (now + timedelta(hours=1)).time().replace(second=0, microsecond=0)
    end_t = (now + timedelta(hours=1, minutes=20)).time().replace(second=0, microsecond=0)

    test_appt = Appointment(
        appointment_id="TEST_LATE_RESCHED_01",
        patient_id="P15",
        doctor_id="D1",
        speciality="General",
        visit_type="new",
        appointment_date=appt_date,
        start_time=start_t,
        end_time=end_t,
        status="booked",
        reason="General checkup"
    )
    db_session.merge(test_appt)
    db_session.commit()

    # Pick a future valid weekday slot (e.g. 5 days ahead)
    new_d = (now + timedelta(days=5)).date()
    while new_d.weekday() == 6:  # Skip Sunday
        new_d += timedelta(days=1)

    pat_headers = get_auth_headers("P15", "patient", "Deepak Verma")
    reschedule_payload = {
        "doctor_id": "D1",
        "speciality": "General",
        "visit_type": "new",
        "date": new_d.isoformat(),
        "start_time": "14:00"
    }

    res = client.post("/api/v1/appointments/TEST_LATE_RESCHED_01/reschedule", json=reschedule_payload, headers=pat_headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["outcome"] == "to_staff"
    assert data["approval_status"] == "reschedule_pending"
    assert data["status"] == "booked"

    # Staff inspects and approves
    staff_headers = get_auth_headers("S01", "staff", "Clinic Reception")
    approval = db_session.query(StaffApproval).filter(
        StaffApproval.appointment_id == "TEST_LATE_RESCHED_01",
        StaffApproval.status == "pending"
    ).first()
    assert approval is not None
    assert approval.action_type == "reschedule"

    res_appr = client.post(f"/api/v1/staff/approvals/{approval.id}/approve", headers=staff_headers)
    assert res_appr.status_code == 200, res_appr.text
    appr_data = res_appr.json()
    assert appr_data["status"] == "approved"
    assert appr_data["appointment"]["appointment_date"] == new_d.isoformat()
    assert appr_data["appointment"]["start_time"] == "14:00"

    # Verify DB
    db_session.expire_all()
    reloaded = db_session.query(Appointment).filter(Appointment.appointment_id == "TEST_LATE_RESCHED_01").first()
    assert reloaded.appointment_date == new_d
    assert reloaded.start_time == time(14, 0)
    assert reloaded.status == "booked"

def test_r1_staff_rejection_idempotent(db_session: Session):
    """
    R1: Staff rejects request -> status becomes 'rejected', appointment stays unchanged.
    """
    now = datetime.now()
    appt_date = now.date()
    start_t = (now + timedelta(hours=1)).time().replace(second=0, microsecond=0)
    end_t = (now + timedelta(hours=1, minutes=20)).time().replace(second=0, microsecond=0)

    test_appt = Appointment(
        appointment_id="TEST_REJECT_01",
        patient_id="P03",
        doctor_id="D1",
        speciality="Cataract",
        visit_type="new",
        appointment_date=appt_date,
        start_time=start_t,
        end_time=end_t,
        status="booked",
        reason="Blurry vision"
    )
    db_session.merge(test_appt)
    db_session.commit()

    # Patient initiates cancel inside 2h
    pat_headers = get_auth_headers("P03", "patient", "Lakshmi Nair")
    client.post("/api/v1/appointments/TEST_REJECT_01/cancel", headers=pat_headers)

    approval = db_session.query(StaffApproval).filter(
        StaffApproval.appointment_id == "TEST_REJECT_01",
        StaffApproval.status == "pending"
    ).first()
    assert approval is not None

    # Staff rejects
    staff_headers = get_auth_headers("S01", "staff", "Clinic Reception")
    res = client.post(f"/api/v1/staff/approvals/{approval.id}/reject", headers=staff_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "rejected"

    # Verify DB
    db_session.expire_all()
    appt = db_session.query(Appointment).filter(Appointment.appointment_id == "TEST_REJECT_01").first()
    assert appt.status == "booked", "Appointment must remain booked after rejection"

    # Idempotent second reject
    res_repeat = client.post(f"/api/v1/staff/approvals/{approval.id}/reject", headers=staff_headers)
    assert res_repeat.status_code == 200
    assert res_repeat.json()["status"] == "rejected"

def test_r1_staff_approval_revalidation_rejects_conflict(db_session: Session):
    """
    Safeguard 2: If replacement slot becomes double booked before Staff approves,
    approval revalidation via ClinicRulesEngine rejects the approval with HTTP 409.
    """
    now = datetime.now()
    appt_date = now.date()
    start_t = (now + timedelta(hours=1)).time().replace(second=0, microsecond=0)
    end_t = (now + timedelta(hours=1, minutes=20)).time().replace(second=0, microsecond=0)

    try:
        test_appt = Appointment(
            appointment_id="TEST_CONFLICT_01",
            patient_id="P16",
            doctor_id="D1",
            speciality="General",
            visit_type="new",
            appointment_date=appt_date,
            start_time=start_t,
            end_time=end_t,
            status="booked",
            reason="General check"
        )
        db_session.merge(test_appt)
        db_session.commit()

        # Pick a future slot
        new_d = (now + timedelta(days=6)).date()
        while new_d.weekday() == 6:  # Skip Sunday
            new_d += timedelta(days=1)

        # Patient requests reschedule inside 2h
        pat_headers = get_auth_headers("P16", "patient", "Vikas Yadav")
        reschedule_payload = {
            "doctor_id": "D1",
            "speciality": "General",
            "visit_type": "new",
            "date": new_d.isoformat(),
            "start_time": "15:00"
        }
        client.post("/api/v1/appointments/TEST_CONFLICT_01/reschedule", json=reschedule_payload, headers=pat_headers)

        approval = db_session.query(StaffApproval).filter(
            StaffApproval.appointment_id == "TEST_CONFLICT_01",
            StaffApproval.status == "pending"
        ).first()
        assert approval is not None

        # In the meantime, another patient books that exact slot (15:00 - 15:20 on new_d with D1)
        competing_appt = Appointment(
            appointment_id="COMPETING_01",
            patient_id="P17",
            doctor_id="D1",
            speciality="General",
            visit_type="new",
            appointment_date=new_d,
            start_time=time(15, 0),
            end_time=time(15, 20),
            status="booked",
            reason="Competing booking"
        )
        db_session.merge(competing_appt)
        db_session.commit()

        # Staff attempts to approve -> ClinicRulesEngine detects DOUBLE_BOOKED and rejects approval
        staff_headers = get_auth_headers("S01", "staff", "Clinic Reception")
        res_appr = client.post(f"/api/v1/staff/approvals/{approval.id}/approve", headers=staff_headers)
        assert res_appr.status_code == 409
        assert "DOUBLE_BOOKED" in res_appr.text or "overlaps" in res_appr.text

        # Verify approval status in DB became 'rejected'
        db_session.expire_all()
        reloaded_approval = db_session.query(StaffApproval).filter(StaffApproval.id == approval.id).first()
        assert reloaded_approval.status == "rejected"
        # Original appointment remains booked at original time
        reloaded_appt = db_session.query(Appointment).filter(Appointment.appointment_id == "TEST_CONFLICT_01").first()
        assert reloaded_appt.status == "booked"
        assert reloaded_appt.appointment_date == appt_date
    finally:
        db_session.query(StaffApproval).filter(StaffApproval.appointment_id.in_(["TEST_CONFLICT_01", "COMPETING_01"])).delete(synchronize_session=False)
        db_session.query(Appointment).filter(Appointment.appointment_id.in_(["TEST_CONFLICT_01", "COMPETING_01"])).delete(synchronize_session=False)
        db_session.commit()
