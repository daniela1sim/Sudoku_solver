"""Backend-only selection of mathematical Sudoku solving algorithms.

No UI or logical-solving code depends on this dispatcher. A future hybrid
solver can pass its CandidateState to propagation, exact cover, or MILP
without losing candidate exclusions.
"""

from __future__ import annotations

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from .propagation import PropagationResult, PropagationSolver
from .exact_cover import ExactCoverResult, ExactCoverSolver
from .integer_programming import IntegerProgrammingResult, IntegerProgrammingSolver
from .reference import ReferenceResult, ReferenceSolver


class ConstraintSolver:
    """Select an exact constraint backend without changing application/UI code.

    ``algorithm='reference'`` is available only for clue-based board inputs.
    Propagation, exact cover, and integer programming understand ``CandidateState``.
    Both implementations return a result with solutions, solution_count,
    exhaustive, first_solution, is_unique, and is_unsatisfiable properties.
    """

    def __init__(self, *, algorithm: str = "propagation", variable_heuristic: str = "mrv",
                 value_heuristic: str = "ascending") -> None:
        if algorithm == "reference":
            if variable_heuristic != "mrv" or value_heuristic != "ascending":
                raise ValueError("Search heuristics cannot be configured for the reference solver")
            self.backend = ReferenceSolver()
        elif algorithm == "exact_cover":
            if variable_heuristic != "mrv" or value_heuristic != "ascending":
                raise ValueError("Search heuristics cannot be configured for the exact-cover solver")
            self.backend = ExactCoverSolver()
        elif algorithm == "integer_programming":
            if variable_heuristic != "mrv" or value_heuristic != "ascending":
                raise ValueError("Search heuristics cannot be configured for the integer-programming solver")
            self.backend = IntegerProgrammingSolver()
        elif algorithm == "propagation":
            self.backend = PropagationSolver(variable_heuristic=variable_heuristic,
                                             value_heuristic=value_heuristic)
        else:
            raise ValueError("algorithm must be 'reference', 'propagation', 'exact_cover', or 'integer_programming'")
        self.algorithm = algorithm

    def analyze(self, puzzle: SudokuBoard | CandidateState | str, *, limit: int = 2) -> ReferenceResult | PropagationResult | ExactCoverResult | IntegerProgrammingResult:
        if self.algorithm == "reference" and isinstance(puzzle, CandidateState):
            raise TypeError("reference solver accepts only SudokuBoard or puzzle string")
        return self.backend.analyze(puzzle, limit=limit)

    def solve(self, puzzle: SudokuBoard | CandidateState | str) -> SudokuBoard | None:
        return self.analyze(puzzle, limit=1).first_solution

    def count_solutions(self, puzzle: SudokuBoard | CandidateState | str, *, limit: int = 2) -> int:
        return self.analyze(puzzle, limit=limit).solution_count
