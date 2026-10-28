"""Complementary disjoint locked groups in *standard* Sudoku.

A naked subset partitions the remaining cells/digits of a unit into two
non-overlapping groups. This is equivalent to a complementary hidden subset,
not an extra Sudoku constraint. This technique provides a distinct explanatory
view of existing deductions; it does not increase deductive power.
"""
from __future__ import annotations
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Premise
from sudoku.solvers.logical.base import LogicalTechnique
from sudoku.solvers.logical.subsets import NakedSubset
from sudoku.solvers.logical.singles import _units


class DisjointGroups(LogicalTechnique):
    @property
    def name(self) -> str:
        return "Disjoint Groups"

    def find_deductions(self, state: CandidateState) -> tuple[Deduction,...]:
        if not isinstance(state,CandidateState):
            raise TypeError("state must be a CandidateState")
        results = []
        seen = set()
        # A naked subset of size 2–4 separates the unit's missing digits
        # into disjoint groups; deduce the same eliminations with an explicit
        # complementary-group interpretation.
        for size in (2,3,4):
            for found in NakedSubset(size).find_deductions(state):
                premise = found.premises[0]
                matched = next(((kind,index,unit) for kind,index,unit in _units()
                                if set(premise.cells).issubset(unit)
                                and any(e.cell in unit for e in found.eliminations)),None)
                if matched is None:
                    continue
                kind,index,unit = matched
                board=state.board
                missing = frozenset(range(1,10)) - {board.value_at(*p) for p in unit}
                remainder = missing - premise.digits
                other_cells = tuple(p for p in unit if board.value_at(*p)==0 and p not in premise.cells)
                description = (f"In {kind} {index+1}, cells {premise.cells} reserve digits "
                               f"{sorted(premise.digits)}; the remaining cells form a disjoint "
                               f"group using digits {sorted(remainder)}. The groups cannot share digits.")
                key=(found.eliminations,kind,index)
                if key in seen: continue
                seen.add(key)
                results.append(Deduction(self.name,(Premise(description,premise.cells,premise.digits),),
                                         eliminations=found.eliminations))
        return tuple(results)
