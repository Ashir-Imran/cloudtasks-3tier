"""Structured JSON logs (CloudWatch friendly) + Prometheus metrics."""
import json
import logging
import os
import sys
import time
import uuid

from flask import g, request
from prometheus_client import Counter, Histogram

REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "endpoint", "status"])
LATENCY = Histogram("http_request_duration_seconds", "Request latency in seconds", ["endpoint"])
QUIET = {"/api/health", "/metrics"}
log = logging.getLogger("request")


class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        data.update(getattr(record, "fields", {}))
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data)


def setup_logging():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def register(app):
    @app.before_request
    def _start():
        g.start = time.perf_counter()
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]

    @app.after_request
    def _finish(resp):
        endpoint = request.url_rule.rule if request.url_rule else "unmatched"
        elapsed = time.perf_counter() - getattr(g, "start", time.perf_counter())
        REQUESTS.labels(request.method, endpoint, resp.status_code).inc()
        LATENCY.labels(endpoint).observe(elapsed)
        resp.headers["X-Request-ID"] = getattr(g, "request_id", "-")
        if endpoint not in QUIET:
            log.info("request", extra={"fields": {
                "request_id": getattr(g, "request_id", "-"), "method": request.method,
                "path": request.path, "status": resp.status_code,
                "ms": round(elapsed * 1000, 1), "user_id": getattr(g, "user_id", None)}})
        return resp
