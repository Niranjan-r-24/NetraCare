from datetime import datetime, date, time, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from app.models import Doctor, DoctorSpeciality, WeeklySchedule, Holiday, Patient, Appointment
from app.schemas import ReasonCodeEnum, VisitTypeEnum, RoleEnum
from app.services.clock import ClockService

DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

class RuleValidationResult:
    def __init__(self, allowed: bool, outcome: str = "allowed", reason_code: Optional[ReasonCodeEnum] = None, message: str = ""):
        self.allowed = allowed
        self.outcome = outcome  # "allowed", "refused", "to_staff"
        self.reason_code = reason_code
        self.message = message

class ClinicRulesEngine:

    @staticmethod
    def calculate_end_time(start_t: time, visit_type: VisitTypeEnum) -> time:
        duration_mins = 20 if visit_type == VisitTypeEnum.new else 10
        dt = datetime.combine(date.today(), start_t) + timedelta(minutes=duration_mins)
        return dt.time()

    @classmethod
    def validate_booking(
        cls,
        db: Session,
        doctor_id: str,
        speciality: str,
        visit_type: VisitTypeEnum,
        appt_date: date,
        start_t: time,
        patient_id: str,
        role: RoleEnum = RoleEnum.patient,
        exclude_appointment_id: Optional[str] = None,
        clock_override: Optional[datetime] = None
    ) -> RuleValidationResult:
        now = ClockService.now(clock_override)

        # 1. INVALID_START_TIME: Start time must be on a 10-minute mark
        if start_t.minute % 10 != 0 or start_t.second != 0:
            return RuleValidationResult(
                allowed=False,
                outcome="refused",
                reason_code=ReasonCodeEnum.INVALID_START_TIME,
                message="Appointments must start on a 10-minute mark (e.g. 09:00, 09:10, 09:20)."
            )

        # 2. IN_PAST: Appointment start time must not be before clinic clock
        appt_dt = datetime.combine(appt_date, start_t)
        if appt_dt < now:
            return RuleValidationResult(
                allowed=False,
                outcome="refused",
                reason_code=ReasonCodeEnum.IN_PAST,
                message="Cannot book an appointment in the past."
            )

        # 3. BEYOND_30_DAYS: More than 30 days ahead from clinic date
        days_ahead = (appt_date - now.date()).days
        if days_ahead > 30:
            return RuleValidationResult(
                allowed=False,
                outcome="refused",
                reason_code=ReasonCodeEnum.BEYOND_30_DAYS,
                message=f"Appointments can only be booked up to 30 days in advance (attempted {days_ahead} days)."
            )

        # 4. CLINIC_CLOSED: Sunday
        if appt_date.weekday() == 6:  # 6 is Sunday
            return RuleValidationResult(
                allowed=False,
                outcome="refused",
                reason_code=ReasonCodeEnum.CLINIC_CLOSED,
                message="The clinic is closed on Sundays."
            )

        # 5. HOLIDAY: Listed in holidays table
        is_holiday = db.query(Holiday).filter(Holiday.holiday_date == appt_date).first()
        if is_holiday:
            return RuleValidationResult(
                allowed=False,
                outcome="refused",
                reason_code=ReasonCodeEnum.HOLIDAY,
                message=f"The clinic is closed for a holiday: {is_holiday.name}."
            )

        # 6. OUTSIDE_SESSION: Before 9 AM, during lunch (1-2 PM), or at/after 6 PM
        start_min = start_t.hour * 60 + start_t.minute
        is_am = (9 * 60 <= start_min < 13 * 60)
        is_pm = (14 * 60 <= start_min < 18 * 60)
        if not (is_am or is_pm):
            return RuleValidationResult(
                allowed=False,
                outcome="refused",
                reason_code=ReasonCodeEnum.OUTSIDE_SESSION,
                message="Start time is outside clinic operating sessions (AM: 09:00-13:00, PM: 14:00-18:00)."
            )

        # 7. ENDS_AFTER_SESSION: 20 or 10 min would extend past session boundary
        end_t = cls.calculate_end_time(start_t, visit_type)
        end_min = end_t.hour * 60 + end_t.minute
        if is_am and end_min > 13 * 60:
            return RuleValidationResult(
                allowed=False,
                outcome="refused",
                reason_code=ReasonCodeEnum.ENDS_AFTER_SESSION,
                message=f"Appointment would end at {end_t.strftime('%H:%M')}, past the 13:00 AM session boundary."
            )
        if is_pm and end_min > 18 * 60:
            return RuleValidationResult(
                allowed=False,
                outcome="refused",
                reason_code=ReasonCodeEnum.ENDS_AFTER_SESSION,
                message=f"Appointment would end at {end_t.strftime('%H:%M')}, past the 18:00 PM session boundary."
            )

        # 8. SPECIALITY_MISMATCH: Doctor covers that speciality
        doctor = db.query(Doctor).filter(Doctor.doctor_id == doctor_id).first()
        if not doctor:
            return RuleValidationResult(
                allowed=False,
                outcome="refused",
                reason_code=ReasonCodeEnum.SPECIALITY_MISMATCH,
                message="Doctor not found."
            )
        doc_specs = [s.speciality.lower() for s in doctor.specialities]
        if speciality.lower() not in doc_specs:
            return RuleValidationResult(
                allowed=False,
                outcome="refused",
                reason_code=ReasonCodeEnum.SPECIALITY_MISMATCH,
                message=f"{doctor.name} does not cover {speciality}."
            )

        # 9. DOCTOR_OFF & SURGERY_SESSION from weekly schedule
        day_str = DAY_ABBR[appt_date.weekday()]
        session_str = "AM" if is_am else "PM"
        sched = db.query(WeeklySchedule).filter(
            WeeklySchedule.doctor_id == doctor_id,
            WeeklySchedule.day == day_str,
            WeeklySchedule.session == session_str
        ).first()

        if not sched or sched.status == "OFF":
            return RuleValidationResult(
                allowed=False,
                outcome="refused",
                reason_code=ReasonCodeEnum.DOCTOR_OFF,
                message=f"{doctor.name} is off on {day_str} {session_str}."
            )
        if sched.status == "SURGERY":
            return RuleValidationResult(
                allowed=False,
                outcome="refused",
                reason_code=ReasonCodeEnum.SURGERY_SESSION,
                message=f"{doctor.name} is in surgery on {day_str} {session_str}."
            )

        # 10. Follow-up requirements
        if visit_type == VisitTypeEnum.follow_up:
            completed_visits = db.query(Appointment).filter(
                Appointment.patient_id == patient_id,
                Appointment.speciality.ilike(speciality),
                Appointment.status == "completed"
            ).order_by(Appointment.appointment_date.desc(), Appointment.start_time.desc()).all()

            if not completed_visits:
                return RuleValidationResult(
                    allowed=False,
                    outcome="refused",
                    reason_code=ReasonCodeEnum.NO_PREVIOUS_VISIT,
                    message=f"Patient has no prior completed consultation in {speciality}."
                )

            last_doctor_id = completed_visits[0].doctor_id
            if last_doctor_id != doctor_id:
                last_doc = db.query(Doctor).filter(Doctor.doctor_id == last_doctor_id).first()
                last_doc_name = last_doc.name if last_doc else last_doctor_id
                return RuleValidationResult(
                    allowed=False,
                    outcome="refused",
                    reason_code=ReasonCodeEnum.FOLLOW_UP_DIFFERENT_DOCTOR,
                    message=f"Follow-up must be with {last_doc_name}, who conducted the previous visit."
                )

        # 11. ACTIVE_BOOKING_EXISTS: Patient already has a booked appointment in that speciality
        active_booking_query = db.query(Appointment).filter(
            Appointment.patient_id == patient_id,
            Appointment.speciality.ilike(speciality),
            Appointment.status == "booked"
        )
        if exclude_appointment_id:
            active_booking_query = active_booking_query.filter(Appointment.appointment_id != exclude_appointment_id)
        
        if active_booking_query.first():
            return RuleValidationResult(
                allowed=False,
                outcome="refused",
                reason_code=ReasonCodeEnum.ACTIVE_BOOKING_EXISTS,
                message=f"Patient already has an active booked appointment for {speciality}."
            )

        # 12. DOUBLE_BOOKED: Overlaps another booked appointment with that doctor
        existing_appts_query = db.query(Appointment).filter(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == appt_date,
            Appointment.status == "booked"
        )
        if exclude_appointment_id:
            existing_appts_query = existing_appts_query.filter(Appointment.appointment_id != exclude_appointment_id)

        for existing in existing_appts_query.all():
            # Check overlap: max(start1, start2) < min(end1, end2)
            if max(existing.start_time, start_t) < min(existing.end_time, end_t):
                return RuleValidationResult(
                    allowed=False,
                    outcome="refused",
                    reason_code=ReasonCodeEnum.DOUBLE_BOOKED,
                    message=f"This time slot overlaps an existing booking ({existing.start_time.strftime('%H:%M')}-{existing.end_time.strftime('%H:%M')})."
                )

        # All checks passed!
        return RuleValidationResult(allowed=True, outcome="allowed", message="Booking is valid.")

    @classmethod
    def validate_cancellation(
        cls,
        db: Session,
        appointment: Appointment,
        acting_role: RoleEnum,
        acting_patient_id: Optional[str] = None,
        clock_override: Optional[datetime] = None
    ) -> RuleValidationResult:
        now = ClockService.now(clock_override)

        # 1. NOT_ACTIVE: Must be currently 'booked'
        if appointment.status != "booked":
            return RuleValidationResult(
                allowed=False,
                outcome="refused",
                reason_code=ReasonCodeEnum.NOT_ACTIVE,
                message=f"Appointment is already {appointment.status} and cannot be cancelled."
            )

        # 2. NOT_YOUR_APPOINTMENT: If role is patient, must own the appointment
        if acting_role == RoleEnum.patient:
            if not acting_patient_id or appointment.patient_id != acting_patient_id:
                return RuleValidationResult(
                    allowed=False,
                    outcome="refused",
                    reason_code=ReasonCodeEnum.NOT_YOUR_APPOINTMENT,
                    message="You cannot cancel an appointment belonging to another patient."
                )

            # 3. INSIDE_2_HOURS: If within 2 hours of appointment start, send to staff
            appt_dt = datetime.combine(appointment.appointment_date, appointment.start_time)
            diff = appt_dt - now
            if diff < timedelta(hours=2):
                return RuleValidationResult(
                    allowed=False,
                    outcome="to_staff",
                    reason_code=ReasonCodeEnum.INSIDE_2_HOURS,
                    message="Late cancellation within 2 hours requires Staff assistance. Please contact Staff."
                )

        # Staff can cancel anytime
        return RuleValidationResult(allowed=True, outcome="allowed", message="Cancellation permitted.")

    @classmethod
    def validate_reschedule(
        cls,
        db: Session,
        appointment: Appointment,
        new_doctor_id: str,
        new_speciality: str,
        new_visit_type: VisitTypeEnum,
        new_date: date,
        new_start_time: time,
        acting_role: RoleEnum,
        acting_patient_id: Optional[str] = None,
        clock_override: Optional[datetime] = None
    ) -> RuleValidationResult:
        # Step 1: Cancellation validation of original appointment
        cancel_result = cls.validate_cancellation(
            db=db,
            appointment=appointment,
            acting_role=acting_role,
            acting_patient_id=acting_patient_id,
            clock_override=clock_override
        )
        if not cancel_result.allowed and cancel_result.reason_code != ReasonCodeEnum.INSIDE_2_HOURS:
            return cancel_result

        # Step 2: Booking validation for new slot, excluding the current appointment from active checks
        book_result = cls.validate_booking(
            db=db,
            doctor_id=new_doctor_id,
            speciality=new_speciality,
            visit_type=new_visit_type,
            appt_date=new_date,
            start_t=new_start_time,
            patient_id=appointment.patient_id,
            role=acting_role,
            exclude_appointment_id=appointment.appointment_id,
            clock_override=clock_override
        )
        if not book_result.allowed:
            return book_result

        if not cancel_result.allowed and cancel_result.reason_code == ReasonCodeEnum.INSIDE_2_HOURS:
            return cancel_result

        return book_result
