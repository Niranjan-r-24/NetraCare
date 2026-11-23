import sys
import os
import pytest
from datetime import datetime, date, time, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath("backend"))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Doctor, Patient, Appointment, StaffApproval, UrgentCase
from app.schemas import ReasonCodeEnum, VisitTypeEnum
from app.services.clock import ClockService
from app.services.llm import LLMService, RedFlagOutput, EMERGENCY_RESPONSE_TEXT
from app.services.rag import RAGService, I_DONT_KNOW_RESPONSE
from app.services.tools import (
    search_clinic_docs,
    list_doctors,
    find_slots,
    my_appointments,
    book_appointment,
    cancel_appointment,
    reschedule_appointment,
    ALL_TOOLS
)
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_r2_all_tools_metadata():
    """Verify all 7 tools exist, have valid descriptions, and patient_id is never an LLM argument."""
    tool_names = [t.name for t in ALL_TOOLS]
    expected_names = [
        "search_clinic_docs",
        "list_doctors",
        "find_slots",
        "my_appointments",
        "book_appointment",
        "cancel_appointment",
        "reschedule_appointment"
    ]
    assert tool_names == expected_names

    for t in ALL_TOOLS:
        assert t.description, f"Tool {t.name} missing description"
        args = list(t.args.keys())
        assert "patient_id" not in args, f"Tool {t.name} must never expose patient_id to the LLM!"


def test_r2_list_doctors(db_session: Session):
    """Test list_doctors returns all doctors and supports speciality filtering."""
    # All doctors
    all_docs = list_doctors.invoke({})
    assert len(all_docs) == 5
    doc_ids = [d["doctor_id"] for d in all_docs]
    assert set(doc_ids) == {"D1", "D2", "D3", "D4", "D5"}
    for d in all_docs:
        assert d["name"]
        assert len(d["specialities"]) >= 1
        assert len(d["opd_days"]) >= 1
        assert len(d["opd_schedule"]) >= 1

    # Filtered by speciality
    glaucoma_docs = list_doctors.invoke({"speciality": "Glaucoma"})
    assert len(glaucoma_docs) == 1
    assert glaucoma_docs[0]["name"] == "Dr. Meera Iyer"
    assert glaucoma_docs[0]["doctor_id"] == "D2"


def test_r2_find_slots(db_session: Session):
    """Test find_slots returns up to 10 earliest free slots and respects filters."""
    # Find paediatric slots (Dr. Vikram Menon on Saturday)
    now = ClockService.now()
    start_str = (now.date() + timedelta(days=1)).isoformat()
    end_str = (now.date() + timedelta(days=14)).isoformat()

    slots = find_slots.invoke({
        "speciality": "Paediatric",
        "visit_type": "new",
        "start_date": start_str,
        "end_date": end_str
    })
    assert isinstance(slots, list)
    assert len(slots) <= 10
    if slots:
        assert all(s["speciality"].lower() == "paediatric" for s in slots)
        assert all(s["doctor_id"] == "D5" for s in slots)
        assert all(s["duration_minutes"] == 20 for s in slots)
        # Ensure earliest first
        dates = [(s["date"], s["start_time"]) for s in slots]
        assert dates == sorted(dates)

    # Doctor off on Thursday (Dr. Meera Iyer)
    curr = now.date() + timedelta(days=1)
    while curr.weekday() != 3:  # 3 is Thursday
        curr += timedelta(days=1)
    thursday_str = curr.isoformat()

    thurs_slots = find_slots.invoke({
        "doctor_id": "D2",
        "start_date": thursday_str,
        "end_date": thursday_str
    })
    assert thurs_slots == [], "Dr. Iyer is off on Thursdays so no slots should be returned"

    # Session filter AM vs PM on next Monday (Dr. Anand Rao has OPD)
    curr = now.date() + timedelta(days=1)
    while curr.weekday() != 0:  # 0 is Monday
        curr += timedelta(days=1)
    monday_str = curr.isoformat()

    am_slots = find_slots.invoke({
        "doctor_id": "D1",
        "start_date": monday_str,
        "end_date": monday_str,
        "session": "AM"
    })
    if am_slots:
        assert all(s["session"] == "AM" for s in am_slots)
        assert all(s["start_time"] < "13:00" for s in am_slots)

    pm_slots = find_slots.invoke({
        "doctor_id": "D1",
        "start_date": monday_str,
        "end_date": monday_str,
        "session": "PM"
    })
    if pm_slots:
        assert all(s["session"] == "PM" for s in pm_slots)
        assert all(s["start_time"] >= "14:00" for s in pm_slots)


