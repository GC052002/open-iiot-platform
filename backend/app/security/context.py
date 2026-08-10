"""Contexto de seguridad compartido: cipher + almacén de usuarios + secretos.

Se inicializa desde el entorno. En arranque (F4.0) `state.startup` sustituye el almacén
por-env por uno respaldado en BD (`DbUserStore`) y crea el `SecretStore`. `configure()`
permite reconfigurarlo en tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Union

from app.security.crypto import CredentialCipher
from app.security.rbac import UserStore

if TYPE_CHECKING:
    from app.security.secrets import SecretStore
    from app.security.user_store import DbUserStore

cipher = CredentialCipher()
# En Fase 2 el store venía de env; en F4.0 `state.startup` lo reemplaza por DbUserStore.
user_store: Union["UserStore", "DbUserStore"] = UserStore.from_env()
secret_store: "SecretStore | None" = None


def configure(*, users_json: str | None = None, key: str | None = None) -> None:
    """Reconfigura el contexto (tests / arranque explícito)."""
    global cipher, user_store
    if key is not None:
        cipher = CredentialCipher(key)
    if users_json is not None:
        user_store = UserStore.from_env(users_json)


def set_user_store(store: "UserStore | DbUserStore") -> None:
    global user_store
    user_store = store


def set_secret_store(store: "SecretStore | None") -> None:
    global secret_store
    secret_store = store
