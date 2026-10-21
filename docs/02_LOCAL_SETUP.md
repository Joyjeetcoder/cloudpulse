# 2. Optional laptop setup

These are instructions for you to execute. The app was not run locally during preparation.

## Option A: Docker Desktop

Start Docker Desktop in Linux-container mode. From the `cloudpulse` repository root, configure `.env` as described in guide 1, then run:

```powershell
docker compose up --build -d
docker compose logs --tail 60 cloudpulse
```

Open <http://localhost:8000>. Enter the value of `DASHBOARD_TOKEN` from your `.env`.

The database and redacted logs live in a Docker named volume, so they persist across ordinary container restarts. The local port is bound to `127.0.0.1` and is not exposed to your network.

Stop without deleting data:

```powershell
docker compose down
```

After changing `.env`, recreate the container to apply the changed environment:

```powershell
docker compose up -d --force-recreate
```

`docker compose down -v` deletes the data volume. Use it only if you want a completely empty dashboard.

## Option B: Python and Node directly

Use Python 3.12 and Node.js 22. From the `cloudpulse` repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
cd frontend
npm install
npm run build
cd ..
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000 --workers 1 --env-file .env
```

The `.env.example` paths assume commands run from this repository root. Open <http://localhost:8000>. SQLite lives in `cloudpulse/data`, and the built dashboard lives in `cloudpulse/frontend/dist`.

On macOS/Linux, use `python3 -m venv .venv` and `.venv/bin/python` instead of the Windows paths.

If you want frontend hot reload, keep the backend running, open another terminal, and run `npm run dev` inside `frontend`. Open the Vite URL it prints (normally <http://localhost:5173>). The configured Vite proxy sends `/api` requests to the backend on port 8000.

Your first `npm install` creates `frontend/package-lock.json`. Commit it so later Docker and CI builds use `npm ci`.

## Use real data before configuring a webhook

You can verify your keys without a tunnel:

1. Run a workflow in your public test repository and wait until it completes.
2. Copy its URL, such as `https://github.com/YOU/cloudpulse-test-app/actions/runs/123456789`.
3. Open CloudPulse → **Import a run**.
4. Select the test repository, paste the URL, and import it.
5. For a failure, watch the analysis status become Ready, Needs review, or Analysis failed.

Import calls the real GitHub API. It is also the recovery path when a webhook was missed. It imports the latest attempt of the selected run and does not reset an existing completed record.

## Receive automatic GitHub events

GitHub cannot call `http://localhost:8000`. For an automatic end-to-end demo, use the Azure deployment in the next guide. If you already use a trusted HTTPS tunnel, point it at port 8000 and configure its public URL plus `/webhook/github` in GitHub. If that public URL changes, update the GitHub webhook.

## Run the included checks yourself

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
cd backend
..\.venv\Scripts\python.exe -m pytest -q
cd ..
```

These tests do not need your Gemini/GitHub keys or call those providers. CI runs them separately using temporary configuration.
