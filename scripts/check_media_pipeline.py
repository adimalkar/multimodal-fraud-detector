"""Exercise image, PDF, and video preprocessing or real API jobs with synthetic evidence."""

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.qwen_agent import encode_image, encode_pdf_pages, extract_video_frames  # noqa: E402
from check_backend import check_backend  # noqa: E402


def create_fixtures(directory):
    image = Image.new("RGB", (640, 360), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((60, 85, 580, 295), outline="navy", width=5)
    draw.text((100, 135), "SYNTHETIC PIPELINE CHECK", fill="black")
    draw.text((100, 175), "No real claim or fraud label", fill="black")

    image_path = directory / "synthetic_claim.jpg"
    document_path = directory / "synthetic_claim.pdf"
    video_path = directory / "synthetic_claim.avi"
    image.save(image_path, format="JPEG")
    image.save(document_path, format="PDF", resolution=100.0)

    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"MJPG"), 2.0, (640, 360)
    )
    if not writer.isOpened():
        raise RuntimeError("OpenCV could not create the synthetic AVI fixture")
    try:
        for frame_index in range(10):
            frame = np.asarray(image).copy()
            cv2.putText(
                frame,
                f"Frame {frame_index + 1}",
                (100, 250),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 0),
                2,
            )
            writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    finally:
        writer.release()

    if not video_path.exists() or video_path.stat().st_size == 0:
        raise RuntimeError("Synthetic AVI fixture was not written")
    return [
        ("Image", image_path, "image/jpeg"),
        ("Document", document_path, "application/pdf"),
        ("Video", video_path, "video/x-msvideo"),
    ]


def check_preprocessing(fixtures):
    image_path, document_path, video_path = (item[1] for item in fixtures)
    counts = {
        "image_encoded": bool(encode_image(str(image_path))),
        "pdf_pages": len(encode_pdf_pages(str(document_path))),
        "video_frames": len(extract_video_frames(str(video_path))),
    }
    if not counts["image_encoded"] or counts["pdf_pages"] < 1 or counts["video_frames"] < 1:
        raise RuntimeError(f"Preprocessing failed: {counts}")
    print(f"Preprocessing passed: {json.dumps(counts, sort_keys=True)}")


def run_job(base_url, media_type, path, content_type, timeout_seconds):
    with path.open("rb") as evidence:
        response = requests.post(
            base_url + "/api/analyze",
            files={"file": (path.name, evidence, content_type)},
            timeout=30,
        )
    response.raise_for_status()
    job_id = response.json()["job_id"]
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        response = requests.get(base_url + f"/api/jobs/{job_id}", timeout=15)
        response.raise_for_status()
        job = response.json()
        if job["status"] == "failed":
            raise RuntimeError(f"{media_type} job {job_id} failed: {job.get('error')}")
        if job["status"] == "completed":
            result = job.get("result") or {}
            confidence = result.get("confidence_score")
            if (
                result.get("media_type") != media_type
                or result.get("classification") not in {"Real", "Fake"}
                or not isinstance(confidence, (int, float))
                or not 0 <= confidence <= 1
                or not result.get("vision_findings")
            ):
                raise RuntimeError(f"{media_type} job {job_id} returned an invalid result")
            print(
                f"{media_type} job completed: "
                f"{json.dumps({'job_id': job_id, 'classification': result['classification'], 'confidence': confidence})}"
            )
            return
        time.sleep(5)
    raise TimeoutError(f"{media_type} job {job_id} did not complete in {timeout_seconds}s")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", help="Backend origin for provider-backed jobs")
    parser.add_argument("--preprocess-only", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()
    if not args.preprocess_only and not args.base_url:
        parser.error("base_url is required unless --preprocess-only is set")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")

    try:
        with tempfile.TemporaryDirectory(prefix="fraud-pipeline-check-") as tmpdir:
            fixtures = create_fixtures(Path(tmpdir))
            check_preprocessing(fixtures)
            if not args.preprocess_only:
                base_url = args.base_url.rstrip("/")
                check_backend(base_url)
                for media_type, path, content_type in fixtures:
                    run_job(base_url, media_type, path, content_type, args.timeout_seconds)
                print("All three provider-backed modalities completed with structured results")
    except (OSError, ValueError, RuntimeError, TimeoutError, requests.RequestException) as error:
        print(f"Media pipeline check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
