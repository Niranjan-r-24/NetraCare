import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Appointment, Patient, Doctor, StaffApproval
from app.schemas import (
    SearchDebugResponse, RoleEnum, StaffApprovalOut, StaffApprovalActionResponse,
    VisitTypeEnum
)
from app.api.deps import CurrentUser, get_current_user
from app.services.rag import RAGService
from app.services.rules_engine import ClinicRulesEngine
from app.api.appointments import map_appointment_to_out

logger = logging.getLogger("netracare.api.staff")

router = APIRouter(tags=["Staff Desk"])

def map_approval_to_out(appr: StaffApproval, db: Session) -> StaffApprovalOut:
    patient = db.query(Patient).filter(Patient.patient_id == appr.patient_id).first()
    new_doc = db.query(Doctor).filter(Doctor.doctor_id == appr.new_doctor_id).first() if appr.new_doctor_id else None
    return StaffApprovalOut(
        id=appr.id,
        appointment_id=appr.appointment_id,
        patient_id=appr.patient_id,
        patient_name=patient.name if patient else appr.patient_id,
        action_type=appr.action_type,
        new_doctor_id=appr.new_doctor_id,
        new_doctor_name=new_doc.name if new_doc else None,
        new_speciality=appr.new_speciality,
        new_visit_type=appr.new_visit_type,
        new_date=appr.new_date,
        new_start_time=appr.new_start_time.strftime("%H:%M") if appr.new_start_time else None,
        new_end_time=appr.new_end_time.strftime("%H:%M") if appr.new_end_time else None,
        status=appr.status,
        reason=appr.reason,
        created_at=appr.created_at,
        reviewed_at=appr.reviewed_at,
        reviewed_by=appr.reviewed_by
    )

@router.get("/staff/search-debug", response_model=SearchDebugResponse)
@router.get("/api/v1/staff/search-debug", response_model=SearchDebugResponse)
def staff_search_debug(
    q: str = Query(..., min_length=1, description="Search query string"),
    current_user: CurrentUser = Depends(get_current_user)
):
    # RBAC: Strictly staff only
    if current_user.role != RoleEnum.staff:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only clinic staff can access the search debug interface."
        )

    clean_query = q.strip()
    results = RAGService.hybrid_search(clean_query, top_k=4)

    return SearchDebugResponse(
        query=clean_query,
        keyword_only=results["keyword_only"],
        vector_only=results["vector_only"],
        hybrid=results["hybrid"]
    )

