"""Bounded, explainable ALS-Chains with disjoint Almost Locked Sets.

An ALS contains n unsolved cells from a single Sudoku unit and n+1
candidate digits. Consecutive ALSs are joined by *restricted common
candidates* (RCCs): every position for that digit in one ALS sees every
position in the other. Adjacent links must use different digits.

For an ALS chain A0 -x1- A1 -x2- ... -xk- Ak and a digit z shared by the
end ALSs, different from x1 and xk, at least one terminal ALS contains z.
Therefore z can be eliminated from outside cells that see all z positions
in both end ALSs.

For easier verification this conservative first version requires every
ALS in the chain to be pairwise disjoint. Overlapping/looping chains and
multi-digit/group links are intentionally not supported. The search is
bounded by maximum group size, chain length, deductions, and expansions.
"""

from __future__ import annotations

from collections import defaultdict

from sudoku.core.board import Cell
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Premise, cell_label
from sudoku.solvers.logical.als import (
    AlmostLockedSet,
    find_almost_locked_sets,
    _rcc_positions,
)
from sudoku.solvers.logical.base import LogicalTechnique
from sudoku.solvers.logical.strong_links import _sees


def _terminal_eliminations(
    state: CandidateState,
    first: AlmostLockedSet,
    last: AlmostLockedSet,
    digit: int,
    excluded: frozenset[Cell],
) -> tuple[Elimination, ...]:
    """Find external candidates seeing every terminal occurrence of digit."""
    holders = tuple(
        cell for group in (first, last) for cell in group.cells
        if digit in state.candidates_at(*cell)
    )
    if not holders:
        return ()
    return tuple(
        Elimination(cell, digit)
        for cell in state.unsolved_cells()
        if cell not in excluded
        and digit in state.candidates_at(*cell)
        and all(_sees(cell, holder) for holder in holders)
    )


def _chain_premises(
    state: CandidateState,
    groups: tuple[AlmostLockedSet, ...],
    links: tuple[int, ...],
    terminal: int,
) -> tuple[Premise, ...]:
    """Encode the entire witness, alternating ALS and RCC premises."""
    result: list[Premise] = []
    for i, group in enumerate(groups):
        result.append(Premise(
            f"ALS {i + 1}: {', '.join(map(cell_label, group.cells))} "
            f"contains {len(group.cells)} cells and candidates "
            f"{sorted(group.digits)}.",
            group.cells,
            group.digits,
        ))
        if i + 1 < len(groups):
            digit = links[i]
            positions = _rcc_positions(state, group, groups[i + 1], digit)
            assert positions is not None
            result.append(Premise(
                f"RCC {digit} excludes its simultaneous occurrence in ALS "
                f"{i + 1} and ALS {i + 2}.",
                positions,
                frozenset({digit}),
            ))
    # Explanation (not a source of trust): verifier reconstructs the above.
    result.append(Premise(
        f"At least one terminal ALS must contain {terminal}. "
        f"Eliminate {terminal} from cells seeing every terminal occurrence.",
        (),
        frozenset({terminal}),
    ))
    return tuple(result)


class ALSChain(LogicalTechnique):
    """Discover ALS-Chains of 3+ groups with bounded depth and work.

    A 2-group ALS chain is already implemented by ``ALSXZ``. Limiting
    ``max_sets`` prevents an exponential graph search from overwhelming
    the logical solver. Results are ordered deterministically.
    """

    def __init__(
        self,
        max_als_size: int = 3,
        max_sets: int = 4,
        *,
        max_deductions: int = 100,
        max_expansions: int = 20000,
    ) -> None:
        for value, name, low, high in (
            (max_als_size, 'max_als_size', 1, 4),
            (max_sets, 'max_sets', 3, 6),
            (max_deductions, 'max_deductions', 1, 1000),
            (max_expansions, 'max_expansions', 1, 1000000),
        ):
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f'{name} must be an integer in [{low}, {high}]')
        self.max_als_size = max_als_size
        self.max_sets = max_sets
        self.max_deductions = max_deductions
        self.max_expansions = max_expansions

    @property
    def name(self) -> str:
        return 'ALS-Chain'

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        if not isinstance(state, CandidateState):
            raise TypeError('state must be a CandidateState')
        groups = find_almost_locked_sets(state, max_size=self.max_als_size)
        if len(groups) < 3:
            return ()

        by_digit: dict[int, list[int]] = defaultdict(list)
        for i, group in enumerate(groups):
            for digit in group.digits:
                by_digit[digit].append(i)

        # Precompute eligible RCC edges once, in both directions.
        neighbors: list[list[tuple[int, int]]] = [[] for _ in groups]
        cellsets = [frozenset(group.cells) for group in groups]
        for i, group in enumerate(groups):
            seen_edges: set[tuple[int, int]] = set()
            for digit in sorted(group.digits):
                for j in by_digit[digit]:
                    if j == i or cellsets[i] & cellsets[j]:
                        continue
                    if _rcc_positions(state, group, groups[j], digit) is None:
                        continue
                    seen_edges.add((j, digit))
            neighbors[i] = sorted(seen_edges)

        deductions: list[Deduction] = []
        signatures: set[tuple[int, tuple[Elimination, ...]]] = set()
        expansions = 0

        def dfs(path: tuple[int, ...], links: tuple[int, ...], occupied: frozenset[Cell]) -> None:
            nonlocal expansions
            if (len(deductions) >= self.max_deductions
                    or expansions >= self.max_expansions):
                return
            current = path[-1]
            if len(path) >= 3 and path[0] < current:
                first, last = groups[path[0]], groups[current]
                for terminal in sorted((first.digits & last.digits) - {links[0], links[-1]}):
                    effects = _terminal_eliminations(
                        state, first, last, terminal, occupied
                    )
                    if not effects:
                        continue
                    signature = (terminal, effects)
                    if signature in signatures:
                        continue
                    signatures.add(signature)
                    ordered_groups = tuple(groups[i] for i in path)
                    deductions.append(Deduction(
                        technique=self.name,
                        premises=_chain_premises(state, ordered_groups, links, terminal),
                        eliminations=effects,
                    ))
                    if len(deductions) >= self.max_deductions:
                        return
            if len(path) >= self.max_sets:
                return
            for nxt, digit in neighbors[current]:
                if (links and digit == links[-1]) or cellsets[nxt] & occupied:
                    continue
                if expansions >= self.max_expansions or len(deductions) >= self.max_deductions:
                    return
                expansions += 1
                dfs(path + (nxt,), links + (digit,), occupied | cellsets[nxt])

        for i in range(len(groups)):
            if len(deductions) >= self.max_deductions or expansions >= self.max_expansions:
                break
            dfs((i,), (), cellsets[i])
        return tuple(deductions)
