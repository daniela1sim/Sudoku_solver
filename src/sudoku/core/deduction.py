"""Immutable, structured records of human-style Sudoku deductions.

A Deduction records *what* a technique proposes and the evidence it cites.
It does not apply moves or prove the underlying Sudoku inference. Later,
a proof-checking layer can verify technique-specific premises against a
CandidateState before an executor applies the recorded effects.

Coordinates use zero-based (row, column) indexing internally.
"""

from __future__ import annotations

from dataclasses import dataclass

from sudoku.core.board import Cell, SudokuBoard


def _validate_cell(cell: Cell) -> None:
    if not isinstance(cell, tuple) or len(cell) != 2:
        raise TypeError("cell must be a (row, column) tuple")
    SudokuBoard._check_cell(*cell)


def _validate_digit(digit: int) -> None:
    if type(digit) is not int or digit not in SudokuBoard.DIGITS:
        raise ValueError("digit must be an integer from 1 to 9")


def cell_label(cell: Cell) -> str:
    """Return human-readable one-based notation, e.g. (0, 2) -> 'R1C3'."""
    _validate_cell(cell)
    return f"R{cell[0] + 1}C{cell[1] + 1}"


@dataclass(frozen=True, slots=True)
class Placement:
    """A proposed placement of a digit in an empty cell."""

    cell: Cell
    digit: int

    def __post_init__(self) -> None:
        _validate_cell(self.cell)
        _validate_digit(self.digit)


@dataclass(frozen=True, slots=True)
class Elimination:
    """A proposed removal of a digit from a cell's candidate set."""

    cell: Cell
    digit: int

    def __post_init__(self) -> None:
        _validate_cell(self.cell)
        _validate_digit(self.digit)


@dataclass(frozen=True, slots=True)
class Premise:
    """An evidence statement supporting a deduction.

    `cells` identifies relevant locations; `digits` identifies relevant
    values. `description` explains the observed relationship. These fields
    are evidence annotations, NOT a machine-checkable proof by themselves.
    """

    description: str
    cells: tuple[Cell, ...] = ()
    digits: frozenset[int] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("premise description must be nonempty")
        if not isinstance(self.cells, tuple):
            raise TypeError("premise cells must be a tuple")
        for cell in self.cells:
            _validate_cell(cell)
        if len(set(self.cells)) != len(self.cells):
            raise ValueError("premise cells must not repeat")
        if not isinstance(self.digits, frozenset):
            raise TypeError("premise digits must be a frozenset")
        for digit in self.digits:
            _validate_digit(digit)


@dataclass(frozen=True, slots=True)
class Deduction:
    """A single technique's proposed logical step and supporting premises.

    Immutable records can be inspected, logged, and formatted independently
    of a solver. Construction checks shape and internal consistency only:
    it does NOT guarantee that premises are true or effects are entailed.
    """

    technique: str
    premises: tuple[Premise, ...]
    placements: tuple[Placement, ...] = ()
    eliminations: tuple[Elimination, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.technique, str) or not self.technique.strip():
            raise ValueError("technique must be nonempty")
        if not isinstance(self.premises, tuple) or not self.premises or not all(
            isinstance(premise, Premise) for premise in self.premises
        ):
            raise ValueError("premises must be a nonempty tuple of Premise objects")
        if not isinstance(self.placements, tuple) or not all(
            isinstance(move, Placement) for move in self.placements
        ):
            raise TypeError("placements must be a tuple of Placement objects")
        if not isinstance(self.eliminations, tuple) or not all(
            isinstance(move, Elimination) for move in self.eliminations
        ):
            raise TypeError("eliminations must be a tuple of Elimination objects")
        if not self.placements and not self.eliminations:
            raise ValueError("deduction must have at least one effect")
        if len(set(self.placements)) != len(self.placements):
            raise ValueError("duplicate placements")
        if len(set(self.eliminations)) != len(self.eliminations):
            raise ValueError("duplicate eliminations")
        placed_cells = [move.cell for move in self.placements]
        if len(set(placed_cells)) != len(placed_cells):
            raise ValueError("a deduction cannot place multiple digits in one cell")
        if any(move.cell in placed_cells for move in self.eliminations):
            raise ValueError("a deduction cannot place and eliminate in the same cell")

    @property
    def affected_cells(self) -> frozenset[Cell]:
        """Cells altered by the proposed effects (not premise-only cells)."""
        return frozenset(move.cell for move in (*self.placements, *self.eliminations))
