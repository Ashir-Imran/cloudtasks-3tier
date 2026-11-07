import logging
import os
import socket
import uuid
from datetime import date, datetime

import psycopg2.errors
from flask import Flask, Response, g, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

import db
import observability
import storage
from auth import (EMAIL_RE, burn_password_check, check_password, hash_password,
                  login_required, make_token)

observability.setup_logging()
log = logging.getLogger("app")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024 + 8192  # 5 MB uploads
observability.register(app)

STATUSES = ("todo", "in_progress", "done")
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/gif", "application/pdf", "text/plain"}
MAX_ATTACHMENTS = 10


# ---------------------------------------------------------------- helpers
def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def iso(row):
    return {k: (v.isoformat() if isinstance(v, (date, datetime)) else v) for k, v in row.items()}


def clean_task(d, partial=False):
    """Validate task input. Returns (clean_dict, error_message)."""
    out = {}
    if "title" in d or not partial:
        t = d.get("title")
        if not isinstance(t, str) or not t.strip():
            return None, "title is required"
        if len(t.strip()) > 200:
            return None, "title too long (max 200)"
        out["title"] = t.strip()
    if "description" in d:
        v = d["description"] or ""
        if not isinstance(v, str) or len(v) > 2000:
            return None, "description must be text up to 2000 characters"
        out["description"] = v
    if "priority" in d:
        p = d["priority"]
        if isinstance(p, bool) or not isinstance(p, int) or p not in (1, 2, 3):
            return None, "priority must be 1, 2 or 3"
        out["priority"] = p
    if "status" in d:
        if d["status"] not in STATUSES:
            return None, "status must be one of: " + ", ".join(STATUSES)
        out["status"] = d["status"]
    if "due_date" in d:
        v = d["due_date"]
        if v in (None, ""):
            out["due_date"] = None
        else:
            try:
                out["due_date"] = date.fromisoformat(v)
            except (TypeError, ValueError):
                return None, "due_date must be YYYY-MM-DD"
    return out, None


TASK_SELECT = """SELECT t.id, t.title, t.description, t.priority, t.status, t.due_date,
                        t.created_at, t.updated_at,
                        (SELECT COUNT(*) FROM attachments a WHERE a.task_id = t.id) AS attachment_count
                 FROM tasks t"""


# ---------------------------------------------------------------- errors
@app.errorhandler(HTTPException)
def http_error(e):
    return jsonify(error=e.name.lower()), e.code


@app.errorhandler(Exception)
def unexpected(e):
    log.exception("unhandled error")
    return jsonify(error="internal server error"), 500


# ---------------------------------------------------------------- ops
@app.get("/api/health")
def health():
    # Liveness only (no dependencies): used by the load balancer health check
    return jsonify(status="ok"), 200


@app.get("/api/ready")
def ready():
    result, code = {"database": "up", "storage": "disabled"}, 200
    try:
        with db.cursor(dict_rows=False) as cur:
            cur.execute("SELECT 1")
    except Exception:
        result["database"], code = "down", 503
    if storage.enabled():
        result["storage"] = "up" if storage.healthy() else "down"
    result["status"] = "ready" if code == 200 else "degraded"
    return jsonify(result), code


@app.get("/api/info")
def info():
    # Which container served this request (handy to demo load balancing)
    return jsonify(hostname=socket.gethostname(), version=os.environ.get("APP_VERSION", "dev"))


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


# ---------------------------------------------------------------- auth
@app.post("/api/auth/register")
def register():
    d = body()
    email = (d.get("email") or "").strip().lower() if isinstance(d.get("email"), str) else ""
    password = d.get("password") if isinstance(d.get("password"), str) else ""
    name = (d.get("name") or "").strip()[:100] if isinstance(d.get("name"), str) else ""
    if not EMAIL_RE.match(email) or len(email) > 255:
        return jsonify(error="a valid email is required"), 400
    if not 8 <= len(password) <= 128:
        return jsonify(error="password must be 8-128 characters"), 400
    try:
        with db.cursor() as cur:
            cur.execute("INSERT INTO users (email, name, password_hash) VALUES (%s,%s,%s) "
                        "RETURNING id, email, name", (email, name, hash_password(password)))
            user = cur.fetchone()
    except psycopg2.errors.UniqueViolation:
        return jsonify(error="email already registered"), 409
    return jsonify(token=make_token(user["id"]), user=user), 201


