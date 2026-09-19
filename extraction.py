"""
Document intelligence layer.

This module turns a raw uploaded file (PDF / image / text) into:
  1. Plain text (via PDF text extraction, falling back to OCR for images/scans)
  2. Structured clinical fields (dates, medications, diagnoses, allergies, lab values)

The field extraction here is intentionally a transparent, rule-based
(regex + keyword) pipeline so the whole system is inspectable and runs with
no external API calls. It is written behind a single `extract_fields()`
entry point so it can be swapped for a real medical NLP model or an LLM
call (e.g. the Anthropic API) without touching any other layer of the app -
routers and the conflict/timeline services only depend on the
`structured_data` dict shape documented below, not on how it was produced.

structured_data shape:
{
    "medications": [{"name": str, "dosage": str|None, "frequency": str|None}],
    "diagnoses": [str],
    "allergies": [str],
    "lab_values": [{"test": str, "value": str, "unit": str|None}],
    "dates_found": [str]  # ISO strings, all date-like mentions in the doc
}
"""
import datetime
import os
import re
from typing import Optional

from dateutil import parser as dateparser

# --- Optional heavy deps: degrade gracefully if not installed / no OCR binary ---
try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None

try:
    import pytesseract
    from PIL import Image
except ImportError:  # pragma: no cover
    pytesseract = None
    Image = None


DATE_PATTERN = re.compile(
    r"""
    (?P<d1>\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}\b)          # 12/05/2024, 12-05-24
    |(?P<d2>\b\d{4}-\d{2}-\d{2}\b)                          # 2024-05-12
    |(?P<d3>\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b)
    |(?P<d4>\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b)
    """,
    re.IGNORECASE | re.VERBOSE,
)

MEDICATION_LINE = re.compile(
    r"(?P<name>[A-Z][A-Za-z0-9\-]{2,30})\s+"
    r"(?P<dosage>\d+(?:\.\d+)?\s?(?:mg|mcg|g|ml|IU|units))"
    r"(?:\s*[-,]?\s*(?P<frequency>(?:once|twice|thrice|\d+\s*x)?\s*(?:daily|a day|per day|"
    r"every\s+\d+\s*h(?:ours)?|BID|TID|QID|OD|HS|PRN)))?",
    re.IGNORECASE,
)

LAB_LINE = re.compile(
    r"(?P<test>[A-Za-z][A-Za-z0-9 /\-]{2,40}?)\s*[:\-]\s*"
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>[A-Za-z/%µu]{0,10})?"
)

SECTION_KEYWORDS = {
    "allergies": ["allergies", "allergic to", "known allergy", "known allergies"],
    "diagnoses": ["diagnosis", "diagnoses", "impression", "assessment"],
    "medications": ["medications", "prescription", "prescribed", "rx", "meds"],
}


def extract_text_from_file(file_path: str, content_type: str) -> tuple[str, str]:
    """Returns (raw_text, status_note)."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".txt":
        with open(file_path, "r", errors="ignore") as f:
            return f.read(), "read as plain text"

    if ext == ".pdf":
        if pdfplumber is None:
            return "", "pdfplumber not installed; cannot extract PDF text"
        text_parts = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    text_parts.append(page_text)
            text = "\n".join(text_parts).strip()
            if text:
                return text, "extracted via pdfplumber text layer"
            # Fall through to OCR if the PDF had no text layer (scanned doc)
        except Exception as e:  # noqa: BLE001
            return "", f"pdfplumber failed: {e}"

    if ext in {".png", ".jpg", ".jpeg", ".tiff"} or (ext == ".pdf"):
        if pytesseract is None or Image is None:
            return "", "OCR unavailable (pytesseract/Pillow not installed, or no tesseract binary on host)"
        try:
            img = Image.open(file_path)
            text = pytesseract.image_to_string(img)
            return text.strip(), "extracted via OCR (pytesseract)"
        except Exception as e:  # noqa: BLE001
            return "", f"OCR failed: {e}. If this is a fresh install, ensure the 'tesseract-ocr' system package is present."

    return "", f"unsupported file extension '{ext}'"


def _normalize_date(raw: str) -> Optional[str]:
    try:
        dt = dateparser.parse(raw, fuzzy=True, dayfirst=False)
        if dt and 1900 <= dt.year <= datetime.date.today().year + 1:
            return dt.date().isoformat()
    except Exception:  # noqa: BLE001
        pass
    return None


def _find_dates(text: str) -> list[str]:
    found = []
    for m in DATE_PATTERN.finditer(text):
        raw = next(g for g in m.groups() if g)
        norm = _normalize_date(raw)
        if norm and norm not in found:
            found.append(norm)
    return found


def _find_section_lines(text: str, keywords: list[str]) -> list[str]:
    """Grab the line(s) following a section header keyword, e.g. 'Allergies: Penicillin'."""
    lines = text.splitlines()
    hits = []
    for i, line in enumerate(lines):
        low = line.lower()
        for kw in keywords:
            if kw in low:
                # same-line content after the keyword/colon
                after = re.split(r"[:\-]", line, maxsplit=1)
                if len(after) > 1 and after[1].strip():
                    hits.append(after[1].strip())
                # also grab the next non-empty line, common in scanned forms
                elif i + 1 < len(lines) and lines[i + 1].strip():
                    hits.append(lines[i + 1].strip())
    return hits


def extract_fields(text: str, doc_type: str) -> dict:
    if not text:
        return {"medications": [], "diagnoses": [], "allergies": [], "lab_values": [], "dates_found": []}

    medications = []
    for m in MEDICATION_LINE.finditer(text):
        medications.append(
            {
                "name": m.group("name").strip(),
                "dosage": (m.group("dosage") or "").strip() or None,
                "frequency": (m.group("frequency") or "").strip() or None,
            }
        )

    allergy_lines = _find_section_lines(text, SECTION_KEYWORDS["allergies"])
    allergies = []
    for line in allergy_lines:
        parts = re.split(r",|;|\band\b", line, flags=re.IGNORECASE)
        allergies.extend([p.strip().rstrip(".") for p in parts if p.strip() and p.strip().lower() not in ("none", "nka", "n/a")])

    diagnosis_lines = _find_section_lines(text, SECTION_KEYWORDS["diagnoses"])
    diagnoses = [d.strip().rstrip(".") for d in diagnosis_lines if d.strip()]

    lab_values = []
    if doc_type == "lab_report":
        for m in LAB_LINE.finditer(text):
            test = m.group("test").strip()
            if len(test) < 3 or test.lower() in ("date", "time", "page"):
                continue
            lab_values.append(
                {"test": test, "value": m.group("value"), "unit": (m.group("unit") or "").strip() or None}
            )

    dates_found = _find_dates(text)

    return {
        "medications": medications,
        "diagnoses": diagnoses,
        "allergies": sorted(set(allergies), key=str.lower),
        "lab_values": lab_values[:40],
        "dates_found": dates_found,
    }


def best_guess_document_date(dates_found: list[str], provided_date: Optional[str]) -> tuple[Optional[str], str]:
    if provided_date:
        return provided_date, "provided"
    if dates_found:
        # Heuristic: earliest mentioned date is usually the document/event date
        # (later dates are often follow-up or expiry dates). This is a simple
        # heuristic and can be revisited with real-world documents.
        return sorted(dates_found)[0], "extracted"
    return None, "unknown"
