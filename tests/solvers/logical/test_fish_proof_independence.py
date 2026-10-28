"""Adversarial checks for independent fish proof verification.

These fixtures use synthetic candidate states to isolate individual mathematical
rules.  The reference-oracle test uses a real uniquely solvable puzzle.
"""

from dataclasses import replace

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Elimination, Premise
from sudoku.solvers.logical.fish import XWing, Swordfish, Jellyfish
from sudoku.solvers.logical.finned_fish import FinnedXWing, FinnedSwordfish, FinnedJellyfish
from sudoku.solvers.logical.verification import DeductionVerifier


def empty_state():
    return CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))


def basic_state(size, transpose=False):
    state = empty_state()
    bases = tuple(range(0, 2 * size, 2))
    covers = tuple(range(0, 2 * size, 2))
    for base in bases:
        for cover in range(9):
            if cover not in covers:
                cell = (cover, base) if transpose else (base, cover)
                state._candidates[cell].discard(1)
    return state


def finned_xwing_state(transpose=False):
    state = empty_state()
    def cell(r, c):
        return (c, r) if transpose else (r, c)
    for c in range(9):
        if c not in (1, 4):
            state._candidates[cell(0, c)].discard(1)
        if c not in (1, 4, 5):
            state._candidates[cell(3, c)].discard(1)
    return state


def finned_state(size, transpose=False):
    state = empty_state()
    positions = ({0: {0, 3}, 3: {0, 3, 4, 6}, 6: {3, 6}} if size == 3 else
                 {0: {0, 2}, 2: {2, 3}, 3: {0, 3, 4, 6}, 6: {3, 6}})
    def cell(r, c):
        return (c, r) if transpose else (r, c)
    for r in range(9):
        for c in range(9):
            state._candidates[cell(r, c)].discard(1)
    for r, positions_in_row in positions.items():
        for c in positions_in_row:
            state._candidates[cell(r, c)].add(1)
    state._candidates[cell(4, 3)].add(1)
    return state


@pytest.mark.parametrize('technique,state_factory', [
    (XWing, lambda: basic_state(2)),
    (Swordfish, lambda: basic_state(3, True)),
    (Jellyfish, lambda: basic_state(4)),
    (FinnedXWing, lambda: finned_xwing_state(True)),
    (FinnedSwordfish, lambda: finned_state(3)),
    (FinnedJellyfish, lambda: finned_state(4, True)),
])
def test_fish_verified_without_discovery(monkeypatch, technique, state_factory):
    import sudoku.solvers.logical.fish as fish
    import sudoku.solvers.logical.finned_fish as finned_fish

    state = state_factory()
    tech = technique()
    deduction = tech.find_first(state)
    assert deduction is not None
    assert deduction.eliminations

    def blocked(*_args, **_kwargs):
        raise AssertionError('Verifier must not invoke fish discovery')
    monkeypatch.setattr(fish, '_fish_patterns', blocked)
    monkeypatch.setattr(finned_fish, '_finned_xwing_patterns', blocked)
    monkeypatch.setattr(finned_fish, '_general_finned_fish_patterns', blocked)
    DeductionVerifier.verify(state, tech, deduction)


@pytest.mark.parametrize('technique,state_factory', [
    (XWing, lambda: basic_state(2)),
    (Swordfish, lambda: basic_state(3)),
    (Jellyfish, lambda: basic_state(4)),
    (FinnedXWing, lambda: finned_xwing_state()),
    (FinnedSwordfish, lambda: finned_state(3)),
    (FinnedJellyfish, lambda: finned_state(4)),
])
def test_rejects_invalid_fish_witness_and_wrong_digit(technique, state_factory):
    state = state_factory()
    tech = technique()
    good = tech.find_first(state)
    assert good is not None
    premise = good.premises[0]

    shortened = replace(good, premises=(replace(premise, cells=premise.cells[:-1]),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, tech, shortened)

    other_digit = 9 if next(iter(premise.digits)) != 9 else 8
    wrong_digit = replace(good, premises=(replace(premise, digits=frozenset({other_digit})),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, tech, wrong_digit)

    bogus_target = replace(good, eliminations=(Elimination((8, 8), 9),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, tech, bogus_target)


def test_rejects_extra_candidate_in_basic_fish_base():
    state = basic_state(2)
    deduction = XWing().find_first(state)
    assert deduction is not None
    state._candidates[(0, 8)].add(1)
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, XWing(), deduction)


def test_rejects_missing_finned_xwing_corner():
    state = finned_xwing_state()
    deduction = FinnedXWing().find_first(state)
    assert deduction is not None
    state._candidates[(0, 1)].discard(1)
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, FinnedXWing(), deduction)


def test_rejects_split_fins_in_general_fish():
    state = finned_state(3)
    deduction = FinnedSwordfish().find_first(state)
    assert deduction is not None
    # Add a fin outside the original fin box.
    state._candidates[(3, 8)].add(1)
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, FinnedSwordfish(), deduction)


def test_rejects_target_that_does_not_see_fins():
    state = finned_state(3)
    deduction = FinnedSwordfish().find_first(state)
    assert deduction is not None
    # R2C4 is on the cover column, but cannot see the fin in R4C5.
    state._candidates[(1, 3)].add(1)
    forged = replace(deduction, eliminations=(Elimination((1, 3), 1),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, FinnedSwordfish(), forged)


def test_basic_fish_premise_description_is_not_a_proof():
    state = basic_state(2)
    deduction = XWing().find_first(state)
    assert deduction is not None
    changed = replace(deduction, premises=(replace(deduction.premises[0], description='different prose'),))
    DeductionVerifier.verify(state, XWing(), changed)


def test_finned_xwing_both_corners_can_share_fin_box():
    """Valid corner geometry must not require the covers to be in different boxes."""
    state = empty_state()
    for c in range(9):
        if c not in (3, 4):
            state._candidates[(0, c)].discard(1)
        if c not in (3, 4, 5):
            state._candidates[(3, c)].discard(1)
    technique = FinnedXWing()
    candidates = [d for d in technique.find_deductions(state)
                  if Elimination((4, 3), 1) in d.eliminations]
    assert candidates
    for deduction in candidates:
        DeductionVerifier.verify(state, technique, deduction)
