from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import Caja, ConciliacionBancaria, MovimientoBancario, MovimientoInternoFondo, OperacionCambioDivisa
from .serializers import (
    CajaSerializer,
    ConciliacionBancariaSerializer,
    MovimientoBancarioSerializer,
    MovimientoInternoFondoSerializer,
    OperacionCambioDivisaSerializer,
)


def _empresas(request):
    return get_empresas_visible(request.user)


class CajaViewSet(BaseModelViewSet):
    queryset = Caja.objects.all()
    serializer_class = CajaSerializer

    def get_queryset(self):
        # R-CODE-1 — Caja (finanzas) usa "empresa" como FK (no "id_empresa")
        return Caja.objects.filter(empresa__in=_empresas(self.request))


class MovimientoInternoFondoViewSet(BaseModelViewSet):
    queryset = MovimientoInternoFondo.objects.all()
    serializer_class = MovimientoInternoFondoSerializer

    def get_queryset(self):
        # R-CODE-1 — MovimientoInternoFondo no tiene id_empresa directo; llega via caja_origen→Caja
        return MovimientoInternoFondo.objects.filter(caja_origen__empresa__in=_empresas(self.request))

    def perform_create(self, serializer):
        serializer.save()


class OperacionCambioDivisaViewSet(BaseModelViewSet):
    queryset = OperacionCambioDivisa.objects.all()
    serializer_class = OperacionCambioDivisaSerializer

    def get_queryset(self):
        # R-CODE-1 — el campo FK a empresa es "empresa" (no "id_empresa")
        return OperacionCambioDivisa.objects.filter(empresa__in=_empresas(self.request))

    def create(self, request, *args, **kwargs):
        from apps.contabilidad.services import AsientoError

        try:
            return super().create(request, *args, **kwargs)
        except AsientoError as exc:
            # CTF-013 / R-CODE-11: contabilidad activa sin mapeo CAMBIO_DIVISA —
            # el @transaction.atomic del serializer ya revirtió el doble registro
            # al propagar la excepción; aquí solo se traduce a 422.
            return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    def perform_create(self, serializer):
        serializer.save()


