import { describe, expect, it } from "vitest";
import { PALETTE, createNode, defaultParams, type PaletteItem } from "./model";
import { buildProject, fromProjectNode, toProjectNode } from "./mapping";

describe("paleta / createNode", () => {
  it("la paleta tiene los 3 grupos con items", () => {
    expect(PALETTE.map((g) => g.title)).toEqual(["Drivers", "Lógica", "Widgets"]);
    expect(PALETTE.every((g) => g.items.length > 0)).toBe(true);
  });

  it("createNode aplica type=kind y params por defecto", () => {
    const item: PaletteItem = { kind: "driver", subtype: "modbus_tcp", label: "Modbus", icon: "🔌" };
    const n = createNode(item, { x: 10, y: 20 }, "n1");
    expect(n).toMatchObject({
      id: "n1",
      type: "driver",
      position: { x: 10, y: 20 },
      data: { kind: "driver", subtype: "modbus_tcp", label: "Modbus" },
    });
    expect(n.data.params).toEqual({ host: "127.0.0.1", port: 502, unit: 1, polling_rate: 1.0 });
  });

  it("defaultParams del widget incluye binding tag_id vacío", () => {
    expect(defaultParams("widget", "tank")).toEqual({ tag_id: "" });
  });
});

describe("mapping editor ↔ backend", () => {
  it("toProjectNode expande subtype/params al campo correcto por kind", () => {
    const drv = createNode({ kind: "driver", subtype: "s7", label: "S7", icon: "🔌" }, { x: 0, y: 0 }, "d1");
    expect(toProjectNode(drv)).toMatchObject({ type: "driver", driver_type: "s7", config: drv.data.params });

    const wid = createNode({ kind: "widget", subtype: "tank", label: "Tanque", icon: "🛢️" }, { x: 1, y: 2 }, "w1");
    expect(toProjectNode(wid)).toMatchObject({ type: "widget", widget: "tank", props: { tag_id: "" } });
  });

  it("round-trip fromProjectNode(toProjectNode(n)) preserva los campos de dominio", () => {
    const n = createNode({ kind: "logic", subtype: "scale", label: "Escala", icon: "🧮" }, { x: 5, y: 6 }, "l1");
    const back = fromProjectNode(toProjectNode(n));
    expect(back).toEqual(n);
  });

  it("buildProject arma un ProjectV1 con schema_version y nodos mapeados", () => {
    const n = createNode({ kind: "driver", subtype: "mqtt", label: "MQTT", icon: "🔌" }, { x: 0, y: 0 }, "d1");
    const proj = buildProject({ project_id: "p1", name: "Planta" }, [n], []);
    expect(proj.schema_version).toBe("1");
    expect(proj.project_id).toBe("p1");
    expect(proj.nodes).toHaveLength(1);
    expect(proj.nodes[0]).toMatchObject({ type: "driver", driver_type: "mqtt" });
  });
});
