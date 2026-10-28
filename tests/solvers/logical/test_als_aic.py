"""Soundness, verification, and integration tests for mixed candidate/ALS AICs."""
from dataclasses import replace
import random

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination, Placement, Premise
from sudoku.solvers.logical.als_aic import ALSAIC, _eliminations, _witness
from sudoku.solvers.logical.als_inference_graph import (
    ALSInferenceGraph, ALSNode, CandidateNode, _conflict,
)
from sudoku.solvers.logical.solver import LogicalSolver, SolveStatus
from sudoku.solvers.logical.verification import DeductionVerifier


SOLUTION = (
    "534678912672195348198342567859761423426853791"
    "713924856961537284287419635345286179"
)


def sample_state():
    """Two column ALSs with an RCC on digit 3 in row one.

    ALS A: R1C1 {1,3}; R2C1 {1,2} -> {1,2,3}.
    ALS B: R1C4 {2,3}; R2C4 {1,2} -> {1,2,3}.
    The 3s in R1C1/R1C4 cannot both be true. R2C2 sees every
    potential 1 in each endpoint group and is an elimination target.
    """
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    for cell, digits in (
        ((0, 0), {1, 3}), ((1, 0), {1, 2}),
        ((0, 3), {2, 3}), ((1, 3), {1, 2}),
    ):
        for digit in set(range(1, 10)) - digits:
            state.eliminate(*cell, digit)
    return state


def snapshot(state):
    return (state.board.to_string(), tuple(
        (cell, state.candidates_at(*cell)) for cell in state.unsolved_cells()
    ))


def open_witness(state):
    technique = ALSAIC(max_links=3, max_expansions=30000)
    for deduction in technique.find_deductions(state):
        if len(deduction.premises) == 4 and Elimination((1, 1), 1) in deduction.eliminations:
            return technique, deduction
    raise AssertionError("Expected mixed ALS-AIC deduction not found")


def rcc_witness(state):
    """Construct the RCC path, whose truth is independently checked."""
    a = ((0, 0), (1, 0))
    b = ((0, 3), (1, 3))
    path = (ALSNode(a, 2), ALSNode(a, 3), ALSNode(b, 3), ALSNode(b, 2))
    graph = ALSInferenceGraph(state)
    effects = _eliminations(graph, state, path)
    assert effects
    return Deduction("ALS-AIC", _witness(path, state, "RCC witness"), eliminations=effects)


def test_als_node_validation():
    assert "contains 1" in ALSNode(((0, 0), (1, 0)), 1).label
    for cells in (
        ((0, 0),), ((0, 0), (0, 0)), ((1, 0), (0, 0)),
        ((0, 0), (9, 1)), ((0, 0), (True, 1)),
    ):
        with pytest.raises(ValueError):
            ALSNode(cells, 1)
    for digit in (0, 10, True):
        with pytest.raises(ValueError):
            ALSNode(((0, 0), (0, 1)), digit)


def test_graph_links_als_internal_are_strong_but_not_weak():
    g = ALSInferenceGraph(sample_state())
    a = ALSNode(((0, 0), (1, 0)), 1)
    b = ALSNode(((0, 0), (1, 0)), 3)
    assert a in g.als_nodes and b in g.als_nodes
    assert g.linked(a, b, "strong")
    assert g.linked(b, a, "strong")
    assert not g.linked(a, b, "weak")
    assert not g.linked(b, a, "weak")


def test_graph_restricted_common_candidate_is_weak_not_strong():
    g = ALSInferenceGraph(sample_state())
    a = ALSNode(((0, 0), (1, 0)), 3)
    b = ALSNode(((0, 3), (1, 3)), 3)
    assert g.linked(a, b, "weak")
    assert not g.linked(a, b, "strong")
    assert g.linked(a, CandidateNode(0, 6, 3), "weak")
    assert not g.linked(a, CandidateNode(3, 7, 3), "weak")
    assert not g.linked(a, CandidateNode(0, 0, 3), "weak")


def test_elementary_candidate_conflicts():
    a = CandidateNode(0, 0, 1)
    assert not _conflict(a, a)
    assert _conflict(a, CandidateNode(0, 0, 2))
    assert _conflict(a, CandidateNode(0, 8, 1))
    assert _conflict(a, CandidateNode(8, 0, 1))
    assert _conflict(a, CandidateNode(1, 1, 1))
    assert not _conflict(a, CandidateNode(4, 5, 1))
    assert not _conflict(a, CandidateNode(0, 8, 2))


def test_discovery_and_verification_do_not_modify_state():
    state = sample_state()
    original = snapshot(state)
    tech, witness = open_witness(state)
    DeductionVerifier.verify(state, tech, witness)
    assert snapshot(state) == original
    assert tech.find_deductions(state) == tech.find_deductions(state)
    assert witness.technique == "ALS-AIC"
    assert not witness.placements


