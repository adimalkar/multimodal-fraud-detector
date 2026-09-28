"""Private-beta tenant token authentication for durable analysis routes."""

from __future__ import annotations

import hmac
import json
import os

from fastapi import HTTPException, Request


def configured_tokens() -> dict[str, str] | None:
    raw = os.getenv("ANALYSIS_TOKENS_JSON", "")
    try:
        tokens = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(tokens, dict) or not tokens or any(
        not isinstance(owner, str) or not owner.strip()
        or not isinstance(token, str) or len(token) < 32
        for owner, token in tokens.items()
    ):
        return None
    if len(set(tokens.values())) != len(tokens):
        return None
    return tokens


def require_tenant(request: Request) -> str:
    tokens = configured_tokens()
    if tokens is None:
        raise HTTPException(status_code=503, detail="Analysis authentication is not configured")
    authorization = request.headers.get("authorization", "")
    scheme, _, credential = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credential:
        raise HTTPException(status_code=401, detail="Bearer token required")
    for owner, token in tokens.items():
        if hmac.compare_digest(credential.encode("utf-8"), token.encode("utf-8")):
            return owner
    raise HTTPException(status_code=401, detail="Invalid bearer token")
