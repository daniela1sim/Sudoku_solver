"""Run with python -m sudoku.app (loopback only)."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
import traceback

from sudoku.app.service import SudokuService
from sudoku.app.techniques import catalog


class AppServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address):
        super().__init__(address, Handler)
        self.service = SudokuService()
        self.sessions = self.service.sessions


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload, content_type="application/json"):
        data = json.dumps(payload).encode() if content_type == "application/json" else payload
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/techniques":
            self.reply(200, catalog())
            return
        assets = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                  "/style.css": ("style.css", "text/css; charset=utf-8")}
        asset = assets.get(self.path)
        if asset is None:
            self.reply(404, {"error": "Not found"})
            return
        self.reply(200, files("sudoku.app").joinpath("static", asset[0]).read_bytes(), asset[1])

    def do_POST(self):
        # JSON-only requests and same-origin checks protect the local service
        # from requests initiated by unrelated web pages.
        origin = self.headers.get("Origin")
        expected = f"http://127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != expected.removeprefix("http://") or (origin and origin != expected):
            self.reply(403, {"error": "Use the local application URL"})
            return
        if self.headers.get("Content-Type") != "application/json":
            self.reply(415, {"error": "Expected JSON"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            limit = 12 * 1024 * 1024 if self.path == "/api/image" else 4096
            if not 0 < length <= limit:
                raise ValueError(f"Request body must be between 1 and {limit} bytes")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("Expected a JSON object")
            status, response = self.server.service.dispatch(self.path, body)
        except (ValueError, TypeError) as exc:
            self.reply(400, {"error": str(exc)})
            return
        except Exception:
            self.log_error("Unexpected solver failure: %s", traceback.format_exc())
            self.reply(500, {"error": "The solver could not verify this step. Reload the puzzle to retry."})
            return
        self.reply(status, response)


def main():
    parser = argparse.ArgumentParser(description="Interactive Sudoku deduction explorer")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    with AppServer(("127.0.0.1", args.port)) as server:
        print(f"Sudoku explorer: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
