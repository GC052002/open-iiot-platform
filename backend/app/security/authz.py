"""Autorización por proyecto (ABAC ligero, F4.1 — Rev D1 §8.1.1).

La autorización **siempre** ocurre en el servidor. Cada proyecto (`project_id` =
tenant id) tiene miembros con un rol: `owner > editor > operator > viewer`. Un `admin`
global se resuelve como `owner` de cualquier proyecto.

- `read`    (viewer+):   ver tags/historial/suscribirse por WS.
- `operate` (operator+): escribir setpoints (`write` por WS).
- `edit`    (editor+):   editar topología/lógica/HMI.
- `manage`  (owner):     gestionar miembros, publicar, config sensible.

La dependencia FastAPI `require_project(perm)` extrae el `project_id` de la ruta, la
query o el cuerpo y verifica el rol del usuario para ESE proyecto. El frontend solo
oculta; nunca autoriza.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from app.security.auth import current_user
from app.security.rbac import User
from app.storage.config_repository import ConfigRepository

# perm por proyecto -> roles de proyecto que lo tienen (jerárquico).
PROJECT_PERMISSIONS: dict[str, set[str]] = {
    "read": {"viewer", "operator", "editor", "owner"},
    "operate": {"operator", "editor", "owner"},
    "edit": {"editor", "owner"},
    "manage": {"owner"},
}


def project_can(role_proj: str | None, perm: str) -> bool:
    return role_proj is not None and role_proj in PROJECT_PERMISSIONS.get(perm, set())


async def project_role(
    username: str, role_global: str, project_id: str, repo: ConfigRepository | None
) -> str | None:
    """Rol efectivo del usuario en el proyecto. `admin` global -> `owner`.

    Si no hay repositorio de configuración (modo abierto/dev), el admin anónimo también
    se resuelve como `owner`; el resto no tiene acceso por proyecto.
    """
    if role_global == "admin":
        return "owner"
    if repo is None:
        return None
    return await repo.get_member_role(project_id, username)


async def _extract_project_id(request: Request) -> str | None:
    pid = request.path_params.get("project_id") or request.query_params.get("project_id")
    if pid:
        return pid
    # Cuerpo JSON (POST/PATCH). Starlette cachea el body, así que el endpoint lo relee.
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - cuerpo ausente/no-JSON
        return None
    if isinstance(body, dict):
        val = body.get("project_id")
        return str(val) if val is not None else None
    return None


async def authorize_project(user: User, project_id: str, perm: str) -> None:
    """Verifica `perm` sobre `project_id` para endpoints con un `project_id` ya resuelto
    (p. ej. con valor por defecto). Lanza 403 si no procede."""
    from app.state import state  # import perezoso (evita ciclo state<->authz)

    role = await project_role(user.username, user.role, project_id, state.config_repo)
    if not project_can(role, perm):
        raise HTTPException(status_code=403, detail=f"permiso de proyecto denegado: {perm}")


def require_project(perm: str):
    """Dependencia que exige `perm` sobre el `project_id` de la petición."""

    async def _dep(request: Request, user: User = Depends(current_user)) -> tuple[User, str]:
        from app.state import state  # import perezoso (evita ciclo state<->authz)

        project_id = await _extract_project_id(request)
        if not project_id:
            raise HTTPException(status_code=422, detail="project_id requerido")
        role = await project_role(user.username, user.role, project_id, state.config_repo)
        if not project_can(role, perm):
            raise HTTPException(status_code=403,
                                detail=f"permiso de proyecto denegado: {perm}")
        return user, project_id

    return _dep
