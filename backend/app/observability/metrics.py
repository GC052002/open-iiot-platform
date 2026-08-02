"""Registro de métricas ligero con exposición en formato Prometheus (F2.4c).

Sin dependencias externas (apto air-gapped). Soporta contadores, gauges (incl. de
"último valor" para latencias) y **fuentes de gauge dinámicas** (callbacks evaluados
al renderizar, p. ej. clientes WS conectados o alarmas activas).
"""

from __future__ import annotations

from typing import Callable, Iterable

# Una fuente dinámica devuelve tuplas (nombre, labels, valor).
GaugeSource = Callable[[], Iterable[tuple[str, dict, float]]]


class Metrics:
    def __init__(self) -> None:
        self._counters: dict[tuple, float] = {}
        self._gauges: dict[tuple, float] = {}
        self._types: dict[str, str] = {}
        self._sources: list[GaugeSource] = []

    @staticmethod
    def _key(name: str, labels: dict | None) -> tuple:
        return (name, tuple(sorted((labels or {}).items())))

    def inc(self, name: str, labels: dict | None = None, amount: float = 1.0) -> None:
        self._counters[self._key(name, labels)] = self._counters.get(self._key(name, labels), 0.0) + amount
        self._types[name] = "counter"

    def set_gauge(self, name: str, labels: dict | None = None, value: float = 0.0) -> None:
        self._gauges[self._key(name, labels)] = float(value)
        self._types[name] = "gauge"

    # Latencias / "último valor" se modelan como gauge.
    observe = set_gauge

    def register_source(self, source: GaugeSource) -> None:
        self._sources.append(source)

    def reset(self) -> None:
        self._counters.clear()
        self._gauges.clear()
        self._sources.clear()
        self._types.clear()

    def render(self) -> str:
        lines: list[str] = []
        emitted: set[str] = set()

        def emit(name: str, labels: dict, value: float) -> None:
            if name not in emitted:
                lines.append(f"# TYPE {name} {self._types.get(name, 'gauge')}")
                emitted.add(name)
            if labels:
                inner = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
                name_part = f"{name}{{{inner}}}"
            else:
                name_part = name
            lines.append(f"{name_part} {value}")

        for (name, lbl), val in self._counters.items():
            emit(name, dict(lbl), val)
        for (name, lbl), val in self._gauges.items():
            emit(name, dict(lbl), val)
        for source in self._sources:
            try:
                for name, labels, value in source():
                    self._types.setdefault(name, "gauge")
                    emit(name, labels, float(value))
            except Exception:  # noqa: BLE001 - una fuente no debe romper el scrape
                continue
        return "\n".join(lines) + "\n"


metrics = Metrics()
