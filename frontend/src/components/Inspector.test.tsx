import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Inspector } from "./Inspector";
import { useProjectStore } from "../store/projectStore";
import { createNode, type PaletteItem } from "../editor/model";

const DRV: PaletteItem = { kind: "driver", subtype: "modbus_tcp", label: "Modbus", icon: "🔌" };

afterEach(() => {
  cleanup();
  useProjectStore.getState().clear();
});

describe("<Inspector>", () => {
  it("muestra el vacío sin selección", () => {
    render(<Inspector />);
    expect(screen.getByText(/Selecciona un nodo/i)).toBeTruthy();
  });

  it("edita la etiqueta y la refleja en el store", () => {
    useProjectStore.getState().addNode(createNode(DRV, { x: 0, y: 0 }, "n1")); // auto-selecciona
    render(<Inspector />);
    const label = screen.getByDisplayValue("Modbus");
    fireEvent.change(label, { target: { value: "PLC-1" } });
    expect(useProjectStore.getState().nodes[0].data.label).toBe("PLC-1");
  });

  it("cambiar el subtipo reinicia los params a los del nuevo tipo", () => {
    useProjectStore.getState().addNode(createNode(DRV, { x: 0, y: 0 }, "n1"));
    render(<Inspector />);
    const select = screen.getByDisplayValue("Modbus TCP");
    fireEvent.change(select, { target: { value: "s7" } });
    const data = useProjectStore.getState().nodes[0].data;
    expect(data.subtype).toBe("s7");
    expect(data.params).toMatchObject({ rack: 0, slot: 1 });
  });

  it("edita un parámetro numérico conservando el tipo", () => {
    useProjectStore.getState().addNode(createNode(DRV, { x: 0, y: 0 }, "n1"));
    render(<Inspector />);
    const portInput = screen.getByDisplayValue("502");
    fireEvent.change(portInput, { target: { value: "5020" } });
    expect(useProjectStore.getState().nodes[0].data.params.port).toBe(5020);
  });
});
