"""
Motor transaccional de conciliación N:M Pagos ↔ Facturas/Obligaciones (Ola A2).

Anclado en ``core.Contacto`` y ``finanzas.AsignacionPago`` (patrón
``account.partial.reconcile`` de Odoo):

- Conciliación 1 → N (un ``Pago`` distribuido entre varias obligaciones parciales/totales)
  y N → 1 (múltiples ``Pago`` cubriendo una misma obligación).
- Cálculo de anticipos / saldos a favor por ``core.Contacto`` sin duplicar pagos.
- Propuesta FIFO determinística por fecha de vencimiento.
- Conversión multimoneda con ``TasaCambio`` (nunca fallback implícito 1:1) y
  cálculo + contabilización de diferencial cambiario (``GANANCIA`` / ``PERDIDA``).
- Política contable uniforme ``R-CODE-11`` (``generar_asiento_o_fallar``) más
  ``generar_asiento=False`` explícito para importaciones históricas.
- Sincronía exacta con ``AbonoCxC``, ``AbonoCxP``, ``FacturaFiscal`` y aging,
  más reversión atómica con contra-asiento cuadrado (``R-PROD-4``).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

if TYPE_CHECKING:
    from apps.contabilidad.models import AsientoContable
    from apps.core.models import Contacto, Empresa
    from apps.finanzas.models import AsignacionPago, Moneda, Pago

logger = logging.getLogger(__name__)

_DOS_DECIMALES = Decimal("0.01")
_CUATRO_DECIMALES = Decimal("0.0001")
_OCHO_DECIMALES = Decimal("0.00000001")
_CERO = Decimal("0.0000")
_TOLERANCIA_REDONDEO = Decimal("0.01")

TIPOS_DOCUMENTO_INGRESO = frozenset({"CUENTA_POR_COBRAR", "FACTURA_VENTA"})
TIPOS_DOCUMENTO_EGRESO = frozenset({"CUENTA_POR_PAGAR", "FACTURA_COMPRA"})
TIPOS_DOCUMENTO_VALIDOS = TIPOS_DOCUMENTO_INGRESO | TIPOS_DOCUMENTO_EGRESO


# ── Excepciones de dominio ────────────────────────────────────────────────────


class ConciliacionPagoError(Exception):
    """Error de negocio en conciliación de pagos (datos/estado/topes -> 400)."""


class ConciliacionTenantError(ConciliacionPagoError):
    """Acceso cross-tenant o documento sin empresa asociada (fail-closed -> 404)."""


class ConciliacionContableError(ConciliacionPagoError):
    """Asiento contable obligatorio fallido (R-CODE-11 -> 422 tras rollback)."""


# ── Helpers internos de parseo, scoping y resolución ──────────────────────────


def _parse_decimal_positivo(valor: Any, campo: str) -> Decimal:
    """Convierte a ``Decimal`` finito estrictamente positivo (cero float aritmético)."""
    if valor is None or isinstance(valor, bool):
        raise ConciliacionPagoError(f"El campo '{campo}' es obligatorio y debe ser numérico.")
    if isinstance(valor, Decimal):
        monto = valor
    else:
        texto = str(valor).strip()
        if not texto:
            raise ConciliacionPagoError(f"El campo '{campo}' es obligatorio y no puede estar vacío.")
        try:
            monto = Decimal(texto)
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ConciliacionPagoError(f"Valor numérico inválido para '{campo}': {valor!r}.") from exc
    if not monto.is_finite():
        raise ConciliacionPagoError(f"El valor de '{campo}' debe ser un número finito.")
    if monto <= Decimal("0"):
        raise ConciliacionPagoError(f"El valor de '{campo}' debe ser mayor a cero.")
    return monto


def _parse_tasa_opcional(valor: Any, campo: str) -> Decimal | None:
    """Parsea una tasa opcional; si viene presente exige ``Decimal > 0``."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    return _parse_decimal_positivo(valor, campo)


def _tolerancia_redondeo_moneda(*, misma_moneda: bool, tasa_aplicada: Decimal) -> Decimal:
    """Retorna 0 en misma moneda y tolerancia proporcional a 0.0001*tasa en multimoneda."""
    if misma_moneda:
        return Decimal("0")
    tolerancia_tasa = (Decimal("0.0001") * tasa_aplicada).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)
    return max(_TOLERANCIA_REDONDEO, tolerancia_tasa)


def _fecha_local_pago(pago: "Pago") -> date:
    """Retorna la fecha del pago en la zona horaria del proyecto."""
    fecha_dt = pago.fecha_pago
    if isinstance(fecha_dt, date) and not isinstance(fecha_dt, datetime):
        return fecha_dt
    if timezone.is_aware(fecha_dt):
        return timezone.localdate(fecha_dt)
    return fecha_dt.date()


def _normalizar_uuid_param(raw: Any, mensaje: str) -> UUID:
    if isinstance(raw, UUID):
        return raw
    try:
        return UUID(str(raw))
    except (ValueError, TypeError) as exc:
        raise ConciliacionTenantError(mensaje) from exc


def _extraer_empresa_id(documento: Any) -> UUID:
    """Extrae el UUID de empresa del documento (fail-closed -> ``ConciliacionTenantError``)."""
    if documento is None:
        raise ConciliacionTenantError("El documento destino no existe.")
    for attr in ("id_empresa_id", "empresa_id"):
        if hasattr(documento, attr):
            val = getattr(documento, attr)
            if val is not None:
                return (
                    val
                    if isinstance(val, UUID)
                    else _normalizar_uuid_param(val, "El documento no tiene una empresa válida.")
                )
    raise ConciliacionTenantError(f"El documento {documento.__class__.__name__} no tiene empresa asociada.")


def _resolver_contacto_tercero(
    empresa_id: UUID,
    tercero: Any,
    rol_etiqueta: str,
    etiqueta_doc: str,
) -> "Contacto":
    if tercero is None:
        raise ConciliacionPagoError(f"El documento {etiqueta_doc} no tiene {rol_etiqueta} asociado.")
    if tercero.id_empresa_id != empresa_id:
        raise ConciliacionTenantError(f"El {rol_etiqueta} de {etiqueta_doc} pertenece a otra empresa.")
    contacto = getattr(tercero, "contacto", None)
    if contacto is None:
        raise ConciliacionPagoError(f"El {rol_etiqueta} '{tercero.razon_social}' no tiene un core.Contacto asociado.")
    if contacto.id_empresa_id != empresa_id:
        raise ConciliacionTenantError(f"El contacto del {rol_etiqueta} en {etiqueta_doc} pertenece a otra empresa.")
    if not contacto.activo:
        raise ConciliacionPagoError(f"El contacto asociado a {etiqueta_doc} está inactivo.")
    return contacto


