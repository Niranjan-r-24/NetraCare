from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import VisitTypeEnum, FreeSlotsResponse
from app.services.slots_service import FreeSlotsService

router = APIRouter(prefix="/slots", tags=["Free Slots"])

@router.get("", response_model=FreeSlotsResponse)
def get_free_slots(
    doctor_id: str = Query(..., description="ID of the doctor (e.g. D1)"),
    date: date = Query(..., description="Target date (YYYY-MM-DD)"),
    visit_type: VisitTypeEnum = Query(..., description="new or follow_up"),
    db: Session = Depends(get_db)
):
    slots = FreeSlotsService.get_available_slots(
        db=db,
        doctor_id=doctor_id,
        slot_date=date,
        visit_type=visit_type
    )
    duration = 20 if visit_type == VisitTypeEnum.new else 10
    return FreeSlotsResponse(
        doctor_id=doctor_id,
        date=date,
        visit_type=visit_type,
        duration_minutes=duration,
        slots=slots
    )
