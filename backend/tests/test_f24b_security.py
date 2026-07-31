"""F2.4b: seguridad — cifrado Fernet, RBAC, auth opt-in, audit y notificadores."""

import time

import httpx
import pytest

from app.alarms.notifier import format_message
from app.models.alarm import AlarmEvent
from app.security.crypto import CredentialCipher
from app.security.rbac import UserStore, can, hash_password, verify_password


# --- Cifrado / tokens -------------------------------------------------------

def test_cipher_encrypt_decrypt_roundtrip():
    c = CredentialCipher(CredentialCipher.generate_key())
    assert c.decrypt(c.encrypt("s3cr3t")) == "s3cr3t"


def test_token_sign_verify_and_expiry():
    c = CredentialCipher(CredentialCipher.generate_key())
    tok = c.sign_token({"username": "u", "role": "admin"})
    assert c.verify_token(tok)["role"] == "admin"
    assert c.verify_token("basura") is None                  # inválido
    time.sleep(2.1)
    assert c.verify_token(tok, ttl_seconds=1) is None        # expirado (edad > 1s)


# --- RBAC -------------------------------------------------------------------

def test_permission_matrix():
    assert can("admin", "project:write") and can("engineer", "project:write")
    assert not can("operator", "project:write")
    assert can("operator", "tag:write") and not can("viewer", "tag:write")
    assert can("viewer", "read")
    assert can("admin", "audit:read") and not can("engineer", "audit:read")


def test_password_hashing():
    salt, h = hash_password("clave")
    assert verify_password("clave", salt, h)
    assert not verify_password("otra", salt, h)


def test_user_store_from_env_and_auth():
    store = UserStore.from_env('[{"username":"ana","role":"engineer","password":"pw"}]')
    assert store.enabled
    assert store.authenticate("ana", "pw").role == "engineer"
    assert store.authenticate("ana", "mala") is None
    assert UserStore.from_env("").enabled is False           # sin usuarios => modo abierto


# --- Notificadores ----------------------------------------------------------

def test_notifier_format_message():
    ev = AlarmEvent(project_id="P", rule_id="r", tag_id="t", severity="critical",
                    message="Nivel alto", state="active", value=99)
    txt = format_message(ev)
    assert "CRITICAL" in txt and "ACTIVADA" in txt and "99" in txt and "Nivel alto" in txt


# --- Auth end-to-end (opt-in) sobre la app ----------------------------------

async def test_open_mode_allows_without_token(monkeypatch):
    # Sin usuarios configurados: endpoints abiertos.
    from app.security import context
    context.configure(users_json="")
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        assert (await c.get("/tags?project_id=x")).status_code == 200


async def test_enabled_mode_requires_token_and_role():
    from app.security import context
    context.configure(key=CredentialCipher.generate_key(),
                      users_json='[{"username":"op","role":"operator","password":"pw"},'
                                 '{"username":"eng","role":"engineer","password":"pw"}]')
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        # Sin token => 401
        assert (await c.get("/tags?project_id=x")).status_code == 401
        # Login operator, pero POST /projects exige engineer => 403
        tok = (await c.post("/login", json={"username": "op", "password": "pw"})).json()["token"]
        r = await c.post("/projects", json={"schema_version": "1", "project_id": "x", "name": "n"},
                         headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 403
        # Engineer sí puede
        tok2 = (await c.post("/login", json={"username": "eng", "password": "pw"})).json()["token"]
        r2 = await c.post("/projects", json={"schema_version": "1", "project_id": "x", "name": "n"},
                          headers={"Authorization": f"Bearer {tok2}"})
        assert r2.status_code == 200
    context.configure(users_json="")  # restaurar modo abierto para otros tests


def _app():
    from app.main import app
    return app
