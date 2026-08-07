/**
 * Widgets HMI con data-binding en vivo por `tag_id` (F3.2).
 *
 * `WidgetBody` lee el valor actual del `tagStore` (alimentado por los `tag_update`
 * del WS) usando `props.tag_id` y lo pinta según el subtipo (tank/valve/chart). El
 * origen del dato es indiferente (Modbus/MQTT/S7/OPC UA): sólo importa el `tag_id`,
 * tal como fija el contrato. Los cálculos (`tankFillPct`, `valveState`) son puros y
 * se testean sin React.
 */

import { useTagStore } from "../store/tagStore";
import { Sparkline } from "../components/Sparkline";

export type ValveState = "open" | "closed" | "unknown";

/** Nivel de llenado 0..100 de un tanque para `value` en el rango [min, max]. */
export function tankFillPct(value: unknown, min: number, max: number): number {
  if (typeof value !== "number" || max === min) return 0;
  const pct = ((value - min) / (max - min)) * 100;
  return Math.max(0, Math.min(100, pct));
}

/** Estado de una válvula. `open_value` es el umbral numérico de "abierta". */
export function valveState(value: unknown, openValue = 1): ValveState {
  if (value === null || value === undefined) return "unknown";
  if (typeof value === "boolean") return value ? "open" : "closed";
  if (typeof value === "number") return value >= openValue ? "open" : "closed";
  const s = String(value).trim().toLowerCase();
  if (["1", "true", "open", "on", "abierta"].includes(s)) return "open";
  if (["0", "false", "closed", "off", "cerrada"].includes(s)) return "closed";
  return "unknown";
}

function fmt(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

const num = (v: unknown, def: number): number => (typeof v === "number" ? v : def);

interface Props {
  subtype: string;
  params: Record<string, unknown>;
}

/** Cuerpo visual del nodo widget, con el valor en vivo del tag enlazado. */
export function WidgetBody({ subtype, params }: Props) {
  const tagId = typeof params.tag_id === "string" ? params.tag_id : "";
  const live = useTagStore((s) => (tagId ? s.tags[tagId] : undefined));

  if (!tagId) return <div className="wg-empty">sin binding</div>;

  const value = live?.value;
  const bad = live?.quality === "bad";

  if (subtype === "tank") {
    const pct = tankFillPct(value, num(params.min, 0), num(params.max, 100));
    return (
      <div className={`wg-tank${bad ? " wg-bad" : ""}`} title={tagId}>
        <div className="wg-tank-body">
          <div className="wg-tank-fill" style={{ height: `${pct}%` }} />
        </div>
        <div className="wg-value">{fmt(value)}</div>
      </div>
    );
  }

  if (subtype === "valve") {
    const st = valveState(value, num(params.open_value, 1));
    const label = st === "open" ? "ABIERTA" : st === "closed" ? "CERRADA" : "—";
    return (
      <div className={`wg-valve wg-valve-${st}`} title={tagId}>
        <span className="wg-valve-dot" />
        <span className="wg-valve-label">{label}</span>
      </div>
    );
  }

  // chart (por defecto)
  return (
    <div className={`wg-chart${bad ? " wg-bad" : ""}`} title={tagId}>
      <Sparkline data={live?.trend ?? []} width={130} height={34} />
      <div className="wg-value">{fmt(value)}</div>
    </div>
  );
}
