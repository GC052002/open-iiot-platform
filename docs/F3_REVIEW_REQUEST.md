# Solicitud de revisión — Fase 3 (F3.0 + F3.1) · Frontend IIoT/SCADA

> **Para:** GLM 5.2 y Gemini (revisores externos).
> **De:** el equipo (implementación por Claude/Opus).
> **Repo:** `GC052002/open-iiot-platform` · rama `main` · PRs **#19 (F3.0)** y **#20 (F3.1)**.
> **Adjunto:** `frontend_bundle.txt` (todo el código del frontend de esta fase) y, al
> final, el diff del bugfix del backend.

## 0. Cómo queremos la revisión

Somos un equipo humano + IA con **presupuesto de tokens acotado**. Trabajamos por
fases atómicas y **revisamos-una-vez / integramos-en-lote** (no ida-y-vuelta continuo).
Por favor:

1. Priorizad **bugs reales, riesgos de seguridad y decisiones de arquitectura** que
   cueste revertir más adelante, por encima de estilo.
2. Marcad cada punto como **BLOCKER / MEDIA / BAJA / NIT** y, si podéis, con el
   archivo:línea.
3. Si algo ya está **diferido a propósito** (lo listamos abajo), no lo reabráis salvo
   que veáis un riesgo que se nos escapa.
4. Respuesta ideal: una tabla de hallazgos que podamos integrar como "Rev N".

## 1. Contexto del proyecto

Plataforma IIoT/SCADA open source (alternativa a WinCC/Ignition). **Backend** Python
(FastAPI + asyncio) ya completo (Fase 2): motor multi-tenant, drivers Modbus/MQTT/S7/
OPC UA, historiador SQLite, alarmas, seguridad Fernet/RBAC/audit, métricas Prometheus.
80→82 tests verdes.

**Fase 3 = frontend visual** (canvas HMI tipo Node-RED/WinCC), en React. El contrato
WS/REST se fijó en la Fase 1 y **no se renegocia** (`backend/app/ws/protocol.py`,
`backend/app/models/node.py`). Esta fase lo **consume**.

Stack elegido: **React 18 + TypeScript + Vite + @xyflow/react (React Flow v12) +
Zustand**. Tests con **Vitest**. Dev con proxy de Vite al backend; en prod el bundle
se sirve desde el propio backend (mismo origen → air-gapped, sin CDNs).

## 2. Qué se entregó

### F3.0 — Scaffold + conexión (PR #19)
- Espejo tipado del contrato en `src/api/types.ts` (WS + modelos).
- Cliente **REST** (`src/api/rest.ts`, Bearer opt-in) y **WS** (`src/api/ws.ts`) con
  **reconexión** (backoff exponencial + jitter) y **re-suscripción idempotente** al
  reconectar. Helpers puros testeables (`buildWsUrl`, `nextBackoffMs`,
  `parseServerMessage`).
- `src/api/connection.ts`: orquesta REST+WS hacia los stores (singleton, fuera de React).
- Stores Zustand: `tagStore` (tags en vivo + reducer puro `applyTagValues` + buffer de
  sparkline), `sessionStore` (token + project_id, persist localStorage),
  `connectionStore` (status + snapshot + error).
- UI: login opcional, barra de conexión, tabla de tags en vivo con sparkline.
- **Bugfix del backend descubierto al integrar** (ver §4).

### F3.1 — Editor de canvas (PR #20, sin cambios en backend)
- **Modelo uniforme** del nodo del editor (`src/editor/model.ts`): un solo
  `EditorNodeData` = `{ label, kind, subtype, params }` para los tres tipos de nodo.
  La idea: no duplicar en el frontend la lógica de los tres nombres de campo del
  backend (`config`/`params`/`props`).
- **Mapping puro** (`src/editor/mapping.ts`): `toProjectNode`/`fromProjectNode`/
  `buildProject` expanden/colapsan ese shape uniforme al contrato del backend. El
  round-trip `fromProjectNode(toProjectNode(n))` es idempotente (test).
- **projectStore** (Zustand + persist): nodes/edges/selección/meta; acciones
  add/update/remove/onChanges/onConnect. Diseño persistido en localStorage.
- **Paleta** arrastrable (HTML5 DnD) → **canvas editable** (`screenToFlowPosition` al
  soltar, conectar, seleccionar, borrar con Supr) → **inspector** (label, subtipo que
  reinicia params, params tipados número/booleano/texto + editor JSON avanzado).

**Tests:** frontend 39 verdes; backend 82 verdes; `tsc --noEmit` + `vite build` limpios.

## 3. Decisiones de diseño (para validar, no para reabrir sin motivo)

1. **Modelo uniforme del editor** con mapping al backend, en vez de tres tipos de nodo
   separados en el front. ¿Simplificación correcta o esconde un acoplamiento que
   molestará en F3.2/F3.3?
