import hmac
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request

from app.auth.service import SESSION_COOKIE_NAME, auth_service


def safe_next_path(value):
    if not value or not isinstance(value, str):
        return None
    if not value.startswith("/") or value.startswith("//") or "\\" in value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        return None
    return value


def optional_current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    return auth_service.resolve_session(token) if token else None


def require_authenticated_user(user=Depends(optional_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_owner(user=Depends(require_authenticated_user)):
    if user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Owner role required")
    return user


def require_csrf(request: Request, user=Depends(require_authenticated_user)):
    supplied = request.headers.get("X-CSRF-Token", "")
    expected = user.get("csrf_token", "")
    if not supplied or not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="Invalid request token")
    return user


def require_owner_csrf(request: Request, user=Depends(require_owner)):
    supplied = request.headers.get("X-CSRF-Token", "")
    expected = user.get("csrf_token", "")
    if not supplied or not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="Invalid request token")
    return user
