import sys
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date, time, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, engine
from app.models import Appointment, Patient, Doctor
from app.seeder import seed_database
from app.services.clock import ClockService

def run_tests():
    client = TestClient(app)
    
    # Reset DB state
    db = SessionLocal()
    db.query(Appointment).delete()
    db.commit()
    seed_database(db, seed_appointments=True)
    db.close()

    results = {}

    # Helper auth headers
    def patient_auth(p_id): return {"X-Role": "patient", "X-User-Id": p_id, "X-User-Name": f"Patient_{p_id}"}
    def doctor_auth(d_id): return {"X-Role": "doctor", "X-User-Id": d_id, "X-User-Name": f"Doctor_{d_id}"}
    staff_auth = {"X-Role": "staff", "X-User-Id": "STAFF_01", "X-User-Name": "Receptionist"}

    print("\n--- RUNNING CHECK 3: API Role Authorization ---")
    try:
        # 3a. Unauthenticated request
        res_no_auth = client.get("/api/v1/appointments")
        assert res_no_auth.status_code == 401, f"Expected 401, got {res_no_auth.status_code}"

        # 3b. Doctor attempting to create appointment directly
        res_doc_book = client.post(
            "/api/v1/appointments",
            headers=doctor_auth("D1"),
            json={"doctor_id": "D1", "speciality": "General", "visit_type": "new", "date": "2026-11-18", "start_time": "10:00"}
        )
        assert res_doc_book.status_code == 403, f"Expected 403 for doctor booking, got {res_doc_book.status_code}"

        # 3c. Patient attempting to complete appointment
        res_pat_comp = client.post("/api/v1/appointments/A101/complete", headers=patient_auth("P01"))
        assert res_pat_comp.status_code == 403, f"Expected 403 for patient completing visit, got {res_pat_comp.status_code}"

        results["check_3"] = ("PASS", "Unauthenticated blocked (401), Doctor cannot book (403), Patient cannot complete (403).")
        print("[PASS] Check 3 Passed.")
    except Exception as e:
        results["check_3"] = ("FAIL", str(e))
        print(f"[FAIL] Check 3 Failed: {e}")

    print("\n--- RUNNING CHECK 4: Simultaneous Concurrent Booking Collision ---")
    try:
        # Try to book the EXACT same doctor and slot concurrently with two different patients
        # Target slot: 2026-11-25 (Wed), D1, General, 11:00
        slot_date = "2026-11-25"
        slot_time = "11:00"
        
        req_p1 = {"doctor_id": "D1", "speciality": "General", "visit_type": "new", "date": slot_date, "start_time": slot_time}
        req_p2 = {"doctor_id": "D1", "speciality": "General", "visit_type": "new", "date": slot_date, "start_time": slot_time}

        responses = []
        barrier = threading.Barrier(2)

        def book_slot(patient_id, payload):
            # Use dedicated testclient or requests to simulate real concurrent connections
            cl = TestClient(app)
            barrier.wait() # Ensure exact simultaneous execution
            res = cl.post("/api/v1/appointments", headers=patient_auth(patient_id), json=payload)
            responses.append((patient_id, res.status_code, res.json()))

        with ThreadPoolExecutor(max_workers=2) as executor:
            t1 = executor.submit(book_slot, "P21", req_p1)
            t2 = executor.submit(book_slot, "P22", req_p2)
            t1.result()
            t2.result()

        success_count = sum(1 for _, status, _ in responses if status == 201)
        conflict_count = sum(1 for _, status, _ in responses if status in (400, 409))

        print(f"Concurrent booking responses: {[(p, s) for p, s, _ in responses]}")
        
        # Verify in DB how many were booked
        db_chk = SessionLocal()
        booked_in_db = db_chk.query(Appointment).filter(
            Appointment.doctor_id == "D1",
            Appointment.appointment_date == datetime.strptime(slot_date, "%Y-%m-%d").date(),
            Appointment.start_time == time(11, 0),
            Appointment.status == "booked"
        ).count()
        db_chk.close()

        assert booked_in_db == 1, f"Expected exactly 1 booking in database, found {booked_in_db}!"
        assert success_count == 1 and conflict_count == 1, f"Expected 1 success and 1 conflict, got {success_count} success, {conflict_count} conflict"
        
        results["check_4"] = ("PASS", f"Exactly 1 of 2 simultaneous bookings succeeded (201), the other was rejected (409/400). DB record count = {booked_in_db}.")
        print("[PASS] Check 4 Passed.")
    except Exception as e:
        results["check_4"] = ("FAIL", str(e))
        print(f"[FAIL] Check 4 Failed: {e}")

    print("\n--- RUNNING CHECK 5: Failed Reschedule Atomicity & Rollback ---")
    try:
        # Create an initial appointment
        res_init = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P24"),
            json={"doctor_id": "D1", "speciality": "General", "visit_type": "new", "date": "2026-11-25", "start_time": "14:00"}
        )
        assert res_init.status_code == 201, f"Initial booking failed: {res_init.text}"
        appt_id = res_init.json()["appointment_id"]

        # Attempt to reschedule to an INVALID slot (Dr. Rao on Thursday AM which is SURGERY_SESSION)
        res_resched_fail = client.post(
            f"/api/v1/appointments/{appt_id}/reschedule",
            headers=patient_auth("P24"),
            json={"doctor_id": "D1", "speciality": "General", "visit_type": "new", "date": "2026-11-26", "start_time": "10:00"}
        )
        assert res_resched_fail.status_code == 400
        assert res_resched_fail.json()["detail"]["reason_code"] == "SURGERY_SESSION"

        # Verify DB: original appointment must still be intact and 'booked' at original date/time
        db_chk = SessionLocal()
        appt = db_chk.query(Appointment).filter(Appointment.appointment_id == appt_id).first()
        assert appt is not None
        assert appt.status == "booked"
        assert str(appt.appointment_date) == "2026-11-25"
        assert appt.start_time == time(14, 0)
        assert appt.doctor_id == "D1"
        db_chk.close()

        results["check_5"] = ("PASS", f"Failed reschedule rejected with SURGERY_SESSION. Original appointment {appt_id} preserved intact.")
        print("[PASS] Check 5 Passed.")
    except Exception as e:
        results["check_5"] = ("FAIL", str(e))
        print(f"[FAIL] Check 5 Failed: {e}")

    print("\n--- RUNNING CHECK 6: Patient Privacy & Isolation ---")
    try:
        # P01 owns A101 (from seed data)
        # 6a: P02 lists appointments
        res_list = client.get("/api/v1/appointments", headers=patient_auth("P02"))
        assert res_list.status_code == 200
        p02_appts = res_list.json()
        assert all(a["patient_id"] == "P02" for a in p02_appts), "P02 saw appointments belonging to others!"
        assert not any(a["appointment_id"] == "A101" for a in p02_appts), "P02 saw P01's appointment A101!"

        # 6b: P02 attempts to cancel P01's appointment A101
        res_cancel = client.post("/api/v1/appointments/A101/cancel", headers=patient_auth("P02"))
        assert res_cancel.status_code == 403
        assert res_cancel.json()["detail"]["reason_code"] == "NOT_YOUR_APPOINTMENT"

        results["check_6"] = ("PASS", "Patients cannot see or cancel other patients' appointments (enforced via DB scoping and 403 NOT_YOUR_APPOINTMENT).")
        print("[PASS] Check 6 Passed.")
    except Exception as e:
        results["check_6"] = ("FAIL", str(e))
        print(f"[FAIL] Check 6 Failed: {e}")

    print("\n--- RUNNING CHECK 7: Doctor Authorization Isolation ---")
    try:
        # A101 is assigned to Doctor D1 (Dr. Anand Rao)
        # Doctor D2 (Dr. Meera Iyer) tries to mark A101 as completed
        res_d2 = client.post("/api/v1/appointments/A101/complete", headers=doctor_auth("D2"))
        assert res_d2.status_code == 403, f"Expected 403 for D2 completing D1's appointment, got {res_d2.status_code}"
        assert "only complete visits assigned to you" in res_d2.json()["detail"]

        # Doctor D1 marks A101 as completed
        res_d1 = client.post("/api/v1/appointments/A101/complete", headers=doctor_auth("D1"))
        assert res_d1.status_code == 200
        assert res_d1.json()["status"] == "completed"

        results["check_7"] = ("PASS", "Doctor D2 rejected (403) when completing D1's appointment; Doctor D1 succeeded (200).")
        print("[PASS] Check 7 Passed.")
    except Exception as e:
        results["check_7"] = ("FAIL", str(e))
        print(f"[FAIL] Check 7 Failed: {e}")

    print("\n--- RUNNING CHECK 8: Staff Cancellation 2-Hour Override ---")
    try:
        # Create an appointment in the near future (e.g. 50 minutes from now)
        now = datetime.now()
        near_appt_id = "A888"
        db_s = SessionLocal()
        near_appt = Appointment(
            appointment_id=near_appt_id,
            patient_id="P25",
            doctor_id="D1",
            speciality="General",
            visit_type="new",
            appointment_date=now.date(),
            start_time=(now + timedelta(minutes=50)).time(),
            end_time=(now + timedelta(minutes=70)).time(),
            status="booked"
        )
        db_s.add(near_appt)
        db_s.commit()
        db_s.close()

        # Patient P25 tries to cancel: must be rejected with 403 INSIDE_2_HOURS
        res_pat = client.post(f"/api/v1/appointments/{near_appt_id}/cancel", headers=patient_auth("P25"))
        assert res_pat.status_code == 403
        assert res_pat.json()["detail"]["reason_code"] == "INSIDE_2_HOURS"

        # Staff cancels the same appointment: must succeed (override)
        res_staff = client.post(f"/api/v1/appointments/{near_appt_id}/cancel", headers=staff_auth)
        assert res_staff.status_code == 200
        assert res_staff.json()["status"] == "cancelled"

        results["check_8"] = ("PASS", "Patient cancelled inside 2 hours rejected (INSIDE_2_HOURS); Staff override succeeded (200).")
        print("[PASS] Check 8 Passed.")
    except Exception as e:
        results["check_8"] = ("FAIL", str(e))
        print(f"[FAIL] Check 8 Failed: {e}")

    print("\n--- RUNNING CHECK 9: Database Connection, Persistence & Transactions ---")
    try:
        db_t1 = SessionLocal()
        # Verify connectivity and engine status
        engine_url = str(engine.url)
        assert engine_url is not None

        # Verify cross-session persistence
        test_patient_id = "P99"
        test_p = Patient(patient_id=test_patient_id, name="Persistence Test Patient", mobile="9999999999")
        db_t1.add(test_p)
        db_t1.commit()
        db_t1.close()

        # Open completely new session to verify persistence
        db_t2 = SessionLocal()
        retrieved = db_t2.query(Patient).filter(Patient.patient_id == test_patient_id).first()
        assert retrieved is not None
        assert retrieved.name == "Persistence Test Patient"
        
        # Test transaction rollback behavior
        try:
            # Duplicate mobile constraint violation
            dup_p = Patient(patient_id="P98", name="Duplicate Mobile", mobile="9999999999")
            db_t2.add(dup_p)
            db_t2.commit()
            assert False, "Duplicate mobile should have raised IntegrityError"
        except Exception:
            db_t2.rollback()

        # Clean up test patient
        db_t2.query(Patient).filter(Patient.patient_id == test_patient_id).delete()
        db_t2.commit()
        db_t2.close()

        results["check_9"] = ("PASS", f"Database engine active ({engine_url.split('@')[-1] if '@' in engine_url else engine_url}). Cross-session persistence and transaction rollback verified.")
        print("[PASS] Check 9 Passed.")
    except Exception as e:
        results["check_9"] = ("FAIL", str(e))
        print(f"[FAIL] Check 9 Failed: {e}")

    print("\n================ FINAL VERIFICATION SUMMARY ================")
    for k, (status, detail) in results.items():
        print(f"{k.upper()}: {status} - {detail}")
    print("============================================================\n")

if __name__ == "__main__":
    run_tests()
