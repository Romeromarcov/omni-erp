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
                        mapping.save(
                            update_fields=["id_omni", "checksum", "ultimo_sync"]
                        )
                    res["creados" if creado else "actualizados"] += 1
                else:
                    res["omitidos"] += 1
            except Exception as exc:  # best-effort: no abortar el lote
                res["fallidos"] += 1
                if len(res["errores"]) < 50:
                    res["errores"].append(
                        {"id_externo": id_externo, "error": str(exc)[:300]}
                    )
                logger.warning(
                    "ingerir_en_omni %s:%s → %s", tipo_entidad, id_externo, exc
                )

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
                producto = Producto.objects.filter(
                    id_empresa=empresa, nombre_producto=nombre
                ).first()

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
                    "Producto externo %s omitido: no hay Moneda configurada para "
                    "id_moneda_precio (empresa %s).",
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

    def _resolver_o_crear_cliente(self, datos: dict, instancia: "ConectorInstancia"):
        """
        Resuelve el ``crm.Cliente`` del pedido; si no existe, lo auto-crea
        (decisión del owner: auto-crear maestros faltantes). Idempotente por
        ``referencia_externa`` (= id externo de Odoo). Si hay un ``core.Contacto``
        ya sincronizado con el mismo id externo, lo enlaza y reutiliza su RIF.

        Retorna el Cliente o ``None`` si no hay datos mínimos (nombre).
        Multi-tenant: todo acotado a ``instancia.id_empresa`` (R-CODE-1).
        """
        from apps.crm.models import Cliente
        from apps.integration_hub.models import EntidadSincronizada

        empresa = instancia.id_empresa
        ext = str(datos.get("cliente_id_externo") or "")
        nombre = (datos.get("cliente_nombre") or "").strip()

        # 1. Idempotencia por referencia externa.
        if ext:
            existente = Cliente.objects.filter(
                id_empresa=empresa, referencia_externa=ext
            ).first()
            if existente:
                return existente

        # 2. Enlazar al Contacto ya sincronizado (mismo id externo), si existe.
        contacto = None
        rif = ""
        if ext:
            mapping = EntidadSincronizada.objects.filter(
                id_instancia=instancia, tipo_entidad="contactos", id_externo=ext
            ).first()
            if mapping and mapping.id_omni:
                from apps.core.models import Contacto

                contacto = Contacto.objects.filter(
                    pk=mapping.id_omni, id_empresa=empresa
                ).first()
                if contacto:
                    rif = getattr(contacto, "rif", "") or ""
                    ya = Cliente.objects.filter(
                        id_empresa=empresa, contacto=contacto
                    ).first()
                    if ya:
                        return ya

        if not nombre:
            return None

        # 3. Auto-crear el maestro. El create por ORM no dispara el validador de
        #    RIF; usamos el RIF del contacto si lo hay (puede quedar vacío).
        return Cliente.objects.create(
            id_empresa=empresa,
            razon_social=nombre,
            rif=rif,
            referencia_externa=ext or None,
            contacto=contacto,
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
            pedido = Pedido.objects.filter(
                id_empresa=empresa, numero_pedido=numero
            ).first()
            if pedido:
                for field, value in campos.items():
                    setattr(pedido, field, value)
                pedido.save()
            else:
                pedido = Pedido.objects.create(
                    id_empresa=empresa, numero_pedido=numero, **campos
                )

            # Reemplazar líneas (la fuente externa es la verdad).
            pedido.detalles.all().delete()
            for linea in datos.get("lineas") or []:
                producto = self._resolver_producto_mapeado(
                    linea.get("product_id"), instancia
                )
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
        Resuelve/auto-crea el ``proveedores.Proveedor`` de la orden de compra.
        Análogo a ``_resolver_o_crear_cliente``: idempotente por
        ``referencia_externa``; enlaza al ``core.Contacto`` ya sincronizado y
        reutiliza su RIF. Retorna el Proveedor o None si no hay nombre.
        """
        from apps.integration_hub.models import EntidadSincronizada
        from apps.proveedores.models import Proveedor

        empresa = instancia.id_empresa
        ext = str(datos.get("proveedor_id_externo") or "")
        nombre = (datos.get("proveedor_nombre") or "").strip()

        if ext:
            existente = Proveedor.objects.filter(
                id_empresa=empresa, referencia_externa=ext
            ).first()
            if existente:
                return existente

        contacto = None
        rif = ""
        if ext:
            mapping = EntidadSincronizada.objects.filter(
                id_instancia=instancia, tipo_entidad="contactos", id_externo=ext
            ).first()
            if mapping and mapping.id_omni:
                from apps.core.models import Contacto

                contacto = Contacto.objects.filter(
                    pk=mapping.id_omni, id_empresa=empresa
                ).first()
                if contacto:
                    rif = getattr(contacto, "rif", "") or ""
                    ya = Proveedor.objects.filter(
                        id_empresa=empresa, contacto=contacto
                    ).first()
                    if ya:
                        return ya

        if not nombre:
            return None

        return Proveedor.objects.create(
            id_empresa=empresa,
            razon_social=nombre,
            rif=rif,
            referencia_externa=ext or None,
            contacto=contacto,
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
            orden = OrdenCompra.objects.filter(
                id_empresa=empresa, numero_orden=numero
            ).first()
            if orden:
                for field, value in campos.items():
                    setattr(orden, field, value)
                orden.save()
            else:
                orden = OrdenCompra.objects.create(
                    id_empresa=empresa, numero_orden=numero, **campos
                )

            orden.detalles.all().delete()
            for linea in datos.get("lineas") or []:
                producto = self._resolver_producto_mapeado(
                    linea.get("product_id"), instancia
                )
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

        from apps.finanzas.models import Moneda
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

        moneda = (
            Moneda.objects.filter(codigo_iso=datos.get("moneda")).first()
            or Moneda.objects.filter(codigo_iso="USD").first()
            or Moneda.objects.first()
        )
        if moneda is None:
            logger.warning(
                "Factura de venta %s omitida: no hay Moneda configurada para "
                "id_moneda (empresa %s).",
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
            factura = FacturaFiscal.objects.filter(
                id_empresa=empresa, numero_factura=numero
            ).first()
            if factura:
                for field, value in campos.items():
                    setattr(factura, field, value)
                factura.save()
            else:
                factura = FacturaFiscal.objects.create(
                    id_empresa=empresa, numero_factura=numero, **campos
                )

            # Reemplazar líneas (la fuente externa es la verdad).
            factura.detalles.all().delete()
            for linea in datos.get("lineas") or []:
                producto = self._resolver_producto_mapeado(
                    linea.get("product_id"), instancia
                )
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

        producto = self._resolver_producto_mapeado(
            datos.get("producto_id_externo"), instancia
        )
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
