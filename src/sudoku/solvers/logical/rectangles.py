"""Empty Rectangle and Unique Rectangle Types 1–6 Sudoku deductions.

All Unique Rectangle techniques REQUIRE a uniquely solvable puzzle; unlike Empty
Rectangle it is not a consequence of Sudoku house constraints alone.
"""
from __future__ import annotations

from itertools import combinations
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Premise, cell_label
from sudoku.solvers.logical.base import LogicalTechnique
from sudoku.solvers.logical.strong_links import _links, _sees, _box


def _empty_rectangle_patterns(state: CandidateState):
    """Yield (cells, digits, effects, explanation) for sound ER contradictions.

    If target t=d, one endpoint of a strong link is excluded, forcing the
    other endpoint q=d. If every candidate inside the ER box sees either
    t or q, the box has nowhere for d, hence t!=d.
    """
    for digit in range(1, 10):
        for box_index in range(9):
            br, bc = (box_index // 3) * 3, (box_index % 3) * 3
            inside = tuple((r,c) for r in range(br,br+3) for c in range(bc,bc+3)
                           if digit in state.candidates_at(r,c))
            if len(inside) < 3:
                continue
            for pivot_row in range(br,br+3):
                for pivot_col in range(bc,bc+3):
                    if not all(r == pivot_row or c == pivot_col for r,c in inside):
                        continue
                    # Proper cross: at least one candidate in each arm.
                    if not (any(r == pivot_row and c != pivot_col for r,c in inside)
                            and any(c == pivot_col and r != pivot_row for r,c in inside)):
                        continue
                    for link in _links(state, digit):
                        if link.kind not in ('row','column'):
                            continue
                        for near, far in (link.cells, link.cells[::-1]):
                            if _box(near) == box_index or _box(far) == box_index:
                                continue
                            for target in state.unsolved_cells():
                                if target in (near, far) or _box(target) == box_index:
                                    continue
                                if digit not in state.candidates_at(*target) or not _sees(target,near):
                                    continue
                                if all(_sees(p,target) or _sees(p,far) for p in inside):
                                    cells = inside + (near,far,target)
                                    explanation = (f"If {cell_label(target)} were {digit}, it would exclude "
                                        f"{cell_label(near)}, forcing {cell_label(far)}={digit}; "
                                        f"then box {box_index+1} would have no position for {digit}.")
                                    yield cells, frozenset({digit}), (Elimination(target,digit),), explanation


def _unique_rectangle_type1_patterns(state: CandidateState):
    """Type 1 deadly rectangles spanning exactly two boxes."""
    for r1,r2 in combinations(range(9),2):
        for c1,c2 in combinations(range(9),2):
            cells = ((r1,c1),(r1,c2),(r2,c1),(r2,c2))
            if len({_box(cell) for cell in cells}) != 2:
                continue
            sets = tuple(state.candidates_at(*cell) for cell in cells)
            if any(len(s)<2 for s in sets):
                continue
            for i,roof in enumerate(cells):
                bases = [sets[j] for j in range(4) if j!=i]
                pair = bases[0]
                if len(pair)!=2 or any(s!=pair for s in bases[1:]):
                    continue
                if len(sets[i]) <= 2 or not pair.issubset(sets[i]):
                    continue
                effects = tuple(Elimination(roof,d) for d in sorted(pair))
                explanation = (f"Under the unique-solution assumption, "
                    f"{cell_label(roof)} cannot contain either of {sorted(pair)}: "
                    "otherwise the four corners form a deadly rectangle with two solutions.")
                yield cells, pair, effects, explanation


class EmptyRectangle(LogicalTechnique):
    @property
    def name(self)->str:
        return 'Empty Rectangle'

    def find_deductions(self,state:CandidateState)->tuple[Deduction,...]:
        found=[]
        seen=set()
        for cells,digits,effects,explanation in _empty_rectangle_patterns(state):
            key=(cells[-1],next(iter(digits)))
            if key in seen: continue
            seen.add(key)
            found.append(Deduction(self.name,(Premise(explanation,cells,digits),),eliminations=effects))
        return tuple(found)


class UniqueRectangleType1(LogicalTechnique):
    """A uniqueness-based technique. Must be explicitly enabled by callers."""
    @property
    def name(self)->str:
        return 'Unique Rectangle Type 1'

    def find_deductions(self,state:CandidateState)->tuple[Deduction,...]:
        return tuple(Deduction(self.name,(Premise(desc,cells,digits),),eliminations=effects)
                     for cells,digits,effects,desc in _unique_rectangle_type1_patterns(state))


# Each pattern is represented by exactly four corners across two boxes.
# The 'floor' corners are a bivalue pair, and the two adjacent 'roof'
# corners may carry additional candidates.  The same two-box invariant
# is essential: it makes swapping the two deadly digits preserve boxes.
def _two_roof_rectangles(state: CandidateState):
    for r1, r2 in combinations(range(9), 2):
        for c1, c2 in combinations(range(9), 2):
            corners = ((r1, c1), (r1, c2), (r2, c1), (r2, c2))
            if len({_box(c) for c in corners}) != 2:
                continue
            sets = tuple(state.candidates_at(*c) for c in corners)
            if any(len(s) < 2 for s in sets):
                continue
            for roofs in ((0,1),(2,3),(0,2),(1,3)):
                floors = tuple(corners[i] for i in range(4) if i not in roofs)
                a, b = floors
                pair = state.candidates_at(*a)
                if len(pair) != 2 or state.candidates_at(*b) != pair:
                    continue
                roof_cells = tuple(corners[i] for i in roofs)
                roof_sets = tuple(state.candidates_at(*c) for c in roof_cells)
                if not all(pair < cs for cs in roof_sets):
                    continue
                yield corners, floors, roof_cells, pair, roof_sets


def _shared_units(cells):
    a, b = cells
    if a[0] == b[0]:
        yield tuple((a[0], c) for c in range(9))
    if a[1] == b[1]:
        yield tuple((r, a[1]) for r in range(9))
    if _box(a) == _box(b):
        br, bc = a[0] // 3 * 3, a[1] // 3 * 3
        yield tuple((r,c) for r in range(br, br+3) for c in range(bc, bc+3))


def _unique_rectangle_type2_patterns(state: CandidateState):
    """Two roofs share precisely one extra; it is true in at least one roof."""
    for corners, floors, roofs, pair, roof_sets in _two_roof_rectangles(state):
        extra_a, extra_b = (s - pair for s in roof_sets)
        if len(extra_a) != 1 or extra_a != extra_b:
            continue
        digit = next(iter(extra_a))
        effects = tuple(Elimination(cell, digit) for cell in state.unsolved_cells()
                        if cell not in corners and digit in state.candidates_at(*cell)
                        and all(_sees(cell, roof) for roof in roofs))
        if effects:
            desc = (f"Unique Rectangle Type 2: {cell_label(roofs[0])} or "
                    f"{cell_label(roofs[1])} must contain {digit} to avoid the deadly pair "
                    f"{sorted(pair)}; remove {digit} from cells seeing both.")
            yield corners, frozenset(pair | extra_a), effects, desc


def _unique_rectangle_type3_patterns(state: CandidateState):
    """The roof extras act as a virtual cell in a naked subset.

    If at least one roof takes an extra, and an outside set of k-1 cells
    together with all roof extras uses exactly k digits, these k digits
    occupy the outside cells plus *one* of the roof cells. Consequently,
    they can be removed from all other cells in their shared unit.
    """
    for corners, floors, roofs, pair, roof_sets in _two_roof_rectangles(state):
        extras = frozenset().union(*(s - pair for s in roof_sets))
        for unit in _shared_units(roofs):
            outsiders = tuple(cell for cell in unit if cell not in corners and
                              state.candidates_at(*cell))
            # Size 2–4: a virtual roof + up to three ordinary cells.
            for size in range(max(2, len(extras)), 5):
                if len(outsiders) < size - 1:
                    continue
                for selected in combinations(outsiders, size - 1):
                    digits = extras.union(*(state.candidates_at(*c) for c in selected))
                    if len(digits) != size:
                        continue
                    # This is a naked subset with one existential roof slot.
                    # Targets must be outside the roofs AND the selected cells.
                    effects = tuple(Elimination(cell, digit)
                        for cell in unit if cell not in corners and cell not in selected
                        for digit in sorted(digits & state.candidates_at(*cell)))
                    if not effects:
                        continue
                    desc = (f"Unique Rectangle Type 3: one of {cell_label(roofs[0])} "
                            f"and {cell_label(roofs[1])} must use an extra candidate; "
                            f"together with {', '.join(cell_label(c) for c in selected)}, "
                            f"the digits {sorted(digits)} are confined to {size} places in a unit.")
                    yield corners + selected, frozenset(pair | digits), effects, desc


def _unique_rectangle_type4_patterns(state: CandidateState):
    """If a deadly digit is conjugate across the roofs, eliminate the other.

    The conjugate must hold in an actual common row, column, or box.
    """
    for corners, floors, roofs, pair, roof_sets in _two_roof_rectangles(state):
        for digit in sorted(pair):
            if not any(tuple(c for c in unit if digit in state.candidates_at(*c)) == roofs
                       for unit in _shared_units(roofs)):
                continue
            other = next(iter(pair - {digit}))
            effects = tuple(Elimination(roof, other) for roof in roofs)
            desc = (f"Unique Rectangle Type 4: {digit} is conjugate between "
                    f"{cell_label(roofs[0])} and {cell_label(roofs[1])}; "
                    f"{other} in either roof would create a deadly rectangle.")
            yield corners, pair, effects, desc


def _unique_rectangle_type5_patterns(state: CandidateState):
    """HoDoKu Type 5: a single guardian digit at diagonal (or 3) corners.

    To avoid a deadly rectangle, at least one guardian must be true; the
    guardian can therefore be removed from any cell seeing every guardian.
    The 2-corner version must be diagonal (adjacent roofs are Type 2).
    """
    for r1, r2 in combinations(range(9), 2):
        for c1, c2 in combinations(range(9), 2):
            corners = ((r1, c1), (r1, c2), (r2, c1), (r2, c2))
            if len({_box(c) for c in corners}) != 2:
                continue
            cs = tuple(state.candidates_at(*cell) for cell in corners)
            for a, b in combinations(sorted(set.intersection(*(set(s) for s in cs))), 2):
                pair = frozenset((a, b))
                if any(len(s) < 2 for s in cs):
                    continue
                extras = [s - pair for s in cs]
                guardians = tuple(corners[i] for i, s in enumerate(extras) if s)
                if len(guardians) not in (2, 3):
                    continue
                if len(guardians) == 2 and not (
                    (guardians[0][0] != guardians[1][0]) and
                    (guardians[0][1] != guardians[1][1])
                ):
                    continue
                if any(len(s) != 1 for s in extras if s):
                    continue
                digit = next(iter(next(s for s in extras if s)))
                if any(s != frozenset({digit}) for s in extras if s):
                    continue
                effects = tuple(Elimination(cell, digit)
                    for cell in state.unsolved_cells()
                    if cell not in corners and digit in state.candidates_at(*cell)
                    and all(_sees(cell, g) for g in guardians))
                if effects:
                    desc = (f"Unique Rectangle Type 5: at least one of "
                            f"{', '.join(cell_label(g) for g in guardians)} must be "
                            f"{digit} to avoid a deadly rectangle on {sorted(pair)}. "
                            "Eliminate the guardian from cells seeing every guardian.")
                    yield corners, frozenset(pair | {digit}), effects, desc


def _unique_rectangle_type6_patterns(state: CandidateState):
    """HoDoKu Type 6: two diagonal floors, and X-Wing confinement of d.

    The four corner candidates for digit d are its only appearances in
    BOTH selected rows and BOTH selected columns. Under uniqueness, d
    cannot occur in either diagonal roof, or a deadly rectangle results.
    """
    for r1, r2 in combinations(range(9), 2):
        for c1, c2 in combinations(range(9), 2):
            corners = ((r1, c1), (r1, c2), (r2, c1), (r2, c2))
            if len({_box(c) for c in corners}) != 2:
                continue
            sets = [state.candidates_at(*cell) for cell in corners]
            for fi in ((0, 3), (1, 2)):
                roofs = tuple(corners[i] for i in range(4) if i not in fi)
                floors = (corners[fi[0]], corners[fi[1]])
                pair = sets[fi[0]]
                if len(pair) != 2 or sets[fi[1]] != pair:
                    continue
                if not all(pair < state.candidates_at(*roof) for roof in roofs):
                    continue
                for digit in sorted(pair):
                    if any(digit in state.candidates_at(r,c)
                           for r in (r1,r2) for c in range(9) if c not in (c1,c2)):
                        continue
                    if any(digit in state.candidates_at(r,c)
                           for c in (c1,c2) for r in range(9) if r not in (r1,r2)):
                        continue
                    effects = tuple(Elimination(roof, digit) for roof in roofs)
                    desc = (f"Unique Rectangle Type 6: candidate {digit} is "
                            "restricted to the four rectangle corners in both "
                            "rows and columns. Putting it in a roof would "
                            "force a deadly rectangle, so remove it from both roofs.")
                    yield corners, pair, effects, desc


class _UniqueRectangleVariant(LogicalTechnique):
    """Base for opt-in uniqueness patterns with independent verification."""
    _type: int

    @property
    def name(self) -> str:
        return f"Unique Rectangle Type {self._type}"

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        pattern_function = _UNIQUE_RECTANGLE_PATTERNS[self._type]
        found = []
        seen = set()
        for cells, digits, effects, explanation in pattern_function(state):
            key = tuple(effects)
            if key in seen:
                continue
            seen.add(key)
            found.append(Deduction(self.name,
                (Premise(explanation, cells, digits),), eliminations=effects))
        return tuple(found)


class UniqueRectangleType2(_UniqueRectangleVariant):
    _type = 2


class UniqueRectangleType3(_UniqueRectangleVariant):
    _type = 3


class UniqueRectangleType4(_UniqueRectangleVariant):
    _type = 4


class UniqueRectangleType5(_UniqueRectangleVariant):
    _type = 5


class UniqueRectangleType6(_UniqueRectangleVariant):
    _type = 6


_UNIQUE_RECTANGLE_PATTERNS = {
    1: _unique_rectangle_type1_patterns,
    2: _unique_rectangle_type2_patterns,
    3: _unique_rectangle_type3_patterns,
    4: _unique_rectangle_type4_patterns,
    5: _unique_rectangle_type5_patterns,
    6: _unique_rectangle_type6_patterns,
}


def _hidden_rectangle_patterns(state: CandidateState):
    """Hidden UR: a bivalue corner and orthogonal conjugate links at its opposite.

    All four cells span exactly two boxes and retain both deadly candidates.
    At least two corners must have extras, distinguishing it from UR Type 1.
    """
    for r1, r2 in combinations(range(9), 2):
        for c1, c2 in combinations(range(9), 2):
            corners = ((r1,c1),(r1,c2),(r2,c1),(r2,c2))
            if len({_box(c) for c in corners}) != 2:
                continue
            sets = tuple(state.candidates_at(*c) for c in corners)
            if any(not s for s in sets):
                continue
            for anchor in corners:
                pair = sets[corners.index(anchor)]
                if len(pair) != 2 or any(not pair.issubset(s) for s in sets):
                    continue
                if sum(len(s)>2 for s in sets) < 2:
                    continue
                target = next(c for c in corners if c[0]!=anchor[0] and c[1]!=anchor[1])
                for locked_digit in sorted(pair):
                    # Digit confined to the two rectangle columns in the target row,
                    # and the two rectangle rows in the target column.
                    row, col = target
                    if any(locked_digit in state.candidates_at(row,c)
                           for c in range(9) if c not in (c1,c2)):
                        continue
                    if any(locked_digit in state.candidates_at(rr,col)
                           for rr in range(9) if rr not in (r1,r2)):
                        continue
                    other = next(iter(pair - {locked_digit}))
                    desc = (f"Hidden Unique Rectangle: {cell_label(anchor)} is bivalue "
                            f"{sorted(pair)}; {locked_digit} is confined to the rectangle "
                            f"in row {row+1} and column {col+1}. Under uniqueness, "
                            f"remove {other} from {cell_label(target)}.")
                    yield corners, pair, (Elimination(target, other),), desc


class HiddenUniqueRectangle(LogicalTechnique):
    """Hidden Unique Rectangle; requires a uniquely solvable original puzzle."""

    @property
    def name(self) -> str:
        return "Hidden Unique Rectangle"

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        found = []
        seen = set()
        for cells, digits, effects, explanation in _hidden_rectangle_patterns(state):
            key = (cells, effects)
            if key in seen:
                continue
            seen.add(key)
            found.append(Deduction(self.name, (Premise(explanation, cells, digits),),
                                   eliminations=effects))
        return tuple(found)
