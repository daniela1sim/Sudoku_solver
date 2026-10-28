"""Shared interface for human-style Sudoku solving techniques.

Techniques inspect a :class:`CandidateState` and propose immutable
:class:`Deduction` objects. They must never modify the supplied state.
Validating the *mathematical justification* and applying deductions are
separate responsibilities of the future solving engine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction


class LogicalTechnique(ABC):
    """Abstract base for algorithms that discover Sudoku deductions.

    Subclasses provide a unique, human-readable ``name`` and implement
    ``find_deductions``. Returning an empty tuple means the technique cannot
    currently identify a deduction; it does *not* mean the grid is unsolvable.

    Implementations should:
      * inspect the supplied state without mutating it;
      * return only actual effects (not candidates already absent);
      * use zero-based coordinates in returned deductions;
      * return deductions in a deterministic order when practical;
      * supply premises describing why each effect follows.

    Note: ``Deduction`` currently checks structure, not logical truth.
    The future deduction verifier must check proposed premises and effects
    before the solver applies anything.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable technique identifier, e.g. 'Naked Single'."""

    @abstractmethod
    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        """Return deductions applicable to ``state`` without changing it."""

    def find_first(self, state: CandidateState) -> Deduction | None:
        """Return the first proposed deduction, or ``None`` if none exist."""
        deductions = self.find_deductions(state)
        return deductions[0] if deductions else None
