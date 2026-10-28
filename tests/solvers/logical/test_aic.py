"""AIC inference graph and verifier: real chains, loops and forged witnesses."""
from dataclasses import replace
from itertools import product

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Elimination, Placement, Premise
from sudoku.solvers.logical.aic import AIC
from sudoku.solvers.logical.inference_graph import CandidateNode, InferenceGraph
from sudoku.solvers.logical.solver import LogicalSolver, SolveStatus
from sudoku.solvers.logical.verification import DeductionVerifier


def state_with(overrides, *, restrict=None):
    state = CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))
    for (r, c), allowed in overrides.items():
        for digit in set(range(1, 10)) - set(allowed):
            state.eliminate(r, c, digit)
    for cell, digit in restrict or ():
        state.eliminate(*cell, digit)
    return state


def fingerprint(state):
    return (state.board.to_string(), tuple(
        (cell, state.candidates_at(*cell)) for cell in state.unsolved_cells()
    ))


def open_state():
    # A 5-link AIC: 1(R1C1)=3(R1C1)-3(R5C1)=2(R5C1)
    #             -2(R5C5)=2(R1C5).
    # The endpoints have different digits. Target R1C5#1 conflicts with
    # first endpoint via row and with last endpoint in the same cell.
    overrides = {(0, 0): {1, 3}, (4, 0): {2, 3},
                 (4, 4): {2, 4}, (0, 4): {1, 2, 5}}
    restrictions = [((r, 4), 2) for r in range(9) if r not in (0, 4)]
    return state_with(overrides, restrict=restrictions)


def continuous_state():
    return state_with({(0, 0): {1, 2}, (0, 3): {1, 2}})


def forced_state():
    # A 7-link strong/strong discontinuity forces R1C1=1.
    overrides = {(0, 0): {1, 2}, (0, 3): {2, 3},
                 (4, 3): {1, 3}, (4, 0): {1, 4}}
    restrictions = [((r, 0), 1) for r in range(9) if r not in (0, 4)]
    return state_with(overrides, restrict=restrictions)


def find_elimination(state, target, tech=None):
    tech = tech or AIC()
    return next(d for d in tech.find_deductions(state)
                if target in d.eliminations)


def find_placement(state, move, tech=None):
    tech = tech or AIC()
    return next(d for d in tech.find_deductions(state)
                if move in d.placements)


def path_nodes(deduction):
    return tuple(CandidateNode(*p.cells[0], next(iter(p.digits)))
                 for p in deduction.premises)


def test_graph_bivalue_and_same_cell_weak_links():
    state = state_with({(0, 0): {1, 2}, (0, 4): {2, 3, 4}})
    graph = InferenceGraph(state)
    a = CandidateNode(0, 0, 1)
    b = CandidateNode(0, 0, 2)
    c = CandidateNode(0, 4, 2)
    d = CandidateNode(0, 4, 3)
    assert graph.linked(a, b, "strong")
    assert graph.linked(a, b, "weak")
    assert graph.linked(b, c, "weak")
    assert not graph.linked(b, c, "strong")
    assert graph.linked(c, d, "weak")
    assert not graph.linked(c, d, "strong")
    assert graph.neighbors(a, "strong") == tuple(sorted(graph.neighbors(a, "strong")))


def test_conjugate_house_link_and_three_position_nonlink():
    state = state_with({}, restrict=[((r, 0), 7) for r in range(9) if r not in (0, 4)])
    graph = InferenceGraph(state)
    assert graph.linked(CandidateNode(0, 0, 7), CandidateNode(4, 0, 7), "strong")
    other = InferenceGraph(CandidateState(SudokuBoard([[0] * 9 for _ in range(9)])))
    assert not other.linked(CandidateNode(0, 0, 7), CandidateNode(4, 0, 7), "strong")
    assert other.linked(CandidateNode(0, 0, 7), CandidateNode(4, 0, 7), "weak")


def test_graph_bad_arguments():
    with pytest.raises(TypeError):
        InferenceGraph(None)
    graph = InferenceGraph(continuous_state())
    with pytest.raises(ValueError):
        graph.neighbors(CandidateNode(0, 0, 1), "neither")
    with pytest.raises(ValueError):
        graph.linked(CandidateNode(0, 0, 1), CandidateNode(0, 0, 2), "neither")


