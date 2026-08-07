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
import { createJSONStorage, persist, type StateStorage } from "zustand/middleware";
import type { AppNode, EditorNodeData } from "../editor/model";

/**
 * Persiste sólo los campos de dominio del nodo, descartando el estado transitorio
 * de React Flow (`selected`, `dragging`, `measured`, `width`/`height`…). Rev 14
 * (MEDIA): si no, al recargar un nodo podía quedar bloqueado como "seleccionado".
 */
export function sanitizeNodes(nodes: AppNode[]): AppNode[] {
  return nodes.map((n) => ({ id: n.id, type: n.type, position: n.position, data: n.data }));
}

/**
 * Storage con debounce sobre localStorage. Rev 14 (BLOCKER): React Flow emite un
 * cambio por cada píxel de arrastre; escribir en localStorage síncronamente en cada
 * uno congela el navegador. Agrupamos las escrituras y volcamos tras `ms` de calma.
 */
export function debouncedStorage(ms = 500): StateStorage {
  const pending = new Map<string, string>();
  let timer: ReturnType<typeof setTimeout> | null = null;
  const flush = () => {
    timer = null;
    for (const [k, v] of pending) localStorage.setItem(k, v);
    pending.clear();
  };
  return {
    getItem: (key) => localStorage.getItem(key),
    setItem: (key, value) => {
      pending.set(key, value);
      if (timer) clearTimeout(timer);
      timer = setTimeout(flush, ms);
    },
    removeItem: (key) => {
      pending.delete(key);
      localStorage.removeItem(key);
    },
  };
}

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
    {
      name: "iiot.project",
      storage: createJSONStorage(() => debouncedStorage(500)),
      partialize: (s) => ({ nodes: sanitizeNodes(s.nodes), edges: s.edges, meta: s.meta }),
    },
  ),
);
