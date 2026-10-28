"""Remote Pairs: alternating chains of identical bivalue cells.

Every chain vertex has exactly the same pair {a, b}. Consecutive
vertices see each other, forcing alternating values. In a chain with
an odd number of edges (four or more cells), the endpoints have
opposite values. Any *outside* candidate seeing both endpoints can
therefore contain neither a nor b.

The graph is two-colored to find candidate chains. Non-bipartite
components are skipped: their candidate assumptions already conflict.
Two-vertex pairs are intentionally left to the Naked Pair technique.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from itertools import combinations

from sudoku.core.board import Cell
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Premise, cell_label
from sudoku.solvers.logical.base import LogicalTechnique
from sudoku.solvers.logical.strong_links import _sees


@dataclass(frozen=True, slots=True)
class _PairComponent:
    pair: frozenset[int]
    colors: tuple[tuple[Cell, int], ...]

    @property
    def cells(self) -> tuple[Cell, ...]:
        return tuple(cell for cell, _ in self.colors)


def _pair_components(state: CandidateState) -> tuple[_PairComponent, ...]:
    """Return bipartite peer graphs grouped by exact bivalue pair."""
    if not isinstance(state, CandidateState):
        raise TypeError("state must be a CandidateState")

    by_pair: dict[frozenset[int], list[Cell]] = {}
    for cell in state.unsolved_cells():
        digits = state.candidates_at(*cell)
        if len(digits) == 2:
            by_pair.setdefault(digits, []).append(cell)

    result: list[_PairComponent] = []
    for pair in sorted(by_pair, key=lambda p: tuple(sorted(p))):
        nodes = sorted(by_pair[pair])
        graph = {cell: set() for cell in nodes}
        for a, b in combinations(nodes, 2):
            if _sees(a, b):
                graph[a].add(b)
                graph[b].add(a)
        seen: set[Cell] = set()
        for start in nodes:
            if start in seen:
                continue
            color = {start: 0}
            queue = deque([start])
            valid = True
            while queue:
                current = queue.popleft()
                for peer in sorted(graph[current]):
                    expected = 1 - color[current]
                    if peer not in color:
                        color[peer] = expected
                        queue.append(peer)
                    elif color[peer] != expected:
                        valid = False
            seen.update(color)
            if valid and len(color) >= 4:
                result.append(_PairComponent(pair, tuple(sorted(color.items()))))
    return tuple(result)


def _shortest_path(graph: dict[Cell, tuple[Cell, ...]], start: Cell, end: Cell) -> tuple[Cell, ...]:
    """Deterministically return the shortest peer path, or an empty tuple."""
    parents: dict[Cell, Cell | None] = {start: None}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        if current == end:
            break
        for nxt in graph[current]:
            if nxt not in parents:
                parents[nxt] = current
                queue.append(nxt)
    if end not in parents:
        return ()
    path = []
    node: Cell | None = end
    while node is not None:
        path.append(node)
        node = parents[node]
    return tuple(reversed(path))


def _remote_pair_patterns(state: CandidateState):
    """Yield (witness chain, pair, valid eliminations) deterministically.

    Require endpoints to be non-peers and connected by at least three
    peer edges. This excludes elementary Naked Pair deductions.
    """
    if not isinstance(state, CandidateState):
        raise TypeError("state must be a CandidateState")
    for component in _pair_components(state):
        colors = dict(component.colors)
        cells = component.cells
        graph = {
            cell: tuple(other for other in cells if _sees(cell, other))
            for cell in cells
        }
        for a, b in combinations(cells, 2):
            if colors[a] == colors[b] or _sees(a, b):
                continue
            path = _shortest_path(graph, a, b)
            if len(path) < 4 or len(path) % 2 != 0:
                continue
            effects = tuple(
                Elimination(target, digit)
                for target in state.unsolved_cells()
                if target not in cells and _sees(target, a) and _sees(target, b)
                for digit in sorted(component.pair)
                if digit in state.candidates_at(*target)
            )
            if effects:
                yield path, component.pair, effects


class RemotePairs(LogicalTechnique):
    """Find candidate eliminations using even-length bivalue chains."""

    @property
    def name(self) -> str:
        return "Remote Pairs"

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        if not isinstance(state, CandidateState):
            raise TypeError("state must be a CandidateState")
        deductions = []
        for chain, pair, effects in _remote_pair_patterns(state):
            a, b = chain[0], chain[-1]
            digits = ", ".join(map(str, sorted(pair)))
            description = (
                f"Remote Pairs ({digits}): the bivalue cells "
                + " → ".join(map(cell_label, chain))
                + f" alternate between these digits. {cell_label(a)} and "
                f"{cell_label(b)} therefore contain opposite digits. "
                "Remove either digit from outside cells seeing both endpoints."
            )
            deductions.append(Deduction(
                technique=self.name,
                premises=(Premise(description, chain, pair),),
                eliminations=effects,
            ))
        return tuple(deductions)
