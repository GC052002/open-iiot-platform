/**
 * Resuelve qué proyecto abre el visor (F4.2).
 *
 * El operador entra directo a su entrega: si su `project_id` de sesión no está en la
 * lista visible (o es el "default"), se selecciona el primero accesible. Con varios
 * proyectos, un selector permite cambiar. La lista ya viene filtrada por el backend.
 */

import { useEffect, useState } from "react";
import { listProjects } from "../api/rest";
import type { ProjectSummary } from "../api/types";
import { useSessionStore } from "../store/sessionStore";
import { Viewer } from "./Viewer";

export function ViewerRoute() {
  const token = useSessionStore((s) => s.token);
  const projectId = useSessionStore((s) => s.projectId);
  const setProjectId = useSessionStore((s) => s.setProjectId);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const list = await listProjects(token);
        if (!alive) return;
        setProjects(list);
        const ids = list.map((p) => p.project_id);
        if (list.length > 0 && !ids.includes(projectId)) setProjectId(ids[0]);
      } catch {
        /* sin lista: se usa el project_id de sesión tal cual */
      }
    })();
    return () => {
      alive = false;
    };
    // Solo al montar / cambiar de token: no re-disparar por cada setProjectId.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <div className="viewer-route">
      {projects.length > 1 && (
        <div className="viewer-picker">
          <label>
            Proyecto:{" "}
            <select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              {projects.map((p) => (
                <option key={p.project_id} value={p.project_id}>
                  {p.name ?? p.project_id}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      <Viewer key={projectId} projectId={projectId} />
    </div>
  );
}
