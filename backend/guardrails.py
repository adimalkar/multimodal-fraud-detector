import os
import time
from typing import Dict, List, Tuple, Optional
from fastapi import HTTPException, Request, UploadFile

# Environment configurations with sensible free-tier defaults
MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", "50"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_BATCH_SIZE = int(os.environ.get("MAX_BATCH_SIZE", "10"))
DEFAULT_RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "60"))

# Allowed file extensions for multimodal analysis
ALLOWED_EXTENSIONS = {
    # Images
    "jpg", "jpeg", "png", "webp",
    # Documents
    "pdf",
    # Video
    "mp4", "avi", "mov", "mkv", "webm"
}

ALLOWED_MIME_PREFIXES = ("image/", "video/", "application/pdf")


class InMemoryRateLimiter:
    """
    Lightweight in-memory sliding window rate limiter designed for free-tier deployments.
    Does not require Redis or external state stores.
    Automatically purges expired client windows to prevent memory leaks.
    """

    def __init__(self, default_limit: int = DEFAULT_RATE_LIMIT, window_seconds: int = 60):
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        # client_ip -> list of timestamps
        self._requests: Dict[str, List[float]] = {}
        self._last_cleanup = time.time()

    def _cleanup_old_records(self, now: float):
        """Purge entries older than the window to keep memory flat."""
        if now - self._last_cleanup < 60:
            return
        cutoff = now - self.window_seconds
        stale_ips = []
        for ip, timestamps in self._requests.items():
            valid_ts = [t for t in timestamps if t > cutoff]
            if not valid_ts:
                stale_ips.append(ip)
            else:
                self._requests[ip] = valid_ts
        for ip in stale_ips:
            self._requests.pop(ip, None)
        self._last_cleanup = now

    def check(self, client_id: str, limit: Optional[int] = None) -> Tuple[bool, int, int]:
        """
        Checks if the request is permitted.
        Returns: (is_allowed, remaining_requests, retry_after_seconds)
        """
        now = time.time()
        self._cleanup_old_records(now)

        limit_to_use = limit if limit is not None else self.default_limit
        cutoff = now - self.window_seconds

        timestamps = self._requests.get(client_id, [])
        # Filter timestamps within current window
        valid_ts = [t for t in timestamps if t > cutoff]

        if len(valid_ts) >= limit_to_use:
            # Rate limit exceeded
            oldest_in_window = valid_ts[0]
            retry_after = max(1, int(self.window_seconds - (now - oldest_in_window)))
            self._requests[client_id] = valid_ts
            return False, 0, retry_after

        # Record new request
        valid_ts.append(now)
        self._requests[client_id] = valid_ts
        remaining = max(0, limit_to_use - len(valid_ts))
        return True, remaining, 0

    def reset(self):
        """Clears all tracked requests (useful in tests)."""
        self._requests.clear()


# Global rate limiter instance
rate_limiter = InMemoryRateLimiter()


def get_client_ip(request: Request) -> str:
    """Extracts client IP from proxy headers (Cloudflare, Vercel, Render) or direct connection."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First IP in list is original client
        return forwarded.split(",")[0].strip()
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def enforce_rate_limit(request: Request, limit: Optional[int] = None):
    """
    Enforces in-memory rate limiting. Raises HTTP 429 if threshold is exceeded.
    """
    client_ip = get_client_ip(request)
    allowed, remaining, retry_after = rate_limiter.check(client_ip, limit=limit)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Please wait {retry_after} seconds before retrying.",
            headers={"Retry-After": str(retry_after), "X-RateLimit-Remaining": "0"}
        )


def validate_file_extension(filename: str) -> str:
    """
    Validates file extension against allowed formats.
    Returns the lowercased extension or raises HTTP 415.
    """
    if not filename or "." not in filename:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file format. Missing file extension. Supported formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '.{ext}'. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    return ext


def validate_file_size(file: UploadFile):
    """
    Validates that uploaded file size does not exceed free-tier container memory limit.
    Raises HTTP 413 if file is larger than MAX_FILE_SIZE_BYTES.
    """
    try:
        file.file.seek(0, 2)  # Seek to end
        size = file.file.tell()
        file.file.seek(0)  # Rewind to start
        if size > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File '{file.filename}' exceeds maximum allowed size of {MAX_FILE_SIZE_MB}MB ({round(size / (1024 * 1024), 2)}MB detected)."
            )
    except HTTPException:
        raise
    except Exception:
        # In case underlying file object doesn't support seek, proceed gracefully
        pass


def validate_batch_size(files: List[UploadFile]):
    """
    Validates that a batch upload doesn't exceed the safe sequential processing limit.
    """
    if not files or len(files) == 0:
        raise HTTPException(status_code=400, detail="No files provided in batch upload.")
    if len(files) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Batch size of {len(files)} exceeds maximum limit of {MAX_BATCH_SIZE} files per batch."
        )
