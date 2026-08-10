/**
 * Gestor de proyectos (F4.1/F4.1b).
 *
 * Lista los proyectos visibles (el backend ya filtra por membresía), permite
 * **abrir** uno en el editor (`GET /projects/{id}` → `loadGraph`), gestionar sus
 * **miembros** (`/members`) y **publicar** una entrega inmutable (`/publish`).
 */

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  addMember,
  getProject,
  listMembers,
  listProjects,
  publishProject,
  removeMember,
} from "../api/rest";
import type { Member, ProjectSummary, RoleProj } from "../api/types";
import { fromProjectEdge, fromProjectNode } from "../editor/mapping";
import { useProjectStore } from "../store/projectStore";
import { useSessionStore } from "../store/sessionStore";

const PROJ_ROLES: RoleProj[] = ["viewer", "operator", "editor", "owner"];

export function ProjectsPanel() {
  const token = useSessionStore((s) => s.token);
  const setProjectId = useSessionStore((s) => s.setProjectId);
  const loadGraph = useProjectStore((s) => s.loadGraph);

  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [memberForm, setMemberForm] = useState({ username: "", role: "viewer" as RoleProj });
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setProjects(await listProjects(token));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "error al listar proyectos");
    }
  }, [token]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const loadMembers = useCallback(
    async (projectId: string) => {
      try {
        setMembers(await listMembers(projectId, token));
      } catch {
        setMembers([]);
      }
    },
    [token],
  );

  async function onSelect(projectId: string) {
    setSelected(projectId);
    setNote(null);
    await loadMembers(projectId);
  }

  async function onOpen(projectId: string) {
    try {
      const p = await getProject(projectId, token);
      loadGraph(
        p.nodes.map(fromProjectNode),
        p.edges.map(fromProjectEdge),
        p.tags,
        { project_id: p.project_id, name: p.name },
      );
      setProjectId(projectId);
      setNote(`Proyecto '${p.name}' abierto en el editor.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "error al abrir el proyecto");
    }
  }

  async function onPublish(projectId: string) {
    try {
      const res = await publishProject(projectId, token);
      setNote(`Publicada la versión de entrega v${res.delivery_version}.`);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "error al publicar");
    }
  }

  async function onAddMember() {
    if (!selected || !memberForm.username) return;
    try {
      await addMember(selected, memberForm.username.trim(), memberForm.role, token);
      setMemberForm({ username: "", role: "viewer" });
      await loadMembers(selected);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "error al añadir miembro");
    }
  }

  async function onRemoveMember(username: string) {
    if (!selected) return;
    try {
      await removeMember(selected, username, token);
      await loadMembers(selected);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "error al quitar miembro");
    }
  }

  return (
    <div className="projects-panel">
      <ul className="projects-list" aria-label="proyectos">
        {projects.map((p) => (
          <li key={p.project_id} className={selected === p.project_id ? "sel" : ""}>
            <button className="proj-name" onClick={() => onSelect(p.project_id)}>
              {p.name ?? p.project_id}
              {p.delivery_version ? <span className="proj-ver"> v{p.delivery_version}</span> : null}
            </button>
            <span className="proj-actions">
              <button className="sec" onClick={() => onOpen(p.project_id)}>
                Abrir
              </button>
              <button className="sec" onClick={() => onPublish(p.project_id)}>
                Publicar
              </button>
            </span>
          </li>
        ))}
        {projects.length === 0 && <li className="conn-note">Sin proyectos.</li>}
      </ul>

      {selected && (
        <div className="members-box">
          <div className="side-title">Miembros de «{selected}»</div>
          <ul className="members-list" aria-label="miembros">
            {members.map((m) => (
              <li key={m.username}>
                <span>
                  {m.username} — <em>{m.role_proj}</em>
                </span>
                <button className="sec danger" onClick={() => onRemoveMember(m.username)}>
                  ✕
                </button>
              </li>
            ))}
          </ul>
          <div className="member-add">
            <input
              aria-label="nuevo miembro"
              placeholder="usuario"
              value={memberForm.username}
              onChange={(e) => setMemberForm({ ...memberForm, username: e.target.value })}
            />
            <select
              aria-label="rol de proyecto"
              value={memberForm.role}
              onChange={(e) => setMemberForm({ ...memberForm, role: e.target.value as RoleProj })}
            >
              {PROJ_ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            <button onClick={onAddMember}>+ Añadir</button>
          </div>
        </div>
      )}

      {note && <div className="conn-note">{note}</div>}
      {error && <div className="conn-error">⚠ {error}</div>}
    </div>
  );
}
