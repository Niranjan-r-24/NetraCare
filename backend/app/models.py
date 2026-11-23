from datetime import datetime, date, time
from sqlalchemy import (
    Column, String, Integer, Date, Time, DateTime, ForeignKey, UniqueConstraint, Index, Text, Boolean
)
from sqlalchemy.orm import relationship
from app.database import Base

class Doctor(Base):
    __tablename__ = "doctors"

    doctor_id = Column(String(10), primary_key=True, index=True)
    name = Column(String(100), nullable=False)

    specialities = relationship("DoctorSpeciality", back_populates="doctor", cascade="all, delete-orphan")
    schedules = relationship("WeeklySchedule", back_populates="doctor", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="doctor")

class DoctorSpeciality(Base):
    __tablename__ = "doctor_specialities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doctor_id = Column(String(10), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    speciality = Column(String(50), nullable=False)

    __table_args__ = (
        UniqueConstraint("doctor_id", "speciality", name="uq_doctor_speciality"),
    )

    doctor = relationship("Doctor", back_populates="specialities")

class WeeklySchedule(Base):
    __tablename__ = "weekly_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doctor_id = Column(String(10), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    day = Column(String(3), nullable=False)  # Mon, Tue, Wed, Thu, Fri, Sat
    session = Column(String(2), nullable=False)  # AM, PM
    status = Column(String(10), nullable=False)  # OPD, SURGERY, OFF

    __table_args__ = (
        UniqueConstraint("doctor_id", "day", "session", name="uq_doctor_day_session"),
    )

    doctor = relationship("Doctor", back_populates="schedules")

class Holiday(Base):
    __tablename__ = "holidays"

    holiday_date = Column(Date, primary_key=True, index=True)
    name = Column(String(150), nullable=False)

class Patient(Base):
    __tablename__ = "patients"

    patient_id = Column(String(10), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    mobile = Column(String(15), nullable=False, unique=True, index=True)
    year_of_birth = Column(Integer, nullable=True)
    general_health = Column(String(255), nullable=True, default="None recorded")
    allergies = Column(String(255), nullable=True, default="None known")
    created_at = Column(DateTime, default=datetime.utcnow)

    appointments = relationship("Appointment", back_populates="patient")
    urgent_cases = relationship("UrgentCase", back_populates="patient")
    approvals = relationship("StaffApproval", back_populates="patient")

class Appointment(Base):
    __tablename__ = "appointments"

    appointment_id = Column(String(20), primary_key=True, index=True)
    patient_id = Column(String(10), ForeignKey("patients.patient_id"), nullable=False)
    doctor_id = Column(String(10), ForeignKey("doctors.doctor_id"), nullable=False)
    speciality = Column(String(50), nullable=False)
    visit_type = Column(String(15), nullable=False)  # 'new' or 'follow_up'
    appointment_date = Column(Date, nullable=False, index=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    status = Column(String(15), nullable=False, default="booked")  # 'booked', 'completed', 'cancelled'
    reason = Column(String(300), nullable=True)
    doctor_note = Column(Text, nullable=True)
    is_urgent = Column(Boolean, nullable=False, default=False)
    source = Column(String(20), nullable=False, default="Website")
    intake_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_doctor_date_status", "doctor_id", "appointment_date", "status"),
        Index("idx_patient_speciality_status", "patient_id", "speciality", "status"),
        Index("idx_urgent_date", "is_urgent", "appointment_date"),
    )

    doctor = relationship("Doctor", back_populates="appointments")
    patient = relationship("Patient", back_populates="appointments")
    urgent_cases = relationship("UrgentCase", back_populates="appointment")
    approvals = relationship("StaffApproval", back_populates="appointment")

class UrgentCase(Base):
    __tablename__ = "urgent_cases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String(10), ForeignKey("patients.patient_id"), nullable=False, index=True)
    appointment_id = Column(String(20), ForeignKey("appointments.appointment_id"), nullable=True)
    reason = Column(String(300), nullable=False)
    category = Column(String(50), nullable=False)
    why = Column(Text, nullable=False)
    source = Column(String(20), nullable=True, default="Appointment")
    is_seen = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    seen_at = Column(DateTime, nullable=True)

    patient = relationship("Patient", back_populates="urgent_cases")
    appointment = relationship("Appointment", back_populates="urgent_cases")

class StaffApproval(Base):
    __tablename__ = "staff_approvals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    appointment_id = Column(String(20), ForeignKey("appointments.appointment_id"), nullable=False, index=True)
    patient_id = Column(String(10), ForeignKey("patients.patient_id"), nullable=False, index=True)
    action_type = Column(String(20), nullable=False)  # 'cancel' or 'reschedule'
    new_doctor_id = Column(String(10), ForeignKey("doctors.doctor_id"), nullable=True)
    new_speciality = Column(String(50), nullable=True)
    new_visit_type = Column(String(15), nullable=True)
    new_date = Column(Date, nullable=True)
    new_start_time = Column(Time, nullable=True)
    new_end_time = Column(Time, nullable=True)
    status = Column(String(20), nullable=False, default="pending", index=True)  # 'pending', 'approved', 'rejected'
    reason = Column(String(300), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String(100), nullable=True)

    appointment = relationship("Appointment", back_populates="approvals")
    patient = relationship("Patient", back_populates="approvals")
    new_doctor = relationship("Doctor")
