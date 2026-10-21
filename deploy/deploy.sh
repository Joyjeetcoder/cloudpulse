#!/usr/bin/env bash
# Called by Azure VM Run Command (root); deploys an immutable public GHCR image.
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Run this script with sudo." >&2; exit 1; fi
image=${1:?Pass ghcr.io/owner/repository@sha256:digest}
if [[ ! "$image" =~ ^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+@sha256:[a-f0-9]{64}$ ]]; then
  echo "Expected an immutable GHCR image digest." >&2; exit 1
fi
if [[ ! -f /opt/cloudpulse/app.env ]]; then
  echo "Missing /opt/cloudpulse/app.env; follow docs/03_AZURE.md." >&2; exit 1
fi
chmod 600 /opt/cloudpulse/app.env
install -d -o 10001 -g 10001 -m 700 /var/lib/cloudpulse
docker network inspect cloudpulse-net >/dev/null
# Pull before stopping the currently running version. GHCR package must be public.
docker pull "$image" >/dev/null
previous=$(docker inspect --format '{{.Config.Image}}' cloudpulse-app 2>/dev/null || true)
start_container() {
  local target=$1
  docker rm -f cloudpulse-app >/dev/null 2>&1 || true
  docker run -d --name cloudpulse-app --restart unless-stopped \
    --network cloudpulse-net --env-file /opt/cloudpulse/app.env \
    -e DATA_DIR=/data -e FRONTEND_DIR=/app/static \
    --security-opt no-new-privileges:true --cap-drop ALL \
    --log-opt max-size=10m --log-opt max-file=3 \
    -v /var/lib/cloudpulse:/data "$target" >/dev/null
}
wait_healthy() {
  local status
  for _ in $(seq 1 30); do
    status=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' cloudpulse-app 2>/dev/null || true)
    [[ "$status" == "healthy" ]] && return 0
    [[ "$status" == "unhealthy" ]] && return 1
    sleep 3
  done
  return 1
}
if start_container "$image" && wait_healthy; then
  printf '%s\n' "$image" > /opt/cloudpulse/current-image
  printf 'CLOUDPULSE_DEPLOY_OK %s\n' "$image"
else
  echo "New application did not become healthy." >&2
  docker logs --tail 50 cloudpulse-app >&2 || true
  if [[ -n "$previous" ]]; then
    echo "Restoring the previous image." >&2
    start_container "$previous"
    wait_healthy || echo "Previous image also needs operator attention." >&2
  fi
  exit 1
fi
