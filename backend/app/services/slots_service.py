from datetime import datetime, date, time, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models import WeeklySchedule, Holiday, Appointment
from app.schemas import VisitTypeEnum
from app.services.clock import ClockService
from app.services.rules_engine import ClinicRulesEngine, DAY_ABBR

class FreeSlotsService:

    @classmethod
    def get_available_slots(
        cls,
        db: Session,
        doctor_id: str,
        slot_date: date,
        visit_type: VisitTypeEnum,
        clock_override: Optional[datetime] = None
    ) -> List[str]:
        now = ClockService.now(clock_override)

        # Basic calendar guards
        if slot_date.weekday() == 6:  # Sunday
            return []
        
        days_ahead = (slot_date - now.date()).days
        if days_ahead < 0 or days_ahead > 30:
            return []

        # Check holiday
        if db.query(Holiday).filter(Holiday.holiday_date == slot_date).first():
            return []

        # Check doctor schedule for AM and PM
        day_str = DAY_ABBR[slot_date.weekday()]
        am_sched = db.query(WeeklySchedule).filter(
            WeeklySchedule.doctor_id == doctor_id,
            WeeklySchedule.day == day_str,
            WeeklySchedule.session == "AM"
        ).first()
        pm_sched = db.query(WeeklySchedule).filter(
            WeeklySchedule.doctor_id == doctor_id,
            WeeklySchedule.day == day_str,
            WeeklySchedule.session == "PM"
        ).first()

        am_available = am_sched and am_sched.status == "OPD"
        pm_available = pm_sched and pm_sched.status == "OPD"

        if not am_available and not pm_available:
            return []

        # Fetch all booked appointments for doctor on this date
        booked_appts = db.query(Appointment).filter(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == slot_date,
            Appointment.status == "booked"
        ).all()

        duration_mins = 20 if visit_type == VisitTypeEnum.new else 10
        available_slots = []

        # Generate AM candidates (09:00 - 13:00)
        if am_available:
            curr = datetime.combine(slot_date, time(9, 0))
            am_limit = datetime.combine(slot_date, time(13, 0))
            while curr + timedelta(minutes=duration_mins) <= am_limit:
                slot_t = curr.time()
                end_t = (curr + timedelta(minutes=duration_mins)).time()
                # Check if in past
                if curr >= now:
                    # Check overlap with booked
                    overlap = any(
                        max(b.start_time, slot_t) < min(b.end_time, end_t)
                        for b in booked_appts
                    )
                    if not overlap:
                        available_slots.append(slot_t.strftime("%H:%M"))
                curr += timedelta(minutes=10)

        # Generate PM candidates (14:00 - 18:00)
        if pm_available:
            curr = datetime.combine(slot_date, time(14, 0))
            pm_limit = datetime.combine(slot_date, time(18, 0))
            while curr + timedelta(minutes=duration_mins) <= pm_limit:
                slot_t = curr.time()
                end_t = (curr + timedelta(minutes=duration_mins)).time()
                if curr >= now:
                    overlap = any(
                        max(b.start_time, slot_t) < min(b.end_time, end_t)
                        for b in booked_appts
                    )
                    if not overlap:
                        available_slots.append(slot_t.strftime("%H:%M"))
                curr += timedelta(minutes=10)

        return available_slots
