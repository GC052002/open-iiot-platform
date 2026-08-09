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
