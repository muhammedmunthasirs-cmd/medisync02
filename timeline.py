from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user
from ..services.conflicts import recompute_conflicts

router = APIRouter(prefix="/api/patients/{patient_id}", tags=["timeline"])


def _get_patient_or_404(db: Session, patient_id: str) -> models.Patient:
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


DOC_TYPE_LABELS = {
    "prescription": "Prescription",
    "lab_report": "Lab Report",
    "consultation_note": "Consultation Note",
    "scan": "Imaging / Scan",
    "discharge_summary": "Discharge Summary",
    "other": "Document",
}


def _summarize(doc: models.Document) -> str:
    sd = doc.structured_data or {}
    parts = []
    if sd.get("diagnoses"):
        parts.append("Dx: " + "; ".join(sd["diagnoses"][:3]))
    if sd.get("medications"):
        meds = ", ".join(
            f"{m['name']}" + (f" {m['dosage']}" if m.get("dosage") else "") for m in sd["medications"][:4]
        )
        parts.append("Meds: " + meds)
    if sd.get("lab_values"):
        labs = ", ".join(f"{l['test']}={l['value']}{l.get('unit') or ''}" for l in sd["lab_values"][:4])
        parts.append("Labs: " + labs)
    if sd.get("allergies"):
        parts.append("Allergies noted: " + ", ".join(sd["allergies"][:5]))
    if not parts:
        if doc.extraction_status == "failed":
            return "Text extraction did not find structured data; open the document to review manually."
        return "No structured fields detected automatically; open the document to review."
    return " | ".join(parts)


@router.get("/timeline", response_model=list[schemas.TimelineEvent])
def get_timeline(
    patient_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    patient = _get_patient_or_404(db, patient_id)
    docs = (
        db.query(models.Document)
        .filter(models.Document.patient_id == patient.id)
        .all()
    )

    events = []
    for doc in docs:
        events.append(
            schemas.TimelineEvent(
                date=doc.document_date,
                date_is_estimated=(doc.date_source == "extracted"),
                document_id=doc.id,
                doc_type=doc.doc_type,
                title=f"{DOC_TYPE_LABELS.get(doc.doc_type, 'Document')} — {doc.original_filename}",
                summary=_summarize(doc),
                structured_data=doc.structured_data or {},
            )
        )

    # Chronological order; undated documents sort to the end, most-recent-known first
    dated = sorted([e for e in events if e.date], key=lambda e: e.date, reverse=True)
    undated = [e for e in events if not e.date]
    return dated + undated


@router.get("/conflicts", response_model=list[schemas.ConflictOut])
def get_conflicts(
    patient_id: str,
    include_resolved: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    patient = _get_patient_or_404(db, patient_id)
    q = db.query(models.ConflictFlag).filter(models.ConflictFlag.patient_id == patient.id)
    if not include_resolved:
        q = q.filter(models.ConflictFlag.resolved == False)  # noqa: E712
    severity_order = {"high": 0, "medium": 1, "low": 2}
    flags = q.all()
    flags.sort(key=lambda f: severity_order.get(f.severity, 3))
    return flags


@router.post("/conflicts/recompute", response_model=list[schemas.ConflictOut])
def recompute(
    patient_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    patient = _get_patient_or_404(db, patient_id)
    flags = recompute_conflicts(db, patient)
    db.commit()
    severity_order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: severity_order.get(f.severity, 3))
    return flags


@router.post("/conflicts/{conflict_id}/resolve", response_model=schemas.ConflictOut)
def resolve_conflict(
    patient_id: str,
    conflict_id: str,
    payload: schemas.ConflictResolve,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _get_patient_or_404(db, patient_id)
    flag = (
        db.query(models.ConflictFlag)
        .filter(models.ConflictFlag.id == conflict_id, models.ConflictFlag.patient_id == patient_id)
        .first()
    )
    if not flag:
        raise HTTPException(status_code=404, detail="Conflict flag not found")
    flag.resolved = True
    flag.resolved_note = payload.resolved_note
    db.commit()
    db.refresh(flag)
    return flag
