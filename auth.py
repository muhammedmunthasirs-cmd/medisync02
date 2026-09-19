import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import hash_password, verify_password, create_access_token
from ..deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=schemas.Token, status_code=status.HTTP_201_CREATED)
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    assigned_role = payload.role if payload.role in ("doctor", "patient", "admin", "clinician") else "patient"

    user = models.User(
        email=payload.email,
        full_name=payload.full_name,
        phone=payload.phone,
        role=assigned_role,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.flush()

    if assigned_role in ("patient", "clinician"):
        # Create Patient entity and PatientProfile
        short_id = uuid.uuid4().hex[:6].upper()
        mrn = f"MRN-{short_id}"
        patient_record = models.Patient(
            mrn=mrn,
            full_name=payload.full_name,
            notes="Account created via self-service patient portal.",
            created_by=user.id,
        )
        db.add(patient_record)

        patient_profile = models.PatientProfile(
            user_id=user.id,
            mrn=mrn,
            preferred_language=payload.preferred_language or "English",
        )
        db.add(patient_profile)

    # Add welcome notification
    welcome_notif = models.Notification(
        user_id=user.id,
        title="Welcome to MediSync",
        message=f"Welcome to MediSync, {payload.full_name}! Your {assigned_role.capitalize()} account is active.",
        category="system",
    )
    db.add(welcome_notif)

    db.commit()
    db.refresh(user)

    token = create_access_token(subject=user.id)
    return schemas.Token(access_token=token, user=make_user_out(user))


def make_user_out(user: models.User) -> schemas.UserOut:
    lang = "English"
    if user.patient_profile and user.patient_profile.preferred_language:
        lang = user.patient_profile.preferred_language
    elif user.doctor_profile and user.doctor_profile.languages:
        lang = user.doctor_profile.languages[0]
    return schemas.UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        role=user.role,
        is_active=user.is_active,
        preferred_language=lang,
    )


@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(subject=user.id)
    return schemas.Token(access_token=token, user=make_user_out(user))


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return make_user_out(current_user)
