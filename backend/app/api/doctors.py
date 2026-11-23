from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models import Doctor, DoctorSpeciality, WeeklySchedule, Patient, Appointment
from app.schemas import (
    DoctorOut, WeeklyScheduleOut, DoctorSummaryOut, PastVisitNoteOut, RoleEnum
)
from app.api.deps import CurrentUser, get_current_user
from app.services.clock import ClockService
from app.services.llm import LLMService

router = APIRouter(tags=["Doctors & Schedules"])

@router.get("/doctors", response_model=List[DoctorOut])
def list_doctors(db: Session = Depends(get_db)):
    doctors = db.query(Doctor).all()
    result = []
    for d in doctors:
        specs = [s.speciality for s in d.specialities]
        result.append(DoctorOut(doctor_id=d.doctor_id, name=d.name, specialities=specs))
    return result

@router.get("/doctors/specialities", response_model=List[str])
def list_specialities(db: Session = Depends(get_db)):
    specs = db.query(DoctorSpeciality.speciality).distinct().all()
    return sorted([s[0] for s in specs])

@router.get("/doctors/{doctor_id}", response_model=DoctorOut)
def get_doctor(doctor_id: str, db: Session = Depends(get_db)):
    d = db.query(Doctor).filter(Doctor.doctor_id == doctor_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Doctor not found")
    specs = [s.speciality for s in d.specialities]
    return DoctorOut(doctor_id=d.doctor_id, name=d.name, specialities=specs)

@router.get("/doctors/{doctor_id}/schedule", response_model=List[WeeklyScheduleOut])
def get_doctor_schedule(doctor_id: str, db: Session = Depends(get_db)):
    schedules = db.query(WeeklySchedule).filter(WeeklySchedule.doctor_id == doctor_id).all()
    return [
        WeeklyScheduleOut(day=s.day, session=s.session, status=s.status)
        for s in schedules
    ]

@router.get("/doctor/patients/{patient_id}/summary", response_model=DoctorSummaryOut)
@router.get("/doctors/patients/{patient_id}/summary", response_model=DoctorSummaryOut)
def get_doctor_patient_summary(
    patient_id: str,
    appointment_id: Optional[str] = Query(None, description="Optional appointment ID to read today's reason"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # RBAC: Strictly restricted to doctors
    if current_user.role != RoleEnum.doctor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted: Only doctors can view clinical patient summaries."
        )

    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    # Age calculation from year_of_birth
    clinic_year = ClockService.now().year
    age = (clinic_year - patient.year_of_birth) if patient.year_of_birth else None

    # Resolve today's reason
    today_reason = None
    if appointment_id:
        today_appt = db.query(Appointment).filter(Appointment.appointment_id == appointment_id).first()
        if today_appt and today_appt.reason:
            today_reason = today_appt.reason

    if not today_reason:
        # Check if there is an active/booked appointment for this patient
        recent_appt = db.query(Appointment).filter(
            Appointment.patient_id == patient_id,
            Appointment.status == "booked"
        ).order_by(Appointment.appointment_date.desc()).first()
        if recent_appt and recent_appt.reason:
            today_reason = recent_appt.reason

    # Query completed visits across all doctors (newest first)
    completed_appts = db.query(Appointment).filter(
        Appointment.patient_id == patient_id,
        Appointment.status == "completed"
    ).order_by(Appointment.appointment_date.desc(), Appointment.start_time.desc()).all()

    visits_list = []
    past_notes_out = []
    for appt in completed_appts:
        doc = db.query(Doctor).filter(Doctor.doctor_id == appt.doctor_id).first()
        doc_name = doc.name if doc else appt.doctor_id
        visits_list.append({
            "date": str(appt.appointment_date),
            "doctor_id": appt.doctor_id,
            "doctor_name": doc_name,
            "speciality": appt.speciality,
            "reason": appt.reason,
            "doctor_note": appt.doctor_note
        })
        past_notes_out.append(PastVisitNoteOut(
            appointment_id=appt.appointment_id,
            date=appt.appointment_date,
            doctor_id=appt.doctor_id,
            doctor_name=doc_name,
            speciality=appt.speciality,
            visit_type=appt.visit_type,
            reason=appt.reason,
            doctor_note=appt.doctor_note
        ))

    summary_text = LLMService.generate_doctor_summary(
        patient_name=patient.name,
        age=age,
        general_health=patient.general_health or "None recorded",
        allergies=patient.allergies or "None known",
        today_reason=today_reason,
        completed_visits=visits_list
    )

    return DoctorSummaryOut(
        patient_id=patient.patient_id,
        patient_name=patient.name,
        age=age,
        general_health=patient.general_health or "None recorded",
        allergies=patient.allergies or "None known",
        today_reason=today_reason,
        summary=summary_text,
        disclaimer="AI summary of recorded notes. Check the notes below.",
        past_notes=past_notes_out
    )
