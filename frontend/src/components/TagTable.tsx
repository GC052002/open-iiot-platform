/**
 * Tabla de tags en vivo. Toma el orden/nombres del snapshot REST (`connectionStore`)
 * y los valores en tiempo real del `tagStore` (alimentado por los `tag_update` del
 * WS). Es la prueba end-to-end de F3.0: ver datos del backend fluyendo en la UI.
 */

import { useConnectionStore } from "../store/connectionStore";
import { useTagStore } from "../store/tagStore";
import { Sparkline } from "./Sparkline";
import type { Quality } from "../api/types";

function fmt(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

const badgeClass: Record<Quality, string> = {
  good: "b-good",
  bad: "b-bad",
  uncertain: "b-uncertain",
};

export function TagTable() {
  const rows = useConnectionStore((s) => s.rows);
  const tags = useTagStore((s) => s.tags);

  // Si el snapshot REST vino vacío pero llegan tags por WS, mostramos esos ids.
  const ids = rows.length > 0 ? rows.map((r) => r.id) : Object.keys(tags);

  if (ids.length === 0) {
    return <div className="empty">Sin tags. Conecta a un proyecto cargado en el backend.</div>;
  }

  const names = new Map(rows.map((r) => [r.id, r.name]));

  return (
    <table className="tag-table">
      <thead>
        <tr>
          <th>Tag</th>
          <th>Valor</th>
          <th>Calidad</th>
          <th>Tendencia</th>
        </tr>
      </thead>
      <tbody>
        {ids.map((id) => {
          const live = tags[id];
          const quality = (live?.quality ?? "bad") as Quality;
          return (
            <tr key={id}>
              <td>
                <div className="tag-name">{names.get(id) ?? id}</div>
                <div className="tag-id">{id}</div>
              </td>
              <td className="tag-val">{fmt(live?.value)}</td>
              <td>
                <span className={`badge ${badgeClass[quality]}`}>{quality}</span>
              </td>
              <td>
                <Sparkline data={live?.trend ?? []} />
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
