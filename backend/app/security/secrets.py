"""Gestión de secretos: credenciales de PLC FUERA del JSON (F4.1c — Rev D1 §8.1.3).

El JSON de un proyecto (plantilla/entrega) **nunca** contiene contraseñas. Referencia
un `credential_id` mediante `{"$secret": "<credential_id>"}` en la config del driver;
el backend lo resuelve en runtime e inyecta el valor en memoria antes de instanciar el
driver, de modo que el JSON de entrega se puede loguear/compartir sin riesgo.

Almacén: Fernet con la **KEK de instancia** (`IIOT_FERNET_KEY`, reutiliza `crypto.py`),
persistido en el `ConfigRepository`. Vault/SOPS quedan para cuando haga falta rotación.
"""

from __future__ import annotations

from typing import Any

from app.security.crypto import CredentialCipher
from app.storage.config_repository import ConfigRepository

SECRET_REF = "$secret"


class SecretStore:
    def __init__(self, repo: ConfigRepository, cipher: CredentialCipher) -> None:
        self._repo = repo
        self._cipher = cipher

    async def put_secret(self, credential_id: str, plaintext: str) -> None:
        await self._repo.put_secret(credential_id, self._cipher.encrypt(plaintext))

    async def resolve_secret(self, credential_id: str) -> str | None:
        ciphertext = await self._repo.get_secret(credential_id)
        if ciphertext is None:
            return None
        return self._cipher.decrypt(ciphertext)

    async def resolve_config(self, config: Any) -> Any:
        """Devuelve una copia de `config` con las referencias `$secret` resueltas.

        Recorre dicts/listas de forma recursiva. Una referencia no resuelta lanza
        `KeyError` (fail-closed: mejor no arrancar que conectar sin credencial).
        """
        if isinstance(config, dict):
            if SECRET_REF in config and len(config) == 1:
                cred_id = config[SECRET_REF]
                value = await self.resolve_secret(cred_id)
                if value is None:
                    raise KeyError(f"secreto no encontrado: {cred_id!r}")
                return value
            return {k: await self.resolve_config(v) for k, v in config.items()}
        if isinstance(config, list):
            return [await self.resolve_config(v) for v in config]
        return config
