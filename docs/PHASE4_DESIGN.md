# Fase 4 — Diseño: Plataforma multiusuario y entrega a cliente

> **Estado:** propuesta de diseño (cerrar antes de codificar, ROADMAP §0.1).
> **Autor:** Opus, a partir de los requisitos del creador (GC052002).
> **Para revisar:** GLM 5.2 y Gemini (revisión de **diseño**, no de código todavía).

## 0. Objetivo

Pasar de un "editor de proyectos" (Fase 3, ya funcional) a una **plataforma
multiusuario** donde:

- Tú y tus programadores **crean/editan/ven** proyectos con **permisos por proyecto**.
- Un proyecto se **entrega a un cliente**, que recibe una **cuenta única (editor)** y
  una **"ventana" (visor HMI responsive)** para operar: cambiar setpoints permitidos,
  ver estadísticas/consumo y exportar datos.
- El sistema **guarda registros históricos** (mensuales, consumo) y puede **reenviar
  datos a un tercero** (JSON/MQTT/CSV) en tiempo casi real.
- El creador hace **backup del proyecto antes de entregar**; tras la entrega, los
  cambios del cliente quedan bajo su responsabilidad.

Esto concreta el "F4 — Escalado/multi-tenant/hardening" del ROADMAP (ABAC §10.2) y lo
reorienta a las necesidades reales de producto.

## 1. Qué ya existe (no rehacer)

| Pieza | Dónde | Reutilizamos para |
|---|---|---|
| RBAC (roles, PBKDF2, `can()`) | `security/rbac.py` | base de permisos |
| Login + token firmado (Fernet) | `security/auth.py`, `POST /login` | autenticación |
| Multi-tenant por `project_id` | `state.py`, TagCache segmentado | aislamiento de datos |
| Historiador (series + `audit`) | `storage/` + `/history`, `/audit` | registros, reportes, auditoría |
| Repository abstracto (SQLite hoy, Postgres luego) | `storage/repository.py` | persistir usuarios/proyectos |
| Export/Import JSON del proyecto | `editor/projectIO.ts` (F3.3) | **backup antes de entregar** |
| Escritura de setpoints + audit | WS `WriteMsg`, `_handle_write` | "cambiar parámetros" del cliente |
| Suscriptores del TagCache (delta/raw) | `engine/tag_cache.py` | **egress a terceros** (nuevo sink) |

## 2. Qué es nuevo (alcance de F4)

### 2.1 Modelo de identidad y permisos (F4.0 + F4.1)

**Usuarios persistidos** (hoy vienen de la env `IIOT_USERS`):
- Tabla `users(username PK, password_hash, role_global, active, created_at)`.
  `role_global`: `admin` (superusuario) · `engineer` (crea proyectos) · `client`.
- Bootstrap: si la tabla está vacía, se siembra un admin desde env (una sola vez).
- Hashing PBKDF2 (ya en `rbac.py`); tokens Fernet (ya).

**Propiedad y compartición por proyecto** (ABAC ligero, sin Casbin todavía):
- Persistir el proyecto: `projects(project_id PK, name, owner, schema_json, updated_at)`.
  (Hoy el proyecto solo vive en memoria; para compartir/entregar debe persistirse y
  cargarse al arrancar.)
- `project_members(project_id, username, role_proj)` con
  `role_proj ∈ {owner, editor, viewer, operator}`:
  - **owner**: control total del proyecto (incluye gestionar miembros).
  - **editor**: edita topología/lógica/HMI.
  - **operator** (= el **cliente**): NO edita el diseño; solo opera la "ventana"
    (cambiar setpoints permitidos, ver, exportar).
  - **viewer**: solo lectura.
- Resolución efectiva: `project_role(user, project_id)` → rol; `admin` global ve todo.
- **Aplicación server-side** en API (`/projects/*`) y WS (subscribe = viewer+; write =
  operator+/editor). Nunca se confía en el cliente.

> **Decisión:** tabla propia de miembros ahora (menos dependencias, air-gapped);
> Casbin (§10.2) solo si las políticas se vuelven complejas (multi-planta jerárquico).

### 2.2 Visor HMI del cliente — la "ventana" (F4.2)

- **Ruta/vista separada** del editor: HMI en modo operación (widgets en vivo), diseñada
  **responsive/móvil** (no el editor de 3 columnas).
- **Setpoints editables por el cliente**: el diseñador marca qué tags son `writable`
  (flag por tag) y qué widget los controla; el visor muestra un control (slider/toggle/
  input) que envía `WriteMsg` (gated por `operator+` + audit). El resto es solo lectura.
- **Export**: descargar el snapshot/histórico visible (CSV/JSON).

### 2.3 Reportes: registros mensuales y consumo (F4.3)

- El historiador ya guarda crudo. Añadir agregación:
  `GET /reports?project_id&tag_id&from&to&bucket=hour|day|month&agg=avg|sum|min|max|last`.
