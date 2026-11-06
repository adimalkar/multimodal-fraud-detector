"""Provenance checks that run before any model call.

These read what a file says about its own origin: signed Content Credentials
(C2PA), unsigned IPTC/XMP source tags, generator metadata, and visible
generator watermarks.

They are only ever used to raise a file for review, never to clear it. A file
that declares itself AI-generated is incriminating itself, so a valid
signature is enough to report that declaration even without a trust list. The
absence of a declaration, or a "camera" declaration, proves nothing: metadata
is easy to strip, and an unverified claim of authenticity is exactly what a
forger would add.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

from PIL import Image, ImageOps

PROVENANCE_VERSION = "provenance-v1"

# IPTC digital source types that describe synthetic or partly synthetic media.
# https://cv.iptc.org/newscodes/digitalsourcetype/
AI_SOURCE_TYPES = {
    "trainedalgorithmicmedia",
    "compositewithtrainedalgorithmicmedia",
    "algorithmicmedia",
    "compositesynthetic",
}

C2PA_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/heic", "image/avif",
    "video/mp4", "video/quicktime", "application/pdf",
}

# Names that appear in generator metadata or as visible marks. Matching is
# case-insensitive on whole words, and every match is reported with the exact
# text so a reviewer can judge it.
GENERATOR_NAMES = [
    "midjourney", "dall-e", "dall·e", "dalle", "openai", "chatgpt", "stable diffusion",
    "stablediffusion", "sdxl", "comfyui", "automatic1111", "novelai", "invokeai",
    "adobe firefly", "firefly", "imagen", "gemini", "nano banana", "google ai", "flux",
    "ideogram", "leonardo.ai", "runway", "sora", "veo", "kling", "pika", "hailuo",
    "seedream", "recraft", "bing image creator", "meta ai", "grok",
]
GENERATOR_PATTERN = re.compile(
    r"(?<![a-z])(" + "|".join(re.escape(name) for name in GENERATOR_NAMES) + r")(?![a-z])",
    re.IGNORECASE,
)
# Generators known to stamp a visible text mark on their output. Kept narrow,
# because OCR runs on real photos too and a shop sign reading "Gemini" or
# "Flux" must not raise a claim.
WATERMARK_NAMES = ["veo", "sora", "kling", "hailuo", "grok", "meta ai", "pika", "runway"]
WATERMARK_PATTERN = re.compile(
    r"(?<![a-z])(" + "|".join(re.escape(name) for name in WATERMARK_NAMES) + r")(?![a-z])",
    re.IGNORECASE,
)
AI_LABEL_PATTERN = re.compile(
    r"\b(ai[- ]generated|generated (?:by|with) ai|made with ai|imagined with ai|created with ai)\b",
    re.IGNORECASE,
)

# PNG text chunks written by local generators. Their presence is the signal;
# their content (often the full prompt) is not copied into the report.
GENERATOR_PNG_KEYS = {
    "parameters": "Stable Diffusion WebUI (A1111/Forge)",
    "prompt": "ComfyUI",
    "workflow": "ComfyUI",
    "dream": "InvokeAI",
    "invokeai_metadata": "InvokeAI",
    "sd-metadata": "InvokeAI",
}

XMP_PACKET = re.compile(rb"<x:xmpmeta.*?</x:xmpmeta>", re.DOTALL)
XMP_SOURCE_TYPE = re.compile(rb"digitalsourcetype[^/]{0,200}?/([A-Za-z]+)", re.IGNORECASE)

MAX_SCAN_BYTES = 64 * 1024 * 1024
OCR_TIMEOUT_SECONDS = 10
WATERMARK_FRAMES = 3


def _finding(kind: str, strength: str, summary: str, source: str) -> Dict[str, str]:
    return {"kind": kind, "strength": strength, "summary": summary, "source": source}


def _source_type_name(value: Optional[str]) -> str:
    return (value or "").rstrip("/").rsplit("/", 1)[-1].strip()


def check_content_credentials(path: str, content_type: str) -> Dict[str, Any]:
    """Read an embedded C2PA manifest without fetching anything remote."""
    if content_type not in C2PA_TYPES:
        return {"check": "content_credentials", "state": "unsupported"}

    import json

    import c2pa

    trust_anchors = os.getenv("C2PA_TRUST_ANCHORS_PATH")
    verify: Dict[str, Any] = {
        "verify_after_reading": True,
        "verify_trust": bool(trust_anchors),
        "remote_manifest_fetch": False,
        "ocsp_fetch": False,
    }
    settings: Dict[str, Any] = {"verify": verify}
    if trust_anchors:
        try:
            with open(trust_anchors, encoding="utf-8") as anchors:
                settings["trust"] = {"trust_anchors": anchors.read()}
        except OSError:
            return {"check": "content_credentials", "state": "error", "error_type": "TrustListUnreadable"}

    try:
        with c2pa.Context.from_dict(settings) as context:
            reader = c2pa.Reader.try_create(path, context=context)
            if reader is None:
                return {"check": "content_credentials", "state": "absent"}
            with reader:
                manifest_store = json.loads(reader.json())
                validation = reader.get_validation_state()
    except c2pa.C2paError as error:
        return {"check": "content_credentials", "state": "error", "error_type": type(error).__name__}

    manifests = manifest_store.get("manifests") or {}
    active = manifests.get(manifest_store.get("active_manifest") or "") or {}
    source_types: List[str] = []
    descriptions: List[str] = []
    for manifest in manifests.values():
        for assertion in manifest.get("assertions") or []:
            if not str(assertion.get("label", "")).startswith("c2pa.actions"):
                continue
            for action in (assertion.get("data") or {}).get("actions") or []:
                name = _source_type_name(action.get("digitalSourceType"))
                if name:
                    source_types.append(name)
                if name.lower() in AI_SOURCE_TYPES and action.get("description"):
                    descriptions.append(str(action["description"])[:200])

    signature = active.get("signature_info") or {}
    state = {"Trusted": "valid_trusted", "Valid": "valid_untrusted", "Invalid": "invalid"}.get(validation, "unknown")
    return {
        "check": "content_credentials",
        "state": state,
        "trust_list_configured": bool(trust_anchors),
        "signer": signature.get("issuer") or signature.get("common_name"),
        "generator": [info.get("name") for info in active.get("claim_generator_info") or [] if info.get("name")][:3],
        "source_types": list(dict.fromkeys(source_types)),
        "ai_declared": any(name.lower() in AI_SOURCE_TYPES for name in source_types),
        "descriptions": list(dict.fromkeys(descriptions))[:3],
    }


def check_embedded_tags(path: str) -> Dict[str, Any]:
    """Find IPTC digital source types in XMP packets. These are unsigned."""
    with open(path, "rb") as source:
        data = source.read(MAX_SCAN_BYTES)
    source_types = sorted({
        match.decode("ascii", "ignore")
        for packet in XMP_PACKET.findall(data)
        for match in XMP_SOURCE_TYPE.findall(packet)
    })
    return {
        "check": "embedded_tags",
        "state": "found" if source_types else "absent",
        "source_types": source_types,
        "ai_declared": any(name.lower() in AI_SOURCE_TYPES for name in source_types),
    }


def check_generator_metadata(path: str, media_type: str) -> Dict[str, Any]:
    """Look for metadata written by image generators. Images only."""
    if media_type != "Image":
        return {"check": "generator_metadata", "state": "unsupported"}
    hits: List[str] = []
    try:
        with Image.open(path) as image:
            for key, tool in GENERATOR_PNG_KEYS.items():
                if any(str(name).lower() == key for name in image.info):
                    hits.append(f"{tool} settings in the '{key}' text field")
            exif = image.getexif()
            # Tool fields name the program. Free-text fields only count when they say "AI generated".
            for tag, label, pattern in (
                (305, "Software", GENERATOR_PATTERN), (271, "Make", GENERATOR_PATTERN), (272, "Model", GENERATOR_PATTERN),
                (270, "Description", AI_LABEL_PATTERN), (315, "Artist", AI_LABEL_PATTERN),
            ):
                value = str(exif.get(tag) or "")
                if pattern.search(value) or AI_LABEL_PATTERN.search(value):
                    hits.append(f"{label} tag reads \"{value.strip()[:80]}\"")
    except Exception as error:  # Metadata problems are reported, never fatal.
        return {"check": "generator_metadata", "state": "error", "error_type": type(error).__name__}
    return {"check": "generator_metadata", "state": "found" if hits else "absent", "hits": hits}


def _video_frames(path: str, count: int = WATERMARK_FRAMES) -> List[Image.Image]:
    import cv2

    capture = cv2.VideoCapture(path)
    frames: List[Image.Image] = []
    try:
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        for position in range(count):
            capture.set(cv2.CAP_PROP_POS_FRAMES, round((position + 0.5) * total / count) if total > 0 else 0)
            okay, frame = capture.read()
            if okay:
                frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    finally:
        capture.release()
    return frames


def _strips(image: Image.Image) -> List[Image.Image]:
    """Generator marks sit along the top or bottom edge."""
    image = image.convert("L")
    width, height = image.size
    strips = []
    for box in ((0, int(height * 0.86), width, height), (0, 0, width, int(height * 0.1))):
        strip = ImageOps.autocontrast(image.crop(box))
        scale = max(1, min(3, 1800 // max(1, strip.width)))
        strips.append(strip.resize((strip.width * scale, strip.height * scale)))
    return strips


def _ocr(image: Image.Image) -> str:
    with tempfile.TemporaryDirectory() as directory:
        source = os.path.join(directory, "strip.png")
        image.save(source)
        result = subprocess.run(
            ["tesseract", source, "-", "--psm", "11"],
            capture_output=True, text=True, timeout=OCR_TIMEOUT_SECONDS,
        )
    return result.stdout


def check_visible_watermark(path: str, media_type: str) -> Dict[str, Any]:
    """OCR the frame edges for a visible generator mark or an "AI generated" label."""
    if media_type not in {"Image", "Video"}:
        return {"check": "visible_watermark", "state": "unsupported"}
    if not shutil.which("tesseract"):
        return {"check": "visible_watermark", "state": "not_run", "reason": "OCR is not installed on this server"}
    try:
        if media_type == "Video":
            images = _video_frames(path)
        else:
            with Image.open(path) as image:
                images = [image.convert("RGB")]
        matches = set()
        for image in images:
            for strip in _strips(image):
                for line in _ocr(strip).splitlines():
                    for found in WATERMARK_PATTERN.findall(line) + AI_LABEL_PATTERN.findall(line):
                        matches.add(found.strip())
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        return {"check": "visible_watermark", "state": "error", "error_type": type(error).__name__}
    return {
        "check": "visible_watermark",
        "state": "found" if matches else "absent",
        "frames_checked": len(images),
        "text": sorted(matches),
    }


def model_reported_watermark(text: Optional[str]) -> Optional[str]:
    """Keep a vision-model watermark report only if it names a generator."""
    if not text:
        return None
    text = str(text).strip()
    return text[:80] if WATERMARK_PATTERN.search(text) or AI_LABEL_PATTERN.search(text) else None


def summarise(checks: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    for check in checks:
        name = check["check"]
        if name == "content_credentials" and check.get("ai_declared"):
            said = f" (\"{check['descriptions'][0]}\")" if check.get("descriptions") else ""
            signer = check.get("signer") or "an unnamed signer"
            if check["state"] in {"valid_trusted", "valid_untrusted"}:
                trust = "a trusted" if check["state"] == "valid_trusted" else "a valid"
                findings.append(_finding(
                    "declared_ai_signed", "strong",
                    f"Content Credentials with {trust} signature from {signer} declare this file AI-generated{said}.",
                    name,
                ))
            else:
                findings.append(_finding(
                    "declared_ai_broken_signature", "moderate",
                    f"Content Credentials declare this file AI-generated{said}, but the signature does not verify, "
                    "so the file was changed after signing.",
                    name,
                ))
        elif name == "embedded_tags" and check.get("ai_declared"):
            types = ", ".join(t for t in check["source_types"] if t.lower() in AI_SOURCE_TYPES)
            findings.append(_finding(
                "declared_ai_tag", "strong",
                f"An embedded IPTC source tag declares this file AI-generated ({types}).",
                name,
            ))
        elif name == "generator_metadata" and check.get("hits"):
            findings.append(_finding(
                "generator_metadata", "strong",
                "Image-generator metadata is present: " + "; ".join(check["hits"]) + ".",
                name,
            ))
        elif name == "visible_watermark" and check.get("text"):
            findings.append(_finding(
                "visible_watermark", "moderate",
                "Visible text along the frame edge matches an AI generator's mark: " + ", ".join(f"\"{t}\"" for t in check["text"]) + ".",
                name,
            ))
    return findings


def inspect_provenance(path: str, media_type: str, content_type: str) -> Dict[str, Any]:
    """Run every provenance check. Each check reports its own state, so a skipped check never reads as clean."""
    checks = [
        check_content_credentials(path, content_type),
        check_embedded_tags(path),
        check_generator_metadata(path, media_type),
        check_visible_watermark(path, media_type),
    ]
    findings = summarise(checks)
    return {
        "version": PROVENANCE_VERSION,
        "checks": checks,
        "findings": findings,
        "decisive": any(finding["strength"] == "strong" for finding in findings),
        "note": "Provenance can raise a file for review but never clears one: metadata is easy to strip or forge.",
    }
