"""Contexto de seguridad compartido: cipher + almacén de usuarios (F2.4b).

Se inicializa desde el entorno. `configure()` permite reconfigurarlo en tests.
"""

from __future__ import annotations

from app.security.crypto import CredentialCipher
from app.security.rbac import UserStore

cipher = CredentialCipher()
user_store = UserStore.from_env()


def configure(*, users_json: str | None = None, key: str | None = None) -> None:
    """Reconfigura el contexto (tests / arranque explícito)."""
    global cipher, user_store
    if key is not None:
        cipher = CredentialCipher(key)
    if users_json is not None:
        user_store = UserStore.from_env(users_json)