def _resolver_contacto_documento(empresa: "Empresa", documento: Any) -> "Contacto":
    """Resuelve el ``core.Contacto`` común de un documento destino (fail-closed)."""
    from apps.compras.models import FacturaCompra
    from apps.core.models import Contacto
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar
    from apps.cuentas_por_pagar.models import CuentaPorPagar
    from apps.integration_hub.models import EntidadSincronizada
    from apps.proveedores.models import Proveedor
    from apps.ventas.models import FacturaFiscal

    doc_empresa_id = _extraer_empresa_id(documento)
    if doc_empresa_id != empresa.pk:
        raise ConciliacionTenantError(f"El documento {documento.__class__.__name__} pertenece a otra empresa.")

    if isinstance(documento, CuentaPorCobrar):
        if documento.cliente_id is not None:
            return _resolver_contacto_tercero(empresa.pk, documento.cliente, "cliente", "CuentaPorCobrar")

        externo_id = (documento.cliente_externo_id or "").strip()
        if not externo_id:
            raise ConciliacionPagoError("La CuentaPorCobrar no tiene cliente ni identificador externo.")

        if externo_id.startswith("proveedor:"):
            raw_prov_id = externo_id[len("proveedor:") :].strip()
            try:
                prov_uuid = UUID(raw_prov_id)
            except (ValueError, TypeError) as exc:
                raise ConciliacionPagoError(f"Identificador de proveedor externo inválido: '{externo_id}'.") from exc
            proveedor = Proveedor.objects.select_related("contacto").filter(pk=prov_uuid).first()
            if proveedor is None:
                raise ConciliacionPagoError(f"El Proveedor referenciado por '{externo_id}' no existe.")
            if proveedor.id_empresa_id != empresa.pk:
                raise ConciliacionTenantError("El proveedor de reintegro pertenece a otra empresa.")
            if not proveedor.activo:
                raise ConciliacionPagoError(f"El proveedor '{proveedor.razon_social}' está inactivo.")
            return _resolver_contacto_tercero(empresa.pk, proveedor, "proveedor", "CuentaPorCobrar")

        mappings = list(
            EntidadSincronizada.objects.filter(
                id_instancia__id_empresa=empresa,
                id_instancia__activo=True,
                tipo_entidad="contactos",
                id_externo=externo_id,
                activo=True,
                id_omni__isnull=False,
            )
            .exclude(id_omni="")
            .order_by("-ultimo_sync")
        )
        if not mappings:
            raise ConciliacionPagoError(f"No existe Contacto sincronizado para el deudor externo '{externo_id}'.")

        contacto_uuids: set[UUID] = set()
        for mapping in mappings:
            try:
                contacto_uuids.add(UUID(str(mapping.id_omni)))
            except (ValueError, TypeError) as exc:
                raise ConciliacionPagoError(
                    f"Identificador de contacto sincronizado inválido para '{externo_id}'."
                ) from exc

        if len(contacto_uuids) > 1:
            raise ConciliacionPagoError(
                f"Mapeo ambiguo para el deudor externo '{externo_id}': "
                "múltiples instancias activas apuntan a contactos distintos."
            )

        contacto_uuid = next(iter(contacto_uuids))
        contacto = Contacto.objects.filter(pk=contacto_uuid).first()
        if contacto is None:
            raise ConciliacionPagoError(f"El Contacto mapeado para '{externo_id}' no existe.")
        if contacto.id_empresa_id != empresa.pk:
            raise ConciliacionTenantError("El Contacto sincronizado pertenece a otra empresa.")
        if not contacto.activo:
            raise ConciliacionPagoError(f"El Contacto sincronizado para '{externo_id}' está inactivo.")
        return contacto

    if isinstance(documento, FacturaFiscal):
        return _resolver_contacto_tercero(empresa.pk, documento.id_cliente, "cliente", "FacturaFiscal")

    if isinstance(documento, CuentaPorPagar):
        return _resolver_contacto_tercero(empresa.pk, documento.id_proveedor, "proveedor", "CuentaPorPagar")

    if isinstance(documento, FacturaCompra):
        orden = getattr(documento, "id_orden_compra", None)
        if orden is None:
            raise ConciliacionPagoError("La FacturaCompra no tiene orden de compra asociada.")
        if orden.id_empresa_id != empresa.pk:
            raise ConciliacionTenantError("La orden de compra pertenece a otra empresa.")
        return _resolver_contacto_tercero(empresa.pk, orden.id_proveedor, "proveedor", "FacturaCompra")

    raise ConciliacionPagoError(
        f"Tipo de documento no soportado para resolución de contacto: {documento.__class__.__name__}."
    )


def _resolver_moneda_documento(
    empresa: "Empresa",
    pago: "Pago",
    tipo_documento: str,
    documento: Any,
    moneda_explicita: Any = None,
) -> "Moneda":
    """Determina la moneda efectiva del documento y valida scoping multi-tenant."""
    from apps.ventas.models import FacturaFiscal

    if isinstance(documento, FacturaFiscal):
        moneda_doc = documento.id_moneda
        if moneda_explicita is not None and moneda_explicita != "":
            moneda_req = _cargar_moneda_para_empresa(empresa, moneda_explicita)
            if moneda_req.pk != moneda_doc.pk:
                raise ConciliacionPagoError("La moneda indicada no coincide con la moneda de la FacturaFiscal.")
        return moneda_doc

    if moneda_explicita is not None and moneda_explicita != "":
        return _cargar_moneda_para_empresa(empresa, moneda_explicita)

    if empresa.id_moneda_base_id is not None and empresa.id_moneda_base is not None:
        return empresa.id_moneda_base

    return pago.id_moneda


def _cargar_moneda_para_empresa(empresa: "Empresa", raw_moneda: Any) -> "Moneda":
    from apps.finanzas.models import Moneda

    if isinstance(raw_moneda, Moneda):
        moneda = raw_moneda
    else:
        texto = str(raw_moneda).strip()
        if not texto:
            raise ConciliacionPagoError("Debe indicar una moneda válida.")
        moneda_obj: Moneda | None = None
        try:
            moneda_uuid = UUID(texto)
            moneda_obj = Moneda.objects.filter(pk=moneda_uuid).first()
        except (ValueError, TypeError):
            moneda_obj = Moneda.objects.filter(codigo_iso__iexact=texto).first()
        if moneda_obj is None:
            raise ConciliacionPagoError(f"Moneda '{raw_moneda}' no encontrada.")
        moneda = moneda_obj

    if moneda.empresa_id is not None and moneda.empresa_id != empresa.pk and not moneda.es_publica:
        raise ConciliacionTenantError("La moneda pertenece a otra empresa.")
    if not moneda.activo:
        raise ConciliacionPagoError(f"La moneda '{moneda.codigo_iso}' está inactiva.")
    return moneda


# ── Consultas de saldos y sugerencia FIFO ─────────────────────────────────────


def _es_instancia_no_guardada(obj: Any) -> bool:
    if obj is None or getattr(obj, "pk", None) is None:
        return True
    state = getattr(obj, "_state", None)
    return bool(state is not None and getattr(state, "adding", False))


def saldo_disponible_pago(pago: "Pago") -> Decimal:
    """Retorna el saldo no asignado disponible de un ``Pago`` (siempre >= 0)."""
    if _es_instancia_no_guardada(pago):
        raise ConciliacionPagoError("Debe indicar un Pago guardado en base de datos.")
    total_asignado: Decimal = pago.asignaciones.filter(estado="ACTIVA", activo=True).aggregate(
        total=Coalesce(
            Sum("monto_asignado_pago"),
            _CERO,
            output_field=DecimalField(max_digits=18, decimal_places=4),
        )
    )["total"]
    disponible = (Decimal(str(pago.monto)) - Decimal(str(total_asignado))).quantize(
        _CUATRO_DECIMALES, rounding=ROUND_HALF_UP
    )
    return max(_CERO, disponible)


def _total_asignado_documento(empresa_id: UUID, tipo_doc: str, fk_field: str, documento: Any) -> Decimal:
    from apps.finanzas.models import AsignacionPago

    asignado: Decimal = AsignacionPago.objects.filter(
        id_empresa_id=empresa_id,
        tipo_documento=tipo_doc,
        estado="ACTIVA",
        activo=True,
        **{fk_field: documento},
    ).aggregate(
        t=Coalesce(
            Sum("monto_asignado_documento"),
            _CERO,
            output_field=DecimalField(max_digits=18, decimal_places=4),
        )
    )["t"]
    return Decimal(str(asignado)).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)


def saldo_pendiente_documento(documento: Any, *, empresa_id: UUID | str | None = None) -> Decimal:
    """Retorna el saldo pendiente de cobro/pago de un documento soportado."""
    from apps.compras.models import FacturaCompra
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar
    from apps.cuentas_por_pagar.models import CuentaPorPagar
    from apps.ventas.models import FacturaFiscal

    doc_empresa_id = _extraer_empresa_id(documento)
    if empresa_id is not None:
        esperada = _normalizar_uuid_param(empresa_id, "Identificador de empresa inválido.")
        if doc_empresa_id != esperada:
            raise ConciliacionTenantError(f"El documento {documento.__class__.__name__} pertenece a otra empresa.")

    if isinstance(documento, CuentaPorCobrar):
        if documento.estado == "pagada":
            return Decimal("0.00")
        total_abonado: Decimal = documento.abonos.aggregate(
            t=Coalesce(
                Sum("monto"),
                Decimal("0.00"),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )["t"]
        restante = (Decimal(str(documento.monto)) - Decimal(str(total_abonado))).quantize(
            _DOS_DECIMALES, rounding=ROUND_HALF_UP
        )
        return max(Decimal("0.00"), restante)

    if isinstance(documento, CuentaPorPagar):
        if not documento.activo or documento.estado in ("PAGADA", "ANULADA"):
            return _CERO
        return max(
            _CERO,
            Decimal(str(documento.monto_pendiente)).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP),
        )

    if isinstance(documento, FacturaFiscal):
        if not documento.activo or documento.estado in ("ANULADA", "BORRADOR", "PAGADA"):
            return _CERO
        asignado = _total_asignado_documento(doc_empresa_id, "FACTURA_VENTA", "id_factura_venta", documento)
        restante = (Decimal(str(documento.monto_total)) - asignado).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)
        return max(_CERO, restante)

    if isinstance(documento, FacturaCompra):
        if not documento.activo:
            return _CERO
        asignado_fc = _total_asignado_documento(doc_empresa_id, "FACTURA_COMPRA", "id_factura_compra", documento)
        restante = (Decimal(str(documento.monto_total)) - asignado_fc).quantize(
            _CUATRO_DECIMALES, rounding=ROUND_HALF_UP
        )
        return max(_CERO, restante)

    raise ConciliacionPagoError(
        f"Tipo de documento no soportado para cálculo de saldo: {documento.__class__.__name__}."
    )


