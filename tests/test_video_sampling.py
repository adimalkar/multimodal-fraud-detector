"""Scene-aware bounded video sampling and honest coverage on controlled clips."""

import hashlib
import json
import shutil
import subprocess

import pytest

from backend import video_evidence, video_sampling_probe


def _clip(tmp_path, *, hard_cut=True, duration=4):
    path = tmp_path / "clip.mp4"
    inputs = [
        "-f", "lavfi", "-i", f"color=c=red:s=160x90:r=10:d={duration / 2 if hard_cut else duration}",
    ]
    if hard_cut:
        inputs += ["-f", "lavfi", "-i", f"color=c=blue:s=160x90:r=10:d={duration / 2}"]
    mapping = (["-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]"]
               if hard_cut else ["-map", "0:v:0"])
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-threads", "1",
        *inputs, *mapping, "-c:v", "mpeg4", "-q:v", "4", "-an", "-y", str(path),
    ], check=True, timeout=20)
    return path


def _analyze(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return video_evidence.analyze_video_sampling_evidence(str(path), "video/mp4", digest)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg system binaries unavailable")
def test_hard_cut_has_timestamped_frame_lineage_without_verdict(tmp_path):
    result = _analyze(_clip(tmp_path))
    structure, synthetic, face, sampling = result["task_results"]
    assert result["pipeline_version"] == "video-evidence-v2"
    assert result["classification"] == "Unknown"
    assert result["decision"] == "manual_review"
    assert result["model_usage"] == {"cost": 0.0, "calls": 0}
    if sampling["status"] != "supported":
        print(json.dumps(sampling, indent=2))
    assert sampling["status"] == "supported", sampling
    assert sampling["finding"] == "undetermined"
    assert sampling["coverage"]["scene_scan_complete"] is True
    assert sampling["coverage"]["frames_read"] == 3
    assert any(1900 <= event <= 2100 for event in sampling["evidence"]["scene_candidates_ms"])
    assert any("scene_cut" in frame["reasons"] for frame in sampling["evidence"]["frames"])
    assert all(frame["state"] == "read" and len(frame["frame_sha256"]) == 64
               and abs(frame["timestamp_ms"] - frame["requested_ms"]) <= 100
               and max(frame["image_size_px"]) <= 640
               and frame["source_stream_index"] == structure["evidence"]["streams"][0]["index"]
               for frame in sampling["evidence"]["frames"])
    assert sampling["evidence"]["source_asset_sha256"] == structure["evidence"]["asset_sha256"]
    assert sampling["coverage"]["frames_retained"] == 0
    assert sampling["coverage"]["model_frames_inspected"] == 0
    assert structure["coverage"]["frames_decoded"] == 3
    assert synthetic["state"] == face["state"] == "not_checked"


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg system binaries unavailable")
def test_steady_clip_keeps_anchor_coverage_and_duration_budget(tmp_path):
    steady = _analyze(_clip(tmp_path, hard_cut=False))
    sampling = steady["task_results"][-1]
    assert sampling["state"] == "read", sampling
    assert sampling["evidence"]["scene_candidates_ms"] == []
    assert sampling["coverage"]["requested_count"] == 3

    long_clip = _analyze(_clip(tmp_path, hard_cut=False, duration=22))
    sampling = long_clip["task_results"][-1]
    assert sampling["state"] == "sampling_limit_exceeded"
    assert sampling["status"] == "unsupported"
    assert sampling["coverage"]["frames_read"] == 0


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg system binaries unavailable")
def test_frame_lineage_uses_video_stream_index_when_audio_is_first(tmp_path):
    path = tmp_path / "audio-first.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-threads", "1",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-f", "lavfi", "-i", "color=c=red:s=160x90:r=10:d=2",
        "-map", "0:a:0", "-map", "1:v:0", "-c:a", "aac", "-c:v", "mpeg4",
        "-q:v", "4", "-y", str(path),
    ], check=True, timeout=20)
    result = _analyze(path)
    structure, _, _, sampling = result["task_results"]
    video = next(item for item in structure["evidence"]["streams"]
                 if item["type"] == "video")
    assert video["index"] == 1
    assert sampling["status"] == "supported", sampling
    assert all(frame["source_stream_index"] == 1
               for frame in sampling["evidence"]["frames"])


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg system binaries unavailable")
def test_scan_failure_and_decode_failure_are_visible(tmp_path, monkeypatch):
    path = _clip(tmp_path)
    monkeypatch.setattr(video_sampling_probe, "_scene_scan",
                        lambda *_: ([], False, "DecodeFailed"))
    original_frame = video_sampling_probe._frame

    def fail_middle(*args):
        if args[2]["requested_ms"] == 2000:
            return {**args[2], "state": "decode_error", "error_type": "FrameExtractionFailed"}
        return original_frame(*args)

    monkeypatch.setattr(video_sampling_probe, "_frame", fail_middle)
    result = video_sampling_probe.probe(path, "video/mp4")
    assert result["state"] == "partial"
    assert result["coverage"]["scene_scan_complete"] is False
    assert result["coverage"]["scene_scan_error_type"] == "DecodeFailed"
    assert result["coverage"]["failed_requested_ms"] == [2000]
    assert result["coverage"]["frames_read"] == 2


def test_sampling_plan_is_bounded_and_combines_nearby_cut():
    plan = video_sampling_probe._plan(4000, [2000, 2100, 2500, 2900, 3400])
    assert len(plan) <= 6
    assert any("anchor" in item["reasons"] and "scene_cut" in item["reasons"]
               for item in plan)


def test_sampling_child_has_no_provider_or_storage_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    observed = {}

    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return json.dumps({"state": "partial", "frames": []}).encode(), b""

    def fake_popen(*args, **kwargs):
        observed.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(video_evidence.subprocess, "Popen", fake_popen)
    assert video_evidence._sampling_probe(tmp_path / "clip.mp4", "video/mp4")["state"] == "partial"
    assert "OPENROUTER_API_KEY" not in observed["env"]
    assert "AWS_SECRET_ACCESS_KEY" not in observed["env"]
    assert observed["start_new_session"]
