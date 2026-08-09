"""`LogicEngine` — suscriptor **delta** del TagCache que ejecuta los `LogicNode`.

Patrón idéntico al `AlarmEngine`: instancia global, estado **por `project_id`**. Cada
`LogicNode` con `params.input` y `params.output` se convierte en un `LogicRunner`:
al cambiar su tag de entrada, calcula (estrategia built-in o `expr` en sandbox) y
**publica un tag derivado** (`output`) de vuelta al TagCache, que fluye a WS/widgets/
historiador. El binding sigue siendo por `tag_id` (contrato §3.10).

Seguridad/robustez:
- `output == input` se descarta al registrar (evita el auto-bucle trivial).
- El cómputo nunca lanza (fail-safe en `strategies.py`): un LogicNode roto no tumba
  el motor ni el proyecto.
- Cadenas `A→logic→B→logic→C` funcionan porque publicar el derivado dispara de nuevo
  a los suscriptores delta; el deadband del TagCache y la ausencia de cambio cortan la
  propagación (ciclos explícitos A→B→A son responsabilidad del diseñador).
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from app.logic.strategies import Compute, build_compute
from app.models.node import LogicNode
from app.models.tag import TagValue

log = logging.getLogger("iiot.logic")

#: Firma del publicador: `await publish(project_id, [TagValue, ...])`.
Publish = Callable[[str, list[TagValue]], Awaitable[Any]]


class LogicRunner:
    """Un `LogicNode` operativo: mapea un tag de entrada a uno de salida."""

    def __init__(self, node_id: str, input_tag: str, output_tag: str, compute: Compute) -> None:
        self.node_id = node_id
        self.input_tag = input_tag
        self.output_tag = output_tag
        self._compute = compute

    def run(self, value: Any) -> float | None:
        return self._compute(value)


def _build_runner(node: LogicNode) -> LogicRunner | None:
    p = node.params or {}
    input_tag = p.get("input")
    output_tag = p.get("output")
    if not isinstance(input_tag, str) or not isinstance(output_tag, str):
        return None
    if not input_tag or not output_tag or input_tag == output_tag:
        return None  # sin binding completo o auto-bucle
    return LogicRunner(node.id, input_tag, output_tag, build_compute(node.strategy, p))


class LogicEngine:
    def __init__(self, publish: Publish) -> None:
        self._publish = publish
        # project_id -> input_tag -> [runners]
        self._by_input: dict[str, dict[str, list[LogicRunner]]] = {}

    # -- Registro por proyecto ------------------------------------------------
    def register_project(self, project_id: str, nodes: list[LogicNode]) -> None:
        self.unregister_project(project_id)
        by_input: dict[str, list[LogicRunner]] = {}
        for node in nodes:
            runner = _build_runner(node)
            if runner is not None:
                by_input.setdefault(runner.input_tag, []).append(runner)
        if by_input:
            self._by_input[project_id] = by_input

    def unregister_project(self, project_id: str) -> None:
        self._by_input.pop(project_id, None)

    def runner_count(self, project_id: str) -> int:
        return sum(len(v) for v in self._by_input.get(project_id, {}).values())

    # -- Suscriptor delta del TagCache ---------------------------------------
    async def on_tag_update(self, project_id: str, changed: list[TagValue]) -> None:
        runners_by_input = self._by_input.get(project_id)
        if not runners_by_input:
            return
        derived: list[TagValue] = []
        for value in changed:
            for runner in runners_by_input.get(value.tag_id, ()):  # type: ignore[arg-type]
                out = runner.run(value.value)
                if out is not None:
                    derived.append(
                        TagValue(tag_id=runner.output_tag, value=out, quality=value.quality)
                    )
        if derived:
            # Publicar de vuelta al TagCache; dispara a los suscriptores (WS, etc.).
            await self._publish(project_id, derived)
