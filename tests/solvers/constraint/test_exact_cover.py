"""Independent Algorithm X regression tests and oracle comparisons."""

from random import Random

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateContradiction, CandidateState
from sudoku.solvers.constraint import ConstraintSolver, ExactCoverSolver, ReferenceSolver
from sudoku.solvers.logical.singles import NakedSingle
from sudoku.solvers.logical.solver import LogicalSolver, SolveStatus

SOLVED = '534678912672195348198342567859761423426853791713924856961537284287419635345286179'
CLASSIC = '530070000600195000098000060800060003400803001700020006060000280000419005000080079'
EXAMPLES = (
    CLASSIC,
    '003020600900305001001806400008102900700000008006708200002609500800203009005010300',
    '200080300060070084030500209000105408000000000402706000301007040720040060004010003',
    '000000010400000000020000000000050407008000300001090000300400200050100000000806000',
    '005000987040050001007000000200048000090100000600200000300600200000009070000000500',
    '023700006800060590900000700000040970307096002000000000500470000000002000080000000',
)


def is_valid_completion(puzzle, solution):
    return (SudokuBoard.from_string(solution).is_complete()
            and all(g == '0' or g == d for g, d in zip(puzzle, solution)))


@pytest.mark.parametrize('puzzle', EXAMPLES)
def test_known_unique_cases_match_oracle(puzzle):
    result = ExactCoverSolver().analyze(puzzle)
    assert result.solutions == ReferenceSolver().analyze(puzzle).solutions
    assert result.is_unique and result.exhaustive and result.has_solution
    assert is_valid_completion(puzzle, result.solutions[0])
    assert result.first_solution.is_complete()
    assert result.statistics.nodes >= 82
    assert result.statistics.row_selections >= 81
    assert result.statistics.row_selections == result.statistics.decisions + result.statistics.forced_selections
    assert result.statistics.max_depth == 81
    assert result.statistics.elapsed_seconds >= 0


def test_solved_board_requires_only_forced_rows():
    board = SudokuBoard.from_string(SOLVED)
    result = ExactCoverSolver().analyze(board)
    assert result.solutions == (SOLVED,) and result.is_unique
    assert result.statistics.decisions == 0
    assert result.statistics.forced_selections == 81
    assert result.statistics.dead_ends == result.statistics.backtracks == 0
    assert board.to_string() == SOLVED


def test_globally_impossible_but_locally_legal_clue():
    impossible = CLASSIC[:2] + '1' + CLASSIC[3:]
    assert SudokuBoard.from_string(impossible).is_valid()
    result = ExactCoverSolver().analyze(impossible)
    assert result.is_unsatisfiable and result.exhaustive
    assert not result.has_solution and result.first_solution is None
    assert ExactCoverSolver().solve(impossible) is None
    assert ExactCoverSolver().count_solutions(impossible) == 0


def test_multiple_solutions_empty_board_and_limit_semantics():
    ambiguous = ''.join('0' if d in '12' else d for d in SOLVED)
    solver = ExactCoverSolver()
    result = solver.analyze(ambiguous)
    assert result.solution_count == 2 and result.has_multiple_solutions
    assert not result.is_unique and not result.exhaustive
    assert len(set(result.solutions)) == 2
    assert all(is_valid_completion(ambiguous, s) for s in result.solutions)
    assert solver.count_solutions(ambiguous, limit=1) == 1
    # Search both branches exhaustively, including cover/uncover restoration.
    exhaustive = solver.analyze(ambiguous, limit=3)
    assert exhaustive.exhaustive and exhaustive.solution_count == 2
    assert set(exhaustive.solutions) == set(result.solutions)
    assert solver.analyze('0' * 81).has_multiple_solutions
    one = solver.analyze(CLASSIC, limit=1)
    assert one.solutions == (SOLVED,) and not one.exhaustive and not one.is_unique


def test_candidate_state_eliminations_are_preserved():
    board = SudokuBoard.from_string(CLASSIC)
    state = CandidateState(board)
    assert 1 in state.candidates_at(0, 2)
    state.eliminate(0, 2, 1)
    choices = state.candidates_at(0, 2)
    assert ExactCoverSolver().analyze(state).solutions == (SOLVED,)
    assert state.candidates_at(0, 2) == choices
    assert state.board.to_string() == board.to_string() == CLASSIC


