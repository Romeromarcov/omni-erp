from django.db.models import Count, Sum
from apps.core.serializer_mixins import TenantFKScopeMixin
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import get_empresas_visible

from .models import (
    ConceptoNomina,
    DetalleNomina,
    Nomina,
    NominaExtrasalarial,
    PeriodoNomina,
    ProcesoNomina,
    ProcesoNominaExtrasalarial,
)
from .serializers import (
    ConceptoNominaSerializer,
    DetalleNominaSerializer,
    NominaExtrasalarialSerializer,
    NominaSerializer,
    PeriodoNominaSerializer,
    ProcesoNominaExtrasalarialSerializer,
    ProcesoNominaSerializer,
)


def _empresas(request):
    return get_empresas_visible(request.user)


class PeriodoNominaViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = PeriodoNomina.objects.all()
    serializer_class = PeriodoNominaSerializer
    filterset_fields = ["estado", "tipo_periodo", "id_empresa", "activo"]
    search_fields = ["nombre_periodo"]
    ordering_fields = ["fecha_inicio", "fecha_fin", "fecha_pago", "nombre_periodo"]
    ordering = ["-fecha_inicio"]

    def get_queryset(self):
        # R-CODE-1: filtrar por empresas visibles del usuario autenticado
        return PeriodoNomina.objects.filter(id_empresa__in=_empresas(self.request))

    @action(detail=False, methods=["get"])
    def activos(self, request):
        """Obtiene períodos activos de las empresas propias"""
        periodos_activos = self.get_queryset().filter(activo=True)
        serializer = self.get_serializer(periodos_activos, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def abiertos(self, request):
        """Obtiene períodos en estado abierto de las empresas propias"""
        # R-CODE-1: get_queryset() ya aplica filtro de empresa; nunca self.queryset
        periodos_abiertos = self.get_queryset().filter(estado="ABIERTO", activo=True)
        serializer = self.get_serializer(periodos_abiertos, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def cerrar(self, request, pk=None):
        """Cierra un período de nómina"""
        periodo = self.get_object()

        if periodo.estado != "ABIERTO":
            return Response(
                {"error": "Solo se pueden cerrar períodos en estado abierto"}, status=status.HTTP_400_BAD_REQUEST
            )

        periodo.estado = "CERRADO"
        periodo.save()

        serializer = self.get_serializer(periodo)
        return Response(serializer.data)


class ConceptoNominaViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = ConceptoNomina.objects.all()
    serializer_class = ConceptoNominaSerializer
    filterset_fields = ["tipo_concepto", "categoria", "activo", "id_empresa", "es_fijo", "es_porcentaje"]
    search_fields = ["codigo_concepto", "nombre_concepto"]
    ordering_fields = ["codigo_concepto", "nombre_concepto", "fecha_creacion"]
    ordering = ["codigo_concepto"]

    def get_queryset(self):
        # R-CODE-1
        return ConceptoNomina.objects.filter(id_empresa__in=_empresas(self.request))

    @action(detail=False, methods=["get"])
    def por_tipo(self, request):
        """Obtiene conceptos filtrados por tipo de las empresas propias"""
        # R-CODE-1: get_queryset() ya aplica filtro de empresa; nunca self.queryset
        qs = self.get_queryset().filter(activo=True)
        tipo = request.query_params.get("tipo")
        if tipo:
            qs = qs.filter(tipo_concepto=tipo)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def devengados(self, request):
        """Obtiene conceptos de tipo devengado de las empresas propias"""
        # R-CODE-1: get_queryset() ya aplica filtro de empresa
        conceptos = self.get_queryset().filter(tipo_concepto="DEVENGADO", activo=True)
        serializer = self.get_serializer(conceptos, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def deducciones(self, request):
        """Obtiene conceptos de tipo deducción de las empresas propias"""
        # R-CODE-1: get_queryset() ya aplica filtro de empresa
        conceptos = self.get_queryset().filter(tipo_concepto="DEDUCCION", activo=True)
        serializer = self.get_serializer(conceptos, many=True)
        return Response(serializer.data)


class ProcesoNominaViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = ProcesoNomina.objects.all()
    serializer_class = ProcesoNominaSerializer
    filterset_fields = ["estado", "id_empresa", "id_periodo_nomina"]
    search_fields = ["numero_proceso"]
    ordering_fields = ["fecha_proceso", "numero_proceso", "total_neto"]
    ordering = ["-fecha_proceso"]

    def get_queryset(self):
        # R-CODE-1
        return ProcesoNomina.objects.filter(id_empresa__in=_empresas(self.request))

    @action(detail=True, methods=["post"])
    def procesar(self, request, pk=None):
        """Procesa la nómina LOTTT del período (CTF-013, TEST-5).

        Calcula la nómina de cada empleado activo (motor `calculo_lottt` con
        parámetros de `ParametroSistema`), persiste `Nomina` + `DetalleNomina`,
        totaliza el proceso y genera el asiento `NOMINA` — todo atómico
        (R-CODE-11). Body opcional: ``{"empleados": {"<id_empleado>": {
        "dias_trabajados": 30, "horas_extra_diurnas": "4", ...}}}``.

        Re-procesar un proceso COMPLETADO/APROBADO/CANCELADO → 400 (los recibos
        emitidos son inmutables; cancele y cree un proceso nuevo).
        """
        from apps.contabilidad.services import AsientoError

        from .services import NominaProcesoError, procesar_proceso_nomina

        proceso = self.get_object()

        datos_empleados = request.data.get("empleados") if isinstance(request.data, dict) else None
        if datos_empleados is not None and not isinstance(datos_empleados, dict):
            return Response(
                {"error": "'empleados' debe ser un objeto {id_empleado: {datos…}}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            proceso, asiento, advertencia = procesar_proceso_nomina(
                proceso, datos_empleados, usuario=request.user
            )
        except NominaProcesoError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except AsientoError as exc:
            # Contabilidad activa sin mapeo NOMINA (u otro error de asiento):
            # el @transaction.atomic del servicio ya revirtió todo el proceso
            # al propagar la excepción — aquí solo se traduce a 422.
            return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        data = self.get_serializer(proceso).data
        data["asiento_contable"] = str(asiento.id_asiento) if asiento else None
        if advertencia:
            data["advertencia_asiento"] = advertencia
        return Response(data)

    @action(detail=True, methods=["post"])
    def aprobar(self, request, pk=None):
        """Aprueba un proceso de nómina"""
        proceso = self.get_object()

        if proceso.estado != "COMPLETADO":
            return Response(
                {"error": "Solo se pueden aprobar procesos completados"}, status=status.HTTP_400_BAD_REQUEST
            )

        proceso.estado = "APROBADO"
        proceso.save()

        # Actualizar estado de nóminas asociadas
        Nomina.objects.filter(id_proceso_nomina=proceso, estado="CALCULADA").update(estado="APROBADA")

        serializer = self.get_serializer(proceso)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def resumen(self, request, pk=None):
        """Obtiene resumen del proceso de nómina"""
        proceso = self.get_object()
        nominas = proceso.nominas.all()

        resumen = {
            "total_empleados": nominas.count(),
            "total_devengado": nominas.aggregate(Sum("total_devengado"))["total_devengado__sum"] or 0,
            "total_deducciones": nominas.aggregate(Sum("total_deducciones"))["total_deducciones__sum"] or 0,
            "total_neto": nominas.aggregate(Sum("total_neto"))["total_neto__sum"] or 0,
            # BUG-M1: paréntesis obligatorios — sin ellos la precedencia hacía
            # `sum or (0 / n)` y promedio_sueldo devolvía la suma completa.
            "promedio_sueldo": (nominas.aggregate(Sum("sueldo_base"))["sueldo_base__sum"] or 0)
            / max(nominas.count(), 1),
        }

        return Response(resumen)


class NominaViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = Nomina.objects.all()
    serializer_class = NominaSerializer
    filterset_fields = ["estado", "id_proceso_nomina", "id_empleado"]
    search_fields = ["id_empleado__nombre", "id_empleado__apellido"]
    ordering_fields = ["fecha_calculo", "total_neto", "sueldo_base"]
    ordering = ["-fecha_calculo"]

    def get_queryset(self):
        # R-CODE-1: filtrar via FK chain Nomina → ProcesoNomina → empresa
        empresas = _empresas(self.request)
        return Nomina.objects.filter(id_proceso_nomina__id_empresa__in=empresas)

    @action(detail=True, methods=["post"])
    def aprobar(self, request, pk=None):
        """Aprueba una nómina individual"""
        nomina = self.get_object()

        if nomina.estado != "CALCULADA":
            return Response({"error": "Solo se pueden aprobar nóminas calculadas"}, status=status.HTTP_400_BAD_REQUEST)

        nomina.estado = "APROBADA"
        nomina.save()

        serializer = self.get_serializer(nomina)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def marcar_pagada(self, request, pk=None):
        """Marca una nómina como pagada"""
        nomina = self.get_object()

        if nomina.estado != "APROBADA":
            return Response(
                {"error": "Solo se pueden marcar como pagadas nóminas aprobadas"}, status=status.HTTP_400_BAD_REQUEST
            )

        nomina.estado = "PAGADA"
        nomina.save()

        serializer = self.get_serializer(nomina)
        return Response(serializer.data)


class DetalleNominaViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = DetalleNomina.objects.all()
    serializer_class = DetalleNominaSerializer
    filterset_fields = ["id_nomina", "id_concepto_nomina"]
    ordering_fields = ["valor_total"]
    ordering = ["id_concepto_nomina__codigo_concepto"]

    def get_queryset(self):
        # R-CODE-1: filtrar via FK chain DetalleNomina → Nomina → ProcesoNomina → empresa
        empresas = _empresas(self.request)
        return DetalleNomina.objects.filter(
            id_nomina__id_proceso_nomina__id_empresa__in=empresas
        )


class ProcesoNominaExtrasalarialViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = ProcesoNominaExtrasalarial.objects.all()
    serializer_class = ProcesoNominaExtrasalarialSerializer
    filterset_fields = ["estado", "tipo_proceso", "id_empresa"]
    search_fields = ["numero_proceso"]
    ordering_fields = ["fecha_proceso", "total_monto"]
    ordering = ["-fecha_proceso"]

    def get_queryset(self):
        # R-CODE-1
        return ProcesoNominaExtrasalarial.objects.filter(id_empresa__in=_empresas(self.request))

    @action(detail=True, methods=["post"])
    def procesar(self, request, pk=None):
        """Procesa nómina extrasalarial"""
        proceso = self.get_object()

        if proceso.estado != "EN_PROCESO":
            return Response(
                {"error": "El proceso ya ha sido completado o cancelado"}, status=status.HTTP_400_BAD_REQUEST
            )

        proceso.estado = "COMPLETADO"
        proceso.save()

        serializer = self.get_serializer(proceso)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def aprobar(self, request, pk=None):
        """Aprueba proceso extrasalarial"""
        proceso = self.get_object()

        if proceso.estado != "COMPLETADO":
            return Response(
                {"error": "Solo se pueden aprobar procesos completados"}, status=status.HTTP_400_BAD_REQUEST
            )

        proceso.estado = "APROBADO"
        proceso.save()

        # Actualizar nóminas extrasalariales asociadas
        NominaExtrasalarial.objects.filter(id_proceso_extrasalarial=proceso, estado="CALCULADA").update(
            estado="APROBADA"
        )

        serializer = self.get_serializer(proceso)
        return Response(serializer.data)


class NominaExtrasalarialViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = NominaExtrasalarial.objects.all()
    serializer_class = NominaExtrasalarialSerializer
    filterset_fields = ["estado", "id_proceso_extrasalarial", "id_empleado"]
    search_fields = ["id_empleado__nombre", "id_empleado__apellido"]
    ordering_fields = ["fecha_calculo", "monto_neto"]
    ordering = ["-fecha_calculo"]

    def get_queryset(self):
        # R-CODE-1: filtrar via FK chain → ProcesoNominaExtrasalarial → empresa
        empresas = _empresas(self.request)
        return NominaExtrasalarial.objects.filter(
            id_proceso_extrasalarial__id_empresa__in=empresas
        )

    @action(detail=True, methods=["post"])
    def aprobar(self, request, pk=None):
        """Aprueba nómina extrasalarial"""
        nomina = self.get_object()

        if nomina.estado != "CALCULADA":
            return Response({"error": "Solo se pueden aprobar nóminas calculadas"}, status=status.HTTP_400_BAD_REQUEST)

        nomina.estado = "APROBADA"
        nomina.save()

        serializer = self.get_serializer(nomina)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def marcar_pagada(self, request, pk=None):
        """Marca nómina extrasalarial como pagada"""
        nomina = self.get_object()

        if nomina.estado != "APROBADA":
            return Response(
                {"error": "Solo se pueden marcar como pagadas nóminas aprobadas"}, status=status.HTTP_400_BAD_REQUEST
            )

        nomina.estado = "PAGADA"
        nomina.save()

        serializer = self.get_serializer(nomina)
        return Response(serializer.data)
