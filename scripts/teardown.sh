#!/usr/bin/env bash
# CloudPulse teardown - run AFTER the presentation to stop all Azure charges.
#
# Cost model: B1ms compute ~$0.01/h, Standard_LRS 32 GB disk ~$4.80/mo,
# Standard static public IP ~$2.88/mo. Deallocating the VM stops compute
# only; the disk and the public IP keep billing. terraform destroy removes
# every resource in the group, which is the only way to reach zero.
#
# Run from infra/terraform. Terraform must be on PATH:
#   export PATH="$HOME/.local/bin:$PATH"

set -euo pipefail
cd "$(dirname "$0")/infra/terraform"

echo "==> Resource inventory (before)"
az vm list --resource-group rg-cloudpulse-dc11d2 \
  --query "[].{type:'VM',name:name,size:hardwareProfile.vmSize}" -o table
az disk list --resource-group rg-cloudpulse-dc11d2 \
  --query "[].{type:'Disk',name:name,sku:sku.name}" -o table
az network public-ip list --resource-group rg-cloudpulse-dc11d2 \
  --query "[].{type:'PublicIP',name:name,ip:ipAddress,sku:sku.name}" -o table

echo
echo "==> Backing up the run database and redacted logs"
HOST=cloudpulse-dc11d2.indiasouthcentral.cloudapp.azure.com
if ssh -i "$HOME/.ssh/cloudpulse_azure" -o ConnectTimeout=25 -o BatchMode=yes \
      "cloudpulseadmin@$HOST" \
      "sudo tar -C /var/lib -czf /tmp/cloudpulse-data.tgz cloudpulse && \
       sudo install -o cloudpulseadmin -g cloudpulseadmin -m 600 \
         /tmp/cloudpulse-data.tgz /home/cloudpulseadmin/cloudpulse-data.tgz" 2>/dev/null; then
  scp -i "$HOME/.ssh/cloudpulse_azure" -o ConnectTimeout=25 \
      "cloudpulseadmin@$HOST:cloudpulse-data.tgz" ./cloudpulse-data.tgz
  echo "    saved to infra/terraform/cloudpulse-data.tgz"
  echo "    NOTE: it contains logs and metadata. Do not commit or publish it."
else
  echo "    backup skipped (VM unreachable). The database will be lost."
fi

echo
echo "==> Destroying every CloudPulse resource"
terraform destroy -auto-approve

echo
echo "==> Verifying nothing is left billing"
echo "-- resource group:"
az group show -n rg-cloudpulse-dc11d2 --query name -o tsv 2>&1 | tail -1
echo "-- public IPs:"
az network public-ip list --query "[?contains(name,'cloudpulse')].{name:name,ip:ipAddress}" -o table
echo "-- disks:"
az disk list --query "[?contains(name,'cloudpulse')].{name:name}" -o table
echo "-- VMs:"
az vm list --query "[?contains(name,'cloudpulse')].{name:name,group:resourceGroup}" -o table

echo
echo "If the group still exists, delete it directly:"
echo "  az group delete -n rg-cloudpulse-dc11d2 -y"

echo
echo "==> Optional: remove the published container image"
echo "  https://github.com/users/Joyjeetcoder/packages/container/cloudpulse/settings"
echo "  (free to keep; it only uses GHCR storage)"
