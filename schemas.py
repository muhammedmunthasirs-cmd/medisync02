import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field


# ---------- Auth ----------
class UserCreate(BaseModel):
    email: str
    full_name: str
    phone: Optional[str] = None
    password: str = Field(min_length=8)
    role: str = "patient"  # doctor | patient | admin
    preferred_language: Optional[str] = "English"


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    phone: Optional[str] = None
    role: str
    is_active: bool = True
    preferred_language: Optional[str] = "English"

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Doctor & UIDAI E-KYC ----------
class DoctorRegistration(BaseModel):
    email: str
    full_name: str
    phone: Optional[str] = None
    password: str = Field(min_length=8)
    registration_number: str
    medical_council: str
    specialization: str
    experience_years: int = 1
    languages: List[str] = ["English"]
    clinic_name: Optional[str] = None
    aadhaar_masked: Optional[str] = None
    uidai_doc_name: Optional[str] = None
    degree_doc_name: Optional[str] = None


class DoctorAvailabilityUpdate(BaseModel):
    availability_days: List[str] = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    availability_time: str = "09:00 AM - 05:00 PM"


class DoctorProfileOut(BaseModel):
    id: str
    user_id: str
    full_name: str
    email: str
    phone: Optional[str]
    registration_number: str
    medical_council: str
    specialization: str
    experience_years: int
    languages: List[str]
    clinic_name: Optional[str]
    availability_days: List[str] = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    availability_time: str = "09:00 AM - 05:00 PM"
    aadhaar_masked: Optional[str]
    kyc_status: str
    kyc_docs: Dict[str, Any]
    verified_by: Optional[str]
    verification_notes: Optional[str]
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class DoctorMatchResult(BaseModel):
    doctor_id: str
    user_id: str
    full_name: str
    specialization: str
    experience_years: int
    clinic_name: Optional[str]
    languages: List[str]
    availability_days: List[str] = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    availability_time: str = "09:00 AM - 05:00 PM"
    kyc_status: str
    match_score: int  # 0 to 100 percentage
    matched_languages: List[str]
    is_available_for_call: bool = True


# ---------- Patient Profile ----------
class PatientProfileCreate(BaseModel):
    mrn: str
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    preferred_language: str = "English"
    emergency_contact: Optional[str] = None
    known_allergies: List[str] = []
    notes: Optional[str] = None


class PatientProfileOut(BaseModel):
    id: str
    user_id: str
    full_name: str
    email: str
    phone: Optional[str]
    mrn: str
    date_of_birth: Optional[str]
    gender: Optional[str]
    blood_group: Optional[str]
    preferred_language: str
    emergency_contact: Optional[str]
    known_allergies: List[str]
    notes: Optional[str]

    class Config:
        from_attributes = True


# ---------- Clinical Consultations & Prescriptions ----------
class MedicationItem(BaseModel):
    name: str
    dosage: str
    frequency: str  # e.g. "1-0-1 (Morning & Night)"
    duration: str   # e.g. "5 days"
    instructions: str = "After food"


class ConsultationCreate(BaseModel):
    patient_id: str
    doctor_id: str
    language_used: str = "English"
    problem_description: Optional[str] = None
    diagnosis_cure: Optional[str] = None
    follow_up_date: Optional[str] = None
    notes: Optional[str] = None


class PrescriptionCreate(BaseModel):
    consultation_id: str
    patient_id: str
    problem_description: Optional[str] = None
    diagnosis_cure: Optional[str] = None
    follow_up_date: Optional[str] = None
    medications: List[MedicationItem] = []
    general_advice: Optional[str] = None


class PrescriptionOut(BaseModel):
    id: str
    consultation_id: str
    patient_id: str
    doctor_id: str
    doctor_name: str
    patient_name: str
    medications: List[Dict[str, Any]]
    general_advice: Optional[str]
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class DocumentRequestCreate(BaseModel):
    note: Optional[str] = None


class DocumentVerifyAction(BaseModel):
    verified: bool = True
    notes: Optional[str] = None


class ConsultationOut(BaseModel):
    id: str
    patient_id: str
    patient_name: str
    doctor_id: str
    doctor_name: str
    doctor_specialization: Optional[str] = None
    scheduled_at: datetime.datetime
    status: str
    language_used: str
    problem_description: Optional[str]
    diagnosis_cure: Optional[str]
    follow_up_date: Optional[str]
    notes: Optional[str]
    documents_required: bool = False
    documents_verified: bool = False
    documents_request_note: Optional[str] = None
    uploaded_documents: List[Dict[str, Any]] = []
    created_at: datetime.datetime
    prescription: Optional[PrescriptionOut] = None

    class Config:
        from_attributes = True


# ---------- Notifications ----------
class NotificationOut(BaseModel):
    id: str
    user_id: str
    title: str
    message: str
    category: str
    is_read: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True


# ---------- Admin & Audit ----------
class AdminVerificationAction(BaseModel):
    doctor_id: str
    action: str  # "approve" | "reject"
    verification_notes: Optional[str] = None


class AdminStatsOut(BaseModel):
    total_users: int
    total_patients: int
    total_doctors: int
    pending_kyc_count: int
    verified_doctors_count: int
    total_consultations: int
    total_prescriptions: int


class AuditLogOut(BaseModel):
    id: str
    actor_id: str
    actor_name: Optional[str]
    action: str
    target_type: Optional[str]
    target_id: Optional[str]
    details: Dict[str, Any]
    created_at: datetime.datetime

    class Config:
        from_attributes = True


# ---------- Patients Support ----------
class PatientCreate(BaseModel):
    mrn: str
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    preferred_language: str = "English"
    known_allergies: List[str] = []
    notes: Optional[str] = None
    initial_problem: Optional[str] = None


class PatientUpdate(BaseModel):
    full_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    known_allergies: Optional[List[str]] = None
    notes: Optional[str] = None


class PatientOut(BaseModel):
    id: str
    mrn: str
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    preferred_language: Optional[str] = "English"
    date_of_birth: Optional[str]
    gender: Optional[str]
    blood_group: Optional[str] = None
    known_allergies: List[str]
    notes: Optional[str]
    created_at: datetime.datetime
    document_count: int = 0
    open_conflict_count: int = 0

    class Config:
        from_attributes = True


class DocumentOut(BaseModel):
    id: str
    patient_id: str
    doc_type: str
    original_filename: str
    document_date: Optional[str]
    date_source: str
    structured_data: Dict[str, Any]
    extraction_status: str
    extraction_notes: Optional[str]
    uploaded_at: datetime.datetime

    class Config:
        from_attributes = True


class DocumentDetailOut(DocumentOut):
    raw_text: Optional[str]


class TimelineEvent(BaseModel):
    date: Optional[str]
    date_is_estimated: bool
    document_id: str
    doc_type: str
    title: str
    summary: str
    structured_data: Dict[str, Any]


class ConflictOut(BaseModel):
    id: str
    patient_id: str
    kind: str
    severity: str
    description: str
    related_document_ids: List[str]
    resolved: bool
    resolved_note: Optional[str]
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class ConflictResolve(BaseModel):
    note: Optional[str] = None

