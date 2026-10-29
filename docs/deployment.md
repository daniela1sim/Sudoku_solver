# Free Render deployment

The repository includes a `render.yaml` Blueprint for one **Free** Python web
service, including image recognition. No database or paid service is requested.

1. Push these files to GitHub.
2. Sign in at https://dashboard.render.com and choose **New > Blueprint**.
3. Connect the repository and select the branch containing `render.yaml`.
4. Confirm that the service plan is **Free**, then deploy.
5. Open the HTTPS URL Render provides. Test puzzle entry, hints, replay and an
   image upload. `/healthz` returns `{"status":"ok"}` when the app is running.

Render supplies `PORT` and `RENDER_EXTERNAL_URL` automatically. For a custom
domain set `PUBLIC_URL` to its exact HTTPS origin, without a path. POST requests
must match this configured host and origin. Forwarded host headers are not trusted.

Build: `pip install ".[web,vision]"`

Start: `gunicorn 'sudoku.app.web:create_app()' --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 120 --access-logfile -`

Keep **one worker**: up to 32 replay sessions are held in that process's memory.
Sessions expire on restart, deployment, free-service sleep, or eviction by newer
sessions. Users can reload their puzzle. This is a small demo configuration;
shared persistent session storage and workload controls are needed before scaling.
Long computations can exceed the worker timeout and reset sessions.

Free services sleep after 15 idle minutes and may take about a minute to wake.
Usage limits apply. Without a payment method, Render suspends services or builds
rather than charging for overages. See https://render.com/docs/free.

Uploaded images are processed in server memory and are not saved. The deployed
Linux environment's available fonts can affect recognition; always review results.

## Local verification

Install `pip install ".[web,dev,vision]"`, then run `python -m pytest tests/app -q`.
The original `python -m sudoku.app` local server remains available.
Gunicorn runs on Linux (including Render), not native Windows.
