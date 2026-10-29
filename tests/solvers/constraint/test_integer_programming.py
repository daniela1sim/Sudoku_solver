"""MILP solver regression tests against an independent backtracking oracle."""

from random import Random

import pytest

pytest.importorskip("scipy", reason="MILP backend requires optional SciPy dependency")

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateContradiction, CandidateState
from sudoku.solvers.constraint import ConstraintSolver, IntegerProgrammingSolver, ReferenceSolver
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


def is_valid_completion(puzzle: str, solution: str) -> bool:
    return (SudokuBoard.from_string(solution).is_complete()
            and all(g == "0" or g == v for g, v in zip(puzzle, solution)))


@pytest.mark.parametrize("puzzle", EXAMPLES)
def test_known_unique_puzzles_agree_with_reference(puzzle):
    result = IntegerProgrammingSolver().analyze(puzzle)
    assert result.solutions == ReferenceSolver().analyze(puzzle).solutions
    assert result.is_unique and result.exhaustive
    assert result.solution_count == 1 and result.has_solution
    assert is_valid_completion(puzzle, result.solutions[0])
    assert result.first_solution.is_complete()
    assert result.statistics.milp_calls == 2
    assert result.statistics.no_good_cuts == 1
    assert result.statistics.elapsed_seconds >= 0


def test_solved_board_and_input_immutability():
    board = SudokuBoard.from_string(SOLVED)
    result = IntegerProgrammingSolver().analyze(board)
    assert result.solutions == (SOLVED,) and result.is_unique
    assert result.statistics.milp_calls == 2
    assert board.to_string() == SOLVED


def test_globally_impossible_clues():
    impossible = CLASSIC[:2] + "1" + CLASSIC[3:]
    assert SudokuBoard.from_string(impossible).is_valid()
    result = IntegerProgrammingSolver().analyze(impossible)
    assert result.is_unsatisfiable and result.exhaustive
    assert not result.has_solution and result.first_solution is None
    assert result.statistics.milp_calls == 1 and result.statistics.no_good_cuts == 0
    assert IntegerProgrammingSolver().solve(impossible) is None
    assert IntegerProgrammingSolver().count_solutions(impossible) == 0


def test_solution_cap_and_uniqueness_proof():
    ambiguous = ''.join('0' if digit in '12' else digit for digit in SOLVED)
    solver = IntegerProgrammingSolver()
    limited = solver.analyze(ambiguous)
    assert limited.solution_count == 2 and limited.has_multiple_solutions
    assert not limited.exhaustive and not limited.is_unique
    assert len(set(limited.solutions)) == 2
    assert all(is_valid_completion(ambiguous, s) for s in limited.solutions)
    assert limited.statistics.milp_calls == 2
    assert limited.statistics.no_good_cuts == 1

    exhaustive = solver.analyze(ambiguous, limit=3)
    assert exhaustive.exhaustive and exhaustive.solution_count == 2
    assert set(exhaustive.solutions) == set(limited.solutions)
    assert exhaustive.statistics.milp_calls == 3
    assert exhaustive.statistics.no_good_cuts == 2

    one = solver.analyze(CLASSIC, limit=1)
    assert one.solution_count == 1 and not one.exhaustive and not one.is_unique
    assert one.statistics.milp_calls == 1 and one.statistics.no_good_cuts == 0
    assert solver.count_solutions(ambiguous, limit=1) == 1
    assert solver.analyze('0' * 81).has_multiple_solutions


def test_preserves_candidate_eliminations_and_board():
    board = SudokuBoard.from_string(CLASSIC)
    state = CandidateState(board)
    state.eliminate(0, 2, 1)
    before = {(r, c): state.candidates_at(r, c) for r, c in state.unsolved_cells()}
    result = IntegerProgrammingSolver().analyze(state)
    assert result.solutions == (SOLVED,)
    assert before == {(r, c): state.candidates_at(r, c) for r, c in state.unsolved_cells()}
    assert state.board.to_string() == board.to_string() == CLASSIC


def test_globally_necessary_candidate_removed():
    state = CandidateState(SudokuBoard.from_string(CLASSIC))
    try:
        state.eliminate(0, 2, 4)
    except CandidateContradiction:
        pass  # Local candidate consistency already catches the contradiction.
    else:
        assert IntegerProgrammingSolver().analyze(state).is_unsatisfiable


def test_globally_impossible_candidate_state_rejected_even_when_locally_consistent():
    # On this harder puzzle, R1C2 must be 3 globally, but deleting that
    # candidate does not break CandidateState's local cell/unit checks.
    puzzle = EXAMPLES[4]
    state = CandidateState(SudokuBoard.from_string(puzzle))
    assert state.eliminate(0, 1, 3)
    assert IntegerProgrammingSolver().analyze(state).is_unsatisfiable
    assert ReferenceSolver().solve(puzzle).to_string()[1] == '3'


