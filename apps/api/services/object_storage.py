"""Object storage helper for Cloudflare R2 (Sprint 7 chunk 7.6, 7.11).

The questionnaire flow needs to:
  - upload an XLSX from the client to durable storage,
  - hand a key to the background worker,
  - generate a pre-signed download URL when the run is ready.

Production uses Cloudflare R2 (S3-compatible). For local development and
tests we fall back to a directory on the local filesystem so nothing needs
real R2 credentials. ``R2 not configured`` is not an error — it just means
``put_bytes`` writes to ``settings.local_object_storage_dir`` and
``presigned_get_url`` returns a ``file://`` URL. The same code path works
for unit tests that monkeypatch the storage dir.

Refs: PLAN.md chunks 7.6, 7.11; ADR-0008.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apps.api.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredObject:
    """Reference to an object placed in R2 (or the local fallback)."""

    key: str
    backend: str  # 'r2' | 'local'
    size_bytes: int


class ObjectStorage:
    """Thin wrapper around boto3 + a local-filesystem fallback."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = None
        self._bucket = settings.r2_bucket_name
        self._local_dir = Path(
            os.environ.get(
                "LOCAL_OBJECT_STORAGE_DIR",
                "/tmp/auditpilot-object-storage",
            )
        )

    def _r2_configured(self) -> bool:
        s = self._settings
        return bool(s.r2_account_id and s.r2_access_key_id and s.r2_secret_access_key)

    def _get_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        if not self._r2_configured():
            return None
        try:
            import boto3  # type: ignore[import-untyped]
            from botocore.config import Config  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("boto3 not installed; falling back to local storage")
            return None

        account_id = self._settings.r2_account_id
        endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
        access_key = self._settings.r2_access_key_id.get_secret_value()  # type: ignore[union-attr]
        secret_key = self._settings.r2_secret_access_key.get_secret_value()  # type: ignore[union-attr]
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4", region_name="auto"),
        )
        return self._client

    @property
    def backend(self) -> str:
        return "r2" if self._r2_configured() else "local"

    def make_key(self, *, user_id: str, kind: str, suffix: str = "") -> str:
        """Compute a stable per-user, per-kind object key."""
        token = uuid.uuid4().hex
        safe_kind = kind.replace("/", "_")
        return f"users/{user_id}/{safe_kind}/{token}{suffix}"

    def _safe_local_path(self, key: str) -> Path:
        """Resolve ``key`` against the local storage root and reject escapes.

        Mitigates path traversal (``..`` components) at the boundary so
        downstream consumers can trust the returned path.
        """
        if "\x00" in key:
            raise ValueError("invalid object key")
        root = self._local_dir.resolve()
        candidate = (self._local_dir / key).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("object key escapes storage root") from exc
        return candidate

    def put_bytes(self, key: str, body: bytes, *, content_type: str) -> StoredObject:
        client = self._get_client()
        if client is not None:
            client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
            )
            return StoredObject(key=key, backend="r2", size_bytes=len(body))
        path = self._safe_local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return StoredObject(key=key, backend="local", size_bytes=len(body))

    def get_bytes(self, key: str) -> bytes:
        client = self._get_client()
        if client is not None:
            resp = client.get_object(Bucket=self._bucket, Key=key)
            return resp["Body"].read()
        return self._safe_local_path(key).read_bytes()

    def local_path(self, key: str) -> Path:
        """Return a filesystem path for ``key`` — fetching from R2 if needed.

        The questionnaire worker runs ``parse_xlsx`` and ``assemble_filled_xlsx``
        against local paths because openpyxl is a sync library. For R2-backed
        objects this materialises a copy into a tmp dir; for local-backed
        objects it returns the original path directly.
        """
        if self.backend == "local":
            return self._safe_local_path(key)
        body = self.get_bytes(key)
        # Cache R2 objects under a contained sub-directory to keep traversal
        # impossible even if a tampered key ever escapes the resolver.
        cache_root = (self._local_dir / "_r2_cache").resolve()
        candidate = (cache_root / key).resolve()
        try:
            candidate.relative_to(cache_root)
        except ValueError as exc:
            raise ValueError("object key escapes cache root") from exc
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(body)
        return candidate

    def presigned_get_url(self, key: str, *, ttl_seconds: int = 900) -> str:
        client = self._get_client()
        if client is not None:
            url = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=ttl_seconds,
            )
            return url
        path = self._safe_local_path(key)
        return f"file://{path.absolute()}"


_storage: ObjectStorage | None = None


def get_object_storage(settings: Settings | None = None) -> ObjectStorage:
    """Lazy module-level accessor; routes inject this via ``Depends``."""
    global _storage
    if _storage is None:
        if settings is None:
            settings = Settings()
        _storage = ObjectStorage(settings)
    return _storage


def reset_object_storage() -> None:
    """Test hook — resets the module-level singleton."""
    global _storage
    _storage = None


__all__ = [
    "ObjectStorage",
    "StoredObject",
    "get_object_storage",
    "reset_object_storage",
]
