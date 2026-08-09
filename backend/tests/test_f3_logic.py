"""Tests del `LogicNode` (F3): estrategias, sandbox asteval y `LogicEngine`."""

from __future__ import annotations

import pytest

from app.engine.tag_cache import TagCache
from app.logic.engine import LogicEngine, _build_runner
from app.logic.strategies import MAX_EXPR_LEN, build_compute
from app.models.node import LogicNode
from app.models.tag import Tag, TagValue


# -- Estrategias built-in (puras) --------------------------------------------
def test_scale():
    c = build_compute("scale", {"a": 2.0, "b": 1.0})
    assert c(10) == 21.0
    assert c(0) == 1.0


def test_moving_average():
    c = build_compute("avg", {"window": 3})
    assert [c(v) for v in (0, 3, 6, 9)] == [0.0, 1.5, 3.0, 6.0]  # media de los últimos 3


def test_deadband_filter():
    c = build_compute("deadband", {"deadband": 2.0})
    assert c(0) == 0.0        # primero pasa
    assert c(1) is None       # cambio < 2 → suprimido
    assert c(3) == 3.0        # cambio >= 2 → pasa
    assert c(3.5) is None


def test_non_numeric_input_returns_none():
    assert build_compute("scale", {"a": 1, "b": 0})("hola") is None
    assert build_compute("avg", {})(None) is None


# -- Sandbox de expresiones (seguridad) --------------------------------------
def test_expr_valid():
    c = build_compute("expr", {"expr": "x*a + 2", "a": 3})
    assert c(5) == 17.0


@pytest.mark.parametrize(
    "malicious",
    [
        '__import__("os").system("echo pwned")',
        'open("/etc/passwd").read()',
        "x.__class__",
        "(1).__class__.__bases__",
        "().__class__.__mro__",
    ],
)
def test_expr_sandbox_blocks_malicious(malicious):
    # Fail-safe: la expresión peligrosa se bloquea y devuelve None, sin lanzar.
    assert build_compute("expr", {"expr": malicious})(1) is None


def test_expr_length_limit():
    huge = "1+" * (MAX_EXPR_LEN) + "1"
    assert build_compute("expr", {"expr": huge})(0) is None


def test_expr_only_numeric_params_enter_symtable():
    # Un parámetro no numérico no debe filtrarse al symtable (queda indefinido → None).
    c = build_compute("expr", {"expr": "x + evil", "evil": "os"})
    assert c(1) is None


# -- Construcción de runners --------------------------------------------------
def _logic(node_id: str, strategy: str, **params) -> LogicNode:
    return LogicNode(id=node_id, strategy=strategy, params=params)


def test_runner_requires_input_and_output():
    assert _build_runner(_logic("l1", "scale", a=1)) is None          # faltan input/output
    assert _build_runner(_logic("l2", "scale", input="x", output="x")) is None  # auto-bucle
    r = _build_runner(_logic("l3", "scale", input="raw", output="scaled", a=2))
    assert r is not None and r.input_tag == "raw" and r.output_tag == "scaled"


# -- LogicEngine (cómputo + publicación) -------------------------------------
async def test_logic_engine_publishes_derived():
    published: list[tuple[str, list[TagValue]]] = []

    async def fake_publish(project_id, samples):
        published.append((project_id, samples))

    eng = LogicEngine(publish=fake_publish)
    eng.register_project("p1", [_logic("l1", "scale", input="raw", output="scaled", a=10, b=5)])
    assert eng.runner_count("p1") == 1

    await eng.on_tag_update("p1", [TagValue(tag_id="raw", value=2.0)])
    assert len(published) == 1
    pid, samples = published[0]
    assert pid == "p1"
    assert samples[0].tag_id == "scaled" and samples[0].value == 25.0  # 10*2+5

    # Un tag no enlazado no produce derivados.
    published.clear()
    await eng.on_tag_update("p1", [TagValue(tag_id="otro", value=1.0)])
    assert published == []


async def test_logic_engine_end_to_end_via_tagcache():
    """Integración: el LogicEngine suscrito al TagCache publica el derivado, que
    queda disponible en el snapshot (como lo vería el WS/widget)."""
    cache = TagCache()
    cache.set_tags("p1", {"raw": Tag(id="raw", name="raw", driver_id="d", address="0")})
    eng = LogicEngine(publish=cache.update)
    cache.subscribe(eng.on_tag_update)
    eng.register_project("p1", [_logic("l1", "scale", input="raw", output="scaled", a=2, b=0)])

    await cache.update("p1", [TagValue(tag_id="raw", value=21.0)])
    derived = cache.get("p1", "scaled")
    assert derived is not None and derived.value == 42.0


async def test_logic_engine_unregister():
    eng = LogicEngine(publish=lambda *_: None)  # type: ignore[arg-type]
    eng.register_project("p1", [_logic("l1", "scale", input="raw", output="scaled")])
    assert eng.runner_count("p1") == 1
    eng.unregister_project("p1")
    assert eng.runner_count("p1") == 0
