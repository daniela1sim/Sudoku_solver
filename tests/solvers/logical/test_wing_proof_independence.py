"""Adversarial tests for witness-directed Wing verification.

Verifier must validate the claimed local logical relationships rather than
run pattern discovery and compare its output against the claim.
"""

from dataclasses import replace

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Elimination, Placement, Premise
from sudoku.solvers.logical.verification import DeductionVerifier
from sudoku.solvers.logical.wings import XYWing, XYZWing, WWing
from sudoku.solvers.logical.wing_proofs import verify_wing


def pattern(technique):
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    if technique is XYWing:
        assignments = {(1, 1): {1, 2}, (1, 4): {1, 3}, (4, 1): {2, 3}}
        target, digit = (4, 4), 3
    elif technique is XYZWing:
        assignments = {(1, 1): {1, 2, 3}, (1, 2): {1, 3}, (2, 1): {2, 3}}
        target, digit = (2, 2), 3
    else:
        for col in range(9):
            if col not in (0, 3):
                state.eliminate(1, col, 1)
        assignments = {(0, 0): {1, 2}, (3, 3): {1, 2}}
        target, digit = (0, 3), 2
    for cell, candidates in assignments.items():
        state._candidates[cell] = candidates.copy()
    state._assert_consistent()
    found = [
        d for d in technique().find_deductions(state)
        if Elimination(target, digit) in d.eliminations
    ]
    assert found
    return state, found[0], target, digit


@pytest.mark.parametrize('technique', [XYWing, XYZWing, WWing])
def test_independent_of_detector_and_all_its_helpers(monkeypatch, technique):
    state, deduction, _, _ = pattern(technique)
    import sudoku.solvers.logical.wings as detector
    import sudoku.solvers.logical.strong_links as strong_links

    def broken(*args, **kwargs):
        raise AssertionError('Wing detector or one of its helpers was called')

    monkeypatch.setattr(detector, '_wing_patterns', broken)
    monkeypatch.setattr(detector, '_common_eliminations', broken)
    monkeypatch.setattr(detector, '_sees', broken)
    monkeypatch.setattr(strong_links, '_links', broken)
    DeductionVerifier.verify(state, technique(), deduction)


@pytest.mark.parametrize('technique', [XYWing, XYZWing, WWing])
def test_proof_is_nonmutating_and_accepts_subset_of_effects(technique):
    state, deduction, target, digit = pattern(technique)
    before = {(r, c): state.candidates_at(r, c) for r in range(9) for c in range(9)}
    smaller = replace(deduction, eliminations=(Elimination(target, digit),))
    assert DeductionVerifier.verify(state, technique(), smaller) is None
    assert before == {(r, c): state.candidates_at(r, c) for r in range(9) for c in range(9)}


