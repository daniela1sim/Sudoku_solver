"""Naked Single and Hidden Single deductions for standard 9×9 Sudoku.

Both techniques are *read-only*: they return immutable Deduction records
without changing the CandidateState. They assume that its candidate sets
faithfully represent the deductions already made. The solver will later
verify deductions and apply their placements.
"""

from __future__ import annotations

from sudoku.core.board import Cell, SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Placement, Premise, cell_label
from sudoku.solvers.logical.base import LogicalTechnique


def _units() -> tuple[tuple[str, int, tuple[Cell, ...]], ...]:
    """Return rows, columns, and boxes in stable order (zero-based indices)."""
    rows = tuple(
        ("row", r, tuple((r, c) for c in range(9))) for r in range(9)
    )
    columns = tuple(
        ("column", c, tuple((r, c) for r in range(9))) for c in range(9)
    )
    boxes = tuple(
        (
            "box",
            br * 3 + bc,
            tuple(
                (r, c)
                for r in range(br * 3, br * 3 + 3)
                for c in range(bc * 3, bc * 3 + 3)
            ),
        )
        for br in range(3)
        for bc in range(3)
    )
    return rows + columns + boxes


class NakedSingle(LogicalTechnique):
    """Place the sole remaining candidate of an empty cell."""

    @property
    def name(self) -> str:
        return "Naked Single"

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        if not isinstance(state, CandidateState):
            raise TypeError("state must be a CandidateState")
        deductions: list[Deduction] = []
        for cell in state.unsolved_cells():
            candidates = state.candidates_at(*cell)
            if len(candidates) != 1:
                continue
            digit = next(iter(candidates))
            deductions.append(
                Deduction(
                    technique=self.name,
                    premises=(
                        Premise(
                            description=(
                                f"{cell_label(cell)} has only one remaining "
                                f"candidate: {digit}."
                            ),
                            cells=(cell,),
                            digits=frozenset({digit}),
                        ),
                    ),
                    placements=(Placement(cell=cell, digit=digit),),
                )
            )
        return tuple(deductions)


class HiddenSingle(LogicalTechnique):
    """Place a digit with exactly one candidate position in a unit.

    The same placement may be forced in more than one unit; it is reported
    once, using the first supporting unit in row/column/box order.
    """

    @property
    def name(self) -> str:
        return "Hidden Single"

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        if not isinstance(state, CandidateState):
            raise TypeError("state must be a CandidateState")
        board = state.board
        deductions: list[Deduction] = []
        seen: set[Placement] = set()

        for kind, index, unit in _units():
            placed = {board.value_at(*cell) for cell in unit} - {0}
            for digit in sorted(SudokuBoard.DIGITS - placed):
                cells = tuple(
                    cell for cell in unit if digit in state.candidates_at(*cell)
                )
                if len(cells) != 1:
                    continue
                placement = Placement(cell=cells[0], digit=digit)
                if placement in seen:
                    continue
                seen.add(placement)
                unit_label = f"{kind} {index + 1}"
                deductions.append(
                    Deduction(
                        technique=self.name,
                        premises=(
                            Premise(
                                description=(
                                    f"In {unit_label}, digit {digit} can occur "
                                    f"only in {cell_label(cells[0])}."
                                ),
                                cells=unit,
                                digits=frozenset({digit}),
                            ),
                        ),
                        placements=(placement,),
                    )
                )
        return tuple(deductions)
