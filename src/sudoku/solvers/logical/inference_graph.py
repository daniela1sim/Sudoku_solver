"""Reusable, candidate-level Boolean inference graph for standard Sudoku.

A node (r, c, d) means that cell (r, c) contains digit d.

STRONG: at least one of the two nodes is true (A or B).
WEAK:  the two nodes cannot both be true (not A or not B).

In this initial engine all constructed strong links are *conjugate*: exactly
one endpoint is true. Consequently each strong link is also a weak link.
These definitions support candidate links inside cells as well as among
positions in a row, column, or box. Group and ALS nodes are future extensions.
"""
from __future__ import annotations

from dataclasses import dataclass

from sudoku.core.board import Cell
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import cell_label


@dataclass(frozen=True, order=True, slots=True)
class CandidateNode:
    """A proposition ``cell == digit`` (zero-based cell coordinates)."""

    row: int
    col: int
    digit: int

    @property
    def cell(self) -> Cell:
        return self.row, self.col

    @property
    def label(self) -> str:
        return f"{cell_label(self.cell)}={self.digit}"


class InferenceGraph:
    """Build and expose independently checkable strong/weak candidate links.

    Only candidate positions present in the supplied state are represented.
    Adjacency is deterministic, and neither construction nor queries mutate
    the candidate state.
    """

    def __init__(self, state: CandidateState) -> None:
        if not isinstance(state, CandidateState):
            raise TypeError("state must be a CandidateState")
        nodes = tuple(sorted(CandidateNode(*cell, digit)
                             for cell in state.unsolved_cells()
                             for digit in state.candidates_at(*cell)))
        self.nodes = nodes
        weak: dict[CandidateNode, set[CandidateNode]] = {v: set() for v in nodes}
        strong: dict[CandidateNode, set[CandidateNode]] = {v: set() for v in nodes}

        def pair(a: CandidateNode, b: CandidateNode, *, conjugate: bool) -> None:
            if a == b:
                return
            weak[a].add(b)
            weak[b].add(a)
            if conjugate:
                strong[a].add(b)
                strong[b].add(a)

        # Exactly one digit per cell; bivalue cells are conjugate pairs.
        for r, c in state.unsolved_cells():
            group = tuple(CandidateNode(r, c, d)
                          for d in sorted(state.candidates_at(r, c)))
            for i, a in enumerate(group):
                for b in group[i + 1:]:
                    pair(a, b, conjugate=len(group) == 2)

        # Exactly one occurrence of each missing digit in every house.
        # Filled positions are absent from the candidate state by design.
        for unit in state._units():
            for digit in range(1, 10):
                group = tuple(CandidateNode(*cell, digit) for cell in unit
                              if digit in state.candidates_at(*cell))
                for i, a in enumerate(group):
                    for b in group[i + 1:]:
                        pair(a, b, conjugate=len(group) == 2)

        self.strong = {v: frozenset(strong[v]) for v in nodes}
        self.weak = {v: frozenset(weak[v]) for v in nodes}
        self._sorted_strong = {v: tuple(sorted(strong[v])) for v in nodes}
        self._sorted_weak = {v: tuple(sorted(weak[v])) for v in nodes}

    def neighbors(self, node: CandidateNode, kind: str) -> tuple[CandidateNode, ...]:
        if kind == "strong":
            return self._sorted_strong.get(node, ())
        if kind == "weak":
            return self._sorted_weak.get(node, ())
        raise ValueError("kind must be 'strong' or 'weak'")

    def linked(self, a: CandidateNode, b: CandidateNode, kind: str) -> bool:
        if kind == "strong":
            return b in self.strong.get(a, ())
        if kind == "weak":
            return b in self.weak.get(a, ())
        raise ValueError("kind must be 'strong' or 'weak'")

    def common_weak_neighbors(
        self, a: CandidateNode, b: CandidateNode
    ) -> frozenset[CandidateNode]:
        """Candidates that cannot be true alongside either endpoint."""
        return self.weak.get(a, frozenset()) & self.weak.get(b, frozenset())
