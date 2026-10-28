                            if r not in (base,fin_row)
                            and _box(cell(r,corner))==fin_box
                            and d in state.candidates_at(*cell(r,corner)))
                        if not targets: continue
                        corners=(cell(base,a),cell(base,b),cell(fin_row,a),cell(fin_row,b))
                        fins=tuple(cell(fin_row,c) for c in fin_cols)
                        explanation=(f"Finned X-Wing on {d}: base line {base+1} has two positions; "
                            f"line {fin_row+1} has the same corners plus fins "
                            f"{', '.join(cell_label(x) for x in fins)} confined to the "
                            "corner box. Either a fin is true or the ordinary X-Wing "
                            "holds; both cases exclude the target candidates.")
                        yield corners+fins,frozenset({d}),targets,explanation


class FinnedXWing(LogicalTechnique):
    @property
    def name(self)->str:
        return 'Finned X-Wing'

    def find_deductions(self,state:CandidateState)->tuple[Deduction,...]:
        found=[]; seen=set()
        for cells,digits,effects,explanation in _finned_xwing_patterns(state):
            key=(cells,effects)
            if key in seen: continue
            seen.add(key)
            found.append(Deduction(self.name,(Premise(explanation,cells,digits),),eliminations=effects))
        return tuple(found)


def _general_finned_fish_patterns(state: CandidateState, size: int):
    """Standard single-box finned fish of a given size, both orientations.

    A fin is an uncovered candidate in a chosen base line. Targets are in
    cover lines outside all base lines and see every fin. Allow degenerate
    (sashimi) base patterns; the same disjunctive proof remains valid.
    """
    if size not in (3, 4):
        raise ValueError("size must be 3 or 4")
    for digit in range(1, 10):
        for transpose in (False, True):
            def cell(r, c):
                return (c, r) if transpose else (r, c)
            positions = {
                r: frozenset(c for c in range(9)
                             if digit in state.candidates_at(*cell(r, c)))
                for r in range(9)
            }
            for bases in combinations(range(9), size):
                if any(not positions[r] for r in bases):
                    continue
                # Only one base line may contain uncovered candidates (the fins).
                # Every other base line must fit completely within `size`
                # cover columns, and therefore have at most `size` candidates.
                if sum(len(positions[r]) <= size for r in bases) < size - 1:
                    continue
                for covers in combinations(range(9), size):
                    cover_set = frozenset(covers)
                    fins = tuple(cell(r,c) for r in bases for c in sorted(positions[r]-cover_set))
                    if not fins or len({_box(c) for c in fins}) != 1:
                        continue
                    fin_lines = {r for r in bases if positions[r]-cover_set}
                    if len(fin_lines) != 1:
                        continue
                    if any(not positions[r].intersection(cover_set) for r in bases):
                        continue
                    # To exclude candidate d in a cover line, it must see all fins.
                    effects = tuple(
                        Elimination(cell(r,c), digit)
                        for r in range(9) if r not in bases
                        for c in covers
                        if digit in state.candidates_at(*cell(r,c))
                        and all(_sees_fish(cell(r,c), fin) for fin in fins)
                    )
                    if not effects:
                        continue
                    anchor = tuple(cell(r,c) for r in bases for c in covers
                                   if c in positions[r])
                    description = (
                        f"Finned {'Swordfish' if size == 3 else 'Jellyfish'} on {digit}: "
                        f"{size} base lines and {size} cover lines; all uncovered "
                        f"candidates ({', '.join(cell_label(c) for c in fins)}) "
                        "lie in one box. Each target sees every fin and is "
                        "excluded whether a fin is true or the fish holds."
                    )
                    yield anchor + fins, frozenset({digit}), effects, description


def _sees_fish(a, b):
    return a != b and (a[0] == b[0] or a[1] == b[1] or _box(a) == _box(b))


class _FinnedFish(LogicalTechnique):
    size: int

    @property
    def name(self) -> str:
        return 'Finned Swordfish' if self.size == 3 else 'Finned Jellyfish'

    def find_deductions(self, state: CandidateState) -> tuple[Deduction, ...]:
        found = []
        seen = set()
        for cells, digits, effects, explanation in _general_finned_fish_patterns(state, self.size):
            key = (cells, effects)
            if key in seen:
                continue
            seen.add(key)
            found.append(Deduction(self.name, (Premise(explanation, cells, digits),),
                                   eliminations=effects))
        return tuple(found)


class FinnedSwordfish(_FinnedFish):
    size = 3


class FinnedJellyfish(_FinnedFish):
    size = 4
