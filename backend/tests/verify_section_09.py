import sys
import os
from datetime import datetime, date, time, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, Base, engine
from app.seeder import seed_database
from app.models import Appointment
from app.services.llm import LLMService, RedFlagOutput
from unittest.mock import patch

def run_section_09_checks():
    client = TestClient(app)
    db = SessionLocal()
    # Clear appointments and re-seed with fresh appointments seed for test baseline
    db.query(Appointment).delete()
    db.commit()
    seed_database(db, seed_appointments=True)
    db.close()

    print("=" * 60)
    print("RUNNING NETRACARE HANDOUT SECTION 09 VERIFICATION CHECKS")
    print("=" * 60)

    # Patient auth headers helper
    def patient_auth(p_id, name="Patient"):
        return {"X-Role": "patient", "X-User-Id": p_id, "X-User-Name": name}

    # Staff auth headers helper
    staff_auth = {"X-Role": "staff", "X-User-Id": "STAFF_01", "X-User-Name": "Receptionist"}

    passed = 0
    total = 13

    # Patch LLMService red flags to return non-red flag for routine checks during rule verification
    with patch.object(LLMService, "check_red_flags", return_value=RedFlagOutput(red_flag=False, category=None, why="Routine check")):
        # Check 1: Book a new consultation with a free doctor in OPD -> Booked, 20 minutes
        # Wed 2026-11-18, Dr. Rao (D1), General, 09:40
        res = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P20"),
            json={"doctor_id": "D1", "speciality": "General", "visit_type": "new", "date": "2026-11-18", "start_time": "09:40", "reason": "Routine eye check"}
        )
        assert res.status_code == 201, f"Check 1 failed: {res.text}"
        data = res.json()
        assert data["start_time"] == "09:40" and data["end_time"] == "10:00"
        c1_appt_id = data["appointment_id"]
        print("[PASS] Check 1: Booked 20-min new consultation with free OPD doctor (09:40-10:00).")
        passed += 1

        # Check 2: Book the same doctor and time again for another patient -> Refused: slot taken
        res2 = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P21"),
            json={"doctor_id": "D1", "speciality": "General", "visit_type": "new", "date": "2026-11-18", "start_time": "09:40", "reason": "Routine checkup"}
        )
        assert res2.status_code == 409 and res2.json()["detail"]["reason_code"] == "DOUBLE_BOOKED"
        print("[PASS] Check 2: Double booking correctly refused with DOUBLE_BOOKED.")
        passed += 1

        # Check 3: Book Dr. Rao on a Thursday morning -> Refused: surgery session
        res3 = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P22"),
            json={"doctor_id": "D1", "speciality": "Cataract", "visit_type": "new", "date": "2026-11-19", "start_time": "10:00", "reason": "Cataract consultation"}
        )
        assert res3.status_code == 400 and res3.json()["detail"]["reason_code"] == "SURGERY_SESSION"
        print("[PASS] Check 3: Dr. Rao Thursday AM booking refused with SURGERY_SESSION.")
        passed += 1

        # Check 4: Book Dr. Iyer on any Thursday -> Refused: doctor not at the clinic
        res4 = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P22"),
            json={"doctor_id": "D2", "speciality": "Glaucoma", "visit_type": "new", "date": "2026-11-19", "start_time": "10:00", "reason": "Glaucoma review"}
        )
        assert res4.status_code == 400 and res4.json()["detail"]["reason_code"] == "DOCTOR_OFF"
        print("[PASS] Check 4: Dr. Iyer Thursday booking refused with DOCTOR_OFF.")
        passed += 1

        # Check 5: Book at 1:30 PM (lunch), Sunday, or holiday -> Refused
        # 5a: Lunch 13:30
        res5a = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P22"),
            json={"doctor_id": "D1", "speciality": "General", "visit_type": "new", "date": "2026-11-18", "start_time": "13:30", "reason": "Routine checkup"}
        )
        assert res5a.status_code == 400 and res5a.json()["detail"]["reason_code"] == "OUTSIDE_SESSION"
        # 5b: Sunday 2026-11-22
        res5b = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P22"),
            json={"doctor_id": "D1", "speciality": "General", "visit_type": "new", "date": "2026-11-22", "start_time": "10:00", "reason": "Routine checkup"}
        )
        assert res5b.status_code == 400 and res5b.json()["detail"]["reason_code"] == "CLINIC_CLOSED"
        # 5c: Holiday 2026-11-24 (Staff training day)
        res5c = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P22"),
            json={"doctor_id": "D1", "speciality": "General", "visit_type": "new", "date": "2026-11-24", "start_time": "10:00", "reason": "Routine checkup"}
        )
        assert res5c.status_code == 400 and res5c.json()["detail"]["reason_code"] == "HOLIDAY"
        print("[PASS] Check 5: Lunch (OUTSIDE_SESSION), Sunday (CLINIC_CLOSED), and holiday (HOLIDAY) refused.")
        passed += 1

        # Check 6: Book a new consultation at 12:50 PM -> Refused: would end after 1 PM
        res6 = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P22"),
            json={"doctor_id": "D1", "speciality": "General", "visit_type": "new", "date": "2026-11-18", "start_time": "12:50", "reason": "Routine checkup"}
        )
        assert res6.status_code == 400 and res6.json()["detail"]["reason_code"] == "ENDS_AFTER_SESSION"
        print("[PASS] Check 6: 12:50 PM new consultation refused with ENDS_AFTER_SESSION.")
        passed += 1

        # Check 7: Book more than 30 days ahead, or in the past -> Refused
        past_d = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        res7a = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P22"),
            json={"doctor_id": "D1", "speciality": "General", "visit_type": "new", "date": past_d, "start_time": "10:00", "reason": "Routine checkup"}
        )
        assert res7a.status_code == 400 and res7a.json()["detail"]["reason_code"] == "IN_PAST"

        future_d = (date.today() + timedelta(days=35)).strftime("%Y-%m-%d")
        res7b = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P22"),
            json={"doctor_id": "D1", "speciality": "General", "visit_type": "new", "date": future_d, "start_time": "10:00", "reason": "Routine checkup"}
        )
        assert res7b.status_code == 400 and res7b.json()["detail"]["reason_code"] == "BEYOND_30_DAYS"
        print("[PASS] Check 7: Past booking (IN_PAST) and >30 days (BEYOND_30_DAYS) refused.")
        passed += 1

        # Check 8: Book Dr. Khan for Glaucoma -> Refused: doctor doesn't cover it
        res8 = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P22"),
            json={"doctor_id": "D4", "speciality": "Glaucoma", "visit_type": "new", "date": "2026-11-18", "start_time": "10:00", "reason": "Glaucoma test"}
        )
        assert res8.status_code == 400 and res8.json()["detail"]["reason_code"] == "SPECIALITY_MISMATCH"
        print("[PASS] Check 8: Specialty mismatch correctly refused with SPECIALITY_MISMATCH.")
        passed += 1

        # Check 9: Book a second Cataract appointment for a patient who has one -> Refused: active booking exists
        # Seed data has A101 for P01 in Cataract
        res9 = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P01"),
            json={"doctor_id": "D2", "speciality": "Cataract", "visit_type": "new", "date": "2026-11-18", "start_time": "10:00", "reason": "Second Cataract consultation"}
        )
        assert res9.status_code == 409 and res9.json()["detail"]["reason_code"] == "ACTIVE_BOOKING_EXISTS"
        print("[PASS] Check 9: Second Cataract booking refused with ACTIVE_BOOKING_EXISTS.")
        passed += 1

        # Check 10: Book a follow-up for a patient never seen, or with a different doctor -> Refused
        # 10a: P17 never seen for General
        res10a = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P17"),
            json={"doctor_id": "D1", "speciality": "General", "visit_type": "follow_up", "date": "2026-11-18", "start_time": "10:00", "reason": "Follow up consultation"}
        )
        assert res10a.status_code == 400 and res10a.json()["detail"]["reason_code"] == "NO_PREVIOUS_VISIT"

        # 10b: P18 completed Cataract with Dr. Rao (A006), tries Dr. Iyer
        res10b = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P18"),
            json={"doctor_id": "D2", "speciality": "Cataract", "visit_type": "follow_up", "date": "2026-11-18", "start_time": "10:00", "reason": "Follow up consultation"}
        )
        assert res10b.status_code == 400 and res10b.json()["detail"]["reason_code"] == "FOLLOW_UP_DIFFERENT_DOCTOR"
        print("[PASS] Check 10: Follow-up rules (NO_PREVIOUS_VISIT & FOLLOW_UP_DIFFERENT_DOCTOR) enforced.")
        passed += 1

        # Check 11: As a patient, cancel an appointment that starts in under 2 hours -> Refused: to_staff
        # In test context with seed appointments, A103 is at 11:00 on 2026-11-02 (P03).
        # We can create a quick appointment for P23 at datetime.now() + 1 hour to test dynamically.
        now = datetime.now()
        near_time = (now + timedelta(minutes=45)).strftime("%H:%M")
        # Using direct DB creation for a near-future appointment to test cancellation
        db2 = SessionLocal()
        near_appt = Appointment(
            appointment_id="A999",
            patient_id="P23",
            doctor_id="D1",
            speciality="General",
            visit_type="new",
            appointment_date=now.date(),
            start_time=(now + timedelta(minutes=45)).time(),
            end_time=(now + timedelta(minutes=65)).time(),
            status="booked"
        )
        db2.add(near_appt)
        db2.commit()
        db2.close()

        res11 = client.post("/api/v1/appointments/A999/cancel", headers=patient_auth("P23"))
        assert res11.status_code == 403 and res11.json()["detail"]["reason_code"] == "INSIDE_2_HOURS"
        print("[PASS] Check 11: Late patient cancellation (<2 hrs) refused with INSIDE_2_HOURS.")
        passed += 1

        # Check 12: As Staff, cancel that same appointment -> Cancelled
        res12 = client.post("/api/v1/appointments/A999/cancel", headers=staff_auth)
        assert res12.status_code == 200 and res12.json()["status"] == "cancelled"
        print("[PASS] Check 12: Staff override successfully cancelled appointment within 2 hours.")
        passed += 1

        # Check 13: Cancel a booking, then book that slot as someone else -> Booked: slot is free again
        res13a = client.post(f"/api/v1/appointments/{c1_appt_id}/cancel", headers=patient_auth("P20"))
        assert res13a.status_code == 200 and res13a.json()["status"] == "cancelled"
        # Now P21 books the exact same slot (2026-11-18, D1, General, 09:40)
        res13b = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P21"),
            json={"doctor_id": "D1", "speciality": "General", "visit_type": "new", "date": "2026-11-18", "start_time": "09:40", "reason": "General checkup"}
        )
        assert res13b.status_code == 201, f"Check 13 booking failed: {res13b.text}"
        print("[PASS] Check 13: Slot was released upon cancellation and booked by another patient.")
        passed += 1

    print("=" * 60)
    print(f"RESULT: ALL {passed}/{total} HANDOUT SECTION 09 CHECKS PASSED PERFECTLY!")
    print("=" * 60)

if __name__ == "__main__":
    run_section_09_checks()
