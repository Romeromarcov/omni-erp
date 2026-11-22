"""Vistas REST del módulo CRM (clientes + pipeline/etapas/leads/actividades S4)."""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.exceptions import domain_error_response
from apps.core.models import Usuarios
from apps.core.viewsets import (
    ActiveFilterMixin,
    BaseModelViewSet,
    NulSafeFilterMixin,
    SoftDeleteModelMixin,
    get_empresa_primaria,
    get_empresas_visible,
    validar_uuid_param,
)

from .models import Actividad, Cliente, ContactoCliente, DireccionCliente, Etapa, Lead, Pipeline
from .serializers import (
    ActividadSerializer,
    AnonimizarLeadInputSerializer,
    AsegurarPipelineInputSerializer,
    ClienteSerializer,
    CompletarActividadSerializer,
    ContactoClienteSerializer,
    ConvertirLeadInputSerializer,
    ConvertirLeadResponseSerializer,
    DireccionClienteSerializer,
    EtapaSerializer,
    LeadSerializer,
    MoverEtapaSerializer,
    PipelineSerializer,
    ReordenarEtapasSerializer,
)
from .services import (
    CrmError,
    asegurar_pipeline_empresa,
    completar_actividad,
    crear_lead_crm,
    mover_lead_etapa,
    registrar_actividad_crm,
    reordenar_etapas_pipeline,
    validar_sin_nul_recursivo,
)
from .services_conversion import anonimizar_lead, convertir_lead_a_cliente


def _empresas(request):
    return get_empresas_visible(request.user)


class ClienteViewSet(BaseModelViewSet):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer

    def get_queryset(self):
        empresas = _empresas(self.request)
        qs = Cliente.objects.filter(id_empresa__in=empresas)
        empresa_id = self.request.query_params.get("empresa")
        if empresa_id:
            qs = qs.filter(id_empresa=empresa_id)
        return qs

    @action(detail=False, methods=["get"], url_path="buscar-por-rif")
    def buscar_por_rif(self, request):
        """GET /api/crm/clientes/buscar-por-rif/?rif=J-12345678"""
        rif = request.query_params.get("rif", "").strip()
        if not rif:
            return Response({"error": "Parámetro 'rif' requerido."}, status=status.HTTP_400_BAD_REQUEST)
        qs = self.get_queryset().filter(rif__icontains=rif)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="historial-ventas")
    def historial_ventas(self, request, pk=None):
        """GET /api/crm/clientes/{pk}/historial-ventas/"""
        from apps.ventas.models import Pedido
        from apps.ventas.serializers import PedidoSerializer

        cliente = self.get_object()
        pedidos = (
            Pedido.objects.filter(
                id_empresa__in=_empresas(request),
                id_cliente=cliente,
            )
            .select_related("id_empresa")
            .prefetch_related("detalles")
            .order_by("-fecha_pedido")
        )

        return Response(
            {
                "cliente_id": str(cliente.id_cliente),
                "razon_social": cliente.razon_social,
                "rif": cliente.rif,
                "tipo_cliente": cliente.tipo_cliente,
                "limite_credito": str(cliente.limite_credito),
                "dias_credito": cliente.dias_credito,
                "pedidos": PedidoSerializer(pedidos, many=True).data,
            }
        )

    @action(detail=True, methods=["get"], url_path="credito-disponible")
    def credito_disponible(self, request, pk=None):
        """
        GET /api/crm/clientes/{pk}/credito-disponible/
        Devuelve saldo de CxC pendiente y crédito disponible.
        """
        from decimal import Decimal

        from django.db.models import Sum

        from apps.cuentas_por_cobrar.models import CuentaPorCobrar

        cliente = self.get_object()
        if cliente.tipo_cliente != "CREDITO":
            return Response({"credito_disponible": None, "detalle": "Cliente de contado."})

        saldo_pendiente = CuentaPorCobrar.objects.filter(
            cliente=cliente,
            empresa__in=_empresas(request),
            estado__in=["pendiente", "parcial", "vencida"],
        ).aggregate(total=Sum("monto"))["total"] or Decimal("0")

        disponible = cliente.limite_credito - saldo_pendiente
        return Response(
            {
                "cliente_id": str(cliente.id_cliente),
                "limite_credito": str(cliente.limite_credito),
                "saldo_pendiente": str(saldo_pendiente),
                "credito_disponible": str(max(disponible, Decimal("0"))),
                "bloqueado": disponible < 0,
            }
        )


