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
