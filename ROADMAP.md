# Roadmap — Plataforma IIoT Open Source

> Plan por fases, con estimación de esfuerzo y una **estrategia explícita de
> ahorro de tokens/coste**, para construir el sistema sin agotar presupuesto de
> IA y dejar margen para otros usos. Complementa `ARCHITECTURE.md`.
>
> **Última revisión:** 2026-07-26.

---

## 0. Estrategia de coste (leer primero)

El objetivo es **no gastar todo el presupuesto de tokens de golpe**. Reglas de
trabajo que seguimos en este proyecto:

1. **Un modelo por tipo de tarea (routing de coste):**
   | Tipo de tarea | Modelo recomendado | Por qué |
   |---|---|---|
   | Arquitectura, decisiones críticas, revisión de seguridad | **Opus (Claude)** | razonamiento profundo, pocas llamadas |
   | **Contratos de interfaz y esquemas base** (`ws/protocol.py`, `Tag`/`Node`/`Project`, `BaseDriver`, discriminators Pydantic) | **Opus** | es interfaz, no boilerplate; que el económico no la fije "por la puerta de atrás" (Rev 4) |
   | **Concurrencia del engine** (`runtime.py` TaskGroup, locking del TagCache) | **Opus** | bug de concurrencia = dato silenciosamente incorrecto, no "atasco"; proactivo, no reactivo (Rev 4) |
   | Implementación de drivers/boilerplate repetitivo | **Modelo económico** (Gemini Flash / GLM / Sonnet) | patrón conocido, alto volumen |
   | Frontend React — **store global + sync WebSocket↔Canvas** | **Sonnet** (nivel intermedio) | manejo de conexiones/eventos de render tiene complejidad real (Rev 3) |
   | Frontend React — componentes gráficos estáticos (tanques, medidores, botones) | **Modelo económico** | repetitivo, verificable a ojo |
   | Tests unitarios — happy-path y plantillas | **Modelo económico** | plantilla + casos; delegar ahorra tokens |
   | Tests unitarios — **escenarios del engine** (concurrencia, deadband, overflow) | **Opus define, económico implementa** | sin esto los tests quedan en superficie y R3 se cuela (Rev 4) |
   | Debug puntual difícil | **Opus** solo cuando el económico se atasca | reservar potencia |

2. **Cerrar el diseño ANTES de codificar.** Ya está hecho: `ARCHITECTURE.md` es
   la fuente de verdad. No se re-discute arquitectura en cada sesión (eso quema
   tokens repitiendo contexto).

3. **Fases atómicas y verificables.** Cada fase produce algo *ejecutable y
   testeable*. Se cierra, se commitea, y se abre la siguiente en **sesión
   nueva** (contexto mínimo → menos tokens por llamada).

4. **Contexto mínimo por sesión.** Trabajar carpeta por carpeta. No cargar todo
   el repo; apuntar el modelo solo a los archivos de la fase.

5. **Andamiaje una vez, relleno barato.** Opus define las **interfaces**
   (`BaseDriver`, esquemas Pydantic, contratos WS); los modelos económicos
   rellenan implementaciones contra esas interfaces.

6. **Presupuesto por fase (semáforo).** Si una fase supera ~1.5× su estimación
   de esfuerzo, parar y revisar el enfoque en vez de seguir quemando.

7. **Semáforo por sesión, no solo por fase (Rev 4).** Una sesión de *debug* puede
   consumir más tokens que toda una fase de implementación económica. Si un modelo
   económico entra en bucle "prueba esto → no funciona", **cortar y escalar a Opus
   antes** del 1.5× de fase — el criterio de escalamiento de la fila "Debug puntual"
   es por sesión, no diferido hasta agotar la fase.

---

## 1. Fases

Estimaciones en **jornadas de trabajo efectivo** (no días de calendario) para 1
desarrollador con apoyo de IA. `[dep]` = depende de.

### Fase 0 — Fundaciones del repo · *~0.5 j* ✅ (en curso)
Diseño cerrado y repo listo para construir.
- [x] `README.md` (spec de alto nivel)
- [x] `ARCHITECTURE.md` consolidado (Rev 1 + Rev 2)
- [x] `ROADMAP.md` (este archivo)
- [ ] `pyproject.toml` + estructura vacía de carpetas + `.pre-commit` (ruff/black)
- [ ] `docker-compose.yml` esqueleto (backend + SQLite + **simulador Modbus TCP**
      —`pymodbus.server` o contenedor `diagslave`— para validar sin PLC físico, Rev 3)
- **Modelo:** Opus (cierre de diseño). **Coste:** bajo.

