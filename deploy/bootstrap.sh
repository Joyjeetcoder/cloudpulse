#!/usr/bin/env bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Run this script with sudo." >&2; exit 1; fi
hostname=${1:?Pass the Azure DNS hostname}
if [[ ! "$hostname" =~ ^[a-z0-9][a-z0-9.-]+[a-z0-9]$ ]]; then echo "Invalid hostname" >&2; exit 1; fi
install -d -m 750 /opt/cloudpulse
install -d -o 10001 -g 10001 -m 700 /var/lib/cloudpulse
docker network inspect cloudpulse-net >/dev/null 2>&1 || docker network create cloudpulse-net >/dev/null
cat > /opt/cloudpulse/Caddyfile <<EOF
$hostname {
    encode zstd gzip
    request_body {
        max_size 1MB
    }
    reverse_proxy cloudpulse-app:8000
}
EOF
chmod 644 /opt/cloudpulse/Caddyfile
docker rm -f cloudpulse-proxy >/dev/null 2>&1 || true
docker run -d --name cloudpulse-proxy --restart unless-stopped \
  --network cloudpulse-net -p 80:80 -p 443:443 \
  --security-opt no-new-privileges:true \
  --log-opt max-size=10m --log-opt max-file=3 \
  -v /opt/cloudpulse/Caddyfile:/etc/caddy/Caddyfile:ro \
  -v cloudpulse-caddy-data:/data -v cloudpulse-caddy-config:/config \
  caddy:2.10.0-alpine >/dev/null
printf 'Proxy configured for https://%s\n' "$hostname"
printf 'Add /opt/cloudpulse/app.env, then deploy an application image.\n'
