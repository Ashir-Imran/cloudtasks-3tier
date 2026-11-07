"""Object storage (Amazon S3 on AWS, MinIO locally). Uses the instance IAM role on AWS."""
import logging
import os
import time

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

log = logging.getLogger("storage")
_client = None


def enabled():
    return bool(os.environ.get("S3_BUCKET"))


def bucket():
    return os.environ["S3_BUCKET"]


def client():
    global _client
    if _client is None:
        endpoint = os.environ.get("S3_ENDPOINT") or None
        _client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
            config=Config(s3={"addressing_style": "path"} if endpoint else {},
                          retries={"max_attempts": 3}, connect_timeout=5, read_timeout=15),
        )
    return _client


def ensure_bucket(retries=10, delay=2):
    """Local dev only: create the bucket in MinIO. On AWS, Terraform owns the bucket."""
    if not enabled() or os.environ.get("S3_AUTO_CREATE") != "1":
        return
    for attempt in range(1, retries + 1):
        try:
            try:
                client().head_bucket(Bucket=bucket())
            except ClientError:
                client().create_bucket(Bucket=bucket())
                log.info("created bucket %s", bucket())
            return
        except (BotoCoreError, ClientError) as exc:
            log.warning("storage not ready (attempt %s/%s): %s", attempt, retries, exc)
            time.sleep(delay)
    log.error("could not prepare bucket; uploads will fail")


def put(key, data, content_type):
    client().put_object(Bucket=bucket(), Key=key, Body=data, ContentType=content_type)


def get(key):
    return client().get_object(Bucket=bucket(), Key=key)


def delete(key):
    try:
        client().delete_object(Bucket=bucket(), Key=key)
    except (BotoCoreError, ClientError) as exc:
        log.warning("could not delete %s: %s", key, exc)


def healthy():
    try:
        client().head_bucket(Bucket=bucket())
        return True
    except (BotoCoreError, ClientError):
        return False