### Fase 1 — Núcleo del motor (MVP ejecutable) · *~3–4 j* — **prioridad**
El corazón: productor/TagCache/consumer con **un** driver, end-to-end.
- [ ] `models/` — Pydantic v2: `Tag` (incl. `deadband: float=0.0`, `deadband_mode:
      Literal["abs","pct"]="abs"`, R4), nodos discriminados por `type`, y `Project`
      como **unión discriminada por `schema_version`** desde v1 (R5)
- [ ] `ws/protocol.py` — **esquema de mensajes WS** (`tag_update`/`subscribe`/`ack`/
      `overflow`), definido con Opus junto a `BaseDriver` (R1) — *entregable de F1*
- [ ] `drivers/base.py` (incl. firma async `write_tag`, Rev 3) + `drivers/registry.py` (Factory + decorador)
- [ ] `drivers/modbus_driver.py` (driver de referencia, contra simulador)
- [ ] `engine/tag_cache.py` — deadband + **política de concurrencia** (lock por tag
      o copy-on-write, documentada, R3)
- [ ] `engine/runtime.py` con **`asyncio.TaskGroup`** (un grupo por driver, cleanup
      garantizado, R2) + `scan_scheduler.py` **neutro de protocolo** (Rev 3)
- [ ] `ws/manager.py` (ConnectionManager con colas acotadas + backpressure)
- [ ] `api/` mínimo: cargar proyecto JSON, listar tags, endpoint WS
- [ ] `pyproject.toml`: pinear **`pymodbus>=3.6,<4`** (R6)
- [ ] Tests del TagCache (concurrencia, deadband, overflow de cola), backpressure y
      registry; simulador Modbus en **fixture de pytest reutilizable** (R6)
- **Salida:** levantar el backend, conectar a un Modbus simulado, ver valores por
  WebSocket en tiempo real. **Hito demostrable.**
- **Modelo:** interfaces con Opus; driver/tests con modelo económico. `[dep: F0]`

### Fase 2 — Drivers reales + persistencia + observabilidad básica · *~4–5 j*
- [ ] `drivers/s7_driver.py` (snap7 en thread pool) `[crítico: no bloquear loop]`
- [ ] `drivers/opcua_driver.py` (asyncua subscriptions)
- [ ] `drivers/mqtt_driver.py` (aiomqtt + TLS; flag `sparkplug` **diseñado**, impl. diferida)
- [ ] `storage/` — Repository + SQLite; `TagBuffer` (batch writes)
- [ ] `security/` — Fernet (clave externa vía env/SOPS) + RBAC básico + audit log
- [ ] Motor de Alarmas (suscriptor) + notificación (Telegram/SMTP)
- [ ] `observability/metrics.py` (Prometheus) + `health.py`
- **Salida:** varios protocolos reales, histórico persistido, alarmas y métricas.
- **Modelo:** cada driver es patrón conocido → **económico**; Opus solo para
  snap7 (threading) y el diseño de seguridad. `[dep: F1]`

### Fase 3 — Frontend (canvas HMI) · *~5–6 j*
- [ ] Scaffold React + React Flow; paleta / canvas / inspector
- [ ] Cliente WebSocket + store de tags en tiempo real
- [ ] Persistencia local (LocalStorage / IndexedDB)
- [ ] Widgets HMI base (tanque, válvula, gráfico) + nodos de driver/lógica
- [ ] Import/export del JSON de proyecto (mismo `schema_version` que backend)
- **Salida:** diseñar un proceso arrastrando nodos y ver datos en vivo.
- **Modelo:** React repetitivo → **económico**; Opus solo para el contrato de
  datos WS↔canvas. `[dep: F1]` (puede solaparse con F2)

### Fase 4 — Escalado, multi-tenant y hardening (cloud-native) · *~4–5 j*
Solo cuando se necesite el modo cloud-native. **Diferible.**
- [ ] `ws/broker.py` — RedisBridge (pub/sub entre workers) + `topics.py`
- [ ] RBAC + **ABAC** con Casbin (multi-planta) + JWT en handshake WS
- [ ] Vault para secretos + rotación de clave Fernet
- [ ] `entry_points` en `DriverRegistry.discover()` (plugins externos)
- [ ] Tracing OpenTelemetry
- [ ] Sparkplug B (implementación Protobuf) si el flag se activa
- **Modelo:** económico para relleno; Opus para Redis/Casbin/seguridad.
  `[dep: F2, F3]`

### Fase 5 — Empaquetado y despliegue · *~2 j*
- [ ] `docker-compose.yml` completo por modo (air-gapped / híbrido / cloud)
- [ ] Docs de instalación + `HEALTHCHECK` + guía de operación
- [ ] Build del frontend embebido para air-gapped (sin CDNs)
- **Modelo:** económico. `[dep: todas]`

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
