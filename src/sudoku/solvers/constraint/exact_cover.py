"""Sudoku as exact cover, solved by Knuth's Algorithm X (sparse sets).

Each candidate placement (row, column, digit) covers four constraints:

* one value in each of the 81 cells;
* each digit once in each of the 9 rows;
* each digit once in each of the 9 columns;
* each digit once in each of the 9 boxes.

There are 324 primary constraints and up to 729 candidate rows. Algorithm X
chooses the most constrained uncovered column, selects one compatible row,
and removes all conflicting rows. Reversible cover/uncover operations avoid
copying the entire matrix at every search node.

This implementation does not import logical strategies, propagation code, or
the independent reference oracle. CandidateState eliminations can optionally
restrict the allowed candidate rows (for future hybrid solving), but are
*assumed* valid rather than verified.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState

_NUM_CELLS = 81
_NUM_CONSTRAINTS = 324
_ALL_DIGITS = (1 << 9) - 1


def _columns_for_placement(cell: int, digit_index: int) -> tuple[int, int, int, int]:
    """Four column IDs for cell 0..80 and digit index 0..8."""
    r, c = divmod(cell, 9)
    b = (r // 3) * 3 + c // 3
    return (cell, 81 + r * 9 + digit_index,
            162 + c * 9 + digit_index, 243 + b * 9 + digit_index)


# Row ID = 9 * (9 * row + column) + (digit - 1).
# Immutable, shared lookup tables; searches never change these tuples.
_ROW_COLUMNS = tuple(
    _columns_for_placement(cell, d) for cell in range(_NUM_CELLS) for d in range(9)
)


@dataclass(frozen=True, slots=True)
class ExactCoverStatistics:
    """Counts for Algorithm X search (including failed search branches).

    nodes: recursive states visited, including solutions and contradictions.
    row_selections: candidate rows attempted, including forced selections.
    decisions: rows attempted from a column with >1 compatible row.
    forced_selections: rows selected from a column with exactly one option.
    dead_ends: recursive states with an uncovered zero-option column.
    backtracks: row selections whose subtree produced no new solution.
    max_depth: maximum selected rows on any search path (at most 81).
    elapsed_seconds: time for matrix construction and search, not input parsing.
    """

    nodes: int
    row_selections: int
    decisions: int
    forced_selections: int
    dead_ends: int
    backtracks: int
    max_depth: int
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class ExactCoverResult:
    """Up to ``limit`` solution grids and whether all possibilities were searched.

    A positive solution limit stops search immediately, so ``exhaustive`` is
    False when that cap is reached. In particular, ``limit=1`` never proves
    uniqueness; to establish uniqueness use ``limit=2``.
    """

    solutions: tuple[str, ...]
    exhaustive: bool
    statistics: ExactCoverStatistics

    @property
    def solution_count(self) -> int:
        return len(self.solutions)

    @property
    def has_solution(self) -> bool:
        return bool(self.solutions)

    @property
    def is_unique(self) -> bool:
        return self.exhaustive and len(self.solutions) == 1

    @property
    def is_unsatisfiable(self) -> bool:
        return self.exhaustive and not self.solutions

    @property
    def has_multiple_solutions(self) -> bool:
        return len(self.solutions) >= 2

    @property
    def first_solution(self) -> SudokuBoard | None:
        return SudokuBoard.from_string(self.solutions[0]) if self.solutions else None


class ExactCoverSolver:
    """Deterministic, complete exact-cover solver for standard 9x9 Sudoku.

    Input is an 81-character puzzle, a SudokuBoard, or a CandidateState. For
    CandidateState, both placements and earlier candidate eliminations restrict
    the exact-cover rows. Inputs are never modified.

    The search uses minimum-column-size (Knuth's S heuristic) with lowest
    column ID as a tie-breaker; candidate rows are explored in ascending ID.
    Its heuristic is fixed and does not accept MRV/LCV parameters.
    """

    @staticmethod
    def _allowed_rows(puzzle: SudokuBoard | CandidateState | str) -> list[int]:
        if isinstance(puzzle, str):
            board = SudokuBoard.from_string(puzzle)
            state = None
        elif isinstance(puzzle, CandidateState):
            state = puzzle
            board = state.board
        elif isinstance(puzzle, SudokuBoard):
            board = puzzle
            state = None
        else:
            raise TypeError("puzzle must be a SudokuBoard, CandidateState, or 81-character string")

        values = [digit for row in board.to_list() for digit in row]
        # For unfilled cells, filter candidates using the original placements.
        # This is only a speed optimization: the exact-cover constraints enforce
        # these restrictions anyway. For CandidateState preserve eliminations.
        row_used = [0] * 9
        col_used = [0] * 9
        box_used = [0] * 9
        for cell, digit in enumerate(values):
            if digit:
                r, c = divmod(cell, 9)
                b = (r // 3) * 3 + c // 3
                bit = 1 << (digit - 1)
                row_used[r] |= bit
                col_used[c] |= bit
                box_used[b] |= bit

        allowed: list[int] = []
        for cell, digit in enumerate(values):
            r, c = divmod(cell, 9)
            if digit:
                allowed.append(cell * 9 + digit - 1)
            else:
                b = (r // 3) * 3 + c // 3
                legal = _ALL_DIGITS & ~(row_used[r] | col_used[c] | box_used[b])
                if state is not None:
                    restricted = 0
                    for candidate in state.candidates_at(r, c):
                        restricted |= 1 << (candidate - 1)
                    legal &= restricted
                while legal:
                    bit = legal & -legal
                    allowed.append(cell * 9 + bit.bit_length() - 1)
                    legal ^= bit
        return allowed

    def analyze(self, puzzle: SudokuBoard | CandidateState | str, *, limit: int = 2) -> ExactCoverResult:
        """Enumerate up to ``limit`` solutions and report search statistics."""
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        allowed_rows = self._allowed_rows(puzzle)
        start = perf_counter()
        columns: dict[int, set[int]] = {c: set() for c in range(_NUM_CONSTRAINTS)}
        for row_id in allowed_rows:
            for column in _ROW_COLUMNS[row_id]:
                columns[column].add(row_id)

        chosen: list[int] = []
        solutions: list[str] = []
        nodes = row_selections = decisions = forced_selections = 0
        dead_ends = backtracks = max_depth = 0
        truncated = False

        def cover(row_id: int) -> list[set[int]]:
            """Select one row and remove all incompatible candidate rows.

            The returned sets are the removed column contents; they form an
            undo log and must be restored in reverse order by uncover().
            """
            removed: list[set[int]] = []
            for col in _ROW_COLUMNS[row_id]:
                rows = columns.pop(col)
                removed.append(rows)
                for conflict in rows:
                    for other in _ROW_COLUMNS[conflict]:
                        if other != col:
                            columns[other].remove(conflict)
            return removed

        def uncover(row_id: int, removed: list[set[int]]) -> None:
            """Exactly reverse cover(), including all conflicting rows."""
            for col, rows in zip(reversed(_ROW_COLUMNS[row_id]), reversed(removed)):
                columns[col] = rows
                for conflict in rows:
                    for other in _ROW_COLUMNS[conflict]:
                        if other != col:
                            columns[other].add(conflict)

        def search(depth: int) -> None:
            nonlocal nodes, row_selections, decisions, forced_selections
            nonlocal dead_ends, backtracks, max_depth, truncated
            nodes += 1
            max_depth = max(depth, max_depth)
            if not columns:
                grid = ["0"] * _NUM_CELLS
                for row_id in chosen:
                    cell, digit_index = divmod(row_id, 9)
                    grid[cell] = str(digit_index + 1)
                solutions.append("".join(grid))
                if len(solutions) >= limit:
                    truncated = True
                return

            # Knuth's S heuristic. Sorting on option count then ID makes the
            # algorithm deterministic even though each column stores a set.
            col = min(columns, key=lambda c: (len(columns[c]), c))
            option_count = len(columns[col])
            if option_count == 0:
                dead_ends += 1
                return

            for row_id in sorted(columns[col]):
                if truncated:
                    break
                row_selections += 1
                if option_count == 1:
                    forced_selections += 1
                else:
                    decisions += 1
                before = len(solutions)
                chosen.append(row_id)
                removed = cover(row_id)
                search(depth + 1)
                uncover(row_id, removed)
                chosen.pop()
                if len(solutions) == before:
                    backtracks += 1

        search(0)
        return ExactCoverResult(
            solutions=tuple(solutions),
            exhaustive=not truncated,
            statistics=ExactCoverStatistics(
                nodes=nodes,
                row_selections=row_selections,
                decisions=decisions,
                forced_selections=forced_selections,
                dead_ends=dead_ends,
                backtracks=backtracks,
                max_depth=max_depth,
                elapsed_seconds=perf_counter() - start,
            ),
        )

    def solve(self, puzzle: SudokuBoard | CandidateState | str) -> SudokuBoard | None:
        """Return a completion, or None if the input is unsatisfiable."""
        return self.analyze(puzzle, limit=1).first_solution

    def count_solutions(self, puzzle: SudokuBoard | CandidateState | str, *, limit: int = 2) -> int:
        """Count solutions, capped by ``limit`` (not necessarily exhaustive)."""
        return self.analyze(puzzle, limit=limit).solution_count
