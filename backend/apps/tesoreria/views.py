from datetime import date
import uuid

from django.db import IntegrityError, transaction
from django.utils.decorators import method_decorator
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import filters, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.core.exceptions import domain_error_response
from apps.core.serializer_mixins import TenantFKScopeMixin
from apps.core.viewsets import ActiveFilterMixin, BaseModelViewSet, get_empresas_visible

from .models import (
    Caja,
    ConciliacionBancaria,
    ConfiguracionConciliacionCuenta,
    DecisionPreconciliacionBancaria,
    ExtractoBancarioArchivo,
    MovimientoBancario,
    MovimientoInternoFondo,
    OperacionCambioDivisa,
    PropuestaConciliacionBancaria,
)
from .serializers import (
    CajaSerializer,
    ConciliacionBancariaSerializer,
    ConfiguracionConciliacionCuentaSerializer,
    DecidirPropuestaRequestSerializer,
    DecisionPreconciliacionBancariaSerializer,
    ExtractoBancarioArchivoSerializer,
    GenerarPropuestasRequestSerializer,
    GenerarPropuestasResponseSerializer,
    ImportarExtractoRequestSerializer,
    ImportarExtractoResponseSerializer,
    MovimientoBancarioSerializer,
    MovimientoInternoFondoSerializer,
    OperacionCambioDivisaSerializer,
    PropuestaConciliacionBancariaSerializer,
    SaldosConsolidadosResponseSerializer,
)


def _empresas(request):
    return get_empresas_visible(request.user)


def _validar_uuid(valor, campo: str) -> str:
    try:
        return str(uuid.UUID(str(valor)))
    except (ValueError, TypeError) as exc:
        raise ValidationError({campo: f"'{valor}' no es un UUID válido."}) from exc


def _validar_fecha(valor, campo: str) -> date:
    try:
        return date.fromisoformat(str(valor).replace("\x00", "").strip())
    except (ValueError, TypeError) as exc:
        raise ValidationError({campo: f"'{valor}' no es una fecha ISO válida (YYYY-MM-DD)."}) from exc


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
            return domain_error_response(exc, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)

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
        qs = super().get_queryset().filter(id_empresa__in=empresas).select_related("id_cuenta_bancaria", "id_empresa")
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
            qs_cuenta = CuentaBancariaEmpresa.objects.select_related("id_empresa", "id_moneda").filter(
                pk=cuenta_uuid, id_empresa=empresa
            )
        else:
            qs_cuenta = CuentaBancariaEmpresa.objects.select_related("id_empresa", "id_moneda").filter(
                pk=cuenta_uuid, id_empresa__in=empresas
            )

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
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)

        codigo_http = status.HTTP_200_OK if res.ya_existia_archivo else status.HTTP_201_CREATED
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
            .select_related("id_cuenta_bancaria", "id_empresa", "id_pago_conciliado")
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
        from apps.finanzas.models import CuentaBancariaEmpresa

        with transaction.atomic():
            CuentaBancariaEmpresa.objects.select_for_update().get(pk=instance.id_cuenta_bancaria_id)
            mov_locked = MovimientoBancario.objects.select_for_update().get(pk=instance.pk)
            if mov_locked.estado == "CONCILIADO":
                raise ValidationError({"error": "No se puede desactivar un movimiento bancario ya conciliado."})
            if ConciliacionBancaria.objects.filter(
                id_empresa_id=mov_locked.id_empresa_id,
                id_cuenta_bancaria_id=mov_locked.id_cuenta_bancaria_id,
                periodo_inicio__lte=mov_locked.fecha_mov,
                periodo_fin__gte=mov_locked.fecha_mov,
                estado="CERRADA",
            ).exists():
                raise ValidationError(
                    {
                        "error": (
                            "No se puede desactivar un movimiento dentro de un período " "de conciliación cerrado."
                        )
                    }
                )
            props_activas = list(
                PropuestaConciliacionBancaria.objects.select_for_update().filter(
                    id_empresa_id=mov_locked.id_empresa_id,
                    id_movimiento_bancario=mov_locked,
                    activo=True,
                )
            )
            if any(p.estado != "PENDIENTE" for p in props_activas):
                raise ValidationError(
                    {
                        "error": (
                            "No se puede desactivar un movimiento con una decisión humana "
                            "de pre-conciliación registrada."
                        )
                    }
                )
            if props_activas:
                PropuestaConciliacionBancaria.objects.filter(pk__in=[p.pk for p in props_activas]).update(activo=False)
            mov_locked.soft_delete()
            instance.activo = False

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
        empresa = empresas.filter(pk=_validar_uuid(empresa_id, "empresa")).first() if empresa_id else empresas.first()
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
    search_fields = ["observaciones", "estado", "id_cuenta_bancaria__nombre_banco"]

    def get_queryset(self):
        return ConciliacionBancaria.objects.filter(id_empresa__in=_empresas(self.request)).select_related(
            "id_cuenta_bancaria", "id_empresa"
        )

    def perform_create(self, serializer):
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


