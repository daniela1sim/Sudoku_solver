"""Boolean inference graph with box-line *grouped candidate* nodes.

A CandidateNode means ``cell == digit``. A GroupNode means that digit
occurs in *at least one* of its member cells (logical OR). A grouped node
is a 2- or 3-cell intersection of one row/column with one box.

For propositions A and B:
    strong link: A or B (at least one true)
    weak link:   not (A and B) (at most one true)

Group links are derived from the current Sudoku constraints, rather than
inferred from geometric appearance alone. In particular, a group can be
weakly linked to another node only when *every* pair of member candidates
is mutually exclusive.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from sudoku.core.board import Cell
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import cell_label
from sudoku.solvers.logical.inference_graph import CandidateNode, InferenceGraph


def _peers(a: Cell, b: Cell) -> bool:
    return a != b and (
        a[0] == b[0] or a[1] == b[1]
        or (a[0] // 3, a[1] // 3) == (b[0] // 3, b[1] // 3)
    )


@dataclass(frozen=True, slots=True)
class GroupNode:
    """Disjunction of one digit in 2–3 cells of a box-line intersection."""

    cells: tuple[Cell, ...]
    digit: int

    def __post_init__(self) -> None:
        if not 2 <= len(self.cells) <= 3 or tuple(sorted(set(self.cells))) != self.cells:
            raise ValueError("A group must contain 2–3 distinct sorted cells")
        if type(self.digit) is not int or not 1 <= self.digit <= 9:
            raise ValueError("Group digit must be between 1 and 9")
        for r, c in self.cells:
            if type(r) is not int or type(c) is not int or not (0 <= r < 9 and 0 <= c < 9):
                raise ValueError("Invalid group cell")
        rows = {r for r, _ in self.cells}
        cols = {c for _, c in self.cells}
        boxes = {(r // 3, c // 3) for r, c in self.cells}
        if len(boxes) != 1 or (len(rows) != 1 and len(cols) != 1):
            raise ValueError("A group must lie in one row/box or column/box intersection")

    @property
    def label(self) -> str:
        return f"{self.digit}@({'|'.join(cell_label(cell) for cell in self.cells)})"


InferenceNode = CandidateNode | GroupNode


def members(node: InferenceNode) -> tuple[CandidateNode, ...]:
    if isinstance(node, CandidateNode):
        return (node,)
    return tuple(CandidateNode(*cell, node.digit) for cell in node.cells)


def _key(node: InferenceNode) -> tuple:
    atoms = members(node)
    return (len(atoms), tuple((a.row, a.col, a.digit) for a in atoms))


class GroupedInferenceGraph:
    """A candidate graph augmented with sound group-to-node links.

    The initial implementation groups only candidates from one box-line
    intersection; it does not yet include ALS, UR or fish propositions.
    """

    def __init__(self, state: CandidateState) -> None:
        if not isinstance(state, CandidateState):
            raise TypeError("state must be a CandidateState")
        basic = InferenceGraph(state)
        group_nodes: set[GroupNode] = set()
        # Candidate positions inside every 3-cell horizontal/vertical box strip.
        for digit in range(1, 10):
            for br in (0, 3, 6):
                for bc in (0, 3, 6):
                    for offset in range(3):
                        segments = (
                            tuple((br + offset, c) for c in range(bc, bc + 3)),
                            tuple((r, bc + offset) for r in range(br, br + 3)),
                        )
                        for segment in segments:
                            cells = tuple(cell for cell in segment if digit in state.candidates_at(*cell))
                            if len(cells) >= 2:
                                group_nodes.add(GroupNode(cells, digit))

        self.nodes: tuple[InferenceNode, ...] = tuple(sorted((*basic.nodes, *group_nodes), key=_key))
        weak: dict[InferenceNode, set[InferenceNode]] = {v: set() for v in self.nodes}
        strong: dict[InferenceNode, set[InferenceNode]] = {v: set() for v in self.nodes}

        def add(a: InferenceNode, b: InferenceNode, *, is_strong: bool) -> None:
            if a == b:
                return
            if is_strong:
                strong[a].add(b)
                strong[b].add(a)
            else:
                weak[a].add(b)
                weak[b].add(a)

        # Preserve the exact links of the original AIC candidate graph.
        for a in basic.nodes:
            for b in basic.weak[a]:
                add(a, b, is_strong=False)
            for b in basic.strong[a]:
                add(a, b, is_strong=True)

        # A group and another proposition are incompatible precisely when
        # every cross-pair of their possible atoms conflicts in Sudoku.
        by_digit: dict[int, list[InferenceNode]] = {d: [] for d in range(1, 10)}
        for node in self.nodes:
            digit = node.digit
            by_digit[digit].append(node)
        for digit_nodes in by_digit.values():
            for a, b in combinations(digit_nodes, 2):
                if isinstance(a, CandidateNode) and isinstance(b, CandidateNode):
                    continue  # Already represented in the basic graph.
                am = members(a)
                bm = members(b)
                if all(_peers(x.cell, y.cell) for x in am for y in bm):
                    add(a, b, is_strong=False)

        # For each missing digit in a unit, SOME candidate cell must contain
        # it. Two disjoint propositions covering all possible positions in
        # that unit therefore form a strong link.
        for unit in state._units():
            unit_cells = frozenset(unit)
            for digit in range(1, 10):
                choices = frozenset(cell for cell in unit if digit in state.candidates_at(*cell))
                if len(choices) < 2:
                    continue
                subsets: dict[frozenset[Cell], InferenceNode] = {}
                for node in by_digit[digit]:
                    cells = frozenset(a.cell for a in members(node))
                    if cells <= choices:
                        subsets[cells] = node
                for a_cells, a in subsets.items():
                    b = subsets.get(choices - a_cells)
                    if b is not None and a_cells and (choices - a_cells):
                        add(a, b, is_strong=True)

        # Here all strong links are mutually exclusive as well. Keep weak
        # adjacency explicit so that strong links may serve as weak links.
        self.strong = {node: frozenset(strong[node]) for node in self.nodes}
        self.weak = {node: frozenset(weak[node]) for node in self.nodes}
        self._strong_ordered = {node: tuple(sorted(strong[node], key=_key)) for node in self.nodes}
        self._weak_ordered = {node: tuple(sorted(weak[node], key=_key)) for node in self.nodes}
        self.candidate_nodes = basic.nodes

    def neighbors(self, node: InferenceNode, kind: str) -> tuple[InferenceNode, ...]:
        if kind == "strong":
            return self._strong_ordered.get(node, ())
        if kind == "weak":
            return self._weak_ordered.get(node, ())
        raise ValueError("kind must be 'strong' or 'weak'")

    def linked(self, a: InferenceNode, b: InferenceNode, kind: str) -> bool:
        if kind == "strong":
            return b in self.strong.get(a, ())
        if kind == "weak":
            return b in self.weak.get(a, ())
        raise ValueError("kind must be 'strong' or 'weak'")

    def common_candidate_conflicts(
        self, a: InferenceNode, b: InferenceNode
    ) -> frozenset[CandidateNode]:
        """Single candidates incompatible with BOTH endpoint propositions."""
        return frozenset(
            target for target in self.candidate_nodes
            if self.linked(target, a, "weak") and self.linked(target, b, "weak")
        )
