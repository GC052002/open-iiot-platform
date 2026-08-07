# Frontend — Editor HMI (Fase 3)

Frontend visual de la plataforma IIoT: canvas tipo **WinCC / Node-RED** para
diseñar procesos y ver datos en vivo. Stack: **React + TypeScript + Vite +
[@xyflow/react](https://reactflow.dev) + Zustand**.

Consume el contrato **estable** del backend (fijado en la Fase 1, no se
renegocia): WS `/ws` (`backend/app/ws/protocol.py`) y REST (`backend/app/api`).
El único punto donde vive ese contrato en el frontend es `src/api/types.ts`.

## Estado

**F3.0 — scaffold + conexión** ✅
- [x] Scaffold Vite + React + TS + React Flow + Zustand.
- [x] Cliente **REST** tipado (`src/api/rest.ts`) + **WebSocket** (`src/api/ws.ts`)
      con reconexión (backoff+jitter) y **re-suscripción** al reconectar.
- [x] **Store de tags** en tiempo real (reducer puro) + sesión persistida en
      `localStorage`. Login opcional (auth **opt-in** en el backend).
- [x] Tabla de tags en vivo con sparkline.

**F3.1 — paleta + canvas editable + inspector** ✅
- [x] **Paleta** arrastrable (Drivers/Lógica/Widgets) → canvas por HTML5 DnD.
- [x] **Canvas editable**: soltar nodos, conectar, seleccionar, borrar (Supr).
- [x] **Inspector** del nodo seleccionado: etiqueta, subtipo (reinicia params) y
      cada parámetro con su tipo (número/booleano/texto) + editor JSON avanzado.
- [x] **Modelo uniforme** (`src/editor/model.ts`) con mapping puro a los
      `DriverNode/LogicNode/WidgetNode` del backend (`src/editor/mapping.ts`) —
      round-trip probado (deja F3.3 import/export casi hecho).
- [x] Diseño persistido en `localStorage` (`src/store/projectStore.ts`).
- [x] Tests (Vitest): **46 verdes** (incluye Rev 14).

**Rev 14 (revisión externa Gemini + GLM)** — endurecido: escritura de comandos que
**no se pierde en silencio** (rechazo visible si el WS no está abierto), persistencia
del diseño con **debounce** y sin estado transitorio, logout automático al **expirar
la sesión** (cierre WS por auth), y esquema de tipos de parámetros en el inspector.

> **Seguridad en producción:** el token viaja en la URL del WS (`?token=`), por lo que
> **producción DEBE servirse sobre WSS/TLS** para que no quede en logs de proxies.

**F3.2 — widgets HMI con data-binding en vivo** ✅
- [x] Widgets **tanque** (nivel), **válvula** (abierta/cerrada) y **gráfico** (tendencia)
      que leen el valor en vivo del `tagStore` por `props.tag_id` (`src/editor/widgets.tsx`).
- [x] Binding en el inspector: `tag_id` como **select de los tags en vivo** del backend.
- [x] Helpers puros (`tankFillPct`, `valveState`) testeados. Tests (Vitest): **53 verdes**.

> **Probar en vivo:** con el backend + un proyecto cargado, pulsa **Conectar**, arrastra
> un **Tanque** al lienzo, selecciónalo y elige el tag en **«tag enlazado»** → el widget
> refleja el valor en tiempo real. El origen (Modbus/MQTT/S7/OPC UA) es indiferente.

Próximo (ver `../CONTINUATION.md`): **F3.2** widgets HMI con data-binding por
`tag_id`; **F3.3** import/export del JSON de proyecto + `LogicNode` sandbox.

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
  editor/
    model.ts        # Modelo uniforme del editor + paleta + createNode + DnD helpers
    mapping.ts      # Editor ↔ backend (toProjectNode/fromProjectNode/buildProject)
    nodeTypes.tsx   # Nodo custom del canvas (driver/logic/widget) con handles
  components/
    LoginBar.tsx  ConnectionBar.tsx  TagTable.tsx  Sparkline.tsx
    Palette.tsx   FlowCanvas.tsx     Inspector.tsx
  App.tsx  main.tsx
```

## Cómo probar el editor (F3.1)

`npm run dev` → arrastra un bloque de la **paleta** (izquierda) al lienzo; haz clic
en un nodo para editarlo en el **inspector** (derecha); une nodos arrastrando de un
puerto a otro; borra con **Supr**. El diseño se guarda solo en `localStorage`. No
necesita backend (el editor es offline; la barra de conexión es para ver datos en
vivo, F3.0).
