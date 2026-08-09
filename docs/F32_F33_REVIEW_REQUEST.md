# Solicitud de revisión — Fase 3.2 + 3.3 · Frontend IIoT/SCADA

> **Para:** GLM 5.2 y Gemini (revisores externos).
> **De:** el equipo (implementación por Claude/Opus).
> **Repo:** `GC052002/open-iiot-platform` · rama `main` · PRs **#23 (F3.2)** y **#25 (F3.3)**.
> **Contexto previo:** F3.0/F3.1 ya revisadas (Rev 14, integrada). Ver
> `docs/F3_REVIEW_REQUEST.md`.

## 0. Cómo queremos la revisión

Equipo humano + IA con **presupuesto de tokens acotado**; revisamos-una-vez /
integramos-en-lote. Por favor:

1. Priorizad **bugs reales, seguridad y decisiones de arquitectura** difíciles de
   revertir, por encima de estilo.
2. Marcad cada punto **BLOCKER / MEDIA / BAJA / NIT** con `archivo:línea`.
3. No reabráis lo **diferido a propósito** (abajo) salvo riesgo que se nos escape.
4. Devolvednos una **tabla** de hallazgos para integrarla como "Rev N".

## 1. Contexto

Plataforma IIoT/SCADA open source. Backend Python (FastAPI+asyncio) completo
(Fase 2). Frontend React+TS+Vite+**@xyflow/react**+**Zustand**, consumiendo el
contrato WS/REST fijado en Fase 1 (`ws/protocol.py`, `models/node.py`). Estas fases
**no cambian el backend**.

Recordatorio de decisiones ya validadas en Rev 14 (no reabrir): modelo uniforme del
editor (`EditorNodeData`), `ConnectionController` singleton, reconexión con
backoff+jitter, mapping puro editor↔backend con round-trip.

## 2. Qué se entregó

### F3.2 — Widgets HMI con data-binding en vivo (PR #23)
- `editor/widgets.tsx`: helpers **puros** `tankFillPct` y `valveState`, + `WidgetBody`
  que se suscribe al `tagStore` por `props.tag_id` y pinta tanque/válvula/gráfico con
  el valor en vivo.
- `editor/nodeTypes.tsx`: el nodo widget delega en `WidgetBody`.
- `editor/model.ts`: `defaultParams` por subtipo de widget (tank min/max; valve
  open_value); `PARAM_TYPES` amplía min/max/open_value.
- `components/Inspector.tsx`: para widgets, `tag_id` es un select de los tags en vivo
  (`connectionStore.rows`), con fallback a texto.

### F3.3 — Editor de Tags + import/export + enviar al backend (PR #25)
- `store/projectStore.ts`: `tags: Tag[]` (data points) con add/update/remove,
  persistidos con debounce; `partialize` limpia estado transitorio (de Rev 14).
- `editor/mapping.ts`: `buildProject(meta, nodes, edges, tags)` → `ProjectV1`.
- `editor/projectIO.ts`: `serializeProject`/`deserializeProject` **puros** (round-trip
  probado) + `downloadJSON`/`readFileText`. Import valida `schema_version:"1"`.
- `components/TagsPanel.tsx`: editor de Tags; `driver_id` se elige entre los nodos
  driver del canvas.
- `components/ProjectToolbar.tsx`: Exportar / Importar / **Enviar al backend**
  (`POST /projects` + `connect`).

**Tests:** frontend **60 verdes** (F3.1=39 → F3.2=53 → F3.3=60). `tsc` + `vite build`
limpios. Verificado e2e con Playwright + backend + simulador Modbus.

## 3. Decisiones de diseño (validar, no reabrir sin motivo)

1. **Widget lee el `tagStore` directamente** (`useTagStore(s => s.tags[tagId])`) dentro
   del nodo de React Flow. ¿Riesgo de rerenders/perf con muchos widgets? ¿Preferís
   selector memoizado / un hook dedicado?
2. **`valveState`/`tankFillPct` puros** con heurística de interpretación (bool/número/
   string, umbral `open_value`). ¿Cubren los casos industriales o falta algo (p.ej.
   calidad `bad` debería forzar "unknown"/alarma visual)?
3. **Binding por tag en vivo** (no contra los tags definidos del proyecto): el select
   se llena de `connectionStore.rows` (snapshot REST del backend conectado). ¿Correcto,
   o el binding debería ofrecer también los tags definidos localmente aunque no estén
   en vivo aún?
4. **Import/export**: `deserializeProject` valida `schema_version` y `name`, pero **no**
   valida en profundidad cada nodo/tag (confía en el backend al enviar). ¿Suficiente
   para v1 o queréis validación con Zod/pydantic-like en el cliente?
5. **Enviar al backend** hace `POST /projects` con `tags` definidos en la UI y luego
   `connect`. Si el proyecto no trae tags, no habrá datos que leer (esperado). ¿OK?
6. **Persistencia**: nodos + edges + **tags** + meta en `localStorage` con debounce
   500ms y `sanitizeNodes`. ¿Algún riesgo con proyectos grandes (límite ~5MB de
   localStorage) que convenga anticipar (IndexedDB)?

## 4. Puntos donde MÁS queremos crítica

- **`editor/widgets.tsx`** — corrección de `tankFillPct`/`valveState` y rerenders del
  `WidgetBody`.
- **`editor/projectIO.ts`** — robustez de `deserializeProject` ante JSON malicioso o
  malformado (no confiar en el archivo). ¿Superficie de riesgo al importar?
- **`components/ProjectToolbar.tsx`** — flujo `POST /projects` + `connect`, manejo de
  errores (ApiError), y que un import no deje el store en estado inconsistente.
- **`store/projectStore.ts`** — que añadir `tags` no rompa las mitigaciones de Rev 14
  (debounce, `partialize`).

## 5. Diferido a propósito (NO reabrir salvo riesgo)

- **`LogicNode` sandbox** (ejecutar lógica del usuario): asteval para expresiones; WASM
  (Wasmer/Extism) para Python real. **Bloque aparte** por ser crítico de seguridad;
  requiere mini-diseño. Es el único pendiente de la Fase 3.
- **Edición de alarmas** en el editor, i18n, temas claros, undo/redo, validación de
  esquema en cliente (Zod), IndexedDB para proyectos grandes.
- Backend: Redis multi-worker, ABAC/Casbin, Vault, TimescaleDB, OTel (Fase 4).
- **Python 3.14**: no soportado aún (R7; Pydantic no lo soporta) — techo `<3.14`.

## 6. Cómo ejecutarlo

```
cd frontend && npm install && npm run dev   # http://localhost:5173
npm test                                     # 60 verdes
npm run build                                # tsc + vite build
# Backend (para datos en vivo): Python 3.11–3.13, IIOT_ALLOW_ANONYMOUS=true,
# arrancar sim + uvicorn; luego "Enviar al backend" desde la UI o POST /projects.
```

Gracias. Devolved los hallazgos como tabla (BLOCKER/MEDIA/BAJA/NIT + archivo:línea).
