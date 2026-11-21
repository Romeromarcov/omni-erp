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
from datetime import datetime
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
        "facturas_compra": "pull_facturas_compra",
        "pagos": "pull_pagos",
        "inventario": "pull_inventario",
    }

    def ejecutar_job(self, job: "JobSincronizacion") -> SyncResult:
        """
        Ejecuta un job de sincronización completo.

        Actualiza el estado del job en la BD conforme avanza.
        Retorna un SyncResult con los contadores finales.
        """

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
            msg = f"El conector {conector.PROVIDER_NAME} no soporta " f"la entidad '{job.tipo_entidad}'."
            self._marcar_fallido(job, msg, resultado)
            return resultado

        # Determinar desde cuándo sincronizar (incremental)
        desde = self._calcular_desde(job)

        if job.direccion in ("inbound", "bidireccional"):
            resultado = self._ejecutar_pull(job, conector, desde, resultado)
            job.refresh_from_db(fields=["estado"])
            if job.estado == "fallido":
                # El pull falló de raíz (sin método, conexión caída, etc.):
                # _ejecutar_pull ya marcó el job; no sobreescribir con 'completado'.
                return resultado

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

    def ingerir_en_omni(
        self,
        instancia: "ConectorInstancia",
        tipo_entidad: str,
        registros: list[dict],
    ) -> dict:
        """
        Persiste una lista de registros canónicos en los modelos de Omni,
        reutilizando la deduplicación por checksum (``EntidadSincronizada``) y
        ``_upsert_en_omni`` — sin necesidad de un ``JobSincronizacion``.

        Pensado para que el ``ExportEngine`` (flujo origen → destino) también
        deje la data almacenada en Omni con su estructura canónica: el dato
        fluye Odoo → **Omni** → Sheets, no Odoo → Sheets directo. Así la empresa
        va acumulando su histórico en Omni de cara a una futura migración.

        El mapeo se atribuye a la ``instancia`` de ORIGEN (de donde provienen los
        datos), de modo que un sync inbound posterior reutilice el mismo enlace
        externo↔Omni. Multi-tenant: ``_upsert_en_omni`` acota a ``instancia.id_empresa``.

        Es *best-effort por registro*: un error en uno no aborta el resto.

        Returns:
            dict con contadores: ``creados``, ``actualizados``, ``omitidos``,
            ``fallidos`` y ``errores`` (lista acotada a 50).
        """
        from apps.integration_hub.models import EntidadSincronizada

        res = {
            "creados": 0,
            "actualizados": 0,
            "omitidos": 0,
            "fallidos": 0,
            "errores": [],
        }

        for raw in registros:
            id_externo = str(raw.get("id_externo", ""))
            checksum = raw.get("_checksum", "")
            try:
                mapping, creado = EntidadSincronizada.objects.get_or_create(
                    id_instancia=instancia,
                    tipo_entidad=tipo_entidad,
                    id_externo=id_externo,
                    defaults={"checksum": checksum},
                )

                # Sin cambios desde la última vez: omitir (idéntico a _ejecutar_pull).
                if not creado and mapping.checksum == checksum:
                    res["omitidos"] += 1
                    continue

                id_omni = self._upsert_en_omni(tipo_entidad, raw, instancia)
                if id_omni:
                    with transaction.atomic():
                        mapping.id_omni = id_omni
                        mapping.checksum = checksum
                        mapping.save(update_fields=["id_omni", "checksum", "ultimo_sync"])
                    res["creados" if creado else "actualizados"] += 1
                else:
                    res["omitidos"] += 1
            except Exception as exc:  # best-effort: no abortar el lote
                res["fallidos"] += 1
                if len(res["errores"]) < 50:
                    res["errores"].append({"id_externo": id_externo, "error": str(exc)[:300]})
                logger.warning("ingerir_en_omni %s:%s → %s", tipo_entidad, id_externo, exc)

        return res

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
            msg = f"Entidad '{job.tipo_entidad}' sin método pull."
            resultado.agregar_error("N/A", msg)
            self._marcar_fallido(job, msg, resultado)
            return resultado

        method = getattr(conector, method_name)

        try:
            registros = method(desde=desde)
        except (ConnectorConnectionError, ConnectorDataError, ConnectorNotSupportedError) as exc:
            resultado.agregar_error("N/A", str(exc))
            logger.error("Pull error [%s / %s]: %s", job.id_instancia.nombre, job.tipo_entidad, exc)
            self._marcar_fallido(job, str(exc), resultado)
            return resultado
        except Exception as exc:
            msg = f"Error inesperado: {type(exc).__name__}: {exc}"
            resultado.agregar_error("N/A", msg)
            logger.exception("Pull inesperado [%s / %s]", job.id_instancia.nombre, job.tipo_entidad)
            self._marcar_fallido(job, msg, resultado)
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
                    logs_batch.append(
                        LogDetalleSincronizacion(
                            id_job=job,
                            id_externo=id_externo,
                            id_omni=mapping.id_omni or "",
                            operacion="omitir",
                            resumen_externo={"nombre": raw.get("nombre", "")},
                        )
                    )
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

                    logs_batch.append(
                        LogDetalleSincronizacion(
                            id_job=job,
                            id_externo=id_externo,
                            id_omni=id_omni,
                            operacion=operacion,
                            resumen_externo={"nombre": raw.get("nombre", "")},
                        )
                    )
                else:
                    resultado.omitidos += 1

            except Exception as exc:
                resultado.agregar_error(id_externo, str(exc))
                logs_batch.append(
                    LogDetalleSincronizacion(
                        id_job=job,
                        id_externo=id_externo,
                        operacion="error",
                        mensaje_error=str(exc)[:500],
                        resumen_externo={"nombre": raw.get("nombre", "")},
                    )
                )
                logger.warning("Error sincronizando %s:%s → %s", job.tipo_entidad, id_externo, exc)

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
            "pedidos_venta": self._upsert_pedido_venta,
            "pedidos_compra": self._upsert_pedido_compra,
            "facturas_venta": self._upsert_factura_venta,
            "facturas_compra": self._upsert_factura_compra,
            "pagos": self._upsert_pago,
            "inventario": self._upsert_inventario,
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
        Upsert de contacto contra el modelo unificado ``core.Contacto``.
        Busca por identificador fiscal (rif) o email; si existe, actualiza;
        si no, crea. Siempre acotado a la empresa de la instancia (R-CODE-1).
        """
        from apps.core.models import Contacto

        empresa = instancia.id_empresa
        id_fiscal = datos.get("identificador_fiscal") or ""
        email = datos.get("email") or ""

        # Buscar existente (siempre dentro del tenant)
        contacto = None
        if id_fiscal:
            contacto = Contacto.objects.filter(id_empresa=empresa, rif=id_fiscal).first()
        if not contacto and email:
            contacto = Contacto.objects.filter(id_empresa=empresa, email=email).first()

        campos = {
            "nombre": datos.get("nombre") or "",
            "email": email,
            "telefono": datos.get("telefono") or datos.get("movil") or "",
            "es_cliente": datos.get("es_cliente", False),
            "es_proveedor": datos.get("es_proveedor", False),
            "rif": id_fiscal,
            "direccion_fiscal": datos.get("direccion") or "",
        }

        with transaction.atomic():
            if contacto:
                for field, value in campos.items():
                    setattr(contacto, field, value)
                contacto.save()
                return str(contacto.pk)
            nuevo = Contacto.objects.create(id_empresa=empresa, **campos)
            return str(nuevo.pk)

    def _upsert_producto(self, datos: dict, instancia: "ConectorInstancia") -> str | None:
        """
        Upsert de producto en el inventario de Omni (modelo real ``Producto``).
        Busca por sku (codigo_interno externo); si existe, actualiza; si no, crea.

        Si la empresa no tiene una moneda utilizable para ``id_moneda_precio``
        (FK obligatoria), el registro se omite (return None) y se loguea —
        nunca se crea un producto inválido.
        """
        from decimal import Decimal, InvalidOperation

        from apps.finanzas.models import Moneda
        from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida

        empresa = instancia.id_empresa
        sku = datos.get("codigo_interno") or datos.get("sku") or ""

        def _decimal(valor) -> Decimal:
            try:
                return Decimal(str(valor))
            except (InvalidOperation, TypeError, ValueError):
                return Decimal("0")

        producto = None
        if sku:
            producto = Producto.objects.filter(id_empresa=empresa, sku=sku).first()
        else:
            # Sin SKU externo: la clave de idempotencia cae al nombre dentro
            # del tenant, para que re-sincronizar no duplique el producto.
            nombre = datos.get("nombre") or ""
            if nombre:
                producto = Producto.objects.filter(id_empresa=empresa, nombre_producto=nombre).first()

        campos = {
            "nombre_producto": datos.get("nombre") or "",
            "sku": sku or None,
            "descripcion": datos.get("descripcion_venta") or datos.get("descripcion") or "",
            "precio_venta_sugerido": _decimal(datos.get("precio_venta") or 0),
            "costo_promedio": _decimal(datos.get("costo") or 0),
        }

        with transaction.atomic():
            if producto:
                for field, value in campos.items():
                    setattr(producto, field, value)
                producto.save()
                return str(producto.pk)

            # FKs obligatorias del modelo real: resolver defaults del tenant.
            moneda = (
                Moneda.objects.filter(codigo_iso=datos.get("moneda")).first()
                or Moneda.objects.filter(codigo_iso="USD").first()
                or Moneda.objects.first()
            )
            if moneda is None:
                logger.warning(
                    "Producto externo %s omitido: no hay Moneda configurada para " "id_moneda_precio (empresa %s).",
                    datos.get("id_externo", ""),
                    empresa.pk,
                )
                return None

            categoria, _ = CategoriaProducto.objects.get_or_create(
                id_empresa=empresa,
                nombre_categoria="Importados (Integration Hub)",
                defaults={"descripcion": "Productos creados por sincronización externa."},
            )
            unidad, _ = UnidadMedida.objects.get_or_create(
                id_empresa=empresa,
                abreviatura="UND",
                defaults={"nombre": "Unidad", "tipo": "CANTIDAD"},
            )

            nuevo = Producto.objects.create(
                id_empresa=empresa,
                id_categoria=categoria,
                id_unidad_medida_base=unidad,
                id_moneda_precio=moneda,
                **campos,
            )
            return str(nuevo.pk)

    # ── Pedidos de venta (Fase 2) ──────────────────────────────────────────────

    @staticmethod
    def _safe_decimal_money(valor):
        """Convierte a Decimal en la frontera externa (R-CODE-4). 0 si inválido."""
        from decimal import Decimal, InvalidOperation

        try:
            return Decimal(str(valor))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0")

    @staticmethod
    def _resolver_moneda_para_empresa(empresa, codigo_iso: str | None):
        """Resuelve una ``Moneda`` activa visible para ``empresa`` (nunca de otro tenant)."""
        from django.db.models import Q

        from apps.finanzas.models import Moneda

        visibles = Moneda.objects.filter(
            Q(empresa=empresa) | Q(empresa__isnull=True) | Q(es_publica=True),
            activo=True,
        ).order_by("-es_publica", "id_moneda")
        codigo = (codigo_iso or "").strip()
        if codigo:
            exacta = visibles.filter(codigo_iso__iexact=codigo).first()
            if exacta is not None:
                return exacta
        return visibles.filter(codigo_iso="USD").first() or visibles.first()

    def _asegurar_contacto_de_tercero(
        self,
        tercero,
        instancia: "ConectorInstancia",
        *,
        id_externo: str = "",
        es_cliente: bool = False,
        es_proveedor: bool = False,
    ):
        """Garantiza que ``Cliente``/``Proveedor`` tenga un ``core.Contacto`` enlazado en el tenant."""
        from apps.core.models import Contacto
        from apps.crm.models import Cliente
        from apps.integration_hub.models import EntidadSincronizada
        from apps.proveedores.models import Proveedor

        empresa = instancia.id_empresa
        ext = (id_externo or "").strip()
        contacto = getattr(tercero, "contacto", None)
        if contacto is not None and contacto.id_empresa_id != empresa.pk:
            contacto = None

        if contacto is None and ext:
            mapping = EntidadSincronizada.objects.filter(
                id_instancia=instancia, tipo_entidad="contactos", id_externo=ext
            ).first()
            if mapping and mapping.id_omni:
                contacto = Contacto.objects.filter(pk=mapping.id_omni, id_empresa=empresa).first()

        rif_tercero = (getattr(tercero, "rif", "") or "").strip()
        if contacto is None and rif_tercero:
            contacto = Contacto.objects.filter(id_empresa=empresa, rif=rif_tercero).first()

        if contacto is None:
            contacto = Contacto.objects.create(
                id_empresa=empresa,
                nombre=(getattr(tercero, "razon_social", "") or f"Contacto {ext or tercero.pk}").strip(),
                rif=rif_tercero,
                email=getattr(tercero, "email", "") or "",
                telefono=getattr(tercero, "telefono", "") or "",
                direccion_fiscal=getattr(tercero, "direccion", "") or "",
                es_cliente=es_cliente,
                es_proveedor=es_proveedor,
            )
        else:
            campos_rol: list[str] = []
            if es_cliente and not contacto.es_cliente:
                contacto.es_cliente = True
                campos_rol.append("es_cliente")
            if es_proveedor and not contacto.es_proveedor:
                contacto.es_proveedor = True
                campos_rol.append("es_proveedor")
            if campos_rol:
                contacto.save(update_fields=campos_rol)

        if getattr(tercero, "contacto_id", None) != contacto.pk:
            ocupado = (
                Cliente.objects.filter(contacto=contacto).exclude(pk=tercero.pk).exists()
                if isinstance(tercero, Cliente)
                else Proveedor.objects.filter(contacto=contacto).exclude(pk=tercero.pk).exists()
            )
            if not ocupado:
                tercero.contacto = contacto
                tercero.save(update_fields=["contacto"])

        if ext:
            mapping, creado = EntidadSincronizada.objects.get_or_create(
                id_instancia=instancia,
                tipo_entidad="contactos",
                id_externo=ext,
                defaults={"id_omni": str(contacto.pk), "modelo_omni": "apps.core.models.Contacto"},
            )
            if not creado and not mapping.id_omni:
                mapping.id_omni = str(contacto.pk)
                mapping.modelo_omni = "apps.core.models.Contacto"
                mapping.save(update_fields=["id_omni", "modelo_omni", "ultimo_sync"])

        return contacto

    def _resolver_o_crear_tercero(
        self,
        modelo,
        *,
        ext: str,
        nombre: str,
        instancia: "ConectorInstancia",
        es_cliente: bool,
        es_proveedor: bool,
    ):
        """Resuelve o auto-crea ``crm.Cliente`` / ``proveedores.Proveedor`` con su ``core.Contacto``."""
        from apps.core.models import Contacto
        from apps.integration_hub.models import EntidadSincronizada

        empresa = instancia.id_empresa
        tercero = None

        if ext:
            tercero = modelo.objects.filter(id_empresa=empresa, referencia_externa=ext).first()

        contacto = None
        rif = ""
        if tercero is None and ext:
            mapping = EntidadSincronizada.objects.filter(
                id_instancia=instancia, tipo_entidad="contactos", id_externo=ext
            ).first()
            if mapping and mapping.id_omni:
                contacto = Contacto.objects.filter(pk=mapping.id_omni, id_empresa=empresa).first()
                if contacto:
                    rif = getattr(contacto, "rif", "") or ""
                    tercero = modelo.objects.filter(id_empresa=empresa, contacto=contacto).first()

        if tercero is None:
            if not nombre:
                return None
            tercero = modelo.objects.create(
                id_empresa=empresa,
                razon_social=nombre,
                rif=rif,
                referencia_externa=ext or None,
                contacto=contacto,
            )

        self._asegurar_contacto_de_tercero(
            tercero,
            instancia,
            id_externo=ext,
            es_cliente=es_cliente,
            es_proveedor=es_proveedor,
        )
        return tercero

    def _resolver_o_crear_cliente(self, datos: dict, instancia: "ConectorInstancia"):
        """
        Resuelve el ``crm.Cliente`` del pedido; si no existe, lo auto-crea
        y garantiza un ``core.Contacto`` enlazado. Multi-tenant (R-CODE-1).
        """
        from apps.crm.models import Cliente

        return self._resolver_o_crear_tercero(
            Cliente,
            ext=str(datos.get("cliente_id_externo") or "").strip(),
            nombre=(datos.get("cliente_nombre") or "").strip(),
            instancia=instancia,
            es_cliente=True,
            es_proveedor=False,
        )

    def _resolver_producto_mapeado(self, product_id_field, instancia: "ConectorInstancia"):
        """
        Resuelve un ``inventario.Producto`` desde el ``product_id`` de una línea
        Odoo (``[id, nombre]``) usando el mapa de ``EntidadSincronizada`` de
        productos. Retorna None si el producto no fue sincronizado aún.
        """
        from apps.integration_hub.models import EntidadSincronizada
        from apps.inventario.models import Producto

        empresa = instancia.id_empresa
        if isinstance(product_id_field, list) and product_id_field:
            pid = str(product_id_field[0])
        elif product_id_field:
            pid = str(product_id_field)
        else:
            return None

        mapping = EntidadSincronizada.objects.filter(
            id_instancia=instancia, tipo_entidad="productos", id_externo=pid
        ).first()
        if mapping and mapping.id_omni:
            return Producto.objects.filter(pk=mapping.id_omni, id_empresa=empresa).first()
        return None

    def _upsert_pedido_venta(self, datos: dict, instancia: "ConectorInstancia") -> str | None:
        """
        Upsert de pedido de venta en ``ventas.Pedido`` (+ líneas en
        ``DetallePedido``). Idempotente por ``(id_empresa, numero_pedido)``.

        - Resuelve/auto-crea el cliente (``_resolver_o_crear_cliente``); si no hay
          cliente resoluble, omite el pedido (return None).
        - Reemplaza las líneas en cada sync; las líneas cuyo producto aún no está
          sincronizado en Omni se omiten (no rompen el pedido).
        Multi-tenant: acotado a la empresa de la instancia (R-CODE-1).
        """
        from apps.ventas.models import DetallePedido, Pedido

        empresa = instancia.id_empresa
        numero = (datos.get("numero") or "").strip()
        if not numero:
            logger.warning(
                "Pedido de venta externo %s omitido: sin número.",
                datos.get("id_externo", ""),
            )
            return None

        cliente = self._resolver_o_crear_cliente(datos, instancia)
        if cliente is None:
            logger.warning(
                "Pedido de venta %s omitido: cliente no resoluble.",
                datos.get("id_externo", ""),
            )
            return None

        estado_map = {
            "borrador": "PENDIENTE",
            "enviado": "ENVIADO",
            "confirmado": "APROBADO",
            "cerrado": "APROBADO",
            "cancelado": "ANULADO",
        }
        fecha = (datos.get("fecha_pedido") or "")[:10] or dj_timezone.now().date().isoformat()

        campos = {
            "id_cliente": cliente,
            "fecha_pedido": fecha,
            "estado": estado_map.get(datos.get("estado") or "", "PENDIENTE"),
            "referencia_externa": str(datos.get("id_externo") or "") or None,
            "tipo_operacion": "venta",
        }

        with transaction.atomic():
            pedido = Pedido.objects.filter(id_empresa=empresa, numero_pedido=numero).first()
            if pedido:
                for field, value in campos.items():
                    setattr(pedido, field, value)
                pedido.save()
            else:
                pedido = Pedido.objects.create(id_empresa=empresa, numero_pedido=numero, **campos)

            # Reemplazar líneas (la fuente externa es la verdad).
            pedido.detalles.all().delete()
            for linea in datos.get("lineas") or []:
                producto = self._resolver_producto_mapeado(linea.get("product_id"), instancia)
                if producto is None:
                    continue
                DetallePedido.objects.create(
                    id_pedido=pedido,
                    id_producto=producto,
                    cantidad=self._safe_decimal_money(linea.get("product_uom_qty")),
                    precio_unitario=self._safe_decimal_money(linea.get("price_unit")),
                    subtotal=self._safe_decimal_money(linea.get("price_subtotal")),
                )

        return str(pedido.pk)

    # ── Pedidos de compra (Fase 2) ─────────────────────────────────────────────

    def _resolver_o_crear_proveedor(self, datos: dict, instancia: "ConectorInstancia"):
        """
        Resuelve/auto-crea el ``proveedores.Proveedor`` y garantiza su ``core.Contacto``.
        """
        from apps.proveedores.models import Proveedor

        return self._resolver_o_crear_tercero(
            Proveedor,
            ext=str(datos.get("proveedor_id_externo") or "").strip(),
            nombre=(datos.get("proveedor_nombre") or "").strip(),
            instancia=instancia,
            es_cliente=False,
            es_proveedor=True,
        )

    def _upsert_pedido_compra(self, datos: dict, instancia: "ConectorInstancia") -> str | None:
        """
        Upsert de orden de compra en ``compras.OrdenCompra`` (+ líneas en
        ``DetalleOrdenCompra``). Idempotente por ``(id_empresa, numero_orden)``.
        Resuelve/auto-crea el proveedor; líneas con producto no sincronizado se
        omiten. Multi-tenant (R-CODE-1); Decimal en la frontera (R-CODE-4).
        """
        from apps.compras.models import DetalleOrdenCompra, OrdenCompra

        empresa = instancia.id_empresa
        numero = (datos.get("numero") or "").strip()
        if not numero:
            logger.warning(
                "Orden de compra externa %s omitida: sin número.",
                datos.get("id_externo", ""),
            )
            return None

        proveedor = self._resolver_o_crear_proveedor(datos, instancia)
        if proveedor is None:
            logger.warning(
                "Orden de compra %s omitida: proveedor no resoluble.",
                datos.get("id_externo", ""),
            )
            return None

        # Estados Odoo (purchase.order) → OrdenCompra de Omni.
        estado_map = {
            "draft": "BORRADOR",
            "sent": "ENVIADA",
            "to approve": "ENVIADA",
            "purchase": "APROBADA",
            "done": "CERRADA",
            "cancel": "ANULADA",
        }
        fecha = (datos.get("fecha_pedido") or "")[:10] or dj_timezone.now().date().isoformat()

        campos = {
            "id_proveedor": proveedor,
            "fecha_orden": fecha,
            "estado": estado_map.get(datos.get("estado") or "", "BORRADOR"),
            "referencia_externa": str(datos.get("id_externo") or "") or None,
            "tipo_operacion": "compra",
        }

        with transaction.atomic():
            orden = OrdenCompra.objects.filter(id_empresa=empresa, numero_orden=numero).first()
            if orden:
                for field, value in campos.items():
                    setattr(orden, field, value)
                orden.save()
            else:
                orden = OrdenCompra.objects.create(id_empresa=empresa, numero_orden=numero, **campos)

            orden.detalles.all().delete()
            for linea in datos.get("lineas") or []:
                producto = self._resolver_producto_mapeado(linea.get("product_id"), instancia)
                if producto is None:
                    continue
                DetalleOrdenCompra.objects.create(
                    id_orden_compra=orden,
                    id_producto=producto,
                    cantidad=self._safe_decimal_money(linea.get("product_qty")),
                    precio_unitario=self._safe_decimal_money(linea.get("price_unit")),
                    subtotal=self._safe_decimal_money(linea.get("price_subtotal")),
                )

        return str(orden.pk)

    # ── Facturas de venta (Fase 2) ─────────────────────────────────────────────

    def _upsert_factura_venta(self, datos: dict, instancia: "ConectorInstancia") -> str | None:
        """
        Upsert de factura de venta en ``ventas.FacturaFiscal`` (+ líneas en
        ``DetalleFacturaFiscal``). Idempotente por ``(id_empresa, numero_factura)``
        y por ``referencia_externa``.

        Documento fiscal **importado**: refleja una factura ya emitida en el
        sistema externo (Odoo ``account.move`` posted) para acumular el histórico
        en Omni. No re-emite ni dispara numeración fiscal; ``numero_control`` se
        toma del número externo. Estado ``EMITIDA`` (``PAGADA`` si Odoo la marca
        pagada). Multi-tenant: acotado a la empresa de la instancia (R-CODE-1).

        - Resuelve/auto-crea el cliente (``_resolver_o_crear_cliente``); sin
          cliente resoluble, omite la factura (return None).
        - Requiere una ``Moneda`` para la FK obligatoria ``id_moneda`` (externa →
          USD → primera); si no hay ninguna, omite la factura.
        - Reemplaza las líneas en cada sync; las líneas cuyo producto aún no está
          sincronizado se omiten (no rompen el documento).
        """
        from decimal import Decimal

        from apps.ventas.models import DetalleFacturaFiscal, FacturaFiscal

        empresa = instancia.id_empresa
        numero = (datos.get("numero") or "").strip()
        if not numero:
            logger.warning(
                "Factura de venta externa %s omitida: sin número.",
                datos.get("id_externo", ""),
            )
            return None

        cliente = self._resolver_o_crear_cliente(datos, instancia)
        if cliente is None:
            logger.warning(
                "Factura de venta %s omitida: cliente no resoluble.",
                datos.get("id_externo", ""),
            )
            return None

        moneda = self._resolver_moneda_para_empresa(empresa, datos.get("moneda"))
        if moneda is None:
            logger.warning(
                "Factura de venta %s omitida: no hay Moneda configurada para " "id_moneda (empresa %s).",
                datos.get("id_externo", ""),
                empresa.pk,
            )
            return None

        fecha = (datos.get("fecha_factura") or "")[:10] or dj_timezone.now().date().isoformat()
        vencimiento = (datos.get("fecha_vencimiento") or "")[:10] or None
        estado = "PAGADA" if (datos.get("estado_pago") or "") == "pagado" else "EMITIDA"

        campos = {
            "id_cliente": cliente,
            "numero_control": numero,
            "fecha_emision": fecha,
            "fecha_vencimiento": vencimiento,
            "base_imponible": self._safe_decimal_money(datos.get("subtotal")),
            "monto_iva": self._safe_decimal_money(datos.get("impuestos")),
            "monto_igtf": Decimal("0"),
            "monto_total": self._safe_decimal_money(datos.get("total")),
            "id_moneda": moneda,
            "estado": estado,
            "referencia_externa": str(datos.get("id_externo") or "") or None,
            "observaciones": (datos.get("origen_pedido") or "") or None,
        }

        with transaction.atomic():
            factura = FacturaFiscal.objects.filter(id_empresa=empresa, numero_factura=numero).first()
            if factura:
                for field, value in campos.items():
                    setattr(factura, field, value)
                factura.save()
            else:
                factura = FacturaFiscal.objects.create(id_empresa=empresa, numero_factura=numero, **campos)

            # Reemplazar líneas (la fuente externa es la verdad).
            factura.detalles.all().delete()
            for linea in datos.get("lineas") or []:
                producto = self._resolver_producto_mapeado(linea.get("product_id"), instancia)
                if producto is None:
                    continue
                subtotal = self._safe_decimal_money(linea.get("price_subtotal"))
                total_linea = self._safe_decimal_money(linea.get("price_total"))
                # El impuesto de la línea = total con impuesto − subtotal.
                monto_impuesto = total_linea - subtotal if total_linea > subtotal else Decimal("0")
                DetalleFacturaFiscal.objects.create(
                    id_factura=factura,
                    id_producto=producto,
                    cantidad=self._safe_decimal_money(linea.get("quantity")),
                    precio_unitario=self._safe_decimal_money(linea.get("price_unit")),
                    subtotal=subtotal,
                    monto_impuesto=monto_impuesto,
                    total_linea=total_linea or subtotal,
                )

        return str(factura.pk)

    # ── Facturas de compra (Ola B6) ────────────────────────────────────────────

    def _upsert_factura_compra(self, datos: dict, instancia: "ConectorInstancia") -> str | None:
        """
        Upsert idempotente (history-only) de factura de compra en ``compras.FacturaCompra``
        (+ ``DetalleFacturaCompra`` y ``cuentas_por_pagar.CuentaPorPagar`` asociada).

        - Número tomado de ``numero`` o ``referencia``; si ambos vacíos, omite.
        - Auto-crea ``proveedores.Proveedor`` y su ``core.Contacto`` común.
        - Enlaza opcionalmente a ``OrdenCompra`` por ``origen_pedido`` (``None`` si no existe).
        - Cero asientos contables ni movimientos de caja/inventario (history-only).
        """
        from decimal import Decimal

        from django.utils.dateparse import parse_date

        from apps.compras.models import DetalleFacturaCompra, FacturaCompra, OrdenCompra
        from apps.cuentas_por_pagar.models import CuentaPorPagar

        empresa = instancia.id_empresa
        numero = (datos.get("numero") or datos.get("referencia") or "").strip()[:50]
        if not numero:
            logger.warning(
                "Factura de compra externa %s omitida: sin número.",
                datos.get("id_externo", ""),
            )
            return None

        proveedor = self._resolver_o_crear_proveedor(datos, instancia)
        if proveedor is None:
            logger.warning(
                "Factura de compra %s omitida: proveedor no resoluble.",
                datos.get("id_externo", ""),
            )
            return None

        origen_pedido = (datos.get("origen_pedido") or "").strip()
        orden = (
            OrdenCompra.objects.filter(id_empresa=empresa, numero_orden=origen_pedido).first()
            if origen_pedido
            else None
        )

        fecha_emision = parse_date((datos.get("fecha_factura") or "")[:10] or "") or dj_timezone.now().date()
        fecha_vencimiento = parse_date((datos.get("fecha_vencimiento") or "")[:10] or "") or fecha_emision

        total = max(Decimal("0"), self._safe_decimal_money(datos.get("total")))
        estado_pago = (datos.get("estado_pago") or "").strip().lower()
        if estado_pago in ("pagado", "paid", "en_proceso", "in_payment"):
            estado_cxp = "PAGADA"
        elif estado_pago in ("parcial", "partial"):
            estado_cxp = "PARCIAL"
        else:
            estado_cxp = "PENDIENTE"

        saldo_raw = datos.get("saldo_pendiente")
        if saldo_raw in (None, ""):
            saldo_pendiente = Decimal("0") if estado_cxp == "PAGADA" else total
        else:
            saldo_pendiente = max(Decimal("0"), min(total, self._safe_decimal_money(saldo_raw)))

        id_externo = str(datos.get("id_externo") or "").strip()
        referencia_ext = f"odoo:in_invoice:{id_externo}"[:100] if id_externo else None

        doc_json = {
            "moneda": str(datos.get("moneda") or ""),
            "estado_pago": estado_pago,
            "saldo_pendiente": str(saldo_pendiente),
            "fecha_vencimiento": fecha_vencimiento.isoformat(),
            "origen_pedido": origen_pedido,
        }

        with transaction.atomic():
            factura, _creada = FacturaCompra.objects.update_or_create(
                id_empresa=empresa,
                numero_factura=numero,
                defaults={
                    "id_proveedor": proveedor,
                    "id_orden_compra": orden,
                    "fecha_emision": fecha_emision,
                    "monto_total": total,
                    "referencia_externa": referencia_ext,
                    "documento_json": doc_json,
                    "observaciones": origen_pedido or None,
                    "activo": True,
                },
            )

            factura.detalles.all().delete()
            for linea in datos.get("lineas") or []:
                producto = self._resolver_producto_mapeado(linea.get("product_id"), instancia)
                if producto is None:
                    continue
                cantidad = self._safe_decimal_money(linea.get("quantity"))
                precio_unitario = self._safe_decimal_money(linea.get("price_unit"))
                descuento_pct = min(
                    Decimal("100.00"),
                    max(
                        Decimal("0.00"),
                        self._safe_decimal_money(linea.get("discount")).quantize(Decimal("0.01")),
                    ),
                )
                subtotal = self._safe_decimal_money(linea.get("price_subtotal"))
                total_linea = self._safe_decimal_money(linea.get("price_total"))
                monto_impuesto = total_linea - subtotal if total_linea > subtotal else Decimal("0")
                bruto = cantidad * precio_unitario
                descuento_monto = (
                    bruto - subtotal if bruto > subtotal and descuento_pct > Decimal("0") else Decimal("0")
                )
                DetalleFacturaCompra.objects.create(
                    id_factura_compra=factura,
                    id_producto=producto,
                    cantidad=cantidad,
                    precio_unitario=precio_unitario,
                    descuento_porcentaje=descuento_pct,
                    descuento_monto=descuento_monto,
                    subtotal=subtotal,
                    monto_impuesto=monto_impuesto,
                    total_linea=total_linea or subtotal,
                )

            cxp = CuentaPorPagar.objects.filter(id_empresa=empresa, id_factura_compra=factura).first()
            if cxp is None and referencia_ext:
                cxp = CuentaPorPagar.objects.filter(id_empresa=empresa, referencia_externa=referencia_ext).first()

            cxp_defaults = {
                "id_proveedor": proveedor,
                "id_factura_compra": factura,
                "referencia_externa": referencia_ext,
                "documento_json": doc_json,
                "tipo_operacion": "FACTURA_COMPRA",
                "monto_total": total,
                "monto_pendiente": saldo_pendiente,
                "fecha_emision": fecha_emision,
                "fecha_vencimiento": fecha_vencimiento,
                "estado": estado_cxp,
                "activo": True,
            }
            if cxp is not None:
                for field, value in cxp_defaults.items():
                    setattr(cxp, field, value)
                cxp.save()
            else:
                CuentaPorPagar.objects.create(id_empresa=empresa, **cxp_defaults)

        return str(factura.pk)

    # ── Pagos (Fase 2 + Ola B6 N:M) ───────────────────────────────────────────

    def _asegurar_contacto_de_documento(
        self,
        doc,
        instancia: "ConectorInstancia",
        *,
        id_externo: str = "",
    ):
        """Asegura ``core.Contacto`` en el tercero de un documento legacy si carece de él."""
        if getattr(doc, "cliente_id", None):
            return self._asegurar_contacto_de_tercero(doc.cliente, instancia, id_externo=id_externo, es_cliente=True)
        if getattr(doc, "id_cliente_id", None):
            return self._asegurar_contacto_de_tercero(
                doc.id_cliente, instancia, id_externo=id_externo, es_cliente=True
            )
        if getattr(doc, "id_proveedor_id", None):
            return self._asegurar_contacto_de_tercero(
                doc.id_proveedor, instancia, id_externo=id_externo, es_proveedor=True
            )
        if getattr(doc, "id_orden_compra_id", None) and doc.id_orden_compra.id_proveedor_id:
            return self._asegurar_contacto_de_tercero(
                doc.id_orden_compra.id_proveedor,
                instancia,
                id_externo=id_externo,
                es_proveedor=True,
            )
        return None

    def _resolver_o_crear_contacto_desde_pago(
        self,
        datos: dict,
        instancia: "ConectorInstancia",
        *,
        es_cliente: bool,
        es_proveedor: bool,
        docs_resueltos: list[tuple[str, object]],
    ):
        """Resuelve o crea el ``core.Contacto`` propietario de un pago importado."""
        from apps.core.models import Contacto
        from apps.crm.models import Cliente
        from apps.finanzas.services_conciliacion_pagos import (
            ConciliacionPagoError,
            _resolver_contacto_documento,
        )
        from apps.integration_hub.models import EntidadSincronizada
        from apps.proveedores.models import Proveedor

        empresa = instancia.id_empresa
        ext_socio = str(datos.get("socio_id_externo") or "").strip()
        socio_nombre = (datos.get("socio_nombre") or "").strip()

        contacto = None
        for _, doc_res in docs_resueltos:
            try:
                contacto_doc = _resolver_contacto_documento(empresa, doc_res)
            except ConciliacionPagoError:
                contacto_doc = self._asegurar_contacto_de_documento(doc_res, instancia, id_externo=ext_socio)
            if contacto is None and contacto_doc is not None:
                contacto = contacto_doc

        if contacto is None and ext_socio:
            mapping = EntidadSincronizada.objects.filter(
                id_instancia=instancia, tipo_entidad="contactos", id_externo=ext_socio
            ).first()
            if mapping and mapping.id_omni:
                contacto = Contacto.objects.filter(pk=mapping.id_omni, id_empresa=empresa).first()

        if contacto is None and ext_socio:
            if es_cliente:
                cli = Cliente.objects.filter(id_empresa=empresa, referencia_externa=ext_socio).first()
                if cli is not None:
                    contacto = self._asegurar_contacto_de_tercero(
                        cli, instancia, id_externo=ext_socio, es_cliente=True
                    )
            if contacto is None and es_proveedor:
                prov = Proveedor.objects.filter(id_empresa=empresa, referencia_externa=ext_socio).first()
                if prov is not None:
                    contacto = self._asegurar_contacto_de_tercero(
                        prov, instancia, id_externo=ext_socio, es_proveedor=True
                    )

        if contacto is None and (socio_nombre or ext_socio):
            contacto = Contacto.objects.create(
                id_empresa=empresa,
                nombre=socio_nombre or f"Contacto {ext_socio}",
                es_cliente=es_cliente,
                es_proveedor=es_proveedor,
            )

        if contacto is not None:
            campos_rol: list[str] = []
            if es_cliente and not contacto.es_cliente:
                contacto.es_cliente = True
                campos_rol.append("es_cliente")
            if es_proveedor and not contacto.es_proveedor:
                contacto.es_proveedor = True
                campos_rol.append("es_proveedor")
            if campos_rol:
                contacto.save(update_fields=campos_rol)
            if ext_socio:
                mapping, creado = EntidadSincronizada.objects.get_or_create(
                    id_instancia=instancia,
                    tipo_entidad="contactos",
                    id_externo=ext_socio,
                    defaults={"id_omni": str(contacto.pk), "modelo_omni": "apps.core.models.Contacto"},
                )
                if not creado and not mapping.id_omni:
                    mapping.id_omni = str(contacto.pk)
                    mapping.modelo_omni = "apps.core.models.Contacto"
                    mapping.save(update_fields=["id_omni", "modelo_omni", "ultimo_sync"])

        return contacto

    def _upsert_pago(self, datos: dict, instancia: "ConectorInstancia") -> str | None:
        """
        Upsert de pago en ``finanzas.Pago`` + ``finanzas.AsignacionPago`` (N:M) en
        modo estrictamente **history-only** (``generar_asiento=False``,
        ``modo_historico_externo=True``, ``id_transaccion_financiera=None``).

        Soporta:
        - Cobros de cliente (``inbound``/``customer`` -> ``INGRESO``) contra 0, 1 o N
          ``FacturaFiscal`` / ``CuentaPorCobrar``.
        - Pagos a proveedor (``outbound``/``supplier`` -> ``EGRESO``) contra 0, 1 o N
          ``CuentaPorPagar`` (vinculada a ``FacturaCompra``) o ``FacturaCompra``.
        - Anticipos / saldos a favor (``tipo_documento="ANTICIPO"``) cuando no trae
          facturas reconciliadas.
        """
        from datetime import datetime, time as _time
        from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

        from django.db.models import DecimalField, Q, Sum
        from django.db.models.functions import Coalesce
        from django.utils.dateparse import parse_date

        from apps.compras.models import FacturaCompra
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar
        from apps.cuentas_por_pagar.models import CuentaPorPagar
        from apps.finanzas.models import MetodoPago, Pago
        from apps.finanzas.services import TasaCambioError, obtener_tasa_cambio
        from apps.finanzas.services_conciliacion_pagos import (
            _saldo_aplicable_historico_documento,
            aplicar_pago_a_documentos,
            saldo_disponible_pago,
        )
        from apps.integration_hub.models import EntidadSincronizada
        from apps.ventas.models import FacturaFiscal

        empresa = instancia.id_empresa
        ext = str(datos.get("id_externo") or "").strip()
        if not ext:
            return None

        tipo = (datos.get("tipo") or "").strip()
        tipo_socio = (datos.get("tipo_socio") or "").strip()
        if tipo == "inbound" and tipo_socio == "customer":
            tipo_operacion = "INGRESO"
        elif tipo == "outbound" and tipo_socio == "supplier":
            tipo_operacion = "EGRESO"
        else:
            logger.warning(
                "Pago externo %s omitido: tipo=%s socio=%s no soportado.",
                ext,
                tipo,
                tipo_socio,
            )
            return None

        moneda = self._resolver_moneda_para_empresa(empresa, datos.get("moneda"))
        if moneda is None:
            logger.warning("Pago externo %s omitido: sin Moneda configurada.", ext)
            return None

        reconciliaciones_raw = list(datos.get("reconciliaciones") or [])
        ext_move_ids: list[str] = []
        seen_ext: set[str] = set()
        for inv_ext in datos.get("facturas_externas") or []:
            sid = str(inv_ext or "").strip()
            if sid and sid not in seen_ext:
                seen_ext.add(sid)
                ext_move_ids.append(sid)
        for rec in reconciliaciones_raw:
            sid = str(rec.get("move_id_externo") or "").strip()
            if sid and sid not in seen_ext:
                seen_ext.add(sid)
                ext_move_ids.append(sid)

        tiene_referencia_facturas = bool(ext_move_ids or reconciliaciones_raw)

        docs_por_ext: dict[str, tuple[str, object]] = {}
        docs_resueltos: list[tuple[str, object]] = []
        vistos_doc_pk: set[tuple[str, str]] = set()

        for inv_ext in ext_move_ids:
            par_resuelto: tuple[str, object] | None = None
            if tipo_operacion == "INGRESO":
                mapping = EntidadSincronizada.objects.filter(
                    id_instancia=instancia, tipo_entidad="facturas_venta", id_externo=inv_ext
                ).first()
                if mapping and mapping.id_omni:
                    fac = FacturaFiscal.objects.filter(pk=mapping.id_omni, id_empresa=empresa, activo=True).first()
                    if fac is not None:
                        par_resuelto = ("FACTURA_VENTA", fac)
                if par_resuelto is None:
                    cxc = (
                        CuentaPorCobrar.objects.filter(
                            empresa=empresa,
                            referencia_externa__in=[inv_ext, f"odoo:out_invoice:{inv_ext}"],
                        )
                        .exclude(estado="anulada")
                        .order_by("pk")
                        .first()
                    )
                    if cxc is not None:
                        par_resuelto = ("CUENTA_POR_COBRAR", cxc)
            else:
                mapping = EntidadSincronizada.objects.filter(
                    id_instancia=instancia, tipo_entidad="facturas_compra", id_externo=inv_ext
                ).first()
                if mapping and mapping.id_omni:
                    fc = FacturaCompra.objects.filter(pk=mapping.id_omni, id_empresa=empresa, activo=True).first()
                    if fc is not None:
                        cxp = (
                            CuentaPorPagar.objects.filter(id_empresa=empresa, id_factura_compra=fc, activo=True)
                            .order_by("fecha_creacion")
                            .first()
                        )
                        par_resuelto = ("CUENTA_POR_PAGAR", cxp) if cxp is not None else ("FACTURA_COMPRA", fc)
                if par_resuelto is None:
                    cxp_fb = (
                        CuentaPorPagar.objects.filter(
                            id_empresa=empresa,
                            referencia_externa__in=[inv_ext, f"odoo:in_invoice:{inv_ext}"],
                            activo=True,
                        )
                        .order_by("fecha_creacion")
                        .first()
                    )
                    if cxp_fb is not None:
                        par_resuelto = ("CUENTA_POR_PAGAR", cxp_fb)

            if par_resuelto is not None:
                docs_por_ext[inv_ext] = par_resuelto
                clave_pk = (par_resuelto[0], str(par_resuelto[1].pk))
                if clave_pk not in vistos_doc_pk:
                    vistos_doc_pk.add(clave_pk)
                    docs_resueltos.append(par_resuelto)

        if not docs_resueltos and tiene_referencia_facturas:
            logger.warning(
                "Pago externo %s omitido: ninguna de las facturas referenciadas (%s) está sincronizada en Omni.",
                ext,
                ext_move_ids,
            )
            return None

        if len(docs_resueltos) >= 2 and not reconciliaciones_raw:
            logger.warning(
                "Pago externo %s omitido: reconciliación múltiple (%s docs) sin detalle de montos parciales.",
                ext,
                len(docs_resueltos),
            )
            return None

        contacto = self._resolver_o_crear_contacto_desde_pago(
            datos,
            instancia,
            es_cliente=(tipo_operacion == "INGRESO"),
            es_proveedor=(tipo_operacion == "EGRESO"),
            docs_resueltos=docs_resueltos,
        )
        if not docs_resueltos and contacto is None:
            logger.warning("Pago externo %s omitido: anticipo sin contacto identificable.", ext)
            return None

        metodo, _ = MetodoPago.objects.get_or_create(
            empresa=empresa,
            nombre_metodo="Importado (Integration Hub)",
            defaults={"tipo_metodo": "OTRO", "es_generico": False},
        )

        fecha_d = parse_date((datos.get("fecha") or "")[:10] or "") or dj_timezone.now().date()
        fecha_dt = dj_timezone.make_aware(datetime.combine(fecha_d, _time()))
        monto_nuevo = max(Decimal("0"), self._safe_decimal_money(datos.get("monto")))
        referencia_str = (f"odoo:{ext} " + (datos.get("referencia") or "")).strip()[:100]

        if not docs_resueltos:
            tipo_doc_pago = "ANTICIPO"
            id_doc_pago = None
            id_factura_fk = None
            id_cxp_fk = None
        elif len(docs_resueltos) == 1:
            u_tipo, u_doc = docs_resueltos[0]
            id_factura_fk = u_doc if u_tipo == "FACTURA_VENTA" else None
            id_cxp_fk = u_doc if u_tipo == "CUENTA_POR_PAGAR" else None
            if u_tipo == "FACTURA_VENTA":
                tipo_doc_pago = "FACTURA"
                id_doc_pago = u_doc.pk
            elif u_tipo == "CUENTA_POR_COBRAR":
                tipo_doc_pago = "CXC"
                id_doc_pago = None
            elif u_tipo == "CUENTA_POR_PAGAR":
                tipo_doc_pago = "CXP"
                id_doc_pago = u_doc.pk
            else:
                tipo_doc_pago = "COMPRA"
                id_doc_pago = u_doc.pk
        else:
            tipo_doc_pago = "CONCILIACION_MULTIPLE"
            id_doc_pago = None
            id_factura_fk = None
            id_cxp_fk = None

        with transaction.atomic():
            pago = None
            mapping_pago = EntidadSincronizada.objects.filter(
                id_instancia=instancia, tipo_entidad="pagos", id_externo=ext
            ).first()
            if mapping_pago and mapping_pago.id_omni:
                pago = Pago.objects.filter(pk=mapping_pago.id_omni, id_empresa=empresa).first()
            if pago is None:
                pago = (
                    Pago.objects.filter(id_empresa=empresa)
                    .filter(Q(referencia=f"odoo:{ext}") | Q(referencia__startswith=f"odoo:{ext} "))
                    .order_by("fecha_creacion", "id_pago")
                    .first()
                )

            if pago is not None:
                asignado_activo: Decimal = pago.asignaciones.filter(estado="ACTIVA", activo=True).aggregate(
                    total=Coalesce(
                        Sum("monto_asignado_pago"),
                        Decimal("0.0000"),
                        output_field=DecimalField(max_digits=18, decimal_places=4),
                    )
                )["total"]
                monto_eff = max(monto_nuevo, Decimal(str(asignado_activo)))
                pago.id_contacto = contacto
                pago.tipo_operacion = tipo_operacion
                pago.tipo_documento = tipo_doc_pago
                pago.id_documento = id_doc_pago
                pago.fecha_pago = fecha_dt
                pago.monto = monto_eff
                pago.id_moneda = moneda
                pago.id_metodo_pago = metodo
                pago.id_factura = id_factura_fk
                pago.id_cxp = id_cxp_fk
                pago.referencia = referencia_str
                pago.save()
            else:
                pago = Pago.objects.create(
                    id_empresa=empresa,
                    id_contacto=contacto,
                    tipo_operacion=tipo_operacion,
                    tipo_documento=tipo_doc_pago,
                    id_documento=id_doc_pago,
                    fecha_pago=fecha_dt,
                    monto=monto_nuevo,
                    id_moneda=moneda,
                    id_metodo_pago=metodo,
                    id_factura=id_factura_fk,
                    id_cxp=id_cxp_fk,
                    referencia=referencia_str,
                    id_transaccion_financiera=None,
                )

            if docs_resueltos:
                refs_activas = set(
                    pago.asignaciones.filter(estado="ACTIVA", activo=True)
                    .exclude(referencia_externa="")
                    .values_list("referencia_externa", flat=True)
                )
                lote_asignaciones: list[dict] = []
                disponible_restante = saldo_disponible_pago(pago)
                saldo_doc_cache: dict[tuple[str, str], Decimal] = {}

                if reconciliaciones_raw:
                    for idx, rec in enumerate(reconciliaciones_raw):
                        move_ext = str(rec.get("move_id_externo") or "").strip()
                        if move_ext not in docs_por_ext or disponible_restante <= Decimal("0"):
                            continue
                        t_tipo, t_doc = docs_por_ext[move_ext]
                        pr_id = str(rec.get("partial_reconcile_id") or "").strip()
                        ref_asig = f"odoo:pr:{pr_id}"[:100] if pr_id else f"odoo:pay:{ext}:doc:{t_doc.pk}:{idx}"[:100]
                        if ref_asig in refs_activas:
                            continue

                        clave_cache = (t_tipo, str(t_doc.pk))
                        if clave_cache not in saldo_doc_cache:
                            saldo_doc_cache[clave_cache] = _saldo_aplicable_historico_documento(
                                empresa.pk, t_tipo, t_doc
                            )
                        saldo_doc_rest = saldo_doc_cache[clave_cache]
                        if saldo_doc_rest <= Decimal("0"):
                            continue

                        monto_pago_pr = self._safe_decimal_money(rec.get("monto_pago") or rec.get("monto_base"))
                        monto_doc_pr = self._safe_decimal_money(rec.get("monto_documento") or rec.get("monto_base"))
                        if monto_pago_pr <= Decimal("0") or monto_doc_pr <= Decimal("0"):
                            continue

                        if t_tipo == "FACTURA_VENTA":
                            moneda_doc_obj = t_doc.id_moneda
                        else:
                            moneda_doc_obj = (
                                self._resolver_moneda_para_empresa(empresa, rec.get("moneda_documento"))
                                or empresa.id_moneda_base
                                or moneda
                            )

                        if moneda_doc_obj.pk == pago.id_moneda_id:
                            quant = Decimal("0.01") if t_tipo == "CUENTA_POR_COBRAR" else Decimal("0.0001")
                            monto_apl = min(monto_pago_pr, disponible_restante, saldo_doc_rest).quantize(
                                quant, rounding=ROUND_DOWN
                            )
                            if monto_apl <= Decimal("0"):
                                continue
                            lote_asignaciones.append(
                                {
                                    "tipo_documento": t_tipo,
                                    "id_documento": t_doc.pk,
                                    "monto_asignado_pago": monto_apl,
                                    "monto_asignado_documento": monto_apl,
                                    "moneda_documento": moneda_doc_obj.codigo_iso,
                                    "referencia_externa": ref_asig,
                                }
                            )
                            disponible_restante -= monto_apl
                            saldo_doc_cache[clave_cache] -= monto_apl
                        else:
                            tasa_orig = (monto_doc_pr / monto_pago_pr).quantize(
                                Decimal("0.00000001"), rounding=ROUND_HALF_UP
                            )
                            if tasa_orig <= Decimal("0"):
                                continue
                            monto_pago_eff = min(monto_pago_pr, disponible_restante).quantize(
                                Decimal("0.0001"), rounding=ROUND_DOWN
                            )
                            quant_doc = Decimal("0.01") if t_tipo == "CUENTA_POR_COBRAR" else Decimal("0.0001")
                            monto_doc_eff = min(
                                monto_doc_pr,
                                saldo_doc_rest,
                                (monto_pago_eff * tasa_orig).quantize(quant_doc, rounding=ROUND_HALF_UP),
                            ).quantize(quant_doc, rounding=ROUND_DOWN)
                            if monto_doc_eff < monto_doc_pr:
                                monto_pago_eff = min(
                                    disponible_restante,
                                    (monto_doc_eff / tasa_orig).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
                                )
                            if monto_pago_eff <= Decimal("0") or monto_doc_eff <= Decimal("0"):
                                continue
                            tasa_eff = (monto_doc_eff / monto_pago_eff).quantize(
                                Decimal("0.00000001"), rounding=ROUND_HALF_UP
                            )
                            lote_asignaciones.append(
                                {
                                    "tipo_documento": t_tipo,
                                    "id_documento": t_doc.pk,
                                    "monto_asignado_pago": monto_pago_eff,
                                    "monto_asignado_documento": monto_doc_eff,
                                    "moneda_documento": moneda_doc_obj.codigo_iso,
                                    "tasa_aplicada": tasa_eff,
                                    "referencia_externa": ref_asig,
                                }
                            )
                            disponible_restante -= monto_pago_eff
                            saldo_doc_cache[clave_cache] -= monto_doc_eff
                        refs_activas.add(ref_asig)
                elif len(docs_resueltos) == 1:
                    t_tipo, t_doc = docs_resueltos[0]
                    ref_asig = f"odoo:pay:{ext}:doc:{t_doc.pk}"[:100]
                    ya_asignado = (
                        ref_asig in refs_activas
                        or pago.asignaciones.filter(
                            estado="ACTIVA",
                            activo=True,
                            tipo_documento=t_tipo,
                            id_documento=str(t_doc.pk),
                        ).exists()
                    )
                    if not ya_asignado and disponible_restante > Decimal("0"):
                        saldo_doc_rest = _saldo_aplicable_historico_documento(empresa.pk, t_tipo, t_doc)
                        if t_tipo == "FACTURA_VENTA":
                            moneda_doc_obj = t_doc.id_moneda
                        else:
                            moneda_doc_obj = empresa.id_moneda_base or moneda
                        if saldo_doc_rest > Decimal("0"):
                            if moneda_doc_obj.pk == pago.id_moneda_id:
                                quant = Decimal("0.01") if t_tipo == "CUENTA_POR_COBRAR" else Decimal("0.0001")
                                monto_apl = min(disponible_restante, saldo_doc_rest).quantize(
                                    quant, rounding=ROUND_DOWN
                                )
                                if monto_apl > Decimal("0"):
                                    lote_asignaciones.append(
                                        {
                                            "tipo_documento": t_tipo,
                                            "id_documento": t_doc.pk,
                                            "monto_asignado_pago": monto_apl,
                                            "monto_asignado_documento": monto_apl,
                                            "moneda_documento": moneda_doc_obj.codigo_iso,
                                            "referencia_externa": ref_asig,
                                        }
                                    )
                            else:
                                try:
                                    tasa_obj = obtener_tasa_cambio(
                                        pago.id_moneda, moneda_doc_obj, empresa=empresa, fecha=fecha_d
                                    )
                                    tasa_val = Decimal(str(tasa_obj.valor_tasa))
                                except TasaCambioError:
                                    tasa_val = Decimal("0")
                                if tasa_val > Decimal("0"):
                                    quant_doc = Decimal("0.01") if t_tipo == "CUENTA_POR_COBRAR" else Decimal("0.0001")
                                    monto_doc_eff = min(
                                        saldo_doc_rest,
                                        (disponible_restante * tasa_val).quantize(quant_doc, rounding=ROUND_DOWN),
                                    ).quantize(quant_doc, rounding=ROUND_DOWN)
                                    monto_pago_eff = min(
                                        disponible_restante,
                                        (monto_doc_eff / tasa_val).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
                                    )
                                    if monto_pago_eff > Decimal("0") and monto_doc_eff > Decimal("0"):
                                        lote_asignaciones.append(
                                            {
                                                "tipo_documento": t_tipo,
                                                "id_documento": t_doc.pk,
                                                "monto_asignado_pago": monto_pago_eff,
                                                "monto_asignado_documento": monto_doc_eff,
                                                "moneda_documento": moneda_doc_obj.codigo_iso,
                                                "tasa_aplicada": tasa_val,
                                                "referencia_externa": ref_asig,
                                            }
                                        )

                if lote_asignaciones:
                    aplicar_pago_a_documentos(
                        pago,
                        lote_asignaciones,
                        generar_asiento=False,
                        modo_historico_externo=True,
                    )

        return str(pago.pk)

    # ── Inventario / stock (Fase 2) ────────────────────────────────────────────

    def _upsert_inventario(self, datos: dict, instancia: "ConectorInstancia") -> str | None:
        """
        Upsert de stock por producto en ``inventario.StockActual``.

        Resuelve el producto por el mapa ``EntidadSincronizada``; si no está
        sincronizado, omite (no se puede crear el producto desde un quant). El
        stock importado se consolida en un almacén por defecto del tenant
        (creado si no existe). Idempotente por ``(producto, variante, almacén)``.
        Multi-tenant (R-CODE-1); cantidades en Decimal (R-CODE-4).
        """
        from apps.almacenes.models import Almacen
        from apps.inventario.models import StockActual

        empresa = instancia.id_empresa

        producto = self._resolver_producto_mapeado(datos.get("producto_id_externo"), instancia)
        if producto is None:
            logger.debug(
                "Stock externo %s omitido: producto no sincronizado.",
                datos.get("id_externo", ""),
            )
            return None

        almacen, _ = Almacen.objects.get_or_create(
            id_empresa=empresa,
            codigo_almacen="IH-IMPORT",
            defaults={"nombre_almacen": "Importado (Integration Hub)"},
        )

        disponible = self._safe_decimal_money(datos.get("cantidad_disponible"))
        comprometida = self._safe_decimal_money(datos.get("cantidad_reservada"))

        with transaction.atomic():
            stock, _creado = StockActual.objects.update_or_create(
                id_empresa=empresa,
                id_producto=producto,
                id_variante=None,
                id_almacen=almacen,
                defaults={
                    "cantidad_disponible": disponible,
                    "cantidad_comprometida": comprometida,
                },
            )
        return str(stock.pk)

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

    def _marcar_completado(self, job: "JobSincronizacion", resultado: SyncResult) -> None:
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

    def _marcar_fallido(self, job: "JobSincronizacion", mensaje: str, resultado: SyncResult) -> None:
        """Marca el job como fallido con mensaje de error."""
        job.estado = "fallido"
        job.completado_en = dj_timezone.now()
        # Persistir los contadores parciales: distingue "falló sin procesar
        # nada" de "falló a mitad" en la auditoría del job.
        job.total_registros = resultado.total
        job.procesados = resultado.procesados
        job.creados = resultado.creados
        job.actualizados = resultado.actualizados
        job.omitidos = resultado.omitidos
        job.fallidos = resultado.fallidos
        job.resumen_errores = [{"error": mensaje}]
        job.save()

        job.id_instancia.estado = "error"
        job.id_instancia.mensaje_estado = mensaje[:500]
        job.id_instancia.save(update_fields=["estado", "mensaje_estado"])

        logger.error("Job fallido [%s]: %s", job.id_instancia.nombre, mensaje)