@pytest.mark.parametrize('technique', [XYWing, XYZWing, WWing])
def test_rejects_different_technique_or_premise_digits(technique):
    state, deduction, _, _ = pattern(technique)
    incorrect = replace(deduction, technique='Impersonated Wing')
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, technique(), incorrect)
    premise = deduction.premises[0]
    wrong_digits = replace(deduction, premises=(replace(premise, digits=frozenset({9})),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, technique(), wrong_digits)


@pytest.mark.parametrize('technique', [XYWing, XYZWing, WWing])
def test_rejects_wrong_target_digit(technique):
    state, deduction, target, digit = pattern(technique)
    wrong_digit = next(d for d in range(1, 10) if d != digit)
    forged = replace(deduction, eliminations=(Elimination(target, wrong_digit),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, technique(), forged)


@pytest.mark.parametrize('technique,forged_cell', [
    (XYWing, (1, 5)),  # sees wing in row 2, not other wing in column 2
    (XYZWing, (1, 5)), # sees pivot and first wing, not the second
    (WWing, (0, 4)),   # sees first wing, not second
])
def test_rejects_elimination_without_all_required_peers(technique, forged_cell):
    state, deduction, _, digit = pattern(technique)
    forged = replace(deduction, eliminations=(Elimination(forged_cell, digit),))
    with pytest.raises(ValueError, match='not justified'):
        DeductionVerifier.verify(state, technique(), forged)


@pytest.mark.parametrize('technique', [XYWing, XYZWing, WWing])
def test_rejects_eliminating_pattern_cell(technique):
    state, deduction, _, digit = pattern(technique)
    forged = replace(deduction, eliminations=(Elimination(deduction.premises[0].cells[0], digit),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, technique(), forged)


@pytest.mark.parametrize('technique', [XYWing, XYZWing, WWing])
def test_rejects_stale_candidate_at_target(technique):
    state, deduction, target, digit = pattern(technique)
    state.eliminate(*target, digit)
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, technique(), deduction)


@pytest.mark.parametrize('technique', [XYWing, XYZWing, WWing])
def test_rejects_placement_in_wing_deduction(technique):
    state, deduction, target, digit = pattern(technique)
    forged = replace(deduction, placements=(Placement((8, 8), 9),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, technique(), forged)


@pytest.mark.parametrize('technique', [XYWing, XYZWing, WWing])
def test_rejects_extra_premise(technique):
    state, deduction, _, _ = pattern(technique)
    forged = replace(deduction, premises=deduction.premises + (
        Premise('Extra', ((8, 8),), frozenset({9})),
    ))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, technique(), forged)


def test_xy_wing_requires_a_bivalue_pivot_and_distinct_wing_digits():
    state, deduction, _, _ = pattern(XYWing)
    state._candidates[(1, 1)] = {1, 2, 4}
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, XYWing(), deduction)
    state._candidates[(1, 1)] = {1, 2}
    state._candidates[(4, 1)] = {1, 3}
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, XYWing(), deduction)


def test_xy_wing_requires_both_wings_to_see_the_pivot():
    state, deduction, _, _ = pattern(XYWing)
    p = deduction.premises[0]
    # The moved bivalue wing still has the correct candidates, but no pivot peer.
    state._candidates[(5, 5)] = {1, 3}
    bad = replace(deduction, premises=(replace(p, cells=(p.cells[0], (5, 5), p.cells[2])),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, XYWing(), bad)


def test_xyz_wing_requires_pivot_to_contain_target_and_exactly_three_digits():
    state, deduction, _, _ = pattern(XYZWing)
    state._candidates[(1, 1)] = {1, 2}
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, XYZWing(), deduction)
    state._candidates[(1, 1)] = {1, 2, 3, 4}
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, XYZWing(), deduction)


def test_xyz_wing_rejects_target_that_sees_both_wings_but_not_pivot():
    # With pivot and wings in different boxes, target can see two wings while
    # failing to see the pivot. XYZ (unlike XY) requires all THREE peers.
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    pivot, a, b, target = (0, 0), (0, 4), (4, 0), (4, 4)
    for cell, ds in ((pivot, {1, 2, 3}), (a, {1, 3}), (b, {2, 3})):
        state._candidates[cell] = ds
    premise = Premise('Forged XYZ-Wing', (pivot, a, b), frozenset({1, 2, 3}))
    from sudoku.core.deduction import Deduction
    deduction = Deduction('XYZ-Wing', (premise,), eliminations=(Elimination(target, 3),))
    with pytest.raises(ValueError, match='not justified'):
        DeductionVerifier.verify(state, XYZWing(), deduction)


def test_w_wing_rejects_nonconjugate_link_after_new_candidate():
    state, deduction, _, _ = pattern(WWing)
    # This is the only unit containing both link endpoints (row 2).
    state._candidates[(1, 2)].add(1)
    with pytest.raises(ValueError, match='conjugate'):
        DeductionVerifier.verify(state, WWing(), deduction)


