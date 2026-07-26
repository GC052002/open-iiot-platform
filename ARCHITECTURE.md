# Arquitectura — Plataforma IIoT Open Source

> Documento único de arquitectura y decisiones de diseño para la plataforma IIoT
> (reemplazo Open Source de WinCC / SCADA / Ignition). Complementa el `README.md`
> (especificación de alto nivel) y el `ROADMAP.md` (fases, tiempos y presupuesto).
>
> **Estado:** propuesta de diseño consolidada (aún sin implementación de código).
> **Versión del documento:** consolidada (Rev 1 Claude + Rev 2 externa Gemini/GLM).
> **Última revisión:** 2026-07-26.

---

## 0. Cómo leer este documento

Este archivo unifica dos rondas de revisión:

- **Rev 1** — arquitectura base (motor productor/consumidor, drivers, seguridad).
- **Rev 2** — deltas externos (escalado multi-worker, ABAC, observabilidad,
  aiomqtt, etc.), aceptados con dos matices y una estrategia de fases.

Todo lo aceptado está integrado aquí como **una sola decisión**. Cada capacidad
avanzada indica en qué **fase** entra (ver `ROADMAP.md`) para no construir todo
de golpe.

**Principio rector de alcance:** *lo mínimo que funciona en modo air-gapped
single-worker es v1; lo que solo hace falta en cloud-native multi-planta se
difiere a fases posteriores.*

---

## 1. Objetivo y alcance

Software de código abierto, modular y seguro para Industria 4.0. Entorno de
diseño visual e interactivo (estilo Node-RED / WinCC / Ignition) para
integración de sistemas, HMI, control y comunicación con PLCs e instrumentación
industrial, sin licencias costosas.

Dos capas desacopladas:

- **Frontend** — UI + canvas interactivo (React + React Flow).
- **Backend** — motor asíncrono de comunicaciones y tiempo real (Python 3.11+
  con FastAPI).

---

## 2. Vista general de la arquitectura

