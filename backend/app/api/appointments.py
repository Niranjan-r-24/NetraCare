from datetime import datetime, date, time
from typing import List, Optional
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Appointment, Patient, Doctor, UrgentCase, StaffApproval
from app.schemas import (
    AppointmentCreate, AppointmentReschedule, AppointmentOut, CompleteAppointmentRequest,
    RoleEnum, ReasonCodeEnum
)
from app.api.deps import CurrentUser, get_current_user
from app.services.rules_engine import ClinicRulesEngine
from app.services.llm import LLMService, EMERGENCY_RESPONSE_TEXT, RED_FLAG_FAILURE_MESSAGE

logger = logging.getLogger("netracare.api.appointments")

router = APIRouter(prefix="/appointments", tags=["Appointments"])

def generate_next_appointment_id(db: Session) -> str:
    appts = db.query(Appointment.appointment_id).all()
    max_num = 0
    for (a_id,) in appts:
        if a_id.startswith("A") and a_id[1:].isdigit():
            num = int(a_id[1:])
            if num > max_num:
                max_num = num
    next_num = max_num + 1
    return f"A{next_num:03d}"

def map_appointment_to_out(appt: Appointment, db: Session, emergency_msg: Optional[str] = None, outcome: Optional[str] = None) -> AppointmentOut:
    patient = db.query(Patient).filter(Patient.patient_id == appt.patient_id).first()
    doctor = db.query(Doctor).filter(Doctor.doctor_id == appt.doctor_id).first()
    
    pending_appr = db.query(StaffApproval).filter(
        StaffApproval.appointment_id == appt.appointment_id,
        StaffApproval.status == "pending"
    ).first()
    approval_status = f"{pending_appr.action_type}_pending" if pending_appr else None

    return AppointmentOut(
        appointment_id=appt.appointment_id,
        patient_id=appt.patient_id,
        patient_name=patient.name if patient else appt.patient_id,
        doctor_id=appt.doctor_id,
        doctor_name=doctor.name if doctor else appt.doctor_id,
        speciality=appt.speciality,
        visit_type=appt.visit_type,
        appointment_date=appt.appointment_date,
        start_time=appt.start_time.strftime("%H:%M"),
        end_time=appt.end_time.strftime("%H:%M"),
        status=appt.status,
        reason=appt.reason,
        doctor_note=appt.doctor_note,
        is_urgent=bool(appt.is_urgent),
        emergency_message=emergency_msg,
        approval_status=approval_status,
        outcome=outcome,
        source=getattr(appt, "source", "Website") or "Website",
        intake_notes=getattr(appt, "intake_notes", None),
        created_at=appt.created_at
    )

