"""Utilidades de lectura por bloques compartidas por drivers de polling (D-M4).

Generalizado a partir de Modbus + S7 (ambos leen rangos contiguos con un límite de
tamaño por petición). El algoritmo es idéntico; solo cambian la unidad (registros de
16 bits en Modbus, bytes en S7) y el máximo por PDU, que se pasan como parámetro.
"""

from __future__ import annotations

from typing import Any


def group_contiguous_spans(
    spans: list[tuple[Any, int, int]], max_units: int = 120
) -> list[tuple[int, int]]:
    """Agrupa `spans` `(item, start, width)` en rangos `(start, count)` contiguos, sin
    partir un span entre dos peticiones y respetando `max_units` por bloque.

    `item` (p. ej. el Tag) se ignora aquí; solo se usan `start` y `width`.
    """
    if not spans:
        return []
    ordered = sorted(spans, key=lambda s: s[1])
    ranges: list[tuple[int, int]] = []
    cur_start = ordered[0][1]
    cur_end = cur_start + ordered[0][2]  # exclusivo
    for _item, start, width in ordered[1:]:
        end = start + width
        if start > cur_end or (end - cur_start) > max_units:
            ranges.append((cur_start, cur_end - cur_start))
            cur_start, cur_end = start, end
        else:
            cur_end = max(cur_end, end)
    ranges.append((cur_start, cur_end - cur_start))
    return ranges
