import logging
from datetime import datetime, date, time, timedelta
from typing import Optional, List, Dict, Any
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from app.database import SessionLocal
from app.models import Doctor, DoctorSpeciality, WeeklySchedule, Holiday, Appointment, UrgentCase, StaffApproval
from app.schemas import VisitTypeEnum, RoleEnum, ReasonCodeEnum
from app.services.clock import ClockService
from app.services.rules_engine import ClinicRulesEngine
from app.services.slots_service import FreeSlotsService
from app.services.rag import RAGService, I_DONT_KNOW_RESPONSE
from app.services.llm import LLMService, EMERGENCY_RESPONSE_TEXT, RED_FLAG_FAILURE_MESSAGE
from app.api.appointments import generate_next_appointment_id

logger = logging.getLogger("netracare.tools")


def resolve_doctor_id(db, raw_id: Optional[str]) -> Optional[str]:
    """Resolve doctor ID handling both 'D1' and 'D01' formats seamlessly."""
    if not raw_id:
        return None
    raw = raw_id.strip()
    doc = db.query(Doctor).filter(Doctor.doctor_id == raw).first()
    if doc:
        return doc.doctor_id
    if raw.startswith("D0") and len(raw) == 3:
        alt = "D" + raw[2:]
        if db.query(Doctor).filter(Doctor.doctor_id == alt).first():
            return alt
    elif raw.startswith("D") and len(raw) == 2 and raw[1].isdigit():
        alt = f"D0{raw[1]}"
        if db.query(Doctor).filter(Doctor.doctor_id == alt).first():
            return alt
    return raw


def ask_patient_confirmation(action_data: dict, config: Optional[RunnableConfig] = None) -> bool:
    """
    Request confirmation from the patient using LangGraph's interrupt().
    In unit test / direct execution mode outside a LangGraph runner,
    inspects config['configurable']['auto_confirm'] if present.
    """
    if config:
        cfg = config.get("configurable", {})
        if "auto_confirm" in cfg:
            return bool(cfg["auto_confirm"])

    try:
        resume_val = interrupt(action_data)
        if isinstance(resume_val, dict):
            return bool(resume_val.get("confirm", False))
        return bool(resume_val)
    except RuntimeError as e:
        if config and "auto_confirm" in config.get("configurable", {}):
            return bool(config["configurable"]["auto_confirm"])
        raise RuntimeError(
            f"LangGraph interrupt called outside runnable context for action '{action_data.get('action')}'. "
            f"When testing tools directly, supply config={{'configurable': {{'auto_confirm': True/False}}}}."
        ) from e


@tool
def search_clinic_docs(query: str) -> dict:
    """Search the NetraCare clinic knowledge base (policies, doctors, procedures, fees, FAQs) and return a grounded answer with citations or I don't know."""
    q = (query or "").strip()
    if not q:
        return {
            "answer": I_DONT_KNOW_RESPONSE,
            "sources": [],
            "answered": False
        }

    try:
        search_res = RAGService.hybrid_search(q, top_k=4)
        answer_res = RAGService.generate_grounded_answer(q, search_res.get("hybrid", []))
        is_answered = (
            answer_res.get("answer") != I_DONT_KNOW_RESPONSE
            and not answer_res.get("is_error", False)
        )
        return {
            "answer": answer_res.get("answer", I_DONT_KNOW_RESPONSE),
            "sources": answer_res.get("sources", []),
            "answered": is_answered
        }
    except Exception as e:
        logger.error(f"Error executing search_clinic_docs: {e}")
        return {
            "answer": "Sorry, I can't answer just now. Please try again, or ask Staff at the front desk.",
            "sources": [],
            "answered": False
        }