def test_open_aic_different_endpoint_digits_and_verification():
    state = open_state()
    baseline = fingerprint(state)
    tech = AIC()
    expected = Elimination((0, 4), 1)
    deduction = find_elimination(state, expected, tech)
    path = path_nodes(deduction)
    assert path[0].digit != path[-1].digit
    assert len(path) == 6
    assert deduction.placements == ()
    DeductionVerifier.verify(state, tech, deduction)
    assert fingerprint(state) == baseline


def test_open_chain_endpoint_logic_by_bruteforce():
    # Enumerate all assignments for the 3 bivalue cells and the endpoint's
    # target cell, respecting only local Sudoku peer conflicts and the
    # restricted column-4 location of 2 (either R1C5 or R5C5).
    from sudoku.solvers.logical.strong_links import _sees
    choices = {(0, 0): {1, 3}, (4, 0): {2, 3},
               (4, 4): {2, 4}, (0, 4): {1, 2, 5}}
    counted = 0
    for digits in product(*(sorted(s) for s in choices.values())):
        assign = dict(zip(choices, digits))
        if any(_sees(a, b) and assign[a] == assign[b]
               for i, a in enumerate(assign) for b in list(assign)[i+1:]):
            continue
        if 2 not in (assign[(4, 4)], assign[(0, 4)]):
            continue
        counted += 1
        assert assign[(0, 4)] != 1
    assert counted > 0


def test_continuous_cycle_and_independent_verification():
    state = continuous_state()
    tech = AIC(max_links=5)
    expected = {Elimination((0, 8), 1), Elimination((0, 8), 2)}
    cycle = next(d for d in tech.find_deductions(state)
                 if path_nodes(d)[0] == path_nodes(d)[-1]
                 and d.eliminations and expected <= set(d.eliminations))
    assert len(cycle.premises) == 5
    DeductionVerifier.verify(state, tech, cycle)


def test_strong_discontinuity_forces_placement():
    state = forced_state()
    move = Placement((0, 0), 1)
    tech = AIC(max_links=7)
    deduction = find_placement(state, move, tech)
    assert path_nodes(deduction)[0] == path_nodes(deduction)[-1]
    assert len(deduction.premises) == 8
    DeductionVerifier.verify(state, tech, deduction)


def test_strong_loop_by_bruteforce():
    # A false would imply B=true, C=false, D=true, E=false,
    # F=true, G=false, contradicting the column-0 strong link A or G.
    from sudoku.solvers.logical.strong_links import _sees
    choices = {(0, 0): {1, 2}, (0, 3): {2, 3},
               (4, 3): {1, 3}, (4, 0): {1, 4}}
    surviving = 0
    for assignment in product(*(sorted(v) for v in choices.values())):
        taken = dict(zip(choices, assignment))
        if any(_sees(a, b) and taken[a] == taken[b]
               for i, a in enumerate(taken) for b in list(taken)[i + 1:]):
            continue
        if 1 not in (taken[(0, 0)], taken[(4, 0)]):
            continue
        surviving += 1
        assert taken[(0, 0)] == 1
    assert surviving > 0


def test_solver_integration_and_nonmutation():
    state = open_state()
    before = fingerprint(state)
    tech = AIC()
    result = LogicalSolver(techniques=(tech,)).solve(state, max_steps=1)
    assert result.status == SolveStatus.STEP_LIMIT
    assert result.steps
    assert result.steps[0].deduction.technique == "AIC"
    assert result.steps[0].deduction.eliminations
    assert fingerprint(state) == before
    assert fingerprint(result.steps[0].before) == before
    assert fingerprint(result.state) != before


def test_default_registration_and_no_uniqueness_assumption():
    assert [t.name for t in LogicalSolver().techniques][-3:] == ["AIC", "Grouped AIC", "ALS-AIC"]
    assert DeductionVerifier.supports(AIC())


@pytest.mark.parametrize("options", [
    {"max_links": 2}, {"max_links": 4}, {"max_links": 11},
    {"max_links": True}, {"max_expansions": 0},
    {"max_expansions": True}, {"max_deductions": 0},
    {"max_deductions": 1001},
])
def test_bad_configurations(options):
    with pytest.raises(ValueError):
        AIC(**options)


def test_invalid_input_and_no_fake_deductions():
    tech = AIC(max_expansions=1)
    with pytest.raises(TypeError):
        tech.find_deductions(None)
    assert len(tech.find_deductions(open_state())) <= tech.max_deductions
    assert AIC().find_deductions(CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))) == ()