def test_r2_my_appointments(db_session: Session):
    """Test my_appointments returns authenticated patient's appointments and isolates data."""
    p01_appts = my_appointments.invoke(
        {},
        config={"configurable": {"patient_id": "P01"}}
    )
    assert isinstance(p01_appts, list)

    # Cross-patient check: ensure P02 does not see P01's appointments
    p02_appts = my_appointments.invoke(
        {},
        config={"configurable": {"patient_id": "P02"}}
    )
    assert isinstance(p02_appts, list)
    p01_ids = {a["appointment_id"] for a in p01_appts}
    p02_ids = {a["appointment_id"] for a in p02_appts}
    assert p01_ids.isdisjoint(p02_ids), "Patient appointments must be completely isolated"

    # Unauthenticated context returns empty list
    unauth_appts = my_appointments.invoke({}, config={"configurable": {}})
    assert unauth_appts == []


@patch.object(LLMService, "check_red_flags")
def test_r2_book_appointment_refusals_and_emergency(mock_rf, db_session: Session):
    """Test book_appointment rule enforcement and red-flag check."""
    mock_rf.return_value = RedFlagOutput(red_flag=False, category=None, why="Routine check")
    config = {"configurable": {"patient_id": "P01", "auto_confirm": True}}

    # Missing reason
    res_no_reason = book_appointment.invoke({
        "doctor_id": "D1",
        "speciality": "Cataract",
        "visit_type": "new",
        "date": "2026-11-20",
        "start_time": "10:00",
        "reason": ""
    }, config=config)
    assert res_no_reason["result"] == "refused"
    assert res_no_reason["reason_code"] == "MISSING_REASON"

    # Doctor off (Dr. Meera Iyer on Thursday)
    curr = ClockService.now().date() + timedelta(days=1)
    while curr.weekday() != 3:
        curr += timedelta(days=1)
    res_off = book_appointment.invoke({
        "doctor_id": "D2",
        "speciality": "Glaucoma",
        "visit_type": "new",
        "date": curr.isoformat(),
        "start_time": "10:00",
        "reason": "Routine eye check"
    }, config=config)
    assert res_off["result"] == "refused"
    assert res_off["reason_code"] == ReasonCodeEnum.DOCTOR_OFF.value

    # Speciality mismatch (Dr. Rao does not cover Paediatric)
    res_mismatch = book_appointment.invoke({
        "doctor_id": "D1",
        "speciality": "Paediatric",
        "visit_type": "new",
        "date": "2026-11-23",
        "start_time": "10:00",
        "reason": "Child vision problem"
    }, config=config)
    assert res_mismatch["result"] == "refused"
    assert res_mismatch["reason_code"] == ReasonCodeEnum.SPECIALITY_MISMATCH.value

    # Red-flag emergency reason creates UrgentCase
    mock_rf.return_value = RedFlagOutput(
        red_flag=True,
        category="chemical_or_injury",
        why="Chemical burn to eye"
    )
    res_emergency = book_appointment.invoke({
        "doctor_id": "D1",
        "speciality": "Cataract",
        "visit_type": "new",
        "date": "2026-11-23",
        "start_time": "10:00",
        "reason": "Chemical cleaner splashed in my eye and burning severely"
    }, config=config)
    assert res_emergency["result"] == "emergency"
    assert "urgent attention" in res_emergency["message"].lower()

    # Verify urgent case created with [Chat] prefix
    urgent = db_session.query(UrgentCase).filter(
        UrgentCase.patient_id == "P01",
        UrgentCase.reason.like("%[Chat]%")
    ).first()
    assert urgent is not None


