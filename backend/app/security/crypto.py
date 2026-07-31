"""Cifrado de credenciales y firma de tokens con Fernet (ARCHITECTURE §3.5, F2.4b).

La clave **nunca** se versiona: viene de `IIOT_FERNET_KEY` (env / SOPS / Vault, §10.4).
Si no está definida, se genera una clave **efímera** (solo dev; se pierde al reiniciar,
y se registra un aviso). El mismo cifrado sirve para:
  - cifrar credenciales de driver (passwords OPC UA/MQTT, etc.),
  - firmar tokens de sesión (Fernet con TTL — sin dependencia extra de JWT).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger("iiot.security")


class CredentialCipher:
    def __init__(self, key: str | bytes | None = None) -> None:
        key = key or os.environ.get("IIOT_FERNET_KEY")
        if not key:
            key = Fernet.generate_key()
            log.warning(
                "IIOT_FERNET_KEY no definida: usando clave EFÍMERA (no persistente). "
                "Define IIOT_FERNET_KEY en producción (env/SOPS/Vault)."
            )
        self._fernet = Fernet(key if isinstance(key, bytes) else key.encode())

    # -- Cifrado de credenciales ---------------------------------------------
    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode()).decode()

    # -- Tokens de sesión (Fernet con TTL) -----------------------------------
    def sign_token(self, data: dict[str, Any]) -> str:
        return self._fernet.encrypt(json.dumps(data).encode()).decode()

    def verify_token(self, token: str, ttl_seconds: int = 3600) -> dict[str, Any] | None:
        try:
            raw = self._fernet.decrypt(token.encode(), ttl=ttl_seconds)
        except (InvalidToken, ValueError):
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def generate_key() -> str:
        return Fernet.generate_key().decode()
