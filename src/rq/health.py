"""Minimal /health endpoint for Fly to ping (Phase 7, req 3).

Implemented with the stdlib asyncio server rather than FastAPI to avoid adding a
web framework to §5's dependency set. Runs in the bot's event loop, so a healthy
response means the bot process (long-polling + scheduler) is alive.
"""

from __future__ import annotations

import asyncio
import json

from . import __version__
from .logging import get_logger

log = get_logger("health")


async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=5)
        # Drain the rest of the request headers.
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=5)
            if line in (b"\r\n", b"\n", b""):
                break
    except (asyncio.TimeoutError, ConnectionError):
        writer.close()
        return

    path = b"/"
    parts = request_line.split()
    if len(parts) >= 2:
        path = parts[1]

    if path.startswith(b"/health"):
        body = json.dumps({"status": "ok", "version": __version__}).encode()
        status = b"200 OK"
    else:
        body = b'{"status":"not found"}'
        status = b"404 Not Found"

    writer.write(
        b"HTTP/1.1 " + status + b"\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: " + str(len(body)).encode() + b"\r\n"
        b"Connection: close\r\n\r\n" + body
    )
    try:
        await writer.drain()
    finally:
        writer.close()


async def start_health_server(host: str = "0.0.0.0", port: int = 8080) -> asyncio.AbstractServer:
    server = await asyncio.start_server(_handle, host, port)
    bound = server.sockets[0].getsockname() if server.sockets else (host, port)
    log.info("health.listening", host=bound[0], port=bound[1])
    return server
