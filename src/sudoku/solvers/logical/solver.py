"""Deterministic orchestration of explainable, human-style Sudoku deductions.

Technique-specific verification lives in verification.py. Additional technique
families need verifier support before they can safely be registered.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from collections.abc import Iterable

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction
from sudoku.solvers.logical.base import LogicalTechnique
from sudoku.solvers.logical.singles import HiddenSingle, NakedSingle
from sudoku.solvers.logical.subsets import (NakedPair, HiddenPair, NakedTriple, HiddenTriple, NakedQuad, HiddenQuad)
from sudoku.solvers.logical.verification import DeductionVerifier
from sudoku.solvers.logical.locked_candidates import Pointing, Claiming
from sudoku.solvers.logical.fish import XWing, Swordfish, Jellyfish
from sudoku.solvers.logical.strong_links import Skyscraper, TwoStringKite, Crane
from sudoku.solvers.logical.wings import XYWing, XYZWing, WWing
from sudoku.solvers.logical.rectangles import EmptyRectangle, UniqueRectangleType1, UniqueRectangleType2, UniqueRectangleType3, UniqueRectangleType4, UniqueRectangleType5, UniqueRectangleType6, HiddenUniqueRectangle
from sudoku.solvers.logical.finned_fish import FinnedXWing, FinnedSwordfish, FinnedJellyfish
from sudoku.solvers.logical.uniqueness import BUGPlusOne
from sudoku.solvers.logical.coloring import SimpleColoring
from sudoku.solvers.logical.remote_pairs import RemotePairs
from sudoku.solvers.logical.x_chains import XChain
from sudoku.solvers.logical.xy_chains import XYChain
from sudoku.solvers.logical.als import ALSXZ
from sudoku.solvers.logical.als_chains import ALSChain
from sudoku.solvers.logical.sue_de_coq import SueDeCoq
from sudoku.solvers.logical.aic import AIC
from sudoku.solvers.logical.grouped_aic import GroupedAIC
from sudoku.solvers.logical.als_aic import ALSAIC


class SolveStatus(str, Enum):
    SOLVED = "solved"
    STUCK = "stuck"
    STEP_LIMIT = "step_limit"


@dataclass(frozen=True, slots=True)
class SolveStep:
    """One verified deduction plus reproducible states before and after it."""

    deduction: Deduction
    before: CandidateState
    after: CandidateState


@dataclass(frozen=True, slots=True)
class SolveResult:
    """A snapshot of the final state and the deductions used to reach it."""

    status: SolveStatus
    state: CandidateState
    steps: tuple[SolveStep, ...]

    @property
    def solved(self) -> bool:
        return self.status is SolveStatus.SOLVED


class LogicalSolver:
    """Apply one verified deduction at a time, respecting technique priority.

    The input board/state is copied; solving never changes the caller's input.
    A step is committed only after all its effects have succeeded on a copy.

    Only registered techniques with independent mathematical verification are accepted.
    """

    def __init__(self, techniques: Iterable[LogicalTechnique] | None = None, *, allow_uniqueness: bool = False) -> None:
        if type(allow_uniqueness) is not bool:
            raise TypeError("allow_uniqueness must be a boolean")
        if techniques is None:
            techniques = (NakedSingle(), HiddenSingle(), Pointing(), Claiming(), NakedPair(), HiddenPair(),
                          NakedTriple(), HiddenTriple(), NakedQuad(), HiddenQuad(),
                          XWing(), Swordfish(), Jellyfish(),
                          Skyscraper(), TwoStringKite(), Crane(),
                          XYWing(), XYZWing(), WWing(), EmptyRectangle(), FinnedXWing(), FinnedSwordfish(), FinnedJellyfish(),
                          SimpleColoring(), RemotePairs(), XChain(), XYChain(), ALSXZ(), SueDeCoq(), ALSChain(), AIC(), GroupedAIC(), ALSAIC(max_links=3, max_als_groups=35, max_expansions=700, max_deductions=20))
            if allow_uniqueness:
                techniques += (UniqueRectangleType1(), UniqueRectangleType2(), UniqueRectangleType3(), UniqueRectangleType4(), UniqueRectangleType5(), UniqueRectangleType6(), HiddenUniqueRectangle(), BUGPlusOne())
        self.techniques = tuple(techniques)
        if not allow_uniqueness and any(isinstance(t, (UniqueRectangleType1, UniqueRectangleType2, UniqueRectangleType3, UniqueRectangleType4, UniqueRectangleType5, UniqueRectangleType6, HiddenUniqueRectangle, BUGPlusOne)) for t in self.techniques):
            raise ValueError("Uniqueness-based techniques require allow_uniqueness=True")
        if any(not isinstance(t, LogicalTechnique) for t in self.techniques):
            raise TypeError("techniques must contain LogicalTechnique instances")
        if any(not DeductionVerifier.supports(t) for t in self.techniques):
            raise NotImplementedError("Some registered techniques do not have verifiers")

    def solve(
        self,
        puzzle: SudokuBoard | CandidateState,
        *,
        max_steps: int | None = None,
    ) -> SolveResult:
        """Solve until complete, stuck, or the optional deduction step limit is hit.

        ``max_steps=0`` inspects the initial state without making any moves.
        No guessing or backtracking is performed.
        """
        if isinstance(puzzle, CandidateState):
            state = puzzle.copy()
        elif isinstance(puzzle, SudokuBoard):
            state = CandidateState(puzzle)
        else:
            raise TypeError("puzzle must be SudokuBoard or CandidateState")
        if max_steps is not None and (type(max_steps) is not int or max_steps < 0):
            raise ValueError("max_steps must be a nonnegative integer or None")

        history: list[SolveStep] = []
        while True:
            if state.is_complete():
                status = SolveStatus.SOLVED
                break
            if max_steps is not None and len(history) >= max_steps:
                status = SolveStatus.STEP_LIMIT
                break

            selected: tuple[LogicalTechnique, Deduction] | None = None
            for technique in self.techniques:
                proposed = technique.find_first(state)
                if proposed is not None:
                    selected = (technique, proposed)
                    break
            if selected is None:
                status = SolveStatus.STUCK
                break

            technique, deduction = selected
            DeductionVerifier.verify(state, technique, deduction)
            candidate = state.copy()
            for move in deduction.placements:
                candidate.place(*move.cell, move.digit)
            for move in deduction.eliminations:
                candidate.eliminate(*move.cell, move.digit)
            history.append(SolveStep(deduction, state.copy(), candidate.copy()))
            state = candidate

        return SolveResult(status, state.copy(), tuple(history))
