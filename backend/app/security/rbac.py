"""RBAC — roles, permisos y usuarios (ARCHITECTURE §3.6, F2.4b).

Roles: admin > engineer > operator > viewer. La autorización se **impone en el
backend** (no en la UI). El hash de contraseña usa `pbkdf2_hmac` de la stdlib (sin
dependencias extra). ABAC multi-planta (por `project_id`) es F4 (§10.2).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Literal

from pydantic import BaseModel

Role = Literal["admin", "engineer", "operator", "viewer"]

# permiso -> roles que lo tienen
PERMISSIONS: dict[str, set[str]] = {
    "read": {"admin", "engineer", "operator", "viewer"},
    "tag:write": {"admin", "engineer", "operator"},
    "project:write": {"admin", "engineer"},
    "audit:read": {"admin"},
    "user:manage": {"admin"},
}

_PBKDF2_ROUNDS = 100_000


def can(role: str, permission: str) -> bool:
    return role in PERMISSIONS.get(permission, set())


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Devuelve `(salt_hex, hash_hex)` con PBKDF2-HMAC-SHA256."""
    salt = salt or os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ROUNDS)
    return salt, dk.hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    _, computed = hash_password(password, salt)
    return hmac.compare_digest(computed, expected_hash)


class User(BaseModel):
    username: str
    role: Role
    salt: str = ""
    password_hash: str = ""


class UserStore:
    """Almacén de usuarios en memoria. Se puebla desde `IIOT_USERS` (JSON) o vacío.

    Formato de `IIOT_USERS` (dev): `[{"username":"admin","role":"admin","password":"secreto"}]`
    Las contraseñas en claro se **hashean al cargar** (no se guardan en claro en memoria).
    Un almacén persistente (BD) es F4.
    """

    def __init__(self, users: list[User] | None = None) -> None:
        self._users: dict[str, User] = {u.username: u for u in (users or [])}

    @property
    def enabled(self) -> bool:
        """Si no hay usuarios configurados, la auth queda desactivada (modo abierto)."""
        return bool(self._users)

    @classmethod
    def from_env(cls, raw: str | None = None) -> "UserStore":
        raw = raw if raw is not None else os.environ.get("IIOT_USERS", "")
        if not raw.strip():
            return cls([])
        users: list[User] = []
        for entry in json.loads(raw):
            salt, phash = hash_password(entry["password"])
            users.append(User(username=entry["username"], role=entry["role"],
                              salt=salt, password_hash=phash))
        return cls(users)

    def add(self, username: str, password: str, role: Role) -> User:
        salt, phash = hash_password(password)
        user = User(username=username, role=role, salt=salt, password_hash=phash)
        self._users[username] = user
        return user

    def authenticate(self, username: str, password: str) -> User | None:
        user = self._users.get(username)
        if user is None or not verify_password(password, user.salt, user.password_hash):
            return None
        return user
