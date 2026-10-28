"""Tests for sound XY-Wing, XYZ-Wing and W-Wing candidate configurations."""
from dataclasses import replace

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Elimination, Premise
from sudoku.solvers.logical.solver import LogicalSolver, SolveStatus
from sudoku.solvers.logical.verification import DeductionVerifier
from sudoku.solvers.logical.wings import XYWing, XYZWing, WWing


def make_pattern(technique):
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    if technique is XYWing:
        # Pivot R2C2 {1,2}, wings R2C5 {1,3}, R5C2 {2,3}.
        # R5C5 sees both wings but not the pivot.
        assignments = {(1, 1): {1, 2}, (1, 4): {1, 3},
                       (4, 1): {2, 3}}
        target, digit = (4, 4), 3
    elif technique is XYZWing:
        # Pivot R2C2 {1,2,3}, wings R2C3 {1,3}, R3C2 {2,3}.
        # R3C3 sees all three via their shared box.
        assignments = {(1, 1): {1, 2, 3}, (1, 2): {1, 3},
                       (2, 1): {2, 3}}
        target, digit = (2, 2), 3
    else:
        # Wing cells R1C1 and R4C4 both {1,2}.
        # Digit 1 is conjugate in row 2 at C1 and C4.
        # R1C4 sees both wings; digit 2 can be removed.
        assignments = {(0, 0): {1, 2}, (3, 3): {1, 2}}
        for c in range(9):
            if c not in (0, 3):
                state.eliminate(1, c, 1)
        target, digit = (0, 3), 2
    # Synthetic candidate state; other cells retain all digits.
    for cell, candidates in assignments.items():
        state._candidates[cell] = candidates.copy()
    state._assert_consistent()
    return state, target, digit


@pytest.mark.parametrize('technique', [XYWing, XYZWing, WWing])
def test_discovery_validation_and_execution(technique):
    state, target, digit = make_pattern(technique)
    before = state.copy()
    solver_technique = technique()
    deductions = solver_technique.find_deductions(state)
    assert deductions
    assert Elimination(target, digit) in {e for d in deductions for e in d.eliminations}
    assert deductions == solver_technique.find_deductions(state)
    for deduction in deductions:
        DeductionVerifier.verify(state, solver_technique, deduction)
    assert all(state.candidates_at(r, c) == before.candidates_at(r, c)
               for r in range(9) for c in range(9))
    result = LogicalSolver([solver_technique]).solve(state, max_steps=1)
    assert result.status is SolveStatus.STEP_LIMIT
    assert len(result.steps) == 1
    for elimination in result.steps[0].deduction.eliminations:
        assert elimination.digit not in result.state.candidates_at(*elimination.cell)


@pytest.mark.parametrize('technique', [XYWing, XYZWing, WWing])
def test_reject_forged_effect(technique):
    state, _, digit = make_pattern(technique)
    good = technique().find_first(state)
    assert good is not None
    forged = replace(good, eliminations=(Elimination(good.premises[0].cells[0], digit),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, technique(), forged)


@pytest.mark.parametrize('technique', [XYWing, XYZWing, WWing])
def test_reject_forged_pattern(technique):
    state, _, _ = make_pattern(technique)
    good = technique().find_first(state)
    assert good is not None
    forged = replace(good, premises=(Premise('False pattern', ((8, 8),), frozenset({9})),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, technique(), forged)


def test_registered_and_solved_board_no_wings():
    assert [t.name for t in LogicalSolver().techniques][16:19] == [
        'XY-Wing', 'XYZ-Wing', 'W-Wing'
    ]
    solved = SudokuBoard.from_string(
        '534678912672195348198342567859761423426853791713924856'
        '961537284287419635345286179'
    )
    for technique in (XYWing(), XYZWing(), WWing()):
        assert DeductionVerifier.supports(technique)
        assert technique.find_deductions(CandidateState(solved)) == ()
