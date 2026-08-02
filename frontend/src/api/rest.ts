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

import type { AlarmRule, Project, TagRow } from "./types";

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

/** `POST /login` → token de sesión. `null` no aplica: lanza ApiError(401). */
export async function login(username: string, password: string): Promise<string> {
  const body = await request<{ token: string }>("/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  return body.token;
}

/** `GET /projects` → ids de proyectos cargados en el runtime. */
export function listProjects(token?: string | null): Promise<string[]> {
  return request<string[]>("/projects", { token });
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
