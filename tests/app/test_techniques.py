import pytest

from sudoku.app.session import ReplaySession
from sudoku.app.techniques import catalog, selected_solver


def test_catalog_matches_defaults_and_marks_uniqueness():
    entries = catalog()
    assert len({item['name'] for item in entries}) == len(entries)
    assert {item['name'] for item in entries if not item['requires_uniqueness']} == {
        t.name for t in selected_solver().techniques
    }
    assert next(item for item in entries if item['name'] == 'Unique Rectangle Type 1')['requires_uniqueness']


def test_selection_preserves_priority_and_uniqueness_gate():
    assert [t.name for t in selected_solver(['Hidden Single', 'Naked Single']).techniques] == ['Naked Single', 'Hidden Single']
    assert not selected_solver([]).techniques
    assert len(selected_solver(['Unique Rectangle Type 1'], allow_uniqueness=True).techniques) == 1


@pytest.mark.parametrize('names', ['Naked Single', [1], ['Unknown'], ['Naked Single', 'Naked Single'], ['Unique Rectangle Type 1']])
def test_invalid_or_disallowed_selection(names):
    with pytest.raises(ValueError):
        selected_solver(names)


def test_hints_and_replay_respect_no_techniques():
    puzzle = '034678912672195348198342567859761423426853791713924856961537284287419635345286179'
    session = ReplaySession(puzzle, techniques=[])
    assert session.act('hint')['hint'] is None
    replay = session.act('replay')
    assert replay['total'] == 0 and replay['status'] == 'stuck'
    assert replay['grid'] == puzzle and replay['techniques'] == []


def test_singles_preset_stops_on_advanced_puzzle():
    puzzle = '005000987040050001007000000200048000090100000600200000300600200000009070000000500'
    session = ReplaySession(puzzle, techniques=['Naked Single', 'Hidden Single'])
    session.act('replay')
    assert session.stuck
    assert not session.states[-1].is_complete()
    assert all(step.deduction.technique in {'Naked Single', 'Hidden Single'} for step in session.steps)
