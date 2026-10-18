"""Sign in with Google and per-user sessions.

The browser gets a Google ID token from Google Identity Services and posts it here. We verify it against Google's
keys and our client ID, upsert the user and set an HttpOnly session cookie. The cookie holds a random token; only its
SHA-256 is stored. Only the OAuth client ID is needed: no client secret.

Modes (mode()):
  google - GOOGLE_CLIENT_ID is set: everyone signs in and sees only their own projects.
  dev    - no client ID and the app runs on localhost (or GLR_AUTH=dev): one built-in "local" user, no sign-in.
  off    - no client ID on a public host: sign-in is refused instead of silently sharing one account.
"""

import asyncio
import hashlib
import secrets
from urllib.parse import urlparse

from fastapi import HTTPException, Request, Response
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from . import db
from .config import settings

COOKIE = "glr_session"
SESSION_TTL_S = 30 * 24 * 3600
LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_google_request = google_requests.Request()


def mode() -> str:
    if settings.google_client_id:
        return "google"
    host = urlparse(settings.public_base_url).hostname or ""
    if settings.auth_mode == "dev" or host in LOOPBACK:
        return "dev"
    return "off"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public_config(user: dict | None) -> dict:
    return {"mode": mode(), "google_client_id": settings.google_client_id or None, "user": user}


def optional_user(request: Request) -> dict | None:
    """FastAPI dependency: the signed-in user, or None."""
    m = mode()
    if m == "dev":
        # Only for requests from this machine (Vite proxy, make serve), so a misconfigured public deploy
        # never hands every visitor the local account.
        return db.ensure_local_user() if request.client and request.client.host in LOOPBACK else None
    if m == "google" and (token := request.cookies.get(COOKIE)):
        return db.session_user(_hash(token))
    return None


def require_user(request: Request) -> dict:
    """FastAPI dependency: the signed-in user, or 401."""
    if user := optional_user(request):
        return user
    if mode() == "off":
        raise HTTPException(503, "Sign-in is not configured on this server (set GOOGLE_CLIENT_ID).")
    raise HTTPException(401, "Sign in with Google first.")


def allowed(email: str) -> bool:
    """GLR_ALLOWED_EMAILS: exact emails or @domain entries. Empty = any verified Google account."""
    rules = {e.strip().lower() for e in settings.allowed_emails.split(",") if e.strip()}
    email = email.lower()
    return not rules or email in rules or "@" + email.split("@")[-1] in rules


def owns(user: dict | None, project: dict) -> bool:
    return user is not None and project.get("user_id") == user["id"]


async def login_with_google(credential: str, response: Response) -> dict:
    if mode() != "google":
        raise HTTPException(400, "Google sign-in is not configured (GOOGLE_CLIENT_ID is empty).")
    try:
        claims = await asyncio.to_thread(id_token.verify_oauth2_token, credential, _google_request,
                                         settings.google_client_id)
    except ValueError:
        raise HTTPException(401, "Google sign-in could not be verified. Try again.")
    if not claims.get("email") or not claims.get("email_verified"):
        raise HTTPException(401, "Your Google account has no verified email address.")
    if not allowed(claims["email"]):
        raise HTTPException(403, "This demo is invite-only. Ask the team to add your email.")
    user = db.upsert_google_user(claims["sub"], claims["email"], claims.get("name"), claims.get("picture"))
    token = secrets.token_urlsafe(32)
    db.create_session(user["id"], _hash(token), SESSION_TTL_S)
    response.set_cookie(COOKIE, token, max_age=SESSION_TTL_S, httponly=True, samesite="lax", path="/",
                        secure=settings.public_base_url.startswith("https://"))
    return user


def logout(request: Request, response: Response) -> None:
    if token := request.cookies.get(COOKIE):
        db.delete_session(_hash(token))
    response.delete_cookie(COOKIE, path="/")
