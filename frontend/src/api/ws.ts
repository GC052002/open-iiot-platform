/**
 * Cliente WebSocket del backend (`/ws`).
 *
 * Responsabilidades:
 *  - Handshake con token vía query param (`?token=...`) — el backend cachea el rol
 *    en el handshake (Rev 12), así que el WriteMsg no lo reenvía en el hot path.
 *  - Reconexión automática con backoff exponencial + jitter.
 *  - Re-suscripción idempotente al reconectar (mantiene el set deseado de tags).
 *  - Parseo/validación laxa de los mensajes servidor→cliente.
 *
 * Los helpers puros (`buildWsUrl`, `nextBackoffMs`, `parseServerMessage`) se testean
 * sin abrir un socket real. La clase acepta una factoría de WebSocket inyectable.
 */

import type { ClientMessage, ServerMessage, WriteMsg } from "./types";

export type WsStatus = "idle" | "connecting" | "open" | "closed";

const SERVER_TYPES = new Set(["tag_update", "ack", "overflow", "error"]);

/** Construye la URL del WS a partir del origen actual (ws/wss) + token opcional. */
export function buildWsUrl(location: { protocol: string; host: string }, token?: string | null): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const base = `${proto}://${location.host}/ws`;
  return token ? `${base}?token=${encodeURIComponent(token)}` : base;
}

/** Backoff exponencial acotado con jitter (evita tormentas de reconexión). */
export function nextBackoffMs(attempt: number, baseMs = 500, maxMs = 10_000): number {
  const exp = Math.min(maxMs, baseMs * 2 ** attempt);
  const jitter = Math.random() * (exp / 2);
  return Math.round(exp / 2 + jitter);
}

/** Valida y parsea un mensaje servidor→cliente. Devuelve `null` si es inválido. */
export function parseServerMessage(raw: string): ServerMessage | null {
  let obj: unknown;
  try {
    obj = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!obj || typeof obj !== "object") return null;
  const type = (obj as { type?: unknown }).type;
  if (typeof type !== "string" || !SERVER_TYPES.has(type)) return null;
  return obj as ServerMessage;
}

type WsFactory = (url: string) => WebSocket;

export interface WsClientOptions {
  /** Token de sesión (opcional; auth opt-in en el backend). */
  token?: string | null;
  onMessage?: (msg: ServerMessage) => void;
  onStatus?: (status: WsStatus) => void;
  /** Origen; por defecto `window.location`. Inyectable para tests. */
  location?: { protocol: string; host: string };
  /** Factoría de WebSocket; por defecto `new WebSocket(url)`. Inyectable para tests. */
  wsFactory?: WsFactory;
}

/** Una suscripción deseada: conjunto de tag_ids por proyecto. */
type SubMap = Map<string, Set<string>>;

export class WsClient {
  private ws: WebSocket | null = null;
  private status: WsStatus = "idle";
  private attempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closedByUser = false;
  private readonly desired: SubMap = new Map();

  private readonly token?: string | null;
  private readonly onMessage?: (msg: ServerMessage) => void;
  private readonly onStatus?: (status: WsStatus) => void;
  private readonly location: { protocol: string; host: string };
  private readonly wsFactory: WsFactory;

  constructor(opts: WsClientOptions = {}) {
    this.token = opts.token;
    this.onMessage = opts.onMessage;
    this.onStatus = opts.onStatus;
    this.location = opts.location ?? window.location;
    this.wsFactory = opts.wsFactory ?? ((url) => new WebSocket(url));
  }

  getStatus(): WsStatus {
    return this.status;
  }

  connect(): void {
    if (this.ws && (this.status === "open" || this.status === "connecting")) return;
    this.closedByUser = false;
    this.open();
  }

  private open(): void {
    this.setStatus("connecting");
    const url = buildWsUrl(this.location, this.token);
    const ws = this.wsFactory(url);
    this.ws = ws;

    ws.onopen = () => {
      this.attempt = 0;
      this.setStatus("open");
      this.resubscribeAll();
    };
    ws.onmessage = (ev: MessageEvent) => {
      const msg = parseServerMessage(String(ev.data));
      if (msg) this.onMessage?.(msg);
    };
    ws.onclose = () => {
      this.ws = null;
      this.setStatus("closed");
      if (!this.closedByUser) this.scheduleReconnect();
    };
    ws.onerror = () => {
      // El navegador dispara onclose tras onerror; ahí se agenda la reconexión.
      try {
        ws.close();
      } catch {
        /* ya cerrado */
      }
    };
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    const delay = nextBackoffMs(this.attempt++);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (!this.closedByUser) this.open();
    }, delay);
  }

  close(): void {
    this.closedByUser = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      try {
        this.ws.close();
      } catch {
        /* noop */
      }
      this.ws = null;
    }
    this.setStatus("closed");
  }

  /** Añade tags al set deseado y (si hay conexión) envía el subscribe. */
  subscribe(projectId: string, tagIds: string[]): void {
    const set = this.desired.get(projectId) ?? new Set<string>();
    tagIds.forEach((t) => set.add(t));
    this.desired.set(projectId, set);
    this.send({ type: "subscribe", project_id: projectId, tag_ids: tagIds });
  }

  /** Quita tags del set deseado y envía el unsubscribe. */
  unsubscribe(projectId: string, tagIds: string[]): void {
    const set = this.desired.get(projectId);
    if (set) {
      tagIds.forEach((t) => set.delete(t));
      if (set.size === 0) this.desired.delete(projectId);
    }
    this.send({ type: "unsubscribe", project_id: projectId, tag_ids: tagIds });
  }

  /** Solicita una escritura de tag (RBAC/audit se aplican en el backend). */
  write(msg: Omit<WriteMsg, "type">): void {
    this.send({ type: "write", ...msg });
  }

  private resubscribeAll(): void {
    for (const [projectId, set] of this.desired) {
      if (set.size > 0) {
        this.send({ type: "subscribe", project_id: projectId, tag_ids: [...set] });
      }
    }
  }

  private send(msg: ClientMessage): boolean {
    if (this.ws && this.status === "open") {
      this.ws.send(JSON.stringify(msg));
      return true;
    }
    return false; // se re-enviará al reconectar (subscribe) o se pierde (write puntual)
  }

  private setStatus(status: WsStatus): void {
    if (status !== this.status) {
      this.status = status;
      this.onStatus?.(status);
    }
  }
}
