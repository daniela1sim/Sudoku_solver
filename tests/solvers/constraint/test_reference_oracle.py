"""End-to-end comparison of logical deductions with an independent CSP oracle.

These tests intentionally audit each deduction against the original puzzle,
not against the logical engine's already-pruned candidate sets.
"""

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.solvers.constraint import ReferenceSolver
from sudoku.solvers.logical.solver import LogicalSolver


@pytest.mark.parametrize("puzzle", [
    "530070000600195000098000060800060003400803001700020006060000280000419005000080079",
    "005000987040050001007000000200048000090100000600200000300600200000009070000000500",
    "023700006800060590900000700000040970307096002000000000500470000000002000080000000",
])
def test_every_logical_effect_is_entailment_of_original_clues(puzzle):
    oracle = ReferenceSolver()
    assert oracle.analyze(puzzle).is_unique

    logical_result = LogicalSolver().solve(SudokuBoard.from_string(puzzle))
    assert logical_result.solved
    assert logical_result.steps

    checked = 0
    for step in logical_result.steps:
        for placement in step.deduction.placements:
            assert oracle.forces_placement(puzzle, *placement.cell, placement.digit), (
                f"Unsound {step.deduction.technique} placement: {placement}"
            )
            checked += 1
        for elimination in step.deduction.eliminations:
            assert oracle.proves_elimination(puzzle, *elimination.cell, elimination.digit), (
                f"Unsound {step.deduction.technique} elimination: {elimination}"
            )
            checked += 1
    assert checked >= 40
