/**
 * Controlador de conexión: orquesta REST + WS y alimenta los stores.
 *
 * Flujo de `connect(projectId, token)`:
 *   1. `GET /tags` → snapshot inicial (nombres + últimos valores) para pintar filas.
 *   2. Abre el WS (`WsClient`), suscribe a los tag_ids del proyecto.
 *   3. Rutea `tag_update`/`overflow` a los stores; `ack`/`error` se loguean.
 *
 * Se mantiene fuera de React (singleton) para que la lógica de red no dependa del
 * ciclo de vida de los componentes; la UI sólo observa los stores.
 */

import { listTags } from "./rest";
import type { ServerMessage } from "./types";
import { WsClient, type WsStatus } from "./ws";
import { useConnectionStore } from "../store/connectionStore";
import { useTagStore } from "../store/tagStore";

export class ConnectionController {
  private ws: WsClient | null = null;
  private projectId = "default";

  async connect(projectId: string, token?: string | null): Promise<void> {
    this.disconnect();
    this.projectId = projectId;

    const conn = useConnectionStore.getState();
    conn.setError(null);
    useTagStore.getState().reset();

    // 1. Snapshot REST (nombres + valores actuales). Si falla, seguimos con WS;
    //    los tags aparecerán al llegar los tag_update, pero sin nombre legible.
    let tagIds: string[] = [];
    try {
      const rows = await listTags(projectId, token);
      conn.setRows(rows);
      tagIds = rows.map((r) => r.id);
    } catch (err) {
      conn.setError(err instanceof Error ? err.message : String(err));
      conn.setRows([]);
    }

    // 2. WebSocket con reconexión + re-suscripción.
    this.ws = new WsClient({
      token,
      onStatus: (s: WsStatus) => useConnectionStore.getState().setStatus(s),
      onMessage: (m: ServerMessage) => this.handleMessage(m),
    });
    this.ws.connect();
    if (tagIds.length > 0) this.ws.subscribe(projectId, tagIds);
  }

  private handleMessage(msg: ServerMessage): void {
    switch (msg.type) {
      case "tag_update":
        useTagStore.getState().applyUpdate(msg.values);
        break;
      case "overflow":
        useTagStore.getState().addDropped(msg.dropped);
        break;
      case "error":
        useConnectionStore.getState().setError(`${msg.code}: ${msg.detail}`);
        break;
      case "ack":
        // Las escrituras se confirman aquí; F3.1+ mapeará request_id → UI.
        break;
    }
  }

  /** Escribe un valor a un tag (RBAC/audit en el backend). */
  write(tagId: string, value: unknown, token?: string | null): void {
    this.ws?.write({
      project_id: this.projectId,
      tag_id: tagId,
      value,
      request_id: crypto.randomUUID(),
      token,
    });
  }

  disconnect(): void {
    this.ws?.close();
    this.ws = null;
    useConnectionStore.getState().setStatus("idle");
  }
}

/** Singleton usado por la UI. */
export const connection = new ConnectionController();
