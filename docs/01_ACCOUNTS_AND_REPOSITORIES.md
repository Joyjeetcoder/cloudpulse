# 1. Accounts, keys, and repositories

This guide uses Windows PowerShell examples because that matches your current setup. The Git commands also work on macOS/Linux. Replace all uppercase placeholders before running commands.

## 1.1 Install the tools

For the recommended Azure route:

- [Git](https://git-scm.com/downloads)
- [Python 3.12](https://www.python.org/downloads/) to generate secrets and optionally run locally
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli-windows)
- [Terraform](https://developer.hashicorp.com/terraform/install), version 1.6 or later, below 2
- Windows OpenSSH client (`ssh`, `scp`, and `ssh-keygen`)

For the optional laptop route, also install [Docker Desktop](https://www.docker.com/products/docker-desktop/), or Node.js 22 if running Python and React directly. The cloud build uses GitHub's runners, so a local Docker installation is not required for the Azure route.

Extract the ZIP into a normal writable folder, such as `C:\Projects\CloudPulse-Part1`. In PowerShell, navigate to its `cloudpulse` folder:

```powershell
cd C:\Projects\CloudPulse-Part1\cloudpulse
```

Use your actual extraction path if different.

## 1.2 Create the two public repositories

At <https://github.com/new>, create these empty public repositories:

1. `cloudpulse`
2. `cloudpulse-test-app`

Leave GitHub's options to initialize a README, license, and `.gitignore` unchecked: these folders already contain their initial files. Do not upload the ZIP itself. Git is recommended because it preserves the `.github` directories.

Push the application:

```powershell
cd C:\Projects\CloudPulse-Part1\cloudpulse
git init
git add .
git commit -m "Add CloudPulse Part 1 with Gemini and Azure deployment"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/cloudpulse.git
git push -u origin main
```

If Git asks you to configure your author name/email, follow its instructions using your own details. Authenticate using Git Credential Manager's browser flow; do not put a personal access token in the remote URL.

Push the test app:

```powershell
cd ..\cloudpulse-test-app
git init
git add .
git commit -m "Add reproducible CloudPulse demo workflows"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/cloudpulse-test-app.git
git push -u origin main
```

In each GitHub repository, open **Actions** and allow workflows if GitHub requests it. The test repository's first workflow should pass. The CloudPulse repository runs checks and builds an image; Azure deployment is skipped until its variables are configured later. Because this package was not executed during preparation, resolve any CI error before progressing.

**Check the repository root:** you should directly see `backend`, `frontend`, `Dockerfile`, and `.github` in the application repository. In the test repository, directly see `app.py`, `scenario.txt`, and `.github`.

## 1.3 Create a Gemini API key

1. Open <https://aistudio.google.com/apikey> and sign in to your Google account.
2. Create or choose a project and generate a Gemini API key.
3. Check the project's available models and quota. The supplied default is `gemini-3.8-flash`, matching Google's documentation at package preparation time. If that model is not enabled in your project, set `GEMINI_MODEL` to an available text model supporting structured output.
4. Keep the key private. It goes in the backend's `.env`, never in React code or a public repository.

Google changes model availability, free-tier access, and quota by account/model. See [API key setup](https://ai.google.dev/gemini-api/docs/api-key) and [pricing](https://ai.google.dev/gemini-api/docs/pricing). No OpenAI key is needed. A Gemini chat subscription is not a substitute for a Developer API key.

The backend uses Gemini's `generateContent` REST endpoint with JSON-schema output (`generationConfig.responseFormat`). No Google SDK installation or model training is required. The exact model is configurable in one environment variable.

## 1.4 Create a GitHub token for log downloads

In GitHub, open **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.

- Give it a recognizable name, such as `cloudpulse-read-actions`.
- Set a short expiry that covers your demo.
- Choose your account as the resource owner.
- Under repository access, select your **test repository**. Select **Actions: Read-only** under repository permissions. Metadata read access is automatic.
- Generate and copy it once into your private `.env`.

GitHub may show only a public-repository option for certain account/access combinations. Use a token that can read Actions metadata and logs for your selected public test repository. The app still enforces its own configured repository allowlist.

This token lets CloudPulse read logs. It is different from the webhook secret, the dashboard token, and GitHub Actions' automatically supplied `GITHUB_TOKEN`.

## 1.5 Configure `.env`

From the `cloudpulse` folder:

```powershell
Copy-Item .env.example .env
python scripts/make_secrets.py
notepad .env
```

If Windows uses `py` instead of `python`, run `py -3.12 scripts/make_secrets.py`.

Copy the generated values into the corresponding two lines. Then set:

```dotenv
GITHUB_WEBHOOK_SECRET=YOUR_FIRST_GENERATED_SECRET
DASHBOARD_TOKEN=YOUR_SECOND_GENERATED_SECRET
GITHUB_TOKEN=YOUR_FINE_GRAINED_GITHUB_TOKEN
GITHUB_REPOSITORIES=YOUR_USERNAME/cloudpulse-test-app
GEMINI_API_KEY=YOUR_AI_STUDIO_API_KEY
GEMINI_MODEL=gemini-3.8-flash
```

Leave the remaining defaults initially. Use plain `KEY=value` lines without surrounding quotes, spaces around `=`, or shell commands. The generated secrets are safe for this format. Do not use the same value for the two generated secrets.

| Setting | Used for |
|---|---|
| `GITHUB_WEBHOOK_SECRET` | Proves a webhook was signed with the secret you configured in GitHub |
| `DASHBOARD_TOKEN` | Opens the dashboard and authorizes its API requests |
| `GITHUB_TOKEN` | Reads the selected repository's Actions information and logs |
| `GEMINI_API_KEY` | Calls Gemini to analyze an excerpt |
| `GITHUB_REPOSITORIES` | Restricts monitored repositories; comma-separated if expanded later |

Before later commits, run `git status`. `.env`, data files, private keys, and Terraform state are ignored. The example files contain placeholders and can be public. If you accidentally commit a real key, revoke it and generate another; simply deleting it from the latest commit does not revoke it.

## 1.6 Confirm Azure access

Open <https://portal.azure.com>, then **Subscriptions**. Confirm:

- Your subscription is active and the credit balance really is available.
- You may create a Linux VM, a public IP, and network resources in a permitted region.
- For automatic deployment, you may create a user-assigned managed identity and assign a role scoped to your VM. Subscription Owner or an appropriate RBAC administrator can do the role assignment. Ordinary Contributor access alone may not.

The next guide provides a manual-deployment fallback if your college blocks identity or role assignment creation. Do not assume every VM SKU is available just because you have credit.

**Next:** [Deploy to Azure](03_AZURE.md), or [run locally](02_LOCAL_SETUP.md) first if you prefer.
