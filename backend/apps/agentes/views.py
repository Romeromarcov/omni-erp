"""
Vistas del módulo de Agentes IA (M9).

Expone:
  - PrediccionAgenteViewSet: CRUD de predicciones con aislamiento multi-tenant.
  - Acciones custom para ejecutar los agentes: cobranza, reorden, personalizacion.

Los agentes operan en shadow mode: observan datos pero NO modifican registros de negocio.
"""
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import PrediccionAgente
from .serializers import PrediccionAgenteSerializer


def _empresa_o_error(request):
    """Devuelve la primera empresa visible del usuario, o None si no tiene."""
    empresas = get_empresas_visible(request.user)
    return empresas.first()


class PrediccionAgenteViewSet(BaseModelViewSet):
    """
    CRUD de predicciones de agentes IA.

    GET  /agentes/predicciones/          — listar (filtrable por ?agente=)
    GET  /agentes/predicciones/{pk}/     — detalle
    PATCH /agentes/predicciones/{pk}/   — actualizar resultado_humano / categoria_correcta
    DELETE /agentes/predicciones/{pk}/  — eliminar

    Acciones custom:
    POST /agentes/predicciones/analizar-cobranza/     — ejecutar CobranzaEstrategaAgent
    POST /agentes/predicciones/analizar-reorden/      — ejecutar ReordenSugeridorAgent
    POST /agentes/predicciones/analizar-personalizacion/ — ejecutar PersonalizacionCapa2Agent
    """

    queryset = PrediccionAgente.objects.all()
    serializer_class = PrediccionAgenteSerializer
    search_fields = ["agente", "categoria_predicha", "input_texto"]
    ordering_fields = ["fecha_prediccion", "confianza", "agente"]
    ordering = ["-fecha_prediccion"]

    def get_queryset(self):
        # R-CODE-1
        empresas = get_empresas_visible(self.request.user)
        qs = PrediccionAgente.objects.filter(id_empresa__in=empresas)
        # Filtro opcional por agente
        agente = self.request.query_params.get("agente")
        if agente:
            qs = qs.filter(agente=agente)
        return qs

    @action(detail=False, methods=["post"], url_path="analizar-cobranza")
    def analizar_cobranza(self, request):
        """
        POST /agentes/predicciones/analizar-cobranza/

        Ejecuta el CobranzaEstrategaAgent para la empresa del usuario.
        Body (opcional): {"persistir": true}

        Retorna lista de sugerencias de cobranza para CxC vencidas.
        """
        from .cobranza import CobranzaEstrategaAgent

        empresa = _empresa_o_error(request)
        if not empresa:
            return Response({"detail": "Sin empresa asignada."}, status=status.HTTP_403_FORBIDDEN)

        persistir = request.data.get("persistir", False)
        agente = CobranzaEstrategaAgent(empresa=empresa)
        try:
            sugerencias = agente.analizar(persistir=persistir)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        data = [
            {
                "cxc_id": str(s.cxc_id),
                "cliente_nombre": s.cliente_nombre,
                "monto": str(s.monto),
                "dias_vencida": s.dias_vencida,
                "prioridad": s.prioridad,
                "canal_sugerido": s.canal_sugerido,
                "mensaje": s.mensaje,
                "motivo": s.motivo,
            }
            for s in sugerencias
        ]
        return Response({"sugerencias": data, "total": len(data)})

    @action(detail=False, methods=["post"], url_path="analizar-reorden")
    def analizar_reorden(self, request):
        """
        POST /agentes/predicciones/analizar-reorden/

        Ejecuta el ReordenSugeridorAgent para la empresa del usuario.
        Body (opcional): {"solo_alertas": true, "persistir": false}

        Retorna lista de sugerencias de reorden de inventario.
        """
        from .reorden import ReordenSugeridorAgent

        empresa = _empresa_o_error(request)
        if not empresa:
            return Response({"detail": "Sin empresa asignada."}, status=status.HTTP_403_FORBIDDEN)

        solo_alertas = request.data.get("solo_alertas", True)
        persistir = request.data.get("persistir", False)
        agente = ReordenSugeridorAgent(empresa=empresa)
        try:
            sugerencias = agente.analizar(solo_alertas=solo_alertas, persistir=persistir)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        data = [
            {
                "producto_id": str(s.producto_id),
                "nombre_producto": s.nombre_producto,
                "stock_disponible": s.stock_disponible,
                "cantidad_minima": s.cantidad_minima,
                "estado": s.estado,
                "cantidad_sugerida": s.cantidad_sugerida,
                "motivo": s.motivo,
                "prioridad": s.prioridad,
            }
            for s in sugerencias
        ]
        return Response({"sugerencias": data, "total": len(data)})

    @action(detail=False, methods=["post"], url_path="analizar-personalizacion")
    def analizar_personalizacion(self, request):
        """
        POST /agentes/predicciones/analizar-personalizacion/

        Ejecuta el PersonalizacionCapa2Agent para la empresa del usuario.

        Retorna recomendaciones de flujo de documentos, listas de precios y crédito a clientes.
        """
        from .personalizacion_agente import PersonalizacionCapa2Agent

        empresa = _empresa_o_error(request)
        if not empresa:
            return Response({"detail": "Sin empresa asignada."}, status=status.HTTP_403_FORBIDDEN)

        agente = PersonalizacionCapa2Agent(empresa=empresa)
        try:
            resultado = agente.analizar()
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(
            {
                "flujo_documentos": resultado.flujo_documentos,
                "listas_precios": resultado.listas_precios,
                "credito_clientes": resultado.credito_clientes,
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
