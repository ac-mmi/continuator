"""stdlib HTTP server for Continuator Phase 2 API."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from continuator import __version__
from continuator.runtime import ensure_runtime


class ContinuatorHandler(BaseHTTPRequestHandler):
    server_version = f"continuator/{__version__}"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        data = json.loads(raw.decode("utf-8") or "{}")
        return data if isinstance(data, dict) else {}

    def _send_json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "baseline": "v10-050+repair+continuation_export_v2_frontier+explain_v1",
                    "model_loaded": True,
                    "version": __version__,
                },
            )
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        body = self._read_json()

        try:
            if path == "/v1/extract":
                self._handle_extract(body)
            elif path == "/v1/checkpoint":
                self._handle_checkpoint(body)
            elif path == "/v1/resume":
                self._handle_resume(body, refresh=False)
            elif path == "/v1/resume/refresh":
                self._handle_resume(body, refresh=True)
            else:
                self._send_json(404, {"error": "not found"})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": f"{type(exc).__name__}: {exc}"})

    def _handle_extract(self, body: dict[str, Any]) -> None:
        transcript = str(body.get("transcript") or "").strip()
        if not transcript:
            raise ValueError("transcript required")
        from continuator.platform.extract import extract_full

        project = str(body.get("project") or body.get("label") or "conversation")
        record, _session = extract_full(
            transcript,
            label=str(body.get("label") or project),
            project=project,
            tier="full",
        )
        self._send_json(200, {"checkpoint": record})

    def _handle_checkpoint(self, body: dict[str, Any]) -> None:
        transcript = str(body.get("transcript") or "").strip()
        if not transcript:
            raise ValueError("transcript required")
        project = str(body.get("project") or "conversation")
        update = bool(body.get("update"))
        from checkpoint_store_v2 import find_checkpoint_for_update, load_checkpoint, save_checkpoint
        from continuator.platform.extract import extract_full, extract_incremental

        if update:
            prior = find_checkpoint_for_update(project)
            if prior:
                record, _ = extract_incremental(
                    transcript,
                    prior,
                    label=str(body.get("label") or project),
                    project=project,
                    tier="full",
                )
                path = save_checkpoint(record)
                record = load_checkpoint(path) or record
                self._send_json(200, {"path": str(path), "checkpoint": record})
                return
        record, _ = extract_full(
            transcript,
            label=str(body.get("label") or project),
            project=project,
            tier="full",
        )
        path = save_checkpoint(record)
        record = load_checkpoint(path) or record
        self._send_json(200, {"path": str(path), "checkpoint": record})

    def _handle_resume(self, body: dict[str, Any], *, refresh: bool) -> None:
        from continuator.platform.resume import load_and_resume

        fmt = str(body.get("format") or "briefing")
        text, record, elapsed_ms = load_and_resume(
            target=str(body.get("path") or "") or None,
            project=str(body.get("project") or "") or None,
            fmt=fmt,
            refresh=refresh,
            transcript=str(body.get("transcript") or "").strip() or None,
        )
        self._send_json(200, {"text": text, "elapsed_ms": round(elapsed_ms, 1), "checkpoint_id": record.get("id")})


def run_server(*, host: str = "127.0.0.1", port: int = 8741) -> None:
    ensure_runtime()
    server = ThreadingHTTPServer((host, port), ContinuatorHandler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
