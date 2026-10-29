import base64

import pytest

from sudoku.app.web import create_app

URL = 'https://sudoku.example.com'
PUZZLE = '034678912672195348198342567859761423426853791713924856961537284287419635345286179'


@pytest.fixture
def client():
    return create_app(URL).test_client()


def post(client, path, body, **kwargs):
    return client.post(path, json=body, base_url=URL, **kwargs)


def test_hosted_roundtrip(client):
    for path in ('/', '/app.js', '/style.css', '/api/techniques', '/healthz'):
        response = client.get(path, base_url=URL)
        assert response.status_code == 200
        assert response.headers['X-Content-Type-Options'] == 'nosniff'
    initial = post(client, '/api/start', {'puzzle': PUZZLE}, headers={'Origin': URL})
    assert initial.status_code == 200
    token = initial.json['session']
    assert initial.json['total'] == 1
    hint = post(client, '/api/action', {'session': token, 'action': 'hint'})
    assert hint.json['hint'] and hint.json['grid'] == PUZZLE
    assert post(client, '/api/action', {'session': token, 'action': 'next'}).json['status'] == 'solved'
    assert post(client, '/api/action', {'session': token, 'action': 'seek', 'cursor': 0}).json['grid'] == PUZZLE


def test_hosted_request_boundaries(client):
    assert post(client, '/api/start', {'puzzle': PUZZLE}, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert post(client, '/api/start', {'puzzle': PUZZLE}, headers={'Host': 'evil.example', 'X-Forwarded-Host': 'sudoku.example.com'}).status_code == 403
    assert client.post('/api/start', base_url=URL, data='{}', content_type='text/plain').status_code == 415
    assert post(client, '/api/start', []).status_code == 400
    assert post(client, '/api/start', {'puzzle': '1' * 81}).status_code == 400
    assert post(client, '/api/start', {'puzzle': '0' * 5000}).status_code == 413
    assert client.post('/api/start', base_url=URL, data='{', content_type='application/json').status_code == 400
    assert post(client, '/api/action', {'session': 'missing'}).status_code == 404
    assert client.get('/../pyproject.toml', base_url=URL).status_code == 404


def test_hosted_image(client, monkeypatch):
    import sudoku.vision
    seen = []
    def read(data):
        seen.append(data)
        return {'puzzle': '0' * 81}
    monkeypatch.setattr(sudoku.vision, 'read_image', read)
    assert post(client, '/api/image', {'image': base64.b64encode(b'image').decode()}).status_code == 200
    assert seen == [b'image']
    assert post(client, '/api/image', {'image': '!!'}).status_code == 400


def test_render_origin_configuration(monkeypatch):
    monkeypatch.delenv('PUBLIC_URL', raising=False)
    monkeypatch.setenv('RENDER_EXTERNAL_URL', URL)
    assert create_app().test_client().post('/api/start', base_url=URL, json={'puzzle': PUZZLE}).status_code == 200
    with pytest.raises(ValueError):
        create_app('https://example.com/path')


@pytest.mark.parametrize('puzzle,status,count,exact', [
    (PUZZLE, 'unique', 1, True),
    ('0' * 81, 'multiple', 2, False),
    ('147000003250001000309000000080020004000410020900000600003000009400002000001008007',
     'unsatisfiable', 0, True),
])
def test_check_outcomes(client, puzzle, status, count, exact):
    response = post(client, '/api/check', {'puzzle': puzzle})
    assert response.status_code == 200
    assert response.json == {'status': status, 'solution_count': count, 'count_is_exact': exact}


@pytest.mark.parametrize('puzzle', [None, 123, '', '0' * 80, 'x' * 81, '11' + '0' * 79])
def test_check_rejects_invalid_input(client, puzzle):
    assert post(client, '/api/check', {'puzzle': puzzle}).status_code == 400


def test_check_has_same_request_protection(client):
    assert post(client, '/api/check', {'puzzle': PUZZLE}, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert post(client, '/api/check', {'puzzle': '0' * 5000}).status_code == 413
    assert post(client, '/api/check', []).status_code == 400


def test_check_does_not_change_replay_or_depend_on_assumption():
    from sudoku.app.service import SudokuService
    service = SudokuService()
    _, initial = service.dispatch('/api/start', {'puzzle': PUZZLE, 'techniques': []})
    session = service.sessions[initial['session']]
    before = session.view()
    for assumed in (False, True):
        _, result = service.dispatch('/api/check', {
            'puzzle': '0' * 81, 'allow_uniqueness': assumed, 'techniques': []})
        assert result['status'] == 'multiple'
    assert session.view() == before
    assert len(service.sessions) == 1
