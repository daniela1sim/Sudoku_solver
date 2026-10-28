"""Simple Coloring regression tests: traps, wraps, verification and execution."""

from dataclasses import replace

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Elimination, Premise
from sudoku.solvers.logical.coloring import (
    SimpleColoring, _colored_components, _sees,
)
from sudoku.solvers.logical.solver import LogicalSolver, SolveStatus
from sudoku.solvers.logical.verification import DeductionVerifier


def empty_state() -> CandidateState:
    return CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))


def trap_state() -> CandidateState:
    """R1C1--R1C2 is a row conjugate pair for 1.

    R2C3 sees both via box 1, so 1 can be eliminated there. The other
    digits remain unconstrained to preserve CandidateState consistency.
    """
    state = empty_state()
    for col in range(2, 9):
        state.eliminate(0, col, 1)
    return state


def wrap_state() -> CandidateState:
    """Four strong links form a chain with a same-color box conflict.

    For digit 1: R1C1 -- R1C5 -- R5C5 -- R5C2 -- R2C2.
    R1C1 and R2C2 belong to the same box (but do not form a box strong
    link), so color 0 is impossible at R1C1, R5C5, and R2C2.
    """
    state = empty_state()
    for col in range(9):
        if col not in (0, 4):
            state.eliminate(0, col, 1)
    for row in range(9):
        if row not in (0, 4):
            state.eliminate(row, 4, 1)
    for col in range(9):
        if col not in (1, 4):
            state.eliminate(4, col, 1)
    for row in range(9):
        if row not in (1, 4):
            state.eliminate(row, 1, 1)
    return state


def deductions_matching(state: CandidateState, keyword: str):
    return tuple(d for d in SimpleColoring().find_deductions(state)
                 if keyword in d.premises[0].description)


def snapshot(state: CandidateState):
    return (state.board.to_string(),
            {cell: state.candidates_at(*cell) for cell in state.unsolved_cells()})


def test_color_trap_finds_both_color_visibility():
    state = trap_state()
    deductions = deductions_matching(state, "Color Trap for 1")
    assert len(deductions) == 1
    deduction = deductions[0]
    assert deduction.technique == "Simple Coloring"
    assert deduction.premises[0].cells == ((0, 0), (0, 1))
    assert Elimination((1, 2), 1) in deduction.eliminations
    assert all(e.digit == 1 and e.cell not in ((0, 0), (0, 1))
               for e in deduction.eliminations)
    DeductionVerifier.verify(state, SimpleColoring(), deduction)


def test_color_wrap_eliminates_entire_false_parity():
    state = wrap_state()
    wraps = deductions_matching(state, "Color Wrap for 1")
    assert len(wraps) == 1
    assert set(wraps[0].eliminations) == {
        Elimination((0, 0), 1), Elimination((1, 1), 1),
        Elimination((4, 4), 1),
    }
    assert wraps[0].premises[0].cells == (
        (0, 0), (0, 4), (1, 1), (4, 1), (4, 4),
    )
    DeductionVerifier.verify(state, SimpleColoring(), wraps[0])


def test_coloring_uses_strong_links_from_rows_columns_and_boxes():
    state = wrap_state()
    component = _colored_components(state, 1)[0]
    colors = dict(component.colors)
    assert colors[(0, 0)] != colors[(0, 4)]  # Row strong link
    assert colors[(0, 4)] != colors[(4, 4)]  # Column strong link
    assert _sees((0, 0), (1, 1))          # Weak, same-color box conflict
    assert colors[(0, 0)] == colors[(1, 1)]

    box_state = empty_state()
    # Leave only two positions for 1 in the top-left box.
    for row in range(3):
        for col in range(3):
            if (row, col) not in ((0, 0), (1, 1)):
                box_state.eliminate(row, col, 1)
    box_component = next(c for c in _colored_components(box_state, 1)
                         if (0, 0) in c.cells)
    assert dict(box_component.colors)[(0, 0)] != dict(box_component.colors)[(1, 1)]


def test_non_mutating_deterministic_discovery():
    state = wrap_state()
    before = snapshot(state)
    first = SimpleColoring().find_deductions(state)
    assert first == SimpleColoring().find_deductions(state)
    assert snapshot(state) == before
    assert first


def test_solver_applies_verified_color_trap_and_records_step():
    state = trap_state()
    before = snapshot(state)
    result = LogicalSolver((SimpleColoring(),)).solve(state, max_steps=1)
    assert result.status is SolveStatus.STEP_LIMIT
    assert len(result.steps) == 1
    deduction = result.steps[0].deduction
    assert Elimination((1, 2), 1) in deduction.eliminations
    assert 1 not in result.state.candidates_at(1, 2)
    assert 1 in state.candidates_at(1, 2)
    assert snapshot(state) == before
    assert snapshot(result.steps[0].before) == before


def test_solver_applies_color_wrap():
    result = LogicalSolver((SimpleColoring(),)).solve(wrap_state(), max_steps=1)
    assert len(result.steps) == 1
    assert "Color Wrap" in result.steps[0].deduction.premises[0].description
    for cell in ((0, 0), (1, 1), (4, 4)):
        assert 1 not in result.state.candidates_at(*cell)


def test_rejects_forged_elimination_even_when_candidate_exists():
    state = trap_state()
    good = SimpleColoring().find_first(state)
    assert good is not None
    assert 1 in state.candidates_at(7, 7)
    bad = replace(good, eliminations=(Elimination((7, 7), 1),))
    with pytest.raises(ValueError, match="not justified"):
        DeductionVerifier.verify(state, SimpleColoring(), bad)


def test_rejects_forged_premise_digit_and_cells():
    state = trap_state()
    good = SimpleColoring().find_first(state)
    assert good is not None
    bad_digits = replace(good, premises=(Premise("fake", good.premises[0].cells,
                                               frozenset({9})),))
    bad_cells = replace(good, premises=(Premise("fake", ((0, 0),),
                                              frozenset({1})),))
    for invalid in (bad_digits, bad_cells):
        with pytest.raises(ValueError):
            DeductionVerifier.verify(state, SimpleColoring(), invalid)


def test_rejects_mixed_wrap_and_trap_targets_in_one_deduction():
    state = wrap_state()
    wraps = deductions_matching(state, "Color Wrap for 1")
    traps = deductions_matching(state, "Color Trap for 1")
    assert wraps and traps
    forged = replace(wraps[0], eliminations=(wraps[0].eliminations[0],
                                            traps[0].eliminations[0]))
    with pytest.raises(ValueError, match="not justified"):
        DeductionVerifier.verify(state, SimpleColoring(), forged)


def test_stale_deduction_is_rejected():
    state = trap_state()
    move = SimpleColoring().find_first(state)
    assert move is not None
    state.eliminate(1, 2, 1)
    # Rebuild the wrap/trap effects from the modified candidate state.
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, SimpleColoring(),
                                 replace(move, eliminations=(Elimination((1, 2), 1),)))


def test_empty_or_solved_state_has_no_deductions():
    state = empty_state()
    assert SimpleColoring().find_deductions(state) == ()
    solved = (
        "534678912672195348198342567859761423426853791713924856"
        "961537284287419635345286179"
    )
    assert SimpleColoring().find_deductions(
        CandidateState(SudokuBoard.from_string(solved))) == ()


def test_validation_and_solver_registration():
    technique = SimpleColoring()
    assert DeductionVerifier.supports(technique)
    assert "Simple Coloring" in [t.name for t in LogicalSolver().techniques]
    with pytest.raises(TypeError):
        technique.find_deductions(object())
    with pytest.raises(ValueError):
        _colored_components(trap_state(), 10)
