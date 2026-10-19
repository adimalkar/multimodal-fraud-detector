"""Bounded PDF page rendering and English OCR in a credential-free child."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from backend.pdf_probe import MAX_PAGES

MAX_OCR_PAGES = 4
MAX_RENDER_EDGE = 1400
MAX_RENDER_BYTES = 8 * 1024 * 1024
MAX_TSV_BYTES = 256 * 1024
MAX_WORDS_PER_PAGE = 100
MAX_WORD_CHARS = 64
COMMAND_TIMEOUT_SECONDS = 15


def _set_limits() -> None:
    if sys.platform != "win32":
        import resource

        memory = 512 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_RENDER_BYTES, MAX_RENDER_BYTES))


def _version(command: str) -> str | None:
    try:
        result = subprocess.run(
            [command, "-v" if command == "pdftoppm" else "--version"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=3, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    line = (result.stdout or result.stderr).decode("ascii", "ignore").splitlines()
    return line[0][:80] if result.returncode == 0 and line else None


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError("Invalid renderer output")
    width, height = struct.unpack(">II", header[16:24])
    if not 1 <= width <= MAX_RENDER_EDGE or not 1 <= height <= MAX_RENDER_EDGE:
        raise ValueError("Renderer output exceeded pixel limit")
    return width, height


def _words(tsv: bytes, width: int, height: int) -> tuple[int, list[dict], float | None]:
    reader = csv.DictReader(io.StringIO(tsv.decode("utf-8", "replace")), delimiter="\t")
    if not reader.fieldnames or not {"level", "left", "top", "width", "height", "conf", "text"}.issubset(reader.fieldnames):
        raise ValueError("Invalid OCR output")
    count = 0
    confidence_sum = 0.0
    words = []
    for row in reader:
        if row["level"] != "5" or not (word := (row["text"] or "").strip()):
            continue
        left, top, box_width, box_height = (int(row[key]) for key in ("left", "top", "width", "height"))
        confidence = float(row["conf"])
        if (not 0 <= confidence <= 100 or left < 0 or top < 0 or box_width < 1
                or box_height < 1 or left + box_width > width or top + box_height > height):
            raise ValueError("Invalid OCR geometry")
        count += 1
        confidence_sum += confidence
        if len(words) < MAX_WORDS_PER_PAGE:
            words.append({
                "text": word[:MAX_WORD_CHARS],
                "text_capped": len(word) > MAX_WORD_CHARS,
                "bbox_px": [left, top, left + box_width, top + box_height],
                "confidence": round(confidence / 100, 3),
            })
    return count, words, round(confidence_sum / (100 * count), 3) if count else None


def _one_page(path: Path, page: int, directory: Path) -> dict:
    output_base = directory / f"page-{page}"
    render = subprocess.run(
        ["pdftoppm", "-f", str(page), "-l", str(page), "-singlefile", "-gray",
         "-png", "-scale-to", str(MAX_RENDER_EDGE), "-q", str(path), str(output_base)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=COMMAND_TIMEOUT_SECONDS, check=False,
    )
    image_path = output_base.with_suffix(".png")
    if render.returncode != 0 or not image_path.is_file():
        return {"page": page, "state": "render_error"}
    if image_path.stat().st_size > MAX_RENDER_BYTES:
        return {"page": page, "state": "render_limit_exceeded"}
    width, height = _png_size(image_path)
    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
    tsv_base = directory / f"ocr-{page}"
    ocr = subprocess.run(
        ["tesseract", str(image_path), str(tsv_base), "-l", "eng", "--psm", "3", "tsv"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=COMMAND_TIMEOUT_SECONDS, check=False,
    )
    tsv_path = tsv_base.with_suffix(".tsv")
    if ocr.returncode != 0 or not tsv_path.is_file():
        return {"page": page, "state": "ocr_error", "render_sha256": digest,
                "image_size_px": [width, height]}
    if tsv_path.stat().st_size > MAX_TSV_BYTES:
        return {"page": page, "state": "ocr_output_limit_exceeded",
                "render_sha256": digest, "image_size_px": [width, height]}
    count, words, mean = _words(tsv_path.read_bytes(), width, height)
    return {
        "page": page, "state": "read", "render_sha256": digest,
        "image_size_px": [width, height], "word_count": count,
        "words_reported": len(words), "words_capped": count > len(words),
        "mean_word_confidence": mean, "words": words,
    }


def probe(path: Path, pages: list[int]) -> dict:
    if not 1 <= len(pages) <= MAX_OCR_PAGES or len(set(pages)) != len(pages):
        raise ValueError("Invalid OCR page selection")
    if any(not 1 <= page <= MAX_PAGES for page in pages):
        raise ValueError("Invalid OCR page number")
    if not shutil.which("pdftoppm") or not shutil.which("tesseract"):
        return {"state": "dependency_unavailable", "pages": []}
    observations = []
    with tempfile.TemporaryDirectory(prefix="pdf-ocr-") as temporary:
        directory = Path(temporary)
        for page in pages:
            try:
                observations.append(_one_page(path, page, directory))
            except subprocess.TimeoutExpired:
                observations.append({"page": page, "state": "timeout"})
            except Exception as error:
                observations.append({"page": page, "state": "page_error",
                                     "error_type": type(error).__name__})
    return {
        "state": "read" if all(item["state"] == "read" for item in observations) else "partial",
        "pages": observations,
        "renderer_version": _version("pdftoppm"),
        "ocr_version": _version("tesseract"),
        "ocr_language": "eng",
        "render_max_edge_px": MAX_RENDER_EDGE,
    }


def main() -> None:
    _set_limits()
    try:
        result = probe(Path(sys.argv[1]), [int(page) for page in sys.argv[2].split(",")])
    except Exception as error:
        result = {"state": "probe_error", "error_type": type(error).__name__, "pages": []}
    sys.stdout.write(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
