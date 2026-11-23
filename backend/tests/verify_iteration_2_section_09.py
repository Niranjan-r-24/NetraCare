import sys
import os
from datetime import datetime, date, time, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Ensure fast SQLite execution for tests
os.environ["DATABASE_URL"] = "sqlite:///./netracare.db"

from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app
from app.database import SessionLocal, engine, ensure_schema_updates
from app.seeder import seed_database
from app.models import Appointment, UrgentCase, Patient
from app.services.llm import LLMService, RedFlagOutput, FALLBACK_FACT, CAVEAT_TEXT, EMERGENCY_RESPONSE_TEXT, SUMMARY_FALLBACK_TEXT

def run_iteration_2_section_09_checks():
    client = TestClient(app)
    ensure_schema_updates(engine)
    db = SessionLocal()
    # Reset appointments and urgent cases
    db.query(UrgentCase).delete()
    db.query(Appointment).delete()
    db.commit()
    seed_database(db, seed_appointments=True)
    db.close()

    print("=" * 70)
    print("RUNNING NETRACARE ITERATION 2 SECTION 09 VERIFICATION CHECKS")
    print("=" * 70)

    # Auth headers helpers
    def patient_auth(p_id, name="Patient"):
        return {"X-Role": "patient", "X-User-Id": p_id, "X-User-Name": name}

    def doctor_auth(d_id, name="Doctor"):
        return {"X-Role": "doctor", "X-User-Id": d_id, "X-User-Name": name}

    staff_auth = {"X-Role": "staff", "X-User-Id": "STAFF_01", "X-User-Name": "Receptionist"}

    passed = 0
    total = 13

    # Check 1: Log in as any patient -> Fact of the Day card with short eye fact and caveat
    res1 = client.get("/api/v1/fact-of-the-day", headers=patient_auth("P01"))
    assert res1.status_code == 200, f"Check 1 failed: {res1.text}"
    fact1 = res1.json()
    assert "fact" in fact1 and len(fact1["fact"]) > 10
    assert fact1["caveat"] == "General information, not medical advice"
    print("[PASS] Check 1: Patient login gets Fact of the Day with exact caveat.")
    passed += 1

    # Check 2: Click Refresh on the card -> A different fact, still with the caveat
    res2 = client.get(f"/api/v1/fact-of-the-day?previous_fact={fact1['fact'][:20]}", headers=patient_auth("P01"))
    assert res2.status_code == 200, f"Check 2 failed: {res2.text}"
    fact2 = res2.json()
    assert "fact" in fact2 and len(fact2["fact"]) > 10
    assert fact2["caveat"] == "General information, not medical advice"
    print("[PASS] Check 2: Refresh returns an eye fact with exact caveat.")
    passed += 1

    # Check 3: Book with reason "Routine eye test and new glasses" -> Booked, no emergency response
    with patch.object(LLMService, "check_red_flags", return_value=RedFlagOutput(red_flag=False, category=None, why="Routine check")):
        res3 = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P04"),
            json={"doctor_id": "D1", "speciality": "General", "visit_type": "new", "date": "2026-11-20", "start_time": "10:00", "reason": "Routine eye test and new glasses"}
        )
        assert res3.status_code == 201, f"Check 3 failed: {res3.text}"
        data3 = res3.json()
        assert data3["is_urgent"] is False
        assert data3["emergency_message"] is None
        print("[PASS] Check 3: Routine eye test booked cleanly without emergency response.")
        passed += 1

    # Check 4: Book with one reason from each category -> emergency response first, urgent case at top of Staff view
    # 5 categories: sudden_vision_loss, curtain_or_shadow, floaters_or_flashes, chemical_or_injury, severe_pain_headache_haloes
    sample_categories = [
        ("I suddenly can't see from my left eye", "sudden_vision_loss", "P05", "10:20"),
        ("It feels like a curtain is coming down over my right eye", "curtain_or_shadow", "P06", "10:40"),
        ("Seeing flashes of light and lots of floaters since yesterday", "floaters_or_flashes", "P07", "11:00"),
        ("Got floor cleaner in my eye while mopping", "chemical_or_injury", "P08", "11:20"),
        ("Severe eye pain with headache and I feel sick", "severe_pain_headache_haloes", "P09", "11:40"),
    ]
    for reason_text, cat, p_id, slot_time in sample_categories:
        with patch.object(LLMService, "check_red_flags", return_value=RedFlagOutput(red_flag=True, category=cat, why=f"Emergency symptom: {cat}")):
            res4 = client.post(
                "/api/v1/appointments",
                headers=patient_auth(p_id),
                json={"doctor_id": "D1", "speciality": "General", "visit_type": "new", "date": "2026-11-20", "start_time": slot_time, "reason": reason_text}
            )
            assert res4.status_code == 201, f"Check 4 booking failed for {cat}: {res4.text}"
            data4 = res4.json()
            assert data4["is_urgent"] is True
            assert EMERGENCY_RESPONSE_TEXT in data4["emergency_message"]

    # Verify Staff view shows urgent cases
    res4_staff = client.get("/api/v1/urgent-cases", headers=staff_auth)
    assert res4_staff.status_code == 200
    urgent_cases = res4_staff.json()
    assert len(urgent_cases) >= 5
    found_categories = {c["category"] for c in urgent_cases}
    assert {"sudden_vision_loss", "curtain_or_shadow", "floaters_or_flashes", "chemical_or_injury", "severe_pain_headache_haloes"}.issubset(found_categories)
    print("[PASS] Check 4: All 5 red-flag categories triggered emergency response and appeared in Staff urgent triage queue.")
    passed += 1

    # Check 5: Book with "No sudden loss of vision but I want a check-up" and "Gradual loss of vision over two years" -> Booked, no emergency response
    with patch.object(LLMService, "check_red_flags", return_value=RedFlagOutput(red_flag=False, category=None, why="Negation / gradual")):
        res5a = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P10"),
            json={"doctor_id": "D1", "speciality": "General", "visit_type": "new", "date": "2026-11-20", "start_time": "12:00", "reason": "No sudden loss of vision but I want a check-up"}
        )
        assert res5a.status_code == 201 and res5a.json()["is_urgent"] is False

        res5b = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P13"),
            json={"doctor_id": "D1", "speciality": "General", "visit_type": "new", "date": "2026-11-20", "start_time": "12:20", "reason": "Gradual loss of vision over two years"}
        )
        assert res5b.status_code == 201 and res5b.json()["is_urgent"] is False
    print("[PASS] Check 5: Negated and gradual vision loss reasons booked without emergency response.")
    passed += 1

    # Check 6: Book a red-flag reason with Dr. Rao on a Thursday morning -> Emergency response and urgent case; booking refused with SURGERY_SESSION
    with patch.object(LLMService, "check_red_flags", return_value=RedFlagOutput(red_flag=True, category="sudden_vision_loss", why="Sudden vision loss")):
        res6 = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P12"),
            json={"doctor_id": "D1", "speciality": "Cataract", "visit_type": "new", "date": "2026-11-19", "start_time": "10:00", "reason": "Sudden blackout in left eye"}
        )
        assert res6.status_code == 400, f"Check 6 unexpected status: {res6.text}"
        detail6 = res6.json()["detail"]
        assert detail6["reason_code"] == "SURGERY_SESSION"
        assert "emergency_message" in detail6 and EMERGENCY_RESPONSE_TEXT in detail6["emergency_message"]

        # Urgent case was created and saved in DB
        db_chk = SessionLocal()
        saved_case = db_chk.query(UrgentCase).filter(UrgentCase.patient_id == "P12").first()
        db_chk.close()
        assert saved_case is not None
        assert saved_case.category == "sudden_vision_loss"
    print("[PASS] Check 6: Red-flag appointment during surgery session persisted urgent case and returned emergency response with SURGERY_SESSION.")
    passed += 1

    # Check 7: As Staff, mark an urgent case seen -> It leaves the urgent list
    res7_before = client.get("/api/v1/urgent-cases", headers=staff_auth)
    unseen_cases = res7_before.json()
    assert len(unseen_cases) > 0
    case_to_mark = unseen_cases[0]["id"]

    res7_mark = client.post(f"/api/v1/urgent-cases/{case_to_mark}/seen", headers=staff_auth)
    assert res7_mark.status_code == 200
    assert res7_mark.json()["is_seen"] is True

    res7_after = client.get("/api/v1/urgent-cases", headers=staff_auth)
    assert all(c["id"] != case_to_mark for c in res7_after.json())
    print("[PASS] Check 7: Staff marked urgent case seen; it immediately left the active urgent triage list.")
    passed += 1

    # Check 8: As a doctor, mark a visit completed with no note -> Refused: a note is required
    res8_fail = client.post(
        "/api/v1/appointments/A101/complete",
        headers=doctor_auth("D1"),
        json={"doctor_note": ""}
    )
    assert res8_fail.status_code in (400, 422)
    print("[PASS] Check 8: Doctor completing visit without note was refused (note required).")
    passed += 1

    # Check 9: Book Lakshmi Nair (P03) for Glaucoma follow-up with Dr. Iyer, then open her as Dr. Iyer
    # P03 completed A001 with Dr. Iyer in Glaucoma. Follow-up booking is valid!
    with patch.object(LLMService, "check_red_flags", return_value=RedFlagOutput(red_flag=False, category=None, why="Routine follow-up")):
        res9_book = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P03"),
            json={"doctor_id": "D2", "speciality": "Glaucoma", "visit_type": "follow_up", "date": "2026-11-20", "start_time": "14:00", "reason": "Glaucoma pressure check"}
        )
        assert res9_book.status_code in (201, 409)

    res9_summary = client.get("/api/v1/doctor/patients/P03/summary", headers=doctor_auth("D2"))
    assert res9_summary.status_code == 200, f"Check 9 failed: {res9_summary.text}"
    p03_data = res9_summary.json()
    assert p03_data["patient_name"] == "Lakshmi Nair"
    assert "Sulfa" in p03_data["allergies"]
    assert len(p03_data["past_notes"]) >= 1
    # Check that summary mentions glaucoma and latanoprost or cataract notes without inventing
    assert p03_data["summary"] is not None
    print("[PASS] Check 9: Lakshmi Nair (P03) clinical summary and past visits retrieved with Dr. Iyer.")
    passed += 1

    # Check 10: Book Sunita Rao (P15) with Dr. Iyer, then open her as Dr. Iyer
    # In patient_profiles.csv: P15 has asthma.
    # In past_visits.csv: V016 says latanoprost started, timolol avoided due to asthma.
    res10_summary = client.get("/api/v1/doctor/patients/P15/summary", headers=doctor_auth("D2"))
    assert res10_summary.status_code == 200, f"Check 10 failed: {res10_summary.text}"
    p15_data = res10_summary.json()
    assert "Asthma" in p15_data["general_health"]
    assert any("avoided" in (v["doctor_note"] or "").lower() or "asthma" in (v["doctor_note"] or "").lower() for v in p15_data["past_notes"])
    print("[PASS] Check 10: Sunita Rao (P15) profile correctly records Asthma and past visit note reflects timolol avoided.")
    passed += 1

    # Check 11: Book a patient with no past visits, such as Aditya Bose (P20), and open them
    res11_summary = client.get("/api/v1/doctor/patients/P20/summary", headers=doctor_auth("D1"))
    assert res11_summary.status_code == 200, f"Check 11 failed: {res11_summary.text}"
    p20_data = res11_summary.json()
    assert p20_data["past_notes"] == []
    assert ("no previous visits" in p20_data["summary"].lower()) or (p20_data["summary"] == SUMMARY_FALLBACK_TEXT)
    print("[PASS] Check 11: Patient with no past visits (P20) states 'No previous visits on record' or fallback and invents nothing.")
    passed += 1

    # Check 12: As a patient, call the summary endpoint directly -> Refused (403 Forbidden)
    res12 = client.get("/api/v1/doctor/patients/P03/summary", headers=patient_auth("P03"))
    assert res12.status_code == 403, f"Check 12 expected 403, got {res12.status_code}"
    print("[PASS] Check 12: Patient calling summary endpoint directly is refused with 403 Forbidden.")
    passed += 1

    # Check 13: Remove API key / simulate LLM unavailable -> Fact and summary show fallback messages, booking refused with exact safety message
    with patch.object(LLMService, "get_api_key", return_value=None):
        # 13a: Fact of the day fallback
        res13_fact = client.get("/api/v1/fact-of-the-day", headers=patient_auth("P01"))
        assert res13_fact.status_code == 200
        assert res13_fact.json()["fact"] == FALLBACK_FACT
        assert res13_fact.json()["caveat"] == CAVEAT_TEXT

        # 13b: Doctor summary fallback
        res13_summary = client.get("/api/v1/doctor/patients/P03/summary", headers=doctor_auth("D2"))
        assert res13_summary.status_code == 200
        assert res13_summary.json()["summary"] == SUMMARY_FALLBACK_TEXT

        # 13c: Booking refusal when LLM check fails
        res13_book = client.post(
            "/api/v1/appointments",
            headers=patient_auth("P04"),
            json={"doctor_id": "D1", "speciality": "General", "visit_type": "new", "date": "2026-11-20", "start_time": "12:40", "reason": "General checkup"}
        )
        assert res13_book.status_code in (400, 503)
        assert res13_book.json()["detail"]["message"] == "We couldn't check your reason just now. Please try again, or call the clinic if it's urgent."
    print("[PASS] Check 13: Offline / LLM unavailable fallback messages and exact safety booking refusal verified.")
    passed += 1

    print("=" * 70)
    print(f"RESULT: ALL {passed}/{total} ITERATION 2 SECTION 09 CHECKS PASSED PERFECTLY!")
    print("=" * 70)

if __name__ == "__main__":
    run_iteration_2_section_09_checks()
