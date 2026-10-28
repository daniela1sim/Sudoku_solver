"""XY-Wing, XYZ-Wing and W-Wing deductions for standard Sudoku.

Each detector returns immutable deductions and never mutates CandidateState.
The pattern enumerator is also used by the independent verifier to check
candidate relationships and the complete set of permitted eliminations.
"""
from __future__ import annotations

from itertools import combinations

from sudoku.core.board import Cell
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Premise, cell_label
from sudoku.solvers.logical.base import LogicalTechnique
from sudoku.solvers.logical.strong_links import _links, _sees


def _common_eliminations(
    state: CandidateState, digit: int, sources: tuple[Cell, ...]
) -> tuple[Elimination, ...]:
    return tuple(
        Elimination(cell, digit)
        for cell in state.unsolved_cells()
        if cell not in sources
        and digit in state.candidates_at(*cell)
        and all(_sees(cell, source) for source in sources)
    )


def _wing_patterns(state: CandidateState, kind: str):
    """Yield (pattern_cells, digit_set, effects, explanation).

    XY/XYZ ordering: pivot, x-wing, y-wing. W-Wing ordering:
    first bivalue cell, strong-link endpoint 1, endpoint 2, second bivalue.
    """
    if not isinstance(state, CandidateState):
        raise TypeError("state must be CandidateState")
    if kind not in {"XY-Wing", "XYZ-Wing", "W-Wing"}:
        raise ValueError("Unsupported wing technique")

    bivalue = tuple(cell for cell in state.unsolved_cells()
                    if len(state.candidates_at(*cell)) == 2)
    if kind in {"XY-Wing", "XYZ-Wing"}:
        pivots = (bivalue if kind == "XY-Wing" else
                  tuple(cell for cell in state.unsolved_cells()
                        if len(state.candidates_at(*cell)) == 3))
        for pivot in pivots:
            pv = state.candidates_at(*pivot)
            neighbours = tuple(cell for cell in bivalue if _sees(pivot, cell))
            for wing_a, wing_b in combinations(neighbours, 2):
                a, b = state.candidates_at(*wing_a), state.candidates_at(*wing_b)
                z_values = (a & b) - (pv if kind == "XY-Wing" else frozenset())
                if len(z_values) != 1:
                    continue
                z = next(iter(z_values))
                if kind == "XY-Wing":
                    # Wing pairs {x,z}, {y,z}, pivot {x,y}.
                    if len((a | b) - {z}) != 2 or (a | b) - {z} != pv:
                        continue
                else:
                    # Pivot {x,y,z}, wings {x,z}, {y,z}.
                    if z not in pv or a | b != pv or len((a | b) - {z}) != 2:
                        continue
                # Consistent ordering by the unique pivot digit in each wing.
                x, y = sorted(pv - {z}) if kind == "XYZ-Wing" else sorted(pv)
                if x not in a:
                    wing_a, wing_b = wing_b, wing_a
                sources = (pivot, wing_a, wing_b)
                effects = _common_eliminations(
                    state, z, (wing_a, wing_b) if kind == "XY-Wing" else sources
                )
                if effects:
                    explanation = (
                        f"{cell_label(pivot)} is the pivot; wings "
                        f"{cell_label(wing_a)} and {cell_label(wing_b)} force "
                        f"digit {z} into at least one of "
                        + ("the wings" if kind == "XY-Wing" else "the three pattern cells")
                        + "."
                    )
                    yield sources, frozenset(pv | {z}), effects, explanation
    else:
        for wing_a, wing_b in combinations(bivalue, 2):
            digits = state.candidates_at(*wing_a)
            if state.candidates_at(*wing_b) != digits or _sees(wing_a, wing_b):
                continue
            for link_digit in sorted(digits):
                target_digit = next(iter(digits - {link_digit}))
                for link in _links(state, link_digit):
                    a, b = link.cells
                    if len({wing_a, wing_b, a, b}) != 4:
                        continue
                    if _sees(wing_a, a) and _sees(wing_b, b):
                        ends = (a, b)
                    elif _sees(wing_a, b) and _sees(wing_b, a):
                        ends = (b, a)
                    else:
                        continue
                    cells = (wing_a, *ends, wing_b)
                    effects = _common_eliminations(state, target_digit, (wing_a, wing_b))
                    if effects:
                        explanation = (
                            f"{cell_label(wing_a)} and {cell_label(wing_b)} "
                            f"both contain {sorted(digits)}. A conjugate link "
                            f"for {link_digit} between {cell_label(ends[0])} and "
                            f"{cell_label(ends[1])} forces at least one wing "
                            f"to contain {target_digit}."
                        )
                        yield cells, frozenset(digits), effects, explanation


class _WingTechnique(LogicalTechnique):
    _name: str

    @property
    def name(self) -> str:
        return self._name

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        found: list[Deduction] = []
        seen: set[tuple[tuple[Cell, ...], int, tuple[Elimination, ...]]] = set()
        for cells, digits, effects, description in _wing_patterns(state, self.name):
            # Equivalent W-Wing patterns can arise from more than one link.
            key = (cells, min(e.digit for e in effects), effects)
            if key in seen:
                continue
            seen.add(key)
            found.append(Deduction(
                technique=self.name,
                premises=(Premise(description, cells, digits),),
                eliminations=effects,
            ))
        return tuple(found)


class XYWing(_WingTechnique):
    _name = "XY-Wing"


class XYZWing(_WingTechnique):
    _name = "XYZ-Wing"


class WWing(_WingTechnique):
    _name = "W-Wing"