def test_two_als_rcc_witness_and_verification():
    state = sample_state()
    tech = ALSAIC(max_links=3)
    ded = rcc_witness(state)
    assert all(len(p.cells) == 2 for p in ded.premises)
    assert len(ded.eliminations) > 0
    DeductionVerifier.verify(state, tech, ded)


def test_als_aic_search_includes_rcc_witness():
    state = sample_state()
    ds = ALSAIC(max_links=3, max_expansions=50000).find_deductions(state)
    assert any(all(len(p.cells) == 2 for p in d.premises) for d in ds)


def test_solver_executes_verified_als_aic_and_keeps_input_unchanged():
    state = sample_state()
    before = snapshot(state)
    tech = ALSAIC(max_links=3)
    result = LogicalSolver(techniques=(tech,)).solve(state, max_steps=1)
    assert result.status is SolveStatus.STEP_LIMIT
    assert len(result.steps) == 1
    assert result.steps[0].deduction.technique == "ALS-AIC"
    assert snapshot(state) == before
    assert snapshot(result.state) != before
    assert snapshot(result.steps[0].before) == before


def test_default_enabled_without_uniqueness():
    assert DeductionVerifier.supports(ALSAIC())
    assert LogicalSolver().techniques[-1].name == "ALS-AIC"
    assert LogicalSolver(allow_uniqueness=False).techniques[-1].name == "ALS-AIC"


@pytest.mark.parametrize("kwargs", [
    {"max_links": 2}, {"max_links": 4}, {"max_links": True},
    {"max_als_size": 1}, {"max_als_size": 5}, {"max_als_size": False},
    {"max_als_groups": 0}, {"max_als_groups": 501},
    {"max_expansions": 0}, {"max_expansions": True},
    {"max_deductions": 0}, {"max_deductions": 1001},
])
def test_configuration_is_validated(kwargs):
    with pytest.raises(ValueError):
        ALSAIC(**kwargs)


def test_reject_non_candidate_state():
    with pytest.raises(TypeError):
        ALSAIC().find_deductions(None)
    with pytest.raises(TypeError):
        ALSInferenceGraph(None)


@pytest.mark.parametrize("mutation", [
    "technique", "wrong_digit", "absent_candidate", "invalid_als",
    "broken_strong", "broken_weak", "repeat", "longer_than_limit",
    "wrong_target", "placement", "stale_state", "all_candidates",
])
def test_forged_witness_rejected(mutation):
    state = sample_state()
    tech, deduction = open_witness(state)
    premises = list(deduction.premises)
    if mutation == "technique":
        bad = replace(deduction, technique="AIC")
    elif mutation == "wrong_digit":
        premises[0] = replace(premises[0], digits=frozenset({8}))
        bad = replace(deduction, premises=tuple(premises))
    elif mutation == "absent_candidate":
        premises[2] = Premise("absent", ((0, 0),), frozenset({8}))
        bad = replace(deduction, premises=tuple(premises))
    elif mutation == "invalid_als":
        premises[0] = Premise("invalid", ((0, 0), (3, 4)), frozenset({1}))
        bad = replace(deduction, premises=tuple(premises))
    elif mutation == "broken_strong":
        premises[1] = Premise("broken", ((3, 7),), frozenset({9}))
        bad = replace(deduction, premises=tuple(premises))
    elif mutation == "broken_weak":
        premises[2] = Premise("broken", ((4, 4),), frozenset({9}))
        bad = replace(deduction, premises=tuple(premises))
    elif mutation == "repeat":
        premises[2] = premises[0]
        bad = replace(deduction, premises=tuple(premises))
    elif mutation == "longer_than_limit":
        bad = replace(deduction, premises=deduction.premises + deduction.premises[:2])
    elif mutation == "wrong_target":
        bad = replace(deduction, eliminations=(Elimination((8, 8), 8),))
    elif mutation == "placement":
        bad = replace(deduction, eliminations=(), placements=(Placement((2, 2), 1),))
    elif mutation == "stale_state":
        altered = state.copy()
        first = premises[0]
        altered.eliminate(*first.cells[0], next(iter(first.digits)))
        state = altered
        bad = deduction
    else:  # all_candidates
        premises[1] = replace(premises[1], digits=frozenset({1, 2}))
        bad = replace(deduction, premises=tuple(premises))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, tech, bad)


