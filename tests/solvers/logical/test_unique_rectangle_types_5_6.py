"""Regression tests for uniqueness-based rectangle Types 5 and 6."""
from dataclasses import replace

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Elimination
from sudoku.solvers.logical.rectangles import UniqueRectangleType5, UniqueRectangleType6
from sudoku.solvers.logical.solver import LogicalSolver
from sudoku.solvers.logical.verification import DeductionVerifier


CORNERS = ((0, 0), (0, 3), (1, 0), (1, 3))


def new_state():
    return CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))


def type5_state():
    state = new_state()
    # Diagonal guardians R1C4 and R2C1: both contain the extra 3.
    for cell in ((0, 0), (1, 3)):
        state._candidates[cell] = {1, 2}
    for cell in ((0, 3), (1, 0)):
        state._candidates[cell] = {1, 2, 3}
    return state


def type6_state():
    state = new_state()
    # Diagonal floors R1C1 and R2C4, roofs R1C4 and R2C1.
    for cell in ((0, 0), (1, 3)):
        state._candidates[cell] = {1, 2}
    for cell in ((0, 3), (1, 0)):
        state._candidates[cell] = {1, 2, 3}
    # 1 occurs in the chosen two rows and two columns ONLY at their corners.
    for r in (0, 1):
        for c in range(9):
            if (r, c) not in CORNERS:
                state._candidates[(r, c)].discard(1)
    for c in (0, 3):
        for r in range(9):
            if (r, c) not in CORNERS:
                state._candidates[(r, c)].discard(1)
    return state


@pytest.mark.parametrize('technique,maker,target', [
    (UniqueRectangleType5, type5_state, Elimination((0, 1), 3)),
    (UniqueRectangleType6, type6_state, Elimination((0, 3), 1)),
])
def test_valid_deduction_verified_without_mutation(technique, maker, target):
    state = maker()
    before = {c: state.candidates_at(*c) for c in state.unsolved_cells()}
    deductions = [d for d in technique().find_deductions(state) if target in d.eliminations]
    assert deductions
    for d in deductions:
        DeductionVerifier.verify(state, technique(), d)
        forged = replace(d, eliminations=(Elimination((8, 8), 9),))
        with pytest.raises(ValueError):
            DeductionVerifier.verify(state, technique(), forged)
    assert before == {c: state.candidates_at(*c) for c in state.unsolved_cells()}


def test_type5_requires_common_guardian():
    state = type5_state()
    state._candidates[(1, 0)] = {1, 2, 4}
    assert not UniqueRectangleType5().find_deductions(state)


def test_type5_adjacent_roofs_not_recognized_as_type5():
    state = new_state()
    for cell in CORNERS:
        state._candidates[cell] = {1, 2}
    for cell in ((0, 0), (0, 3)):
        state._candidates[cell].add(3)
    assert not UniqueRectangleType5().find_deductions(state)


def test_type6_requires_confinement_in_rows_and_columns():
    state = type6_state()
    state._candidates[(0, 6)].add(1)
    assert not UniqueRectangleType6().find_deductions(state)
    state._candidates[(0, 6)].discard(1)
    state._candidates[(8, 0)].add(1)
    assert not UniqueRectangleType6().find_deductions(state)


def test_type6_requires_diagonal_bivalue_floors():
    state = type6_state()
    state._candidates[(0, 0)].add(4)
    assert not UniqueRectangleType6().find_deductions(state)


@pytest.mark.parametrize('cls', [UniqueRectangleType5, UniqueRectangleType6])
def test_techniques_require_opt_in(cls):
    assert not any(isinstance(t, cls) for t in LogicalSolver().techniques)
    assert any(isinstance(t, cls) for t in LogicalSolver(allow_uniqueness=True).techniques)
    with pytest.raises(ValueError, match='allow_uniqueness'):
        LogicalSolver(techniques=(cls(),))
    LogicalSolver(techniques=(cls(),), allow_uniqueness=True)
