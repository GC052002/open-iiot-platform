/**
 * Cliente REST del backend.
 *
 * URLs relativas: en dev pasan por el proxy de Vite (`vite.config.ts`); en
 * producción el bundle se sirve desde el propio backend, así que el mismo origen
 * sirve API y estáticos (sin CORS, sin hosts hardcodeados → air-gapped friendly).
 *
 * Auth **opt-in** (§3.6): si `IIOT_USERS` no está configurado el backend deja los
 * endpoints abiertos; con token, se envía `Authorization: Bearer <token>`.
 */

import type {
  AlarmRule,
  LoginResult,
  Member,
  Project,
  ProjectSummary,
  RoleGlobal,
  RoleProj,
  TagRow,
  UserInfo,
  VersionInfo,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`HTTP ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

/** Construye las cabeceras, incluyendo el Bearer token si existe. */
export function authHeaders(token?: string | null): HeadersInit {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

async function request<T>(
  path: string,
  init: RequestInit & { token?: string | null } = {},
): Promise<T> {
  const { token, headers, ...rest } = init;
  const res = await fetch(path, {
    ...rest,
    headers: { ...authHeaders(token), ...headers },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      /* respuesta sin cuerpo JSON */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

/** `POST /login` → token + rol global. Lanza ApiError(401) si falla. */
export function login(username: string, password: string): Promise<LoginResult> {
  return request<LoginResult>("/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

/** `GET /projects` → proyectos visibles para el usuario (filtrado por membresía). */
export function listProjects(token?: string | null): Promise<ProjectSummary[]> {
  return request<ProjectSummary[]>("/projects", { token });
}

// -- Gestión de usuarios (admin, F4.0) --------------------------------------

export function listUsers(token?: string | null): Promise<UserInfo[]> {
  return request<UserInfo[]>("/users", { token });
}

export function createUser(
  username: string,
  password: string,
  role: RoleGlobal,
  token?: string | null,
): Promise<UserInfo> {
  return request<UserInfo>("/users", {
    method: "POST",
    body: JSON.stringify({ username, password, role }),
    token,
  });
}

export function setUserActive(
  username: string,
  active: boolean,
  token?: string | null,
): Promise<UserInfo> {
  return request<UserInfo>(`/users/${encodeURIComponent(username)}`, {
    method: "PATCH",
    body: JSON.stringify({ active }),
    token,
  });
}

export function deleteUser(username: string, token?: string | null): Promise<unknown> {
  return request(`/users/${encodeURIComponent(username)}`, { method: "DELETE", token });
}

// -- Miembros de proyecto (F4.1) --------------------------------------------

export function listMembers(projectId: string, token?: string | null): Promise<Member[]> {
  return request<Member[]>(`/projects/${encodeURIComponent(projectId)}/members`, { token });
}

export function addMember(
  projectId: string,
  username: string,
  roleProj: RoleProj,
  token?: string | null,
): Promise<Member> {
  return request<Member>(`/projects/${encodeURIComponent(projectId)}/members`, {
    method: "POST",
    body: JSON.stringify({ username, role_proj: roleProj }),
    token,
  });
}

export function removeMember(
  projectId: string,
  username: string,
  token?: string | null,
): Promise<unknown> {
  return request(
    `/projects/${encodeURIComponent(projectId)}/members/${encodeURIComponent(username)}`,
    { method: "DELETE", token },
  );
}

// -- Publicación / versiones (F4.1b) ----------------------------------------

export function publishProject(
  projectId: string,
  token?: string | null,
): Promise<{ project_id: string; delivery_version: number }> {
  return request(`/projects/${encodeURIComponent(projectId)}/publish`, {
    method: "POST",
    token,
  });
}

export function listVersions(projectId: string, token?: string | null): Promise<VersionInfo[]> {
  return request<VersionInfo[]>(`/projects/${encodeURIComponent(projectId)}/versions`, { token });
}

/** `GET /projects/{id}` → topología completa (para hidratar el canvas). */
export function getProject(projectId: string, token?: string | null): Promise<Project> {
  return request<Project>(`/projects/${encodeURIComponent(projectId)}`, { token });
}

/** `POST /projects` → carga/arranca un proyecto en el backend. */
export function createProject(
  project: Project,
  token?: string | null,
): Promise<{ status: string; project_id: string; tags: number }> {
  return request("/projects", {
    method: "POST",
    body: JSON.stringify(project),
    token,
  });
}

/** `GET /tags?project_id=` → proyección ligera (snapshot inicial para la UI). */
export function listTags(projectId: string, token?: string | null): Promise<TagRow[]> {
  return request<TagRow[]>(`/tags?project_id=${encodeURIComponent(projectId)}`, { token });
}

/** `GET /alarms?project_id=` → alarmas activas. */
export function listAlarms(projectId: string, token?: string | null): Promise<AlarmRule[]> {
  return request<AlarmRule[]>(`/alarms?project_id=${encodeURIComponent(projectId)}`, { token });
}

/** `GET /history` → histórico de un tag (para gráficos de tendencia en F3.2). */
export function getHistory(
  projectId: string,
  tagId: string,
  limit = 1000,
  token?: string | null,
): Promise<Array<Record<string, unknown>>> {
  const q = new URLSearchParams({
    project_id: projectId,
    tag_id: tagId,
    limit: String(limit),
  });
  return request(`/history?${q.toString()}`, { token });
}
