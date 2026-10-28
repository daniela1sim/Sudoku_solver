"""Tests for candidate tracking, propagation, and consistency checks."""

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState


PUZZLE = (
    "530070000"
    "600195000"
    "098000060"
    "800060003"
    "400803001"
    "700020006"
    "060000280"
    "000419005"
    "000080079"
)

SOLVED = (
    "534678912"
    "672195348"
    "198342567"
    "859761423"
    "426853791"
    "713924856"
    "961537284"
    "287419635"
    "345286179"
)


@pytest.fixture
def board():
    return SudokuBoard.from_string(PUZZLE)


@pytest.fixture
def state(board):
    return CandidateState(board)


def test_initialize_candidates_from_row_column_and_box(state):
    assert state.candidates_at(0, 2) == frozenset({1, 2, 4})
    assert state.candidates_at(0, 0) == frozenset()
    assert len(state.unsolved_cells()) == 51
    assert state.unsolved_cells() == tuple(sorted(state.unsolved_cells()))
    assert not state.is_complete()


def test_reject_invalid_board_argument():
    with pytest.raises(TypeError, match="SudokuBoard"):
        CandidateState([[0] * 9 for _ in range(9)])


@pytest.mark.parametrize("row,col", [(-1, 0), (9, 0), (0, 9), (0, -1), (True, 1), (1, 1.5)])
def test_candidates_at_rejects_invalid_coordinates(state, row, col):
    with pytest.raises(IndexError):
        state.candidates_at(row, col)


@pytest.mark.parametrize("digit", [0, 10, -1, True, 1.0, "1"])
def test_eliminate_rejects_invalid_digits(state, digit):
    with pytest.raises(ValueError, match="digit"):
        state.eliminate(0, 2, digit)


def test_eliminate_rejects_invalid_coordinates(state):
    with pytest.raises(IndexError):
        state.eliminate(9, 0, 1)


def test_elimination_is_persistent_and_idempotent(state):
    assert state.eliminate(0, 2, 2) is True
    assert state.candidates_at(0, 2) == frozenset({1, 4})
    assert state.eliminate(0, 2, 2) is False
    assert state.candidates_at(0, 2) == frozenset({1, 4})
    # Eliminating a digit absent from the candidates does nothing.
    assert state.eliminate(0, 2, 9) is False


def test_eliminating_from_filled_cell_is_noop(state):
    assert state.eliminate(0, 0, 5) is False
    assert state.board.value_at(0, 0) == 5


def test_elimination_that_empties_cell_rolls_back():
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    for digit in range(1, 9):
        assert state.eliminate(0, 0, digit)
    before = state.candidates_at(0, 0)
    with pytest.raises(ValueError, match="no candidates"):
        state.eliminate(0, 0, 9)
    assert state.candidates_at(0, 0) == before


def test_elimination_that_removes_last_position_in_unit_rolls_back():
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    for col in range(8):
        state.eliminate(0, col, 1)
    assert state.candidates_at(0, 8) == frozenset(range(1, 10))
    with pytest.raises(ValueError, match="no possible position"):
        state.eliminate(0, 8, 1)
    assert 1 in state.candidates_at(0, 8)


def test_place_propagates_to_row_column_and_box_peers_and_keeps_other_candidates():
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    state.eliminate(0, 1, 2)  # Earlier elimination must not be restored.
    state.place(0, 0, 1)
    assert state.board.value_at(0, 0) == 1
    assert state.candidates_at(0, 0) == frozenset()
    assert (0, 0) not in state.unsolved_cells()
    for cell in [(0, 8), (8, 0), (2, 2)]:
        assert 1 not in state.candidates_at(*cell)
    assert 1 in state.candidates_at(4, 4)  # Non-peer unaffected.
    assert 2 not in state.candidates_at(0, 1)


def test_placement_must_be_a_current_candidate(state):
    state.eliminate(0, 2, 2)
    with pytest.raises(ValueError, match="not a candidate"):
        state.place(0, 2, 2)
    assert state.board.value_at(0, 2) == 0
    with pytest.raises(ValueError, match="not a candidate"):
        state.place(0, 0, 5)  # Given cell cannot be replaced.
    with pytest.raises(ValueError, match="not a candidate"):
        state.place(0, 2, 9)  # Conflicts with current clues.


def test_failed_placement_restores_board_and_all_candidates():
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    # Row 1 must contain digit 1 in C1. Placing 1 at R2C1 would
    # make digit 1 impossible anywhere in row 1.
    for col in range(1, 9):
        state.eliminate(0, col, 1)
    before_grid = state.board.to_string()
    before_candidates = {cell: state.candidates_at(*cell) for cell in state.unsolved_cells()}
    with pytest.raises(ValueError, match="no possible position"):
        state.place(1, 0, 1)
    assert state.board.to_string() == before_grid
    assert {cell: state.candidates_at(*cell) for cell in state.unsolved_cells()} == before_candidates


def test_state_copies_input_board_and_returns_defensive_board_snapshot(board):
    state = CandidateState(board)
    board.place(0, 2, 4)
    assert state.board.value_at(0, 2) == 0
    snapshot = state.board
    snapshot.place(0, 2, 4)
    assert state.board.value_at(0, 2) == 0


def test_copy_has_independent_board_and_candidate_sets(state):
    state.eliminate(0, 2, 2)
    clone = state.copy()
    assert clone.candidates_at(0, 2) == frozenset({1, 4})
    clone.place(0, 2, 4)
    assert clone.board.value_at(0, 2) == 4
    assert state.board.value_at(0, 2) == 0
    assert state.candidates_at(0, 2) == frozenset({1, 4})
    state.eliminate(0, 2, 1)
    assert clone.candidates_at(0, 2) == frozenset()


def test_full_solved_board_is_complete():
    state = CandidateState(SudokuBoard.from_string(SOLVED))
    assert state.is_complete()
    assert state.unsolved_cells() == ()
    assert state.candidates_at(0, 0) == frozenset()


def test_repr_exposes_state_summary(state):
    representation = repr(state)
    assert "CandidateState" in representation
    assert "unsolved=51" in representation
