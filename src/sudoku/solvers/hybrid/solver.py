"""Coordinate verified human-logic deductions with optional exact search.

Three modes have intentionally different semantics:

* logical: human-style deductions only; the result may be STUCK or STEP_LIMIT;
* constraint: immediately run the selected mathematical solver;
* hybrid: run human logic first, then fall back only on STUCK (or explicitly
  on STEP_LIMIT if the caller opts in).

The logical solver owns the only explainable deduction trace. Constraint search
returns a solution and search statistics, not fabricated human deductions.
Its input is the *entire* logical CandidateState, retaining all eliminations.
The independent reference backend accepts exclusions via its ``forbidden``
assumptions. The coordinator translates excluded candidates explicitly, rather
than passing a CandidateState to its clue-only dispatcher.

This module does not import or modify application/UI code.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.solvers.constraint import ConstraintSolver
from sudoku.solvers.constraint.exact_cover import ExactCoverResult
from sudoku.solvers.constraint.integer_programming import IntegerProgrammingResult
from sudoku.solvers.constraint.propagation import PropagationResult
from sudoku.solvers.constraint.reference import ReferenceResult
from sudoku.solvers.logical.solver import LogicalSolver, SolveResult, SolveStatus, SolveStep


ConstraintResult = ReferenceResult | PropagationResult | ExactCoverResult | IntegerProgrammingResult


class SolveMode(str, Enum):
    """Which solving stages the coordinator should execute."""

    LOGICAL = "logical"
    CONSTRAINT = "constraint"
    HYBRID = "hybrid"


class HybridStatus(str, Enum):
    """Final outcome; STUCK and STEP_LIMIT are not claims of unsatisfiability."""

    SOLVED = "solved"
    STUCK = "stuck"
    STEP_LIMIT = "step_limit"
    UNSATISFIABLE = "unsatisfiable"


@dataclass(frozen=True, slots=True)
class HybridResult:
    """Snapshots of the solving phases and the chosen completion, if any.

    ``steps`` contains exclusively verified human deductions. Algorithmic
    placements are *not* inserted into it. ``handoff_state`` is the logical
    state at which fallback started (None when no fallback occurred). ``state``
    is the final snapshot, including any mathematical completion. All original
    givens are retained when completing the board.

    ``constraint_result`` is None if no search ran. Exact solution counting and
    uniqueness information are meaningful only when this field is present;
    solving by logical steps alone does not certify uniqueness.
    """

    mode: SolveMode
    status: HybridStatus
    state: CandidateState
    logical_result: SolveResult | None
    constraint_result: ConstraintResult | None
    handoff_state: CandidateState | None
    completed_by: str | None
    constraint_algorithm: str

    @property
    def solved(self) -> bool:
        return self.status is HybridStatus.SOLVED

    @property
    def first_solution(self) -> SudokuBoard | None:
        return self.state.board if self.solved else None

    @property
    def steps(self) -> tuple[SolveStep, ...]:
        return self.logical_result.steps if self.logical_result is not None else ()

    @property
    def used_fallback(self) -> bool:
        return self.logical_result is not None and self.constraint_result is not None

    @property
    def solution_count(self) -> int | None:
        """Number found by the constraint backend, or None if not queried."""
        return self.constraint_result.solution_count if self.constraint_result is not None else None

    @property
    def is_unique(self) -> bool | None:
        """None if uniqueness was not checked (logical-only completion)."""
        return self.constraint_result.is_unique if self.constraint_result is not None else None


class HybridSolver:
    """Configure a backend-only solving policy independently from the UI.

    ``mode`` chooses human logic, mathematical search, or logical-first fallback.
    ``constraint_algorithm`` is one of 'reference', 'propagation', 'exact_cover',
    or 'integer_programming'. ``logical_solver`` may be a configured LogicalSolver
    instance with a restricted technique set; the default uses its full set.

    ``fallback_on_step_limit=False`` deliberately prevents an artificial step
    cap from triggering search. With True, reaching the cap is an intentional
    handoff even when additional logical deductions may still be available.
    """

    def __init__(
        self,
        *,
        mode: SolveMode | str = SolveMode.HYBRID,
        constraint_algorithm: str = "propagation",
        variable_heuristic: str = "mrv",
        value_heuristic: str = "ascending",
        logical_solver: LogicalSolver | None = None,
        fallback_on_step_limit: bool = False,
    ) -> None:
        try:
            self.mode = SolveMode(mode)
        except (ValueError, TypeError) as exc:
            raise ValueError("mode must be 'logical', 'constraint', or 'hybrid'") from exc
        if logical_solver is not None and not isinstance(logical_solver, LogicalSolver):
            raise TypeError("logical_solver must be a LogicalSolver or None")
        if type(fallback_on_step_limit) is not bool:
            raise TypeError("fallback_on_step_limit must be a bool")

        # Validate the algorithm and its heuristics at construction, even in
        # logical mode, so a later policy change cannot conceal bad settings.
        self.constraint_solver = ConstraintSolver(
            algorithm=constraint_algorithm,
            variable_heuristic=variable_heuristic,
            value_heuristic=value_heuristic,
        )
        self.logical_solver = logical_solver if logical_solver is not None else LogicalSolver()
        self.fallback_on_step_limit = fallback_on_step_limit
        self.constraint_algorithm = constraint_algorithm

    @staticmethod
    def _initial_state(puzzle: SudokuBoard | CandidateState | str) -> CandidateState:
        if isinstance(puzzle, CandidateState):
            return puzzle.copy()
        if isinstance(puzzle, SudokuBoard):
            return CandidateState(puzzle)
        if isinstance(puzzle, str):
            return CandidateState(SudokuBoard.from_string(puzzle))
        raise TypeError("puzzle must be a SudokuBoard, CandidateState, or 81-character string")

    def _run_constraint(self, state: CandidateState, limit: int) -> ConstraintResult:
        """Forward the complete constraint state to the selected backend.

        The reference solver intentionally does not accept CandidateState.
        Instead translate its extra eliminations into explicit forbidden
        assumptions, leaving the original solver and facade unchanged. These
        assumptions are provided *as constraints*, not asserted to be proven
        independently by the reference oracle.
        """
        if self.constraint_algorithm != "reference":
            return self.constraint_solver.analyze(state, limit=limit)

        board = state.board
        forbidden = tuple(
            (r, c, digit)
            for r, c in state.unsolved_cells()
            for digit in range(1, 10)
            if board.can_place(r, c, digit)
            and digit not in state.candidates_at(r, c)
        )
        return self.constraint_solver.backend.analyze(
            board, limit=limit, forbidden=forbidden,
        )

    @staticmethod
    def _apply_solution(state: CandidateState, solution: SudokuBoard) -> CandidateState:
        """Construct a final state retaining original givens and domain history.

        Search is authoritative for the *completion*, not for an explanation.
        Placing these values does not create a human-technique deduction trace.
        """
        completed = state.copy()
        for r, c in completed.unsolved_cells():
            digit = solution.value_at(r, c)
            if digit not in completed.candidates_at(r, c):
                raise RuntimeError("Constraint backend produced a solution violating the candidate state")
            completed.place(r, c, digit)
        if not completed.is_complete():
            raise RuntimeError("Constraint backend returned an incomplete solution")
        return completed

    def solve(
        self,
        puzzle: SudokuBoard | CandidateState | str,
        *,
        max_logical_steps: int | None = None,
        solution_limit: int = 2,
    ) -> HybridResult:
        """Run the configured stages, without mutating the caller's puzzle.

        A limit of 2 allows mathematical search to establish uniqueness or
        multiple solutions; limit=1 provides only a feasible completion.
        Logical-only mode never invokes a constraint solver. Constraint-only
        mode never invokes the logical solver. In hybrid mode, a logical STUCK
        status triggers fallback, while STEP_LIMIT does so only if configured.
        """
        if type(solution_limit) is not int or solution_limit < 1:
            raise ValueError("solution_limit must be a positive integer")
        if max_logical_steps is not None and (type(max_logical_steps) is not int or max_logical_steps < 0):
            raise ValueError("max_logical_steps must be a nonnegative integer or None")
        if self.mode is SolveMode.CONSTRAINT and max_logical_steps is not None:
            raise ValueError("max_logical_steps applies only to logical or hybrid modes")

        state = self._initial_state(puzzle)
        logical_result: SolveResult | None = None
        if self.mode is not SolveMode.CONSTRAINT:
            logical_result = self.logical_solver.solve(state, max_steps=max_logical_steps)
            state = logical_result.state.copy()
            if logical_result.status is SolveStatus.SOLVED:
                return HybridResult(
                    self.mode, HybridStatus.SOLVED, state, logical_result,
                    None, None, "logical", self.constraint_algorithm,
                )
            if (self.mode is SolveMode.LOGICAL
                    or (logical_result.status is SolveStatus.STEP_LIMIT
                        and not self.fallback_on_step_limit)):
                status = (HybridStatus.STUCK if logical_result.status is SolveStatus.STUCK
                          else HybridStatus.STEP_LIMIT)
                return HybridResult(
                    self.mode, status, state, logical_result,
                    None, None, None, self.constraint_algorithm,
                )

        handoff = state.copy() if logical_result is not None else None
        constraint_result = self._run_constraint(state, solution_limit)
        solution = constraint_result.first_solution
        if solution is None:
            if not constraint_result.is_unsatisfiable:
                raise RuntimeError("Constraint search stopped without a solution or an infeasibility proof")
            return HybridResult(
                self.mode, HybridStatus.UNSATISFIABLE, state, logical_result,
                constraint_result, handoff, None, self.constraint_algorithm,
            )

        completed = self._apply_solution(state, solution)
        return HybridResult(
            self.mode, HybridStatus.SOLVED, completed, logical_result,
            constraint_result, handoff, "constraint", self.constraint_algorithm,
        )
