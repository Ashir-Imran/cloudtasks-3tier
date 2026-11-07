"""Password hashing + JWT authentication."""
import datetime
import os
import re
from functools import wraps

import jwt
from flask import g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

SECRET = os.environ.get("JWT_SECRET", "")
if len(SECRET) < 16:
    raise RuntimeError("JWT_SECRET must be set (at least 16 characters)")

TTL_HOURS = int(os.environ.get("JWT_TTL_HOURS", "8"))
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def hash_password(password):
    return generate_password_hash(password)


def check_password(stored_hash, password):
    return check_password_hash(stored_hash, password)


def burn_password_check(password):
    """Constant-ish time for unknown users (prevents user enumeration by timing)."""
    check_password_hash(_DUMMY_HASH, password)


def make_token(user_id):
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + datetime.timedelta(hours=TTL_HOURS)}
    return jwt.encode(payload, SECRET, algorithm="HS256")


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify(error="authentication required"), 401
        try:
            payload = jwt.decode(header[7:], SECRET, algorithms=["HS256"])
            g.user_id = int(payload["sub"])
        except (jwt.PyJWTError, KeyError, ValueError):
            return jsonify(error="invalid or expired token"), 401
        return fn(*args, **kwargs)
    return wrapper
