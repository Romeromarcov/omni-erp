"""Vistas API para Nómina Dual VE (Fichas Duales, Préstamos, Dispersión/Arqueo y Simulador LOTTT)."""

from __future__ import annotations

from django.db import transaction
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import domain_error_response
from apps.core.serializer_mixins import TenantFKScopeMixin
from apps.core.throttling import EscrituraRateThrottle
from apps.core.viewsets import ActiveFilterMixin, NulSafeFilterMixin, get_empresas_visible, validar_uuid_param
from apps.rrhh.models import Empleado

from .models import DispersionPagoNomina, FichaSalarialDual, PrestamoEmpleado
from .serializers_dual import (
    DispersionPagoNominaSerializer,
    FichaSalarialDualSerializer,
    PrestamoEmpleadoSerializer,
    SimularLiquidacionInputSerializer,
)
from .services_dual import NominaDualError, calcular_arqueo_efectivo_usd, simular_liquidacion_lottt


def _no_nul(valor: str | None, campo: str) -> str | None:
    if valor is None or valor == "":
        return None
    if "\x00" in str(valor):
        raise ValidationError({campo: "Parámetro inválido."})
    return str(valor).strip()


def resolver_empresa_nomina(user, raw_empresa_id=None):
    empresas = get_empresas_visible(user)
    if raw_empresa_id:
        uid = validar_uuid_param(str(raw_empresa_id), "id_empresa")
        empresa = empresas.filter(pk=uid).first()
        if empresa is None:
            raise ValidationError({"id_empresa": "Empresa no encontrada o sin acceso."})
        return empresa
    empresa = empresas.first()
    if empresa is None:
        raise ValidationError({"id_empresa": "No tiene una empresa activa asignada."})
    return empresa


