"""Independent checks of the exact reference solver and its audit API."""

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.solvers.constraint import ReferenceSolver


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


@pytest.fixture
def solver():
    return ReferenceSolver()


def assert_solution_preserves_clues(puzzle: str, solution: SudokuBoard):
    assert solution.is_complete()
    assert len(solution.to_string()) == 81
    assert all(given == "0" or given == actual for given, actual in zip(puzzle, solution.to_string()))


@pytest.mark.parametrize("puzzle", EXAMPLES)
def test_repo_ui_example_puzzles_have_exactly_one_solution(solver, puzzle):
    result = solver.analyze(puzzle)
    assert result.solution_count == 1
    assert result.exhaustive and result.is_unique
    assert result.first_solution is not None
    assert_solution_preserves_clues(puzzle, result.first_solution)
    assert result.statistics.nodes > 0


def test_known_classic_solution_and_counters(solver):
    result = solver.analyze(CLASSIC)
    assert result.solutions == (SOLVED,)
    assert result.statistics.branches >= 1
    assert result.statistics.nodes >= result.statistics.branches
    assert result.statistics.elapsed_seconds >= 0
    assert result.is_unique and not result.is_unsatisfiable


def test_one_solution_limit_never_proves_uniqueness(solver):
    result = solver.analyze(CLASSIC, limit=1)
    assert result.solution_count == 1
    assert not result.exhaustive
    assert not result.is_unique


def test_solved_input(solver):
    result = solver.analyze(SOLVED)
    assert result.solutions == (SOLVED,)
    assert result.is_unique
    assert result.statistics.branches == 0


def test_multiple_solutions_and_capped_counts(solver):
    # Swapping every 1 and 2 in any completion gives a different completion.
    puzzle = "".join("0" if d in "12" else d for d in SOLVED)
    result = solver.analyze(puzzle)
    assert result.solution_count == 2
    assert result.has_multiple_solutions
    assert not result.is_unique
    assert not result.exhaustive
    assert len(set(result.solutions)) == 2
    all_solution_preserve = all(
        all(given == "0" or given == digit for given, digit in zip(puzzle, solution))
        for solution in result.solutions
    )
    assert all_solution_preserve
    assert solver.count_solutions(puzzle, limit=1) == 1


def test_empty_grid_is_not_mistaken_for_unique(solver):
    result = solver.analyze("0" * 81)
    assert result.has_multiple_solutions
    assert not result.exhaustive


def test_locally_legal_but_globally_impossible_clue(solver):
    # A 1 at R1C3 is locally permissible but destroys every completion.
    impossible = CLASSIC[:2] + "1" + CLASSIC[3:]
    board = SudokuBoard.from_string(impossible)
    assert board.is_valid()
    result = solver.analyze(board)
    assert result.is_unsatisfiable
    assert not result.has_solution
    assert not result.is_unique
    assert solver.solve(board) is None
    assert solver.count_solutions(board) == 0


def test_forced_assumptions_and_forbidden_assumptions(solver):
    assert solver.has_solution(CLASSIC, forced=[(0, 2, 4)])
    assert not solver.has_solution(CLASSIC, forced=[(0, 2, 1)])
    assert solver.has_solution(CLASSIC, forbidden=[(0, 2, 1)])
    assert not solver.has_solution(CLASSIC, forbidden=[(0, 2, 4)])
    assert solver.analyze(CLASSIC, forced=[(0, 2, 4)]).is_unique


def test_contradictory_forced_and_forbidden_assumptions(solver):
    assert not solver.has_solution(CLASSIC, forced=[(0, 2, 4), (0, 2, 1)])
    assert not solver.has_solution(CLASSIC, forced=[(0, 2, 4)], forbidden=[(0, 2, 4)])
    assert not solver.has_solution(CLASSIC, forced=[(0, 0, 1)])  # contradicts fixed 5
    assert not solver.has_solution(CLASSIC, forbidden=[(0, 0, 5)])
    assert not solver.has_solution(CLASSIC, forced=[(0, 2, 4), (0, 3, 4)])


def test_oracle_entailment_methods(solver):
    assert solver.allows_candidate(CLASSIC, 0, 2, 4)
    assert not solver.allows_candidate(CLASSIC, 0, 2, 1)
    assert solver.forces_placement(CLASSIC, 0, 2, 4)
    assert not solver.forces_placement(CLASSIC, 0, 2, 1)
    assert solver.proves_elimination(CLASSIC, 0, 2, 1)
    assert not solver.proves_elimination(CLASSIC, 0, 2, 4)


def test_oracle_requires_at_least_one_completion(solver):
    impossible = CLASSIC[:2] + "1" + CLASSIC[3:]
    assert not solver.forces_placement(impossible, 0, 2, 4)
    assert not solver.proves_elimination(impossible, 0, 2, 1)


def test_original_board_is_not_mutated(solver):
    board = SudokuBoard.from_string(CLASSIC)
    initial = board.to_string()
    result = solver.analyze(board, forced=((0, 2, 4),), forbidden=((0, 3, 2),))
    assert result.has_solution
    assert board.to_string() == initial
    answer = solver.solve(board)
    assert answer is not board
    assert answer.is_complete()
    assert board.to_string() == initial


def test_search_is_deterministic_except_for_time(solver):
    first = solver.analyze(CLASSIC)
    second = solver.analyze(CLASSIC)
    assert first.solutions == second.solutions
    assert first.statistics.nodes == second.statistics.nodes
    assert first.statistics.branches == second.statistics.branches
    assert first.statistics.dead_ends == second.statistics.dead_ends


@pytest.mark.parametrize("limit", [0, -1, 1.5, True, "2", None])
def test_invalid_limit(solver, limit):
    with pytest.raises(ValueError):
        solver.analyze(CLASSIC, limit=limit)


@pytest.mark.parametrize("assumption", [(-1, 0, 1), (0, 9, 1), (0, 0, 0), (0, 0, 10), (True, 0, 1), (0, 1), "012", (0, 0, 3.0)])
def test_invalid_assumptions(solver, assumption):
    with pytest.raises(ValueError):
        solver.analyze(CLASSIC, forced=[assumption])
    with pytest.raises(ValueError):
        solver.analyze(CLASSIC, forbidden=[assumption])


def test_assumptions_must_be_iterable(solver):
    with pytest.raises(TypeError):
        solver.analyze(CLASSIC, forced=None)


def test_invalid_puzzle_type_and_conflicting_givens(solver):
    with pytest.raises(TypeError):
        solver.solve([0] * 81)
    with pytest.raises(ValueError):
        solver.solve("11" + "0" * 79)


def test_does_not_depend_on_logical_state_or_verifier(monkeypatch, solver):
    # Even when the logical verifier cannot operate, this module remains usable.
    from sudoku.solvers.logical.verification import DeductionVerifier
    def unavailable(*_args, **_kwargs):
        raise AssertionError("logical verification must not be called")
    monkeypatch.setattr(DeductionVerifier, "verify", unavailable)
    assert solver.solve(CLASSIC).to_string() == SOLVED
