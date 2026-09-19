import io
import json
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def run_tests():
    print("Testing new enhancement features...")

    # 1. Login doctor
    login_resp = client.post("/api/auth/login", data={"username": "doctor@medisync.local", "password": "DoctorPass123!"})
    assert login_resp.status_code == 200, login_resp.text
    doc_token = login_resp.json()["access_token"]
    doc_headers = {"Authorization": f"Bearer {doc_token}"}
    print("[PASS] Doctor login OK")

    # 2. Login patient
    login_pat = client.post("/api/auth/login", data={"username": "patient@medisync.local", "password": "PatientPass123!"})
    assert login_pat.status_code == 200, login_pat.text
    pat_token = login_pat.json()["access_token"]
    pat_headers = {"Authorization": f"Bearer {pat_token}"}
    pat_id = login_pat.json()["user"]["id"]
    print("[PASS] Patient login OK")

    # 3. Doctor updates availability schedule
    avail_resp = client.put(
        "/api/doctors/me/availability",
        headers=doc_headers,
        json={"availability_days": ["Monday", "Wednesday", "Friday"], "availability_time": "10:00 AM - 04:00 PM"}
    )
    assert avail_resp.status_code == 200, avail_resp.text
    assert avail_resp.json()["availability_time"] == "10:00 AM - 04:00 PM"
    assert "Monday" in avail_resp.json()["availability_days"]
    print("[PASS] Doctor availability update OK")

    # 4. Patient matchmaking returns doctor availability
    match_resp = client.get("/api/doctors/match?language=Hindi", headers=pat_headers)
    assert match_resp.status_code == 200, match_resp.text
    matches = match_resp.json()
    assert len(matches) > 0
    top_doc = matches[0]
    assert "availability_time" in top_doc
    assert "availability_days" in top_doc
    print(f"[PASS] Matchmaking with availability info OK: {top_doc['availability_time']}")

    # 5. Doctor adds new patient in standard format
    import uuid
    test_mrn = f"MRN-{uuid.uuid4().hex[:6].upper()}"
    new_patient_payload = {
        "mrn": test_mrn,
        "full_name": "Ramesh Gupta",
        "date_of_birth": "1985-04-12",
        "gender": "Male",
        "known_allergies": ["Penicillin", "Dust"],
        "notes": "History of hypertension and seasonal asthma."
    }
    create_pat_resp = client.post("/api/patients", headers=doc_headers, json=new_patient_payload)
    assert create_pat_resp.status_code == 201, create_pat_resp.text
    assert create_pat_resp.json()["full_name"] == "Ramesh Gupta"
    assert create_pat_resp.json()["mrn"] == test_mrn
    print(f"[PASS] Doctor successfully added new patient in standard format OK ({test_mrn})")

    # 6. Create consultation session
    consult_payload = {
        "patient_id": pat_id,
        "doctor_id": login_resp.json()["user"]["id"],
        "language_used": "Hindi",
        "problem_description": "Chest congestion and severe cough"
    }
    consult_resp = client.post("/api/consultations", headers=pat_headers, json=consult_payload)
    assert consult_resp.status_code == 201, consult_resp.text
    consult_id = consult_resp.json()["id"]
    print(f"[PASS] Consultation session created: {consult_id}")

    # 7. Doctor requests scan / lab reports
    req_docs_resp = client.post(
        f"/api/consultations/{consult_id}/request-docs",
        headers=doc_headers,
        json={"note": "Please upload Chest X-Ray and CBC blood test report."}
    )
    assert req_docs_resp.status_code == 200, req_docs_resp.text
    assert req_docs_resp.json()["documents_required"] is True
    assert req_docs_resp.json()["documents_verified"] is False
    print("[PASS] Doctor requested scan/lab reports OK")

    # 8. Doctor attempts to prescribe before documents are verified -> MUST FAIL WITH 400!
    rx_payload = {
        "consultation_id": consult_id,
        "patient_id": pat_id,
        "problem_description": "Severe bronchitis",
        "diagnosis_cure": "Rest, hydration, inhaler and antibiotics.",
        "medications": [
            {"name": "Azithromycin 500mg", "dosage": "1 Tab", "frequency": "1-0-0 (Morning)", "duration": "3 days", "instructions": "After food"}
        ]
    }
    premature_rx = client.post("/api/consultations/prescribe", headers=doc_headers, json=rx_payload)
    assert premature_rx.status_code == 400, "Should have blocked prescription when documents are unverified!"
    print(f"[PASS] Prescription correctly blocked before document verification: {premature_rx.json()['detail']}")

    # 9. Patient uploads scan / lab report
    fake_file = io.BytesIO(b"Fake chest x-ray lab report content")
    upload_resp = client.post(
        f"/api/consultations/{consult_id}/upload-docs",
        headers=pat_headers,
        data={"doc_type": "scan"},
        files={"file": ("chest_xray_scan.pdf", fake_file, "application/pdf")}
    )
    assert upload_resp.status_code == 200, upload_resp.text
    assert len(upload_resp.json()["uploaded_documents"]) == 1
    assert upload_resp.json()["uploaded_documents"][0]["name"] == "chest_xray_scan.pdf"
    print("[PASS] Patient uploaded scan/lab report OK")

    # 10. Doctor verifies the document
    verify_resp = client.post(
        f"/api/consultations/{consult_id}/verify-docs",
        headers=doc_headers,
        json={"verified": True, "notes": "X-Ray clear, mild bronchial thickening."}
    )
    assert verify_resp.status_code == 200, verify_resp.text
    assert verify_resp.json()["documents_verified"] is True
    print("[PASS] Doctor verified patient diagnostic documents OK")

    # 11. Now doctor prescribes -> MUST SUCCEED!
    rx_success = client.post("/api/consultations/prescribe", headers=doc_headers, json=rx_payload)
    assert rx_success.status_code == 200, rx_success.text
    assert rx_success.json()["status"] == "completed"
    assert rx_success.json()["prescription"] is not None
    print("[PASS] Prescription successfully issued after document verification OK!")

    print("\nALL 11 ENHANCEMENT TESTS PASSED 100%!")

if __name__ == "__main__":
    run_tests()
