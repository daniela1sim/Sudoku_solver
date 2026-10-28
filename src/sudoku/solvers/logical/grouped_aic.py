"""Bounded Grouped Alternating Inference Chains (Grouped AICs).

Extends candidate-level AICs with proposition nodes representing one digit
in one of 2–3 cells in a row/column–box intersection. A deduction's ordered
premises are a machine-checkable chain witness; independent verification
rebuilds the graph and checks each link from CandidateState.

Supported: open endpoint eliminations, strong/strong discontinuous forced
singleton placements, and continuous-loop eliminations along weak edges.
No uniqueness assumption is used. The search is incomplete by design when
its configured expansion or length bound is reached.
"""
from __future__ import annotations

from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Placement, Premise
from sudoku.solvers.logical.base import LogicalTechnique
from sudoku.solvers.logical.grouped_inference_graph import (
    GroupNode, GroupedInferenceGraph, InferenceNode, members,
)


def grouped_witness(path: tuple[InferenceNode, ...], reasoning: str) -> tuple[Premise, ...]:
    return tuple(
        Premise(
            description=(f"{reasoning}. " if i == 0 else "")
            + f"Grouped AIC node {i + 1}: {node.label}; incoming "
            + ("start" if i == 0 else ("strong" if (i - 1) % 2 == 0 else "weak")),
            cells=tuple(atom.cell for atom in members(node)),
            digits=frozenset({node.digit}),
        ) for i, node in enumerate(path)
    )


def _effect_candidates(
    graph: GroupedInferenceGraph, path: tuple[InferenceNode, ...], *, closed: bool
) -> tuple[Elimination, ...]:
    chain_atoms = {atom for node in path for atom in members(node)}
    eliminated = set()
    if closed:
        for index, (a, b) in enumerate(zip(path, path[1:])):
            if index % 2 == 1:  # Every weak link, including closing link.
                eliminated.update(graph.common_candidate_conflicts(a, b))
    else:
        eliminated.update(graph.common_candidate_conflicts(path[0], path[-1]))
    return tuple(
        Elimination(atom.cell, atom.digit)
        for atom in sorted(eliminated - chain_atoms)
    )


class GroupedAIC(LogicalTechnique):
    """Search for verifiable, bounded AICs containing a grouped node."""

    def __init__(self, *, max_links: int = 7, max_expansions: int = 30000,
                 max_deductions: int = 60) -> None:
        if type(max_links) is not int or max_links not in (3, 5, 7, 9):
            raise ValueError("max_links must be 3, 5, 7, or 9")
        if type(max_expansions) is not int or not 1 <= max_expansions <= 1000000:
            raise ValueError("max_expansions must be an integer from 1 to 1000000")
        if type(max_deductions) is not int or not 1 <= max_deductions <= 1000:
            raise ValueError("max_deductions must be an integer from 1 to 1000")
        self.max_links = max_links
        self.max_expansions = max_expansions
        self.max_deductions = max_deductions

    @property
    def name(self) -> str:
        return "Grouped AIC"

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        if not isinstance(state, CandidateState):
            raise TypeError("state must be a CandidateState")
        graph = GroupedInferenceGraph(state)
        results: list[Deduction] = []
        seen_effects: set[tuple] = set()
        expansions = 0
        exhausted = False

        def record(path: tuple[InferenceNode, ...], *, closed: bool = False,
                   forced: bool = False) -> None:
            if not any(isinstance(node, GroupNode) for node in path):
                return  # This belongs to ordinary candidate-level AIC.
            if forced:
                if isinstance(path[0], GroupNode):
                    return  # A forced group is not a single-digit placement.
                effect = Placement(path[0].cell, path[0].digit)
                signature = ("place", effect)
                if signature in seen_effects:
                    return
                deduction = Deduction(
                    self.name,
                    grouped_witness(path, "Two strong links meet: the singleton endpoint must be true"),
                    placements=(effect,),
                )
            else:
                effects = _effect_candidates(graph, path, closed=closed)
                if not effects:
                    return
                signature = ("eliminate", effects)
                if signature in seen_effects:
                    return
                reason = ("Continuous grouped AIC: each weak edge has a true endpoint"
                          if closed else "Open grouped AIC: at least one endpoint is true")
                deduction = Deduction(
                    self.name, grouped_witness(path, reason), eliminations=effects
                )
            seen_effects.add(signature)
            results.append(deduction)

        # Prioritize grouped starts to find useful new implications within a
        # bounded search. Start singletons as well: groups may be interior.
        starts = tuple(node for node in graph.nodes if isinstance(node, GroupNode)) + tuple(
            node for node in graph.nodes if not isinstance(node, GroupNode)
        )
        for limit in range(3, self.max_links + 1, 2):
            if exhausted or len(results) >= self.max_deductions:
                break
            for start in starts:
                if not graph.strong[start]:
                    continue
                path: list[InferenceNode] = [start]
                used_atoms = set(members(start))
                visited = {start}

                def visit() -> None:
                    nonlocal expansions, exhausted
                    if exhausted or len(results) >= self.max_deductions:
                        return
                    length = len(path) - 1
                    if length >= limit:
                        if length % 2 == 1 and graph.linked(path[-1], start, "weak"):
                            expansions += 1
                            if expansions > self.max_expansions:
                                exhausted = True
                            else:
                                record(tuple((*path, start)), closed=True)
                        return
                    kind = "strong" if length % 2 == 0 else "weak"
                    for next_node in graph.neighbors(path[-1], kind):
                        expansions += 1
                        if expansions > self.max_expansions:
                            exhausted = True
                            return
                        if len(results) >= self.max_deductions:
                            return
                        next_length = length + 1
                        if next_node == start:
                            if next_length >= 3 and kind == "strong":
                                record(tuple((*path, start)), forced=True)
                            elif next_length >= 4 and kind == "weak":
                                record(tuple((*path, start)), closed=True)
                            continue
                        if next_node in visited:
                            continue
                        atoms = set(members(next_node))
                        if atoms & used_atoms:
                            continue  # Exclude overlapping atomic propositions.
                        path.append(next_node)
                        visited.add(next_node)
                        used_atoms.update(atoms)
                        if next_length >= 3 and kind == "strong":
                            record(tuple(path))
                        visit()
                        used_atoms.difference_update(atoms)
                        visited.remove(next_node)
                        path.pop()
                        if exhausted or len(results) >= self.max_deductions:
                            return

                visit()
                if exhausted or len(results) >= self.max_deductions:
                    break
        return tuple(results)
