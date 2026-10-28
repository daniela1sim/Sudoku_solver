"""Almost Locked Sets and the singly-linked ALS-XZ elimination rule.

A set of n unsolved cells in one Sudoku unit is an Almost Locked Set (ALS)
when its candidate union contains exactly n+1 digits. Two *disjoint* ALSs
connected through a Restricted Common Candidate (RCC) x force a shared,
non-RCC digit z into at least one ALS. Any cell seeing every z position in
both ALSs can therefore eliminate z.

This module deliberately implements only the singly-linked ALS-XZ rule.
Doubly-linked and overlapping-ALS extensions are future work.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from sudoku.core.board import Cell
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Premise, cell_label
from sudoku.solvers.logical.base import LogicalTechnique
from sudoku.solvers.logical.singles import _units
from sudoku.solvers.logical.strong_links import _sees


@dataclass(frozen=True, slots=True)
class AlmostLockedSet:
    """An ALS with a canonical cell ordering and one supporting unit."""

    cells: tuple[Cell, ...]
    digits: frozenset[int]
    kind: str
    index: int


def _candidate_union(state: CandidateState, cells: tuple[Cell, ...]) -> frozenset[int]:
    return frozenset().union(*(state.candidates_at(*cell) for cell in cells))


def is_als(state: CandidateState, cells: tuple[Cell, ...]) -> bool:
    """Validate an ALS witness against the current candidates, not prose."""
    if not cells or len(set(cells)) != len(cells):
        return False
    if any(not state.candidates_at(*cell) for cell in cells):
        return False
    if not any(set(cells).issubset(unit) for _, _, unit in _units()):
        return False
    return len(_candidate_union(state, cells)) == len(cells) + 1


def find_almost_locked_sets(
    state: CandidateState, *, max_size: int = 3,
) -> tuple[AlmostLockedSet, ...]:
    """Enumerate nonempty ALSs in all 27 units, deduplicating repeated sets.

    A bivalue cell counts as a 1-cell ALS. Restricting the maximum size
    bounds combinatorial cost independently of the 9x9 board dimension.
    """
    if not isinstance(state, CandidateState):
        raise TypeError("state must be a CandidateState")
    if type(max_size) is not int or not 1 <= max_size <= 8:
        raise ValueError("max_size must be an integer between 1 and 8")
    found: dict[tuple[Cell, ...], AlmostLockedSet] = {}
    for kind, index, unit in _units():
        eligible = [cell for cell in unit if 1 < len(state.candidates_at(*cell)) <= max_size + 1]
        for n in range(1, min(max_size, len(eligible)) + 1):
            for cells in combinations(eligible, n):
                canonical = tuple(sorted(cells))
                if canonical in found:
                    continue
                digits = _candidate_union(state, canonical)
                if len(digits) == n + 1:
                    found[canonical] = AlmostLockedSet(canonical, digits, kind, index)
    return tuple(sorted(found.values(), key=lambda item: item.cells))


def _rcc_positions(
    state: CandidateState, a: AlmostLockedSet, b: AlmostLockedSet, digit: int,
) -> tuple[Cell, ...] | None:
    """Return RCC positions only if every cross-pair sees each other."""
    left = tuple(cell for cell in a.cells if digit in state.candidates_at(*cell))
    right = tuple(cell for cell in b.cells if digit in state.candidates_at(*cell))
    if not left or not right or not all(_sees(x, y) for x in left for y in right):
        return None
    return tuple(sorted((*left, *right)))


def _xz_effects(
    state: CandidateState, a: AlmostLockedSet, b: AlmostLockedSet, z: int,
) -> tuple[Elimination, ...]:
    z_cells = tuple(cell for cell in (*a.cells, *b.cells)
                    if z in state.candidates_at(*cell))
    members = set(a.cells) | set(b.cells)
    return tuple(Elimination(cell, z) for cell in state.unsolved_cells()
                 if cell not in members and z in state.candidates_at(*cell)
                 and all(_sees(cell, holder) for holder in z_cells))


class ALSXZ(LogicalTechnique):
    """Search for disjoint ALS pairs with a restricted common candidate."""

    def __init__(self, max_size: int = 3) -> None:
        if type(max_size) is not int or not 1 <= max_size <= 4:
            raise ValueError("max_size must be an integer between 1 and 4")
        self.max_size = max_size

    @property
    def name(self) -> str:
        return "ALS-XZ"

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        if not isinstance(state, CandidateState):
            raise TypeError("state must be a CandidateState")
        result: list[Deduction] = []
        groups = find_almost_locked_sets(state, max_size=self.max_size)
        for a, b in combinations(groups, 2):
            if not set(a.cells).isdisjoint(b.cells):
                continue
            shared = a.digits & b.digits
            if len(shared) < 2:
                continue
            for x in sorted(shared):
                positions = _rcc_positions(state, a, b, x)
                if positions is None:
                    continue
                for z in sorted(shared - {x}):
                    effects = _xz_effects(state, a, b, z)
                    if not effects:
                        continue
                    result.append(Deduction(
                        technique=self.name,
                        premises=(
                            Premise(f"ALS A: {', '.join(map(cell_label, a.cells))} "
                                    f"has {len(a.cells) + 1} candidates.",
                                    a.cells, a.digits),
                            Premise(f"ALS B: {', '.join(map(cell_label, b.cells))} "
                                    f"has {len(b.cells) + 1} candidates.",
                                    b.cells, b.digits),
                            Premise(f"Candidate {x} is restricted between the ALSs: "
                                    f"it cannot appear in both. Consequently, at least "
                                    f"one ALS must contain {z}, which can be removed "
                                    f"from common peers of all its possible positions.",
                                    positions, frozenset({x})),
                        ),
                        eliminations=effects,
                    ))
        return tuple(result)
