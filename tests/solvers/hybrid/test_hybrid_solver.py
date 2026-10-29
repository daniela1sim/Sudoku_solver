"""Stage ownership, safe handoff, and end-to-end hybrid solving tests."""

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState, CandidateContradiction
from sudoku.solvers.constraint import ReferenceSolver
from sudoku.solvers.hybrid import HybridResult, HybridSolver, HybridStatus, SolveMode
from sudoku.solvers.logical.singles import NakedSingle
from sudoku.solvers.logical.locked_candidates import Pointing
from sudoku.solvers.logical.solver import LogicalSolver, SolveStatus

SOLVED = "534678912672195348198342567859761423426853791713924856961537284287419635345286179"
CLASSIC = "530070000600195000098000060800060003400803001700020006060000280000419005000080079"
HARD = "005000987040050001007000000200048000090100000600200000300600200000009070000000500"
IMPOSSIBLE = CLASSIC[:2] + "2" + CLASSIC[3:]
MULTI = "".join("0" if d in "12" else d for d in SOLVED)
ALGORITHMS = ["reference", "propagation", "exact_cover", "integer_programming"]


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_constraint_only_skips_logical_and_retains_original_givens(algorithm):
    board = SudokuBoard.from_string(CLASSIC)
    solver = HybridSolver(mode="constraint", constraint_algorithm=algorithm)
    result = solver.solve(board)
    assert result.mode is SolveMode.CONSTRAINT
    assert result.status is HybridStatus.SOLVED
    assert result.solved and result.completed_by == "constraint"
    assert result.logical_result is None and result.steps == ()
    assert result.handoff_state is None and not result.used_fallback
    assert result.constraint_result is not None
    assert result.solution_count == 1 and result.is_unique is True
    assert result.state.board.to_string() == SOLVED
    assert result.first_solution.to_string() == SOLVED
    assert result.state.board.givens == board.givens
    assert board.to_string() == CLASSIC


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_hybrid_falls_back_on_genuine_stuck_state(algorithm):
    board = SudokuBoard.from_string(HARD)
    logical = LogicalSolver((NakedSingle(),))
    direct = logical.solve(board)
    assert direct.status is SolveStatus.STUCK
    result = HybridSolver(mode="hybrid", logical_solver=logical,
                          constraint_algorithm=algorithm).solve(board)
    assert result.solved and result.completed_by == "constraint"
    assert result.used_fallback and result.handoff_state is not None
    assert result.logical_result.status is SolveStatus.STUCK
    assert len(result.steps) == len(direct.steps)
    assert result.handoff_state.board.to_string() == direct.state.board.to_string()
    assert result.handoff_state.board.givens == board.givens
    assert result.state.board.givens == board.givens
    assert result.state.board.to_string() == ReferenceSolver().solve(board).to_string()
    assert result.state.is_complete()
    assert board.to_string() == HARD


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_logical_completion_never_runs_constraint_search(algorithm):
    solver = HybridSolver(mode="hybrid", constraint_algorithm=algorithm)
    board = SudokuBoard.from_string("0" + SOLVED[1:])
    result = solver.solve(board)
    assert result.solved
    assert result.completed_by == "logical"
    assert result.logical_result is not None
    assert len(result.steps) == 1
    assert result.constraint_result is None and not result.used_fallback
    assert result.handoff_state is None
    assert result.solution_count is None and result.is_unique is None
    assert result.state.board.givens == board.givens
    assert board.value_at(0, 0) == 0


def test_human_only_stays_stuck_even_with_available_constraint_backend():
    board = SudokuBoard.from_string(HARD)
    result = HybridSolver(mode="logical", logical_solver=LogicalSolver((NakedSingle(),))).solve(board)
    assert result.mode is SolveMode.LOGICAL
    assert result.status is HybridStatus.STUCK and not result.solved
    assert result.logical_result.status is SolveStatus.STUCK
    assert result.constraint_result is None and result.completed_by is None
    assert result.first_solution is None and result.is_unique is None
    assert not result.state.is_complete()


def test_step_limit_never_triggers_default_fallback():
    board = SudokuBoard.from_string(CLASSIC)
    result = HybridSolver(mode="hybrid").solve(board, max_logical_steps=0)
    assert result.status is HybridStatus.STEP_LIMIT
    assert result.logical_result.status is SolveStatus.STEP_LIMIT
    assert result.constraint_result is None
    assert not result.used_fallback and not result.solved
    assert result.state.board.to_string() == CLASSIC
    assert result.steps == ()


@pytest.mark.parametrize("algorithm", ["propagation", "exact_cover", "integer_programming", "reference"])
def test_opt_in_fallback_on_step_limit(algorithm):
    board = SudokuBoard.from_string(CLASSIC)
    result = HybridSolver(mode="hybrid", fallback_on_step_limit=True,
                          constraint_algorithm=algorithm).solve(board, max_logical_steps=0)
    assert result.solved and result.used_fallback
    assert result.logical_result.status is SolveStatus.STEP_LIMIT
    assert result.handoff_state.board.to_string() == CLASSIC
    assert result.state.board.to_string() == SOLVED