2. **`ConnectionController` singleton fuera de React** (la red no depende del ciclo de
   vida de componentes; la UI solo observa stores). ¿De acuerdo, o preferís un
   hook/provider?
3. **Reconexión WS**: backoff exponencial + jitter, re-suscripción del set deseado al
   reabrir. Los `write` que caen con el socket cerrado **se pierden** (no se encolan) —
   los `subscribe` sí se re-emiten. ¿Aceptable para v1?
4. **Persistencia local con `localStorage`** (no IndexedDB) para sesión y diseño. El
   roadmap mencionaba "LocalStorage/IndexedDB"; elegimos localStorage por simplicidad.
   ¿Suficiente para el tamaño de proyecto esperado?
5. **Auth opt-in respetada en el cliente**: sin usuarios el backend va abierto; con
   token, Bearer en REST y `?token=` en el handshake WS. Sin renegociar el contrato.
6. **Tests**: priorizamos **lógica pura** (reducers, helpers, mapping, store) + unos
   pocos render tests (jsdom). No hay e2e de navegador en CI (se verificó a mano con
   Playwright). ¿Cobertura adecuada para el presupuesto?

## 4. Bugfix del backend descubierto al integrar (revisar la corrección)

Al hacer la verificación e2e REST+WS contra el simulador Modbus, el WebSocket **cerraba
toda conexión en runtime** con `TypeError: unhashable type: '_Client'`.

- **Causa:** `_Client` es un `@dataclass` (eq=True por defecto → **unhashable**), pero
  se usa como clave de `set`/`dict` de enrutado (`_clients`, `_subs`, `per_client`).
- **Por qué no lo cazaron los tests:** solo cubrían `_enqueue`, nunca
  `connect`/`subscribe`/`on_tag_update`.
- **Fix:** `@dataclass(eq=False)` (identidad por objeto) + 2 tests de regresión
  (hashabilidad y camino real connect→subscribe→on_tag_update).

**Pregunta:** ¿`eq=False` es la elección correcta (identidad por objeto para una
conexión), o preferiríais `@dataclass(frozen=True)`/`__hash__` explícito? ¿Veis otros
sitios del backend con el mismo patrón latente?

## 5. Puntos donde MÁS queremos vuestra crítica

- **`src/api/ws.ts`** — corrección de la máquina de estados de reconexión (timers,
  `closedByUser`, doble `onerror`/`onclose`, fugas de timers). ¿Algún caso en que se
  quede reconectando en bucle o duplique sockets?
- **`src/api/connection.ts`** — orquestación REST+WS y manejo de errores del snapshot.
- **`src/editor/mapping.ts` + `model.ts`** — ¿el shape uniforme aguanta bien F3.2
  (binding por `tag_id`) y F3.3 (import/export + LogicNode sandbox)?
- **`src/store/projectStore.ts`** — `persist` de React Flow nodes/edges: ¿riesgo de
  guardar estado transitorio (dragging/selección) o de incompatibilidad al subir de
  versión de React Flow?
- **Seguridad** — token en `localStorage` y en query param del WS (`?token=`). Sabemos
  que el query param puede acabar en logs; el backend cachea el rol en el handshake.
  ¿Lo dejamos así en v1 o proponéis subprotocolo/cookie ya?

## 6. Diferido a propósito (NO reabrir salvo riesgo)

- **F3.2:** widgets HMI (tanque/válvula/gráfico) con data-binding en vivo por `tag_id`.
- **F3.3:** import/export del JSON de proyecto (el mapping ya está) + `LogicNode` con
  sandbox (asteval para cálculos; WASM Wasmer/Extism para Python real — Docker
  descartado por cold-start).
- **UI para definir Tags** (los data points id/driver/address): aún no existe; llega en
  F3.2/F3.3. Por eso el editor hoy modela topología pero un `POST /projects` desde el
  editor no tendría tags que leer todavía.
- **e2e de navegador en CI**, i18n, temas claros, undo/redo, multi-selección avanzada.
- Backend: Redis multi-worker, ABAC/Casbin, Vault, TimescaleDB, tracing OTel (Fase 4).

## 7. Cómo ejecutarlo

```
# Frontend (no necesita backend para el editor F3.1)
cd frontend && npm install && npm run dev   # http://localhost:5173
npm test                                     # 39 verdes
npm run build                                # tsc + vite build

# Backend (para datos en vivo, F3.0) — nota: seguridad fail-closed
#   dev/demo: IIOT_ALLOW_ANONYMOUS=true
#   luego POST /projects con un proyecto (ver DEMO.md) y "Conectar" en la UI
```

Gracias. Devolvednos los hallazgos como tabla (BLOCKER/MEDIA/BAJA/NIT + archivo:línea)
y los integramos como "Rev N".
