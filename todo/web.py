"""Local web GUI: a tiny JSON API plus a single-page, Apple-style front end (stdlib only)."""
from __future__ import annotations

import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .store import TodoError, TodoStore

STATIC = Path(__file__).with_name("index.html")


def make_server(path: str | None, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = "todo-web"

        def log_message(self, *a: Any) -> None:  # keep the terminal quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, data: Any) -> None:
            self._send(code, json.dumps(data).encode())

        def _host_ok(self) -> bool:  # defends against DNS rebinding
            h = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
            return h in ("127.0.0.1", "localhost", "::1", host)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 1_000_000:
                raise TodoError("request too large")
            if n == 0:
                return {}
            try:
                data = json.loads(self.rfile.read(n))
            except ValueError:
                raise TodoError("invalid JSON body") from None
            if not isinstance(data, dict):
                raise TodoError("JSON body must be an object")
            return data

        def _dispatch(self, method: str) -> None:
            if not self._host_ok():
                return self._json(403, {"error": "forbidden host"})
            url = self.path.split("?", 1)
            route, query = url[0], (url[1] if len(url) > 1 else "")
            if method == "GET" and route in ("/", "/index.html"):
                return self._send(200, STATIC.read_bytes(), "text/html; charset=utf-8")
            if not route.startswith("/api/"):
                return self._json(404, {"error": "not found"})
            if method != "GET" and "application/json" not in (self.headers.get("Content-Type") or ""):
                return self._json(415, {"error": "Content-Type must be application/json"})
            try:
                self._json(*self._api(method, route, query))
            except TodoError as exc:
                self._json(404 if "no task" in str(exc) else 400, {"error": str(exc)})
            except Exception as exc:  # never kill the server on a bad request
                self._json(500, {"error": str(exc)})

        def _api(self, method: str, route: str, query: str) -> tuple[int, Any]:
            store = TodoStore(path)
            parts = route.strip("/").split("/")[1:]
            if parts == ["tasks"] and method == "GET":
                params = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
                from urllib.parse import unquote_plus
                status = params.get("status", "all")
                if status not in ("all", "pending", "done"):
                    raise TodoError("invalid status")
                tasks = store.query(status=status, text=unquote_plus(params.get("q", "")) or None)
                return 200, [asdict(t) | {"overdue": t.is_overdue()} for t in tasks]
            if parts == ["tasks"] and method == "POST":
                b = self._body()
                t = store.add(str(b.get("title", "")), b.get("priority") or "medium", b.get("due") or None,
                              b.get("tags") or [], b.get("note") or "", b.get("repeat") or None,
                              b.get("parent"))
                return 201, asdict(t)
            if parts == ["restore"] and method == "POST":
                return 200, {"restored": [t.id for t in store.restore()]}
            if parts == ["clear"] and method == "POST":
                return 200, {"removed": store.clear_done()}
            if len(parts) == 2 and parts[0] == "tasks":
                try:
                    tid = int(parts[1])
                except ValueError:
                    raise TodoError("no task with that id") from None
                if method == "DELETE":
                    store.remove(tid)
                    return 200, {"removed": tid}
                if method == "PATCH":
                    b = self._body()
                    fields = {k: b[k] for k in ("title", "priority", "note", "repeat") if k in b}
                    if "tags" in b:
                        fields["tags"] = b["tags"] or []
                    if "due" in b:
                        if b["due"]:
                            fields["due"] = b["due"]
                        else:
                            fields["clear_due"] = True
                    if fields:
                        store.edit(tid, **fields)
                    if "done" in b:
                        if b["done"]:
                            store.complete(tid)
                        else:
                            store.set_done(tid, False)
                    return 200, asdict(store.get(tid))
            return 404, {"error": "not found"}

        def do_GET(self) -> None: self._dispatch("GET")
        def do_POST(self) -> None: self._dispatch("POST")
        def do_PATCH(self) -> None: self._dispatch("PATCH")
        def do_DELETE(self) -> None: self._dispatch("DELETE")

    return ThreadingHTTPServer((host, port), Handler)