class MovimientoBancarioViewSet(BaseModelViewSet):
    """
    CRUD de movimientos bancarios.

    GET  /tesoreria/movimientos-bancarios/                   — listar (filtros: ?empresa=, ?cuenta=, ?estado=)
    POST /tesoreria/movimientos-bancarios/                   — registrar manual
    POST /tesoreria/movimientos-bancarios/importar-csv/      — importar extracto CSV
    POST /tesoreria/movimientos-bancarios/conciliar-auto/    — conciliación automática
    """

    queryset = MovimientoBancario.objects.all()
    serializer_class = MovimientoBancarioSerializer

    def get_queryset(self):
        empresas = _empresas(self.request)
        qs = MovimientoBancario.objects.filter(id_empresa__in=empresas).select_related(
            "id_cuenta_bancaria", "id_empresa"
        )
        cuenta_id = self.request.query_params.get("cuenta")
        estado = self.request.query_params.get("estado")
        if cuenta_id:
            qs = qs.filter(id_cuenta_bancaria=cuenta_id)
        if estado:
            qs = qs.filter(estado=estado)
        return qs.order_by("-fecha_mov")

    def perform_create(self, serializer):
        from decimal import Decimal
        from .services import registrar_movimiento_bancario

        empresa = serializer.validated_data["id_empresa"]
        cuenta = serializer.validated_data["id_cuenta_bancaria"]
        # Validate tenant
        if empresa not in _empresas(self.request):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Sin acceso a esta empresa.")
        serializer.save()

    @action(detail=False, methods=["post"], url_path="importar-csv")
    def importar_csv(self, request):
        """
        POST /tesoreria/movimientos-bancarios/importar-csv/

        Body: multipart/form-data con campos:
          - cuenta_bancaria: UUID de CuentaBancariaEmpresa
          - archivo: el CSV
        CSV esperado (con cabecera): fecha,descripcion,tipo,monto,referencia
        """
        from apps.finanzas.models import CuentaBancariaEmpresa
        from .services import importar_extracto_csv, ConciliacionError

        empresa_id = request.data.get("empresa")
        cuenta_id = request.data.get("cuenta_bancaria")
        archivo = request.FILES.get("archivo")

        if not cuenta_id or not archivo:
            return Response(
                {"error": "Se requieren: cuenta_bancaria y archivo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        empresas = _empresas(request)
        empresa = empresas.filter(pk=empresa_id).first() if empresa_id else empresas.first()
        if not empresa:
            return Response({"error": "Sin empresa accesible."}, status=status.HTTP_403_FORBIDDEN)

        try:
            cuenta = CuentaBancariaEmpresa.objects.get(pk=cuenta_id, id_empresa=empresa)
        except CuentaBancariaEmpresa.DoesNotExist:
            return Response({"error": "Cuenta bancaria no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        resultado = importar_extracto_csv(empresa, cuenta, archivo)
        return Response(resultado, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="conciliar-auto")
    def conciliar_auto(self, request):
        """
        POST /tesoreria/movimientos-bancarios/conciliar-auto/
        Body: {"cuenta_bancaria": "<uuid>", "tolerancia_dias": 3}
        """
        from apps.finanzas.models import CuentaBancariaEmpresa
        from .services import conciliar_automatico

        cuenta_id = request.data.get("cuenta_bancaria")
        tolerancia = int(request.data.get("tolerancia_dias", 3))

        if not cuenta_id:
            return Response({"error": "Se requiere cuenta_bancaria."}, status=status.HTTP_400_BAD_REQUEST)

        empresas = _empresas(request)
        try:
            cuenta = CuentaBancariaEmpresa.objects.get(pk=cuenta_id, id_empresa__in=empresas)
        except CuentaBancariaEmpresa.DoesNotExist:
            return Response({"error": "Cuenta bancaria no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        empresa = cuenta.id_empresa
        resultado = conciliar_automatico(empresa, cuenta, tolerancia_dias=tolerancia)
        return Response(resultado, status=status.HTTP_200_OK)


class ConciliacionBancariaViewSet(BaseModelViewSet):
    """
    CRUD de sesiones de conciliación bancaria.

    GET  /tesoreria/conciliaciones-bancarias/         — listar
    POST /tesoreria/conciliaciones-bancarias/         — iniciar sesión
    POST /tesoreria/conciliaciones-bancarias/{pk}/cerrar/ — cerrar sesión
    """

    queryset = ConciliacionBancaria.objects.all()
    serializer_class = ConciliacionBancariaSerializer

    def get_queryset(self):
        return ConciliacionBancaria.objects.filter(
            id_empresa__in=_empresas(self.request)
        ).select_related("id_cuenta_bancaria", "id_empresa")

    def perform_create(self, serializer):
        from decimal import Decimal
        from .services import iniciar_conciliacion

        empresa = serializer.validated_data["id_empresa"]
        cuenta = serializer.validated_data["id_cuenta_bancaria"]
        saldo_banco = serializer.validated_data["saldo_banco"]
        saldo_libro = serializer.validated_data["saldo_libro"]
        periodo_inicio = serializer.validated_data["periodo_inicio"]
        periodo_fin = serializer.validated_data["periodo_fin"]

        conciliacion = iniciar_conciliacion(
            empresa=empresa,
            cuenta_bancaria=cuenta,
            periodo_inicio=periodo_inicio,
            periodo_fin=periodo_fin,
            saldo_banco=saldo_banco,
            saldo_libro=saldo_libro,
            usuario=self.request.user,
        )
        # Return created object via serializer (bypass normal save)
        serializer.instance = conciliacion

    @action(detail=True, methods=["post"], url_path="cerrar")
    def cerrar(self, request, pk=None):
        """
        POST /tesoreria/conciliaciones-bancarias/{pk}/cerrar/

        Cierra la sesión de conciliación y recalcula contadores de pendientes/conciliados.
        """
        from .services import cerrar_conciliacion

        conciliacion = self.get_object()
        if conciliacion.estado == "CERRADA":
            return Response(
                {"detalle": "La conciliación ya estaba cerrada.", "estado": "CERRADA"},
                status=status.HTTP_200_OK,
            )
        cerrar_conciliacion(conciliacion, usuario=request.user)
        return Response(ConciliacionBancariaSerializer(conciliacion).data)
