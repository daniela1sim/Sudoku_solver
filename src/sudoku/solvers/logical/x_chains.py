"""X-Chains: alternating strong/weak links for one Sudoku candidate digit.

A strong link joins the only two possible positions for the digit in a
row, column, or box. A weak link joins two cells that see one another:
they cannot both contain that digit (a strong link is also a valid weak link).

An alternating chain STRONG / WEAK / ... / STRONG establishes that at
least one of its two endpoints must contain the digit. The digit can
therefore be eliminated from every *other* cell seeing both endpoints.

Only open, simple chains of 3, 5, or 7 links are searched by default.
Search is bounded intentionally; X-Loops, grouped links, and general AICs
are outside this module's scope.
"""

from __future__ import annotations

from sudoku.core.board import Cell, SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Premise, cell_label
from sudoku.solvers.logical.base import LogicalTechnique
from sudoku.solvers.logical.strong_links import _links, _sees


def _chain_graph(
    state: CandidateState, digit: int
) -> tuple[dict[Cell, tuple[Cell, ...]], dict[Cell, tuple[Cell, ...]]]:
    """Build strong and weak adjacency maps from current candidate positions."""
    cells = tuple(cell for cell in state.unsolved_cells()
                  if digit in state.candidates_at(*cell))
    strong: dict[Cell, set[Cell]] = {cell: set() for cell in cells}
    for link in _links(state, digit):
        a, b = link.cells
        strong[a].add(b)
        strong[b].add(a)
    weak = {cell: tuple(other for other in cells if _sees(cell, other))
            for cell in cells}
    return ({cell: tuple(sorted(neighbors)) for cell, neighbors in strong.items()},
            weak)


def _chain_eliminations(
    state: CandidateState, digit: int, chain: tuple[Cell, ...],
    candidate_cells: tuple[Cell, ...] | None = None,
) -> tuple[Elimination, ...]:
    """Only candidates outside the witness chain that see both endpoints."""
    candidates = (candidate_cells if candidate_cells is not None else
                  tuple(cell for cell in state.unsolved_cells()
                        if digit in state.candidates_at(*cell)))
    start, end = chain[0], chain[-1]
    excluded = set(chain)
    return tuple(Elimination(cell, digit) for cell in candidates
                 if cell not in excluded
                 and _sees(cell, start) and _sees(cell, end))


def _x_chain_patterns(state: CandidateState, max_links: int = 7):
    """Yield ``(digit, chain, effects)`` with one shortest witness per endpoint pair.

    Paths are simple (no repeated cells), have an odd number of links,
    and alternate strong/weak beginning with strong. Searches in ascending
    order of path length, canonicalizing each chain against its reversal.
    This is an intentionally bounded depth-first enumeration, not a claim
    to enumerate all unbounded chains.
    """
    if not isinstance(state, CandidateState):
        raise TypeError("state must be a CandidateState")
    if type(max_links) is not int or max_links < 3 or max_links > 9 or max_links % 2 == 0:
        raise ValueError("max_links must be an odd integer between 3 and 9")

    for digit in sorted(SudokuBoard.DIGITS):
        strong, weak = _chain_graph(state, digit)
        candidate_cells = tuple(sorted(strong))
        starts = tuple(cell for cell in candidate_cells if strong[cell])
        # One explanation per unordered endpoint pair; shorter chains first.
        found_endpoints: set[tuple[Cell, Cell]] = set()
        for limit in range(3, max_links + 1, 2):
            seen_paths: set[tuple[Cell, ...]] = set()
            for start in starts:
                path = [start]
                visited = {start}

                def visit() -> tuple[tuple[Cell, ...], ...]:
                    length = len(path) - 1
                    if length == limit:
                        chain = tuple(path)
                        canonical = min(chain, chain[::-1])
                        if canonical in seen_paths:
                            return ()
                        seen_paths.add(canonical)
                        endpoints = tuple(sorted((chain[0], chain[-1])))
                        if endpoints in found_endpoints:
                            return ()
                        effects = _chain_eliminations(state, digit, chain, candidate_cells)
                        if not effects:
                            return ()
                        found_endpoints.add(endpoints)
                        return ((canonical, effects),)
                    neighbors = strong[path[-1]] if length % 2 == 0 else weak[path[-1]]
                    result = []
                    for nxt in neighbors:
                        if nxt in visited:
                            continue
                        path.append(nxt)
                        visited.add(nxt)
                        result.extend(visit())
                        visited.remove(nxt)
                        path.pop()
                    return tuple(result)

                for chain, effects in visit():
                    yield digit, chain, effects


class XChain(LogicalTechnique):
    """Find single-digit X-Chains of bounded odd link length.

    ``max_links=7`` searches 4-, 6-, and 8-cell chains. Increasing to 9
    may be noticeably slower in candidate-dense states. Minimum is 3.
    """

    def __init__(self, max_links: int = 7) -> None:
        if type(max_links) is not int or max_links < 3 or max_links > 9 or max_links % 2 == 0:
            raise ValueError("max_links must be an odd integer between 3 and 9")
        self.max_links = max_links

    @property
    def name(self) -> str:
        return "X-Chain"

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        deductions = []
        for digit, chain, effects in _x_chain_patterns(state, self.max_links):
            rendered = []
            for index, cell in enumerate(chain):
                if index:
                    rendered.append("=strong=" if index % 2 else "-weak-")
                rendered.append(cell_label(cell))
            description = (
                f"X-Chain for digit {digit}: {' '.join(rendered)}. "
                f"A strong link starts and ends the alternating chain, so "
                f"at least one of {cell_label(chain[0])} or "
                f"{cell_label(chain[-1])} contains {digit}. "
                "Eliminate that digit from other cells seeing both endpoints."
            )
            deductions.append(Deduction(
                technique=self.name,
                premises=(Premise(description, chain, frozenset({digit})),),
                eliminations=effects,
            ))
        return tuple(deductions)
