"""
Vistas del módulo de Agentes IA (M9 / Plan 05 P2-2).

Expone:
  - PrediccionAgenteViewSet: CRUD de predicciones con aislamiento multi-tenant.
  - Acciones custom (asíncronas vía Celery → HTTP 202 Accepted):
      · analizar-cobranza        — encola CobranzaEstrategaAgent
      · analizar-reorden         — encola ReordenSugeridorAgent
      · analizar-personalizacion — encola PersonalizacionCapa2Agent
      · clasificar-gasto         — encola ClasificadorGastos en modo producción
      · metricas-clasificador    — métricas de calidad del ClasificadorGastos
      · sugerencias-activas      — predicciones pendientes de revisión humana
      · responder / evaluar      — feedback humano sobre una predicción
  - EjecucionAgenteViewSet: consulta de solo lectura de ejecuciones asíncronas.
"""

from datetime import date
import logging
import re

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.core.idempotency import idempotent
from apps.core.throttling import EscrituraRateThrottle
from apps.core.viewsets import BaseModelViewSet, NulSafeFilterMixin, get_empresas_visible, validar_uuid_param

from .models import ConsumoLLM, EjecucionAgente, PrediccionAgente
from .operativos import AGENTES_OPERATIVOS, ejecutar_agente_operativo
from .serializers import (
    AnalizarCobranzaInputSerializer,
    AnalizarPersonalizacionInputSerializer,
    AnalizarReordenInputSerializer,
    CalificarLeadConnectInputSerializer,
    ClasificarGastoInputSerializer,
    ConsumoLLMResumenSerializer,
    ConsumoLLMSerializer,
    EjecucionAgenteSerializer,
    EjecutarAgenteOperativoInputSerializer,
    PrediccionAgenteSerializer,
    ProponerSeguimientoConnectInputSerializer,
)
from .services import AgenteError, calcular_resumen_consumo_llm, encolar_ejecucion_agente

logger = logging.getLogger(__name__)

_EMPRESA_ID_QUERY_PARAM = openapi.Parameter(
    "empresa_id",
    openapi.IN_QUERY,
    description="UUID de empresa visible (obligatorio para superusuarios Omni sin empresa propia).",
    type=openapi.TYPE_STRING,
    format=openapi.FORMAT_UUID,
    required=False,
)


