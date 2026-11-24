import os
import re
from typing import Dict, Any, List
from PIL import Image
from PIL.ExifTags import TAGS

SUSPICIOUS_SOFTWARE_KEYWORDS = [
    "photoshop", "canva", "gimp", "lightroom", "affinity",
    "snapseed", "procreate", "midjourney", "stable diffusion",
    "dall-e", "comfyui", "automatic1111", "firefly", "picsart",
    "facetune", "remini", "vanceai", "ilovepdf", "sejda", "smallpdf"
]

_PDF_SIMPLE_ESCAPES = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "b": "\b",
    "f": "\f",
    "(": "(",
    ")": ")",
    "\\": "\\",
}


def _clean_exif_text(value: Any) -> str | None:
    """Normalize raw EXIF tag values (bytes/NUL-padded strings) into clean text."""
    if value is None:
        return None
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="ignore")
    else:
        text = str(value)
    cleaned = text.replace("\x00", "").strip()
    return cleaned or None


def _decode_pdf_bytes(raw_bytes: bytes) -> str | None:
    """Decode PDF byte sequences (UTF-16BE BOM, UTF-8, or PDFDoc/Latin-1)."""
    if raw_bytes.startswith(b"\xfe\xff"):
        text = raw_bytes[2:].decode("utf-16-be", errors="ignore")
    else:
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = raw_bytes.decode("latin-1", errors="ignore")
    cleaned = text.replace("\x00", "").strip()
    return cleaned or None


def _decode_pdf_literal(raw: str) -> str | None:
    """Decode PDF literal string escapes (including octal sequences like \\056)."""
    out = bytearray()
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if ch == "\\" and i + 1 < n:
            nxt = raw[i + 1]
            if nxt in "\r\n":
                # Backslash immediately before newline is a line continuation.
                i += 3 if (nxt == "\r" and i + 2 < n and raw[i + 2] == "\n") else 2
                continue
            if nxt in _PDF_SIMPLE_ESCAPES:
                out.extend(_PDF_SIMPLE_ESCAPES[nxt].encode("latin-1"))
                i += 2
                continue
            if "0" <= nxt <= "7":
                end = min(i + 4, n)
                j = i + 2
                while j < end and "0" <= raw[j] <= "7":
                    j += 1
                out.append(int(raw[i + 1 : j], 8) & 0xFF)
                i = j
                continue
            out.extend(nxt.encode("latin-1", errors="ignore"))
            i += 2
        else:
            out.extend(ch.encode("latin-1", errors="ignore"))
            i += 1
    return _decode_pdf_bytes(bytes(out))


def _extract_pdf_info_field(content_sample: str, key: str) -> str | None:
    """Extract and decode a PDF Info dictionary field written as (...) or <hex>."""
    match = re.search(rf"/{re.escape(key)}\b\s*(?!<<)([(<])", content_sample)
    if not match:
        return None
    opener = match.group(1)
    start = match.end()

    if opener == "(":
        depth = 1
        i = start
        n = len(content_sample)
        while i < n and depth > 0:
            ch = content_sample[i]
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return _decode_pdf_literal(content_sample[start:i])
            i += 1
        return None

    end_idx = content_sample.find(">", start)
    if end_idx == -1:
        return None
    hex_digits = re.sub(r"\s+", "", content_sample[start:end_idx])
    if not hex_digits or not re.fullmatch(r"[0-9a-fA-F]+", hex_digits):
        return None
    if len(hex_digits) % 2 == 1:
        hex_digits += "0"
    return _decode_pdf_bytes(bytes.fromhex(hex_digits))

def extract_image_metadata(file_path: str) -> Dict[str, Any]:
    """Extract image metadata and unverified contextual observations."""
    flags: List[str] = []
    meta: Dict[str, Any] = {
        "format": "Unknown",
        "dimensions": "Unknown",
        "software": None,
        "camera_make": None,
        "camera_model": None,
        "created_at": None,
        "modified_at": None,
        "has_gps": False
    }

    try:
        with Image.open(file_path) as img:
            meta["format"] = img.format or "Unknown"
            meta["dimensions"] = f"{img.width}x{img.height}"
            meta["mode"] = img.mode

            # Square dimensions occur in both genuine crops and generated images.
            if img.width == img.height and img.width in [512, 768, 1024, 1536]:
                flags.append(f"Image dimensions are {img.width}x{img.height}; dimensions alone do not establish origin")

            exif_data = img._getexif()
            if exif_data:
                parsed_exif = {}
                for tag_id, value in exif_data.items():
                    tag_name = TAGS.get(tag_id, str(tag_id))
                    parsed_exif[tag_name] = value

                meta["software"] = _clean_exif_text(
                    parsed_exif.get("Software") or parsed_exif.get("ProcessingSoftware")
                )
                meta["camera_make"] = _clean_exif_text(parsed_exif.get("Make"))
                meta["camera_model"] = _clean_exif_text(parsed_exif.get("Model"))
                meta["created_at"] = _clean_exif_text(
                    parsed_exif.get("DateTimeOriginal") or parsed_exif.get("DateTimeDigitized")
                )
                meta["modified_at"] = _clean_exif_text(parsed_exif.get("DateTime"))
                meta["has_gps"] = "GPSInfo" in parsed_exif

                # Software tags are editable and do not authenticate the file.
                if meta["software"]:
                    software_str = meta["software"]
                    for keyword in SUSPICIOUS_SOFTWARE_KEYWORDS:
                        if keyword in software_str.lower():
                            flags.append(f"Software tag reports {software_str}; this tag is not independently verified")
                            break

                # A date difference can reflect ordinary editing or export.
                if meta["created_at"] and meta["modified_at"] and meta["created_at"] != meta["modified_at"]:
                    flags.append("Capture and modification date tags differ; this can reflect ordinary editing")
            else:
                # Sharing and export frequently remove EXIF.
                if meta["format"] in ["JPEG", "JPG"]:
                    flags.append("No EXIF tags found; absence does not establish image origin")

    except Exception as e:
        flags.append(f"Metadata parsing notice: {e}")

    return {
        "metadata": meta,
        "flags_count": len(flags),
        "flags": flags
    }

