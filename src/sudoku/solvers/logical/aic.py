"""Bounded Alternating Inference Chains with machine-verifiable witnesses.

This first general candidate-level engine includes:
* Open AICs: STRONG - WEAK - ... - STRONG; any candidate weakly
  linked to BOTH endpoints can be eliminated, even for different digits.
* Discontinuous STRONG/STRONG loops: the repeated end node must be true.
* Continuous loops: off-loop eliminations on each weak link.

A weak/weak discontinuity is covered by open-chain eliminations (the target
candidate is weakly linked to both endpoints). AICs do not use uniqueness.
Only individual candidate nodes, not grouped or ALS nodes, are supported.
"""
from __future__ import annotations

from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Placement, Premise
from sudoku.solvers.logical.base import LogicalTechnique
from sudoku.solvers.logical.inference_graph import CandidateNode, InferenceGraph


def _witness(path: tuple[CandidateNode, ...], outcome: str) -> tuple[Premise, ...]:
    """Ordered candidate nodes form the proof certificate, not its free text."""
    parts = []
    for i, node in enumerate(path):
        entering = "start" if i == 0 else ("strong" if (i - 1) % 2 == 0 else "weak")
        parts.append(Premise(
            description=(f"{outcome}. " if i == 0 else "")
                        + f"AIC node {i + 1}: {node.label}; incoming {entering} link",
            cells=(node.cell,), digits=frozenset({node.digit}),
        ))
    return tuple(parts)


def _effects_for_cycle(
    graph: InferenceGraph, path: tuple[CandidateNode, ...]
) -> tuple[Elimination, ...]:
    """Eliminate off-cycle nodes seeing both ends of any cycle weak link."""
    excluded = set(path)
    eliminations: set[Elimination] = set()
    for i in range(1, len(path)):
        if (i - 1) % 2 != 1:
            continue  # Every second link, including the closing weak link.
        a, b = path[i - 1], path[i]
        for candidate in graph.common_weak_neighbors(a, b) - excluded:
            eliminations.add(Elimination(candidate.cell, candidate.digit))
    return tuple(sorted(eliminations, key=lambda e: (*e.cell, e.digit)))


class AIC(LogicalTechnique):
    """Find bounded candidate-level alternating chains and loops.

    ``max_links`` is the longest open/strong-discontinuous path. A closing
    weak edge may yield a continuous loop of one additional link.
    ``max_expansions`` is a global DFS budget for each discovery call; reaching
    it may miss deductions but never makes returned deductions unsound.
    """

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
        return "AIC"

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        if not isinstance(state, CandidateState):
            raise TypeError("state must be a CandidateState")
        graph = InferenceGraph(state)
        results: list[Deduction] = []
        fingerprints: set[tuple] = set()
        expansions = 0
        exhausted = False

        def store(path: tuple[CandidateNode, ...], *, cycle: bool = False,
                  forced: bool = False) -> None:
            if forced:
                effect = Placement(path[0].cell, path[0].digit)
                signature = ("place", effect)
                if signature in fingerprints:
                    return
                deduction = Deduction(
                    self.name,
                    _witness(path, "Strong/strong discontinuity: assuming the first "
                             "candidate false forces it true, so it must be placed"),
                    placements=(effect,),
                )
            else:
                if cycle:
                    effects = _effects_for_cycle(graph, path)
                else:
                    excluded = set(path)
                    effects = tuple(Elimination(node.cell, node.digit)
                                    for node in sorted(graph.common_weak_neighbors(
                                        path[0], path[-1]) - excluded))
                if not effects:
                    return
                # Prefer the first (typically shortest) witness for an effect set.
                signature = ("eliminate", effects)
                if signature in fingerprints:
                    return
                reasoning = (
                    "Continuous AIC: each weak edge has at least one true "
                    "endpoint, excluding candidates that conflict with both"
                    if cycle else
                    "Open AIC: at least one endpoint is true, so candidates "
                    "conflicting with both endpoints are excluded"
                )
                deduction = Deduction(self.name, _witness(path, reasoning),
                                      eliminations=effects)
            fingerprints.add(signature)
            results.append(deduction)

        # Search short chains before long ones. Avoid repeated nodes except for
        # the closing edge back to the first node, a valid loop witness.
        for limit in range(3, self.max_links + 1, 2):
            if exhausted or len(results) >= self.max_deductions:
                break
            for start in graph.nodes:
                if not graph.strong[start]:
                    continue
                path = [start]
                visited = {start}

                def visit() -> None:
                    nonlocal expansions, exhausted
                    if exhausted or len(results) >= self.max_deductions:
                        return
                    length = len(path) - 1
                    if length >= limit:
                        # A strong-ended path may still close with one final
                        # weak link into a continuous loop.
                        if length % 2 == 1 and path[0] in graph.weak[path[-1]]:
                            expansions += 1
                            if expansions > self.max_expansions:
                                exhausted = True
                            else:
                                store(tuple((*path, start)), cycle=True)
                        return
                    kind = "strong" if length % 2 == 0 else "weak"
                    for next_node in graph.neighbors(path[-1], kind):
                        if exhausted or len(results) >= self.max_deductions:
                            return
                        expansions += 1
                        if expansions > self.max_expansions:
                            exhausted = True
                            return
                        new_length = length + 1
                        if next_node == start:
                            if new_length >= 3 and kind == "strong":
                                store(tuple((*path, start)), forced=True)
                            elif new_length >= 4 and kind == "weak":
                                store(tuple((*path, start)), cycle=True)
                            continue
                        if next_node in visited:
                            continue
                        path.append(next_node)
                        visited.add(next_node)
                        if new_length >= 3 and kind == "strong":
                            store(tuple(path))
                        visit()
                        visited.remove(next_node)
                        path.pop()

                visit()
                if exhausted or len(results) >= self.max_deductions:
                    break
        return tuple(results)
