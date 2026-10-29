"""Hosted WSGI application. Run with a single worker: sessions live in memory."""
import os
from importlib.resources import files
from urllib.parse import urlsplit

from flask import Flask, jsonify, request, Response
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from sudoku.app.service import SudokuService
from sudoku.app.techniques import catalog


def create_app(public_url=None):
    public_url = public_url or os.environ.get('PUBLIC_URL') or os.environ.get('RENDER_EXTERNAL_URL')
    if not public_url:
        raise ValueError('Set PUBLIC_URL to the website URL (or use RENDER_EXTERNAL_URL).')
    url = urlsplit(public_url)
    if url.scheme not in ('http', 'https') or not url.netloc or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment:
        raise ValueError('PUBLIC_URL must be an HTTP(S) origin without a path.')
    origin = f'{url.scheme}://{url.netloc}'
    app = Flask(__name__, static_folder=None)
    app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024
    service = SudokuService()

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.get('/healthz')
    def health():
        return jsonify(status='ok')

    @app.get('/')
    @app.get('/app.js')
    @app.get('/style.css')
    def asset():
        name, mime = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}[request.path]
        return Response(files('sudoku.app').joinpath('static', name).read_bytes(), mimetype=mime)

    @app.get('/api/techniques')
    def techniques():
        return jsonify(catalog())

    @app.post('/api/<operation>')
    def api(operation):
        # Compare against configured origin, never untrusted forwarded headers.
        if request.host != url.netloc or (request.headers.get('Origin') is not None and request.headers['Origin'] != origin):
            return jsonify(error='Use the application URL'), 403
        if request.mimetype != 'application/json':
            return jsonify(error='Expected JSON'), 415
        if operation not in ('start', 'action', 'image'):
            return jsonify(error='Not found'), 404
        limit = app.config['MAX_CONTENT_LENGTH'] if operation == 'image' else 4096
        request.max_content_length = limit
        try:
            body = request.get_json()
            if not isinstance(body, dict):
                raise ValueError('Expected a JSON object')
            status, payload = service.dispatch(request.path, body)
            return jsonify(payload), status
        except RequestEntityTooLarge:
            return jsonify(error=f'Request body must be at most {limit} bytes'), 413
        except (BadRequest, ValueError, TypeError) as exc:
            return jsonify(error=str(exc)), 400
        except Exception:
            app.logger.exception('Unexpected solver failure')
            return jsonify(error='The solver could not verify this step. Reload the puzzle to retry.'), 500

    return app
