import os
import sys

os.environ.setdefault("SKIP_DB_INIT", "1")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-123456")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_REGION", "us-east-1")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
