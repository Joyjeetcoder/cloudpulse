# 4. Connect GitHub and demonstrate CloudPulse

## 4.1 Add the webhook to the test repository

Use the **test repository** (`YOUR_USERNAME/cloudpulse-test-app`) for this setup:

1. Open **Settings → Webhooks → Add webhook**.
2. Set **Payload URL** to Terraform's `webhook_url`, ending in `/webhook/github`.
3. Set **Content type** to `application/json`.
4. Set **Secret** to the exact value of `GITHUB_WEBHOOK_SECRET` in the server's environment file.
5. Keep SSL verification enabled.
6. Choose **Let me select individual events**, then select **Workflow runs**.
7. Leave **Active** selected and add the webhook.

GitHub sends a `ping`. Under **Recent deliveries**, its response should be HTTP 200 with `pong`. Completed workflow events should return HTTP 202. That 202 means the event is durably queued; analysis happens after the response.

If you accidentally select another event type, CloudPulse will acknowledge and ignore it. Configure **Workflow runs**, not just **Pushes**, **Check suites**, or **Workflow jobs**.

## 4.2 Generate your first successful run

In the test repository's **Actions** tab, select **CloudPulse Demo CI → Run workflow**. Choose `main` and scenario `success`.

Wait for the GitHub run to finish. CloudPulse should show:

- Outcome: **success**
- Analysis: **Not required**
- Correct repository, branch, commit, run number, and attempt

Gemini is not called for a successful run.

## 4.3 Generate real failures

Use **Run workflow** again and choose each scenario separately:

| Scenario | What actually fails | What the analysis should broadly identify |
|---|---|---|
| `test_failure` | pytest compares the actual total 250 with an intentionally wrong expected value 249 | A failing assertion in `test_order_total` |
| `missing_dependency` | Python imports a deliberately nonexistent module | `ModuleNotFoundError`; a missing module/import |
| `syntax_error` | Python compiles a deliberately invalid function definition | A `SyntaxError` in the demo module |
| `configuration_error` | Python reads an unset `CLOUDPULSE_DEMO_REQUIRED` environment variable | A missing required configuration value |

These are controlled test cases, not hardcoded analysis results. Gemini receives the actual generated logs. Its exact wording will vary, and it can be wrong.

The missing module is intentionally named `cloudpulse_deliberately_missing_package`. Do not blindly try to install a similarly named package from a public package index. For this demonstration, restore the `success` scenario to return the test repository to its healthy state.

When a failure appears in CloudPulse, open the row and check:

1. GitHub's failed conclusion is preserved.
2. The failed job/step matches GitHub.
3. The probable cause is consistent with the deliberate scenario.
4. Supporting evidence shows an actual excerpt line and its job/line number.
5. The suggested fix is appropriate and requires human review.
6. The GitHub link opens the correct workflow.

The app checks that Gemini's evidence IDs exist in the supplied excerpt. It does **not** prove that the explanation follows logically from those lines. If Gemini produces invalid evidence or says it lacks evidence, the app reports **Needs review** rather than presenting the unsupported explanation.

## 4.4 Demonstrate a push-triggered workflow

Manual selection makes rehearsal easy. The workflow also runs on pushes and pull requests, as proposed in the synopsis.

To demonstrate a deliberate failure caused by a push, change `scenario.txt` in the test repository to:

```text
test_failure
```

Then, from the `cloudpulse-test-app` folder:

```powershell
git add scenario.txt
git commit -m "Demonstrate assertion failure for CloudPulse"
git push
```

Show GitHub Actions starting, failing, and then appearing in CloudPulse. For a passing follow-up, put `success` back in `scenario.txt`, commit, and push again. The two commits produce distinct genuine workflow runs.

## 4.5 Show reliability features

### Duplicate delivery

Open the test repository's webhook → **Recent deliveries** → a completed workflow event → **Redeliver**. The response should say `duplicate`; the dashboard should retain one record for that run attempt. A new **GitHub rerun** is different: its `run_attempt` increases, so it should produce a separate record.

### Missed webhook

GitHub does not guarantee automatic redelivery for every failed delivery. If the VM was stopped or a webhook was misconfigured, use **Recent deliveries → Redeliver**, or CloudPulse's **Import a run** with the completed run URL. Import retrieves the latest attempt through the real GitHub API.

### Provider error

A missing/invalid Gemini key, quota exhaustion, or invalid model should produce an analysis error while preserving the failed GitHub conclusion. Fix the server configuration, recreate the container, and click **Analyze again**. A temporary GitHub/Gemini error is retried up to `MAX_ANALYSIS_ATTEMPTS` (3 by default), after 30 and then 60 seconds. Invalid credentials and invalid JSON are not repeatedly retried automatically.

### Persistence

Restart the app container, refresh the dashboard, and check that records remain:

```bash
sudo docker restart cloudpulse-app
```

If processing was interrupted, its record returns to the queue on startup. This recovery assumes exactly one active application process.

## 4.6 Demonstrate CloudPulse's own CI/CD

In the **application** repository, make a small README change, commit it, and push to `main`. Show its **CloudPulse CI and Deploy** workflow:

1. Backend checks and frontend build.
2. Docker image publication to GHCR.
3. OIDC login to Azure.
4. VM deployment with a health check and success marker.

Then refresh the hosted dashboard. Its existing database remains present. The default repository allowlist monitors only the test app; CloudPulse's own pipeline can be demonstrated in GitHub without ingesting it. Monitoring it as well requires adding it to `GITHUB_REPOSITORIES`, updating token permissions, and adding a second webhook.

## Acceptance checklist — complete with your accounts

| Check | Your result |
|---|---|
| Application CI checks and image build pass | |
| Public HTTPS dashboard opens | |
| Wrong dashboard token is rejected | |
| Webhook ping returns 200 | |
| Completed event returns 202 | |
| Successful run appears with no LLM analysis | |
| Test failure produces appropriate cause and supporting line | |
| Dependency failure produces appropriate cause and supporting line | |
| Syntax failure produces appropriate cause and supporting line | |
| Configuration failure produces appropriate cause and supporting line | |
| Duplicate redelivery does not create another record | |
| A GitHub rerun is stored as another attempt | |
| Records survive container restart | |
| A provider problem preserves the original build status | |
| Automatic deployment from application `main` succeeds, if enabled | |

Do not claim a check passed until you actually observe it. Keep screenshots and the corresponding GitHub run URLs for your report.

## Honest presentation wording

Once your checks pass, describe this as:

> CloudPulse is an Azure-deployed prototype that monitors completed GitHub Actions workflows and uses Gemini to produce probable failure explanations linked to actual log lines. It includes a React dashboard, persistent run history, Docker packaging, Terraform infrastructure, and a GitHub Actions deployment pipeline.

Only include “deployment pipeline” in that description if the deployment job actually works in your account. Failure prediction, fine-tuning, notification services, and autonomous repair are deferred. Infrastructure is reproducible with Terraform, but account login, credentials, GitHub webhook setup, and initial configuration remain manual bootstrap steps.
