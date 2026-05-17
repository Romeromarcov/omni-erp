"""
API endpoints para generación de libros SENIAT.

GET /api/fiscal/libro-ventas/?empresa=<uuid>&desde=YYYY-MM-DD&hasta=YYYY-MM-DD
GET /api/fiscal/libro-compras/?empresa=<uuid>&desde=YYYY-MM-DD&hasta=YYYY-MM-DD
"""

from datetime import date

from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.models import Empresa

from .libros_seniat import generar_libro_compras_txt, generar_libro_ventas_txt


class LibroVentasView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        empresa_id = request.query_params.get("empresa")
        desde_str = request.query_params.get("desde")
        hasta_str = request.query_params.get("hasta")

        if not empresa_id or not desde_str or not hasta_str:
            from rest_framework.response import Response
            from rest_framework import status
            return Response(
                {"error": "Parámetros requeridos: empresa, desde, hasta"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            empresa = Empresa.objects.get(pk=empresa_id)
        except Empresa.DoesNotExist:
            from rest_framework.response import Response
            from rest_framework import status
            return Response({"error": "Empresa no encontrada"}, status=status.HTTP_404_NOT_FOUND)

        try:
            fecha_inicio = date.fromisoformat(desde_str)
            fecha_fin = date.fromisoformat(hasta_str)
        except ValueError:
            from rest_framework.response import Response
            from rest_framework import status
            return Response(
                {"error": "Formato de fecha inválido. Use YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        contenido = generar_libro_ventas_txt(empresa, fecha_inicio, fecha_fin)
        nombre_archivo = f"libro_ventas_{desde_str}_{hasta_str}.txt"

        response = HttpResponse(contenido, content_type="text/plain; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{nombre_archivo}"'
        return response


class LibroComprasView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        empresa_id = request.query_params.get("empresa")
        desde_str = request.query_params.get("desde")
        hasta_str = request.query_params.get("hasta")

        if not empresa_id or not desde_str or not hasta_str:
            from rest_framework.response import Response
            from rest_framework import status
            return Response(
                {"error": "Parámetros requeridos: empresa, desde, hasta"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            empresa = Empresa.objects.get(pk=empresa_id)
        except Empresa.DoesNotExist:
            from rest_framework.response import Response
            from rest_framework import status
            return Response({"error": "Empresa no encontrada"}, status=status.HTTP_404_NOT_FOUND)

        try:
            fecha_inicio = date.fromisoformat(desde_str)
            fecha_fin = date.fromisoformat(hasta_str)
        except ValueError:
            from rest_framework.response import Response
            from rest_framework import status
            return Response(
                {"error": "Formato de fecha inválido. Use YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        contenido = generar_libro_compras_txt(empresa, fecha_inicio, fecha_fin)
        nombre_archivo = f"libro_compras_{desde_str}_{hasta_str}.txt"

        response = HttpResponse(contenido, content_type="text/plain; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{nombre_archivo}"'
        return response
