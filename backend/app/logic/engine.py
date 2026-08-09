"""`LogicEngine` — suscriptor **delta** del TagCache que ejecuta los `LogicNode`.

Patrón idéntico al `AlarmEngine`: instancia global, estado **por `project_id`**. Cada
`LogicNode` con `params.input` y `params.output` se convierte en un `LogicRunner`:
al cambiar su tag de entrada, calcula (estrategia built-in o `expr` en sandbox) y
**publica un tag derivado** (`output`) de vuelta al TagCache, que fluye a WS/widgets/
historiador. El binding sigue siendo por `tag_id` (contrato §3.10).

Seguridad/robustez (Rev 16, revisión externa):
- **Event loop:** la `expr` (sandbox asteval) se ejecuta en `asyncio.to_thread` con
  `wait_for(timeout)`, para que un cálculo lento NO congele el polling de PLCs / WS.
  Las built-in (scale/avg/deadband) son triviales y corren inline.
- **Ciclos de realimentación:** al registrar se detectan ciclos en el grafo
  `output→input` entre LogicNodes y se descartan los runners implicados (los `A→B→A`
  quedarían en bucle infinito). `output == input` también se descarta.
- **Aislamiento:** cada cómputo va en su propio try/except → un LogicNode roto (o que
  agota el timeout) no afecta a los demás ni tumba el motor.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from app.logic.strategies import Compute, build_compute
from app.models.node import LogicNode
from app.models.tag import TagValue

log = logging.getLogger("iiot.logic")

#: Firma del publicador: `await publish(project_id, [TagValue, ...])`.
Publish = Callable[[str, list[TagValue]], Awaitable[Any]]

#: Presupuesto de tiempo para una `expr` de usuario (Rev 16). asteval acota además
#: internamente; esto libera el event loop aunque el thread siga ocupado un instante.
EXPR_TIMEOUT_S = 0.5


class LogicRunner:
    """Un `LogicNode` operativo: mapea un tag de entrada a uno de salida."""

    def __init__(
        self, node_id: str, input_tag: str, output_tag: str, compute: Compute, sandboxed: bool
    ) -> None:
        self.node_id = node_id
        self.input_tag = input_tag
        self.output_tag = output_tag
        self.sandboxed = sandboxed  # True para `expr` → se ejecuta en thread + timeout
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
    return LogicRunner(
        node.id, input_tag, output_tag, build_compute(node.strategy, p), node.strategy == "expr"
    )


def _break_cycles(runners: list[LogicRunner]) -> list[LogicRunner]:
    """Descarta los runners que participan en un ciclo `output→input` (anti-bucle
    infinito, Rev 16). Las cadenas acíclicas `A→B→C` se conservan."""
    by_input: dict[str, list[LogicRunner]] = {}
    for r in runners:
        by_input.setdefault(r.input_tag, []).append(r)

    # Aristas r → n cuando n.input == r.output. "Peeling": se retiran iterativamente
    # los runners cuyos sucesores ya se retiraron (los que no pueden estar en ciclo);
    # los que sobreviven forman parte de algún ciclo y se descartan.
    succ: dict[int, list[int]] = {
        id(r): [id(n) for n in by_input.get(r.output_tag, ())] for r in runners
    }
    on_cycle = {id(r) for r in runners}
    changed = True
    while changed:
        changed = False
        for r in runners:
            rid = id(r)
            if rid in on_cycle and all(s not in on_cycle for s in succ[rid]):
                on_cycle.discard(rid)
                changed = True

    kept = [r for r in runners if id(r) not in on_cycle]
    if on_cycle:
        log.warning("LogicEngine: %d runner(s) en ciclo descartados", len(on_cycle))
    return kept


class LogicEngine:
    def __init__(self, publish: Publish) -> None:
        self._publish = publish
        # project_id -> input_tag -> [runners]
        self._by_input: dict[str, dict[str, list[LogicRunner]]] = {}

    # -- Registro por proyecto ------------------------------------------------
    def register_project(self, project_id: str, nodes: list[LogicNode]) -> None:
        self.unregister_project(project_id)
        runners = [r for r in (_build_runner(n) for n in nodes) if r is not None]
        runners = _break_cycles(runners)
        by_input: dict[str, list[LogicRunner]] = {}
        for runner in runners:
            by_input.setdefault(runner.input_tag, []).append(runner)
        if by_input:
            self._by_input[project_id] = by_input

    def unregister_project(self, project_id: str) -> None:
        self._by_input.pop(project_id, None)

    def runner_count(self, project_id: str) -> int:
        return sum(len(v) for v in self._by_input.get(project_id, {}).values())

    # -- Cómputo con aislamiento y timeout -----------------------------------
    async def _compute(self, runner: LogicRunner, value: Any) -> float | None:
        try:
            if runner.sandboxed:
                # No bloquear el event loop con código de usuario (Rev 16).
                return await asyncio.wait_for(
                    asyncio.to_thread(runner.run, value), EXPR_TIMEOUT_S
                )
            return runner.run(value)
        except asyncio.TimeoutError:
            log.warning("LogicNode %s excedió el timeout de %ss", runner.node_id, EXPR_TIMEOUT_S)
            return None
        except Exception as exc:  # noqa: BLE001 - aislamiento: un runner no rompe a otros
            log.warning("LogicNode %s falló: %s", runner.node_id, exc)
            return None

    # -- Suscriptor delta del TagCache ---------------------------------------
    async def on_tag_update(self, project_id: str, changed: list[TagValue]) -> None:
        runners_by_input = self._by_input.get(project_id)
        if not runners_by_input:
            return
        derived: list[TagValue] = []
        for value in changed:
            for runner in runners_by_input.get(value.tag_id, ()):  # type: ignore[arg-type]
                out = await self._compute(runner, value.value)
                if out is not None:
                    derived.append(
                        TagValue(tag_id=runner.output_tag, value=out, quality=value.quality)
                    )
        if derived:
            # Publicar de vuelta al TagCache; dispara a los suscriptores (WS, etc.).
            await self._publish(project_id, derived)
