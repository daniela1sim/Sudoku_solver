"""Short alternating strong-link chains, independent proof checks, integration."""
from dataclasses import replace

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Elimination, Premise
from sudoku.solvers.logical.strong_links import Skyscraper, TwoStringKite, Crane
from sudoku.solvers.logical.solver import LogicalSolver, SolveStatus
from sudoku.solvers.logical.verification import DeductionVerifier


def make_pattern(technique):
    """Build sound candidate states using only elimination of digit 1."""
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    if technique is Skyscraper:
        # R1: c1/c5; R4: c1/c6; target R2C6.
        for c in range(9):
            if c not in (0, 4):
                state.eliminate(0, c, 1)
            if c not in (0, 5):
                state.eliminate(3, c, 1)
        target = (1, 5)
    elif technique is TwoStringKite:
        # R1: c1/c5; C2: r2/r4; connect r1c1 to r2c2 in box 1.
        for c in range(9):
            if c not in (0, 4):
                state.eliminate(0, c, 1)
        for r in range(9):
            if r not in (1, 3):
                state.eliminate(r, 1, 1)
        target = (3, 4)
    else:
        # Box 1: r1c1/r2c2; R4: c2/c5; connect r2c2 to r4c2.
        for r in range(3):
            for c in range(3):
                if (r, c) not in ((0, 0), (1, 1)):
                    state.eliminate(r, c, 1)
        for c in range(9):
            if c not in (1, 4):
                state.eliminate(3, c, 1)
        target = (0, 4)
    return state, target


@pytest.mark.parametrize("technique", [Skyscraper, TwoStringKite, Crane])
def test_find_verify_and_apply(technique):
    state, target = make_pattern(technique)
    before = state.copy()
    solver_technique = technique()
    deductions = solver_technique.find_deductions(state)
    assert deductions
    assert any(Elimination(target, 1) in deduction.eliminations for deduction in deductions)
    assert deductions == solver_technique.find_deductions(state)
    for deduction in deductions:
        DeductionVerifier.verify(state, solver_technique, deduction)
    assert all(state.candidates_at(r, c) == before.candidates_at(r, c)
               for r in range(9) for c in range(9))
    result = LogicalSolver([solver_technique]).solve(state, max_steps=1)
    assert result.status is SolveStatus.STEP_LIMIT
    assert len(result.steps) == 1
    assert all(e.digit not in result.state.candidates_at(*e.cell)
               for e in result.steps[0].deduction.eliminations)


@pytest.mark.parametrize("technique", [Skyscraper, TwoStringKite, Crane])
def test_forged_elimination_rejected(technique):
    state, _ = make_pattern(technique)
    good = technique().find_first(state)
    assert good is not None
    # Claim elimination on a pattern cell, which is never a legal effect.
    forged = replace(good, eliminations=(Elimination(good.premises[0].cells[0], 1),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, technique(), forged)


@pytest.mark.parametrize("technique", [Skyscraper, TwoStringKite, Crane])
def test_forged_pattern_rejected(technique):
    state, _ = make_pattern(technique)
    good = technique().find_first(state)
    forged = replace(good, premises=(Premise("False pattern", ((1, 8), (2, 8), (3, 8), (4, 8)), frozenset({1})),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, technique(), forged)


def test_all_registered_and_fully_solved_state_has_none():
    assert [t.name for t in LogicalSolver().techniques][13:16] == [
        "Skyscraper", "2-String Kite", "Crane"
    ]
    solved = SudokuBoard.from_string(
        "534678912672195348198342567859761423426853791713924856"
        "961537284287419635345286179"
    )
    for technique in (Skyscraper(), TwoStringKite(), Crane()):
        assert DeductionVerifier.supports(technique)
        assert technique.find_deductions(CandidateState(solved)) == ()