@method_decorator(
    name="list",
    decorator=swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter("empresa", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_UUID),
            openapi.Parameter("cuenta", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_UUID),
        ]
    ),
)
class ConfiguracionConciliacionCuentaViewSet(ActiveFilterMixin, BaseModelViewSet):
    """Configuración multi-tenant de cuentas contables y diario externo por cuenta bancaria."""

    queryset = ConfiguracionConciliacionCuenta.objects.all()
    serializer_class = ConfiguracionConciliacionCuentaSerializer
    search_fields = [
        "codigo_cuenta_comisiones",
        "codigo_cuenta_igtf",
        "codigo_cuenta_transito_pendientes",
        "id_cuenta_bancaria__nombre_banco",
        "id_cuenta_bancaria__numero_cuenta",
    ]
    ordering_fields = ["fecha_creacion", "fecha_actualizacion", "ventana_dias"]

    def get_queryset(self):
        empresas = _empresas(self.request)
        qs = (
            super()
            .get_queryset()
            .filter(id_empresa__in=empresas)
            .select_related(
                "id_empresa",
                "id_cuenta_bancaria",
                "id_cuenta_comisiones",
                "id_cuenta_igtf",
                "id_cuenta_transito_pendientes",
                "id_conector_odoo__id_proveedor",
            )
        )
        empresa_id = self.request.query_params.get("empresa")
        cuenta_id = self.request.query_params.get("cuenta")
        if empresa_id:
            qs = qs.filter(id_empresa=_validar_uuid(empresa_id, "empresa"))
        if cuenta_id:
            qs = qs.filter(id_cuenta_bancaria=_validar_uuid(cuenta_id, "cuenta"))
        return qs.order_by("-fecha_creacion")

    def perform_create(self, serializer):
        empresa = serializer.validated_data["id_empresa"]
        if empresa not in _empresas(self.request):
            raise PermissionDenied("Sin acceso a esta empresa.")
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError as exc:
            raise ValidationError(
                {
                    "id_cuenta_bancaria": (
                        "Ya existe una configuración de conciliación activa para esta cuenta bancaria."
                    )
                }
            ) from exc

    def perform_update(self, serializer):
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError as exc:
            raise ValidationError(
                {
                    "id_cuenta_bancaria": (
                        "Ya existe otra configuración de conciliación activa para esta cuenta bancaria."
                    )
                }
            ) from exc

    def perform_destroy(self, instance):
        instance.soft_delete()


