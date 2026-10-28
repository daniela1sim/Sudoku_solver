"""Strict Sue de Coq (two-sector disjoint subsets) deductions.

At the crossing of one line and one box, C has candidate union V.
A line-side ALS L and a box-side ALS B have disjoint candidate sets,
both contained in V, and |C|+|L|+|B| = |V|. Their digits are then
locked to their respective sectors, giving two-sided eliminations.

Scope: the complete 2- or 3-cell unsolved crossing and side ALSs of up to
``max_side_size`` cells; broader extended Sue de Coq is not attempted.
"""

from __future__ import annotations

from sudoku.core.board import Cell
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Premise, cell_label
from sudoku.solvers.logical.als import AlmostLockedSet, find_almost_locked_sets, _candidate_union
from sudoku.solvers.logical.base import LogicalTechnique


def _sector_effects(
    state: CandidateState,
    line: tuple[Cell, ...], box: tuple[Cell, ...],
    cross: tuple[Cell, ...], line_group: AlmostLockedSet,
    box_group: AlmostLockedSet,
) -> tuple[Elimination, ...]:
    """Compute permitted two-sector eliminations from a proven partition."""
    v = _candidate_union(state, cross)
    leftovers = v - line_group.digits - box_group.digits
    forbidden: set[Elimination] = set()
    for cell in line:
        if cell in cross or cell in line_group.cells:
            continue
        for digit in (line_group.digits | leftovers) & state.candidates_at(*cell):
            forbidden.add(Elimination(cell, digit))
    for cell in box:
        if cell in cross or cell in box_group.cells:
            continue
        for digit in (box_group.digits | leftovers) & state.candidates_at(*cell):
            forbidden.add(Elimination(cell, digit))
    return tuple(sorted(forbidden, key=lambda e: (e.cell, e.digit)))


class SueDeCoq(LogicalTechnique):
    """Find strict Sue de Coq patterns at every row/box and column/box crossing."""

    def __init__(self, max_side_size: int = 3) -> None:
        if type(max_side_size) is not int or not 1 <= max_side_size <= 4:
            raise ValueError("max_side_size must be an integer between 1 and 4")
        self.max_side_size = max_side_size

    @property
    def name(self) -> str:
        return "Sue de Coq"

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        if not isinstance(state, CandidateState):
            raise TypeError("state must be a CandidateState")
        groups = find_almost_locked_sets(state, max_size=self.max_side_size)
        results: list[Deduction] = []
        seen: set[tuple] = set()
        boxes = [tuple((r, c) for r in range(br, br + 3) for c in range(bc, bc + 3))
                 for br in (0, 3, 6) for bc in (0, 3, 6)]
        lines = [tuple((r, c) for c in range(9)) for r in range(9)] + [
            tuple((r, c) for r in range(9)) for c in range(9)]
        for line in lines:
            for box in boxes:
                intersect = set(line) & set(box)
                if not intersect:
                    continue
                cross = tuple(cell for cell in line if cell in intersect
                              and state.candidates_at(*cell))
                if not 2 <= len(cross) <= 3:
                    continue
                v = _candidate_union(state, cross)
                if len(v) < len(cross) + 2:
                    continue
                line_side = set(line) - intersect
                box_side = set(box) - intersect
                left = [a for a in groups if set(a.cells) <= line_side and a.digits <= v]
                right = [b for b in groups if set(b.cells) <= box_side and b.digits <= v]
                for a in left:
                    for b in right:
                        if a.digits & b.digits or len(v) != len(cross) + len(a.cells) + len(b.cells):
                            continue
                        effects = _sector_effects(state, line, box, cross, a, b)
                        if not effects:
                            continue
                        key = (cross, a.cells, b.cells)
                        if key in seen:
                            continue
                        seen.add(key)
                        leftover = v - a.digits - b.digits
                        results.append(Deduction(
                            technique=self.name,
                            premises=(
                                Premise(
                                    "Box/line intersection "
                                    + ", ".join(map(cell_label, cross))
                                    + f" has {len(v)} candidates for {len(cross)} cells.",
                                    cross, v),
                                Premise("Line-side ALS "
                                        + ", ".join(map(cell_label, a.cells))
                                        + ": its digits are locked in this line plus the intersection.",
                                        a.cells, a.digits),
                                Premise("Box-side ALS "
                                        + ", ".join(map(cell_label, b.cells))
                                        + ": its digits are locked in this box plus the intersection. "
                                        + (f"Intersection-only digits: {sorted(leftover)}." if leftover else ""),
                                        b.cells, b.digits),
                            ),
                            eliminations=effects,
                        ))
        return tuple(results)
