import csv
import os
import logging
from datetime import datetime, date, time
from pathlib import Path
from sqlalchemy.orm import Session
from app.config import settings
from app.database import Base, engine, SessionLocal, ensure_schema_updates
from app.models import Doctor, DoctorSpeciality, WeeklySchedule, Holiday, Patient, Appointment

logger = logging.getLogger("netracare.seeder")

def seed_database(db: Session, data_dir: str = None, seed_appointments: bool = False, iter2_data_dir: str = None):
    if not data_dir:
        data_path = settings.resolved_data_dir
    else:
        data_path = Path(data_dir)

    if not iter2_data_dir:
        iter2_data_path = settings.resolved_iter2_data_dir
    else:
        iter2_data_path = Path(iter2_data_dir)

    if not data_path.exists():
        logger.error(f"Data directory not found: {data_path}")
        return

    # Create tables and ensure schema updates
    ensure_schema_updates(engine)

    # 1. Seed Doctors & Specialities
    doctors_file = data_path / "doctors.csv"
    if doctors_file.exists():
        with open(doctors_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                d_id = row["doctor_id"].strip()
                name = row["name"].strip()
                specs = [s.strip() for s in row["specialities"].split(";") if s.strip()]
                
                doc = db.query(Doctor).filter(Doctor.doctor_id == d_id).first()
                if not doc:
                    doc = Doctor(doctor_id=d_id, name=name)
                    db.add(doc)
                    db.flush()
                else:
                    doc.name = name

                for spec in specs:
                    existing = db.query(DoctorSpeciality).filter(
                        DoctorSpeciality.doctor_id == d_id,
                        DoctorSpeciality.speciality == spec
                    ).first()
                    if not existing:
                        db.add(DoctorSpeciality(doctor_id=d_id, speciality=spec))
        db.commit()
        logger.info("Doctors and specialities loaded.")

    # 2. Seed Weekly Schedule
    schedule_file = data_path / "weekly_schedule.csv"
    if schedule_file.exists():
        with open(schedule_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                d_id = row["doctor_id"].strip()
                day = row["day"].strip()
                session = row["session"].strip()
                status = row["status"].strip()

                sched = db.query(WeeklySchedule).filter(
                    WeeklySchedule.doctor_id == d_id,
                    WeeklySchedule.day == day,
                    WeeklySchedule.session == session
                ).first()
                if not sched:
                    db.add(WeeklySchedule(doctor_id=d_id, day=day, session=session, status=status))
                else:
                    sched.status = status
        db.commit()
        logger.info("Weekly schedules loaded.")

    # 3. Seed Holidays
    holidays_file = data_path / "holidays.csv"
    if holidays_file.exists():
        with open(holidays_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                h_date = datetime.strptime(row["date"].strip(), "%Y-%m-%d").date()
                name = row["name"].strip()
                existing = db.query(Holiday).filter(Holiday.holiday_date == h_date).first()
                if not existing:
                    db.add(Holiday(holiday_date=h_date, name=name))
                else:
                    existing.name = name
        db.commit()
        logger.info("Holidays loaded.")

    # 4. Seed Patients
    patients_file = data_path / "patients.csv"
    if patients_file.exists():
        with open(patients_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                p_id = row["patient_id"].strip()
                name = row["name"].strip()
                mobile = row["mobile"].strip()
                yob = int(row["year_of_birth"].strip()) if row.get("year_of_birth") else None

                p = db.query(Patient).filter(Patient.patient_id == p_id).first()
                if not p:
                    db.add(Patient(patient_id=p_id, name=name, mobile=mobile, year_of_birth=yob))
                else:
                    p.name = name
                    p.mobile = mobile
                    p.year_of_birth = yob
        db.commit()
        logger.info("Patients loaded.")

    # 5. Optionally Seed Appointments (seed data / stretch testing)
    if seed_appointments:
        appts_file = data_path / "appointments_seed.csv"
        if appts_file.exists():
            with open(appts_file, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    a_id = row["appointment_id"].strip()
                    p_id = row["patient_id"].strip()
                    d_id = row["doctor_id"].strip()
                    spec = row["speciality"].strip()
                    v_type = row["visit_type"].strip()
                    a_date = datetime.strptime(row["date"].strip(), "%Y-%m-%d").date()
                    s_time = datetime.strptime(row["start_time"].strip(), "%H:%M").time()
                    e_time = datetime.strptime(row["end_time"].strip(), "%H:%M").time()
                    status = row["status"].strip()

                    existing = db.query(Appointment).filter(Appointment.appointment_id == a_id).first()
                    if not existing:
                        db.add(Appointment(
                            appointment_id=a_id,
                            patient_id=p_id,
                            doctor_id=d_id,
                            speciality=spec,
                            visit_type=v_type,
                            appointment_date=a_date,
                            start_time=s_time,
                            end_time=e_time,
                            status=status
                        ))
                    else:
                        existing.status = status
            db.commit()
            logger.info("Seed appointments loaded.")

    # 6. Seed Iteration 2 Patient Profiles
    profiles_file = iter2_data_path / "patient_profiles.csv" if iter2_data_path.exists() else data_path / "patient_profiles.csv"
    if not profiles_file.exists() and (data_path / "patient_profiles.csv").exists():
        profiles_file = data_path / "patient_profiles.csv"

    if profiles_file.exists():
        with open(profiles_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                p_id = row["patient_id"].strip()
                g_health = row.get("general_health", "None recorded").strip()
                allergies = row.get("allergies", "None known").strip()
                p = db.query(Patient).filter(Patient.patient_id == p_id).first()
                if p:
                    p.general_health = g_health
                    p.allergies = allergies
        db.commit()
        logger.info("Patient profiles (health & allergies) loaded.")

    # 7. Seed Iteration 2 Past Visits (Historical Completed Consultations)
    past_visits_file = iter2_data_path / "past_visits.csv" if iter2_data_path.exists() else data_path / "past_visits.csv"
    if not past_visits_file.exists() and (data_path / "past_visits.csv").exists():
        past_visits_file = data_path / "past_visits.csv"

    if past_visits_file.exists():
        with open(past_visits_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                v_id = row["visit_id"].strip()
                p_id = row["patient_id"].strip()
                d_id = row["doctor_id"].strip()
                spec = row["speciality"].strip()
                v_type = row["visit_type"].strip()
                v_date = datetime.strptime(row["date"].strip(), "%Y-%m-%d").date()
                s_time = datetime.strptime(row["start_time"].strip(), "%H:%M").time()
                e_time = datetime.strptime(row["end_time"].strip(), "%H:%M").time()
                reason = row.get("reason", "").strip()
                doc_note = row.get("doctor_note", "").strip()

                existing = db.query(Appointment).filter(Appointment.appointment_id == v_id).first()
                if not existing:
                    db.add(Appointment(
                        appointment_id=v_id,
                        patient_id=p_id,
                        doctor_id=d_id,
                        speciality=spec,
                        visit_type=v_type,
                        appointment_date=v_date,
                        start_time=s_time,
                        end_time=e_time,
                        status="completed",
                        reason=reason,
                        doctor_note=doc_note,
                        is_urgent=False
                    ))
                else:
                    existing.status = "completed"
                    existing.reason = reason
                    existing.doctor_note = doc_note
        db.commit()
        logger.info("Past visits (completed appointments) loaded.")

if __name__ == "__main__":
    import sys
    with_appts = "--with-appointments" in sys.argv
    db = SessionLocal()
    try:
        seed_database(db, seed_appointments=with_appts)
        print("Database seeding completed successfully.")
    finally:
        db.close()
