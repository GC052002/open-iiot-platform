/**
 * Barra de conexión: elige `project_id`, conecta/desconecta el WS y muestra el
 * estado (idle/connecting/open/closed) + errores + contador de backpressure.
 */

import { connection } from "../api/connection";
import { useConnectionStore } from "../store/connectionStore";
import { useSessionStore } from "../store/sessionStore";
import { useTagStore } from "../store/tagStore";
import type { WsStatus } from "../api/ws";

const STATUS_LABEL: Record<WsStatus, string> = {
  idle: "desconectado",
  connecting: "conectando…",
  open: "conectado",
  closed: "reconectando…",
};

export function ConnectionBar() {
  const { projectId, setProjectId, token } = useSessionStore();
  const status = useConnectionStore((s) => s.status);
  const error = useConnectionStore((s) => s.error);
  const dropped = useTagStore((s) => s.dropped);

  const connected = status === "open" || status === "connecting" || status === "closed";

  return (
    <div className="conn-bar">
      <label>
        Proyecto
        <input
          aria-label="project_id"
          value={projectId}
          size={16}
          disabled={connected}
          onChange={(e) => setProjectId(e.target.value)}
        />
      </label>
      {!connected ? (
        <button onClick={() => connection.connect(projectId.trim() || "default", token)}>
          Conectar
        </button>
      ) : (
        <button className="sec" onClick={() => connection.disconnect()}>
          Detener
        </button>
      )}
      <span className={`status-pill status-${status}`}>● {STATUS_LABEL[status]}</span>
      {error && <span className="conn-error">⚠ {error}</span>}
      {dropped > 0 && (
        <span className="conn-note">backpressure: {dropped} muestras descartadas</span>
      )}
    </div>
  );
}
