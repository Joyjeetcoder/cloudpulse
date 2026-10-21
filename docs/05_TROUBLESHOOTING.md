# 5. Troubleshooting

Start with the error shown in the dashboard or GitHub Actions. Do not paste API keys, `.env` contents, or raw secret-bearing logs into a public issue. If asking for help, share the error text and relevant sanitized lines.

## Nothing appears in the dashboard

1. Confirm the workflow is **completed**.
2. In the test repository, check **Settings → Webhooks → Recent deliveries**.
3. Verify the event is `workflow_run`, action `completed`, and the URL ends in `/webhook/github`.
4. Verify `GITHUB_REPOSITORIES` contains the exact `owner/test-repo` (the application normalizes case).
5. If the webhook was added after the workflow finished, use **Import a run** or start a new workflow.

| Symptom | Meaning and next step |
|---|---|
| Webhook 401 | The secret in GitHub differs from `GITHUB_WEBHOOK_SECRET`. Set both to the same generated value and recreate the app container. |
| Webhook 403 | The source repository is outside the allowlist. Correct `GITHUB_REPOSITORIES`. |
| Webhook 404 | Wrong URL/path, proxy target, or server. Use Terraform's exact webhook URL. |
| Webhook timeout/502 | The VM/app may be stopped or still starting. Check `docker ps`, cloud-init, and proxy logs. |
| Event acknowledged as ignored | Wrong event/action; select Workflow runs and wait until completed. |
| Duplicate | The run attempt is already stored. Use Analyze again for analysis retry, or rerun the workflow in GitHub for a new attempt. |

## Analysis fails

| Message/problem | Check |
|---|---|
| GitHub rejected access | Fine-grained PAT, expiry, correct repository owner, and Actions read permission. Public visibility does not eliminate every log API permission requirement. |
| GitHub run/log not available | Logs may not yet be ready, may have expired, or may be inaccessible. Let automatic retries finish; open the failed job on GitHub and confirm logs exist. |
| Gemini 400/401/403 | Correct API key, Gemini API restrictions, Google project eligibility/billing, and supported request/model. |
| Gemini 404 | `GEMINI_MODEL` is unavailable to your project or no longer exists. Choose an enabled text model supporting structured output. |
| Gemini quota/rate limit | Check AI Studio quotas for that model/project. Wait, reduce repeated test runs, or enable eligible paid usage if you choose. Azure credit does not pay this bill. |
| Gemini did not finish | Output limit or provider filtering. You can raise `GEMINI_MAX_OUTPUT_TOKENS` up to 8192, at a possible cost increase, or choose a suitable model. |
| Invalid/empty analysis | The response did not match the required schema. It is not shown as a completed explanation. Retry once or review model support. |
| Needs review | The model reported insufficient evidence, cited a missing line, or the failure had no usable failed-job logs. Inspect the original workflow. |
| Analysis sits in Queued | Transient retries wait 30/60 seconds. Check health and app logs if it does not progress. One worker processes one run at a time. |
| Job log too large | Downloads are bounded. The excerpt might miss the final error. Increase the configured size within its supported limit or inspect GitHub manually. |

The provided Gemini client follows the REST documentation as of preparation and uses `generationConfig.responseFormat.text`. If Google changes the API or your chosen model requires another schema field, adapt `backend/app/gemini.py` to its current official documentation. Do not replace API errors with fabricated analysis.

The backend stores API errors as safe messages and logs error types, not provider response bodies or credentials. For a full provider error, reproduce the smallest non-sensitive request in your provider's own tools.

## Cannot open the Azure dashboard

- Use the DNS hostname, not the bare public IP, for the configured HTTPS site.
- Verify the VM is running, NSG rules allow TCP 80/443, and the DNS name resolves to its public IP.
- Check the proxy: `sudo docker logs --tail 60 cloudpulse-proxy`.
- Certificate issuance needs public DNS and network reachability. Avoid repeatedly deleting the proxy's certificate data volume; certificate issuers have rate limits.
- Check app health: `sudo docker inspect --format '{{.State.Health.Status}}' cloudpulse-app`.
- The app is intentionally not published on VM port 8000. Use the HTTPS proxy.

## Cannot SSH to the VM

Your public IP may have changed since the Terraform apply. Update `ssh_allowed_cidr` to the new IPv4 `/32`, review `terraform plan`, and apply it. Do not open SSH to all addresses just to bypass this check. Use the private SSH key corresponding to the public key supplied to Terraform.

## Terraform fails

- `az login`, then `az account set --subscription ...` for the correct subscription.
- Confirm `subscription_id` in `terraform.tfvars` matches.
- Register Microsoft.Compute, Microsoft.Network, and Microsoft.ManagedIdentity as described in guide 3.
- **RequestDisallowedByPolicy**: choose a permitted region/resource, or ask the subscription administrator.
- **SkuNotAvailable / quota**: choose a permitted size with enough RAM or request quota.
- **AuthorizationFailed on roleAssignments**: your account lacks RBAC assignment rights. Ask an authorized administrator, or set `enable_github_deploy=false` and use manual deployments.
- Never delete state to “fix” an error. Refresh/review the plan against the resources already created.

## GitHub image/deployment fails

| Problem | Fix |
|---|---|
| `verify` fails | Open that job's first failing step. Correct the source/dependency issue; do not bypass the checks. |
| GHCR publish denied | Check Actions package-write permissions and whether an older package is owned/linked differently. The workflow's package job requests `packages: write`. |
| VM image pull denied | Make the GHCR container package public. The repository being public is not sufficient. |
| Deploy job skipped | `AZURE_CLIENT_ID` is missing, or the run is not for `main`. |
| OIDC “no matching federated identity” | Exact repository casing/name and `main` subject must match Terraform. Variables must point to the intended managed identity and tenant. |
| Azure Run Command denied | Check VM-scoped role assignment and propagation. `AZURE_RESOURCE_GROUP` and `AZURE_VM_NAME` must match Terraform outputs. |
| Missing app.env | Complete the initial SSH/environment-file setup. CI does not upload application secrets. |
| New app unhealthy | Inspect `sudo docker logs --tail 80 cloudpulse-app`. Generate valid distinct secrets and verify permissions on `/var/lib/cloudpulse`. |

The VM deployment role is intentionally powerful on this single VM because it runs the deployment script. It is scoped to the project VM, not the whole subscription. No SSH access from changing GitHub runner IPs is required for the automatic path.

## Data appears empty after restart/deployment

- Azure: check that `/var/lib/cloudpulse/cloudpulse.db` exists and is mounted at `/data` in the container.
- Local Docker: check you are using the same Compose project/directory and did not remove its named volume.
- Direct Python: run from the same repository root, or set an absolute `DATA_DIR`.
- If the VM was replaced or Terraform destroyed its OS disk, restore your backup. The app does not provide managed database replication or automatic backups.

## Reset a forgotten dashboard token

Generate a new token on your computer with `scripts/make_secrets.py`, update only `DASHBOARD_TOKEN` in the server environment, recreate the app container, and log in again. Changing `GITHUB_WEBHOOK_SECRET` requires also changing the secret in GitHub.
