"""Tests del TagCache — escenarios definidos por Opus (deadband, notificación).

Estos son los "escenarios del engine" que, según ROADMAP §0, define Opus. Cubren
R3 (concurrencia/consistencia) y R4 (deadband) para que no queden en superficie.
"""

import pytest

from app.engine.tag_cache import TagCache
from app.models.tag import Tag, TagValue


def _tag(tag_id: str, deadband: float = 0.0, mode: str = "abs") -> Tag:
    return Tag(
        id=tag_id, name=tag_id, driver_id="d1", address="0",
        deadband=deadband, deadband_mode=mode,
    )


async def test_deadband_zero_reports_everything():
    cache = TagCache({"t": _tag("t", deadband=0.0)})
    changed = await cache.update([TagValue(tag_id="t", value=1.0)])
    assert len(changed) == 1
    changed = await cache.update([TagValue(tag_id="t", value=1.0)])  # sin cambio
    assert len(changed) == 1  # deadband 0 => siempre reporta


async def test_deadband_abs_filters_small_changes():
    cache = TagCache({"t": _tag("t", deadband=0.5, mode="abs")})
    assert len(await cache.update([TagValue(tag_id="t", value=10.0)])) == 1
    assert len(await cache.update([TagValue(tag_id="t", value=10.2)])) == 0  # < 0.5
    assert len(await cache.update([TagValue(tag_id="t", value=10.7)])) == 1  # >= 0.5


async def test_deadband_pct_relative_to_previous():
    cache = TagCache({"t": _tag("t", deadband=10.0, mode="pct")})
    await cache.update([TagValue(tag_id="t", value=100.0)])
    assert len(await cache.update([TagValue(tag_id="t", value=105.0)])) == 0  # 5% < 10%
    assert len(await cache.update([TagValue(tag_id="t", value=120.0)])) == 1  # 20% >= 10%


async def test_snapshot_keeps_last_value_even_if_not_reported():
    cache = TagCache({"t": _tag("t", deadband=1.0)})
    await cache.update([TagValue(tag_id="t", value=5.0)])
    await cache.update([TagValue(tag_id="t", value=5.1)])  # no reportado
    snap = cache.snapshot(["t"])
    assert snap[0].value == 5.1  # el último valor SÍ se guarda para snapshot


async def test_observer_notified_only_on_significant_change():
    cache = TagCache({"t": _tag("t", deadband=1.0)})
    received: list[TagValue] = []

    async def sub(values):
        received.extend(values)

    cache.subscribe(sub)
    await cache.update([TagValue(tag_id="t", value=1.0)])   # significativo (primer valor)
    await cache.update([TagValue(tag_id="t", value=1.2)])   # < deadband, no notifica
    assert len(received) == 1
