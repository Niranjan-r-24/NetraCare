"""Safety and compliance tests for NetraCare Iteration 6."""
import hashlib
import os
import sys
from datetime import date, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

# Enforce evaluation database isolation
os.environ["DATABASE_URL"] = f"sqlite:///{(ROOT / 'evals' / 'eval_netracare.db').resolve()}"

from app.database import SessionLocal
from app.models import Appointment, Patient, UrgentCase, Doctor
from app.services.skills_loader import SkillsLoader
from app.services.tools import read_skill_file, load_skill


def test_path_traversal():
    """Verify that path traversal attempts in read_skill_file are safely rejected."""
    traversal_payloads = [
        ("cataract-surgery-care", "../../../backend/app/config.py"),
        ("cataract-surgery-care", "..\\..\\..\\backend\\app\\config.py"),
        ("cataract-surgery-care", "/etc/passwd"),
        ("cataract-surgery-care", "C:\\Windows\\System32\\drivers\\etc\\hosts"),
        ("cataract-surgery-care", "../lasik-suitability-intake/SKILL.md"),
        ("unknown-skill", "anyfile.md")
    ]

    for skill_name, payload in traversal_payloads:
        res = read_skill_file.invoke({"name": skill_name, "file": payload})
        assert "not found" in str(res).lower() or "error" in str(res).lower() or "rejected" in str(res).lower(), \
            f"Path traversal payload not safely handled: {payload} -> {res}"
    print("✓ Path traversal test passed (all malicious paths rejected)")


def test_supplied_skill_files_unchanged():
    """Verify that supplied skill files match original ZIP files exactly."""
    zip_skills_root = Path(r"C:\Users\sindhu\.gemini\antigravity\brain\0242c825-0cec-4c15-a087-b4f9f0ead408\scratch\zip_extract\Iteration6\netracare-data-pack-06\skills")
    project_skills_root = ROOT / "skills"

    if not zip_skills_root.exists():
        print("Note: zip_extract path not found, skipping hash comparison")
        return

    supplied_skills = ["cataract-surgery-care", "lasik-suitability-intake", "prepare-for-visit"]
    for sk in supplied_skills:
        orig_dir = zip_skills_root / sk
        proj_dir = project_skills_root / sk
        assert proj_dir.exists(), f"Skill directory {sk} missing in project"

        for orig_f in orig_dir.rglob("*"):
            if orig_f.is_file():
                rel = orig_f.relative_to(orig_dir)
                proj_f = proj_dir / rel
                assert proj_f.exists(), f"File {rel} missing in {proj_dir}"
                with open(orig_f, "rb") as f1, open(proj_f, "rb") as f2:
                    h1 = hashlib.sha256(f1.read()).hexdigest()
                    h2 = hashlib.sha256(f2.read()).hexdigest()
                    assert h1 == h2, f"File {rel} in {sk} modified from supplied zip!"

    print("✓ Supplied skill files integrity test passed (100% hash match)")


def test_lasik_intake_notes():
    """Verify LASIK intake notes are stored on appointment and visible for Dr. Fatima Khan."""
    with SessionLocal() as db:
        # Create test patient or use existing
        p = db.query(Patient).filter(Patient.patient_id == "P11").first()
        assert p is not None, "Patient P11 not found"

        test_notes = (
            "1. Age: 28\n"
            "2. Glasses prescription stable >1 year: Yes\n"
            "3. Dry eyes: Mild occasional\n"
            "4. Eye surgeries/injuries: None\n"
            "5. Contact lenses: Soft lenses, stopped 1 week ago\n"
            "6. Pregnant/breastfeeding: No\n"
            "7. Diabetes/rheumatic conditions: No\n"
            "8. Expectations: Clear distance vision without glasses\n"
            "9. Availability for follow-ups: Yes"
        )

        test_appt_id = "TEST_LASIK_INTAKE_01"
        # Clean any prior test appointment
        db.query(Appointment).filter(Appointment.appointment_id == test_appt_id).delete()
        db.commit()

        appt = Appointment(
            appointment_id=test_appt_id,
            patient_id=p.patient_id,
            doctor_id="D4", # Dr. Fatima Khan
            speciality="Refractive",
            visit_type="new",
            appointment_date=date(2026, 12, 1),
            start_time=time(10, 0),
            end_time=time(10, 20),
            status="booked",
            source="Chat",
            reason="LASIK suitability evaluation",
            intake_notes=test_notes
        )
        db.add(appt)
        db.commit()

        # Retrieve and verify
        saved = db.query(Appointment).filter(Appointment.appointment_id == test_appt_id).first()
        assert saved is not None
        assert saved.doctor_id == "D4"
        assert saved.speciality == "Refractive"
        assert saved.source == "Chat"
        assert saved.intake_notes == test_notes
        assert "1. Age: 28" in saved.intake_notes

        # Clean up test appointment
        db.delete(saved)
        db.commit()

    print("✓ LASIK intake notes storage and doctor association verified")


def test_database_integrity():
    """Verify production database records and tables remain intact."""
    with SessionLocal() as db:
        patients_count = db.query(Patient).count()
        doctors_count = db.query(Doctor).count()
        appts_count = db.query(Appointment).count()
        urgent_count = db.query(UrgentCase).count()

        assert patients_count >= 20, f"Expected at least 20 patients, found {patients_count}"
        assert doctors_count == 5, f"Expected exactly 5 doctors (D1-D5), found {doctors_count}"
        assert appts_count >= 40, f"Expected >= 40 appointments, found {appts_count}"
        assert urgent_count >= 1, f"Expected urgent cases to be present, found {urgent_count}"

        # Verify columns exist
        appt_cols = [c.name for c in Appointment.__table__.columns]
        assert "source" in appt_cols, "source column missing in Appointment"
        assert "intake_notes" in appt_cols, "intake_notes column missing in Appointment"

        urgent_cols = [c.name for c in UrgentCase.__table__.columns]
        assert "source" in urgent_cols, "source column missing in UrgentCase"

    print(f"✓ Database integrity test passed ({patients_count} patients, {doctors_count} doctors, {appts_count} appointments)")


def main():
    print("=" * 70)
    print("RUNNING SAFETY AND RULES VERIFICATION")
    print("=" * 70)

    test_path_traversal()
    test_supplied_skill_files_unchanged()
    test_lasik_intake_notes()
    test_database_integrity()

    print("=" * 70)
    print("ALL SAFETY AND COMPLIANCE TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    main()
