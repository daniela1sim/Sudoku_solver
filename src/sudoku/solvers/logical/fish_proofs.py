"""Independent, witness-directed proof checks for basic and finned fish.

These checks do not call or import fish discovery routines.  They use only
CandidateState, the immutable deduction and Sudoku unit geometry.  A witness
is encoded using the existing premise.cells (all active pattern candidates).
Premise.description is explanatory text, never evidence.
"""

from __future__ import annotations

from itertools import combinations

from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination


def _candidate(state: CandidateState, cell: tuple[int, int], digit: int) -> bool:
    return digit in state.candidates_at(*cell)


def _coordinate(cell: tuple[int, int], orientation: str) -> tuple[int, int]:
    return cell if orientation == "row" else (cell[1], cell[0])


def _cell(base: int, cover: int, orientation: str) -> tuple[int, int]:
    return (base, cover) if orientation == "row" else (cover, base)


def _box(cell: tuple[int, int]) -> tuple[int, int]:
    return cell[0] // 3, cell[1] // 3


def _sees(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a != b and (a[0] == b[0] or a[1] == b[1] or _box(a) == _box(b))


def _line_has_digit(state: CandidateState, base: int, orientation: str, digit: int) -> bool:
    board = state.board
    return any(board.value_at(*_cell(base, c, orientation)) == digit for c in range(9))


def _positions(state: CandidateState, base: int, orientation: str, digit: int) -> frozenset[int]:
    return frozenset(c for c in range(9) if _candidate(state, _cell(base, c, orientation), digit))


def _shape(deduction: Deduction, technique_name: str) -> tuple[tuple[tuple[int, int], ...], int, frozenset[Elimination]]:
    if (deduction.technique != technique_name or deduction.placements
            or len(deduction.premises) != 1 or not deduction.eliminations):
        raise ValueError("Unexpected fish deduction structure")
    premise = deduction.premises[0]
    if len(premise.digits) != 1 or not premise.cells:
        raise ValueError("Fish witness requires exactly one digit and supporting cells")
    digit = next(iter(premise.digits))
    effects = frozenset(deduction.eliminations)
    if any(move.digit != digit for move in effects):
        raise ValueError("Fish elimination uses an unrelated digit")
    return premise.cells, digit, effects


def verify_basic_fish(state: CandidateState, deduction: Deduction, *, name: str, size: int) -> None:
    """Check that the witness lines form a fish, then check every elimination."""
    cells, digit, effects = _shape(deduction, name)
    for orientation in ("row", "column"):
        bases = { _coordinate(cell, orientation)[0] for cell in cells }
        covers = { _coordinate(cell, orientation)[1] for cell in cells }
        if len(bases) != size or len(covers) != size:
            continue
        if any(_line_has_digit(state, b, orientation, digit) for b in bases):
            continue
        positions = {b: _positions(state, b, orientation, digit) for b in bases}
        if any(not (2 <= len(cs) <= size) or not cs.issubset(covers) for cs in positions.values()):
            continue
        actual = { _cell(b, c, orientation) for b, cs in positions.items() for c in cs }
        if actual != set(cells):
            continue
        if all(
            _candidate(state, move.cell, digit)
            and _coordinate(move.cell, orientation)[0] not in bases
            and _coordinate(move.cell, orientation)[1] in covers
            for move in effects
        ):
            return
    raise ValueError("Fish elimination is not justified")


def verify_finned_xwing(state: CandidateState, deduction: Deduction, *, name: str) -> None:
    """Verify the corner order, fin confinement and target corner box."""
    cells, digit, effects = _shape(deduction, name)
    if len(cells) < 5:
        raise ValueError("Finned X-Wing requires four corners and at least one fin")
    corners, fins = cells[:4], cells[4:]
    for orientation in ("row", "column"):
        (b0, a), (b0_other, b), (b1, a_other), (b1_other, b_other) = (
            _coordinate(x, orientation) for x in corners
        )
        if (b0 != b0_other or b1 != b1_other or b0 == b1
                or b0 // 3 == b1 // 3 or a == b or a != a_other or b != b_other):
            continue
        if any(_line_has_digit(state, base, orientation, digit) for base in (b0, b1)):
            continue
        if _positions(state, b0, orientation, digit) != frozenset({a, b}):
            continue
        extra = _positions(state, b1, orientation, digit) - {a, b}
        if (not extra or not {a, b}.issubset(_positions(state, b1, orientation, digit))
                or set(fins) != {_cell(b1, c, orientation) for c in extra}):
            continue
        boxes = {_box(fin) for fin in fins}
        if len(boxes) != 1:
            continue
        fin_box = next(iter(boxes))
        fin_corner = [c for c in (a, b) if _box(_cell(b1, c, orientation)) == fin_box]
        if not fin_corner:
            continue
        if all(
            _candidate(state, move.cell, digit)
            and _coordinate(move.cell, orientation)[0] not in (b0, b1)
            and _coordinate(move.cell, orientation)[1] in fin_corner
            and _box(move.cell) == fin_box
            for move in effects
        ):
            return
    raise ValueError("Finned X-Wing elimination is not justified")


def verify_general_finned_fish(
    state: CandidateState, deduction: Deduction, *, name: str, size: int
) -> None:
    """Validate any single-fin-line/single-box fish fitting the supplied witness.

    Cover combinations are reconstructed *only for the supplied base lines*;
    this does not invoke the pattern detector or search other base-line sets.
    """
    cells, digit, effects = _shape(deduction, name)
    evidence = set(cells)
    for orientation in ("row", "column"):
        bases = {_coordinate(cell, orientation)[0] for cell in cells}
        if len(bases) != size:
            continue
        if any(_line_has_digit(state, b, orientation, digit) for b in bases):
            continue
        positions = {b: _positions(state, b, orientation, digit) for b in bases}
        if any(not cs for cs in positions.values()):
            continue
        actual = {_cell(b, c, orientation) for b, cs in positions.items() for c in cs}
        if evidence != actual:
            continue
        # An elimination must be outside all fish base lines.
        if any(_coordinate(move.cell, orientation)[0] in bases
               or not _candidate(state, move.cell, digit) for move in effects):
            continue
        target_covers = {_coordinate(move.cell, orientation)[1] for move in effects}
        if len(target_covers) > size:
            continue
        for rest in combinations(sorted(set(range(9)) - target_covers), size - len(target_covers)):
            covers = target_covers | set(rest)
            fins = [_cell(b, c, orientation) for b in bases for c in positions[b] - covers]
            if not fins or len({_box(fin) for fin in fins}) != 1:
                continue
            if len({_coordinate(fin, orientation)[0] for fin in fins}) != 1:
                continue
            if any(not (positions[b] & covers) for b in bases):
                continue
            if all(
                _coordinate(move.cell, orientation)[1] in covers
                and all(_sees(move.cell, fin) for fin in fins)
                for move in effects
            ):
                return
    raise ValueError("Finned fish elimination is not justified")