@patch.object(LLMService, "check_red_flags")
def test_r2_book_appointment_confirmation_workflow(mock_rf, db_session: Session):
    """Test book_appointment confirmation workflow: no change if cancelled, booked if confirmed."""
    mock_rf.return_value = RedFlagOutput(red_flag=False, category=None, why="Routine check")
    patient_id = "P14"
    # Find a valid future Wednesday for Dr. Meera Iyer (Glaucoma)
    now = ClockService.now().date()
    curr = now + timedelta(days=2)
    while curr.weekday() != 2:  # Wednesday
        curr += timedelta(days=1)
    target_date = curr.isoformat()
    target_time = "10:00"

    # Clean up any conflicting booking for P14
    db_session.query(Appointment).filter(
        Appointment.patient_id == patient_id,
        Appointment.appointment_date == curr,
        Appointment.start_time == time(10, 0)
    ).delete()
    db_session.commit()

    try:
        # 1. Decline on confirmation card (auto_confirm=False)
        decline_config = {"configurable": {"patient_id": patient_id, "auto_confirm": False}}
        res_declined = book_appointment.invoke({
            "doctor_id": "D2",
            "speciality": "Glaucoma",
            "visit_type": "new",
            "date": target_date,
            "start_time": target_time,
            "reason": "Routine glaucoma screening"
        }, config=decline_config)

        assert res_declined["result"] == "cancelled_by_patient"
        existing = db_session.query(Appointment).filter(
            Appointment.patient_id == patient_id,
            Appointment.appointment_date == curr,
            Appointment.start_time == time(10, 0),
            Appointment.status == "booked"
        ).first()
        assert existing is None, "Database must not change when patient cancels confirmation!"

        # 2. Confirm on confirmation card (auto_confirm=True)
        confirm_config = {"configurable": {"patient_id": patient_id, "auto_confirm": True}}
        res_confirmed = book_appointment.invoke({
            "doctor_id": "D2",
            "speciality": "Glaucoma",
            "visit_type": "new",
            "date": target_date,
            "start_time": target_time,
            "reason": "Routine glaucoma screening"
        }, config=confirm_config)

        assert res_confirmed["result"] == "booked"
        assert "appointment_id" in res_confirmed
        new_id = res_confirmed["appointment_id"]

        db_session.expire_all()
        created = db_session.query(Appointment).filter(Appointment.appointment_id == new_id).first()
        assert created is not None
        assert created.status == "booked"
        assert created.doctor_id == "D2"
        assert created.speciality == "Glaucoma"
        assert created.patient_id == patient_id
    finally:
        db_session.query(Appointment).filter(
            Appointment.patient_id == patient_id,
            Appointment.appointment_date == curr,
            Appointment.start_time == time(10, 0)
        ).delete()
        db_session.commit()


def test_r2_cancel_appointment_workflow(db_session: Session):
    """Test cancel_appointment ownership checks, confirmation, and late cancel routing."""
    future_date = ClockService.now().date() + timedelta(days=5)
    test_appt = Appointment(
        appointment_id="TEST_TOOL_CANCEL_01",
        patient_id="P01",
        doctor_id="D1",
        speciality="Cataract",
        visit_type="new",
        appointment_date=future_date,
        start_time=time(11, 0),
        end_time=time(11, 20),
        status="booked",
        reason="Check cataract progression"
    )
    db_session.merge(test_appt)
    db_session.commit()

    # 1. Cross-patient attempt: P02 attempts to cancel P01's appointment
    cross_config = {"configurable": {"patient_id": "P02", "auto_confirm": True}}
    res_cross = cancel_appointment.invoke(
        {"appointment_id": "TEST_TOOL_CANCEL_01"},
        config=cross_config
    )
    assert res_cross["result"] == "refused"
    assert res_cross["reason_code"] == ReasonCodeEnum.NOT_YOUR_APPOINTMENT.value

    # 2. Patient declines confirmation (auto_confirm=False)
    decline_config = {"configurable": {"patient_id": "P01", "auto_confirm": False}}
    res_decline = cancel_appointment.invoke(
        {"appointment_id": "TEST_TOOL_CANCEL_01"},
        config=decline_config
    )
    assert res_decline["result"] == "cancelled_by_patient"
    db_session.expire_all()
    reloaded = db_session.query(Appointment).filter(Appointment.appointment_id == "TEST_TOOL_CANCEL_01").first()
    assert reloaded.status == "booked"

    # 3. Patient confirms standard cancellation (> 2 hours away)
    confirm_config = {"configurable": {"patient_id": "P01", "auto_confirm": True}}
    res_confirm = cancel_appointment.invoke(
        {"appointment_id": "TEST_TOOL_CANCEL_01"},
        config=confirm_config
    )
    assert res_confirm["result"] == "cancelled"
    db_session.expire_all()
    reloaded = db_session.query(Appointment).filter(Appointment.appointment_id == "TEST_TOOL_CANCEL_01").first()
    assert reloaded.status == "cancelled"

    # 4. Late cancellation (< 2 hours away)
    now = datetime.now()
    late_appt = Appointment(
        appointment_id="TEST_TOOL_CANCEL_LATE",
        patient_id="P01",
        doctor_id="D1",
        speciality="Cataract",
        visit_type="new",
        appointment_date=now.date(),
        start_time=(now + timedelta(minutes=45)).time().replace(second=0, microsecond=0),
        end_time=(now + timedelta(minutes=65)).time().replace(second=0, microsecond=0),
        status="booked",
        reason="Urgent follow-up"
    )
    db_session.merge(late_appt)
    db_session.commit()

    res_late = cancel_appointment.invoke(
        {"appointment_id": "TEST_TOOL_CANCEL_LATE"},
        config=confirm_config
    )
    assert res_late["result"] == "to_staff"
    assert res_late["reason_code"] == ReasonCodeEnum.INSIDE_2_HOURS.value

    db_session.expire_all()
    reloaded_late = db_session.query(Appointment).filter(Appointment.appointment_id == "TEST_TOOL_CANCEL_LATE").first()
    assert reloaded_late.status == "booked", "Appointment must remain booked until Staff approves"

    approval = db_session.query(StaffApproval).filter(
        StaffApproval.appointment_id == "TEST_TOOL_CANCEL_LATE",
        StaffApproval.status == "pending"
    ).first()
    assert approval is not None
    assert approval.action_type == "cancel"


