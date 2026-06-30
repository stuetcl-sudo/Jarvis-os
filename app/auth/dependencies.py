from fastapi import Depends, HTTPException, Request

from app.auth.service import SESSION_COOKIE_NAME, auth_service


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
