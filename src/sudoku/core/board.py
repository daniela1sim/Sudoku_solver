"""Core 9×9 Sudoku board representation.

The board stores cell values and identifies immutable clues. It deliberately
contains no solving strategies or candidate-elimination logic.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeAlias

Cell: TypeAlias = tuple[int, int]
Grid: TypeAlias = Sequence[Sequence[int]]


class SudokuBoard:
    """A mutable Sudoku board with immutable original clues.

    Coordinates are zero-based: ``(0, 0)`` is the top-left cell.
    Empty cells contain ``0``; filled cells contain integers from 1 to 9.

    The constructor treats each nonzero input value as a fixed clue.
    Contradictory clues are rejected, but a conflict-free puzzle is not
    necessarily solvable or uniquely solvable.
    """

    SIZE = 9
    BOX_SIZE = 3
    DIGITS = frozenset(range(1, 10))

    def __init__(self, grid: Grid) -> None:
        if len(grid) != self.SIZE:
            raise ValueError("Sudoku grid must have exactly 9 rows")

        rows: list[list[int]] = []
        for row_index, row in enumerate(grid):
            if len(row) != self.SIZE:
                raise ValueError(f"Row {row_index} must have exactly 9 cells")
            values = list(row)
            for col_index, value in enumerate(values):
                if type(value) is not int or not 0 <= value <= 9:
                    raise ValueError(
                        f"Cell ({row_index}, {col_index}) must be an integer from 0 to 9"
                    )
            rows.append(values)

        self._grid = rows
        self._givens: frozenset[Cell] = frozenset(
            (r, c)
            for r in range(self.SIZE)
            for c in range(self.SIZE)
            if self._grid[r][c] != 0
        )
        if not self.is_valid():
            raise ValueError("Initial Sudoku clues violate row, column, or box constraints")

    @classmethod
    def from_string(cls, puzzle: str) -> SudokuBoard:
        """Construct a board from 81 characters; '0' or '.' means empty."""
        if len(puzzle) != cls.SIZE * cls.SIZE:
            raise ValueError("Puzzle string must contain exactly 81 characters")
        if any(character not in "0123456789." for character in puzzle):
            raise ValueError("Puzzle string may contain only digits and '.'")
        values = [0 if char == "." else int(char) for char in puzzle]
        return cls([values[i:i + cls.SIZE] for i in range(0, 81, cls.SIZE)])

    @staticmethod
    def _check_cell(row: int, col: int) -> None:
        if type(row) is not int or type(col) is not int or not (0 <= row < 9 and 0 <= col < 9):
            raise IndexError("Cell coordinates must be integers between 0 and 8")

    @staticmethod
    def _check_index(index: int) -> None:
        if type(index) is not int or not 0 <= index < 9:
            raise IndexError("Row or column index must be an integer between 0 and 8")

    def value_at(self, row: int, col: int) -> int:
        """Return the digit at a cell (0 if empty)."""
        self._check_cell(row, col)
        return self._grid[row][col]

    def is_given(self, row: int, col: int) -> bool:
        """Whether the cell was filled in the original puzzle."""
        self._check_cell(row, col)
        return (row, col) in self._givens

    @property
    def givens(self) -> frozenset[Cell]:
        """Coordinates of immutable original clues."""
        return self._givens

    def row(self, index: int) -> tuple[int, ...]:
        """Return a snapshot of a row."""
        self._check_index(index)
        return tuple(self._grid[index])

    def column(self, index: int) -> tuple[int, ...]:
        """Return a snapshot of a column."""
        self._check_index(index)
        return tuple(self._grid[r][index] for r in range(self.SIZE))

    def box(self, row: int, col: int) -> tuple[int, ...]:
        """Return the nine values in the box containing (row, col), row-major."""
        self._check_cell(row, col)
        start_row = (row // self.BOX_SIZE) * self.BOX_SIZE
        start_col = (col // self.BOX_SIZE) * self.BOX_SIZE
        return tuple(
            self._grid[r][c]
            for r in range(start_row, start_row + self.BOX_SIZE)
            for c in range(start_col, start_col + self.BOX_SIZE)
        )

    def can_place(self, row: int, col: int, digit: int) -> bool:
        """Check whether a digit can legally replace the current cell value.

        Fixed clues cannot be changed, even to the same digit. This method
        checks only immediate Sudoku constraints, not global solvability.
        """
        self._check_cell(row, col)
        if type(digit) is not int or digit not in self.DIGITS or (row, col) in self._givens:
            return False
        return (
            all(c == col or self._grid[row][c] != digit for c in range(self.SIZE))
            and all(r == row or self._grid[r][col] != digit for r in range(self.SIZE))
            and all(
                (r, c) == (row, col) or self._grid[r][c] != digit
                for r in range((row // 3) * 3, (row // 3) * 3 + 3)
                for c in range((col // 3) * 3, (col // 3) * 3 + 3)
            )
        )

    def place(self, row: int, col: int, digit: int) -> None:
        """Place a nonzero digit in a mutable cell, rejecting local conflicts.

        A different value cannot overwrite an existing placement. Call
        ``clear`` first if changing an earlier placement is intentional.
        """
        self._check_cell(row, col)
        if (row, col) in self._givens:
            raise ValueError("Cannot modify an original clue")
        if self._grid[row][col] != 0:
            raise ValueError("Cell is already filled; clear it before placing another digit")
        if not self.can_place(row, col, digit):
            raise ValueError(f"Digit {digit!r} cannot be placed at ({row}, {col})")
        self._grid[row][col] = digit

    def clear(self, row: int, col: int) -> None:
        """Remove a non-given placement, restoring an empty cell."""
        self._check_cell(row, col)
        if (row, col) in self._givens:
            raise ValueError("Cannot clear an original clue")
        self._grid[row][col] = 0

    def is_valid(self) -> bool:
        """Whether all filled cells obey row, column, and box uniqueness."""
        def no_duplicates(values: Sequence[int]) -> bool:
            filled = [value for value in values if value != 0]
            return len(filled) == len(set(filled))

        for i in range(self.SIZE):
            if not no_duplicates(self.row(i)) or not no_duplicates(self.column(i)):
                return False
        return all(
            no_duplicates(self.box(r, c))
            for r in range(0, self.SIZE, self.BOX_SIZE)
            for c in range(0, self.SIZE, self.BOX_SIZE)
        )

    def is_complete(self) -> bool:
        """Whether every cell is filled and the grid is valid."""
        return all(value != 0 for row in self._grid for value in row) and self.is_valid()

    def to_list(self) -> list[list[int]]:
        """Return a deep copy of the grid data."""
        return [row.copy() for row in self._grid]

    def to_string(self) -> str:
        """Return a compact 81-digit representation (zeros for blanks)."""
        return "".join(str(value) for row in self._grid for value in row)

    def copy(self) -> SudokuBoard:
        """Copy the board, retaining the *original* immutable clue positions."""
        clone = object.__new__(SudokuBoard)
        clone._grid = self.to_list()
        clone._givens = self._givens
        return clone

    def __repr__(self) -> str:
        return f"SudokuBoard.from_string({self.to_string()!r})"

    def __str__(self) -> str:
        lines = []
        for r in range(self.SIZE):
            if r in (3, 6):
                lines.append("------+-------+------")
            values = [str(value) if value else "." for value in self._grid[r]]
            lines.append(" ".join(values[:3]) + " | " + " ".join(values[3:6]) + " | " + " ".join(values[6:]))
        return "\n".join(lines)
