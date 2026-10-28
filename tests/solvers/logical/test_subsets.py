"""Naked/Hidden Pair discovery, verification, and solver integration."""

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Premise
from sudoku.solvers.logical.subsets import HiddenPair, NakedPair
from sudoku.solvers.logical.solver import LogicalSolver, SolveStatus
from sudoku.solvers.logical.verification import DeductionVerifier


def blank():
    return CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))


def naked_state():
    state = blank()
    for col in (0, 1):
        for digit in range(3, 10):
            state.eliminate(0, col, digit)
    return state


def hidden_state():
    state = blank()
    for col in range(2, 9):
        for digit in (1, 2):
            state.eliminate(0, col, digit)
    return state


@pytest.mark.parametrize('technique,factory', [(NakedPair(), naked_state), (HiddenPair(), hidden_state)])
def test_detect_and_verify_without_mutation(technique, factory):
    state = factory()
    before = state.copy()
    deductions = technique.find_deductions(state)
    assert deductions
    assert all(d.technique == technique.name for d in deductions)
    for deduction in deductions:
        DeductionVerifier.verify(state, technique, deduction)
    assert state.board.to_string() == before.board.to_string()
    assert all(state.candidates_at(r, c) == before.candidates_at(r, c) for r in range(9) for c in range(9))
    assert technique.find_deductions(state) == deductions


def test_naked_pair_effects_are_only_peers():
    d = next(d for d in NakedPair().find_deductions(naked_state()) if d.premises[0].cells == ((0, 0), (0, 1)))
    assert Elimination((0, 2), 1) in d.eliminations
    assert Elimination((0, 2), 2) in d.eliminations
    assert all(e.cell not in ((0, 0), (0, 1)) for e in d.eliminations)
    assert all(e.digit in {1, 2} for e in d.eliminations)


def test_hidden_pair_restricts_both_cells():
    d = next(d for d in HiddenPair().find_deductions(hidden_state()) if d.premises[0].cells == ((0, 0), (0, 1)))
    assert Elimination((0, 0), 3) in d.eliminations
    assert Elimination((0, 1), 9) in d.eliminations
    assert all(e.cell in ((0, 0), (0, 1)) for e in d.eliminations)
    assert all(e.digit not in {1, 2} for e in d.eliminations)


@pytest.mark.parametrize('technique,factory', [(NakedPair(), naked_state), (HiddenPair(), hidden_state)])
def test_solver_applies_one_pair_step(technique, factory):
    state = factory()
    result = LogicalSolver((technique,)).solve(state, max_steps=1)
    assert result.status is SolveStatus.STEP_LIMIT
    assert len(result.steps) == 1
    assert result.steps[0].deduction.eliminations
    assert state.candidates_at(0, 2) == (frozenset(range(1, 10)) if isinstance(technique, NakedPair) else frozenset(range(3, 10)))


def test_reject_forged_effect_for_naked_pair():
    state = naked_state()
    bogus = Deduction(
        technique='Naked Pair',
        premises=(Premise('naked pair', ((0, 0), (0, 1)), frozenset({1, 2})),),
        eliminations=(Elimination((4, 4), 1),),
    )
    with pytest.raises(ValueError, match='not justified'):
        DeductionVerifier.verify(state, NakedPair(), bogus)


def test_reject_forged_premise_for_hidden_pair():
    state = blank()
    bogus = Deduction(
        technique='Hidden Pair',
        premises=(Premise('hidden pair', ((0, 0), (0, 1)), frozenset({1, 2})),),
        eliminations=(Elimination((0, 0), 3),),
    )
    with pytest.raises(ValueError, match='Invalid pair'):
        DeductionVerifier.verify(state, HiddenPair(), bogus)


def test_no_pairs_on_blank_grid():
    state = blank()
    assert NakedPair().find_deductions(state) == ()
    assert HiddenPair().find_deductions(state) == ()
