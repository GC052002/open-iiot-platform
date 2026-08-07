import { beforeEach, describe, expect, it } from "vitest";
import { useProjectStore } from "./projectStore";
import { createNode, type PaletteItem } from "../editor/model";

const DRV: PaletteItem = { kind: "driver", subtype: "modbus_tcp", label: "Modbus", icon: "🔌" };

beforeEach(() => {
  useProjectStore.getState().clear();
  useProjectStore.getState().select(null);
});

describe("projectStore", () => {
  it("addNode agrega y auto-selecciona", () => {
    const n = createNode(DRV, { x: 0, y: 0 }, "n1");
    useProjectStore.getState().addNode(n);
    const s = useProjectStore.getState();
    expect(s.nodes).toHaveLength(1);
    expect(s.selectedId).toBe("n1");
  });

  it("updateNodeData mergea sin pisar params", () => {
    useProjectStore.getState().addNode(createNode(DRV, { x: 0, y: 0 }, "n1"));
    useProjectStore.getState().updateNodeData("n1", { label: "PLC-1" });
    const n = useProjectStore.getState().nodes[0];
    expect(n.data.label).toBe("PLC-1");
    expect(n.data.params).toMatchObject({ host: "127.0.0.1" });
  });

  it("setNodeParams reemplaza el dict de params", () => {
    useProjectStore.getState().addNode(createNode(DRV, { x: 0, y: 0 }, "n1"));
    useProjectStore.getState().setNodeParams("n1", { host: "10.0.0.5", port: 5020 });
    expect(useProjectStore.getState().nodes[0].data.params).toEqual({ host: "10.0.0.5", port: 5020 });
  });

  it("removeNode elimina el nodo, sus edges y deselecciona", () => {
    const a = createNode(DRV, { x: 0, y: 0 }, "a");
    const b = createNode(DRV, { x: 1, y: 1 }, "b");
    const st = useProjectStore.getState();
    st.addNode(a);
    st.addNode(b);
    st.onConnect({ source: "a", target: "b", sourceHandle: null, targetHandle: null });
    expect(useProjectStore.getState().edges).toHaveLength(1);
    useProjectStore.getState().select("a");
    useProjectStore.getState().removeNode("a");
    const s = useProjectStore.getState();
    expect(s.nodes.map((n) => n.id)).toEqual(["b"]);
    expect(s.edges).toHaveLength(0);
    expect(s.selectedId).toBeNull();
  });

  it("onConnect crea un edge entre dos nodos", () => {
    const st = useProjectStore.getState();
    st.addNode(createNode(DRV, { x: 0, y: 0 }, "a"));
    st.addNode(createNode(DRV, { x: 1, y: 1 }, "b"));
    st.onConnect({ source: "a", target: "b", sourceHandle: null, targetHandle: null });
    const e = useProjectStore.getState().edges[0];
    expect(e).toMatchObject({ source: "a", target: "b" });
  });
});
