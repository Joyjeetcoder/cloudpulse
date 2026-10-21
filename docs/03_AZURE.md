# 3. Deploy CloudPulse to Azure

## What this creates

One small Ubuntu VM runs the application container and a Caddy HTTPS proxy. SQLite and sanitized logs persist at `/var/lib/cloudpulse` on the VM's managed OS disk. Terraform also creates a resource group, network, subnet, network security group, public IP, and an Azure DNS hostname. Automatic deployment optionally adds a managed identity with GitHub OIDC trust and a role scoped to this VM.

This uses a VM instead of the previously suggested App Service because SQLite relies on local file locking. Microsoft advises against placing SQLite on App Service storage mounts. You still get HTTPS without buying a domain: Terraform gives the public IP an Azure hostname, and Caddy requests a certificate for it.

**Before applying:** check your actual Azure credit balance, subscription restrictions, permitted regions, and the selected VM's displayed price. The default `Standard_B1ms` is a small starting point, not a guarantee of availability or free usage. Builds run on GitHub, not on this small VM. Use a permitted equivalent with at least 2 GB RAM if necessary. A disk and static public IP also have their own charges.

Set a budget notification in Azure **Cost Management → Budgets**. A notification is not a hard spending cap. The app does not automatically shut down your resources.

## 3.1 Let GitHub build your image first

After pushing the `cloudpulse` repository:

1. Open its **Actions** tab and the **CloudPulse CI and Deploy** workflow.
2. Wait for `verify` and `package` to pass. The `deploy` job will be skipped because the Azure repository variables are not set yet.
3. Open the workflow run's **Summary**. Copy the immutable image address printed by the package job. It looks like:

   `ghcr.io/yourusername/cloudpulse@sha256:64_HEXADECIMAL_CHARACTERS`

4. Open your GitHub profile → **Packages** → the `cloudpulse` container package → **Package settings** → **Change visibility** → **Public**. A public repository does not always make a newly published GHCR package public automatically.

The VM pulls this image anonymously. If you leave the package private, deployment will fail with a registry access error. Public images must never contain keys; the Docker build excludes environment files and data.

If CI fails, fix that error first using its log and [troubleshooting](05_TROUBLESHOOTING.md). The source was not run during package preparation.

## 3.2 Sign in to Azure from PowerShell

```powershell
az login
az account list --query "[].{Name:name,ID:id,State:state}" -o table
az account set --subscription "YOUR-SUBSCRIPTION-ID"
```

If browser login is blocked, use `az login --use-device-code`.

Register the resource providers this project actually uses:

```powershell
az provider register --namespace Microsoft.Compute --wait
az provider register --namespace Microsoft.Network --wait
az provider register --namespace Microsoft.ManagedIdentity --wait
```

If your subscription forbids registration or creating these resources, use an already permitted subscription or ask its administrator. Do not bypass college subscription restrictions.

## 3.3 Create an SSH key and prepare Terraform

