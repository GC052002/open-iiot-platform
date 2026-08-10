import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("../api/rest", async (orig) => ({
  ...(await orig<typeof import("../api/rest")>()),
  listProjects: vi.fn(),
  listMembers: vi.fn(),
  publishProject: vi.fn(),
  getProject: vi.fn(),
}));

import * as rest from "../api/rest";
import { ProjectsPanel } from "./ProjectsPanel";
import { useProjectStore } from "../store/projectStore";
import { useSessionStore } from "../store/sessionStore";

beforeEach(() => {
  useSessionStore.setState({ token: "tok", username: "eng", role: "engineer" });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("<ProjectsPanel>", () => {
  it("lista proyectos y publica una entrega", async () => {
    vi.mocked(rest.listProjects).mockResolvedValue([
      { project_id: "P", name: "Planta", delivery_version: 1 },
    ]);
    vi.mocked(rest.publishProject).mockResolvedValue({ project_id: "P", delivery_version: 2 });
    render(<ProjectsPanel />);

    expect(await screen.findByText("Planta")).toBeTruthy();
    fireEvent.click(screen.getByText("Publicar"));
    await waitFor(() => expect(rest.publishProject).toHaveBeenCalledWith("P", expect.anything()));
  });

  it("abre un proyecto en el editor (loadGraph)", async () => {
    vi.mocked(rest.listProjects).mockResolvedValue([{ project_id: "P", name: "Planta" }]);
    vi.mocked(rest.getProject).mockResolvedValue({
      schema_version: "1",
      project_id: "P",
      name: "Planta",
      nodes: [],
      edges: [],
      tags: [
        {
          id: "t0",
          name: "Nivel",
          driver_id: "d1",
          address: "0",
          data_type: "float",
          deadband: 0,
          deadband_mode: "abs",
        },
      ],
      alarms: [],
    });
    render(<ProjectsPanel />);
    await screen.findByText("Planta");
    fireEvent.click(screen.getByText("Abrir"));

    await waitFor(() => expect(useProjectStore.getState().tags).toHaveLength(1));
    expect(useProjectStore.getState().meta.project_id).toBe("P");
  });
});
