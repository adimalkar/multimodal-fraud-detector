"""Private immutable original-byte storage for durable jobs."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import uuid
from pathlib import Path

from fastapi import HTTPException

from backend import storage
from backend.guardrails import MAX_FILE_SIZE_BYTES


def _matches_signature(filename: str, head: bytes) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext in {"jpg", "jpeg"}:
        return head.startswith(b"\xff\xd8\xff")
    if ext == "png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == "webp":
        return head.startswith(b"RIFF") and head[8:12] == b"WEBP"
    if ext == "pdf":
        return head.startswith(b"%PDF-")
    if ext in {"mp4", "mov"}:
        return head[4:8] == b"ftyp"
    if ext == "avi":
        return head.startswith(b"RIFF") and head[8:12] == b"AVI "
    if ext in {"mkv", "webm"}:
        return head.startswith(b"\x1a\x45\xdf\xa3")
    return False


class EvidenceArtifactStore:
    def __init__(self, backend: str | None = None, local_dir: str | None = None):
        self.backend = backend or os.getenv("DURABLE_ARTIFACT_BACKEND", "local")
        self.local_dir = Path(local_dir or os.getenv("DURABLE_ARTIFACT_DIR", "temp_uploads/durable"))
        if self.backend not in {"local", "s3"}:
            raise ValueError("DURABLE_ARTIFACT_BACKEND must be local or s3")
        if self.backend == "s3" and not storage.is_storage_configured():
            raise ValueError("S3/R2 credentials are required for durable object storage")
        if self.backend == "local":
            self.local_dir.mkdir(parents=True, exist_ok=True)

    def put_upload(self, file, filename: str) -> tuple[str, str, int]:
        suffix = Path(filename).suffix.lower()
        key = f"evidence/{uuid.uuid4().hex}{suffix}"
        digest = hashlib.sha256()
        total = 0
        head = b""
        temporary_dir = self.local_dir if self.backend == "local" else None
        with tempfile.NamedTemporaryFile(delete=False, dir=temporary_dir) as output:
            temporary = Path(output.name)
            try:
                file.seek(0)
                while chunk := file.read(64 * 1024):
                    total += len(chunk)
                    if total > MAX_FILE_SIZE_BYTES:
                        raise HTTPException(status_code=413, detail="Evidence exceeds file size limit")
                    if len(head) < 16:
                        head += chunk[:16 - len(head)]
                    digest.update(chunk)
                    output.write(chunk)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
        try:
            if total == 0 or not _matches_signature(filename, head):
                raise HTTPException(status_code=415, detail="Evidence bytes do not match file type")
            if self.backend == "s3":
                storage.get_s3_client().upload_file(
                    str(temporary), storage.S3_BUCKET_NAME, key,
                    ExtraArgs={"ContentType": "application/octet-stream"},
                )
            else:
                destination = self.local_dir / key.split("/", 1)[1]
                os.replace(temporary, destination)
            return key, digest.hexdigest(), total
        finally:
            temporary.unlink(missing_ok=True)

    def materialize(self, key: str, expected_sha256: str) -> Path:
        if not self._valid_key(key):
            raise ValueError("Invalid evidence key")
        if self.backend == "local":
            path = self.local_dir / key.split("/", 1)[1]
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(key).suffix) as output:
                path = Path(output.name)
            try:
                storage.get_s3_client().download_file(storage.S3_BUCKET_NAME, key, str(path))
            except Exception:
                path.unlink(missing_ok=True)
                raise
        hasher = hashlib.sha256()
        with path.open("rb") as evidence:
            while chunk := evidence.read(64 * 1024):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        if digest != expected_sha256:
            if self.backend == "s3":
                path.unlink(missing_ok=True)
            raise ValueError("Stored evidence hash mismatch")
        return path

    def release_materialized(self, path: Path):
        if self.backend == "s3":
            path.unlink(missing_ok=True)

    def delete(self, key: str):
        if not self._valid_key(key):
            raise ValueError("Invalid evidence key")
        if self.backend == "s3":
            storage.get_s3_client().delete_object(Bucket=storage.S3_BUCKET_NAME, Key=key)
        else:
            (self.local_dir / key.split("/", 1)[1]).unlink(missing_ok=True)

    @staticmethod
    def _valid_key(key: str) -> bool:
        return bool(re.fullmatch(
            r"evidence/[0-9a-f]{32}\.(?:jpg|jpeg|png|webp|pdf|mp4|avi|mov|mkv|webm)", key
        ))
