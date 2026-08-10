/**
 * Gestión de usuarios (F4.0) — solo `admin`.
 *
 * Lista/crea/activa/desactiva/borra usuarios vía `/users`. La autorización real es
 * del backend (`user:manage`); aquí solo se pinta para el admin. Reutiliza el token
 * de la sesión.
 */

import { useCallback, useEffect, useState } from "react";
import { ApiError, createUser, deleteUser, listUsers, setUserActive } from "../api/rest";
import type { RoleGlobal, UserInfo } from "../api/types";
import { useSessionStore } from "../store/sessionStore";

const ROLES: RoleGlobal[] = ["admin", "engineer", "client"];

export function UsersPanel() {
  const token = useSessionStore((s) => s.token);
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [form, setForm] = useState({ username: "", password: "", role: "client" as RoleGlobal });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setUsers(await listUsers(token));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "error al listar usuarios");
    }
  }, [token]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function onCreate() {
    if (!form.username || !form.password) return setError("usuario y contraseña requeridos");
    setBusy(true);
    try {
      await createUser(form.username.trim(), form.password, form.role, token);
      setForm({ username: "", password: "", role: "client" });
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "error al crear usuario");
    } finally {
      setBusy(false);
    }
  }

  async function onToggleActive(u: UserInfo) {
    try {
      await setUserActive(u.username, !u.active, token);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "error al actualizar");
    }
  }

  async function onDelete(username: string) {
    try {
      await deleteUser(username, token);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "error al borrar");
    }
  }

  return (
    <div className="users-panel">
      <table className="users-table" aria-label="usuarios">
        <thead>
          <tr>
            <th>Usuario</th>
            <th>Rol</th>
            <th>Estado</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.username} className={u.active ? "" : "user-inactive"}>
              <td>{u.username}</td>
              <td>{u.role}</td>
              <td>{u.active ? "activo" : "inactivo"}</td>
              <td className="users-actions">
                <button className="sec" onClick={() => onToggleActive(u)}>
                  {u.active ? "Desactivar" : "Activar"}
                </button>
                <button className="sec danger" onClick={() => onDelete(u.username)}>
                  ✕
                </button>
              </td>
            </tr>
          ))}
          {users.length === 0 && (
            <tr>
              <td colSpan={4} className="conn-note">
                Sin usuarios.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <div className="user-add">
        <div className="side-title">Nuevo usuario</div>
        <input
          aria-label="nuevo usuario"
          placeholder="usuario"
          value={form.username}
          onChange={(e) => setForm({ ...form, username: e.target.value })}
        />
        <input
          aria-label="nueva contraseña"
          placeholder="contraseña"
          type="password"
          value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })}
        />
        <select
          aria-label="nuevo rol"
          value={form.role}
          onChange={(e) => setForm({ ...form, role: e.target.value as RoleGlobal })}
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <button onClick={onCreate} disabled={busy}>
          + Crear usuario
        </button>
        {error && <div className="conn-error">⚠ {error}</div>}
      </div>
    </div>
  );
}
