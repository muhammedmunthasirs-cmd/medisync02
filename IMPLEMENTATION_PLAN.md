# Implementation Plan: MediSync Telemedicine & Clinical Workflow Platform

Upgrade MediSync from a basic clinician timeline demo into a comprehensive healthcare platform featuring an accessible light theme, multi-role authentication (Doctor, Patient, Admin) with instant demo accounts, real-time video calling with camera access, 11-language localization (i18n), doctor UIDAI E-KYC registration & admin verification, language-based doctor matchmaking, clinical diagnosis/cure/prescriptions, role-structured database, and notification center.

## User Review Required

> [!IMPORTANT]
> - **Theme Switch**: The interface will be fully upgraded to a modern, clinical **Light Theme** with high-contrast, accessible typography (`Plus Jakarta Sans` / `Inter`, WCAG AA/AAA compliant).
> - **Authentication & Roles**: Three independent roles are supported: **Doctor**, **Patient**, and **Administrator**. Quick-login buttons on the login screen will allow one-click switching between demo accounts for all three roles.
> - **11 Languages**: Full support for English (main), Hindi, Tamil, Telugu, Malayalam, Gujarati, Marathi, Punjabi, Kannada, Assamese, and Bengali.
> - **Camera Access & Video Consultation**: WebRTC / `navigator.mediaDevices.getUserMedia` with real camera and microphone feeds, in-call clinical prescription drawer, and realistic consultation room simulation.
> - **UIDAI E-KYC**: Doctor registration captures medical council registration, specialization, spoken languages, masked Aadhaar, and document certificate uploads, which administrators can review, approve, or reject.

## Open Questions
None currently. The requirements are well-defined and we will provide seamless fallback behavior (e.g. virtual camera/preview if a physical camera is not attached or blocked).

---

## Proposed Changes

### Backend Architecture & Database Layer

#### [MODIFY] [models.py](file:///c:/Users/muham/Downloads/medisync/medisync/backend/app/models.py)
- Update `User` model with `role` (`doctor`, `patient`, `admin`), `is_active`, `phone`.
- Add `DoctorProfile`:
  - `registration_number`, `medical_council`, `specialization`, `experience_years`, `languages` (JSON list), `clinic_name`, `aadhaar_masked`, `kyc_status` (`pending`, `verified`, `rejected`), `kyc_docs` (JSON), `verified_by`, `verification_notes`.
- Add `PatientProfile`:
  - `user_id`, `mrn`, `date_of_birth`, `gender`, `blood_group`, `preferred_language`, `emergency_contact`, `allergies` (JSON list), `medical_history`.
- Add `Consultation`:
  - `patient_id`, `doctor_id`, `scheduled_at`, `status` (`scheduled`, `active`, `completed`), `language`, `problem_description`, `diagnosis_cure`, `notes`.
- Add `Prescription`:
  - `consultation_id`, `patient_id`, `doctor_id`, `medications` (JSON array: name, dosage, frequency, duration, instructions), `lifestyle_cure_advice`, `follow_up_date`.
- Add `Notification`:
  - `user_id`, `title`, `message`, `category` (`kyc`, `appointment`, `video_call`, `prescription`, `system`), `is_read`, `created_at`.
- Add `AuditLog`:
  - `actor_id`, `action`, `target_type`, `target_id`, `details` (JSON), `timestamp`.

#### [MODIFY] [security.py](file:///c:/Users/muham/Downloads/medisync/medisync/backend/app/security.py)
- Use standard `bcrypt` directly to eliminate passlib's Python 3.13 bcrypt 4.x/5.x compatibility bug.

#### [MODIFY] [schemas.py](file:///c:/Users/muham/Downloads/medisync/medisync/backend/app/schemas.py)
- Add schemas for:
  - Doctor registration with UIDAI details and KYC fields.
  - Doctor profile update and KYC verification by Admin.
  - Consultation creation and completion (problem, cure).
  - Prescription creation with structured medication items (name, dose, frequency, duration, instructions).
  - Language matchmaking query and doctor match score result.
  - Notification list and mark-as-read.
  - Admin audit overview and verification actions.

