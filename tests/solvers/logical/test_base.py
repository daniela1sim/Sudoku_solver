"""Contract tests for the logical-technique abstraction."""

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Placement, Premise
from sudoku.solvers.logical.base import LogicalTechnique


PUZZLE = (
    '530070000'
    '600195000'
    '098000060'
    '800060003'
    '400803001'
    '700020006'
    '060000280'
    '000419005'
    '000080079'
)


class ExampleTechnique(LogicalTechnique):
    @property
    def name(self) -> str:
        return 'Example'

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        if 4 not in state.candidates_at(0, 2):
            return ()
        return (
            Deduction(
                technique=self.name,
                premises=(Premise(description='Example premise', cells=((0, 2),)),),
                placements=(Placement(cell=(0, 2), digit=4),),
            ),
        )


def test_cannot_instantiate_abstract_base():
    with pytest.raises(TypeError):
        LogicalTechnique()


def test_name_and_first_deduction():
    state = CandidateState(SudokuBoard.from_string(PUZZLE))
    technique = ExampleTechnique()
    assert technique.name == 'Example'
    found = technique.find_deductions(state)
    assert isinstance(found, tuple)
    assert len(found) == 1
    assert technique.find_first(state) == found[0]


def test_no_deductions_returns_none():
    state = CandidateState(SudokuBoard.from_string(PUZZLE))
    state.eliminate(0, 2, 4)
    assert ExampleTechnique().find_first(state) is None


def test_example_technique_does_not_mutate_state():
    state = CandidateState(SudokuBoard.from_string(PUZZLE))
    original_grid = state.board.to_string()
    original_candidates = {cell: state.candidates_at(*cell) for cell in state.unsolved_cells()}
    ExampleTechnique().find_deductions(state)
    assert state.board.to_string() == original_grid
    assert {cell: state.candidates_at(*cell) for cell in state.unsolved_cells()} == original_candidates
