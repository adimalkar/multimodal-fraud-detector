# Phase 4a: bounded video structure evidence

Status: opt-in `video-evidence-v1` on the durable backend. This is the first video-specific path and has no AI-generated or fraud classification capability.

## What runs

The worker verifies the private original's SHA-256, then starts a credential-free child process to inspect container and stream metadata with FFprobe. The child forces the expected local demuxer for MP4/MOV, AVI, or Matroska/WebM and permits only the local file protocol. It requests selected JSON fields: container family, duration, stream type/codec, video dimensions, frame rate, rotation, and whether audio streams exist. It does not return filenames, user metadata tags, frame pixels, or audio content. The [FFprobe documentation](https://www.ffmpeg.org/ffprobe.html) describes its JSON and selected-entry interfaces.

The path accepts at most 50 MiB and reports videos over 120 seconds as unsupported for this phase. It caps FFprobe input analysis at 5 MiB and 5 seconds, output at 64 KiB, stream count at 16, and dimensions at 8,192 pixels per edge. The child has a 512 MiB address-space limit, a 12 CPU-second limit, and a 10-second FFprobe command timeout; the parent has a 20-second wall timeout and kills the child process group on expiry. A malformed or unparseable container produces a typed error. Missing FFprobe, missing/invalid duration or frame rate, multiple video streams, absent video, and limit breaches have explicit states. Reported metadata remains untrusted and incomplete for some containers.

The `video_structure` task reports the original hash, sanitized stream observations, and coverage. It always records **zero decoded frames and zero inspected runtime**. `synthetic_video` and `face_manipulation` tasks explicitly say `not_checked`; audio content is also not inspected. A low frame rate, missing audio, metadata value, or parser failure cannot establish manipulation. The top-level result stays `manual_review`, `Unknown`, no calibrated score, and zero model calls.

## Rollout

Deploy a v1-capable worker with FFprobe before setting `VIDEO_EVIDENCE_PIPELINE_ENABLED=1` on the web service. New video jobs store `video-evidence-v1` and use internal `queued_video_v1`; older workers cannot claim them. Public API status remains `queued`. Keep the flag off until the durable backend's authenticated intake, PostgreSQL, private storage and separate worker are active. The existing provider-based video path remains the default when the flag is off.

## Verification and next milestone

Real short video fixtures cover container, video and audio streams, duration limits, malformed media, missing FFprobe, secret-free child launch, queue versioning, retry, idempotency, and zero billed model calls. These tests establish structural plumbing, not detection accuracy. Next, add bounded scene-aware frame sampling with timestamps, decode-gap coverage and derived-artifact lineage. Candidate video/face detectors and any policy still require rights-cleared held-out evaluation and separate false-positive gates.
