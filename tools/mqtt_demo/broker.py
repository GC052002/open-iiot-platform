"""Broker MQTT local para DEMO de la Rama 2 (Edge Push / IOT2050).

Sustituto pure-python del broker on-premise de planta (Mosquitto/EMQX). No usar en
producción — es solo para probar la ingesta MQTT sin instalar un broker nativo.

Uso:
    pip install aiomqtt amqtt
    python tools/mqtt_demo/broker.py      # escucha en :1883
"""

from __future__ import annotations

import asyncio
import logging

logging.getLogger("amqtt").setLevel(logging.WARNING)
logging.getLogger("transitions").setLevel(logging.WARNING)


async def main() -> None:
    from amqtt.broker import Broker

    broker = Broker({"listeners": {"default": {"type": "tcp", "bind": "0.0.0.0:1883"}}})
    await broker.start()
    print("Broker MQTT escuchando en :1883 (Ctrl+C para parar)")
    try:
        await asyncio.Event().wait()  # correr indefinidamente
    finally:
        await broker.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
