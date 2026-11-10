#!/bin/bash
# App tier bootstrap: install Docker, read secrets from Secrets Manager, run the container.
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
DB_PASSWORD=$(retry aws secretsmanager get-secret-value --region "$REGION" --secret-id "${db_secret_arn}" --query SecretString --output text)
JWT_SECRET=$(retry aws secretsmanager get-secret-value --region "$REGION" --secret-id "${jwt_secret_arn}" --query SecretString --output text)

# env file lives on tmpfs (/run), readable by root only
umask 077
cat > /run/cloudtasks.env <<ENVEOF
DB_HOST=${db_host}
DB_PORT=5432
DB_NAME=${db_name}
DB_USER=${db_user}
DB_PASSWORD=$DB_PASSWORD
JWT_SECRET=$JWT_SECRET
S3_BUCKET=${s3_bucket}
AWS_REGION=$REGION
PGSSLMODE=require
ENVEOF

retry docker pull "${image}"

docker run -d --name app --restart always -p 5000:5000 \
  --env-file /run/cloudtasks.env \
  --log-driver awslogs \
  --log-opt awslogs-region="$REGION" \
  --log-opt awslogs-group="${log_group}" \
  "${image}"
