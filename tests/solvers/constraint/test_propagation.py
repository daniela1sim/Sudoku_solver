"""End-to-end propagation tests against the independent reference oracle."""

from random import Random

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState, CandidateContradiction
from sudoku.solvers.constraint import ConstraintSolver, PropagationSolver, ReferenceSolver
from sudoku.solvers.logical.singles import NakedSingle
from sudoku.solvers.logical.solver import LogicalSolver, SolveStatus

SOLVED = "534678912672195348198342567859761423426853791713924856961537284287419635345286179"
CLASSIC = "530070000600195000098000060800060003400803001700020006060000280000419005000080079"
EXAMPLES = (
    CLASSIC,
    "003020600900305001001806400008102900700000008006708200002609500800203009005010300",
    "200080300060070084030500209000105408000000000402706000301007040720040060004010003",
    "000000010400000000020000000000050407008000300001090000300400200050100000000806000",
    "005000987040050001007000000200048000090100000600200000300600200000009070000000500",
    "023700006800060590900000700000040970307096002000000000500470000000002000080000000",
)
HEURISTICS = (
    ("mrv", "ascending"),
    ("mrv", "lcv"),
    ("mrv_degree", "ascending"),
    ("mrv_degree", "lcv"),
    ("first", "ascending"),
    ("first", "lcv"),
)


def assert_valid_completion(puzzle, solution):
    assert solution.is_complete()
    assert all(given == "0" or given == actual for given, actual in zip(puzzle, solution.to_string()))


@pytest.mark.parametrize("puzzle", EXAMPLES)
@pytest.mark.parametrize("variable,value", HEURISTICS)
def test_unique_puzzles_agree_with_reference_across_heuristics(puzzle, variable, value):
    result = PropagationSolver(variable_heuristic=variable, value_heuristic=value).analyze(puzzle)
    assert result.solutions == ReferenceSolver().analyze(puzzle).solutions
    assert result.is_unique
    assert result.has_solution
    assert not result.has_multiple_solutions
    assert_valid_completion(puzzle, result.first_solution)
    assert result.statistics.nodes >= 1
    assert result.statistics.decisions >= result.statistics.backtracks
    assert result.statistics.max_depth <= result.statistics.decisions
    assert result.statistics.elapsed_seconds >= 0


def test_empty_board_and_multi_solution_limit():
    solver = PropagationSolver()
    swap_1_2 = "".join("0" if digit in "12" else digit for digit in SOLVED)
    result = solver.analyze(swap_1_2)
    assert result.solution_count == 2
    assert result.has_multiple_solutions
    assert not result.is_unique
    assert not result.exhaustive
    assert len(set(result.solutions)) == 2
    assert all_valid(swap_1_2, result.solutions)
    assert solver.count_solutions(swap_1_2, limit=1) == 1
    assert solver.analyze("0" * 81).has_multiple_solutions


def all_valid(puzzle: str, solutions: tuple[str, ...]) -> bool:
    return all(SudokuBoard.from_string(s).is_complete() and
               all(g == "0" or g == d for g, d in zip(puzzle, s)) for s in solutions)


def test_solved_input_and_single_solution_limit():
    solver = PropagationSolver()
    assert solver.analyze(SOLVED).is_unique
    result = solver.analyze(CLASSIC, limit=1)
    assert result.solution_count == 1
    assert not result.exhaustive
    assert not result.is_unique
    assert result.statistics.nodes == 1
    assert result.statistics.decisions == 0
    assert result.statistics.max_depth == 0
    assert result.statistics.propagations > 0


def test_globally_unsatisfiable_and_invalid_givens():
    impossible = CLASSIC[:2] + "1" + CLASSIC[3:]
    assert SudokuBoard.from_string(impossible).is_valid()
    result = PropagationSolver().analyze(impossible)
    assert result.is_unsatisfiable
    assert result.first_solution is None
    assert not result.has_solution
    assert not result.is_unique
    assert result.solution_count == 0
    with pytest.raises(ValueError):
        PropagationSolver().solve("11" + "0" * 79)


def test_state_eliminations_are_preserved_and_inputs_unmodified():
    board = SudokuBoard.from_string(CLASSIC)
    state = CandidateState(board)
    assert 1 in state.candidates_at(0, 2)
    state.eliminate(0, 2, 1)
    before = state.candidates_at(0, 2)
    result = PropagationSolver().analyze(state)
    assert result.solutions == (SOLVED,)
    assert state.board.to_string() == CLASSIC
    assert state.candidates_at(0, 2) == before
    assert board.to_string() == CLASSIC
    assert PropagationSolver().solve(board).to_string() == SOLVED