@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(
    req: AppointmentCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # RBAC on patient identity
    if current_user.role == RoleEnum.patient:
        patient_id = current_user.user_id
    elif current_user.role == RoleEnum.staff:
        if not req.patient_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="patient_id is required when booking as staff."
            )
        patient_id = req.patient_id
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Doctors cannot create appointments directly."
        )

    # Verify patient exists
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found.")

    # R3: Mandatory appointment reason
    reason_str = (req.reason or "").strip()
    if not reason_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Appointment reason is required (up to 300 characters)."}
        )
    if len(reason_str) > 300:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Appointment reason must not exceed 300 characters."}
        )

    # R4: Red-flag check with LLM before clinic rules
    try:
        red_flag_res = LLMService.check_red_flags(reason_str)
    except Exception as e:
        logger.error(f"Red flag check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": RED_FLAG_FAILURE_MESSAGE}
        )

    is_urgent = False
    emergency_msg = None
    urgent_case = None

    if red_flag_res.red_flag:
        is_urgent = True
        emergency_msg = EMERGENCY_RESPONSE_TEXT
        # Persist urgent case immediately
        urgent_case = UrgentCase(
            patient_id=patient_id,
            reason=reason_str,
            category=red_flag_res.category or "urgent",
            why=red_flag_res.why,
            is_seen=False
        )
        db.add(urgent_case)
        db.commit()
        db.refresh(urgent_case)

    try:
        start_t = datetime.strptime(req.start_time.strip(), "%H:%M").time()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"reason_code": ReasonCodeEnum.INVALID_START_TIME, "message": "Time format must be HH:MM"}
        )

    # Run unified clinic rules check
    val = ClinicRulesEngine.validate_booking(
        db=db,
        doctor_id=req.doctor_id,
        speciality=req.speciality,
        visit_type=req.visit_type,
        appt_date=req.date,
        start_t=start_t,
        patient_id=patient_id,
        role=current_user.role
    )

    if not val.allowed:
        http_status = status.HTTP_400_BAD_REQUEST
        if val.reason_code in (ReasonCodeEnum.DOUBLE_BOOKED, ReasonCodeEnum.ACTIVE_BOOKING_EXISTS):
            http_status = status.HTTP_409_CONFLICT
        elif val.reason_code == ReasonCodeEnum.INVALID_START_TIME:
            http_status = status.HTTP_422_UNPROCESSABLE_ENTITY

        detail_payload = {
            "reason_code": val.reason_code,
            "outcome": val.outcome,
            "message": val.message
        }
        if emergency_msg:
            detail_payload["emergency_message"] = emergency_msg
            detail_payload["urgent_case_id"] = urgent_case.id if urgent_case else None

        raise HTTPException(
            status_code=http_status,
            detail=detail_payload
        )

    end_t = ClinicRulesEngine.calculate_end_time(start_t, req.visit_type)
    new_id = generate_next_appointment_id(db)
    
    booking_source = req.source if req.source else ("Staff" if current_user.role == RoleEnum.staff else "Website")

    appt = Appointment(
        appointment_id=new_id,
        patient_id=patient_id,
        doctor_id=req.doctor_id,
        speciality=req.speciality,
        visit_type=req.visit_type.value,
        appointment_date=req.date,
        start_time=start_t,
        end_time=end_t,
        status="booked",
        reason=reason_str,
        is_urgent=is_urgent,
        source=booking_source,
        intake_notes=req.intake_notes
    )
    db.add(appt)
    if urgent_case:
        urgent_case.appointment_id = new_id
    db.commit()
    db.refresh(appt)

    return map_appointment_to_out(appt, db, emergency_msg=emergency_msg)

@router.get("", response_model=List[AppointmentOut])
def list_appointments(
    date: Optional[date] = None,
    doctor_id: Optional[str] = None,
    patient_id: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Appointment)

    # RBAC Scoping
    if current_user.role == RoleEnum.patient:
        # Brief Section 07 / R3: Patients only ever see their own appointments
        query = query.filter(Appointment.patient_id == current_user.user_id)
    elif current_user.role == RoleEnum.doctor:
        # Doctors see their own assigned appointments
        query = query.filter(Appointment.doctor_id == current_user.user_id)
        if date:
            query = query.filter(Appointment.appointment_date == date)
    elif current_user.role == RoleEnum.staff:
        # Staff can inspect any appointment with filters
        if patient_id:
            query = query.filter(Appointment.patient_id == patient_id)
        if doctor_id:
            query = query.filter(Appointment.doctor_id == doctor_id)
        if date:
            query = query.filter(Appointment.appointment_date == date)

    # Order by date and time
    appts = query.order_by(Appointment.appointment_date.asc(), Appointment.start_time.asc()).all()
    return [map_appointment_to_out(a, db) for a in appts]

@router.post("/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel_appointment(
    appointment_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    appt = db.query(Appointment).filter(Appointment.appointment_id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    val = ClinicRulesEngine.validate_cancellation(
        db=db,
        appointment=appt,
        acting_role=current_user.role,
        acting_patient_id=current_user.user_id if current_user.role == RoleEnum.patient else None
    )

    if not val.allowed:
        if val.reason_code == ReasonCodeEnum.INSIDE_2_HOURS and current_user.role == RoleEnum.patient:
            # R1: Inside 2 hours late cancellation creates StaffApproval and returns to_staff
            existing_appr = db.query(StaffApproval).filter(
                StaffApproval.appointment_id == appt.appointment_id,
                StaffApproval.status == "pending"
            ).first()
            if not existing_appr:
                new_appr = StaffApproval(
                    appointment_id=appt.appointment_id,
                    patient_id=appt.patient_id,
                    action_type="cancel",
                    status="pending",
                    reason=val.message
                )
                db.add(new_appr)
                db.commit()
            return map_appointment_to_out(appt, db, outcome="to_staff")

        http_status = status.HTTP_400_BAD_REQUEST
        if val.reason_code == ReasonCodeEnum.NOT_YOUR_APPOINTMENT:
            http_status = status.HTTP_403_FORBIDDEN
        elif val.reason_code == ReasonCodeEnum.INSIDE_2_HOURS:
            http_status = status.HTTP_403_FORBIDDEN

        raise HTTPException(
            status_code=http_status,
            detail={
                "reason_code": val.reason_code,
                "outcome": val.outcome,
                "message": val.message
            }
        )

    appt.status = "cancelled"
    db.commit()
    db.refresh(appt)

    return map_appointment_to_out(appt, db)

@router.post("/{appointment_id}/complete", response_model=AppointmentOut)
def complete_appointment(
    appointment_id: str,
    req: CompleteAppointmentRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    appt = db.query(Appointment).filter(Appointment.appointment_id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Only assigned doctor or staff can complete
    if current_user.role == RoleEnum.doctor and appt.doctor_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only complete visits assigned to you."
        )
    if current_user.role == RoleEnum.patient:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Patients cannot mark visits completed."
        )

    # R2: Required doctor note
    note = (req.doctor_note or "").strip()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A clinical doctor note is required to mark a visit completed."
        )

    if appt.status != "booked":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot complete appointment with status '{appt.status}'."
        )

    appt.status = "completed"
    appt.doctor_note = note
    db.commit()
    db.refresh(appt)

    return map_appointment_to_out(appt, db)

