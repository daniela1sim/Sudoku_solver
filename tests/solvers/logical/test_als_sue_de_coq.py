"""ALS-XZ and Sue de Coq: discovery, mathematical proofs and integration."""

from dataclasses import replace

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Elimination, Premise
from sudoku.solvers.logical.als import ALSXZ, find_almost_locked_sets, is_als
from sudoku.solvers.logical.sue_de_coq import SueDeCoq
from sudoku.solvers.logical.solver import LogicalSolver, SolveStatus
from sudoku.solvers.logical.verification import DeductionVerifier


def restricted_state(cells, board=None):
    if board is None:
        board = SudokuBoard([[0] * 9 for _ in range(9)])
    state = CandidateState(board)
    for (r, c), allowed in cells.items():
        for digit in sorted(set(range(1, 10)) - set(allowed)):
            state.eliminate(r, c, digit)
    return state


def snapshot(state):
    return state.board.to_string(), tuple(
        (cell, state.candidates_at(*cell)) for cell in state.unsolved_cells()
    )


def als_state(transpose=False):
    cells = {(0, 0): {1, 2}, (1, 0): {1, 2, 3}, (1, 1): {2, 3}}
    return restricted_state({(c, r) if transpose else (r, c): values
                             for (r, c), values in cells.items()})


def sue_state(transpose=False):
    cells = {
        (0, 0): {1, 2, 5},
        (0, 1): {2, 3, 5},
        (0, 2): {3, 4, 5},
        (0, 3): {1, 2},
        (1, 0): {3, 4},
    }
    return restricted_state({(c, r) if transpose else (r, c): values
                             for (r, c), values in cells.items()})


def matching_als(state, *, transpose=False):
    a, b = ((0, 0),), ((1, 0), (1, 1))
    if transpose:
        a, b = tuple((c, r) for r, c in a), tuple((c, r) for r, c in b)
    return next(d for d in ALSXZ().find_deductions(state)
                if d.premises[0].cells == a and d.premises[1].cells == b
                and d.premises[2].digits == frozenset({1}))


def matching_sue(state, *, transpose=False):
    cross = ((0, 0), (0, 1), (0, 2))
    if transpose:
        cross = tuple((c, r) for r, c in cross)
    return next(d for d in SueDeCoq().find_deductions(state)
                if d.premises[0].cells == cross)


@pytest.mark.parametrize('transpose', [False, True])
def test_als_xz_discovery_and_all_witnesses_verified(transpose):
    state = als_state(transpose)
    before = snapshot(state)
    tech = ALSXZ()
    results = tech.find_deductions(state)
    assert results and results == tech.find_deductions(state)
    good = matching_als(state, transpose=transpose)
    target = (0, 2) if transpose else (2, 0)
    assert Elimination(target, 2) in good.eliminations
    assert len(good.premises) == 3
    assert good.placements == ()
    assert all(d.technique == 'ALS-XZ' for d in results)
    for deduction in results:
        DeductionVerifier.verify(state, tech, deduction)
    assert snapshot(state) == before


def test_als_enumerator_recognizes_bivalue_and_multi_cell_groups():
    state = als_state()
    sets = find_almost_locked_sets(state, max_size=3)
    assert any(group.cells == ((0, 0),) and group.digits == {1, 2} for group in sets)
    assert any(group.cells == ((1, 0), (1, 1))
               and group.digits == {1, 2, 3} for group in sets)
    assert len({group.cells for group in sets}) == len(sets)
    assert is_als(state, ((1, 0), (1, 1)))
    assert not is_als(state, ((0, 0), (4, 4)))


def test_als_xz_requires_restricted_common_candidate():
    state = restricted_state({(0, 0): {1, 2}, (4, 4): {1, 2}})
    assert not ALSXZ().find_deductions(state)


def test_als_xz_rejects_wrong_effect_and_forged_rcc():
    state = als_state()
    good = matching_als(state)
    tech = ALSXZ()
    wrong_target = replace(good, eliminations=(Elimination((4, 4), 2),))
    with pytest.raises(ValueError, match='not justified'):
        DeductionVerifier.verify(state, tech, wrong_target)
    altered_link = replace(good, premises=(*good.premises[:2], Premise(
        'Forged RCC', ((0, 0), (1, 1)), frozenset({1})
    )))
    with pytest.raises(ValueError, match='restricted common'):
        DeductionVerifier.verify(state, tech, altered_link)
    reversed_digits = replace(good, eliminations=(Elimination((2, 0), 1),))
    with pytest.raises(ValueError, match='RCC'):
        DeductionVerifier.verify(state, tech, reversed_digits)


def test_als_xz_rejects_wrong_group_and_stale_state():
    state = als_state()
    tech = ALSXZ()
    good = matching_als(state)
    forged = replace(good, premises=(
        replace(good.premises[0], cells=((0, 0), (4, 4))),
        *good.premises[1:],
    ))
    with pytest.raises(ValueError, match='ALS'):
        DeductionVerifier.verify(state, tech, forged)
    state.eliminate(1, 0, 1)
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, tech, good)


