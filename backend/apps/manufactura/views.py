from decimal import Decimal, InvalidOperation

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import (
    ActiveFilterMixin,
    BaseModelViewSet,
    SoftDeleteModelMixin,
    get_empresas_visible,
)

from . import services
from .models import (
    CentroTrabajo,
    ConfiguracionManufactura,
    ConsumoMaterial,
    EtapaProduccion,
    ListaMateriales,
    ListaMaterialesDetalle,
    OperacionProduccion,
    OrdenProduccion,
    ProduccionTerminada,
    RegistroOperacion,
    RutaProduccion,
    RutaProduccionDetalle,
)
from .serializers import (
    CentroTrabajoSerializer,
    ConfiguracionManufacturaSerializer,
    ConsumoMaterialSerializer,
    EtapaOrdenProduccionSerializer,
    EtapaProduccionSerializer,
    ListaMaterialesDetalleSerializer,
    ListaMaterialesSerializer,
    OperacionProduccionSerializer,
    OrdenProduccionSerializer,
    ProduccionTerminadaSerializer,
    RegistroOperacionSerializer,
    RutaProduccionDetalleSerializer,
    RutaProduccionSerializer,
)


def _empresas(request):
    return get_empresas_visible(request.user)


class ListaMaterialesViewSet(BaseModelViewSet):
    queryset = ListaMateriales.objects.all()
    serializer_class = ListaMaterialesSerializer

    def get_queryset(self):
        # R-CODE-1 — el campo FK a empresa es "empresa" (no "id_empresa")
        return ListaMateriales.objects.filter(empresa__in=_empresas(self.request))

    def perform_create(self, serializer):
        # CTF-004: inyectar empresa automáticamente — el cliente no puede elegirla
        empresa = _empresas(self.request).first()
        if not empresa:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("El usuario no tiene empresa asignada.")
        serializer.save(empresa=empresa)


class RutaProduccionViewSet(BaseModelViewSet):
    queryset = RutaProduccion.objects.all()
    serializer_class = RutaProduccionSerializer

    def get_queryset(self):
        # R-CODE-1 — el campo FK a empresa es "empresa" (no "id_empresa")
        return RutaProduccion.objects.filter(empresa__in=_empresas(self.request))

    def perform_create(self, serializer):
        # CTF-004: inyectar empresa automáticamente
        empresa = _empresas(self.request).first()
        if not empresa:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("El usuario no tiene empresa asignada.")
        serializer.save(empresa=empresa)


def _error(mensaje, codigo=status.HTTP_400_BAD_REQUEST):
    return Response({"error": mensaje}, status=codigo)


def _parse_decimal(valor, nombre, default=None):
    """Parsea un Decimal del payload; ValueError con mensaje claro si es inválido."""
    if valor is None or valor == "":
        return default
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"El campo '{nombre}' no es un número válido.") from exc


