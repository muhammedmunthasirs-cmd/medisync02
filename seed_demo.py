"""
Seeds complete demo accounts for MediSync:
- Administrator: admin@medisync.local / AdminPass123!
- Doctor 1 (Verified): doctor@medisync.local / DoctorPass123! (Dr. Rajesh Sharma, Hindi/Punjabi/English)
- Doctor 2 (Verified): doctor2@medisync.local / DoctorPass123! (Dr. Priya Sundaram, Tamil/Malayalam/Telugu/English)
- Doctor 3 (Pending KYC): doctor.pending@medisync.local / DoctorPass123! (Dr. Amit Patel, Gujarati/Marathi/Hindi)
- Patient 1: patient@medisync.local / PatientPass123! (Asha Verma, Hindi/English)
- Patient 2: patient2@medisync.local / PatientPass123! (Kavitha Murugan, Tamil/Kannada/English)
"""
import sys
import os
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, Base, engine
from app import models
from app.security import hash_password

# Re-create tables
Base.metadata.create_all(bind=engine)
db = SessionLocal()

print("Seeding MediSync platform demo data...")

# 1. Administrator
admin = db.query(models.User).filter(models.User.email == "admin@medisync.local").first()
if not admin:
    admin = models.User(
        email="admin@medisync.local",
        full_name="System Administrator",
        phone="+91 98765 00001",
        role="admin",
        password_hash=hash_password("AdminPass123!"),
    )
    db.add(admin)
    db.flush()
    print("[OK] Created Administrator: admin@medisync.local / AdminPass123!")

# 2. Doctor 1 (Verified, North India languages: Hindi, Punjabi, English)
doc1 = db.query(models.User).filter(models.User.email == "doctor@medisync.local").first()
if not doc1:
    doc1 = models.User(
        email="doctor@medisync.local",
        full_name="Dr. Rajesh Sharma",
        phone="+91 98111 22334",
        role="doctor",
        password_hash=hash_password("DoctorPass123!"),
    )
    db.add(doc1)
    db.flush()

    doc1_profile = models.DoctorProfile(
        user_id=doc1.id,
        registration_number="NMC-IND-88421",
        medical_council="National Medical Commission (NMC)",
        specialization="General Medicine & Cardiology",
        experience_years=12,
        languages=["English", "Hindi", "Punjabi"],
        clinic_name="Apollo Health Hub, New Delhi",
        availability_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        availability_time="09:00 AM - 05:00 PM",
        aadhaar_masked="XXXX-XXXX-9284",
        kyc_status="verified",
        kyc_docs={
            "uidai_cert": "UIDAI_Aadhaar_Verified_9284.xml",
            "degree_cert": "MBBS_MD_NMC_License_88421.pdf",
        },
        verified_by=admin.id,
        verification_notes="Aadhaar and NMC registration verified against National Doctors Registry.",
    )
    db.add(doc1_profile)
    print("[OK] Created Doctor 1 (Verified): doctor@medisync.local / DoctorPass123! (Hindi, Punjabi, English)")

# 3. Doctor 2 (Verified, South India languages: Tamil, Malayalam, Telugu, English)
doc2 = db.query(models.User).filter(models.User.email == "doctor2@medisync.local").first()
if not doc2:
    doc2 = models.User(
        email="doctor2@medisync.local",
        full_name="Dr. Priya Sundaram",
        phone="+91 94444 55667",
        role="doctor",
        password_hash=hash_password("DoctorPass123!"),
    )
    db.add(doc2)
    db.flush()

    doc2_profile = models.DoctorProfile(
        user_id=doc2.id,
        registration_number="TNMC-54321",
        medical_council="Tamil Nadu Medical Council",
        specialization="Pediatrics & Family Medicine",
        experience_years=9,
        languages=["English", "Tamil", "Malayalam", "Telugu"],
        clinic_name="Meenakshi Care Clinic, Chennai",
        availability_days=["Monday", "Tuesday", "Thursday", "Friday", "Saturday"],
        availability_time="10:00 AM - 06:00 PM",
        aadhaar_masked="XXXX-XXXX-4512",
        kyc_status="verified",
        kyc_docs={
            "uidai_cert": "UIDAI_Aadhaar_Verified_4512.xml",
            "degree_cert": "MBBS_DCH_TNMC_54321.pdf",
        },
        verified_by=admin.id,
        verification_notes="State Medical Council and Aadhaar biometric OTP verification confirmed.",
    )
    db.add(doc2_profile)
    print("[OK] Created Doctor 2 (Verified): doctor2@medisync.local / DoctorPass123! (Tamil, Malayalam, Telugu, English)")

