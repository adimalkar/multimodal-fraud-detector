"""Resource-limited, credential-free ffprobe child for video structure evidence."""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

MAX_VIDEO_BYTES = 50 * 1024 * 1024
MAX_DURATION_SECONDS = 120
MAX_STREAMS = 16
MAX_EDGE_PX = 8192
COMMAND_TIMEOUT_SECONDS = 10
DEMUXERS = {
    "video/mp4": "mov", "video/quicktime": "mov",
    "video/x-msvideo": "avi", "video/x-matroska": "matroska",
    "video/webm": "matroska",
}
FORMAT_FAMILIES = {
    "mov": {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"},
    "avi": {"avi"}, "matroska": {"matroska", "webm"},
}
SAFE_CODEC = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")


def _set_limits() -> None:
    if sys.platform != "win32":
        import resource

        memory = 512 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))


def _number(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _fps(value: object) -> float | None:
    try:
        result = float(Fraction(str(value)))
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        return None
    return round(result, 3) if math.isfinite(result) and 0 < result <= 240 else None


def _rotation(stream: dict) -> int | None:
    values = [stream.get("tags", {}).get("rotate")]
    values.extend(item.get("rotation") for item in stream.get("side_data_list", []))
    for value in values:
        try:
            angle = int(value) % 360
        except (TypeError, ValueError, OverflowError):
            continue
        if angle in {0, 90, 180, 270}:
            return angle
    return None


def _stream_summary(stream: dict) -> dict:
    kind = stream.get("codec_type")
    codec = stream.get("codec_name")
    item = {
        "index": stream.get("index") if isinstance(stream.get("index"), int) else None,
        "type": kind if kind in {"video", "audio", "subtitle", "data", "attachment"} else "other",
        "codec": codec if isinstance(codec, str) and SAFE_CODEC.fullmatch(codec) else None,
    }
    if kind == "video":
        width, height = stream.get("width"), stream.get("height")
        item.update({
            "width_px": width if isinstance(width, int) and 0 < width <= MAX_EDGE_PX else None,
            "height_px": height if isinstance(height, int) and 0 < height <= MAX_EDGE_PX else None,
            "avg_frame_rate_fps": _fps(stream.get("avg_frame_rate")),
            "rotation_degrees": _rotation(stream),
            "duration_seconds": _number(stream.get("duration")),
        })
    return item


def _version() -> str | None:
    try:
        process = subprocess.run(
            ["ffprobe", "-version"], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=3, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = process.stdout.decode("ascii", "ignore").splitlines()
    return lines[0][:80] if process.returncode == 0 and lines else None


def probe(path: Path, content_type: str) -> dict:
    demuxer = DEMUXERS.get(content_type)
    if demuxer is None:
        return {"state": "unsupported_media_type", "streams": []}
    if path.stat().st_size > MAX_VIDEO_BYTES:
        return {"state": "file_limit_exceeded", "streams": []}
    if not shutil.which("ffprobe"):
        return {"state": "dependency_unavailable", "streams": []}
    command = [
        "ffprobe", "-v", "error", "-protocol_whitelist", "file",
        "-probesize", "5000000", "-analyzeduration", "5000000",
        "-f", demuxer, "-i", str(path),
        "-show_entries", "format=format_name,duration:stream=index,codec_type,codec_name,"
        "width,height,avg_frame_rate,duration:stream_tags=rotate:stream_side_data=rotation",
        "-of", "json",
    ]
    try:
        process = subprocess.run(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=COMMAND_TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"state": "probe_error", "error_type": "TimeoutExpired", "streams": []}
    if process.returncode != 0 or len(process.stdout) > 64 * 1024:
        return {"state": "probe_error", "error_type": "ProbeFailed", "streams": []}
    try:
        data = json.loads(process.stdout)
    except (ValueError, UnicodeDecodeError):
        return {"state": "probe_error", "error_type": "ProbeOutputInvalid", "streams": []}
    raw_streams = data.get("streams", [])
    if not isinstance(raw_streams, list) or any(not isinstance(item, dict) for item in raw_streams):
        return {"state": "probe_error", "error_type": "ProbeOutputInvalid", "streams": []}
    if len(raw_streams) > MAX_STREAMS:
        return {"state": "stream_limit_exceeded", "stream_count": len(raw_streams),
                "streams": []}
    format_info = data.get("format", {})
    format_names = set(str(format_info.get("format_name", "")).split(","))
    if not format_names.intersection(FORMAT_FAMILIES[demuxer]):
        return {"state": "unsupported_container", "streams": []}
    streams = [_stream_summary(item) for item in raw_streams]
    video_streams = [item for item in streams if item["type"] == "video"]
    duration = _number(format_info.get("duration"))
    if duration is None and len(video_streams) == 1:
        duration = video_streams[0]["duration_seconds"]
    if not video_streams:
        state = "no_video_stream"
    elif duration is not None and duration > MAX_DURATION_SECONDS:
        state = "duration_limit_exceeded"
    elif (len(video_streams) != 1 or duration is None
          or any(item["width_px"] is None or item["height_px"] is None
                 or item["avg_frame_rate_fps"] is None for item in video_streams)):
        state = "metadata_incomplete"
    else:
        state = "parsed"
    return {
        "state": state, "container": demuxer, "duration_seconds": duration,
        "streams": streams, "stream_count": len(streams),
        "video_stream_count": len(video_streams),
        "audio_stream_count": sum(item["type"] == "audio" for item in streams),
        "ffprobe_version": _version(),
    }


def main() -> None:
    _set_limits()
    try:
        result = probe(Path(sys.argv[1]), sys.argv[2])
    except Exception as error:
        result = {"state": "probe_error", "error_type": type(error).__name__,
                  "streams": []}
    sys.stdout.write(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
