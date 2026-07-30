"""Preflight de conectividad a un PLC/servidor real (F2.3).

Valida en segundos que un driver conecta y lee un tag contra hardware real, usando
exactamente el mismo código de driver que el motor (no hay nada "de demo"). Útil para
comprobar la conexión en planta antes de arrancar la plataforma completa.

Ejemplos:
  # Modbus TCP (holding register 0)
  python -m app.tools.plc_check --type modbus_tcp --host 192.168.0.10 --address 0 --data-type int

  # Siemens S7 (DB1, byte 0, REAL)
  python -m app.tools.plc_check --type s7 --host 192.168.0.1 --rack 0 --slot 1 --address DB1.0 --data-type float

  # OPC UA (push; escucha 5 s)
  python -m app.tools.plc_check --type opcua --url opc.tcp://192.168.0.5:4840 --address "ns=2;i=3" --seconds 5

  # MQTT (push; escucha mensajes del Edge 5 s)
  python -m app.tools.plc_check --type mqtt --host 192.168.0.20 --topic "iiot/edge/+/data" --address temperature --seconds 5
"""

from __future__ import annotations

import argparse
import asyncio

import app.drivers  # noqa: F401 - registra los drivers built-in
from app.drivers.base import BaseDriver
from app.drivers.registry import create_driver
from app.models.node import DriverNode
from app.models.tag import Tag, TagValue


def build_driver(args: argparse.Namespace) -> tuple[BaseDriver, Tag]:
    """Construye un driver + tag desde los argumentos (puro, sin conectar)."""
    config: dict = {}
    for key in ("host", "port", "unit", "rack", "slot", "url", "topic",
                "lwt_topic", "device_topic_index"):
        val = getattr(args, key, None)
        if val is not None:
            config[key] = val

    node = DriverNode(id="check", driver_type=args.type, config=config)
    tag = Tag(id="probe", name="probe", driver_id="check",
              address=args.address, data_type=args.data_type)
    driver = create_driver(node)
    driver.bind_tags([tag])
    return driver, tag


async def _collect_push(driver: BaseDriver, seconds: float) -> list[TagValue]:
    got: list[TagValue] = []
    stopping = asyncio.Event()

    async def publish(samples: list[TagValue]) -> None:
        got.extend(samples)

    task = asyncio.create_task(driver.run(publish, stopping))
    await asyncio.sleep(seconds)
    stopping.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    return got


async def run_check(args: argparse.Namespace) -> int:
    driver, tag = build_driver(args)
    print(f"→ Conectando driver '{args.type}' ...")
    await driver.connect()
    print("  conectado.")
    try:
        try:
            samples = await driver.read_block([tag])          # polling
        except NotImplementedError:
            print(f"  driver push: escuchando {args.seconds}s ...")
            samples = await _collect_push(driver, args.seconds)  # push
        if not samples:
            print("⚠ Sin muestras (¿dirección/topic correctos? ¿el Edge publica?).")
            return 1
        for s in samples:
            print(f"✓ {s.tag_id} = {s.value!r}  quality={s.quality}  ts={s.ts.isoformat()}")
        return 0
    finally:
        await driver.disconnect()


def main() -> None:
    ap = argparse.ArgumentParser(description="Preflight de conectividad a PLC/servidor real.")
    ap.add_argument("--type", required=True, choices=["modbus_tcp", "s7", "opcua", "mqtt"])
    ap.add_argument("--address", required=True, help="Dirección del tag (según protocolo).")
    ap.add_argument("--data-type", default="int", dest="data_type",
                    choices=["bool", "int", "float", "string"])
    ap.add_argument("--host")
    ap.add_argument("--port", type=int)
    ap.add_argument("--unit", type=int, help="Modbus unit/slave id.")
    ap.add_argument("--rack", type=int, help="S7 rack.")
    ap.add_argument("--slot", type=int, help="S7 slot.")
    ap.add_argument("--url", help="OPC UA endpoint (opc.tcp://...).")
    ap.add_argument("--topic", help="MQTT topic de suscripción.")
    ap.add_argument("--lwt-topic", dest="lwt_topic", help="MQTT LWT topic.")
    ap.add_argument("--device-topic-index", dest="device_topic_index", type=int)
    ap.add_argument("--seconds", type=float, default=5.0, help="Escucha (drivers push).")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(run_check(args)))


if __name__ == "__main__":
    main()
