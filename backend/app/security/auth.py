"""Autenticación y autorización FastAPI (F2.4b, endurecido en Rev 12).

**Fail-closed:** si no hay usuarios configurados, el acceso anónimo (admin) solo se
concede con `IIOT_ALLOW_ANONYMOUS=true` (dev/air-gapped explícito). Sin ese flag y sin
usuarios, se rechaza (servidor mal configurado). Con `IIOT_USERS` definido, se exige
`Authorization: Bearer <token>` y el rol adecuado.
"""

from __future__ import annotations

import os

from fastapi import Depends, Header, HTTPException

from app.security import context
from app.security.rbac import User, can

_ANONYMOUS = User(username="anonymous", role="admin")


def _anonymous_allowed() -> bool:
    return os.environ.get("IIOT_ALLOW_ANONYMOUS", "false").lower() == "true"


def login(username: str, password: str) -> str | None:
    """Autentica y devuelve un token firmado (Fernet+TTL); None si falla."""
    user = context.user_store.authenticate(username, password)
    if user is None:
        return None
    return context.cipher.sign_token({"username": user.username, "role": user.role})


def resolve_user(token: str | None) -> User | None:
    """Resuelve el usuario desde un token (o anónimo en modo dev). None = no autorizado.

    Compartido por REST y WebSocket (auth en el handshake, Rev 12).
    """
    if not context.user_store.enabled:
        return _ANONYMOUS if _anonymous_allowed() else None
    if not token:
        return None
    data = context.cipher.verify_token(token)
    if data is None:
        return None
    return User(username=data["username"], role=data["role"])


async def current_user(authorization: str | None = Header(default=None)) -> User:
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    if not context.user_store.enabled and not _anonymous_allowed():
        raise HTTPException(status_code=403,
                            detail="servidor sin autenticación configurada (define IIOT_USERS)")
    user = resolve_user(token)
    if user is None:
        raise HTTPException(status_code=401, detail="token requerido o inválido")
    return user


def require(permission: str):
    """Dependencia que exige un permiso; devuelve el usuario si lo tiene."""

    async def _dep(user: User = Depends(current_user)) -> User:
        if not can(user.role, permission):
            raise HTTPException(status_code=403, detail=f"permiso denegado: {permission}")
        return user

    return _dep