```
┌──────────────────────────────── FRONTEND (React + React Flow) ────────────────────────────────┐
│  Paleta (Drivers/Lógica/Widgets) · Canvas · Inspector de propiedades · Persistencia local       │
└───────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                             │  WebSocket (streaming)  +  REST (config/escrituras)
┌───────────────────────────────────────────▼────────────────────────────────────────────────────┐
│                                    BACKEND (FastAPI + asyncio)                                    │
│                                                                                                   │
│   Drivers (productores) ─► TagCache (última muestra + deadband) ─► Broadcaster local ─► WS clients│
│   · S7 (snap7, en hilo)         │                                    ▲                             │
│   · Modbus (pymodbus, hilo)     ├─► Motor de Alarmas (suscriptor) ─► Notificaciones (Telegram/SMTP)│
│   · OPC UA (asyncua, nativo)    ├─► TagBuffer (suscriptor) ─► batch writes ─► TimescaleDB/SQLite   │
│   · MQTT (aiomqtt, TLS)         └─► RedisBridge (pub/sub) ─► broadcasters de otros workers [F3]    │
│                                                                                                   │
│   Cola de comandos (escrituras) ◄──────── REST · RBAC(+ABAC) · audit log · patrón Command         │
│   Seguridad: cifrado Fernet (clave externa) · Observabilidad: Prometheus /metrics + health [F2+]  │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Principio central:** productor / consumidor totalmente desacoplado. Los drivers
**nunca** hablan directamente con los WebSockets; escriben al **TagCache** y
varios suscriptores independientes (Broadcaster, Alarmas, TagBuffer) consumen de
él (patrón Observer). Esto separa la cadencia de polling de la de render y evita
que un cliente lento afecte al scan.

`[F2]`, `[F3]`… indican la fase del `ROADMAP.md` en que se implementa cada pieza.

---

## 3. Riesgos y decisiones (base — Rev 1)

Ordenados por prioridad. Riesgo → decisión adoptada.

### 3.1 `python-snap7` bloquea el event loop — **crítico**
Wrapper sobre librería C **síncrona**; llamarlo en una corrutina bloquea todo el
loop (demás drivers, WebSockets, alarmas). Igual, parcialmente, para `pymodbus`.
**Decisión:** todo driver bloqueante corre fuera del loop vía
`asyncio.to_thread` / `run_in_executor` con `ThreadPoolExecutor` dedicado (o
proceso por driver en alta carga). El core se uniforma con un *Adapter* detrás de
`BaseDriver` y no sabe si el driver es síncrono o async nativo.

### 3.2 Lecturas por bloque, no por tag — **rendimiento**
**Decisión:** un `ScanScheduler` agrupa tags contiguos por driver y rango (DB /
zona de memoria) en una sola petición y rebana en memoria. Diferencia entre
~50 ms y ~2 s de ciclo de scan.
**Neutralidad de protocolo (Rev 3):** el `ScanScheduler` **no** conoce la
semántica de "contiguo" de ningún protocolo. Entrega al driver una lista genérica
de `Tag` y es el `BaseDriver` (o su subclase) quien traduce qué significa
agrupar/optimizar en su contexto — rangos de Holding Registers en Modbus, `DB` en
S7, subárboles de nodos en OPC UA. Así F2 añade S7/OPC UA sin tocar el scheduler.

### 3.3 Desacople polling ↔ WebSocket — **rendimiento / estabilidad**
**Decisión:** los drivers escriben al TagCache; un emisor independiente hace
*push* solo con **cambios** (report-by-exception / deadband) a cadencia limitada
(5–10 Hz máx).

### 3.4 Backpressure en WebSockets — **estabilidad**
**Decisión:** cola **acotada** por cliente (`asyncio.Queue(maxsize=N)`) con
descarte del valor **más viejo** — en telemetría, el último valor es el que
importa.

### 3.5 Seguridad de credenciales (Fernet) — **seguridad**
Lo determinante es **dónde vive la clave**. **Decisión:** la clave Fernet
proviene de fuente externa (nunca del JSON ni versionada); mecanismos concretos
por modo de red en **§10.4**. Contempla rotación.

### 3.6 RBAC real en el backend — **seguridad**
Bloquear el canvas en React es UX, no seguridad. **Decisión:** autorización
impuesta en cada endpoint del backend; toda **escritura** a PLC se audita (quién,
cuándo, valor anterior → nuevo) vía patrón *Command* con confirmación explícita.
Extensión ABAC multi-planta en **§10.2**.
**Contrato de escritura desde F1 (Rev 3):** aunque F1 es principalmente lectura,
la firma asíncrona de escritura se define en `BaseDriver` **desde la Fase 1**
para que el flujo Command de F2 encaje sin parches:
`async def write_tag(self, tag_id: str, value: Any) -> bool: ...`

### 3.7 Esquema del JSON de proyecto versionado — **mantenibilidad**
**Decisión:** `schema_version` en el JSON desde el día 1 y validación con
**Pydantic v2**. Plan de migraciones entre versiones.

### 3.8 Persistencia de histórico y alarmas — **arquitectura**
**Decisión:** PostgreSQL + **TimescaleDB** en despliegues con recursos;
**SQLite** para air-gapped / edge. Abstraído tras un **Repository** para no
acoplar el motor al motor de BD.

### 3.9 OPC UA y MQTT — aprovechar async nativo
**Decisión:** OPC UA usa **subscriptions** del servidor (no polling manual); MQTT
usa **aiomqtt** (async nativo, ver §11.2). Ambos publican al mismo TagCache.

### 3.10 Endurecimiento de la Fase 1 (Rev 4) — evitar refactor del core
Seis decisiones que deben cerrarse **dentro de F1** para no refactorizar el core
antes del hito demostrable:

- **R1 — Contrato de mensajes WS es entregable de F1.** `ws/protocol.py` con el
  esquema Pydantic de mensajes (`tag_update`, `subscribe`, `ack`, `overflow`),
  definido con Opus junto a `BaseDriver`. F3 (frontend) consume ese contrato
  estable sin renegociarlo. *(Antes flotaba entre F1 y F3.)*
- **R2 — Concurrencia estructurada en `runtime.py`.** Usar
  **`asyncio.TaskGroup`** (Python 3.11+): un grupo por driver, cancelación en
  cascada y *cleanup* garantizado. Nada de `create_task` sueltos (fugas de tareas
  en fallo, shutdown sucio, caídas en reconexiones reales).
- **R3 — Política de concurrencia del TagCache.** Múltiples writers (drivers) +
  readers (broadcaster ya en F1). **Decisión:** *lock por tag* (granularidad
  fina) o *copy-on-write* de la entrada; documentar la elección en
  `tag_cache.py`. Evita datos mezclados bajo carga.
- **R4 — Deadband en el modelo `Tag` desde F1.** `deadband: float = 0.0` y
  `deadband_mode: Literal["abs","pct"] = "abs"`. `0.0` = reportar todo (tests).
  Sin esto, un analógico ruidoso satura el WS al conectar el primer cliente.
- **R5 — `schema_version` con dispatcher.** Modelar `Project` como **unión
  discriminada** por `schema_version` desde F1, aunque solo exista `v1`. Coste
  cero ahora, migración trivial en F2/F3.
- **R6 — Pinear `pymodbus` y fijar el simulador.** `pymodbus>=3.6,<4` en
  `pyproject.toml` y el simulador (`StartAsyncTcpServer`) en un **fixture de
  pytest reutilizable**. Evita tests verdes en local y rotos en `pip install`
  limpio.

---

## 4. Estructura del motor (productor / TagCache / consumidores)

```
Drivers (productores) ──► TagCache (última muestra + deadband) ──┬─► Broadcaster ──► WS (consumidores)
   cada uno en su                                                ├─► Motor de Alarmas ──► notificaciones
   propia tarea/hilo                                             └─► TagBuffer ──► batch ──► Timescale/SQLite
        ▲                                                              (suscriptor de persistencia, §11.1)
        └──────────────── Cola de comandos (escrituras) ◄──────────── REST + RBAC(+ABAC) + audit
