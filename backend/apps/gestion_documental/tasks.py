"""
Tareas Celery del módulo gestion_documental.

La eliminación de archivos en S3 se hace de forma asíncrona para no
bloquear las requests HTTP. Si S3 está temporalmente caído, la tarea
se reintenta con backoff exponencial.
"""
from __future__ import annotations

import logging
from typing import Optional

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name='gestion_documental.eliminar_archivo_s3',
    bind=True,
    max_retries=5,
    default_retry_delay=30,   # 30s → 60s → 120s → 240s → 480s
    acks_late=True,
)
def eliminar_archivo_s3(
    self,
    s3_key: str,
    documento_id: Optional[str] = None,
) -> dict:
    """
    Elimina un archivo del bucket S3 de forma asíncrona.

    Se llama después de borrar el registro Documento de la DB.
    Si el objeto ya no existe en S3 (double-delete), se considera exitoso.

    Args:
        s3_key       — Clave S3 del objeto a eliminar.
        documento_id — UUID del Documento ya eliminado de DB (solo para logging).

    Returns:
        dict con s3_key y resultado.
    """
    from apps.core.storage import StorageService

    logger.info(
        'gestion_documental.eliminar_archivo_s3 iniciado — key=%s doc_id=%s task=%s',
        s3_key, documento_id, self.request.id,
    )

    storage = StorageService()

    try:
        storage.delete_file(s3_key)
        logger.info(
            'gestion_documental.eliminar_archivo_s3 OK — key=%s',
            s3_key,
        )
        return {'task_id': self.request.id, 's3_key': s3_key, 'status': 'deleted'}

    except Exception as exc:
        logger.warning(
            'gestion_documental.eliminar_archivo_s3 fallo (intento %d): %s — %s',
            self.request.retries + 1, s3_key, exc,
        )
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


@shared_task(
    name='gestion_documental.limpiar_archivos_huerfanos',
    bind=True,
    max_retries=2,
)
def limpiar_archivos_huerfanos(self, empresa_id: str) -> dict:
    """
    Tarea periódica: lista objetos en S3 bajo empresas/{empresa_id}/ y
    elimina los que no tienen registro correspondiente en Documento.

    Solo se ejecuta vía django-celery-beat (schedule administrable desde Admin).
    No elimina objetos subidos en las últimas 24h (ventana de seguridad).

    Args:
        empresa_id — UUID de la empresa a limpiar.

    Returns:
        dict con conteo de objetos analizados y eliminados.
    """
    from datetime import datetime, timedelta, timezone as tz
    from apps.gestion_documental.models import Documento
    from apps.core.storage import StorageService, _get_s3_client
    from django.conf import settings

    if not getattr(settings, 'USE_S3', False):
        logger.debug('limpiar_archivos_huerfanos: USE_S3=False, nada que hacer.')
        return {'analizado': 0, 'eliminado': 0}

    prefix = f"empresas/{empresa_id}/"
    ventana_seguridad = datetime.now(tz=tz.utc) - timedelta(hours=24)

    storage = StorageService()
    client = _get_s3_client()

    paginator = client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=storage.bucket, Prefix=prefix)

    rutas_en_db = set(
        Documento.objects.filter(
            id_empresa_id=empresa_id
        ).values_list('ruta_almacenamiento', flat=True)
    )

    analizado = 0
    eliminado = 0

    for page in pages:
        for obj in page.get('Contents', []):
            key = obj['Key']
            last_modified = obj.get('LastModified')
            analizado += 1

            # No tocar archivos recientes
            if last_modified and last_modified > ventana_seguridad:
                continue

            if key not in rutas_en_db:
                try:
                    client.delete_object(Bucket=storage.bucket, Key=key)
                    eliminado += 1
                    logger.info('limpiar_archivos_huerfanos: eliminado %s', key)
                except Exception as exc:
                    logger.warning('limpiar_archivos_huerfanos: error eliminando %s: %s', key, exc)

    logger.info(
        'limpiar_archivos_huerfanos: empresa=%s analizado=%d eliminado=%d',
        empresa_id, analizado, eliminado,
    )
    return {'empresa_id': empresa_id, 'analizado': analizado, 'eliminado': eliminado}
