"""Herramientas MCP de Compras — Source-to-PO (ADR-003).

Herramientas expuestas (scope ``compras:write``):
  - ``compras_crear_requisicion``
  - ``compras_adjudicar_oferta``
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import logging
from typing import Any
import uuid

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("omni.mcp.compras")

_PRIORIDADES_VALIDAS = frozenset({"BAJA", "MEDIA", "ALTA", "URGENTE"})


@contextmanager
def _ctx(capability_token: str, scope: str, *, empresa_id: str | None = None) -> Iterator[dict[str, Any]]:
    from apps.core.mcp_server import mcp_tenant_context  # noqa: PLC0415

    with mcp_tenant_context(capability_token, scope, empresa_id=empresa_id) as context:
        yield context


def _parse_uuid_mcp(raw: str, campo: str) -> uuid.UUID:
    limpio = str(raw or "").strip()
    if not limpio or "\x00" in limpio:
        raise ValueError(f"El parámetro '{campo}' es inválido.")
    try:
        return uuid.UUID(limpio)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"El parámetro '{campo}' no es un UUID válido.") from exc


def _parse_decimal_mcp(valor: Any, campo: str) -> Decimal:
    if valor is None or isinstance(valor, bool):
        raise ValueError(f"El campo '{campo}' debe ser numérico.")
    try:
        dec = valor if isinstance(valor, Decimal) else Decimal(str(valor).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Valor numérico inválido para '{campo}': {valor!r}.") from exc
    if not dec.is_finite():
        raise ValueError(f"El valor de '{campo}' debe ser finito.")
    return dec


def compras_crear_requisicion(
    capability_token: str,
    empresa_id: str,
    numero_requisicion: str,
    justificacion: str,
    items: list[dict[str, Any]],
    fecha_necesidad: str = "",
    prioridad: str = "MEDIA",
    id_departamento: str = "",
    id_solicitante: str = "",
    enviar_aprobacion: bool = False,
) -> dict[str, Any]:
    """Crea una RequisicionCompra con sus líneas y opcionalmente la envía a aprobación.

    Scope requerido: ``compras:write``
    """
    from apps.compras.models import DetalleRequisicionCompra, RequisicionCompra  # noqa: PLC0415
    from apps.compras.services import CompraError  # noqa: PLC0415
    from apps.compras.services_procurement import enviar_requisicion_aprobacion  # noqa: PLC0415
    from apps.core.models import Departamento, Empresa, Usuarios  # noqa: PLC0415
    from apps.inventario.models import Producto  # noqa: PLC0415

    with _ctx(capability_token, "compras:write", empresa_id=empresa_id) as ctx:
        try:
            emp_uuid = _parse_uuid_mcp(empresa_id, "empresa_id")
            empresa = Empresa.objects.filter(pk=emp_uuid, activo=True).first()
            if empresa is None:
                raise ValueError("Empresa no encontrada o inactiva.")

            num_limpio = str(numero_requisicion or "").strip()
            just_limpia = str(justificacion or "").strip()
            if not num_limpio or not just_limpia:
                raise ValueError("numero_requisicion y justificacion son requeridos.")
            if RequisicionCompra.objects.filter(id_empresa=empresa, numero_requisicion=num_limpio).exists():
                raise ValueError(f"Ya existe la requisición '{num_limpio}'.")

            prio = str(prioridad or "MEDIA").strip().upper()
            if prio not in _PRIORIDADES_VALIDAS:
                raise ValueError(f"Prioridad inválida: {prio!r}.")

            hoy = timezone.localdate()
            if fecha_necesidad and str(fecha_necesidad).strip():
                try:
                    f_nec = date.fromisoformat(str(fecha_necesidad).strip())
                except ValueError as exc:
                    raise ValueError("fecha_necesidad debe tener formato YYYY-MM-DD.") from exc
            else:
                f_nec = hoy + timedelta(days=7)

            departamento = None
            if id_departamento and str(id_departamento).strip():
                dep_uuid = _parse_uuid_mcp(id_departamento, "id_departamento")
                departamento = Departamento.objects.filter(pk=dep_uuid, id_empresa=empresa, activo=True).first()
                if departamento is None:
                    raise ValueError("Departamento no encontrado en la empresa.")

            if id_solicitante and str(id_solicitante).strip():
                sol_uuid = _parse_uuid_mcp(id_solicitante, "id_solicitante")
                solicitante = Usuarios.objects.filter(pk=sol_uuid, empresas=empresa, is_active=True).first()
            else:
                solicitante = Usuarios.objects.filter(empresas=empresa, is_active=True).order_by("pk").first()
            if solicitante is None:
                raise ValueError("No se encontró un usuario solicitante activo en la empresa.")

            if not isinstance(items, list) or not items:
                raise ValueError("Debe especificar al menos un ítem en 'items'.")

            lineas_validadas: list[tuple[Producto, Decimal, Decimal | None]] = []
            monto_estimado = Decimal("0.0000")
            for idx, it in enumerate(items, start=1):
                if not isinstance(it, dict):
                    raise ValueError(f"Ítem #{idx} inválido.")
                prod_uuid = _parse_uuid_mcp(str(it.get("id_producto", "")), f"items[{idx}].id_producto")
                producto = Producto.objects.filter(pk=prod_uuid, id_empresa=empresa, activo=True).first()
                if producto is None:
                    raise ValueError(f"Producto {prod_uuid} no encontrado o inactivo en la empresa.")
                cantidad = _parse_decimal_mcp(it.get("cantidad"), f"items[{idx}].cantidad")
                if cantidad <= 0:
                    raise ValueError(f"La cantidad del ítem #{idx} debe ser mayor que cero.")
                precio_raw = it.get("precio_estimado")
                precio_est: Decimal | None = None
                if precio_raw not in (None, ""):
                    precio_est = _parse_decimal_mcp(precio_raw, f"items[{idx}].precio_estimado")
                    if precio_est < 0:
                        raise ValueError(f"El precio estimado del ítem #{idx} no puede ser negativo.")
                    monto_estimado += cantidad * precio_est
                lineas_validadas.append((producto, cantidad, precio_est))

            with transaction.atomic():
                req = RequisicionCompra.objects.create(
                    id_empresa=empresa,
                    id_solicitante=solicitante,
                    id_departamento=departamento,
                    numero_requisicion=num_limpio,
                    fecha_requisicion=hoy,
                    estado="BORRADOR",
                    prioridad=prio,
                    fecha_necesidad=f_nec,
                    justificacion=just_limpia,
                )
                for producto, cantidad, precio_est in lineas_validadas:
                    DetalleRequisicionCompra.objects.create(
                        id_requisicion=req,
                        id_producto=producto,
                        cantidad_solicitada=cantidad,
                        precio_estimado=precio_est,
                    )
                if enviar_aprobacion:
                    req = enviar_requisicion_aprobacion(req, solicitante)
        except (ValueError, CompraError) as exc:
            return {"error": str(exc)}

        logger.info(
            "compras_crear_requisicion | actor=%s | tenant=%s | req=%s | estado=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            req.pk,
            req.estado,
        )
        return {
            "id_requisicion": str(req.pk),
            "numero_requisicion": req.numero_requisicion,
            "estado": req.estado,
            "prioridad": req.prioridad,
            "lineas": len(lineas_validadas),
            "monto_estimado": str(monto_estimado.quantize(Decimal("0.0001"))),
        }


def compras_adjudicar_oferta(
    capability_token: str,
    empresa_id: str,
    oferta_id: str,
    almacen_destino_id: str,
    adjudicacion_parcial: list[dict[str, Any]] | None = None,
    rechazar_competidoras: bool = True,
    usuario_id: str = "",
) -> dict[str, Any]:
    """Adjudica una OfertaProveedor (total o parcial) generando una OrdenCompra en BORRADOR.

    Scope requerido: ``compras:write``
    """
    from apps.almacenes.models import Almacen  # noqa: PLC0415
    from apps.compras.models import OfertaProveedor  # noqa: PLC0415
    from apps.compras.services import CompraError  # noqa: PLC0415
    from apps.compras.services_procurement import adjudicar_oferta_a_orden_compra  # noqa: PLC0415
    from apps.core.models import Usuarios  # noqa: PLC0415

    with _ctx(capability_token, "compras:write", empresa_id=empresa_id) as ctx:
        try:
            emp_uuid = _parse_uuid_mcp(empresa_id, "empresa_id")
            ofe_uuid = _parse_uuid_mcp(oferta_id, "oferta_id")
            alm_uuid = _parse_uuid_mcp(almacen_destino_id, "almacen_destino_id")

            oferta = OfertaProveedor.objects.filter(
                pk=ofe_uuid,
                id_solicitud_cotizacion__id_empresa_id=emp_uuid,
            ).first()
            if oferta is None:
                raise ValueError("Oferta no encontrada en la empresa.")

            almacen = Almacen.objects.filter(pk=alm_uuid, id_empresa_id=emp_uuid, activo=True).first()
            if almacen is None:
                raise ValueError("Almacén destino no encontrado o inactivo en la empresa.")

            usuario = None
            if usuario_id and str(usuario_id).strip():
                usr_uuid = _parse_uuid_mcp(usuario_id, "usuario_id")
                usuario = Usuarios.objects.filter(pk=usr_uuid, empresas__id_empresa=emp_uuid, is_active=True).first()
                if usuario is None:
                    raise ValueError("Usuario no encontrado o inactivo en la empresa.")

            parcial_norm = None
            if adjudicacion_parcial is not None:
                if not isinstance(adjudicacion_parcial, list):
                    raise ValueError("adjudicacion_parcial debe ser una lista.")
                parcial_norm = []
                for idx, it in enumerate(adjudicacion_parcial, start=1):
                    if not isinstance(it, dict):
                        raise ValueError(f"Ítem parcial #{idx} inválido.")
                    prod_uuid = _parse_uuid_mcp(
                        str(it.get("id_producto", "")),
                        f"adjudicacion_parcial[{idx}].id_producto",
                    )
                    cant = _parse_decimal_mcp(it.get("cantidad"), f"adjudicacion_parcial[{idx}].cantidad")
                    parcial_norm.append({"id_producto": str(prod_uuid), "cantidad": cant})

            res = adjudicar_oferta_a_orden_compra(
                oferta,
                almacen,
                usuario,
                adjudicacion_parcial=parcial_norm,
                rechazar_competidoras=bool(rechazar_competidoras),
            )
        except (ValueError, CompraError) as exc:
            return {"error": str(exc)}

        oc = res["orden_compra"]
        logger.info(
            "compras_adjudicar_oferta | actor=%s | tenant=%s | oc=%s | oferta=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            oc.pk,
            oferta.pk,
        )
        return {
            "id_orden_compra": str(oc.pk),
            "numero_orden": oc.numero_orden,
            "estado_orden": oc.estado,
            "monto_total": str(res["monto_total"]),
            "oferta_id": str(res["oferta"].pk),
            "oferta_estado": res["oferta"].estado,
            "rfq_id": str(res["rfq"].pk),
            "rfq_estado": res["rfq"].estado,
            "lineas": res["lineas"],
        }


MCP_TOOLS: list[dict[str, Any]] = [
    {
        "fn": compras_crear_requisicion,
        "name": "compras_crear_requisicion",
        "scope": "compras:write",
    },
    {
        "fn": compras_adjudicar_oferta,
        "name": "compras_adjudicar_oferta",
        "scope": "compras:write",
    },
]
