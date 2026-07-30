# Roadmap — Plataforma IIoT Open Source

> Plan por fases, con estimación de esfuerzo y una **estrategia explícita de
> ahorro de tokens/coste**, para construir el sistema sin agotar presupuesto de
> IA y dejar margen para otros usos. Complementa `ARCHITECTURE.md`.
>
> **Última revisión:** 2026-07-26.

---

## 0. Flujo de trabajo y estrategia de coste (leer primero)

**Roles del equipo (humano + IA):**
- **Claude (Opus)** implementa el código **fase por fase**.
- **GLM y Gemini** son **revisores/críticos**: sobre cada fase entregada proponen
  mejoras, alternativas y ajustes para hacer el sistema más fluido. Sus aportes
  aceptados se integran como una nueva "Rev N" en los documentos y luego en el código.

El objetivo es **no gastar todo el presupuesto de tokens de golpe**. Reglas:

1. **Cerrar el diseño ANTES de codificar.** Hecho: `ARCHITECTURE.md` es la fuente
   de verdad. No se re-discute arquitectura en cada sesión (eso quema tokens
   repitiendo contexto). Los revisores comentan sobre el diseño cerrado, no lo
   reabren entero.

2. **Fases atómicas y verificables.** Cada fase produce algo *ejecutable y
   testeable* (F1 = 14 tests verdes). Se cierra, se commitea, y se abre la
   siguiente en **sesión nueva** (contexto mínimo → menos tokens por llamada).

3. **Contexto mínimo por sesión.** Trabajar carpeta por carpeta; apuntar solo a
   los archivos de la fase, no cargar todo el repo.

4. **Ciclo revisar-una-vez, integrar-en-lote.** Los revisores dan feedback sobre
   la fase entregada; se integra en un solo pase (como Rev 3/Rev 4), no en un
   ida-y-vuelta continuo que multiplica llamadas.

5. **Presupuesto por fase (semáforo).** Si una fase supera ~1.5× su estimación de
   esfuerzo, parar y revisar el enfoque en vez de seguir quemando.

6. **Semáforo por sesión, no solo por fase (Rev 4).** Una sesión de *debug* puede
   consumir más tokens que toda una fase de implementación. Si el trabajo entra en
   bucle "prueba esto → no funciona" (p. ej. pelear con una API de librería en
   transición), **cortar y cambiar de enfoque antes** del 1.5× de fase, no diferir
   hasta agotar la fase. *(Ejemplo real: el pin de `pymodbus` a `<3.9` se decidió al
   toparse con el datastore en migración de 3.14, en vez de seguir depurándolo.)*

---

## 1. Fases

Estimaciones en **jornadas de trabajo efectivo** (no días de calendario) para 1
desarrollador con apoyo de IA. `[dep]` = depende de.

### Fase 0 — Fundaciones del repo · *~0.5 j* ✅ **Completa**
Diseño cerrado y repo listo para construir.
- [x] `README.md` (spec de alto nivel)
- [x] `ARCHITECTURE.md` consolidado (Rev 1–4)
- [x] `ROADMAP.md` (este archivo)
- [x] `pyproject.toml` + estructura de carpetas del backend
- [x] `docker-compose.yml` (backend + **simulador Modbus TCP**) para validar sin PLC físico

### Fase 1 — Núcleo del motor (MVP ejecutable) · *~3–4 j* ✅ **Completa (14 tests verdes)**
El corazón: productor/TagCache/consumer con **un** driver, end-to-end.
- [x] `models/` — Pydantic v2: `Tag` (`deadband`/`deadband_mode`, R4), nodos
      discriminados por `type`, `Project` como unión discriminada por `schema_version` (R5)
- [x] `ws/protocol.py` — esquema de mensajes WS (R1)
- [x] `drivers/base.py` (async `write_tag`, Rev 3) + `drivers/registry.py` (Factory + decorador)
- [x] `drivers/modbus_driver.py` (real, lectura por bloques) + `drivers/modbus_sim.py`
- [x] `engine/tag_cache.py` — deadband + copy-on-write (R3)
- [x] `engine/runtime.py` con **`asyncio.TaskGroup`** (R2) + `scan_scheduler.py` neutro (Rev 3)
- [x] `ws/manager.py` (ConnectionManager con colas acotadas + backpressure drop-oldest)
- [x] `api/` (`POST /projects`, `GET /projects/current`, `GET /tags`) + `main.py` WS `/ws`
- [x] `pyproject.toml`: pin **`pymodbus>=3.6,<3.9`** (R6, ver §0.6)
- [x] Tests: deadband, backpressure, unión discriminada, registry, roundtrip driver↔sim,
      y **end-to-end** API→runtime→tags; simulador en fixture de pytest reutilizable (R6)
- **Salida:** ✅ backend levanta, conecta al Modbus simulado y expone valores por API/WS.
- **Modelo:** implementado por Opus; pendiente de revisión por GLM/Gemini. `[dep: F0]`

### Fase 2 — Drivers reales + persistencia + multi-tenant · *~5–6 j* (sub-fases)
Partida en sub-pasos testeables (Rev 7 afinó el alcance con ingesta híbrida y
multi-tenant). Cada sub-fase se cierra verde antes de la siguiente.

- **F2.0 — Núcleo multi-tenant** ✅ **Completa (26 tests verdes)**
  - [x] Orden temporal en `TagCache.update` (descarta out-of-order, Rev 7)
  - [x] `project_id` transversal (`ProjectV1`) + `TagCache` segmentado por proyecto
  - [x] `Runtime`/`TaskGroup` por `project_id` (aislamiento noisy-neighbor) vía `AppState`
  - [x] `ConnectionManager` global enrutando por `(project_id, tag_id)`; API/WS project-aware
