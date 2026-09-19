import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import UPLOAD_DIR, MAX_UPLOAD_BYTES, ALLOWED_DOC_TYPES, ALLOWED_UPLOAD_EXTENSIONS
from ..database import get_db
from ..deps import get_current_user
from ..services.extraction import extract_text_from_file, extract_fields, best_guess_document_date
from ..services.conflicts import recompute_conflicts

router = APIRouter(prefix="/api/patients/{patient_id}/documents", tags=["documents"])


def _get_patient_or_404(db: Session, patient_id: str) -> models.Patient:
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.get("", response_model=list[schemas.DocumentOut])
def list_documents(
    patient_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _get_patient_or_404(db, patient_id)
    docs = (
        db.query(models.Document)
        .filter(models.Document.patient_id == patient_id)
        .order_by(models.Document.uploaded_at.desc())
        .all()
    )
    return docs


@router.post("", response_model=schemas.DocumentDetailOut, status_code=201)
async def upload_document(
    patient_id: str,
    doc_type: str = Form(...),
    document_date: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    patient = _get_patient_or_404(db, patient_id)

    if doc_type not in ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"doc_type must be one of {ALLOWED_DOC_TYPES}")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_UPLOAD_EXTENSIONS)}",
        )

    patient_dir = os.path.join(UPLOAD_DIR, patient_id)
    os.makedirs(patient_dir, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(patient_dir, stored_name)

    size = 0
    with open(dest_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                os.remove(dest_path)
                raise HTTPException(status_code=413, detail="File exceeds the 20MB upload limit.")
            out.write(chunk)

    document = models.Document(
        patient_id=patient_id,
        doc_type=doc_type,
        original_filename=file.filename or stored_name,
        storage_path=dest_path,
        uploaded_by=current_user.id,
    )

    # --- Run the extraction pipeline synchronously (fine for MVP scale; move to a
    # background task/queue such as Celery or FastAPI BackgroundTasks for production
    # volumes of large scanned documents). ---
    try:
        raw_text, note = extract_text_from_file(dest_path, file.content_type or "")
        fields = extract_fields(raw_text, doc_type)
        guessed_date, date_source = best_guess_document_date(fields["dates_found"], document_date)

        document.raw_text = raw_text
        document.structured_data = fields
        document.document_date = guessed_date
        document.date_source = date_source
        document.extraction_status = "ok" if raw_text else "failed"
        document.extraction_notes = note
    except Exception as e:  # noqa: BLE001
        document.extraction_status = "failed"
        document.extraction_notes = f"Unexpected extraction error: {e}"
        document.document_date = document_date
        document.date_source = "provided" if document_date else "unknown"

    db.add(document)
    db.commit()
    db.refresh(document)

    recompute_conflicts(db, patient)
    db.commit()

    return document


@router.get("/{document_id}", response_model=schemas.DocumentDetailOut)
def get_document(
    patient_id: str,
    document_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _get_patient_or_404(db, patient_id)
    doc = (
        db.query(models.Document)
        .filter(models.Document.id == document_id, models.Document.patient_id == patient_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{document_id}", status_code=204)
def delete_document(
    patient_id: str,
    document_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    patient = _get_patient_or_404(db, patient_id)
    doc = (
        db.query(models.Document)
        .filter(models.Document.id == document_id, models.Document.patient_id == patient_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if os.path.exists(doc.storage_path):
        try:
            os.remove(doc.storage_path)
        except OSError:
            pass

    db.delete(doc)
    db.commit()

    recompute_conflicts(db, patient)
    db.commit()
    return None