@router.get("/staff/approvals", response_model=List[StaffApprovalOut])
@router.get("/api/v1/staff/approvals", response_model=List[StaffApprovalOut])
def list_staff_approvals(
    status_filter: Optional[str] = Query("pending", alias="status"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != RoleEnum.staff:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only clinic staff can access approval requests."
        )

    query = db.query(StaffApproval)
    if status_filter and status_filter.lower() != "all":
        query = query.filter(StaffApproval.status == status_filter.lower())
    
    approvals = query.order_by(StaffApproval.created_at.desc()).all()
    return [map_approval_to_out(a, db) for a in approvals]

@router.post("/staff/approvals/{approval_id}/approve", response_model=StaffApprovalActionResponse)
@router.post("/api/v1/staff/approvals/{approval_id}/approve", response_model=StaffApprovalActionResponse)
def approve_staff_request(
    approval_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != RoleEnum.staff:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only clinic staff can approve requests."
        )

    appr = db.query(StaffApproval).filter(StaffApproval.id == approval_id).first()
    if not appr:
        raise HTTPException(status_code=404, detail="Approval request not found.")

    # Idempotency check: if already approved
    appt = db.query(Appointment).filter(Appointment.appointment_id == appr.appointment_id).first()
    if appr.status == "approved":
        return StaffApprovalActionResponse(
            approval_id=appr.id,
            status="approved",
            message="Request is already approved.",
            appointment=map_appointment_to_out(appt, db) if appt else None
        )

    if appr.status == "rejected":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot approve a request that has already been rejected."
        )

    if not appt:
        raise HTTPException(status_code=404, detail="Target appointment not found.")

    reviewer_name = current_user.name or current_user.user_id

    # Safeguard 2: Revalidate using ClinicRulesEngine
    if appr.action_type == "cancel":
        val = ClinicRulesEngine.validate_cancellation(
            db=db,
            appointment=appt,
            acting_role=RoleEnum.staff
        )
        if not val.allowed:
            appr.status = "rejected"
            appr.reviewed_at = datetime.utcnow()
            appr.reviewed_by = reviewer_name
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot approve cancellation: {val.message}"
            )

        # Atomic commit
        appt.status = "cancelled"
        appr.status = "approved"
        appr.reviewed_at = datetime.utcnow()
        appr.reviewed_by = reviewer_name
        db.commit()
        db.refresh(appt)

        return StaffApprovalActionResponse(
            approval_id=appr.id,
            status="approved",
            message=f"Appointment {appt.appointment_id} cancellation approved successfully.",
            appointment=map_appointment_to_out(appt, db)
        )

    elif appr.action_type == "reschedule":
        visit_type_enum = VisitTypeEnum(appr.new_visit_type) if appr.new_visit_type else VisitTypeEnum.new
        val = ClinicRulesEngine.validate_reschedule(
            db=db,
            appointment=appt,
            new_doctor_id=appr.new_doctor_id,
            new_speciality=appr.new_speciality,
            new_visit_type=visit_type_enum,
            new_date=appr.new_date,
            new_start_time=appr.new_start_time,
            acting_role=RoleEnum.staff
        )
        if not val.allowed:
            appr.status = "rejected"
            appr.reviewed_at = datetime.utcnow()
            appr.reviewed_by = reviewer_name
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot approve reschedule (slot unavailable or invalid): {val.message}"
            )

        # Atomic commit
        appt.doctor_id = appr.new_doctor_id
        appt.speciality = appr.new_speciality
        appt.visit_type = appr.new_visit_type
        appt.appointment_date = appr.new_date
        appt.start_time = appr.new_start_time
        appt.end_time = appr.new_end_time
        appt.status = "booked"
        appr.status = "approved"
        appr.reviewed_at = datetime.utcnow()
        appr.reviewed_by = reviewer_name
        db.commit()
        db.refresh(appt)

        return StaffApprovalActionResponse(
            approval_id=appr.id,
            status="approved",
            message=f"Appointment {appt.appointment_id} rescheduled to {appr.new_date} {appr.new_start_time.strftime('%H:%M')} successfully.",
            appointment=map_appointment_to_out(appt, db)
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action type '{appr.action_type}'.")

@router.post("/staff/approvals/{approval_id}/reject", response_model=StaffApprovalActionResponse)
@router.post("/api/v1/staff/approvals/{approval_id}/reject", response_model=StaffApprovalActionResponse)
def reject_staff_request(
    approval_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != RoleEnum.staff:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only clinic staff can reject requests."
        )

    appr = db.query(StaffApproval).filter(StaffApproval.id == approval_id).first()
    if not appr:
        raise HTTPException(status_code=404, detail="Approval request not found.")

    # Idempotency check
    appt = db.query(Appointment).filter(Appointment.appointment_id == appr.appointment_id).first()
    if appr.status == "rejected":
        return StaffApprovalActionResponse(
            approval_id=appr.id,
            status="rejected",
            message="Request is already rejected.",
            appointment=map_appointment_to_out(appt, db) if appt else None
        )

    if appr.status == "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reject a request that has already been approved."
        )

    reviewer_name = current_user.name or current_user.user_id
    appr.status = "rejected"
    appr.reviewed_at = datetime.utcnow()
    appr.reviewed_by = reviewer_name
    db.commit()

    return StaffApprovalActionResponse(
        approval_id=appr.id,
        status="rejected",
        message=f"Request {approval_id} for appointment {appr.appointment_id} has been rejected.",
        appointment=map_appointment_to_out(appt, db) if appt else None
    )

