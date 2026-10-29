"""Sudoku constraint propagation and deterministic, configurable DFS search.

Unlike the independent :mod:`reference` oracle, this solver can resume from a
``CandidateState``, preserving every candidate elimination made by the logical
solver.  It does not invoke human techniques or the deduction verifier.

Domains are nine-bit integers. Constraint propagation enforces peer inequality
and the unit requirement that each digit has at least one possible position,
including naked and hidden singles. Search copies domains at branch points;
the input board and candidate state are never changed.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import perf_counter

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState

_ALL = (1 << 9) - 1
_UNITS = (
    tuple(tuple(9 * r + c for c in range(9)) for r in range(9))
    + tuple(tuple(9 * r + c for r in range(9)) for c in range(9))
    + tuple(
        tuple(9 * r + c for r in range(br, br + 3) for c in range(bc, bc + 3))
        for br in (0, 3, 6) for bc in (0, 3, 6)
    )
)
_PEERS = tuple(
    tuple(sorted({j for unit in _UNITS if i in unit for j in unit if j != i}))
    for i in range(81)
)


@dataclass(frozen=True, slots=True)
class PropagationStatistics:
    """Deterministic counters, except for elapsed wall-clock time.

    ``nodes`` counts visits to DFS states, including dead ends and solutions.
    ``decisions`` counts speculative branches attempted (not forced singles).
    ``propagations`` counts domains reduced to one value by a forced deduction,
    excluding initial clues and branch decisions (including failed branches).
    ``backtracks`` counts attempted branches yielding no new solution.
    ``max_depth`` is the maximum number of nested speculative decisions.
    """

    nodes: int
    decisions: int
    propagations: int
    backtracks: int
    max_depth: int
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class PropagationResult:
    """Up to ``limit`` completed grids and whether the search was exhaustive.

    When a positive solution limit is reached, ``exhaustive`` is False even
    if the last possible branch was just visited. Therefore ``limit=1`` never
    proves uniqueness; use the default ``limit=2`` for that purpose.
    """

    solutions: tuple[str, ...]
    exhaustive: bool
    statistics: PropagationStatistics

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


class PropagationSolver:
    """Constraint propagator with DFS, variable ordering, and value ordering.

    ``variable_heuristic`` is ``mrv`` (fewest candidates, row-major ties),
    ``mrv_degree`` (MRV, then most unresolved peers), or ``first`` (row-major).
    ``value_heuristic`` is ``ascending`` or ``lcv`` (least constraining value).

    Input may be an 81-character puzzle, ``SudokuBoard``, or a ``CandidateState``.
    A CandidateState represents additional constraints from prior deductions.
    These eliminations are *assumed sound*, not re-verified here; the independent
    ReferenceSolver must continue to validate deductions from original clues.
    """

    def __init__(self, *, variable_heuristic: str = "mrv", value_heuristic: str = "ascending") -> None:
        if variable_heuristic not in ("mrv", "mrv_degree", "first"):
            raise ValueError("variable_heuristic must be 'mrv', 'mrv_degree', or 'first'")
        if value_heuristic not in ("ascending", "lcv"):
            raise ValueError("value_heuristic must be 'ascending' or 'lcv'")
        self.variable_heuristic = variable_heuristic
        self.value_heuristic = value_heuristic

    @staticmethod
    def _domains(puzzle: SudokuBoard | CandidateState | str) -> list[int]:
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

        domains: list[int] = []
        for row in range(9):
            for col in range(9):
                digit = board.value_at(row, col)
                if digit:
                    domains.append(1 << (digit - 1))
                else:
                    choices = (state.candidates_at(row, col) if state is not None
                               else (d for d in range(1, 10) if board.can_place(row, col, d)))
                    mask = 0
                    for candidate in choices:
                        mask |= 1 << (candidate - 1)
                    domains.append(mask)
        return domains

    def analyze(self, puzzle: SudokuBoard | CandidateState | str, *, limit: int = 2) -> PropagationResult:
        """Find up to ``limit`` solutions without modifying the supplied input."""
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        domains = self._domains(puzzle)
        start = perf_counter()
        solutions: list[str] = []
        nodes = decisions = propagations = backtracks = max_depth = 0
        truncated = False

        def propagate(state: list[int]) -> bool:
            nonlocal propagations
            # Any singleton acts as an assigned value. Process each just once
            # until all peer domains are consistent; then check all units.
            if any(mask == 0 for mask in state):
                return False
            pending = deque(i for i, mask in enumerate(state) if mask.bit_count() == 1)
            processed: set[int] = set()
            while True:
                while pending:
                    cell = pending.popleft()
                    if cell in processed:
                        continue
                    processed.add(cell)
                    bit = state[cell]
                    for peer in _PEERS[cell]:
                        original = state[peer]
                        if original & bit:
                            reduced = original & ~bit
                            if not reduced:
                                return False
                            state[peer] = reduced
                            if reduced.bit_count() == 1:
                                propagations += 1
                                pending.append(peer)
                # A unit with no position for some digit is contradictory.
                # A digit with one position forces that position (hidden single).
                added = False
                for unit in _UNITS:
                    for bit_index in range(9):
                        bit = 1 << bit_index
                        location = -1
                        for cell in unit:
                            if state[cell] & bit:
                                if location != -1:
                                    location = -2  # multiple possible positions
                                    break
                                location = cell
                        if location == -1:
                            return False
                        if location >= 0 and state[location] != bit:
                            state[location] = bit
                            propagations += 1
                            pending.append(location)
                            added = True
                if not added:
                    return True

        def choose_variable(state: list[int]) -> int:
            if self.variable_heuristic == "first":
                return next(i for i, mask in enumerate(state) if mask.bit_count() > 1)
            unresolved = (i for i, mask in enumerate(state) if mask.bit_count() > 1)
            if self.variable_heuristic == "mrv":
                return min(unresolved, key=lambda i: (state[i].bit_count(), i))
            return min(unresolved, key=lambda i: (
                state[i].bit_count(),
                -sum(state[peer].bit_count() > 1 for peer in _PEERS[i]),
                i,
            ))

        def ordered_values(state: list[int], cell: int) -> list[int]:
            bits = [1 << i for i in range(9) if state[cell] & (1 << i)]
            if self.value_heuristic == "lcv":
                bits.sort(key=lambda bit: (
                    sum(bool(state[peer] & bit) for peer in _PEERS[cell]
                        if state[peer].bit_count() > 1),
                    bit,
                ))
            return bits

        def search(state: list[int], depth: int) -> None:
            nonlocal nodes, decisions, backtracks, max_depth, truncated
            nodes += 1
            max_depth = max(max_depth, depth)
            if not propagate(state):
                return
            if all(mask.bit_count() == 1 for mask in state):
                solutions.append("".join(str(mask.bit_length()) for mask in state))
                if len(solutions) >= limit:
                    truncated = True
                return

            cell = choose_variable(state)
            for bit in ordered_values(state, cell):
                if truncated:
                    break
                decisions += 1
                previous_count = len(solutions)
                branch = state.copy()
                branch[cell] = bit
                search(branch, depth + 1)
                if len(solutions) == previous_count:
                    backtracks += 1

        search(domains, 0)
        return PropagationResult(
            tuple(solutions), not truncated,
            PropagationStatistics(nodes, decisions, propagations, backtracks,
                                  max_depth, perf_counter() - start),
        )

    def solve(self, puzzle: SudokuBoard | CandidateState | str) -> SudokuBoard | None:
        """Return one solved board or None when the input is unsatisfiable."""
        return self.analyze(puzzle, limit=1).first_solution

    def count_solutions(self, puzzle: SudokuBoard | CandidateState | str, *, limit: int = 2) -> int:
        """Count solutions up to a positive cap (not necessarily exhaustively)."""
        return self.analyze(puzzle, limit=limit).solution_count
