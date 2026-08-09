"""Simulador de Edge (IOT2050 + Node-RED) para la DEMO de la Rama 2.

Publica JSON de telemetría a un broker MQTT, imitando lo que haría la IOT2050:
lee el PLC, empaqueta en JSON y publica. El backend (driver `mqtt`) se suscribe y
deposita los datos en el mismo TagCache que la Rama 1 (Modbus/S7 directo).

Formato del payload (respetado por `app/drivers/mqtt_driver.py`):
    {"ts": "<ISO8601 opcional>", "values": {"<address>": <valor>, ...}}
Los `address` deben coincidir con los `address` de los tags del proyecto.

Uso:
    pip install aiomqtt amqtt
    python tools/mqtt_demo/edge_sim.py                 # broker local, topic planta/edge1
    python tools/mqtt_demo/edge_sim.py --host 10.0.0.5 --topic planta/linea2 --interval 0.5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from datetime import datetime, timezone


async def main() -> None:
    import aiomqtt

    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--topic", default="planta/edge1")
    ap.add_argument("--interval", type=float, default=1.0, help="segundos entre publicaciones")
    args = ap.parse_args()

    print(f"Publicando en {args.host}:{args.port} topic={args.topic} cada {args.interval}s")
    i = 0
    async with aiomqtt.Client(hostname=args.host, port=args.port) as client:
        while True:
            payload = json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "values": {
                    "temp": round(70 + 10 * math.sin(i / 6), 2),   # onda suave
                    "nivel": 30 + (i % 20),                        # rampa 30..49
                    "bomba": bool(i % 2),                          # booleano on/off
                },
            })
            await client.publish(args.topic, payload, qos=1)
            print("->", payload)
            i += 1
            await asyncio.sleep(args.interval)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
