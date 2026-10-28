"""Integration tests for the initial logical solving engine."""

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.solvers.logical.singles import HiddenSingle, NakedSingle
from sudoku.solvers.logical.solver import LogicalSolver, SolveStatus

SOLVED = (
    "534678912" "672195348" "198342567"
    "859761423" "426853791" "713924856"
    "961537284" "287419635" "345286179"
)


def test_solves_one_missing_cell_without_mutating_input():
    original = SudokuBoard.from_string("0" + SOLVED[1:])
    result = LogicalSolver().solve(original)
    assert result.status is SolveStatus.SOLVED
    assert result.solved
    assert result.state.board.to_string() == SOLVED
    assert original.value_at(0, 0) == 0
    assert len(result.steps) == 1
    assert result.steps[0].deduction.technique == "Naked Single"
    assert result.steps[0].before.board.value_at(0, 0) == 0
    assert result.steps[0].after.board.value_at(0, 0) == 5


def test_already_solved_has_no_steps():
    result = LogicalSolver().solve(SudokuBoard.from_string(SOLVED))
    assert result.solved and result.steps == ()


def test_empty_board_is_stuck():
    result = LogicalSolver().solve(SudokuBoard([[0] * 9 for _ in range(9)]))
    assert result.status is SolveStatus.STUCK and result.steps == ()


def test_limit_zero_and_one():
    puzzle = SudokuBoard.from_string("00" + SOLVED[2:])
    zero = LogicalSolver().solve(puzzle, max_steps=0)
    one = LogicalSolver().solve(puzzle, max_steps=1)
    assert zero.status is SolveStatus.STEP_LIMIT and zero.steps == ()
    assert one.status is SolveStatus.STEP_LIMIT and len(one.steps) == 1
    assert not one.solved


def test_candidate_state_is_copied_and_existing_eliminations_preserved():
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    for col in range(8):
        state.eliminate(0, col, 1)
    result = LogicalSolver((HiddenSingle(),)).solve(state, max_steps=1)
    assert result.steps[0].deduction.technique == "Hidden Single"
    assert result.state.board.value_at(0, 8) == 1
    assert state.board.value_at(0, 8) == 0
    assert state.candidates_at(0, 0) == frozenset(range(2, 10))


def test_configurable_no_techniques_and_validation():
    puzzle = SudokuBoard.from_string("0" + SOLVED[1:])
    assert LogicalSolver(()).solve(puzzle).status is SolveStatus.STUCK
    assert LogicalSolver((NakedSingle(),)).solve(puzzle).solved
    with pytest.raises(TypeError):
        LogicalSolver((object(),))
    with pytest.raises(TypeError):
        LogicalSolver().solve(None)
    for invalid in (-1, True, 1.2):
        with pytest.raises(ValueError):
            LogicalSolver().solve(puzzle, max_steps=invalid)


def test_repeatable_history_and_independent_results():
    puzzle = SudokuBoard.from_string("00" + SOLVED[2:])
    solver = LogicalSolver()
    first = solver.solve(puzzle)
    second = solver.solve(puzzle)
    assert first.solved and second.solved
    assert [step.deduction for step in first.steps] == [step.deduction for step in second.steps]
    assert first.state is not second.state
