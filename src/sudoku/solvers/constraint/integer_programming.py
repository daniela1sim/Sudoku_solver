"""Sudoku as a binary integer linear program (MILP), using SciPy/HiGHS.

The binary variable x[r,c,d] means digit d occurs in cell (r,c).
Each variable participates in four of the 324 exact-cover equalities:
one digit per cell, and each digit once per row, column, and box.

Unlike Algorithm X, this implementation delegates feasibility to a general
mixed-integer programming backend. It does not call any other Sudoku solver.
SciPy is deliberately optional: install ``pip install -e '.[milp]'`` to use it.

To enumerate distinct completions, exclude each found 81-variable solution
with a no-good inequality. Search is exhaustive only if HiGHS proves that the
remaining model is infeasible; reaching ``limit`` is not such a proof.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from time import perf_counter

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState

_NUM_VARIABLES = 729
_NUM_EQUALITIES = 324


@dataclass(frozen=True, slots=True)
class IntegerProgrammingStatistics:
    """Metrics for a complete ``analyze()`` invocation.

    ``milp_calls`` includes the final infeasibility proof when performed.
    ``no_good_cuts`` counts cuts actually applied during MILP calls; when
    the requested solution cap is reached, no final infeasibility call runs.
    ``mip_nodes`` is the sum of branch-and-bound nodes reported by HiGHS, or
    None if no calls reported that metric. It is *not* comparable with DFS nodes
    in the reference, propagation, or exact-cover backends.
    """

    milp_calls: int
    no_good_cuts: int
    mip_nodes: int | None
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class IntegerProgrammingResult:
    """Enumerated completed grids, with exact capped-count semantics."""

    solutions: tuple[str, ...]
    exhaustive: bool
    statistics: IntegerProgrammingStatistics

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


@lru_cache(maxsize=1)
def _constraint_matrix():
    """Build the immutable 324x729 sparse Sudoku incidence matrix lazily.

    Lazy loading keeps SciPy an optional dependency for all other backends.
    Each column contains exactly four ones. The CSR matrix is never mutated.
    """
    try:
        from scipy.sparse import coo_matrix
    except ImportError as exc:
        raise ImportError(
            "The integer_programming backend requires SciPy. "
            "Install it with: pip install -e '.[milp]'"
        ) from exc

    rows: list[int] = []
    cols: list[int] = []
    for cell in range(81):
        r, c = divmod(cell, 9)
        box = (r // 3) * 3 + c // 3
        for d in range(9):
            variable = cell * 9 + d
            rows.extend((cell, 81 + r * 9 + d, 162 + c * 9 + d, 243 + box * 9 + d))
            cols.extend((variable,) * 4)
    return coo_matrix(([1.0] * len(rows), (rows, cols)),
                      shape=(_NUM_EQUALITIES, _NUM_VARIABLES)).tocsr()


class IntegerProgrammingSolver:
    """Find Sudoku solutions using binary MILP feasibility via SciPy/HiGHS.

    Accepts SudokuBoard, 81-character puzzle strings, or CandidateState.
    For CandidateState, all previously justified candidate exclusions are
    enforced as variable upper bounds. Inputs are never modified.

    Results are deterministic in validity and solution *count*, but the first
    solution of a nonunique puzzle need not match search-based algorithms.
    """

    @staticmethod
    def _variable_bounds(puzzle: SudokuBoard | CandidateState | str):
        try:
            import numpy as np
        except ImportError as exc:
            raise ImportError(
                "The integer_programming backend requires SciPy and NumPy. "
                "Install them with: pip install -e '.[milp]'"
            ) from exc

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

        lower = np.zeros(_NUM_VARIABLES, dtype=float)
        upper = np.zeros(_NUM_VARIABLES, dtype=float)
        for r in range(9):
            for c in range(9):
                cell = 9 * r + c
                digit = board.value_at(r, c)
                if digit:
                    index = cell * 9 + digit - 1
                    lower[index] = 1.0
                    upper[index] = 1.0
                else:
                    choices = (state.candidates_at(r, c) if state is not None
                               else (d for d in range(1, 10) if board.can_place(r, c, d)))
                    for d in choices:
                        upper[cell * 9 + d - 1] = 1.0
        return board, state, lower, upper

    def analyze(self, puzzle: SudokuBoard | CandidateState | str, *, limit: int = 2) -> IntegerProgrammingResult:
        """Find at most ``limit`` completions, proving uniqueness if possible.

        If HiGHS returns a limit/error status instead of feasible or provably
        infeasible, raise RuntimeError rather than misreporting unsatisfiability.
        """
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")

        try:
            import numpy as np
            from scipy.optimize import Bounds, LinearConstraint, milp
            from scipy.sparse import csr_matrix
        except ImportError as exc:
            raise ImportError(
                "The integer_programming backend requires SciPy and NumPy. "
                "Install them with: pip install -e '.[milp]'"
            ) from exc

        board, state, lower, upper = self._variable_bounds(puzzle)
        start = perf_counter()
        base_matrix = _constraint_matrix()
        original_constraints = LinearConstraint(
            base_matrix, np.ones(_NUM_EQUALITIES), np.ones(_NUM_EQUALITIES)
        )
        objective = np.zeros(_NUM_VARIABLES)
        integrality = np.ones(_NUM_VARIABLES, dtype=int)
        bounds = Bounds(lower, upper)
        solutions: list[str] = []
        excluded: list[tuple[int, ...]] = []
        nodes_seen = 0
        nodes_available = False
        calls = 0
        exhaustive = False

        while len(solutions) < limit:
            constraints = [original_constraints]
            if excluded:
                # Each cut forbids all 81 placements of a previously found
                # completion from being chosen together again.
                row_indices = [i for i, selected in enumerate(excluded) for _ in selected]
                column_indices = [column for selected in excluded for column in selected]
                cut_matrix = csr_matrix(
                    (np.ones(len(column_indices)), (row_indices, column_indices)),
                    shape=(len(excluded), _NUM_VARIABLES),
                )
                constraints.append(LinearConstraint(
                    cut_matrix, np.full(len(excluded), -np.inf),
                    np.full(len(excluded), 80.0),
                ))

            result = milp(
                c=objective,
                integrality=integrality,
                bounds=bounds,
                constraints=constraints,
                options={"disp": False},
            )
            calls += 1
            count = getattr(result, "mip_node_count", None)
            if count is not None:
                nodes_seen += int(count)
                nodes_available = True

            if result.status == 2:  # HiGHS proves the remaining MILP infeasible.
                exhaustive = True
                break
            if result.status != 0 or result.x is None:
                raise RuntimeError(
                    f"MILP solver could not establish feasibility/infeasibility "
                    f"(status={result.status}): {result.message}"
                )

            # MILP returns floating point values. Check both integer tolerances
            # and actual Sudoku feasibility, rather than trusting rounding.
            if not np.all(np.isclose(result.x, np.rint(result.x), atol=1e-6, rtol=0)):
                raise RuntimeError("MILP returned a non-integral candidate solution")
            selected = tuple(int(i) for i in np.flatnonzero(result.x > 0.5))
            if len(selected) != 81 or not np.all(base_matrix[:, selected].sum(axis=1) == 1):
                raise RuntimeError("MILP returned a solution violating Sudoku constraints")
            if (np.any(upper[list(selected)] < 1)
                    or np.any(result.x < lower - 1e-6)
                    or np.any(result.x > upper + 1e-6)):
                raise RuntimeError("MILP returned a solution violating variable bounds")
            grid = ['0'] * 81
            for index in selected:
                cell, digit_index = divmod(index, 9)
                grid[cell] = str(digit_index + 1)
            completed = ''.join(grid)
            if (not SudokuBoard.from_string(completed).is_complete()
                    or any(g and completed[i] != str(g)
                           for i, g in enumerate(v for row in board.to_list() for v in row))
                    or (state is not None and any(
                        board.value_at(r, c) == 0
                        and int(completed[9 * r + c]) not in state.candidates_at(r, c)
                        for r in range(9) for c in range(9)))):
                raise RuntimeError("MILP returned a completion inconsistent with its input")
            if completed in solutions:
                raise RuntimeError("MILP returned an already-excluded solution")
            solutions.append(completed)
            excluded.append(selected)

        return IntegerProgrammingResult(
            solutions=tuple(solutions),
            exhaustive=exhaustive,
            statistics=IntegerProgrammingStatistics(
                milp_calls=calls,
                no_good_cuts=max(0, calls - 1),
                mip_nodes=nodes_seen if nodes_available else None,
                elapsed_seconds=perf_counter() - start,
            ),
        )

    def solve(self, puzzle: SudokuBoard | CandidateState | str) -> SudokuBoard | None:
        """Return one valid completion or None for a provably impossible puzzle."""
        return self.analyze(puzzle, limit=1).first_solution

    def count_solutions(self, puzzle: SudokuBoard | CandidateState | str, *, limit: int = 2) -> int:
        """Count distinct completions up to ``limit`` (not necessarily exhaustive)."""
        return self.analyze(puzzle, limit=limit).solution_count
