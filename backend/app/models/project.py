"""Modelo `Project` — topología completa importada/exportada como JSON.

R5 (ARCHITECTURE §3.10): `Project` es una **unión discriminada por
`schema_version`** desde el día 1, aunque solo exista `v1`. Coste cero ahora,
migración trivial cuando aparezca `v2`: se añade `ProjectV2` a la unión y un
`migrate_v1_to_v2`, sin tocar el resto del código.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter

from app.models.node import Node
from app.models.tag import Tag


class Edge(BaseModel):
    """Conexión dirigida entre dos nodos del canvas."""

    id: str
    source: str
    target: str


class ProjectV1(BaseModel):
    schema_version: Literal["1"] = "1"
    name: str
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    tags: list[Tag] = Field(default_factory=list)


# Unión discriminada. Hoy solo v1; el discriminador deja la puerta abierta a v2+.
Project = Annotated[
    Union[ProjectV1,],  # noqa: UP007 - trailing comma mantiene la forma de unión
    Field(discriminator="schema_version"),
]

# Adaptador reutilizable para validar/parsear JSON entrante.
ProjectAdapter: TypeAdapter[ProjectV1] = TypeAdapter(Project)


def load_project(raw: dict | str | bytes) -> ProjectV1:
    """Valida y parsea un proyecto desde dict o JSON crudo (usado por `api/`)."""
    if isinstance(raw, dict):
        return ProjectAdapter.validate_python(raw)
    return ProjectAdapter.validate_json(raw)
