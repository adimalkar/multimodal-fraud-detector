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
VIDEO_SAMPLING_PIPELINE_VERSION = "video-evidence-v2"
VIDEO_POLICY_VERSION = "manual-review-video-v1"
VIDEO_SAMPLING_POLICY_VERSION = "manual-review-video-v2"
PROBE_TIMEOUT_SECONDS = 20
SAMPLING_PROBE_TIMEOUT_SECONDS = 70


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


def _sampling_probe(path: Path, content_type: str) -> dict:
    process = subprocess.Popen(
        [sys.executable, "-m", "backend.video_sampling_probe", str(path), content_type],
        cwd=Path(__file__).resolve().parent.parent,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env={"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONNOUSERSITE": "1",
             "OMP_THREAD_LIMIT": "1"},
        start_new_session=os.name == "posix",
    )
    try:
        output, _ = process.communicate(timeout=SAMPLING_PROBE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
        process.communicate()
        return {"state": "probe_error", "error_type": "TimeoutExpired", "frames": []}
    if process.returncode != 0 or len(output) > 128 * 1024:
        return {"state": "probe_error", "error_type": "ProbeFailed", "frames": []}
    try:
        result = json.loads(output)
    except (ValueError, UnicodeDecodeError):
        return {"state": "probe_error", "error_type": "ProbeOutputInvalid", "frames": []}
    if not isinstance(result, dict) or result.get("state") not in {
        "read", "partial", "dependency_unavailable", "structure_unavailable",
        "sampling_limit_exceeded", "start_time_unsupported", "probe_error",
    } or not isinstance(result.get("frames"), list):
        return {"state": "probe_error", "error_type": "ProbeOutputInvalid", "frames": []}
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


def analyze_video_sampling_evidence(path: str, content_type: str,
                                    expected_sha256: str) -> dict:
    """Add bounded frame lineage to v1, without a synthetic-video verdict."""
    result = analyze_video_evidence(path, content_type, expected_sha256)
    result["pipeline_version"] = VIDEO_SAMPLING_PIPELINE_VERSION
    for task in result["task_results"]:
        task["policy_version"] = VIDEO_SAMPLING_POLICY_VERSION
    structure = result["task_results"][0]
    sampling = {
        "task": "video_sampling", "status": "inconclusive",
        "finding": "undetermined", "state": "not_checked",
        "evidence": [],
        "coverage": {"duration_total_ms": None, "scene_scan_complete": False,
                     "requested_count": 0, "frames_read": 0,
                     "failed_requested_ms": [], "frames_retained": 0,
                     "model_frames_inspected": 0},
        "calibrated_score": None, "policy_version": VIDEO_SAMPLING_POLICY_VERSION,
        "limitations": (
            "At most six frames are decoded from clips of at most 20 seconds. "
            "Scene scan uses six frames per second at 320 pixels and can miss short edits. "
            "Frame hashes and timestamps are observations; no synthetic-video, face, "
            "or audio detector ran. No derived frame is retained."
        ),
    }
    result["task_results"].append(sampling)
    if structure["status"] != "supported":
        sampling["state"] = "not_checked_structure"
        return result
    sample = _sampling_probe(Path(path), content_type)
    if _sha256_file(Path(path))[0] != expected_sha256:
        raise ValueError("Original evidence hash changed during video sampling")
    state = sample["state"]
    sampling.update({
        "status": "supported" if state == "read" else
                  "unsupported" if state in {"dependency_unavailable", "sampling_limit_exceeded",
                                             "start_time_unsupported"} else
                  "error" if state == "probe_error" else "inconclusive",
        "state": state,
        "evidence": {"source_asset_sha256": expected_sha256, **sample},
    })
    sampling["coverage"].update(sample.get("coverage", {}))
    structure["coverage"]["frames_decoded"] = sampling["coverage"]["frames_read"]
    structure["limitations"] = (
        "Container metadata and sampled-frame hashes are structural observations only. "
        "Unsampled moments, audio, and face tracks were not reviewed by a detector."
    )
    return result
