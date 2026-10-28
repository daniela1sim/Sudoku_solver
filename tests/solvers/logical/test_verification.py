"""Independent checks for the deduction verification layer."""

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Placement, Premise
from sudoku.solvers.logical.base import LogicalTechnique
from sudoku.solvers.logical.singles import HiddenSingle, NakedSingle
from sudoku.solvers.logical.verification import DeductionVerifier

SOLVED = (
    "534678912" "672195348" "198342567"
    "859761423" "426853791" "713924856"
    "961537284" "287419635" "345286179"
)


def proposed(technique: str, row: int, col: int, digit: int) -> Deduction:
    return Deduction(
        technique=technique,
        premises=(Premise(description="Example evidence"),),
        placements=(Placement(cell=(row, col), digit=digit),),
    )


def test_supported_techniques():
    assert DeductionVerifier.supports(NakedSingle())
    assert DeductionVerifier.supports(HiddenSingle())


def test_valid_naked_single_does_not_mutate_state():
    state = CandidateState(SudokuBoard.from_string("0" + SOLVED[1:]))
    before = state.board.to_string()
    assert DeductionVerifier.verify(state, NakedSingle(), proposed("Naked Single", 0, 0, 5)) is None
    assert state.board.to_string() == before


def test_reject_invalid_naked_single_and_wrong_name():
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    with pytest.raises(ValueError, match="Invalid Naked Single"):
        DeductionVerifier.verify(state, NakedSingle(), proposed("Naked Single", 0, 0, 5))
    with pytest.raises(ValueError, match="Unexpected deduction"):
        DeductionVerifier.verify(state, NakedSingle(), proposed("Hidden Single", 0, 0, 5))


def test_valid_hidden_single_from_candidate_eliminations():
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    for col in range(8):
        state.eliminate(0, col, 1)
    assert DeductionVerifier.verify(state, HiddenSingle(), proposed("Hidden Single", 0, 8, 1)) is None


def test_reject_invalid_hidden_single():
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    with pytest.raises(ValueError, match="Invalid Hidden Single"):
        DeductionVerifier.verify(state, HiddenSingle(), proposed("Hidden Single", 0, 0, 1))


def test_reject_digit_not_in_candidates():
    state = CandidateState(SudokuBoard.from_string("0" + SOLVED[1:]))
    with pytest.raises(ValueError, match="not an available candidate"):
        DeductionVerifier.verify(state, NakedSingle(), proposed("Naked Single", 0, 0, 4))


def test_unsupported_technique_fails_closed():
    class Unsupported(LogicalTechnique):
        @property
        def name(self):
            return "Unsupported"

        def find_deductions(self, state):
            return ()

    unsupported = Unsupported()
    assert not DeductionVerifier.supports(unsupported)
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    with pytest.raises(NotImplementedError):
        DeductionVerifier.verify(state, unsupported, proposed("Unsupported", 0, 0, 1))
