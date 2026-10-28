"""Short single-digit alternating chains: Skyscraper, 2-String Kite, Crane.

Each deduction follows the pattern A == B -- C == D, where '==' denotes
an exact two-position (conjugate) link in a Sudoku house and '--' denotes
mutual exclusion (the cells see each other). At least one of A and D must
contain the digit, so it can be removed from any candidate seeing both.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from sudoku.core.board import Cell, SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Premise, cell_label
from sudoku.solvers.logical.base import LogicalTechnique


@dataclass(frozen=True, slots=True)
class _StrongLink:
    kind: str  # row, column, box
    index: int
    cells: tuple[Cell, Cell]


def _box(cell: Cell) -> int:
    return (cell[0] // 3) * 3 + cell[1] // 3


def _sees(a: Cell, b: Cell) -> bool:
    return a != b and (a[0] == b[0] or a[1] == b[1] or _box(a) == _box(b))


def _links(state: CandidateState, digit: int) -> tuple[_StrongLink, ...]:
    board = state.board
    result = []
    for kind in ("row", "column", "box"):
        for i in range(9):
            if kind == "row":
                cells = ((i, c) for c in range(9))
            elif kind == "column":
                cells = ((r, i) for r in range(9))
            else:
                br, bc = (i // 3) * 3, (i % 3) * 3
                cells = ((r, c) for r in range(br, br + 3) for c in range(bc, bc + 3))
            cells = tuple(cells)
            if any(board.value_at(*cell) == digit for cell in cells):
                continue
            positions = tuple(cell for cell in cells if digit in state.candidates_at(*cell))
            if len(positions) == 2:
                result.append(_StrongLink(kind, i, positions))
    return tuple(result)


def _matching_connector(technique: str, a: _StrongLink, b: _StrongLink,
                        x: Cell, y: Cell) -> bool:
    if technique == "Skyscraper":
        # Two parallel line links, joined by a perpendicular weak link.
        if a.kind != b.kind or a.kind not in ("row", "column"):
            return False
        return x[1] == y[1] if a.kind == "row" else x[0] == y[0]
    if technique == "2-String Kite":
        # One row and one column conjugate, joined through a shared box.
        return {a.kind, b.kind} == {"row", "column"} and _box(x) == _box(y)
    if technique == "Crane":
        # A box conjugate and a line conjugate, joined through a line.
        return ("box" in (a.kind, b.kind)
                and {a.kind, b.kind} != {"box"}
                and (x[0] == y[0] or x[1] == y[1]))
    raise ValueError(f"Unsupported strong-link technique: {technique}")


def _strong_link_patterns(state: CandidateState, technique: str):
    """Yield (digit, chain_cells, effects) for each valid oriented chain.

    The chain is (tail_a, connector_a, connector_b, tail_b).
    Used independently by both discovery and deduction verification.
    """
    if not isinstance(state, CandidateState):
        raise TypeError("state must be a CandidateState")
    for digit in sorted(SudokuBoard.DIGITS):
        links = _links(state, digit)
        seen = set()
        for first, second in combinations(links, 2):
            for a_tail, a_middle in ((first.cells[0], first.cells[1]),
                                     (first.cells[1], first.cells[0])):
                for b_middle, b_tail in ((second.cells[0], second.cells[1]),
                                         (second.cells[1], second.cells[0])):
                    chain = (a_tail, a_middle, b_middle, b_tail)
                    if len(set(chain)) != 4:
                        continue
                    if not _sees(a_middle, b_middle):
                        continue
                    if not _matching_connector(technique, first, second, a_middle, b_middle):
                        continue
                    # Canonicalize reverse chains and duplicated unit descriptions.
                    key = min(chain, chain[::-1])
                    if key in seen:
                        continue
                    effects = tuple(
                        Elimination((r, c), digit)
                        for r in range(9) for c in range(9)
                        if (r, c) not in chain
                        and digit in state.candidates_at(r, c)
                        and _sees((r, c), a_tail) and _sees((r, c), b_tail)
                    )
                    if not effects:
                        continue
                    seen.add(key)
                    yield digit, chain, effects


class _TwoStrongLinks(LogicalTechnique):
    _name: str

    @property
    def name(self) -> str:
        return self._name

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        deductions = []
        for digit, chain, effects in _strong_link_patterns(state, self.name):
            a, b, c, d = chain
            description = (
                f"{self.name} on digit {digit}: {cell_label(a)} and {cell_label(b)} "
                f"form a strong link, as do {cell_label(c)} and {cell_label(d)}. "
                f"{cell_label(b)} and {cell_label(c)} see each other, so at "
                f"least one of the outer endpoints {cell_label(a)} or "
                f"{cell_label(d)} must contain {digit}. Remove {digit} from "
                "cells seeing both endpoints."
            )
            deductions.append(Deduction(
                technique=self.name,
                premises=(Premise(description, chain, frozenset({digit})),),
                eliminations=effects,
            ))
        return tuple(deductions)


class Skyscraper(_TwoStrongLinks):
    _name = "Skyscraper"


class TwoStringKite(_TwoStrongLinks):
    _name = "2-String Kite"


class Crane(_TwoStrongLinks):
    _name = "Crane"