class OrdenProduccionViewSet(BaseModelViewSet):
    """CRUD de OF + acciones del ciclo 1.I (R-CODE-7):

      POST /{pk}/consumir-materiales/  — explota BOM y descuenta inventario
      POST /{pk}/avanzar-etapa/        — completa la siguiente etapa (quién/cuándo/MO)
      GET  /{pk}/etapas/               — etapas de la OF con su estado y costo MO
      POST /{pk}/completar/            — entrada de PT valorada al costo real
      GET  /{pk}/costeo/               — costeo real (materiales + MO + overhead)
      GET  /{pk}/mrp/                  — faltantes para producir la orden
    """

    queryset = OrdenProduccion.objects.all()
    serializer_class = OrdenProduccionSerializer

    def get_queryset(self):
        # R-CODE-1 — el campo FK a empresa es "empresa" (no "id_empresa")
        return OrdenProduccion.objects.filter(empresa__in=_empresas(self.request))

    def perform_create(self, serializer):
        # CTF-004: inyectar empresa automáticamente
        empresa = _empresas(self.request).first()
        if not empresa:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("El usuario no tiene empresa asignada.")
        orden = serializer.save(empresa=empresa)
        # 1.I — materializar etapas del catálogo también al crear por API.
        services.crear_etapas_para_orden(orden)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _almacen_de(self, orden, almacen_id):
        """Resuelve el almacén DENTRO de la empresa de la orden (R-CODE-1)."""
        from apps.almacenes.models import Almacen

        if not almacen_id:
            raise ValueError("El campo 'almacen_id' es obligatorio.")
        almacen = Almacen.objects.filter(pk=almacen_id, id_empresa=orden.empresa).first()
        if almacen is None:
            raise ValueError("Almacén no encontrado en la empresa de la orden.")
        return almacen

    @staticmethod
    def _costo_json(costo: dict) -> dict:
        # Decimal → str para no perder precisión en JSON (R-CODE-4)
        return {k: str(v) for k, v in costo.items()}

    # ── Acciones 1.I ─────────────────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="consumir-materiales")
    def consumir_materiales(self, request, pk=None):
        """Explota la BOM de la orden y descuenta los materiales del inventario."""
        from apps.inventario.services import StockInsuficienteError

        orden = self.get_object()
        try:
            almacen = self._almacen_de(orden, request.data.get("almacen_id"))
            resultado = services.consumir_materiales_orden(
                orden,
                almacen=almacen,
                usuario=request.user,
                incluir_opcionales=bool(request.data.get("incluir_opcionales", False)),
            )
        except (ValueError, services.ManufacturaError, StockInsuficienteError) as exc:
            return _error(str(exc))
        return Response({
            "estado": orden.estado,
            "consumos": ConsumoMaterialSerializer(resultado["consumos"], many=True).data,
            "costo_materiales": str(resultado["costo_materiales"]),
        })

    @action(detail=True, methods=["post"], url_path="avanzar-etapa")
    def avanzar_etapa(self, request, pk=None):
        """Completa la siguiente etapa pendiente registrando quién/cuándo y la
        mano de obra (horas × tarifa y/o destajo)."""
        orden = self.get_object()
        try:
            etapa = services.avanzar_etapa_orden(
                orden,
                usuario=request.user,
                horas_trabajadas=_parse_decimal(request.data.get("horas_trabajadas"), "horas_trabajadas", Decimal("0")),
                tarifa_hora=_parse_decimal(request.data.get("tarifa_hora"), "tarifa_hora", Decimal("0")),
                cantidad_destajo=_parse_decimal(request.data.get("cantidad_destajo"), "cantidad_destajo", Decimal("0")),
                observaciones=str(request.data.get("observaciones", "")),
            )
        except (ValueError, services.ManufacturaError) as exc:
            return _error(str(exc))
        orden.refresh_from_db()
        return Response({
            "estado_orden": orden.estado,
            "etapa": EtapaOrdenProduccionSerializer(etapa).data,
            "etapas_pendientes": orden.etapas.filter(estado="pendiente").count(),
        })

    @action(detail=True, methods=["get"])
    def etapas(self, request, pk=None):
        """Etapas de la OF en secuencia, con estado y costo de mano de obra."""
        orden = self.get_object()
        qs = orden.etapas.select_related("etapa").order_by("orden")
        return Response(EtapaOrdenProduccionSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"])
    def completar(self, request, pk=None):
        """Registra producción terminada: entrada de PT al inventario valorada
        al costo real. Falla (400) si quedan etapas pendientes."""
        orden = self.get_object()
        try:
            almacen = self._almacen_de(orden, request.data.get("almacen_id"))
            resultado = services.registrar_produccion_terminada(
                orden,
                cantidad=_parse_decimal(request.data.get("cantidad"), "cantidad", orden.cantidad),
                almacen=almacen,
                usuario=request.user,
                mano_obra=_parse_decimal(request.data.get("mano_obra"), "mano_obra"),
                costos_indirectos=_parse_decimal(request.data.get("costos_indirectos"), "costos_indirectos"),
            )
        except (ValueError, services.ManufacturaError) as exc:
            return _error(str(exc))
        orden.refresh_from_db()
        return Response({
            "estado": orden.estado,
            "produccion_id": str(resultado["produccion"].pk),
            "costo": self._costo_json(resultado["costo"]),
        })

    @action(detail=True, methods=["get"])
    def costeo(self, request, pk=None):
        """Costeo real acumulado de la OF: materiales consumidos (costo del
        movimiento) + mano de obra de etapas + overhead configurable."""
        orden = self.get_object()
        try:
            costo = services.costeo_real_orden(orden)
        except services.ManufacturaError as exc:
            return _error(str(exc))
        etapas = orden.etapas.select_related("etapa").order_by("orden")
        return Response({
            "orden_id": str(orden.pk),
            "estado": orden.estado,
            "costo": self._costo_json(costo),
            "etapas": EtapaOrdenProduccionSerializer(etapas, many=True).data,
        })

    @action(detail=True, methods=["get"])
    def mrp(self, request, pk=None):
        """MRP básico: faltantes de materiales para producir la orden
        (explosión de BOM vs StockActual; disponible neto)."""
        orden = self.get_object()
        almacen = None
        try:
            almacen_id = request.query_params.get("almacen_id")
            if almacen_id:
                almacen = self._almacen_de(orden, almacen_id)
            faltantes = services.calcular_mrp_orden(
                orden,
                almacen=almacen,
                incluir_opcionales=request.query_params.get("incluir_opcionales") in ("true", "1"),
            )
        except (ValueError, services.ManufacturaError) as exc:
            return _error(str(exc))
        return Response({
            "orden_id": str(orden.pk),
            "cantidad": str(orden.cantidad),
            "faltantes": [
                {
                    "producto_id": f["producto_id"],
                    "producto": f["producto"],
                    "requerido": str(f["requerido"]),
                    "disponible": str(f["disponible"]),
                    "a_comprar": str(f["a_comprar"]),
                }
                for f in faltantes
            ],
        })


class ConsumoMaterialViewSet(BaseModelViewSet):
    queryset = ConsumoMaterial.objects.all()
    serializer_class = ConsumoMaterialSerializer

    def get_queryset(self):
        # R-CODE-1 — ConsumoMaterial llega via orden_produccion→OrdenProduccion
        return ConsumoMaterial.objects.filter(orden_produccion__empresa__in=_empresas(self.request))


class ProduccionTerminadaViewSet(BaseModelViewSet):
    queryset = ProduccionTerminada.objects.all()
    serializer_class = ProduccionTerminadaSerializer

    def get_queryset(self):
        # R-CODE-1 — ProduccionTerminada llega via orden_produccion→OrdenProduccion
        return ProduccionTerminada.objects.filter(orden_produccion__empresa__in=_empresas(self.request))


class ListaMaterialesDetalleViewSet(BaseModelViewSet):
    queryset = ListaMaterialesDetalle.objects.all()
    serializer_class = ListaMaterialesDetalleSerializer

    def get_queryset(self):
        # R-CODE-1 — ListaMaterialesDetalle llega via id_lista_materiales→ListaMateriales
        return ListaMaterialesDetalle.objects.filter(id_lista_materiales__empresa__in=_empresas(self.request))


class CentroTrabajoViewSet(BaseModelViewSet):
    queryset = CentroTrabajo.objects.all()
    serializer_class = CentroTrabajoSerializer

    def get_queryset(self):
        # R-CODE-1
        return CentroTrabajo.objects.filter(id_empresa__in=_empresas(self.request))


class OperacionProduccionViewSet(BaseModelViewSet):
    queryset = OperacionProduccion.objects.all()
    serializer_class = OperacionProduccionSerializer

    def get_queryset(self):
        # R-CODE-1
        return OperacionProduccion.objects.filter(id_empresa__in=_empresas(self.request))


class RutaProduccionDetalleViewSet(BaseModelViewSet):
    queryset = RutaProduccionDetalle.objects.all()
    serializer_class = RutaProduccionDetalleSerializer

    def get_queryset(self):
        # R-CODE-1 — RutaProduccionDetalle llega via id_ruta_produccion→RutaProduccion
        return RutaProduccionDetalle.objects.filter(id_ruta_produccion__empresa__in=_empresas(self.request))


class RegistroOperacionViewSet(BaseModelViewSet):
    queryset = RegistroOperacion.objects.all()
    serializer_class = RegistroOperacionSerializer

    def get_queryset(self):
        # R-CODE-1 — RegistroOperacion llega via id_orden_produccion→OrdenProduccion
        return RegistroOperacion.objects.filter(id_orden_produccion__empresa__in=_empresas(self.request))


class EtapaProduccionViewSet(SoftDeleteModelMixin, ActiveFilterMixin, BaseModelViewSet):
    """Catálogo de etapas de fabricación por empresa (1.I).

    DELETE = soft-delete (R-CODE-6). POST /crear-estandar/ siembra la secuencia
    estándar de mueblería (corte → … → control final) para la empresa del usuario.
    """

    queryset = EtapaProduccion.objects.all()
    serializer_class = EtapaProduccionSerializer
    search_fields = ["codigo", "nombre"]
    ordering_fields = ["orden", "codigo", "nombre"]
    ordering = ["orden"]

    def get_queryset(self):
        # R-CODE-1 — el campo FK a empresa es "empresa"
        return super().get_queryset().filter(empresa__in=_empresas(self.request))

    def perform_create(self, serializer):
        # CTF-004: inyectar empresa automáticamente
        empresa = _empresas(self.request).first()
        if not empresa:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("El usuario no tiene empresa asignada.")
        serializer.save(empresa=empresa)

    @action(detail=False, methods=["post"], url_path="crear-estandar")
    def crear_estandar(self, request):
        """Crea las etapas estándar de mueblería para la empresa del usuario."""
        empresa = _empresas(request).first()
        if not empresa:
            return _error("El usuario no tiene empresa asignada.", status.HTTP_403_FORBIDDEN)
        creadas = services.crear_etapas_estandar(empresa)
        return Response(
            {"creadas": EtapaProduccionSerializer(creadas, many=True).data},
            status=status.HTTP_201_CREATED if creadas else status.HTTP_200_OK,
        )


class ConfiguracionManufacturaViewSet(BaseModelViewSet):
    """Configuración de manufactura por empresa (overhead configurable, 1.I)."""

    queryset = ConfiguracionManufactura.objects.all()
    serializer_class = ConfiguracionManufacturaSerializer
    search_fields = []
    ordering_fields = ["porcentaje_overhead"]

    def get_queryset(self):
        # R-CODE-1
        return ConfiguracionManufactura.objects.filter(empresa__in=_empresas(self.request))

    def perform_create(self, serializer):
        # CTF-004: inyectar empresa automáticamente (OneToOne por empresa)
        from rest_framework.exceptions import PermissionDenied, ValidationError

        empresa = _empresas(self.request).first()
        if not empresa:
            raise PermissionDenied("El usuario no tiene empresa asignada.")
        if ConfiguracionManufactura.objects.filter(empresa=empresa).exists():
            raise ValidationError("La empresa ya tiene configuración de manufactura; usa PATCH.")
        serializer.save(empresa=empresa)