def test_r2_reschedule_appointment_workflow(db_session: Session):
    """Test reschedule_appointment ownership, rules, confirmation, and late reschedule."""
    future_date = ClockService.now().date() + timedelta(days=6)
    test_appt = Appointment(
        appointment_id="TEST_TOOL_RESCHED_01",
        patient_id="P03",
        doctor_id="D1",
        speciality="General",
        visit_type="new",
        appointment_date=future_date,
        start_time=time(10, 0),
        end_time=time(10, 20),
        status="booked",
        reason="General eye check"
    )
    db_session.merge(test_appt)
    db_session.commit()

    # 1. Cross-patient attempt
    cross_config = {"configurable": {"patient_id": "P04", "auto_confirm": True}}
    res_cross = reschedule_appointment.invoke({
        "appointment_id": "TEST_TOOL_RESCHED_01",
        "new_doctor_id": "D1",
        "new_date": (future_date + timedelta(days=1)).isoformat(),
        "new_start_time": "11:00"
    }, config=cross_config)
    assert res_cross["result"] == "refused"
    assert res_cross["reason_code"] == ReasonCodeEnum.NOT_YOUR_APPOINTMENT.value

    # 2. Invalid replacement slot (Doctor off on Sunday)
    curr = future_date
    while curr.weekday() != 6:  # Sunday
        curr += timedelta(days=1)
    res_invalid = reschedule_appointment.invoke({
        "appointment_id": "TEST_TOOL_RESCHED_01",
        "new_doctor_id": "D1",
        "new_date": curr.isoformat(),
        "new_start_time": "10:00"
    }, config={"configurable": {"patient_id": "P03", "auto_confirm": True}})
    assert res_invalid["result"] == "refused"
    assert res_invalid["reason_code"] == ReasonCodeEnum.CLINIC_CLOSED.value

    # 3. Patient declines confirmation on a valid Monday/Wednesday/Friday for Dr. Kiran Shah (D3)
    target_date = future_date + timedelta(days=1)
    while target_date.weekday() not in (0, 2, 4):  # Mon, Wed, Fri
        target_date += timedelta(days=1)
    
    # Ensure slot is free
    db_session.query(Appointment).filter(
        Appointment.doctor_id == "D3",
        Appointment.appointment_date == target_date,
        Appointment.start_time == time(10, 0)
    ).delete()
    db_session.commit()

    res_decline = reschedule_appointment.invoke({
        "appointment_id": "TEST_TOOL_RESCHED_01",
        "new_doctor_id": "D3",
        "new_date": target_date.isoformat(),
        "new_start_time": "10:00"
    }, config={"configurable": {"patient_id": "P03", "auto_confirm": False}})
    assert res_decline["result"] == "cancelled_by_patient"

    # 4. Patient confirms standard reschedule (> 2 hours away)
    res_confirm = reschedule_appointment.invoke({
        "appointment_id": "TEST_TOOL_RESCHED_01",
        "new_doctor_id": "D3",
        "new_date": target_date.isoformat(),
        "new_start_time": "10:00"
    }, config={"configurable": {"patient_id": "P03", "auto_confirm": True}})
    assert res_confirm["result"] == "rescheduled"

    db_session.expire_all()
    reloaded = db_session.query(Appointment).filter(Appointment.appointment_id == "TEST_TOOL_RESCHED_01").first()
    assert reloaded.doctor_id == "D3"
    assert reloaded.appointment_date == target_date
    assert reloaded.start_time == time(10, 0)
    assert reloaded.status == "booked"