def extract_pdf_metadata(file_path: str) -> Dict[str, Any]:
    """Extract PDF header metadata as unverified context."""
    flags: List[str] = []
    meta: Dict[str, Any] = {
        "format": "PDF",
        "creator": None,
        "producer": None,
        "creation_date": None,
        "mod_date": None,
    }

    try:
        # Read the first 64KB and last 64KB where metadata dictionaries reside
        file_size = os.path.getsize(file_path)
        chunks = []
        with open(file_path, "rb") as f:
            chunks.append(f.read(min(65536, file_size)))
            if file_size > 65536:
                f.seek(max(0, file_size - 65536))
                chunks.append(f.read(65536))

        content_sample = b"\n".join(chunks).decode("latin-1", errors="ignore")

        meta["creator"] = _extract_pdf_info_field(content_sample, "Creator")
        meta["producer"] = _extract_pdf_info_field(content_sample, "Producer")
        meta["creation_date"] = _extract_pdf_info_field(content_sample, "CreationDate")
        meta["mod_date"] = _extract_pdf_info_field(content_sample, "ModDate")

        # Editing tools and conversion services are routine in valid PDFs.
        combined_tools = f"{meta.get('creator') or ''} {meta.get('producer') or ''}".lower()
        for kw in SUSPICIOUS_SOFTWARE_KEYWORDS:
            if kw in combined_tools:
                flags.append(f"PDF tool tag mentions {kw.capitalize()}; this does not establish forgery")
                break

        if meta["creation_date"] and meta["mod_date"] and meta["creation_date"] != meta["mod_date"]:
            flags.append("PDF creation and modification date tags differ; this does not establish forgery")

    except Exception as e:
        flags.append(f"PDF metadata inspection error: {e}")

    return {
        "metadata": meta,
        "flags_count": len(flags),
        "flags": flags
    }

def extract_video_metadata(file_path: str) -> Dict[str, Any]:
    """Inspects video stream parameters using OpenCV."""
    flags: List[str] = []
    meta: Dict[str, Any] = {
        "format": "Video",
        "dimensions": "Unknown",
        "fps": 0,
        "total_frames": 0,
        "duration_seconds": 0
    }

    cap = None
    try:
        import cv2
        cap = cv2.VideoCapture(file_path)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
            frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            duration = round(frames / fps, 2) if fps > 0 else 0

            meta["dimensions"] = f"{w}x{h}"
            meta["fps"] = round(fps, 1)
            meta["total_frames"] = frames
            meta["duration_seconds"] = duration

            # Low frame rate occurs in genuine CCTV and exported clips.
            if 0 < fps < 15:
                flags.append(f"Video frame rate is {fps:.1f} FPS; frame rate alone does not establish origin")
        else:
            flags.append("Failed to decode video container stream")
    except Exception as e:
        flags.append(f"Video metadata error: {e}")
    finally:
        if cap is not None:
            cap.release()

    return {
        "metadata": meta,
        "flags_count": len(flags),
        "flags": flags
    }

def extract_metadata(file_path: str, media_type: str) -> Dict[str, Any]:
    """Extract metadata observations without treating them as proof of tampering."""
    if not os.path.exists(file_path):
        return {"metadata": {}, "flags_count": 0, "flags": []}

    if media_type == "Document" or file_path.lower().endswith(".pdf"):
        return extract_pdf_metadata(file_path)
    elif media_type == "Video" or any(file_path.lower().endswith(ext) for ext in [".mp4", ".avi", ".mov", ".webm", ".mkv"]):
        return extract_video_metadata(file_path)
    else:
        return extract_image_metadata(file_path)
