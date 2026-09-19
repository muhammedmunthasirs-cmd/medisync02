"""
Rule-based conflict & missing-information detection.

Runs across ALL of a patient's documents whenever a document is added,
edited, or removed. Replaces (not appends to) the set of *unresolved,
auto-generated* flags each time, so it never accumulates duplicates or goes
stale. Manually resolved flags are preserved via a resolved-signature set,
carried over if the same underlying issue reappears.

This is deliberately conservative and explainable (no black-box scoring) -
every flag says exactly which documents and which fields triggered it, so a
clinician can verify in a few seconds rather than trust a number.
"""
from sqlalchemy.orm import Session

from .. import models


def _norm(s: str) -> str:
    return s.strip().lower()


def recompute_conflicts(db: Session, patient: models.Patient) -> list[models.ConflictFlag]:
    documents = (
        db.query(models.Document)
        .filter(models.Document.patient_id == patient.id)
        .all()
    )

    # Preserve resolutions: build a signature -> (resolved, note) map from existing flags
    existing = db.query(models.ConflictFlag).filter(models.ConflictFlag.patient_id == patient.id).all()
    resolution_by_signature = {
        (f.kind, f.description): (f.resolved, f.resolved_note) for f in existing
    }
    for f in existing:
        db.delete(f)

    new_flags: list[models.ConflictFlag] = []

    def add_flag(kind: str, severity: str, description: str, related_ids: list[str]):
        sig = (kind, description)
        resolved, note = resolution_by_signature.get(sig, (False, None))
        flag = models.ConflictFlag(
            patient_id=patient.id,
            kind=kind,
            severity=severity,
            description=description,
            related_document_ids=related_ids,
            resolved=resolved,
            resolved_note=note,
        )
        db.add(flag)
        new_flags.append(flag)

    # --- 1. Missing document date -> can't be placed reliably on the timeline ---
    for doc in documents:
        if not doc.document_date:
            add_flag(
                "missing_info",
                "low",
                f"'{doc.original_filename}' ({doc.doc_type.replace('_', ' ')}) has no identifiable date; "
                f"it will not appear in the correct place on the timeline until a date is confirmed.",
                [doc.id],
            )

    # --- 2. Allergy vs. prescribed medication conflicts ---
    declared_allergies = {_norm(a) for a in (patient.known_allergies or [])}
    extracted_allergy_docs: dict[str, list[str]] = {}  # allergy(norm) -> [doc_id]
    for doc in documents:
        for a in (doc.structured_data or {}).get("allergies", []):
            extracted_allergy_docs.setdefault(_norm(a), []).append(doc.id)

    all_known_allergies = dict.fromkeys(declared_allergies)  # allergy -> None, just a set-like
    all_known_allergies_sources = {a: ["patient_record"] for a in declared_allergies}
    for a, doc_ids in extracted_allergy_docs.items():
        all_known_allergies_sources.setdefault(a, []).extend(doc_ids)

    for doc in documents:
        if doc.doc_type != "prescription":
            continue
        for med in (doc.structured_data or {}).get("medications", []):
            med_name_norm = _norm(med.get("name", ""))
            if not med_name_norm:
                continue
            for allergy in all_known_allergies_sources:
                if allergy and (allergy in med_name_norm or med_name_norm in allergy):
                    sources = all_known_allergies_sources[allergy]
                    related = list({doc.id, *[s for s in sources if s != "patient_record"]})
                    add_flag(
                        "allergy_conflict",
                        "high",
                        f"'{doc.original_filename}' prescribes {med.get('name')}, which appears to match "
                        f"a documented allergy to '{allergy}'. Verify before this medication is administered.",
                        related,
                    )

    # --- 3. Conflicting dosages for the same medication across prescriptions ---
    med_dosage_map: dict[str, dict[str, list[str]]] = {}  # med_name -> dosage -> [doc_ids]
    for doc in documents:
        if doc.doc_type != "prescription":
            continue
        for med in (doc.structured_data or {}).get("medications", []):
            name = _norm(med.get("name", ""))
            dosage = (med.get("dosage") or "unspecified").strip().lower()
            if not name:
                continue
            med_dosage_map.setdefault(name, {}).setdefault(dosage, []).append(doc.id)

    for name, dosage_map in med_dosage_map.items():
        distinct_dosages = [d for d in dosage_map if d != "unspecified"]
        if len(distinct_dosages) > 1:
            related = sorted({doc_id for d in distinct_dosages for doc_id in dosage_map[d]})
            dosage_list = ", ".join(sorted(distinct_dosages))
            add_flag(
                "dosage_conflict",
                "medium",
                f"Multiple different dosages found across prescriptions for '{name}': {dosage_list}. "
                f"Confirm which is the current active dose.",
                related,
            )

    # --- 4. Patient has prescriptions but no declared allergy status on file ---
    has_prescription = any(d.doc_type == "prescription" for d in documents)
    if has_prescription and not patient.known_allergies:
        add_flag(
            "missing_info",
            "medium",
            "Patient has prescriptions on file but no allergy status has been declared on the patient "
            "record. Confirm and record known allergies (or 'no known allergies').",
            [],
        )

    db.flush()
    return new_flags
