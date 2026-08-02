import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, authHeaders, listTags, login } from "./rest";

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
  it("devuelve el token del backend", async () => {
    mockFetch(200, { token: "abc" });
    await expect(login("u", "p")).resolves.toBe("abc");
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
