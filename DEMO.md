# DEMO / Runbook — plataforma IIoT contra PLC real

> Guion para conectar la plataforma a un **PLC físico** en planta y presentarla en vivo.
> Los drivers son los mismos del motor (no hay nada "de demo"): el mismo código que
> valida el preflight es el que corre en producción.

## 0. Instalación (en el equipo de planta)

```bash
cd open-iiot-platform
pip install -e ".[dev,drivers]"     # core + drivers reales (snap7, asyncua, aiomqtt)
```
- `python-snap7>=2.0` incluye los binarios nativos → **no** hace falta instalar libsnap7 en el SO.
- Asegura conectividad de red al PLC (misma subred / VLAN OT, firewall abierto al puerto).

## 1. Preflight de conectividad (¡hazlo primero en planta!)

Valida en segundos que el PLC responde, **antes** de arrancar todo:

```bash
# Modbus TCP — holding register 0 (ajusta host/unit/address a tu PLC)
python -m app.tools.plc_check --type modbus_tcp --host 192.168.0.10 --unit 1 --address 0 --data-type int

# Siemens S7-1200/1500 — DB1, byte 0, REAL (ajusta rack/slot: S7-1200/1500 suele ser rack 0 / slot 1)
python -m app.tools.plc_check --type s7 --host 192.168.0.1 --rack 0 --slot 1 --address DB1.0 --data-type float

# OPC UA — escucha 5 s (NodeId real del servidor)
python -m app.tools.plc_check --type opcua --url opc.tcp://192.168.0.5:4840 --address "ns=2;i=3" --seconds 5
```
Salida esperada: `✓ probe = <valor>  quality=good  ts=...`. Si falla, el mensaje indica
si es conexión (host/puerto/rack-slot) o lectura (dirección).

## 2. Arranca el backend

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000    # + historiador SQLite (WAL)
```

## 3. Carga tu proyecto (con la topología del PLC real)

Ejemplo con un driver **S7** (adáptalo a tu PLC; para Modbus usa `driver_type:"modbus_tcp"`
con `host/port/unit` y `address` = offset de registro):

```bash
curl -X POST localhost:8000/projects -H 'content-type: application/json' -d '{
  "schema_version": "1",
  "project_id": "planta_real",
  "name": "Planta",
  "nodes": [{"id":"plc1","type":"driver","driver_type":"s7",
             "config":{"host":"192.168.0.1","rack":0,"slot":1,"polling_rate":0.5}}],
  "tags": [
    {"id":"nivel","name":"Nivel","driver_id":"plc1","address":"DB1.0","data_type":"float"},
    {"id":"marcha","name":"Marcha","driver_id":"plc1","address":"DB1.4","data_type":"bool"}
  ]
}'
```

## 4. Observa datos en vivo

```bash
curl "localhost:8000/tags?project_id=planta_real"                       # último valor
curl "localhost:8000/history?project_id=planta_real&tag_id=nivel&limit=5"  # histórico persistido
curl localhost:8000/health                                              # salud por proyecto
```

WebSocket en tiempo real → `ws://localhost:8000/ws`, enviar:
```json
{"type":"subscribe","project_id":"planta_real","tag_ids":["nivel","marcha"]}
```
Recibes `tag_update` a medida que el PLC cambia (con backpressure/`overflow`).

## Direccionamiento por protocolo (referencia rápida)

| Driver | `driver_type` | `address` | Config clave |
|---|---|---|---|
| Modbus TCP | `modbus_tcp` | offset de Holding Register (`"0"`, `"1"`, ...) | `host`, `port` (502), `unit` |
| Siemens S7 | `s7` | `DB{n}.{byte}` (`"DB1.0"`, `"DB1.4"`) | `host`, `rack`, `slot` |
| OPC UA | `opcua` | NodeId (`"ns=2;i=3"`, `"ns=2;s=Temp"`) | `url` |
| MQTT (Edge) | `mqtt` | clave del payload / `device/clave` | `host`, `topic`, `lwt_topic`, `device_topic_index` |

Tipos de dato: `bool`, `int` (S7 INT 16-bit / Modbus 1 registro), `float` (S7 REAL / Modbus 2 registros, big-endian).

## 5. Qué contar en la presentación

- **Arquitectura desacoplada:** productor → `TagCache` → consumidores. El origen (S7/Modbus
  polling, MQTT/OPC UA push) es indiferente: todo converge en el `TagCache`.
- **Multi-tenant:** `project_id` segmenta datos y aísla fallos (un `TaskGroup` por planta).
- **Persistencia industrial:** historiador WAL + escritura en batch + reintento sin pérdida.
- **Robustez:** reconexión con backoff, backpressure en WS, timeouts por driver.
- **Calidad:** 54 tests verdes; cada fase revisada por revisores externos (Rev 1–10).

## Notas de campo

- Si el preflight S7 falla, prueba **rack 0 / slot 1** (S7-1200/1500) o **rack 0 / slot 2**
  (S7-300/400). Habilita "PUT/GET" y accesos por DB no optimizados en el PLC si el DB no se lee.
- Modbus: si tu PLC expone *input registers* o *coils* en vez de *holding registers*, avísame
  — hoy el driver lee holding registers (lo más común); añadir tablas es trivial (F2.4).
