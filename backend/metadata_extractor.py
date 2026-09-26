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

def extract_image_metadata(file_path: str) -> Dict[str, Any]:
    """Extracts EXIF metadata, camera tags, and forensic software flags from images."""
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

            # Check for square dimensions typical of popular AI generative models (512x512, 1024x1024)
            if img.width == img.height and img.width in [512, 768, 1024, 1536]:
                flags.append(f"Image has exact square dimension ({img.width}x{img.height}) characteristic of AI generators")

            exif_data = img._getexif()
            if exif_data:
                parsed_exif = {}
                for tag_id, value in exif_data.items():
                    tag_name = TAGS.get(tag_id, str(tag_id))
                    parsed_exif[tag_name] = value

                meta["software"] = parsed_exif.get("Software") or parsed_exif.get("ProcessingSoftware")
                meta["camera_make"] = parsed_exif.get("Make")
                meta["camera_model"] = parsed_exif.get("Model")
                meta["created_at"] = parsed_exif.get("DateTimeOriginal") or parsed_exif.get("DateTimeDigitized")
                meta["modified_at"] = parsed_exif.get("DateTime")
                meta["has_gps"] = "GPSInfo" in parsed_exif

                # Check for suspicious editing software
                if meta["software"]:
                    software_str = str(meta["software"]).strip()
                    for keyword in SUSPICIOUS_SOFTWARE_KEYWORDS:
                        if keyword in software_str.lower():
                            flags.append(f"Post-processing or AI editing signature detected in metadata: {software_str}")
                            break

                # Check for timestamp divergence
                if meta["created_at"] and meta["modified_at"] and meta["created_at"] != meta["modified_at"]:
                    flags.append("Original capture timestamp differs from modification timestamp")
            else:
                # If everyday photo format has completely stripped EXIF metadata
                if meta["format"] in ["JPEG", "JPG"]:
                    flags.append("Camera sensor & hardware EXIF metadata is completely stripped or absent")

    except Exception as e:
        flags.append(f"Metadata parsing notice: {e}")

    return {
        "metadata": meta,
        "flags_count": len(flags),
        "flags": flags
    }

def extract_pdf_metadata(file_path: str) -> Dict[str, Any]:
    """Inspects PDF document stream headers for producer and editor software signatures."""
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

        # Scan for /Creator and /Producer
        creator_match = re.search(r"/Creator\s*\((.*?)\)", content_sample)
        if creator_match:
            meta["creator"] = creator_match.group(1).strip()

        producer_match = re.search(r"/Producer\s*\((.*?)\)", content_sample)
        if producer_match:
            meta["producer"] = producer_match.group(1).strip()

        date_match = re.search(r"/CreationDate\s*\((.*?)\)", content_sample)
        if date_match:
            meta["creation_date"] = date_match.group(1).strip()

        mod_match = re.search(r"/ModDate\s*\((.*?)\)", content_sample)
        if mod_match:
            meta["mod_date"] = mod_match.group(1).strip()

        # Check for editing tools
        combined_tools = f"{meta.get('creator') or ''} {meta.get('producer') or ''}".lower()
        for kw in SUSPICIOUS_SOFTWARE_KEYWORDS:
            if kw in combined_tools:
                flags.append(f"Document was created/modified using editing or online conversion tool: {kw.capitalize()}")
                break

        if meta["creation_date"] and meta["mod_date"] and meta["creation_date"] != meta["mod_date"]:
            flags.append("Document modified date does not match creation date")

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

            # Low FPS anomaly check (often indicative of synthesized animation or GIF converted to MP4)
            if 0 < fps < 15:
                flags.append(f"Abnormally low frame rate detected ({fps:.1f} FPS), often associated with synthesized video")

            cap.release()
        else:
            flags.append("Failed to decode video container stream")
    except Exception as e:
        flags.append(f"Video metadata error: {e}")

    return {
        "metadata": meta,
        "flags_count": len(flags),
        "flags": flags
    }

def extract_metadata(file_path: str, media_type: str) -> Dict[str, Any]:
    """Unified entry point to extract metadata and detect tampering flags across any media."""
    if not os.path.exists(file_path):
        return {"metadata": {}, "flags_count": 0, "flags": []}

    if media_type == "Document" or file_path.lower().endswith(".pdf"):
        return extract_pdf_metadata(file_path)
    elif media_type == "Video" or any(file_path.lower().endswith(ext) for ext in [".mp4", ".avi", ".mov", ".webm", ".mkv"]):
        return extract_video_metadata(file_path)
    else:
        return extract_image_metadata(file_path)