def test_step_limit_with_one_deduction_retains_provenance():
    board = SudokuBoard.from_string("00" + SOLVED[2:])
    result = HybridSolver(mode="hybrid", fallback_on_step_limit=True).solve(
        board, max_logical_steps=1,
    )
    assert result.solved and result.used_fallback
    assert len(result.steps) == 1
    assert result.steps[0].before.board.to_string() == board.to_string()
    assert result.steps[0].after.board.to_string() == result.handoff_state.board.to_string()
    assert result.handoff_state.board.to_string() != result.state.board.to_string()
    assert result.state.board.to_string() == SOLVED
    assert result.completed_by == "constraint"


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_unsatisfiable_board_reports_unsatisfiable_only_after_search(algorithm):
    # Don't run unbounded logical techniques on an impossible board. A solver
    # with no techniques reliably produces STUCK, allowing a complete search.
    solver = HybridSolver(mode="hybrid", constraint_algorithm=algorithm,
                          logical_solver=LogicalSolver(()))
    result = solver.solve(IMPOSSIBLE)
    assert result.status is HybridStatus.UNSATISFIABLE
    assert not result.solved and result.first_solution is None
    assert result.constraint_result.is_unsatisfiable
    assert result.used_fallback and result.completed_by is None
    assert result.logical_result.status is SolveStatus.STUCK
    assert result.solution_count == 0 and result.is_unique is False


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_count_cap_and_nonunique_completions(algorithm):
    solver = HybridSolver(mode="constraint", constraint_algorithm=algorithm)
    result = solver.solve(MULTI, solution_limit=2)
    assert result.solved
    assert result.constraint_result.has_multiple_solutions
    assert result.solution_count == 2 and result.is_unique is False
    assert result.first_solution.is_complete()
    assert all(g == "0" or g == s for g, s in zip(MULTI, result.first_solution.to_string()))
    one = solver.solve(MULTI, solution_limit=1)
    assert one.solved and one.solution_count == 1 and one.is_unique is False
    assert not one.constraint_result.exhaustive


def test_candidate_state_eliminations_survive_fallback_and_final_completion():
    original = CandidateState(SudokuBoard.from_string(CLASSIC))
    assert 1 in original.candidates_at(0, 2)
    original.eliminate(0, 2, 1)
    before = original.candidates_at(0, 2)
    solver = HybridSolver(mode="hybrid", logical_solver=LogicalSolver(()))
    result = solver.solve(original)
    assert result.used_fallback
    assert result.handoff_state.candidates_at(0, 2) == before
    assert result.logical_result.state.candidates_at(0, 2) == before
    assert result.state.board.to_string() == SOLVED
    assert result.state.board.givens == original.board.givens
    assert original.board.to_string() == CLASSIC
    assert original.candidates_at(0, 2) == before
    assert (0, 2) in original.unsolved_cells()


def test_real_logical_elimination_is_preserved_in_handoff():
    board = SudokuBoard.from_string(CLASSIC)
    logical = LogicalSolver((Pointing(),))
    result = HybridSolver(logical_solver=logical, fallback_on_step_limit=True,
                          constraint_algorithm="exact_cover").solve(
        board, max_logical_steps=1,
    )
    assert result.solved and result.used_fallback
    assert len(result.steps) == 1
    assert result.steps[0].deduction.technique == "Pointing"
    assert result.steps[0].deduction.eliminations
    for move in result.steps[0].deduction.eliminations:
        assert move.digit not in result.handoff_state.candidates_at(*move.cell)
    assert result.state.board.to_string() == SOLVED
    assert result.state.board.givens == board.givens


def test_reference_accepts_handoff_after_real_logical_elimination():
    board = SudokuBoard.from_string(CLASSIC)
    solver = HybridSolver(logical_solver=LogicalSolver((Pointing(),)),
                          fallback_on_step_limit=True, constraint_algorithm="reference")
    result = solver.solve(board, max_logical_steps=1)
    assert result.solved and result.used_fallback
    assert len(result.steps[0].deduction.eliminations) > 0
    assert result.state.board.to_string() == SOLVED


def test_reference_backend_preserves_candidate_eliminations_as_assumptions():
    state = CandidateState(SudokuBoard.from_string(CLASSIC))
    state.eliminate(0, 2, 1)
    before = state.candidates_at(0, 2)
    for mode in ("hybrid", "constraint"):
        solver = HybridSolver(mode=mode, constraint_algorithm="reference",
                              logical_solver=LogicalSolver(()))
        result = solver.solve(state)
        assert result.solved and result.state.board.to_string() == SOLVED
        assert result.state.board.givens == state.board.givens
        if mode == "hybrid":
            assert result.handoff_state.candidates_at(0, 2) == before
    assert state.candidates_at(0, 2) == before