@app.post("/api/auth/login")
def login():
    d = body()
    email = (d.get("email") or "").strip().lower() if isinstance(d.get("email"), str) else ""
    password = d.get("password") if isinstance(d.get("password"), str) else ""
    if not email or not password or len(password) > 128:
        return jsonify(error="email and password are required"), 400
    with db.cursor() as cur:
        cur.execute("SELECT id, email, name, password_hash FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
    if user is None:
        burn_password_check(password)
        return jsonify(error="invalid email or password"), 401
    if not check_password(user["password_hash"], password):
        return jsonify(error="invalid email or password"), 401
    return jsonify(token=make_token(user["id"]),
                   user={"id": user["id"], "email": user["email"], "name": user["name"]})


@app.get("/api/auth/me")
@login_required
def me():
    with db.cursor() as cur:
        cur.execute("SELECT id, email, name FROM users WHERE id = %s", (g.user_id,))
        user = cur.fetchone()
    if user is None:
        return jsonify(error="invalid or expired token"), 401
    return jsonify(user)


# ---------------------------------------------------------------- tasks
@app.get("/api/tasks")
@login_required
def list_tasks():
    where, params = ["t.user_id = %s"], [g.user_id]
    status = request.args.get("status", "")
    if status in STATUSES:
        where.append("t.status = %s")
        params.append(status)
    priority = request.args.get("priority", "")
    if priority in ("1", "2", "3"):
        where.append("t.priority = %s")
        params.append(int(priority))
    q = request.args.get("q", "").strip()[:100]
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(t.title ILIKE %s OR t.description ILIKE %s)")
        params += [like, like]
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(50, max(1, int(request.args.get("per_page", 10))))
    except ValueError:
        return jsonify(error="page and per_page must be numbers"), 400
    clause = " WHERE " + " AND ".join(where)
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM tasks t" + clause, params)
        total = cur.fetchone()["n"]
        cur.execute(TASK_SELECT + clause +
                    " ORDER BY (t.status = 'done'), t.priority DESC, t.due_date NULLS LAST, t.id DESC"
                    " LIMIT %s OFFSET %s", params + [per_page, (page - 1) * per_page])
        items = [iso(r) for r in cur.fetchall()]
    return jsonify(items=items, total=total, page=page, per_page=per_page)


@app.post("/api/tasks")
@login_required
def create_task():
    clean, err = clean_task(body())
    if err:
        return jsonify(error=err), 400
    cols = ["user_id"] + list(clean)
    vals = [g.user_id] + list(clean.values())
    with db.cursor() as cur:
        cur.execute("INSERT INTO tasks (%s) VALUES (%s) RETURNING id" %
                    (", ".join(cols), ", ".join(["%s"] * len(cols))), vals)
        new_id = cur.fetchone()["id"]
        cur.execute(TASK_SELECT + " WHERE t.id = %s", (new_id,))
        row = cur.fetchone()
    return jsonify(iso(row)), 201


@app.get("/api/tasks/<int:task_id>")
@login_required
def get_task(task_id):
    with db.cursor() as cur:
        cur.execute(TASK_SELECT + " WHERE t.id = %s AND t.user_id = %s", (task_id, g.user_id))
        row = cur.fetchone()
        if row is None:
            return jsonify(error="not found"), 404
        cur.execute("SELECT id, filename, content_type, size_bytes, created_at FROM attachments "
                    "WHERE task_id = %s ORDER BY id", (task_id,))
        attachments = [iso(a) for a in cur.fetchall()]
    task = iso(row)
    task["attachments"] = attachments
    return jsonify(task)


@app.put("/api/tasks/<int:task_id>")
@login_required
def update_task(task_id):
    clean, err = clean_task(body(), partial=True)
    if err:
        return jsonify(error=err), 400
    if not clean:
        return jsonify(error="nothing to update"), 400
    sets = ", ".join("%s = %%s" % c for c in clean) + ", updated_at = NOW()"
    with db.cursor() as cur:
        cur.execute("UPDATE tasks SET " + sets + " WHERE id = %s AND user_id = %s RETURNING id",
                    list(clean.values()) + [task_id, g.user_id])
        if cur.fetchone() is None:
            return jsonify(error="not found"), 404
        cur.execute(TASK_SELECT + " WHERE t.id = %s", (task_id,))
        row = cur.fetchone()
    return jsonify(iso(row))


@app.delete("/api/tasks/<int:task_id>")
@login_required
def delete_task(task_id):
    with db.cursor() as cur:
        cur.execute("SELECT a.s3_key FROM attachments a JOIN tasks t ON t.id = a.task_id "
                    "WHERE t.id = %s AND t.user_id = %s", (task_id, g.user_id))
        keys = [r["s3_key"] for r in cur.fetchall()]
        cur.execute("DELETE FROM tasks WHERE id = %s AND user_id = %s", (task_id, g.user_id))
        if cur.rowcount == 0:
            return jsonify(error="not found"), 404
    if storage.enabled():
        for k in keys:
            storage.delete(k)
    return "", 204


@app.get("/api/stats")
@login_required
def stats():
    with db.cursor() as cur:
        cur.execute("""SELECT COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE status = 'todo') AS todo,
                  COUNT(*) FILTER (WHERE status = 'in_progress') AS in_progress,
                  COUNT(*) FILTER (WHERE status = 'done') AS done,
                  COUNT(*) FILTER (WHERE status <> 'done' AND due_date < CURRENT_DATE) AS overdue
                FROM tasks WHERE user_id = %s""", (g.user_id,))
        return jsonify(cur.fetchone())


# ---------------------------------------------------------------- attachments (S3)
@app.post("/api/tasks/<int:task_id>/attachments")
@login_required
def upload_attachment(task_id):
    if not storage.enabled():
        return jsonify(error="file storage is not configured"), 503
    f = request.files.get("file")
    if f is None or not f.filename:
        return jsonify(error="file is required"), 400
    ctype = (f.mimetype or "").lower()
    if ctype not in ALLOWED_TYPES:
        return jsonify(error="file type not allowed (png, jpg, gif, pdf, txt)"), 415
    data = f.read()
    if not data:
        return jsonify(error="file is empty"), 400
    filename = secure_filename(f.filename) or "file"
    with db.cursor() as cur:
        cur.execute("SELECT 1 FROM tasks WHERE id = %s AND user_id = %s", (task_id, g.user_id))
        if cur.fetchone() is None:
            return jsonify(error="not found"), 404
        cur.execute("SELECT COUNT(*) AS n FROM attachments WHERE task_id = %s", (task_id,))
        if cur.fetchone()["n"] >= MAX_ATTACHMENTS:
            return jsonify(error="attachment limit reached (10 per task)"), 400
    key = "%s/%s/%s-%s" % (g.user_id, task_id, uuid.uuid4().hex, filename)
    storage.put(key, data, ctype)
    try:
        with db.cursor() as cur:
            cur.execute("INSERT INTO attachments (task_id, filename, s3_key, content_type, size_bytes) "
                        "VALUES (%s,%s,%s,%s,%s) RETURNING id, filename, content_type, size_bytes, created_at",
                        (task_id, filename, key, ctype, len(data)))
            row = cur.fetchone()
    except Exception:
        storage.delete(key)
        raise
    return jsonify(iso(row)), 201


def _own_attachment(att_id):
    with db.cursor() as cur:
        cur.execute("SELECT a.id, a.filename, a.s3_key, a.content_type FROM attachments a "
                    "JOIN tasks t ON t.id = a.task_id WHERE a.id = %s AND t.user_id = %s",
                    (att_id, g.user_id))
        return cur.fetchone()


@app.get("/api/attachments/<int:att_id>/download")
@login_required
def download_attachment(att_id):
    row = _own_attachment(att_id)
    if row is None:
        return jsonify(error="not found"), 404
    obj = storage.get(row["s3_key"])
    return Response(obj["Body"].read(), mimetype=row["content_type"], headers={
        "Content-Disposition": 'attachment; filename="%s"' % row["filename"],
        "X-Content-Type-Options": "nosniff"})


@app.delete("/api/attachments/<int:att_id>")
@login_required
def delete_attachment(att_id):
    row = _own_attachment(att_id)
    if row is None:
        return jsonify(error="not found"), 404
    with db.cursor() as cur:
        cur.execute("DELETE FROM attachments WHERE id = %s", (att_id,))
    storage.delete(row["s3_key"])
    return "", 204


# ---------------------------------------------------------------- startup
def startup():
    if os.environ.get("SKIP_DB_INIT") == "1":
        return
    db.migrate()
    storage.ensure_bucket()


startup()