- **Consumo** (para tags contador): `delta = last - first` en la ventana, o suma de
  incrementos positivos (manejo de reinicios de contador).
- Frontend: vista de reportes + export CSV. Eficiente en SQLite para rangos moderados;
  TimescaleDB (continuous aggregates) cuando escale.

### 2.4 Egress a terceros (F4.4)

- Un **forwarder** = suscriptor del TagCache (como el historiador/alarmas) que **reenvía
  muestras hacia afuera** según config **por proyecto**:
  `{ enabled, protocol: http|mqtt|file, endpoint, format: json|csv, interval_s, tags[], auth }`.
- `interval_s` configurable (puede ser < 1s); **batch + cola acotada + backoff**
  (patrón `QueuedNotifier`), asíncrono, **nunca bloquea el motor**.
- Solo salida; credenciales por env/secreto; TLS para HTTP/MQTT.

> **Decisión:** el egress es **config de proyecto**, no un nodo del canvas (el canvas
> modela la ingesta y el HMI; el egress es infraestructura del proyecto).

### 2.5 Backup y entrega

- **Backup = Exportar** el proyecto JSON (ya existe) + opción de **exportar histórico**
  (CSV/JSON) → un "paquete de entrega".
- **Modelo de despliegue** (fork principal):
  - **A) Por cliente (recomendado OT):** exportas → despliegas una **instancia del
    cliente** (Docker) donde él tiene su cuenta `operator` y su "ventana". Aislado,
    air-gapped. Tras la entrega, sus cambios son suyos. La **plantilla maestra** se
    queda contigo.
  - **B) Central multi-tenant:** una instancia con todos los usuarios/clientes;
    `project_members` controla el acceso. Requiere Postgres + hardening (portal SaaS).
  - Ambos parten del **mismo core**; A se apoya en el empaquetado (Fase 5).

## 3. Persistencia

- Extender el patrón Repository: `UserRepository`, `ProjectRepository`,
  `MembershipRepository`. **SQLite ahora** (mismo estilo que el historiador, air-gapped);
  **PostgreSQL** cuando se active el modo central/nube (misma interfaz, otra impl.).
- `PROJECT_CONTEXT §2` ya prevé PostgreSQL (config) + Timescale (series); se faseará.

## 4. Sub-fases propuestas (cada una cierra verde y se mergea)

| Sub-fase | Entregable | Depende de |
|---|---|---|
| **F4.0** | Usuarios persistidos + API de gestión (`/users`) + UI de admin | — |
| **F4.1** | Proyectos persistidos + propiedad/miembros + permisos por proyecto (API+WS) | F4.0 |
| **F4.2** | Visor HMI responsive del cliente + setpoints `writable` + export | F4.1 |
| **F4.3** | Reportes (mensuales/consumo) + export CSV | F2.1 (historiador) |
| **F4.4** | Egress a terceros (HTTP/MQTT/CSV) | F4.1 |
| **F4.5** (opcional) | Empaquetado por cliente (Docker) = solapa con Fase 5 | F4.1 |

Orden recomendado: **F4.0 → F4.1** (identidad es la base) → luego F4.2/F4.3/F4.4 en el
orden que priorices.

## 5. Seguridad (transversal)

- Contraseñas PBKDF2; tokens Fernet con TTL; **fail-closed**.
- **Autorización por proyecto siempre en el servidor** (API y WS); el frontend solo
  oculta, no autoriza.
- **Audit** de todo lo sensible: alta/baja de usuarios, cambios de miembros/roles,
  escrituras de setpoint, exportaciones, cambios de config de egress.
- Egress: solo saliente, credenciales fuera del código, TLS.

## 6. Preguntas para los revisores (diseño)

1. **Roles por proyecto**: ¿`owner/editor/operator/viewer` son suficientes? ¿El
   "cliente" es exactamente `operator` (opera+exporta, no edita diseño)?
2. **ABAC**: ¿tabla propia ahora y Casbin solo si crece, o Casbin ya?
3. **Egress**: ¿config de proyecto (propuesto) o un `SinkNode` en el canvas?
4. **"Editable por cliente"**: ¿flag `writable` por **tag** (propuesto) o por widget?
5. **Persistencia**: ¿SQLite ahora → Postgres luego (propuesto), o Postgres ya?
6. **Despliegue**: ¿por-cliente (A, recomendado) o central multi-tenant (B)? Marca el
   alcance de F4.1 y de la Fase 5.
7. **Consumo**: para contadores, ¿`last-first` con manejo de reinicios, o suma de deltas
   positivos? ¿Algún estándar del sector que debamos seguir?

## 7. Fuera de alcance de F4 (diferido)

- Redis multi-worker (escala horizontal), Vault (rotación de secretos), Sparkplug B,
  tracing OpenTelemetry — quedan como **F4-infra** / Fase 5 según necesidad.
- WASM para `LogicNode` (Python real) — aislamiento definitivo de cómputo no-confiable.