def saldo_a_favor_contacto(
    empresa: "Empresa",
    contacto: "Contacto",
    *,
    tipo_operacion: str | None = None,
) -> dict[str, Any]:
    """Consulta en BD (sin N+1) los saldos a favor / anticipos disponibles de un contacto."""
    from apps.finanzas.models import Pago

    if empresa is None or contacto is None:
        raise ConciliacionTenantError("Empresa y contacto son obligatorios.")
    if contacto.id_empresa_id != empresa.pk:
        raise ConciliacionTenantError("El contacto no pertenece a la empresa indicada.")
    if tipo_operacion is not None and tipo_operacion not in ("INGRESO", "EGRESO"):
        raise ConciliacionPagoError(f"tipo_operacion inválido: {tipo_operacion!r}.")

    qs = (
        Pago.objects.filter(id_empresa=empresa, id_contacto=contacto)
        .select_related("id_moneda")
        .annotate(
            monto_asignado_agg=Coalesce(
                Sum(
                    "asignaciones__monto_asignado_pago",
                    filter=Q(asignaciones__estado="ACTIVA", asignaciones__activo=True),
                ),
                _CERO,
                output_field=DecimalField(max_digits=18, decimal_places=4),
            )
        )
        .annotate(
            saldo_disponible_agg=ExpressionWrapper(
                F("monto") - F("monto_asignado_agg"),
                output_field=DecimalField(max_digits=18, decimal_places=4),
            )
        )
        .filter(saldo_disponible_agg__gt=Decimal("0"))
        .order_by("fecha_pago", "id_pago")
    )
    if tipo_operacion is not None:
        qs = qs.filter(tipo_operacion=tipo_operacion)

    pagos_con_saldo: list[dict[str, Any]] = []
    total_por_moneda: dict[str, dict[str, Any]] = {}
    por_operacion: dict[str, dict[str, Decimal]] = {"INGRESO": {}, "EGRESO": {}}

    for pago in qs:
        saldo_disp = Decimal(str(pago.saldo_disponible_agg)).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)
        monto_orig = Decimal(str(pago.monto)).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)
        monto_asig = Decimal(str(pago.monto_asignado_agg)).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)
        moneda = pago.id_moneda
        codigo = moneda.codigo_iso

        pagos_con_saldo.append(
            {
                "pago_id": str(pago.id_pago),
                "tipo_operacion": pago.tipo_operacion,
                "tipo_documento": pago.tipo_documento,
                "fecha_pago": pago.fecha_pago,
                "moneda_id": str(moneda.id_moneda),
                "moneda_codigo": codigo,
                "monto_original": monto_orig,
                "monto_asignado": monto_asig,
                "saldo_disponible": saldo_disp,
                "referencia": pago.referencia or "",
            }
        )

        if codigo not in total_por_moneda:
            total_por_moneda[codigo] = {
                "moneda_id": str(moneda.id_moneda),
                "codigo_iso": codigo,
                "simbolo": moneda.simbolo,
                "INGRESO": _CERO,
                "EGRESO": _CERO,
                "cantidad_pagos": 0,
            }
        grupo = total_por_moneda[codigo]
        if pago.tipo_operacion == "INGRESO":
            grupo["INGRESO"] = Decimal(grupo["INGRESO"]) + saldo_disp
        else:
            grupo["EGRESO"] = Decimal(grupo["EGRESO"]) + saldo_disp
        grupo["cantidad_pagos"] = int(grupo["cantidad_pagos"]) + 1

        op_map = por_operacion[pago.tipo_operacion]
        op_map[codigo] = op_map.get(codigo, _CERO) + saldo_disp

    return {
        "empresa_id": str(empresa.pk),
        "contacto_id": str(contacto.pk),
        "tipo_operacion": tipo_operacion,
        "total_por_moneda": total_por_moneda,
        "por_operacion": por_operacion,
        "pagos_con_saldo": pagos_con_saldo,
    }


