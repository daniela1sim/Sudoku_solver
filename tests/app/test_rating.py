from types import SimpleNamespace

from sudoku.app.session import ReplaySession
from sudoku.solvers.logical.rating import TECHNIQUE_SCORES, estimate_rating
from sudoku.solvers.logical.solver import LogicalSolver


SOLVED = '534678912672195348198342567859761423426853791713924856961537284287419635345286179'


def test_last_value_and_replay_cursor_independence():
    session = ReplaySession('0' + SOLVED[1:])
    initial = session.act('replay')['rating']
    assert initial['score'] == 1.0
    assert initial['status'] == 'complete'
    assert session.act('next')['rating'] == initial
    assert session.act('seek', 0)['rating'] == initial


def test_disabled_techniques_do_not_manufacture_a_score():
    session = ReplaySession('0' + SOLVED[1:], techniques=[])
    rating = session.act('replay')['rating']
    assert rating['status'] == 'incomplete'
    assert rating['score'] is None


def test_filled_grid_has_no_solving_difficulty():
    assert ReplaySession(SOLVED).view()['rating']['status'] == 'already_complete'
    assert ReplaySession(SOLVED).view()['rating']['score'] is None


def test_peak_is_not_sum_and_partial_paths_are_not_final_scores():
    steps = [SimpleNamespace(deduction=SimpleNamespace(technique=name))
             for name in ('X-Wing', 'XY-Wing', 'Naked Pair')]
    assert estimate_rating(steps, complete=True)['score'] == 4.2
    partial = estimate_rating(steps, complete=False)
    assert partial['score'] is None
    assert partial['observed_peak'] == 4.2
    invalid = estimate_rating(steps, complete=True, contradiction=True)
    assert invalid['score'] is None and invalid['observed_peak'] is None


def test_unknown_technique_does_not_silently_underrate():
    steps = [SimpleNamespace(deduction=SimpleNamespace(technique='Future technique'))]
    rating = estimate_rating(steps, complete=True)
    assert rating['status'] == 'unsupported' and rating['score'] is None


def test_catalog_is_covered_and_within_scale():
    assert {t.name for t in LogicalSolver(allow_uniqueness=True).techniques} == set(TECHNIQUE_SCORES)
    assert all(1.0 <= score <= 11.9 for score in TECHNIQUE_SCORES.values())


def test_contradictory_replay_is_unrated_even_at_initial_cursor():
    session = ReplaySession('147000003250001000309000000080020004000410020900000600003000009400002000001008007')
    assert session.act('replay')['rating']['status'] == 'contradiction'
    assert session.act('seek', 0)['rating']['score'] is None
