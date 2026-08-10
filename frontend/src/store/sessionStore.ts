/**
 * Store de sesión (Zustand + persistencia local).
 *
 * Persiste en `localStorage` lo mínimo para retomar la sesión: token, usuario y
 * el último `project_id` abierto. El token es de sesión (firmado por el backend);
 * en air-gapped/dev no hay usuarios y el token queda vacío (auth opt-in, §3.6).
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { RoleGlobal } from "../api/types";

interface SessionStore {
  token: string | null;
  username: string | null;
  role: RoleGlobal | null;
  projectId: string;
  setSession: (token: string, username: string, role: RoleGlobal) => void;
  clearSession: () => void;
  setProjectId: (projectId: string) => void;
}

/** El operador/cliente entra en modo visor (solo-lectura); el resto, al editor. */
export function isViewerRole(role: RoleGlobal | null): boolean {
  return role === "client" || role === "operator" || role === "viewer";
}

export const useSessionStore = create<SessionStore>()(
  persist(
    (set) => ({
      token: null,
      username: null,
      role: null,
      projectId: "default",
      setSession: (token, username, role) => set({ token, username, role }),
      clearSession: () => set({ token: null, username: null, role: null }),
      setProjectId: (projectId) => set({ projectId }),
    }),
    { name: "iiot.session" },
  ),
);