def test_globally_necessary_elimination_makes_state_unsatisfiable():
    state = CandidateState(SudokuBoard.from_string(CLASSIC))
    try:
        state.eliminate(0, 2, 4)
    except CandidateContradiction:
        pass
    else:
        assert ExactCoverSolver().analyze(state).is_unsatisfiable
    assert ReferenceSolver().solve(CLASSIC).to_string() == SOLVED


def test_resume_from_genuine_human_stuck_state():
    puzzle = EXAMPLES[4]
    board = SudokuBoard.from_string(puzzle)
    logical = LogicalSolver(techniques=(NakedSingle(),)).solve(board)
    assert logical.status is SolveStatus.STUCK
    prior = {(r, c): logical.state.candidates_at(r, c)
             for r, c in logical.state.unsolved_cells()}
    result = ExactCoverSolver().analyze(logical.state)
    assert result.is_unique
    assert result.solutions == ReferenceSolver().analyze(puzzle).solutions
    assert prior == {(r, c): logical.state.candidates_at(r, c)
                     for r, c in logical.state.unsolved_cells()}
    assert board.to_string() == puzzle


def test_deterministic_choice_order_and_counters():
    results = [ExactCoverSolver().analyze(EXAMPLES[4]) for _ in range(3)]
    assert len({r.solutions for r in results}) == 1
    def counters(result):
        s = result.statistics
        return (s.nodes, s.row_selections, s.decisions, s.forced_selections,
                s.dead_ends, s.backtracks, s.max_depth)
    assert len({counters(r) for r in results}) == 1


def test_random_clue_subsets_against_independent_reference():
    rng = Random(20261029)
    for count in (23, 27, 32, 38, 47, 60):
        for _ in range(3):
            kept = set(rng.sample(range(81), count))
            puzzle = ''.join(d if i in kept else '0' for i, d in enumerate(SOLVED))
            oracle = ReferenceSolver().analyze(puzzle)
            actual = ExactCoverSolver().analyze(puzzle)
            assert (actual.solution_count, actual.is_unique, actual.is_unsatisfiable,
                    actual.has_multiple_solutions) == (
                    oracle.solution_count, oracle.is_unique, oracle.is_unsatisfiable,
                    oracle.has_multiple_solutions)
            assert all(is_valid_completion(puzzle, s) for s in actual.solutions)
            if oracle.is_unique:
                assert actual.solutions == oracle.solutions


@pytest.mark.parametrize('limit', [0, -3, True, 1.2, '2', None])
def test_bad_limit(limit):
    with pytest.raises(ValueError):
        ExactCoverSolver().analyze(CLASSIC, limit=limit)


@pytest.mark.parametrize('puzzle', [None, [], 12, {'puzzle': CLASSIC}])
def test_bad_input_type(puzzle):
    with pytest.raises(TypeError):
        ExactCoverSolver().solve(puzzle)


def test_invalid_clues_rejected():
    with pytest.raises(ValueError):
        ExactCoverSolver().solve('11' + '0' * 79)
    with pytest.raises(ValueError):
        ExactCoverSolver().solve('bad puzzle')


def test_facade_selects_exact_cover_and_rejects_irrelevant_heuristics():
    facade = ConstraintSolver(algorithm='exact_cover')
    assert facade.solve(CLASSIC).to_string() == SOLVED
    assert facade.count_solutions(CLASSIC) == 1
    assert facade.analyze(CLASSIC).is_unique
    assert facade.solve(CandidateState(SudokuBoard.from_string(CLASSIC))).to_string() == SOLVED
    with pytest.raises(ValueError, match='heuristics'):
        ConstraintSolver(algorithm='exact_cover', variable_heuristic='first')
    with pytest.raises(ValueError, match='heuristics'):
        ConstraintSolver(algorithm='exact_cover', value_heuristic='lcv')


def test_exact_cover_is_independent_of_other_solvers_and_verifier(monkeypatch):
    from sudoku.solvers.constraint.propagation import PropagationSolver
    from sudoku.solvers.logical.verification import DeductionVerifier
    def unavailable(*args, **kwargs):
        raise AssertionError('exact cover must not invoke other solvers')
    monkeypatch.setattr(ReferenceSolver, 'analyze', unavailable)
    monkeypatch.setattr(PropagationSolver, 'analyze', unavailable)
    monkeypatch.setattr(DeductionVerifier, 'verify', unavailable)
    assert ExactCoverSolver().solve(CLASSIC).to_string() == SOLVED
