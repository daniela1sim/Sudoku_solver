"""ALS-Chains: real RCC witnesses, inference, validation, and integration."""

from dataclasses import replace
from itertools import product

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Elimination, Premise
from sudoku.solvers.logical.als_chains import ALSChain
from sudoku.solvers.logical.solver import LogicalSolver, SolveStatus
from sudoku.solvers.logical.strong_links import _sees
from sudoku.solvers.logical.verification import DeductionVerifier


THREE = {
    (0, 0): {1, 4},
    (0, 3): {1, 2},
    (1, 3): {2, 5},
    (2, 3): {2, 4},
}
FOUR = {
    (0, 0): {1, 6},
    (0, 3): {1, 2},
    (1, 3): {2, 5},
    (2, 3): {2, 7},
    (2, 4): {3, 7},
    (3, 4): {3, 6},
}


def make_state(cells, transpose=False):
    board = SudokuBoard([[0] * 9 for _ in range(9)])
    state = CandidateState(board)
    for (r, c), allowed in cells.items():
        if transpose:
            r, c = c, r
        for digit in range(1, 10):
            if digit not in allowed:
                state.eliminate(r, c, digit)
    return state


def fingerprint(state):
    return state.board.to_string(), tuple(
        (cell, state.candidates_at(*cell)) for cell in state.unsolved_cells()
    )


def target(case, transpose=False):
    cell, digit = ((2, 0), 4) if case == 3 else ((3, 0), 6)
    if transpose:
        cell = cell[::-1]
    return Elimination(cell, digit)


def find_relevant(state, case, transpose=False):
    technique = ALSChain(max_sets=case)
    expected = target(case, transpose)
    deductions = technique.find_deductions(state)
    result = next(d for d in deductions if expected in d.eliminations)
    return technique, result


@pytest.mark.parametrize('case,cells', [(3, THREE), (4, FOUR)])
@pytest.mark.parametrize('transpose', [False, True])
def test_discovery_and_verification(case, cells, transpose):
    state = make_state(cells, transpose)
    before = fingerprint(state)
    technique, step = find_relevant(state, case, transpose)
    assert len(step.premises) == 2 * case
    assert len(step.premises[1:-1:2]) == case - 1
    assert step.placements == ()
    assert technique.find_deductions(state) == technique.find_deductions(state)
    assert target(case, transpose) in step.eliminations
    assert DeductionVerifier.supports(technique)
    for deduction in technique.find_deductions(state):
        DeductionVerifier.verify(state, technique, deduction)
    assert fingerprint(state) == before


@pytest.mark.parametrize('cells,case,z', [(THREE, 3, 4), (FOUR, 4, 6)])
def test_chain_terminal_inference_by_independent_assignment_enumeration(cells, case, z):
    """Brute force just the example ALS cells and their pairwise conflicts."""
    keys = tuple(cells)
    satisfying = 0
    first = (0, 0)
    last = (2, 3) if case == 3 else (3, 4)
    for assignment in product(*(sorted(cells[cell]) for cell in keys)):
        values = dict(zip(keys, assignment))
        if any(_sees(a, b) and values[a] == values[b]
               for i, a in enumerate(keys) for b in keys[i + 1:]):
            continue
        satisfying += 1
        assert values[first] == z or values[last] == z
    assert satisfying > 0  # Avoid a vacuous proof.


def test_solver_one_step_removes_verified_candidate():
    state = make_state(THREE)
    before = fingerprint(state)
    solver = LogicalSolver(techniques=(ALSChain(max_sets=3),))
    result = solver.solve(state, max_steps=1)
    assert result.status == SolveStatus.STEP_LIMIT
    assert len(result.steps) == 1
    assert result.steps[0].deduction.technique == 'ALS-Chain'
    assert target(3) in result.steps[0].deduction.eliminations
    assert 4 not in result.state.candidates_at(2, 0)
    assert 4 in state.candidates_at(2, 0)
    assert fingerprint(state) == before
    assert fingerprint(result.steps[0].before) == before


def test_only_two_als_is_not_an_als_chain():
    # A two-ALS chain is ALS-XZ, intentionally not handled here.
    state = make_state({(0, 0): {1, 4}, (0, 3): {1, 4}})
    # Other bivalue ALSs might be generated from two distinct cells, but
    # no possible three-member chain with two different RCCs is present.
    assert ALSChain().find_deductions(state) == ()


