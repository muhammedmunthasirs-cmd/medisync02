import os
import uuid
import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user
from ..config import UPLOAD_DIR

router = APIRouter(prefix="/api/consultations", tags=["consultations"])


def _format_consultation(c: models.Consultation, db: Session) -> schemas.ConsultationOut:
    rx = db.query(models.Prescription).filter(models.Prescription.consultation_id == c.id).first()
    rx_out = None
    if rx:
        rx_out = schemas.PrescriptionOut(
            id=rx.id,
            consultation_id=rx.consultation_id,
            patient_id=rx.patient_id,
            doctor_id=rx.doctor_id,
            doctor_name=rx.consultation.doctor.full_name if (rx.consultation and rx.consultation.doctor and rx.consultation.doctor.full_name.startswith("Dr.")) else (f"Dr. {rx.consultation.doctor.full_name}" if rx.consultation and rx.consultation.doctor else "Doctor"),
            patient_name=rx.consultation.patient.full_name if rx.consultation and rx.consultation.patient else "Patient",
            medications=rx.medications or [],
            general_advice=rx.general_advice,
            created_at=rx.created_at,
        )

    doc_profile = db.query(models.DoctorProfile).filter(models.DoctorProfile.user_id == c.doctor_id).first()
    spec = doc_profile.specialization if doc_profile else "General Physician"

    doc_display = c.doctor.full_name if (c.doctor and c.doctor.full_name.startswith("Dr.")) else (f"Dr. {c.doctor.full_name}" if c.doctor else "Doctor")
    return schemas.ConsultationOut(
        id=c.id,
        patient_id=c.patient_id,
        patient_name=c.patient.full_name if c.patient else "Patient",
        doctor_id=c.doctor_id,
        doctor_name=doc_display,
        doctor_specialization=spec,
        scheduled_at=c.scheduled_at,
        status=c.status,
        language_used=c.language_used,
        problem_description=c.problem_description,
        diagnosis_cure=c.diagnosis_cure,
        follow_up_date=c.follow_up_date,
        notes=c.notes,
        documents_required=bool(c.documents_required),
        documents_verified=bool(c.documents_verified),
        documents_request_note=c.documents_request_note,
        uploaded_documents=c.uploaded_documents or [],
        created_at=c.created_at,
        prescription=rx_out,
    )


