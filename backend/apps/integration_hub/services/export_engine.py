"""
ExportEngine — orquesta exportaciones outbound (origen → destino).

Lee entidades canónicas de un conector de ORIGEN (p. ej. Odoo) con ``pull_*`` y
las escribe en un conector de DESTINO (p. ej. Google Sheets) vía
``push_entidades()``. Registra un ``JobSincronizacion`` (``direccion="outbound"``)
por entidad, con sus contadores.

Complementa al ``SyncEngine`` (que cubre el flujo inbound externo → Omni). Aquí
el dato fluye de un sistema a otro **en forma canónica**, sin acoplar el destino
a la API del origen (ADR-003).

Multi-tenant (R-CODE-1): origen y destino deben pertenecer a la MISMA empresa.

Uso::

    from apps.integration_hub.services.export_engine import ExportEngine
    jobs = ExportEngine().exportar(instancia_sheets, tipos=["contactos", "productos"])
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.utils import timezone as dj_timezone

from apps.integration_hub.connectors.base import ConnectorError, SyncResult
from apps.integration_hub.connectors.registry import registry

if TYPE_CHECKING:
    from apps.integration_hub.models import ConectorInstancia, JobSincronizacion

logger = logging.getLogger(__name__)


class ExportEngine:
    """Motor de exportación outbound (lee de un origen, escribe en un destino)."""

    # Límite de registros por entidad y corrida (override: config 'limite_export').
    LIMITE_EXPORT = 5000

    # Mapeo tipo_entidad → método pull_* del conector de origen.
    SOURCE_PULL = {
        "contactos": "pull_contactos",
        "productos": "pull_productos",
        "pedidos_venta": "pull_pedidos_venta",
        "pedidos_compra": "pull_pedidos_compra",
        "facturas_venta": "pull_facturas_venta",
        "pagos": "pull_pagos",
        "inventario": "pull_inventario",
    }

    def exportar(
        self,
        instancia_destino: "ConectorInstancia",
        tipos: list[str] | None = None,
        iniciado_por=None,
        incremental: bool = True,
    ) -> list["JobSincronizacion"]:
        """
        Exporta las entidades indicadas (o ``entidades_activas`` del destino).

        Devuelve la lista de ``JobSincronizacion`` creados (uno por entidad).
        Lanza ``ConnectorError`` si el origen no está configurado o es de otra
        empresa (antes de crear ningún job).
        """
        from apps.integration_hub.models import ConectorInstancia

        destino = registry.get_connector(instancia_destino)
        origen_inst = self._resolver_origen(instancia_destino, ConectorInstancia)
        origen = registry.get_connector(origen_inst)

        entidades = tipos or list(instancia_destino.entidades_activas or [])
        jobs: list["JobSincronizacion"] = []
        for tipo in entidades:
            jobs.append(
                self._ejecutar_entidad(
                    instancia_destino,
                    origen_inst,
                    origen,
                    destino,
                    tipo,
                    iniciado_por,
                    incremental,
                )
            )

        self._persistir_spreadsheet_id(instancia_destino, destino)
        return jobs

    # ── Internos ─────────────────────────────────────────────────────────────

    def _resolver_origen(self, instancia_destino, ConectorInstancia):
        cfg = instancia_destino.get_config()
        source_id = cfg.get("source_instancia_id")
        if not source_id:
            raise ConnectorError(
                "El conector de destino no tiene 'source_instancia_id' configurado "
                "(la instancia origen de la que exportar, p. ej. el conector Odoo)."
            )
        try:
            origen = ConectorInstancia.objects.get(pk=source_id)
        except ConectorInstancia.DoesNotExist as exc:
            raise ConnectorError(
                f"La instancia origen '{source_id}' no existe."
            ) from exc
        # R-CODE-1: aislamiento multi-tenant estricto.
        if origen.id_empresa_id != instancia_destino.id_empresa_id:
            raise ConnectorError(
                "La instancia origen pertenece a otra empresa (aislamiento multi-tenant)."
            )
        return origen

    def _ejecutar_entidad(
        self,
        instancia_destino,
        origen_inst,
        origen,
        destino,
        tipo,
        iniciado_por,
        incremental,
    ):
        from apps.integration_hub.models import JobSincronizacion

        job = JobSincronizacion.objects.create(
            id_instancia=instancia_destino,
            tipo_entidad=tipo,
            direccion="outbound",
            estado="en_progreso",
            iniciado_en=dj_timezone.now(),
            iniciado_por=iniciado_por,
            parametros={"origen": str(origen_inst.pk)},
        )

        metodo = self.SOURCE_PULL.get(tipo)
        if not metodo or not hasattr(origen, metodo):
            self._fallar(
                job, f"El conector de origen no sabe leer la entidad '{tipo}'."
            )
            return job
        if not destino.supports(tipo):
            self._fallar(job, f"El destino no soporta exportar la entidad '{tipo}'.")
            return job

        desde = self._calcular_desde(job) if incremental else None
        # Los pull_* del origen tienen límites por defecto bajos (200-500);
        # sin un límite generoso, lo que exceda se perdería y el sync
        # incremental nunca lo recuperaría (desde avanza igual).
        limite = int(
            instancia_destino.get_config().get("limite_export", self.LIMITE_EXPORT)
        )
        try:
            registros = getattr(origen, metodo)(desde=desde, limite=limite)
            # Omni como hub: además de exportar, persistimos la data en los
            # modelos canónicos de Omni (Odoo → Omni → Sheets), salvo que la
            # config lo desactive con persistir_en_omni=False.
            persistencia = self._persistir_en_omni(
                instancia_destino, origen_inst, tipo, registros
            )
            resultado = destino.push_entidades(tipo, registros)
        except Exception as exc:
            self._fallar(job, f"{type(exc).__name__}: {exc}")
            return job

        if persistencia is not None:
            # Trazabilidad: dejamos el resumen de lo persistido en Omni en los
            # parámetros del job (visible en el historial).
            job.parametros = {**(job.parametros or {}), "omni_persistencia": persistencia}

        if limite and len(registros) >= limite:
            # Posible truncamiento: marcarlo como error visible para que el
            # operador re-ejecute (o suba 'limite_export') y no pierda datos.
            resultado.agregar_error(
                "N/A",
                f"El origen devolvió {len(registros)} registros (límite "
                f"{limite}): puede haber datos sin exportar. Re-ejecuta la "
                "exportación o sube 'limite_export' en la configuración.",
            )

        self._completar(job, resultado)
        return job

    def _persistir_en_omni(self, instancia_destino, origen_inst, tipo, registros):
        """
        Persiste los registros canónicos en los modelos de Omni vía el
        ``SyncEngine`` (Omni como hub/traductor). Devuelve el resumen de
        contadores, o ``None`` si está desactivado por config.

        Best-effort: si la persistencia falla, NO rompe la exportación al
        destino (el flujo a Sheets debe seguir funcionando). El error se
        registra en el resumen para trazabilidad.
        """
        if not instancia_destino.get_config().get("persistir_en_omni", True):
            return None

        from apps.integration_hub.services.sync_engine import SyncEngine

        try:
            return SyncEngine().ingerir_en_omni(origen_inst, tipo, registros)
        except Exception as exc:  # nunca tumbar la exportación por esto
            logger.exception(
                "Persistencia en Omni falló [%s/%s] — la exportación continúa",
                instancia_destino.nombre,
                tipo,
            )
            return {"error": f"{type(exc).__name__}: {exc}"}

    def _calcular_desde(self, job):
        from apps.integration_hub.models import JobSincronizacion as Job

        ultimo = (
            Job.objects.filter(
                id_instancia=job.id_instancia,
                tipo_entidad=job.tipo_entidad,
                direccion="outbound",
                estado__in=["completado", "completado_con_errores"],
                completado_en__isnull=False,
            )
            .exclude(pk=job.pk)
            .order_by("-completado_en")
            .first()
        )
        return ultimo.completado_en if ultimo else None

    def _persistir_spreadsheet_id(self, instancia_destino, destino):
        """Guarda el spreadsheet_id si el destino auto-creó la planilla."""
        nuevo_id = getattr(destino, "spreadsheet_id", "")
        cfg = instancia_destino.get_config()
        if nuevo_id and cfg.get("spreadsheet_id") != nuevo_id:
            cfg = dict(cfg)
            cfg["spreadsheet_id"] = nuevo_id
            instancia_destino.configuracion = cfg
            instancia_destino.save(update_fields=["configuracion"])

    def _completar(self, job, resultado: SyncResult):
        job.estado = "completado" if resultado.exitoso else "completado_con_errores"
        job.completado_en = dj_timezone.now()
        job.total_registros = resultado.total
        job.creados = resultado.creados
        job.actualizados = resultado.actualizados
        job.omitidos = resultado.omitidos
        job.fallidos = resultado.fallidos
        job.procesados = (
            resultado.creados
            + resultado.actualizados
            + resultado.omitidos
            + resultado.fallidos
        )
        job.resumen_errores = resultado.errores[:50]
        job.save()

        job.id_instancia.ultimo_sync = dj_timezone.now()
        job.id_instancia.estado = "activo"
        job.id_instancia.save(update_fields=["ultimo_sync", "estado"])
        logger.info(
            "Export %s [%s]: creados=%s actualizados=%s omitidos=%s fallidos=%s",
            job.tipo_entidad,
            job.id_instancia.nombre,
            resultado.creados,
            resultado.actualizados,
            resultado.omitidos,
            resultado.fallidos,
        )

    def _fallar(self, job, mensaje: str):
        job.estado = "fallido"
        job.completado_en = dj_timezone.now()
        job.resumen_errores = [{"error": mensaje[:500]}]
        job.save()
        logger.error(
            "Export fallido [%s/%s]: %s",
            job.id_instancia.nombre,
            job.tipo_entidad,
            mensaje,
        )
