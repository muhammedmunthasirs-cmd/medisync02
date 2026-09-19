from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/patients", tags=["patients"])


def _to_out(db: Session, p: models.Patient) -> schemas.PatientOut:
    doc_count = db.query(models.Document).filter(models.Document.patient_id == p.id).count()
    open_conflicts = (
        db.query(models.ConflictFlag)
        .filter(models.ConflictFlag.patient_id == p.id, models.ConflictFlag.resolved == False)  # noqa: E712
        .count()
    )
    out = schemas.PatientOut.model_validate(p)
    out.document_count = doc_count
    out.open_conflict_count = open_conflicts

    # Populate profile details if exists
    profile = db.query(models.PatientProfile).filter(models.PatientProfile.mrn == p.mrn).first()
    if profile:
        out.blood_group = profile.blood_group
        out.preferred_language = profile.preferred_language or "English"
        if profile.user:
            out.email = profile.user.email
            out.phone = profile.user.phone
    return out


@router.get("", response_model=list[schemas.PatientOut])
def list_patients(
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    q = db.query(models.Patient)
    if search:
        like = f"%{search}%"
        q = q.filter((models.Patient.full_name.ilike(like)) | (models.Patient.mrn.ilike(like)))
    patients = q.order_by(models.Patient.created_at.desc()).all()
    return [_to_out(db, p) for p in patients]


@router.post("", response_model=schemas.PatientOut, status_code=201)
def create_patient(
    payload: schemas.PatientCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    existing = db.query(models.Patient).filter(models.Patient.mrn == payload.mrn).first()
    if existing:
        raise HTTPException(status_code=400, detail="A patient with this MRN already exists.")

    patient = models.Patient(
        mrn=payload.mrn,
        full_name=payload.full_name,
        date_of_birth=payload.date_of_birth,
        gender=payload.gender,
        known_allergies=payload.known_allergies,
        notes=payload.notes,
        created_by=current_user.id,
    )
    db.add(patient)
    db.flush()

    # Ensure a corresponding User and PatientProfile exist for consultations & login
    email_synthetic = (payload.email or f"{payload.mrn.lower().replace('-', '_')}@medisync.local").strip()
    existing_user = db.query(models.User).filter(models.User.email == email_synthetic).first()
    target_user = existing_user
    if not target_user:
        from ..security import hash_password
        target_user = models.User(
            email=email_synthetic,
            full_name=payload.full_name,
            phone=payload.phone,
            role="patient",
            password_hash=hash_password("PatientPass123!"),
        )
        db.add(target_user)
        db.flush()

    # Check/create PatientProfile
    existing_profile = db.query(models.PatientProfile).filter(models.PatientProfile.user_id == target_user.id).first()
    if not existing_profile:
        new_profile = models.PatientProfile(
            user_id=target_user.id,
            mrn=payload.mrn,
            date_of_birth=payload.date_of_birth,
            gender=payload.gender,
            blood_group=payload.blood_group,
            known_allergies=payload.known_allergies,
            notes=payload.notes,
            preferred_language=payload.preferred_language or "English",
        )
        db.add(new_profile)
    else:
        existing_profile.blood_group = payload.blood_group or existing_profile.blood_group
        existing_profile.preferred_language = payload.preferred_language or existing_profile.preferred_language

    # If created by doctor, create an initial consultation record so both see it
    if current_user.role in ("doctor", "clinician"):
        consultation = models.Consultation(
            patient_id=target_user.id,
            doctor_id=current_user.id,
            language_used=payload.preferred_language or "English",
            problem_description=payload.initial_problem or payload.notes or "Initial consultation record created by doctor.",
            status="scheduled",
        )
        db.add(consultation)

        # Notify patient
        notif = models.Notification(
            user_id=target_user.id,
            title="Registered with Care Provider",
            message=f"Dr. {current_user.full_name} added you to their patient practice list.",
            category="appointment",
        )
        db.add(notif)

    db.commit()
    db.refresh(patient)
    return _to_out(db, patient)


@router.get("/{patient_id}", response_model=schemas.PatientOut)
def get_patient(
    patient_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return _to_out(db, patient)


@router.patch("/{patient_id}", response_model=schemas.PatientOut)
def update_patient(
    patient_id: str,
    payload: schemas.PatientUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(patient, field, value)

    db.commit()
    db.refresh(patient)

    # Allergy list changed -> re-check for allergy conflicts against existing prescriptions
    from ..services.conflicts import recompute_conflicts
    recompute_conflicts(db, patient)
    db.commit()

    return _to_out(db, patient)


@router.delete("/{patient_id}", status_code=204)
def delete_patient(
    patient_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    db.delete(patient)
    db.commit()
    return None
