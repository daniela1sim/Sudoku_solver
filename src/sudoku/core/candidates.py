"""Candidate tracking for an explainable 9×9 Sudoku solver.

CandidateState owns a copy of a SudokuBoard. Changes must go through this
class so that previously justified eliminations are never silently restored.
"""

from __future__ import annotations

from sudoku.core.board import Cell, SudokuBoard


class CandidateContradiction(ValueError):
    """A candidate update leaves a cell or unit with no legal completion."""


class CandidateState:
    """A board and its remaining candidates, kept in sync.

    Coordinates are zero-based. Filled cells have no candidates. Candidate
    eliminations persist until the state is discarded; speculative search
    should use ``copy()`` instead of clearing previously placed values.

    This class enforces Sudoku constraints but does not *prove* that a requested
    elimination or placement is logically entailed. The future deduction
    engine will be responsible for supplying and verifying justifications.
    """

    def __init__(self, board: SudokuBoard) -> None:
        if not isinstance(board, SudokuBoard):
            raise TypeError("board must be a SudokuBoard")
        self._board = board.copy()
        self._candidates: dict[Cell, set[int]] = {}
        for r in range(SudokuBoard.SIZE):
            for c in range(SudokuBoard.SIZE):
                if self._board.value_at(r, c) == 0:
                    self._candidates[(r, c)] = {
                        digit for digit in SudokuBoard.DIGITS
                        if self._board.can_place(r, c, digit)
                    }
        self._assert_consistent()

    @property
    def board(self) -> SudokuBoard:
        """Return an independent snapshot; external mutations cannot desync us."""
        return self._board.copy()

    def candidates_at(self, row: int, col: int) -> frozenset[int]:
        """Return candidates for an empty cell, or an empty set if filled."""
        SudokuBoard._check_cell(row, col)
        return frozenset(self._candidates.get((row, col), ()))

    def unsolved_cells(self) -> tuple[Cell, ...]:
        """Return empty cells in row-major order."""
        return tuple(self._candidates)

    def _units(self) -> tuple[tuple[Cell, ...], ...]:
        rows = [tuple((r, c) for c in range(9)) for r in range(9)]
        cols = [tuple((r, c) for r in range(9)) for c in range(9)]
        boxes = [
            tuple((r, c) for r in range(br, br + 3) for c in range(bc, bc + 3))
            for br in (0, 3, 6) for bc in (0, 3, 6)
        ]
        return tuple(rows + cols + boxes)

    def _assert_consistent(self) -> None:
        """Reject empty candidate sets and digits with no place in a unit."""
        if any(not candidates for candidates in self._candidates.values()):
            raise CandidateContradiction("Contradiction: an empty cell has no candidates")
        for index, unit in enumerate(self._units()):
            placed = {self._board.value_at(*cell) for cell in unit} - {0}
            for digit in SudokuBoard.DIGITS - placed:
                if not any(digit in self._candidates.get(cell, ()) for cell in unit):
                    name = ('row', 'column', 'box')[index // 9]
                    raise CandidateContradiction(
                        f"Contradiction: digit {digit} has no possible position in {name} {index % 9 + 1}"
                    )

    def eliminate(self, row: int, col: int, digit: int) -> bool:
        """Remove one candidate, checking immediate consistency.

        Return True if removed, False if already absent. Raises ValueError if
        this would leave a cell or unit without any legal completion.
        Does not establish that the elimination is *logically justified*.
        """
        SudokuBoard._check_cell(row, col)
        if type(digit) is not int or digit not in SudokuBoard.DIGITS:
            raise ValueError("digit must be an integer from 1 to 9")
        cell = (row, col)
        if cell not in self._candidates or digit not in self._candidates[cell]:
            return False
        self._candidates[cell].remove(digit)
        try:
            self._assert_consistent()
        except CandidateContradiction as exc:
            exc.state = self.copy()
            self._candidates[cell].add(digit)
            raise
        return True

    def place(self, row: int, col: int, digit: int) -> None:
        """Place a current candidate and propagate peer eliminations atomically.

        The candidate must be currently available, not merely locally legal.
        This operation does not itself prove the placement is forced.
        """
        SudokuBoard._check_cell(row, col)
        if digit not in self.candidates_at(row, col):
            raise ValueError(f"Digit {digit!r} is not a candidate at ({row}, {col})")
        next_board = self._board.copy()
        next_board.place(row, col, digit)
        next_candidates = {cell: choices.copy() for cell, choices in self._candidates.items()}
        del next_candidates[(row, col)]
        for (r, c), choices in next_candidates.items():
            if r == row or c == col or (r // 3, c // 3) == (row // 3, col // 3):
                choices.discard(digit)
        original_board, original_candidates = self._board, self._candidates
        self._board, self._candidates = next_board, next_candidates
        try:
            self._assert_consistent()
        except CandidateContradiction as exc:
            exc.state = self.copy()
            self._board, self._candidates = original_board, original_candidates
            raise

    def copy(self) -> CandidateState:
        """Return a fully independent copy, including prior eliminations."""
        clone = object.__new__(CandidateState)
        clone._board = self._board.copy()
        clone._candidates = {cell: choices.copy() for cell, choices in self._candidates.items()}
        return clone

    def is_complete(self) -> bool:
        return self._board.is_complete()

    def __repr__(self) -> str:
        return f"CandidateState(board={self._board!r}, unsolved={len(self._candidates)})"
