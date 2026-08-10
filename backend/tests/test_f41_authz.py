"""F4.1 / F4.1b / F4.1c — permisos por proyecto, publicación y secretos."""

from __future__ import annotations

import httpx
from app.main import _ws_authorized, app
from app.security import context
from app.security.authz import project_can, project_role
from app.security.user_store import DbUserStore
from app.state import state
from app.ws.manager import _Client

# --- Matriz de permisos por proyecto (unit) ---------------------------------

def test_project_permissions_matrix():
    assert project_can("viewer", "read") and not project_can("viewer", "operate")
    assert project_can("operator", "operate") and not project_can("operator", "edit")
    assert project_can("editor", "edit") and not project_can("editor", "manage")
    assert project_can("owner", "manage")
    assert not project_can(None, "read")


async def test_project_role_resolution(config_env):
    cfg = config_env
    await cfg.add_member("P", "eng", "editor")
    # admin global => owner de cualquier proyecto.
    assert await project_role("x", "admin", "P", cfg) == "owner"
    # miembro => su rol.
    assert await project_role("eng", "engineer", "P", cfg) == "editor"
    # no miembro => sin acceso.
    assert await project_role("otro", "engineer", "P", cfg) is None


# --- Helpers de API ---------------------------------------------------------

def _project(pid: str) -> dict:
    return {"schema_version": "1", "project_id": pid, "name": pid,
            "nodes": [], "edges": [], "tags": []}


async def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _login(c, u, p):
    return (await c.post("/login", json={"username": u, "password": p})).json()["token"]


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


async def _seed_users(**roles: str) -> None:
    store: DbUserStore = context.user_store  # type: ignore[assignment]
    for username, role in roles.items():
        await store.create_user(username, "pw", role)


# --- Aislamiento entre proyectos (Rev D1 §8.1.1) ----------------------------

async def test_cross_project_edit_denied(config_env):
    await _seed_users(enga="engineer", engb="engineer")
    async with await _client() as c:
        ta = await _login(c, "enga", "pw")
        tb = await _login(c, "engb", "pw")
        # Cada engineer crea su propio proyecto (queda como owner).
        assert (await c.post("/projects", json=_project("A"), headers=_h(ta))).status_code == 200
        assert (await c.post("/projects", json=_project("B"), headers=_h(tb))).status_code == 200
        # engb NO puede editar A (no es miembro) — la topología ajena está protegida.
        r = await c.post("/projects", json=_project("A"), headers=_h(tb))
        assert r.status_code == 403
        # enga sí puede reeditar A.
        assert (await c.post("/projects", json=_project("A"), headers=_h(ta))).status_code == 200


async def test_operator_cannot_edit_but_can_read(config_env):
    cfg = config_env
    await _seed_users(owner="engineer", op="client")
    async with await _client() as c:
        to = await _login(c, "owner", "pw")
        assert (await c.post("/projects", json=_project("P"), headers=_h(to))).status_code == 200
        await cfg.add_member("P", "op", "operator")
        top = await _login(c, "op", "pw")
        # operator NO edita topología.
        assert (await c.post("/projects", json=_project("P"), headers=_h(top))).status_code == 403
        # pero sí lee sus datos.
        assert (await c.get("/tags?project_id=P", headers=_h(top))).status_code == 200
        # ...y no la de un proyecto donde no es miembro.
        assert (await c.get("/tags?project_id=otro", headers=_h(top))).status_code == 403


async def test_ws_write_requires_operate(config_env):
    cfg = config_env
    await cfg.add_member("P", "viewer1", "viewer")
    await cfg.add_member("P", "op1", "operator")

    viewer = _Client(ws=None)  # type: ignore[arg-type]
    viewer.username, viewer.role = "viewer1", "viewer"
    op = _Client(ws=None)  # type: ignore[arg-type]
    op.username, op.role = "op1", "client"

    assert await _ws_authorized(viewer, "P", "read") is True
    assert await _ws_authorized(viewer, "P", "operate") is False   # viewer no escribe
    assert await _ws_authorized(op, "P", "operate") is True        # operator sí


# --- Miembros ---------------------------------------------------------------

async def test_members_api_manage_only(config_env):
    await _seed_users(owner="engineer", vis="viewer")
    async with await _client() as c:
        to = await _login(c, "owner", "pw")
        await c.post("/projects", json=_project("P"), headers=_h(to))
        # owner añade a un viewer.
        r = await c.post("/projects/P/members", json={"username": "vis", "role_proj": "viewer"},
                         headers=_h(to))
        assert r.status_code == 200
        members = {m["username"]: m["role_proj"]
                   for m in (await c.get("/projects/P/members", headers=_h(to))).json()}
        assert members == {"owner": "owner", "vis": "viewer"}
        # el viewer NO puede gestionar miembros (manage).
        tv = await _login(c, "vis", "pw")
        assert (await c.post("/projects/P/members", json={"username": "x", "role_proj": "viewer"},
                             headers=_h(tv))).status_code == 403
        # owner elimina al viewer.
        assert (await c.delete("/projects/P/members/vis", headers=_h(to))).status_code == 200


# --- Publicación / versiones (F4.1b) ----------------------------------------