def _resolver_empresa(request, empresa_id=None):
    """
    Resuelve la empresa objetivo respetando multi-empresa, matriz↔subsidiaria y superusuario.

    - Sin empresas visibles → ``(None, 403)``.
    - Con ``empresa_id`` explícito → valida pertenencia a ``get_empresas_visible`` (403 si ajena).
    - Sin ``empresa_id`` explícito:
      · Usa ``user.id_empresa`` si existe y es visible.
      · Si ``es_superusuario_omni=True`` (sin empresa propia), exige ``empresa_id`` (400).
      · Para usuarios multi-empresa/matriz, prioriza su(s) empresa(s) asignada(s) antes de subsidiarias.
    """
    user = request.user
    empresas = get_empresas_visible(user)
    if not empresas.exists():
        return None, Response({"detail": "Sin empresa asignada."}, status=status.HTTP_403_FORBIDDEN)

    if empresa_id is not None:
        empresa = empresas.filter(pk=empresa_id).first()
        if empresa is None:
            return None, Response(
                {"detail": "No tienes permiso para operar sobre esa empresa."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return empresa, None

    id_empresa_propia = getattr(user, "id_empresa_id", None) or getattr(user, "id_empresa", None)
    if id_empresa_propia is not None:
        id_empresa_propia_pk = getattr(id_empresa_propia, "pk", id_empresa_propia)
        empresa_propia = empresas.filter(pk=id_empresa_propia_pk).first()
        if empresa_propia is not None:
            return empresa_propia, None

    if getattr(user, "es_superusuario_omni", False):
        return None, Response(
            {"detail": "Debe especificar empresa_id para operar como superusuario Omni."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if hasattr(user, "empresas"):
        propia_m2m = user.empresas.filter(pk__in=empresas.values("pk")).order_by("id_empresa").first()
        if propia_m2m is not None:
            return propia_m2m, None

    return empresas.first(), None


def _validar_input(serializer_cls, raw_data):
    """Valida el payload de entrada con el serializer DRF (acepta None como dict vacío)."""
    data = {} if raw_data is None else raw_data
    serializer = serializer_cls(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


# ── Helpers para sugerencias activas ──────────────────────────────────────────

_TITULOS_AGENTE = {
    "cobranza_estratega": "Cobranza",
    "reorden_sugeridor": "Reorden de Stock",
    "clasificador_gastos": "Clasificación de Gasto",
    "personalizacion_capa2": "Personalización",
    "connect_calificador": "Calificador Connect",
    "connect_seguimiento": "Seguimiento Connect",
}


def _titulo_sugerencia(prediccion) -> str:
    """Genera un título legible para la tarjeta de sugerencia."""
    agente_label = _TITULOS_AGENTE.get(prediccion.agente, prediccion.agente)
    if prediccion.agente == "cobranza_estratega":
        cliente = prediccion.input_metadata.get("cliente_nombre", "")
        monto = prediccion.input_monto
        if cliente:
            return f"Contactar a {cliente}" + (f" — ${monto}" if monto else "")
        return "Acción de cobranza requerida"
    if prediccion.agente == "reorden_sugeridor":
        producto = prediccion.input_metadata.get("nombre_producto", prediccion.input_texto or "")
        if producto:
            return f"Reponer: {producto[:40]}"
        return "Reorden de inventario sugerido"
    if prediccion.agente == "clasificador_gastos":
        return f"Clasificar gasto: {prediccion.categoria_predicha}"
    if prediccion.agente == "connect_calificador":
        return f"Lead Connect ({prediccion.categoria_predicha})"
    if prediccion.agente == "connect_seguimiento":
        return f"Seguimiento Connect: {prediccion.categoria_predicha}"
    return f"Sugerencia — {agente_label}: {prediccion.categoria_predicha}"


def _accion_para_sugerencia(prediccion) -> str:
    """Retorna la URL de acción sugerida para navegar desde la tarjeta."""
    meta = prediccion.input_metadata or {}
    if prediccion.agente == "cobranza_estratega":
        cxc_id = meta.get("cxc_id")
        if cxc_id:
            return f"/cxc/{cxc_id}/"
    if prediccion.agente == "reorden_sugeridor":
        prod_id = meta.get("producto_id")
        if prod_id:
            return f"/inventario/productos/{prod_id}/"
    if prediccion.agente in ("connect_calificador", "connect_seguimiento"):
        if meta.get("solicitud_aprobacion_id"):
            return "/aprobaciones/solicitudes"
        if meta.get("lead_id"):
            return "/crm/pipeline"
    return ""


class PrediccionAgenteViewSet(NulSafeFilterMixin, BaseModelViewSet):
    """
    CRUD de predicciones de agentes IA y disparo asíncrono de análisis.

    GET  /agentes/predicciones/                         — listar (filtrable por ?agente=)
    GET  /agentes/predicciones/{pk}/                    — detalle
    PATCH /agentes/predicciones/{pk}/                   — actualizar resultado_humano / categoria_correcta
    DELETE /agentes/predicciones/{pk}/                  — eliminar

    Acciones custom:
    POST /agentes/predicciones/analizar-cobranza/       — encola CobranzaEstrategaAgent (202)
    POST /agentes/predicciones/analizar-reorden/        — encola ReordenSugeridorAgent (202)
    POST /agentes/predicciones/analizar-personalizacion/ — encola PersonalizacionCapa2Agent (202)
    POST /agentes/predicciones/clasificar-gasto/        — encola ClasificadorGastos (202)
    """

    queryset = PrediccionAgente.objects.all()
    serializer_class = PrediccionAgenteSerializer
    lookup_value_regex = r"[0-9a-fA-F-]{36}"
    search_fields = ["agente", "categoria_predicha", "input_texto"]
    ordering_fields = ["fecha_prediccion", "confianza", "agente"]
    ordering = ["-fecha_prediccion"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PrediccionAgente.objects.none()
        # R-CODE-1
        empresas = get_empresas_visible(self.request.user)
        qs = PrediccionAgente.objects.filter(id_empresa__in=empresas)
        agente = self.request.query_params.get("agente")
        if agente:
            if "\x00" in agente:
                raise ValidationError({"agente": "Parámetro de consulta inválido."})
            qs = qs.filter(agente=agente)
        return qs

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        if lookup_url_kwarg in self.kwargs:
            validar_uuid_param(self.kwargs[lookup_url_kwarg], self.lookup_field)
        return super().get_object()

    def _responder_encolado(self, request, *, empresa, agente: str, parametros: dict):
        iniciado_por = request.user if getattr(request.user, "is_authenticated", False) else None
        try:
            ejecucion = encolar_ejecucion_agente(
                empresa=empresa,
                agente=agente,
                parametros=parametros,
                iniciado_por=iniciado_por,
            )
        except AgenteError:
            return Response(
                {"code": "agente_error", "detail": "No se pudo encolar el análisis del agente."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            EjecucionAgenteSerializer(ejecucion).data,
            status=status.HTTP_202_ACCEPTED,
        )

    @swagger_auto_schema(
        request_body=AnalizarCobranzaInputSerializer,
        responses={202: EjecucionAgenteSerializer},
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="analizar-cobranza",
        throttle_classes=[*BaseModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def analizar_cobranza(self, request):
        """
        POST /agentes/predicciones/analizar-cobranza/

        Encola en Celery el ``CobranzaEstrategaAgent`` para la empresa indicada o por defecto.
        Body (opcional): {"empresa_id": "<uuid>", "persistir": true}

        Retorna HTTP 202 Accepted con el estado de la ``EjecucionAgente``.
        """
        if not get_empresas_visible(request.user).exists():
            return Response({"detail": "Sin empresa asignada."}, status=status.HTTP_403_FORBIDDEN)

        params = _validar_input(AnalizarCobranzaInputSerializer, request.data)
        empresa, err = _resolver_empresa(request, empresa_id=params.get("empresa_id"))
        if err is not None:
            return err

        return self._responder_encolado(
            request,
            empresa=empresa,
            agente="cobranza_estratega",
            parametros={"persistir": bool(params.get("persistir", False))},
        )

    @swagger_auto_schema(
        request_body=AnalizarReordenInputSerializer,
        responses={202: EjecucionAgenteSerializer},
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="analizar-reorden",
        throttle_classes=[*BaseModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def analizar_reorden(self, request):
        """
        POST /agentes/predicciones/analizar-reorden/

        Encola en Celery el ``ReordenSugeridorAgent`` para la empresa indicada o por defecto.
        Body (opcional): {"empresa_id": "<uuid>", "solo_alertas": true, "persistir": false}

        Retorna HTTP 202 Accepted con el estado de la ``EjecucionAgente``.
        """
        if not get_empresas_visible(request.user).exists():
            return Response({"detail": "Sin empresa asignada."}, status=status.HTTP_403_FORBIDDEN)

        params = _validar_input(AnalizarReordenInputSerializer, request.data)
        empresa, err = _resolver_empresa(request, empresa_id=params.get("empresa_id"))
        if err is not None:
            return err

        return self._responder_encolado(
            request,
            empresa=empresa,
            agente="reorden_sugeridor",
            parametros={
                "solo_alertas": bool(params.get("solo_alertas", True)),
                "persistir": bool(params.get("persistir", False)),
            },
        )

    @swagger_auto_schema(
        request_body=AnalizarPersonalizacionInputSerializer,
        responses={202: EjecucionAgenteSerializer},
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="analizar-personalizacion",
        throttle_classes=[*BaseModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def analizar_personalizacion(self, request):
        """
        POST /agentes/predicciones/analizar-personalizacion/

        Encola en Celery el ``PersonalizacionCapa2Agent`` para la empresa indicada o por defecto.

        Retorna HTTP 202 Accepted con el estado de la ``EjecucionAgente``.
        """
        if not get_empresas_visible(request.user).exists():
            return Response({"detail": "Sin empresa asignada."}, status=status.HTTP_403_FORBIDDEN)

        params = _validar_input(AnalizarPersonalizacionInputSerializer, request.data)
        empresa, err = _resolver_empresa(request, empresa_id=params.get("empresa_id"))
        if err is not None:
            return err

        return self._responder_encolado(
            request,
            empresa=empresa,
            agente="personalizacion_capa2",
            parametros={},
        )

    @swagger_auto_schema(
        request_body=ClasificarGastoInputSerializer,
        responses={202: EjecucionAgenteSerializer},
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="clasificar-gasto",
        throttle_classes=[*BaseModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def clasificar_gasto(self, request):
        """
        POST /agentes/predicciones/clasificar-gasto/

        Valida pertenencia multi-tenant del gasto en todas las empresas visibles (R-CODE-1)
        y encola en Celery el ``ClasificadorGastos`` sobre la empresa dueña del gasto.

        Body:
          {
            "gasto_id": "<uuid>",
            "aplicar": false
          }

        Retorna HTTP 202 Accepted con el estado de la ``EjecucionAgente``.
        """
        from apps.gastos.models import Gasto

        empresas = get_empresas_visible(request.user)
        if not empresas.exists():
            return Response({"detail": "Sin empresa asignada."}, status=status.HTTP_403_FORBIDDEN)

        params = _validar_input(ClasificarGastoInputSerializer, request.data)
        gasto_id = params["gasto_id"]
        aplicar = bool(params.get("aplicar", False))

        # R-CODE-1: buscar en TODAS las empresas visibles (matriz, subsidiarias, multi-empresa)
        gasto = Gasto.objects.select_related("id_empresa").filter(pk=gasto_id, id_empresa__in=empresas).first()
        if gasto is None:
            return Response({"detail": "Gasto no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        return self._responder_encolado(
            request,
            empresa=gasto.id_empresa,
            agente="clasificador_gastos",
            parametros={"gasto_id": str(gasto_id), "aplicar": aplicar},
        )

    @swagger_auto_schema(
        request_body=CalificarLeadConnectInputSerializer,
        responses={202: EjecucionAgenteSerializer, 403: "Sin empresa asignada", 404: "Lead no encontrado"},
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="calificar-lead-connect",
        throttle_classes=[*BaseModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def calificar_lead_connect(self, request):
        """
        POST /api/agentes/predicciones/calificar-lead-connect/

        Valida pertenencia multi-tenant del lead y encola ``connect_calificador`` (HTTP 202).
        """
        from apps.crm.models import Lead

        empresas = get_empresas_visible(request.user)
        if not empresas.exists():
            return Response({"detail": "Sin empresa asignada."}, status=status.HTTP_403_FORBIDDEN)

        params = _validar_input(CalificarLeadConnectInputSerializer, request.data)
        lead_id = params["lead_id"]

        lead = Lead.objects.select_related("id_empresa").filter(pk=lead_id, id_empresa__in=empresas).first()
        if lead is None:
            return Response({"detail": "Lead no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        return self._responder_encolado(
            request,
            empresa=lead.id_empresa,
            agente="connect_calificador",
            parametros={"lead_id": str(lead_id)},
        )

    @swagger_auto_schema(
        request_body=ProponerSeguimientoConnectInputSerializer,
        responses={202: EjecucionAgenteSerializer, 403: "Sin empresa asignada", 404: "Lead no encontrado"},
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="proponer-seguimiento-connect",
        throttle_classes=[*BaseModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def proponer_seguimiento_connect(self, request):
        """
        POST /api/agentes/predicciones/proponer-seguimiento-connect/

        Valida pertenencia multi-tenant del lead y encola ``connect_seguimiento`` (HTTP 202).
        Toda propuesta de envío externo crea obligatoriamente una ``SolicitudAprobacion``
        (``CONNECT_ENVIO_EXTERNO``) sin enviar mensajes directamente.
        """
        from apps.crm.models import Lead

        empresas = get_empresas_visible(request.user)
        if not empresas.exists():
            return Response({"detail": "Sin empresa asignada."}, status=status.HTTP_403_FORBIDDEN)

        params = _validar_input(ProponerSeguimientoConnectInputSerializer, request.data)
        lead_id = params["lead_id"]

        lead = Lead.objects.select_related("id_empresa").filter(pk=lead_id, id_empresa__in=empresas).first()
        if lead is None:
            return Response({"detail": "Lead no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        return self._responder_encolado(
            request,
            empresa=lead.id_empresa,
            agente="connect_seguimiento",
            parametros={"lead_id": str(lead_id)},
        )

    @swagger_auto_schema(manual_parameters=[_EMPRESA_ID_QUERY_PARAM])
    @action(detail=False, methods=["get"], url_path="metricas-clasificador")
    def metricas_clasificador(self, request):
        """
        GET /agentes/predicciones/metricas-clasificador/

        Devuelve métricas de calidad del ClasificadorGastos para la empresa.
        """
        from .clasificador import ClasificadorGastos

        empresa_raw = request.query_params.get("empresa_id")
        empresa_uuid = validar_uuid_param(empresa_raw, "empresa_id") if empresa_raw else None
        empresa, err = _resolver_empresa(request, empresa_id=empresa_uuid)
        if err is not None:
            return err

        metricas = ClasificadorGastos.metricas_empresa(str(empresa.pk))
        return Response(metricas)

    @swagger_auto_schema(manual_parameters=[_EMPRESA_ID_QUERY_PARAM])
    @action(detail=False, methods=["get"], url_path="sugerencias-activas")
    def sugerencias_activas(self, request):
        """
        GET /agentes/predicciones/sugerencias-activas/

        Retorna las predicciones pendientes de revisión humana para las empresas visibles
        (o para ``?empresa_id=`` cuando se especifica). Por defecto las últimas 10,
        ordenadas por confianza DESC.

        Query params:
          ?limite=N     — máximo de resultados (default 10, max 50)
          ?agente=      — filtrar por nombre de agente
          ?empresa_id=  — acotar a una empresa visible (obligatorio para superusuario Omni)
        """
        empresas = get_empresas_visible(request.user)
        if not empresas.exists():
            return Response({"detail": "Sin empresa asignada."}, status=status.HTTP_403_FORBIDDEN)

        empresa_raw = request.query_params.get("empresa_id")
        if empresa_raw:
            empresa_uuid = validar_uuid_param(empresa_raw, "empresa_id")
            empresa, err = _resolver_empresa(request, empresa_id=empresa_uuid)
            if err is not None:
                return err
            qs = PrediccionAgente.objects.filter(
                id_empresa=empresa,
                resultado_humano="pendiente",
            )
        else:
            id_empresa_propia = getattr(request.user, "id_empresa_id", None) or getattr(
                request.user, "id_empresa", None
            )
            if getattr(request.user, "es_superusuario_omni", False) and id_empresa_propia is None:
                return Response(
                    {"detail": "Debe especificar empresa_id para operar como superusuario Omni."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = PrediccionAgente.objects.filter(
                id_empresa__in=empresas,
                resultado_humano="pendiente",
            )

        limite_raw = request.query_params.get("limite", 10)
        try:
            limite = max(1, min(int(limite_raw), 50))
        except (ValueError, TypeError) as exc:
            raise ValidationError({"limite": "El parámetro limite debe ser un entero válido."}) from exc

        agente_filtro = request.query_params.get("agente")
        if agente_filtro:
            if "\x00" in agente_filtro:
                raise ValidationError({"agente": "Parámetro de consulta inválido."})
            qs = qs.filter(agente=agente_filtro)

        sugerencias = qs.order_by("-confianza", "-fecha_prediccion")[:limite]

        data = []
        for s in sugerencias:
            accion = _accion_para_sugerencia(s)
            data.append(
                {
                    "id": str(s.id_prediccion),
                    "agente": s.agente,
                    "titulo": _titulo_sugerencia(s),
                    "descripcion": s.razonamiento or s.categoria_predicha,
                    "categoria": s.categoria_predicha,
                    "confianza": round(s.confianza, 3),
                    "monto": str(s.input_monto) if s.input_monto else None,
                    "metadata": s.input_metadata,
                    "url_accion": accion,
                    "fecha": s.fecha_prediccion.isoformat(),
                }
            )

        return Response({"sugerencias": data, "total": len(data)})

    @action(detail=True, methods=["post"], url_path="responder")
    def responder(self, request, pk=None):
        """
        POST /agentes/predicciones/{pk}/responder/

        Registra la respuesta humana a una sugerencia del agente.
        Body: {"accion": "aceptar"|"rechazar", "comentario": "..."}

        Retorna la predicción actualizada.
        """
        prediccion = self.get_object()

        accion = request.data.get("accion")
        if accion not in ("aceptar", "rechazar"):
            return Response(
                {"detail": "El campo 'accion' debe ser 'aceptar' o 'rechazar'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if prediccion.resultado_humano != "pendiente":
            return Response(
                {"detail": f"Esta sugerencia ya fue procesada: {prediccion.resultado_humano}."},
                status=status.HTTP_409_CONFLICT,
            )

        prediccion.resultado_humano = "aceptada" if accion == "aceptar" else "rechazada"
        comentario = request.data.get("comentario", "")
        if comentario:
            meta = dict(prediccion.input_metadata or {})
            meta["comentario_humano"] = comentario
            prediccion.input_metadata = meta

        prediccion.save(update_fields=["resultado_humano", "input_metadata"])

        return Response(
            {
                "id": str(prediccion.id_prediccion),
                "resultado_humano": prediccion.resultado_humano,
                "agente": prediccion.agente,
                "categoria": prediccion.categoria_predicha,
            }
        )

    @action(detail=True, methods=["patch"], url_path="evaluar")
    def evaluar(self, request, pk=None):
        """
        PATCH /agentes/predicciones/{pk}/evaluar/

        Registra la evaluación humana de una predicción.
        Body: {"resultado_humano": "aceptada|rechazada", "categoria_correcta": "..."}
        """
        prediccion = self.get_object()
        resultado = request.data.get("resultado_humano")
        if resultado not in ("aceptada", "rechazada"):
            return Response(
                {"detail": "resultado_humano debe ser 'aceptada' o 'rechazada'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        prediccion.resultado_humano = resultado
        cat = request.data.get("categoria_correcta", "")
        if cat:
            prediccion.categoria_correcta = cat
        prediccion.save(update_fields=["resultado_humano", "categoria_correcta"])
        return Response(PrediccionAgenteSerializer(prediccion).data)


class EjecucionAgenteViewSet(NulSafeFilterMixin, viewsets.ReadOnlyModelViewSet):
    """
    Consulta de solo lectura para ejecuciones asíncronas de agentes IA (Plan 05 P2-2).

    GET /api/agentes/ejecuciones/       — listar (filtros ?agente=, ?estado=, ?search=, ?ordering=)
    GET /api/agentes/ejecuciones/{id}/  — detalle de ejecución, estado y resultado
    """

    queryset = EjecucionAgente.objects.all()
    serializer_class = EjecucionAgenteSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PageNumberPagination
    lookup_value_regex = r"[0-9a-fA-F-]{36}"
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["agente", "estado", "celery_task_id"]
    ordering_fields = ["fecha_creacion", "fecha_fin", "estado", "agente"]
    ordering = ["-fecha_creacion"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return EjecucionAgente.objects.none()
        # R-CODE-1: estricto por empresas visibles del usuario
        empresas = get_empresas_visible(self.request.user)
        qs = EjecucionAgente.objects.select_related("id_empresa", "iniciado_por").filter(
            id_empresa__in=empresas,
        )
        for param_name, field_name in (("agente", "agente"), ("estado", "estado")):
            val = self.request.query_params.get(param_name)
            if val:
                if "\x00" in val:
                    raise ValidationError({param_name: "Parámetro de consulta inválido."})
                qs = qs.filter(**{field_name: val.strip()})
        return qs

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        if lookup_url_kwarg in self.kwargs:
            validar_uuid_param(self.kwargs[lookup_url_kwarg], self.lookup_field)
        return super().get_object()


_FECHA_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_CONSUMO_LLM_QUERY_PARAMS = [
    _EMPRESA_ID_QUERY_PARAM,
    openapi.Parameter(
        "modelo",
        openapi.IN_QUERY,
        description="Filtrar por identificador exacto del modelo LLM.",
        type=openapi.TYPE_STRING,
        required=False,
    ),
    openapi.Parameter(
        "uso",
        openapi.IN_QUERY,
        description="Filtrar por tipo de uso (agente, chat, analisis).",
        type=openapi.TYPE_STRING,
        required=False,
    ),
    openapi.Parameter(
        "fecha_desde",
        openapi.IN_QUERY,
        description="Fecha inicial inclusive (YYYY-MM-DD).",
        type=openapi.TYPE_STRING,
        format=openapi.FORMAT_DATE,
        required=False,
    ),
    openapi.Parameter(
        "fecha_hasta",
        openapi.IN_QUERY,
        description="Fecha final inclusive (YYYY-MM-DD).",
        type=openapi.TYPE_STRING,
        format=openapi.FORMAT_DATE,
        required=False,
    ),
]


def _parse_fecha_query(raw: str | None, campo: str) -> date | None:
    if raw is None:
        return None
    if "\x00" in raw:
        raise ValidationError({campo: "Parámetro de consulta inválido."})
    limpio = raw.strip()
    if not limpio:
        return None
    if not _FECHA_ISO_RE.match(limpio):
        raise ValidationError({campo: f"Formato de fecha inválido para '{campo}'. Use YYYY-MM-DD."})
    try:
        return date.fromisoformat(limpio)
    except ValueError as exc:
        raise ValidationError({campo: f"Fecha inválida para '{campo}'."}) from exc


class ConsumoLLMViewSet(NulSafeFilterMixin, viewsets.ReadOnlyModelViewSet):
    """
    Consulta de solo lectura del consumo de tokens y costos LLM por tenant (Plan 05 P2-3).

    GET /api/agentes/consumo-llm/         — listado histórico paginado
    GET /api/agentes/consumo-llm/{id}/    — detalle de evento
    GET /api/agentes/consumo-llm/resumen/ — resumen agregado (totales + por_modelo + por_uso)
    """

    queryset = ConsumoLLM.objects.all()
    serializer_class = ConsumoLLMSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PageNumberPagination
    lookup_value_regex = r"[0-9a-fA-F-]{36}"
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["modelo", "uso", "proveedor"]
    ordering_fields = [
        "creado_en",
        "costo_estimado_usd",
        "tokens_entrada",
        "tokens_salida",
        "latencia_ms",
        "modelo",
        "uso",
    ]
    ordering = ["-creado_en"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ConsumoLLM.objects.none()
        # R-CODE-1: estricto a empresas visibles; nunca expone filas globales (id_empresa=None).
        empresas = get_empresas_visible(self.request.user)
        qs = ConsumoLLM.objects.select_related("id_empresa").filter(
            id_empresa__isnull=False,
            id_empresa__in=empresas,
        )

        empresa_raw = self.request.query_params.get("empresa_id")
        if empresa_raw is not None:
            if "\x00" in empresa_raw:
                raise ValidationError({"empresa_id": "Parámetro de consulta inválido."})
            if empresa_raw.strip():
                empresa_uuid = validar_uuid_param(empresa_raw, "empresa_id")
                if not empresas.filter(pk=empresa_uuid).exists():
                    raise PermissionDenied("No tienes permiso para operar sobre esa empresa.")
                qs = qs.filter(id_empresa_id=empresa_uuid)

        for param_name, field_name in (("modelo", "modelo"), ("uso", "uso")):
            val = self.request.query_params.get(param_name)
            if val is not None:
                if "\x00" in val:
                    raise ValidationError({param_name: "Parámetro de consulta inválido."})
                limpio = val.strip()
                if limpio:
                    qs = qs.filter(**{field_name: limpio})

        fecha_desde = _parse_fecha_query(self.request.query_params.get("fecha_desde"), "fecha_desde")
        fecha_hasta = _parse_fecha_query(self.request.query_params.get("fecha_hasta"), "fecha_hasta")
        if fecha_desde is not None and fecha_hasta is not None and fecha_desde > fecha_hasta:
            raise ValidationError({"fecha_desde": "'fecha_desde' no puede ser posterior a 'fecha_hasta'."})
        if fecha_desde is not None:
            qs = qs.filter(creado_en__date__gte=fecha_desde)
        if fecha_hasta is not None:
            qs = qs.filter(creado_en__date__lte=fecha_hasta)

        return qs

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        if lookup_url_kwarg in self.kwargs:
            validar_uuid_param(self.kwargs[lookup_url_kwarg], self.lookup_field)
        return super().get_object()

    @swagger_auto_schema(manual_parameters=_CONSUMO_LLM_QUERY_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @swagger_auto_schema(
        manual_parameters=_CONSUMO_LLM_QUERY_PARAMS,
        responses={200: ConsumoLLMResumenSerializer},
    )
    @action(detail=False, methods=["get"], url_path="resumen")
    def resumen(self, request):
        """
        GET /api/agentes/consumo-llm/resumen/

        Retorna totales agregados (llamadas, tokens in/out, costo_total_usd,
        latencia_promedio_ms) y desglose ``por_modelo`` y ``por_uso``.
        """
        qs = self.filter_queryset(self.get_queryset())
        resumen_data = calcular_resumen_consumo_llm(qs)
        serializer = ConsumoLLMResumenSerializer(resumen_data)
        return Response(serializer.data)


class AgentesOperativosViewSet(viewsets.ViewSet):
    """Catálogo y ejecución síncrona/determinista + LLM de los 5 Agentes IA Operativos (Plan 09 Fase 8.2)."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [*viewsets.ViewSet.throttle_classes, EscrituraRateThrottle]

    @swagger_auto_schema(manual_parameters=[_EMPRESA_ID_QUERY_PARAM])
    @action(detail=False, methods=["get"], url_path="catalogo")
    def catalogo(self, request):
        raw_emp = request.query_params.get("empresa_id")
        emp_param = str(validar_uuid_param(raw_emp, "empresa_id")) if raw_emp is not None else None
        empresa, err = _resolver_empresa(request, emp_param)
        if err is not None:
            return err
        return Response({"empresa_id": str(empresa.pk), "agentes": list(AGENTES_OPERATIVOS.values())})

    @swagger_auto_schema(
        request_body=EjecutarAgenteOperativoInputSerializer,
        responses={200: openapi.Response("Resultado de ejecución del agente IA operativo.")},
    )
    @idempotent(scope="agentes:ejecutar_operativo")
    @action(detail=False, methods=["post"], url_path="ejecutar")
    def ejecutar(self, request):
        ser = EjecutarAgenteOperativoInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        raw_emp = vd.get("id_empresa")
        empresa, err = _resolver_empresa(request, str(raw_emp) if raw_emp else None)
        if err is not None:
            return err
        res = ejecutar_agente_operativo(
            empresa,
            vd["agente"],
            usuario=request.user,
            persistir=vd["persistir"],
            limite=vd["limite"],
        )
        return Response(res, status=status.HTTP_200_OK)