def sugerir_distribucion_fifo(pago: "Pago", *, tipo_documento: str | None = None) -> dict[str, Any]:
    """Propone distribución FIFO determinística de un ``Pago`` sobre obligaciones abiertas del contacto."""
    from apps.compras.models import FacturaCompra
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar
    from apps.cuentas_por_pagar.models import CuentaPorPagar
    from apps.finanzas.services import TasaCambioError, obtener_tasa_cambio
    from apps.integration_hub.models import EntidadSincronizada
    from apps.ventas.models import FacturaFiscal

    empresa_id = _extraer_empresa_id(pago)
    if pago.id_contacto_id is None:
        raise ConciliacionPagoError("El pago debe tener un contacto asignado para sugerir distribución.")
    contacto = pago.id_contacto
    if contacto is None or contacto.id_empresa_id != empresa_id:
        raise ConciliacionTenantError("El contacto del pago pertenece a otra empresa.")
    if not contacto.activo:
        raise ConciliacionPagoError("El contacto del pago está inactivo.")

    if pago.tipo_operacion == "INGRESO":
        tipos_permitidos = TIPOS_DOCUMENTO_INGRESO
    elif pago.tipo_operacion == "EGRESO":
        tipos_permitidos = TIPOS_DOCUMENTO_EGRESO
    else:
        raise ConciliacionPagoError(f"Tipo de operación no soportado: {pago.tipo_operacion!r}.")

    if tipo_documento is not None:
        if tipo_documento not in tipos_permitidos:
            raise ConciliacionPagoError(
                f"El tipo de documento {tipo_documento!r} no es compatible con operación {pago.tipo_operacion}."
            )
        tipos_buscar: frozenset[str] = frozenset({tipo_documento})
    else:
        tipos_buscar = tipos_permitidos

    disponible = saldo_disponible_pago(pago)
    if disponible <= Decimal("0"):
        return {
            "pago_id": str(pago.pk),
            "saldo_disponible": _CERO,
            "propuestas": [],
            "total_a_aplicar": _CERO,
            "saldo_a_favor_resultante": _CERO,
            "omitidas_sin_tasa": [],
        }

    empresa = pago.id_empresa
    moneda_base_default = empresa.id_moneda_base or pago.id_moneda
    fecha_ref = _fecha_local_pago(pago)

    # Cada candidato: (sort_key, tipo_doc, pk_str, ref, fecha_emision, fecha_vcto, moneda_doc, saldo_doc)
    candidatos: list[tuple[tuple[date, date, str], str, str, str, date, date, "Moneda", Decimal]] = []

    if "CUENTA_POR_COBRAR" in tipos_buscar:
        from apps.proveedores.models import Proveedor

        candidatos_ext = list(
            EntidadSincronizada.objects.filter(
                id_instancia__id_empresa=empresa,
                id_instancia__activo=True,
                tipo_entidad="contactos",
                id_omni=str(contacto.pk),
                activo=True,
            )
            .exclude(id_externo="")
            .values_list("id_externo", flat=True)
        )
        externo_ids_buscar: list[str] = []
        if candidatos_ext:
            conflicting = set(
                EntidadSincronizada.objects.filter(
                    id_instancia__id_empresa=empresa,
                    id_instancia__activo=True,
                    tipo_entidad="contactos",
                    id_externo__in=candidatos_ext,
                    activo=True,
                    id_omni__isnull=False,
                )
                .exclude(id_omni="")
                .exclude(id_omni=str(contacto.pk))
                .values_list("id_externo", flat=True)
            )
            externo_ids_buscar = [eid for eid in candidatos_ext if eid not in conflicting]

        prov_ids = list(
            Proveedor.objects.filter(id_empresa_id=empresa_id, contacto=contacto, activo=True).values_list(
                "pk", flat=True
            )
        )
        for prov_pk in prov_ids:
            externo_ids_buscar.append(f"proveedor:{prov_pk}")

        filtro_contacto = Q(cliente__contacto_id=contacto.pk, cliente__id_empresa_id=empresa_id)
        if externo_ids_buscar:
            filtro_contacto |= Q(cliente__isnull=True, cliente_externo_id__in=externo_ids_buscar)
        cxc_qs = (
            CuentaPorCobrar.objects.filter(
                empresa_id=empresa_id,
                estado__in=["pendiente", "parcial", "vencida"],
            )
            .filter(filtro_contacto)
            .annotate(
                total_abonado_agg=Coalesce(
                    Sum("abonos__monto"),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
        )
        for cxc in cxc_qs:
            saldo_cxc = (Decimal(str(cxc.monto)) - Decimal(str(cxc.total_abonado_agg))).quantize(
                _DOS_DECIMALES, rounding=ROUND_HALF_UP
            )
            if saldo_cxc <= Decimal("0"):
                continue
            sort_key = (cxc.fecha_vencimiento, cxc.fecha_emision, str(cxc.pk))
            candidatos.append(
                (
                    sort_key,
                    "CUENTA_POR_COBRAR",
                    str(cxc.pk),
                    cxc.referencia_externa or f"CxC-{cxc.pk}",
                    cxc.fecha_emision,
                    cxc.fecha_vencimiento,
                    moneda_base_default,
                    saldo_cxc,
                )
            )

    if "FACTURA_VENTA" in tipos_buscar:
        fv_qs = (
            FacturaFiscal.objects.filter(
                id_empresa_id=empresa_id,
                activo=True,
                estado__in=["EMITIDA", "VENCIDA"],
                id_cliente__contacto_id=contacto.pk,
                id_cliente__id_empresa_id=empresa_id,
            )
            .select_related("id_moneda")
            .annotate(
                total_asig_agg=Coalesce(
                    Sum(
                        "asignaciones_pago__monto_asignado_documento",
                        filter=Q(asignaciones_pago__estado="ACTIVA", asignaciones_pago__activo=True),
                    ),
                    _CERO,
                    output_field=DecimalField(max_digits=18, decimal_places=4),
                )
            )
        )
        for fv in fv_qs:
            saldo_fv = (Decimal(str(fv.monto_total)) - Decimal(str(fv.total_asig_agg))).quantize(
                _CUATRO_DECIMALES, rounding=ROUND_HALF_UP
            )
            if saldo_fv <= Decimal("0"):
                continue
            fecha_vcto = fv.fecha_vencimiento or fv.fecha_emision
            sort_key = (fecha_vcto, fv.fecha_emision, str(fv.pk))
            candidatos.append(
                (
                    sort_key,
                    "FACTURA_VENTA",
                    str(fv.pk),
                    fv.numero_factura,
                    fv.fecha_emision,
                    fecha_vcto,
                    fv.id_moneda,
                    saldo_fv,
                )
            )

    if "CUENTA_POR_PAGAR" in tipos_buscar:
        cxp_qs = CuentaPorPagar.objects.filter(
            id_empresa_id=empresa_id,
            activo=True,
            estado__in=["PENDIENTE", "PARCIAL", "VENCIDA"],
            monto_pendiente__gt=Decimal("0"),
            id_proveedor__contacto_id=contacto.pk,
            id_proveedor__id_empresa_id=empresa_id,
        )
        for cxp in cxp_qs:
            saldo_cxp = Decimal(str(cxp.monto_pendiente)).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)
            if saldo_cxp <= Decimal("0"):
                continue
            sort_key = (cxp.fecha_vencimiento, cxp.fecha_emision, str(cxp.pk))
            candidatos.append(
                (
                    sort_key,
                    "CUENTA_POR_PAGAR",
                    str(cxp.pk),
                    cxp.referencia_externa or f"CxP-{str(cxp.pk)[:8]}",
                    cxp.fecha_emision,
                    cxp.fecha_vencimiento,
                    moneda_base_default,
                    saldo_cxp,
                )
            )

    if "FACTURA_COMPRA" in tipos_buscar:
        fc_qs = FacturaCompra.objects.filter(
            id_empresa_id=empresa_id,
            activo=True,
            id_orden_compra__id_empresa_id=empresa_id,
            id_orden_compra__id_proveedor__contacto_id=contacto.pk,
            id_orden_compra__id_proveedor__id_empresa_id=empresa_id,
        ).annotate(
            total_asig_agg=Coalesce(
                Sum(
                    "asignaciones_pago__monto_asignado_documento",
                    filter=Q(asignaciones_pago__estado="ACTIVA", asignaciones_pago__activo=True),
                ),
                _CERO,
                output_field=DecimalField(max_digits=18, decimal_places=4),
            )
        )
        for fc in fc_qs:
            saldo_fc = (Decimal(str(fc.monto_total)) - Decimal(str(fc.total_asig_agg))).quantize(
                _CUATRO_DECIMALES, rounding=ROUND_HALF_UP
            )
            if saldo_fc <= Decimal("0"):
                continue
            sort_key = (fc.fecha_emision, fc.fecha_emision, str(fc.pk))
            candidatos.append(
                (
                    sort_key,
                    "FACTURA_COMPRA",
                    str(fc.pk),
                    fc.numero_factura,
                    fc.fecha_emision,
                    fc.fecha_emision,
                    moneda_base_default,
                    saldo_fc,
                )
            )

    candidatos.sort(key=lambda item: item[0])

    restante_pago = disponible
    total_a_aplicar = _CERO
    propuestas: list[dict[str, Any]] = []
    omitidas_sin_tasa: list[dict[str, str]] = []
    tasas_cache: dict[UUID, Decimal] = {}

    for _sort_key, tipo_doc, pk_str, ref_str, f_emision, f_vcto, moneda_doc, saldo_doc in candidatos:
        if restante_pago <= Decimal("0"):
            break

        if moneda_doc.pk == pago.id_moneda_id:
            tasa_aplicada = Decimal("1.00000000")
        elif moneda_doc.pk in tasas_cache:
            tasa_aplicada = tasas_cache[moneda_doc.pk]
        else:
            try:
                tasa_obj = obtener_tasa_cambio(
                    pago.id_moneda,
                    moneda_doc,
                    empresa=empresa,
                    fecha=fecha_ref,
                )
                tasa_aplicada = Decimal(str(tasa_obj.valor_tasa))
                tasas_cache[moneda_doc.pk] = tasa_aplicada
            except TasaCambioError as exc:
                omitidas_sin_tasa.append(
                    {
                        "tipo_documento": tipo_doc,
                        "id_documento": pk_str,
                        "moneda_codigo": moneda_doc.codigo_iso,
                        "motivo": str(exc),
                    }
                )
                continue

        if tasa_aplicada <= Decimal("0"):
            continue

        quant_doc = _DOS_DECIMALES if tipo_doc == "CUENTA_POR_COBRAR" else _CUATRO_DECIMALES
        misma_moneda = moneda_doc.pk == pago.id_moneda_id
        tolerancia = _tolerancia_redondeo_moneda(misma_moneda=misma_moneda, tasa_aplicada=tasa_aplicada)

        if misma_moneda:
            tope_linea = min(restante_pago, saldo_doc)
            quant_pago_misma = _DOS_DECIMALES if tipo_doc == "CUENTA_POR_COBRAR" else _CUATRO_DECIMALES
            monto_aplicar_pago = tope_linea.quantize(quant_pago_misma, rounding=ROUND_DOWN)
            monto_aplicar_doc = monto_aplicar_pago.quantize(quant_doc, rounding=ROUND_DOWN)
        else:
            necesario_pago = max(
                _CUATRO_DECIMALES,
                (saldo_doc / tasa_aplicada).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP),
            )
            if restante_pago >= necesario_pago:
                monto_aplicar_pago = necesario_pago
                monto_aplicar_doc = saldo_doc.quantize(quant_doc, rounding=ROUND_HALF_UP)
                if abs(monto_aplicar_doc - (monto_aplicar_pago * tasa_aplicada)) > tolerancia:
                    monto_aplicar_doc = min(
                        saldo_doc,
                        (monto_aplicar_pago * tasa_aplicada).quantize(quant_doc, rounding=ROUND_HALF_UP),
                    )
            else:
                monto_aplicar_pago = restante_pago.quantize(_CUATRO_DECIMALES, rounding=ROUND_DOWN)
                monto_aplicar_doc = min(
                    saldo_doc,
                    (monto_aplicar_pago * tasa_aplicada).quantize(quant_doc, rounding=ROUND_HALF_UP),
                )

        if monto_aplicar_pago <= Decimal("0") or monto_aplicar_doc <= Decimal("0"):
            continue

        restante_pago = (restante_pago - monto_aplicar_pago).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)
        total_a_aplicar = (total_a_aplicar + monto_aplicar_pago).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)

        propuestas.append(
            {
                "tipo_documento": tipo_doc,
                "id_documento": pk_str,
                "referencia": ref_str,
                "fecha_emision": f_emision,
                "fecha_vencimiento": f_vcto,
                "moneda_documento": str(moneda_doc.pk),
                "moneda_documento_codigo": moneda_doc.codigo_iso,
                "saldo_pendiente_documento": saldo_doc,
                "tasa_aplicada": tasa_aplicada,
                "monto_asignado_pago": monto_aplicar_pago,
                "monto_asignado_documento": monto_aplicar_doc,
            }
        )

    saldo_resultante = (disponible - total_a_aplicar).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)
    if saldo_resultante < Decimal("0"):
        raise ConciliacionPagoError(
            f"La distribución FIFO excede el saldo disponible del pago ({total_a_aplicar} > {disponible})."
        )
    return {
        "pago_id": str(pago.pk),
        "saldo_disponible": disponible,
        "propuestas": propuestas,
        "total_a_aplicar": total_a_aplicar,
        "saldo_a_favor_resultante": saldo_resultante,
        "omitidas_sin_tasa": omitidas_sin_tasa,
    }