@method_decorator(
    name="list",
    decorator=swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter("empresa", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_UUID),
            openapi.Parameter("cuenta", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_UUID),
            openapi.Parameter("estado", openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter("tipo", openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter("regla", openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter("desde", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
            openapi.Parameter("hasta", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
        ]
    ),
)
class PropuestaConciliacionBancariaViewSet(
    ActiveFilterMixin,
    TenantFKScopeMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Cola multi-tenant de pre-conciliación bancaria y revisión humana.

    GET  /tesoreria/propuestas-conciliacion/               — listar propuestas (?empresa=, ?cuenta=, ?estado=, ?tipo=, ?desde=, ?hasta=)
    GET  /tesoreria/propuestas-conciliacion/{pk}/          — detalle de propuesta
    POST /tesoreria/propuestas-conciliacion/generar/       — ejecutar motor R1/R2/R3 sobre cuenta
    POST /tesoreria/propuestas-conciliacion/{pk}/decidir/  — aprobar / rechazar / corregir / reabrir
    GET  /tesoreria/propuestas-conciliacion/aprobadas/     — propuestas aprobadas o corregidas (?decididas_desde=, ?decididas_hasta=)
    GET  /tesoreria/propuestas-conciliacion/bitacora/      — bitácora inmutable de decisiones humanas
    """

    queryset = PropuestaConciliacionBancaria.objects.all()
    serializer_class = PropuestaConciliacionBancariaSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PageNumberPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "motivo",
        "pago_nombre",
        "pago_socio",
        "cuenta_contable_codigo",
        "id_movimiento_bancario__descripcion",
        "id_movimiento_bancario__referencia",
    ]
    ordering_fields = ["puntaje", "generada_en", "decidida_en"]

    def paginate_queryset(self, queryset):
        if queryset.ordered is False:
            queryset = queryset.order_by("pk")
        return super().paginate_queryset(queryset)

    def get_queryset(self):
        empresas = _empresas(self.request)
        qs = (
            super()
            .get_queryset()
            .filter(id_empresa__in=empresas, id_movimiento_bancario__activo=True)
            .select_related(
                "id_empresa",
                "id_movimiento_bancario__id_cuenta_bancaria__id_moneda",
                "id_pago_nativo",
                "id_cuenta_contable",
                "decidida_por",
            )
        )
        params = self.request.query_params
        empresa_id = params.get("empresa")
        cuenta_id = params.get("cuenta")
        estado = params.get("estado")
        tipo = params.get("tipo")
        regla = params.get("regla")
        desde = params.get("desde")
        hasta = params.get("hasta")

        if empresa_id:
            qs = qs.filter(id_empresa=_validar_uuid(empresa_id, "empresa"))
        if cuenta_id:
            qs = qs.filter(id_movimiento_bancario__id_cuenta_bancaria=_validar_uuid(cuenta_id, "cuenta"))
        if estado:
            qs = qs.filter(estado=estado.replace("\x00", "").strip().upper())
        if tipo:
            qs = qs.filter(tipo=tipo.replace("\x00", "").strip().upper())
        if regla:
            qs = qs.filter(regla=regla.replace("\x00", "").strip().upper())
        if desde:
            qs = qs.filter(id_movimiento_bancario__fecha_mov__gte=_validar_fecha(desde, "desde"))
        if hasta:
            qs = qs.filter(id_movimiento_bancario__fecha_mov__lte=_validar_fecha(hasta, "hasta"))
        return qs.order_by(
            "-id_movimiento_bancario__fecha_mov",
            "-id_movimiento_bancario__orden_en_archivo",
            "-generada_en",
        )

    @swagger_auto_schema(
        request_body=GenerarPropuestasRequestSerializer,
        responses={200: GenerarPropuestasResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="generar")
    def generar(self, request):
        from apps.finanzas.models import CuentaBancariaEmpresa

        from .preconciliacion import PreconciliacionError, generar_propuestas_conciliacion

        req_ser = GenerarPropuestasRequestSerializer(data=request.data)
        req_ser.is_valid(raise_exception=True)
        datos = req_ser.validated_data

        empresas = _empresas(request)
        empresa_id = datos.get("empresa")
        cuenta_uuid = datos["cuenta_bancaria"]

        if empresa_id:
            empresa = empresas.filter(pk=empresa_id).first()
            if empresa is None:
                return Response(
                    {"error": "Sin empresa accesible."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            cuenta = (
                CuentaBancariaEmpresa.objects.select_related("id_empresa", "id_moneda")
                .filter(pk=cuenta_uuid, id_empresa=empresa)
                .first()
            )
        else:
            cuenta = (
                CuentaBancariaEmpresa.objects.select_related("id_empresa", "id_moneda")
                .filter(pk=cuenta_uuid, id_empresa__in=empresas)
                .first()
            )
            empresa = cuenta.id_empresa if cuenta is not None else None

        if cuenta is None or empresa is None:
            return Response(
                {"error": "Cuenta bancaria no encontrada."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            resumen = generar_propuestas_conciliacion(
                empresa=empresa,
                cuenta_bancaria=cuenta,
                desde=datos.get("desde"),
                hasta=datos.get("hasta"),
                incluir_odoo=datos.get("incluir_odoo"),
            )
        except PreconciliacionError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)

        return Response(resumen, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        request_body=DecidirPropuestaRequestSerializer,
        responses={200: PropuestaConciliacionBancariaSerializer},
    )
    @action(detail=True, methods=["post"], url_path="decidir")
    def decidir(self, request, pk=None):
        from .preconciliacion import (
            DecisionPreconciliacionInvalida,
            PreconciliacionError,
            decidir_propuesta_conciliacion,
        )

        instancia = self.get_object()
        req_ser = DecidirPropuestaRequestSerializer(data=request.data)
        req_ser.is_valid(raise_exception=True)
        datos = req_ser.validated_data

        try:
            actualizada = decidir_propuesta_conciliacion(
                empresa=instancia.id_empresa,
                propuesta_id=str(instancia.pk),
                accion=datos["accion"],
                usuario=request.user,
                pago_nativo_id=(str(datos["pago_nativo_id"]) if datos.get("pago_nativo_id") else None),
                pago_externo_id=datos.get("pago_externo_id") or "",
                pago_nombre=datos.get("pago_nombre") or "",
                cuenta_contable_id=(str(datos["cuenta_contable_id"]) if datos.get("cuenta_contable_id") else None),
                cuenta_contable_codigo=datos.get("cuenta_contable_codigo") or "",
                comentario=datos.get("comentario") or "",
            )
        except DecisionPreconciliacionInvalida as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        except PreconciliacionError as exc:
            return domain_error_response(exc, status_code=status.HTTP_404_NOT_FOUND)

        actualizada_full = self.get_queryset().get(pk=actualizada.pk)
        return Response(
            PropuestaConciliacionBancariaSerializer(actualizada_full).data,
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter("empresa", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_UUID),
            openapi.Parameter("cuenta", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_UUID),
            openapi.Parameter("decididas_desde", openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter("decididas_hasta", openapi.IN_QUERY, type=openapi.TYPE_STRING),
        ],
        responses={200: PropuestaConciliacionBancariaSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="aprobadas")
    def aprobadas(self, request):
        qs = self.get_queryset().filter(estado__in=["APROBADA", "CORREGIDA"])
        dec_desde = request.query_params.get("decididas_desde")
        dec_hasta = request.query_params.get("decididas_hasta")
        if dec_desde:
            qs = qs.filter(decidida_en__date__gte=_validar_fecha(dec_desde, "decididas_desde"))
        if dec_hasta:
            qs = qs.filter(decidida_en__date__lte=_validar_fecha(dec_hasta, "decididas_hasta"))
        qs = qs.order_by(
            "id_movimiento_bancario__id_cuenta_bancaria__nombre_banco",
            "id_movimiento_bancario__fecha_mov",
            "id_movimiento_bancario__orden_en_archivo",
        )
        pagina = self.paginate_queryset(qs)
        if pagina is not None:
            ser = PropuestaConciliacionBancariaSerializer(pagina, many=True)
            return self.get_paginated_response(ser.data)
        return Response(PropuestaConciliacionBancariaSerializer(qs, many=True).data)

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter("empresa", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_UUID),
            openapi.Parameter("propuesta", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_UUID),
            openapi.Parameter("movimiento", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_UUID),
            openapi.Parameter("accion", openapi.IN_QUERY, type=openapi.TYPE_STRING),
        ],
        responses={200: DecisionPreconciliacionBancariaSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="bitacora")
    def bitacora(self, request):
        empresas = _empresas(request)
        qs = DecisionPreconciliacionBancaria.objects.filter(id_empresa__in=empresas, activo=True).select_related(
            "id_movimiento_bancario", "id_propuesta"
        )

        params = request.query_params
        if params.get("empresa"):
            qs = qs.filter(id_empresa=_validar_uuid(params.get("empresa"), "empresa"))
        if params.get("propuesta"):
            qs = qs.filter(id_propuesta=_validar_uuid(params.get("propuesta"), "propuesta"))
        if params.get("movimiento"):
            qs = qs.filter(id_movimiento_bancario=_validar_uuid(params.get("movimiento"), "movimiento"))
        if params.get("accion"):
            qs = qs.filter(accion=str(params.get("accion")).replace("\x00", "").strip().upper())

        qs = qs.order_by("-fecha_decision")
        pagina = self.paginate_queryset(qs)
        if pagina is not None:
            ser = DecisionPreconciliacionBancariaSerializer(pagina, many=True)
            return self.get_paginated_response(ser.data)
        return Response(DecisionPreconciliacionBancariaSerializer(qs, many=True).data)
