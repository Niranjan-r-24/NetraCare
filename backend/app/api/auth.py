import json
import base64
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Patient, Doctor
from app.schemas import LoginRequest, LoginResponse, RoleEnum

router = APIRouter(prefix="/auth", tags=["Authentication"])

def generate_next_patient_id(db: Session) -> str:
    patients = db.query(Patient.patient_id).all()
    max_num = 0
    for (p_id,) in patients:
        if p_id.startswith("P") and p_id[1:].isdigit():
            num = int(p_id[1:])
            if num > max_num:
                max_num = num
    next_num = max_num + 1
    return f"P{next_num:02d}"

@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    if req.role == RoleEnum.patient:
        if not req.mobile or not req.name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mobile number and name are required for patient login."
            )
        clean_mobile = req.mobile.strip()
        clean_name = req.name.strip()

        patient = db.query(Patient).filter(Patient.mobile == clean_mobile).first()
        if not patient:
            # R3: New mobile creates a new patient record
            new_id = generate_next_patient_id(db)
            patient = Patient(
                patient_id=new_id,
                name=clean_name,
                mobile=clean_mobile
            )
            db.add(patient)
            db.commit()
            db.refresh(patient)
        else:
            # Update name if provided
            if clean_name and patient.name != clean_name:
                patient.name = clean_name
                db.commit()
                db.refresh(patient)

        token_payload = {"role": "patient", "user_id": patient.patient_id, "name": patient.name, "mobile": patient.mobile}
        token = base64.b64encode(json.dumps(token_payload).encode("utf-8")).decode("utf-8")
        return LoginResponse(
            token=token,
            role=RoleEnum.patient,
            user_id=patient.patient_id,
            name=patient.name,
            mobile=patient.mobile
        )

    elif req.role == RoleEnum.doctor:
        if not req.doctor_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Doctor ID is required for doctor login."
            )
        doc = db.query(Doctor).filter(Doctor.doctor_id == req.doctor_id.strip()).first()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Doctor with ID {req.doctor_id} not found."
            )
        token_payload = {"role": "doctor", "user_id": doc.doctor_id, "name": doc.name}
        token = base64.b64encode(json.dumps(token_payload).encode("utf-8")).decode("utf-8")
        return LoginResponse(
            token=token,
            role=RoleEnum.doctor,
            user_id=doc.doctor_id,
            name=doc.name
        )

    elif req.role == RoleEnum.staff:
        staff_name = (req.name or "Clinic Staff").strip()
        staff_id = "STAFF_01"
        token_payload = {"role": "staff", "user_id": staff_id, "name": staff_name}
        token = base64.b64encode(json.dumps(token_payload).encode("utf-8")).decode("utf-8")
        return LoginResponse(
            token=token,
            role=RoleEnum.staff,
            user_id=staff_id,
            name=staff_name
        )
