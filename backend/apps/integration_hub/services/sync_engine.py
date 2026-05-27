"""
SyncEngine — Motor de sincronización del Integration Hub.

Orquesta la ejecución de jobs de sincronización:
1. Obtiene el conector correcto del registry.
2. Llama pull_* o push_* según la entidad y dirección.
3. Aplica deduplicación usando EntidadSincronizada (checksum).
4. Registra resultados en JobSincronizacion y LogDetalleSincronizacion.
5. Actualiza ultimo_sync en ConectorInstancia.

Uso (desde Celery task o view):
    from apps.integration_hub.services.sync_engine import SyncEngine

    engine = SyncEngine()
    resultado = engine.ejecutar_job(job)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone as dj_timezone

from apps.integration_hub.connectors.base import (
    BaseConnector,
    ConnectorConnectionError,
    ConnectorDataError,
    ConnectorNotSupportedError,
    SyncResult,
)
from apps.integration_hub.connectors.registry import registry

if TYPE_CHECKING:
    from apps.integration_hub.models import (
        ConectorInstancia,
        EntidadSincronizada,
        JobSincronizacion,
    )

logger = logging.getLogger(__name__)


class SyncEngine:
    """Motor principal de sincronización."""

    # Mapeo tipo_entidad → método del conector
    PULL_METHODS = {
        "contactos": "pull_contactos",
        "productos": "pull_productos",
        "pedidos_venta": "pull_pedidos_venta",
        "pedidos_compra": "pull_pedidos_compra",
        "facturas_venta": "pull_facturas_venta",
        "pagos": "pull_pagos",
        "inventario": "pull_inventario",
    }

    def ejecutar_job(self, job: "JobSincronizacion") -> SyncResult:
        """
        Ejecuta un job de sincronización completo.

        Actualiza el estado del job en la BD conforme avanza.
        Retorna un SyncResult con los contadores finales.
        """
        from apps.integration_hub.models import JobSincronizacion, LogDetalleSincronizacion

        resultado = SyncResult(tipo_entidad=job.tipo_entidad)

        # Marcar inicio
        job.estado = "en_progreso"
        job.iniciado_en = dj_timezone.now()
        job.save(update_fields=["estado", "iniciado_en"])

        try:
            conector = registry.get_connector(job.id_instancia)
        except Exception as exc:
            self._marcar_fallido(job, str(exc), resultado)
            return resultado

        # Verificar que la entidad esté soportada
        if not conector.supports(job.tipo_entidad):
            msg = (
                f"El conector {conector.PROVIDER_NAME} no soporta "
                f"la entidad '{job.tipo_entidad}'."
            )
            self._marcar_fallido(job, msg, resultado)
            return resultado

        # Determinar desde cuándo sincronizar (incremental)
        desde = self._calcular_desde(job)

        if job.direccion in ("inbound", "bidireccional"):
            resultado = self._ejecutar_pull(job, conector, desde, resultado)

        # outbound no implementado en esta versión (Fase 1)
        if job.direccion == "outbound":
            self._marcar_fallido(
                job,
                "Sincronización outbound no implementada en esta versión.",
                resultado,
            )
            return resultado

        # Completar job
        self._marcar_completado(job, resultado)
        return resultado

    def _ejecutar_pull(
        self,
        job: "JobSincronizacion",
        conector: BaseConnector,
        desde: datetime | None,
        resultado: SyncResult,
    ) -> SyncResult:
        """Ejecuta la fase de pull (externo → Omni)."""
        from apps.integration_hub.models import (
            EntidadSincronizada,
            LogDetalleSincronizacion,
        )

        method_name = self.PULL_METHODS.get(job.tipo_entidad)
        if not method_name:
            resultado.agregar_error("N/A", f"Entidad '{job.tipo_entidad}' sin método pull.")
            return resultado

        method = getattr(conector, method_name)

        try:
            registros = method(desde=desde)
        except (ConnectorConnectionError, ConnectorDataError, ConnectorNotSupportedError) as exc:
            resultado.agregar_error("N/A", str(exc))
            logger.error("Pull error [%s / %s]: %s", job.id_instancia.nombre, job.tipo_entidad, exc)
            return resultado
        except Exception as exc:
            resultado.agregar_error("N/A", f"Error inesperado: {type(exc).__name__}: {exc}")
            logger.exception("Pull inesperado [%s / %s]", job.id_instancia.nombre, job.tipo_entidad)
            return resultado

        resultado.total = len(registros)
        job.total_registros = resultado.total
        job.save(update_fields=["total_registros"])

        logs_batch: list[LogDetalleSincronizacion] = []

        for raw in registros:
            id_externo = str(raw.get("id_externo", ""))
            checksum = raw.get("_checksum", "")

            try:
                # ¿Ya existe este registro sincronizado?
                mapping, creado_mapping = EntidadSincronizada.objects.get_or_create(
                    id_instancia=job.id_instancia,
                    tipo_entidad=job.tipo_entidad,
                    id_externo=id_externo,
                    defaults={"checksum": checksum},
                )

                # Detectar cambios vía checksum
                if not creado_mapping and mapping.checksum == checksum:
                    resultado.omitidos += 1
                    logs_batch.append(LogDetalleSincronizacion(
                        id_job=job,
                        id_externo=id_externo,
                        id_omni=mapping.id_omni or "",
                        operacion="omitir",
                        resumen_externo={"nombre": raw.get("nombre", "")},
                    ))
                    continue

                # Sincronizar en Omni
                id_omni = self._upsert_en_omni(job.tipo_entidad, raw, job.id_instancia)

                if id_omni:
                    # Actualizar mapping
                    with transaction.atomic():
                        mapping.id_omni = id_omni
                        mapping.checksum = checksum
                        mapping.save(update_fields=["id_omni", "checksum", "ultimo_sync"])

                    if creado_mapping:
                        resultado.creados += 1
                        operacion = "crear"
                    else:
                        resultado.actualizados += 1
                        operacion = "actualizar"

                    logs_batch.append(LogDetalleSincronizacion(
                        id_job=job,
                        id_externo=id_externo,
                        id_omni=id_omni,
                        operacion=operacion,
                        resumen_externo={"nombre": raw.get("nombre", "")},
                    ))
                else:
                    resultado.omitidos += 1

            except Exception as exc:
                resultado.agregar_error(id_externo, str(exc))
                logs_batch.append(LogDetalleSincronizacion(
                    id_job=job,
                    id_externo=id_externo,
                    operacion="error",
                    mensaje_error=str(exc)[:500],
                    resumen_externo={"nombre": raw.get("nombre", "")},
                ))
                logger.warning("Error sincronizando %s:%s → %s", job.tipo_entidad, id_externo, exc)

            resultado.procesados = resultado.creados + resultado.actualizados + resultado.omitidos + resultado.fallidos

        # Bulk create logs (eficiencia)
        if logs_batch:
            LogDetalleSincronizacion.objects.bulk_create(logs_batch, batch_size=200)

        return resultado

    def _upsert_en_omni(
        self,
        tipo_entidad: str,
        datos: dict,
        instancia: "ConectorInstancia",
    ) -> str | None:
        """
        Crea o actualiza el registro en Omni según el tipo de entidad.

        Returns:
            ID del registro Omni creado/actualizado, o None si se omitió.

        Nota: En esta versión inicial se registran los datos en el mapa de
        sincronización para trazabilidad. La integración profunda con los
        modelos de Omni (crm.Contacto, inventario.Producto, etc.) se implementa
        por entidad en fases posteriores.
        """
        handlers = {
            "contactos": self._upsert_contacto,
            "productos": self._upsert_producto,
            # Las demás entidades se implementan por fase
        }

        handler = handlers.get(tipo_entidad)
        if handler:
            return handler(datos, instancia)

        # Para entidades sin handler: retornar el id_externo como placeholder
        # y loguear que el dato fue recibido pero no integrado profundamente aún
        logger.debug(
            "Entidad '%s' recibida (id_externo=%s) pero sin handler de upsert activo.",
            tipo_entidad,
            datos.get("id_externo", ""),
        )
        return datos.get("id_externo", "")

    def _upsert_contacto(self, datos: dict, instancia: "ConectorInstancia") -> str | None:
        """
        Upsert de contacto en el CRM de Omni.
        Busca por identificador_fiscal o email; si existe, actualiza; si no, crea.
        """
        try:
            # Intentar importar el modelo del CRM
            from apps.crm.models import Contacto  # type: ignore
        except ImportError:
            # El módulo CRM aún no tiene el modelo Contacto unificado (Fase 1 M1)
            # Retornar el id_externo para que el mapping quede registrado
            return datos.get("id_externo", "")

        empresa = instancia.id_empresa
        id_fiscal = datos.get("identificador_fiscal") or ""
        email = datos.get("email") or ""

        # Buscar existente
        contacto = None
        if id_fiscal:
            contacto = Contacto.objects.filter(
                id_empresa=empresa, identificador_fiscal=id_fiscal
            ).first()
        if not contacto and email:
            contacto = Contacto.objects.filter(
                id_empresa=empresa, email=email
            ).first()

        campos = {
            "nombre": datos.get("nombre") or "",
            "email": email,
            "telefono": datos.get("telefono") or "",
            "movil": datos.get("movil") or "",
            "es_cliente": datos.get("es_cliente", False),
            "es_proveedor": datos.get("es_proveedor", False),
            "identificador_fiscal": id_fiscal,
            "direccion": datos.get("direccion") or "",
            "ciudad": datos.get("ciudad") or "",
            "notas": datos.get("notas") or "",
        }

        with transaction.atomic():
            if contacto:
                for field, value in campos.items():
                    setattr(contacto, field, value)
                contacto.save()
                return str(contacto.pk)
            else:
                nuevo = Contacto.objects.create(id_empresa=empresa, **campos)
                return str(nuevo.pk)

    def _upsert_producto(self, datos: dict, instancia: "ConectorInstancia") -> str | None:
        """
        Upsert de producto en el inventario de Omni.
        Busca por codigo_interno o nombre; si existe, actualiza; si no, crea.
        """
        try:
            from apps.inventario.models import Producto  # type: ignore
        except ImportError:
            return datos.get("id_externo", "")

        empresa = instancia.id_empresa
        codigo = datos.get("codigo_interno") or ""

        producto = None
        if codigo:
            producto = Producto.objects.filter(
                id_empresa=empresa, codigo_interno=codigo
            ).first()

        campos = {
            "nombre": datos.get("nombre") or "",
            "codigo_interno": codigo,
            "descripcion": datos.get("descripcion_venta") or "",
            "precio_venta": datos.get("precio_venta") or 0,
            "costo": datos.get("costo") or 0,
        }

        with transaction.atomic():
            if producto:
                for field, value in campos.items():
                    setattr(producto, field, value)
                producto.save()
                return str(producto.pk)
            else:
                nuevo = Producto.objects.create(id_empresa=empresa, **campos)
                return str(nuevo.pk)

    def _calcular_desde(self, job: "JobSincronizacion") -> datetime | None:
        """
        Calcula desde qué fecha sincronizar para sync incremental.
        Usa el último sync exitoso de esta entidad en la instancia.
        """
        if job.parametros.get("desde"):
            try:
                return datetime.fromisoformat(job.parametros["desde"])
            except (ValueError, TypeError):
                pass

        # Buscar el último job completado para esta entidad
        from apps.integration_hub.models import JobSincronizacion as Job
        ultimo = (
            Job.objects.filter(
                id_instancia=job.id_instancia,
                tipo_entidad=job.tipo_entidad,
                estado__in=["completado", "completado_con_errores"],
                completado_en__isnull=False,
            )
            .exclude(pk=job.pk)
            .order_by("-completado_en")
            .first()
        )

        return ultimo.completado_en if ultimo else None

    def _marcar_completado(
        self, job: "JobSincronizacion", resultado: SyncResult
    ) -> None:
        """Actualiza el job con los contadores finales."""
        job.estado = "completado" if resultado.exitoso else "completado_con_errores"
        job.completado_en = dj_timezone.now()
        job.total_registros = resultado.total
        job.procesados = resultado.procesados
        job.creados = resultado.creados
        job.actualizados = resultado.actualizados
        job.omitidos = resultado.omitidos
        job.fallidos = resultado.fallidos
        job.resumen_errores = resultado.errores[:50]
        job.save()

        # Actualizar último sync en la instancia
        job.id_instancia.ultimo_sync = dj_timezone.now()
        job.id_instancia.estado = "activo"
        job.id_instancia.save(update_fields=["ultimo_sync", "estado"])

        logger.info(
            "Job completado [%s / %s]: creados=%s actualizados=%s omitidos=%s fallidos=%s",
            job.id_instancia.nombre,
            job.tipo_entidad,
            resultado.creados,
            resultado.actualizados,
            resultado.omitidos,
            resultado.fallidos,
        )

    def _marcar_fallido(
        self, job: "JobSincronizacion", mensaje: str, resultado: SyncResult
    ) -> None:
        """Marca el job como fallido con mensaje de error."""
        job.estado = "fallido"
        job.completado_en = dj_timezone.now()
        job.resumen_errores = [{"error": mensaje}]
        job.save()

        job.id_instancia.estado = "error"
        job.id_instancia.mensaje_estado = mensaje[:500]
        job.id_instancia.save(update_fields=["estado", "mensaje_estado"])

        logger.error("Job fallido [%s]: %s", job.id_instancia.nombre, mensaje)
