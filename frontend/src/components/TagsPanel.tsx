/**
 * Editor de Tags del proyecto (F3.3): define los data points (id/nombre/driver/
 * dirección/tipo) que el backend poll-eará. El `driver_id` se elige entre los nodos
 * driver del canvas, cerrando el lazo topología → tags → `POST /projects`.
 */

import { useState } from "react";
import type { DataType, Tag } from "../api/types";
import { useProjectStore } from "../store/projectStore";

const DATA_TYPES: DataType[] = ["bool", "int", "float", "string"];

const emptyForm = { id: "", name: "", address: "", data_type: "float" as DataType };

export function TagsPanel() {
  const tags = useProjectStore((s) => s.tags);
  const nodes = useProjectStore((s) => s.nodes);
  const addTag = useProjectStore((s) => s.addTag);
  const updateTag = useProjectStore((s) => s.updateTag);
  const removeTag = useProjectStore((s) => s.removeTag);

  const drivers = nodes.filter((n) => n.data.kind === "driver");
  const [form, setForm] = useState(emptyForm);
  const [driverId, setDriverId] = useState("");
  const [error, setError] = useState<string | null>(null);

  function add() {
    const id = form.id.trim();
    if (!id) return setError("el tag necesita un id");
    if (tags.some((t) => t.id === id)) return setError(`ya existe un tag '${id}'`);
    if (!driverId) return setError("elige un driver (añade un nodo driver al canvas)");
    const tag: Tag = {
      id,
      name: form.name.trim() || id,
      driver_id: driverId,
      address: form.address.trim(),
      data_type: form.data_type,
      deadband: 0,
      deadband_mode: "abs",
    };
    addTag(tag);
    setForm(emptyForm);
    setError(null);
  }

  return (
    <div className="tags-panel">
      {tags.length === 0 && <div className="conn-note">Sin tags definidos.</div>}
      {tags.map((t) => (
        <div className="tagdef" key={t.id}>
          <div className="tagdef-row">
            <span className="tagdef-id">{t.id}</span>
            <button className="sec danger tagdef-x" title="Quitar" onClick={() => removeTag(t.id)}>
              ✕
            </button>
          </div>
          <input
            aria-label={`nombre ${t.id}`}
            value={t.name}
            placeholder="nombre"
            onChange={(e) => updateTag(t.id, { name: e.target.value })}
          />
          <div className="tagdef-row2">
            <input
              aria-label={`address ${t.id}`}
              value={t.address}
              placeholder="dirección"
              onChange={(e) => updateTag(t.id, { address: e.target.value })}
            />
            <select
              aria-label={`tipo ${t.id}`}
              value={t.data_type}
              onChange={(e) => updateTag(t.id, { data_type: e.target.value as DataType })}
            >
              {DATA_TYPES.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </div>
          <div className="tagdef-driver">driver: {t.driver_id}</div>
        </div>
      ))}

      <div className="tag-add">
        <div className="side-title">Nuevo tag</div>
        <input
          aria-label="nuevo id"
          placeholder="id (p. ej. nivel)"
          value={form.id}
          onChange={(e) => setForm({ ...form, id: e.target.value })}
        />
        <select aria-label="nuevo driver" value={driverId} onChange={(e) => setDriverId(e.target.value)}>
          <option value="">— driver —</option>
          {drivers.map((d) => (
            <option key={d.id} value={d.id}>
              {d.data.label} ({d.id})
            </option>
          ))}
        </select>
        <div className="tagdef-row2">
          <input
            aria-label="nueva address"
            placeholder="dirección"
            value={form.address}
            onChange={(e) => setForm({ ...form, address: e.target.value })}
          />
          <select
            aria-label="nuevo tipo"
            value={form.data_type}
            onChange={(e) => setForm({ ...form, data_type: e.target.value as DataType })}
          >
            {DATA_TYPES.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>
        <button onClick={add}>+ Añadir tag</button>
        {error && <div className="conn-error">⚠ {error}</div>}
      </div>
    </div>
  );
}
