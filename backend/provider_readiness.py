"""Check provider authentication without making billable model requests."""

import threading
import time

import requests

try:
    from backend.qwen_agent import OPENROUTER_API_KEY
except ImportError:
    from qwen_agent import OPENROUTER_API_KEY


AUTH_CHECKS = {
    "openrouter": ("https://openrouter.ai/api/v1/key", OPENROUTER_API_KEY),
}
AUTH_CACHE_SECONDS = 60
_cache = {"expires_at": 0.0, "result": None}
_cache_lock = threading.Lock()


def verify_provider_authentication():
    """Return provider auth states; never include key values or response bodies."""
    with _cache_lock:
        now = time.monotonic()
        if _cache["result"] is not None and now < _cache["expires_at"]:
            return _cache["result"].copy()

        result = {}
        for provider, (url, key) in AUTH_CHECKS.items():
            if not key:
                result[provider] = {"status": "unconfigured", "http_status": None}
                continue
            try:
                response = requests.get(
                    url,
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=5,
                )
            except requests.RequestException:
                result[provider] = {"status": "unavailable", "http_status": None}
                continue

            if response.status_code == 200:
                status = "authenticated"
            elif response.status_code in {401, 403}:
                status = "rejected"
            else:
                status = "unavailable"
            result[provider] = {"status": status, "http_status": response.status_code}

        _cache["result"] = result
        _cache["expires_at"] = time.monotonic() + AUTH_CACHE_SECONDS
        return result.copy()
