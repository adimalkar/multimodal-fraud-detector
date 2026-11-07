"""Signed-in visitors from the web app.

The web app signs a short-lived HS256 token for each signed-in visitor with
WEB_AUTH_SECRET. The engine checks that token on every route that spends model
credits or shows screening history. With no secret set the engine stays open,
which keeps local development and the existing tests unchanged.
"""

from __future__ import annotations

import os

import jwt
from fastapi import HTTPException, Request

ISSUER = "fraudsight-web"
AUDIENCE = "fraudsight-engine"
MIN_SECRET_LENGTH = 32
MAX_TOKEN_LIFETIME_SECONDS = 3600
CLOCK_LEEWAY_SECONDS = 30
MAX_SUBJECT_LENGTH = 200
DEFAULT_DAILY_FILE_LIMIT = 25


def _raw_secret() -> str:
    return os.getenv("WEB_AUTH_SECRET", "").strip()


def web_auth_enabled() -> bool:
    """True once a secret is set, even a bad one, so a short secret fails closed."""
    return bool(_raw_secret())


def web_auth_state() -> str:
    secret = _raw_secret()
    if not secret:
        return "off"
    return "on" if len(secret) >= MIN_SECRET_LENGTH else "misconfigured"


def daily_file_limit() -> int:
    try:
        value = int(os.getenv("WEB_DAILY_FILE_LIMIT", str(DEFAULT_DAILY_FILE_LIMIT)))
    except ValueError:
        return DEFAULT_DAILY_FILE_LIMIT
    return max(value, 0)


def bearer_credential(request: Request) -> str:
    scheme, _, credential = request.headers.get("authorization", "").partition(" ")
    return credential.strip() if scheme.lower() == "bearer" else ""


def verify_web_token(token: str) -> str | None:
    """Return the owner id for a valid web token, or None."""
    secret = _raw_secret()
    if len(secret) < MIN_SECRET_LENGTH or not token:
        return None
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience=AUDIENCE,
            issuer=ISSUER,
            leeway=CLOCK_LEEWAY_SECONDS,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError:
        return None
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip() or len(subject) > MAX_SUBJECT_LENGTH:
        return None
    try:
        lifetime = float(claims["exp"]) - float(claims["iat"])
    except (TypeError, ValueError):
        return None
    if lifetime <= 0 or lifetime > MAX_TOKEN_LIFETIME_SECONDS:
        return None
    return f"web:{subject}"


def require_user(request: Request) -> str | None:
    """Return the signed-in owner, or None when sign-in is switched off."""
    state = web_auth_state()
    if state == "off":
        return None
    if state == "misconfigured":
        raise HTTPException(status_code=503, detail="Sign-in is misconfigured on the engine")
    owner = verify_web_token(bearer_credential(request))
    if owner is None:
        raise HTTPException(status_code=401, detail="Sign in to use the screening engine")
    return owner