- **F2.1 — Persistencia** ✅ **Completa (33 tests verdes)**
  - [x] `storage/` Repository abstracto + `SQLiteHistorian` (sqlite3 stdlib, air-gapped)
  - [x] `TagBuffer` suscriptor **raw** con flush en batch (por tiempo o tamaño)
  - [x] Endpoint `GET /history?project_id=&tag_id=&limit=` + wiring en `AppState` (startup/shutdown)
  - *(TimescaleDB/PostgreSQL = misma interfaz Repository, otra implementación; F2.4+)*
- **F2.2 — Rama MQTT** ✅ **Completa (43 tests verdes)**
  - [x] Unificación poll/push: `BaseDriver.run(publish, stopping)` (polling por defecto;
        push lo sobrescribe) — el Runtime trata igual a Modbus y MQTT
  - [x] `drivers/mqtt_driver.py` (aiomqtt, import perezoso): parsea JSON → `TagCache`,
        **respeta el `ts` del Edge**, **LWT → `quality="bad"`**, flag `sparkplug` diseñado
  - [x] Tests de parsing puros (mapeo por address, ts, LWT, no-JSON) sin broker
  - *(TLS y escritura vía MQTT command topic → F2.4)*
- **F2.3 — Drivers S7 + OPC UA** ✅ **Completa (52 tests verdes)**
  - [x] `drivers/s7_driver.py` (polling): `python-snap7` en `to_thread` (no bloquea el
        loop), direcciones `DB{n}.{offset}`, decode/encode S7 big-endian, agrupación por DB
  - [x] `drivers/opcua_driver.py` (push): `asyncua` subscriptions, mapeo NodeId→tag
  - [x] **D-M4:** agrupación por bloques extraída a `blockutil.group_contiguous_spans`,
        compartida por Modbus y S7
  - [x] Tests puros (parseo/decode/encode/mapeo) sin PLC/servidor; `DEMO.md` para presentar
  - *(prueba en vivo de S7/OPC UA requiere PLC/servidor real)*
- **F2.4 — Seguridad + valor añadido:** Fernet (clave externa) + RBAC + audit log;
  Motor de Alarmas (suscriptor) + notificación; `observability/metrics.py` (Prometheus) + `health.py`.
- **Ejecución:** implementa Opus (atención a snap7/threading y seguridad); revisan GLM/Gemini. `[dep: F1]`

### Fase 3 — Frontend (canvas HMI) · *~5–6 j*
- [ ] Scaffold React + React Flow; paleta / canvas / inspector
- [ ] Cliente WebSocket + store de tags en tiempo real
- [ ] Persistencia local (LocalStorage / IndexedDB)
- [ ] Widgets HMI base (tanque, válvula, gráfico) + nodos de driver/lógica
- [ ] Import/export del JSON de proyecto (mismo `schema_version` que backend)
- **Salida:** diseñar un proceso arrastrando nodos y ver datos en vivo.
- **Ejecución:** implementa Opus (el contrato WS↔canvas ya está fijado en F1);
  revisan GLM/Gemini. `[dep: F1]` (puede solaparse con F2)

### Fase 4 — Escalado, multi-tenant y hardening (cloud-native) · *~4–5 j*
Solo cuando se necesite el modo cloud-native. **Diferible.**
- [ ] `ws/broker.py` — RedisBridge (pub/sub entre workers) + `topics.py`
- [ ] RBAC + **ABAC** con Casbin (multi-planta) + JWT en handshake WS
- [ ] Vault para secretos + rotación de clave Fernet
- [ ] `entry_points` en `DriverRegistry.discover()` (plugins externos)
- [ ] Tracing OpenTelemetry
- [ ] Sparkplug B (implementación Protobuf) si el flag se activa
- **Ejecución:** implementa Opus (Redis/Casbin/seguridad son críticos);
  revisan GLM/Gemini. `[dep: F2, F3]`

### Fase 5 — Empaquetado y despliegue · *~2 j*
- [ ] `docker-compose.yml` completo por modo (air-gapped / híbrido / cloud)
- [ ] Docs de instalación + `HEALTHCHECK` + guía de operación
- [ ] Build del frontend embebido para air-gapped (sin CDNs)
- **Ejecución:** implementa Opus; revisan GLM/Gemini. `[dep: todas]`

---

## 2. Resumen de esfuerzo

| Fase | Esfuerzo | Entregable | ¿Diferible? |
|---|---|---|---|
| F0 Fundaciones | ~0.5 j | Repo + diseño cerrado | no |
| **F1 Núcleo motor** | ~3–4 j | **MVP en vivo (Modbus)** | **no — prioridad** |
| F2 Drivers + persistencia | ~4–5 j | Protocolos reales, histórico, alarmas | no |
| F3 Frontend canvas | ~5–6 j | HMI visual en vivo | no |
| F4 Escalado/multi-tenant | ~4–5 j | Cloud-native | **sí (hasta necesitarlo)** |
| F5 Empaquetado | ~2 j | Despliegue por modo | parcial |
| **Total v1 (F0–F3, F5)** | **~15–18 j** | Plataforma usable single-planta | — |
| Total con cloud (F4) | ~19–23 j | Multi-planta escalable | — |

**Camino mínimo a algo usable:** F0 → F1 → F3 (un driver + canvas) ya da una demo
funcional. F2 y F4 amplían protocolos y escala.

---

## 3. Cómo arrancamos (siguiente acción)

Propuesta para gastar poco y avanzar: cerrar **F0** (pyproject + estructura +
compose esqueleto) y hacer **F1** hasta el hito "ver un tag Modbus por WebSocket".
Eso es un MVP demostrable con un único driver, y es donde conviene invertir el
razonamiento de Opus (interfaces); el resto de drivers y el frontend se rellenan
después con modelos más económicos.
