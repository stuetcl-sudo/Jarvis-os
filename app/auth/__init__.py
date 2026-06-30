"""Local authentication, sessions, CSRF and role enforcement."""

from app.auth.service import auth_service

__all__ = ["auth_service"]