# 4. Doctor 3 (Pending KYC for Admin Review)
doc3 = db.query(models.User).filter(models.User.email == "doctor.pending@medisync.local").first()
if not doc3:
    doc3 = models.User(
        email="doctor.pending@medisync.local",
        full_name="Dr. Amit Patel",
        phone="+91 97222 33445",
        role="doctor",
        password_hash=hash_password("DoctorPass123!"),
    )
    db.add(doc3)
    db.flush()

    doc3_profile = models.DoctorProfile(
        user_id=doc3.id,
        registration_number="GMC-77123",
        medical_council="Gujarat Medical Council",
        specialization="Orthopedics & Joint Care",
        experience_years=7,
        languages=["English", "Gujarati", "Marathi", "Hindi"],
        clinic_name="Surat Ortho Spine Center",
        availability_days=["Monday", "Wednesday", "Friday"],
        availability_time="09:30 AM - 04:30 PM",
        aadhaar_masked="XXXX-XXXX-3341",
        kyc_status="pending",
        kyc_docs={
            "uidai_cert": "UIDAI_EKYC_Pending_3341.pdf",
            "degree_cert": "MS_Ortho_Degree_Cert.pdf",
        },
    )
    db.add(doc3_profile)
    print("[OK] Created Doctor 3 (Pending KYC): doctor.pending@medisync.local / DoctorPass123! (Gujarati, Marathi, Hindi)")
else:
    if doc3.doctor_profile:
        doc3.doctor_profile.kyc_status = "pending"
        db.commit()

# 5. Patient 1 (Asha Verma - Hindi & English)
pat1 = db.query(models.User).filter(models.User.email == "patient@medisync.local").first()
if not pat1:
    pat1 = models.User(
        email="patient@medisync.local",
        full_name="Asha Verma",
        phone="+91 98765 43210",
        role="patient",
        password_hash=hash_password("PatientPass123!"),
    )
    db.add(pat1)
    db.flush()

    pat1_profile = models.PatientProfile(
        user_id=pat1.id,
        mrn="MRN-0001",
        date_of_birth="1985-03-12",
        gender="female",
        blood_group="B+",
        preferred_language="Hindi",
        emergency_contact="+91 98765 99999",
        known_allergies=["Penicillin"],
        notes="Hypertension managed on lifestyle. Known allergy to Penicillin group antibiotics.",
    )
    db.add(pat1_profile)

    # Legacy Patient record for timeline & OCR compatibility
    legacy_pat1 = db.query(models.Patient).filter(models.Patient.mrn == "MRN-0001").first()
    if not legacy_pat1:
        legacy_pat1 = models.Patient(
            id=pat1.id,
            mrn="MRN-0001",
            full_name="Asha Verma",
            date_of_birth="1985-03-12",
            gender="female",
            known_allergies=["Penicillin"],
            notes="Seeded demo patient. Upload medical documents to populate timeline and conflict detection.",
            created_by=doc1.id,
        )
        db.add(legacy_pat1)
    print("[OK] Created Patient 1: patient@medisync.local / PatientPass123! (Asha Verma, Preferred: Hindi)")