# ── Helpers de bloqueo y resolución de targets ────────────────────────────────


def _normalizar_target_item(item: Mapping[str, Any]) -> tuple[str, int | UUID]:
    from apps.compras.models import FacturaCompra
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar
    from apps.cuentas_por_pagar.models import CuentaPorPagar
    from apps.ventas.models import FacturaFiscal

    if not isinstance(item, Mapping):
        raise ConciliacionPagoError("Cada ítem de asignación debe ser un diccionario.")

    tipo_doc = str(item.get("tipo_documento") or "").strip()
    if tipo_doc not in TIPOS_DOCUMENTO_VALIDOS:
        raise ConciliacionPagoError(f"tipo_documento inválido: {tipo_doc!r}.")

    modelo_por_tipo: dict[str, type[Any]] = {
        "CUENTA_POR_COBRAR": CuentaPorCobrar,
        "CUENTA_POR_PAGAR": CuentaPorPagar,
        "FACTURA_VENTA": FacturaFiscal,
        "FACTURA_COMPRA": FacturaCompra,
    }
    expected_cls = modelo_por_tipo[tipo_doc]

    doc_obj = item.get("documento")
    raw_id = item.get("id_documento")
    if doc_obj is not None:
        if not isinstance(doc_obj, expected_cls):
            raise ConciliacionPagoError(f"La instancia entregada en 'documento' no corresponde a {tipo_doc}.")
        if _es_instancia_no_guardada(doc_obj):
            raise ConciliacionPagoError("El documento destino debe estar guardado en BD.")
        if raw_id is not None and str(raw_id) != str(doc_obj.pk):
            raise ConciliacionPagoError("id_documento no coincide con la instancia en 'documento'.")
        pk_norm: int | UUID = doc_obj.pk
        return tipo_doc, pk_norm

    if raw_id is None or (isinstance(raw_id, str) and not raw_id.strip()):
        raise ConciliacionPagoError("Cada asignación debe indicar 'id_documento' o 'documento'.")

    if tipo_doc == "CUENTA_POR_COBRAR":
        if isinstance(raw_id, bool):
            raise ConciliacionPagoError("id_documento inválido para CuentaPorCobrar.")
        try:
            return tipo_doc, int(str(raw_id).strip())
        except (ValueError, TypeError) as exc:
            raise ConciliacionPagoError(f"id_documento inválido para CuentaPorCobrar: {raw_id!r}.") from exc

    try:
        return tipo_doc, raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id).strip())
    except (ValueError, TypeError) as exc:
        raise ConciliacionPagoError(f"id_documento UUID inválido para {tipo_doc}: {raw_id!r}.") from exc


def _lock_target_documento(tipo_doc: str, pk_norm: int | UUID) -> Any:
    """Adquiere ``select_for_update()`` sobre el documento destino."""
    from apps.compras.models import FacturaCompra
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar
    from apps.cuentas_por_pagar.models import CuentaPorPagar
    from apps.ventas.models import FacturaFiscal

    try:
        if tipo_doc == "CUENTA_POR_COBRAR":
            cxc_pk = pk_norm if isinstance(pk_norm, int) and not isinstance(pk_norm, bool) else int(str(pk_norm))
            return CuentaPorCobrar.objects.select_for_update().get(pk=cxc_pk)
        uuid_pk = pk_norm if isinstance(pk_norm, UUID) else UUID(str(pk_norm))
        if tipo_doc == "CUENTA_POR_PAGAR":
            return CuentaPorPagar.objects.select_for_update().get(pk=uuid_pk)
        if tipo_doc == "FACTURA_VENTA":
            return FacturaFiscal.objects.select_for_update().get(pk=uuid_pk)
        if tipo_doc == "FACTURA_COMPRA":
            return FacturaCompra.objects.select_for_update().get(pk=uuid_pk)
    except (
        CuentaPorCobrar.DoesNotExist,
        CuentaPorPagar.DoesNotExist,
        FacturaFiscal.DoesNotExist,
        FacturaCompra.DoesNotExist,
        ValueError,
        TypeError,
    ) as exc:
        raise ConciliacionTenantError(f"Documento {tipo_doc}:{pk_norm} no encontrado o sin acceso.") from exc

    raise ConciliacionPagoError(f"tipo_documento inválido: {tipo_doc!r}.")


def _validar_estado_abierto_documento(tipo_doc: str, doc: Any) -> None:
    if tipo_doc == "CUENTA_POR_COBRAR":
        if doc.estado == "pagada":
            raise ConciliacionPagoError("La CuentaPorCobrar ya se encuentra pagada.")
    elif tipo_doc == "CUENTA_POR_PAGAR":
        if not doc.activo or doc.estado in ("PAGADA", "ANULADA"):
            raise ConciliacionPagoError(f"La CuentaPorPagar no acepta conciliaciones en estado '{doc.estado}'.")
    elif tipo_doc == "FACTURA_VENTA":
        if not doc.activo or doc.estado in ("BORRADOR", "ANULADA", "PAGADA"):
            raise ConciliacionPagoError(f"La FacturaFiscal no acepta conciliaciones en estado '{doc.estado}'.")
    elif tipo_doc == "FACTURA_COMPRA":
        if not doc.activo:
            raise ConciliacionPagoError("La FacturaCompra está inactiva y no puede conciliarse.")


def _calcular_diferencial_cambiario(
    *,
    tipo_operacion: str,
    tipo_doc: str,
    documento: Any,
    pago: "Pago",
    empresa: "Empresa",
    moneda_doc: "Moneda",
    monto_asignado_pago: Decimal,
    monto_asignado_documento: Decimal,
    tasa_original_raw: Any,
    tasa_liquidacion_raw: Any,
) -> tuple[Decimal, str]:
    """Calcula monto y signo del diferencial cambiario (``GANANCIA`` / ``PERDIDA``)."""
    moneda_funcional_id = empresa.id_moneda_base_id or empresa.id_moneda_pais_id
    if (
        moneda_funcional_id is not None
        and moneda_doc.pk == moneda_funcional_id
        and pago.id_moneda_id == moneda_funcional_id
    ):
        return _CERO, ""

    tasa_orig = _parse_tasa_opcional(tasa_original_raw, "tasa_original")
    tasa_liq = _parse_tasa_opcional(tasa_liquidacion_raw, "tasa_liquidacion")

    if tasa_orig is None and tasa_liq is None:
        if tipo_doc == "FACTURA_VENTA" and moneda_doc.pk == pago.id_moneda_id:
            tasa_orig_eff = Decimal(str(documento.tasa_cambio))
            tasa_liq_eff = Decimal(str(pago.tasa))
        else:
            return _CERO, ""
    elif tasa_orig is not None and tasa_liq is not None:
        tasa_orig_eff = tasa_orig
        tasa_liq_eff = tasa_liq
    elif tasa_orig is None and tasa_liq is not None:
        if tipo_doc == "FACTURA_VENTA" and moneda_doc.pk == pago.id_moneda_id:
            tasa_orig_eff = Decimal(str(documento.tasa_cambio))
            tasa_liq_eff = tasa_liq
        else:
            return _CERO, ""
    else:
        if tasa_orig is None:
            return _CERO, ""
        tasa_orig_eff = tasa_orig
        tasa_liq_eff = Decimal(str(pago.tasa))

    if tasa_orig_eff <= Decimal("0") or tasa_liq_eff <= Decimal("0"):
        raise ConciliacionPagoError("Las tasas de cambio para diferencial cambiario deben ser mayores a cero.")

    delta = tasa_liq_eff - tasa_orig_eff
    if delta == Decimal("0"):
        return _CERO, ""

    if moneda_doc.pk != pago.id_moneda_id and moneda_funcional_id is not None and moneda_doc.pk == moneda_funcional_id:
        monto_base_calculo = monto_asignado_pago
    else:
        monto_base_calculo = monto_asignado_documento

    diferencia = (monto_base_calculo * abs(delta)).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)
    if diferencia <= Decimal("0"):
        return _CERO, ""

    if tipo_operacion == "INGRESO":
        tipo_diferencia = "GANANCIA" if delta > Decimal("0") else "PERDIDA"
    else:
        tipo_diferencia = "PERDIDA" if delta > Decimal("0") else "GANANCIA"

    return diferencia, tipo_diferencia