def test_solver_has_no_false_placement_from_forced_als_proposition():
    # A true ALS proposition doesn't specify which cell contains the digit.
    state = sample_state()
    tech = ALSAIC(max_links=3)
    ded = rcc_witness(state)
    forged = replace(ded, eliminations=(), placements=(Placement((0, 0), 2),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, tech, forged)


def test_reduced_budget_is_deterministic_and_may_miss_deductions():
    state = sample_state()
    tech = ALSAIC(max_links=3, max_expansions=1, max_deductions=1)
    first = tech.find_deductions(state)
    assert first == tech.find_deductions(state)
    assert len(first) <= 1


def test_als_links_do_not_require_unique_solution():
    # Empty grid has many solutions, yet the ALS rules remain sound.
    technique = ALSAIC(max_links=3)
    assert technique.name == "ALS-AIC"
    assert DeductionVerifier.supports(technique)


@pytest.mark.parametrize("seed", [3, 8, 21, 34, 55])
def test_known_solution_is_preserved(seed):
    solution = [int(x) for x in SOLUTION]
    randomizer = random.Random(seed)
    cells = list(range(81))
    randomizer.shuffle(cells)
    for removed in (40, 50, 60):
        grid = solution.copy()
        for cell in cells[:removed]:
            grid[cell] = 0
        state = CandidateState(SudokuBoard([grid[i:i + 9] for i in range(0, 81, 9)]))
        technique = ALSAIC(max_links=3, max_als_size=2,
                           max_expansions=2500, max_deductions=10)
        for deduction in technique.find_deductions(state):
            DeductionVerifier.verify(state, technique, deduction)
            for effect in deduction.eliminations:
                assert solution[effect.cell[0] * 9 + effect.cell[1]] != effect.digit
            for effect in deduction.placements:
                assert solution[effect.cell[0] * 9 + effect.cell[1]] == effect.digit


def test_continuous_als_aic_loop_eliminates_common_conflicts():
    state = sample_state()
    for digit in set(range(1, 10)) - {1, 2}:
        state.eliminate(1, 1, digit)
    group = ((0, 0), (1, 0))
    path = (
        ALSNode(group, 1), ALSNode(group, 2),
        CandidateNode(1, 1, 2), CandidateNode(1, 1, 1),
        ALSNode(group, 1),
    )
    graph = ALSInferenceGraph(state)
    assert [graph.linked(a, b, "strong" if i % 2 == 0 else "weak")
            for i, (a, b) in enumerate(zip(path, path[1:]))] == [True] * 4
    effects = _eliminations(graph, state, path, closed=True)
    assert Elimination((0, 1), 1) in effects
    assert Elimination((1, 2), 2) in effects
    deduction = Deduction("ALS-AIC", _witness(path, state, "continuous loop"),
                          eliminations=effects)
    assert DeductionVerifier.verify(state, ALSAIC(max_links=3), deduction) is None


def test_strong_discontinuity_around_als_forces_candidate():
    state = sample_state()
    for r in range(2, 9):
        state.eliminate(r, 0, 1)
    group = ((0, 3), (1, 3))
    endpoint = CandidateNode(0, 0, 1)
    path = (
        endpoint, CandidateNode(0, 0, 3),
        ALSNode(group, 3), ALSNode(group, 1),
        CandidateNode(1, 0, 1), endpoint,
    )
    graph = ALSInferenceGraph(state)
    assert all(graph.linked(a, b, "strong" if i % 2 == 0 else "weak")
               for i, (a, b) in enumerate(zip(path, path[1:])))
    deduction = Deduction("ALS-AIC", _witness(path, state, "forced singleton"),
                          placements=(Placement((0, 0), 1),))
    assert DeductionVerifier.verify(state, ALSAIC(max_links=5), deduction) is None
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, ALSAIC(max_links=3), deduction)


def test_als_discontinuity_cannot_be_misreported_as_a_singleton_placement():
    state = sample_state()
    group = ((0, 0), (1, 0))
    # Repeat an ALS node in a purported forced loop, with a placement effect.
    path = (ALSNode(group, 1), ALSNode(group, 2), CandidateNode(1, 3, 2),
            ALSNode(((0, 3), (1, 3)), 3), ALSNode(group, 1))
    forged = Deduction("ALS-AIC", _witness(path, state, "not a forced candidate"),
                       placements=(Placement((0, 0), 1),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, ALSAIC(max_links=5), forged)


def test_internal_als_strong_link_cannot_be_used_as_a_weak_link():
    state = sample_state()
    group = ((0, 0), (1, 0))
    path = (ALSNode(group, 1), ALSNode(group, 2), ALSNode(group, 3),
            CandidateNode(0, 3, 3))
    bad = Deduction("ALS-AIC", _witness(path, state, "invalid weak link"),
                    eliminations=(Elimination((1, 1), 1),))
    with pytest.raises(ValueError, match="weak link"):
        DeductionVerifier.verify(state, ALSAIC(max_links=3), bad)
