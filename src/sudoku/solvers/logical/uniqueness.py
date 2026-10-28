"""Global uniqueness-based Sudoku techniques.

BUG+1 (Bivalue Universal Grave plus one) relies on an externally established
unique solution. It must not be enabled for arbitrary puzzles unless that
assumption has been verified separately.
"""

from __future__ import annotations

from collections import Counter

from sudoku.core.board import Cell, SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Placement, Premise, cell_label
from sudoku.solvers.logical.base import LogicalTechnique
from sudoku.solvers.logical.singles import _units


def _pure_bug_after_removal(
    state: CandidateState, extra_cell: Cell, removed_digit: int
) -> bool:
    """Whether excluding one candidate creates a genuine *balanced* BUG.

    Every empty cell must then be bivalue, and each digit missing from each
    row/column/box must occur in exactly two remaining candidate sets.
    Merely checking the number of candidates per cell is insufficient.
    This function reads the state but never modifies it.
    """
    board = state.board
    for _, _, cells in _units():
        placed = {board.value_at(*cell) for cell in cells} - {0}
        counts: Counter[int] = Counter()
        for cell in cells:
            candidates = state.candidates_at(*cell)
            if cell == extra_cell:
                candidates = candidates - {removed_digit}
            if candidates and len(candidates) != 2:
                return False
            counts.update(candidates)
        for digit in SudokuBoard.DIGITS:
            if digit in placed:
                if counts[digit] != 0:
                    return False
            elif counts[digit] != 2:
                return False
    return True


def _bug_plus_one_patterns(state: CandidateState) -> tuple[tuple[Cell, int], ...]:
    """Find a three-candidate cell whose extra digit prevents a pure BUG.

    A positive result is *conditional* on the original Sudoku having exactly
    one solution. This function cannot establish that global assumption.
    """
    if not isinstance(state, CandidateState):
        raise TypeError("state must be a CandidateState")

    trivalue: list[Cell] = []
    for cell in state.unsolved_cells():
        size = len(state.candidates_at(*cell))
        if size == 3:
            trivalue.append(cell)
        elif size != 2:
            return ()
    if len(trivalue) != 1:
        return ()

    extra_cell = trivalue[0]
    return tuple(
        (extra_cell, digit)
        for digit in sorted(state.candidates_at(*extra_cell))
        if _pure_bug_after_removal(state, extra_cell, digit)
    )


class BUGPlusOne(LogicalTechnique):
    """Place the extra candidate in a verified BUG+1 candidate state.

    Requires the additional assumption of an initially unique Sudoku puzzle.
    Standard constraint propagation cannot justify this placement alone.
    """

    @property
    def name(self) -> str:
        return "BUG+1"

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        result: list[Deduction] = []
        for cell, digit in _bug_plus_one_patterns(state):
            result.append(
                Deduction(
                    technique=self.name,
                    premises=(
                        Premise(
                            description=(
                                f"Every other unsolved cell is bivalue. Removing "
                                f"{digit} from {cell_label(cell)} would create a "
                                "Bivalue Universal Grave: each remaining digit "
                                "has exactly two candidate positions in every "
                                "row, column, and box where it is missing. "
                                "Assuming the puzzle has a unique solution, "
                                f"{cell_label(cell)} must therefore be {digit}."
                            ),
                            cells=(cell,),
                            digits=frozenset({digit}),
                        ),
                    ),
                    placements=(Placement(cell=cell, digit=digit),),
                )
            )
        return tuple(result)