def _resolver_monto_asiento_moneda_base(
    *,
    empresa: "Empresa",
    tipo_asiento: str,
    pago: "Pago",
    moneda_doc: "Moneda",
    monto_pago: Decimal,
    monto_doc: Decimal,
    fecha_ref: date,
) -> Decimal | None:
    """Convierte el monto del asiento principal a ``empresa.id_moneda_base``."""
    from apps.contabilidad.models import MapeoContable
    from apps.finanzas.services import TasaCambioError, convertir_monto

    moneda_base = empresa.id_moneda_base
    if moneda_base is None or pago.id_moneda_id == moneda_base.pk:
        return monto_pago
    if moneda_doc.pk == moneda_base.pk:
        return monto_doc
    try:
        return convertir_monto(
            monto_pago,
            pago.id_moneda,
            moneda_base,
            empresa=empresa,
            fecha=fecha_ref,
        )
    except TasaCambioError as exc:
        tiene_mapeo = MapeoContable.objects.filter(
            id_empresa=empresa,
            tipo_asiento=tipo_asiento,
            activo=True,
        ).exists()
        if getattr(empresa, "contabilidad_activa", False) or tiene_mapeo:
            raise ConciliacionContableError(
                f"No se pudo convertir el monto del asiento {tipo_asiento} a moneda base "
                f"{moneda_base.codigo_iso}: {exc}"
            ) from exc
        logger.warning(
            "Asiento %s omitido por falta de tasa hacia moneda base (%s -> %s) en modo sin fricción.",
            tipo_asiento,
            pago.id_moneda.codigo_iso,
            moneda_base.codigo_iso,
        )
        return None


# ── Operación principal: aplicar_pago_a_documentos ────────────────────────────


