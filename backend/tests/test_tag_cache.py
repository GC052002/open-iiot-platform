"""Tests del TagCache — deadband (R4), notificación (T-M1) y orden temporal (Rev 7).

Se usan timestamps explícitos crecientes para que el control de orden temporal no
interfiera con los escenarios de deadband (y para ser deterministas).
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.engine.tag_cache import TagCache
from app.models.tag import Tag, TagValue

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
_P = "p1"  # project_id de prueba


def _tag(tag_id: str, deadband: float = 0.0, mode: str = "abs") -> Tag:
    return Tag(id=tag_id, name=tag_id, driver_id="d1", address="0",
               deadband=deadband, deadband_mode=mode)


def _tv(tag_id: str, value, secs: float) -> TagValue:
    return TagValue(tag_id=tag_id, value=value, ts=_BASE + timedelta(seconds=secs))


def _cache(tag: Tag) -> TagCache:
    c = TagCache()
    c.set_tags(_P, {tag.id: tag})
    return c


async def test_deadband_zero_reports_everything():
    cache = _cache(_tag("t", deadband=0.0))
    assert len(await cache.update(_P, [_tv("t", 1.0, 0)])) == 1
    assert len(await cache.update(_P, [_tv("t", 1.0, 1)])) == 1  # deadband 0 => siempre


async def test_deadband_abs_filters_small_changes():
    cache = _cache(_tag("t", deadband=0.5, mode="abs"))
    assert len(await cache.update(_P, [_tv("t", 10.0, 0)])) == 1
    assert len(await cache.update(_P, [_tv("t", 10.2, 1)])) == 0  # < 0.5
    assert len(await cache.update(_P, [_tv("t", 10.7, 2)])) == 1  # >= 0.5


async def test_deadband_pct_relative_to_previous():
    cache = _cache(_tag("t", deadband=10.0, mode="pct"))
    await cache.update(_P, [_tv("t", 100.0, 0)])
    assert len(await cache.update(_P, [_tv("t", 105.0, 1)])) == 0  # 5% < 10%
    assert len(await cache.update(_P, [_tv("t", 120.0, 2)])) == 1  # 20% >= 10%


async def test_snapshot_keeps_last_value_even_if_not_reported():
    cache = _cache(_tag("t", deadband=1.0))
    await cache.update(_P, [_tv("t", 5.0, 0)])
    await cache.update(_P, [_tv("t", 5.1, 1)])  # no reportado (deadband)
    assert cache.snapshot(_P, ["t"])[0].value == 5.1  # pero sí guardado


async def test_observer_notified_only_on_significant_change():
    cache = _cache(_tag("t", deadband=1.0))
    received: list[TagValue] = []

    async def sub(project_id, values):
        received.extend(values)

    cache.subscribe(sub)
    await cache.update(_P, [_tv("t", 1.0, 0)])  # primer valor: significativo
    await cache.update(_P, [_tv("t", 1.2, 1)])  # < deadband: no notifica
    assert len(received) == 1


# --- Rev 7: orden temporal (out-of-order) ----------------------------------

async def test_out_of_order_sample_is_dropped():
    cache = _cache(_tag("t", deadband=0.0))
    await cache.update(_P, [_tv("t", 10.0, 5)])          # ts=5
    changed = await cache.update(_P, [_tv("t", 99.0, 3)])  # ts=3 (más viejo)
    assert changed == []                                  # descartado
    assert cache.snapshot(_P, ["t"])[0].value == 10.0     # no sobrescrito


async def test_equal_timestamp_is_dropped():
    cache = _cache(_tag("t", deadband=0.0))
    await cache.update(_P, [_tv("t", 10.0, 5)])
    assert await cache.update(_P, [_tv("t", 11.0, 5)]) == []  # ts igual => se ignora


# --- Rev 7: aislamiento por project_id -------------------------------------

async def test_projects_are_isolated():
    cache = TagCache()
    cache.set_tags("A", {"t": _tag("t")})
    cache.set_tags("B", {"t": _tag("t")})
    await cache.update("A", [_tv("t", 1.0, 0)])
    await cache.update("B", [_tv("t", 2.0, 0)])
    assert cache.get("A", "t").value == 1.0
    assert cache.get("B", "t").value == 2.0  # mismo tag_id, sin colisión
