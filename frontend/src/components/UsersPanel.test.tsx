import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("../api/rest", async (orig) => ({
  ...(await orig<typeof import("../api/rest")>()),
  listUsers: vi.fn(),
  createUser: vi.fn(),
  setUserActive: vi.fn(),
  deleteUser: vi.fn(),
}));

import * as rest from "../api/rest";
import { UsersPanel } from "./UsersPanel";
import { useSessionStore } from "../store/sessionStore";

beforeEach(() => {
  useSessionStore.setState({ token: "tok", username: "admin", role: "admin" });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("<UsersPanel>", () => {
  it("lista los usuarios del backend", async () => {
    vi.mocked(rest.listUsers).mockResolvedValue([
      { username: "admin", role: "admin", active: true },
      { username: "cli", role: "client", active: false },
    ]);
    render(<UsersPanel />);
    expect(await screen.findByText("admin")).toBeTruthy();
    expect(screen.getByText("cli")).toBeTruthy();
    expect(screen.getByText("inactivo")).toBeTruthy();
  });

  it("crea un usuario con el rol elegido", async () => {
    vi.mocked(rest.listUsers).mockResolvedValue([]);
    vi.mocked(rest.createUser).mockResolvedValue({ username: "u", role: "engineer", active: true });
    render(<UsersPanel />);
    await waitFor(() => expect(rest.listUsers).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText("nuevo usuario"), { target: { value: "u" } });
    fireEvent.change(screen.getByLabelText("nueva contraseña"), { target: { value: "pw" } });
    fireEvent.change(screen.getByLabelText("nuevo rol"), { target: { value: "engineer" } });
    fireEvent.click(screen.getByText(/Crear usuario/));

    await waitFor(() =>
      expect(rest.createUser).toHaveBeenCalledWith("u", "pw", "engineer", expect.anything()),
    );
  });
});
