"""Opt-in video structure observations; media authenticity remains undetermined."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from backend.video_probe import DEMUXERS, MAX_VIDEO_BYTES

VIDEO_PIPELINE_VERSION = "video-evidence-v1"
VIDEO_POLICY_VERSION = "manual-review-video-v1"
PROBE_TIMEOUT_SECONDS = 20


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(64 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def _probe(path: Path, content_type: str) -> dict:
    process = subprocess.Popen(
        [sys.executable, "-m", "backend.video_probe", str(path), content_type],
        cwd=Path(__file__).resolve().parent.parent,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env={"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONNOUSERSITE": "1"},
        start_new_session=os.name == "posix",
    )
    try:
        output, _ = process.communicate(timeout=PROBE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
        process.communicate()
        return {"state": "probe_error", "error_type": "TimeoutExpired", "streams": []}
    if process.returncode != 0 or len(output) > 64 * 1024:
        return {"state": "probe_error", "error_type": "ProbeFailed", "streams": []}
    try:
        result = json.loads(output)
    except (ValueError, UnicodeDecodeError):
        return {"state": "probe_error", "error_type": "ProbeOutputInvalid", "streams": []}
    if not isinstance(result, dict) or result.get("state") not in {
        "parsed", "metadata_incomplete", "no_video_stream", "duration_limit_exceeded",
        "stream_limit_exceeded", "unsupported_container", "dependency_unavailable",
        "probe_error", "file_limit_exceeded", "unsupported_media_type",
    } or not isinstance(result.get("streams"), list):
        return {"state": "probe_error", "error_type": "ProbeOutputInvalid", "streams": []}
    return result


def analyze_video_evidence(path: str, content_type: str, expected_sha256: str) -> dict:
    original = Path(path)
    digest, size = _sha256_file(original)
    if digest != expected_sha256:
        raise ValueError("Original evidence hash changed before video analysis")
    if content_type not in DEMUXERS:
        probe = {"state": "unsupported_media_type", "streams": []}
    elif size > MAX_VIDEO_BYTES:
        probe = {"state": "file_limit_exceeded", "streams": []}
    else:
        probe = _probe(original, content_type)
        if _sha256_file(original)[0] != expected_sha256:
            raise ValueError("Original evidence hash changed during video analysis")
    state = probe["state"]
    status = (
        "supported" if state == "parsed" else
        "inconclusive" if state == "metadata_incomplete" else
        "error" if state == "probe_error" else "unsupported"
    )
    return {
        "pipeline_version": VIDEO_PIPELINE_VERSION,
        "decision": "manual_review", "classification": "Unknown",
        "confidence": 0.0, "needs_review": True,
        "model_usage": {"cost": 0.0, "calls": 0},
        "task_results": [
            {
                "task": "video_structure", "status": status,
                "finding": "undetermined", "state": state,
                "evidence": {"asset_sha256": digest, "file_bytes": size, **probe},
                "coverage": {
                    "stream_metadata_read": state in {"parsed", "metadata_incomplete",
                                                      "duration_limit_exceeded", "no_video_stream"},
                    "streams_reported": len(probe.get("streams", [])),
                    "duration_reported_seconds": probe.get("duration_seconds"),
                    "frames_decoded": 0, "runtime_inspected_seconds": 0,
                    "audio_content_inspected": False,
                },
                "calibrated_score": None, "policy_version": VIDEO_POLICY_VERSION,
                "limitations": (
                    "Container and stream metadata are untrusted structural hints. "
                    "No frames, audio samples, scenes, or timestamps were decoded or inspected. "
                    "A low frame rate, missing duration, or missing audio is not fraud evidence."
                ),
            },
            {
                "task": "synthetic_video", "status": "inconclusive",
                "finding": "undetermined", "state": "not_checked",
                "evidence": [], "coverage": {"frames_inspected": 0, "runtime_inspected_seconds": 0},
                "calibrated_score": None, "policy_version": VIDEO_POLICY_VERSION,
                "limitations": "No generated-video detector or scene-aware sampling ran.",
            },
            {
                "task": "face_manipulation", "status": "inconclusive",
                "finding": "undetermined", "state": "not_checked",
                "evidence": [], "coverage": {"face_tracks_inspected": 0},
                "calibrated_score": None, "policy_version": VIDEO_POLICY_VERSION,
                "limitations": "No face tracks or face-manipulation detector ran.",
            },
        ],
    }
