"""XY-Chain regression tests: deductions, proof verification, and integration."""

from dataclasses import replace

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Elimination, Placement, Premise
from sudoku.solvers.logical.solver import LogicalSolver, SolveStatus
from sudoku.solvers.logical.verification import DeductionVerifier
from sudoku.solvers.logical.xy_chains import XYChain, _xy_chain_patterns


FOUR = ((0, 0), (0, 4), (3, 4), (3, 0))
FOUR_PAIRS = ((1, 2), (2, 3), (3, 4), (4, 1))
FIVE = ((0, 0), (0, 4), (3, 4), (3, 7), (6, 7))
FIVE_PAIRS = ((1, 2), (2, 3), (3, 4), (4, 5), (5, 1))
SIX = ((0, 0), (0, 4), (3, 4), (3, 7), (6, 7), (6, 0))
SIX_PAIRS = ((1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 1))
EIGHT = ((0, 0), (0, 4), (3, 4), (3, 7),
         (6, 7), (6, 2), (4, 2), (4, 0))
EIGHT_PAIRS = ((1, 2), (2, 3), (3, 4), (4, 5),
               (5, 6), (6, 7), (7, 8), (8, 1))
THREE = ((0, 0), (0, 4), (3, 4))
THREE_PAIRS = ((1, 2), (2, 3), (3, 1))


def make_state(cells=FOUR, pairs=FOUR_PAIRS):
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    for (r, c), allowed in zip(cells, pairs, strict=True):
        for digit in range(1, 10):
            if digit not in allowed:
                state.eliminate(r, c, digit)
    return state


def snapshot(state):
    return (state.board.to_string(), tuple(
        (cell, state.candidates_at(*cell)) for cell in state.unsolved_cells()
    ))


def find_witness(state, cells, *, min_cells=4, max_cells=8):
    technique = XYChain(min_cells=min_cells, max_cells=max_cells)
    deduction = next(
        d for d in technique.find_deductions(state)
        if d.premises[0].digits == frozenset({1})
        and d.premises[0].cells in (cells, cells[::-1])
    )
    return technique, deduction


@pytest.mark.parametrize("cells,pairs,target", [
    (FOUR, FOUR_PAIRS, (1, 0)),
    (FIVE, FIVE_PAIRS, (6, 0)),
    (SIX, SIX_PAIRS, (4, 0)),
    (EIGHT, EIGHT_PAIRS, (2, 0)),
])
def test_multidigit_chain_discovery_and_verification(cells, pairs, target):
    state = make_state(cells, pairs)
    technique, d = find_witness(state, cells, max_cells=len(cells))
    assert d.technique == 'XY-Chain'
    assert d.placements == ()
    assert Elimination(target, 1) in d.eliminations
    assert all(e.digit == 1 and e.cell not in cells for e in d.eliminations)
    assert 'at least one endpoint' in d.premises[0].description
    DeductionVerifier.verify(state, technique, d)


def test_three_cell_xy_wing_only_when_enabled():
    state = make_state(THREE, THREE_PAIRS)
    assert not any(len(d.premises[0].cells) == 3 for d in XYChain().find_deductions(state))
    technique, deduction = find_witness(state, THREE, min_cells=3, max_cells=3)
    assert Elimination((3, 0), 1) in deduction.eliminations
    DeductionVerifier.verify(state, technique, deduction)


def test_search_limit_filters_longer_paths():
    state = make_state(FIVE, FIVE_PAIRS)
    assert not any(d.premises[0].cells in (FIVE, FIVE[::-1])
                   for d in XYChain(max_cells=4).find_deductions(state))
    _, d = find_witness(state, FIVE, max_cells=5)
    with pytest.raises(ValueError, match='witness'):
        DeductionVerifier.verify(state, XYChain(max_cells=4), d)


def test_determinism_all_deductions_verified_and_no_mutation():
    state = make_state(SIX, SIX_PAIRS)
    before = snapshot(state)
    technique = XYChain(max_cells=6)
    first = technique.find_deductions(state)
    assert first
    assert first == technique.find_deductions(state)
    assert snapshot(state) == before
    # Only one witness per unordered endpoint pair and target digit.
    keys = [(
        next(iter(d.premises[0].digits)),
        tuple(sorted((d.premises[0].cells[0], d.premises[0].cells[-1])))
    ) for d in first]
    assert len(keys) == len(set(keys))
    for deduction in first:
        DeductionVerifier.verify(state, technique, deduction)