class ContactoClienteViewSet(BaseModelViewSet):
    queryset = ContactoCliente.objects.all()
    serializer_class = ContactoClienteSerializer

    def get_queryset(self):
        # R-CODE-1: filtrar por empresa a través del FK id_cliente → id_empresa
        return ContactoCliente.objects.filter(id_empresa__in=_empresas(self.request))


class DireccionClienteViewSet(BaseModelViewSet):
    queryset = DireccionCliente.objects.all()
    serializer_class = DireccionClienteSerializer

    def get_queryset(self):
        # R-CODE-1: filtrar por empresa a través del FK id_cliente → id_empresa
        return DireccionCliente.objects.filter(id_empresa__in=_empresas(self.request))


# ── CRM ligero (Omni Connect S4): Pipeline, Etapa, Lead y Actividad ───────────


def _django_validation_a_drf(exc: DjangoValidationError) -> ValidationError:
    if hasattr(exc, "message_dict"):
        return ValidationError(exc.message_dict)
    return ValidationError({"detail": exc.messages})


def _validar_param_texto(valor: str | None, campo: str) -> str | None:
    if valor is None:
        return None
    try:
        validar_sin_nul_recursivo(valor, campo)
    except DjangoValidationError as exc:
        raise ValidationError({campo: "Parámetro de consulta inválido."}) from exc
    return valor


class _BaseCrmConnectViewSet(NulSafeFilterMixin, SoftDeleteModelMixin, ActiveFilterMixin, BaseModelViewSet):
    """Mixin base para los ViewSets de CRM ligero (NUL-safe, UUID-safe, soft-delete)."""

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        for key, values in request.query_params.lists():
            _validar_param_texto(str(key), "error")
            for val in values:
                _validar_param_texto(val, str(key))

    def _validar_lookup_uuid(self) -> None:
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        if lookup_url_kwarg in self.kwargs:
            validar_uuid_param(self.kwargs[lookup_url_kwarg], self.lookup_field)

    def get_object(self):
        self._validar_lookup_uuid()
        return super().get_object()

    def _get_object_any_state(self):
        self._validar_lookup_uuid()
        return super()._get_object_any_state()

    def _guardar_validado(self, instancia: Any) -> None:
        try:
            with transaction.atomic():
                instancia.full_clean()
                instancia.save()
        except DjangoValidationError as exc:
            raise _django_validation_a_drf(exc) from exc
        except IntegrityError as exc:
            raise ValidationError({"detail": "Conflicto de unicidad o integridad con un registro existente."}) from exc


def _empresa_activa_para_request(request: Request, empresa_payload: Any = None):
    if empresa_payload is not None:
        return empresa_payload
    empresas = _empresas(request)
    empresa_param = request.query_params.get("empresa") or request.query_params.get("empresa_id")
    if empresa_param:
        emp_uuid = uuid.UUID(validar_uuid_param(empresa_param, "empresa"))
        empresa = empresas.filter(pk=emp_uuid).first()
        if empresa is None:
            raise PermissionDenied("No tienes acceso a la empresa solicitada.")
        return empresa
    empresa = get_empresa_primaria(request.user)
    if empresa is None:
        raise PermissionDenied("El usuario no tiene empresa asignada.")
    return empresa