@pytest.mark.parametrize('kwargs', [
    {'max_als_size': 0}, {'max_als_size': 5}, {'max_als_size': True},
    {'max_sets': 2}, {'max_sets': 7}, {'max_sets': False},
    {'max_deductions': 0}, {'max_deductions': 1001},
    {'max_expansions': 0}, {'max_expansions': -1},
])
def test_reject_invalid_limits(kwargs):
    with pytest.raises(ValueError):
        ALSChain(**kwargs)


def test_invalid_input():
    with pytest.raises(TypeError, match='CandidateState'):
        ALSChain().find_deductions(None)


def test_search_budget_is_conservative():
    state = make_state(FOUR)
    assert ALSChain(max_sets=4, max_expansions=1).find_deductions(state) == ()
    assert len(ALSChain(max_sets=4, max_deductions=1).find_deductions(state)) <= 1


def test_no_uniqueness_requirement():
    assert 'ALS-Chain' in [t.name for t in LogicalSolver().techniques]
    assert DeductionVerifier.supports(ALSChain())


@pytest.mark.parametrize('modification', [
    'wrong_technique', 'bad_rcc_digit', 'bad_rcc_positions',
    'repeat_link', 'overlap', 'wrong_als_digits',
    'bad_terminal', 'wrong_target', 'absent_target', 'missing_premise',
])
def test_verifier_rejects_forged_deductions(modification):
    state = make_state(FOUR)
    technique, step = find_relevant(state, 4)
    premises = list(step.premises)
    if modification == 'wrong_technique':
        forged = replace(step, technique='ALS-XZ')
    elif modification == 'bad_rcc_digit':
        premises[1] = replace(premises[1], digits=frozenset({9}))
        forged = replace(step, premises=tuple(premises))
    elif modification == 'bad_rcc_positions':
        premises[1] = replace(premises[1], cells=((8, 8),))
        forged = replace(step, premises=tuple(premises))
    elif modification == 'repeat_link':
        premises[3] = replace(premises[3], digits=premises[1].digits)
        forged = replace(step, premises=tuple(premises))
    elif modification == 'overlap':
        premises[4] = replace(premises[4], cells=premises[0].cells,
                              digits=premises[0].digits)
        forged = replace(step, premises=tuple(premises))
    elif modification == 'wrong_als_digits':
        premises[0] = replace(premises[0], digits=frozenset({1, 8}))
        forged = replace(step, premises=tuple(premises))
    elif modification == 'bad_terminal':
        premises[-1] = replace(premises[-1], digits=frozenset({1}))
        forged = replace(step, premises=tuple(premises))
    elif modification == 'wrong_target':
        forged = replace(step, eliminations=(Elimination((7, 7), 6),))
    elif modification == 'absent_target':
        state.eliminate(*target(4).cell, target(4).digit)
        forged = step
    else:
        forged = replace(step, premises=tuple(premises[:-1]))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, technique, forged)


def test_subset_of_proven_eliminations_is_valid():
    state = make_state(FOUR)
    technique, step = find_relevant(state, 4)
    assert len(step.eliminations) >= 2
    smaller = replace(step, eliminations=(step.eliminations[0],))
    DeductionVerifier.verify(state, technique, smaller)


def test_forged_witness_is_rejected_even_with_unchanged_explanation():
    state = make_state(THREE)
    technique, deduction = find_relevant(state, 3)
    first = deduction.premises[0]
    # Descriptions don't authorize an incorrect candidate set.
    replacement = Premise(first.description, first.cells, frozenset({1, 8}))
    forged = replace(deduction, premises=(replacement, *deduction.premises[1:]))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, technique, forged)


def test_candidate_eliminations_preserve_known_completion_on_sampled_puzzles():
    """Property-style regression against a valid Sudoku completion.

    The puzzle states are created by removing clues from a completed grid.
    Any sound candidate deduction must preserve the known completion.
    """
    import random

    solution = (
        '534678912672195348198342567859761423426853791713924856'
        '961537284287419635345286179'
    )
    rng = random.Random(16)
    technique = ALSChain(max_sets=4)
    for sample in range(20):
        keep = 0.21 + 0.02 * (sample % 7)
        puzzle = ''.join(c if rng.random() < keep else '0' for c in solution)
        state = CandidateState(SudokuBoard.from_string(puzzle))
        for deduction in technique.find_deductions(state):
            DeductionVerifier.verify(state, technique, deduction)
            for effect in deduction.eliminations:
                row, col = effect.cell
                assert int(solution[9 * row + col]) != effect.digit
