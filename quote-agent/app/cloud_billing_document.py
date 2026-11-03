"""Document adapters for Cloud Billing Quote inputs.

Adapters only expose source text and stable references. They intentionally do
not classify cloud products or map them to Huawei Cloud.
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any

from pypdf import PdfReader


MAX_PDF_PAGES = 100
MAX_PDF_TEXT_CHARS = 500_000


def _extract_declared_monthly_total(text: str) -> float | None:
    """Extract an estimate-level monthly total when the document declares one."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        lowered = line.lower()
        if "monthly cost" not in lowered and "monthly total" not in lowered:
            continue
        for candidate in lines[index + 1 : index + 5]:
            amounts = re.findall(r"(?<!\d)(\d[\d,]*\.\d{2})\s*(?:USD|US\$|\$)", candidate, re.I)
            if amounts:
                # Estimate summaries generally place upfront, monthly, annual in
                # that order. Prefer the second value when all three are present.
                selected = amounts[1] if len(amounts) >= 2 else amounts[0]
                return float(selected.replace(",", ""))
    return None


def parse_cloud_billing_pdf(content: bytes, filename: str) -> dict[str, Any]:
    """Extract a text PDF into complete pages and stable line-level references."""
    if not content.startswith(b"%PDF"):
        raise ValueError("The uploaded .pdf file does not have a valid PDF signature.")

    try:
        reader = PdfReader(BytesIO(content))
    except Exception as exc:
        raise ValueError(f"The uploaded PDF could not be opened: {exc}") from exc

    if reader.is_encrypted:
        raise ValueError("Encrypted PDF files are not supported.")
    if not reader.pages:
        raise ValueError("The uploaded PDF has no pages.")
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ValueError(f"PDF files are limited to {MAX_PDF_PAGES} pages.")

    pages: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    total_chars = 0
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text(extraction_mode="layout") or ""
        except TypeError:
            text = page.extract_text() or ""
        text = text.replace("\x00", "").strip("\n")
        total_chars += len(text)
        if total_chars > MAX_PDF_TEXT_CHARS:
            raise ValueError(
                f"Extracted PDF text exceeds the {MAX_PDF_TEXT_CHARS:,}-character limit."
            )

        page_lines: list[dict[str, Any]] = []
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line_text = raw_line.rstrip()
            if not line_text.strip():
                continue
            source_ref = f"pdf-line::{page_number}::{line_number}"
            entry = {
                "source_ref": source_ref,
                "page_number": page_number,
                "line_number": line_number,
                "text": line_text,
                "_line_number": line_number,
            }
            page_lines.append(entry)
            rows.append(entry)
        pages.append({"page_number": page_number, "text": text, "lines": page_lines})

    full_text = "\n\f\n".join(page["text"] for page in pages)
    if len(full_text.strip()) < 80:
        raise ValueError(
            "No usable text was extracted from the PDF. Scanned/image-only PDFs "
            "require OCR and are not supported yet."
        )

    return {
        "filename": filename,
        "sheet": "PDF",
        "document_type": "cloud_billing_pdf",
        "columns": ["source_ref", "page_number", "line_number", "text"],
        "rows": rows,
        "pages": pages,
        "full_text": full_text,
        "declared_monthly_total": _extract_declared_monthly_total(full_text),
        "page_count": len(pages),
    }
