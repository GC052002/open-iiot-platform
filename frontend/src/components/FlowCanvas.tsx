/**
 * Canvas editable (F3.1).
 *
 * Fuente de verdad en `projectStore`. Soporta: soltar nodos desde la paleta
 * (HTML5 DnD → `screenToFlowPosition`), conectar nodos, seleccionar (alimenta el
 * inspector) y borrar (Supr/Backspace, que limpia también los edges conectados).
 */

import { useCallback, useMemo } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { createNode, parsePaletteItem, PALETTE_MIME, type AppNode } from "../editor/model";
import { nodeTypes } from "../editor/nodeTypes";
import { useProjectStore } from "../store/projectStore";

function Canvas() {
  const { screenToFlowPosition } = useReactFlow();
  const nodes = useProjectStore((s) => s.nodes);
  const edges = useProjectStore((s) => s.edges);
  const onNodesChange = useProjectStore((s) => s.onNodesChange);
  const onEdgesChange = useProjectStore((s) => s.onEdgesChange);
  const onConnect = useProjectStore((s) => s.onConnect);
  const addNode = useProjectStore((s) => s.addNode);
  const select = useProjectStore((s) => s.select);

  const types = useMemo(() => nodeTypes, []);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const item = parsePaletteItem(e.dataTransfer.getData(PALETTE_MIME));
      if (!item) return;
      const position = screenToFlowPosition({ x: e.clientX, y: e.clientY });
      addNode(createNode(item, position));
    },
    [screenToFlowPosition, addNode],
  );

  return (
    <div className="canvas-wrap" onDrop={onDrop} onDragOver={onDragOver}>
      <ReactFlow<AppNode>
        nodes={nodes}
        edges={edges}
        nodeTypes={types}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={(_e, node) => select(node.id)}
        onPaneClick={() => select(null)}
        deleteKeyCode={["Backspace", "Delete"]}
        colorMode="dark"
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} />
        <MiniMap pannable zoomable />
        <Controls />
      </ReactFlow>
      {nodes.length === 0 && (
        <div className="canvas-empty">Arrastra bloques de la paleta para empezar a diseñar.</div>
      )}
    </div>
  );
}

export function FlowCanvas() {
  return (
    <ReactFlowProvider>
      <Canvas />
    </ReactFlowProvider>
  );
}
