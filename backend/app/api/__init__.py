"""API REST (multi-tenant + RBAC + autorización por proyecto, F4.0/F4.1).

Autorización en dos niveles:
- **Global** (`security/auth.require`): capacidades transversales (gestión de usuarios,
  creación de proyectos). En modo air-gapped/dev sin usuarios, el usuario es un admin
  anónimo y los endpoints quedan abiertos.
- **Por proyecto** (`security/authz.require_project`): cada endpoint que toca un
  `project_id` verifica el rol del usuario para ESE proyecto (Rev D1 §8.1.1). El
  frontend solo oculta; la autorización real es del backend.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.models.project import load_project
from app.security.auth import current_user, login, require
from app.security.authz import authorize_project, project_can, project_role, require_project
from app.security.rbac import User, can
from app.state import state

router = APIRouter()


# -- Autenticación -----------------------------------------------------------
@router.post("/login")
async def do_login(body: dict[str, str]) -> dict[str, str]:
    token = login(body.get("username", ""), body.get("password", ""))
    if token is None:
        raise HTTPException(status_code=401, detail="credenciales inválidas")
    await state.audit("login", username=body.get("username"))
    return {"token": token}


# -- Gestión de usuarios (admin, F4.0) ---------------------------------------
def _db_user_store():
    from app.security import context
    from app.security.user_store import DbUserStore

    store = context.user_store
    if not isinstance(store, DbUserStore):
        raise HTTPException(status_code=409,
                            detail="gestión de usuarios no disponible (store no persistente)")
    return store


@router.post("/users")
async def create_user(body: dict[str, Any],
                      user: User = Depends(require("user:manage"))) -> dict[str, Any]:
    store = _db_user_store()
    username, password, role = body.get("username"), body.get("password"), body.get("role")
    if not username or not password or role not in ("admin", "engineer", "client",
                                                    "operator", "viewer"):
        raise HTTPException(status_code=422, detail="username, password y role válidos requeridos")
    if store.get(username) is not None:
        raise HTTPException(status_code=409, detail="el usuario ya existe")
    await store.create_user(username, password, role)
    await state.audit("user:create", username=user.username, detail=f"{username}/{role}")
    return {"username": username, "role": role, "active": True}


@router.get("/users")
async def list_users(user: User = Depends(require("user:manage"))) -> list[dict[str, Any]]:
    return _db_user_store().list_users()


@router.patch("/users/{username}")
async def update_user(username: str, body: dict[str, Any],
                      user: User = Depends(require("user:manage"))) -> dict[str, Any]:
    store = _db_user_store()
    if store.get(username) is None:
        raise HTTPException(status_code=404, detail="usuario no encontrado")
    if "active" in body:
        await store.set_active(username, bool(body["active"]))
        await state.audit("user:active", username=user.username,
                          detail=username, new_value=body["active"])
    if body.get("password"):
        await store.set_password(username, body["password"])
        await state.audit("user:password", username=user.username, detail=username)
    updated = store.get(username)
    return {"username": username, "role": updated.role, "active": updated.active}


@router.delete("/users/{username}")
async def delete_user(username: str,
                      user: User = Depends(require("user:manage"))) -> dict[str, str]:
    store = _db_user_store()
    if store.get(username) is None:
        raise HTTPException(status_code=404, detail="usuario no encontrado")
    await store.delete_user(username)
    await state.audit("user:delete", username=user.username, detail=username)
    return {"status": "deleted", "username": username}


# -- Proyectos ---------------------------------------------------------------
@router.post("/projects")
async def create_project(body: dict[str, Any],
                         user: User = Depends(current_user)) -> dict[str, Any]:
    try:
        project = load_project(body)
    except Exception as exc:  # noqa: BLE001 - validación Pydantic -> 422
        raise HTTPException(status_code=422, detail=f"proyecto inválido: {exc}") from exc

    existing = None
    if state.config_repo is not None:
        existing = await state.config_repo.get_project(project.project_id)

    if existing is not None:
        # Edición: exige rol de proyecto `edit` (un operator NO edita topología, §8.2.4).
        role = await project_role(user.username, user.role, project.project_id, state.config_repo)
        if not project_can(role, "edit"):
            raise HTTPException(status_code=403, detail="permiso de proyecto denegado: edit")
        owner = existing["owner"]
    else:
        # Creación: exige capacidad global de crear proyectos.
        if not can(user.role, "project:write"):
            raise HTTPException(status_code=403, detail="permiso denegado: project:write")
        owner = user.username

    await state.start_project(project)
    await state.persist_project(project, owner)
    if existing is None and state.config_repo is not None:
        await state.config_repo.add_member(project.project_id, user.username, "owner")
    await state.audit("project:load", username=user.username, project_id=project.project_id,
                      detail=f"{len(project.tags)} tags")
    return {"status": "running", "project_id": project.project_id, "tags": len(project.tags)}


@router.get("/projects")
async def list_projects(user: User = Depends(require("read"))) -> list[dict[str, Any]]:
    if state.config_repo is None:
        # Modo abierto/dev: solo los proyectos en ejecución.
        return [{"project_id": pid} for pid in state.project_ids()]
    if user.role == "admin":
        return await state.config_repo.list_projects()
    return await state.config_repo.list_projects_for_user(user.username)


@router.get("/projects/{project_id}")
async def get_project(project_id: str,
                      dep: tuple[User, str] = Depends(require_project("read"))) -> dict[str, Any]:
    runtime = state.runtime(project_id)
    if runtime is not None:
        return runtime.project.model_dump()
    if state.config_repo is not None:
        record = await state.config_repo.get_project(project_id)
        if record is not None:
            return load_project(record["schema_json"]).model_dump()
    raise HTTPException(status_code=404, detail=f"proyecto no encontrado: {project_id!r}")


# -- Miembros por proyecto (F4.1) --------------------------------------------
@router.get("/projects/{project_id}/members")
async def list_members(project_id: str,
                       dep: tuple[User, str] = Depends(require_project("read"))
                       ) -> list[dict[str, Any]]:
    if state.config_repo is None:
        return []
    return await state.config_repo.list_members(project_id)


@router.post("/projects/{project_id}/members")
async def add_member(project_id: str, body: dict[str, Any],
                     dep: tuple[User, str] = Depends(require_project("manage"))
                     ) -> dict[str, Any]:
    user, _ = dep
    if state.config_repo is None:
        raise HTTPException(status_code=409, detail="persistencia no inicializada")
    member, role_proj = body.get("username"), body.get("role_proj")
    if not member or role_proj not in ("owner", "editor", "operator", "viewer"):
        raise HTTPException(status_code=422, detail="username y role_proj válidos requeridos")
    await state.config_repo.add_member(project_id, member, role_proj)
    await state.audit("member:add", username=user.username, project_id=project_id,
                      detail=f"{member}/{role_proj}")
    return {"project_id": project_id, "username": member, "role_proj": role_proj}


@router.delete("/projects/{project_id}/members/{member}")
async def remove_member(project_id: str, member: str,
                        dep: tuple[User, str] = Depends(require_project("manage"))
                        ) -> dict[str, str]:
    user, _ = dep
    if state.config_repo is None:
        raise HTTPException(status_code=409, detail="persistencia no inicializada")
    await state.config_repo.remove_member(project_id, member)
    await state.audit("member:remove", username=user.username, project_id=project_id, detail=member)
    return {"status": "removed", "username": member}


# -- Publicación / versiones de entrega (F4.1b) ------------------------------
@router.post("/projects/{project_id}/publish")
async def publish_project(project_id: str,
                          dep: tuple[User, str] = Depends(require_project("manage"))
                          ) -> dict[str, Any]:
    user, _ = dep
    try:
        version = await state.publish_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="proyecto no persistido") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await state.audit("project:publish", username=user.username, project_id=project_id,
                      new_value=version)
    return {"project_id": project_id, "delivery_version": version}


@router.get("/projects/{project_id}/versions")
async def list_versions(project_id: str,
                        dep: tuple[User, str] = Depends(require_project("read"))
                        ) -> list[dict[str, Any]]:
    if state.config_repo is None:
        return []
    return await state.config_repo.list_versions(project_id)


# -- Secretos (F4.1c) --------------------------------------------------------
@router.post("/secrets")
async def put_secret(body: dict[str, Any],
                     user: User = Depends(require("project:write"))) -> dict[str, str]:
    if state.secret_store is None:
        raise HTTPException(status_code=409, detail="almacén de secretos no inicializado")
    cred_id, secret = body.get("credential_id"), body.get("secret")
    if not cred_id or secret is None:
        raise HTTPException(status_code=422, detail="credential_id y secret requeridos")
    await state.secret_store.put_secret(cred_id, secret)
    await state.audit("secret:put", username=user.username, detail=cred_id)
    return {"status": "stored", "credential_id": cred_id}


# -- Datos (por proyecto) ----------------------------------------------------
# Estos endpoints llevan `project_id` con valor por defecto ("default"), así que la
# autorización por proyecto se hace en línea (no vía dependencia sobre la request).
@router.get("/alarms")
async def alarms(project_id: str = "default",
                 user: User = Depends(current_user)) -> list[dict[str, Any]]:
    await authorize_project(user, project_id, "read")
    return state.alarms.active_alarms(project_id)


@router.get("/history")
async def history(project_id: str, tag_id: str, limit: int = 1000,
                  user: User = Depends(current_user)) -> list[dict[str, Any]]:
    await authorize_project(user, project_id, "read")
    if state.repo is None:
        return []
    return await state.repo.query(project_id, tag_id, limit)


@router.get("/tags")
async def list_tags(project_id: str = "default",
                    user: User = Depends(current_user)) -> list[dict[str, Any]]:
    await authorize_project(user, project_id, "read")
    runtime = state.runtime(project_id)
    if runtime is None:
        return []
    snap = {v.tag_id: v for v in state.tag_cache.snapshot(project_id)}
    out: list[dict[str, Any]] = []
    for tag in runtime.project.tags:
        value = snap.get(tag.id)
        out.append({"id": tag.id, "name": tag.name,
                    "value": value.value if value else None,
                    "quality": value.quality if value else "bad"})
    return out


# -- Auditoría ---------------------------------------------------------------
@router.get("/audit")
async def audit(project_id: str | None = None, limit: int = 200,
                user: User = Depends(require("audit:read"))) -> list[dict[str, Any]]:
    if state.repo is None:
        return []
    return await state.repo.query_audit(project_id, limit)
