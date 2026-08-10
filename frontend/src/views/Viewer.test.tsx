import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("../api/rest", async (orig) => ({
  ...(await orig<typeof import("../api/rest")>()),
  getProject: vi.fn(),
}));

vi.mock("../api/connection", () => ({
  connection: { connect: vi.fn(), disconnect: vi.fn(), write: vi.fn(() => true) },
}));

import * as rest from "../api/rest";
import { connection } from "../api/connection";
import { Viewer, toCsv } from "./Viewer";
import { useSessionStore } from "../store/sessionStore";
import type { Project } from "../api/types";

const PROJECT: Project = {
  schema_version: "1",
  project_id: "P",
  name: "Planta",
  nodes: [
    { id: "w1", label: "Tanque", type: "widget", position: { x: 0, y: 0 }, widget: "tank",
      props: { tag_id: "t0", min: 0, max: 100 } },
  ],
  edges: [],
  tags: [
    { id: "t0", name: "Nivel", driver_id: "d1", address: "0", data_type: "float",
      deadband: 0, deadband_mode: "abs", writable: false },
    { id: "sp", name: "Consigna", driver_id: "d1", address: "1", data_type: "float",
      deadband: 0, deadband_mode: "abs", writable: true, unit: "°C" },
  ],
  alarms: [],
};

beforeEach(() => {
  useSessionStore.setState({ token: "tok", username: "op", role: "operator" });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("toCsv", () => {
  it("serializa filas y escapa comas/comillas", () => {
    const csv = toCsv([{ id: "t0", name: "a,b", value: 1, unit: "", quality: "good", ts: "x" }]);
    expect(csv.split("\n")[0]).toBe("id,name,value,unit,quality,ts");
    expect(csv).toContain('"a,b"');
  });
});

describe("<Viewer>", () => {
  it("conecta en vivo y pinta los widgets (solo-lectura)", async () => {
    vi.mocked(rest.getProject).mockResolvedValue(PROJECT);
    render(<Viewer projectId="P" />);
    expect(await screen.findByText("Planta")).toBeTruthy();
    expect(screen.getByText("Tanque")).toBeTruthy();
    expect(connection.connect).toHaveBeenCalledWith("P", expect.anything());
    // No hay paleta ni toolbar de edición en el visor.
    expect(screen.queryByText(/Añadir tag/)).toBeNull();
  });

  it("un setpoint writable dispara connection.write", async () => {
    vi.mocked(rest.getProject).mockResolvedValue(PROJECT);
    render(<Viewer projectId="P" />);
    await screen.findByText("Setpoints");
    fireEvent.change(screen.getByLabelText("setpoint sp"), { target: { value: "55" } });
    fireEvent.click(screen.getByText("Enviar"));
    await waitFor(() =>
      expect(connection.write).toHaveBeenCalledWith("sp", 55, expect.anything()),
    );
  });
});
