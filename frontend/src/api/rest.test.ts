import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  addMember,
  authHeaders,
  createUser,
  listProjects,
  listTags,
  login,
  publishProject,
} from "./rest";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("authHeaders", () => {
  it("incluye Content-Type siempre y Bearer sólo con token", () => {
    expect(authHeaders()).toEqual({ "Content-Type": "application/json" });
    expect(authHeaders("tok")).toEqual({
      "Content-Type": "application/json",
      Authorization: "Bearer tok",
    });
  });
});

function mockFetch(status: number, body: unknown) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: "x",
    json: async () => body,
  } as Response);
}

describe("login", () => {
  it("devuelve token, usuario y rol del backend", async () => {
    mockFetch(200, { token: "abc", username: "u", role: "engineer" });
    await expect(login("u", "p")).resolves.toEqual({
      token: "abc",
      username: "u",
      role: "engineer",
    });
  });

  it("lanza ApiError con el detalle en fallo", async () => {
    mockFetch(401, { detail: "credenciales inválidas" });
    await expect(login("u", "p")).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
      detail: "credenciales inválidas",
    });
  });
});

describe("endpoints F4 (identidad/proyectos)", () => {
  it("listProjects hace GET /projects con el token", async () => {
    const spy = mockFetch(200, [{ project_id: "P", name: "P" }]);
    await expect(listProjects("tok")).resolves.toEqual([{ project_id: "P", name: "P" }]);
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe("/projects");
    expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });

  it("createUser hace POST /users con el cuerpo correcto", async () => {
    const spy = mockFetch(200, { username: "cli", role: "client", active: true });
    await createUser("cli", "pw", "client", "tok");
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe("/users");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      username: "cli",
      password: "pw",
      role: "client",
    });
  });

  it("addMember codifica el project_id y envía role_proj", async () => {
    const spy = mockFetch(200, { username: "u", role_proj: "viewer" });
    await addMember("planta a", "u", "viewer", "tok");
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe("/projects/planta%20a/members");
    expect(JSON.parse(init?.body as string)).toEqual({ username: "u", role_proj: "viewer" });
  });

  it("publishProject hace POST /projects/{id}/publish", async () => {
    const spy = mockFetch(200, { project_id: "P", delivery_version: 3 });
    await expect(publishProject("P", "tok")).resolves.toEqual({
      project_id: "P",
      delivery_version: 3,
    });
    expect(spy.mock.calls[0][0]).toBe("/projects/P/publish");
  });
});

describe("listTags", () => {
  it("codifica el project_id en la query", async () => {
    const spy = mockFetch(200, []);
    await listTags("planta demo", "tok");
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe("/tags?project_id=planta%20demo");
    expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });
});

describe("ApiError", () => {
  it("compone un mensaje legible", () => {
    expect(new ApiError(404, "no encontrado").message).toBe("HTTP 404: no encontrado");
  });
});
