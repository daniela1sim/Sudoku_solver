"""Regression tests for conditional, whole-board BUG+1 deductions.

The synthetic fixture deliberately represents *candidate geometry*, not a
uniquely solvable Sudoku. These tests check the BUG+1 pattern and its safety
gates; only the caller can establish the puzzle's uniqueness assumption.
"""
from dataclasses import replace

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Elimination, Placement, Premise
from sudoku.solvers.logical.solver import LogicalSolver, SolveStatus
from sudoku.solvers.logical.uniqueness import BUGPlusOne
from sudoku.solvers.logical.verification import DeductionVerifier

SOLVED = (
    "534678912" "672195348" "198342567"
    "859761423" "426853791" "713924856"
    "961537284" "287419635" "345286179"
)


def almost_bug_state() -> CandidateState:
    """Two complete digit permutations give a balanced 81-cell BUG graph.

    Adding a third candidate at R1C1 creates the precise BUG+1 pattern.
    The fixture does NOT have a unique solution, by construction.
    """
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    for r in range(9):
        for c in range(9):
            d = int(SOLVED[9 * r + c])
            state._candidates[(r, c)] = {d, d % 9 + 1}
    state._candidates[(0, 0)].add(7)
    state._assert_consistent()
    return state


def test_detects_extra_candidate_and_generates_structured_placement():
    state = almost_bug_state()
    deductions = BUGPlusOne().find_deductions(state)
    assert len(deductions) == 1
    deduction = deductions[0]
    assert deduction.technique == "BUG+1"
    assert deduction.placements == (Placement((0, 0), 7),)
    assert deduction.eliminations == ()
    assert deduction.premises[0].cells == ((0, 0),)
    assert deduction.premises[0].digits == frozenset({7})
    assert "unique solution" in deduction.premises[0].description
    DeductionVerifier.verify(state, BUGPlusOne(), deduction)


def test_nonmutation_and_deterministic_discovery():
    state = almost_bug_state()
    snapshot = {cell: state.candidates_at(*cell) for cell in state.unsolved_cells()}
    technique = BUGPlusOne()
    assert technique.find_deductions(state) == technique.find_deductions(state)
    assert snapshot == {cell: state.candidates_at(*cell) for cell in state.unsolved_cells()}


def test_bivalue_alone_is_insufficient_without_global_unit_balance():
    state = almost_bug_state()
    # Still one trivalue cell, but another row/column/box no longer has
    # exactly two appearances of every digit after removing the extra.
    state._candidates[(0, 1)] = {4, 6}
    assert len(state.candidates_at(0, 1)) == 2
    assert BUGPlusOne().find_deductions(state) == ()


@pytest.mark.parametrize("mutation", ["second_trivalue", "quad", "single", "all_bivalue"])
def test_requires_exactly_one_trivalue_and_all_other_cells_bivalue(mutation):
    state = almost_bug_state()
    if mutation == "second_trivalue":
        state._candidates[(1, 1)].add(9)
    elif mutation == "quad":
        state._candidates[(0, 0)].add(8)
    elif mutation == "single":
        state._candidates[(1, 1)] = {7}
    else:
        state._candidates[(0, 0)].remove(7)
    assert BUGPlusOne().find_deductions(state) == ()


def test_verifier_rejects_forged_placement_and_premise():
    state = almost_bug_state()
    deduction = BUGPlusOne().find_first(state)
    assert deduction is not None
    bad_moves = (
        replace(deduction, placements=(Placement((0, 0), 5),)),
        replace(deduction, placements=(Placement((0, 1), 7),)),
        replace(deduction, eliminations=(Elimination((1, 1), 5),)),
        replace(deduction, technique="Hidden Single"),
        replace(deduction, premises=(Premise("fake", ((0, 1),), frozenset({7})),)),
    )
    for invalid in bad_moves:
        with pytest.raises(ValueError):
            DeductionVerifier.verify(state, BUGPlusOne(), invalid)


def test_verifier_rejects_pattern_after_state_changes():
    state = almost_bug_state()
    deduction = BUGPlusOne().find_first(state)
    assert deduction is not None
    state._candidates[(0, 1)] = {4, 6}
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, BUGPlusOne(), deduction)


def test_opt_in_gate_on_default_and_custom_solver():
    assert "BUG+1" not in [t.name for t in LogicalSolver().techniques]
    assert "BUG+1" in [t.name for t in LogicalSolver(allow_uniqueness=True).techniques]
    with pytest.raises(ValueError, match="allow_uniqueness"):
        LogicalSolver((BUGPlusOne(),))
    assert LogicalSolver((BUGPlusOne(),), allow_uniqueness=True).techniques[0].name == "BUG+1"


# HoDoKu BUG+1 worked example: R1C8 has {3,5,6}, and 6 is forced.
# Source: https://hodoku.sourceforge.net/en/show_example.php?file=bug101&tech=BUG+%2B+1
HODOKU_POSITION = (
    "140780009" "280450107" "370610008"
    "953871002" "724965813" "861324975"
    "618237594" "597148326" "432596781"
)


def test_hodoku_example_has_exactly_one_completion():
    """Independently establish the uniqueness assumption for this fixture.

    This small brute-force check is test-only; it is not used for BUG+1
    discovery or for the logical solver's deductions.
    """
    def count_completions(board: SudokuBoard, limit: int = 2) -> int:
        empty = [(r, c) for r in range(9) for c in range(9)
                 if board.value_at(r, c) == 0]
        if not empty:
            return int(board.is_complete())
        choices = [
            (tuple(d for d in range(1, 10) if board.can_place(r, c, d)), r, c)
            for r, c in empty
        ]
        options, row, col = min(choices, key=lambda x: len(x[0]))
        total = 0
        for digit in options:
            next_board = board.copy()
            next_board.place(row, col, digit)
            total += count_completions(next_board, limit - total)
            if total >= limit:
                break
        return total

    assert count_completions(SudokuBoard.from_string(HODOKU_POSITION)) == 1


def test_hodoku_example_detects_r1c8_equals_6():
    state = CandidateState(SudokuBoard.from_string(HODOKU_POSITION))
    assert state.candidates_at(0, 7) == frozenset({3, 5, 6})
    deduction = BUGPlusOne().find_first(state)
    assert deduction is not None
    assert deduction.placements == (Placement((0, 7), 6),)
    DeductionVerifier.verify(state, BUGPlusOne(), deduction)


def test_solver_applies_verified_deduction_with_history():
    # Unlike the synthetic balanced-candidate fixture, this is a genuine
    # partially solved Sudoku from the published HoDoKu BUG+1 example.
    state = CandidateState(SudokuBoard.from_string(HODOKU_POSITION))
    solver = LogicalSolver((BUGPlusOne(),), allow_uniqueness=True)
    result = solver.solve(state, max_steps=1)
    assert result.status is SolveStatus.STEP_LIMIT
    assert len(result.steps) == 1
    assert result.steps[0].deduction.placements == (Placement((0, 7), 6),)
    assert result.steps[0].before.board.value_at(0, 7) == 0
    assert result.steps[0].after.board.value_at(0, 7) == 6
    assert result.state.board.value_at(0, 7) == 6
    assert state.board.value_at(0, 7) == 0


def test_invalid_type_is_rejected():
    with pytest.raises(TypeError):
        BUGPlusOne().find_deductions(object())
