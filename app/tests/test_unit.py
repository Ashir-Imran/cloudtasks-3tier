"""Unit tests: no database or S3 needed (run on every CI build)."""
import auth
from app import app, clean_task


def client():
    app.config["TESTING"] = True
    return app.test_client()


def bearer(user_id=1):
    return {"Authorization": "Bearer " + auth.make_token(user_id)}


def test_health():
    r = client().get("/api/health")
    assert r.status_code == 200 and r.get_json()["status"] == "ok"


def test_info_has_hostname():
    assert "hostname" in client().get("/api/info").get_json()


def test_metrics_exposed():
    c = client()
    c.get("/api/health")
    r = c.get("/metrics")
    assert r.status_code == 200 and b"http_requests_total" in r.data


def test_request_id_header():
    assert client().get("/api/health").headers.get("X-Request-ID")


def test_tasks_require_auth():
    assert client().get("/api/tasks").status_code == 401
    assert client().post("/api/tasks", json={"title": "x"}).status_code == 401


def test_invalid_token_rejected():
    r = client().get("/api/tasks", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401


def test_token_roundtrip_and_tamper():
    token = auth.make_token(7)
    assert token.count(".") == 2
    r = client().get("/api/tasks", headers={"Authorization": "Bearer " + token + "x"})
    assert r.status_code == 401


def test_password_hash():
    h = auth.hash_password("correct horse")
    assert h != "correct horse"
    assert auth.check_password(h, "correct horse")
    assert not auth.check_password(h, "wrong")


def test_register_validation():
    c = client()
    assert c.post("/api/auth/register", json={"email": "bad", "password": "longenough"}).status_code == 400
    assert c.post("/api/auth/register", json={"email": "a@b.co", "password": "short"}).status_code == 400
    assert c.post("/api/auth/register", data="notjson").status_code == 400


def test_login_validation():
    assert client().post("/api/auth/login", json={}).status_code == 400


def test_task_validation():
    c = client()
    assert c.post("/api/tasks", json={"title": "  "}, headers=bearer()).status_code == 400
    assert c.post("/api/tasks", json={"title": "x" * 201}, headers=bearer()).status_code == 400
    assert c.post("/api/tasks", json={"title": "ok", "priority": 9}, headers=bearer()).status_code == 400
    assert c.post("/api/tasks", json={"title": "ok", "status": "nope"}, headers=bearer()).status_code == 400
    assert c.post("/api/tasks", json={"title": "ok", "due_date": "31/12/2026"}, headers=bearer()).status_code == 400


def test_clean_task_partial():
    out, err = clean_task({"status": "done"}, partial=True)
    assert err is None and out == {"status": "done"}
    out, err = clean_task({"due_date": ""}, partial=True)
    assert out == {"due_date": None}


def test_unknown_route_json():
    r = client().get("/api/nope")
    assert r.status_code == 404 and "error" in r.get_json()
