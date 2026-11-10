#!/bin/bash
# Web tier bootstrap: install Docker and run the Nginx container.
set -euo pipefail
exec > >(tee /var/log/user-data.log) 2>&1

retry() {
  for i in $(seq 1 10); do
    "$@" && return 0
    echo "retry $i/10 failed: $*" >&2
    sleep 15
  done
  return 1
}

retry dnf install -y docker
systemctl enable --now docker

REGION="${region}"
retry docker pull "${image}"

docker run -d --name web --restart always -p 80:80 \
  -e APP_UPSTREAM="${app_upstream}" \
  -e NGINX_RESOLVER="${resolver}" \
  --log-driver awslogs \
  --log-opt awslogs-region="$REGION" \
  --log-opt awslogs-group="${log_group}" \
  "${image}"
