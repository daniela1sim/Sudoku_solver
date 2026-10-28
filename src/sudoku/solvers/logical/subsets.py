"""Explainable naked and hidden subsets (pairs, triples, quads)."""

from __future__ import annotations

from itertools import combinations

from sudoku.core.board import Cell, SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Premise, cell_label
from sudoku.solvers.logical.base import LogicalTechnique
from sudoku.solvers.logical.singles import _units

_NAMES = {2: 'Pair', 3: 'Triple', 4: 'Quad'}


def _deduction(name: str, kind: str, index: int, cells: tuple[Cell, ...],
               digits: frozenset[int], effects: tuple[Elimination, ...]) -> Deduction:
    labels = ', '.join(cell_label(cell) for cell in cells)
    values = ', '.join(str(d) for d in sorted(digits))
    if name.startswith('Naked'):
        explanation = (f'In {kind} {index + 1}, cells {labels} collectively have only '
                       f'the {len(digits)} candidates {{{values}}}. These digits are reserved '
                       'for these cells and can be removed from other cells in the unit.')
    else:
        explanation = (f'In {kind} {index + 1}, digits {{{values}}} can occur only in '
                       f'cells {labels}. Those cells must contain these digits, '
                       'so their other candidates can be removed.')
    return Deduction(name, (Premise(explanation, cells, digits),), eliminations=effects)


class NakedSubset(LogicalTechnique):
    """Find n cells in a unit whose combined candidate set has size n."""

    def __init__(self, size: int):
        if type(size) is not int or size not in _NAMES:
            raise ValueError('size must be 2, 3, or 4')
        self.size = size

    @property
    def name(self) -> str:
        return f'Naked {_NAMES[self.size]}'

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        if not isinstance(state, CandidateState):
            raise TypeError('state must be a CandidateState')
        results = []
        seen = set()
        for kind, index, unit in _units():
            eligible = [cell for cell in unit if 1 <= len(state.candidates_at(*cell)) <= self.size]
            for cells in combinations(eligible, self.size):
                digits = frozenset().union(*(state.candidates_at(*cell) for cell in cells))
                if len(digits) != self.size:
                    continue
                # Reject overfull groups: more than n cells confined to n digits.
                if any(cell not in cells and state.candidates_at(*cell) and
                       state.candidates_at(*cell) <= digits for cell in unit):
                    continue
                effects = tuple(Elimination(cell, digit)
                                for cell in unit if cell not in cells
                                for digit in sorted(digits & state.candidates_at(*cell)))
                if not effects:
                    continue
                key = (cells, digits, effects)
                if key not in seen:
                    seen.add(key)
                    results.append(_deduction(self.name, kind, index, cells, digits, effects))
        return tuple(results)


class HiddenSubset(LogicalTechnique):
    """Find n missing digits restricted to the same n cells of one unit."""

    def __init__(self, size: int):
        if type(size) is not int or size not in _NAMES:
            raise ValueError('size must be 2, 3, or 4')
        self.size = size

    @property
    def name(self) -> str:
        return f'Hidden {_NAMES[self.size]}'

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        if not isinstance(state, CandidateState):
            raise TypeError('state must be a CandidateState')
        results = []
        seen = set()
        board = state.board
        for kind, index, unit in _units():
            placed = {board.value_at(*cell) for cell in unit} - {0}
            positions = {digit: frozenset(cell for cell in unit if digit in state.candidates_at(*cell))
                         for digit in sorted(SudokuBoard.DIGITS - placed)}
            eligible = [digit for digit, cells in positions.items() if 1 <= len(cells) <= self.size]
            for group in combinations(eligible, self.size):
                cells_set = frozenset().union(*(positions[d] for d in group))
                if len(cells_set) != self.size:
                    continue
                cells = tuple(cell for cell in unit if cell in cells_set)
                digits = frozenset(group)
                effects = tuple(Elimination(cell, digit)
                                for cell in cells
                                for digit in sorted(state.candidates_at(*cell) - digits))
                if not effects:
                    continue
                key = (cells, digits, effects)
                if key not in seen:
                    seen.add(key)
                    results.append(_deduction(self.name, kind, index, cells, digits, effects))
        return tuple(results)


class NakedPair(NakedSubset):
    def __init__(self):
        super().__init__(2)


class HiddenPair(HiddenSubset):
    def __init__(self):
        super().__init__(2)


class NakedTriple(NakedSubset):
    def __init__(self):
        super().__init__(3)


class HiddenTriple(HiddenSubset):
    def __init__(self):
        super().__init__(3)


class NakedQuad(NakedSubset):
    def __init__(self):
        super().__init__(4)


class HiddenQuad(HiddenSubset):
    def __init__(self):
        super().__init__(4)
