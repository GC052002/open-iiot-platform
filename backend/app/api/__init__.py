"""API REST mínima (multi-tenant, Rev 7).

Endpoints:
  - POST /projects              -> cargar topología JSON y arrancar su Runtime.
  - GET  /projects              -> listar project_ids en ejecución.
  - GET  /projects/{project_id} -> devolver la topología cargada.
  - GET  /tags?project_id=...   -> tags con su último valor conocido.

Autorización: RBAC/ABAC es F2/F4 (§3.6, §10.2). En F1/F2.0 los endpoints quedan
abiertos; el punto de inserción del middleware de auth se marca abajo.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.models.project import load_project
from app.state import state

# TODO(F2.4): router.dependencies=[Depends(require_permission(...))] para RBAC/ABAC.
router = APIRouter()


@router.post("/projects")
async def create_project(body: dict[str, Any]) -> dict[str, Any]:
    try:
        project = load_project(body)
    except Exception as exc:  # noqa: BLE001 - validación Pydantic -> 422
        raise HTTPException(status_code=422, detail=f"proyecto inválido: {exc}") from exc
    await state.start_project(project)
    return {"status": "running", "project_id": project.project_id, "tags": len(project.tags)}


@router.get("/projects")
async def list_projects() -> list[str]:
    return state.project_ids()


@router.get("/projects/{project_id}")
async def get_project(project_id: str) -> dict[str, Any]:
    runtime = state.runtime(project_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail=f"proyecto no cargado: {project_id!r}")
    return runtime.project.model_dump()


@router.get("/tags")
async def list_tags(project_id: str = "default") -> list[dict[str, Any]]:
    runtime = state.runtime(project_id)
    if runtime is None:
        return []
    snap = {v.tag_id: v for v in state.tag_cache.snapshot(project_id)}
    out: list[dict[str, Any]] = []
    for tag in runtime.project.tags:
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
