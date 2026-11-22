"""Tareas Celery periódicas de Omni Connect (Plan 07 S10).

Purga registros ``connect.Toque`` más antiguos que la ventana de retención
configurada (``CONNECT_TOQUES_RETENCION_DIAS``, default 365 días), aislando cada
tenant con ``rls_tenant_context`` y eliminando en lotes pequeños sin bloquear.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("apps.connect.tasks")

_BATCH_SIZE_DEFAULT = 1000
_BATCH_SIZE_MAX = 5000


@shared_task(
    name="connect.purgar_toques_antiguos",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def purgar_toques_antiguos(
    self,
    *,
    dias_retencion: int | None = None,
    batch_size: int = _BATCH_SIZE_DEFAULT,
) -> dict[str, int]:
    """Elimina en lotes los ``Toque`` vencidos por tenant bajo RLS fail-closed."""
    from apps.core import rls  # noqa: PLC0415
    from apps.core.models import Empresa  # noqa: PLC0415

    from .models import Toque  # noqa: PLC0415

    dias_cfg = getattr(settings, "CONNECT_TOQUES_RETENCION_DIAS", 365)
    dias_efectivos = max(1, int(dias_cfg if dias_retencion is None else dias_retencion))
    lote = max(1, min(int(batch_size), _BATCH_SIZE_MAX))
    cutoff = timezone.now() - timedelta(days=dias_efectivos)

    with rls.rls_bypass():
        empresa_ids = list(Empresa.objects.filter(activo=True).values_list("id_empresa", flat=True))

    empresas_procesadas = 0
    toques_eliminados = 0
    errores = 0

    for empresa_id in empresa_ids:
        try:
            eliminados_empresa = 0
            with rls.rls_tenant_context([empresa_id]):
                while True:
                    ids_lote = list(
                        Toque.objects.filter(
                            id_empresa_id=empresa_id,
                            fecha_toque__lt=cutoff,
                        )
                        .order_by("fecha_toque", "pk")
                        .values_list("pk", flat=True)[:lote]
                    )
                    if not ids_lote:
                        break
                    borrados, _ = Toque.objects.filter(
                        id_empresa_id=empresa_id,
                        pk__in=ids_lote,
                    ).delete()
                    eliminados_empresa += borrados

            empresas_procesadas += 1
            toques_eliminados += eliminados_empresa
            if eliminados_empresa > 0:
                logger.info(
                    "connect.purgar_toques_antiguos | empresa=%s | eliminados=%d | dias=%d",
                    empresa_id,
                    eliminados_empresa,
                    dias_efectivos,
                )
        except Exception:  # noqa: BLE001 — aislamiento por tenant: no detiene al resto
            errores += 1
            logger.exception("Error purgando toques antiguos de Connect para empresa %s", empresa_id)

    logger.info(
        "connect.purgar_toques_antiguos completada | empresas=%d | eliminados=%d | errores=%d | dias=%d",
        empresas_procesadas,
        toques_eliminados,
        errores,
        dias_efectivos,
    )
    return {
        "empresas_procesadas": empresas_procesadas,
        "toques_eliminados": toques_eliminados,
        "errores": errores,
        "dias_retencion": dias_efectivos,
    }
