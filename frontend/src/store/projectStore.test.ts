import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { debouncedStorage, sanitizeNodes, useProjectStore } from "./projectStore";
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

describe("sanitizeNodes (Rev 14)", () => {
  it("descarta estado transitorio de React Flow, conserva dominio", () => {
    const n = { ...createNode(DRV, { x: 3, y: 4 }, "n1"), selected: true, dragging: true, width: 120 };
    const [clean] = sanitizeNodes([n as never]);
    expect(clean).toEqual({ id: "n1", type: "driver", position: { x: 3, y: 4 }, data: n.data });
    expect("selected" in clean).toBe(false);
    expect("dragging" in clean).toBe(false);
  });
});

describe("debouncedStorage (Rev 14)", () => {
  afterEach(() => vi.useRealTimers());

  it("agrupa escrituras y sólo vuelca tras el periodo de calma", () => {
    vi.useFakeTimers();
    const store: Record<string, string> = {};
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => {
        store[k] = v;
      },
      removeItem: (k: string) => {
        delete store[k];
      },
    });
    const s = debouncedStorage(500);
    s.setItem("k", "1");
    s.setItem("k", "2");
    s.setItem("k", "3");
    expect(store.k).toBeUndefined(); // aún no volcó
    vi.advanceTimersByTime(500);
    expect(store.k).toBe("3"); // una sola escritura, la última
    vi.unstubAllGlobals();
  });
});
