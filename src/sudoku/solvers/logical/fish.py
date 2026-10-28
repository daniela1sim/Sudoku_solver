"""Generalized basic fish: X-Wing (2), Swordfish (3), Jellyfish (4).

For one digit, n base rows (or columns) have candidate positions confined
within exactly n cover columns (or rows). The digit must occupy the
intersections, allowing its removal from other cells of those cover units.
This module intentionally implements *basic* fish, not finned/sashimi fish.
"""

from __future__ import annotations

from itertools import combinations

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Premise, cell_label
from sudoku.solvers.logical.base import LogicalTechnique

_FISH_NAMES = {2: "X-Wing", 3: "Swordfish", 4: "Jellyfish"}


def _fish_patterns(state: CandidateState, size: int):
    """Yield (orientation, digit, base indices, cover indices, base cells, effects).

    Recomputed by the verifier, independently of any submitted premise text.
    """
    board = state.board
    for digit in sorted(SudokuBoard.DIGITS):
        for orientation in ("row", "column"):
            positions = {}
            for base in range(9):
                base_cells = tuple((base, c) for c in range(9)) if orientation == "row" else tuple(
                    (r, base) for r in range(9)
                )
                if any(board.value_at(*cell) == digit for cell in base_cells):
                    continue
                covers = frozenset(
                    cell[1] if orientation == "row" else cell[0]
                    for cell in base_cells if digit in state.candidates_at(*cell)
                )
                if 2 <= len(covers) <= size:
                    positions[base] = covers
            for bases in combinations(sorted(positions), size):
                covers = frozenset().union(*(positions[base] for base in bases))
                if len(covers) != size:
                    continue
                base_cells = tuple(
                    (base, cover) if orientation == "row" else (cover, base)
                    for base in bases for cover in sorted(positions[base])
                )
                effects = tuple(
                    Elimination((r, c), digit)
                    for r in range(9) for c in range(9)
                    if ((c in covers and r not in bases) if orientation == "row"
                        else (r in covers and c not in bases))
                    and digit in state.candidates_at(r, c)
                )
                if effects:
                    yield orientation, digit, bases, covers, base_cells, effects


class BasicFish(LogicalTechnique):
    """Generalized basic fish of size 2, 3 or 4."""

    def __init__(self, size: int):
        if type(size) is not int or size not in _FISH_NAMES:
            raise ValueError("fish size must be 2, 3, or 4")
        self.size = size

    @property
    def name(self) -> str:
        return _FISH_NAMES[self.size]

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        if not isinstance(state, CandidateState):
            raise TypeError("state must be a CandidateState")
        results = []
        seen = set()
        for orientation, digit, bases, covers, cells, effects in _fish_patterns(state, self.size):
            key = (orientation, digit, bases, tuple(sorted(covers)))
            if key in seen:
                continue
            seen.add(key)
            base_label = ", ".join(str(i + 1) for i in bases)
            cover_label = ", ".join(str(i + 1) for i in sorted(covers))
            opposite = "columns" if orientation == "row" else "rows"
            description = (
                f"{self.name} for digit {digit}: base {orientation}s {base_label} "
                f"contain this digit only in {opposite} {cover_label}. "
                f"These {self.size} cover units must each use one of the base "
                f"{orientation}s, so remove {digit} from their other cells. "
                f"Pattern positions: {', '.join(map(cell_label, cells))}."
            )
            results.append(Deduction(
                technique=self.name,
                premises=(Premise(description, cells, frozenset({digit})),),
                eliminations=effects,
            ))
        return tuple(results)


class XWing(BasicFish):
    def __init__(self):
        super().__init__(2)


class Swordfish(BasicFish):
    def __init__(self):
        super().__init__(3)


class Jellyfish(BasicFish):
    def __init__(self):
        super().__init__(4)