def test_conflicting_elimination_in_candidate_state_is_not_ignored():
    state = CandidateState(SudokuBoard.from_string(CLASSIC))
    # R1C3=4 is globally necessary but not necessarily a local single.
    try:
        state.eliminate(0, 2, 4)
    except CandidateContradiction:
        pass  # A locally detected contradiction is also correct.
    else:
        assert PropagationSolver().analyze(state).is_unsatisfiable
    # The clue-only oracle must still find a valid solution.
    assert ReferenceSolver().solve(CLASSIC).to_string() == SOLVED


def test_resume_from_a_genuine_logical_stuck_state():
    puzzle = EXAMPLES[4]
    original = SudokuBoard.from_string(puzzle)
    logical = LogicalSolver(techniques=(NakedSingle(),)).solve(original)
    assert logical.status is SolveStatus.STUCK
    assert not logical.state.is_complete()
    solution = PropagationSolver().solve(logical.state)
    assert solution is not None
    assert_valid_completion(puzzle, solution)
    assert solution.to_string() == ReferenceSolver().solve(original).to_string()
    assert original.to_string() == puzzle


def test_determinism_across_runs():
    solver = PropagationSolver(variable_heuristic="mrv_degree", value_heuristic="lcv")
    first = solver.analyze(EXAMPLES[4])
    second = solver.analyze(EXAMPLES[4])
    assert first.solutions == second.solutions
    assert (first.statistics.nodes, first.statistics.decisions,
            first.statistics.propagations, first.statistics.backtracks,
            first.statistics.max_depth) == (
            second.statistics.nodes, second.statistics.decisions,
            second.statistics.propagations, second.statistics.backtracks,
            second.statistics.max_depth)


def test_randomized_clue_subsets_are_valid_and_reference_compatible():
    # Removing clues from a solved board produces valid puzzles. It may make
    # them nonunique, so don't demand identical first solutions or ordering.
    random = Random(8675309)
    reference = ReferenceSolver()
    solver = PropagationSolver(variable_heuristic="mrv_degree", value_heuristic="lcv")
    for clue_count in (24, 28, 35, 40, 45, 50, 60):
        for _ in range(2):
            kept = set(random.sample(range(81), clue_count))
            puzzle = "".join(d if i in kept else "0" for i, d in enumerate(SOLVED))
            oracle = reference.analyze(puzzle)
            result = solver.analyze(puzzle)
            assert result.solution_count == oracle.solution_count
            assert result.is_unique == oracle.is_unique
            assert all_valid(puzzle, result.solutions)


@pytest.mark.parametrize("limit", [0, -3, True, 2.5, "2", None])
def test_bad_solution_limit(limit):
    with pytest.raises(ValueError):
        PropagationSolver().analyze(CLASSIC, limit=limit)


@pytest.mark.parametrize("puzzle", [None, [], 35, {"grid": "0" * 81}])
def test_bad_input_type(puzzle):
    with pytest.raises(TypeError):
        PropagationSolver().solve(puzzle)


@pytest.mark.parametrize("name", ["minimum", "", None, 42])
def test_bad_variable_heuristic(name):
    with pytest.raises(ValueError):
        PropagationSolver(variable_heuristic=name)


@pytest.mark.parametrize("name", ["maximum", "", None, 42])
def test_bad_value_heuristic(name):
    with pytest.raises(ValueError):
        PropagationSolver(value_heuristic=name)


def test_constraint_facade_selection_and_contract():
    propagation = ConstraintSolver(algorithm="propagation", variable_heuristic="mrv_degree", value_heuristic="lcv")
    reference = ConstraintSolver(algorithm="reference")
    assert propagation.solve(CLASSIC).to_string() == reference.solve(CLASSIC).to_string() == SOLVED
    assert propagation.analyze(CLASSIC).is_unique == reference.analyze(CLASSIC).is_unique
    assert propagation.count_solutions(CLASSIC) == reference.count_solutions(CLASSIC) == 1
    candidate_state = CandidateState(SudokuBoard.from_string(CLASSIC))
    assert propagation.solve(candidate_state).to_string() == SOLVED
    with pytest.raises(TypeError):
        reference.solve(candidate_state)
    with pytest.raises(ValueError):
        ConstraintSolver(algorithm="does_not_exist")
    with pytest.raises(ValueError):
        ConstraintSolver(algorithm="reference", value_heuristic="lcv")
