/**
 * Store de sesión (Zustand + persistencia local).
 *
 * Persiste en `localStorage` lo mínimo para retomar la sesión: token, usuario y
 * el último `project_id` abierto. El token es de sesión (firmado por el backend);
 * en air-gapped/dev no hay usuarios y el token queda vacío (auth opt-in, §3.6).
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface SessionStore {
  token: string | null;
  username: string | null;
  projectId: string;
  setSession: (token: string, username: string) => void;
  clearSession: () => void;
  setProjectId: (projectId: string) => void;
}

export const useSessionStore = create<SessionStore>()(
  persist(
    (set) => ({
      token: null,
      username: null,
      projectId: "default",
      setSession: (token, username) => set({ token, username }),
      clearSession: () => set({ token: null, username: null }),
      setProjectId: (projectId) => set({ projectId }),
    }),
    { name: "iiot.session" },
  ),
);
