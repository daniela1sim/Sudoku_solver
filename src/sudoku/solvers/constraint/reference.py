"""Independent, exact Sudoku reference solver using MRV and bitmask backtracking.

This module deliberately depends only on ``SudokuBoard`` and Python's standard
library. In particular, it never consults ``CandidateState``, human techniques,
or ``DeductionVerifier``. It can therefore act as a separate correctness oracle.

All searches are deterministic. Solution counts are *capped*: finding two
solutions proves non-uniqueness, but ``limit=1`` cannot establish uniqueness.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Iterable, TypeAlias

from sudoku.core.board import SudokuBoard

Assignment: TypeAlias = tuple[int, int, int]
_ALL = (1 << 9) - 1
_BOX = tuple((i // 27) * 3 + (i % 9) // 3 for i in range(81))


@dataclass(frozen=True, slots=True)
class SearchStatistics:
    """Counters for a single reference search, including its elapsed time."""

    nodes: int
    branches: int
    dead_ends: int
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class ReferenceResult:
    """Solutions and search metadata.

    ``solutions`` contains at most ``limit`` completed 81-character grids.
    ``exhaustive`` is False whenever we stopped at the solution limit.
    An unsatisfiable puzzle has zero solutions and an exhaustive search.
    """

    solutions: tuple[str, ...]
    exhaustive: bool
    statistics: SearchStatistics

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


class ReferenceSolver:
    """A standalone classic-Sudoku exact solver using MRV and bitmasks.

    ``forced`` and ``forbidden`` are optional (row, column, digit) assumptions.
    They let a future verifier query whether a proposed move follows from the
    *original clues*. Contradictory assumptions return an unsatisfiable result;
    malformed arguments raise ValueError/TypeError instead.

    Note that this solver does not model already eliminated candidates, unless
    they are supplied explicitly as ``forbidden`` assumptions. That separation
    is deliberate: trusting a logical solver's candidate state would undermine
    its independence as a correctness oracle.
    """

    @staticmethod
    def _board(puzzle: SudokuBoard | str) -> SudokuBoard:
        if isinstance(puzzle, SudokuBoard):
            return puzzle.copy()
        if isinstance(puzzle, str):
            return SudokuBoard.from_string(puzzle)
        raise TypeError("puzzle must be a SudokuBoard or an 81-character string")

    @staticmethod
    def _assumptions(values: Iterable[Assignment], name: str) -> tuple[Assignment, ...]:
        try:
            entries = tuple(values)
        except TypeError as exc:
            raise TypeError(f"{name} must be an iterable of (row, column, digit)") from exc
        for item in entries:
            if not isinstance(item, (tuple, list)) or len(item) != 3:
                raise ValueError(f"{name} entries must be (row, column, digit) triples")
            r, c, d = item
            if any(type(v) is not int for v in (r, c, d)) or not (0 <= r < 9 and 0 <= c < 9 and 1 <= d <= 9):
                raise ValueError(f"{name} coordinates must be 0..8 and digits 1..9")
        return entries

    def analyze(
        self,
        puzzle: SudokuBoard | str,
        *,
        limit: int = 2,
        forced: Iterable[Assignment] = (),
        forbidden: Iterable[Assignment] = (),
    ) -> ReferenceResult:
        """Return up to ``limit`` solutions, with MRV search statistics.

        ``limit=2`` is sufficient to decide unsatisfiable/unique/non-unique
        for a fully explored search or when at least two solutions are found.
        An intermediate positive count on a truncated search is a lower bound.
        """
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        board = self._board(puzzle)
        forced_moves = self._assumptions(forced, "forced")
        forbidden_moves = self._assumptions(forbidden, "forbidden")

        start = perf_counter()
        cells = [value for row in board.to_list() for value in row]
        row_bits = [0] * 9
        col_bits = [0] * 9
        box_bits = [0] * 9
        denied = [0] * 81
        contradiction = False

        for i, digit in enumerate(cells):
            if digit:
                bit = 1 << (digit - 1)
                r, c, b = i // 9, i % 9, _BOX[i]
                # SudokuBoard already checks this, but this guard keeps the
                # search independent from its validation implementation.
                if row_bits[r] & bit or col_bits[c] & bit or box_bits[b] & bit:
                    contradiction = True
                    break
                row_bits[r] |= bit
                col_bits[c] |= bit
                box_bits[b] |= bit

        for r, c, digit in forbidden_moves:
            i = 9 * r + c
            bit = 1 << (digit - 1)
            denied[i] |= bit
            if cells[i] == digit:
                contradiction = True

        # Handle forced assignments without modifying SudokuBoard, including
        # mutually contradictory forcing assumptions.
        force_map: dict[int, int] = {}
        for r, c, digit in forced_moves:
            i = 9 * r + c
            if i in force_map and force_map[i] != digit:
                contradiction = True
            force_map[i] = digit
        for i, digit in force_map.items():
            bit = 1 << (digit - 1)
            if denied[i] & bit or cells[i] not in (0, digit):
                contradiction = True
                continue
            if cells[i] == digit:
                continue
            r, c, b = i // 9, i % 9, _BOX[i]
            if row_bits[r] & bit or col_bits[c] & bit or box_bits[b] & bit:
                contradiction = True
                continue
            cells[i] = digit
            row_bits[r] |= bit
            col_bits[c] |= bit
            box_bits[b] |= bit

        if contradiction:
            return ReferenceResult((), True, SearchStatistics(0, 0, 0, perf_counter() - start))

        solutions: list[str] = []
        nodes = branches = dead_ends = 0
        truncated = False

        def search() -> None:
            nonlocal nodes, branches, dead_ends, truncated
            nodes += 1
            best_index = -1
            best_mask = 0
            best_count = 10
            for i, current in enumerate(cells):
                if current:
                    continue
                mask = _ALL & ~(row_bits[i // 9] | col_bits[i % 9] | box_bits[_BOX[i]] | denied[i])
                count = mask.bit_count()
                if count == 0:
                    dead_ends += 1
                    return
                if count < best_count:
                    best_index, best_mask, best_count = i, mask, count
                    if count == 1:
                        break
            if best_index == -1:
                solutions.append("".join(str(d) for d in cells))
                if len(solutions) >= limit:
                    truncated = True
                return

            r, c, b = best_index // 9, best_index % 9, _BOX[best_index]
            while best_mask:
                bit = best_mask & -best_mask
                best_mask ^= bit
                digit = bit.bit_length()
                branches += 1
                cells[best_index] = digit
                row_bits[r] |= bit
                col_bits[c] |= bit
                box_bits[b] |= bit
                search()
                cells[best_index] = 0
                row_bits[r] ^= bit
                col_bits[c] ^= bit
                box_bits[b] ^= bit
                if truncated:
                    return

        search()
        return ReferenceResult(
            tuple(solutions),
            not truncated,
            SearchStatistics(nodes, branches, dead_ends, perf_counter() - start),
        )

    def solve(self, puzzle: SudokuBoard | str) -> SudokuBoard | None:
        """Return one valid completed board, or None if unsatisfiable."""
        return self.analyze(puzzle, limit=1).first_solution

    def count_solutions(self, puzzle: SudokuBoard | str, *, limit: int = 2) -> int:
        """Return the number of solutions found, capped at ``limit``."""
        return self.analyze(puzzle, limit=limit).solution_count

    def has_solution(
        self,
        puzzle: SudokuBoard | str,
        *,
        forced: Iterable[Assignment] = (),
        forbidden: Iterable[Assignment] = (),
    ) -> bool:
        """Test satisfiability under additional placements/exclusions."""
        return self.analyze(puzzle, limit=1, forced=forced, forbidden=forbidden).has_solution

    def allows_candidate(self, puzzle: SudokuBoard | str, row: int, col: int, digit: int) -> bool:
        """Whether *some* completion assigns digit to the specified cell."""
        return self.has_solution(puzzle, forced=((row, col, digit),))

    def forces_placement(self, puzzle: SudokuBoard | str, row: int, col: int, digit: int) -> bool:
        """Whether every completion assigns digit to this cell (non-vacuously)."""
        # Calling analyze first prevents calling an unsatisfiable puzzle a proof.
        if not self.allows_candidate(puzzle, row, col, digit):
            return False
        return not self.has_solution(puzzle, forbidden=((row, col, digit),))

    def proves_elimination(self, puzzle: SudokuBoard | str, row: int, col: int, digit: int) -> bool:
        """Whether no completion contains this candidate (non-vacuously)."""
        return self.has_solution(puzzle) and not self.allows_candidate(puzzle, row, col, digit)
