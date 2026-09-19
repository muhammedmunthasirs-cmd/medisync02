from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_admin(current_user: models.User):
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required.")


@router.get("/stats", response_model=schemas.AdminStatsOut)
def get_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_admin(current_user)

    total_users = db.query(models.User).count()
    total_patients = db.query(models.User).filter(models.User.role == "patient").count()
    total_doctors = db.query(models.User).filter(models.User.role == "doctor").count()
    pending_kyc = db.query(models.DoctorProfile).filter(models.DoctorProfile.kyc_status == "pending").count()
    verified_docs = db.query(models.DoctorProfile).filter(models.DoctorProfile.kyc_status == "verified").count()
    total_consultations = db.query(models.Consultation).count()
    total_prescriptions = db.query(models.Prescription).count()

    return schemas.AdminStatsOut(
        total_users=total_users,
        total_patients=total_patients,
        total_doctors=total_doctors,
        pending_kyc_count=pending_kyc,
        verified_doctors_count=verified_docs,
        total_consultations=total_consultations,
        total_prescriptions=total_prescriptions,
    )


@router.get("/doctors/pending-kyc", response_model=List[schemas.DoctorProfileOut])
def get_pending_kyc(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_admin(current_user)

    profiles = db.query(models.DoctorProfile).filter(models.DoctorProfile.kyc_status == "pending").all()
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
                aadhaar_masked=p.aadhaar_masked,
                kyc_status=p.kyc_status,
                kyc_docs=p.kyc_docs or {},
                verified_by=p.verified_by,
                verification_notes=p.verification_notes,
                created_at=p.created_at,
            )
        )
    return results


@router.post("/doctors/verify")
def verify_doctor(
    payload: schemas.AdminVerificationAction,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_admin(current_user)

    doctor = db.query(models.DoctorProfile).filter(models.DoctorProfile.id == payload.doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor profile not found.")

    new_status = "verified" if payload.action.lower() == "approve" else "rejected"
    doctor.kyc_status = new_status
    doctor.verified_by = current_user.id
    doctor.verification_notes = payload.verification_notes or ("Verified UIDAI and credentials." if new_status == "verified" else "Credentials rejected.")

    # Notify doctor
    if new_status == "verified":
        title = "UIDAI E-KYC Verified Successfully"
        msg = f"Congratulations Dr. {doctor.user.full_name}! Your UIDAI E-KYC and Medical Council registration have been verified by the Administrator. You can now accept patient video consultations."
    else:
        title = "UIDAI E-KYC Verification Update"
        msg = f"Your KYC application could not be verified. Note from Administrator: {doctor.verification_notes}"

    notif = models.Notification(
        user_id=doctor.user_id,
        title=title,
        message=msg,
        category="kyc",
    )
    db.add(notif)

    # Log audit
    audit = models.AuditLog(
        actor_id=current_user.id,
        action=f"DOCTOR_KYC_{new_status.upper()}",
        target_type="doctor",
        target_id=doctor.id,
        details={
            "doctor_name": doctor.user.full_name,
            "registration_number": doctor.registration_number,
            "action": payload.action,
            "notes": payload.verification_notes,
        },
    )
    db.add(audit)

    db.commit()
    return {"status": "ok", "doctor_id": doctor.id, "kyc_status": new_status}


@router.get("/audit-logs", response_model=List[schemas.AuditLogOut])
def get_audit_logs(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_admin(current_user)

    logs = db.query(models.AuditLog).order_by(models.AuditLog.created_at.desc()).limit(limit).all()
    out = []
    for log in logs:
        out.append(
            schemas.AuditLogOut(
                id=log.id,
                actor_id=log.actor_id,
                actor_name=log.actor.full_name if log.actor else "System",
                action=log.action,
                target_type=log.target_type,
                target_id=log.target_id,
                details=log.details or {},
                created_at=log.created_at,
            )
        )
    return out
