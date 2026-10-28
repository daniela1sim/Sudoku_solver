"""Replay sessions retain candidate eliminations and preview verified hints."""

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState, CandidateContradiction
from sudoku.app.techniques import selected_solver


def describe(deduction):
    if deduction is None:
        return None
    return {
        "technique": deduction.technique,
        "premises": [
            {"description": p.description, "cells": p.cells, "digits": sorted(p.digits)}
            for p in deduction.premises
        ],
        "placements": [{"cell": m.cell, "digit": m.digit} for m in deduction.placements],
        "eliminations": [{"cell": m.cell, "digit": m.digit} for m in deduction.eliminations],
    }


class ReplaySession:
    def __init__(self, puzzle: str, *, allow_uniqueness: bool = False, techniques=None):
        self.solver = selected_solver(techniques, allow_uniqueness=allow_uniqueness)
        board = SudokuBoard.from_string(puzzle)
        self.states = [CandidateState(board)]
        self.steps = []
        self.cursor = 0
        self.pending = None
        self.stuck = False
        self.contradiction = None

    def hint(self):
        if self.cursor < len(self.steps):
            return self.steps[self.cursor].deduction
        if self.pending is None and not self.stuck and not self.states[-1].is_complete():
            try:
                result = self.solver.solve(self.states[-1], max_steps=1)
            except CandidateContradiction as exc:
                self.contradiction = str(exc)
                self.stuck = True
                self.pending = exc.step
                return self.pending.deduction
            self.pending = result.steps[0] if result.steps else None
            self.stuck = self.pending is None
        return self.pending.deduction if self.pending else None

    def act(self, action, cursor=None):
        hint = None
        if action == "hint":
            hint = self.hint()
        elif action == "next":
            if self.cursor < len(self.steps):
                self.cursor += 1
            elif self.hint() is not None:
                self.steps.append(self.pending)
                self.states.append(self.pending.after.copy())
                self.pending = None
                self.cursor += 1
        elif action == "seek":
            if type(cursor) is not int or not 0 <= cursor <= len(self.steps):
                raise ValueError("Replay position is outside the recorded history")
            self.cursor = cursor
        elif action == "replay":
            # Generate from the latest saved candidate state, retaining all
            # previous eliminations and keeping the displayed replay position.
            # Commit each successful step so a later contradiction cannot
            # discard the partial replay. Failed updates remain atomic.
            saved_cursor = self.cursor
            self.cursor = len(self.steps)
            while self.hint() is not None:
                step = self.pending
                self.steps.append(step)
                self.states.append(step.after.copy())
                self.pending = None
                self.cursor = len(self.steps)
            self.stuck = not self.states[-1].is_complete()
            self.cursor = len(self.steps) if self.contradiction else saved_cursor
        else:
            raise ValueError("Unknown action")
        return self.view(hint)

    def view(self, hint=None):
        state = self.states[self.cursor]
        board = state.board
        return {
            "techniques": [t.name for t in self.solver.techniques],
            "grid": board.to_string(),
            "givens": sorted(board.givens),
            "candidates": [sorted(state.candidates_at(r, c)) for r in range(9) for c in range(9)],
            "cursor": self.cursor,
            "total": len(self.steps),
            "status": "solved" if state.is_complete() else (
                ("contradiction" if self.contradiction else "stuck")
                if self.stuck and self.cursor == len(self.steps) else "ready"
            ),
            "contradiction": self.contradiction if self.cursor == len(self.steps) else None,
            "hint": describe(hint),
            "last": describe(self.steps[self.cursor - 1].deduction) if self.cursor else None,
            "history": [step.deduction.technique for step in self.steps[:self.cursor]],
        }
