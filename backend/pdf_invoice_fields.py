"""Conservative, invoice-only arithmetic observations over bounded page lines."""

from __future__ import annotations

import re
from decimal import Decimal

AMOUNT = r"(?:USD\s*)?\$?\s*(\d{1,3}(?:,\d{3})*|\d{1,9})\.(\d{2})"
LABELS = {
    "subtotal": re.compile(rf"^\s*sub\s*total\s*[:\-]?\s*{AMOUNT}\s*$", re.I),
    "tax": re.compile(rf"^\s*(?:sales\s+)?tax\s*[:\-]?\s*{AMOUNT}\s*$", re.I),
    "total": re.compile(rf"^\s*(?:grand\s+total|total)\s*[:\-]?\s*{AMOUNT}\s*$", re.I),
}
INVOICE_MARKER = re.compile(r"\binvoice\b", re.I)
OTHER_ADJUSTMENT = re.compile(
    r"\b(?:shipping|delivery|discount|handling|service\s+charge|surcharge|"
    r"fee|tip|credit|payment|paid|deposit|balance|rounding)\b", re.I
)
ANY_AMOUNT = re.compile(AMOUNT, re.I)


def ocr_lines(page: dict) -> list[dict]:
    """Rebuild short reading lines from OCR word boxes; retain a union box."""
    rows: list[list[dict]] = []
    for word in sorted(page.get("words", []), key=lambda item: (
            (item["bbox_px"][1] + item["bbox_px"][3]) / 2, item["bbox_px"][0])):
        box = word["bbox_px"]
        center = (box[1] + box[3]) / 2
        tolerance = max(8, (box[3] - box[1]) / 2)
        for row in rows:
            first = row[0]["bbox_px"]
            if abs(center - (first[1] + first[3]) / 2) <= tolerance:
                row.append(word)
                break
        else:
            rows.append([word])
    lines = []
    for index, row in enumerate(rows, 1):
        row.sort(key=lambda word: word["bbox_px"][0])
        boxes = [word["bbox_px"] for word in row]
        raw = " ".join(word["text"] for word in row)
        lines.append({
            "text": raw[:160], "text_capped": len(raw) > 160,
            "citation": {"page": page["page"], "source": "ocr", "line": index,
                         "bbox_px": [min(box[0] for box in boxes), min(box[1] for box in boxes),
                                     max(box[2] for box in boxes), max(box[3] for box in boxes)]},
            "low_ocr_confidence": any(word["confidence"] < 0.8 or word["text_capped"]
                                      for word in row),
        })
    return lines


def extract_invoice_fields(lines: list[dict], complete_coverage: bool) -> dict:
    """Return cited amounts and a rule result, abstaining on ambiguous extraction."""
    if not any(INVOICE_MARKER.search(line["text"]) for line in lines):
        return {"state": "unsupported_document_type", "fields": {},
                "check": "not_run", "reason": "invoice_marker_missing"}
    candidates: dict[str, list[dict]] = {field: [] for field in LABELS}
    other_adjustments = []
    for line in lines:
        if OTHER_ADJUSTMENT.search(line["text"]) and ANY_AMOUNT.search(line["text"]):
            other_adjustments.append(line["citation"])
        for field, pattern in LABELS.items():
            match = pattern.fullmatch(line["text"])
            if match:
                value = f"{match.group(1).replace(',', '')}.{match.group(2)}"
                candidates[field].append({
                    "value": value, "citation": line["citation"],
                    "low_ocr_confidence": line.get("low_ocr_confidence", False),
                })
    if not complete_coverage:
        return {"state": "incomplete_coverage", "fields": candidates,
                "check": "not_run", "reason": "unread_or_truncated_page"}
    if any(len(items) > 1 for items in candidates.values()):
        return {"state": "ambiguous_fields", "fields": candidates,
                "check": "not_run", "reason": "repeated_amount_label"}
    if any(not items for items in candidates.values()):
        return {"state": "missing_fields", "fields": candidates,
                "check": "not_run", "reason": "subtotal_tax_total_required"}
    if other_adjustments:
        return {"state": "unsupported_adjustments", "fields": candidates,
                "check": "not_run", "reason": "additional_amount_lines",
                "additional_amount_citations": other_adjustments[:10]}
    if any(items[0]["low_ocr_confidence"] for items in candidates.values()):
        return {"state": "low_ocr_confidence", "fields": candidates,
                "check": "not_run", "reason": "amount_line_below_ocr_threshold"}
    subtotal = Decimal(candidates["subtotal"][0]["value"])
    tax = Decimal(candidates["tax"][0]["value"])
    total = Decimal(candidates["total"][0]["value"])
    difference = total - subtotal - tax
    return {
        "state": "checked", "fields": candidates,
        "check": "match" if difference == 0 else "mismatch",
        "rule": "subtotal_plus_tax_equals_total_exact_cents",
        "difference": f"{difference:.2f}",
    }
