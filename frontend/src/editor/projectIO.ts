/**
 * Import/export del proyecto como JSON (F3.3).
 *
 * `serializeProject`/`deserializeProject` son **puras** y hacen el round-trip entre
 * el estado del editor (nodes/edges/tags/meta) y el `ProjectV1` del backend (mismo
 * `schema_version`), reutilizando el mapping de `mapping.ts`. Los helpers de archivo
 * (`downloadJSON`, `readFileText`) son envoltorios finos del navegador.
 */

import type { Edge } from "@xyflow/react";
import type { ProjectV1, Tag } from "../api/types";
import type { AppNode } from "./model";
import { buildProject, fromProjectEdge, fromProjectNode } from "./mapping";
import type { ProjectMeta } from "../store/projectStore";

export interface EditorGraph {
  nodes: AppNode[];
  edges: Edge[];
  tags: Tag[];
  meta: ProjectMeta;
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
    raw = JSON.parse(json);
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
  const nodes = (p.nodes ?? []).map(fromProjectNode);
  const edges = (p.edges ?? []).map(fromProjectEdge);
  const tags = (p.tags ?? []) as Tag[];
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
