/**
 * Estado de la conexión al backend (Zustand): status del WS, filas de tags del
 * snapshot REST inicial y último error. La UI lee de aquí; el `ConnectionController`
 * (api/connection.ts) escribe.
 */

import { create } from "zustand";
import type { TagRow } from "../api/types";
import type { WsStatus } from "../api/ws";

interface ConnectionStore {
  status: WsStatus;
  rows: TagRow[]; // orden/metadatos de los tags (nombre) del snapshot REST
  error: string | null;
  setStatus: (status: WsStatus) => void;
  setRows: (rows: TagRow[]) => void;
  setError: (error: string | null) => void;
}

export const useConnectionStore = create<ConnectionStore>((set) => ({
  status: "idle",
  rows: [],
  error: null,
  setStatus: (status) => set({ status }),
  setRows: (rows) => set({ rows }),
  setError: (error) => set({ error }),
}));
