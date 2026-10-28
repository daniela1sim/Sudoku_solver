import pytest

from sudoku.app.session import ReplaySession
from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.solvers.logical.singles import HiddenSingle
from sudoku.solvers.logical.subsets import NakedPair
from sudoku.solvers.logical.solver import LogicalSolver


SOLVED = '534678912672195348198342567859761423426853791713924856961537284287419635345286179'


def test_contradiction_keeps_last_consistent_state_and_replay():
    puzzle = '147000003250001000309000000080020004000410020900000600003000009400002000001008007'
    session = ReplaySession(puzzle)
    final = session.act('replay')
    assert final['status'] == 'contradiction'
    assert final['cursor'] == final['total'] == 4
    assert final['grid'][19] == '6'  # R3C2
    assert final['grid'][11] == '8'  # R2C3
    assert final['grid'][17] == '6'  # R2C9
    assert final['grid'][47] == '4'  # Show the hidden single exposing the contradiction.
    assert final['contradiction']
    assert session.act('replay') == final
    assert session.act('hint') == final
    assert session.act('next') == final
    initial = session.act('seek', 0)
    assert initial['grid'] == puzzle and initial['status'] == 'ready'
    assert initial['contradiction'] is None
    assert session.act('seek', 4) == final


def test_verification_failure_is_not_treated_as_puzzle_contradiction(monkeypatch):
    session = ReplaySession('00' + SOLVED[2:])
    def fail(*args, **kwargs):
        raise ValueError('Invalid deduction witness')
    monkeypatch.setattr(session.solver, 'solve', fail)
    with pytest.raises(ValueError, match='Invalid deduction witness'):
        session.act('replay')
    assert session.contradiction is None


def test_hint_is_read_only_and_cached_then_applied():
    session = ReplaySession('00' + SOLVED[2:])
    before = session.view()
    hint = session.act('hint')
    assert hint['grid'] == before['grid']
    assert hint['candidates'] == before['candidates']
    assert hint['cursor'] == hint['total'] == 0
    assert hint['hint']['placements'] == [{'cell': (0, 0), 'digit': 5}]
    assert session.act('hint') == hint
    applied = session.act('next')
    assert applied['cursor'] == applied['total'] == 1
    assert applied['hint'] is None
    assert applied['last'] == hint['hint']
    assert applied['grid'][0] == '5'


def test_full_replay_generates_multiple_steps_without_advancing_display():
    session = ReplaySession('000' + SOLVED[3:])
    initial = session.view()
    session.act('hint')
    replay = session.act('replay')
    assert replay['total'] == 3
    assert replay['cursor'] == 0
    assert replay['grid'] == initial['grid']
    assert replay['candidates'] == initial['candidates']
    assert replay['hint'] is None
    assert replay['history'] == []
    assert len(session.act('next')['history']) == 1
    assert len(session.act('seek', 2)['history']) == 2
    assert session.act('seek', 0)['history'] == []
    assert session.act('seek', 3)['status'] == 'solved'
    assert len(session.view()['history']) == 3
    assert session.act('replay')['total'] == 3


def test_full_replay_extends_applied_history():
    session = ReplaySession('000' + SOLVED[3:])
    first = session.act('next')
    replay = session.act('replay')
    assert replay['cursor'] == 1 and replay['total'] == 3
    assert replay['grid'] == first['grid']
    assert session.act('next')['cursor'] == 2


def test_replay_restores_exact_candidate_states_without_duplicating_history():
    session = ReplaySession('00' + SOLVED[2:])
    initial = session.view()
    first = session.act('next')
    last = session.act('next')
    assert last['status'] == 'solved'
    assert last['grid'] == SOLVED
    rewound = session.act('seek', 0)
    assert rewound['grid'] == initial['grid']
    assert rewound['candidates'] == initial['candidates']
    assert rewound['last'] is None
    replayed = session.act('next')
    assert replayed['grid'] == first['grid']
    assert replayed['candidates'] == first['candidates']
    assert replayed['total'] == 2
    assert session.act('hint')['hint'] == last['last']
    assert session.act('next') == last


def test_candidate_eliminations_survive_replay():
    # A state that requires the saved candidate sets to find its hidden single.
    session = ReplaySession('0' * 81)
    state = CandidateState(SudokuBoard.from_string('0' * 81))
    for col in range(8):
        state.eliminate(0, col, 1)
    session.states = [state]
    session.solver = LogicalSolver((HiddenSingle(),))
    before = session.view()
    session.act('next')
    rewound = session.act('seek', 0)
    assert rewound['candidates'] == before['candidates']
    assert 1 not in rewound['candidates'][0]
    assert session.act('hint')['hint']['placements'] == [{'cell': (0, 8), 'digit': 1}]


def test_solved_and_stuck_are_distinct():
    solved = ReplaySession(SOLVED)
    assert solved.act('hint')['status'] == 'solved'
    assert solved.act('next')['total'] == 0
    stuck = ReplaySession('0' * 81)
    assert stuck.act('hint')['status'] == 'stuck'
    assert stuck.act('next')['total'] == 0


def test_elimination_only_hint_and_replay():
    session = ReplaySession('0' * 81)
    for col in (0, 1):
        for digit in range(3, 10):
            session.states[0].eliminate(0, col, digit)
    session.solver = LogicalSolver((NakedPair(),))
    before = session.view()
    preview = session.act('hint')
    assert preview['hint']['eliminations'] and not preview['hint']['placements']
    assert preview['candidates'] == before['candidates']
    after = session.act('next')
    assert after['grid'] == before['grid']
    assert after['candidates'][2] == list(range(3, 10))
    assert session.act('seek', 0)['candidates'] == before['candidates']
    assert session.act('next')['candidates'] == after['candidates']


@pytest.mark.parametrize('cursor', [-1, 1, True, '0', None])
def test_invalid_seek(cursor):
    with pytest.raises(ValueError):
        ReplaySession(SOLVED).act('seek', cursor)


def test_invalid_puzzles_and_actions():
    with pytest.raises(ValueError):
        ReplaySession('11' + '0' * 79)
    with pytest.raises(ValueError):
        ReplaySession('123')
    with pytest.raises(ValueError):
        ReplaySession(SOLVED).act('unknown')
