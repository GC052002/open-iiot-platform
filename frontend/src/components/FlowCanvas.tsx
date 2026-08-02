/**
 * Canvas React Flow — esqueleto de F3.0.
 *
 * Aquí sólo montamos el lienzo (fondo, controles, minimapa) con unos nodos de
 * muestra que representan las tres familias de la paleta (driver/lógica/widget,
 * `models/node.py`). En F3.1 se añaden paleta arrastrable, conexión de nodos e
 * inspector de propiedades; en F3.2, el data-binding por `tag_id` a los widgets.
 */

import { useCallback } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

const initialNodes: Node[] = [
  {
    id: "driver-1",
    position: { x: 40, y: 40 },
    data: { label: "🔌 Driver Modbus" },
    style: nodeStyle("#2f81f7"),
  },
  {
    id: "logic-1",
    position: { x: 300, y: 140 },
    data: { label: "🧮 Lógica: escala" },
    style: nodeStyle("#d29922"),
  },
  {
    id: "widget-1",
    position: { x: 560, y: 40 },
    data: { label: "🛢️ Widget: tanque" },
    style: nodeStyle("#2ea043"),
  },
];

const initialEdges: Edge[] = [
  { id: "e1", source: "driver-1", target: "logic-1" },
  { id: "e2", source: "logic-1", target: "widget-1" },
];

function nodeStyle(color: string): React.CSSProperties {
  return {
    background: "#171b22",
    color: "#e6edf3",
    border: `1px solid ${color}`,
    borderRadius: 8,
    padding: "8px 12px",
    fontSize: 13,
  };
}

export function FlowCanvas() {
  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges],
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={onConnect}
      colorMode="dark"
      fitView
      proOptions={{ hideAttribution: true }}
    >
      <Background gap={16} />
      <MiniMap pannable zoomable />
      <Controls />
    </ReactFlow>
  );
}
