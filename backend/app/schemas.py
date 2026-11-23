from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Literal, Dict, Any
from datetime import date, time, datetime
from enum import Enum

class RoleEnum(str, Enum):
    patient = "patient"
    doctor = "doctor"
    staff = "staff"

class VisitTypeEnum(str, Enum):
    new = "new"
    follow_up = "follow_up"

class AppointmentStatusEnum(str, Enum):
    booked = "booked"
    completed = "completed"
    cancelled = "cancelled"

class ReasonCodeEnum(str, Enum):
    INVALID_START_TIME = "INVALID_START_TIME"
    IN_PAST = "IN_PAST"
    BEYOND_30_DAYS = "BEYOND_30_DAYS"
    CLINIC_CLOSED = "CLINIC_CLOSED"
    HOLIDAY = "HOLIDAY"
    OUTSIDE_SESSION = "OUTSIDE_SESSION"
    ENDS_AFTER_SESSION = "ENDS_AFTER_SESSION"
    DOCTOR_OFF = "DOCTOR_OFF"
    SURGERY_SESSION = "SURGERY_SESSION"
    SPECIALITY_MISMATCH = "SPECIALITY_MISMATCH"
    DOUBLE_BOOKED = "DOUBLE_BOOKED"
    ACTIVE_BOOKING_EXISTS = "ACTIVE_BOOKING_EXISTS"
    NO_PREVIOUS_VISIT = "NO_PREVIOUS_VISIT"
    FOLLOW_UP_DIFFERENT_DOCTOR = "FOLLOW_UP_DIFFERENT_DOCTOR"
    INSIDE_2_HOURS = "INSIDE_2_HOURS"
    NOT_YOUR_APPOINTMENT = "NOT_YOUR_APPOINTMENT"
    NOT_ACTIVE = "NOT_ACTIVE"
    PATIENT_DETAILS_MISMATCH = "PATIENT_DETAILS_MISMATCH"
    RED_FLAG = "RED_FLAG"

class LoginRequest(BaseModel):
    role: RoleEnum
    mobile: Optional[str] = None
    name: Optional[str] = None
    doctor_id: Optional[str] = None

class LoginResponse(BaseModel):
    token: str
    role: RoleEnum
    user_id: str
    name: str
    mobile: Optional[str] = None

class DoctorSpecialityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    speciality: str

class WeeklyScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    day: str
    session: str
    status: str

class DoctorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    doctor_id: str
    name: str
    specialities: List[str]

class FreeSlotsQuery(BaseModel):
    doctor_id: str
    date: date
    visit_type: VisitTypeEnum

class FreeSlotsResponse(BaseModel):
    doctor_id: str
    date: date
    visit_type: VisitTypeEnum
    duration_minutes: int
    slots: List[str]

class AppointmentCreate(BaseModel):
    patient_id: Optional[str] = None
    doctor_id: str
    speciality: str
    visit_type: VisitTypeEnum
    date: date
    start_time: str  # "HH:MM"
    reason: Optional[str] = Field(None, max_length=300, description="Reason for visit (required, max 300 chars)")
    source: Optional[str] = Field("Website", description="Origin of booking: Website, Chat, Staff, MCP")
    intake_notes: Optional[str] = Field(None, description="Pre-assessment intake answers")

class AppointmentReschedule(BaseModel):
    doctor_id: str
    speciality: str
    visit_type: VisitTypeEnum
    date: date
    start_time: str

class CompleteAppointmentRequest(BaseModel):
    doctor_note: str = Field(..., min_length=1, description="Required doctor clinical note")

class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    appointment_id: str
    patient_id: str
    patient_name: Optional[str] = None
    doctor_id: str
    doctor_name: Optional[str] = None
    speciality: str
    visit_type: VisitTypeEnum
    appointment_date: date
    start_time: str
    end_time: str
    status: AppointmentStatusEnum
    reason: Optional[str] = None
    doctor_note: Optional[str] = None
    is_urgent: bool = False
    emergency_message: Optional[str] = None
    approval_status: Optional[str] = None
    outcome: Optional[str] = None
    source: Optional[str] = "Website"
    intake_notes: Optional[str] = None
    created_at: Optional[datetime] = None

class UrgentCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    patient_id: str
    patient_name: Optional[str] = None
    patient_mobile: Optional[str] = None
    appointment_id: Optional[str] = None
    reason: str
    category: str
    why: str
    is_seen: bool
    created_at: datetime
    seen_at: Optional[datetime] = None
    is_chat_origin: bool = False
    is_mcp_origin: bool = False
    source: Optional[str] = "Appointment"

class PastVisitNoteOut(BaseModel):
    appointment_id: str
    date: date
    doctor_id: str
    doctor_name: str
    speciality: str
    visit_type: str
    reason: Optional[str] = None
    doctor_note: Optional[str] = None

class DoctorSummaryOut(BaseModel):
    patient_id: str
    patient_name: str
    age: Optional[int] = None
    general_health: str
    allergies: str
    today_reason: Optional[str] = None
    summary: str
    disclaimer: str = "AI summary of recorded notes. Check the notes below."
    past_notes: List[PastVisitNoteOut] = []

class FactOfTheDayOut(BaseModel):
    fact: str
    caveat: str = "General information, not medical advice"

class StaffApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    appointment_id: str
    patient_id: str
    patient_name: Optional[str] = None
    action_type: str  # 'cancel' or 'reschedule'
    new_doctor_id: Optional[str] = None
    new_doctor_name: Optional[str] = None
    new_speciality: Optional[str] = None
    new_visit_type: Optional[str] = None
    new_date: Optional[date] = None
    new_start_time: Optional[str] = None
    new_end_time: Optional[str] = None
    status: str  # 'pending', 'approved', 'rejected'
    reason: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None

class StaffApprovalActionResponse(BaseModel):
    approval_id: int
    status: str
    message: str
    appointment: Optional[AppointmentOut] = None

class RuleRefusalDetail(BaseModel):
    reason_code: ReasonCodeEnum
    message: str
    outcome: str = "refused"  # "refused" or "to_staff"

# ============================================================================
# Iteration 3: Patient Chat & Search Debug Schemas
# ============================================================================
class ChatMessage(BaseModel):
    role: Literal["patient", "assistant", "user"]
    content: str = Field(..., min_length=1, max_length=1000)

class ChatRequest(BaseModel):
    message: Optional[str] = Field(None, max_length=500, description="Patient message up to 500 characters")
    history: List[ChatMessage] = Field(default_factory=list, description="Optional previous messages")
    thread_id: Optional[str] = Field(None, description="LangGraph thread ID")
    confirm: Optional[bool] = Field(None, description="Patient confirmation True/False from confirmation card")

class ChatResponse(BaseModel):
    answer: str
    sources: List[str] = Field(default_factory=list)
    is_emergency: bool = False
    is_error: bool = False
    pending_action: Optional[Dict[str, Any]] = None
    thread_id: Optional[str] = None

class SearchDebugChunk(BaseModel):
    source: str
    section: str
    chunk_id: str
    content: str
    score: float

class SearchDebugResponse(BaseModel):
    query: str
    keyword_only: List[SearchDebugChunk]
    vector_only: List[SearchDebugChunk]
    hybrid: List[SearchDebugChunk]

