"""Attachment byte storage. Bytes live only in object storage, never on the service disk."""

from collections.abc import Callable
from functools import lru_cache
from typing import Any, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException, status

from app.config import get_settings


class StorageError(RuntimeError):
    pass


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def check(self) -> None: ...


class S3Storage:
    def __init__(
        self,
        bucket: str,
        endpoint: str | None,
        access_key: str | None,
        secret_key: str | None,
        region: str,
        auto_create: bool,
    ) -> None:
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint or None,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3},
                connect_timeout=5,
                read_timeout=30,
            ),
        )
        self._ensured = not auto_create
        # Readiness probes must answer fast: short timeouts and no retries.
        self.probe = boto3.client(
            "s3",
            endpoint_url=endpoint or None,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 1, "mode": "standard"},
                connect_timeout=2,
                read_timeout=3,
            ),
        )

    def _ensure_bucket(self) -> None:
        if not self._ensured:
            try:
                self.client.head_bucket(Bucket=self.bucket)
            except ClientError:
                self.client.create_bucket(Bucket=self.bucket)
            self._ensured = True

    def _call(self, fn: Callable[..., Any], **kwargs: Any) -> Any:
        self._ensure_bucket()
        try:
            return fn(Bucket=self.bucket, **kwargs)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(type(exc).__name__) from exc

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._call(self.client.put_object, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        body = self._call(self.client.get_object, Key=key)["Body"]
        data: bytes = body.read()
        return data

    def delete(self, key: str) -> None:
        self._call(self.client.delete_object, Key=key)

    def check(self) -> None:
        try:
            self._ensure_bucket()
            self.probe.head_bucket(Bucket=self.bucket)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(type(exc).__name__) from exc


class MemoryStorage:
    """In-process fake for unit tests."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    def get(self, key: str) -> bytes:
        if key not in self.objects:
            raise StorageError("NoSuchKey")
        return self.objects[key][0]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def check(self) -> None:
        return None


@lru_cache
def _configured() -> Storage | None:
    s = get_settings()
    if not s.storage_bucket:
        return None
    return S3Storage(
        bucket=s.storage_bucket,
        endpoint=s.storage_endpoint,
        access_key=s.storage_access_key,
        secret_key=s.storage_secret_key,
        region=s.storage_region,
        auto_create=s.storage_auto_create_bucket,
    )


def optional_storage() -> Storage | None:
    return _configured()


def get_storage() -> Storage:
    storage = _configured()
    if storage is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Attachment storage is not configured"
        )
    return storage
