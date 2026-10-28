"""Generalized basic fish detection, proof verification, and integration."""
from dataclasses import replace

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Premise
from sudoku.solvers.logical.fish import BasicFish, XWing, Swordfish, Jellyfish
from sudoku.solvers.logical.solver import LogicalSolver, SolveStatus
from sudoku.solvers.logical.verification import DeductionVerifier


def fish_state(size: int, orientation: str = "row") -> CandidateState:
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    bases = tuple(range(0, size * 2, 2))
    covers = tuple(range(0, size * 2, 2))
    for base in bases:
        for other in range(9):
            if other not in covers:
                cell = (base, other) if orientation == "row" else (other, base)
                state.eliminate(*cell, 1)
    return state


@pytest.mark.parametrize("size,cls", [(2, XWing), (3, Swordfish), (4, Jellyfish)])
@pytest.mark.parametrize("orientation", ["row", "column"])
def test_fish_discovery_and_verification(size, cls, orientation):
    state = fish_state(size, orientation)
    before = state.copy()
    technique = cls()
    deductions = technique.find_deductions(state)
    assert deductions
    assert deductions == technique.find_deductions(state)
    for deduction in deductions:
        DeductionVerifier.verify(state, technique, deduction)
    assert state.board.to_string() == before.board.to_string()
    assert all(state.candidates_at(r, c) == before.candidates_at(r, c)
               for r in range(9) for c in range(9))
    result = LogicalSolver([technique]).solve(state, max_steps=1)
    assert result.status == SolveStatus.STEP_LIMIT
    assert len(result.steps) == 1
    assert result.steps[0].deduction.eliminations
    assert all(e.digit not in result.state.candidates_at(*e.cell)
               for e in result.steps[0].deduction.eliminations)


@pytest.mark.parametrize("bad_size", [0, 1, 5, True, 2.0])
def test_invalid_size(bad_size):
    with pytest.raises(ValueError):
        BasicFish(bad_size)


def test_forged_effect_rejected():
    state = fish_state(2)
    good = XWing().find_first(state)
    bad = replace(good, eliminations=(Elimination((4, 4), 1),))
    with pytest.raises(ValueError, match="not justified"):
        DeductionVerifier.verify(state, XWing(), bad)


def test_forged_premise_rejected():
    state = fish_state(2)
    good = XWing().find_first(state)
    bad = replace(good, premises=(Premise("Wrong pattern", ((1, 1),), frozenset({1})),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, XWing(), bad)


def test_no_effect_no_deduction():
    # Completed rows/columns outside the base pattern can remove possible eliminations;
    # a fully solved puzzle must not create fish deductions.
    solved = (
        "534678912672195348198342567859761423426853791713924856"
        "961537284287419635345286179"
    )
    state = CandidateState(SudokuBoard.from_string(solved))
    assert not XWing().find_deductions(state)
    assert not Swordfish().find_deductions(state)
    assert not Jellyfish().find_deductions(state)


def test_supported_and_registered():
    assert all(DeductionVerifier.supports(x) for x in (XWing(), Swordfish(), Jellyfish()))
    names = [t.name for t in LogicalSolver().techniques]
    assert names[10:13] == ["X-Wing", "Swordfish", "Jellyfish"]
