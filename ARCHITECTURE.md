# Arquitectura — Plataforma IIoT Open Source

> Documento de arquitectura y decisiones de diseño para la plataforma IIoT
> (reemplazo Open Source de WinCC / SCADA / Ignition). Complementa el
> `README.md`, que actúa como especificación de alto nivel.
>
> **Estado:** propuesta de diseño (aún sin implementación de código).
> **Última revisión:** 2026-07-26.

---

## 1. Objetivo y alcance

Software de código abierto, modular y seguro para Industria 4.0. Entorno de
diseño visual e interactivo (estilo Node-RED / WinCC / Ignition) para
integración de sistemas, HMI, control y comunicación con PLCs e instrumentación
industrial, sin licencias costosas.

El sistema se divide en dos capas desacopladas:

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
│   Drivers (productores)  ─►  TagCache (última muestra + deadband)  ─►  Broadcaster  ─► WS clients │
│   · S7 (snap7, en hilo)          · report-by-exception                 · colas acotadas           │
│   · Modbus (pymodbus)                                                   · suscripción por tag      │
│   · OPC UA (asyncua, async nativo)                                                                 │
│   · MQTT (paho, TLS)          Cola de comandos (escrituras) ◄──────────── REST / RBAC / audit      │
│                                                                                                   │
│   Suscriptores del TagCache: Motor de Alarmas ─► Notificaciones (Telegram / SMTP) + Histórico     │
│   Seguridad: RBAC · cifrado Fernet de credenciales · audit log de escrituras                      │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Principio central:** productor / consumidor totalmente desacoplado. Los drivers
nunca hablan directamente con los WebSockets; escriben al *TagCache* y un
*broadcaster* independiente publica a los clientes. Esto separa la cadencia de
polling de la cadencia de render y evita que un cliente lento afecte al scan.

---

## 3. Revisión de arquitectura: riesgos y decisiones

Ordenados por prioridad. Cada uno incluye el riesgo y la decisión de diseño
adoptada.

### 3.1 `python-snap7` bloquea el event loop — **crítico**

`python-snap7` es un wrapper sobre una librería C **síncrona**. Llamarlo dentro
de una corrutina bloquea todo el event loop de `asyncio` (todos los demás
drivers, los WebSockets, las alarmas). Lo mismo aplica parcialmente a
`pymodbus` según la versión.

**Decisión:** todo driver bloqueante se ejecuta fuera del loop mediante
`asyncio.to_thread` / `run_in_executor` con un `ThreadPoolExecutor` dedicado (o,
en escenarios de alta carga, un proceso por driver). El core del motor no debe
saber si un driver es síncrono o asíncrono nativo — se uniforma vía un *Adapter*
detrás de la interfaz `BaseDriver`.

### 3.2 Lecturas por bloque, no por tag — **rendimiento**

Un panel con cientos de tags no debe generar un request por tag. PLCs Siemens y
Modbus rinden mucho mejor con **lecturas por bloques** (agrupar tags contiguos
por DB / rango de memoria en una sola petición y rebanar en memoria).

**Decisión:** un `ScanScheduler` agrupa tags por driver y por rango contiguo,
minimizando round-trips. Diferencia entre ~50 ms y ~2 s de ciclo de scan.

### 3.3 Desacople polling ↔ WebSocket — **rendimiento / estabilidad**

No transmitir a la UI a la velocidad del polling. Enviar todos los valores en
cada ciclo satura el WebSocket y el render de React.

**Decisión:** los drivers escriben al TagCache; un emisor independiente hace
*push* solo con **cambios** (report-by-exception / deadband) a una cadencia
limitada (p. ej. 5–10 Hz máximo).

### 3.4 Backpressure en WebSockets — **estabilidad**

Un cliente lento (móvil por VPN) no debe hacer crecer una cola en memoria sin
límite.

**Decisión:** cola **acotada** por cliente (`asyncio.Queue(maxsize=N)`) con
política de descarte del valor **más viejo** — en telemetría, el último valor es
el que importa.

### 3.5 Seguridad de credenciales (Fernet) — **seguridad**

Cifrar con Fernet está bien, pero lo determinante es **dónde vive la clave**. Si
la clave está junto al ciphertext, no se protege nada.

**Decisión:** la clave Fernet proviene de variable de entorno / secreto externo
/ archivo con permisos `0600` fuera del repositorio; nunca en el JSON del
proyecto ni versionada. Contemplar rotación de clave.

### 3.6 RBAC real en el backend — **seguridad**

Bloquear el canvas para el Operador en React es UX, no seguridad. La
autorización real (quién escribe a un PLC, quién edita la topología) debe
imponerse en cada endpoint del backend.

**Decisión:** RBAC aplicado en el backend por endpoint. Toda **escritura** a un
PLC se audita: quién, cuándo, valor anterior → nuevo. Escrituras vía *Command*
con confirmación explícita.

### 3.7 Esquema del JSON de proyecto versionado — **mantenibilidad**

Sin versión de esquema, un proyecto guardado con una versión vieja del editor
romperá silenciosamente al importarse.

**Decisión:** `schema_version` en el JSON desde el día 1 y validación con
**Pydantic v2** en el backend. Plan de migraciones entre versiones de esquema.

### 3.8 Persistencia de histórico y alarmas — **arquitectura**

