import http.client
import json
import threading

import pytest

from sudoku.app.__main__ import AppServer


@pytest.fixture
def server():
    app = AppServer(('127.0.0.1', 0))
    thread = threading.Thread(target=app.serve_forever, daemon=True)
    thread.start()
    yield app
    app.shutdown()
    app.server_close()
    thread.join()


def request(server, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
    connection.request(method, path, body, headers or {})
    response = connection.getresponse()
    data = response.read()
    status = response.status
    connection.close()
    return status, data


def post(server, path, body):
    status, data = request(server, 'POST', path, json.dumps(body), {'Content-Type': 'application/json'})
    return status, json.loads(data)


def test_assets_and_full_hint_roundtrip(server):
    for path in ['/', '/app.js', '/style.css']:
        status, data = request(server, 'GET', path)
        assert status == 200 and data
    assert request(server, 'GET', '/../pyproject.toml')[0] == 404
    puzzle = '034678912672195348198342567859761423426853791713924856961537284287419635345286179'
    status, initial = post(server, '/api/start', {'puzzle': puzzle})
    assert status == 200
    assert initial['total'] == 1 and initial['cursor'] == 0
    token = initial['session']
    status, hinted = post(server, '/api/action', {'session': token, 'action': 'hint'})
    assert status == 200 and hinted['hint'] and hinted['grid'] == puzzle
    status, solved = post(server, '/api/action', {'session': token, 'action': 'next'})
    assert status == 200 and solved['status'] == 'solved'
    assert post(server, '/api/action', {'session': token, 'action': 'seek', 'cursor': 0})[1]['grid'] == puzzle


def test_start_automatically_prepares_multiple_replay_steps(server):
    puzzle = '530070000600195000098000060800060003400803001700020006060000280000419005000080079'
    status, initial = post(server, '/api/start', {'puzzle': puzzle})
    assert status == 200
    assert initial['total'] == 51
    assert initial['cursor'] == 0 and initial['grid'] == puzzle


def test_api_rejects_bad_input_and_cross_origin_requests(server):
    assert post(server, '/api/start', {'puzzle': '11' + '0' * 79})[0] == 400
    assert post(server, '/api/start', {'puzzle': '0' * 81, 'allow_uniqueness': 'yes'})[0] == 400
    assert post(server, '/api/action', {'session': 'missing', 'action': 'hint'})[0] == 404
    # These checks reject headers before reading a body. Avoid an unread body
    # causing a Windows TCP reset when the server closes the connection.
    assert request(server, 'POST', '/api/start', None, {'Content-Type': 'text/plain'})[0] == 415
    assert request(server, 'POST', '/api/start', None, {'Content-Type': 'application/json', 'Origin': 'https://example.com'})[0] == 403
    assert request(server, 'POST', '/api/start', '{', {'Content-Type': 'application/json'})[0] == 400


def test_api_technique_selection(server):
    status, data = request(server, 'GET', '/api/techniques')
    assert status == 200 and any(t['name'] == 'Naked Single' for t in json.loads(data))
    puzzle = '034678912672195348198342567859761423426853791713924856961537284287419635345286179'
    status, response = post(server, '/api/start', {'puzzle': puzzle, 'techniques': []})
    assert status == 200 and response['total'] == 0 and response['techniques'] == []
    status, response = post(server, '/api/start', {'puzzle': puzzle, 'techniques': ['Naked Single']})
    assert status == 200 and response['total'] == 1 and response['techniques'] == ['Naked Single']
    assert post(server, '/api/start', {'puzzle': puzzle, 'techniques': ['Unknown']})[0] == 400
    assert post(server, '/api/start', {'puzzle': puzzle, 'techniques': ['Unique Rectangle Type 1']})[0] == 400


def test_start_explains_unsatisfiable_image_clues(server):
    # These match the supplied colored-grid image, including all empty cells.
    # No duplicate givens exist, but the board has no completion.
    puzzle = '147000003250001000309000000080020004000410020900000600003000009400002000001008007'
    for techniques in [None, []]:
        status, response = post(server, '/api/start', {'puzzle': puzzle, 'techniques': techniques})
        assert status == 400
        assert 'no solution with the current clues' in response['error']
        assert not server.sessions


def test_image_api_validates_upload_and_does_not_start_session(server, monkeypatch):
    import base64
    import sudoku.vision
    seen = []

    def reader(data):
        seen.append(data)
        return {'puzzle': '0' * 81, 'cells': [], 'conflicts': []}

    monkeypatch.setattr(sudoku.vision, 'read_image', reader)
    image = base64.b64encode(b'image bytes' * 500).decode()
    status, data = post(server, '/api/image', {'image': image})
    assert status == 200 and data['puzzle'] == '0' * 81
    assert seen == [b'image bytes' * 500]
    assert not server.sessions
    for body in [{'image': '!!'}, {'image': 123}, {}]:
        assert post(server, '/api/image', body)[0] == 400
    assert request(server, 'POST', '/api/image', None, {
        'Content-Type': 'application/json', 'Origin': 'https://example.com'})[0] == 403
