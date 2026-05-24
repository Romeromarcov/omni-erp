"""
API endpoints para generación de libros fiscales SENIAT.

TXT:
  GET /api/fiscal/libro-ventas/?empresa=<uuid>&desde=YYYY-MM-DD&hasta=YYYY-MM-DD
  GET /api/fiscal/libro-ventas/?empresa=<uuid>&periodo=YYYY-MM
  GET /api/fiscal/libro-compras/?empresa=<uuid>&desde=YYYY-MM-DD&hasta=YYYY-MM-DD
  GET /api/fiscal/libro-compras/?empresa=<uuid>&periodo=YYYY-MM

PDF:
  GET /api/fiscal/libro-ventas-pdf/?empresa=<uuid>&periodo=YYYY-MM
  GET /api/fiscal/libro-compras-pdf/?empresa=<uuid>&periodo=YYYY-MM

Gestión de períodos:
  GET  /api/fiscal/periodos-fiscales/?empresa=<uuid>
  POST /api/fiscal/periodos-fiscales/<año>/<mes>/cerrar/?empresa=<uuid>
"""

from datetime import date

from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.viewsets import get_empresas_visible

from .libros_seniat import (
    _periodo_a_rango,
    generar_libro_compras_pdf,
    generar_libro_compras_txt,
    generar_libro_ventas_pdf,
    generar_libro_ventas_txt,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _resolver_empresa(request):
    """
    Devuelve (empresa, error_response).
    Valida que el usuario tenga acceso a la empresa solicitada.
    """
    empresa_id = request.query_params.get("empresa")
    if not empresa_id:
        return None, Response(
            {"error": "Parámetro 'empresa' requerido."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    empresas_visibles = get_empresas_visible(request.user)
    try:
        empresa = empresas_visibles.get(pk=empresa_id)
    except Exception:
        return None, Response(
            {"error": "Empresa no encontrada o sin acceso."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return empresa, None


def _resolver_rango(request):
    """
    Resuelve (fecha_inicio, fecha_fin) desde ?periodo=YYYY-MM o ?desde/hasta.
    Devuelve (inicio, fin, error_response).
    """
    periodo = request.query_params.get("periodo")
    if periodo:
        try:
            inicio, fin = _periodo_a_rango(periodo)
            return inicio, fin, None
        except ValueError as exc:
            return None, None, Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    desde_str = request.query_params.get("desde")
    hasta_str = request.query_params.get("hasta")
    if not desde_str or not hasta_str:
        return None, None, Response(
            {"error": "Requerido: 'periodo' (YYYY-MM) ó 'desde'+'hasta' (YYYY-MM-DD)."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        return date.fromisoformat(desde_str), date.fromisoformat(hasta_str), None
    except ValueError:
        return None, None, Response(
            {"error": "Formato de fecha inválido. Use YYYY-MM-DD."},
            status=status.HTTP_400_BAD_REQUEST,
        )


# ── TXT views ──────────────────────────────────────────────────────────────────

class LibroVentasView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        empresa, err = _resolver_empresa(request)
        if err:
            return err
        inicio, fin, err = _resolver_rango(request)
        if err:
            return err

        contenido = generar_libro_ventas_txt(empresa, inicio, fin)
        nombre = f"libro_ventas_{inicio}_{fin}.txt"
        resp = HttpResponse(contenido, content_type="text/plain; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{nombre}"'
        return resp


class LibroComprasView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        empresa, err = _resolver_empresa(request)
        if err:
            return err
        inicio, fin, err = _resolver_rango(request)
        if err:
            return err

        contenido = generar_libro_compras_txt(empresa, inicio, fin)
        nombre = f"libro_compras_{inicio}_{fin}.txt"
        resp = HttpResponse(contenido, content_type="text/plain; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{nombre}"'
        return resp


# ── PDF views ──────────────────────────────────────────────────────────────────

class LibroVentasPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        empresa, err = _resolver_empresa(request)
        if err:
            return err
        inicio, fin, err = _resolver_rango(request)
        if err:
            return err

        pdf_bytes = generar_libro_ventas_pdf(empresa, inicio, fin)
        nombre = f"libro_ventas_{inicio}_{fin}.pdf"
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{nombre}"'
        return resp


class LibroComprasPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        empresa, err = _resolver_empresa(request)
        if err:
            return err
        inicio, fin, err = _resolver_rango(request)
        if err:
            return err

        pdf_bytes = generar_libro_compras_pdf(empresa, inicio, fin)
        nombre = f"libro_compras_{inicio}_{fin}.pdf"
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{nombre}"'
        return resp


# ── Períodos fiscales ──────────────────────────────────────────────────────────

class PeriodoFiscalView(APIView):
    """
    GET  /api/fiscal/periodos-fiscales/?empresa=<uuid>
         Lista los períodos registrados de la empresa.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        empresa, err = _resolver_empresa(request)
        if err:
            return err

        from .models import PeriodoFiscal

        periodos = PeriodoFiscal.objects.filter(id_empresa=empresa).order_by("-año", "-mes")
        data = [
            {
                "año": p.año,
                "mes": p.mes,
                "cerrado": p.cerrado,
                "fecha_cierre": p.fecha_cierre,
            }
            for p in periodos
        ]
        return Response(data)


class CerrarPeriodoFiscalView(APIView):
    """
    POST /api/fiscal/periodos-fiscales/<año>/<mes>/cerrar/?empresa=<uuid>

    Marca el período como cerrado; idempotente si ya estaba cerrado.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, año: int, mes: int):
        empresa, err = _resolver_empresa(request)
        if err:
            return err

        from django.utils import timezone

        from .models import PeriodoFiscal

        periodo, _ = PeriodoFiscal.objects.get_or_create(
            id_empresa=empresa, año=año, mes=mes
        )
        if periodo.cerrado:
            return Response(
                {"detalle": "El período ya estaba cerrado.", "cerrado": True},
                status=status.HTTP_200_OK,
            )

        periodo.cerrado = True
        periodo.fecha_cierre = timezone.now()
        periodo.cerrado_por = request.user
        periodo.save(update_fields=["cerrado", "fecha_cierre", "cerrado_por"])

        return Response(
            {
                "detalle": f"Período {año}/{mes:02d} cerrado exitosamente.",
                "cerrado": True,
                "fecha_cierre": periodo.fecha_cierre,
            },
            status=status.HTTP_200_OK,
        )
