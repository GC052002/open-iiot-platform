/**
 * Import/export del proyecto como JSON (F3.3).
 *
 * `serializeProject`/`deserializeProject` son **puras** y hacen el round-trip entre
 * el estado del editor (nodes/edges/tags/meta) y el `ProjectV1` del backend (mismo
 * `schema_version`), reutilizando el mapping de `mapping.ts`. Los helpers de archivo
 * (`downloadJSON`, `readFileText`) son envoltorios finos del navegador.
 */

import type { Edge } from "@xyflow/react";
import type { DataType, ProjectV1, Tag } from "../api/types";
import type { AppNode } from "./model";
import { buildProject, fromProjectEdge, fromProjectNode } from "./mapping";
import type { ProjectMeta } from "../store/projectStore";

export interface EditorGraph {
  nodes: AppNode[];
  edges: Edge[];
  tags: Tag[];
  meta: ProjectMeta;
}

// Rev 15 (BLOCKER, Prototype Pollution): claves que jamás deben entrar desde un
// JSON importado. El reviver de JSON.parse las descarta antes de que existan.
const FORBIDDEN_KEYS = new Set(["__proto__", "constructor", "prototype"]);
const DATA_TYPES: readonly DataType[] = ["bool", "int", "float", "string"];

/** Parse defensivo: descarta claves peligrosas durante el parseo (anti-pollution). */
function safeParseJSON(json: string): unknown {
  return JSON.parse(json, (key, value) => (FORBIDDEN_KEYS.has(key) ? undefined : value));
}

/**
 * Valida y **normaliza** un tag importado (Rev 15, BLOCKER). Construye un objeto
 * nuevo con sólo los campos del contrato (sin claves extra), fuerza `address` a
 * string y verifica `data_type`. Lanza `Error` claro si el tag es inválido.
 */
function validateTag(raw: unknown, index: number): Tag {
  if (!raw || typeof raw !== "object") {
    throw new Error(`tag #${index}: no es un objeto`);
  }
  const t = raw as Record<string, unknown>;
  if (typeof t.id !== "string" || !t.id) {
    throw new Error(`tag #${index}: 'id' debe ser un string no vacío`);
  }
  if (typeof t.driver_id !== "string" || !t.driver_id) {
    throw new Error(`tag '${t.id}': 'driver_id' debe ser un string no vacío`);
  }
  const data_type = t.data_type as DataType;
  if (!DATA_TYPES.includes(data_type)) {
    throw new Error(
      `tag '${t.id}': data_type inválido '${String(t.data_type)}' (permitidos: ${DATA_TYPES.join(", ")})`,
    );
  }
  const dbMode = t.deadband_mode === "pct" ? "pct" : "abs";
  return {
    id: t.id,
    name: typeof t.name === "string" && t.name ? t.name : t.id,
    driver_id: t.driver_id,
    address: t.address == null ? "" : String(t.address), // fuerza a string (D-m2)
    data_type,
    unit: typeof t.unit === "string" ? t.unit : null,
    deadband: typeof t.deadband === "number" ? t.deadband : 0,
    deadband_mode: dbMode,
  };
}

/** Estado del editor → JSON del proyecto (indentado, listo para descargar). */
export function serializeProject(
  meta: ProjectMeta,
  nodes: AppNode[],
  edges: Edge[],
  tags: Tag[],
): string {
  return JSON.stringify(buildProject(meta, nodes, edges, tags), null, 2);
}

/**
 * JSON del proyecto → estado del editor. Lanza `Error` con mensaje claro si el
 * JSON es inválido o no es un proyecto `schema_version:"1"`.
 */
export function deserializeProject(json: string): EditorGraph {
  let raw: unknown;
  try {
    raw = safeParseJSON(json); // Rev 15: reviver anti prototype-pollution
  } catch {
    throw new Error("el archivo no es JSON válido");
  }
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("el JSON no es un objeto de proyecto");
  }
  const p = raw as Partial<ProjectV1>;
  if (p.schema_version !== "1") {
    throw new Error(`schema_version no soportada: ${String(p.schema_version)} (se espera "1")`);
  }
  if (typeof p.name !== "string" || !p.name) {
    throw new Error("el proyecto no tiene 'name'");
  }
  if (p.nodes != null && !Array.isArray(p.nodes)) throw new Error("'nodes' debe ser una lista");
  if (p.tags != null && !Array.isArray(p.tags)) throw new Error("'tags' debe ser una lista");
  const nodes = (p.nodes ?? []).map(fromProjectNode);
  const edges = (p.edges ?? []).map(fromProjectEdge);
  const tags = (p.tags ?? []).map(validateTag); // Rev 15: valida/normaliza cada tag
  const meta: ProjectMeta = { project_id: p.project_id ?? "default", name: p.name };
  return { nodes, edges, tags, meta };
}

/** Dispara la descarga de un archivo de texto en el navegador. */
export function downloadJSON(filename: string, content: string): void {
  const blob = new Blob([content], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** Lee un `File` como texto (para el input de importar). */
export function readFileText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error("no se pudo leer el archivo"));
    reader.readAsText(file);
  });
}
