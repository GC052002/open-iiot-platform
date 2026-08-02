import { afterEach, describe, expect, it, vi } from "vitest";
import { WsClient } from "./ws";

/** WebSocket falso controlable para test (sin red). */
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  closed = false;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    if (this.closed) return;
    this.closed = true;
    this.onclose?.();
  }
  open() {
    this.onopen?.();
  }
  emit(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
  parsedSent() {
    return this.sent.map((s) => JSON.parse(s));
  }
}

const loc = { protocol: "http:", host: "localhost:8000" };

function makeClient(onMessage?: (m: unknown) => void) {
  FakeWebSocket.instances = [];
  const client = new WsClient({
    location: loc,
    wsFactory: (url) => new FakeWebSocket(url) as unknown as WebSocket,
    onMessage: onMessage as never,
  });
  return client;
}

afterEach(() => {
  vi.useRealTimers();
});

describe("WsClient", () => {
  it("envía subscribe tras abrir la conexión", () => {
    const client = makeClient();
    client.connect();
    const ws = FakeWebSocket.instances[0];
    ws.open();
    client.subscribe("planta", ["a", "b"]);
    expect(ws.parsedSent()).toContainEqual({
      type: "subscribe",
      project_id: "planta",
      tag_ids: ["a", "b"],
    });
  });

  it("re-suscribe el set deseado al reconectar", () => {
    vi.useFakeTimers();
    const client = makeClient();
    client.connect();
    const ws0 = FakeWebSocket.instances[0];
    ws0.open();
    client.subscribe("planta", ["a", "b"]);

    // Caída de red (no iniciada por el usuario) → reconexión programada.
    ws0.close();
    vi.advanceTimersByTime(20_000);
    const ws1 = FakeWebSocket.instances[1];
    expect(ws1).toBeDefined();
    ws1.open();

    // Al reabrir, el cliente re-suscribe automáticamente lo deseado.
    expect(ws1.parsedSent()).toContainEqual({
      type: "subscribe",
      project_id: "planta",
      tag_ids: ["a", "b"],
    });
  });

  it("no reconecta si el cierre lo pide el usuario", () => {
    vi.useFakeTimers();
    const client = makeClient();
    client.connect();
    FakeWebSocket.instances[0].open();
    client.close();
    vi.advanceTimersByTime(60_000);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("entrega los mensajes válidos del servidor al callback", () => {
    const received: unknown[] = [];
    const client = makeClient((m) => received.push(m));
    client.connect();
    const ws = FakeWebSocket.instances[0];
    ws.open();
    ws.emit({ type: "tag_update", values: [{ tag_id: "a", value: 1, quality: "good", ts: "t" }] });
    ws.emit({ type: "basura" }); // descartado por parseServerMessage
    expect(received).toHaveLength(1);
  });
});
