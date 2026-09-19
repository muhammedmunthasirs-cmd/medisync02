import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import hash_password
from ..deps import get_current_user
from ..config import UPLOAD_DIR

router = APIRouter(prefix="/api/doctors", tags=["doctors"])


@router.post("/register", response_model=schemas.Token, status_code=status.HTTP_201_CREATED)
def register_doctor(
    payload: schemas.DoctorRegistration,
    db: Session = Depends(get_db),
):
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    user = models.User(
        email=payload.email,
        full_name=payload.full_name,
        phone=payload.phone,
        role="doctor",
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.flush()

    doctor_profile = models.DoctorProfile(
        user_id=user.id,
        registration_number=payload.registration_number,
        medical_council=payload.medical_council,
        specialization=payload.specialization,
        experience_years=payload.experience_years,
        languages=payload.languages,
        clinic_name=payload.clinic_name,
        aadhaar_masked=payload.aadhaar_masked or "XXXX-XXXX-0000",
        kyc_status="pending",
        kyc_docs={
            "uidai_cert": payload.uidai_doc_name or "UIDAI_EKYC_Certified.pdf",
            "degree_cert": payload.degree_doc_name or "Medical_Council_Registration_Cert.pdf",
        },
    )
    db.add(doctor_profile)

    # Add notification for admin
    admins = db.query(models.User).filter(models.User.role == "admin").all()
    for admin in admins:
        notif = models.Notification(
            user_id=admin.id,
            title="New Doctor UIDAI KYC Submitted",
            message=f"Dr. {payload.full_name} ({payload.specialization}) submitted UIDAI E-KYC and credentials for verification.",
            category="kyc",
        )
        db.add(notif)

    # Add welcome notification for doctor
    doc_notif = models.Notification(
        user_id=user.id,
        title="KYC Registration Submitted",
        message="Your UIDAI E-KYC and Medical Council documents have been submitted. An administrator will review and verify your profile shortly.",
        category="kyc",
    )
    db.add(doc_notif)

    # Log audit
    audit = models.AuditLog(
        actor_id=user.id,
        action="DOCTOR_REGISTERED",
        target_type="doctor",
        target_id=doctor_profile.id,
        details={
            "registration_number": payload.registration_number,
            "medical_council": payload.medical_council,
            "specialization": payload.specialization,
        },
    )
    db.add(audit)

    db.commit()
    db.refresh(user)

    from ..security import create_access_token
    token = create_access_token(subject=user.id)
    return schemas.Token(access_token=token, user=schemas.UserOut.model_validate(user))


@router.post("/upload-kyc-doc")
async def upload_kyc_doc(
    doc_type: str = Form(...),  # uidai | degree
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "doctor":
        raise HTTPException(status_code=403, detail="Only doctors can upload KYC documents.")

    doctor = db.query(models.DoctorProfile).filter(models.DoctorProfile.user_id == current_user.id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor profile not found.")

    ext = os.path.splitext(file.filename)[1].lower()
    safe_name = f"kyc_{current_user.id}_{doc_type}{ext}"
    target_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(target_path, "wb") as f:
        f.write(await file.read())

    current_docs = dict(doctor.kyc_docs or {})
    current_docs[doc_type] = file.filename
    doctor.kyc_docs = current_docs
    db.commit()

    return {"status": "ok", "filename": file.filename, "doc_type": doc_type}


@router.get("/match", response_model=List[schemas.DoctorMatchResult])
def match_doctors(
    language: Optional[str] = None,
    specialization: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Language-based matchmaking engine.
    Finds verified doctors, computes match scores based on language and specialization.
    """
    doctors = db.query(models.DoctorProfile).join(models.User).filter(
        models.DoctorProfile.kyc_status == "verified"
    ).all()

    target_lang = (language or "").strip().lower()
    target_spec = (specialization or "").strip().lower()

    results = []
    for doc in doctors:
        doc_langs = [l.strip() for l in (doc.languages or [])]
        doc_langs_lower = [l.lower() for l in doc_langs]

        matched_langs = []
        score = 50  # Base score for verified doctor

        if target_lang:
            if target_lang in doc_langs_lower:
                score += 35
                idx = doc_langs_lower.index(target_lang)
                matched_langs.append(doc_langs[idx])
            elif "english" in doc_langs_lower:
                score += 10
                matched_langs.append("English")
            else:
                score -= 30
        else:
            score += 20
            matched_langs = doc_langs[:2]

        if target_spec:
            spec_keywords = [k.strip() for k in target_spec.split() if len(k) > 2]
            doc_spec_lower = doc.specialization.lower()
            if target_spec in doc_spec_lower or any(k in doc_spec_lower for k in spec_keywords):
                score += 35
            else:
                score -= 10

        score = max(10, min(100, score))

        doc_display_name = doc.user.full_name if doc.user.full_name.startswith("Dr.") else f"Dr. {doc.user.full_name}"
        results.append(
            schemas.DoctorMatchResult(
                doctor_id=doc.id,
                user_id=doc.user_id,
                full_name=doc_display_name,
                specialization=doc.specialization,
                experience_years=doc.experience_years,
                clinic_name=doc.clinic_name,
                languages=doc_langs,
                availability_days=doc.availability_days or ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                availability_time=doc.availability_time or "09:00 AM - 05:00 PM",
                kyc_status=doc.kyc_status,
                match_score=score,
                matched_languages=matched_langs if matched_langs else doc_langs[:1],
                is_available_for_call=True,
            )
        )

    # Sort descending by match score
    results.sort(key=lambda x: x.match_score, reverse=True)
    return results


@router.put("/me/availability", response_model=schemas.DoctorProfileOut)
def update_availability(
    payload: schemas.DoctorAvailabilityUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role != "doctor":
        raise HTTPException(status_code=403, detail="Only doctors can update their availability.")

    doc = db.query(models.DoctorProfile).filter(models.DoctorProfile.user_id == current_user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Doctor profile not found.")

    doc.availability_days = payload.availability_days
    doc.availability_time = payload.availability_time
    db.commit()
    db.refresh(doc)

    return schemas.DoctorProfileOut(
        id=doc.id,
        user_id=doc.user_id,
        full_name=doc.user.full_name,
        email=doc.user.email,
        phone=doc.user.phone,
        registration_number=doc.registration_number,
        medical_council=doc.medical_council,
        specialization=doc.specialization,
        experience_years=doc.experience_years,
        languages=doc.languages or [],
        clinic_name=doc.clinic_name,
        availability_days=doc.availability_days or ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        availability_time=doc.availability_time or "09:00 AM - 05:00 PM",
        aadhaar_masked=doc.aadhaar_masked,
        kyc_status=doc.kyc_status,
        kyc_docs=doc.kyc_docs or {},
        verified_by=doc.verified_by,
        verification_notes=doc.verification_notes,
        created_at=doc.created_at,
    )


@router.get("", response_model=List[schemas.DoctorProfileOut])
def list_doctors(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.DoctorProfile).join(models.User)
    if status_filter:
        query = query.filter(models.DoctorProfile.kyc_status == status_filter)
    elif current_user.role == "patient":
        # Patients only see verified doctors
        query = query.filter(models.DoctorProfile.kyc_status == "verified")

    profiles = query.all()
    results = []
    for p in profiles:
        results.append(
            schemas.DoctorProfileOut(
                id=p.id,
                user_id=p.user_id,
                full_name=p.user.full_name,
                email=p.user.email,
                phone=p.user.phone,
                registration_number=p.registration_number,
                medical_council=p.medical_council,
                specialization=p.specialization,
                experience_years=p.experience_years,
                languages=p.languages or [],
                clinic_name=p.clinic_name,
                availability_days=p.availability_days or ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                availability_time=p.availability_time or "09:00 AM - 05:00 PM",
                aadhaar_masked=p.aadhaar_masked,
                kyc_status=p.kyc_status,
                kyc_docs=p.kyc_docs or {},
                verified_by=p.verified_by,
                verification_notes=p.verification_notes,
                created_at=p.created_at,
            )
        )
    return results


@router.get("/{doctor_id}", response_model=schemas.DoctorProfileOut)
def get_doctor(
    doctor_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    p = db.query(models.DoctorProfile).filter(models.DoctorProfile.id == doctor_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Doctor profile not found.")

    return schemas.DoctorProfileOut(
        id=p.id,
        user_id=p.user_id,
        full_name=p.user.full_name,
        email=p.user.email,
        phone=p.user.phone,
        registration_number=p.registration_number,
        medical_council=p.medical_council,
        specialization=p.specialization,
        experience_years=p.experience_years,
        languages=p.languages or [],
        clinic_name=p.clinic_name,
        availability_days=p.availability_days or ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        availability_time=p.availability_time or "09:00 AM - 05:00 PM",
        aadhaar_masked=p.aadhaar_masked,
        kyc_status=p.kyc_status,
        kyc_docs=p.kyc_docs or {},
        verified_by=p.verified_by,
        verification_notes=p.verification_notes,
        created_at=p.created_at,
    )
