"""
API REST idempotente de conciliación N:M Pagos ↔ Facturas/Obligaciones (Ola A3).

Endpoints:
  GET/POST /api/finanzas/asignaciones-pago/
  GET      /api/finanzas/asignaciones-pago/{id}/
  POST     /api/finanzas/asignaciones-pago/{id}/revertir/
  GET      /api/finanzas/contactos/{id_contacto}/estado-conciliacion/
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db.models import DecimalField, Q, QuerySet, Sum
from django.db.models.functions import Coalesce
from django.utils.decorators import method_decorator
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView

from apps.core.exceptions import domain_error_response
from apps.core.idempotency import IdempotentCreateMixin, idempotent
from apps.core.throttling import EscrituraRateThrottle
from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import AsignacionPago, Pago
from .serializers_conciliacion_pagos import (
    AsignacionPagoSerializer,
    ConciliarDocumentosResponseSerializer,
    CrearAsignacionPagoInputSerializer,
    EstadoConciliacionContactoResponseSerializer,
    RevertirAsignacionInputSerializer,
)
from .services_conciliacion_pagos import (
    TIPOS_DOCUMENTO_EGRESO,
    TIPOS_DOCUMENTO_INGRESO,
    TIPOS_DOCUMENTO_VALIDOS,
    ConciliacionContableError,
    ConciliacionPagoError,
    ConciliacionTenantError,
    aplicar_pago_a_documentos,
    revertir_asignacion_pago,
    saldo_a_favor_contacto,
    saldo_disponible_pago,
)

_DOS_DECIMALES = Decimal("0.01")
_CUATRO_DECIMALES = Decimal("0.0001")
_CERO = Decimal("0.0000")


def _responder_error_conciliacion(exc: ConciliacionPagoError) -> Response:
    """Traduce excepciones de dominio de conciliación a HTTP 404/422/400."""
    if isinstance(exc, ConciliacionTenantError):
        return domain_error_response(exc, status_code=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, ConciliacionContableError):
        return domain_error_response(exc, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
    return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)


def _limpiar_param_texto(raw: str | None) -> str:
    if raw is None:
        return ""
    return raw.replace("\x00", "").strip()


def _parse_uuid_filtro(raw: str, campo: str) -> uuid.UUID:
    limpio = _limpiar_param_texto(raw)
    try:
        return uuid.UUID(limpio)
    except (ValueError, TypeError) as exc:
        raise ValidationError({campo: f"'{limpio}' no es un UUID válido."}) from exc


@method_decorator(
    name="list",
    decorator=swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                "pago",
                openapi.IN_QUERY,
                description="Filtrar por UUID de Pago.",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_UUID,
            ),
            openapi.Parameter(
                "contacto",
                openapi.IN_QUERY,
                description="Filtrar por UUID de core.Contacto.",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_UUID,
            ),
            openapi.Parameter(
                "tipo_documento",
                openapi.IN_QUERY,
                description="Filtrar por tipo de documento destino.",
                type=openapi.TYPE_STRING,
                enum=sorted(TIPOS_DOCUMENTO_VALIDOS),
            ),
            openapi.Parameter(
                "id_documento",
                openapi.IN_QUERY,
                description="Filtrar por identificador del documento destino.",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "estado",
                openapi.IN_QUERY,
                description="Filtrar por estado (ACTIVA | REVERTIDA).",
                type=openapi.TYPE_STRING,
                enum=["ACTIVA", "REVERTIDA"],
            ),
        ]
    ),
)
class AsignacionPagoViewSet(IdempotentCreateMixin, BaseModelViewSet):
    """Gestión idempotente de imputaciones N:M ``Pago ↔ Documento``."""

    queryset = AsignacionPago.objects.all()
    serializer_class = AsignacionPagoSerializer
    http_method_names = ["get", "post", "head", "options"]
    idempotency_scope = "finanzas:asignacion-pago"
    throttle_classes = [*BaseModelViewSet.throttle_classes, EscrituraRateThrottle]
    search_fields = [
        "referencia_externa",
        "tipo_documento",
        "id_documento",
        "motivo_reversion",
        "id_contacto__nombre",
        "id_contacto__rif",
    ]
    ordering_fields = [
        "fecha_aplicacion",
        "fecha_creacion",
        "monto_asignado_pago",
        "monto_asignado_documento",
        "estado",
    ]

    def get_serializer_class(self) -> type[BaseSerializer[Any]]:
        if self.action == "create":
            return CrearAsignacionPagoInputSerializer
        if self.action == "revertir":
            return RevertirAsignacionInputSerializer
        return AsignacionPagoSerializer

    def filter_queryset(self, queryset: QuerySet[AsignacionPago]) -> QuerySet[AsignacionPago]:
        search_param = self.request.query_params.get("search")
        if search_param and "\x00" in search_param:
            raise ValidationError({"search": "Parámetro de búsqueda inválido."})
        return super().filter_queryset(queryset)

    def get_queryset(self) -> QuerySet[AsignacionPago]:
        empresas = get_empresas_visible(self.request.user)
        qs = (
            AsignacionPago.objects.filter(id_empresa__in=empresas)
            .select_related("id_empresa", "id_contacto", "id_pago", "id_moneda_documento")
            .order_by("-fecha_aplicacion", "-fecha_creacion")
        )

        params = self.request.query_params
        pago_raw = params.get("pago")
        if pago_raw:
            qs = qs.filter(id_pago_id=_parse_uuid_filtro(pago_raw, "pago"))

        contacto_raw = params.get("contacto")
        if contacto_raw:
            qs = qs.filter(id_contacto_id=_parse_uuid_filtro(contacto_raw, "contacto"))

        tipo_doc = _limpiar_param_texto(params.get("tipo_documento"))
        if tipo_doc:
            if tipo_doc not in TIPOS_DOCUMENTO_VALIDOS:
                raise ValidationError({"tipo_documento": f"Tipo de documento inválido: {tipo_doc!r}."})
            qs = qs.filter(tipo_documento=tipo_doc)

        id_doc = _limpiar_param_texto(params.get("id_documento"))
        if id_doc:
            qs = qs.filter(id_documento=id_doc)

        estado = _limpiar_param_texto(params.get("estado"))
        if estado:
            if estado not in ("ACTIVA", "REVERTIDA"):
                raise ValidationError({"estado": f"Estado inválido: {estado!r}."})
            qs = qs.filter(estado=estado)

        return qs

    @swagger_auto_schema(
        request_body=CrearAsignacionPagoInputSerializer,
        responses={201: ConciliarDocumentosResponseSerializer},
    )
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        scope = self.idempotency_scope or "finanzas:asignacion-pago"

        @idempotent(scope)
        def _create(view: AsignacionPagoViewSet, req: Request, *a: Any, **kw: Any) -> Response:
            input_ser = CrearAsignacionPagoInputSerializer(data=req.data)
            input_ser.is_valid(raise_exception=True)
            datos = input_ser.validated_data

            empresas = get_empresas_visible(req.user)
            pago = (
                Pago.objects.filter(pk=datos["pago"], id_empresa__in=empresas)
                .select_related("id_empresa", "id_contacto", "id_moneda")
                .first()
            )
            if pago is None:
                return Response(
                    {"error": "Pago no encontrado en las empresas accesibles."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            try:
                creadas = aplicar_pago_a_documentos(
                    pago,
                    datos["asignaciones"],
                    usuario=req.user,
                    generar_asiento=bool(datos.get("generar_asiento", True)),
                    descripcion=str(datos.get("descripcion") or ""),
                )
            except ConciliacionPagoError as exc:
                return _responder_error_conciliacion(exc)

            return Response(
                {
                    "pago_id": str(pago.pk),
                    "saldo_disponible": str(saldo_disponible_pago(pago)),
                    "asignaciones": AsignacionPagoSerializer(creadas, many=True).data,
                },
                status=status.HTTP_201_CREATED,
            )

        return _create(self, request, *args, **kwargs)

    @swagger_auto_schema(
        request_body=RevertirAsignacionInputSerializer,
        responses={200: AsignacionPagoSerializer},
    )
    @idempotent("finanzas:asignacion-revertir")
    @action(detail=True, methods=["post"], url_path="revertir")
    def revertir(self, request: Request, pk: str | None = None) -> Response:
        """Revierte una asignación activa, restaura saldos y emite contra-asiento."""
        asignacion = self.get_object()
        input_ser = RevertirAsignacionInputSerializer(data=request.data)
        input_ser.is_valid(raise_exception=True)
        motivo = str(input_ser.validated_data.get("motivo") or "")

        try:
            revertida = revertir_asignacion_pago(
                asignacion,
                usuario=request.user,
                motivo=motivo,
            )
        except ConciliacionPagoError as exc:
            return _responder_error_conciliacion(exc)

        return Response(AsignacionPagoSerializer(revertida).data, status=status.HTTP_200_OK)


def _obligaciones_abiertas_contacto(
    empresa: Any,
    contacto: Any,
    *,
    tipos_buscar: frozenset[str],
    moneda_default_codigo: str,
) -> list[dict[str, Any]]:
    from apps.compras.models import FacturaCompra
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar
    from apps.cuentas_por_pagar.models import CuentaPorPagar
    from apps.integration_hub.models import EntidadSincronizada
    from apps.proveedores.models import Proveedor
    from apps.ventas.models import FacturaFiscal

    empresa_id = empresa.pk
    obligaciones: list[tuple[tuple[date, date, str, str], dict[str, Any]]] = []

    if "CUENTA_POR_COBRAR" in tipos_buscar:
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
            obligaciones.append(
                (
                    (cxc.fecha_vencimiento, cxc.fecha_emision, "CUENTA_POR_COBRAR", str(cxc.pk)),
                    {
                        "tipo_documento": "CUENTA_POR_COBRAR",
                        "id_documento": str(cxc.pk),
                        "numero_documento": cxc.referencia_externa or f"CxC-{cxc.pk}",
                        "fecha_emision": cxc.fecha_emision,
                        "fecha_vencimiento": cxc.fecha_vencimiento,
                        "monto_total": Decimal(str(cxc.monto)).quantize(_DOS_DECIMALES, rounding=ROUND_HALF_UP),
                        "saldo_pendiente": saldo_cxc,
                        "moneda_codigo": moneda_default_codigo,
                        "estado": cxc.estado,
                    },
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
            f_vcto = fv.fecha_vencimiento or fv.fecha_emision
            obligaciones.append(
                (
                    (f_vcto, fv.fecha_emision, "FACTURA_VENTA", str(fv.pk)),
                    {
                        "tipo_documento": "FACTURA_VENTA",
                        "id_documento": str(fv.pk),
                        "numero_documento": fv.numero_factura,
                        "fecha_emision": fv.fecha_emision,
                        "fecha_vencimiento": f_vcto,
                        "monto_total": Decimal(str(fv.monto_total)).quantize(
                            _CUATRO_DECIMALES, rounding=ROUND_HALF_UP
                        ),
                        "saldo_pendiente": saldo_fv,
                        "moneda_codigo": fv.id_moneda.codigo_iso,
                        "estado": fv.estado,
                    },
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
            obligaciones.append(
                (
                    (cxp.fecha_vencimiento, cxp.fecha_emision, "CUENTA_POR_PAGAR", str(cxp.pk)),
                    {
                        "tipo_documento": "CUENTA_POR_PAGAR",
                        "id_documento": str(cxp.pk),
                        "numero_documento": cxp.referencia_externa or f"CxP-{str(cxp.pk)[:8]}",
                        "fecha_emision": cxp.fecha_emision,
                        "fecha_vencimiento": cxp.fecha_vencimiento,
                        "monto_total": Decimal(str(cxp.monto_total)).quantize(
                            _CUATRO_DECIMALES, rounding=ROUND_HALF_UP
                        ),
                        "saldo_pendiente": saldo_cxp,
                        "moneda_codigo": moneda_default_codigo,
                        "estado": cxp.estado,
                    },
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
            total_asig_fc = Decimal(str(fc.total_asig_agg)).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)
            saldo_fc = (Decimal(str(fc.monto_total)) - total_asig_fc).quantize(
                _CUATRO_DECIMALES, rounding=ROUND_HALF_UP
            )
            if saldo_fc <= Decimal("0"):
                continue
            estado_fc = "PENDIENTE" if total_asig_fc <= Decimal("0") else "PARCIAL"
            obligaciones.append(
                (
                    (fc.fecha_emision, fc.fecha_emision, "FACTURA_COMPRA", str(fc.pk)),
                    {
                        "tipo_documento": "FACTURA_COMPRA",
                        "id_documento": str(fc.pk),
                        "numero_documento": fc.numero_factura,
                        "fecha_emision": fc.fecha_emision,
                        "fecha_vencimiento": fc.fecha_emision,
                        "monto_total": Decimal(str(fc.monto_total)).quantize(
                            _CUATRO_DECIMALES, rounding=ROUND_HALF_UP
                        ),
                        "saldo_pendiente": saldo_fc,
                        "moneda_codigo": moneda_default_codigo,
                        "estado": estado_fc,
                    },
                )
            )

    obligaciones.sort(key=lambda par: par[0])
    return [item for _key, item in obligaciones]


class EstadoConciliacionContactoView(APIView):
    """Estado unificado de pagos disponibles, obligaciones abiertas y asignaciones de un contacto."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                "tipo_operacion",
                openapi.IN_QUERY,
                description="Filtra pagos y obligaciones compatibles (INGRESO | EGRESO).",
                type=openapi.TYPE_STRING,
                enum=["INGRESO", "EGRESO"],
            ),
        ],
        responses={200: EstadoConciliacionContactoResponseSerializer},
    )
    def get(self, request: Request, id_contacto: uuid.UUID) -> Response:
        from apps.core.models import Contacto

        empresas = get_empresas_visible(request.user)
        contacto = (
            Contacto.objects.select_related("id_empresa", "id_empresa__id_moneda_base")
            .filter(pk=id_contacto, id_empresa__in=empresas)
            .first()
        )
        if contacto is None:
            return Response({"error": "Contacto no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        tipo_op_raw = _limpiar_param_texto(request.query_params.get("tipo_operacion"))
        tipo_op: str | None
        if tipo_op_raw == "":
            tipo_op = None
        elif tipo_op_raw in ("INGRESO", "EGRESO"):
            tipo_op = tipo_op_raw
        else:
            raise ValidationError({"tipo_operacion": "Debe ser 'INGRESO' o 'EGRESO'."})

        empresa = contacto.id_empresa
        resumen = saldo_a_favor_contacto(empresa, contacto, tipo_operacion=tipo_op)
        pagos_raw = resumen["pagos_con_saldo"]
        pago_ids = [p["pago_id"] for p in pagos_raw]
        tasas_por_pago: dict[str, Decimal] = {}
        if pago_ids:
            for row in Pago.objects.filter(pk__in=pago_ids).values("id_pago", "tasa"):
                tasas_por_pago[str(row["id_pago"])] = Decimal(str(row["tasa"]))

        pagos_disponibles = [
            {
                "id_pago": p["pago_id"],
                "fecha_pago": p["fecha_pago"],
                "tipo_operacion": p["tipo_operacion"],
                "monto": p["monto_original"],
                "saldo_disponible": p["saldo_disponible"],
                "moneda_codigo": p["moneda_codigo"],
                "referencia": p["referencia"],
                "tasa": tasas_por_pago.get(p["pago_id"], Decimal("1.0000")),
            }
            for p in pagos_raw
        ]

        if tipo_op == "INGRESO":
            tipos_buscar = TIPOS_DOCUMENTO_INGRESO
        elif tipo_op == "EGRESO":
            tipos_buscar = TIPOS_DOCUMENTO_EGRESO
        else:
            tipos_buscar = TIPOS_DOCUMENTO_VALIDOS

        moneda_default_codigo = (
            empresa.id_moneda_base.codigo_iso
            if empresa.id_moneda_base_id and empresa.id_moneda_base is not None
            else (pagos_disponibles[0]["moneda_codigo"] if pagos_disponibles else "USD")
        )
        obligaciones_abiertas = _obligaciones_abiertas_contacto(
            empresa,
            contacto,
            tipos_buscar=tipos_buscar,
            moneda_default_codigo=moneda_default_codigo,
        )

        asigs_qs = (
            AsignacionPago.objects.filter(
                id_empresa=empresa,
                id_contacto=contacto,
                estado="ACTIVA",
                activo=True,
            )
            .select_related("id_contacto", "id_pago", "id_moneda_documento")
            .order_by("-fecha_aplicacion", "-fecha_creacion")
        )
        if tipo_op is not None:
            asigs_qs = asigs_qs.filter(id_pago__tipo_operacion=tipo_op)
        asignaciones_activas = list(asigs_qs[:50])

        payload = {
            "contacto": {
                "id_contacto": contacto.pk,
                "nombre": contacto.nombre_completo,
                "rif": contacto.rif or "",
                "es_cliente": contacto.es_cliente,
                "es_proveedor": contacto.es_proveedor,
            },
            "saldo_a_favor": {
                "total_por_moneda": resumen["total_por_moneda"],
                "total_pagos_con_saldo": len(pagos_disponibles),
            },
            "pagos_disponibles": pagos_disponibles,
            "obligaciones_abiertas": obligaciones_abiertas,
            "asignaciones_activas": asignaciones_activas,
        }
        serializer = EstadoConciliacionContactoResponseSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)
