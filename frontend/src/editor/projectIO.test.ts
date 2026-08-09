import { describe, expect, it } from "vitest";
import { deserializeProject, serializeProject } from "./projectIO";
import { createNode } from "./model";
import type { Tag } from "../api/types";

const meta = { project_id: "planta_demo", name: "Planta Demo" };
const node = createNode(
  { kind: "driver", subtype: "modbus_tcp", label: "Modbus", icon: "🔌" },
  { x: 10, y: 20 },
  "plc1",
);
const edge = { id: "e1", source: "plc1", target: "w1" };
const tag: Tag = {
  id: "nivel",
  name: "Nivel",
  driver_id: "plc1",
  address: "0",
  data_type: "int",
  unit: null,
  deadband: 0,
  deadband_mode: "abs",
};

describe("serialize/deserialize project (F3.3)", () => {
  it("round-trip preserva nodos, edges, tags y meta", () => {
    const json = serializeProject(meta, [node], [edge], [tag]);
    const g = deserializeProject(json);
    expect(g.meta).toEqual(meta);
    expect(g.nodes).toEqual([node]);
    expect(g.edges).toEqual([edge]);
    expect(g.tags).toEqual([tag]);
  });

  it("el JSON exportado tiene schema_version '1' y los tags", () => {
    const obj = JSON.parse(serializeProject(meta, [node], [], [tag]));
    expect(obj.schema_version).toBe("1");
    expect(obj.tags).toHaveLength(1);
    expect(obj.nodes[0]).toMatchObject({ type: "driver", driver_type: "modbus_tcp" });
  });

  it("rechaza JSON inválido con mensaje claro", () => {
    expect(() => deserializeProject("no-json{")).toThrow(/no es JSON/i);
  });

  it("rechaza schema_version no soportada", () => {
    expect(() => deserializeProject(JSON.stringify({ schema_version: "2", name: "x" }))).toThrow(
      /schema_version/i,
    );
  });

  it("rechaza proyecto sin name", () => {
    expect(() => deserializeProject(JSON.stringify({ schema_version: "1" }))).toThrow(/name/i);
  });
});

describe("deserializeProject — endurecido (Rev 15)", () => {
  const base = { schema_version: "1", name: "P", project_id: "p1" };

  it("no contamina Object.prototype con __proto__ malicioso", () => {
    const evil = JSON.stringify({ ...base, ["__proto__"]: { polluted: true } });
    const g = deserializeProject(evil);
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
    expect(g.meta.name).toBe("P");
  });

  it("fuerza address a string al importar", () => {
    const json = JSON.stringify({
      ...base,
      tags: [{ id: "t", driver_id: "d", address: 12345, data_type: "int" }],
    });
    const g = deserializeProject(json);
    expect(g.tags[0].address).toBe("12345");
    expect(typeof g.tags[0].address).toBe("string");
  });

  it("rechaza data_type inválido con mensaje claro", () => {
    const json = JSON.stringify({
      ...base,
      tags: [{ id: "t", driver_id: "d", address: "0", data_type: "real" }],
    });
    expect(() => deserializeProject(json)).toThrow(/data_type inválido/i);
  });

  it("rechaza tag sin driver_id", () => {
    const json = JSON.stringify({ ...base, tags: [{ id: "t", address: "0", data_type: "int" }] });
    expect(() => deserializeProject(json)).toThrow(/driver_id/i);
  });

  it("normaliza name ausente del tag a su id y unit a null", () => {
    const json = JSON.stringify({
      ...base,
      tags: [{ id: "nivel", driver_id: "d", address: "0", data_type: "float" }],
    });
    const t = deserializeProject(json).tags[0];
    expect(t.name).toBe("nivel");
    expect(t.unit).toBeNull();
    expect(t.deadband).toBe(0);
    expect(t.deadband_mode).toBe("abs");
  });
});
