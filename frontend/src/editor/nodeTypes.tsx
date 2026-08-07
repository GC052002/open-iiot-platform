/**
 * Componentes de nodo custom para el canvas (F3.1).
 *
 * Un único `EditorNodeView` sirve a los tres `kind` (driver/logic/widget): se
 * adapta por color/icono y muestra label + subtipo + un resumen de `params`. Trae
 * handles (target a la izquierda, source a la derecha) para poder conectar nodos.
 * El binding en vivo del widget por `tag_id` llega en F3.2.
 */

import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { AppNode, NodeKind } from "./model";

const ACCENT: Record<NodeKind, string> = {
  driver: "#2f81f7",
  logic: "#d29922",
  widget: "#2ea043",
};
const ICON: Record<NodeKind, string> = { driver: "🔌", logic: "🧮", widget: "🛢️" };

/** Resumen corto de params para pintar dentro del nodo. */
function summarize(kind: NodeKind, params: Record<string, unknown>): string {
  if (kind === "driver") {
    const host = params.host ?? params.endpoint;
    return host ? String(host) : "sin destino";
  }
  if (kind === "widget") {
    const tag = params.tag_id;
    return tag ? `tag: ${tag}` : "sin binding";
  }
  const keys = Object.keys(params);
  return keys.length ? keys.map((k) => `${k}=${params[k]}`).join(" · ") : "—";
}

export function EditorNodeView({ data, selected }: NodeProps<AppNode>) {
  const kind = data.kind;
  const accent = ACCENT[kind];
  return (
    <div
      className="rf-node"
      style={{ borderColor: accent, boxShadow: selected ? `0 0 0 2px ${accent}` : "none" }}
    >
      <Handle type="target" position={Position.Left} />
      <div className="rf-node-title">
        <span>{ICON[kind]}</span>
        <span className="rf-node-label">{data.label}</span>
      </div>
      <div className="rf-node-sub" style={{ color: accent }}>
        {data.subtype}
      </div>
      <div className="rf-node-summary">{summarize(kind, data.params)}</div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

/** Mapa que React Flow usa para elegir el componente por `node.type` (= kind). */
export const nodeTypes = {
  driver: EditorNodeView,
  logic: EditorNodeView,
  widget: EditorNodeView,
};
