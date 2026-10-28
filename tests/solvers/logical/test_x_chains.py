"""X-Chain unit and integration tests, including independently checked links."""

from dataclasses import replace

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Elimination, Placement, Premise
from sudoku.solvers.logical.solver import LogicalSolver, SolveStatus
from sudoku.solvers.logical.verification import DeductionVerifier
from sudoku.solvers.logical.x_chains import XChain, _chain_graph


FOUR = ((0, 0), (0, 4), (1, 4), (1, 1))
SIX = ((0, 0), (0, 4), (1, 4), (1, 7), (4, 7), (4, 0))
EIGHT = ((0, 0), (0, 4), (1, 4), (1, 7),
         (4, 7), (4, 2), (5, 2), (5, 0))


def make_state(chain=FOUR, *, digit=1):
    """Only two candidate positions for digit in each chain's strong row."""
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    for index in range(0, len(chain), 2):
        a, b = chain[index:index + 2]
        assert a[0] == b[0]
        for col in range(9):
            if (a[0], col) not in (a, b):
                state.eliminate(a[0], col, digit)
    return state


def snapshot(state):
    return (state.board.to_string(),
            tuple((cell, state.candidates_at(*cell)) for cell in state.unsolved_cells()))


def find_chain(state, expected, *, max_links=7):
    return next(d for d in XChain(max_links=max_links).find_deductions(state)
                if d.premises[0].cells == expected)


def test_four_cell_chain_discovery_and_verification():
    state = make_state()
    deduction = find_chain(state, FOUR, max_links=3)
    assert deduction.technique == "X-Chain"
    assert deduction.premises[0].digits == frozenset({1})
    assert Elimination((2, 2), 1) in deduction.eliminations
    assert all(e.digit == 1 and e.cell not in FOUR for e in deduction.eliminations)
    assert "strong" in deduction.premises[0].description
    assert "weak" in deduction.premises[0].description
    DeductionVerifier.verify(state, XChain(max_links=3), deduction)


def test_six_cell_chain_requires_longer_bound():
    state = make_state(SIX)
    deduction = find_chain(state, SIX, max_links=5)
    assert Elimination((3, 0), 1) in deduction.eliminations
    assert all(d.premises[0].cells != SIX for d in XChain(max_links=3).find_deductions(state))
    DeductionVerifier.verify(state, XChain(max_links=5), deduction)


def test_eight_cell_chain_and_verification_bound():
    state = make_state(EIGHT)
    deduction = find_chain(state, EIGHT, max_links=7)
    assert Elimination((3, 0), 1) in deduction.eliminations
    DeductionVerifier.verify(state, XChain(max_links=7), deduction)
    with pytest.raises(ValueError, match="witness"):
        DeductionVerifier.verify(state, XChain(max_links=5), deduction)


def test_alternative_digit_and_transposition():
    state = make_state(FOUR, digit=8)
    deduction = find_chain(state, FOUR, max_links=3)
    assert deduction.premises[0].digits == frozenset({8})
    assert Elimination((2, 2), 8) in deduction.eliminations
    DeductionVerifier.verify(state, XChain(max_links=3), deduction)

    # Transpose the candidate pattern to strong columns rather than rows.
    transposed = tuple((c, r) for r, c in FOUR)
    tstate = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    for i in range(0, len(transposed), 2):
        a, b = transposed[i:i + 2]
        for row in range(9):
            if (row, a[1]) not in (a, b):
                tstate.eliminate(row, a[1], 8)
    td = find_chain(tstate, transposed, max_links=3)
    assert Elimination((2, 2), 8) in td.eliminations
    DeductionVerifier.verify(tstate, XChain(max_links=3), td)


def test_deterministic_discovery_without_state_mutation():
    state = make_state(SIX)
    before = snapshot(state)
    technique = XChain()
    first = technique.find_deductions(state)
    assert first and first == technique.find_deductions(state)
    assert snapshot(state) == before
    assert len({(d.premises[0].digits, d.premises[0].cells) for d in first}) == len(first)
    for deduction in first:
        DeductionVerifier.verify(state, technique, deduction)


def test_solver_executes_one_step_and_preserves_input():
    state = make_state()
    before = snapshot(state)
    result = LogicalSolver((XChain(max_links=3),)).solve(state, max_steps=1)
    assert result.status is SolveStatus.STEP_LIMIT
    assert len(result.steps) == 1
    assert result.steps[0].deduction.technique == "X-Chain"
    for e in result.steps[0].deduction.eliminations:
        assert e.digit not in result.state.candidates_at(*e.cell)
    assert snapshot(state) == before
    assert snapshot(result.steps[0].before) == before


def test_blank_board_has_no_strong_links_or_x_chains():
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    assert XChain().find_deductions(state) == ()
    assert all(not v for v in _chain_graph(state, 1)[0].values())


def test_rejects_broken_weak_link():
    state = make_state()
    good = find_chain(state, FOUR)
    forged = replace(good, premises=(Premise("invented chain",
                                               (FOUR[0], FOUR[1], FOUR[3], FOUR[2]),
                                               frozenset({1})),))
    with pytest.raises(ValueError, match="alternation"):
        DeductionVerifier.verify(state, XChain(), forged)


def test_rejects_broken_strong_link():
    state = make_state()
    good = find_chain(state, FOUR)
    forged = replace(good, premises=(Premise("invalid strong link",
                                               (FOUR[0], FOUR[1], FOUR[2], (2, 2)),
                                               frozenset({1})),))
    with pytest.raises(ValueError, match="alternation"):
        DeductionVerifier.verify(state, XChain(), forged)


def test_rejects_forged_target_and_interior_elimination():
    state = make_state()
    good = find_chain(state, FOUR)
    for target in ((8, 8), FOUR[1]):
        forged = replace(good, eliminations=(Elimination(target, 1),))
        with pytest.raises(ValueError, match="not justified"):
            DeductionVerifier.verify(state, XChain(), forged)


def test_rejects_wrong_digit_and_wrong_technique():
    state = make_state()
    good = find_chain(state, FOUR)
    forged = replace(good, premises=(Premise("wrong digit", FOUR, frozenset({2})),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, XChain(), forged)
    with pytest.raises(ValueError, match="structure"):
        DeductionVerifier.verify(state, XChain(), replace(good, technique="XY-Chain"))


def test_rejects_stale_effect():
    state = make_state()
    good = find_chain(state, FOUR)
    effect = good.eliminations[0]
    state.eliminate(*effect.cell, effect.digit)
    with pytest.raises(ValueError, match="not justified"):
        DeductionVerifier.verify(state, XChain(), replace(good, eliminations=(effect,)))


def test_rejects_non_simple_chain_and_invalid_move_shape():
    state = make_state()
    good = find_chain(state, FOUR)
    with pytest.raises(ValueError, match="repeat"):
        Premise("loop", (FOUR[0], FOUR[1], FOUR[0], FOUR[3]), frozenset({1}))
    with pytest.raises(ValueError, match="structure"):
        DeductionVerifier.verify(state, XChain(), replace(good, placements=(Placement((8, 8), 2),)))


@pytest.mark.parametrize("value", (0, 1, 2, 4, 6, 8, 10, True, 3.0, "5"))
def test_rejects_invalid_search_bound(value):
    with pytest.raises(ValueError, match="max_links"):
        XChain(value)


def test_default_solver_registration():
    assert "X-Chain" in [t.name for t in LogicalSolver().techniques]
    assert DeductionVerifier.supports(XChain())