def test_r2_search_clinic_docs():
    """Test search_clinic_docs returns grounded answer with sources, or I don't know."""
    # 1. Answerable question with mocked model output
    with patch.object(LLMService, "get_model") as mock_model:
        mock_model.return_value = RunnableLambda(
            lambda x: AIMessage(
                content='{"answer": "Consultation fees at NetraCare are ₹800 for a new consultation and ₹500 for a follow-up visit.", "source_ids": ["clinic_policy_faq_consultation_fees_0"], "answered": true}'
            )
        )
        ans = search_clinic_docs.invoke({"query": "What are the consultation fees at NetraCare?"})
        assert isinstance(ans, dict)
        assert ans["answered"] is True
        assert "800" in ans["answer"] or "fee" in ans["answer"].lower()
        assert len(ans["sources"]) >= 1

    # 2. Out-of-scope question
    with patch.object(LLMService, "get_model") as mock_model:
        mock_model.return_value = RunnableLambda(
            lambda x: AIMessage(
                content='{"answer": "I do not see parking info in the documents.", "source_ids": [], "answered": false}'
            )
        )
        idk = search_clinic_docs.invoke({"query": "Is there valet parking available at the clinic?"})
        assert idk["answered"] is False
        assert "I don't know" in idk["answer"]
        assert idk["sources"] == []


@patch.object(LLMService, "check_red_flags")
def test_r2_langgraph_interrupt_integration(mock_rf, db_session: Session):
    """Verify tools interact correctly with LangGraph's interrupt() and Command(resume=True)."""
    mock_rf.return_value = RedFlagOutput(red_flag=False, category=None, why="Routine check")

    tools = [book_appointment]
    tool_node = ToolNode(tools)

    builder = StateGraph(MessagesState)
    builder.add_node("tools", tool_node)
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    checkpointer = InMemorySaver()
    graph = builder.compile(checkpointer=checkpointer)

    # Valid slot for P16 with Dr. Anand Rao (General) on Monday or Wednesday
    curr = ClockService.now().date() + timedelta(days=3)
    while curr.weekday() not in (0, 2):  # Monday or Wednesday
        curr += timedelta(days=1)

    # Clean up any existing booking at that slot
    db_session.query(Appointment).filter(
        Appointment.doctor_id == "D1",
        Appointment.appointment_date == curr,
        Appointment.start_time == time(11, 0)
    ).delete()
    db_session.query(Appointment).filter(
        Appointment.patient_id == "P16",
        Appointment.speciality == "General",
        Appointment.status == "booked"
    ).delete()
    db_session.commit()

    config = {"configurable": {"thread_id": "test_thread_01", "patient_id": "P16"}}
    call_msg = AIMessage(
        content="",
        tool_calls=[{
            "name": "book_appointment",
            "args": {
                "doctor_id": "D1",
                "speciality": "General",
                "visit_type": "new",
                "date": curr.isoformat(),
                "start_time": "11:00",
                "reason": "Annual vision check"
            },
            "id": "call_book_test_01"
        }]
    )

    try:
        # Invoke graph: must pause on interrupt
        step1 = graph.invoke({"messages": [call_msg]}, config=config)
        assert "__interrupt__" in step1
        interrupts = step1["__interrupt__"]
        assert len(interrupts) == 1
        assert interrupts[0].value["action"] == "book"
        assert "Book Dr. Anand Rao" in interrupts[0].value["summary"]

        # Resume graph with Command(resume=True)
        step2 = graph.invoke(Command(resume=True), config=config)
        last_msg = step2["messages"][-1]
        assert "booked" in last_msg.content
        assert "A" in last_msg.content  # Contains appointment ID
    finally:
        db_session.query(Appointment).filter(
            Appointment.patient_id == "P16",
            Appointment.appointment_date == curr,
            Appointment.start_time == time(11, 0)
        ).delete()
        db_session.commit()
