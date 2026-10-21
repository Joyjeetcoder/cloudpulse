# CloudPulse

**Explain failed GitHub Actions workflows with evidence from their logs.**

CloudPulse receives a signed workflow-completion webhook, retrieves failed-job logs, extracts a bounded excerpt, asks Gemini for a probable explanation, and displays the result in a React dashboard. Every cited line is checked against the excerpt sent to Gemini. This checks the location of the evidence; a human still needs to assess whether the diagnosis is correct.

## What is included

- Signed GitHub `workflow_run` webhooks and a configured repository allowlist.
- Workflow history with separate records for rerun attempts.
- A SQLite-backed work queue, automatic retries for transient provider failures, and restart recovery.
- GitHub API metadata, failed job/step information, and bounded log downloads.
- Best-effort log redaction and source line references.
- Gemini structured JSON output, schema validation, and an inconclusive state for unsupported explanations.
- A React dashboard with status, probable cause, exact supporting lines, suggested fix, and a GitHub link.
- Authenticated dashboard APIs, manual import of completed runs, and manual analysis retry.
- Docker, an Azure VM Terraform configuration, automatic HTTPS, and a GitHub Actions build/deploy workflow.
- A separate companion repository with repeatable real CI failures.

## Setup guides

| Step | Guide |
|---|---|
| 1 | [Accounts and repositories](docs/01_ACCOUNTS_AND_REPOSITORIES.md) |
| 2, optional | [Run on your laptop](docs/02_LOCAL_SETUP.md) |
| 3 | [Azure provisioning and deployment](docs/03_AZURE.md) |
| 4 | [Webhook setup, demonstration, and acceptance checklist](docs/04_DEMO.md) |
| Reference | [Troubleshooting](docs/05_TROUBLESHOOTING.md) |
| Explanation | [Architecture, API, and limitations](docs/06_ARCHITECTURE.md) |

Use the Azure route if your priority is an internet-accessible demonstration without a laptop tunnel.

## Repository layout

| Path | Contents |
|---|---|
| `backend/app/` | FastAPI API, SQLite queue, GitHub client, excerpt extraction, Gemini client |
| `backend/tests/` | Focused checks for authentication, duplicate handling, queue recovery, and evidence validation |
| `frontend/` | React dashboard and Vite build |
| `infra/terraform/` | Azure VM, network, public hostname, restricted SSH, optional GitHub OIDC identity |
| `deploy/` | HTTPS proxy setup and image deployment/rollback scripts |
| `.github/workflows/cloudpulse.yml` | CI, container publishing, and optional Azure deployment |
| `.env.example` | Configuration template; copy to private `.env` |
| `scripts/make_secrets.py` | Generates separate webhook and dashboard secrets on your computer |

## Quick local command, after configuring `.env`

```powershell
docker compose up --build -d
```

Open `http://localhost:8000` and enter `DASHBOARD_TOKEN`. To receive GitHub webhooks, use the Azure deployment or a public HTTPS tunnel you control; GitHub cannot call your laptop's `localhost` address.

## Important operational boundaries

- Run **one application container with one Uvicorn worker**. The queue design assumes a single active worker process.
- Keep the SQLite database on a local disk or Docker volume, not an Azure Files/SMB/NFS share.
- GitHub's workflow conclusion and CloudPulse's analysis state are stored separately. A Gemini failure never changes a GitHub build from failed to successful.
- Automatic retries can repeat a paid Gemini request if a response is lost or the process stops after generation. Request processing is recoverable, but provider billing is not exactly-once.
- The app examines completed runs. It does not stream running build logs or predict future failures.
- Retry/import endpoints require the dashboard token. The public repository does not make your private keys public.

## Verification status

This delivery was **not executed locally**. No credentialed API call, browser run, package installation, Docker build, or Terraform plan/apply was performed during preparation. The included tests are for you and GitHub Actions to run. Follow the demo checklist before presenting the application as working.

Direct dependency versions are specified. A frontend lockfile is intentionally not fabricated: your first `npm install` creates `package-lock.json`; commit that file afterward to improve repeatability. The Dockerfile and CI use `npm ci` once a lockfile exists.

## Cost

Gemini API charges or quotas belong to your Google project. Azure credits cover eligible Azure infrastructure, not Gemini calls. VM compute, its disk, and its public IP can incur charges. Verify your subscription, region, quota, and displayed price before applying Terraform; use the cleanup instructions after the demo.