@pytest.mark.parametrize('transpose', [False, True])
def test_sue_discovery_and_complete_verification(transpose):
    state = sue_state(transpose)
    before = snapshot(state)
    tech = SueDeCoq()
    deductions = tech.find_deductions(state)
    assert deductions and deductions == tech.find_deductions(state)
    d = matching_sue(state, transpose=transpose)
    assert d.premises[1].digits == {1, 2}
    assert d.premises[2].digits == {3, 4}
    # Line-sector eliminations: digits 1,2 plus intersection-only digit 5.
    line_target = (4, 0) if transpose else (0, 4)
    assert {Elimination(line_target, digit) for digit in (1, 2, 5)} <= set(d.eliminations)
    # Box-sector eliminations: digits 3,4 plus digit 5.
    box_target = (1, 1)
    assert {Elimination(box_target, digit) for digit in (3, 4, 5)} <= set(d.eliminations)
    for deduction in deductions:
        DeductionVerifier.verify(state, tech, deduction)
    assert snapshot(state) == before


def test_sue_two_intersection_cells_four_candidates():
    grid = [[0] * 9 for _ in range(9)]
    grid[0][2] = 9  # The third box/row intersection cell is filled.
    state = restricted_state({
        (0, 0): {1, 3}, (0, 1): {2, 4},
        (0, 3): {1, 2}, (1, 0): {3, 4},
    }, SudokuBoard(grid))
    tech = SueDeCoq()
    deduction = next(d for d in tech.find_deductions(state)
                     if d.premises[0].cells == ((0, 0), (0, 1)))
    assert deduction.premises[0].digits == {1, 2, 3, 4}
    DeductionVerifier.verify(state, tech, deduction)


def test_sue_multicell_line_als_and_max_size():
    state = restricted_state({
        (0, 0): {1, 2, 6}, (0, 1): {2, 3, 6}, (0, 2): {4, 5, 6},
        (0, 3): {1, 2}, (0, 4): {2, 3}, (1, 0): {4, 5},
    })
    assert not SueDeCoq(max_side_size=1).find_deductions(state)
    tech = SueDeCoq(max_side_size=2)
    deduction = next(d for d in tech.find_deductions(state)
                     if d.premises[1].cells == ((0, 3), (0, 4)))
    assert deduction.premises[0].digits == {1, 2, 3, 4, 5, 6}
    DeductionVerifier.verify(state, tech, deduction)


def test_sue_rejects_wrong_target_and_wrong_digit():
    state = sue_state()
    tech = SueDeCoq()
    d = matching_sue(state)
    with pytest.raises(ValueError, match='not justified'):
        DeductionVerifier.verify(state, tech,
                                 replace(d, eliminations=(Elimination((4, 4), 1),)))
    with pytest.raises(ValueError, match='not justified'):
        DeductionVerifier.verify(state, tech,
                                 replace(d, eliminations=(Elimination((0, 4), 3),)))
    with pytest.raises(ValueError, match='not justified'):
        DeductionVerifier.verify(state, tech,
                                 replace(d, eliminations=(Elimination((0, 0), 1),)))


def test_sue_rejects_overlapping_side_candidates_and_stale_state():
    state = sue_state()
    tech = SueDeCoq()
    d = matching_sue(state)
    forged = replace(d, premises=(
        d.premises[0],
        replace(d.premises[1], digits=frozenset({3, 4})),
        d.premises[2],
    ))
    with pytest.raises(ValueError, match='partition'):
        DeductionVerifier.verify(state, tech, forged)
    state.eliminate(0, 3, 1)  # The line-side cell is no longer an ALS.
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, tech, d)


@pytest.mark.parametrize('factory,technique', [
    (als_state, ALSXZ), (sue_state, SueDeCoq),
])
def test_solver_step_and_state_isolation(factory, technique):
    state = factory()
    before = snapshot(state)
    solver = LogicalSolver((technique(),))
    result = solver.solve(state, max_steps=1)
    assert result.status is SolveStatus.STEP_LIMIT
    assert len(result.steps) == 1
    assert snapshot(state) == before
    assert snapshot(result.steps[0].before) == before
    for effect in result.steps[0].deduction.eliminations:
        assert effect.digit not in result.state.candidates_at(*effect.cell)


@pytest.mark.parametrize('cls', [ALSXZ, SueDeCoq])
@pytest.mark.parametrize('bad_size', [0, -1, 5, True, 1.5])
def test_invalid_sizes(cls, bad_size):
    with pytest.raises(ValueError):
        cls(bad_size)


def test_invalid_input_and_default_registration():
    for cls in (ALSXZ, SueDeCoq):
        with pytest.raises(TypeError, match='CandidateState'):
            cls().find_deductions(None)
        assert DeductionVerifier.supports(cls())
    names = [tech.name for tech in LogicalSolver().techniques]
    assert names[-6:] == ['ALS-XZ', 'Sue de Coq', 'ALS-Chain', 'AIC', 'Grouped AIC', 'ALS-AIC']


def test_larger_search_configuration_returns_valid_witnesses():
    state = als_state()
    for deduction in ALSXZ(max_size=4).find_deductions(state):
        DeductionVerifier.verify(state, ALSXZ(max_size=4), deduction)
    state = sue_state()
    for deduction in SueDeCoq(max_side_size=4).find_deductions(state):
        DeductionVerifier.verify(state, SueDeCoq(max_side_size=4), deduction)
