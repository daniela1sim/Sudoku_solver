"""Run with python -m sudoku.app (loopback only)."""

import argparse
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
import threading
import traceback
from uuid import uuid4

from sudoku.app.session import ReplaySession


class AppServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address):
        super().__init__(address, Handler)
        self.sessions = OrderedDict()
        self.session_lock = threading.Lock()


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
            if not 0 < length <= 4096:
                raise ValueError("Request body must be between 1 and 4096 bytes")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("Expected a JSON object")
            with self.server.session_lock:
                if self.path == "/api/start":
                    puzzle = body.get("puzzle")
                    if not isinstance(puzzle, str):
                        raise ValueError("Enter an 81-character puzzle")
                    unique = body.get("allow_uniqueness", False)
                    if type(unique) is not bool:
                        raise ValueError("Uniqueness option must be a boolean")
                    session = ReplaySession(puzzle, allow_uniqueness=unique)
                    session.act("replay")
                    token = uuid4().hex
                    self.server.sessions[token] = session
                    while len(self.server.sessions) > 32:
                        self.server.sessions.popitem(last=False)
                    response = {"session": token, **session.view()}
                elif self.path == "/api/action":
                    token = body.get("session")
                    if not isinstance(token, str) or token not in self.server.sessions:
                        self.reply(404, {"error": "Session expired. Load the puzzle again."})
                        return
                    self.server.sessions.move_to_end(token)
                    response = self.server.sessions[token].act(body.get("action"), body.get("cursor"))
                else:
                    self.reply(404, {"error": "Not found"})
                    return
        except (ValueError, TypeError) as exc:
            self.reply(400, {"error": str(exc)})
            return
        except Exception:
            self.log_error("Unexpected solver failure: %s", traceback.format_exc())
            self.reply(500, {"error": "The solver could not verify this step. Reload the puzzle to retry."})
            return
        self.reply(200, response)


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