# 6. Patient 2 (Kavitha Murugan - Tamil & English)
pat2 = db.query(models.User).filter(models.User.email == "patient2@medisync.local").first()
if not pat2:
    pat2 = models.User(
        email="patient2@medisync.local",
        full_name="Kavitha Murugan",
        phone="+91 94441 23456",
        role="patient",
        password_hash=hash_password("PatientPass123!"),
    )
    db.add(pat2)
    db.flush()

    pat2_profile = models.PatientProfile(
        user_id=pat2.id,
        mrn="MRN-0002",
        date_of_birth="1992-07-24",
        gender="female",
        blood_group="O+",
        preferred_language="Tamil",
        emergency_contact="+91 94441 99999",
        known_allergies=["Sulfa drugs"],
        notes="Asthma history since childhood. Prefers Tamil consultation.",
    )
    db.add(pat2_profile)

    legacy_pat2 = db.query(models.Patient).filter(models.Patient.mrn == "MRN-0002").first()
    if not legacy_pat2:
        legacy_pat2 = models.Patient(
            id=pat2.id,
            mrn="MRN-0002",
            full_name="Kavitha Murugan",
            date_of_birth="1992-07-24",
            gender="female",
            known_allergies=["Sulfa drugs"],
            notes="Seeded demo patient 2.",
            created_by=doc2.id,
        )
        db.add(legacy_pat2)
    print("[OK] Created Patient 2: patient2@medisync.local / PatientPass123! (Kavitha Murugan, Preferred: Tamil)")

# 7. Sample Completed Consultation & Prescription
sample_consult = db.query(models.Consultation).first()
if not sample_consult and doc1 and pat1:
    sample_consult = models.Consultation(
        patient_id=pat1.id,
        doctor_id=doc1.id,
        language_used="Hindi",
        problem_description="Patient presented with severe sore throat, dry cough, body aches and intermittent fever (100.4°F) for 3 days.",
        diagnosis_cure="Acute Upper Respiratory Tract Viral Infection. Recommended steam inhalation twice daily, warm saline gargles, high fluid intake, and complete rest for 48 hours.",
        follow_up_date="2026-09-25",
        status="completed",
        notes="Patient advised to monitor temperature and follow up if fever exceeds 102°F or shortness of breath develops.",
    )
    db.add(sample_consult)
    db.flush()

    sample_rx = models.Prescription(
        consultation_id=sample_consult.id,
        patient_id=pat1.id,
        doctor_id=doc1.id,
        medications=[
            {
                "name": "Paracetamol 650mg",
                "dosage": "1 tablet",
                "frequency": "1-0-1 (Morning & Night)",
                "duration": "4 days",
                "instructions": "Take after meals if fever or pain occurs",
            },
            {
                "name": "Levocetirizine 5mg + Montelukast 10mg",
                "dosage": "1 tablet",
                "frequency": "0-0-1 (Night)",
                "duration": "5 days",
                "instructions": "Take at bedtime with water",
            },
            {
                "name": "Dextromethorphan + Chlorpheniramine Syrup",
                "dosage": "10 ml",
                "frequency": "1-1-1 (Thrice daily)",
                "duration": "5 days",
                "instructions": "Take after food for dry cough relief",
            },
        ],
        general_advice="Avoid chilled beverages and oily food. Warm saline water gargle 3 times a day. Wear a mask when near others.",
    )
    db.add(sample_rx)

    # Seed notifications
    notif1 = models.Notification(
        user_id=pat1.id,
        title="Prescription Ready from Dr. Rajesh Sharma",
        message="Your prescription for Acute Upper Respiratory Tract Viral Infection is ready to view and download.",
        category="prescription",
        is_read=False,
    )
    notif2 = models.Notification(
        user_id=admin.id,
        title="Doctor Registration: Dr. Amit Patel",
        message="Dr. Amit Patel (GMC-77123) uploaded UIDAI Aadhaar E-KYC certificates. Action required.",
        category="kyc",
        is_read=False,
    )
    notif3 = models.Notification(
        user_id=doc1.id,
        title="UIDAI E-KYC Approved",
        message="Your National Medical Commission registration and Aadhaar E-KYC have been verified by Admin.",
        category="kyc",
        is_read=True,
    )
    db.add_all([notif1, notif2, notif3])
    print("[OK] Created Sample Consultation, Prescription & Notifications")

db.commit()
db.close()
print("All demo data seeded successfully!")
