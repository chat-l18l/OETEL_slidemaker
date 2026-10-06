"""`slides serve`: HTTP server for the build dir, file watcher, live reload over websocket."""

from __future__ import annotations

import asyncio
import functools
import http.server
import json
import os
import threading
from pathlib import Path
from typing import Callable

from websockets.asyncio.server import broadcast, serve

POLL_INTERVAL = 0.3  # seconds


def fingerprint(root: Path, exclude: Path) -> frozenset[tuple[str, int, int]]:
    """(path, mtime, size) of all source files; polling is robust against editors that
    save via rename and against changes that land while a rebuild is running."""
    out = set()
    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)
        dirnames[:] = [n for n in dirnames if not n.startswith(".") and d / n != exclude]
        for n in filenames:
            if n.startswith(".") or n.endswith("~"):
                continue
            try:
                st = (d / n).stat()
            except FileNotFoundError:
                continue
            out.add((str(d / n), st.st_mtime_ns, st.st_size))
    return frozenset(out)


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def _start_http(root: Path, host: str, port: int) -> http.server.ThreadingHTTPServer:
    handler = functools.partial(_QuietHandler, directory=str(root))
    httpd = http.server.ThreadingHTTPServer((host, port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


async def _serve(watch_dir: Path, out: Path, host: str, port: int,
                 rebuild: Callable[[], str | None]) -> None:
    clients = set()
    last_error: str | None = None

    async def handler(ws):
        clients.add(ws)
        try:
            if last_error:
                await ws.send(json.dumps({"type": "error", "text": last_error}))
            await ws.wait_closed()
        finally:
            clients.discard(ws)

    async with serve(handler, host, port + 1):
        seen = fingerprint(watch_dir, out)
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            now = await asyncio.to_thread(fingerprint, watch_dir, out)
            if now == seen:
                continue
            seen = now
            last_error = await asyncio.to_thread(rebuild)
            if last_error:
                broadcast(clients, json.dumps({"type": "error", "text": last_error}))
            else:
                broadcast(clients, json.dumps({"type": "reload"}))


def run(watch_dir: Path, out: Path, host: str, port: int, rebuild: Callable[[], str | None]) -> None:
    httpd = _start_http(out, host, port)
    try:
        asyncio.run(_serve(watch_dir.resolve(), out.resolve(), host, port, rebuild))
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
