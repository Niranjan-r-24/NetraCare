from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import UrgentCase, Patient
from app.schemas import UrgentCaseOut, RoleEnum
from app.api.deps import CurrentUser, get_current_user

router = APIRouter(prefix="/urgent-cases", tags=["Urgent Cases"])

@router.get("", response_model=List[UrgentCaseOut])
def list_urgent_cases(
    unseen_only: bool = Query(True, description="Filter for unseen urgent cases"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != RoleEnum.staff:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only clinic staff can inspect urgent triage cases."
        )

    query = db.query(UrgentCase)
    if unseen_only:
        query = query.filter(UrgentCase.is_seen == False)

    cases = query.order_by(UrgentCase.created_at.desc()).all()
    # Priority sorting: Unseen MCP urgent cases sit at the top of the queue until marked seen
    cases.sort(key=lambda c: (
        0 if (not c.is_seen and (getattr(c, "source", None) == "MCP" or "from MCP" in (c.reason or "") or "from MCP" in (c.why or "")))
        else (1 if not c.is_seen else 2),
        -c.created_at.timestamp() if c.created_at else 0
    ))

    results = []
    for c in cases:
        p = db.query(Patient).filter(Patient.patient_id == c.patient_id).first()
        is_mcp = (getattr(c, "source", None) == "MCP" or "from MCP" in (c.reason or "") or "from MCP" in (c.why or ""))
        is_chat = ((c.appointment_id is None and not is_mcp) or (c.reason or "").startswith("[Chat]"))
        source_val = getattr(c, "source", None) or ("MCP" if is_mcp else ("Chat" if is_chat else "Appointment"))
        results.append(UrgentCaseOut(
            id=c.id,
            patient_id=c.patient_id,
            patient_name=p.name if p else c.patient_id,
            patient_mobile=p.mobile if p else None,
            appointment_id=c.appointment_id,
            reason=c.reason,
            category=c.category,
            why=c.why,
            is_seen=c.is_seen,
            created_at=c.created_at,
            seen_at=c.seen_at,
            is_chat_origin=is_chat,
            is_mcp_origin=is_mcp,
            source=source_val
        ))
    return results

@router.post("/{case_id}/seen", response_model=UrgentCaseOut)
def mark_urgent_case_seen(
    case_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != RoleEnum.staff:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only clinic staff can acknowledge urgent triage cases."
        )

    c = db.query(UrgentCase).filter(UrgentCase.id == case_id).first()
    if not c:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Urgent case not found.")

    c.is_seen = True
    c.seen_at = datetime.utcnow()
    db.commit()
    db.refresh(c)

    p = db.query(Patient).filter(Patient.patient_id == c.patient_id).first()
    is_mcp = (getattr(c, "source", None) == "MCP" or "from MCP" in (c.reason or "") or "from MCP" in (c.why or ""))
    is_chat = ((c.appointment_id is None and not is_mcp) or (c.reason or "").startswith("[Chat]"))
    source_val = getattr(c, "source", None) or ("MCP" if is_mcp else ("Chat" if is_chat else "Appointment"))
    return UrgentCaseOut(
        id=c.id,
        patient_id=c.patient_id,
        patient_name=p.name if p else c.patient_id,
        patient_mobile=p.mobile if p else None,
        appointment_id=c.appointment_id,
        reason=c.reason,
        category=c.category,
        why=c.why,
        is_seen=c.is_seen,
        created_at=c.created_at,
        seen_at=c.seen_at,
        is_chat_origin=is_chat,
        is_mcp_origin=is_mcp,
        source=source_val
    )