def test_reference_forbidden_assumptions_can_make_puzzle_unsatisfiable():
    # Choose an elimination not locally contradictory, but which excludes
    # the globally necessary value. The reference handoff must honor it.
    for cell in range(81):
        r, c = divmod(cell, 9)
        if CLASSIC[cell] != "0":
            continue
        digit = int(SOLVED[cell])
        state = CandidateState(SudokuBoard.from_string(CLASSIC))
        try:
            state.eliminate(r, c, digit)
        except CandidateContradiction:
            continue
        result = HybridSolver(mode="constraint", constraint_algorithm="reference").solve(state)
        assert result.status is HybridStatus.UNSATISFIABLE
        assert result.constraint_result.is_unsatisfiable
        break
    else:
        pytest.fail("Expected to find a locally consistent forbidden correct digit")


def test_solution_conflicting_with_candidate_state_is_never_accepted():
    state = CandidateState(SudokuBoard.from_string(CLASSIC))
    try:
        state.eliminate(0, 2, 4)
    except CandidateContradiction:
        pytest.skip("Locally contradictory elimination was rejected correctly")
    result = HybridSolver(mode="constraint").solve(state)
    assert result.status is HybridStatus.UNSATISFIABLE
    assert not result.solved and result.first_solution is None


def test_logical_only_does_not_prove_uniqueness_even_on_completed_grid():
    result = HybridSolver(mode="logical").solve(SOLVED)
    assert result.solved and result.completed_by == "logical"
    assert result.steps == () and result.constraint_result is None
    assert result.is_unique is None and result.solution_count is None


def test_input_state_and_handoff_are_distinct_snapshots():
    original = CandidateState(SudokuBoard.from_string(CLASSIC))
    result = HybridSolver(logical_solver=LogicalSolver(())).solve(original)
    assert result.handoff_state is not original
    assert result.handoff_state is not result.logical_result.state
    assert result.state is not result.handoff_state
    result.state._board.clear(0, 2)
    assert original.board.to_string() == CLASSIC
    assert result.handoff_state.board.to_string() == CLASSIC


@pytest.mark.parametrize("mode", [None, "automatic", "", 3, False])
def test_invalid_mode(mode):
    with pytest.raises(ValueError, match="mode"):
        HybridSolver(mode=mode)


@pytest.mark.parametrize("kwargs,exception", [
    ({"logical_solver": object()}, TypeError),
    ({"fallback_on_step_limit": 1}, TypeError),
    ({"constraint_algorithm": "missing"}, ValueError),
    ({"constraint_algorithm": "reference", "value_heuristic": "lcv"}, ValueError),
])
def test_invalid_configuration(kwargs, exception):
    with pytest.raises(exception):
        HybridSolver(**kwargs)


@pytest.mark.parametrize("limit", [0, -1, True, 1.2, "2", None])
def test_invalid_solution_limit(limit):
    with pytest.raises(ValueError, match="solution_limit"):
        HybridSolver(mode="logical").solve(CLASSIC, solution_limit=limit)


@pytest.mark.parametrize("limit", [-1, True, 1.2, "1"])
def test_invalid_max_steps(limit):
    with pytest.raises(ValueError, match="max_logical_steps"):
        HybridSolver().solve(CLASSIC, max_logical_steps=limit)


def test_constraint_mode_rejects_irrelevant_logical_step_limit():
    with pytest.raises(ValueError, match="max_logical_steps"):
        HybridSolver(mode="constraint").solve(CLASSIC, max_logical_steps=0)


@pytest.mark.parametrize("puzzle", [None, {}, [0] * 81, 12])
def test_invalid_input_type(puzzle):
    with pytest.raises(TypeError):
        HybridSolver(mode="constraint").solve(puzzle)


def test_invalid_grid_and_boolean_clues():
    with pytest.raises(ValueError):
        HybridSolver().solve("11" + "0" * 79)
    with pytest.raises(ValueError):
        HybridSolver().solve("0" * 80)


def test_custom_propagation_heuristics():
    solver = HybridSolver(mode="constraint", constraint_algorithm="propagation",
                          variable_heuristic="mrv_degree", value_heuristic="lcv")
    assert solver.solve(CLASSIC).state.board.to_string() == SOLVED


def test_modes_as_enums_and_repeated_deterministic_history():
    solver = HybridSolver(mode=SolveMode.HYBRID, logical_solver=LogicalSolver((NakedSingle(),)))
    a = solver.solve(HARD)
    b = solver.solve(HARD)
    assert a.status is b.status is HybridStatus.SOLVED
    assert [s.deduction for s in a.steps] == [s.deduction for s in b.steps]
    assert a.state.board.to_string() == b.state.board.to_string()