@tool
def list_doctors(speciality: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all NetraCare clinic doctors, their IDs, names, specialities, and OPD schedules."""
    with SessionLocal() as db:
        doctors = db.query(Doctor).order_by(Doctor.doctor_id).all()
        result = []
        for doc in doctors:
            specs = [s.speciality for s in doc.specialities]
            if speciality and speciality.lower() not in [s.lower() for s in specs]:
                continue
            
            opd_days = list(dict.fromkeys([ws.day for ws in doc.schedules if ws.status == "OPD"]))
            schedules = [
                {"day": ws.day, "session": ws.session, "status": ws.status}
                for ws in doc.schedules
                if ws.status == "OPD"
            ]
            result.append({
                "doctor_id": doc.doctor_id,
                "name": doc.name,
                "specialities": specs,
                "opd_days": opd_days,
                "opd_schedule": schedules
            })
        return result


@tool
def find_slots(
    speciality: Optional[str] = None,
    doctor_id: Optional[str] = None,
    visit_type: str = "new",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    session: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Find up to 10 earliest free appointment start times for a speciality or doctor, visit type (new/follow_up), date range, and optional session (AM/PM)."""
    vt = VisitTypeEnum.follow_up if visit_type and "follow" in visit_type.lower() else VisitTypeEnum.new
    session_filter = session.upper().strip() if session and session.upper().strip() in ("AM", "PM") else None

    now = ClockService.now()
    today = now.date()

    if start_date:
        try:
            s_date = datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
            if s_date < today:
                s_date = today
        except ValueError:
            s_date = today
    else:
        s_date = today

    if end_date:
        try:
            e_date = datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
        except ValueError:
            e_date = s_date + timedelta(days=30)
    else:
        e_date = s_date + timedelta(days=30)

    # Hard boundary: at most 30 days ahead from today
    max_limit = today + timedelta(days=30)
    if e_date > max_limit:
        e_date = max_limit

    if s_date > e_date:
        return []

    with SessionLocal() as db:
        if doctor_id:
            resolved_id = resolve_doctor_id(db, doctor_id)
            doctor = db.query(Doctor).filter(Doctor.doctor_id == resolved_id).first() if resolved_id else None
            if not doctor:
                return []
            target_doctors = [doctor]
        elif speciality:
            doc_specs = db.query(DoctorSpeciality).filter(DoctorSpeciality.speciality.ilike(speciality)).all()
            doc_ids = [ds.doctor_id for ds in doc_specs]
            target_doctors = db.query(Doctor).filter(Doctor.doctor_id.in_(doc_ids)).order_by(Doctor.doctor_id).all()
        else:
            target_doctors = db.query(Doctor).order_by(Doctor.doctor_id).all()

        candidate_slots: List[Dict[str, Any]] = []
        curr_day = s_date
        while curr_day <= e_date:
            # Sunday clinic closed
            if curr_day.weekday() == 6:
                curr_day += timedelta(days=1)
                continue

            # Holiday
            if db.query(Holiday).filter(Holiday.holiday_date == curr_day).first():
                curr_day += timedelta(days=1)
                continue

            for doc in target_doctors:
                slots = FreeSlotsService.get_available_slots(db, doc.doctor_id, curr_day, vt)
                for slot_str in slots:
                    slot_hour = int(slot_str.split(":")[0])
                    slot_sess = "AM" if slot_hour < 13 else "PM"
                    if session_filter and slot_sess != session_filter:
                        continue

                    # Determine matched speciality for display
                    matched_spec = speciality
                    if not matched_spec and doc.specialities:
                        matched_spec = doc.specialities[0].speciality

                    candidate_slots.append({
                        "doctor_id": doc.doctor_id,
                        "doctor_name": doc.name,
                        "speciality": matched_spec,
                        "date": curr_day.isoformat(),
                        "start_time": slot_str,
                        "session": slot_sess,
                        "duration_minutes": 20 if vt == VisitTypeEnum.new else 10
                    })
            curr_day += timedelta(days=1)

        # Sort earliest first: by date asc, start_time asc, doctor_id asc
        candidate_slots.sort(key=lambda s: (s["date"], s["start_time"], s["doctor_id"]))
        return candidate_slots[:10]


@tool
def my_appointments(config: RunnableConfig) -> List[Dict[str, Any]]:
    """Get the authenticated patient's upcoming appointments and any requests waiting for Staff approval."""
    patient_id = config.get("configurable", {}).get("patient_id")
    if not patient_id:
        return []

    with SessionLocal() as db:
        appts = db.query(Appointment).filter(
            Appointment.patient_id == patient_id
        ).order_by(Appointment.appointment_date.asc(), Appointment.start_time.asc()).all()

        results = []
        for a in appts:
            doc = db.query(Doctor).filter(Doctor.doctor_id == a.doctor_id).first()
            doc_name = doc.name if doc else a.doctor_id

            pending_appr = db.query(StaffApproval).filter(
                StaffApproval.appointment_id == a.appointment_id,
                StaffApproval.status == "pending"
            ).first()
            approval_status = f"{pending_appr.action_type}_pending" if pending_appr else None

            results.append({
                "appointment_id": a.appointment_id,
                "doctor_id": a.doctor_id,
                "doctor_name": doc_name,
                "speciality": a.speciality,
                "visit_type": a.visit_type,
                "date": a.appointment_date.isoformat(),
                "start_time": a.start_time.strftime("%H:%M"),
                "end_time": a.end_time.strftime("%H:%M"),
                "status": a.status,
                "reason": a.reason,
                "approval_status": approval_status
            })
        return results


@tool
def book_appointment(
    doctor_id: str,
    speciality: str,
    visit_type: str,
    date: str,
    start_time: str,
    reason: str,
    config: RunnableConfig,
    intake_notes: Optional[str] = None
) -> dict:
    """Book an appointment for the authenticated patient after pre-validating clinic rules and receiving patient confirmation."""
    patient_id = config.get("configurable", {}).get("patient_id")
    if not patient_id:
        return {"result": "refused", "message": "Authentication required. Patient identity not found in context."}

    reason_str = (reason or "").strip()
    if not reason_str:
        return {"result": "refused", "reason_code": "MISSING_REASON", "message": "A reason for the appointment is required."}
    if len(reason_str) > 300:
        return {"result": "refused", "reason_code": "REASON_TOO_LONG", "message": "Appointment reason must not exceed 300 characters."}

    # Red-flag check on booking reason
    try:
        red_flag_res = LLMService.check_red_flags(reason_str)
    except Exception as e:
        logger.error(f"Red flag check failed: {e}")
        return {"result": "error", "message": RED_FLAG_FAILURE_MESSAGE}

    if red_flag_res.red_flag:
        with SessionLocal() as db:
            urgent_case = UrgentCase(
                patient_id=patient_id,
                reason=f"[Chat] {reason_str}",
                category=red_flag_res.category or "urgent",
                why=red_flag_res.why,
                is_seen=False
            )
            db.add(urgent_case)
            db.commit()
        return {"result": "emergency", "message": EMERGENCY_RESPONSE_TEXT}

    # Parse inputs
    try:
        appt_date = datetime.strptime(date.strip(), "%Y-%m-%d").date()
        start_t = datetime.strptime(start_time.strip(), "%H:%M").time()
    except ValueError:
        return {
            "result": "refused",
            "reason_code": ReasonCodeEnum.INVALID_START_TIME.value,
            "message": "Invalid date or start time format. Expected YYYY-MM-DD and HH:MM."
        }

    vt = VisitTypeEnum.follow_up if "follow" in visit_type.lower() else VisitTypeEnum.new

    # Pre-validate with ClinicRulesEngine
    with SessionLocal() as db:
        resolved_doc_id = resolve_doctor_id(db, doctor_id) or doctor_id
        val = ClinicRulesEngine.validate_booking(
            db=db,
            doctor_id=resolved_doc_id,
            speciality=speciality,
            visit_type=vt,
            appt_date=appt_date,
            start_t=start_t,
            patient_id=patient_id,
            role=RoleEnum.patient
        )
        if not val.allowed:
            return {
                "result": "refused",
                "reason_code": val.reason_code.value,
                "message": val.message
            }

        doc = db.query(Doctor).filter(Doctor.doctor_id == resolved_doc_id).first()
        doc_name = doc.name if doc else resolved_doc_id

    # Format human-readable confirmation summary
    duration = 10 if vt == VisitTypeEnum.follow_up else 20
    vt_label = "follow-up" if vt == VisitTypeEnum.follow_up else "new"
    formatted_date = appt_date.strftime("%a %d %b")
    time_label = start_t.strftime("%I:%M %p").lstrip("0")
    summary = f"Book {doc_name}, {speciality.title()} {vt_label}, {formatted_date}, {time_label} ({duration} min)?"

    # Request human confirmation via interrupt
    confirmed = ask_patient_confirmation({
        "action": "book",
        "summary": summary,
        "details": {
            "doctor_id": doctor_id,
            "doctor_name": doc_name,
            "speciality": speciality,
            "visit_type": vt.value,
            "date": appt_date.isoformat(),
            "start_time": start_t.strftime("%H:%M"),
            "reason": reason_str,
            "intake_notes": intake_notes
        }
    }, config=config)

    if not confirmed:
        return {
            "result": "cancelled_by_patient",
            "message": "Booking was not confirmed by the patient."
        }

    # Execute booking after confirmation
    with SessionLocal() as db:
        resolved_doc_id = resolve_doctor_id(db, doctor_id) or doctor_id
        # Re-check to prevent race condition
        val2 = ClinicRulesEngine.validate_booking(
            db=db,
            doctor_id=resolved_doc_id,
            speciality=speciality,
            visit_type=vt,
            appt_date=appt_date,
            start_t=start_t,
            patient_id=patient_id,
            role=RoleEnum.patient
        )
        if not val2.allowed:
            return {
                "result": "refused",
                "reason_code": val2.reason_code.value,
                "message": val2.message
            }

        new_id = generate_next_appointment_id(db)
        end_t = ClinicRulesEngine.calculate_end_time(start_t, vt)
        appt = Appointment(
            appointment_id=new_id,
            patient_id=patient_id,
            doctor_id=resolved_doc_id,
            speciality=speciality,
            visit_type=vt.value,
            appointment_date=appt_date,
            start_time=start_t,
            end_time=end_t,
            status="booked",
            reason=reason_str,
            is_urgent=False,
            source="Chat",
            intake_notes=intake_notes
        )
        db.add(appt)
        db.commit()
        db.refresh(appt)

        return {
            "result": "booked",
            "appointment_id": new_id,
            "summary": summary,
            "message": f"Appointment {new_id} booked successfully for {doc_name} on {appt_date.isoformat()} at {start_t.strftime('%H:%M')}."
        }


@tool
def cancel_appointment(appointment_id: str, config: RunnableConfig, reason: Optional[str] = None) -> dict:
    """Cancel an existing booked appointment for the authenticated patient after requesting patient confirmation."""
    patient_id = config.get("configurable", {}).get("patient_id")
    if not patient_id:
        return {"result": "refused", "message": "Authentication required. Patient identity not found in context."}

    with SessionLocal() as db:
        appt = db.query(Appointment).filter(Appointment.appointment_id == appointment_id).first()
        if not appt:
            return {
                "result": "refused",
                "reason_code": "NOT_FOUND",
                "message": f"Appointment {appointment_id} not found."
            }

        if appt.patient_id != patient_id:
            return {
                "result": "refused",
                "reason_code": ReasonCodeEnum.NOT_YOUR_APPOINTMENT.value,
                "message": "You cannot cancel an appointment belonging to another patient."
            }

        val = ClinicRulesEngine.validate_cancellation(
            db=db,
            appointment=appt,
            acting_role=RoleEnum.patient,
            acting_patient_id=patient_id
        )
        if not val.allowed and val.reason_code != ReasonCodeEnum.INSIDE_2_HOURS:
            return {
                "result": "refused",
                "reason_code": val.reason_code.value,
                "message": val.message
            }

        doc = db.query(Doctor).filter(Doctor.doctor_id == appt.doctor_id).first()
        doc_name = doc.name if doc else appt.doctor_id
        date_str = appt.appointment_date.strftime("%a %d %b")
        time_str = appt.start_time.strftime("%I:%M %p").lstrip("0")
        summary = f"Cancel appointment {appt.appointment_id} ({doc_name}, {appt.speciality.title()} {appt.visit_type}, {date_str}, {time_str})?"

    # Request human confirmation
    confirmed = ask_patient_confirmation({
        "action": "cancel",
        "summary": summary,
        "details": {
            "appointment_id": appointment_id
        }
    }, config=config)

    if not confirmed:
        return {
            "result": "cancelled_by_patient",
            "message": "Cancellation was not confirmed by the patient."
        }

    # Execute cancellation / staff approval after confirmation
    with SessionLocal() as db:
        appt = db.query(Appointment).filter(Appointment.appointment_id == appointment_id).first()
        if not appt or appt.status != "booked":
            return {
                "result": "refused",
                "reason_code": ReasonCodeEnum.NOT_ACTIVE.value,
                "message": "Appointment is no longer active."
            }

        val = ClinicRulesEngine.validate_cancellation(
            db=db,
            appointment=appt,
            acting_role=RoleEnum.patient,
            acting_patient_id=patient_id
        )

        if val.reason_code == ReasonCodeEnum.INSIDE_2_HOURS:
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
            return {
                "result": "to_staff",
                "reason_code": ReasonCodeEnum.INSIDE_2_HOURS.value,
                "appointment_id": appt.appointment_id,
                "summary": summary,
                "message": "Your cancellation request is within 2 hours of the appointment and has been sent to Staff for approval."
            }

        appt.status = "cancelled"
        db.commit()
        return {
            "result": "cancelled",
            "appointment_id": appt.appointment_id,
            "summary": summary,
            "message": f"Appointment {appt.appointment_id} has been cancelled successfully."
        }


@tool
def reschedule_appointment(
    appointment_id: str,
    new_date: str,
    new_start_time: str,
    config: RunnableConfig,
    new_doctor_id: Optional[str] = None,
    new_speciality: Optional[str] = None,
    new_visit_type: Optional[str] = None
) -> dict:
    """Reschedule an existing booked appointment for the authenticated patient to a new doctor, date, and start time after requesting patient confirmation."""
    patient_id = config.get("configurable", {}).get("patient_id")
    if not patient_id:
        return {"result": "refused", "message": "Authentication required. Patient identity not found in context."}

    with SessionLocal() as db:
        appt = db.query(Appointment).filter(Appointment.appointment_id == appointment_id).first()
        if not appt:
            return {
                "result": "refused",
                "reason_code": "NOT_FOUND",
                "message": f"Appointment {appointment_id} not found."
            }

        if appt.patient_id != patient_id:
            return {
                "result": "refused",
                "reason_code": ReasonCodeEnum.NOT_YOUR_APPOINTMENT.value,
                "message": "You cannot reschedule an appointment belonging to another patient."
            }

        target_speciality = new_speciality or appt.speciality
        target_visit_type = VisitTypeEnum.follow_up if new_visit_type and "follow" in new_visit_type.lower() else (
            VisitTypeEnum(appt.visit_type) if not new_visit_type else VisitTypeEnum.new
        )

        try:
            target_date = datetime.strptime(new_date.strip(), "%Y-%m-%d").date()
            target_start_t = datetime.strptime(new_start_time.strip(), "%H:%M").time()
        except ValueError:
            return {
                "result": "refused",
                "reason_code": ReasonCodeEnum.INVALID_START_TIME.value,
                "message": "Invalid date or start time format. Expected YYYY-MM-DD and HH:MM."
            }

        doc_id_to_use = new_doctor_id or appt.doctor_id
        resolved_new_doc_id = resolve_doctor_id(db, doc_id_to_use) or doc_id_to_use
        val = ClinicRulesEngine.validate_reschedule(
            db=db,
            appointment=appt,
            new_doctor_id=resolved_new_doc_id,
            new_speciality=target_speciality,
            new_visit_type=target_visit_type,
            new_date=target_date,
            new_start_time=target_start_t,
            acting_role=RoleEnum.patient,
            acting_patient_id=patient_id
        )
        if not val.allowed and val.reason_code != ReasonCodeEnum.INSIDE_2_HOURS:
            return {
                "result": "refused",
                "reason_code": val.reason_code.value,
                "message": val.message
            }

        new_doc = db.query(Doctor).filter(Doctor.doctor_id == resolved_new_doc_id).first()
        new_doc_name = new_doc.name if new_doc else resolved_new_doc_id
        duration = 10 if target_visit_type == VisitTypeEnum.follow_up else 20
        vt_label = "follow-up" if target_visit_type == VisitTypeEnum.follow_up else "new"
        formatted_date = target_date.strftime("%a %d %b")
        time_label = target_start_t.strftime("%I:%M %p").lstrip("0")
        summary = f"Reschedule appointment {appt.appointment_id} to {new_doc_name}, {target_speciality.title()} {vt_label}, {formatted_date}, {time_label} ({duration} min)?"

    # Request human confirmation
    confirmed = ask_patient_confirmation({
        "action": "reschedule",
        "summary": summary,
        "details": {
            "appointment_id": appointment_id,
            "new_doctor_id": resolved_new_doc_id,
            "new_doctor_name": new_doc_name,
            "new_speciality": target_speciality,
            "new_visit_type": target_visit_type.value,
            "new_date": target_date.isoformat(),
            "new_start_time": target_start_t.strftime("%H:%M")
        }
    }, config=config)

    if not confirmed:
        return {
            "result": "cancelled_by_patient",
            "message": "Reschedule was not confirmed by the patient."
        }

    # Execute reschedule / staff approval after confirmation
    with SessionLocal() as db:
        doc_id_to_use = new_doctor_id or appt.doctor_id
        resolved_new_doc_id = resolve_doctor_id(db, doc_id_to_use) or doc_id_to_use
        appt = db.query(Appointment).filter(Appointment.appointment_id == appointment_id).first()
        if not appt or appt.status != "booked":
            return {
                "result": "refused",
                "reason_code": ReasonCodeEnum.NOT_ACTIVE.value,
                "message": "Appointment is no longer active."
            }

        val = ClinicRulesEngine.validate_reschedule(
            db=db,
            appointment=appt,
            new_doctor_id=resolved_new_doc_id,
            new_speciality=target_speciality,
            new_visit_type=target_visit_type,
            new_date=target_date,
            new_start_time=target_start_t,
            acting_role=RoleEnum.patient,
            acting_patient_id=patient_id
        )
        new_end_t = ClinicRulesEngine.calculate_end_time(target_start_t, target_visit_type)

        if val.reason_code == ReasonCodeEnum.INSIDE_2_HOURS:
            existing_appr = db.query(StaffApproval).filter(
                StaffApproval.appointment_id == appt.appointment_id,
                StaffApproval.status == "pending"
            ).first()
            if not existing_appr:
                new_appr = StaffApproval(
                    appointment_id=appt.appointment_id,
                    patient_id=appt.patient_id,
                    action_type="reschedule",
                    new_doctor_id=resolved_new_doc_id,
                    new_speciality=target_speciality,
                    new_visit_type=target_visit_type.value,
                    new_date=target_date,
                    new_start_time=target_start_t,
                    new_end_time=new_end_t,
                    status="pending",
                    reason=val.message
                )
                db.add(new_appr)
                db.commit()
            return {
                "result": "to_staff",
                "reason_code": ReasonCodeEnum.INSIDE_2_HOURS.value,
                "appointment_id": appt.appointment_id,
                "summary": summary,
                "message": "Your reschedule request is within 2 hours of the appointment and has been sent to Staff for approval."
            }

        if not val.allowed:
            return {
                "result": "refused",
                "reason_code": val.reason_code.value,
                "message": val.message
            }

        appt.doctor_id = resolved_new_doc_id
        appt.speciality = target_speciality
        appt.visit_type = target_visit_type.value
        appt.appointment_date = target_date
        appt.start_time = target_start_t
        appt.end_time = new_end_t
        appt.status = "booked"
        db.commit()
        db.refresh(appt)

        return {
            "result": "rescheduled",
            "appointment_id": appt.appointment_id,
            "summary": summary,
            "message": f"Appointment {appt.appointment_id} rescheduled successfully to {new_doc_name} on {target_date.isoformat()} at {target_start_t.strftime('%H:%M')}."
        }


# ============================================================================
# Iteration 6 Tools: Dynamic Agent Skills & Partner Lab (CityCare)
# ============================================================================

@tool
def load_skill(name: str) -> str:
    """Load the complete instructions for an Agent Skill by name.
    Available skills:
    - `cataract-surgery-care`: Instructions before and after cataract surgery (meals, eye shield, washing, driving, screens, drops).
    - `lasik-suitability-intake`: Collects patient's answers to the 9 LASIK pre-assessment questions before booking suitability check with Dr. Fatima Khan.
    - `prepare-for-visit`: Builds a personalized checklist for patient's next booked appointment based on speciality.
    - `children-visit`: Guidance for pediatric eye care, eye tests for children, and visits for patients under 16 with Dr. Vikram Menon.
    """
    from app.services.skills_loader import SkillsLoader
    loader = SkillsLoader.get_instance()
    return loader.load_skill(name)


@tool
def read_skill_file(name: str, file: str) -> str:
    """Read an extra guide, checklist, or question file belonging to a loaded skill (e.g. 'post-op-guide.md', 'questions.md', 'checklists.md').
    Args:
        name: Name of the skill (e.g. 'cataract-surgery-care', 'lasik-suitability-intake', 'prepare-for-visit')
        file: Filename inside that skill's folder
    """
    from app.services.skills_loader import SkillsLoader
    loader = SkillsLoader.get_instance()
    return loader.read_skill_file(name, file)


@tool
def get_lab_test_info(test: str = "") -> dict:
    """Information about a blood or urine test at CityCare Hospital Lab, NetraCare's partner lab.
    Returns fasting rules, sample type, when the report is ready and the indicative price,
    plus the lab's address, timings and home collection.
    Information only: it cannot book tests, read results or say which tests a patient needs.
    Args:
        test: The test name in plain words, for example 'HbA1c' or 'fasting sugar'.
              Leave empty to get the lab's details and the list of tests it offers.
    """
    import os
    import json
    import asyncio
    import concurrent.futures
    from langchain_mcp_adapters.client import MultiServerMCPClient

    lab_url = os.environ.get("CITYCARE_LAB_URL", "http://localhost:8002/mcp").strip()
    try:
        async def _call():
            client = MultiServerMCPClient({
                "citycare": {
                    "transport": "streamable_http",
                    "url": lab_url
                }
            })
            tools = await client.get_tools()
            target = None
            for t in tools:
                if t.name == "get_lab_test_info":
                    target = t
                    break
            if not target:
                raise RuntimeError("Partner tool get_lab_test_info not found")
            return await target.ainvoke({"test": test})

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(lambda: asyncio.run(_call()))
            raw = future.result()

        if isinstance(raw, list) and len(raw) > 0:
            first = raw[0]
            if isinstance(first, dict) and "text" in first:
                text_content = first["text"]
                try:
                    return json.loads(text_content)
                except Exception:
                    return {"result": text_content}
        elif isinstance(raw, str):
            try:
                return json.loads(raw)
            except Exception:
                return {"result": raw}
        elif isinstance(raw, dict):
            return raw

        return {"result": str(raw)}
    except Exception as e:
        logger.warning(f"Failed to connect to CityCare Lab MCP server at {lab_url}: {e}")
        return {
            "error": "unavailable",
            "message": "I can't check CityCare Lab just now. Please ask Staff at the front desk."
        }


ALL_TOOLS = [
    search_clinic_docs,
    list_doctors,
    find_slots,
    my_appointments,
    book_appointment,
    cancel_appointment,
    reschedule_appointment
]

SKILL_AND_LAB_TOOLS = [
    load_skill,
    read_skill_file,
    get_lab_test_info
]

AGENT_TOOLS = ALL_TOOLS + SKILL_AND_LAB_TOOLS

__all__ = [
    "search_clinic_docs",
    "list_doctors",
    "find_slots",
    "my_appointments",
    "book_appointment",
    "cancel_appointment",
    "reschedule_appointment",
    "load_skill",
    "read_skill_file",
    "get_lab_test_info",
    "ALL_TOOLS",
    "AGENT_TOOLS",
    "ask_patient_confirmation"
]