Generate a dedicated SSH key if you do not already have one for this project. Do not overwrite an existing key at this path:

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\cloudpulse_azure" -C "cloudpulse-azure"
Get-Content "$env:USERPROFILE\.ssh\cloudpulse_azure.pub"
```

Keep the private file private. The `.pub` file is the one Terraform needs. A passphrase is fine; you will type it when connecting from your computer.

Find your current public IPv4 address (for example, from your router or a browser search for “my public IP”). It is not your laptop's `192.168.x.x` address. Append `/32` for the SSH rule.

From the `cloudpulse` root:

```powershell
cd infra\terraform
Copy-Item terraform.tfvars.example terraform.tfvars
notepad terraform.tfvars
```

Fill in all placeholders. Example shape, not values to copy verbatim:

```hcl
subscription_id      = "YOUR-AZURE-SUBSCRIPTION-ID"
location             = "centralindia"
project_name         = "cloudpulse"
vm_size              = "Standard_B1ms"
admin_username       = "cloudpulseadmin"
ssh_public_key       = "ssh-ed25519 YOUR-PUBLIC-KEY-CONTENTS cloudpulse-azure"
ssh_allowed_cidr     = "YOUR-PUBLIC-IP/32"
enable_github_deploy = true
github_repository   = "YOUR_USERNAME/cloudpulse"
```

`github_repository` must be the **application repository**, with the exact owner/name casing, not `cloudpulse-test-app`. Its `main` branch is the only GitHub identity allowed to deploy.

If you cannot create managed identities or role assignments, set `enable_github_deploy = false`. The application still works with manual deployments; you should accurately report that its deployment is manual until OIDC is enabled.

## 3.4 Provision resources

```powershell
terraform init
terraform plan
terraform apply
terraform output
```

Review the plan and Azure pricing before answering Terraform's prompt. Save the outputs for the next steps. Keep the `.tfstate` files privately on your computer; do not commit them. Terraform creates its provider lockfile during `init`; commit `.terraform.lock.hcl` for reproducible provider selection.

The key outputs are:

| Output | Purpose |
|---|---|
| `hostname` | Azure DNS hostname to use for SSH and HTTPS |
| `dashboard_url` | Browser URL |
| `webhook_url` | Paste into the test repository's webhook |
| `resource_group`, `vm_name` | Azure operations and GitHub deployment variables |
| `github_azure_client_id`, `azure_tenant_id`, `azure_subscription_id` | OIDC configuration in GitHub |

An Azure **RequestDisallowedByPolicy**, **SkuNotAvailable**, or quota error means you must use a region/size permitted by your subscription. Change `location` or `vm_size`, then review and reapply the plan. Do not create several duplicate VMs while troubleshooting.

Cloud-init takes a few minutes to install Docker and start the proxy after Terraform returns. HTTPS may initially show a connection error or 502 until the app is deployed.

## 3.5 Put your private environment file on the VM

Return to the application repository root:

```powershell
cd ..\..
$CloudPulseHost = "PASTE-THE-HOSTNAME-OUTPUT-HERE"
scp -i "$env:USERPROFILE\.ssh\cloudpulse_azure" .env "cloudpulseadmin@${CloudPulseHost}:cloudpulse.env"
ssh -i "$env:USERPROFILE\.ssh\cloudpulse_azure" "cloudpulseadmin@$CloudPulseHost"
```

On the first SSH connection, compare the host fingerprint with the VM's fingerprint before accepting it. You can obtain the VM's public host-key fingerprint through Azure Portal → VM → **Run command** → `RunShellScript`:

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Once connected, the following commands run **inside the Azure VM**, not PowerShell:

```bash
sudo cloud-init status --wait
sudo install -o root -g root -m 600 ~/cloudpulse.env /opt/cloudpulse/app.env
rm ~/cloudpulse.env
```

The generated application secrets are private to this VM. The deployment script overrides `DATA_DIR` and `FRONTEND_DIR`, so the local path values in `.env` need no manual changes.

If cloud-init reports an error, inspect `sudo tail -n 80 /var/log/cloud-init-output.log`. After resolving a transient Docker download/network error, you can rerun `sudo bash /opt/cloudpulse/bootstrap.sh YOUR_AZURE_HOSTNAME`.

## 3.6 Perform the first deployment

Still inside the VM, paste the immutable image address from the GitHub Actions summary:

```bash
sudo bash /opt/cloudpulse/deploy.sh ghcr.io/YOUR_LOWERCASE_USERNAME/cloudpulse@sha256:YOUR_ACTUAL_DIGEST
```

Use the exact lowercase image address printed by the workflow, not the uppercase placeholder shown here. The script requires a real 64-character SHA256 digest. It pulls the image before replacing the current container, waits for application health, and restores the previous image if the new container fails to start. On the very first deployment there is no previous image to restore.

A successful deployment prints `CLOUDPULSE_DEPLOY_OK` followed by the image address. Check:

```bash
sudo docker ps
sudo docker logs --tail 50 cloudpulse-app
sudo docker logs --tail 50 cloudpulse-proxy
```

Open the `dashboard_url` from Terraform in your browser. Enter `DASHBOARD_TOKEN` from your private `.env`. You should see an empty dashboard and your configured test repository.

Check `https://YOUR_AZURE_HOSTNAME/healthz` for `{"status":"ok"}`. This verifies the server and worker are running; it does not verify GitHub or Gemini credentials. Those are verified through the real demonstration in guide 4.

