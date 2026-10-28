"""Witness-directed verification for XY-Wing, XYZ-Wing and W-Wing.

The wing *detectors* are deliberately not imported here.  The proof checker
reads only current candidates, Sudoku peer geometry, and the structured
witness supplied in ``deduction.premises[0]``.  Explanation text is never
accepted as evidence.

Witness cell order, retained for compatibility with the existing UI/history:
* XY/XYZ: (pivot, wing_with_x, wing_with_y).
* W-Wing: (first_bivalue, first_link_end, second_link_end, second_bivalue).
"""

from __future__ import annotations

from sudoku.core.board import Cell
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction


def _sees(left: Cell, right: Cell) -> bool:
    """Direct Sudoku geometry, independent of the wing generator's helpers."""
    return left != right and (
        left[0] == right[0]
        or left[1] == right[1]
        or (left[0] // 3, left[1] // 3) == (right[0] // 3, right[1] // 3)
    )


def _common_unit_has_exact_pair(
    state: CandidateState, left: Cell, right: Cell, digit: int
) -> bool:
    """A conjugate pair requires exactly these two positions in one unit."""
    if not _sees(left, right):
        return False
    if digit not in state.candidates_at(*left) or digit not in state.candidates_at(*right):
        return False
    units: list[tuple[Cell, ...]] = []
    if left[0] == right[0]:
        units.append(tuple((left[0], col) for col in range(9)))
    if left[1] == right[1]:
        units.append(tuple((row, left[1]) for row in range(9)))
    if (left[0] // 3, left[1] // 3) == (right[0] // 3, right[1] // 3):
        first_row, first_col = (left[0] // 3) * 3, (left[1] // 3) * 3
        units.append(tuple(
            (row, col)
            for row in range(first_row, first_row + 3)
            for col in range(first_col, first_col + 3)
        ))
    return any(
        {cell for cell in unit if digit in state.candidates_at(*cell)} == {left, right}
        for unit in units
    )


def _validate_xy_or_xyz(
    state: CandidateState, cells: tuple[Cell, ...], digits: frozenset[int],
    target_digit: int, *, xyz: bool,
) -> tuple[Cell, ...]:
    if len(cells) != 3:
        raise ValueError("Invalid XY/XYZ-Wing witness: expected pivot and two wings")
    pivot, wing_a, wing_b = cells
    pivot_digits = state.candidates_at(*pivot)
    a = state.candidates_at(*wing_a)
    b = state.candidates_at(*wing_b)
    if not (_sees(pivot, wing_a) and _sees(pivot, wing_b)):
        raise ValueError("Invalid XY/XYZ-Wing witness: wing does not see pivot")
    if len(a) != 2 or len(b) != 2 or target_digit not in a or target_digit not in b:
        raise ValueError("Invalid XY/XYZ-Wing witness: wings must be bivalue with a common target digit")
    # Each wing must have a different non-target digit, equal to the pivot's
    # non-target digits. This is the actual forcing relationship.
    other_a, other_b = a - {target_digit}, b - {target_digit}
    if len(other_a | other_b) != 2:
        raise ValueError("Invalid XY/XYZ-Wing witness: non-target wing digits must differ")
    if xyz:
        if (len(pivot_digits) != 3 or target_digit not in pivot_digits
                or other_a | other_b | {target_digit} != pivot_digits
                or digits != pivot_digits):
            raise ValueError("Invalid XYZ-Wing witness: inconsistent pivot digits")
        return (pivot, wing_a, wing_b)
    if (len(pivot_digits) != 2 or target_digit in pivot_digits
            or other_a | other_b != pivot_digits
            or digits != pivot_digits | {target_digit}):
        raise ValueError("Invalid XY-Wing witness: inconsistent pivot digits")
    return (wing_a, wing_b)


def _validate_w_wing(
    state: CandidateState, cells: tuple[Cell, ...], digits: frozenset[int],
    target_digit: int,
) -> tuple[Cell, ...]:
    if len(cells) != 4:
        raise ValueError("Invalid W-Wing witness: expected two wings and two link endpoints")
    wing_a, link_a, link_b, wing_b = cells
    a, b = state.candidates_at(*wing_a), state.candidates_at(*wing_b)
    if len(a) != 2 or b != a or digits != a or target_digit not in a:
        raise ValueError("Invalid W-Wing witness: wings must have the same bivalue candidates")
    if _sees(wing_a, wing_b):
        raise ValueError("Invalid W-Wing witness: wing cells must not see one another")
    link_digit = next(iter(a - {target_digit}))
    if not (_sees(wing_a, link_a) and _sees(wing_b, link_b)):
        raise ValueError("Invalid W-Wing witness: endpoints must see their associated wings")
    if not _common_unit_has_exact_pair(state, link_a, link_b, link_digit):
        raise ValueError("Invalid W-Wing witness: the link is not a conjugate pair")
    return (wing_a, wing_b)


def verify_wing(state: CandidateState, deduction: Deduction, *, name: str) -> None:
    """Prove every effect from the given witness, without pattern enumeration.

    The existing deduction structure identifies the witness cells, and each
    elimination states the target digit.  Verification is non-mutating and
    rejects stale effects, unrelated digits and non-peer targets.
    """
    if name not in ("XY-Wing", "XYZ-Wing", "W-Wing"):
        raise ValueError("Unsupported wing type")
    if (deduction.technique != name or deduction.placements
            or len(deduction.premises) != 1 or not deduction.eliminations):
        raise ValueError("Unexpected wing deduction shape")
    premise = deduction.premises[0]
    effects = deduction.eliminations
    target_digits = {move.digit for move in effects}
    if len(target_digits) != 1:
        raise ValueError("Wing eliminations must have a single target digit")
    target_digit = next(iter(target_digits))

    if name == "W-Wing":
        sources = _validate_w_wing(state, premise.cells, premise.digits, target_digit)
    else:
        sources = _validate_xy_or_xyz(
            state, premise.cells, premise.digits, target_digit,
            xyz=(name == "XYZ-Wing"),
        )

    if not all(
        move.cell not in sources
        and target_digit in state.candidates_at(*move.cell)
        and all(_sees(move.cell, source) for source in sources)
        for move in effects
    ):
        raise ValueError("Wing elimination is not justified")
