/**
 * Store del proyecto en edición (Zustand + persistencia local).
 *
 * Fuente de verdad del canvas: `nodes`/`edges` de React Flow (con nuestro
 * `EditorNodeData` dentro de `node.data`), la `meta` (project_id/nombre) y el nodo
 * seleccionado. Se persiste en `localStorage` para no perder el diseño al recargar
 * (persistencia local de F3). El export a backend vive en `editor/mapping.ts`.
 */

import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type NodeChange,
} from "@xyflow/react";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { AppNode, EditorNodeData } from "../editor/model";

export interface ProjectMeta {
  project_id: string;
  name: string;
}

interface ProjectStore {
  nodes: AppNode[];
  edges: Edge[];
  selectedId: string | null;
  meta: ProjectMeta;

  onNodesChange: (changes: NodeChange<AppNode>[]) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onConnect: (conn: Connection) => void;

  addNode: (node: AppNode) => void;
  updateNodeData: (id: string, patch: Partial<EditorNodeData>) => void;
  setNodeParams: (id: string, params: Record<string, unknown>) => void;
  removeNode: (id: string) => void;

  select: (id: string | null) => void;
  setMeta: (patch: Partial<ProjectMeta>) => void;
  loadGraph: (nodes: AppNode[], edges: Edge[], meta?: ProjectMeta) => void;
  clear: () => void;
}

const DEFAULT_META: ProjectMeta = { project_id: "planta_demo", name: "Planta Demo" };

export const useProjectStore = create<ProjectStore>()(
  persist(
    (set, get) => ({
      nodes: [],
      edges: [],
      selectedId: null,
      meta: DEFAULT_META,

      onNodesChange: (changes) =>
        set({ nodes: applyNodeChanges(changes, get().nodes) as AppNode[] }),
      onEdgesChange: (changes) => set({ edges: applyEdgeChanges(changes, get().edges) }),
      onConnect: (conn) => set({ edges: addEdge(conn, get().edges) }),

      addNode: (node) => set((s) => ({ nodes: [...s.nodes, node], selectedId: node.id })),

      updateNodeData: (id, patch) =>
        set((s) => ({
          nodes: s.nodes.map((n) =>
            n.id === id ? { ...n, data: { ...n.data, ...patch } } : n,
          ),
        })),

      setNodeParams: (id, params) =>
        set((s) => ({
          nodes: s.nodes.map((n) =>
            n.id === id ? { ...n, data: { ...n.data, params } } : n,
          ),
        })),

      removeNode: (id) =>
        set((s) => ({
          nodes: s.nodes.filter((n) => n.id !== id),
          edges: s.edges.filter((e) => e.source !== id && e.target !== id),
          selectedId: s.selectedId === id ? null : s.selectedId,
        })),

      select: (id) => set({ selectedId: id }),
      setMeta: (patch) => set((s) => ({ meta: { ...s.meta, ...patch } })),
      loadGraph: (nodes, edges, meta) =>
        set((s) => ({ nodes, edges, meta: meta ?? s.meta, selectedId: null })),
      clear: () => set({ nodes: [], edges: [], selectedId: null }),
    }),
    { name: "iiot.project", partialize: (s) => ({ nodes: s.nodes, edges: s.edges, meta: s.meta }) },
  ),
);
