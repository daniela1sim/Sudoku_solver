"""Simple Coloring of single-digit conjugate-link components.

An edge joins the *only* two positions for a digit in a row, column, or
box. Along each connected, bipartite component the digit occupies either
all color-0 vertices or all color-1 vertices, never a mixture.

Two deduction rules are supported:

* Color Wrap: two vertices of one color see each other, so that entire
  color can be eliminated.
* Color Trap: an uncolored candidate sees a vertex of each color, so it
  cannot contain the digit.

All deductions are candidate eliminations. The normal singles techniques
can subsequently turn any newly singleton cells into placements.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from itertools import combinations

from sudoku.core.board import Cell, SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Premise, cell_label
from sudoku.solvers.logical.base import LogicalTechnique
from sudoku.solvers.logical.strong_links import _links, _sees


@dataclass(frozen=True, slots=True)
class _ColorComponent:
    digit: int
    # Sorted cell/color pairs, so the component has a stable identity.
    colors: tuple[tuple[Cell, int], ...]

    @property
    def cells(self) -> tuple[Cell, ...]:
        return tuple(cell for cell, _ in self.colors)

    def side(self, color: int) -> tuple[Cell, ...]:
        return tuple(cell for cell, parity in self.colors if parity == color)


def _colored_components(state: CandidateState, digit: int) -> tuple[_ColorComponent, ...]:
    """Return consistent strong-link components for one digit.

    An odd cycle of *strong* links indicates contradictory input candidates;
    it cannot be two-colored. We skip that component rather than deriving
    arbitrary eliminations from an inconsistent premise.
    """
    if not isinstance(state, CandidateState):
        raise TypeError("state must be a CandidateState")
    if type(digit) is not int or digit not in SudokuBoard.DIGITS:
        raise ValueError("digit must be 1 through 9")

    graph: dict[Cell, set[Cell]] = {}
    for link in _links(state, digit):
        left, right = link.cells
        graph.setdefault(left, set()).add(right)
        graph.setdefault(right, set()).add(left)

    visited: set[Cell] = set()
    components: list[_ColorComponent] = []
    for start in sorted(graph):
        if start in visited:
            continue
        coloring = {start: 0}
        queue = deque([start])
        valid = True
        while queue:
            current = queue.popleft()
            for peer in sorted(graph[current]):
                expected = 1 - coloring[current]
                if peer not in coloring:
                    coloring[peer] = expected
                    queue.append(peer)
                elif coloring[peer] != expected:
                    valid = False
        visited.update(coloring)
        if valid:
            components.append(_ColorComponent(digit, tuple(sorted(coloring.items()))))
    return tuple(components)


def _wrap_effects(state: CandidateState, component: _ColorComponent, color: int) -> tuple[Elimination, ...]:
    """All members of an impossible color (if two of them see each other)."""
    side = component.side(color)
    if not any(_sees(a, b) for a, b in combinations(side, 2)):
        return ()
    return tuple(Elimination(cell, component.digit)
                 for cell in side if component.digit in state.candidates_at(*cell))


def _trap_effects(state: CandidateState, component: _ColorComponent) -> tuple[Elimination, ...]:
    """Candidates outside a component that see at least one of each color."""
    left, right = component.side(0), component.side(1)
    colored = set(component.cells)
    return tuple(
        Elimination(cell, component.digit)
        for cell in state.unsolved_cells()
        if cell not in colored
        and component.digit in state.candidates_at(*cell)
        and any(_sees(cell, other) for other in left)
        and any(_sees(cell, other) for other in right)
    )


def _coloring_patterns(state: CandidateState):
    """Yield (rule, component, eliminated_color, effects) deterministically.

    The eliminated color is an integer for Wrap and None for Trap. Only
    nonempty deductions are returned.
    """
    if not isinstance(state, CandidateState):
        raise TypeError("state must be a CandidateState")
    for digit in sorted(SudokuBoard.DIGITS):
        for component in _colored_components(state, digit):
            for color in (0, 1):
                effects = _wrap_effects(state, component, color)
                if effects:
                    yield "Color Wrap", component, color, effects
            effects = _trap_effects(state, component)
            if effects:
                yield "Color Trap", component, None, effects


class SimpleColoring(LogicalTechnique):
    """Discover Color Wrap and Color Trap eliminations using strong links."""

    @property
    def name(self) -> str:
        return "Simple Coloring"

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        if not isinstance(state, CandidateState):
            raise TypeError("state must be a CandidateState")
        deductions: list[Deduction] = []
        for rule, component, color, effects in _coloring_patterns(state):
            digit = component.digit
            if rule == "Color Wrap":
                side = component.side(color)
                witnesses = next((a, b) for a, b in combinations(side, 2) if _sees(a, b))
                description = (
                    f"Color Wrap for {digit}: {cell_label(witnesses[0])} and "
                    f"{cell_label(witnesses[1])} have the same color but see each "
                    f"other. Every {digit} in that color must be false; "
                    "remove it from those colored cells."
                )
            else:
                description = (
                    f"Color Trap for {digit}: the listed cells form a connected "
                    "alternating two-color strong-link graph. One color must "
                    "contain the digit. An outside candidate seeing both "
                    "colors cannot contain it."
                )
            deductions.append(Deduction(
                technique=self.name,
                premises=(Premise(description, component.cells, frozenset({digit})),),
                eliminations=effects,
            ))
        return tuple(deductions)
