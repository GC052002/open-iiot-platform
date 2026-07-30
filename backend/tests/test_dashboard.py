"""Smoke test del monitor web en vivo servido por el backend."""

import httpx
import pytest

from app.main import app


async def test_dashboard_is_served():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "IIoT Platform" in r.text
        assert "/ws" in r.text  # el cliente WS está embebido
