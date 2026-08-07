import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { WidgetBody, tankFillPct, valveState } from "./widgets";
import { useTagStore } from "../store/tagStore";

afterEach(() => {
  cleanup();
  useTagStore.setState({ tags: {}, dropped: 0 });
});

describe("tankFillPct", () => {
  it("mapea el valor al rango [min,max] y satura en 0..100", () => {
    expect(tankFillPct(50, 0, 100)).toBe(50);
    expect(tankFillPct(0, 0, 100)).toBe(0);
    expect(tankFillPct(150, 0, 100)).toBe(100);
    expect(tankFillPct(-10, 0, 100)).toBe(0);
    expect(tankFillPct(5, 0, 10)).toBe(50);
  });
  it("no numérico o rango degenerado → 0", () => {
    expect(tankFillPct("x", 0, 100)).toBe(0);
    expect(tankFillPct(5, 10, 10)).toBe(0);
  });
});

describe("valveState", () => {
  it("interpreta booleanos, números y strings", () => {
    expect(valveState(true)).toBe("open");
    expect(valveState(false)).toBe("closed");
    expect(valveState(1)).toBe("open");
    expect(valveState(0)).toBe("closed");
    expect(valveState(5, 3)).toBe("open");
    expect(valveState(2, 3)).toBe("closed");
    expect(valveState("open")).toBe("open");
    expect(valveState("cerrada")).toBe("closed");
  });
  it("null/undefined → unknown", () => {
    expect(valveState(null)).toBe("unknown");
    expect(valveState(undefined)).toBe("unknown");
  });
});

describe("<WidgetBody> binding en vivo", () => {
  it("sin tag_id muestra 'sin binding'", () => {
    render(<WidgetBody subtype="tank" params={{ tag_id: "" }} />);
    expect(screen.getByText(/sin binding/i)).toBeTruthy();
  });

  it("el tanque refleja el valor en vivo del tagStore", () => {
    useTagStore.getState().applyUpdate([
      { tag_id: "nivel", value: 73, quality: "good", ts: "2026-08-07T00:00:00Z" },
    ]);
    const { container } = render(
      <WidgetBody subtype="tank" params={{ tag_id: "nivel", min: 0, max: 100 }} />,
    );
    expect(screen.getByText("73")).toBeTruthy();
    const fill = container.querySelector(".wg-tank-fill") as HTMLElement;
    expect(fill.style.height).toBe("73%");
  });

  it("la válvula muestra ABIERTA/CERRADA según el valor", () => {
    useTagStore.getState().applyUpdate([
      { tag_id: "v1", value: true, quality: "good", ts: "2026-08-07T00:00:00Z" },
    ]);
    render(<WidgetBody subtype="valve" params={{ tag_id: "v1", open_value: 1 }} />);
    expect(screen.getByText("ABIERTA")).toBeTruthy();
  });
});
