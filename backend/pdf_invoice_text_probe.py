"""Bounded text-layer lines for the invoice field task, in a credential-free child."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.pdf_probe import (
    MAX_CONTENT_BYTES_PER_PAGE, MAX_PAGES, PYPDF_VERSION, _set_limits,
)

MAX_FIELD_PAGES = 4
MAX_LINES_PER_PAGE = 100
MAX_LINE_CHARS = 160
MAX_TEXT_CHARS_PER_PAGE = 8_000
MAX_PDF_BYTES = 20 * 1024 * 1024


def probe(path: Path, pages: list[int]) -> dict:
    import pypdf

    if pypdf.__version__ != PYPDF_VERSION:
        raise RuntimeError("PDF parser version differs from the pinned version")
    if path.stat().st_size > MAX_PDF_BYTES:
        return {"state": "file_limit_exceeded", "pages": []}
    if len(pages) > MAX_FIELD_PAGES or len(set(pages)) != len(pages):
        raise ValueError("Invalid field page selection")
    reader = pypdf.PdfReader(path, strict=False, root_object_recovery_limit=1000)
    if reader.is_encrypted:
        return {"state": "encrypted", "pages": []}
    if not 1 <= len(reader.pages) <= MAX_PAGES:
        return {"state": "page_limit_exceeded", "pages": []}
    if any(not 1 <= page <= len(reader.pages) for page in pages):
        raise ValueError("Invalid field page number")

    observations = []
    for number in pages:
        try:
            page = reader.pages[number - 1]
            contents = page.get_contents()
            if contents is not None and len(contents.get_data()) > MAX_CONTENT_BYTES_PER_PAGE:
                observations.append({"page": number, "state": "content_limit_exceeded"})
                continue
            raw = page.extract_text() or ""
            lines = [line.strip() for line in raw.splitlines() if line.strip()]
            capped = (len(raw) > MAX_TEXT_CHARS_PER_PAGE or
                      len(lines) > MAX_LINES_PER_PAGE or
                      any(len(line) > MAX_LINE_CHARS for line in lines))
            observations.append({
                "page": number, "state": "read", "lines_capped": capped,
                "lines": [
                    {"line": index, "text": line[:MAX_LINE_CHARS]}
                    for index, line in enumerate(lines[:MAX_LINES_PER_PAGE], 1)
                ],
            })
        except Exception as error:
            observations.append({"page": number, "state": "page_error",
                                 "error_type": type(error).__name__})
    return {"state": "read" if all(item["state"] == "read" for item in observations)
            else "partial", "pages": observations, "parser_version": PYPDF_VERSION}


def main() -> None:
    _set_limits()
    try:
        result = probe(Path(sys.argv[1]), [int(value) for value in sys.argv[2].split(",")]
                       if sys.argv[2] else [])
    except Exception as error:
        result = {"state": "probe_error", "error_type": type(error).__name__, "pages": []}
    sys.stdout.write(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
