# Phase 4b1: bounded scene-aware video sampling

Status: opt-in `video-evidence-v2`, stacked after [video structure evidence](PHASE4_VIDEO_STRUCTURE_EVIDENCE.md). Previously queued v1 jobs keep their version and result.

## What runs

The worker verifies the original SHA-256, runs v1 structural inspection, then launches a separate credential-free FFmpeg child. For a single video stream with a known zero-based start time, a clip of 1–20 seconds, at most 1,920 pixels per edge and at most 60 reported FPS, it scans the timeline at six frames per second and 320 pixels wide for candidate scene cuts. It plans three time anchors plus up to three cuts, merging nearby positions. It accurately seeks and decodes at most six requested frames, scaling each to at most 640 pixels and hashing the temporary PNG. FFmpeg's [scene selection and `showinfo` filters](https://www.ffmpeg.org/ffmpeg-filters.html) and [accurate seeking with `-ss` and `-copyts`](https://www.ffmpeg.org/ffmpeg.html) provide the timestamps. The result records both requested offset and decoded source PTS, original and frame hashes, pixel dimensions, selection reason, and transformation settings. Temporary images are deleted when the child exits.

The child permits only the local file protocol, caps scene-log output at 256 KiB and per-frame logs at 64 KiB, caps each PNG at 2 MiB, and has a 768 MiB address-space limit, 30 CPU-second limit and 70-second parent wall timeout. The scene command has a 25-second timeout; each frame command has a six-second timeout. Decoder errors abort the scene scan where FFmpeg reports them. Any failed requested frame is listed with a typed error and requested position. An incomplete scan or failed sample makes the sampling task inconclusive. `scene_scan_complete` means the bounded six-FPS scan finished; it does **not** mean every source frame decoded correctly or that short edits were found.

The top-level disposition remains `manual_review`, classification `Unknown`, and zero model calls. `synthetic_video` and `face_manipulation` stay `not_checked`; no audio samples or face tracks are analyzed. Frame hashes are evidence lineage, not an authenticity score. A successful scan and six frames cannot establish that the rest of the video is real or generated. The original remains private, and no derived image is retained in the result store.

## Rollout

Deploy a v2-capable worker before setting `VIDEO_SAMPLING_PIPELINE_ENABLED=1` alongside `VIDEO_EVIDENCE_PIPELINE_ENABLED=1` on the web service. New video jobs use `video-evidence-v2` and internal `queued_video_v2`; public status remains `queued`. Keep the flags off for public traffic until the durable backend's authentication, PostgreSQL, private storage and separate worker are verified. The v1 path remains available when the sampling flag is off.

## Verification and next gate

Controlled hard-cut and steady clips verify scene positions, anchors, decoded PTS, hashes and pixel limits. Tests also cover scan/sample failures, over-budget duration, queue versioning, idempotency and zero model billing. These fixtures establish extraction plumbing, not scene-detection recall. Before expanding the clip/frame budget or adding a detector, benchmark short inserted edits, variable frame rate, rotation, corruption, re-encodes and real-world camera clips. Measure missed scenes, decode failures, coverage, p95 latency and cost; then separately evaluate generated-video and face-manipulation candidates on rights-cleared, held-out data.
