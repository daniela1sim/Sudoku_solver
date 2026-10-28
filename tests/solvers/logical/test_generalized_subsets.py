"""Generalized subset discovery and independent proof verification."""
import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Premise
from sudoku.solvers.logical.subsets import (
    NakedSubset, HiddenSubset, NakedPair, HiddenPair,
    NakedTriple, HiddenTriple, NakedQuad, HiddenQuad,
)
from sudoku.solvers.logical.solver import LogicalSolver, SolveStatus
from sudoku.solvers.logical.verification import DeductionVerifier


def empty():
    return CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))


def naked(size):
    state = empty()
    # Every one of the n cells has all n digits; each other cell keeps 1..9.
    for col in range(size):
        for digit in range(size + 1, 10):
            state.eliminate(0, col, digit)
    return state


def hidden(size):
    state = empty()
    for col in range(size, 9):
        for digit in range(1, size + 1):
            state.eliminate(0, col, digit)
    return state


@pytest.mark.parametrize('size', [2, 3, 4])
@pytest.mark.parametrize('family,factory', [(NakedSubset, naked), (HiddenSubset, hidden)])
def test_discover_verify_and_solve(family, factory, size):
    state = factory(size)
    before = state.copy()
    technique = family(size)
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


@pytest.mark.parametrize('cls,size', [
    (NakedPair, 2), (HiddenPair, 2), (NakedTriple, 3),
    (HiddenTriple, 3), (NakedQuad, 4), (HiddenQuad, 4),
])
def test_wrappers(cls, size):
    instance = cls()
    assert instance.size == size
    assert DeductionVerifier.supports(instance)


@pytest.mark.parametrize('cls', [NakedSubset, HiddenSubset])
@pytest.mark.parametrize('size', [0, 1, 5, True, 2.0])
def test_reject_unsupported_sizes(cls, size):
    with pytest.raises(ValueError):
        cls(size)


def test_naked_triple_nonidentical_candidates():
    state = empty()
    for col, allowed in enumerate(({1, 2}, {1, 3}, {2, 3})):
        for digit in set(range(1, 10)) - allowed:
            state.eliminate(0, col, digit)
    deductions = NakedTriple().find_deductions(state)
    assert any(d.premises[0].cells == ((0, 0), (0, 1), (0, 2)) for d in deductions)
    for d in deductions:
        DeductionVerifier.verify(state, NakedTriple(), d)


def test_reject_forged_subset_effect():
    state = naked(3)
    forged = Deduction(
        'Naked Triple',
        (Premise('Triple', ((0, 0), (0, 1), (0, 2)), frozenset({1, 2, 3})),),
        eliminations=(Elimination((4, 4), 1),),
    )
    with pytest.raises(ValueError, match='not justified'):
        DeductionVerifier.verify(state, NakedTriple(), forged)


def test_default_solver_registers_twenty_one_techniques():
    assert [t.name for t in LogicalSolver().techniques] == [
        'Naked Single', 'Hidden Single', 'Pointing', 'Claiming', 'Naked Pair', 'Hidden Pair',
        'Naked Triple', 'Hidden Triple', 'Naked Quad', 'Hidden Quad',
        'X-Wing', 'Swordfish', 'Jellyfish', 'Skyscraper', '2-String Kite', 'Crane',
        'XY-Wing', 'XYZ-Wing', 'W-Wing', 'Empty Rectangle', 'Finned X-Wing', 'Finned Swordfish', 'Finned Jellyfish', 'Simple Coloring', 'Remote Pairs', 'X-Chain', 'XY-Chain', 'ALS-XZ', 'Sue de Coq', 'ALS-Chain', 'AIC', 'Grouped AIC', 'ALS-AIC',
    ]