#### [NEW] [doctors.py](file:///c:/Users/muham/Downloads/medisync/medisync/backend/app/routers/doctors.py)
- Endpoints for:
  - Doctor profile retrieval and update.
  - Doctor registration with UIDAI E-KYC.
  - Matchmaking endpoint: `GET /api/doctors/match?language=tamil&specialization=general`.
  - Doctor list for patients and admin.

#### [NEW] [consultations.py](file:///c:/Users/muham/Downloads/medisync/medisync/backend/app/routers/consultations.py)
- Endpoints for:
  - Booking / initiating consultation.
  - Updating patient problem description.
  - Providing clinical diagnosis, cure recommendations, and prescribing medications.
  - Retrieving consultation history and prescriptions for patient and doctor.

#### [NEW] [admin.py](file:///c:/Users/muham/Downloads/medisync/medisync/backend/app/routers/admin.py)
- Endpoints for:
  - Admin dashboard stats (patients, doctors, consultations, pending KYCs).
  - Listing pending doctor KYC submissions.
  - Approving / rejecting doctor KYC with audit logging.
  - System audit log inspection.

#### [NEW] [notifications.py](file:///c:/Users/muham/Downloads/medisync/medisync/backend/app/routers/notifications.py)
- Endpoints for:
  - Fetching user notifications.
  - Marking notifications as read.
  - Creating system alerts.

#### [MODIFY] [main.py](file:///c:/Users/muham/Downloads/medisync/medisync/backend/app/main.py)
- Register all new routers (`doctors`, `consultations`, `admin`, `notifications`).

#### [MODIFY] [seed_demo.py](file:///c:/Users/muham/Downloads/medisync/medisync/backend/seed_demo.py)
- Seed comprehensive test accounts:
  1. Admin: `admin@medisync.local` / `AdminPass123!`
  2. Verified Doctor (Hindi/Punjabi/English): `doctor@medisync.local` / `DoctorPass123!` (Dr. Rajesh Sharma)
  3. Verified Doctor (Tamil/Telugu/Malayalam/English): `doctor2@medisync.local` / `DoctorPass123!` (Dr. Priya Sundaram)
  4. Pending KYC Doctor (Gujarati/Marathi/Hindi): `doctor.pending@medisync.local` / `DoctorPass123!` (Dr. Amit Patel)
  5. Patient (Hindi/English): `patient@medisync.local` / `PatientPass123!` (Asha Verma)
  6. Patient (Tamil/Kannada): `patient2@medisync.local` / `PatientPass123!` (Kavitha Murugan)
- Pre-seed sample consultation, prescription, and notifications.

---

### Frontend Redesign & Feature Implementation

#### [MODIFY] [styles.css](file:///c:/Users/muham/Downloads/medisync/medisync/frontend/styles.css)
- **Light Theme**: Clean, bright medical palette with white/off-white background (`#f8fafc`), pure white cards (`#ffffff`), crisp borders (`#e2e8f0`), professional teal/indigo accents (`#0284c7`, `#0f766e`, `#2563eb`).
- **Accessible Typography**: High readability fonts (`Plus Jakarta Sans`, `Inter`, 15-16px body, 1.55 line height, dark slate `#0f172a` text, distinct weights for visual hierarchy).
- **Responsive Layouts**:
  - Auth screen with role tabs and 3 one-click demo login cards.
  - Top navigation bar with Language Selector (11 languages), Notification Bell with counter badge, User Profile & Role pill, Sign Out.
  - Dedicated views for Doctor Dashboard, Patient Portal, and Admin Operations Console.
  - Video Consultation modal with real camera stream, self-view PIP, mute/cam toggles, and live clinical note drawer.
  - Doctor Registration form with UIDAI E-KYC file upload.
  - Matchmaker results grid with language tags, match percentage, and instant video call button.
  - Prescription card with print / export layout.