class FichaSalarialDualViewSet(TenantFKScopeMixin, NulSafeFilterMixin, ActiveFilterMixin, viewsets.ModelViewSet):
    """CRUD multi-tenant de Fichas Salariales Duales (LOTTT formal Bs + Paquete Gerencial USD)."""

    queryset = FichaSalarialDual.objects.all()
    serializer_class = FichaSalarialDualSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["id_empleado__nombre", "id_empleado__apellido", "id_empleado__cedula", "canal_pago_gerencial"]
    ordering_fields = ["fecha_creacion", "paquete_objetivo_mensual", "salario_base_formal_ves"]
    ordering = ["-fecha_creacion"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("id_empleado", "id_empresa", "moneda_paquete")
        qs = qs.filter(id_empresa__in=get_empresas_visible(self.request.user))
        canal = _no_nul(self.request.query_params.get("canal_pago_gerencial"), "canal_pago_gerencial")
        if canal:
            qs = qs.filter(canal_pago_gerencial=canal.upper())
        return qs


class PrestamoEmpleadoViewSet(TenantFKScopeMixin, NulSafeFilterMixin, ActiveFilterMixin, viewsets.ModelViewSet):
    """Gestión de préstamos/adelantos con amortización automática por ámbito."""

    queryset = PrestamoEmpleado.objects.all()
    serializer_class = PrestamoEmpleadoSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["id_empleado__nombre", "id_empleado__apellido", "id_empleado__cedula", "estado"]
    ordering_fields = ["fecha_otorgamiento", "saldo_pendiente", "monto_principal"]
    ordering = ["-fecha_otorgamiento"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("id_empleado", "id_empresa", "moneda")
        qs = qs.filter(id_empresa__in=get_empresas_visible(self.request.user))
        estado = _no_nul(self.request.query_params.get("estado"), "estado")
        if estado:
            qs = qs.filter(estado=estado.upper())
        ambito = _no_nul(self.request.query_params.get("ambito_descuento"), "ambito_descuento")
        if ambito:
            qs = qs.filter(ambito_descuento=ambito.upper())
        return qs

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        """Anula lógicamente un préstamo aún no saldado."""
        with transaction.atomic():
            prestamo = PrestamoEmpleado.objects.select_for_update().get(pk=self.get_object().pk)
            if prestamo.estado != "ACTIVO":
                return domain_error_response(
                    NominaDualError(f"No se puede anular un préstamo en estado {prestamo.estado}."),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            prestamo.estado = "ANULADO"
            prestamo.save(update_fields=["estado", "fecha_actualizacion"])
        return Response(self.get_serializer(prestamo).data)


class DispersionPagoNominaViewSet(NulSafeFilterMixin, ActiveFilterMixin, viewsets.ReadOnlyModelViewSet):
    """Consulta, confirmación y arqueo de efectivo USD ($100..$1) de dispersiones de nómina."""

    queryset = DispersionPagoNomina.objects.all()
    serializer_class = DispersionPagoNominaSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["id_empleado__nombre", "id_empleado__apellido", "id_empleado__cedula", "canal_pago"]
    ordering_fields = ["fecha_creacion", "monto", "canal_pago"]
    ordering = ["-fecha_creacion"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("id_empleado", "id_empresa", "id_proceso_nomina", "moneda")
        qs = qs.filter(id_empresa__in=get_empresas_visible(self.request.user))
        proc_id = _no_nul(self.request.query_params.get("id_proceso_nomina"), "id_proceso_nomina")
        if proc_id:
            qs = qs.filter(id_proceso_nomina_id=validar_uuid_param(proc_id, "id_proceso_nomina"))
        canal = _no_nul(self.request.query_params.get("canal_pago"), "canal_pago")
        if canal:
            qs = qs.filter(canal_pago=canal.upper())
        estado = _no_nul(self.request.query_params.get("estado"), "estado")
        if estado:
            qs = qs.filter(estado=estado.upper())
        return qs

    @action(detail=True, methods=["post"], url_path="marcar-pagado")
    def marcar_pagado(self, request, pk=None):
        """Marca una orden de dispersión PENDIENTE como PAGADO."""
        with transaction.atomic():
            disp = DispersionPagoNomina.objects.select_for_update().get(pk=self.get_object().pk)
            if disp.estado != "PENDIENTE":
                return domain_error_response(
                    NominaDualError(f"La dispersión está en estado {disp.estado}; solo se confirman PENDIENTE."),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            disp.estado = "PAGADO"
            disp.save(update_fields=["estado", "fecha_actualizacion"])
        return Response(self.get_serializer(disp).data)

    @action(detail=False, methods=["get"], url_path="arqueo-efectivo")
    def arqueo_efectivo(self, request):
        """Calcula el arqueo de billetes USD ($100/$50/$20/$10/$5/$1) para dispersiones EFECTIVO_USD."""
        qs = self.get_queryset().filter(canal_pago="EFECTIVO_USD", activo=True).exclude(estado="ANULADO")
        rows = [
            {
                "empleado_id": d.id_empleado_id,
                "empleado_nombre": f"{d.id_empleado.nombre} {d.id_empleado.apellido}",
                "monto": d.monto,
            }
            for d in qs
        ]
        try:
            data = calcular_arqueo_efectivo_usd(rows)
        except NominaDualError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        return Response(data)


class SimuladorLiquidacionLOTTTView(APIView):
    """POST /api/nomina/simulador-liquidacion/ — calcula Art. 142 LOTTT, Art. 92 y préstamos."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [*APIView.throttle_classes, EscrituraRateThrottle]

    def post(self, request):
        inp = SimularLiquidacionInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        vd = inp.validated_data
        empresa = resolver_empresa_nomina(request.user, vd.get("id_empresa"))
        empleado = Empleado.objects.filter(pk=vd["id_empleado"], empresa=empresa).first()
        if empleado is None:
            raise ValidationError({"id_empleado": "Empleado no encontrado en la empresa activa."})
        try:
            res = simular_liquidacion_lottt(
                empleado=empleado,
                salario_mensual_integral=vd["salario_mensual_integral"],
                fecha_egreso=vd["fecha_egreso"],
                dias_vacaciones_pendientes=vd["dias_vacaciones_pendientes"],
                despido_injustificado=vd["despido_injustificado"],
                tasa_interes_prestaciones=vd["tasa_interes_prestaciones"],
                empresa=empresa,
            )
        except NominaDualError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        return Response(res)
