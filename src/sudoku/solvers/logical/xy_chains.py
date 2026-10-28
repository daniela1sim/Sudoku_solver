"""Bounded XY-Chains: implications through bivalue Sudoku cells.

Every chain cell has exactly two candidates. Consecutive cells see one
another and share the outgoing digit of the previous cell. If the first
cell is *not* the endpoint digit, each subsequent cell is forced to its
other digit; the last cell is then forced to the endpoint digit.

Thus at least one endpoint contains that digit, allowing elimination from
any other cell seeing both endpoints. This is a non-uniqueness technique.

Three-cell XY-Chains coincide with XY-Wings and can be enabled explicitly
via min_cells=3. The default starts at four cells to avoid duplication.
"""

from __future__ import annotations

from sudoku.core.board import Cell
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Premise, cell_label
from sudoku.solvers.logical.base import LogicalTechnique
from sudoku.solvers.logical.strong_links import _sees


def _bivalue_graph(state: CandidateState) -> tuple[
    dict[Cell, frozenset[int]], dict[tuple[Cell, int], tuple[Cell, ...]]
]:
    """Return bivalue cells and the peers containing each link candidate."""
    candidates = {
        cell: state.candidates_at(*cell)
        for cell in state.unsolved_cells()
        if len(state.candidates_at(*cell)) == 2
    }
    adjacency = {
        (cell, digit): tuple(
            other for other in sorted(candidates)
            if other != cell and digit in candidates[other] and _sees(cell, other)
        )
        for cell, choices in candidates.items()
        for digit in sorted(choices)
    }
    return candidates, adjacency


def _xy_chain_eliminations(
    state: CandidateState, digit: int, chain: tuple[Cell, ...]
) -> tuple[Elimination, ...]:
    """Return currently present endpoint eliminations outside the chain."""
    start, end = chain[0], chain[-1]
    blocked = set(chain)
    return tuple(
        Elimination(cell, digit)
        for cell in sorted(state.unsolved_cells())
        if cell not in blocked
        and digit in state.candidates_at(*cell)
        and _sees(cell, start)
        and _sees(cell, end)
    )


def _xy_chain_patterns(
    state: CandidateState, min_cells: int = 4, max_cells: int = 8
):
    """Yield (endpoint digit, ordered chain, eliminations) in stable order.

    Search shortest chains first, returning at most one witness for each
    (digit, unordered endpoints) pair. The depth bound controls the
    exponential growth of simple paths through bivalue cells.
    """
    if not isinstance(state, CandidateState):
        raise TypeError("state must be a CandidateState")
    if (type(min_cells) is not int or type(max_cells) is not int
            or not 3 <= min_cells <= max_cells <= 10):
        raise ValueError("require integers 3 <= min_cells <= max_cells <= 10")

    choices, adjacency = _bivalue_graph(state)
    found: set[tuple[int, Cell, Cell]] = set()
    for length in range(min_cells, max_cells + 1):
        for digit in range(1, 10):
            for start in sorted(choices):
                if digit not in choices[start]:
                    continue
                outgoing = next(iter(choices[start] - {digit}))
                path = [start]
                visited = {start}

                def walk(link_digit: int):
                    if len(path) == length:
                        if link_digit != digit:
                            return
                        end = path[-1]
                        key = (digit, min(start, end), max(start, end))
                        if key in found:
                            return
                        chain = tuple(path)
                        effects = _xy_chain_eliminations(state, digit, chain)
                        if effects:
                            found.add(key)
                            yield min(chain, chain[::-1]), effects
                        return

                    for next_cell in adjacency[path[-1], link_digit]:
                        if next_cell in visited:
                            continue
                        next_digit = next(iter(choices[next_cell] - {link_digit}))
                        path.append(next_cell)
                        visited.add(next_cell)
                        yield from walk(next_digit)
                        visited.remove(next_cell)
                        path.pop()

                for chain, effects in walk(outgoing):
                    yield digit, chain, effects


class XYChain(LogicalTechnique):
    """Discover XY-Chains with a configurable bound on their cell count.

    Defaults to 4..8 cells, excluding 3-cell XY-Wings, already supported
    by the dedicated XYWing technique. Use min_cells=3 to include them.
    """

    def __init__(self, max_cells: int = 8, *, min_cells: int = 4) -> None:
        if (type(min_cells) is not int or type(max_cells) is not int
                or not 3 <= min_cells <= max_cells <= 10):
            raise ValueError("require integers 3 <= min_cells <= max_cells <= 10")
        self.min_cells = min_cells
        self.max_cells = max_cells

    @property
    def name(self) -> str:
        return "XY-Chain"

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        deductions = []
        for digit, chain, effects in _xy_chain_patterns(
            state, self.min_cells, self.max_cells
        ):
            path = " → ".join(
                f"{cell_label(cell)} {sorted(state.candidates_at(*cell))}"
                for cell in chain
            )
            description = (
                f"XY-Chain on {digit}: {path}. Each bivalue cell sees the next "
                "on the linking digit; if the first endpoint is not "
                f"{digit}, the last must be {digit}. Therefore at least "
                f"one endpoint is {digit}; remove {digit} from other cells "
                "seeing both endpoints."
            )
            deductions.append(Deduction(
                technique=self.name,
                premises=(Premise(description, chain, frozenset({digit})),),
                eliminations=effects,
            ))
        return tuple(deductions)