@pytest.mark.parametrize("modification", [
    "bad_technique", "bad_premise", "bad_strong_link",
    "bad_weak_link", "missing_node", "duplicate_node",
    "forged_elimination", "unavailable_candidate", "wrong_shape", "over_limit",
])
def test_reject_forged_open_chain(modification):
    state = open_state()
    tech = AIC()
    deduction = find_elimination(state, Elimination((0, 4), 1))
    premises = list(deduction.premises)
    if modification == "bad_technique":
        bogus = replace(deduction, technique="XY-Chain")
    elif modification == "bad_premise":
        premises[2] = replace(premises[2], digits=frozenset({7}))
        bogus = replace(deduction, premises=tuple(premises))
    elif modification == "bad_strong_link":
        premises[1] = replace(premises[1], cells=((8, 8),))
        bogus = replace(deduction, premises=tuple(premises))
    elif modification == "bad_weak_link":
        premises[2] = replace(premises[2], cells=((8, 8),))
        bogus = replace(deduction, premises=tuple(premises))
    elif modification == "missing_node":
        bogus = replace(deduction, premises=tuple(premises[:-1]))
    elif modification == "duplicate_node":
        premises[3] = premises[2]
        bogus = replace(deduction, premises=tuple(premises))
    elif modification == "forged_elimination":
        bogus = replace(deduction, eliminations=(Elimination((8, 8), 9),))
    elif modification == "unavailable_candidate":
        bogus = replace(deduction, eliminations=(Elimination((0, 4), 7),))
    elif modification == "wrong_shape":
        bogus = replace(deduction, placements=(Placement((0, 4), 1),), eliminations=())
    else:
        bogus = replace(deduction, premises=deduction.premises)
        with pytest.raises(ValueError):
            DeductionVerifier.verify(state, AIC(max_links=3), bogus)
        return
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, tech, bogus)


def test_forged_loop_target_and_cycle_link():
    state = continuous_state()
    tech = AIC(max_links=5)
    cycle = next(d for d in tech.find_deductions(state)
                 if path_nodes(d)[0] == path_nodes(d)[-1]
                 and d.eliminations)
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, tech, replace(
            cycle, eliminations=(Elimination((8, 8), 9),)
        ))
    premises = list(cycle.premises)
    premises[2] = Premise("forged node", ((8, 8),), frozenset({1}))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, tech, replace(cycle, premises=tuple(premises)))


def test_strong_loop_bad_placement_and_mutated_candidate():
    state = forced_state()
    tech = AIC()
    step = find_placement(state, Placement((0, 0), 1))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, tech, replace(
            step, placements=(Placement((4, 0), 1),)
        ))
    stale = state.copy()
    # Destroy the conjugate relationship by reintroducing a candidate into
    # an unaffected column cell (for tests only, bypassing the elimination API).
    stale._candidates[(2, 0)].add(1)
    with pytest.raises(ValueError):
        DeductionVerifier.verify(stale, tech, step)


def test_short_search_is_deterministic_and_does_not_mutate():
    state = open_state()
    before = fingerprint(state)
    a = AIC(max_links=7, max_expansions=500, max_deductions=2)
    first = a.find_deductions(state)
    assert first == a.find_deductions(state)
    assert len(first) <= 2
    assert fingerprint(state) == before


def test_known_solution_is_preserved_across_many_candidate_states():
    """Every proposed effect must preserve a known valid completion."""
    import random
    solved = (
        "534678912672195348198342567859761423426853791"
        "713924856961537284287419635345286179"
    )
    rng = random.Random(42)
    technique = AIC(max_links=7, max_expansions=18000, max_deductions=30)
    nonempty = 0
    for _ in range(35):
        count = rng.randrange(43, 69)
        blanks = set(rng.sample(range(81), count))
        board = SudokuBoard.from_string("".join(
            "0" if index in blanks else character
            for index, character in enumerate(solved)
        ))
        state = CandidateState(board)
        before = fingerprint(state)
        deductions = technique.find_deductions(state)
        nonempty += bool(deductions)
        for deduction in deductions:
            DeductionVerifier.verify(state, technique, deduction)
            for elimination in deduction.eliminations:
                index = 9 * elimination.cell[0] + elimination.cell[1]
                assert int(solved[index]) != elimination.digit
            for placement in deduction.placements:
                index = 9 * placement.cell[0] + placement.cell[1]
                assert int(solved[index]) == placement.digit
        assert fingerprint(state) == before
    assert nonempty >= 10