El README no define almacenamiento. Alarmas e histórico necesitan persistencia
de series temporales.

**Decisión:** PostgreSQL + TimescaleDB en despliegues con recursos; SQLite como
opción para el modo air-gapped / edge. Abstraer tras un repositorio para no
acoplar el motor a un motor de BD concreto.

### 3.9 OPC UA y MQTT — aprovechar async nativo

`asyncua` (OPC UA) y `paho`/`asyncio-mqtt` encajan de forma nativa en el loop.

**Decisión:** para OPC UA usar **subscriptions** del servidor en lugar de
polling manual; para MQTT, suscripción por tópico. Ambos publican al mismo
TagCache que los drivers de polling.

---

## 4. Estructura del motor (productor / TagCache / consumidor)

```
Drivers (productores) ──► TagCache (última muestra) ──► Broadcaster ──► WS (consumidores)
   cada uno en su          + deadband /                  colas acotadas    suscritos por tag
   propia tarea/hilo        report-by-exception           (descarte FIFO)
        ▲                                                        │
        └──────────────── Cola de comandos (escrituras) ◄────────┘  (REST + RBAC + audit)
```

- **Driver loop:** cada driver es una `asyncio.Task` independiente. Los
  síncronos envuelven su I/O en `to_thread`. Ante caída de un PLC, esa tarea
  reintenta con backoff **sin** afectar a los demás.
- **TagCache:** `dict[tag_id -> última muestra]`. Aplica deadband y notifica a
  suscriptores solo ante cambios significativos.
- **ConnectionManager / Broadcaster:** `dict[tag_id -> set[cliente]]`; cada
  cliente con `asyncio.Queue(maxsize=N)` y descarte del más viejo al llenarse.
- **Motor de alarmas:** es *otro suscriptor* del TagCache (patrón Observer);
  evalúa umbrales y dispara notificaciones + registro histórico.

---

## 5. Estructura de carpetas propuesta (backend)

```
backend/
  app/
    main.py                  # FastAPI app + lifespan (arranque/parada del engine)
    api/                     # REST: proyectos, auth, escrituras (Command)
    ws/
      manager.py             # ConnectionManager + broadcaster (colas acotadas)
    engine/
      runtime.py             # orquesta workers + tag cache
      tag_cache.py           # última muestra + deadband / report-by-exception
      scan_scheduler.py      # agrupa tags en bloques por driver
    drivers/
      base.py                # BaseDriver (interfaz abstracta: connect/read/write/disconnect)
      factory.py             # Factory + registro de drivers
      s7_driver.py           # snap7 en thread pool (Adapter sobre lib síncrona)
      modbus_driver.py       # pymodbus
      opcua_driver.py        # asyncua (async nativo, subscriptions)
      mqtt_driver.py         # paho / TLS
    models/                  # Pydantic v2: esquema de proyecto / nodos / tags (schema_version)
    security/                # RBAC, cifrado Fernet, audit log
    storage/                 # repositorio de histórico/alarmas (Timescale/SQLite)
  tests/
docker-compose.yml
```

---

## 6. Patrones de software

| Patrón | Aplicación |
|---|---|
| **Factory + Registry** | Instanciar drivers por `type` del nodo. Auto-registro por decorador (`@register_driver("modbus_tcp")`). Añadir protocolo = un archivo, sin tocar el core. |
| **Adapter** | Uniformar drivers síncronos (snap7) y async nativos (asyncua) bajo una misma `BaseDriver`. |
| **Strategy** | Nodos de lógica (escalado lineal, deadband, media móvil): transformaciones intercambiables aplicadas al flujo de datos. |
| **Observer / Pub-Sub** | Desacople TagCache → alarmas / broadcaster / notificaciones. Cada consumidor es un suscriptor. |
| **Command** | Escrituras a PLC: encapsulan la operación → habilitan audit log y confirmaciones de forma natural. |
| **Repository** | Abstraer persistencia de histórico/alarmas del motor de BD concreto. |

---

## 7. Modos de red (del README)

| Modo | Descripción | Implicaciones técnicas |
|---|---|---|
| **Local aislado (air-gapped)** | 100% offline, sin CDNs externas. | Empaquetar todos los assets del frontend localmente; SQLite como opción de BD; sin dependencias de servicios externos en runtime. |
| **Híbrido** | Operación local + exposición remota vía VPN/túnel. | Endurecer TLS y autenticación en la superficie remota; separar red OT de la exposición. |
| **Solo nube (cloud-native)** | Servidor WAN/VPS multi-planta. | Multi-tenant; gestión de secretos centralizada; escalado horizontal del motor. |

---

## 8. Próximos pasos

- [ ] Scaffold del backend: `BaseDriver` + `DriverFactory`, `TagCache`,
      `ConnectionManager` con backpressure y un driver Modbus de ejemplo.
- [ ] Definir el esquema Pydantic del JSON de proyecto (`schema_version`).
- [ ] `docker-compose.yml` con backend + BD.
- [ ] Motor de alarmas como suscriptor del TagCache.
- [ ] Estrategia de gestión de la clave Fernet y almacén de certificados
      (OPC UA X.509 / MQTT TLS).

---

_Este documento es una guía viva; se irá actualizando conforme avance la
implementación._
