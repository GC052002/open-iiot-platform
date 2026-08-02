"""Test de backpressure del ConnectionManager (§3.4, drop-oldest)."""

from app.ws.manager import ConnectionManager, _Client, _QUEUE_MAXSIZE
from app.ws.protocol import TagUpdateMsg
from app.models.tag import TagValue


class _FakeWS:
    async def accept(self): ...
    async def send_text(self, text: str): ...


def test_enqueue_drops_oldest_on_full_queue():
    mgr = ConnectionManager()
    client = _Client(ws=_FakeWS())  # type: ignore[arg-type]

    def msg(v: float) -> TagUpdateMsg:
        return TagUpdateMsg(values=[TagValue(tag_id="t", value=v)])

    # Llenar la cola exactamente hasta maxsize.
    for i in range(_QUEUE_MAXSIZE):
        mgr._enqueue(client, msg(float(i)))
    assert client.queue.qsize() == _QUEUE_MAXSIZE
    assert client.dropped == 0

    # Un mensaje más: se descarta el más viejo, no el nuevo.
    mgr._enqueue(client, msg(999.0))
    assert client.queue.qsize() == _QUEUE_MAXSIZE
    assert client.dropped == 1


def test_client_is_hashable_for_routing():
    """Regresión (F3.0): `_Client` es la clave de set/dict de enrutado. Un
    @dataclass normal (eq=True) sería unhashable y rompería el WS en runtime."""
    c1 = _Client(ws=_FakeWS())  # type: ignore[arg-type]
    c2 = _Client(ws=_FakeWS())  # type: ignore[arg-type]
    s = {c1, c2}
    assert len(s) == 2  # identidad por objeto, no por valor
    assert c1 in s and c1 != c2


async def test_routes_only_to_subscribed_clients():
    """Camino real connect→subscribe→on_tag_update (el que dispara el WS endpoint)."""
    mgr = ConnectionManager()
    a = await mgr.connect(_FakeWS())  # type: ignore[arg-type]
    b = await mgr.connect(_FakeWS())  # type: ignore[arg-type]
    assert mgr.client_count() == 2

    mgr.subscribe(a, "p1", ["t0", "t1"])
    mgr.subscribe(b, "p1", ["t1"])

    await mgr.on_tag_update("p1", [TagValue(tag_id="t0", value=1.0)])
    assert a.queue.qsize() == 1  # a suscrito a t0
    assert b.queue.qsize() == 0  # b no suscrito a t0

    await mgr.on_tag_update("p1", [TagValue(tag_id="t1", value=2.0)])
    assert a.queue.qsize() == 2 and b.queue.qsize() == 1  # ambos a t1

    # Un proyecto distinto no llega a nadie de p1.
    await mgr.on_tag_update("p2", [TagValue(tag_id="t1", value=3.0)])
    assert a.queue.qsize() == 2 and b.queue.qsize() == 1

    mgr.disconnect(a)
    assert mgr.client_count() == 1