@router.post("/{appointment_id}/reschedule", response_model=AppointmentOut)
def reschedule_appointment(
    appointment_id: str,
    req: AppointmentReschedule,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    appt = db.query(Appointment).filter(Appointment.appointment_id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    try:
        new_start_t = datetime.strptime(req.start_time.strip(), "%H:%M").time()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"reason_code": ReasonCodeEnum.INVALID_START_TIME, "message": "Time format must be HH:MM"}
        )

    val = ClinicRulesEngine.validate_reschedule(
        db=db,
        appointment=appt,
        new_doctor_id=req.doctor_id,
        new_speciality=req.speciality,
        new_visit_type=req.visit_type,
        new_date=req.date,
        new_start_time=new_start_t,
        acting_role=current_user.role,
        acting_patient_id=current_user.user_id if current_user.role == RoleEnum.patient else None
    )

    if not val.allowed:
        if val.reason_code == ReasonCodeEnum.INSIDE_2_HOURS and current_user.role == RoleEnum.patient:
            # R1: Inside 2 hours late reschedule creates StaffApproval with proposed replacement slot and returns to_staff
            new_end_t = ClinicRulesEngine.calculate_end_time(new_start_t, req.visit_type)
            existing_appr = db.query(StaffApproval).filter(
                StaffApproval.appointment_id == appt.appointment_id,
                StaffApproval.status == "pending"
            ).first()
            if not existing_appr:
                new_appr = StaffApproval(
                    appointment_id=appt.appointment_id,
                    patient_id=appt.patient_id,
                    action_type="reschedule",
                    new_doctor_id=req.doctor_id,
                    new_speciality=req.speciality,
                    new_visit_type=req.visit_type.value,
                    new_date=req.date,
                    new_start_time=new_start_t,
                    new_end_time=new_end_t,
                    status="pending",
                    reason=val.message
                )
                db.add(new_appr)
                db.commit()
            return map_appointment_to_out(appt, db, outcome="to_staff")

        http_status = status.HTTP_400_BAD_REQUEST
        if val.reason_code in (ReasonCodeEnum.DOUBLE_BOOKED, ReasonCodeEnum.ACTIVE_BOOKING_EXISTS):
            http_status = status.HTTP_409_CONFLICT
        elif val.reason_code in (ReasonCodeEnum.NOT_YOUR_APPOINTMENT, ReasonCodeEnum.INSIDE_2_HOURS):
            http_status = status.HTTP_403_FORBIDDEN
        elif val.reason_code == ReasonCodeEnum.INVALID_START_TIME:
            http_status = status.HTTP_422_UNPROCESSABLE_ENTITY

        raise HTTPException(
            status_code=http_status,
            detail={
                "reason_code": val.reason_code,
                "outcome": val.outcome,
                "message": val.message
            }
        )

    # Atomic update
    new_end_t = ClinicRulesEngine.calculate_end_time(new_start_t, req.visit_type)
    appt.doctor_id = req.doctor_id
    appt.speciality = req.speciality
    appt.visit_type = req.visit_type.value
    appt.appointment_date = req.date
    appt.start_time = new_start_t
    appt.end_time = new_end_t
    appt.status = "booked"

    db.commit()
    db.refresh(appt)

    return map_appointment_to_out(appt, db)
