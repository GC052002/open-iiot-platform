"""API REST mínima de la Fase 1.

Endpoints:
  - POST /projects         -> cargar topología JSON y arrancar el Runtime.
  - GET  /projects/current -> devolver la topología cargada.
  - GET  /tags             -> listar tags con su último valor conocido.

Autorización: RBAC/ABAC es F2/F4 (§3.6, §10.2). En F1 los endpoints quedan
abiertos; el punto de inserción del middleware de auth se marca abajo.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.engine.runtime import Runtime
from app.models.project import load_project
from app.state import state

# TODO(F2): router.dependencies=[Depends(require_permission(...))] para RBAC/ABAC.
router = APIRouter()


@router.post("/projects")
async def create_project(body: dict[str, Any]) -> dict[str, Any]:
    try:
        project = load_project(body)
    except Exception as exc:  # noqa: BLE001 - validación Pydantic -> 422
        raise HTTPException(status_code=422, detail=f"proyecto inválido: {exc}") from exc
    await state.start_project(Runtime(project))
    return {"status": "running", "name": project.name, "tags": len(project.tags)}


@router.get("/projects/current")
async def current_project() -> dict[str, Any]:
    if state.runtime is None:
        raise HTTPException(status_code=404, detail="no hay proyecto cargado")
    return state.runtime.project.model_dump()


@router.get("/tags")
async def list_tags() -> list[dict[str, Any]]:
    if state.runtime is None:
        return []
    snap = {v.tag_id: v for v in state.runtime.tag_cache.snapshot()}
    out: list[dict[str, Any]] = []
    for tag in state.runtime.project.tags:
        value = snap.get(tag.id)
        out.append(
            {
                "id": tag.id,
                "name": tag.name,
                "value": value.value if value else None,
                "quality": value.quality if value else "bad",
            }
        )
    return out
