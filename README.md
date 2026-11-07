# CloudTasks v2 - Three-Tier Web Application

Task manager with user accounts, file attachments and monitoring.

```
Browser --> [ WEB: Nginx ] --> [ APP: Flask API ] --> [ DB: PostgreSQL ]
              static UI          JWT auth, REST         users, tasks
              rate limiting      metrics, JSON logs     |
              security headers          |               
                                        +--> [ Object storage: S3 (MinIO locally) ]
```

| Tier | Tech | Folder |
|------|------|--------|
| Web | Nginx: static UI, reverse proxy, rate limit, security headers | `web/` |
| Application | Python Flask + Gunicorn, JWT, Prometheus metrics | `app/` |
| Database | PostgreSQL 16 (Amazon RDS on AWS) | compose `db` |
| Object storage | S3 on AWS / MinIO locally | compose `minio` |

## Run locally
```bash
cp .env.example .env          # edit all secrets (JWT_SECRET: openssl rand -hex 32)
docker compose up --build
# App:   http://localhost:8080
# MinIO: http://localhost:9001   (optional)
```
With monitoring (Prometheus + Grafana):
```bash
docker compose --profile monitoring up --build
# Grafana: http://localhost:3000  (admin / GRAFANA_PASSWORD) -> dashboard "CloudTasks - Application"
# Prometheus: http://localhost:9090
```

## Tests
```bash
cd app
pip install -r requirements-dev.txt
pytest tests/test_unit.py -v                       # no DB needed (runs on every CI build)
RUN_INTEGRATION=1 DB_HOST=localhost DB_USER=appuser DB_PASSWORD=... DB_NAME=tasksdb \
  pytest tests/test_integration.py -v              # needs PostgreSQL; S3 is mocked
```

## Configuration (environment variables)
| Variable | Local | On AWS |
|---|---|---|
| `DB_HOST/PORT/NAME/USER/PASSWORD` | compose | RDS endpoint; password from Secrets Manager |
| `JWT_SECRET` | `.env` | Secrets Manager |
| `S3_BUCKET` | `cloudtasks-uploads` | real bucket name |
| `S3_ENDPOINT`, `S3_AUTO_CREATE` | MinIO | **unset** (real S3, bucket made by Terraform) |
| `AWS_ACCESS_KEY_ID/SECRET` | MinIO creds | **unset** (EC2 instance IAM role) |
| `APP_UPSTREAM`, `NGINX_RESOLVER` (web) | `app:5000`, `127.0.0.11` | internal ALB DNS, `169.254.169.253` |

## API
`POST /api/auth/register|login`, `GET /api/auth/me`,
`GET|POST /api/tasks`, `GET|PUT|DELETE /api/tasks/<id>`, `GET /api/stats`,
`POST /api/tasks/<id>/attachments`, `GET|DELETE /api/attachments/<id>[/download]`,
`GET /api/health` (liveness, for ALB), `GET /api/ready` (DB+S3), `GET /api/info`, `GET /metrics`.