def test_sparse_constraint_matrix_shape_and_incidence():
    from sudoku.solvers.constraint.integer_programming import _constraint_matrix
    import numpy as np

    matrix = _constraint_matrix()
    assert matrix.shape == (324, 729) and matrix.nnz == 4 * 729
    assert np.all(np.asarray(matrix.sum(axis=0)).ravel() == 4)
    assert np.all(np.asarray(matrix.sum(axis=1)).ravel() == 9)


def test_resumes_from_a_genuine_logical_stuck_state():
    puzzle = EXAMPLES[4]
    board = SudokuBoard.from_string(puzzle)
    logical = LogicalSolver(techniques=(NakedSingle(),)).solve(board)
    assert logical.status is SolveStatus.STUCK
    prior = {(r, c): logical.state.candidates_at(r, c)
             for r, c in logical.state.unsolved_cells()}
    result = IntegerProgrammingSolver().analyze(logical.state)
    assert result.is_unique
    assert result.solutions == ReferenceSolver().analyze(puzzle).solutions
    assert prior == {(r, c): logical.state.candidates_at(r, c)
                     for r, c in logical.state.unsolved_cells()}
    assert board.to_string() == puzzle


def test_random_clue_subsets_against_reference():
    rng = Random(20261029)
    for count in (23, 27, 32, 38, 47, 60):
        for _ in range(2):
            kept = set(rng.sample(range(81), count))
            puzzle = ''.join(d if i in kept else '0' for i, d in enumerate(SOLVED))
            oracle = ReferenceSolver().analyze(puzzle)
            actual = IntegerProgrammingSolver().analyze(puzzle)
            assert (actual.solution_count, actual.is_unique, actual.is_unsatisfiable,
                    actual.has_multiple_solutions) == (
                    oracle.solution_count, oracle.is_unique, oracle.is_unsatisfiable,
                    oracle.has_multiple_solutions)
            assert all(is_valid_completion(puzzle, s) for s in actual.solutions)
            if oracle.is_unique:
                assert actual.solutions == oracle.solutions


@pytest.mark.parametrize('limit', [0, -1, True, 1.5, '2', None])
def test_invalid_limit(limit):
    with pytest.raises(ValueError):
        IntegerProgrammingSolver().analyze(CLASSIC, limit=limit)


@pytest.mark.parametrize('puzzle', [None, [], 12, {'puzzle': CLASSIC}])
def test_invalid_input_type(puzzle):
    with pytest.raises(TypeError):
        IntegerProgrammingSolver().solve(puzzle)


def test_invalid_clues_rejected():
    with pytest.raises(ValueError):
        IntegerProgrammingSolver().solve('11' + '0' * 79)
    with pytest.raises(ValueError):
        IntegerProgrammingSolver().solve('bad puzzle')


def test_facade_and_fixed_heuristics():
    facade = ConstraintSolver(algorithm='integer_programming')
    assert facade.solve(CLASSIC).to_string() == SOLVED
    assert facade.count_solutions(CLASSIC) == 1
    assert facade.analyze(CLASSIC).is_unique
    state = CandidateState(SudokuBoard.from_string(CLASSIC))
    assert facade.solve(state).to_string() == SOLVED
    with pytest.raises(ValueError, match='heuristics'):
        ConstraintSolver(algorithm='integer_programming', variable_heuristic='first')
    with pytest.raises(ValueError, match='heuristics'):
        ConstraintSolver(algorithm='integer_programming', value_heuristic='lcv')


def test_independence_from_other_solvers_and_logic(monkeypatch):
    from sudoku.solvers.constraint.propagation import PropagationSolver
    from sudoku.solvers.constraint.exact_cover import ExactCoverSolver
    from sudoku.solvers.logical.verification import DeductionVerifier

    def unavailable(*_args, **_kwargs):
        raise AssertionError('MILP must not call another Sudoku solver')

    monkeypatch.setattr(ReferenceSolver, 'analyze', unavailable)
    monkeypatch.setattr(PropagationSolver, 'analyze', unavailable)
    monkeypatch.setattr(ExactCoverSolver, 'analyze', unavailable)
    monkeypatch.setattr(DeductionVerifier, 'verify', unavailable)
    assert IntegerProgrammingSolver().solve(CLASSIC).to_string() == SOLVED


def test_milp_failure_status_does_not_look_like_unsatisfiable(monkeypatch):
    from scipy import optimize

    def fail(*_args, **_kwargs):
        class Result:
            status = 1
            x = None
            message = 'resource limit'
            mip_node_count = None
        return Result()

    monkeypatch.setattr(optimize, 'milp', fail)
    with pytest.raises(RuntimeError, match='status=1'):
        IntegerProgrammingSolver().analyze(CLASSIC)