```

- **Driver loop:** cada driver es una `asyncio.Task` independiente; los síncronos
  envuelven I/O en `to_thread`. Ante caída de un PLC, reintenta con backoff **sin**
  afectar a los demás.
- **TagCache:** `dict[tag_id -> última muestra]`. Aplica deadband y notifica a
  suscriptores solo ante cambios significativos.
- **Broadcaster / ConnectionManager:** `dict[tag_id -> set[cliente]]`; cada
  cliente con `asyncio.Queue(maxsize=N)` y descarte del más viejo al llenarse.
- **Motor de Alarmas:** suscriptor del TagCache (Observer); evalúa umbrales y
  dispara notificaciones + registro histórico.
- **TagBuffer:** suscriptor de persistencia; acumula muestras y hace *flush* en
  batch (cada N s o M muestras) para no escribir 1 fila por lectura (§11.1).

---

## 5. Estructura de carpetas propuesta (backend)

Las carpetas marcadas `[Fn]` se crean en esa fase; el resto es v1.

```
backend/
  app/
    main.py                  # FastAPI app + lifespan (arranque/parada del engine)
    api/                     # REST: proyectos, auth, escrituras (Command)
    ws/
      protocol.py            # [F1, Rev 4] esquema Pydantic de mensajes WS (tag_update/subscribe/ack/overflow)
      manager.py             # ConnectionManager local + broadcaster (colas acotadas)
      broker.py              # [F3] RedisBridge (pub/sub entre workers)
      topics.py              # [F3] índice tag_id -> set[client_id] (routing selectivo)
    engine/
      runtime.py             # orquesta workers + tag cache
      tag_cache.py           # última muestra + deadband / report-by-exception
      scan_scheduler.py      # agrupa tags en bloques por driver
    drivers/
      base.py                # BaseDriver abstracto: connect / read_block / write_tag(async) / disconnect
      registry.py            # Factory + registro por decorador (+ entry_points en F3, §11.3)
      modbus_driver.py       # pymodbus (driver de referencia de v1)
      s7_driver.py           # [F2] snap7 en thread pool (Adapter sobre lib síncrona)
      opcua_driver.py        # [F2] asyncua (async nativo, subscriptions)
      mqtt_driver.py         # [F2] aiomqtt / TLS (flag sparkplug diseñado, impl. diferida §10.3)
    models/                  # Pydantic v2: esquema de proyecto / nodos / tags (schema_version)
    security/                # RBAC + Fernet + audit log (ABAC/Casbin en F3, §10.2)
    storage/                 # Repository de histórico/alarmas (SQLite v1 / Timescale F2+)
    observability/           # [F2] metrics.py (Prometheus) · health.py  ·  tracing.py [F3]
  tests/
