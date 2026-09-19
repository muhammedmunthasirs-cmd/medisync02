import sqlite3
import json

conn = sqlite3.connect("backend/medisync.db")
c = conn.cursor()

doc_cols = [row[1] for row in c.execute("PRAGMA table_info(doctor_profiles)").fetchall()]
if "availability_days" not in doc_cols:
    c.execute("ALTER TABLE doctor_profiles ADD COLUMN availability_days JSON")
    default_days = json.dumps(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
    c.execute("UPDATE doctor_profiles SET availability_days = ?", (default_days,))
    print("Added availability_days column to doctor_profiles")

if "availability_time" not in doc_cols:
    c.execute("ALTER TABLE doctor_profiles ADD COLUMN availability_time TEXT")
    c.execute("UPDATE doctor_profiles SET availability_time = '09:00 AM - 05:00 PM'")
    print("Added availability_time column to doctor_profiles")

cons_cols = [row[1] for row in c.execute("PRAGMA table_info(consultations)").fetchall()]
if "documents_required" not in cons_cols:
    c.execute("ALTER TABLE consultations ADD COLUMN documents_required BOOLEAN DEFAULT 0")
    print("Added documents_required to consultations")

if "documents_verified" not in cons_cols:
    c.execute("ALTER TABLE consultations ADD COLUMN documents_verified BOOLEAN DEFAULT 0")
    print("Added documents_verified to consultations")

if "documents_request_note" not in cons_cols:
    c.execute("ALTER TABLE consultations ADD COLUMN documents_request_note TEXT")
    print("Added documents_request_note to consultations")

if "uploaded_documents" not in cons_cols:
    c.execute("ALTER TABLE consultations ADD COLUMN uploaded_documents JSON")
    c.execute("UPDATE consultations SET uploaded_documents = '[]'")
    print("Added uploaded_documents to consultations")

conn.commit()
conn.close()
print("Database schema migration complete!")