#### [NEW] [i18n.js](file:///c:/Users/muham/Downloads/medisync/medisync/frontend/i18n.js)
- Comprehensive multi-lingual dictionary for:
  - English (main)
  - Hindi (हिन्दी)
  - Tamil (தமிழ்)
  - Telugu (తెలుగు)
  - Malayalam (മലയാളം)
  - Gujarati (ગુજરાતી)
  - Marathi (मराठी)
  - Punjabi (ਪੰਜਾਬੀ)
  - Kannada (ಕನ್ನಡ)
  - Assamese (অসমীয়া)
  - Bengali (বাংলা)
- Dynamic translation engine updating all text nodes and placeholders with `data-i18n` attributes.

#### [MODIFY] [index.html](file:///c:/Users/muham/Downloads/medisync/medisync/frontend/index.html)
- Modernized HTML markup:
  - Topbar with language picker (11 languages) and notification bell.
  - Enhanced Auth Screen with:
    - Quick Demo Login cards for Doctor, Patient, and Administrator.
    - Role selector for registration (Patient vs Doctor with UIDAI KYC upload).
  - Doctor Dashboard:
    - Patient queue, Consultation manager, Problem/Cure/Prescription composer, Video call launcher, KYC status indicator.
  - Patient Dashboard:
    - Language-based Doctor Matchmaker, My Prescriptions & Timeline, Join Video Call room.
  - Admin Dashboard:
    - Doctor KYC Verification review panel (preview docs, Approve/Reject).
    - Operations Monitor (Audit logs of consultations, appointments, and prescriptions).
  - Video Call Modal:
    - Real camera stream `<video id="local-video">`, remote peer feed `<video id="remote-video">`, camera/mic toggles, timer, full-screen, clinical note drawer.
  - Notification Center modal/drawer.

#### [MODIFY] [app.js](file:///c:/Users/muham/Downloads/medisync/medisync/frontend/app.js)
- Controller logic:
  - Quick-fill demo logins for Doctor, Patient, Admin.
  - Role-based routing and view rendering.
  - Doctor UIDAI E-KYC registration handling.
  - Admin verification actions (Approve/Reject).
  - WebRTC & `navigator.mediaDevices.getUserMedia` camera/mic access with graceful fallbacks.
  - Language-based doctor matchmaking with scoring.
  - Clinical encounter form: Doctor submits problem, cure, and structured medications -> Patient views and prints prescription.
  - Real-time notification updates and unread count badges.
  - Language switching hook with `i18n.js`.

---

## Verification Plan

### Automated Verification
- Run backend database creation & migration:
  `C:\Users\muham\anaconda3\python.exe backend/seed_demo.py`
- Test API endpoints with python test script:
  - Auth test for Doctor, Patient, and Admin accounts.
  - Doctor KYC registration and Admin verification flow.
  - Language matchmaking query across Tamil, Hindi, etc.
  - Consultation creation with Problem, Cure, and Medication items.
  - Notification retrieval.
- Start backend server:
  `C:\Users\muham\anaconda3\python.exe -m uvicorn app.main:app --port 8000`
- Start frontend server:
  `C:\Users\muham\anaconda3\python.exe -m http.server 5500 --directory frontend`

### Manual Verification
1. **Light Theme & Typography**: Verify clean, readable typography with no dark theme artifacts.
2. **One-click Demo Logins**: Test Doctor, Patient, and Admin quick logins.
3. **11 Languages (i18n)**: Switch between English, Hindi, Tamil, Telugu, Malayalam, Gujarati, Marathi, Punjabi, Kannada, Assamese, Bengali and verify UI updates immediately.
4. **Doctor Registration & UIDAI KYC**: Register a new doctor with Aadhaar and certificate upload, log in as Admin, inspect credentials, and verify/approve.
5. **Language Matchmaking**: As a patient, select Tamil or Hindi, find matching verified doctors, and click "Start Video Consultation".
6. **Camera Access & Video Call**: Launch video call, verify browser requests camera/mic access, verify video feeds display properly, test mute/cam off toggles.
7. **Problem, Cure & Medications**: Doctor writes diagnosis & prescribes medicine with dosage/frequency -> Patient sees structured prescription immediately.
8. **Notification Center**: Check notifications bell and badge update across roles.
