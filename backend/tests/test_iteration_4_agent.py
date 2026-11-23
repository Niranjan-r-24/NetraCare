import os
import sys
os.environ["DATABASE_URL"] = "sqlite:///./netracare.db"
from datetime import datetime, date, time, timedelta
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableLambda
from langgraph.types import Command

sys.path.insert(0, os.path.abspath("backend"))

from app.main import app
from app.database import SessionLocal
from app.models import Patient, Doctor, Appointment, UrgentCase, StaffApproval, Holiday
from app.services.clock import ClockService
from app.services.llm import LLMService, RedFlagOutput, EMERGENCY_RESPONSE_TEXT
from app.services.rag import I_DONT_KNOW_RESPONSE
from app.services.agent import (
    build_patient_system_prompt,
    run_agent_turn,
    get_or_create_thread,
    validate_thread_ownership,
    SAFETY_CHECK_ERROR_MESSAGE,
    RECURSION_LIMIT_MESSAGE,
    booking_agent_graph
)

client = TestClient(app)


def patient_auth(user_id="P01", name="Asha Verma"):
    return {
        "X-User-Id": user_id,
        "X-Role": "patient",
        "X-User-Name": name
    }


def staff_auth(user_id="S01", name="Reception Staff"):
    return {
        "X-User-Id": user_id,
        "X-Role": "staff",
        "X-User-Name": name
    }


def doctor_auth(user_id="D1", name="Dr. Anand Rao"):
    return {
        "X-User-Id": user_id,
        "X-Role": "doctor",
        "X-User-Name": name
    }


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# R3: Dynamic Prompt & Context
# ============================================================================
def test_r3_system_prompt_builder(db_session: Session):
    """Verify system prompt includes clinic clock, 30-day calendar, appointments, and minor clause."""
    prompt_p01 = build_patient_system_prompt("P01", db_session)
    assert "Asha Verma" in prompt_p01
    assert "TODAY'S CLINIC CLOCK" in prompt_p01
    assert "30-DAY CLINIC CALENDAR" in prompt_p01
    assert "Sunday" in prompt_p01
    assert "AVAILABLE TOOLS" in prompt_p01
    assert "search_clinic_docs" in prompt_p01

    # Check minor clause for Divya Pillai (P12, age 11)
    prompt_minor = build_patient_system_prompt("P12", db_session)
    assert "CRITICAL - MINOR PATIENT" in prompt_minor
    assert "Paediatric Ophthalmology" in prompt_minor
    assert "Dr. Vikram Menon" in prompt_minor