def test_solver_executes_deduction_and_preserves_input():
    state = make_state()
    before = snapshot(state)
    solver = LogicalSolver((XYChain(max_cells=4),))
    result = solver.solve(state, max_steps=1)
    assert result.status is SolveStatus.STEP_LIMIT
    assert len(result.steps) == 1
    step = result.steps[0]
    assert step.deduction.eliminations
    assert snapshot(state) == before
    assert snapshot(step.before) == before
    for effect in step.deduction.eliminations:
        assert effect.digit not in step.after.candidates_at(*effect.cell)


def test_invalid_link_order_forgery_rejected():
    state = make_state()
    technique, good = find_witness(state, FOUR, max_cells=4)
    forged = replace(good, premises=(Premise(
        'wrong link order', (FOUR[0], FOUR[2], FOUR[1], FOUR[3]), frozenset({1})
    ),))
    with pytest.raises(ValueError, match='link'):
        DeductionVerifier.verify(state, technique, forged)


def test_no_shared_link_candidate_forgery_rejected():
    state = make_state()
    technique, good = find_witness(state, FOUR, max_cells=4)
    # Remove B's candidate 2: it becomes single, breaking the XY-Chain.
    state.eliminate(*FOUR[1], 2)
    with pytest.raises(ValueError, match='bivalue'):
        DeductionVerifier.verify(state, technique, good)


def test_wrong_endpoint_digit_forgery_rejected():
    state = make_state()
    technique, good = find_witness(state, FOUR, max_cells=4)
    wrong = replace(good, premises=(Premise(
        'wrong endpoint digit', FOUR, frozenset({2})
    ),))
    with pytest.raises(ValueError, match='endpoint'):
        DeductionVerifier.verify(state, technique, wrong)


def test_target_not_seeing_both_endpoints_rejected():
    state = make_state()
    technique, good = find_witness(state, FOUR, max_cells=4)
    forged = replace(good, eliminations=(Elimination((8, 8), 1),))
    with pytest.raises(ValueError, match='not justified'):
        DeductionVerifier.verify(state, technique, forged)


def test_chain_cell_target_rejected():
    state = make_state()
    technique, good = find_witness(state, FOUR, max_cells=4)
    forged = replace(good, eliminations=(Elimination(FOUR[0], 1),))
    with pytest.raises(ValueError, match='not justified'):
        DeductionVerifier.verify(state, technique, forged)


def test_stale_effect_rejected():
    state = make_state()
    technique, good = find_witness(state, FOUR, max_cells=4)
    effect = good.eliminations[0]
    state.eliminate(*effect.cell, effect.digit)
    with pytest.raises(ValueError, match='not justified'):
        DeductionVerifier.verify(state, technique, replace(good, eliminations=(effect,)))


def test_forged_placement_or_technique_rejected():
    state = make_state()
    technique, good = find_witness(state, FOUR, max_cells=4)
    with pytest.raises(ValueError, match='structure'):
        DeductionVerifier.verify(state, technique,
                                 replace(good, placements=(Placement((8, 8), 9),)))
    with pytest.raises(ValueError, match='structure'):
        DeductionVerifier.verify(state, technique,
                                 replace(good, technique='X-Chain'))


def test_repeated_witness_cells_not_allowed():
    with pytest.raises(ValueError, match='repeat'):
        Premise('bad path', (FOUR[0], FOUR[1], FOUR[0], FOUR[3]), frozenset({1}))


@pytest.mark.parametrize('kwargs', [
    {'max_cells': 2}, {'max_cells': 11}, {'max_cells': 3},
    {'max_cells': 8, 'min_cells': 2},
    {'max_cells': 5, 'min_cells': 6},
    {'max_cells': 8.0}, {'max_cells': True}, {'min_cells': False},
])
def test_rejects_invalid_bounds(kwargs):
    with pytest.raises(ValueError, match='require integers'):
        XYChain(**kwargs)


def test_reject_wrong_state_type():
    with pytest.raises(TypeError, match='CandidateState'):
        list(_xy_chain_patterns('not a state'))


def test_default_solver_registration_and_uniqueness_independence():
    assert 'XY-Chain' in [t.name for t in LogicalSolver().techniques]
    assert DeductionVerifier.supports(XYChain())
    assert not DeductionVerifier.supports(object())