docker-compose.yml
pyproject.toml
```

---

## 6. Patrones de software

| Patrón | Aplicación |
|---|---|
| **Factory + Registry** | Instanciar drivers por `type` del nodo. Auto-registro por decorador (`@register_driver("modbus_tcp")`); `entry_points` para plugins externos en F3 (§11.3). |
| **Adapter** | Uniformar drivers síncronos (snap7) y async nativos (asyncua/aiomqtt) bajo `BaseDriver`. |
| **Strategy** | Nodos de lógica (escalado lineal, deadband, media móvil): transformaciones intercambiables. |
| **Observer / Pub-Sub** | TagCache → Broadcaster / Alarmas / TagBuffer. Cada consumidor es un suscriptor. |
| **Command** | Escrituras a PLC: encapsulan la operación → audit log + confirmaciones naturales. |
| **Repository** | Abstraer persistencia de histórico/alarmas del motor de BD concreto. |

---

## 7. Modos de red (del README)

| Modo | Descripción | Implicaciones técnicas |
|---|---|---|
| **Local aislado (air-gapped)** | 100% offline, sin CDNs. | Assets del frontend empaquetados localmente; SQLite; sin servicios externos en runtime; single-worker (Redis opcional). |
| **Híbrido** | Local + exposición remota vía VPN/túnel. | Endurecer TLS y auth en la superficie remota; separar red OT de la exposición. |
| **Solo nube (cloud-native)** | Servidor WAN/VPS multi-planta. | Multi-tenant (ABAC); secretos centralizados (Vault); escalado horizontal (Redis Pub/Sub); observabilidad completa. |

---

## 8. Deltas aceptados de la Rev 2 (integrados)

Extensiones sobre la base, cada una atada a su fase. La numeración conserva la de
la revisión externa para trazabilidad.

### 10.1 Escalado horizontal del Broadcaster (Redis Pub/Sub) — **crítico** `[F3]`
El `ConnectionManager` es **local por worker**: con `uvicorn --workers N`, un
driver del worker A no entrega updates a clientes del worker B — el broadcast se
rompe en silencio.
**Decisión:** `RedisBridge` (canal `tag_updates`) obligatorio en cloud-native,
opcional en híbrido/air-gapped (1 worker basta). El TagCache sigue siendo la
fuente de verdad intra-worker; **Redis es solo transporte** entre workers.
**Matiz (Claude):** el *serializer* msgpack/protobuf es optimización prematura —
**JSON en v1**; msgpack solo si el perfilado lo justifica.

### 10.2 RBAC → RBAC + ABAC multi-planta — **seguridad** `[F3]`
Por rol no basta en multi-planta: un ingeniero de Planta A no debe ver/escribir
tags de Planta B.
**Decisión:** modelo híbrido con **Casbin**. Roles: `admin`, `engineer`,
`operator`, `viewer`. Atributos: `plant_id`, `zone_id`, `asset_id`, `project_id`.
Regla: *role permite acción AND atributos coinciden con el recurso*. Handshake WS
con JWT y validación por suscripción. En single-plant, RBAC simple basta (ABAC
inactivo).

### 10.3 Sparkplug B como modo MQTT opcional — **interoperabilidad** `[F2 diseño / F4 impl.]`
MQTT plano no tiene *state management*. Sparkplug B añade birth/death
certificates y namespace estándar — diferenciador frente a Node-RED.
**Decisión (con matiz Claude):** `mqtt_driver.py` se **diseña** con flag
`sparkplug: true|false` desde el inicio, pero la **implementación Protobuf se
difiere** (fuera de v1). `false` → MQTT plano; `true` → payload Protobuf +
`spBv1.0/...` + birth/death.

### 10.4 Gestión concreta de la clave Fernet — **seguridad** `[F1 base / F3 Vault]`
| Modo | Mecanismo | Justificación |
|---|---|---|
| Air-gapped | **SOPS + age** (clave en USB/token, montada al arrancar) | sin red externa |
| Híbrido | Vault on-premise **o** SOPS+age | según infraestructura |
| Cloud-native | **HashiCorp Vault** (dynamic secrets + rotación) | multi-tenant, sin downtime |

La clave **nunca** se commitea ni se hornea en la imagen Docker; el contenedor la
obtiene al arrancar. **Rotación:** re-cifrado de `devices.credentials_encrypted`;
cloud cada 90 días, air-gapped manual con ventana.

### 10.5 Observabilidad — **operaciones** `[F2 métricas/health · F3 tracing]`
**Decisión:**
- **Prometheus** en `/metrics`: por driver (`reads_total`, `reads_failed`,
  `last_read_latency_ms`, `reconnect_count`) y por WS (`connected_clients`,
  `messages_sent`, `queue_overflow_count`).
- **Health checks** en `/health/drivers/{name}` (healthy / last_error /
  last_check) para Docker `HEALTHCHECK` y orquestadores.
- **OpenTelemetry** tracing (span por lectura y por mensaje WS) — diferido a F3.

### 11.1 TagCache vs TagBuffer (desambiguación)
- **TagCache:** última muestra + deadband; hot path → WebSocket.
- **TagBuffer:** batch de muestras para escritura eficiente; hot path →
  persistencia. Es **otro suscriptor Observer** del TagCache (ver §4).

### 11.2 aiomqtt en vez de paho — **implementación**
**Decisión:** `aiomqtt` como dependencia única del backend (async nativo, sin
envolver callbacks en `to_thread`). `paho` directo descartado en backend.

### 11.3 Plugin discovery — decorador ahora, `entry_points` después
**Decisión:** ambos, en fases. F1–F2: `@register_driver` para built-in. F3:
`DriverRegistry.discover()` con `entry_points` para paquetes pip externos
(BACnet, EtherNet/IP, DNP3, Profinet) sin tocar el core.

---

## 9. Matriz de decisiones cerradas (§13 de la Rev 2)

| Pregunta | Decisión |
|---|---|
| ¿Decorador + `entry_points` simultáneos? | **Sí**, faseado (built-in por decorador; externos por entry_points en F3). |
| ¿Sparkplug B opcional o fuera de v1? | **Opcional**; flag diseñado desde el inicio, implementación Protobuf diferida a F4. |
| ¿Redis obligatorio en air-gapped? | **No**; opcional single-worker en air-gapped, obligatorio en cloud-native. |
| ¿Serializer msgpack/protobuf en WS? | **No en v1**; JSON hasta que el perfilado justifique msgpack. |
| ¿Firma de escritura (`write_tag`) en F1 o F2? (Rev 3) | **En F1**, en `BaseDriver`, aunque la implementación Command llegue en F2. |
| ¿`ScanScheduler` acoplado a Modbus? (Rev 3) | **No**; scheduler neutro de protocolo, el driver traduce "contiguo" (§3.2). |
| ¿Simulador Modbus en el repo? (Rev 3) | **Sí**; servicio en `docker-compose` desde F0/F1 para validar sin PLC físico. |
| ¿Contrato de mensajes WS, en qué fase? (Rev 4 · R1) | **F1**, en `ws/protocol.py`, definido con Opus. F3 lo consume sin renegociar. |
| ¿Concurrencia del `runtime.py`? (Rev 4 · R2) | **`asyncio.TaskGroup`** (grupo por driver, cleanup garantizado). |
| ¿Locking del TagCache? (Rev 4 · R3) | Lock por tag (fino) o copy-on-write; decisión documentada en `tag_cache.py`. |
| ¿Deadband en el modelo `Tag`? (Rev 4 · R4) | **Desde F1**: `deadband: float=0.0`, `deadband_mode: Literal["abs","pct"]="abs"`. |
| ¿`schema_version` cómo? (Rev 4 · R5) | Unión **discriminada** en `Project` desde F1, aunque solo exista v1. |
| ¿`pymodbus` pinneado? (Rev 4 · R6) | **`pymodbus>=3.6,<3.9`** (3.9+ migra el datastore) + simulador en fixture de pytest. |
| ¿Plantilla `read_block` en `BaseDriver`? (Rev 5 · D-M4) | **Diferida a F2**: se generaliza (`_group_for_protocol`/`_read_group`/`_decode`) cuando existan S7 y OPC UA reales; abstraer con un solo driver sería especulativo. |
| ¿Timeout del cliente de driver? (Rev 5 · D-H2) | **Obligatorio**: todo driver de red acota timeout/retries para que el backoff del runtime se active ante un PLC caído. |
| ¿`stop()` del runtime? (Rev 5 · R-H1) | Cancela las tareas del TaskGroup (no basta señalizar); `TaskGroup.cancel()` nativo llega en py3.13. |

---

_Documento vivo. La planificación temporal y de esfuerzo vive en `ROADMAP.md`._