@transaction.atomic
def aplicar_pago_a_documentos(
    pago: "Pago",
    asignaciones: Sequence[Mapping[str, Any]],
    *,
    usuario: Any = None,
    generar_asiento: bool = True,
    descripcion: str = "",
) -> list["AsignacionPago"]:
    """Aplica un ``Pago`` a 1..N documentos destino dentro de una transacción atómica."""
    from apps.contabilidad.services import AsientoError, generar_asiento_o_fallar
    from apps.cuentas_por_cobrar.models import AbonoCxC
    from apps.cuentas_por_pagar.models import AbonoCxP
    from apps.finanzas.models import AsignacionPago, Pago
    from apps.finanzas.services import TasaCambioError, obtener_tasa_cambio

    if _es_instancia_no_guardada(pago):
        raise ConciliacionPagoError("Debe indicar un Pago guardado en base de datos.")
    if not asignaciones or isinstance(asignaciones, (str, bytes, Mapping)):
        raise ConciliacionPagoError("Debe especificar al menos una asignación válida.")

    # 1. Validar y normalizar estructura del lote antes de adquirir locks.
    items_normalizados: list[tuple[Mapping[str, Any], str, int | UUID, Decimal]] = []
    targets_unicos: set[tuple[str, int | UUID]] = set()
    for item in asignaciones:
        tipo_doc, pk_norm = _normalizar_target_item(item)
        monto_pago = _parse_decimal_positivo(item.get("monto_asignado_pago"), "monto_asignado_pago")
        items_normalizados.append((item, tipo_doc, pk_norm, monto_pago))
        targets_unicos.add((tipo_doc, pk_norm))

    # 2. Lock determinístico: Pago primero, luego targets ordenados por (tipo_documento, str(pk)).
    try:
        pago_locked = Pago.objects.select_for_update().get(pk=pago.pk)
    except Pago.DoesNotExist as exc:
        raise ConciliacionTenantError("El pago indicado no existe.") from exc

    empresa_id = _extraer_empresa_id(pago_locked)
    empresa = pago_locked.id_empresa

    if pago_locked.tipo_operacion == "INGRESO":
        tipos_permitidos = TIPOS_DOCUMENTO_INGRESO
    elif pago_locked.tipo_operacion == "EGRESO":
        tipos_permitidos = TIPOS_DOCUMENTO_EGRESO
    else:
        raise ConciliacionPagoError(f"Tipo de operación de pago inválido: {pago_locked.tipo_operacion!r}.")

    for _item, tipo_doc, _pk_norm, _monto_pago in items_normalizados:
        if tipo_doc not in tipos_permitidos:
            raise ConciliacionPagoError(
                f"El tipo de documento {tipo_doc!r} no es compatible con un pago {pago_locked.tipo_operacion}."
            )

    targets_locked: dict[tuple[str, str], Any] = {}
    saldos_doc_restantes: dict[tuple[str, str], Decimal] = {}
    contactos_resueltos: list["Contacto"] = []

    for tipo_doc, pk_norm in sorted(targets_unicos, key=lambda k: (k[0], str(k[1]))):
        doc_locked = _lock_target_documento(tipo_doc, pk_norm)
        doc_emp_id = _extraer_empresa_id(doc_locked)
        if doc_emp_id != empresa_id:
            raise ConciliacionTenantError(f"El documento {tipo_doc}:{pk_norm} pertenece a otra empresa.")
        _validar_estado_abierto_documento(tipo_doc, doc_locked)
        contacto_doc = _resolver_contacto_documento(empresa, doc_locked)
        contactos_resueltos.append(contacto_doc)

        key = (tipo_doc, str(pk_norm))
        targets_locked[key] = doc_locked
        saldos_doc_restantes[key] = saldo_pendiente_documento(doc_locked, empresa_id=empresa_id)

    # 3. Validar identidad de core.Contacto común y asignarlo al Pago si faltaba.
    contacto_pago: "Contacto | None" = pago_locked.id_contacto
    if pago_locked.id_contacto_id is not None:
        if contacto_pago is None or contacto_pago.id_empresa_id != empresa_id:
            raise ConciliacionTenantError("El contacto del pago pertenece a otra empresa.")
        if not contacto_pago.activo:
            raise ConciliacionPagoError("El contacto del pago está inactivo.")
        for c_doc in contactos_resueltos:
            if c_doc.pk != contacto_pago.pk:
                raise ConciliacionPagoError("Todos los documentos conciliados deben pertenecer al contacto del pago.")
    else:
        contacto_ids = {c.pk for c in contactos_resueltos}
        if len(contacto_ids) != 1:
            raise ConciliacionPagoError(
                "Todos los documentos de un pago sin contacto previo deben pertenecer al mismo contacto."
            )
        contacto_pago = contactos_resueltos[0]
        pago_locked.id_contacto = contacto_pago
        pago_locked.save(update_fields=["id_contacto", "fecha_actualizacion"])
        pago.id_contacto = contacto_pago

    if contacto_pago is None:
        raise ConciliacionPagoError("No se pudo resolver el contacto del pago.")

    # 4. Verificar tope disponible del pago contra la suma total del lote.
    disponible_pago = saldo_disponible_pago(pago_locked)
    total_lote_pago = sum((m for _, _, _, m in items_normalizados), Decimal("0"))
    if total_lote_pago > disponible_pago:
        raise ConciliacionPagoError(
            f"La suma asignada ({total_lote_pago}) excede el saldo disponible del pago ({disponible_pago})."
        )

    fecha_ref_pago = _fecha_local_pago(pago_locked)
    tipo_asiento = "PAGO_CXC" if pago_locked.tipo_operacion == "INGRESO" else "PAGO_CXP"
    creadas: list[AsignacionPago] = []

    # 5. Ejecutar cada imputación en orden del lote.
    for item, tipo_doc, pk_norm, monto_pago in items_normalizados:
        key = (tipo_doc, str(pk_norm))
        doc_locked = targets_locked[key]
        saldo_doc_actual = saldos_doc_restantes[key]

        moneda_doc = _resolver_moneda_documento(
            empresa,
            pago_locked,
            tipo_doc,
            doc_locked,
            item.get("moneda_documento"),
        )

        tasa_explicit = _parse_tasa_opcional(item.get("tasa_aplicada"), "tasa_aplicada")
        if moneda_doc.pk == pago_locked.id_moneda_id:
            if tasa_explicit is not None and tasa_explicit != Decimal("1"):
                raise ConciliacionPagoError(
                    "Cuando la moneda del pago y la del documento coinciden, tasa_aplicada debe ser 1."
                )
            tasa_aplicada = Decimal("1.00000000")
        else:
            if tasa_explicit is not None:
                tasa_aplicada = tasa_explicit.quantize(_OCHO_DECIMALES, rounding=ROUND_HALF_UP)
            else:
                try:
                    tasa_obj = obtener_tasa_cambio(
                        pago_locked.id_moneda,
                        moneda_doc,
                        empresa=empresa,
                        fecha=fecha_ref_pago,
                    )
                except TasaCambioError as exc:
                    raise ConciliacionPagoError(str(exc)) from exc
                tasa_aplicada = Decimal(str(tasa_obj.valor_tasa))

        if tasa_aplicada <= Decimal("0"):
            raise ConciliacionPagoError("La tasa aplicada debe ser mayor a cero.")

        quant_doc = _DOS_DECIMALES if tipo_doc == "CUENTA_POR_COBRAR" else _CUATRO_DECIMALES
        misma_moneda = moneda_doc.pk == pago_locked.id_moneda_id
        tolerancia = _tolerancia_redondeo_moneda(misma_moneda=misma_moneda, tasa_aplicada=tasa_aplicada)
        if misma_moneda and tipo_doc == "CUENTA_POR_COBRAR" and monto_pago != monto_pago.quantize(_DOS_DECIMALES):
            raise ConciliacionPagoError(
                "Para CUENTA_POR_COBRAR el monto_asignado_documento debe ser múltiplo exacto de 0.01."
            )
        esperado_raw = monto_pago * tasa_aplicada
        monto_doc_raw = item.get("monto_asignado_documento")

        if monto_doc_raw is None or (isinstance(monto_doc_raw, str) and not monto_doc_raw.strip()):
            monto_doc = esperado_raw.quantize(quant_doc, rounding=ROUND_HALF_UP)
        else:
            monto_doc_parsed = _parse_decimal_positivo(monto_doc_raw, "monto_asignado_documento")
            if misma_moneda:
                if monto_doc_parsed != monto_pago:
                    raise ConciliacionPagoError(
                        f"En la misma moneda, monto_asignado_documento ({monto_doc_parsed}) "
                        f"debe coincidir exactamente con monto_asignado_pago ({monto_pago})."
                    )
            elif abs(monto_doc_parsed - esperado_raw) > tolerancia:
                raise ConciliacionPagoError(
                    f"El monto_asignado_documento ({monto_doc_parsed}) difiere de "
                    f"monto_asignado_pago * tasa_aplicada ({esperado_raw.quantize(quant_doc, rounding=ROUND_HALF_UP)})."
                )
            if tipo_doc == "CUENTA_POR_COBRAR" and monto_doc_parsed != monto_doc_parsed.quantize(_DOS_DECIMALES):
                raise ConciliacionPagoError(
                    "Para CUENTA_POR_COBRAR el monto_asignado_documento debe ser múltiplo exacto de 0.01."
                )
            monto_doc = monto_doc_parsed.quantize(quant_doc, rounding=ROUND_HALF_UP)

        if monto_doc <= Decimal("0"):
            raise ConciliacionPagoError("El monto aplicado al documento debe ser mayor a cero.")

        if monto_doc > saldo_doc_actual:
            raise ConciliacionPagoError(
                f"El monto aplicado ({monto_doc}) excede el saldo pendiente del documento {tipo_doc}:{pk_norm} ({saldo_doc_actual})."
            )

        diferencia, tipo_diferencia = _calcular_diferencial_cambiario(
            tipo_operacion=pago_locked.tipo_operacion,
            tipo_doc=tipo_doc,
            documento=doc_locked,
            pago=pago_locked,
            empresa=empresa,
            moneda_doc=moneda_doc,
            monto_asignado_pago=monto_pago,
            monto_asignado_documento=monto_doc,
            tasa_original_raw=item.get("tasa_original"),
            tasa_liquidacion_raw=item.get("tasa_liquidacion"),
        )

        nuevo_saldo_doc = saldo_doc_actual - monto_doc
        saldos_doc_restantes[key] = nuevo_saldo_doc

        desc_linea = (
            str(item.get("descripcion") or descripcion or "").strip()
            or f"Conciliación pago {pago_locked.referencia or pago_locked.id_pago}"
        )
        ref_ext = str(item.get("referencia_externa") or "").strip()[:100]

        abono_cxc: AbonoCxC | None = None
        abono_cxp: AbonoCxP | None = None

        if tipo_doc == "CUENTA_POR_COBRAR":
            monto_cxc_2d = monto_doc.quantize(_DOS_DECIMALES, rounding=ROUND_HALF_UP)
            abono_cxc = AbonoCxC.objects.create(
                cuenta_por_cobrar=doc_locked,
                monto=monto_cxc_2d,
                usuario=usuario,
                descripcion=desc_linea,
                referencia_externa=ref_ext or None,
            )
            doc_locked.estado = "pagada" if nuevo_saldo_doc == Decimal("0") else "parcial"
            doc_locked.save(update_fields=["estado"])
        elif tipo_doc == "CUENTA_POR_PAGAR":
            abono_cxp = AbonoCxP.objects.create(
                cuenta_por_pagar=doc_locked,
                monto=monto_doc,
                usuario=usuario,
                descripcion=desc_linea,
                referencia_externa=ref_ext or None,
            )
            doc_locked.monto_pendiente = (Decimal(str(doc_locked.monto_pendiente)) - monto_doc).quantize(
                _CUATRO_DECIMALES, rounding=ROUND_HALF_UP
            )
            doc_locked.estado = "PAGADA" if doc_locked.monto_pendiente == Decimal("0") else "PARCIAL"
            doc_locked.save(update_fields=["monto_pendiente", "estado"])
        elif tipo_doc == "FACTURA_VENTA":
            if nuevo_saldo_doc == Decimal("0"):
                doc_locked.estado = "PAGADA"
                doc_locked.save(update_fields=["estado"])

        asig_kwargs: dict[str, Any] = {
            "id_empresa": empresa,
            "id_contacto": contacto_pago,
            "id_pago": pago_locked,
            "tipo_documento": tipo_doc,
            "id_abono_cxc": abono_cxc,
            "id_abono_cxp": abono_cxp,
            "monto_asignado_pago": monto_pago.quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP),
            "monto_asignado_documento": monto_doc.quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP),
            "id_moneda_documento": moneda_doc,
            "tasa_aplicada": tasa_aplicada,
            "diferencia_cambiaria": diferencia,
            "tipo_diferencia": tipo_diferencia,
            "estado": "ACTIVA",
            "id_usuario_registro": usuario,
            "referencia_externa": ref_ext,
        }
        if tipo_doc == "CUENTA_POR_COBRAR":
            asig_kwargs["id_cxc"] = doc_locked
        elif tipo_doc == "CUENTA_POR_PAGAR":
            asig_kwargs["id_cxp"] = doc_locked
        elif tipo_doc == "FACTURA_VENTA":
            asig_kwargs["id_factura_venta"] = doc_locked
        elif tipo_doc == "FACTURA_COMPRA":
            asig_kwargs["id_factura_compra"] = doc_locked

        asignacion = AsignacionPago.objects.create(**asig_kwargs)

        if generar_asiento:
            try:
                monto_asiento = _resolver_monto_asiento_moneda_base(
                    empresa=empresa,
                    tipo_asiento=tipo_asiento,
                    pago=pago_locked,
                    moneda_doc=moneda_doc,
                    monto_pago=asignacion.monto_asignado_pago,
                    monto_doc=asignacion.monto_asignado_documento,
                    fecha_ref=fecha_ref_pago,
                )
                asiento = None
                if monto_asiento is not None:
                    asiento, _err = generar_asiento_o_fallar(
                        tipo_asiento,
                        asignacion,
                        empresa,
                        monto=monto_asiento,
                        usuario=usuario,
                    )
                diferencia_asiento = Decimal(str(asignacion.diferencia_cambiaria)).quantize(
                    _DOS_DECIMALES, rounding=ROUND_HALF_UP
                )
                if diferencia_asiento > Decimal("0.00") and tipo_diferencia in ("GANANCIA", "PERDIDA"):
                    tipo_dif_asiento = "GANANCIA_CAMBIARIA" if tipo_diferencia == "GANANCIA" else "PERDIDA_CAMBIARIA"
                    generar_asiento_o_fallar(
                        tipo_dif_asiento,
                        asignacion,
                        empresa,
                        monto=diferencia_asiento,
                        usuario=usuario,
                    )
            except AsientoError as exc:
                logger.exception(
                    "aplicar_pago_a_documentos: asiento obligatorio falló | empresa=%s | pago=%s",
                    empresa_id,
                    pago_locked.pk,
                )
                raise ConciliacionContableError(str(exc)) from exc

            if asiento is not None:
                asignacion.id_asiento = asiento
                asignacion.save(update_fields=["id_asiento", "fecha_actualizacion"])

        creadas.append(asignacion)

    return creadas


# ── Reversión controlada con contra-asiento (R-PROD-4) ────────────────────────


def _numero_contra_asiento(asiento_original: "AsientoContable") -> str:
    fecha = timezone.localdate().strftime("%Y%m%d")
    sufijo = uuid.uuid4().hex[:8].upper()
    return f"REV-{fecha}-{sufijo}-{asiento_original.numero_asiento[:40]}"[:100]


