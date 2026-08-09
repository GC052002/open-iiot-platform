/**
 * Inspector de propiedades del nodo seleccionado (F3.1).
 *
 * Edita label, subtipo (cambia el driver_type/strategy/widget y reinicia sus
 * params por defecto) y cada campo de `params` con el tipo correcto (número,
 * booleano o texto). Un bloque avanzado permite editar el JSON crudo de params
 * para añadir/quitar claves. Todo escribe en `projectStore`.
 */

import { useEffect, useState } from "react";
import { coerceValue, defaultParams, paramType, SUBTYPES } from "../editor/model";
import { useConnectionStore } from "../store/connectionStore";
import { useProjectStore } from "../store/projectStore";
import { useTagStore } from "../store/tagStore";

export function Inspector() {
  const selectedId = useProjectStore((s) => s.selectedId);
  const node = useProjectStore((s) => s.nodes.find((n) => n.id === s.selectedId));
  const updateNodeData = useProjectStore((s) => s.updateNodeData);
  const setNodeParams = useProjectStore((s) => s.setNodeParams);
  const removeNode = useProjectStore((s) => s.removeNode);
  // F3.2/Rev 15: opciones de binding de widgets = tags en vivo del backend
  // (snapshot REST) ∪ tags definidos en el proyecto (aunque aún no lleguen datos).
  const liveRows = useConnectionStore((s) => s.rows);
  const projectTags = useProjectStore((s) => s.tags);
  // Tags presentes en el stream en vivo — incluye los DERIVADOS por LogicNode
  // (p. ej. `scaled`), que no están en /tags ni en los tags del proyecto.
  const liveTags = useTagStore((s) => s.tags);

  if (!node || !selectedId) {
    return (
      <div className="inspector">
        <div className="inspector-empty">Selecciona un nodo para editar sus propiedades.</div>
      </div>
    );
  }

  const { kind, label, subtype, params } = node.data;

  function setParam(key: string, raw: string, value: unknown) {
    setNodeParams(selectedId!, { ...params, [key]: coerceValue(raw, paramType(key, value)) });
  }

  function changeSubtype(newSubtype: string) {
    // Cambiar de subtipo cambia los campos disponibles → reinicia params.
    updateNodeData(selectedId!, { subtype: newSubtype, params: defaultParams(kind, newSubtype) });
  }

  return (
    <div className="inspector">
      <div className="inspector-head">
        <span className={`kind-tag kt-${kind}`}>{kind}</span>
        <span className="inspector-id">{node.id}</span>
        <button className="sec danger" onClick={() => removeNode(selectedId)}>
          Borrar
        </button>
      </div>

      <label className="field">
        <span>Etiqueta</span>
        <input value={label} onChange={(e) => updateNodeData(selectedId, { label: e.target.value })} />
      </label>

      <label className="field">
        <span>Tipo</span>
        <select value={subtype} onChange={(e) => changeSubtype(e.target.value)}>
          {SUBTYPES[kind].map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>

      <div className="field-group-title">Parámetros</div>
      {Object.keys(params).length === 0 && <div className="inspector-empty">Sin parámetros.</div>}
      {Object.entries(params).map(([key, value]) => {
        const t = paramType(key, value);
        // Binding a un tag de origen (select de tags vivos ∪ del proyecto):
        // widget.tag_id (F3.2/Rev 15) y logic.input (LogicNode).
        const isTagBinding =
          (kind === "widget" && key === "tag_id") || (kind === "logic" && key === "input");
        if (isTagBinding) {
          const current = typeof value === "string" ? value : "";
          const seen = new Set<string>();
          const options: { id: string; label: string }[] = [];
          for (const r of liveRows) {
            if (!seen.has(r.id)) {
              seen.add(r.id);
              options.push({ id: r.id, label: `${r.name} (${r.id}) · en vivo` });
            }
          }
          // Derivados por LogicNode (llegan por WS, no están en /tags).
          for (const id of Object.keys(liveTags)) {
            if (!seen.has(id)) {
              seen.add(id);
              options.push({ id, label: `${id} · derivado` });
            }
          }
          for (const tg of projectTags) {
            if (!seen.has(tg.id)) {
              seen.add(tg.id);
              options.push({ id: tg.id, label: `${tg.name} (${tg.id})` });
            }
          }
          const known = options.some((o) => o.id === current);
          return (
            <label className="field" key={key}>
              <span>{key === "input" ? "tag de entrada" : "tag enlazado"}</span>
              <select
                value={current}
                onChange={(e) => setNodeParams(selectedId, { ...params, [key]: e.target.value })}
              >
                <option value="">— sin binding —</option>
                {current && !known && <option value={current}>{current} (desconocido)</option>}
                {options.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
          );
        }
        return (
          <label className="field" key={key}>
            <span>{key}</span>
            {t === "boolean" ? (
              <input
                type="checkbox"
                checked={value === true}
                onChange={(e) => setParam(key, String(e.target.checked), value)}
              />
            ) : (
              <input
                type={t === "number" ? "number" : "text"}
                value={value === null || value === undefined ? "" : String(value)}
                onChange={(e) => setParam(key, e.target.value, value)}
              />
            )}
          </label>
        );
      })}

      <AdvancedParams
        key={node.id}
        value={params}
        onApply={(obj) => setNodeParams(selectedId, obj)}
      />
    </div>
  );
}

/** Editor JSON crudo de params (añadir/quitar claves). Valida antes de aplicar. */
function AdvancedParams({
  value,
  onApply,
}: {
  value: Record<string, unknown>;
  onApply: (obj: Record<string, unknown>) => void;
}) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2));
  const [error, setError] = useState<string | null>(null);

  // Re-sincroniza si cambian los params desde fuera (edición por campos).
  useEffect(() => {
    setText(JSON.stringify(value, null, 2));
    setError(null);
  }, [value]);

  function apply() {
    try {
      const obj = JSON.parse(text);
      if (obj === null || typeof obj !== "object" || Array.isArray(obj)) {
        throw new Error("debe ser un objeto JSON");
      }
      setError(null);
      onApply(obj as Record<string, unknown>);
    } catch (err) {
      setError(err instanceof Error ? err.message : "JSON inválido");
    }
  }

  return (
    <details className="advanced">
      <summary>Avanzado (JSON)</summary>
      <textarea rows={6} value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} />
      {error && <div className="conn-error">⚠ {error}</div>}
      <button className="sec" onClick={apply}>
        Aplicar JSON
      </button>
    </details>
  );
}
