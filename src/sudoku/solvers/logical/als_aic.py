"""Alternating Inference Chains containing Almost Locked Set propositions.

ALS-digit nodes express ``some cell of an ALS contains digit d``. Their
internal strong links are not necessarily conjugate (not always weak).
Search is bounded and intentionally incomplete. All proposed effects are
reconstructed and checked by the independent DeductionVerifier.

This first ALS-AIC implementation mixes individual candidates and ALS-digit
nodes; mixing grouped box-line nodes into the *same* chain is future work.
"""
from __future__ import annotations

from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Placement, Premise
from sudoku.solvers.logical.als_inference_graph import (
    ALSInferenceGraph, ALSNode, CandidateNode, InferenceNode, members,
)
from sudoku.solvers.logical.base import LogicalTechnique


def _witness(path: tuple[InferenceNode, ...], state: CandidateState,
             reason: str) -> tuple[Premise, ...]:
    return tuple(Premise(
        ("ALS-AIC: " + reason + ". " if i == 0 else "")
        + ("ALS node" if isinstance(node, ALSNode) else "Candidate node")
        + f" {i + 1}: {node.label}; incoming "
        + ("start" if i == 0 else ("strong" if (i - 1) % 2 == 0 else "weak")),
        (node.cells if isinstance(node, ALSNode) else (node.cell,)),
        frozenset({node.digit}),
    ) for i, node in enumerate(path))


def _eliminations(graph: ALSInferenceGraph, state: CandidateState,
                  path: tuple[InferenceNode, ...], *, closed: bool = False) -> tuple[Elimination, ...]:
    # Ignore atoms represented anywhere along the path: conservative and
    # avoids explaining an elimination through a proposition using itself.
    used = {atom for node in path for atom in members(node, state)}
    victims: set[CandidateNode] = set()
    if closed:
        for i, (a, b) in enumerate(zip(path, path[1:])):
            if i % 2 == 1:  # Weak links, including the final closing link
                victims.update(graph.common_candidate_conflicts(a, b))
    else:
        victims.update(graph.common_candidate_conflicts(path[0], path[-1]))
    return tuple(Elimination(atom.cell, atom.digit) for atom in sorted(victims - used))


class ALSAIC(LogicalTechnique):
    """Bounded candidate/ALS mixed AIC search, including ALS-internal links."""

    def __init__(self, *, max_links: int = 5, max_als_size: int = 2,
                 max_als_groups: int = 100, max_expansions: int = 12000,
                 max_deductions: int = 40) -> None:
        if type(max_links) is not int or max_links not in (3, 5, 7, 9):
            raise ValueError("max_links must be 3, 5, 7, or 9")
        if type(max_als_size) is not int or not 2 <= max_als_size <= 4:
            raise ValueError("max_als_size must be between 2 and 4")
        if type(max_als_groups) is not int or not 1 <= max_als_groups <= 500:
            raise ValueError("max_als_groups must be between 1 and 500")
        if type(max_expansions) is not int or not 1 <= max_expansions <= 1000000:
            raise ValueError("max_expansions must be between 1 and 1000000")
        if type(max_deductions) is not int or not 1 <= max_deductions <= 1000:
            raise ValueError("max_deductions must be between 1 and 1000")
        self.max_links = max_links
        self.max_als_size = max_als_size
        self.max_als_groups = max_als_groups
        self.max_expansions = max_expansions
        self.max_deductions = max_deductions

    @property
    def name(self) -> str:
        return "ALS-AIC"

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        if not isinstance(state, CandidateState):
            raise TypeError("state must be a CandidateState")
        graph = ALSInferenceGraph(state, max_als_size=self.max_als_size,
                                  max_als_groups=self.max_als_groups)
        results: list[Deduction] = []
        signatures: set[tuple] = set()
        expansions = 0
        exhausted = False

        def record(path: tuple[InferenceNode, ...], *, closed: bool = False,
                   forced: bool = False) -> None:
            if not any(isinstance(n, ALSNode) for n in path):
                return
            if forced:
                if not isinstance(path[0], CandidateNode):
                    return  # An ALS proposition being true is NOT a placement.
                effect = Placement(path[0].cell, path[0].digit)
                signature = ("place", effect)
                if signature in signatures:
                    return
                deduction = Deduction(self.name, _witness(path, state,
                    "Strong/strong discontinuity forces the singleton candidate"),
                    placements=(effect,))
            else:
                effects = _eliminations(graph, state, path, closed=closed)
                if not effects:
                    return
                signature = ("eliminate", effects)
                if signature in signatures:
                    return
                deduction = Deduction(self.name, _witness(path, state,
                    "Continuous ALS-AIC loop" if closed else "Open ALS-AIC"),
                    eliminations=effects)
            signatures.add(signature)
            results.append(deduction)

        # Favor ALS-containing witnesses under a strict shared DFS budget.
        starts: tuple[InferenceNode, ...] = (*graph.als_nodes, *graph.candidate_nodes)
        for limit in range(3, self.max_links + 1, 2):
            if exhausted or len(results) >= self.max_deductions:
                break
            for start in starts:
                if not graph.strong[start]:
                    continue
                path = [start]
                visited = {start}

                def visit() -> None:
                    nonlocal expansions, exhausted
                    if exhausted or len(results) >= self.max_deductions:
                        return
                    count = len(path) - 1
                    if count >= limit:
                        if count % 2 == 1 and graph.linked(path[-1], start, "weak"):
                            expansions += 1
                            if expansions > self.max_expansions:
                                exhausted = True
                            else:
                                record(tuple((*path, start)), closed=True)
                        return
                    kind = "strong" if count % 2 == 0 else "weak"
                    for following in graph.neighbors(path[-1], kind):
                        expansions += 1
                        if expansions > self.max_expansions:
                            exhausted = True
                            return
                        if len(results) >= self.max_deductions:
                            return
                        new_count = count + 1
                        if following == start:
                            if new_count >= 3 and kind == "strong":
                                record(tuple((*path, start)), forced=True)
                            elif new_count >= 4 and kind == "weak":
                                record(tuple((*path, start)), closed=True)
                            continue
                        if following in visited:
                            continue
                        path.append(following)
                        visited.add(following)
                        if new_count >= 3 and kind == "strong":
                            record(tuple(path))
                        visit()
                        visited.remove(following)
                        path.pop()

                visit()
                if exhausted or len(results) >= self.max_deductions:
                    break
        return tuple(results)
