# DEMO — cómo presentar la plataforma IIoT

> Guion reproducible para una demo en vivo. La ruta **Modbus + persistencia + API +
> WebSocket** funciona de extremo a extremo con el simulador incluido (sin PLC físico).
> S7 y OPC UA están implementados pero requieren un PLC/servidor real para verlos en vivo.

## 0. Requisitos

```bash
cd open-iiot-platform
pip install -e ".[dev]"          # core + pytest/httpx
# (opcional, para drivers reales) pip install -e ".[dev,drivers]"
```

## 1. Prueba que todo está verde (30s)

```bash
pytest -q          # 52 passed
```
Muestra que el motor, la ingesta híbrida, la persistencia y los 4 drivers registrados
están cubiertos por tests.

## 2. Arranca el simulador Modbus + el backend

Terminal A:
```bash
python -m app.drivers.modbus_sim      # simulador Modbus TCP en :5020
```
Terminal B:
```bash
uvicorn app.main:app --port 8000      # backend + historiador SQLite (WAL)
```

## 3. Carga un proyecto y observa datos en vivo

Terminal C — cargar la topología (un driver Modbus contra el simulador):
```bash
curl -X POST localhost:8000/projects -H 'content-type: application/json' -d '{
  "schema_version": "1",
  "project_id": "planta_demo",
  "name": "Demo",
  "nodes": [{"id":"d1","type":"driver","driver_type":"modbus_tcp",
             "config":{"host":"127.0.0.1","port":5020,"polling_rate":0.5}}],
  "tags": [
    {"id":"t0","name":"Nivel","driver_id":"d1","address":"0","data_type":"int"},
    {"id":"t1","name":"Presion","driver_id":"d1","address":"1","data_type":"int"}
  ]
}'
```

Ver el último valor (se actualiza con el simulador):
```bash
curl "localhost:8000/tags?project_id=planta_demo"
```

Ver el histórico persistido (lo va guardando el TagBuffer):
```bash
curl "localhost:8000/history?project_id=planta_demo&tag_id=t0&limit=5"
```

Salud por proyecto:
```bash
curl localhost:8000/health
```

## 4. Streaming en tiempo real por WebSocket

Con cualquier cliente WS (o un pequeño script) conecta a `ws://localhost:8000/ws` y envía:
```json
{"type":"subscribe","project_id":"planta_demo","tag_ids":["t0","t1"]}
```
Recibirás mensajes `tag_update` a medida que cambian los valores (con backpressure y
`overflow` si el cliente va lento).

## 5. Qué contar en la presentación

- **Arquitectura desacoplada:** productor → `TagCache` → consumidores. El origen del
  dato (Modbus polling o MQTT push) es indiferente: todo converge en el `TagCache`.
- **Ingesta híbrida:** Modbus (polling) y MQTT (push del Edge IOT2050) unificados bajo
  `BaseDriver.run`. S7 y OPC UA ya encajan en el mismo patrón.
- **Multi-tenant:** `project_id` segmenta datos y aísla fallos (un `TaskGroup` por planta).
- **Persistencia industrial:** historiador con WAL + escritura en batch + reintento sin
  pérdida de telemetría.
- **Calidad:** 52 tests verdes; cada fase revisada por revisores externos (Rev 1–10).

## Notas

- S7 (`python-snap7`) y OPC UA (`asyncua`) requieren PLC/servidor. La lógica (decode,
  direccionamiento, subscriptions) está unit-testeada; la prueba en vivo se hace contra
  un equipo real o un simulador de esos protocolos.
- MQTT (`aiomqtt`) requiere un broker local (p. ej. mosquitto) para verlo en vivo.