class PipelineViewSet(_BaseCrmConnectViewSet):
    """CRUD multi-tenant de embudos de ventas (``crm.Pipeline``) y acciones de etapas."""

    queryset = Pipeline.objects.all()
    serializer_class = PipelineSerializer
    search_fields = ["nombre"]
    ordering_fields = ["nombre", "es_predeterminado", "fecha_creacion", "fecha_actualizacion"]
    ordering = ["nombre"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Pipeline.objects.none()
        qs = super().get_queryset().filter(id_empresa__in=_empresas(self.request))
        empresa_param = self.request.query_params.get("empresa") or self.request.query_params.get("empresa_id")
        if empresa_param:
            qs = qs.filter(id_empresa_id=validar_uuid_param(empresa_param, "empresa"))
        return qs.prefetch_related(
            Prefetch(
                "etapas",
                queryset=Etapa.objects.filter(activo=True).order_by("orden", "nombre"),
            )
        )

    def perform_create(self, serializer):
        data = serializer.validated_data
        empresa = data.get("id_empresa") or get_empresa_primaria(self.request.user)
        if empresa is None:
            raise PermissionDenied("El usuario no tiene empresa asignada.")
        instancia = Pipeline(
            id_empresa=empresa,
            nombre=data["nombre"],
            es_predeterminado=bool(data.get("es_predeterminado", False)),
            activo=bool(data.get("activo", True)),
        )
        self._guardar_validado(instancia)
        serializer.instance = instancia

    def perform_update(self, serializer):
        instancia: Pipeline = serializer.instance
        data = serializer.validated_data
        if "id_empresa" in data and data["id_empresa"].pk != instancia.id_empresa_id:
            raise ValidationError({"id_empresa": "La empresa del pipeline es inmutable."})
        for campo, valor in data.items():
            setattr(instancia, campo, valor)
        self._guardar_validado(instancia)

    @swagger_auto_schema(
        method="post",
        operation_summary="Obtiene o inicializa idempotentemente el pipeline predeterminado de la empresa",
        manual_parameters=[
            openapi.Parameter(
                "empresa",
                openapi.IN_QUERY,
                description="UUID de la empresa visible (opcional).",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_UUID,
                required=False,
            )
        ],
        request_body=AsegurarPipelineInputSerializer,
        responses={200: PipelineSerializer, 400: "Parámetros inválidos", 403: "Sin acceso"},
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="asegurar-predeterminado",
        serializer_class=AsegurarPipelineInputSerializer,
    )
    def asegurar_predeterminado(self, request: Request) -> Response:
        ser = self.get_serializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        empresa = _empresa_activa_para_request(request, ser.validated_data.get("id_empresa"))
        try:
            pipeline = asegurar_pipeline_empresa(empresa)
        except CrmError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="error")

        pipeline_con_etapas = (
            Pipeline.objects.prefetch_related(
                Prefetch("etapas", queryset=Etapa.objects.filter(activo=True).order_by("orden", "nombre"))
            )
            .filter(pk=pipeline.pk)
            .first()
            or pipeline
        )
        return Response(
            PipelineSerializer(pipeline_con_etapas, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        method="post",
        operation_summary="Reordena atómicamente las etapas activas del pipeline",
        request_body=ReordenarEtapasSerializer,
        responses={200: PipelineSerializer, 400: "Orden o etapas inválidas", 404: "Pipeline no encontrado"},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="reordenar-etapas",
        serializer_class=ReordenarEtapasSerializer,
    )
    def reordenar_etapas(self, request: Request, pk: str | None = None) -> Response:
        pipeline = self.get_object()
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            reordenar_etapas_pipeline(pipeline, ser.validated_data["etapas"])
        except (CrmError, DjangoValidationError) as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="error")

        pipeline_refrescado = (
            Pipeline.objects.prefetch_related(
                Prefetch("etapas", queryset=Etapa.objects.filter(activo=True).order_by("orden", "nombre"))
            )
            .filter(pk=pipeline.pk)
            .first()
            or pipeline
        )
        return Response(
            PipelineSerializer(pipeline_refrescado, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )


class EtapaViewSet(_BaseCrmConnectViewSet):
    """CRUD multi-tenant de etapas configurables de ``crm.Pipeline``."""

    queryset = Etapa.objects.all()
    serializer_class = EtapaSerializer
    search_fields = ["nombre"]
    ordering_fields = ["orden", "nombre", "tipo", "fecha_creacion"]
    ordering = ["pipeline", "orden", "nombre"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Etapa.objects.none()
        qs = super().get_queryset().filter(id_empresa__in=_empresas(self.request)).select_related("pipeline")
        empresa_param = self.request.query_params.get("empresa") or self.request.query_params.get("empresa_id")
        if empresa_param:
            qs = qs.filter(id_empresa_id=validar_uuid_param(empresa_param, "empresa"))
        pipeline_param = self.request.query_params.get("pipeline")
        if pipeline_param:
            qs = qs.filter(pipeline_id=validar_uuid_param(pipeline_param, "pipeline"))
        return qs

    def perform_create(self, serializer):
        data = serializer.validated_data
        pipeline = data["pipeline"]
        empresa = data.get("id_empresa") or pipeline.id_empresa
        instancia = Etapa(
            id_empresa=empresa,
            pipeline=pipeline,
            nombre=data["nombre"],
            orden=data.get("orden", 0),
            tipo=data.get("tipo", Etapa.Tipo.ABIERTA),
            activo=bool(data.get("activo", True)),
        )
        self._guardar_validado(instancia)
        serializer.instance = instancia

    def perform_update(self, serializer):
        instancia: Etapa = serializer.instance
        data = serializer.validated_data
        if "id_empresa" in data and data["id_empresa"].pk != instancia.id_empresa_id:
            raise ValidationError({"id_empresa": "La empresa de la etapa es inmutable."})
        for campo, valor in data.items():
            setattr(instancia, campo, valor)
        self._guardar_validado(instancia)


def _annotar_leads_queryset(qs: Any) -> Any:
    ahora = timezone.now()
    return qs.select_related(
        "pipeline",
        "etapa",
        "propietario",
        "tarjeta",
        "perfil",
        "contacto",
        "cliente_convertido",
    ).annotate(
        actividades_pendientes_count=Count(
            "actividades",
            filter=Q(actividades__activo=True, actividades__completada=False),
            distinct=True,
        ),
        actividades_vencidas_count=Count(
            "actividades",
            filter=Q(
                actividades__activo=True,
                actividades__completada=False,
                actividades__fecha_vencimiento__lt=ahora,
            ),
            distinct=True,
        ),
    )


def _lead_serializable(lead_pk: Any, user: Any) -> Lead | None:
    """Recupera un ``Lead`` anotado por PK y empresa visible sin depender de ``query_params``."""
    return _annotar_leads_queryset(Lead.objects.filter(pk=lead_pk, id_empresa__in=get_empresas_visible(user))).first()


class LeadViewSet(_BaseCrmConnectViewSet):
    """CRUD multi-tenant de ``crm.Lead`` con filtros Kanban y acción ``mover-etapa``."""

    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    search_fields = ["nombre", "apellido", "empresa_nombre", "email", "telefono"]
    ordering_fields = [
        "nombre",
        "apellido",
        "empresa_nombre",
        "fuente",
        "fecha_creacion",
        "fecha_actualizacion",
    ]
    ordering = ["-fecha_creacion"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Lead.objects.none()
        qs = _annotar_leads_queryset(super().get_queryset().filter(id_empresa__in=_empresas(self.request)))
        params = self.request.query_params
        empresa_param = params.get("empresa") or params.get("empresa_id")
        if empresa_param:
            qs = qs.filter(id_empresa_id=validar_uuid_param(empresa_param, "empresa"))
        for param_name, field_name in (
            ("pipeline", "pipeline_id"),
            ("etapa", "etapa_id"),
            ("propietario", "propietario_id"),
        ):
            val = params.get(param_name)
            if val:
                qs = qs.filter(**{field_name: validar_uuid_param(val, param_name)})
        fuente = params.get("fuente")
        if fuente:
            fuente_limpia = _validar_param_texto(fuente, "fuente") or ""
            qs = qs.filter(fuente=fuente_limpia.strip().upper())
        return qs

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        empresa = data.get("id_empresa") or get_empresa_primaria(request.user)
        if empresa is None:
            raise PermissionDenied("El usuario no tiene empresa asignada.")
        propietario = data.get("propietario") or (request.user if isinstance(request.user, Usuarios) else None)
        if propietario is None:
            raise PermissionDenied("Se requiere un usuario propietario válido para crear el lead.")

        try:
            lead = crear_lead_crm(
                empresa=empresa,
                nombre=data["nombre"],
                propietario=propietario,
                apellido=data.get("apellido", ""),
                empresa_nombre=data.get("empresa_nombre", ""),
                email=data.get("email", ""),
                telefono=data.get("telefono", ""),
                mensaje=data.get("mensaje", ""),
                fuente=data.get("fuente", Lead.Fuente.MANUAL),
                pipeline=data.get("pipeline"),
                etapa=data.get("etapa"),
                tarjeta=data.get("tarjeta"),
                perfil=data.get("perfil"),
                contacto=data.get("contacto"),
                consentimiento_aceptado=bool(data.get("consentimiento_aceptado", False)),
                consentimiento_fecha=data.get("consentimiento_fecha"),
                consentimiento_texto=data.get("consentimiento_texto", ""),
            )
        except CrmError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="error")
        except DjangoValidationError as exc:
            raise _django_validation_a_drf(exc) from exc
        except IntegrityError as exc:
            raise ValidationError({"detail": "No se pudo crear el lead por restricción de integridad."}) from exc

        lead_refrescado = _lead_serializable(lead.pk, request.user) or lead
        out = self.get_serializer(lead_refrescado)
        headers = self.get_success_headers(out.data)
        return Response(out.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_update(self, serializer):
        instancia: Lead = serializer.instance
        data = serializer.validated_data
        if "id_empresa" in data and data["id_empresa"].pk != instancia.id_empresa_id:
            raise ValidationError({"id_empresa": "La empresa del lead es inmutable."})
        for campo, valor in data.items():
            setattr(instancia, campo, valor)
        self._guardar_validado(instancia)

    @swagger_auto_schema(
        method="post",
        operation_summary="Mueve un lead a otra etapa del mismo pipeline",
        request_body=MoverEtapaSerializer,
        responses={200: LeadSerializer, 400: "Transición de etapa inválida", 404: "Lead no encontrado"},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="mover-etapa",
        serializer_class=MoverEtapaSerializer,
    )
    def mover_etapa(self, request: Request, pk: str | None = None) -> Response:
        lead = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        nueva_etapa = serializer.validated_data["etapa"]
        usuario = request.user if isinstance(request.user, Usuarios) else None
        try:
            lead_actualizado = mover_lead_etapa(lead, nueva_etapa, usuario)
        except (CrmError, DjangoValidationError) as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="error")

        lead_refrescado = _lead_serializable(lead_actualizado.pk, request.user) or lead_actualizado
        return Response(
            LeadSerializer(lead_refrescado, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        method="post",
        operation_summary="Anonimiza la PII de un lead conforme al derecho al olvido",
        request_body=AnonimizarLeadInputSerializer,
        responses={
            200: LeadSerializer,
            400: "Lead ya anonimizado o inválido",
            404: "Lead no encontrado",
        },
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="anonimizar",
        serializer_class=AnonimizarLeadInputSerializer,
    )
    def anonimizar(self, request: Request, pk: str | None = None) -> Response:
        lead = self.get_object()
        payload_in = {} if request.data is None or request.data == "" else request.data
        serializer = self.get_serializer(data=payload_in)
        serializer.is_valid(raise_exception=True)
        usuario = request.user if isinstance(request.user, Usuarios) else None
        empresa_ids = list(_empresas(request).values_list("pk", flat=True))
        request_meta = {
            "REMOTE_ADDR": request.META.get("REMOTE_ADDR"),
            "HTTP_USER_AGENT": request.META.get("HTTP_USER_AGENT"),
            "motivo": serializer.validated_data.get("motivo", ""),
        }
        try:
            lead_anon = anonimizar_lead(
                lead.pk,
                usuario,
                empresa_ids=empresa_ids,
                request_meta=request_meta,
            )
        except (CrmError, DjangoValidationError) as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="error")

        lead_refrescado = _lead_serializable(lead_anon.pk, request.user) or lead_anon
        return Response(
            LeadSerializer(lead_refrescado, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        method="post",
        operation_summary="Convierte atómica e idempotentemente un lead en cliente (+ cotización borrador opcional)",
        request_body=ConvertirLeadInputSerializer,
        responses={
            200: ConvertirLeadResponseSerializer,
            400: "Datos o estado inválido para convertir",
            404: "Lead no encontrado",
        },
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="convertir-cliente",
        serializer_class=ConvertirLeadInputSerializer,
    )
    def convertir_cliente(self, request: Request, pk: str | None = None) -> Response:
        lead = self.get_object()
        payload_in = {} if request.data is None or request.data == "" else request.data
        serializer = self.get_serializer(data=payload_in)
        serializer.is_valid(raise_exception=True)
        usuario = request.user if isinstance(request.user, Usuarios) else None
        empresa_ids = list(_empresas(request).values_list("pk", flat=True))
        request_meta = {
            "REMOTE_ADDR": request.META.get("REMOTE_ADDR"),
            "HTTP_USER_AGENT": request.META.get("HTTP_USER_AGENT"),
        }
        try:
            resultado = convertir_lead_a_cliente(
                lead.pk,
                usuario,
                serializer.validated_data,
                empresa_ids=empresa_ids,
                request_meta=request_meta,
            )
        except (CrmError, DjangoValidationError) as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="error")
        except IntegrityError:
            return domain_error_response(
                CrmError("Conflicto de unicidad o integridad al convertir el lead."),
                status_code=status.HTTP_400_BAD_REQUEST,
                key="error",
            )

        lead_refrescado = _lead_serializable(resultado["lead"].pk, request.user) or resultado["lead"]
        cotizacion = resultado["cotizacion"]
        ctx = self.get_serializer_context()
        return Response(
            {
                "ya_convertido": bool(resultado["ya_convertido"]),
                "lead": LeadSerializer(lead_refrescado, context=ctx).data,
                "cliente": ClienteSerializer(resultado["cliente"], context=ctx).data,
                "cotizacion_id": str(cotizacion.id_cotizacion) if cotizacion is not None else None,
                "numero_cotizacion": cotizacion.numero_cotizacion if cotizacion is not None else None,
            },
            status=status.HTTP_200_OK,
        )


class ActividadViewSet(_BaseCrmConnectViewSet):
    """CRUD multi-tenant de ``crm.Actividad`` y acción ``completar``."""

    queryset = Actividad.objects.all()
    serializer_class = ActividadSerializer
    search_fields = ["asunto", "descripcion"]
    ordering_fields = [
        "tipo",
        "asunto",
        "fecha_vencimiento",
        "completada",
        "fecha_completada",
        "fecha_creacion",
    ]
    ordering = ["-fecha_creacion"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Actividad.objects.none()
        qs = (
            super()
            .get_queryset()
            .filter(id_empresa__in=_empresas(self.request))
            .select_related("lead", "asignado_a", "creado_por", "tarea")
        )
        params = self.request.query_params
        empresa_param = params.get("empresa") or params.get("empresa_id")
        if empresa_param:
            qs = qs.filter(id_empresa_id=validar_uuid_param(empresa_param, "empresa"))
        lead_param = params.get("lead")
        if lead_param:
            qs = qs.filter(lead_id=validar_uuid_param(lead_param, "lead"))
        asignado_param = params.get("asignado_a")
        if asignado_param:
            qs = qs.filter(asignado_a_id=validar_uuid_param(asignado_param, "asignado_a"))
        tipo_param = params.get("tipo")
        if tipo_param:
            tipo_limpio = _validar_param_texto(tipo_param, "tipo") or ""
            qs = qs.filter(tipo=tipo_limpio.strip().upper())
        completada_param = params.get("completada")
        if completada_param is not None and completada_param != "":
            comp_limpio = _validar_param_texto(completada_param, "completada") or ""
            low = comp_limpio.strip().lower()
            if low in ("true", "1", "yes"):
                qs = qs.filter(completada=True)
            elif low in ("false", "0", "no"):
                qs = qs.filter(completada=False)
            else:
                raise ValidationError({"completada": "Valor booleano inválido (use true o false)."})
        return qs

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        lead: Lead = data["lead"]
        empresa = data.get("id_empresa") or lead.id_empresa
        creado_por = request.user if isinstance(request.user, Usuarios) else None

        try:
            actividad = registrar_actividad_crm(
                empresa=empresa,
                lead=lead,
                tipo=data.get("tipo", Actividad.Tipo.NOTA),
                asunto=data["asunto"],
                descripcion=data.get("descripcion", ""),
                fecha_vencimiento=data.get("fecha_vencimiento"),
                completada=bool(data.get("completada", False)),
                asignado_a=data.get("asignado_a"),
                creado_por=creado_por,
                tarea=data.get("tarea"),
            )
        except CrmError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="error")
        except DjangoValidationError as exc:
            raise _django_validation_a_drf(exc) from exc
        except IntegrityError as exc:
            raise ValidationError(
                {"detail": "No se pudo registrar la actividad por restricción de integridad."}
            ) from exc

        out = self.get_serializer(actividad)
        headers = self.get_success_headers(out.data)
        return Response(out.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_update(self, serializer):
        instancia: Actividad = serializer.instance
        data = serializer.validated_data
        if "id_empresa" in data and data["id_empresa"].pk != instancia.id_empresa_id:
            raise ValidationError({"id_empresa": "La empresa de la actividad es inmutable."})
        if "completada" in data:
            nuevo_estado = bool(data["completada"])
            if nuevo_estado != instancia.completada:
                instancia.fecha_completada = timezone.now() if nuevo_estado else None
        for campo, valor in data.items():
            setattr(instancia, campo, valor)
        self._guardar_validado(instancia)

    @swagger_auto_schema(
        method="post",
        operation_summary="Marca o desmarca una actividad como completada",
        request_body=CompletarActividadSerializer,
        responses={200: ActividadSerializer, 400: "Error de validación", 404: "Actividad no encontrada"},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="completar",
        serializer_class=CompletarActividadSerializer,
    )
    def completar(self, request: Request, pk: str | None = None) -> Response:
        actividad = self.get_object()
        serializer = self.get_serializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            actualizada = completar_actividad(
                actividad,
                completada=serializer.validated_data.get("completada", True),
                descripcion=serializer.validated_data.get("descripcion"),
            )
        except (CrmError, DjangoValidationError) as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="error")
        return Response(
            ActividadSerializer(actualizada, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )
