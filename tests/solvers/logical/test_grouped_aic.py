"""Grouped AIC links, deductions, independent verification and integration."""
from dataclasses import replace
import random

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Elimination, Placement, Premise
from sudoku.solvers.logical.grouped_aic import GroupedAIC
from sudoku.solvers.logical.grouped_inference_graph import (
    CandidateNode, GroupNode, GroupedInferenceGraph,
)
from sudoku.solvers.logical.solver import LogicalSolver, SolveStatus
from sudoku.solvers.logical.verification import DeductionVerifier


SOLVED = (
    "534678912672195348198342567859761423426853791"
    "713924856961537284287419635345286179"
)


def empty_state():
    return CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))


def sample_state():
    """3-link proof: R1C5(5) = R1C12(5) - R2C3(5) = R2C5(5)."""
    state = empty_state()
    for col in range(9):
        if col not in (0, 1, 4):
            state.eliminate(0, col, 5)
        if col not in (2, 4):
            state.eliminate(1, col, 5)
    return state


def fingerprint(state):
    return state.board.to_string(), tuple(
        (cell, state.candidates_at(*cell)) for cell in state.unsolved_cells()
    )


def sample_witness(state):
    tech = GroupedAIC(max_links=3, max_expansions=30000)
    target = Elimination((2, 4), 5)
    deductions = tech.find_deductions(state)
    return tech, next(d for d in deductions if target in d.eliminations and len(d.premises) == 4)


def test_group_node_validation():
    valid = GroupNode(((0, 0), (0, 1)), 7)
    assert valid.label.startswith("7@")
    for cells in (
        ((0, 0),), ((0, 1), (0, 1)), ((0, 2), (0, 0)),
        ((0, 0), (1, 1)), ((0, 0), (0, 3)),
        ((0, 0), (0, 1), (0, 2), (0, 3)),
        ((0, 0), (9, 0)),
    ):
        with pytest.raises(ValueError):
            GroupNode(cells, 7)
    for digit in (0, 10, True):
        with pytest.raises(ValueError):
            GroupNode(((0, 0), (0, 1)), digit)


def test_group_strong_and_weak_link():
    graph = GroupedInferenceGraph(sample_state())
    a = CandidateNode(0, 4, 5)
    b = GroupNode(((0, 0), (0, 1)), 5)
    c = CandidateNode(1, 2, 5)
    d = CandidateNode(1, 4, 5)
    assert graph.linked(a, b, "strong")
    assert graph.linked(b, c, "weak")
    assert graph.linked(c, d, "strong")
    assert graph.linked(b, a, "weak")
    assert not graph.linked(b, CandidateNode(4, 0, 5), "weak")
    assert not graph.linked(b, CandidateNode(4, 0, 7), "strong")


def test_group_group_strong_link_from_two_intersections():
    state = empty_state()
    for col in range(9):
        if col not in (0, 1, 3, 4):
            state.eliminate(0, col, 5)
    graph = GroupedInferenceGraph(state)
    left = GroupNode(((0, 0), (0, 1)), 5)
    right = GroupNode(((0, 3), (0, 4)), 5)
    assert graph.linked(left, right, "strong")
    assert graph.linked(left, right, "weak")
    assert graph.linked(right, left, "strong")


def test_open_grouped_chain_discovers_and_verifies():
    state = sample_state()
    snapshot = fingerprint(state)
    technique, witness = sample_witness(state)
    DeductionVerifier.verify(state, technique, witness)
    assert witness.technique == "Grouped AIC"
    assert any(len(p.cells) > 1 for p in witness.premises)
    assert Elimination((2, 4), 5) in witness.eliminations
    assert witness.placements == ()
    assert fingerprint(state) == snapshot
    assert technique.find_deductions(state) == technique.find_deductions(state)


def test_solver_applies_grouped_deduction_without_mutating_input():
    state = sample_state()
    before = fingerprint(state)
    result = LogicalSolver(techniques=(GroupedAIC(max_links=3),)).solve(state, max_steps=1)
    assert result.status is SolveStatus.STEP_LIMIT
    assert len(result.steps) == 1
    assert result.steps[0].deduction.technique == "Grouped AIC"
    assert result.steps[0].deduction.eliminations
    assert fingerprint(state) == before
    assert fingerprint(result.steps[0].before) == before
    assert fingerprint(result.steps[0].after) == fingerprint(result.state)
    assert fingerprint(result.state) != before


@pytest.mark.parametrize("modification", [
    "technique", "wrong_digit", "wrong_strong", "wrong_weak",
    "invalid_group", "overlap", "repeat", "bogus_elimination",
    "false_placement", "wrong_length", "stale_candidate", "no_group",
])
def test_forged_grouped_witness_is_rejected(modification):
    state = sample_state()
    tech, deduction = sample_witness(state)
    premises = list(deduction.premises)
    if modification == "technique":
        forged = replace(deduction, technique="AIC")
    elif modification == "wrong_digit":
        premises[1] = replace(premises[1], digits=frozenset({6}))
        forged = replace(deduction, premises=tuple(premises))
    elif modification == "wrong_strong":
        premises[1] = Premise("bad", ((0, 7),), frozenset({5}))
        forged = replace(deduction, premises=tuple(premises))
    elif modification == "wrong_weak":
        premises[2] = Premise("bad", ((5, 5),), frozenset({5}))
        forged = replace(deduction, premises=tuple(premises))
    elif modification == "invalid_group":
        premises[1] = Premise("diagonal group", ((0, 0), (1, 1)), frozenset({5}))
        forged = replace(deduction, premises=tuple(premises))
    elif modification == "overlap":
        premises[1] = Premise("overlapping", ((0, 0), (0, 4)), frozenset({5}))
        forged = replace(deduction, premises=tuple(premises))
    elif modification == "repeat":
        premises[2] = premises[0]
        forged = replace(deduction, premises=tuple(premises))
    elif modification == "bogus_elimination":
        forged = replace(deduction, eliminations=(Elimination((8, 8), 6),))
    elif modification == "false_placement":
        forged = replace(deduction, eliminations=(), placements=(Placement((2, 4), 5),))
    elif modification == "wrong_length":
        with pytest.raises(ValueError):
            DeductionVerifier.verify(state, GroupedAIC(max_links=3), replace(
                deduction, premises=deduction.premises + deduction.premises[0:2]
            ))
        return
    elif modification == "stale_candidate":
        modified = state.copy()
        modified._candidates[(0, 2)].add(5)  # break row-1 strong group link
        with pytest.raises(ValueError):
            DeductionVerifier.verify(modified, tech, deduction)
        return
    else:
        premises[1] = Premise("single", ((0, 0),), frozenset({5}))
        forged = replace(deduction, premises=tuple(premises))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, tech, forged)


@pytest.mark.parametrize("opts", [
    {"max_links": 2}, {"max_links": 4}, {"max_links": 11},
    {"max_links": True}, {"max_expansions": 0},
    {"max_expansions": False}, {"max_deductions": 0},
    {"max_deductions": 1001},
])
def test_configuration_validation(opts):
    with pytest.raises(ValueError):
        GroupedAIC(**opts)


def test_no_false_positive_without_grouped_links():
    empty = empty_state()
    assert GroupedAIC(max_links=3, max_expansions=1000).find_deductions(empty) == ()
    with pytest.raises(TypeError):
        GroupedAIC().find_deductions(None)


def test_default_registration_and_no_uniqueness_requirement():
    names = [tech.name for tech in LogicalSolver().techniques]
    assert names[-3:] == ["AIC", "Grouped AIC", "ALS-AIC"]
    assert DeductionVerifier.supports(GroupedAIC())


def test_known_solution_is_preserved_by_grouped_chain_effects():
    rng = random.Random(461)
    tech = GroupedAIC(max_links=5, max_expansions=5500, max_deductions=15)
    found = 0
    for _ in range(12):
        blank_positions = set(rng.sample(range(81), rng.randrange(47, 66)))
        puzzle = "".join("0" if i in blank_positions else digit for i, digit in enumerate(SOLVED))
        state = CandidateState(SudokuBoard.from_string(puzzle))
        initial = fingerprint(state)
        deductions = tech.find_deductions(state)
        found += len(deductions)
        for deduction in deductions:
            DeductionVerifier.verify(state, tech, deduction)
            for elimination in deduction.eliminations:
                idx = elimination.cell[0] * 9 + elimination.cell[1]
                assert int(SOLVED[idx]) != elimination.digit
            for placement in deduction.placements:
                idx = placement.cell[0] * 9 + placement.cell[1]
                assert int(SOLVED[idx]) == placement.digit
        assert fingerprint(state) == initial
    assert found >= 1


def test_three_cell_group_and_incomplete_subset_not_registered():
    state = empty_state()
    for col in range(9):
        if col not in (0, 1, 2, 4):
            state.eliminate(0, col, 5)
    graph = GroupedInferenceGraph(state)
    trio = GroupNode(((0, 0), (0, 1), (0, 2)), 5)
    pair = GroupNode(((0, 0), (0, 1)), 5)
    assert trio in graph.nodes
    assert pair not in graph.nodes  # Would omit a third candidate in the strip.
    assert graph.linked(trio, CandidateNode(0, 4, 5), "strong")


def test_continuous_grouped_loop_and_forged_effect():
    state = sample_state()
    tech = GroupedAIC(max_links=3)
    loop = next(d for d in tech.find_deductions(state)
                if d.premises[0].cells == d.premises[-1].cells
                and d.premises[0].digits == d.premises[-1].digits
                and len(d.premises) == 5 and d.eliminations)
    DeductionVerifier.verify(state, tech, loop)
    assert any(e.digit == 5 for e in loop.eliminations)
    with pytest.raises(ValueError, match="not justified"):
        DeductionVerifier.verify(state, tech, replace(
            loop, eliminations=(Elimination((8, 8), 7),)
        ))
