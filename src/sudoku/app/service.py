"""Shared application state and operations for local and hosted transports."""
import base64
import binascii
from collections import OrderedDict
import threading
from uuid import uuid4

from sudoku.app.session import ReplaySession
from sudoku.solvers.constraint.reference import ReferenceSolver


class SudokuService:
    def __init__(self):
        self.sessions = OrderedDict()
        self.session_lock = threading.Lock()

    def dispatch(self, path, body):
        if path == "/api/check":
            puzzle = body.get("puzzle")
            if not isinstance(puzzle, str):
                raise ValueError("Enter an 81-character puzzle")
            # Independent of replay candidates, technique choices and the
            # uniqueness assumption. Do not hold the session lock during search.
            result = ReferenceSolver().analyze(puzzle, limit=2)
            status = ("unsatisfiable" if result.is_unsatisfiable else
                      "unique" if result.is_unique else "multiple")
            return 200, {
                "status": status,
                "solution_count": result.solution_count,
                "count_is_exact": result.exhaustive,
            }
        if path == "/api/image":
            from sudoku.vision import read_image
            encoded = body.get("image")
            if not isinstance(encoded, str):
                raise ValueError("Expected a base64 image")
            try:
                image = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError("Invalid base64 image") from exc
            return 200, read_image(image)
        with self.session_lock:
            if path == "/api/start":
                puzzle = body.get("puzzle")
                if not isinstance(puzzle, str):
                    raise ValueError("Enter an 81-character puzzle")
                unique = body.get("allow_uniqueness", False)
                if type(unique) is not bool:
                    raise ValueError("Uniqueness option must be a boolean")
                session = ReplaySession(puzzle, allow_uniqueness=unique,
                                        techniques=body.get("techniques"))
                session.act("replay")
                token = uuid4().hex
                self.sessions[token] = session
                while len(self.sessions) > 32:
                    self.sessions.popitem(last=False)
                response = {"session": token, **session.view()}
            elif path == "/api/action":
                token = body.get("session")
                if not isinstance(token, str) or token not in self.sessions:
                    return 404, {"error": "Session expired. Load the puzzle again."}
                self.sessions.move_to_end(token)
                response = self.sessions[token].act(body.get("action"), body.get("cursor"))
            else:
                return 404, {"error": "Not found"}
        return 200, response
