"""Registro de métricas ligero con exposición en formato Prometheus (F2.4c).

Sin dependencias externas (apto air-gapped). Soporta contadores, gauges (incl. de
"último valor" para latencias) y **fuentes de gauge dinámicas** (callbacks evaluados
al renderizar, p. ej. clientes WS conectados o alarmas activas).
"""

from __future__ import annotations

import threading
from typing import Callable, Iterable

# Una fuente dinámica devuelve tuplas (nombre, labels, valor).
GaugeSource = Callable[[], Iterable[tuple[str, dict, float]]]


class Metrics:
    def __init__(self) -> None:
        self._counters: dict[tuple, float] = {}
        self._gauges: dict[tuple, float] = {}
        self._types: dict[str, str] = {}
        self._sources: list[GaugeSource] = []
        # Rev 13: los drivers síncronos (S7) corren en to_thread; protegemos las
        # mutaciones para evitar carreras al incrementar/actualizar desde varios hilos.
        self._lock = threading.Lock()

    @staticmethod
    def _key(name: str, labels: dict | None) -> tuple:
        return (name, tuple(sorted((labels or {}).items())))

    def inc(self, name: str, labels: dict | None = None, amount: float = 1.0) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + amount
            self._types[name] = "counter"

    def set_gauge(self, name: str, labels: dict | None = None, value: float = 0.0) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._gauges[key] = float(value)
            self._types[name] = "gauge"

    # Latencias / "último valor" se modelan como gauge.
    observe = set_gauge

    def register_source(self, source: GaugeSource) -> None:
        with self._lock:
            self._sources.append(source)

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._sources.clear()
            self._types.clear()

    def render(self) -> str:
        # Instantánea bajo lock para no iterar dicts que otro hilo esté mutando.
        with self._lock:
            counters = list(self._counters.items())
            gauges = list(self._gauges.items())
            sources = list(self._sources)
            types = dict(self._types)
        lines: list[str] = []
        emitted: set[str] = set()

        def emit(name: str, labels: dict, value: float) -> None:
            if name not in emitted:
                lines.append(f"# TYPE {name} {types.get(name, 'gauge')}")
                emitted.add(name)
            if labels:
                inner = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
                name_part = f"{name}{{{inner}}}"
            else:
                name_part = name
            lines.append(f"{name_part} {value}")

        for (name, lbl), val in counters:
            emit(name, dict(lbl), val)
        for (name, lbl), val in gauges:
            emit(name, dict(lbl), val)
        for source in sources:
            try:
                for name, labels, value in source():
                    types.setdefault(name, "gauge")
                    emit(name, labels, float(value))
            except Exception:  # noqa: BLE001 - una fuente no debe romper el scrape
                continue
        return "\n".join(lines) + "\n"


metrics = Metrics()
