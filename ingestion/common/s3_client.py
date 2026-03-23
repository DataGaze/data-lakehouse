"""S3 client wrapper cho SeaweedFS S3-compatible API."""
from __future__ import annotations

import os
from pathlib import Path

import boto3
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv()


def get_s3_client():
    """Tạo boto3 S3 client kết nối SeaweedFS."""
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",  # SeaweedFS không quan tâm region
    )


def upload_file(local_path: Path, s3_key: str, bucket: str | None = None) -> bool:
    """Upload file lên SeaweedFS S3."""
    bucket = bucket or os.environ["S3_BUCKET"]
    client = get_s3_client()
    client.upload_file(str(local_path), bucket, s3_key)
    return True


def download_file(s3_key: str, local_path: Path, bucket: str | None = None) -> bool:
    """Download file từ SeaweedFS S3."""
    bucket = bucket or os.environ["S3_BUCKET"]
    client = get_s3_client()
    local_path.parent.mkdir(parents=True, exist_ok=True)
    client.download_file(bucket, s3_key, str(local_path))
    return True


def list_objects(prefix: str, bucket: str | None = None) -> list[str]:
    """List objects trong SeaweedFS S3 theo prefix."""
    bucket = bucket or os.environ["S3_BUCKET"]
    client = get_s3_client()
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def object_exists(s3_key: str, bucket: str | None = None) -> bool:
    """Kiểm tra object có tồn tại trên S3."""
    bucket = bucket or os.environ["S3_BUCKET"]
    client = get_s3_client()
    try:
        client.head_object(Bucket=bucket, Key=s3_key)
        return True
    except client.exceptions.ClientError:
        return False
