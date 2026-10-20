"""Bounded scene scan and ephemeral frame extraction in a credential-free child."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from backend.video_probe import DEMUXERS, probe as structure_probe

MAX_DURATION_SECONDS = 20
MAX_SOURCE_EDGE = 1920
MAX_SOURCE_FPS = 60
SCAN_FPS = 6
SCENE_THRESHOLD = 0.3
MAX_SCENE_EVENTS = 100
MAX_SCENE_SAMPLES = 3
MAX_SAMPLE_FRAMES = 6
MAX_FRAME_EDGE = 640
MAX_FRAME_BYTES = 2 * 1024 * 1024
SCAN_TIMEOUT_SECONDS = 25
FRAME_TIMEOUT_SECONDS = 6
SHOWINFO_TIME = re.compile(
    r"^\[Parsed_showinfo_\d+ @ [^\]]+\] n:\s*\d+\s+pts:\s*-?\d+\s+"
    r"pts_time:(-?\d+(?:\.\d+)?)"
)


def _set_limits() -> None:
    if sys.platform != "win32":
        import resource

        memory = 768 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FRAME_BYTES, MAX_FRAME_BYTES))
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))


def _base() -> list[str]:
    return ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "info", "-xerror",
            "-filter_threads", "1",
            "-protocol_whitelist", "file", "-probesize", "5000000",
            "-analyzeduration", "5000000"]


def _start_time(path: Path, demuxer: str) -> float | None:
    process = subprocess.run(
        ["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-f", demuxer,
         "-i", str(path), "-show_entries", "format=start_time", "-of", "json"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=5, check=False,
    )
    if process.returncode != 0 or len(process.stdout) > 4096:
        return None
    try:
        value = float(json.loads(process.stdout)["format"]["start_time"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _times(stderr: bytes, duration_ms: int) -> list[int]:
    times = []
    for line in stderr.decode("utf-8", "replace").splitlines():
        if not (match := SHOWINFO_TIME.search(line)):
            continue
        value = float(match.group(1))
        if math.isfinite(value) and 0 <= value * 1000 <= duration_ms + 500:
            millis = round(value * 1000)
            if not times or millis - times[-1] >= 100:
                times.append(millis)
    return times


def _scene_scan(path: Path, demuxer: str, duration_ms: int) -> tuple[list[int], bool, str | None]:
    command = _base() + [
        "-t", f"{duration_ms / 1000 + 0.25:.3f}", "-f", demuxer,
        "-threads:v", "1", "-i", str(path),
        "-map", "0:v:0", "-an", "-sn", "-dn",
        "-vf", f"fps={SCAN_FPS},scale=320:-2,select=gt(scene\\,{SCENE_THRESHOLD}),showinfo",
        "-fps_mode", "vfr", "-f", "null", "-",
    ]
    try:
        process = subprocess.run(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, timeout=SCAN_TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        return [], False, "TimeoutExpired"
    if process.returncode != 0 or len(process.stderr) > 256 * 1024:
        return [], False, "SceneScanFailed"
    events = _times(process.stderr, duration_ms)
    if len(events) > MAX_SCENE_EVENTS:
        return events[:MAX_SCENE_EVENTS], False, "SceneEventLimitExceeded"
    return events, True, None


def _plan(duration_ms: int, events: list[int]) -> list[dict]:
    planned = [{"requested_ms": round(duration_ms * fraction), "reasons": ["anchor"]}
               for fraction in (0.1, 0.5, 0.9)]
    if events:
        count = min(len(events), MAX_SCENE_SAMPLES)
        indices = ([0] if count == 1 else
                   [round(index * (len(events) - 1) / (count - 1)) for index in range(count)])
        for index in indices:
            event = events[index]
            nearest = min(planned, key=lambda item: abs(item["requested_ms"] - event))
            if abs(nearest["requested_ms"] - event) <= 250:
                if "scene_cut" not in nearest["reasons"]:
                    nearest["reasons"].append("scene_cut")
            else:
                planned.append({"requested_ms": event, "reasons": ["scene_cut"]})
    return sorted(planned[:MAX_SAMPLE_FRAMES], key=lambda item: item["requested_ms"])


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError("Invalid extracted PNG")
    width, height = struct.unpack(">II", header[16:24])
    if not 1 <= width <= MAX_FRAME_EDGE or not 1 <= height <= MAX_FRAME_EDGE:
        raise ValueError("Extracted frame exceeded pixel limit")
    return width, height


def _frame(path: Path, demuxer: str, request: dict, directory: Path,
           duration_ms: int, stream_index: int) -> dict:
    target = directory / f"frame-{request['requested_ms']}.png"
    command = _base() + [
        "-copyts", "-ss", f"{request['requested_ms'] / 1000:.3f}",
        "-t", "1.000", "-f", demuxer, "-threads:v", "1", "-i", str(path),
        "-map", "0:v:0", "-an", "-sn", "-dn", "-frames:v", "1",
        "-vf", f"showinfo,scale={MAX_FRAME_EDGE}:-2", "-fps_mode", "vfr",
        "-threads:v", "1", "-f", "image2", "-update", "1",
        "-vcodec", "png", "-y", str(target),
    ]
    try:
        process = subprocess.run(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, timeout=FRAME_TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        return {**request, "state": "decode_error", "error_type": "TimeoutExpired"}
    if process.returncode != 0 or len(process.stderr) > 64 * 1024 or not target.is_file():
        return {**request, "state": "decode_error", "error_type": "FrameExtractionFailed"}
    if target.stat().st_size > MAX_FRAME_BYTES:
        return {**request, "state": "decode_error", "error_type": "FrameOutputLimitExceeded"}
    times = _times(process.stderr, duration_ms)
    if not times or abs(times[0] - request["requested_ms"]) > 1000:
        return {**request, "state": "decode_error", "error_type": "FrameTimestampInvalid"}
    try:
        width, height = _png_size(target)
    except ValueError:
        return {**request, "state": "decode_error", "error_type": "FrameOutputInvalid"}
    return {
        **request, "state": "read", "timestamp_ms": times[0],
        "frame_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "image_size_px": [width, height], "source_stream_index": stream_index,
        "preprocessing": {"format": "png", "max_edge_px": MAX_FRAME_EDGE,
                          "seek_mode": "accurate_copyts"},
    }


def _version() -> str | None:
    try:
        process = subprocess.run(
            ["ffmpeg", "-version"], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=3, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = process.stdout.decode("ascii", "ignore").splitlines()
    return lines[0][:80] if process.returncode == 0 and lines else None


def probe(path: Path, content_type: str) -> dict:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        return {"state": "dependency_unavailable", "frames": []}
    structure = structure_probe(path, content_type)
    if structure["state"] != "parsed":
        return {"state": "structure_unavailable", "structure_state": structure["state"],
                "frames": []}
    video = next(item for item in structure["streams"] if item["type"] == "video")
    if video["index"] is None:
        return {"state": "structure_unavailable", "structure_state": "stream_index_missing",
                "frames": []}
    duration = structure["duration_seconds"]
    if (duration < 1 or duration > MAX_DURATION_SECONDS or
            video["width_px"] > MAX_SOURCE_EDGE or video["height_px"] > MAX_SOURCE_EDGE or
            video["avg_frame_rate_fps"] > MAX_SOURCE_FPS):
        return {"state": "sampling_limit_exceeded", "frames": [],
                "duration_seconds": duration}
    demuxer = DEMUXERS[content_type]
    start = _start_time(path, demuxer)
    if start is None or abs(start) > 0.05:
        return {"state": "start_time_unsupported", "frames": []}
    duration_ms = round(duration * 1000)
    events, scan_complete, scan_error = _scene_scan(path, demuxer, duration_ms)
    planned = _plan(duration_ms, events)
    with tempfile.TemporaryDirectory(prefix="video-samples-") as temporary:
        frames = [_frame(path, demuxer, item, Path(temporary), duration_ms,
                         video["index"])
                  for item in planned]
    read = sum(item["state"] == "read" for item in frames)
    return {
        "state": "read" if scan_complete and read == len(frames) else "partial",
        "frames": frames, "scene_candidates_ms": events,
        "coverage": {
            "duration_total_ms": duration_ms, "scene_scan_complete": scan_complete,
            "scene_scan_fps": SCAN_FPS, "scene_scan_error_type": scan_error,
            "scene_events_detected": len(events),
            "requested_count": len(planned), "frames_read": read,
            "failed_requested_ms": [item["requested_ms"] for item in frames
                                    if item["state"] != "read"],
            "frames_retained": 0, "model_frames_inspected": 0,
            "audio_content_inspected": False,
        },
        "ffmpeg_version": _version(),
        "scene_threshold": SCENE_THRESHOLD,
        "source_start_time_seconds": start,
    }


def main() -> None:
    _set_limits()
    try:
        result = probe(Path(sys.argv[1]), sys.argv[2])
    except Exception as error:
        result = {"state": "probe_error", "error_type": type(error).__name__,
                  "frames": []}
    sys.stdout.write(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
