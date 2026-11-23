"""NetraCare MCP Server.

Provides two tools for partner applications (e.g. healthcare aggregators)
to discover free consultation slots and book new patient consultations:
  1. find_slots
  2. book_appointment

Serves over Streamable HTTP at http://localhost:8001/mcp using official FastMCP.
Reuses existing ClinicRulesEngine, slots service, red-flag triage, and database models.
"""
import os
import sys
import logging
from pathlib import Path
from datetime import datetime, date, time, timedelta
from typing import Optional, List, Dict, Any

# Ensure backend directory and project root are in sys.path
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server.fastmcp import FastMCP
from app.database import SessionLocal, ensure_schema_updates
from app.models import Doctor, DoctorSpeciality, WeeklySchedule, Holiday, Patient, Appointment, UrgentCase
from app.schemas import ReasonCodeEnum, VisitTypeEnum, RoleEnum
from app.services.clock import ClockService
from app.services.rules_engine import ClinicRulesEngine
from app.services.slots_service import FreeSlotsService
from app.services.llm import LLMService, EMERGENCY_RESPONSE_TEXT
from app.api.appointments import generate_next_appointment_id
from app.services.telemetry import track

logger = logging.getLogger("netracare.mcp_server")
logging.basicConfig(level=logging.INFO)

# Initialize FastMCP application for NetraCare
mcp = FastMCP("NetraCare", host="localhost", port=8001)


