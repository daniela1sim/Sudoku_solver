"""Mathematical Sudoku solvers, separate from human logical techniques.

``ReferenceSolver`` remains an independent clue-based correctness oracle.
``PropagationSolver`` also accepts candidate-state constraints for hybrid use.
"""

from .reference import ReferenceResult, ReferenceSolver, SearchStatistics
from .propagation import PropagationResult, PropagationSolver, PropagationStatistics
from .solver import ConstraintSolver

__all__ = [
    "ReferenceResult", "ReferenceSolver", "SearchStatistics",
    "PropagationResult", "PropagationSolver", "PropagationStatistics", "ConstraintSolver",
]
