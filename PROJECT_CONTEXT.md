# Contexto y propósito del proyecto — Plataforma IIoT Open Source (híbrida y distribuida)

> Documento de visión y propósito. Complementa `README.md` (spec), `ARCHITECTURE.md`
> (decisiones) y `ROADMAP.md` (fases). Explica el *para qué* y la arquitectura de
> ingesta híbrida hacia un núcleo centralizado.

## Propósito

Construir una plataforma SCADA/IIoT open source moderna, robusta y libre de costos
de licenciamiento (alternativa a Ignition / WinCC). No un visor simple, sino un
**ecosistema profesional de nivel industrial** que combine la flexibilidad del
desarrollo web con la seguridad y confiabilidad de la automatización de planta real.

La evolución se estructura en **dos ramas operativas que convergen en un único
núcleo centralizado**, garantizando trazabilidad, diagnóstico de fallas y control
estricto de usuarios.

---

## 1. Arquitectura de doble rama (ingesta híbrida)

- **Rama 1 — Direct Polling:** el motor asíncrono en Python (`Runtime` + `ScanScheduler`)
  lee autómatas/simuladores con drivers optimizados por bloques (Modbus TCP, y en F2
  S7 / OPC UA).
- **Rama 2 — Edge Push (SIMATIC IOT2050):** hardware Siemens en campo con **Node-RED**
  local como *protocol translator*: lee los PLCs (S7/Profinet), empaqueta en JSON y
  **publica** hacia un **broker MQTT local (on-premise)** dentro de la red de planta.
  No se sobrecarga la red ni se exponen servicios.
- **Convergencia en el núcleo:** un cliente MQTT del backend se suscribe al broker
  local y deposita los datos en el **mismo `TagCache`** que la Rama 1. Para el sistema,
  el origen del dato es indiferente: todo se unifica.

## 2. Persistencia centralizada (base de datos maestra)

- **Modelo lógico segmentado:** una única BD centralizada, segmentada por `project_id`
  en todas las tablas (en lugar de una BD por proyecto, insostenible de mantener).
- **Stack (100% open source):**
  - **PostgreSQL** — configuración de proyectos, usuarios, credenciales, RBAC y auditoría.
  - **TimescaleDB / InfluxDB** — historiador de series temporales para la telemetría.
- **Rendimiento a largo plazo:** indexación por tiempo/tag, compresión de datos
  antiguos y políticas automáticas de retención y *downsampling*.

## 3. Seguridad, auditoría y diagnóstico (health monitoring)

- **RBAC por proyecto:** Administradores modifican lógica, drivers e interfaces;
  Operadores solo visualización y control operacional autorizado.
- **Audit trail:** registro transaccional en PostgreSQL de acciones críticas
  (logins, cambios de setpoint, modificaciones de proyecto) con fecha/hora, usuario,
  IP, proyecto y valores (anterior → nuevo).
- **Diagnóstico de conectividad:**
  - *Edge Gateway:* **MQTT LWT** (Last Will and Testament) para registrar el momento
    y la causa exactos si la IOT2050 pierde conexión abruptamente.
  - *Drivers directos:* captura sistemática de excepciones de red antes del backoff
    de reconexión.

## 4. Frontend, enlace de datos y scripting

- **Interfaz unificada:** el usuario diseña el HMI por bloques (`WidgetNode`) igual,
  sin importar si el dato viene de la Rama 1 o la Rama 2.
- **Data binding automático:** sin SQL manual; desde el panel de propiedades del
  widget se enlaza al `tag_id` y el backend traduce de forma transparente al historiador.
- **Motor de scripting (`LogicNode`):** bloque para lógica/cálculos en Python,
  ejecutado en un entorno **sandbox** que evalúa el `TagCache` en tiempo real.

---

## Mapeo con la implementación actual

Este contexto **encaja con lo ya construido**; el desacople productor/`TagCache`/consumidor
es exactamente lo que hace que la ingesta híbrida sea trivial de integrar.

| Elemento del contexto | Estado hoy | Dónde / fase |
|---|---|---|
| Rama 1 Direct Polling (`Runtime`, `ScanScheduler`, Modbus por bloques) | ✅ **Implementado** (F1) | `engine/`, `drivers/modbus_driver.py` |
| Rama 2 MQTT → mismo `TagCache` (Observer) | ✅ **Encaja directo** | driver MQTT publica al `TagCache` como cualquier otra fuente — F2 |
| Node-RED / IOT2050 como traductor de protocolo | ✅ Externo, sin cambios en el core | infraestructura de campo |
| BD única segmentada por `project_id` | ⚠️ **Nuevo** (ver consideración A) | `models/` + `storage/` — F2 |
| PostgreSQL (config/RBAC/audit) + Timescale/Influx (series) | ✅ Previsto | ARCHITECTURE §3.8 — F2 |
| Downsampling / retención / compresión | ✅ Nativo de Timescale | F2+ |
| RBAC por proyecto (admin/operador) | ✅ Previsto; ABAC multi-planta en F4 | ARCHITECTURE §3.6 / §10.2 |
| Audit trail transaccional | ✅ Previsto (patrón Command + audit) | ARCHITECTURE §3.6 — F2 |
| MQTT LWT para caída del Edge | ✅ Encaja en el driver MQTT | F2 |
| Captura de excepciones antes del backoff | ✅ **Implementado** | `runtime.py` (backoff) + timeout del driver (D-H2) |
| `WidgetNode` unificado + data binding por `tag_id` | ✅ Modelo listo; UI en F3 | `models/node.py`, `ws/protocol.py` |
| `LogicNode` scripting Python en sandbox | ⚠️ **Requiere diseño de seguridad** (ver consideración B) | F3/F4 |

## Consideraciones antes de implementar

**A) `project_id` transversal — fácil pero es una decisión de esquema.**
Hay que introducir `project_id` en el modelo (`Project` ya versionado con
`schema_version`, así que la migración es limpia) y como **columna/clave** en las
tablas de config y en el historiador. En el `TagCache` en memoria conviene
namespacing por proyecto (o una instancia de `Runtime` por proyecto). Es trabajo de
F2 (capa `storage/`), sin refactor del motor. **Factible y de bajo riesgo.**

**B) Sandbox del `LogicNode` — el único punto genuinamente delicado.**
Ejecutar Python arbitrario de usuario de forma segura es **notoriamente difícil**:
`eval`/`exec` directos son un agujero de seguridad (acceso a `import`, filesystem,
red). Recomendación de diseño (a decidir en F3/F4, **no** improvisar):
1. **Preferido para cálculos:** un evaluador de expresiones restringido
   (`asteval` o similar) — cubre el 90% de los casos (escalados, fórmulas) sin
   exponer el intérprete completo.
2. **Si se necesita Python "real":** ejecución **fuera de proceso** en un sandbox
   aislado (subproceso con seccomp / contenedor efímero / WASM), con límites de CPU
   y memoria y sin acceso a red ni FS. Nunca en el mismo proceso del backend.
El `LogicNode` ya existe como nodo (patrón Strategy); lo que falta es **la política
de ejecución segura**, que debe cerrarse como decisión de arquitectura antes de codificar.

## Veredicto

**Factible.** La arquitectura modular actual absorbe esta visión sin rediseño: la
ingesta híbrida es una consecuencia natural del `TagCache` como punto de convergencia,
y persistencia/RBAC/auditoría/LWT ya están en el roadmap (F2/F4). Los dos únicos
puntos a cerrar con cuidado son `project_id` (esquema, bajo riesgo) y el **sandbox del
`LogicNode`** (seguridad, requiere decisión de diseño explícita).
