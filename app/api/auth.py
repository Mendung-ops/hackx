"""Shared authentication dependency for dashboard mutations."""
import secrets

from fastapi import Header, HTTPException

from app.db.session import settings


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not settings.admin_token:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_TOKEN belum diatur di .env; endpoint ini dinonaktifkan",
        )
    if not x_admin_token or not secrets.compare_digest(
        x_admin_token.encode(), settings.admin_token.encode()
    ):
        raise HTTPException(status_code=401, detail="token admin salah atau tidak ada")
