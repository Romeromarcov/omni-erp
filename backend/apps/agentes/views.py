"""
Vistas del módulo de Agentes IA (M9).

Expone:
  - PrediccionAgenteViewSet: CRUD de predicciones con aislamiento multi-tenant.
  - Acciones custom:
      · analizar-cobranza      — CobranzaEstrategaAgent (sugerencias, read-only)
      · analizar-reorden        — ReordenSugeridorAgent (sugerencias, read-only)
      · analizar-personalizacion — PersonalizacionCapa2Agent
      · clasificar-gasto        — ClasificadorGastos en MODO PRODUCCIÓN:
                                    predice la categoría de un Gasto y,
                                    si aplicar=true, actualiza id_categoria_gasto.
      · metricas-clasificador   — Métricas de calidad del ClasificadorGastos.

Modo de operación:
  - Cobranza / Reorden / Personalización ya devuelven resultados accionables.
  - ClasificadorGastos emite una predicción (PrediccionAgente) y acepta
    aplicar=true para escribir en el modelo Gasto (modo producción activado).
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


# ── Helpers para sugerencias activas ──────────────────────────────────────────

_TITULOS_AGENTE = {
    "cobranza_estratega": "Cobranza",
    "reorden_sugeridor": "Reorden de Stock",
    "clasificador_gastos": "Clasificación de Gasto",
    "personalizacion_capa2": "Personalización",
}


def _titulo_sugerencia(prediccion) -> str:
    """Genera un título legible para la tarjeta de sugerencia."""
    agente_label = _TITULOS_AGENTE.get(prediccion.agente, prediccion.agente)
    if prediccion.agente == "cobranza_estratega":
        cliente = prediccion.input_metadata.get("cliente_nombre", "")
        monto = prediccion.input_monto
        if cliente:
            return f"Contactar a {cliente}" + (f" — ${monto}" if monto else "")
        return f"Acción de cobranza requerida"
    if prediccion.agente == "reorden_sugeridor":
        producto = prediccion.input_metadata.get("nombre_producto", prediccion.input_texto or "")
        if producto:
            return f"Reponer: {producto[:40]}"
        return "Reorden de inventario sugerido"
    if prediccion.agente == "clasificador_gastos":
        return f"Clasificar gasto: {prediccion.categoria_predicha}"
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
    return ""


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

    @action(detail=False, methods=["post"], url_path="clasificar-gasto")
    def clasificar_gasto(self, request):
        """
        POST /agentes/predicciones/clasificar-gasto/

        Modo PRODUCCIÓN del ClasificadorGastos.  Predice la categoría de un Gasto
        y, opcionalmente, la aplica escribiendo en Gasto.id_categoria_gasto.

        Body:
          {
            "gasto_id": "<uuid>",
            "aplicar": false         # true = actualizar el gasto (producción)
          }

        Flujo:
          1. Verifica que el gasto pertenezca a la empresa del usuario (R-CODE-1).
          2. Ejecuta ClasificadorGastos.clasificar() con descripción + monto.
          3. Persiste PrediccionAgente (resultado_humano="pendiente").
          4. Si aplicar=true:
             a. Busca CategoriaGasto cuyo nombre_categoria coincida
                (case-insensitive) con la predicción.
             b. Si la encuentra, actualiza Gasto.id_categoria_gasto y marca
                la PrediccionAgente como "aceptada".
             c. Si no la encuentra, crea la categoría automáticamente.

        Respuesta:
          {
            "prediccion_id": "...",
            "categoria": "alimentacion",
            "confianza": 0.92,
            "razonamiento": "...",
            "aplicado": true|false,
            "categoria_id": "<uuid>|null"
          }
        """
        from apps.gastos.models import CategoriaGasto, Gasto
        from .clasificador import ClasificadorGastos

        empresa = _empresa_o_error(request)
        if not empresa:
            return Response({"detail": "Sin empresa asignada."}, status=status.HTTP_403_FORBIDDEN)

        gasto_id = request.data.get("gasto_id")
        aplicar = bool(request.data.get("aplicar", False))

        if not gasto_id:
            return Response({"detail": "Se requiere gasto_id."}, status=status.HTTP_400_BAD_REQUEST)

        # R-CODE-1: el gasto debe pertenecer a una empresa visible del usuario
        try:
            gasto = Gasto.objects.get(pk=gasto_id, id_empresa=empresa)
        except Gasto.DoesNotExist:
            return Response({"detail": "Gasto no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        # ── Clasificar ────────────────────────────────────────────────────────
        agente = ClasificadorGastos(empresa=empresa)
        try:
            resultado = agente.clasificar(
                descripcion=gasto.descripcion,
                monto=gasto.monto,
                persistir=True,
            )
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Recuperar la predicción que acabamos de persistir (la más reciente)
        prediccion = (
            PrediccionAgente.objects.filter(
                id_empresa=empresa,
                agente=ClasificadorGastos.AGENTE_ID,
                input_texto=gasto.descripcion,
            )
            .order_by("-fecha_prediccion")
            .first()
        )

        aplicado = False
        categoria_id = None

        # ── Aplicar si se solicitó ────────────────────────────────────────────
        if aplicar and resultado.confianza >= 0.5:
            # Buscar o crear la CategoriaGasto (iexact lookup manual)
            categoria_nombre = resultado.categoria.replace("_", " ").title()
            categoria_obj = (
                CategoriaGasto.objects.filter(
                    id_empresa=empresa,
                    nombre_categoria__iexact=resultado.categoria,
                ).first()
                or CategoriaGasto.objects.create(
                    id_empresa=empresa,
                    nombre_categoria=categoria_nombre,
                    activo=True,
                )
            )
            gasto.id_categoria_gasto = categoria_obj
            gasto.save(update_fields=["id_categoria_gasto"])
            aplicado = True
            categoria_id = str(categoria_obj.pk)

            # Actualizar evaluación humana de la predicción
            if prediccion:
                prediccion.resultado_humano = "aceptada"
                prediccion.categoria_correcta = resultado.categoria
                prediccion.save(update_fields=["resultado_humano", "categoria_correcta"])

        return Response(
            {
                "prediccion_id": str(prediccion.pk) if prediccion else None,
                "categoria": resultado.categoria,
                "confianza": resultado.confianza,
                "razonamiento": resultado.razonamiento,
                "alternativas": resultado.alternativas,
                "modelo_llm": resultado.modelo_llm,
                "aplicado": aplicado,
                "categoria_id": categoria_id,
            }
        )

    @action(detail=False, methods=["get"], url_path="metricas-clasificador")
    def metricas_clasificador(self, request):
        """
        GET /agentes/predicciones/metricas-clasificador/

        Devuelve métricas de calidad del ClasificadorGastos para la empresa.

        Respuesta:
          {
            "total": 150,
            "evaluadas": 80,
            "precision": 0.923,
            "confianza_promedio": 0.847,
            "latencia_promedio_ms": 12.4
          }
        """
        from .clasificador import ClasificadorGastos

        empresa = _empresa_o_error(request)
        if not empresa:
            return Response({"detail": "Sin empresa asignada."}, status=status.HTTP_403_FORBIDDEN)

        metricas = ClasificadorGastos.metricas_empresa(str(empresa.pk))
        return Response(metricas)

    @action(detail=False, methods=["get"], url_path="sugerencias-activas")
    def sugerencias_activas(self, request):
        """
        GET /agentes/predicciones/sugerencias-activas/

        Retorna las predicciones pendientes de revisión humana para la empresa del usuario.
        Por defecto las últimas 10, ordenadas por confianza DESC.

        Query params:
          ?limite=N   — máximo de resultados (default 10, max 50)
          ?agente=    — filtrar por nombre de agente
        """
        empresa = _empresa_o_error(request)
        if not empresa:
            return Response({"detail": "Sin empresa asignada."}, status=status.HTTP_403_FORBIDDEN)

        limite = min(int(request.query_params.get("limite", 10)), 50)
        agente_filtro = request.query_params.get("agente")

        qs = PrediccionAgente.objects.filter(
            id_empresa=empresa,
            resultado_humano="pendiente",
        )
        if agente_filtro:
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
