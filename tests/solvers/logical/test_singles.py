"""Tests for the two human-style single-placement techniques."""

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Placement
from sudoku.solvers.logical.singles import HiddenSingle, NakedSingle


@pytest.fixture
def blank_state():
    return CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))


def test_empty_board_has_no_singles(blank_state):
    assert NakedSingle().find_deductions(blank_state) == ()
    assert HiddenSingle().find_deductions(blank_state) == ()
    assert NakedSingle().find_first(blank_state) is None


def test_naked_single_on_almost_complete_board():
    rows = [list(map(int, s)) for s in (
        "534678912", "672195348", "198342567", "859761423",
        "426853791", "713924856", "961537284", "287419635", "345286179"
    )]
    rows[0][0] = 0
    state = CandidateState(SudokuBoard(rows))
    deduction, = NakedSingle().find_deductions(state)
    assert deduction.technique == "Naked Single"
    assert deduction.placements == (Placement((0, 0), 5),)
    assert deduction.eliminations == ()
    assert "R1C1" in deduction.premises[0].description
    assert state.board.value_at(0, 0) == 0
    assert state.candidates_at(0, 0) == frozenset({5})


def test_hidden_single_without_naked_single(blank_state):
    # Digit 1 has only one candidate position in row 1, but R1C9
    # still has nine candidates (so it is not a Naked Single).
    for col in range(8):
        assert blank_state.eliminate(0, col, 1)
    assert NakedSingle().find_deductions(blank_state) == ()
    deductions = HiddenSingle().find_deductions(blank_state)
    matching = [d for d in deductions if d.placements == (Placement((0, 8), 1),)]
    assert len(matching) == 1
    assert "row 1" in matching[0].premises[0].description
    assert blank_state.candidates_at(0, 8) == frozenset(range(1, 10))


def test_hidden_single_deduplicates_placements(blank_state):
    # Force 1 to R1C1 in both row 1 and column 1.
    for i in range(1, 9):
        blank_state.eliminate(0, i, 1)
        blank_state.eliminate(i, 0, 1)
    matches = [d for d in HiddenSingle().find_deductions(blank_state)
               if d.placements == (Placement((0, 0), 1),)]
    assert len(matches) == 1


def test_repeated_discovery_is_deterministic_and_read_only(blank_state):
    for col in range(8):
        blank_state.eliminate(0, col, 1)
    before = blank_state.copy()
    technique = HiddenSingle()
    assert technique.find_deductions(blank_state) == technique.find_deductions(blank_state)
    assert blank_state.board.to_string() == before.board.to_string()
    for cell in before.unsolved_cells():
        assert blank_state.candidates_at(*cell) == before.candidates_at(*cell)


@pytest.mark.parametrize("technique", [NakedSingle(), HiddenSingle()])
def test_bad_state_rejected(technique):
    with pytest.raises(TypeError):
        technique.find_deductions(None)