def test_w_wing_rejects_weak_pair_that_does_not_connect_to_wing():
    state, deduction, _, _ = pattern(WWing)
    p = deduction.premises[0]
    cells = (p.cells[0], p.cells[2], p.cells[1], p.cells[3])
    bad = replace(deduction, premises=(replace(p, cells=cells),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, WWing(), bad)


def test_w_wing_requires_nonseeing_bivalue_endpoints():
    state, deduction, _, _ = pattern(WWing)
    state._candidates[(0, 1)] = {1, 2}
    p = deduction.premises[0]
    bad = replace(deduction, premises=(replace(p, cells=(p.cells[0], p.cells[1], p.cells[2], (0, 1))),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, WWing(), bad)


def test_w_wing_rejects_mismatched_bivalue_digits():
    state, deduction, _, _ = pattern(WWing)
    state._candidates[(3, 3)] = {1, 3}
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, WWing(), deduction)


@pytest.mark.parametrize('pair,first,second,target', [
    (((1, 1), (4, 1)), (0, 0), (4, 4), (0, 4)),  # column conjugacy
    (((1, 1), (2, 2)), (1, 4), (4, 2), (4, 4)),  # box conjugacy
])
def test_w_wing_conjugacy_in_columns_and_boxes(pair, first, second, target):
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    a, b = pair
    if a[1] == b[1]:
        unit = [(row, a[1]) for row in range(9)]
    else:
        unit = [(row, col) for row in range(3) for col in range(3)]
    for cell in unit:
        if cell not in pair:
            state.eliminate(*cell, 1)
    for cell in (first, second):
        state._candidates[cell] = {1, 2}
    from sudoku.core.deduction import Deduction
    deduction = Deduction(
        'W-Wing', (Premise('Column or box conjugate', (first, a, b, second), frozenset({1, 2})),),
        eliminations=(Elimination(target, 2),),
    )
    verify_wing(state, deduction, name='W-Wing')
    DeductionVerifier.verify(state, WWing(), deduction)


def test_w_wing_rejects_link_with_no_shared_unit():
    state, deduction, _, _ = pattern(WWing)
    p = deduction.premises[0]
    # Still a 4-cell witness; the link endpoints cannot be a conjugate pair.
    state._candidates[(4, 4)] = {1, 2}
    bad = replace(deduction, premises=(replace(p, cells=(p.cells[0], p.cells[1], (4, 4), p.cells[3])),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, WWing(), bad)


def test_w_wing_link_endpoint_is_valid_elimination_target_when_it_sees_both_wings():
    # The W-Wing detector excludes only the two bivalue W wings from targets.
    # A conjugate-link endpoint may itself be a legitimate elimination target.
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    wing_a, wing_b, link_a, link_b = (0, 0), (3, 3), (0, 3), (1, 3)
    # Force a conjugate pair in the upper-middle box (not column 4):
    # wing_b contains digit 1 in the same column, but lies outside the box.
    for row in range(3):
        for col in range(3, 6):
            if (row, col) not in (link_a, link_b):
                state.eliminate(row, col, 1)
    state._candidates[wing_a] = {1, 2}
    state._candidates[wing_b] = {1, 2}
    from sudoku.core.deduction import Deduction
    deduction = Deduction(
        'W-Wing', (Premise('Endpoint sees both wings', (wing_a, link_a, link_b, wing_b), frozenset({1, 2})),),
        eliminations=(Elimination(link_a, 2),),
    )
    DeductionVerifier.verify(state, WWing(), deduction)
    assert any(
        Elimination(link_a, 2) in d.eliminations
        for d in WWing().find_deductions(state)
    )


def test_real_unique_puzzle_wing_effects_pass_independent_constraint_oracle():
    """Check actual discovered wings against an independently counted solution."""
    reference_package = pytest.importorskip('sudoku.solvers.constraint')
    board = SudokuBoard.from_string(
        '530070000600195000098000060800060003400803001700020006'
        '060000280000419005000080079'
    )
    reference = reference_package.ReferenceSolver()
    assert reference.count_solutions(board, limit=2) == 1
    state = CandidateState(board)
    checked = 0
    for technique_cls in (XYWing, XYZWing, WWing):
        technique = technique_cls()
        for deduction in technique.find_deductions(state):
            DeductionVerifier.verify(state, technique, deduction)
            for effect in deduction.eliminations:
                assert reference.proves_elimination(board, *effect.cell, effect.digit)
                checked += 1
    assert checked == 12  # 3 XY-Wings, 1 XYZ-Wing in the input grid
