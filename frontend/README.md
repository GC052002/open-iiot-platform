# Frontend — Editor HMI (Fase 3)

Frontend visual de la plataforma IIoT: canvas tipo **WinCC / Node-RED** para
diseñar procesos y ver datos en vivo. Stack: **React + TypeScript + Vite +
[@xyflow/react](https://reactflow.dev) + Zustand**.

Consume el contrato **estable** del backend (fijado en la Fase 1, no se
renegocia): WS `/ws` (`backend/app/ws/protocol.py`) y REST (`backend/app/api`).
El único punto donde vive ese contrato en el frontend es `src/api/types.ts`.

## Estado — F3.0 (scaffold + conexión)

- [x] Scaffold Vite + React + TS + React Flow + Zustand.
- [x] Cliente **REST** tipado (`src/api/rest.ts`): login, projects, tags, history…
- [x] Cliente **WebSocket** (`src/api/ws.ts`): reconexión con backoff + jitter y
      **re-suscripción** idempotente al reconectar.
- [x] **Store de tags** en tiempo real (`src/store/tagStore.ts`) + reducer puro.
- [x] Sesión persistida en `localStorage` (`src/store/sessionStore.ts`): token +
      último `project_id`. Login opcional (auth **opt-in** en el backend).
- [x] UI mínima: login, barra de conexión, **tabla de tags en vivo** con
      sparkline, y **canvas** React Flow (esqueleto con las 3 familias de nodos).
- [x] Tests (Vitest): 24 verdes.

Próximo (ver `../CONTINUATION.md`): **F3.1** paleta + canvas editable + inspector;
**F3.2** widgets HMI con data-binding por `tag_id`; **F3.3** import/export del JSON
de proyecto + `LogicNode` sandbox.

## Desarrollo

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxy a http://localhost:8000)
```

El backend debe estar corriendo aparte (ver `../CONTINUATION.md`):

```bash
export IIOT_ALLOW_ANONYMOUS=true              # dev/demo (seguridad fail-closed)
python -m app.drivers.modbus_sim &            # simulador Modbus TCP :5020
uvicorn app.main:app --port 8000              # backend
# Cargar un proyecto (POST /projects) — ver DEMO.md para el payload.
```

En dev, Vite hace de proxy de `/ws`, `/tags`, `/projects`, … hacia el backend
(configurable con `VITE_BACKEND`, por defecto `http://localhost:8000`). En
producción, el bundle (`npm run build` → `dist/`) se sirve desde el propio backend:
mismo origen para API y estáticos (**air-gapped**, sin CDNs).

## Scripts

| Script            | Acción                                             |
|-------------------|----------------------------------------------------|
| `npm run dev`     | Servidor de desarrollo (HMR) + proxy al backend.   |
| `npm run build`   | Type-check (`tsc --noEmit`) + build a `dist/`.     |
| `npm run preview` | Sirve el build de producción localmente.           |
| `npm test`        | Tests unitarios (Vitest).                          |
| `npm run lint`    | Solo type-check.                                    |

## Estructura

```
src/
  api/
    types.ts        # Contrato WS + modelos (espejo de backend/app/{ws,models})
    rest.ts         # Cliente REST tipado (Bearer opt-in)
    ws.ts           # WsClient: reconexión + re-suscripción (+ helpers puros)
    connection.ts   # ConnectionController: orquesta REST+WS → stores (singleton)
  store/
    tagStore.ts     # Tags en vivo + reducer puro applyTagValues + sparkline buffer
    sessionStore.ts # token/usuario/project_id (persist localStorage)
    connectionStore.ts # status del WS + filas del snapshot + error
  components/
    LoginBar.tsx  ConnectionBar.tsx  TagTable.tsx  Sparkline.tsx  FlowCanvas.tsx
  App.tsx  main.tsx
```
