/**
 * Tipos del contrato backend↔frontend.
 *
 * Reflejan **fielmente** los esquemas Pydantic del backend para que el canvas
 * (F3) consuma el contrato estable sin renegociarlo (R1, ARCHITECTURE §3.10):
 *   - WS:      backend/app/ws/protocol.py
 *   - Modelos: backend/app/models/{tag,node,project,alarm}.py
 *
 * Codificación WS v1: **JSON**; el campo `type` discrimina el mensaje en ambas
 * direcciones. Si cambia el backend, este archivo es el único punto a tocar.
 */

// ---------------------------------------------------------------------------
// Modelos de dominio (models/)
// ---------------------------------------------------------------------------

export type Quality = "good" | "bad" | "uncertain";
export type DataType = "bool" | "int" | "float" | "string";
export type DeadbandMode = "abs" | "pct";

/** Una muestra concreta de un tag (última-lectura-conocida en el TagCache). */
export interface TagValue {
  tag_id: string;
  value: unknown;
  quality: Quality;
  ts: string; // ISO-8601 (datetime serializado por Pydantic)
}

/** Definición de un tag dentro de la topología del proyecto. */
export interface Tag {
  id: string;
  name: string;
  driver_id: string;
  address: string;
  data_type: DataType;
  unit?: string | null;
  deadband: number;
  deadband_mode: DeadbandMode;
}

export interface XY {
  x: number;
  y: number;
}

interface BaseNode {
  id: string;
  label: string;
  position: XY;
}

export interface DriverNode extends BaseNode {
  type: "driver";
  driver_type: string; // clave del DriverRegistry (p. ej. "modbus_tcp")
  config: Record<string, unknown>;
}

export interface LogicNode extends BaseNode {
  type: "logic";
  strategy: string;
  params: Record<string, unknown>;
}

export interface WidgetNode extends BaseNode {
  type: "widget";
  widget: string; // "tank" | "valve" | "chart" | ...
  props: Record<string, unknown>;
}

export type ProjectNode = DriverNode | LogicNode | WidgetNode;

export interface ProjectEdge {
  id: string;
  source: string;
  target: string;
}

/** Regla de alarma (models/alarm.py). Se mantiene laxa: la valida el backend. */
export interface AlarmRule {
  id: string;
  tag_id: string;
  op: string;
  threshold: number;
  severity?: string;
  [k: string]: unknown;
}

/** Proyecto completo — unión discriminada por `schema_version` (hoy sólo "1"). */
export interface ProjectV1 {
  schema_version: "1";
  project_id: string;
  name: string;
  nodes: ProjectNode[];
  edges: ProjectEdge[];
  tags: Tag[];
  alarms: AlarmRule[];
}

export type Project = ProjectV1;

/** Fila devuelta por `GET /tags` (proyección ligera, no el Tag completo). */
export interface TagRow {
  id: string;
  name: string;
  value: unknown;
  quality: Quality;
}

// ---------------------------------------------------------------------------
// Mensajes WebSocket — Cliente → Servidor (ws/protocol.py)
// ---------------------------------------------------------------------------

export interface SubscribeMsg {
  type: "subscribe";
  project_id: string;
  tag_ids: string[];
}

export interface UnsubscribeMsg {
  type: "unsubscribe";
  project_id: string;
  tag_ids: string[];
}

export interface WriteMsg {
  type: "write";
  project_id: string;
  tag_id: string;
  value: unknown;
  request_id?: string | null;
  token?: string | null;
}

export type ClientMessage = SubscribeMsg | UnsubscribeMsg | WriteMsg;

// ---------------------------------------------------------------------------
// Mensajes WebSocket — Servidor → Cliente (ws/protocol.py)
// ---------------------------------------------------------------------------

export interface TagUpdateMsg {
  type: "tag_update";
  values: TagValue[];
}

export interface AckMsg {
  type: "ack";
  request_id?: string | null;
  ok: boolean;
  detail?: string | null;
}

export interface OverflowMsg {
  type: "overflow";
  dropped: number;
}

export interface ErrorMsg {
  type: "error";
  code: string;
  detail: string;
}

export type ServerMessage = TagUpdateMsg | AckMsg | OverflowMsg | ErrorMsg;
