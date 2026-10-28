"""Locked candidates: pointing (box -> line) and claiming (line -> box)."""
from __future__ import annotations
from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Premise, cell_label
from sudoku.solvers.logical.base import LogicalTechnique


def _locked_patterns(state: CandidateState, mode: str):
    """Yield (support cells, digit, eliminations, description) in stable order."""
    board = state.board
    for digit in sorted(SudokuBoard.DIGITS):
        if mode == "pointing":
            for br in range(3):
                for bc in range(3):
                    box = tuple((r,c) for r in range(br*3,br*3+3) for c in range(bc*3,bc*3+3))
                    positions = tuple(p for p in box if digit in state.candidates_at(*p))
                    if len(positions) < 2:
                        continue
                    for axis in ("row", "column"):
                        indices = {p[0 if axis == "row" else 1] for p in positions}
                        if len(indices) != 1:
                            continue
                        index = next(iter(indices))
                        line = ((index,c) for c in range(9)) if axis == "row" else ((r,index) for r in range(9))
                        effects = tuple(Elimination(p,digit) for p in line if p not in box and digit in state.candidates_at(*p))
                        if effects:
                            description = (f"Digit {digit} is confined to {axis} {index+1} within box {br*3+bc+1}; "
                                           f"remove it from that {axis} outside the box.")
                            yield positions,digit,effects,description
        else:
            for axis in ("row", "column"):
                for index in range(9):
                    line = tuple((index,c) for c in range(9)) if axis == "row" else tuple((r,index) for r in range(9))
                    positions = tuple(p for p in line if digit in state.candidates_at(*p))
                    if len(positions) < 2:
                        continue
                    boxes = {(r//3,c//3) for r,c in positions}
                    if len(boxes) != 1:
                        continue
                    br,bc = next(iter(boxes))
                    box = ((r,c) for r in range(br*3,br*3+3) for c in range(bc*3,bc*3+3))
                    effects = tuple(Elimination(p,digit) for p in box if p not in line and digit in state.candidates_at(*p))
                    if effects:
                        description = (f"Digit {digit} in {axis} {index+1} is confined to box {br*3+bc+1}; "
                                       "remove it from the other cells in that box.")
                        yield positions,digit,effects,description


class LockedCandidates(LogicalTechnique):
    def __init__(self, mode: str):
        if mode not in ("pointing", "claiming"):
            raise ValueError("mode must be 'pointing' or 'claiming'")
        self.mode = mode

    @property
    def name(self) -> str:
        return "Pointing" if self.mode == "pointing" else "Claiming"

    def find_deductions(self, state: CandidateState) -> tuple[Deduction,...]:
        if not isinstance(state,CandidateState):
            raise TypeError("state must be a CandidateState")
        return tuple(Deduction(self.name, (Premise(desc,positions,frozenset({digit})),),
                               eliminations=effects)
                     for positions,digit,effects,desc in _locked_patterns(state,self.mode))


class Pointing(LockedCandidates):
    def __init__(self): super().__init__("pointing")


class Claiming(LockedCandidates):
    def __init__(self): super().__init__("claiming")
