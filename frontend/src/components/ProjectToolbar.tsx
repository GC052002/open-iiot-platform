/**
 * Toolbar del proyecto (F3.3): nombre/id del diseño, contadores, y acciones
 * **exportar** (descarga JSON), **importar** (carga JSON) y **enviar al backend**
 * (`POST /projects` + conectar), cerrando el lazo diseño → datos en vivo.
 */

import { useRef, useState } from "react";
import { ApiError, createProject } from "../api/rest";
import { connection } from "../api/connection";
import { buildProject } from "../editor/mapping";
import { deserializeProject, downloadJSON, readFileText, serializeProject } from "../editor/projectIO";
import { useProjectStore } from "../store/projectStore";
import { useSessionStore } from "../store/sessionStore";

export function ProjectToolbar() {
  const { nodes, edges, tags, meta, setMeta, loadGraph } = useProjectStore();
  const token = useSessionStore((s) => s.token);
  const setProjectId = useSessionStore((s) => s.setProjectId);
  const fileRef = useRef<HTMLInputElement>(null);
  const sendingRef = useRef(false); // Rev 15: guard síncrono anti doble-clic
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function onExport() {
    downloadJSON(`${meta.project_id || "proyecto"}.json`, serializeProject(meta, nodes, edges, tags));
  }

  async function onImportFile(file: File) {
    setErr(null);
    setMsg(null);
    try {
      const g = deserializeProject(await readFileText(file));
      loadGraph(g.nodes, g.edges, g.tags, g.meta);
      setMsg(`importado: ${g.nodes.length} nodos, ${g.tags.length} tags`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "no se pudo importar");
    }
  }

  async function onSend() {
    // Rev 15 (BLOCKER): el `disabled={busy}` se aplica en el próximo render; un
    // doble-clic muy rápido podría colar dos POST. El ref bloquea la reentrada
    // de forma síncrona → nunca se arrancan dos runtimes por doble-clic.
    if (sendingRef.current) return;
    sendingRef.current = true;
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const project = buildProject(meta, nodes, edges, tags);
      const res = await createProject(project, token);
      setMsg(`enviado: ${res.project_id} (${res.tags} tags). Conectando…`);
      setProjectId(res.project_id);
      await connection.connect(res.project_id, token);
    } catch (e) {
      setErr(e instanceof ApiError ? `backend: ${e.detail}` : e instanceof Error ? e.message : "error");
    } finally {
      sendingRef.current = false;
      setBusy(false);
    }
  }

  return (
    <div className="editor-toolbar">
      <label>
        Diseño
        <input value={meta.name} size={16} onChange={(e) => setMeta({ name: e.target.value })} />
      </label>
      <label>
        id
        <input
          value={meta.project_id}
          size={12}
          onChange={(e) => setMeta({ project_id: e.target.value })}
        />
      </label>
      <span className="conn-note">
        {nodes.length} nodos · {edges.length} conexiones · {tags.length} tags
      </span>
      <span className="spacer" />
      <button className="sec" onClick={onExport}>
        Exportar
      </button>
      <button className="sec" onClick={() => fileRef.current?.click()}>
        Importar
      </button>
      <button onClick={onSend} disabled={busy}>
        Enviar al backend
      </button>
      <input
        ref={fileRef}
        type="file"
        accept="application/json,.json"
        style={{ display: "none" }}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onImportFile(f);
          e.target.value = ""; // permite re-importar el mismo archivo
        }}
      />
      {msg && <span className="conn-note">{msg}</span>}
      {err && <span className="conn-error">⚠ {err}</span>}
    </div>
  );
}
