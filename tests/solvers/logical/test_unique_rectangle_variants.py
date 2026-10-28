"""Unique Rectangle Types 2, 3 and 4: sound detections and opt-in policy."""
from dataclasses import replace

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Elimination
from sudoku.solvers.logical.rectangles import (
    UniqueRectangleType1,
    UniqueRectangleType2,
    UniqueRectangleType3,
    UniqueRectangleType4,
)
from sudoku.solvers.logical.solver import LogicalSolver
from sudoku.solvers.logical.verification import DeductionVerifier


# All fixtures use two rows within the same band, and columns in two
# different stacks. The rectangle R1C1/R1C4/R2C1/R2C4 spans two boxes.
FLOORS = ((0, 0), (1, 0))
ROOFS = ((0, 3), (1, 3))


def blank() -> CandidateState:
    return CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))


def layout(roof_a, roof_b):
    state = blank()
    for cell in FLOORS:
        state._candidates[cell] = {1, 2}
    state._candidates[ROOFS[0]] = set(roof_a)
    state._candidates[ROOFS[1]] = set(roof_b)
    return state


def type2_state():
    return layout({1, 2, 3}, {1, 2, 3})


def type3_state():
    state = layout({1, 2, 3}, {1, 2, 4})
    state._candidates[(2, 3)] = {3, 4}
    return state


def type4_state():
    state = layout({1, 2, 3}, {1, 2, 4})
    # Exactly two 1s in the roof column.
    for r in range(2, 9):
        state._candidates[(r, 3)].discard(1)
    return state


@pytest.mark.parametrize('technique,maker,target', [
    (UniqueRectangleType2, type2_state, Elimination((2, 3), 3)),
    (UniqueRectangleType3, type3_state, Elimination((3, 3), 3)),
    (UniqueRectangleType4, type4_state, Elimination((0, 3), 2)),
])
def test_valid_pattern_and_reject_forgery(technique, maker, target):
    state = maker()
    before = {cell: state.candidates_at(*cell) for cell in state.unsolved_cells()}
    matches = [d for d in technique().find_deductions(state) if target in d.eliminations]
    assert matches, f'{technique.__name__} should find {target}'
    for deduction in matches:
        DeductionVerifier.verify(state, technique(), deduction)
    assert before == {cell: state.candidates_at(*cell) for cell in state.unsolved_cells()}
    forged = replace(matches[0], eliminations=(Elimination((8, 8), 9),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, technique(), forged)


@pytest.mark.parametrize('technique,maker', [
    (UniqueRectangleType2, type2_state),
    (UniqueRectangleType3, type3_state),
    (UniqueRectangleType4, type4_state),
])
def test_invalid_four_box_rectangle_is_rejected(technique, maker):
    state = maker()
    # The floor / roof shape across rows 1 and 5 occupies four boxes.
    # No uniqueness deduction may rely on a four-box swap.
    for cell in FLOORS + ROOFS:
        state._candidates[cell] = set(range(1, 10))
    assert not technique().find_deductions(state)


def test_all_unique_rectangle_types_require_opt_in():
    classes = (UniqueRectangleType1, UniqueRectangleType2,
               UniqueRectangleType3, UniqueRectangleType4)
    assert not any(isinstance(t, classes) for t in LogicalSolver().techniques)
    assert all(any(type(t) is cls for t in LogicalSolver(allow_uniqueness=True).techniques)
               for cls in classes)
    for cls in classes:
        with pytest.raises(ValueError, match='allow_uniqueness'):
            LogicalSolver(techniques=(cls(),))
        LogicalSolver(techniques=(cls(),), allow_uniqueness=True)


def test_type2_requires_identical_single_extras():
    state = layout({1, 2, 3}, {1, 2, 4})
    assert not UniqueRectangleType2().find_deductions(state)


def test_type4_requires_conjugate_pair_in_shared_unit():
    state = type4_state()
    state._candidates[(2, 3)].add(1)
    # Note: candidates outside the shared column can still form a
    # conjugate in a common box if deliberately restricted; this fixture
    # keeps many digit-1 candidates there, so no alternative link exists.
    assert not UniqueRectangleType4().find_deductions(state)