def parse_relative_or_iso_date(date_str: str, db, clock_override: Optional[datetime] = None) -> date:
    """
    Parse a date string that may be an ISO string ('2026-11-23') or a relative descriptor
    ('next Monday', 'next Thursday', 'tomorrow', 'a Monday more than 30 days from today').
    If the resolved date lands on a clinic holiday in holidays.csv, moves to the following week.
    """
    now = ClockService.now(clock_override)
    today = now.date()
    s = (date_str or "").strip().lower()

    # Direct ISO date
    try:
        parsed_d = datetime.strptime(s, "%Y-%m-%d").date()
        return parsed_d
    except ValueError:
        pass

    # Check for "more than 30 days"
    if "more than 30 days" in s:
        target = today + timedelta(days=35)
        # align to Monday if requested
        if "monday" in s:
            days_ahead = (0 - target.weekday()) % 7
            target = target + timedelta(days=days_ahead)
        return target

    if "today" in s:
        target = today
    elif "tomorrow" in s:
        target = today + timedelta(days=1)
    else:
        day_map = {
            "monday": 0, "mon": 0,
            "tuesday": 1, "tue": 1,
            "wednesday": 2, "wed": 2,
            "thursday": 3, "thu": 3,
            "friday": 4, "fri": 4,
            "saturday": 5, "sat": 5,
            "sunday": 6, "sun": 6,
        }
        matched_day = None
        for name, val in day_map.items():
            if name in s:
                matched_day = val
                break

        if matched_day is not None:
            days_ahead = (matched_day - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            target = today + timedelta(days=days_ahead)
        else:
            # Fallback attempt: try parsing standard formats
            for fmt in ["%d-%m-%Y", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y"]:
                try:
                    return datetime.strptime(s, fmt).date()
                except ValueError:
                    pass
            target = today

    # Check if target lands on a holiday; if so, move to the following week
    while db.query(Holiday).filter(Holiday.holiday_date == target).first():
        target += timedelta(days=7)

    return target


def parse_start_time_str(time_str: str) -> Optional[time]:
    """Parse a time string into time object ('10:00', '10:00:00', '10.00')."""
    s = (time_str or "").strip()
    for fmt in ["%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"]:
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            pass
    return None


def resolve_doctor_entity(db, doctor_query: Optional[str]) -> Optional[Doctor]:
    """Resolve doctor by ID ('D1', 'D01') or full/partial name ('Dr. Anand Rao', 'Anand Rao')."""
    if not doctor_query:
        return None
    raw = doctor_query.strip()

    # Exact ID match
    doc = db.query(Doctor).filter(Doctor.doctor_id == raw).first()
    if doc:
        return doc

    # Handle D1 vs D01 normalization
    if raw.startswith("D0") and len(raw) == 3 and raw[2].isdigit():
        alt = "D" + raw[2]
        doc = db.query(Doctor).filter(Doctor.doctor_id == alt).first()
        if doc:
            return doc
    elif raw.startswith("D") and len(raw) == 2 and raw[1].isdigit():
        alt = f"D0{raw[1]}"
        doc = db.query(Doctor).filter(Doctor.doctor_id == alt).first()
        if doc:
            return doc

    # Case-insensitive name match
    clean_name = raw.lower().replace("dr.", "").replace("dr", "").strip()
    docs = db.query(Doctor).all()
    for d in docs:
        d_clean = d.name.lower().replace("dr.", "").replace("dr", "").strip()
        if clean_name in d_clean or d_clean in clean_name:
            return d

    return None


def generate_new_patient_id(db) -> str:
    """Generate the next unique patient ID (e.g. 'P101')."""
    patients = db.query(Patient.patient_id).all()
    max_num = 0
    for (pid,) in patients:
        if pid.startswith("P") and pid[1:].isdigit():
            num = int(pid[1:])
            if num > max_num:
                max_num = num
    next_num = max(max_num + 1, 101)
    return f"P{next_num:02d}"


@mcp.tool()
@track(name="mcp_find_slots", tags=["mcp", "slots"])
def find_slots(
    speciality: str,
    date: str,
    doctor: Optional[str] = None
) -> dict:
    """Find free appointment start times for a new consultation (20 minutes duration) at NetraCare.

    Returns available 20-minute slots in the morning (AM: 09:00 - 13:00) and afternoon (PM: 14:00 - 18:00)
    sessions. Operating hours are strictly Monday to Saturday; Sunday and clinic holidays are closed.
    Appointments must be within a 30-day window from the clinic date.

    Args:
        speciality: The clinical speciality (e.g. 'Cataract', 'Glaucoma', 'Retina', 'General',
                    'Cornea', 'Refractive', 'Squint', 'Paediatric').
        date: The target date in YYYY-MM-DD format or relative phrasing (e.g. 'next Monday',
              'next Thursday', 'tomorrow').
        doctor: Optional doctor ID (e.g. 'D1', 'D01') or name (e.g. 'Dr. Kiran Shah'). If omitted,
                slots across all doctors covering the speciality are returned.
    """
    with SessionLocal() as db:
        now = ClockService.now()
        today = now.date()

        try:
            target_date = parse_relative_or_iso_date(date, db)
        except Exception as e:
            return {
                "status": "refused",
                "allowed": False,
                "reason_code": ReasonCodeEnum.IN_PAST.value,
                "message": f"Could not parse date '{date}': {e}",
                "slots": []
            }

        # 1. Past check
        if target_date < today:
            return {
                "status": "refused",
                "allowed": False,
                "reason_code": ReasonCodeEnum.IN_PAST.value,
                "message": "Cannot search for slots in the past.",
                "slots": []
            }

        # 2. Beyond 30 days check
        if (target_date - today).days > 30:
            return {
                "status": "refused",
                "allowed": False,
                "reason_code": ReasonCodeEnum.BEYOND_30_DAYS.value,
                "message": f"Appointments can only be booked up to 30 days in advance (attempted {(target_date - today).days} days).",
                "slots": []
            }

        # 3. Sunday check
        if target_date.weekday() == 6:
            return {
                "status": "refused",
                "allowed": False,
                "reason_code": ReasonCodeEnum.CLINIC_CLOSED.value,
                "message": "The clinic is closed on Sundays.",
                "slots": []
            }

        # 4. Holiday check
        holiday = db.query(Holiday).filter(Holiday.holiday_date == target_date).first()
        if holiday:
            return {
                "status": "refused",
                "allowed": False,
                "reason_code": ReasonCodeEnum.HOLIDAY.value,
                "message": f"The clinic is closed for a holiday: {holiday.name}.",
                "slots": []
            }

        # Resolve target doctor(s)
        target_doctors: List[Doctor] = []
        if doctor:
            doc_obj = resolve_doctor_entity(db, doctor)
            if not doc_obj:
                return {
                    "status": "refused",
                    "allowed": False,
                    "reason_code": ReasonCodeEnum.SPECIALITY_MISMATCH.value,
                    "message": f"Doctor '{doctor}' not found.",
                    "slots": []
                }
            target_doctors = [doc_obj]
        else:
            doc_specs = db.query(DoctorSpeciality).filter(DoctorSpeciality.speciality.ilike(speciality.strip())).all()
            doc_ids = [ds.doctor_id for ds in doc_specs]
            target_doctors = db.query(Doctor).filter(Doctor.doctor_id.in_(doc_ids)).order_by(Doctor.doctor_id).all()

        if not target_doctors:
            return {
                "status": "refused",
                "allowed": False,
                "reason_code": ReasonCodeEnum.SPECIALITY_MISMATCH.value,
                "message": f"No doctors found covering speciality '{speciality}'.",
                "slots": []
            }

        # Check doctor schedule status (OPD vs OFF vs SURGERY)
        day_abbr = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][target_date.weekday()]
        all_slots: List[str] = []
        off_reasons: List[str] = []

        for doc in target_doctors:
            # Check weekly schedule for that doctor on that weekday
            schedules = db.query(WeeklySchedule).filter(
                WeeklySchedule.doctor_id == doc.doctor_id,
                WeeklySchedule.day == day_abbr
            ).all()

            opd_sessions = [s for s in schedules if s.status == "OPD"]
            if not opd_sessions:
                off_sessions = [s for s in schedules if s.status == "OFF"]
                surg_sessions = [s for s in schedules if s.status == "SURGERY"]
                if surg_sessions:
                    off_reasons.append(f"{doc.name} is in surgery on {day_abbr}s.")
                else:
                    off_reasons.append(f"{doc.name} is not at the clinic on {day_abbr}s.")
                continue

            doc_slots = FreeSlotsService.get_available_slots(db, doc.doctor_id, target_date, VisitTypeEnum.new)
            for sl in doc_slots:
                all_slots.append(f"{doc.name} ({doc.doctor_id}): {sl}")

        if not all_slots and off_reasons:
            # No slots because doctor is off/surgery; this is a clear allowed response with empty slots, not an error
            return {
                "status": "allowed",
                "allowed": True,
                "date": target_date.isoformat(),
                "speciality": speciality,
                "slots": [],
                "message": f"No slots: {'; '.join(off_reasons)}"
            }

        return {
            "status": "allowed",
            "allowed": True,
            "date": target_date.isoformat(),
            "speciality": speciality,
            "duration_minutes": 20,
            "slots": all_slots,
            "message": f"Found {len(all_slots)} available 20-minute slots on {target_date.isoformat()}."
        }


@mcp.tool()
@track(name="mcp_book_appointment", tags=["mcp", "book"])
def book_appointment(
    patient_name: str,
    mobile: str,
    speciality: str,
    doctor: str,
    date: str,
    start_time: str,
    reason: str
) -> dict:
    """Book a new consultation appointment (20 minutes duration) at NetraCare Eye Clinic.

    Enforces all clinic rules, patient identity resolution, and mandatory red-flag triage.
    New mobile creates a new patient record. Existing mobile with a different name returns
    PATIENT_DETAILS_MISMATCH. A red flag returns the emergency response, creates an urgent
    case from MCP, and creates no appointment.

    Args:
        patient_name: Full name of the patient (e.g. 'Ravi Kumar').
        mobile: 10-digit mobile number of the patient (e.g. '9000000010').
        speciality: Clinic speciality (e.g. 'Cataract', 'Glaucoma', 'Retina', 'General',
                    'Cornea', 'Refractive', 'Squint', 'Paediatric').
        doctor: Doctor ID (e.g. 'D1', 'D01') or name (e.g. 'Dr. Anand Rao').
        date: Appointment date in YYYY-MM-DD or relative date (e.g. 'next Monday')
              within the 30-day window.
        start_time: Start time on a 10-minute mark in HH:MM format (e.g. '10:00').
        reason: Mandatory clinical reason for the visit (up to 300 characters).
    """
    clean_name = (patient_name or "").strip()
    clean_mobile = "".join(filter(str.isdigit, str(mobile or "")))
    clean_reason = (reason or "").strip()

    if not clean_name:
        return {
            "status": "refused",
            "reason_code": "INVALID_INPUT",
            "message": "Patient name is required."
        }
    if not clean_mobile or len(clean_mobile) < 10:
        return {
            "status": "refused",
            "reason_code": "INVALID_INPUT",
            "message": "Valid 10-digit mobile number is required."
        }
    if not clean_reason:
        return {
            "status": "refused",
            "reason_code": "MISSING_REASON",
            "message": "A reason for the appointment is required (up to 300 characters)."
        }
    if len(clean_reason) > 300:
        return {
            "status": "refused",
            "reason_code": "REASON_TOO_LONG",
            "message": "Appointment reason must not exceed 300 characters."
        }

    with SessionLocal() as db:
        # ---------------------------------------------------------------------
        # 1. Resolve Patient Identity by Mobile & Name
        # ---------------------------------------------------------------------
        patient = db.query(Patient).filter(Patient.mobile == clean_mobile).first()
        if patient:
            # Existing mobile: must match patient name
            if patient.name.strip().lower() != clean_name.lower():
                return {
                    "status": "refused",
                    "reason_code": ReasonCodeEnum.PATIENT_DETAILS_MISMATCH.value,
                    "message": f"The mobile belongs to a patient with a different name ({patient.name}). Never book into someone else's record."
                }
        else:
            # New mobile: create a new patient as at website login
            new_pid = generate_new_patient_id(db)
            patient = Patient(
                patient_id=new_pid,
                name=clean_name,
                mobile=clean_mobile,
                general_health="None recorded",
                allergies="None known"
            )
            db.add(patient)
            db.commit()
            db.refresh(patient)
            logger.info(f"MCP created new patient {patient.patient_id} ({patient.name}, {patient.mobile})")

        # ---------------------------------------------------------------------
        # 2. Mandatory Red-Flag Interception on Reason
        # ---------------------------------------------------------------------
        try:
            rf_res = LLMService.check_red_flags(clean_reason)
        except Exception as e:
            logger.error(f"Red flag check failed in MCP book_appointment: {e}")
            return {
                "status": "error",
                "message": "We couldn't check your reason just now. Please try again, or call the clinic if it's urgent."
            }

        if rf_res.red_flag:
            # Red flag: creates an urgent case from MCP and creates NO appointment
            urgent_case = UrgentCase(
                patient_id=patient.patient_id,
                appointment_id=None,
                reason=f"[from MCP] {clean_reason}",
                category=rf_res.category or "urgent",
                why=f"[from MCP] {rf_res.why}",
                is_seen=False,
                source="MCP"
            )
            db.add(urgent_case)
            db.commit()
            db.refresh(urgent_case)
            logger.warning(f"Red-flag detected in MCP booking: Case #{urgent_case.id} created. Booking refused.")

            return {
                "status": "red_flag",
                "reason_code": ReasonCodeEnum.RED_FLAG.value,
                "emergency_response": EMERGENCY_RESPONSE_TEXT,
                "message": EMERGENCY_RESPONSE_TEXT,
                "urgent_case_id": urgent_case.id,
                "note": "Partner app must show this emergency response to the patient as it is."
            }

        # ---------------------------------------------------------------------
        # 3. Parse and Validate Doctor, Date, and Time
        # ---------------------------------------------------------------------
        doc_obj = resolve_doctor_entity(db, doctor)
        if not doc_obj:
            return {
                "status": "refused",
                "reason_code": ReasonCodeEnum.SPECIALITY_MISMATCH.value,
                "message": f"Doctor '{doctor}' not found."
            }

        try:
            appt_date = parse_relative_or_iso_date(date, db)
        except Exception as e:
            return {
                "status": "refused",
                "reason_code": ReasonCodeEnum.IN_PAST.value,
                "message": f"Could not parse appointment date: {e}"
            }

        # Extract start time from date or start_time field
        time_part = start_time.strip()
        # If start_time was embedded in date string (e.g. 'next Monday 10:00')
        if not time_part or time_part.lower() in ("am", "pm"):
            parts = date.strip().split()
            if len(parts) >= 2 and ":" in parts[-1]:
                time_part = parts[-1]

        start_t = parse_start_time_str(time_part)
        if not start_t:
            return {
                "status": "refused",
                "reason_code": ReasonCodeEnum.INVALID_START_TIME.value,
                "message": f"Invalid start time format '{time_part}'. Expected HH:MM on a 10-minute mark."
            }

        # ---------------------------------------------------------------------
        # 4. Clinic Rules Validation via ClinicRulesEngine
        # ---------------------------------------------------------------------
        val = ClinicRulesEngine.validate_booking(
            db=db,
            doctor_id=doc_obj.doctor_id,
            speciality=speciality.strip(),
            visit_type=VisitTypeEnum.new,
            appt_date=appt_date,
            start_t=start_t,
            patient_id=patient.patient_id,
            role=RoleEnum.patient
        )

        if not val.allowed:
            return {
                "status": "refused",
                "reason_code": val.reason_code.value,
                "message": val.message
            }

        # ---------------------------------------------------------------------
        # 5. Create Appointment with source = 'MCP'
        # ---------------------------------------------------------------------
        new_id = generate_next_appointment_id(db)
        end_t = ClinicRulesEngine.calculate_end_time(start_t, VisitTypeEnum.new)
        appt = Appointment(
            appointment_id=new_id,
            patient_id=patient.patient_id,
            doctor_id=doc_obj.doctor_id,
            speciality=speciality.strip(),
            visit_type=VisitTypeEnum.new.value,
            appointment_date=appt_date,
            start_time=start_t,
            end_time=end_t,
            status="booked",
            reason=clean_reason,
            is_urgent=False,
            source="MCP",
            intake_notes=None
        )
        db.add(appt)
        db.commit()
        db.refresh(appt)

        logger.info(f"MCP booked appointment {appt.appointment_id} for {patient.name} with {doc_obj.name}")

        return {
            "status": "booked",
            "allowed": True,
            "appointment_id": new_id,
            "patient_id": patient.patient_id,
            "patient_name": patient.name,
            "doctor_id": doc_obj.doctor_id,
            "doctor_name": doc_obj.name,
            "speciality": speciality.strip(),
            "date": appt_date.isoformat(),
            "start_time": start_t.strftime("%H:%M"),
            "end_time": end_t.strftime("%H:%M"),
            "source": "MCP",
            "message": f"Appointment {new_id} booked successfully for {patient.name} with {doc_obj.name} on {appt_date.isoformat()} at {start_t.strftime('%H:%M')}."
        }


if __name__ == "__main__":
    ensure_schema_updates()
    print("Starting NetraCare MCP server on http://localhost:8001/mcp (Streamable HTTP)...")
    mcp.run(transport="streamable-http")
