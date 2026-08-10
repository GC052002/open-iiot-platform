"""F4.0 — usuarios persistidos en BD + API de gestión + secretos (parte identidad)."""

from __future__ import annotations

import httpx
import pytest
from app.main import app
from app.security import context
from app.security.crypto import CredentialCipher
from app.security.secrets import SecretStore
from app.security.user_store import DbUserStore
from app.storage import SQLiteConfigRepository

# --- ConfigRepository: CRUD de usuarios -------------------------------------

async def test_config_repo_user_crud():
    repo = SQLiteConfigRepository(":memory:")
    await repo.init()
    try:
        await repo.upsert_user({"username": "ana", "password_hash": "h", "salt": "s",
                                "role_global": "engineer", "active": 1})
        row = await repo.get_user("ana")
        assert row["role_global"] == "engineer" and row["active"] == 1
        assert [u["username"] for u in await repo.list_users()] == ["ana"]
        await repo.set_user_active("ana", False)
        assert (await repo.get_user("ana"))["active"] == 0
        await repo.delete_user("ana")
        assert await repo.get_user("ana") is None
    finally:
        await repo.close()


# --- DbUserStore: caché, auth y bootstrap -----------------------------------

async def test_db_user_store_create_and_authenticate():
    repo = SQLiteConfigRepository(":memory:")
    await repo.init()
    try:
        store = DbUserStore(repo)
        await store.load(bootstrap=False)
        assert store.enabled is False
        await store.create_user("bob", "pw", "admin")
        assert store.enabled is True
        assert store.authenticate("bob", "pw").role == "admin"
        assert store.authenticate("bob", "mala") is None
        await store.set_active("bob", False)
        assert store.authenticate("bob", "pw") is None  # inactivo => sin login
    finally:
        await repo.close()


async def test_db_user_store_bootstrap_from_env(monkeypatch):
    monkeypatch.setenv("IIOT_USERS", '[{"username":"root","role":"admin","password":"pw"}]')
    repo = SQLiteConfigRepository(":memory:")
    await repo.init()
    try:
        store = DbUserStore(repo)
        await store.load()  # tabla vacía => siembra el admin
        assert store.authenticate("root", "pw").role == "admin"
        # Idempotente: recargar no duplica ni resiembra.
        store2 = DbUserStore(repo)
        await store2.load()
        assert len(store2.list_users()) == 1
    finally:
        await repo.close()


# --- SecretStore ------------------------------------------------------------

async def test_secret_store_roundtrip_and_resolve_config():
    repo = SQLiteConfigRepository(":memory:")
    await repo.init()
    try:
        ss = SecretStore(repo, CredentialCipher(CredentialCipher.generate_key()))
        await ss.put_secret("plc_a", "s3cr3t")
        assert await ss.resolve_secret("plc_a") == "s3cr3t"
        assert await ss.resolve_secret("desconocido") is None
        # El ciphertext en BD nunca es el texto plano.
        assert (await repo.get_secret("plc_a")) != "s3cr3t"
        # resolve_config sustituye la referencia $secret.
        cfg = {"host": "10.0.0.5", "password": {"$secret": "plc_a"}}
        out = await ss.resolve_config(cfg)
        assert out == {"host": "10.0.0.5", "password": "s3cr3t"}
        with pytest.raises(KeyError):
            await ss.resolve_config({"pw": {"$secret": "noexiste"}})
    finally:
        await repo.close()


# --- API de gestión de usuarios (admin) -------------------------------------

async def _client():
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://t")


async def _login(c, username, password):
    r = await c.post("/login", json={"username": username, "password": password})
    return r.json()["token"]


async def test_users_api_crud_admin_only(config_env):
    # Sembramos un admin y un engineer directamente en el store del contexto.
    store: DbUserStore = context.user_store  # type: ignore[assignment]
    await store.create_user("admin", "pw", "admin")
    await store.create_user("eng", "pw", "engineer")

    async with await _client() as c:
        admin_tok = await _login(c, "admin", "pw")
        eng_tok = await _login(c, "eng", "pw")
        ah = {"Authorization": f"Bearer {admin_tok}"}
        eh = {"Authorization": f"Bearer {eng_tok}"}

        # engineer NO puede gestionar usuarios.
        assert (await c.get("/users", headers=eh)).status_code == 403

        # admin crea un cliente.
        r = await c.post("/users", json={"username": "cli", "password": "pw", "role": "client"},
                         headers=ah)
        assert r.status_code == 200 and r.json()["role"] == "client"
        # duplicado => 409
        assert (await c.post("/users", json={"username": "cli", "password": "x", "role": "client"},
                             headers=ah)).status_code == 409

        usernames = {u["username"] for u in (await c.get("/users", headers=ah)).json()}
        assert {"admin", "eng", "cli"} <= usernames

        # desactivar => no puede loguear
        assert (await c.patch("/users/cli", json={"active": False}, headers=ah)).status_code == 200
        assert (await c.post("/login", json={"username": "cli", "password": "pw"})).status_code == 401

        # borrar
        assert (await c.delete("/users/cli", headers=ah)).status_code == 200
        assert (await c.delete("/users/cli", headers=ah)).status_code == 404


async def test_users_api_validation_and_password_reset(config_env):
    store: DbUserStore = context.user_store  # type: ignore[assignment]
    await store.create_user("admin", "pw", "admin")
    async with await _client() as c:
        ah = {"Authorization": f"Bearer {await _login(c, 'admin', 'pw')}"}
        # rol inválido => 422
        assert (await c.post("/users", json={"username": "z", "password": "p", "role": "boss"},
                             headers=ah)).status_code == 422
        # patch de usuario inexistente => 404
        assert (await c.patch("/users/nope", json={"active": True}, headers=ah)).status_code == 404
        # reset de contraseña => permite login con la nueva
        await c.post("/users", json={"username": "u", "password": "old", "role": "viewer"},
                     headers=ah)
        assert (await c.patch("/users/u", json={"password": "new"}, headers=ah)).status_code == 200
        assert (await c.post("/login", json={"username": "u", "password": "old"})).status_code == 401
        assert (await c.post("/login", json={"username": "u", "password": "new"})).status_code == 200


async def test_config_repo_upsert_project_preserves_version():
    repo = SQLiteConfigRepository(":memory:")
    await repo.init()
    try:
        await repo.upsert_project("P", "P", "o", '{"v":1}')
        await repo.add_version("P", 1, '{"v":1}')
        assert (await repo.get_project("P"))["delivery_version"] == 1
        # editar la plantilla (upsert) conserva delivery_version.
        await repo.upsert_project("P", "P-edit", "o", '{"v":2}')
        row = await repo.get_project("P")
        assert row["delivery_version"] == 1 and row["name"] == "P-edit"
    finally:
        await repo.close()