@transaction.atomic
def revertir_asignacion_pago(
    asignacion: "AsignacionPago",
    *,
    usuario: Any = None,
    motivo: str = "",
) -> "AsignacionPago":
    """Revierte una ``AsignacionPago`` activa, restaura saldos/estados y emite contra-asiento."""
    from apps.contabilidad.models import AsientoContable, DetalleAsiento
    from apps.cuentas_por_cobrar.models import AbonoCxC
    from apps.cuentas_por_pagar.models import AbonoCxP
    from apps.finanzas.models import AsignacionPago, Pago

    if _es_instancia_no_guardada(asignacion):
        raise ConciliacionPagoError("Debe indicar una AsignacionPago válida.")

    # Lock en orden consistente con aplicar_pago_a_documentos (Pago -> target -> AsignacionPago)
    # para eliminar cualquier posibilidad de deadlock entre operaciones concurrentes.
    try:
        asig_ref = AsignacionPago.objects.only(
            "id_asignacion",
            "id_pago_id",
            "tipo_documento",
            "id_cxc_id",
            "id_cxp_id",
            "id_factura_venta_id",
            "id_factura_compra_id",
        ).get(pk=asignacion.pk)
    except AsignacionPago.DoesNotExist as exc:
        raise ConciliacionTenantError("La asignación de pago no existe.") from exc

    Pago.objects.select_for_update().get(pk=asig_ref.id_pago_id)

    target_pk: int | UUID
    if asig_ref.tipo_documento == "CUENTA_POR_COBRAR" and asig_ref.id_cxc_id is not None:
        target_pk = asig_ref.id_cxc_id
    elif asig_ref.tipo_documento == "CUENTA_POR_PAGAR" and asig_ref.id_cxp_id is not None:
        target_pk = asig_ref.id_cxp_id
    elif asig_ref.tipo_documento == "FACTURA_VENTA" and asig_ref.id_factura_venta_id is not None:
        target_pk = asig_ref.id_factura_venta_id
    elif asig_ref.tipo_documento == "FACTURA_COMPRA" and asig_ref.id_factura_compra_id is not None:
        target_pk = asig_ref.id_factura_compra_id
    else:
        raise ConciliacionPagoError("La asignación no tiene un documento destino válido.")

    target_locked = _lock_target_documento(asig_ref.tipo_documento, target_pk)
    asig_locked = AsignacionPago.objects.select_for_update().get(pk=asignacion.pk)

    if asig_locked.estado == "REVERTIDA" or not asig_locked.activo:
        raise ConciliacionPagoError("La asignación ya fue revertida.")

    empresa_id = _extraer_empresa_id(asig_locked)
    hoy = timezone.localdate()

    # 1. Contra-asiento contable (R-PROD-4).
    asiento_ids: set[UUID] = set()
    if asig_locked.id_asiento_id is not None:
        asiento_ids.add(asig_locked.id_asiento_id)

    asientos_origen = list(
        AsientoContable.objects.select_for_update()
        .filter(id_empresa_id=empresa_id)
        .filter(
            Q(pk__in=asiento_ids)
            | Q(id_documento_origen=asig_locked.id_asignacion, nombre_modelo_origen="AsignacionPago")
        )
        .order_by("fecha_creacion", "pk")
    )

    contra_principal: AsientoContable | None = None
    for asiento_orig in asientos_origen:
        if asiento_orig.estado_asiento == "ANULADO":
            continue
        detalles = list(DetalleAsiento.objects.filter(id_asiento=asiento_orig).order_by("fecha_creacion", "pk"))
        if not detalles:
            raise ConciliacionContableError(
                f"El asiento {asiento_orig.numero_asiento} no tiene detalles para revertir."
            )
        total_orig_debe = sum((Decimal(str(d.debe)) for d in detalles), Decimal("0.00"))
        total_orig_haber = sum((Decimal(str(d.haber)) for d in detalles), Decimal("0.00"))
        if total_orig_debe != total_orig_haber:
            raise ConciliacionContableError(
                f"El asiento {asiento_orig.numero_asiento} está descuadrado ({total_orig_debe} != {total_orig_haber})."
            )

        if asiento_orig.estado_asiento == "BORRADOR":
            asiento_orig.estado_asiento = "ANULADO"
            asiento_orig.save(update_fields=["estado_asiento"])
            continue

        if asiento_orig.estado_asiento == "APROBADO":
            desc_contra = f"Contra-asiento reversión {asiento_orig.numero_asiento}"
            if motivo.strip():
                desc_contra = f"{desc_contra} — {motivo.strip()}"
            contra = AsientoContable.objects.create(
                id_empresa_id=empresa_id,
                fecha_asiento=hoy,
                numero_asiento=_numero_contra_asiento(asiento_orig),
                descripcion=desc_contra,
                id_documento_origen=asig_locked.id_asignacion,
                nombre_modelo_origen="AsignacionPago",
                estado_asiento="APROBADO",
                id_usuario_registro=usuario,
            )
            total_rev_debe = Decimal("0.00")
            total_rev_haber = Decimal("0.00")
            for det in detalles:
                rev_debe = Decimal(str(det.haber))
                rev_haber = Decimal(str(det.debe))
                DetalleAsiento.objects.create(
                    id_asiento=contra,
                    id_cuenta_contable=det.id_cuenta_contable,
                    debe=rev_debe,
                    haber=rev_haber,
                    descripcion_detalle=f"Reversión: {det.descripcion_detalle or asiento_orig.descripcion}",
                )
                total_rev_debe += rev_debe
                total_rev_haber += rev_haber
            if total_rev_debe != total_rev_haber:
                raise ConciliacionContableError("El contra-asiento de reversión quedó descuadrado.")
            if contra_principal is None or asiento_orig.pk == asig_locked.id_asiento_id:
                contra_principal = contra

    # 2. Marcar asignación revertida antes de recalcular saldos en FacturaFiscal/FacturaCompra.
    abono_cxc_id = asig_locked.id_abono_cxc_id
    abono_cxp_id = asig_locked.id_abono_cxp_id

    asig_locked.estado = "REVERTIDA"
    asig_locked.activo = False
    asig_locked.id_abono_cxc = None
    asig_locked.id_abono_cxp = None
    asig_locked.id_asiento_reversion = contra_principal
    asig_locked.fecha_reversion = timezone.now()
    asig_locked.motivo_reversion = (motivo or "")[:255]
    asig_locked.save(
        update_fields=[
            "estado",
            "activo",
            "id_abono_cxc",
            "id_abono_cxp",
            "id_asiento_reversion",
            "fecha_reversion",
            "motivo_reversion",
            "fecha_actualizacion",
        ]
    )

    # 3. Restaurar documento destino y eliminar abono vinculado si aplica.
    if asig_locked.tipo_documento == "CUENTA_POR_COBRAR":
        if abono_cxc_id is not None:
            AbonoCxC.objects.filter(pk=abono_cxc_id).delete()
        total_abonado: Decimal = target_locked.abonos.aggregate(
            t=Coalesce(
                Sum("monto"),
                Decimal("0.00"),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )["t"]
        saldo_cxc = max(
            Decimal("0.00"),
            (Decimal(str(target_locked.monto)) - Decimal(str(total_abonado))).quantize(
                _DOS_DECIMALES, rounding=ROUND_HALF_UP
            ),
        )
        if saldo_cxc == Decimal("0"):
            target_locked.estado = "pagada"
        elif saldo_cxc < Decimal(str(target_locked.monto)):
            target_locked.estado = "parcial"
        else:
            target_locked.estado = "vencida" if target_locked.fecha_vencimiento < hoy else "pendiente"
        target_locked.save(update_fields=["estado"])

    elif asig_locked.tipo_documento == "CUENTA_POR_PAGAR":
        if abono_cxp_id is not None:
            AbonoCxP.objects.filter(pk=abono_cxp_id).delete()
        nuevo_pendiente = (
            Decimal(str(target_locked.monto_pendiente)) + Decimal(str(asig_locked.monto_asignado_documento))
        ).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)
        target_locked.monto_pendiente = min(
            Decimal(str(target_locked.monto_total)).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP),
            nuevo_pendiente,
        )
        if target_locked.monto_pendiente == Decimal("0"):
            target_locked.estado = "PAGADA"
        elif Decimal("0") < target_locked.monto_pendiente < Decimal(str(target_locked.monto_total)):
            target_locked.estado = "PARCIAL"
        else:
            target_locked.estado = "VENCIDA" if target_locked.fecha_vencimiento < hoy else "PENDIENTE"
        target_locked.save(update_fields=["monto_pendiente", "estado"])

    elif asig_locked.tipo_documento == "FACTURA_VENTA":
        if target_locked.estado == "PAGADA":
            asignado_fv = _total_asignado_documento(empresa_id, "FACTURA_VENTA", "id_factura_venta", target_locked)
            saldo_fv = max(
                _CERO,
                (Decimal(str(target_locked.monto_total)) - asignado_fv).quantize(
                    _CUATRO_DECIMALES, rounding=ROUND_HALF_UP
                ),
            )
            if saldo_fv > Decimal("0"):
                target_locked.estado = (
                    "VENCIDA"
                    if (target_locked.fecha_vencimiento is not None and target_locked.fecha_vencimiento < hoy)
                    else "EMITIDA"
                )
                target_locked.save(update_fields=["estado"])

    return asig_locked
