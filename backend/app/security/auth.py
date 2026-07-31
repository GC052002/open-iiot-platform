"""Autenticación y autorización FastAPI (F2.4b).

Modelo **opt-in**: si no hay usuarios configurados (`UserStore.enabled == False`), los
endpoints quedan abiertos y el usuario es un `admin` anónimo (modo air-gapped/dev). Al
configurar usuarios, se exige `Authorization: Bearer <token>` y el rol adecuado.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException

from app.security import context
from app.security.rbac import User, can

_ANONYMOUS = User(username="anonymous", role="admin")


def login(username: str, password: str) -> str | None:
    """Autentica y devuelve un token firmado (Fernet+TTL); None si falla."""
    user = context.user_store.authenticate(username, password)
    if user is None:
        return None
    return context.cipher.sign_token({"username": user.username, "role": user.role})


async def current_user(authorization: str | None = Header(default=None)) -> User:
    if not context.user_store.enabled:
        return _ANONYMOUS  # modo abierto
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="token requerido")
    data = context.cipher.verify_token(authorization[7:])
    if data is None:
        raise HTTPException(status_code=401, detail="token inválido o expirado")
    return User(username=data["username"], role=data["role"])


def require(permission: str):
    """Dependencia que exige un permiso; devuelve el usuario si lo tiene."""

    async def _dep(user: User = Depends(current_user)) -> User:
        if not can(user.role, permission):
            raise HTTPException(status_code=403, detail=f"permiso denegado: {permission}")
        return user

    return _dep
