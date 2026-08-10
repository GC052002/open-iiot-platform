/**
 * Visor HMI del cliente (F4.2) — modo **Runtime** solo-lectura, responsive.
 *
 * No es el editor: no hay paleta, canvas editable ni inspector. Carga la topología
 * publicada (`GET /projects/{id}`), se conecta en vivo (WS) y pinta los widgets en
 * una rejilla adaptable (móvil = 1 columna). Los tags marcados `writable` muestran un
 * control de **setpoint**; la escritura se autoriza server-side (`operate`) + audit.
 * Un botón exporta el snapshot visible a CSV.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { connection } from "../api/connection";
import { ApiError, getProject } from "../api/rest";
import type { Project, Tag, WidgetNode } from "../api/types";
import { WidgetBody } from "../editor/widgets";
import { useConnectionStore } from "../store/connectionStore";
import { useSessionStore } from "../store/sessionStore";
import { useTagStore } from "../store/tagStore";

/** Serializa las filas visibles a CSV (id,nombre,valor,unidad,calidad,ts). */
export function toCsv(rows: Array<Record<string, unknown>>): string {
  const cols = ["id", "name", "value", "unit", "quality", "ts"];
  const esc = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const header = cols.join(",");
  const body = rows.map((r) => cols.map((c) => esc(r[c])).join(",")).join("\n");
  return `${header}\n${body}`;
}

export function Viewer({ projectId }: { projectId: string }) {
  const token = useSessionStore((s) => s.token);
  const status = useConnectionStore((s) => s.status);
  const error = useConnectionStore((s) => s.error);
  const [project, setProject] = useState<Project | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const p = await getProject(projectId, token);
        if (alive) setProject(p);
      } catch (err) {
        if (alive) setLoadError(err instanceof ApiError ? err.detail : "error al cargar");
      }
    })();
    connection.connect(projectId, token);
    return () => {
      alive = false;
      connection.disconnect();
    };
  }, [projectId, token]);

  const widgets = useMemo(
    () => (project?.nodes.filter((n) => n.type === "widget") as WidgetNode[]) ?? [],
    [project],
  );
  const writableTags = useMemo(() => (project?.tags ?? []).filter((t) => t.writable), [project]);

  if (loadError) return <div className="conn-error viewer-msg">⚠ {loadError}</div>;
  if (!project) return <div className="conn-note viewer-msg">Cargando…</div>;

  return (
    <div className="viewer">
      <header className="viewer-header">
        <h2>{project.name}</h2>
        <span className={`conn-badge conn-${status}`}>{status}</span>
        <span className="spacer" />
        <ExportButton projectName={project.project_id} tags={project.tags} />
      </header>

      {error && <div className="conn-error viewer-msg">⚠ {error}</div>}

      {widgets.length > 0 ? (
        <section className="viewer-grid" aria-label="widgets">
          {widgets.map((w) => (
            <div className="viewer-card" key={w.id}>
              <div className="viewer-card-title">{w.label || w.widget}</div>
              <WidgetBody subtype={w.widget} params={w.props} />
            </div>
          ))}
        </section>
      ) : (
        <div className="conn-note viewer-msg">Este proyecto no tiene widgets HMI.</div>
      )}

      {writableTags.length > 0 && (
        <section className="viewer-setpoints" aria-label="setpoints">
          <h3>Setpoints</h3>
          {writableTags.map((t) => (
            <Setpoint key={t.id} tag={t} token={token} />
          ))}
        </section>
      )}
    </div>
  );
}

/** Control de escritura para un tag `writable`. bool = toggle; resto = input. */
function Setpoint({ tag, token }: { tag: Tag; token: string | null }) {
  const live = useTagStore((s) => s.tags[tag.id]);
  const [draft, setDraft] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  function send(value: unknown) {
    const ok = connection.write(tag.id, value, token);
    setMsg(ok ? "enviado" : "sin conexión");
  }

  if (tag.data_type === "bool") {
    const on = live?.value === true || live?.value === 1;
    return (
      <div className="setpoint">
        <span className="setpoint-name">
          {tag.name}
          {tag.unit ? ` (${tag.unit})` : ""}
        </span>
        <button className={on ? "on" : "off"} onClick={() => send(!on)}>
          {on ? "ON" : "OFF"}
        </button>
        {msg && <span className="conn-note">{msg}</span>}
      </div>
    );
  }

  const numeric = tag.data_type === "int" || tag.data_type === "float";
  return (
    <div className="setpoint">
      <span className="setpoint-name">
        {tag.name}
        {tag.unit ? ` (${tag.unit})` : ""}
      </span>
      <span className="setpoint-current">{live ? String(live.value) : "—"}</span>
      <input
        aria-label={`setpoint ${tag.id}`}
        type={numeric ? "number" : "text"}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
      />
      <button
        onClick={() => {
          if (draft === "") return;
          send(numeric ? Number(draft) : draft);
        }}
      >
        Enviar
      </button>
      {msg && <span className="conn-note">{msg}</span>}
    </div>
  );
}

function ExportButton({ projectName, tags }: { projectName: string; tags: Tag[] }) {
  const liveTags = useTagStore((s) => s.tags);
  const onExport = useCallback(() => {
    const rows = tags.map((t) => {
      const live = liveTags[t.id];
      return {
        id: t.id,
        name: t.name,
        value: live?.value ?? null,
        unit: t.unit ?? "",
        quality: live?.quality ?? "bad",
        ts: live?.ts ?? "",
      };
    });
    const blob = new Blob([toCsv(rows)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${projectName}-snapshot.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [projectName, tags, liveTags]);

  return (
    <button className="sec" onClick={onExport}>
      ⬇ Exportar CSV
    </button>
  );
}