@router.post("", response_model=schemas.ConsultationOut, status_code=status.HTTP_201_CREATED)
def create_consultation(
    payload: schemas.ConsultationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    consultation = models.Consultation(
        patient_id=payload.patient_id,
        doctor_id=payload.doctor_id,
        language_used=payload.language_used,
        problem_description=payload.problem_description,
        diagnosis_cure=payload.diagnosis_cure,
        follow_up_date=payload.follow_up_date,
        notes=payload.notes,
        status="in_progress",
    )
    db.add(consultation)
    db.flush()

    # Notify doctor
    doctor_notif = models.Notification(
        user_id=payload.doctor_id,
        title="Incoming Video Consultation Request",
        message=f"Patient {current_user.full_name} initiated a consultation session (Language: {payload.language_used}).",
        category="video_call",
    )
    db.add(doctor_notif)

    # Notify patient
    patient_notif = models.Notification(
        user_id=payload.patient_id,
        title="Consultation Session Created",
        message="Your consultation room is ready. The doctor will connect with you shortly.",
        category="video_call",
    )
    db.add(patient_notif)

    # Log audit
    audit = models.AuditLog(
        actor_id=current_user.id,
        action="CONSULTATION_STARTED",
        target_type="consultation",
        target_id=consultation.id,
        details={"patient_id": payload.patient_id, "doctor_id": payload.doctor_id, "language": payload.language_used},
    )
    db.add(audit)

    db.commit()
    db.refresh(consultation)
    return _format_consultation(consultation, db)


@router.post("/prescribe", response_model=schemas.ConsultationOut)
def record_prescription(
    payload: schemas.PrescriptionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Doctor submits patient problem, diagnosis & cure, and itemized medication prescription.
    """
    consultation = db.query(models.Consultation).filter(models.Consultation.id == payload.consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation session not found.")

    if current_user.role not in ("doctor", "admin", "clinician") and current_user.id != consultation.doctor_id:
        raise HTTPException(status_code=403, detail="Only the consulting doctor can write prescriptions.")

    # Check if documents were requested but not yet verified
    if consultation.documents_required and not consultation.documents_verified:
        raise HTTPException(
            status_code=400,
            detail="Document verification required: Patient scan / lab reports must be verified by doctor before issuing prescription."
        )

    # Update consultation details
    if payload.problem_description:
        consultation.problem_description = payload.problem_description
    if payload.diagnosis_cure:
        consultation.diagnosis_cure = payload.diagnosis_cure
    if payload.follow_up_date:
        consultation.follow_up_date = payload.follow_up_date
    consultation.status = "completed"

    # Convert medication objects to dicts
    meds_list = [m.model_dump() for m in payload.medications]

    # Create or update prescription
    existing_rx = db.query(models.Prescription).filter(models.Prescription.consultation_id == consultation.id).first()
    if existing_rx:
        existing_rx.medications = meds_list
        existing_rx.general_advice = payload.general_advice
    else:
        prescription = models.Prescription(
            consultation_id=consultation.id,
            patient_id=consultation.patient_id,
            doctor_id=consultation.doctor_id,
            medications=meds_list,
            general_advice=payload.general_advice,
        )
        db.add(prescription)

    # Notify patient
    patient_notif = models.Notification(
        user_id=consultation.patient_id,
        title="Prescription & Treatment Plan Issued",
        message=f"Dr. {current_user.full_name} has provided your diagnosis, cure instructions, and prescribed medications.",
        category="prescription",
    )
    db.add(patient_notif)

    # Log audit
    audit = models.AuditLog(
        actor_id=current_user.id,
        action="PRESCRIPTION_ISSUED",
        target_type="prescription",
        target_id=consultation.id,
        details={
            "diagnosis_cure": payload.diagnosis_cure,
            "medication_count": len(meds_list),
        },
    )
    db.add(audit)

    db.commit()
    db.refresh(consultation)
    return _format_consultation(consultation, db)


@router.post("/{consultation_id}/request-docs", response_model=schemas.ConsultationOut)
def request_documents(
    consultation_id: str,
    payload: schemas.DocumentRequestCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Doctor flags that the patient must upload scan / lab reports before proceeding.
    """
    consultation = db.query(models.Consultation).filter(models.Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation session not found.")

    if current_user.role not in ("doctor", "admin", "clinician") and current_user.id != consultation.doctor_id:
        raise HTTPException(status_code=403, detail="Only the consulting doctor can request documents.")

    consultation.documents_required = True
    consultation.documents_verified = False
    consultation.documents_request_note = payload.note or "Please upload required scan/lab reports."

    # Notify patient
    notif = models.Notification(
        user_id=consultation.patient_id,
        title="Medical Documents Requested by Doctor",
        message=f"Dr. {current_user.full_name} requested scan/lab reports: {consultation.documents_request_note}",
        category="appointment",
    )
    db.add(notif)
    db.commit()
    db.refresh(consultation)
    return _format_consultation(consultation, db)


@router.post("/{consultation_id}/upload-docs", response_model=schemas.ConsultationOut)
async def upload_consultation_doc(
    consultation_id: str,
    doc_type: str = Form("scan"),  # scan | lab_report | other
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Patient uploads scan or lab reports for the consultation.
    """
    consultation = db.query(models.Consultation).filter(models.Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation session not found.")

    ext = os.path.splitext(file.filename)[1].lower()
    doc_id = uuid.uuid4().hex
    safe_filename = f"report_{consultation_id}_{doc_id[:8]}{ext}"
    target_path = os.path.join(UPLOAD_DIR, safe_filename)
    with open(target_path, "wb") as f:
        f.write(await file.read())

    current_docs = list(consultation.uploaded_documents or [])
    doc_info = {
        "id": doc_id,
        "name": file.filename,
        "type": doc_type,
        "storage_path": safe_filename,
        "uploaded_by": current_user.full_name,
        "uploaded_at": datetime.datetime.utcnow().isoformat(),
    }
    current_docs.append(doc_info)
    consultation.uploaded_documents = current_docs

    # Notify doctor
    notif = models.Notification(
        user_id=consultation.doctor_id,
        title="Patient Uploaded Diagnostic Reports",
        message=f"Patient {current_user.full_name} uploaded {file.filename} for review & verification.",
        category="appointment",
    )
    db.add(notif)
    db.commit()
    db.refresh(consultation)
    return _format_consultation(consultation, db)


@router.post("/{consultation_id}/verify-docs", response_model=schemas.ConsultationOut)
def verify_documents(
    consultation_id: str,
    payload: schemas.DocumentVerifyAction,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Doctor reviews and verifies the uploaded patient documents, unlocking the prescription step.
    """
    consultation = db.query(models.Consultation).filter(models.Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation session not found.")

    if current_user.role not in ("doctor", "admin", "clinician") and current_user.id != consultation.doctor_id:
        raise HTTPException(status_code=403, detail="Only the consulting doctor can verify documents.")

    consultation.documents_verified = payload.verified

    # Notify patient
    status_text = "verified and approved" if payload.verified else "needs re-upload"
    notif = models.Notification(
        user_id=consultation.patient_id,
        title=f"Medical Documents {status_text.capitalize()}",
        message=f"Dr. {current_user.full_name} has {status_text} your submitted scan/lab reports.",
        category="appointment",
    )
    db.add(notif)

    # Log audit
    audit = models.AuditLog(
        actor_id=current_user.id,
        action="DOCUMENTS_VERIFIED" if payload.verified else "DOCUMENTS_REJECTED",
        target_type="consultation",
        target_id=consultation.id,
        details={"verified": payload.verified, "notes": payload.notes},
    )
    db.add(audit)

    db.commit()
    db.refresh(consultation)
    return _format_consultation(consultation, db)


@router.get("", response_model=List[schemas.ConsultationOut])
def list_consultations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.Consultation)
    if current_user.role == "patient":
        query = query.filter(models.Consultation.patient_id == current_user.id)
    elif current_user.role == "doctor":
        query = query.filter(models.Consultation.doctor_id == current_user.id)
    # Admin sees all consultations

    consultations = query.order_by(models.Consultation.created_at.desc()).all()
    return [_format_consultation(c, db) for c in consultations]


@router.get("/{consultation_id}", response_model=schemas.ConsultationOut)
def get_consultation(
    consultation_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    consultation = db.query(models.Consultation).filter(models.Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found.")
    return _format_consultation(consultation, db)
