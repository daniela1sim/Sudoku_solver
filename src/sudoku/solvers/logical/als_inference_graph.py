"""Boolean inference graph combining candidate nodes and ALS-digit nodes.

An ALS-digit proposition ``(S, d)`` means that digit d occurs *somewhere*
in the Almost Locked Set S. For an n-cell ALS with n+1 candidates:

* any two distinct ALS-digit propositions from the SAME ALS have a STRONG
  link (at least one must be true). Crucially, this does NOT imply a weak
  link; both digits can occur.
* a WEAK link holds between two propositions when every candidate atom
  represented by the first conflicts with every atom in the second.
  For ALS nodes representing the same digit in disjoint ALSs, this is the
  restricted-common-candidate (RCC) condition.

Links between individual candidate nodes are delegated to InferenceGraph.
No uniqueness assumption or extra Sudoku constraints are used.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from sudoku.core.board import Cell
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import cell_label
from sudoku.solvers.logical.als import find_almost_locked_sets
from sudoku.solvers.logical.inference_graph import CandidateNode, InferenceGraph


def _conflict(a: CandidateNode, b: CandidateNode) -> bool:
    """Two elementary assignments cannot simultaneously be true."""
    if a.cell == b.cell:
        return a.digit != b.digit
    if a.digit != b.digit:
        return False
    r1, c1 = a.cell
    r2, c2 = b.cell
    return (r1 == r2 or c1 == c2
            or (r1 // 3, c1 // 3) == (r2 // 3, c2 // 3))


@dataclass(frozen=True, slots=True)
class ALSNode:
    """Proposition: an ALS contains *at least one* occurrence of digit."""

    cells: tuple[Cell, ...]
    digit: int

    def __post_init__(self) -> None:
        if not isinstance(self.cells, tuple) or len(self.cells) < 2:
            raise ValueError("ALS node needs at least two cells")
        if self.cells != tuple(sorted(set(self.cells))):
            raise ValueError("ALS cells must be distinct and sorted")
        if any(type(r) is not int or type(c) is not int or not 0 <= r < 9
               or not 0 <= c < 9 for r, c in self.cells):
            raise ValueError("Invalid ALS cell")
        if type(self.digit) is not int or not 1 <= self.digit <= 9:
            raise ValueError("Invalid ALS digit")

    @property
    def label(self) -> str:
        cells = ",".join(cell_label(cell) for cell in self.cells)
        return f"ALS({cells}) contains {self.digit}"


InferenceNode = CandidateNode | ALSNode


def members(node: InferenceNode, state: CandidateState) -> tuple[CandidateNode, ...]:
    """Active atomic alternatives represented by one proposition."""
    if isinstance(node, CandidateNode):
        return (node,)
    return tuple(CandidateNode(*cell, node.digit) for cell in node.cells
                 if node.digit in state.candidates_at(*cell))


def _key(node: InferenceNode) -> tuple:
    if isinstance(node, CandidateNode):
        return (0, (node.row, node.col), node.digit)
    return (1, node.cells, node.digit)


class ALSInferenceGraph:
    """Candidate graph extended with ALS nodes and sound Boolean links.

    Only 2+-cell ALSs are added: a one-cell ALS is already a bivalue cell
    represented by two individual candidate nodes. ``max_als_groups`` bounds
    expensive ALS enumeration and cross-group links; smaller ALSs are preferred.
    """

    def __init__(self, state: CandidateState, *, max_als_size: int = 2,
                 max_als_groups: int = 100) -> None:
        if not isinstance(state, CandidateState):
            raise TypeError("state must be CandidateState")
        if type(max_als_size) is not int or not 2 <= max_als_size <= 4:
            raise ValueError("max_als_size must be between 2 and 4")
        if type(max_als_groups) is not int or not 1 <= max_als_groups <= 500:
            raise ValueError("max_als_groups must be between 1 and 500")

        basic = InferenceGraph(state)
        groups = (g for g in find_almost_locked_sets(state, max_size=max_als_size)
                  if len(g.cells) >= 2)
        selected = tuple(sorted(groups, key=lambda g: (len(g.cells), g.cells))[:max_als_groups])
        als_nodes = tuple(sorted((ALSNode(g.cells, digit) for g in selected
                                  for digit in g.digits), key=_key))
        self.candidate_nodes = basic.nodes
        self.als_nodes = als_nodes
        self.nodes: tuple[InferenceNode, ...] = (*basic.nodes, *als_nodes)
        self._state = state
        strong: dict[InferenceNode, set[InferenceNode]] = {n: set() for n in self.nodes}
        weak: dict[InferenceNode, set[InferenceNode]] = {n: set() for n in self.nodes}

        def add(a: InferenceNode, b: InferenceNode, kind: str) -> None:
            if a == b:
                return
            target = strong if kind == "strong" else weak
            target[a].add(b)
            target[b].add(a)

        for atom in basic.nodes:
            for neighbor in basic.strong[atom]:
                add(atom, neighbor, "strong")
            for neighbor in basic.weak[atom]:
                add(atom, neighbor, "weak")

        # n cells / n+1 digits: any two different candidate digits cannot
        # BOTH be absent, or n cells would have <= n-1 distinct choices.
        # DO NOT add weak edges for these pairs: both digits may occur!
        by_group: dict[tuple[Cell, ...], list[ALSNode]] = {}
        for node in als_nodes:
            by_group.setdefault(node.cells, []).append(node)
        for group in by_group.values():
            for a, b in combinations(group, 2):
                add(a, b, "strong")

        # An ALS proposition is incompatible with an atomic candidate iff
        # ALL of its possible atomic assignments conflict with that candidate.
        # If the two are identical assignments, they must not be weakly linked.
        als_members = {node: members(node, state) for node in als_nodes}
        for group in als_nodes:
            atoms = als_members[group]
            for atom in basic.nodes:
                if all(_conflict(a, atom) for a in atoms):
                    add(group, atom, "weak")

        # Cross-ALS RCCs: all possible same-digit locations see each other.
        # Only connect disjoint ALS groups; the same group has strong-only links.
        by_digit: dict[int, list[ALSNode]] = {}
        for node in als_nodes:
            by_digit.setdefault(node.digit, []).append(node)
        for digit_nodes in by_digit.values():
            for a, b in combinations(digit_nodes, 2):
                if not set(a.cells).isdisjoint(b.cells):
                    continue
                if all(_conflict(x, y) for x in als_members[a] for y in als_members[b]):
                    add(a, b, "weak")

        self.strong = {node: frozenset(strong[node]) for node in self.nodes}
        self.weak = {node: frozenset(weak[node]) for node in self.nodes}
        self._ordered_strong = {node: tuple(sorted(strong[node], key=_key)) for node in self.nodes}
        self._ordered_weak = {node: tuple(sorted(weak[node], key=_key)) for node in self.nodes}

    def linked(self, a: InferenceNode, b: InferenceNode, kind: str) -> bool:
        if kind == "strong":
            return b in self.strong.get(a, ())
        if kind == "weak":
            return b in self.weak.get(a, ())
        raise ValueError("kind must be 'strong' or 'weak'")

    def neighbors(self, node: InferenceNode, kind: str) -> tuple[InferenceNode, ...]:
        if kind == "strong":
            return self._ordered_strong.get(node, ())
        if kind == "weak":
            return self._ordered_weak.get(node, ())
        raise ValueError("kind must be 'strong' or 'weak'")

    def common_candidate_conflicts(self, a: InferenceNode, b: InferenceNode) -> frozenset[CandidateNode]:
        """Atomic candidates incompatible with both endpoint propositions."""
        return frozenset(atom for atom in self.candidate_nodes
                         if self.linked(atom, a, "weak") and self.linked(atom, b, "weak"))
