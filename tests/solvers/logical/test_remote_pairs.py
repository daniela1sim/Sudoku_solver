"""Remote Pairs regression tests: chains, exclusions and verification."""

from dataclasses import replace

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Premise
from sudoku.solvers.logical.remote_pairs import RemotePairs, _pair_components
from sudoku.solvers.logical.solver import LogicalSolver, SolveStatus
from sudoku.solvers.logical.verification import DeductionVerifier


CHAIN = ((0, 0), (0, 3), (3, 3), (3, 1))
LONG_CHAIN = ((0, 0), (0, 3), (3, 3), (3, 6), (6, 6), (6, 1))


def make_state(cells=CHAIN, pair=(1, 2)):
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    for cell in cells:
        for digit in range(1, 10):
            if digit not in pair:
                state.eliminate(*cell, digit)
    return state


def snapshot(state):
    return state.board.to_string(), tuple(
        (cell, state.candidates_at(*cell)) for cell in state.unsolved_cells()
    )


def first(state):
    deduction = RemotePairs().find_first(state)
    assert deduction is not None
    return deduction


def test_discovers_four_cell_chain_and_both_digit_eliminations():
    state = make_state()
    deduction = first(state)
    assert deduction.technique == "Remote Pairs"
    assert deduction.premises[0].cells == CHAIN
    assert deduction.premises[0].digits == frozenset({1, 2})
    assert Elimination((1, 1), 1) in deduction.eliminations
    assert Elimination((1, 1), 2) in deduction.eliminations
    assert all(e.cell not in CHAIN and e.digit in {1, 2}
               for e in deduction.eliminations)
    assert "R1C1" in deduction.premises[0].description
    DeductionVerifier.verify(state, RemotePairs(), deduction)


def test_long_even_chain_and_other_digit_pair():
    state = make_state(LONG_CHAIN, pair=(4, 7))
    deductions = RemotePairs().find_deductions(state)
    assert deductions
    match = next(d for d in deductions if d.premises[0].cells == LONG_CHAIN)
    assert Elimination((1, 1), 4) in match.eliminations
    assert Elimination((1, 1), 7) in match.eliminations
    DeductionVerifier.verify(state, RemotePairs(), match)


def test_discovery_is_deterministic_and_does_not_mutate():
    state = make_state()
    before = snapshot(state)
    technique = RemotePairs()
    assert technique.find_deductions(state) == technique.find_deductions(state)
    assert snapshot(state) == before


def test_solver_applies_eliminations_and_records_history():
    state = make_state()
    before = snapshot(state)
    result = LogicalSolver((RemotePairs(),)).solve(state, max_steps=1)
    assert result.status is SolveStatus.STEP_LIMIT
    assert len(result.steps) == 1
    assert result.steps[0].deduction.technique == "Remote Pairs"
    assert {1, 2}.isdisjoint(result.state.candidates_at(1, 1))
    assert snapshot(result.steps[0].before) == before
    assert snapshot(state) == before


def test_plain_board_has_no_remote_pair():
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    assert RemotePairs().find_deductions(state) == ()


def test_two_vertex_naked_pair_is_not_remote_pair():
    assert RemotePairs().find_deductions(make_state(CHAIN[:2])) == ()


def test_three_vertex_chain_is_not_remote_pair():
    assert RemotePairs().find_deductions(make_state(CHAIN[:3])) == ()


def test_odd_cycle_is_skipped_rather_than_colored_arbitrarily():
    # The three top-left cells form a triangle of peer links. The fourth
    # vertex connects to the triangle, so the full component is invalid.
    cells = ((0, 0), (0, 1), (1, 0), (3, 0))
    state = make_state(cells)
    assert _pair_components(state) == ()
    assert RemotePairs().find_deductions(state) == ()


def test_rejects_forged_target_outside_common_visibility():
    state = make_state()
    forged = replace(first(state), eliminations=(Elimination((8, 8), 1),))
    with pytest.raises(ValueError, match="not justified"):
        DeductionVerifier.verify(state, RemotePairs(), forged)


def test_rejects_forged_nonpair_elimination():
    state = make_state()
    forged = replace(first(state), eliminations=(Elimination((1, 1), 9),))
    with pytest.raises(ValueError, match="not justified"):
        DeductionVerifier.verify(state, RemotePairs(), forged)


def test_rejects_wrong_premise_pair_and_broken_chain():
    state = make_state()
    good = first(state)
    for premise in (
        Premise("wrong digits", CHAIN, frozenset({1, 3})),
        Premise("broken link", (CHAIN[0], CHAIN[2], CHAIN[1], CHAIN[3]),
                frozenset({1, 2})),
        Premise("too short", CHAIN[:3], frozenset({1, 2})),
    ):
        with pytest.raises(ValueError):
            DeductionVerifier.verify(state, RemotePairs(), replace(good, premises=(premise,)))


def test_rejects_duplicate_premise_cell_at_construction():
    with pytest.raises(ValueError, match="must not repeat"):
        Premise("duplicate cell", (CHAIN[0], CHAIN[1], CHAIN[2], CHAIN[0]),
                frozenset({1, 2}))


def test_rejects_forged_technique_and_placement():
    state = make_state()
    good = first(state)
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, RemotePairs(), replace(good, technique="XY-Wing"))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, RemotePairs(), replace(good, eliminations=()))


def test_rejects_stale_elimination():
    state = make_state()
    good = first(state)
    state.eliminate(1, 1, 1)
    with pytest.raises(ValueError, match="not justified"):
        DeductionVerifier.verify(state, RemotePairs(),
                                 replace(good, eliminations=(Elimination((1, 1), 1),)))


def test_custom_technique_does_not_require_uniqueness():
    solver = LogicalSolver((RemotePairs(),))
    assert solver.techniques[0].name == "Remote Pairs"
    assert "Remote Pairs" in [t.name for t in LogicalSolver().techniques]
    assert DeductionVerifier.supports(RemotePairs())
    with pytest.raises(TypeError):
        RemotePairs().find_deductions(object())
    with pytest.raises(TypeError):
        _pair_components(object())


def test_effect_cannot_be_combined_with_unrelated_chain():
    state = make_state()
    good = first(state)
    # The supplied four-cell chain does not even use the same bivalue pair.
    forged = Deduction(
        technique=good.technique,
        premises=(Premise("unrelated", ((0, 0), (0, 3), (3, 3), (8, 8)),
                          frozenset({1, 2})),),
        eliminations=good.eliminations,
    )
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, RemotePairs(), forged)
