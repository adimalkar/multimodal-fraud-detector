"""Resource-limited child process for bounded PDF structure observations."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PYPDF_VERSION = "6.19.0"
MAX_PAGES = 20
MAX_CONTENT_BYTES_PER_PAGE = 2 * 1024 * 1024
MAX_TEXT_CHARS_REPORTED = 100_000


def _set_limits() -> None:
    # Limits apply before any untrusted PDF is parsed. The parent also enforces
    # a wall-clock timeout; this child shares its container's filesystem/user.
    if sys.platform != "win32":
        import resource

        memory = 512 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_CPU, (12, 12))


def _direct_image_count(page) -> int:
    resources = page.get("/Resources")
    if not resources:
        return 0
    objects = resources.get_object().get("/XObject")
    if not objects:
        return 0
    # This is a direct XObject count, not an exhaustive embedded-image scan.
    return sum(
        object_ref.get_object().get("/Subtype") == "/Image"
        for object_ref in list(objects.get_object().values())[:200]
    )


def probe(path: Path) -> dict:
    import pypdf

    if pypdf.__version__ != PYPDF_VERSION:
        raise RuntimeError("PDF parser version differs from the pinned version")
    reader = pypdf.PdfReader(path, strict=False, root_object_recovery_limit=1000)
    if reader.is_encrypted:
        return {"state": "encrypted", "page_count": None, "pages": []}
    page_count = len(reader.pages)
    if not 1 <= page_count <= MAX_PAGES:
        return {"state": "page_limit_exceeded", "page_count": page_count, "pages": []}

    pages = []
    for index, page in enumerate(reader.pages, 1):
        item = {"page": index, "state": "inspected", "text_chars": 0,
                "text_chars_capped": False, "direct_image_xobjects": 0,
                "content_bytes": 0}
        try:
            contents = page.get_contents()
            content_data = contents.get_data() if contents is not None else b""
            item["content_bytes"] = min(len(content_data), MAX_CONTENT_BYTES_PER_PAGE + 1)
            if len(content_data) > MAX_CONTENT_BYTES_PER_PAGE:
                item["state"] = "content_limit_exceeded"
            else:
                text = page.extract_text() or ""
                item["text_chars"] = min(len(text.strip()), MAX_TEXT_CHARS_REPORTED)
                item["text_chars_capped"] = len(text.strip()) > MAX_TEXT_CHARS_REPORTED
                item["direct_image_xobjects"] = _direct_image_count(page)
        except Exception:
            item["state"] = "parse_error"
        pages.append(item)

    inspected = [page for page in pages if page["state"] == "inspected"]
    text_pages = sum(page["text_chars"] > 0 for page in inspected)
    image_pages = sum(page["direct_image_xobjects"] > 0 for page in inspected)
    if len(inspected) != page_count:
        profile = "undetermined"
    elif text_pages == page_count and image_pages == 0:
        profile = "text_layer_candidate"
    elif image_pages == page_count and text_pages == 0:
        profile = "image_only_candidate"
    elif text_pages and image_pages:
        profile = "mixed_candidate"
    else:
        profile = "undetermined"
    return {
        "state": "parsed", "page_count": page_count, "pages": pages,
        "document_profile": profile, "text_layer_pages": text_pages,
        "direct_image_pages": image_pages, "inspected_pages": len(inspected),
        "has_acroform": bool(reader.root_object.get("/AcroForm")),
    }


def main() -> None:
    _set_limits()
    try:
        result = probe(Path(sys.argv[1]))
    except Exception as error:
        # Never return PDF text, metadata, local paths, or parser exception prose.
        result = {"state": "parse_error", "error_type": type(error).__name__,
                  "page_count": None, "pages": []}
    result["parser_version"] = PYPDF_VERSION
    sys.stdout.write(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
