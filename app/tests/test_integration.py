"""Integration tests: need PostgreSQL. S3 is mocked with moto.
Run with:  RUN_INTEGRATION=1 DB_HOST=localhost DB_PASSWORD=... pytest tests/test_integration.py
"""
import io
import os

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1",
                                reason="set RUN_INTEGRATION=1 and provide a PostgreSQL database")


@pytest.fixture(scope="module")
def client():
    os.environ["S3_BUCKET"] = "test-bucket"
    os.environ["S3_AUTO_CREATE"] = "1"
    from moto import mock_aws
    with mock_aws():
        import db
        import storage
        storage._client = None
        db.migrate(retries=3, delay=1)
        storage.ensure_bucket()
        with db.cursor() as cur:
            cur.execute("TRUNCATE users, tasks, attachments RESTART IDENTITY CASCADE")
        from app import app
        app.config["TESTING"] = True
        yield app.test_client()


def register(client, email):
    r = client.post("/api/auth/register", json={"email": email, "password": "password123", "name": "T"})
    assert r.status_code == 201
    return {"Authorization": "Bearer " + r.get_json()["token"]}


def test_full_flow(client):
    h = register(client, "alice@example.com")
    assert client.post("/api/auth/register", json={"email": "ALICE@example.com", "password": "password123"}).status_code == 409
    assert client.post("/api/auth/login", json={"email": "alice@example.com", "password": "bad-password"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "password123"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "alice@example.com", "password": "password123"}).status_code == 200
    assert client.get("/api/auth/me", headers=h).get_json()["email"] == "alice@example.com"

    t = client.post("/api/tasks", json={"title": "Write report", "priority": 3, "due_date": "2020-01-01"}, headers=h)
    assert t.status_code == 201
    tid = t.get_json()["id"]
    client.post("/api/tasks", json={"title": "Buy milk"}, headers=h)

    lst = client.get("/api/tasks", headers=h).get_json()
    assert lst["total"] == 2 and lst["items"][0]["title"] == "Write report"  # high priority first
    assert client.get("/api/tasks?q=milk", headers=h).get_json()["total"] == 1
    assert client.get("/api/tasks?q=%25", headers=h).get_json()["total"] == 0  # wildcard escaped
    assert client.get("/api/tasks?priority=3", headers=h).get_json()["total"] == 1

    assert client.get("/api/stats", headers=h).get_json()["overdue"] == 1
    u = client.put("/api/tasks/%s" % tid, json={"status": "done"}, headers=h)
    assert u.status_code == 200 and u.get_json()["status"] == "done"
    st = client.get("/api/stats", headers=h).get_json()
    assert st["done"] == 1 and st["overdue"] == 0 and st["total"] == 2

    # attachments
    up = client.post("/api/tasks/%s/attachments" % tid, headers=h, content_type="multipart/form-data",
                     data={"file": (io.BytesIO(b"hello world"), "notes.txt", "text/plain")})
    assert up.status_code == 201
    aid = up.get_json()["id"]
    bad = client.post("/api/tasks/%s/attachments" % tid, headers=h, content_type="multipart/form-data",
                      data={"file": (io.BytesIO(b"MZ"), "virus.exe", "application/x-msdownload")})
    assert bad.status_code == 415
    dl = client.get("/api/attachments/%s/download" % aid, headers=h)
    assert dl.status_code == 200 and dl.data == b"hello world"
    assert client.get("/api/tasks/%s" % tid, headers=h).get_json()["attachments"][0]["filename"] == "notes.txt"

    # another user cannot see or touch alice's data
    h2 = register(client, "bob@example.com")
    assert client.get("/api/tasks/%s" % tid, headers=h2).status_code == 404
    assert client.put("/api/tasks/%s" % tid, json={"title": "hacked"}, headers=h2).status_code == 404
    assert client.delete("/api/tasks/%s" % tid, headers=h2).status_code == 404
    assert client.get("/api/attachments/%s/download" % aid, headers=h2).status_code == 404
    assert client.get("/api/tasks", headers=h2).get_json()["total"] == 0

    assert client.delete("/api/attachments/%s" % aid, headers=h).status_code == 204
    assert client.delete("/api/tasks/%s" % tid, headers=h).status_code == 204
    assert client.get("/api/tasks/%s" % tid, headers=h).status_code == 404


def test_ready(client):
    r = client.get("/api/ready")
    assert r.status_code == 200 and r.get_json()["storage"] == "up"
