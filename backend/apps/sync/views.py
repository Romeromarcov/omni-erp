"""Endpoint de pull de deltas para clientes offline — CTF-008 Nivel 2 (paso 1).

`GET /api/sync/pull/?entity=<tipo>&desde=<ISO8601>&limite=<n>`

Read-only: devuelve los registros del catálogo de la empresa creados o
modificados desde `desde` (cursor por `fecha_actualizacion`). No hay escritura
todavía (el push idempotente + outbox son incrementos posteriores), así que este
paso no tiene riesgo de pérdida de datos.

Reglas: autenticado, aislado por empresa (R-CODE-1), Decimal serializado como
string para no perder precisión (R-CODE-4).
"""
from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from django.apps import apps as django_apps
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.viewsets import get_empresas_visible

from .registry import SYNC_ENTITIES

LIMITE_DEFECTO = 500
LIMITE_MAXIMO = 1000


def _jsonificar(valor):
    """Convierte valores del ORM a tipos JSON-safe preservando precisión."""
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, uuid.UUID):
        return str(valor)
    if isinstance(valor, (datetime.datetime, datetime.date)):
        return valor.isoformat()
    return valor


class SyncPullView(APIView):
    """Pull incremental de una entidad de catálogo para la réplica local."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        nombre = request.query_params.get("entity")
        entidad = SYNC_ENTITIES.get(nombre)
        if entidad is None:
            return Response(
                {"error": f"Entidad no sincronizable: {nombre!r}.",
                 "entidades": sorted(SYNC_ENTITIES)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        desde = None
        desde_raw = request.query_params.get("desde")
        if desde_raw:
            desde = parse_datetime(desde_raw)
            if desde is None:
                return Response(
                    {"error": "El parámetro 'desde' no es un timestamp ISO 8601 válido."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            limite = int(request.query_params.get("limite", LIMITE_DEFECTO))
        except (TypeError, ValueError):
            return Response(
                {"error": "El parámetro 'limite' debe ser un entero."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        limite = max(1, min(limite, LIMITE_MAXIMO))

        empresas = get_empresas_visible(request.user)
        if not empresas.exists():
            return Response(
                {"error": "El usuario no tiene empresa asignada."},
                status=status.HTTP_403_FORBIDDEN,
            )

        modelo = django_apps.get_model(entidad.model_label)
        qs = modelo.objects.filter(**{f"{entidad.empresa_field}__in": empresas})
        if desde is not None:
            # `__gte` (inclusivo) es idempotente: reenviar el mismo cursor puede
            # repetir el registro del borde, que el cliente reaplica por PK.
            qs = qs.filter(**{f"{entidad.delta_field}__gte": desde})

        order = tuple(entidad.pk_field if c == "pk" else c for c in entidad.order_by)
        qs = qs.order_by(*order)

        # Pedimos uno extra para saber si hay más páginas.
        filas = list(qs.values(*entidad.fields)[: limite + 1])
        hay_mas = len(filas) > limite
        filas = filas[:limite]
        resultados = [{k: _jsonificar(v) for k, v in fila.items()} for fila in filas]

        return Response({
            "entity": nombre,
            # Cursor autoritativo para el próximo pull (reloj del servidor).
            "server_time": timezone.now().isoformat(),
            "count": len(resultados),
            "has_more": hay_mas,
            "results": resultados,
        })
