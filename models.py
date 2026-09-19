import datetime
import uuid

from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship

from .database import Base


def gen_id() -> str:
    return uuid.uuid4().hex


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_id)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    role = Column(String, default="patient")  # doctor | patient | admin | clinician
    is_active = Column(Boolean, default=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    doctor_profile = relationship("DoctorProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    patient_profile = relationship("PatientProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")


class DoctorProfile(Base):
    __tablename__ = "doctor_profiles"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    registration_number = Column(String, nullable=False)  # Medical Council Reg No
    medical_council = Column(String, nullable=False)     # e.g. NMC, State Medical Council
    specialization = Column(String, nullable=False)      # e.g. General Medicine, Cardiology, etc.
    experience_years = Column(Integer, default=1)
    languages = Column(JSON, default=list)               # e.g. ["English", "Hindi", "Tamil"]
    clinic_name = Column(String, nullable=True)
    availability_days = Column(JSON, default=lambda: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
    availability_time = Column(String, default="09:00 AM - 05:00 PM")
    aadhaar_masked = Column(String, nullable=True)       # e.g. "XXXX-XXXX-1234"
    kyc_status = Column(String, default="pending")       # pending | verified | rejected
    kyc_docs = Column(JSON, default=dict)                # {"uidai_cert": "...", "degree_cert": "..."}
    verified_by = Column(String, nullable=True)          # Admin user ID
    verification_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="doctor_profile")


class PatientProfile(Base):
    __tablename__ = "patient_profiles"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    mrn = Column(String, unique=True, index=True, nullable=False)
    date_of_birth = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    blood_group = Column(String, nullable=True)
    preferred_language = Column(String, default="English")
    emergency_contact = Column(String, nullable=True)
    known_allergies = Column(JSON, default=list)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="patient_profile")


class Patient(Base):
    __tablename__ = "patients"

    id = Column(String, primary_key=True, default=gen_id)
    mrn = Column(String, unique=True, index=True, nullable=False)  # Medical Record Number
    full_name = Column(String, nullable=False)
    date_of_birth = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    known_allergies = Column(JSON, default=list)
    notes = Column(Text, nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    documents = relationship("Document", back_populates="patient", cascade="all, delete-orphan")
    conflicts = relationship("ConflictFlag", back_populates="patient", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    doc_type = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    storage_path = Column(String, nullable=False)
    document_date = Column(String, nullable=True)
    date_source = Column(String, default="unknown")

    raw_text = Column(Text, nullable=True)
    structured_data = Column(JSON, default=dict)
    extraction_status = Column(String, default="pending")
    extraction_notes = Column(Text, nullable=True)

    uploaded_by = Column(String, ForeignKey("users.id"), nullable=True)
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow)

    patient = relationship("Patient", back_populates="documents")


class ConflictFlag(Base):
    __tablename__ = "conflict_flags"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    kind = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    related_document_ids = Column(JSON, default=list)
    resolved = Column(Boolean, default=False)
    resolved_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    patient = relationship("Patient", back_populates="conflicts")


class Consultation(Base):
    __tablename__ = "consultations"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("users.id"), nullable=False)
    doctor_id = Column(String, ForeignKey("users.id"), nullable=False)
    scheduled_at = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String, default="completed")  # scheduled | in_progress | completed | cancelled
    language_used = Column(String, default="English")
    problem_description = Column(Text, nullable=True)  # Chief complaint / symptoms
    diagnosis_cure = Column(Text, nullable=True)       # Clinical cure & diagnosis
    follow_up_date = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    documents_required = Column(Boolean, default=False)
    documents_verified = Column(Boolean, default=False)
    documents_request_note = Column(Text, nullable=True)
    uploaded_documents = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    patient = relationship("User", foreign_keys=[patient_id])
    doctor = relationship("User", foreign_keys=[doctor_id])
    prescriptions = relationship("Prescription", back_populates="consultation", cascade="all, delete-orphan")


class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(String, primary_key=True, default=gen_id)
    consultation_id = Column(String, ForeignKey("consultations.id"), nullable=False)
    patient_id = Column(String, ForeignKey("users.id"), nullable=False)
    doctor_id = Column(String, ForeignKey("users.id"), nullable=False)
    medications = Column(JSON, default=list)
    general_advice = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    consultation = relationship("Consultation", back_populates="prescriptions")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    category = Column(String, default="system")  # kyc | appointment | video_call | prescription | system
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="notifications")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=gen_id)
    actor_id = Column(String, ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False)
    target_type = Column(String, nullable=True)
    target_id = Column(String, nullable=True)
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    actor = relationship("User", foreign_keys=[actor_id])