# ============================================================================
# R3 & R6: Red-Flag Pre-emption Before Agent/Tool Execution
# ============================================================================
@patch.object(LLMService, "check_red_flags")
def test_r3_red_flag_preempts_chat_and_creates_urgent_case(mock_rf, db_session: Session):
    """Red flag in chat triggers emergency response, urgent case [Chat], and prevents tool execution."""
    mock_rf.return_value = RedFlagOutput(
        red_flag=True,
        category="chemical_or_injury",
        why="Chemical cleaner splashed into eye"
    )

    # Clean up prior urgent cases for P02
    db_session.query(UrgentCase).filter(UrgentCase.patient_id == "P02").delete()
    db_session.commit()

    thread_id = "test_thread_rf_01"
    res = client.post(
        "/api/v1/chat",
        headers=patient_auth("P02", "Rohan Mehta"),
        json={
            "message": "Floor cleaner went in my eye this morning and it burns",
            "thread_id": thread_id
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_emergency"] is True
    assert data["answer"] == EMERGENCY_RESPONSE_TEXT
    assert data["sources"] == []
    assert data["pending_action"] is None

    # Verify urgent case created in database
    urgent = db_session.query(UrgentCase).filter(
        UrgentCase.patient_id == "P02",
        UrgentCase.is_seen == False
    ).first()
    assert urgent is not None
    assert urgent.reason.startswith("[Chat]")
    assert urgent.appointment_id is None
    assert urgent.category == "chemical_or_injury"


@patch.object(LLMService, "check_red_flags")
def test_r3_red_flag_service_failure_halts_safely(mock_rf):
    """If red flag service fails, chat stops safely and returns fixed safety message."""
    mock_rf.side_effect = Exception("API connection timed out")

    res = client.post(
        "/api/v1/chat",
        headers=patient_auth("P03", "Priya Sharma"),
        json={
            "message": "What time does the clinic open tomorrow?",
            "thread_id": "test_thread_rf_fail"
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_error"] is True
    assert data["answer"] == SAFETY_CHECK_ERROR_MESSAGE
    assert data["sources"] == []


# ============================================================================
# R4: Thread Ownership & RBAC Isolation (Safeguard 1)
# ============================================================================
@patch.object(LLMService, "check_red_flags")
def test_r4_thread_ownership_cross_patient_forbidden(mock_rf):
    """Threads are strictly bound to authenticated patient. Cross-patient access gets 403."""
    mock_rf.return_value = RedFlagOutput(red_flag=False, category=None, why="Routine greeting")
    thread_id = "patient_10_secure_thread"

    mock_model = MagicMock()
    mock_model.bind_tools.return_value = mock_model
    mock_model.invoke.return_value = AIMessage(content="Hello! How can I help you today?")

    # Patient P10 establishes thread
    with patch.object(LLMService, "get_model", return_value=mock_model):
        res1 = client.post(
            "/api/v1/chat",
            headers=patient_auth("P10", "Amit Patel"),
            json={"message": "Hello clinic", "thread_id": thread_id}
        )
        assert res1.status_code == 200

    # Patient P11 attempts to access P10's thread -> 403 Forbidden
    res2 = client.post(
        "/api/v1/chat",
        headers=patient_auth("P11", "Sunita Rao"),
        json={"message": "Can I see his appointments?", "thread_id": thread_id}
    )
    assert res2.status_code == 403
    assert "do not have permission" in res2.json()["detail"]


def test_r4_chat_endpoint_rbac():
    """Non-patient roles (staff, doctor) cannot access the patient chat endpoint."""
    res_staff = client.post("/api/v1/chat", headers=staff_auth(), json={"message": "Hello"})
    assert res_staff.status_code == 403

    res_doc = client.post("/api/v1/chat", headers=doctor_auth(), json={"message": "Hello"})
    assert res_doc.status_code == 403


# ============================================================================
# R5: Human-in-the-Loop Confirmation Workflow (Safeguards 3 & 4)
# ============================================================================
@patch.object(LLMService, "check_red_flags")
def test_r5_booking_confirmation_confirm_path(mock_rf, db_session: Session):
    """
    Booking initiates confirmation card via interrupt.
    No database change occurs before Confirm.
    Confirming creates the booking.
    """
    mock_rf.return_value = RedFlagOutput(red_flag=False, category=None, why="Routine follow-up")

    # Pick a future Monday for Dr. Anand Rao (General)
    curr = ClockService.now().date() + timedelta(days=2)
    while curr.weekday() != 0:
        curr += timedelta(days=1)
    target_date = curr.isoformat()
    target_time = "10:00"

    # Clean up any conflicting booking for P15
    db_session.query(Appointment).filter(
        Appointment.patient_id == "P15",
        Appointment.speciality == "General"
    ).delete()
    db_session.query(Appointment).filter(
        Appointment.doctor_id == "D1",
        Appointment.appointment_date == curr,
        Appointment.start_time == time(10, 0)
    ).delete()
    db_session.commit()

    thread_id = f"test_thread_book_confirm_{curr.day}"
    mock_model = MagicMock()
    mock_model.bind_tools.return_value = mock_model

    # Step 1: Agent calls book_appointment tool
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[{
            "name": "book_appointment",
            "args": {
                "doctor_id": "D1",
                "speciality": "General",
                "visit_type": "new",
                "date": target_date,
                "start_time": target_time,
                "reason": "Annual eye examination"
            },
            "id": "call_book_confirm_01"
        }]
    )
    mock_model.invoke.return_value = tool_call_msg

    try:
        with patch.object(LLMService, "get_model", return_value=mock_model):
            # Send booking message
            res1 = client.post(
                "/api/v1/chat",
                headers=patient_auth("P15", "Kavita Reddy"),
                json={
                    "message": f"Book me with Dr. Rao for a general check on {target_date} at 10:00. Reason: Annual eye examination",
                    "thread_id": thread_id
                }
            )
            assert res1.status_code == 200
            data1 = res1.json()
            assert data1["pending_action"] is not None
            assert data1["pending_action"]["action"] == "book"
            assert "Dr. Anand Rao" in data1["pending_action"]["summary"]

            # Verify appointment NOT yet booked in database
            db_appt_before = db_session.query(Appointment).filter(
                Appointment.patient_id == "P15",
                Appointment.appointment_date == curr,
                Appointment.start_time == time(10, 0)
            ).first()
            assert db_appt_before is None

            # Step 2: Patient confirms action
            # Model response after tool completes:
            mock_model.invoke.return_value = AIMessage(content="Your appointment has been confirmed and booked!")

            res2 = client.post(
                "/api/v1/chat",
                headers=patient_auth("P15", "Kavita Reddy"),
                json={
                    "thread_id": thread_id,
                    "confirm": True
                }
            )
            assert res2.status_code == 200
            data2 = res2.json()
            assert data2["pending_action"] is None

            # Verify appointment IS NOW booked in database
            db_appt_after = db_session.query(Appointment).filter(
                Appointment.patient_id == "P15",
                Appointment.appointment_date == curr,
                Appointment.start_time == time(10, 0)
            ).first()
            assert db_appt_after is not None
            assert db_appt_after.status == "booked"
    finally:
        db_session.query(Appointment).filter(
            Appointment.patient_id == "P15",
            Appointment.appointment_date == curr,
            Appointment.start_time == time(10, 0)
        ).delete()
        db_session.commit()


@patch.object(LLMService, "check_red_flags")
def test_r5_booking_confirmation_decline_path(mock_rf, db_session: Session):
    """Pressing No on confirmation card declines action with no database change."""
    mock_rf.return_value = RedFlagOutput(red_flag=False, category=None, why="Routine follow-up")

    curr = ClockService.now().date() + timedelta(days=2)
    while curr.weekday() != 2:  # Wednesday
        curr += timedelta(days=1)
    target_date = curr.isoformat()
    target_time = "11:00"

    thread_id = f"test_thread_book_decline_{curr.day}"
    mock_model = MagicMock()
    mock_model.bind_tools.return_value = mock_model

    tool_call_msg = AIMessage(
        content="",
        tool_calls=[{
            "name": "book_appointment",
            "args": {
                "doctor_id": "D2",
                "speciality": "Glaucoma",
                "visit_type": "new",
                "date": target_date,
                "start_time": target_time,
                "reason": "Eye pressure check"
            },
            "id": "call_book_decline_01"
        }]
    )
    mock_model.invoke.return_value = tool_call_msg

    with patch.object(LLMService, "get_model", return_value=mock_model):
        res1 = client.post(
            "/api/v1/chat",
            headers=patient_auth("P14", "Deepak Joshi"),
            json={
                "message": f"Book Dr. Iyer on {target_date} at 11:00. Reason: Eye pressure check",
                "thread_id": thread_id
            }
        )
        assert res1.status_code == 200
        assert res1.json()["pending_action"] is not None

        # Patient declines action
        mock_model.invoke.return_value = AIMessage(content="Booking cancelled. What would you like to do instead?")
        res2 = client.post(
            "/api/v1/chat",
            headers=patient_auth("P14", "Deepak Joshi"),
            json={
                "thread_id": thread_id,
                "confirm": False
            }
        )
        assert res2.status_code == 200
        assert res2.json()["pending_action"] is None

        # Verify NO appointment was booked
        appt = db_session.query(Appointment).filter(
            Appointment.patient_id == "P14",
            Appointment.appointment_date == curr,
            Appointment.start_time == time(11, 0)
        ).first()
        assert appt is None


@patch.object(LLMService, "check_red_flags")
def test_r5_safeguard_4_new_message_declines_pending_action(mock_rf, db_session: Session):
    """
    Safeguard 4: When a new message arrives while an action is pending confirmation,
    the pending action is safely declined and cleared before processing the new message.
    """
    mock_rf.return_value = RedFlagOutput(red_flag=False, category=None, why="Routine")

    curr = ClockService.now().date() + timedelta(days=2)
    while curr.weekday() != 0:
        curr += timedelta(days=1)
    target_date = curr.isoformat()

    thread_id = "test_thread_safeguard_4"
    mock_model = MagicMock()
    mock_model.bind_tools.return_value = mock_model

    # Step 1: Agent calls book_appointment -> pauses on interrupt
    mock_model.invoke.return_value = AIMessage(
        content="",
        tool_calls=[{
            "name": "book_appointment",
            "args": {
                "doctor_id": "D1",
                "speciality": "General",
                "visit_type": "new",
                "date": target_date,
                "start_time": "12:00",
                "reason": "Eye check"
            },
            "id": "call_book_sg4_01"
        }]
    )

    with patch.object(LLMService, "get_model", return_value=mock_model):
        res1 = client.post(
            "/api/v1/chat",
            headers=patient_auth("P18", "Pooja Nair"),
            json={"message": "Book me next Monday at 12:00. Reason: Eye check", "thread_id": thread_id}
        )
        assert res1.status_code == 200
        assert res1.json()["pending_action"] is not None

        # Step 2: Patient sends a completely new message instead of confirming
        mock_model.invoke.return_value = AIMessage(content="The clinic opens at 9:00 AM on Saturdays.")
        res2 = client.post(
            "/api/v1/chat",
            headers=patient_auth("P18", "Pooja Nair"),
            json={"message": "Actually what time do you open on Saturday?", "thread_id": thread_id}
        )
        assert res2.status_code == 200
        assert res2.json()["pending_action"] is None

        # Verify NO appointment was booked for the pending action
        appt = db_session.query(Appointment).filter(
            Appointment.patient_id == "P18",
            Appointment.appointment_date == curr,
            Appointment.start_time == time(12, 0)
        ).first()
        assert appt is None


# ============================================================================
# R6: Grounded Clinic-Document Answers & Citations
# ============================================================================
def test_r6_grounded_answer_with_citations():
    """search_clinic_docs returns grounded consultation fee answer with citations."""
    from app.services.tools import search_clinic_docs

    with patch.object(LLMService, "get_model") as mock_model:
        mock_model.return_value = RunnableLambda(
            lambda x: AIMessage(
                content='{"answer": "Consultation fees at NetraCare are ₹800 for a new consultation and ₹500 for a follow-up visit.", "source_ids": ["clinic_policy_faq_consultation_fees_0"], "answered": true}'
            )
        )
        res = search_clinic_docs.invoke({"query": "How much is a new consultation?"})
        assert res["answered"] is True
        assert "800" in res["answer"]
        assert any("clinic_policy_faq.md" in s for s in res["sources"])


def test_r6_unanswered_question_fixed_i_dont_know():
    """Uncovered questions return fixed literal I don't know without sources."""
    from app.services.tools import search_clinic_docs

    with patch.object(LLMService, "get_model") as mock_model:
        mock_model.return_value = RunnableLambda(
            lambda x: AIMessage(
                content='{"answer": "No parking details found in clinic documents.", "source_ids": [], "answered": false}'
            )
        )
        res = search_clinic_docs.invoke({"query": "Is there parking at the clinic?"})
        assert res["answered"] is False
        assert I_DONT_KNOW_RESPONSE in res["answer"]
        assert res["sources"] == []
