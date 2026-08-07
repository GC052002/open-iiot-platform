/**
 * Modelo del editor de canvas (F3.1).
 *
 * Un **único shape de datos** para los tres tipos de nodo (`EditorNodeData`): la
 * paleta, el store, los nodos custom y el inspector trabajan todos con él, y el
 * mapping (`mapping.ts`) lo expande a los `DriverNode/LogicNode/WidgetNode` del
 * backend (`models/node.py`) en export, y lo colapsa en import. Así el editor no
 * duplica la lógica de los tres nombres de campo (config/params/props).
 */

import type { Node } from "@xyflow/react";

export type NodeKind = "driver" | "logic" | "widget";

/** Datos que viajan en `node.data` de React Flow (uniforme para los 3 tipos). */
export interface EditorNodeData extends Record<string, unknown> {
  label: string;
  kind: NodeKind;
  /** Subtipo: `driver_type` (modbus_tcp…), `strategy` (scale…) o `widget` (tank…). */
  subtype: string;
  /** Parámetros libres: se mapea a config/params/props según el `kind`. */
  params: Record<string, unknown>;
}

/** Nodo de React Flow con nuestro `data`. `type` = `kind` (elige el componente). */
export type AppNode = Node<EditorNodeData>;

// ---------------------------------------------------------------------------
// Paleta
// ---------------------------------------------------------------------------

export interface PaletteItem {
  kind: NodeKind;
  subtype: string;
  label: string;
  icon: string;
}

export interface PaletteGroup {
  title: string;
  items: PaletteItem[];
}

/** Opciones de subtipo por `kind` (también las usa el inspector para su `<select>`). */
export const SUBTYPES: Record<NodeKind, { value: string; label: string }[]> = {
  driver: [
    { value: "modbus_tcp", label: "Modbus TCP" },
    { value: "s7", label: "Siemens S7" },
    { value: "opcua", label: "OPC UA" },
    { value: "mqtt", label: "MQTT" },
  ],
  logic: [
    { value: "scale", label: "Escala (a·x+b)" },
    { value: "deadband", label: "Deadband" },
    { value: "avg", label: "Media móvil" },
  ],
  widget: [
    { value: "tank", label: "Tanque" },
    { value: "valve", label: "Válvula" },
    { value: "chart", label: "Gráfico" },
  ],
};

const ICONS: Record<NodeKind, string> = { driver: "🔌", logic: "🧮", widget: "🛢️" };

export const PALETTE: PaletteGroup[] = (["driver", "logic", "widget"] as NodeKind[]).map(
  (kind) => ({
    title: kind === "driver" ? "Drivers" : kind === "logic" ? "Lógica" : "Widgets",
    items: SUBTYPES[kind].map((s) => ({
      kind,
      subtype: s.value,
      label: s.label,
      icon: ICONS[kind],
    })),
  }),
);

// ---------------------------------------------------------------------------
// Valores por defecto de `params` según subtipo
// ---------------------------------------------------------------------------

/** Config/params/props inicial al soltar un nodo desde la paleta. */
export function defaultParams(kind: NodeKind, subtype: string): Record<string, unknown> {
  if (kind === "driver") {
    switch (subtype) {
      case "modbus_tcp":
        return { host: "127.0.0.1", port: 502, unit: 1, polling_rate: 1.0 };
      case "s7":
        return { host: "192.168.0.1", rack: 0, slot: 1, polling_rate: 0.5 };
      case "opcua":
        return { endpoint: "opc.tcp://127.0.0.1:4840" };
      case "mqtt":
        return { host: "127.0.0.1", port: 1883 };
      default:
        return {};
    }
  }
  if (kind === "logic") {
    switch (subtype) {
      case "scale":
        return { a: 1.0, b: 0.0 };
      case "deadband":
        return { deadband: 0.5 };
      case "avg":
        return { window: 10 };
      default:
        return {};
    }
  }
  // widget — binding por tag_id (contrato F3.2); vacío = sin dato aún.
  switch (subtype) {
    case "tank":
      return { tag_id: "", min: 0, max: 100 };
    case "valve":
      return { tag_id: "", open_value: 1 };
    default: // chart y otros
      return { tag_id: "" };
  }
}

/** Etiqueta por defecto de un nodo recién creado. */
export function defaultLabel(item: PaletteItem): string {
  return item.label;
}

export type ParamType = "number" | "boolean" | "string";

/**
 * Esquema de tipos de parámetros conocidos (Rev 14, MEDIA). El inspector infería el
 * tipo del valor actual, lo que rompía el tipado si un param llegaba como `null`
 * (p. ej. desde el editor JSON): quedaba como string y el backend lo rechazaba. Con
 * un esquema explícito, un `port` es número aunque su valor actual sea null/"".
 */
const PARAM_TYPES: Record<string, ParamType> = {
  port: "number",
  unit: "number",
  polling_rate: "number",
  rack: "number",
  slot: "number",
  a: "number",
  b: "number",
  deadband: "number",
  window: "number",
  min: "number",
  max: "number",
  open_value: "number",
  host: "string",
  endpoint: "string",
  tag_id: "string",
};

/** Tipo de un parámetro: esquema conocido primero, si no, se infiere del valor. */
export function paramType(key: string, sample: unknown): ParamType {
  if (PARAM_TYPES[key]) return PARAM_TYPES[key];
  if (typeof sample === "number") return "number";
  if (typeof sample === "boolean") return "boolean";
  return "string";
}

/** Convierte el texto de un input al tipo indicado (sin depender del valor actual). */
export function coerceValue(raw: string, type: ParamType): unknown {
  if (type === "number") {
    const n = Number(raw);
    return raw.trim() === "" || Number.isNaN(n) ? 0 : n;
  }
  if (type === "boolean") return raw === "true";
  return raw;
}

/** MIME usado en el dataTransfer al arrastrar un item de la paleta al canvas. */
export const PALETTE_MIME = "application/x-iiot-node";

export function serializePaletteItem(item: PaletteItem): string {
  return JSON.stringify(item);
}

/** Parsea el payload del drop. Devuelve `null` si no es un item válido. */
export function parsePaletteItem(raw: string): PaletteItem | null {
  try {
    const o = JSON.parse(raw);
    if (o && typeof o.kind === "string" && typeof o.subtype === "string") {
      return { kind: o.kind, subtype: o.subtype, label: String(o.label ?? o.subtype), icon: String(o.icon ?? "") };
    }
  } catch {
    /* payload inválido */
  }
  return null;
}

let _seq = 0;
/** Id único y legible para un nodo nuevo (p. ej. `driver_3`). */
export function nextNodeId(kind: NodeKind): string {
  _seq += 1;
  return `${kind}_${Date.now().toString(36)}${_seq}`;
}

/** Crea un `AppNode` a partir de un item de paleta y una posición del canvas. */
export function createNode(item: PaletteItem, position: { x: number; y: number }, id?: string): AppNode {
  return {
    id: id ?? nextNodeId(item.kind),
    type: item.kind,
    position,
    data: {
      label: defaultLabel(item),
      kind: item.kind,
      subtype: item.subtype,
      params: defaultParams(item.kind, item.subtype),
    },
  };
}
