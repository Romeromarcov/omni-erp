"""
StorageService — capa de abstracción sobre S3/MinIO para Omni ERP.

Principios de diseño:
- Multi-tenant: todos los archivos se almacenan bajo ``empresas/{empresa_id}/``
  para garantizar aislamiento físico en el bucket.
- Stateless: no depende de modelos de Django, puede usarse desde tareas Celery.
- Testeable: las llamadas a boto3 son aisladas en métodos pequeños, facilitando
  el mock en tests.
- Togglable: si ``USE_S3=False`` (dev sin MinIO), las operaciones de storage
  se cortocircuitan y devuelven datos ficticios para no romper la app.

Uso típico:
    from apps.core.storage import StorageService

    storage = StorageService()
    s3_key, size = storage.upload_file(
        empresa_id='<uuid>',
        carpeta='facturas',
        filename='factura-001.pdf',
        file_obj=request.FILES['archivo'],
        content_type='application/pdf',
    )
    url = storage.generate_presigned_url(s3_key)
"""

from __future__ import annotations

import logging
import mimetypes
import os
import uuid
from io import BytesIO
from typing import BinaryIO, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Helpers para leer configuración sin importar Django settings ────────────


def _get_s3_client():
    """Crea y retorna un cliente boto3 configurado desde Django settings."""
    import boto3

    from django.conf import settings

    return boto3.client(
        "s3",
        endpoint_url=getattr(settings, "S3_ENDPOINT_URL", "http://localhost:9000"),
        aws_access_key_id=getattr(settings, "S3_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=getattr(settings, "S3_SECRET_KEY", "minioadmin"),
        region_name=getattr(settings, "S3_REGION", "us-east-1"),
        config=_get_boto_config(),
    )


def _get_boto_config():
    """Retorna BotoCoreConfig con path-style (necesario para MinIO en dev)."""
    from botocore.config import Config

    return Config(signature_version="s3v4", s3={"addressing_style": "path"})


def _settings():
    """Devuelve el módulo de settings de Django."""
    from django.conf import settings

    return settings


# ── Clase principal ──────────────────────────────────────────────────────────


class StorageService:
    """
    Servicio de almacenamiento de archivos S3-compatible.

    Todos los métodos comprueban ``USE_S3`` antes de conectar a S3.
    Si ``USE_S3=False``, las operaciones devuelven datos de stub sin
    realizar ninguna llamada de red (útil en dev/test sin MinIO).
    """

    # H-SEC-5: whitelist de extensiones permitidas (más seguro que blacklist:
    # una blacklist nunca cubre todos los vectores — .html, .svg, .htm, etc.).
    ALLOWED_EXTENSIONS = {
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".docx",
        ".xlsx",
        ".xls",
        ".doc",
        ".csv",
        ".txt",
        ".zip",
        ".xml",
    }
    MAX_FILE_SIZE_MB = 100

    def __init__(self):
        cfg = _settings()
        self.use_s3: bool = getattr(cfg, "USE_S3", False)
        self.bucket: str = getattr(cfg, "S3_BUCKET_NAME", "omni-erp")
        self.presigned_expires: int = getattr(cfg, "S3_PRESIGNED_URL_EXPIRES", 3600)

    # ── Métodos públicos ─────────────────────────────────────────────────────

    def upload_file(
        self,
        empresa_id: str,
        carpeta: str,
        filename: str,
        file_obj: BinaryIO,
        content_type: Optional[str] = None,
    ) -> Tuple[str, int]:
        """
        Sube un archivo al bucket y retorna ``(s3_key, size_bytes)``.

        La S3 key generada es:
            ``empresas/{empresa_id}/{carpeta}/{uuid4}_{filename_sanitizado}``

        Args:
            empresa_id   — UUID de la empresa propietaria del archivo.
            carpeta      — Subcarpeta lógica (ej. 'facturas', 'contratos').
            filename     — Nombre original del archivo.
            file_obj     — Objeto file-like (InMemoryUploadedFile, BytesIO, etc.).
            content_type — MIME type. Si es None, se infiere del nombre.

        Returns:
            Tuple (s3_key, size_bytes).

        Raises:
            ValueError  — Si la extensión está bloqueada o el archivo supera
                          el tamaño máximo.
        """
        self._validate_filename(filename)

        safe_name = self._sanitize_filename(filename)
        unique_name = f"{uuid.uuid4().hex}_{safe_name}"
        s3_key = f"empresas/{empresa_id}/{carpeta}/{unique_name}"

        if content_type is None:
            content_type, _ = mimetypes.guess_type(filename)
            content_type = content_type or "application/octet-stream"

        # Leer contenido para medir tamaño
        if hasattr(file_obj, "read"):
            content = file_obj.read()
        else:
            content = file_obj

        size_bytes = len(content)
        self._validate_size(size_bytes, filename)
        self._validate_magic_bytes(content, filename)  # M-SEC-8

        if not self.use_s3:
            logger.debug("StorageService [LOCAL] upload simulado: %s (%d bytes)", s3_key, size_bytes)
            return s3_key, size_bytes

        try:
            client = _get_s3_client()
            self._ensure_bucket(client)
            client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=content,
                ContentType=content_type,
            )
            logger.info("StorageService upload OK: s3://%s/%s (%d bytes)", self.bucket, s3_key, size_bytes)
        except Exception as exc:
            logger.error("StorageService upload FAILED: %s — %s", s3_key, exc)
            raise

        return s3_key, size_bytes

    def generate_presigned_url(
        self,
        s3_key: str,
        expires: Optional[int] = None,
        filename_hint: Optional[str] = None,
    ) -> str:
        """
        Genera una URL pre-firmada para descarga temporal del archivo.

        Args:
            s3_key        — Clave del objeto en S3 (valor almacenado en DB).
            expires       — Segundos de validez. Default: S3_PRESIGNED_URL_EXPIRES.
            filename_hint — Nombre sugerido en el header Content-Disposition.

        Returns:
            URL firmada como string. En modo local retorna una URL ficticia.
        """
        expires = expires or self.presigned_expires

        if not self.use_s3:
            return f"/media/stub/{s3_key}"

        try:
            client = _get_s3_client()
            params: dict = {"Bucket": self.bucket, "Key": s3_key}
            # H-SEC-5: forzar descarga (attachment) siempre, para que el navegador
            # nunca renderice inline contenido potencialmente malicioso (SVG/HTML).
            if filename_hint:
                params["ResponseContentDisposition"] = f'attachment; filename="{filename_hint}"'
            else:
                params["ResponseContentDisposition"] = "attachment"
            url = client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=expires,
            )
            logger.debug("StorageService presigned_url: key=%s expires=%ds", s3_key, expires)
            return url
        except Exception as exc:
            logger.error("StorageService presigned_url FAILED: %s — %s", s3_key, exc)
            raise

    def delete_file(self, s3_key: str) -> bool:
        """
        Elimina un objeto del bucket.

        Returns:
            True si la eliminación fue exitosa (o si está en modo local).
        """
        if not self.use_s3:
            logger.debug("StorageService [LOCAL] delete simulado: %s", s3_key)
            return True

        try:
            client = _get_s3_client()
            client.delete_object(Bucket=self.bucket, Key=s3_key)
            logger.info("StorageService delete OK: s3://%s/%s", self.bucket, s3_key)
            return True
        except Exception as exc:
            logger.error("StorageService delete FAILED: %s — %s", s3_key, exc)
            raise

    def file_exists(self, s3_key: str) -> bool:
        """
        Verifica si un objeto existe en el bucket (usa head_object).

        Returns:
            True si el objeto existe. En modo local siempre retorna True.
        """
        if not self.use_s3:
            return True

        try:
            client = _get_s3_client()
            client.head_object(Bucket=self.bucket, Key=s3_key)
            return True
        except Exception:
            return False

    def get_file_metadata(self, s3_key: str) -> dict:
        """
        Retorna metadatos del objeto (content-type, tamaño, last-modified).

        Returns:
            dict con 'content_type', 'size', 'last_modified'.
            En modo local retorna un dict de stub.
        """
        if not self.use_s3:
            return {"content_type": "application/octet-stream", "size": 0, "last_modified": None}

        try:
            client = _get_s3_client()
            response = client.head_object(Bucket=self.bucket, Key=s3_key)
            return {
                "content_type": response.get("ContentType", "application/octet-stream"),
                "size": response.get("ContentLength", 0),
                "last_modified": response.get("LastModified"),
            }
        except Exception as exc:
            logger.error("StorageService get_metadata FAILED: %s — %s", s3_key, exc)
            raise

    # ── Helpers internos ─────────────────────────────────────────────────────

    # M-SEC-8: firmas (magic bytes) por extensión para los tipos con firma
    # reconocible. Si la extensión está aquí, el contenido DEBE empezar con una
    # de las firmas; así un .pdf/.png que en realidad es HTML/script se rechaza.
    # Los formatos sin firma fiable (csv/txt/xml/doc/xls legacy) no se chequean.
    _MAGIC_SIGNATURES = {
        ".pdf": [b"%PDF"],
        ".png": [b"\x89PNG\r\n\x1a\n"],
        ".jpg": [b"\xff\xd8\xff"],
        ".jpeg": [b"\xff\xd8\xff"],
        ".gif": [b"GIF87a", b"GIF89a"],
        ".webp": [b"RIFF"],  # contenedor RIFF; 'WEBP' va en offset 8
        ".zip": [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"],
        ".docx": [b"PK\x03\x04"],
        ".xlsx": [b"PK\x03\x04"],
    }

    def _validate_magic_bytes(self, content: bytes, filename: str) -> None:
        """M-SEC-8: valida que el contenido coincida con la firma de la extensión."""
        import os as _os

        _, ext = _os.path.splitext(filename.lower())
        firmas = self._MAGIC_SIGNATURES.get(ext)
        if not firmas:
            return  # extensión sin firma fiable — no se valida por magic bytes
        cabecera = content[:16] if isinstance(content, (bytes, bytearray)) else b""
        if not any(cabecera.startswith(f) for f in firmas):
            raise ValueError(
                f"El contenido del archivo no coincide con la extensión '{ext}' "
                "(posible archivo malicioso renombrado)."
            )

    def _validate_filename(self, filename: str) -> None:
        """H-SEC-5: solo se permiten extensiones de la whitelist."""
        _, ext = os.path.splitext(filename.lower())
        if ext not in self.ALLOWED_EXTENSIONS:
            permitidas = ", ".join(sorted(self.ALLOWED_EXTENSIONS))
            raise ValueError(
                f"El tipo de archivo '{ext or '(sin extensión)'}' no está permitido. "
                f"Permitidos: {permitidas}."
            )

    def _validate_size(self, size_bytes: int, filename: str) -> None:
        """Lanza ValueError si el archivo supera MAX_FILE_SIZE_MB."""
        max_bytes = self.MAX_FILE_SIZE_MB * 1024 * 1024
        if size_bytes > max_bytes:
            raise ValueError(
                f"El archivo '{filename}' ({size_bytes // (1024*1024)} MB) "
                f"supera el límite de {self.MAX_FILE_SIZE_MB} MB."
            )

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """
        Limpia el nombre del archivo para usarlo como parte de una S3 key.
        Solo permite alfanuméricos, guiones, puntos y underscores.
        """
        import re

        name, ext = os.path.splitext(filename)
        safe = re.sub(r"[^\w\-.]", "_", name)
        return f"{safe}{ext}"

    def _ensure_bucket(self, client) -> None:
        """Crea el bucket si no existe (útil para MinIO en dev fresh start)."""
        try:
            client.head_bucket(Bucket=self.bucket)
        except Exception:
            try:
                client.create_bucket(Bucket=self.bucket)
                logger.info('StorageService: bucket "%s" creado', self.bucket)
            except Exception as exc:
                # El bucket puede existir ya (race condition) — ignorar
                logger.debug("StorageService _ensure_bucket: %s", exc)
