"""Tareas Celery del subproyecto CxC Lubrikca.

Sincronización **periódica** del espejo desde Odoo (PLAN_TRABAJO Fase 5 — "Sync
programado"). Reusa la infraestructura D2 de Omni: el conjunto de tenants a
sincronizar es el mismo de la cobranza Mode-A (``ParametroSistema``
``cxc.datasource = 'odoo'``), igual que ``integration_hub.sync_cartera_odoo_todos``.

El **cronograma** (cada cuántos minutos) se registra operativamente vía
django-celery-beat (misma convención que el resto del ERP); ver
``docs/cxc-lubrikca/CHECKLIST_GO_LIVE.md``. La tarea es solo lectura de Odoo y
nunca toca las tablas de trabajo humano (Vinculacion/Bandeja/Conciliacion).
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="cxc_lubrikca.sync_todos")
def sync_cxc_lubrikca_todos():
    """Fan-out periódico: encola la sync de cada tenant Mode-A (datasource=odoo)."""
    from apps.configuracion_motor.models import ParametroSistema

    params = ParametroSistema.objects.filter(
        codigo_parametro="cxc.datasource",
        activo=True,
        id_empresa__isnull=False,
    )
    disparados = 0
    for p in params:
        if (p.valor_parametro or "").strip().lower() == "odoo":
            sync_cxc_lubrikca.delay(str(p.id_empresa_id))
            disparados += 1

    logger.info("cxc_lubrikca.sync_todos: %d tenants Odoo encolados", disparados)
    return {"tenants_odoo": disparados}


@shared_task(name="cxc_lubrikca.sync")
def sync_cxc_lubrikca(empresa_id: str):
    """Sincroniza el espejo de una empresa desde Odoo (solo lectura).

    Tolerante a fallos: cualquier error (sin conector, Odoo caído, etc.) se loguea
    y se devuelve como dict — nunca tumba el worker ni reintenta a ciegas.
    """
    try:
        from apps.core.models import Empresa
        from apps.cxc_lubrikca.services.sync import sincronizar_empresa

        empresa = Empresa.objects.get(pk=empresa_id)
        conteos = sincronizar_empresa(empresa)
        logger.info("cxc_lubrikca.sync: empresa=%s conteos=%s", empresa_id, conteos)
        return {"empresa_id": empresa_id, **conteos}
    except Exception as exc:  # noqa: BLE001 — el worker no debe morir por un tenant
        logger.exception("cxc_lubrikca.sync error empresa=%s: %s", empresa_id, exc)
        return {"empresa_id": empresa_id, "error": str(exc)}
