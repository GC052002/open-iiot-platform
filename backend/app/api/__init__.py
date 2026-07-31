"""API REST (multi-tenant + RBAC, Rev 7 / F2.4b).

Autorización **opt-in** (§3.6): si no hay usuarios configurados, los endpoints quedan
abiertos (modo air-gapped/dev) y el usuario es un admin anónimo. Al configurar
usuarios (`IIOT_USERS`), se exige `Authorization: Bearer <token>` y el rol adecuado.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.models.project import load_project
from app.security.auth import current_user, login, require
from app.security.rbac import User
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


# -- Proyectos ---------------------------------------------------------------
@router.post("/projects")
async def create_project(body: dict[str, Any],
                         user: User = Depends(require("project:write"))) -> dict[str, Any]:
    try:
        project = load_project(body)
    except Exception as exc:  # noqa: BLE001 - validación Pydantic -> 422
        raise HTTPException(status_code=422, detail=f"proyecto inválido: {exc}") from exc
    await state.start_project(project)
    await state.audit("project:load", username=user.username, project_id=project.project_id,
                      detail=f"{len(project.tags)} tags")
    return {"status": "running", "project_id": project.project_id, "tags": len(project.tags)}


@router.get("/projects")
async def list_projects(user: User = Depends(require("read"))) -> list[str]:
    return state.project_ids()


@router.get("/projects/{project_id}")
async def get_project(project_id: str, user: User = Depends(require("read"))) -> dict[str, Any]:
    runtime = state.runtime(project_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail=f"proyecto no cargado: {project_id!r}")
    return runtime.project.model_dump()


# -- Datos -------------------------------------------------------------------
@router.get("/alarms")
async def alarms(project_id: str = "default",
                 user: User = Depends(require("read"))) -> list[dict[str, Any]]:
    return state.alarms.active_alarms(project_id)


@router.get("/history")
async def history(project_id: str, tag_id: str, limit: int = 1000,
                  user: User = Depends(require("read"))) -> list[dict[str, Any]]:
    if state.repo is None:
        return []
    return await state.repo.query(project_id, tag_id, limit)


@router.get("/tags")
async def list_tags(project_id: str = "default",
                    user: User = Depends(require("read"))) -> list[dict[str, Any]]:
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
