from __future__ import annotations

import asyncio

from rq import __version__
from rq.health import start_health_server


async def _get(port: int, path: str) -> tuple[str, str]:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
    await writer.drain()
    raw = await reader.read()
    writer.close()
    head, _, body = raw.partition(b"\r\n\r\n")
    return head.decode().splitlines()[0], body.decode()


async def test_health_ok():
    server = await start_health_server(host="127.0.0.1", port=0)
    port = server.sockets[0].getsockname()[1]
    try:
        status, body = await _get(port, "/health")
        assert "200 OK" in status
        assert '"status": "ok"' in body and __version__ in body
    finally:
        server.close()
        await server.wait_closed()


async def test_unknown_path_404():
    server = await start_health_server(host="127.0.0.1", port=0)
    port = server.sockets[0].getsockname()[1]
    try:
        status, _ = await _get(port, "/nope")
        assert "404" in status
    finally:
        server.close()
        await server.wait_closed()
