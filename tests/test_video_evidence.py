"""Real video-container fixtures and conservative video structure coverage."""

import hashlib
import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from backend import video_evidence, video_probe


def _video(tmp_path, *, seconds=1):
    path = tmp_path / "sample.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-threads", "1",
        "-f", "lavfi", "-i", f"color=size=96x64:rate=12:duration={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
        "-c:v", "mpeg4", "-q:v", "5", "-c:a", "aac", "-shortest",
        "-y", str(path),
    ], check=True, timeout=20)
    return path


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg system binaries unavailable")
def test_real_mp4_probe_reports_structure_without_media_verdict(tmp_path):
    path = _video(tmp_path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = video_evidence.analyze_video_evidence(str(path), "video/mp4", digest)
    structure, synthetic, face = result["task_results"]
    assert result["pipeline_version"] == "video-evidence-v1"
    assert result["decision"] == "manual_review"
    assert result["classification"] == "Unknown"
    assert result["model_usage"] == {"cost": 0.0, "calls": 0}
    assert structure["status"] == "supported"
    assert structure["finding"] == "undetermined"
    assert structure["evidence"]["asset_sha256"] == digest
    assert structure["evidence"]["audio_stream_count"] == 1
    assert structure["evidence"]["video_stream_count"] == 1
    assert structure["evidence"]["streams"][0]["width_px"] == 96
    assert structure["evidence"]["streams"][0]["avg_frame_rate_fps"] == 12
    assert structure["coverage"]["frames_decoded"] == 0
    assert structure["coverage"]["audio_content_inspected"] is False
    assert synthetic["state"] == face["state"] == "not_checked"
    assert structure["evidence"]["ffprobe_version"].startswith("ffprobe version")
    assert "filename" not in json.dumps(result)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg system binaries unavailable")
def test_duration_cap_is_typed_without_decoding_frames(tmp_path):
    path = _video(tmp_path, seconds=121)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = video_evidence.analyze_video_evidence(str(path), "video/mp4", digest)
    structure = result["task_results"][0]
    assert structure["state"] == "duration_limit_exceeded"
    assert structure["status"] == "unsupported"
    assert structure["coverage"]["frames_decoded"] == 0


@pytest.mark.skipif(not shutil.which("ffprobe"), reason="FFprobe unavailable")
def test_malformed_and_oversized_media_are_typed(tmp_path, monkeypatch):
    path = tmp_path / "bad.mp4"
    path.write_bytes(b"not a video")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    malformed = video_evidence.analyze_video_evidence(str(path), "video/mp4", digest)
    assert malformed["task_results"][0]["status"] == "error"
    assert malformed["task_results"][0]["state"] == "probe_error"

    monkeypatch.setattr(video_evidence, "MAX_VIDEO_BYTES", 4)
    oversize = video_evidence.analyze_video_evidence(str(path), "video/mp4", digest)
    assert oversize["task_results"][0]["state"] == "file_limit_exceeded"
    assert oversize["task_results"][0]["status"] == "unsupported"
    with pytest.raises(ValueError, match="hash changed"):
        video_evidence.analyze_video_evidence(str(path), "video/mp4", "0" * 64)


def test_probe_rejects_missing_binary_and_untrusted_rate(tmp_path, monkeypatch):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"small")
    monkeypatch.setattr(video_probe.shutil, "which", lambda *_: None)
    assert video_probe.probe(path, "video/mp4")["state"] == "dependency_unavailable"
    assert video_probe._fps("0/0") is None
    assert video_probe._fps("999/1") is None


def test_child_environment_excludes_provider_and_storage_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    observed = {}

    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return b'{"state":"parsed","streams":[]}', b""

    def fake_popen(*args, **kwargs):
        observed.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(video_evidence.subprocess, "Popen", fake_popen)
    assert video_evidence._probe(tmp_path / "sample.mp4", "video/mp4")["state"] == "parsed"
    assert "OPENROUTER_API_KEY" not in observed["env"]
    assert "AWS_SECRET_ACCESS_KEY" not in observed["env"]
    assert observed["start_new_session"]


def test_ffprobe_command_forces_local_container_and_omits_private_tags(tmp_path, monkeypatch):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"sample")
    commands = []
    monkeypatch.setattr(video_probe.shutil, "which", lambda *_: "/usr/bin/ffprobe")
    monkeypatch.setattr(video_probe, "_version", lambda: "ffprobe test")

    def fake_run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "streams": [{"index": 0, "codec_type": "video", "codec_name": "mpeg4",
                         "width": 96, "height": 64, "avg_frame_rate": "12/1"}],
            "format": {"format_name": "mov,mp4", "duration": "1.0",
                       "tags": {"artist": "private"}},
        }).encode())

    monkeypatch.setattr(video_probe.subprocess, "run", fake_run)
    result = video_probe.probe(path, "video/mp4")
    assert result["state"] == "parsed"
    assert "private" not in json.dumps(result)
    assert commands[0][commands[0].index("-protocol_whitelist") + 1] == "file"
    assert commands[0][commands[0].index("-f") + 1] == "mov"
    entries = commands[0][commands[0].index("-show_entries") + 1]
    assert "format_tags" not in entries and "filename" not in entries
