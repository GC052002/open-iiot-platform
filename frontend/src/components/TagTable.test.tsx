import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { TagTable } from "./TagTable";
import { useConnectionStore } from "../store/connectionStore";
import { useTagStore } from "../store/tagStore";

afterEach(() => {
  cleanup();
  useConnectionStore.setState({ status: "idle", rows: [], error: null });
  useTagStore.setState({ tags: {}, dropped: 0 });
});

describe("<TagTable>", () => {
  it("muestra el vacío sin tags", () => {
    render(<TagTable />);
    expect(screen.getByText(/Sin tags/i)).toBeTruthy();
  });

  it("pinta nombre del snapshot REST y el valor en vivo del WS", () => {
    useConnectionStore.setState({
      rows: [{ id: "t0", name: "Nivel", value: null, quality: "bad" }],
    });
    useTagStore.getState().applyUpdate([
      { tag_id: "t0", value: 42.5, quality: "good", ts: "2026-08-02T00:00:00Z" },
    ]);
    render(<TagTable />);
    expect(screen.getByText("Nivel")).toBeTruthy();
    expect(screen.getByText("42.50")).toBeTruthy();
    expect(screen.getByText("good")).toBeTruthy();
  });
});
