/**
 * Login opcional. El backend es auth **opt-in** (§3.6): sin `IIOT_USERS` los
 * endpoints están abiertos y no hace falta iniciar sesión. Si hay usuarios, aquí
 * se obtiene el token (`POST /login`) que luego viaja en REST (Bearer) y en el
 * handshake WS (`?token=`).
 */

import { useState } from "react";
import { ApiError, login } from "../api/rest";
import { useSessionStore } from "../store/sessionStore";

export function LoginBar() {
  const { token, username, setSession, clearSession } = useSessionStore();
  const [user, setUser] = useState("");
  const [pass, setPass] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onLogin() {
    setBusy(true);
    setError(null);
    try {
      const tok = await login(user, pass);
      setSession(tok, user);
      setPass("");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "error de login");
    } finally {
      setBusy(false);
    }
  }

  if (token) {
    return (
      <div className="login-bar">
        <span className="conn-note">👤 {username ?? "sesión"}</span>
        <button className="sec" onClick={clearSession}>
          Salir
        </button>
      </div>
    );
  }

  return (
    <div className="login-bar" style={{ display: "flex", gap: 8, alignItems: "center" }}>
      <input
        aria-label="usuario"
        placeholder="usuario"
        value={user}
        size={12}
        onChange={(e) => setUser(e.target.value)}
      />
      <input
        aria-label="contraseña"
        placeholder="contraseña"
        type="password"
        value={pass}
        size={12}
        onChange={(e) => setPass(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && onLogin()}
      />
      <button onClick={onLogin} disabled={busy || !user}>
        Entrar
      </button>
      {error && <span className="conn-error">{error}</span>}
    </div>
  );
}
