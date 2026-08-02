import { describe, expect, it } from "vitest";
import { buildWsUrl, nextBackoffMs, parseServerMessage } from "./ws";

describe("buildWsUrl", () => {
  it("usa ws:// sobre http y omite token cuando no hay", () => {
    expect(buildWsUrl({ protocol: "http:", host: "localhost:8000" })).toBe(
      "ws://localhost:8000/ws",
    );
  });

  it("usa wss:// sobre https", () => {
    expect(buildWsUrl({ protocol: "https:", host: "plant.local" })).toBe("wss://plant.local/ws");
  });

  it("adjunta el token como query param codificado", () => {
    const url = buildWsUrl({ protocol: "http:", host: "h" }, "a b/c");
    expect(url).toBe("ws://h/ws?token=a%20b%2Fc");
  });
});

describe("nextBackoffMs", () => {
  it("crece con el intento pero nunca supera el techo", () => {
    for (let attempt = 0; attempt < 20; attempt++) {
      const d = nextBackoffMs(attempt, 500, 10_000);
      expect(d).toBeGreaterThan(0);
      expect(d).toBeLessThanOrEqual(10_000);
    }
  });
});

describe("parseServerMessage", () => {
  it("acepta los tipos válidos del contrato", () => {
    const msg = parseServerMessage(
      JSON.stringify({ type: "tag_update", values: [] }),
    );
    expect(msg?.type).toBe("tag_update");
  });

  it("rechaza JSON inválido", () => {
    expect(parseServerMessage("no-json{")).toBeNull();
  });

  it("rechaza tipos desconocidos", () => {
    expect(parseServerMessage(JSON.stringify({ type: "subscribe" }))).toBeNull();
  });

  it("rechaza no-objetos", () => {
    expect(parseServerMessage(JSON.stringify(42))).toBeNull();
  });
});
