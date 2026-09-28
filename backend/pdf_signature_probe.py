"""Bounded, offline PDF signature observations in a credential-free child process."""

from __future__ import annotations

import json
import hashlib
import os
import sys
from pathlib import Path

from backend.pdf_probe import _set_limits

PYHANKO_VERSION = "0.37.0"
MAX_SIGNATURES = 8
MAX_TRUST_BUNDLE_BYTES = 1024 * 1024


def _trust_roots(path_string: str | None):
    if not path_string:
        return [], None
    from pyhanko.keys import load_certs_from_pemder

    path = Path(path_string)
    if not path.is_absolute() or not path.is_file() or path.stat().st_size > MAX_TRUST_BUNDLE_BYTES:
        raise ValueError("Invalid PDF signature trust bundle")
    bundle = path.read_bytes()
    if len(bundle) > MAX_TRUST_BUNDLE_BYTES:
        raise ValueError("Invalid PDF signature trust bundle")
    roots = list(load_certs_from_pemder([str(path)]))
    if not roots:
        raise ValueError("Empty PDF signature trust bundle")
    if path.read_bytes() != bundle:
        raise ValueError("PDF signature trust bundle changed during validation")
    return roots, hashlib.sha256(bundle).hexdigest()


def probe(path: Path, trust_bundle_path: str | None = None) -> dict:
    from pyhanko import version
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    if version.__version__ != PYHANKO_VERSION:
        raise RuntimeError("PDF signature validator version differs from the pinned version")
    roots, bundle_sha256 = _trust_roots(trust_bundle_path)
    configured = bundle_sha256 is not None
    with path.open("rb") as stream:
        reader = PdfFileReader(stream, strict=False)
        signatures = reader.embedded_signatures
        if len(signatures) > MAX_SIGNATURES:
            return {"state": "signature_limit_exceeded", "signature_count": len(signatures),
                    "signatures": [], "trust_roots_configured": configured,
                    "trust_bundle_sha256": bundle_sha256}
        if not signatures:
            return {"state": "unsigned", "signature_count": 0, "signatures": [],
                    "trust_roots_configured": configured,
                    "trust_bundle_sha256": bundle_sha256}

        observations = []
        for index, signature in enumerate(signatures, 1):
            try:
                context = ValidationContext(trust_roots=roots, allow_fetching=False)
                status = validate_pdf_signature(signature, context)
                coverage = status.coverage.name if status.coverage is not None else None
                modification = (
                    status.modification_level.name
                    if status.modification_level is not None else None
                )
                observations.append({
                    "index": index,
                    "state": "checked",
                    "cryptographic_integrity": (
                        "valid" if status.intact and status.valid else "invalid"
                    ),
                    "trust": (
                        "not_configured" if not configured else
                        "anchored_offline" if status.trusted else "untrusted_or_unverifiable"
                    ),
                    "coverage": coverage,
                    "post_signature_updates": (
                        False if coverage == "ENTIRE_FILE" else
                        True if coverage == "ENTIRE_REVISION" else None
                    ),
                    "modification_level": modification,
                    "document_policy_ok": status.docmdp_ok,
                })
            except Exception as error:
                # Parser and validation prose may contain document or certificate data.
                observations.append({"index": index, "state": "verification_error",
                                     "error_type": type(error).__name__})
        return {
            "state": "checked" if all(item["state"] == "checked" for item in observations)
                     else "partial",
            "signature_count": len(signatures),
            "signatures": observations,
            "trust_roots_configured": configured,
            "trust_bundle_sha256": bundle_sha256,
        }


def main() -> None:
    _set_limits()
    try:
        result = probe(Path(sys.argv[1]), os.getenv("PDF_SIGNATURE_TRUST_ROOTS_PATH"))
    except Exception as error:
        result = {"state": "verification_error", "error_type": type(error).__name__,
                  "signature_count": None, "signatures": [],
                  "trust_roots_configured": bool(os.getenv("PDF_SIGNATURE_TRUST_ROOTS_PATH")),
                  "trust_bundle_sha256": None}
    result["validator_version"] = PYHANKO_VERSION
    result["online_revocation_checked"] = False
    sys.stdout.write(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
