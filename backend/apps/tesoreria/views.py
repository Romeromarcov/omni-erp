import uuid

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import filters, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.core.serializer_mixins import TenantFKScopeMixin
from apps.core.viewsets import ActiveFilterMixin, BaseModelViewSet, get_empresas_visible

from .models import (
    Caja,
    ConciliacionBancaria,
    ExtractoBancarioArchivo,
    MovimientoBancario,
    MovimientoInternoFondo,
    OperacionCambioDivisa,
)
from .serializers import (
    CajaSerializer,
    ConciliacionBancariaSerializer,
    ExtractoBancarioArchivoSerializer,
    ImportarExtractoRequestSerializer,
    ImportarExtractoResponseSerializer,
    MovimientoBancarioSerializer,
    MovimientoInternoFondoSerializer,
    OperacionCambioDivisaSerializer,
    SaldosConsolidadosResponseSerializer,
)


def _empresas(request):
    return get_empresas_visible(request.user)


def _validar_uuid(valor, campo: str) -> str:
    try:
        return str(uuid.UUID(str(valor)))
    except (ValueError, TypeError) as exc:
        raise ValidationError({campo: f"'{valor}' no es un UUID válido."}) from exc


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


class ExtractoBancarioArchivoViewSet(
    ActiveFilterMixin,
    TenantFKScopeMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    Gestión multi-tenant de extractos bancarios validados.

    GET    /tesoreria/extractos-bancarios/                     — listar cortes (?empresa=, ?cuenta=, ?cuadra=)
    GET    /tesoreria/extractos-bancarios/{pk}/                — detalle de corte
    DELETE /tesoreria/extractos-bancarios/{pk}/                — borrado lógico (R-CODE-6)
    POST   /tesoreria/extractos-bancarios/importar/            — subir y validar .xlsx / HTML-.xls / .csv
    GET    /tesoreria/extractos-bancarios/saldos-consolidados/ — saldos USD/VES y alertas de continuidad
    """

    queryset = ExtractoBancarioArchivo.objects.all()
    serializer_class = ExtractoBancarioArchivoSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PageNumberPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nombre_archivo", "formato_banco", "observaciones"]
    ordering_fields = ["fecha_hasta", "fecha_desde", "fecha_creacion", "saldo_final"]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def paginate_queryset(self, queryset):
        if queryset.ordered is False:
            queryset = queryset.order_by("pk")
        return super().paginate_queryset(queryset)

    def get_queryset(self):
        empresas = _empresas(self.request)
        qs = super().get_queryset().filter(id_empresa__in=empresas).select_related(
            "id_cuenta_bancaria", "id_empresa"
        )
        empresa_id = self.request.query_params.get("empresa")
        cuenta_id = self.request.query_params.get("cuenta")
        cuadra = self.request.query_params.get("cuadra")
        if empresa_id:
            qs = qs.filter(id_empresa=_validar_uuid(empresa_id, "empresa"))
        if cuenta_id:
            qs = qs.filter(id_cuenta_bancaria=_validar_uuid(cuenta_id, "cuenta"))
        if cuadra is not None and cuadra != "":
            qs = qs.filter(cuadra=cuadra.replace("\x00", "").strip().lower() in ("true", "1", "yes"))
        return qs.order_by("-fecha_hasta", "-fecha_creacion")

    def perform_destroy(self, instance):
        from .extractos import ExtractoBancarioError, desactivar_extracto_bancario

        try:
            desactivar_extracto_bancario(instance)
        except ExtractoBancarioError as exc:
            raise ValidationError({"error": str(exc)}) from exc

    @swagger_auto_schema(
        request_body=ImportarExtractoRequestSerializer,
        responses={
            200: ImportarExtractoResponseSerializer,
            201: ImportarExtractoResponseSerializer,
        },
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="importar",
        parser_classes=[MultiPartParser, FormParser],
    )
    def importar(self, request):
        from apps.finanzas.models import CuentaBancariaEmpresa

        from .extractos import ExtractoBancarioError, importar_extracto_bancario
        from .extractos.lector_hojas import TAMANO_MAXIMO_ARCHIVO

        empresa_id = request.data.get("empresa")
        cuenta_id = request.data.get("cuenta_bancaria")
        formato_banco = request.data.get("formato_banco")
        archivo = request.FILES.get("archivo")

        if not cuenta_id or not archivo:
            return Response(
                {"error": "Se requieren: cuenta_bancaria y archivo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cuenta_uuid = _validar_uuid(cuenta_id, "cuenta_bancaria")
        empresas = _empresas(request)
        if empresa_id:
            empresa_uuid = _validar_uuid(empresa_id, "empresa")
            empresa = empresas.filter(pk=empresa_uuid).first()
            if not empresa:
                return Response(
                    {"error": "Sin empresa accesible."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            qs_cuenta = CuentaBancariaEmpresa.objects.select_related(
                "id_empresa", "id_moneda"
            ).filter(pk=cuenta_uuid, id_empresa=empresa)
        else:
            qs_cuenta = CuentaBancariaEmpresa.objects.select_related(
                "id_empresa", "id_moneda"
            ).filter(pk=cuenta_uuid, id_empresa__in=empresas)

        cuenta = qs_cuenta.first()
        if cuenta is None:
            return Response(
                {"error": "Cuenta bancaria no encontrada."},
                status=status.HTTP_404_NOT_FOUND,
            )

        contenido = archivo.read(TAMANO_MAXIMO_ARCHIVO + 1)
        nombre_archivo = str(getattr(archivo, "name", "extracto") or "extracto").replace("\x00", "")
        formato_limpio = str(formato_banco).replace("\x00", "").strip() if formato_banco else None
        try:
            res = importar_extracto_bancario(
                empresa=cuenta.id_empresa,
                cuenta_bancaria=cuenta,
                contenido=contenido,
                nombre_archivo=nombre_archivo,
                formato_banco=formato_limpio,
                usuario=request.user,
            )
        except ExtractoBancarioError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        codigo_http = (
            status.HTTP_200_OK if res.ya_existia_archivo else status.HTTP_201_CREATED
        )
        return Response(
            {
                "archivo": ExtractoBancarioArchivoSerializer(res.archivo).data,
                "ya_existia_archivo": res.ya_existia_archivo,
                "lineas_nuevas": res.lineas_nuevas,
                "lineas_duplicadas": res.lineas_duplicadas,
                "cuadra": res.cuadra,
                "saltos": res.saltos,
                "avisos": res.avisos,
            },
            status=codigo_http,
        )

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                "empresa",
                openapi.IN_QUERY,
                description="UUID de la empresa (opcional; usa la empresa activa accesible).",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_UUID,
            ),
            openapi.Parameter(
                "cuenta",
                openapi.IN_QUERY,
                description="UUID de CuentaBancariaEmpresa para filtrar.",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_UUID,
            ),
        ],
        responses={200: SaldosConsolidadosResponseSerializer},
    )
    @action(detail=False, methods=["get"], url_path="saldos-consolidados")
    def saldos_consolidados(self, request):
        from .extractos import (
            FORMATOS_BANCO_SOPORTADOS,
            consolidar_saldos_extractos,
            serializar_consolidado,
        )

        empresa_id = request.query_params.get("empresa")
        cuenta_id = request.query_params.get("cuenta")
        empresas = _empresas(request)

        if empresa_id:
            empresa_uuid = _validar_uuid(empresa_id, "empresa")
            empresa = empresas.filter(pk=empresa_uuid).first()
        else:
            empresa = empresas.first()

        if not empresa:
            return Response(
                {"error": "Sin empresa accesible."},
                status=status.HTTP_403_FORBIDDEN,
            )

        cuenta_uuid = _validar_uuid(cuenta_id, "cuenta") if cuenta_id else None
        cons = consolidar_saldos_extractos(empresa, cuenta_id=cuenta_uuid)
        data = serializar_consolidado(cons)
        data["formatos_soportados"] = list(FORMATOS_BANCO_SOPORTADOS)
        return Response(data, status=status.HTTP_200_OK)


class MovimientoBancarioViewSet(ActiveFilterMixin, BaseModelViewSet):
    """
    CRUD de movimientos bancarios.

    GET  /tesoreria/movimientos-bancarios/                   — listar (?empresa=, ?cuenta=, ?estado=, ?categoria=, ?archivo=)
    POST /tesoreria/movimientos-bancarios/                   — registrar manual
    POST /tesoreria/movimientos-bancarios/importar-csv/      — importar extracto CSV
    POST /tesoreria/movimientos-bancarios/conciliar-auto/    — conciliación automática
    """

    queryset = MovimientoBancario.objects.all()
    serializer_class = MovimientoBancarioSerializer
    search_fields = ["descripcion", "referencia", "categoria_clasificacion"]
    ordering_fields = ["fecha_mov", "monto", "fecha_creacion", "orden_en_archivo"]

    def get_queryset(self):
        empresas = _empresas(self.request)
        qs = (
            super()
            .get_queryset()
            .filter(id_empresa__in=empresas)
            .select_related("id_cuenta_bancaria", "id_empresa")
        )
        empresa_id = self.request.query_params.get("empresa")
        cuenta_id = self.request.query_params.get("cuenta")
        estado = self.request.query_params.get("estado")
        categoria = self.request.query_params.get("categoria")
        archivo_id = self.request.query_params.get("archivo")
        if empresa_id:
            qs = qs.filter(id_empresa=_validar_uuid(empresa_id, "empresa"))
        if cuenta_id:
            qs = qs.filter(id_cuenta_bancaria=_validar_uuid(cuenta_id, "cuenta"))
        if estado:
            qs = qs.filter(estado=estado.replace("\x00", ""))
        if categoria:
            qs = qs.filter(categoria_clasificacion=categoria.replace("\x00", ""))
        if archivo_id:
            qs = qs.filter(id_archivo_extracto=_validar_uuid(archivo_id, "archivo"))
        return qs.order_by("-fecha_mov")

    def perform_create(self, serializer):
        empresa = serializer.validated_data["id_empresa"]
        if empresa not in _empresas(self.request):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Sin acceso a esta empresa.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.estado == "CONCILIADO":
            raise ValidationError(
                {"error": "No se puede desactivar un movimiento bancario ya conciliado."}
            )
        instance.soft_delete()

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

        from .services import importar_extracto_csv

        empresa_id = request.data.get("empresa")
        cuenta_id = request.data.get("cuenta_bancaria")
        archivo = request.FILES.get("archivo")

        if not cuenta_id or not archivo:
            return Response(
                {"error": "Se requieren: cuenta_bancaria y archivo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cuenta_uuid = _validar_uuid(cuenta_id, "cuenta_bancaria")
        empresas = _empresas(request)
        empresa = (
            empresas.filter(pk=_validar_uuid(empresa_id, "empresa")).first()
            if empresa_id
            else empresas.first()
        )
        if not empresa:
            return Response({"error": "Sin empresa accesible."}, status=status.HTTP_403_FORBIDDEN)

        try:
            cuenta = CuentaBancariaEmpresa.objects.get(pk=cuenta_uuid, id_empresa=empresa)
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
        try:
            tolerancia = int(request.data.get("tolerancia_dias", 3))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"tolerancia_dias": "Debe ser un entero."}) from exc

        if not cuenta_id:
            return Response({"error": "Se requiere cuenta_bancaria."}, status=status.HTTP_400_BAD_REQUEST)

        cuenta_uuid = _validar_uuid(cuenta_id, "cuenta_bancaria")
        empresas = _empresas(request)
        try:
            cuenta = CuentaBancariaEmpresa.objects.get(pk=cuenta_uuid, id_empresa__in=empresas)
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