async def test_publish_creates_immutable_version(config_env):
    await _seed_users(owner="engineer")
    async with await _client() as c:
        to = await _login(c, "owner", "pw")
        await c.post("/projects", json=_project("P"), headers=_h(to))
        r1 = await c.post("/projects/P/publish", headers=_h(to))
        assert r1.status_code == 200 and r1.json()["delivery_version"] == 1
        r2 = await c.post("/projects/P/publish", headers=_h(to))
        assert r2.json()["delivery_version"] == 2
        versions = (await c.get("/projects/P/versions", headers=_h(to))).json()
        assert [v["version"] for v in versions] == [2, 1]


# --- Persistencia y recarga (F4.1) ------------------------------------------

async def test_projects_persisted_and_reloaded(config_env):
    await _seed_users(owner="engineer")
    async with await _client() as c:
        to = await _login(c, "owner", "pw")
        await c.post("/projects", json=_project("P"), headers=_h(to))
    assert "P" in state.project_ids()
    # Simula un reinicio: parar todo y recargar desde la BD.
    await state.stop_all()
    assert state.project_ids() == []
    await state._load_persisted_projects()
    assert "P" in state.project_ids()


# --- Secretos resueltos en runtime (F4.1c) ----------------------------------

async def test_secret_resolved_in_start_project(config_env):
    cfg = config_env
    await state.secret_store.put_secret("plc_pw", "hunter2")
    project_json = {
        "schema_version": "1", "project_id": "S", "name": "S",
        "nodes": [{"id": "d1", "type": "driver", "driver_type": "modbus_tcp",
                   "config": {"host": "127.0.0.1", "port": 1,
                              "password": {"$secret": "plc_pw"}}}],
        "edges": [], "tags": [],
    }
    from app.models.project import load_project
    await state.start_project(load_project(project_json))
    runtime = state.runtime("S")
    # El runtime recibe la credencial resuelta en memoria...
    assert runtime.project.nodes[0].config["password"] == "hunter2"
    # ...pero lo persistido conserva la REFERENCIA, nunca el secreto en claro.
    await state.persist_project(load_project(project_json), "owner")
    record = await cfg.get_project("S")
    assert "hunter2" not in record["schema_json"]
    assert "$secret" in record["schema_json"]


# --- Listado filtrado por membresía (F4.1) ----------------------------------

async def test_list_projects_filtered_by_membership(config_env):
    await _seed_users(admin="admin", enga="engineer", engb="engineer")
    async with await _client() as c:
        ta = await _login(c, "enga", "pw")
        tb = await _login(c, "engb", "pw")
        adm = await _login(c, "admin", "pw")
        await c.post("/projects", json=_project("A"), headers=_h(ta))
        await c.post("/projects", json=_project("B"), headers=_h(tb))
        # enga solo ve A (es owner); no ve B.
        mine = {p["project_id"] for p in (await c.get("/projects", headers=_h(ta))).json()}
        assert mine == {"A"}
        # admin ve todos.
        allp = {p["project_id"] for p in (await c.get("/projects", headers=_h(adm))).json()}
        assert {"A", "B"} <= allp


# --- Publicación: instantánea inmutable, versión conservada al editar --------

async def test_publish_snapshot_immutable_across_edits(config_env):
    cfg = config_env
    await _seed_users(owner="engineer")
    async with await _client() as c:
        to = await _login(c, "owner", "pw")
        p = _project("P"); p["name"] = "v1-name"
        await c.post("/projects", json=p, headers=_h(to))
        await c.post("/projects/P/publish", headers=_h(to))
        # Editar la plantilla NO cambia la instantánea publicada ni resetea la versión.
        p2 = _project("P"); p2["name"] = "v2-name"
        await c.post("/projects", json=p2, headers=_h(to))
        assert (await cfg.get_project("P"))["delivery_version"] == 1  # conservada
        snap = await cfg.get_version("P", 1)
        assert '"name":"v1-name"' in snap["schema_json"].replace(" ", "")


# --- Autorización del endpoint de secretos ----------------------------------

async def test_secret_api_requires_project_write(config_env):
    await _seed_users(eng="engineer", cli="client")
    async with await _client() as c:
        te = await _login(c, "eng", "pw")
        tc = await _login(c, "cli", "pw")
        # engineer puede registrar credenciales.
        r = await c.post("/secrets", json={"credential_id": "plc_x", "secret": "pw"}, headers=_h(te))
        assert r.status_code == 200
        assert await state.secret_store.resolve_secret("plc_x") == "pw"
        # client NO puede.
        assert (await c.post("/secrets", json={"credential_id": "y", "secret": "z"},
                             headers=_h(tc))).status_code == 403


# --- WS: suscribirse a un proyecto ajeno se deniega --------------------------

async def test_ws_subscribe_denied_for_non_member(config_env):
    cfg = config_env
    await cfg.add_member("P", "m1", "viewer")
    member = _Client(ws=None)  # type: ignore[arg-type]
    member.username, member.role = "m1", "viewer"
    assert await _ws_authorized(member, "P", "read") is True
    assert await _ws_authorized(member, "OTRO", "read") is False  # sin membresía


# --- ConfigRepository: cascada de borrado y snapshots -----------------------

async def test_config_repo_delete_project_cascades(config_env):
    cfg = config_env
    await cfg.upsert_project("Z", "Z", "owner", '{"schema_version":"1","name":"Z"}')
    await cfg.add_member("Z", "u", "editor")
    await cfg.add_version("Z", 1, '{"schema_version":"1","name":"Z"}')
    await cfg.delete_project("Z")
    assert await cfg.get_project("Z") is None
    assert await cfg.list_members("Z") == []
    assert await cfg.list_versions("Z") == []
