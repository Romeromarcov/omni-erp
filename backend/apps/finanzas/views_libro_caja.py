"""
Endpoint de solo lectura del libro maestro de caja — Capa B §6.8.

GET /api/finanzas/libro-maestro-caja/?empresa=<uuid>&desde=YYYY-MM-DD&hasta=YYYY-MM-DD
GET /api/finanzas/libro-maestro-caja/?empresa=<uuid>&periodo=YYYY-MM

Filtros opcionales:
  - moneda=USD            — solo filas de esa moneda (código ISO)
  - tipo=VIRTUAL|FISICA   — solo cajas virtuales o físicas
  - incluir_inactivas=true — incluye cajas desactivadas

Contrato: ``empresa`` es obligatorio y debe ser visible para el usuario
(R-CODE-1, mismo patrón que los libros SENIAT); montos como string (R-CODE-4).
"""

from datetime import date

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.viewsets import get_empresas_visible

from .services_libro_caja import generar_libro_maestro_caja


def _resolver_empresa(request):
    """Devuelve (empresa, error_response) validando acceso del usuario."""
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


def _periodo_a_rango(periodo: str) -> tuple[date, date]:
    """Convierte 'YYYY-MM' en (date_inicio, date_fin) del mes completo."""
    import calendar

    try:
        año_str, mes_str = periodo.split("-")
        año, mes = int(año_str), int(mes_str)
        ultimo_dia = calendar.monthrange(año, mes)[1]
        return date(año, mes, 1), date(año, mes, ultimo_dia)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Formato de período inválido: '{periodo}'. Use YYYY-MM.") from exc


def _resolver_rango(request):
    """Resuelve (desde, hasta, error_response) de ?periodo=YYYY-MM o ?desde/?hasta."""
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


def _money(valor):
    """R-CODE-4: el dinero viaja como string, nunca float."""
    return str(valor)


class LibroMaestroCajaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        empresa, err = _resolver_empresa(request)
        if err:
            return err
        desde, hasta, err = _resolver_rango(request)
        if err:
            return err

        incluir_inactivas = request.query_params.get(
            "incluir_inactivas", "false"
        ).lower() in ("true", "1", "yes")
        moneda = request.query_params.get("moneda") or None
        tipo = request.query_params.get("tipo") or None

        try:
            libro = generar_libro_maestro_caja(
                empresa,
                desde,
                hasta,
                incluir_inactivas=incluir_inactivas,
                moneda_codigo=moneda,
                tipo=tipo,
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "empresa": libro["empresa"],
                "fecha_desde": str(libro["fecha_desde"]),
                "fecha_hasta": str(libro["fecha_hasta"]),
                "cajas": [
                    {
                        **fila,
                        "saldo_inicial": _money(fila["saldo_inicial"]),
                        "entradas": _money(fila["entradas"]),
                        "salidas": _money(fila["salidas"]),
                        "saldo_final": _money(fila["saldo_final"]),
                    }
                    for fila in libro["cajas"]
                ],
                "totales_por_moneda": [
                    {
                        **total,
                        "saldo_inicial": _money(total["saldo_inicial"]),
                        "entradas": _money(total["entradas"]),
                        "salidas": _money(total["salidas"]),
                        "saldo_final": _money(total["saldo_final"]),
                    }
                    for total in libro["totales_por_moneda"]
                ],
            }
        )