Leave TCP ports 80 and 443 open for Caddy's certificate issuance and renewal. SSH remains restricted to your `/32` address. The application port 8000 is accessible only inside Docker's network on the VM.

## 3.7 Enable automatic deployment from GitHub

If `enable_github_deploy = true` successfully applied, Terraform created a **user-assigned managed identity** and a federated trust for the application repo's `main` branch. The identity can invoke commands on this VM through the VM-scoped role. It is not attached to the application container. No permanent Azure password is put in GitHub.

Open the application repository → **Settings → Secrets and variables → Actions → Variables**. Add these **repository variables**:

| GitHub variable | Terraform output |
|---|---|
| `AZURE_CLIENT_ID` | `github_azure_client_id` |
| `AZURE_TENANT_ID` | `azure_tenant_id` |
| `AZURE_SUBSCRIPTION_ID` | `azure_subscription_id` |
| `AZURE_RESOURCE_GROUP` | `resource_group` |
| `AZURE_VM_NAME` | `vm_name` |

These IDs/names are configuration values; your Gemini/GitHub application secrets remain on the VM. In **Actions**, open **CloudPulse CI and Deploy → Run workflow → main**. It will:

1. Run backend checks and build the dashboard.
2. Build and publish a Docker image to GHCR.
3. Obtain a short-lived Azure identity using OIDC.
4. Ask Azure Run Command to deploy that immutable image on your VM.
5. Require the success marker from the VM's deployment script.

Later pushes to `main` repeat this path automatically. Pull requests run verification only. Protect your application's `main` branch and review changes to deployment workflows: anyone who can change trusted main-branch code can control the demo VM.

OIDC/role changes can take several minutes to propagate. If your institution blocks managed identities or role assignments, use manual deployment from section 3.6 each time you publish an updated image, and defer the automatic-deployment claim until your administrator enables it.

## 3.8 Change secrets or configuration

Inside the VM:

```bash
sudo nano /opt/cloudpulse/app.env
sudo bash /opt/cloudpulse/deploy.sh "$(sudo cat /opt/cloudpulse/current-image)"
```

This recreates the container with the new values. A plain `docker restart` does not reload an env-file into an existing container. If you change the webhook secret, also update it in the test repository's webhook settings. Retry previously failed analyses from the dashboard after correcting credentials.

Backend/frontend changes deploy through the image pipeline. Changes to `deploy/*.sh` need to be copied into `/opt/cloudpulse` separately, or applied through a carefully reviewed infrastructure update. Changing Terraform `custom_data` may replace the VM and its OS disk; take a backup first. Ordinary application deployments do not run `terraform apply`.

## 3.9 Pause or clean up after the demo

On your computer, deallocate the VM to stop compute billing while keeping its disk:

```powershell
az vm deallocate --resource-group "YOUR_RESOURCE_GROUP" --name "YOUR_VM_NAME"
```

The app becomes unavailable. Storage and public-IP charges may continue. Restart later with `az vm start` using the same resource group/name; Docker's restart policy brings the containers back.

For complete cleanup, first back up any data you want to keep, then from `infra/terraform`:

```powershell
terraform plan -destroy
terraform destroy
```

**Destroy removes this project's resources and the VM disk containing its database/logs.** It does not remove your GitHub repositories or Google API key. Review the listed resources before confirming.

To make a consistent data backup before deletion, run inside the VM:

```bash
sudo docker stop cloudpulse-app
sudo tar -C /var/lib -czf /opt/cloudpulse/data-backup.tgz cloudpulse
sudo docker start cloudpulse-app
sudo install -o cloudpulseadmin -g cloudpulseadmin -m 600 /opt/cloudpulse/data-backup.tgz /home/cloudpulseadmin/data-backup.tgz
```

Then download it using `scp` to a private location on your computer. It contains project logs and metadata; do not commit it to your public repository. If you changed `admin_username`, replace `cloudpulseadmin` in the commands.

**Next:** [Connect the webhook and demonstrate CloudPulse](04_DEMO.md).
