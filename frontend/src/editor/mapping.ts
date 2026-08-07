/**
 * Mapping editor ↔ backend (`models/project.py`).
 *
 * `toProjectNode`/`toProjectEdge`/`buildProject` producen el JSON que consume el
 * backend (`POST /projects`), con el mismo `schema_version`. `fromProjectNode`
 * hace el camino inverso (import, F3.3). Son funciones **puras**: el round-trip
 * `fromProjectNode(toProjectNode(n))` es idempotente sobre los campos de dominio.
 */

import type { Edge } from "@xyflow/react";
import type {
  DriverNode,
  LogicNode,
  ProjectEdge,
  ProjectNode,
  ProjectV1,
  WidgetNode,
} from "../api/types";
import type { AppNode, EditorNodeData, NodeKind } from "./model";

/** Nodo del editor → nodo del backend (expande `subtype`/`params` al campo correcto). */
export function toProjectNode(n: AppNode): ProjectNode {
  const d = n.data;
  const base = { id: n.id, label: d.label, position: { x: n.position.x, y: n.position.y } };
  switch (d.kind) {
    case "driver":
      return { ...base, type: "driver", driver_type: d.subtype, config: d.params };
    case "logic":
      return { ...base, type: "logic", strategy: d.subtype, params: d.params };
    case "widget":
      return { ...base, type: "widget", widget: d.subtype, props: d.params };
  }
}

/** Nodo del backend → nodo del editor (colapsa el campo específico en `params`). */
export function fromProjectNode(p: ProjectNode): AppNode {
  const kind = p.type as NodeKind;
  let subtype = "";
  let params: Record<string, unknown> = {};
  if (p.type === "driver") {
    subtype = (p as DriverNode).driver_type;
    params = (p as DriverNode).config ?? {};
  } else if (p.type === "logic") {
    subtype = (p as LogicNode).strategy;
    params = (p as LogicNode).params ?? {};
  } else {
    subtype = (p as WidgetNode).widget;
    params = (p as WidgetNode).props ?? {};
  }
  const data: EditorNodeData = { label: p.label ?? "", kind, subtype, params };
  return { id: p.id, type: kind, position: { x: p.position.x, y: p.position.y }, data };
}

export function toProjectEdge(e: Edge): ProjectEdge {
  return { id: e.id, source: e.source, target: e.target };
}

export function fromProjectEdge(e: ProjectEdge): Edge {
  return { id: e.id, source: e.source, target: e.target };
}

/** Ensambla el `ProjectV1` completo listo para `POST /projects`. */
export function buildProject(
  meta: { project_id: string; name: string },
  nodes: AppNode[],
  edges: Edge[],
): ProjectV1 {
  return {
    schema_version: "1",
    project_id: meta.project_id,
    name: meta.name,
    nodes: nodes.map(toProjectNode),
    edges: edges.map(toProjectEdge),
    tags: [],
    alarms: [],
  };
}
