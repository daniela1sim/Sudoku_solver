"""Independent mathematical Sudoku backends (no human-logic coupling)."""

from .reference import ReferenceResult, ReferenceSolver, SearchStatistics
from .propagation import PropagationResult, PropagationSolver, PropagationStatistics
from .exact_cover import ExactCoverResult, ExactCoverSolver, ExactCoverStatistics
from .solver import ConstraintSolver

__all__ = [
    "ReferenceResult", "ReferenceSolver", "SearchStatistics",
    "PropagationResult", "PropagationSolver", "PropagationStatistics",
    "ExactCoverResult", "ExactCoverSolver", "ExactCoverStatistics", "ConstraintSolver",
]
