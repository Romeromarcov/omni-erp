from decimal import Decimal

from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible
from apps.almacenes.models import Almacen

from .models import (
    CategoriaProducto,
    ConversionUnidadMedida,
    MovimientoInventario,
    OperacionInventario,
    PasoOperacion,
    Producto,
    StockActual,
    StockConsignacionCliente,
    StockConsignacionProveedor,
    UnidadMedida,
    VarianteProducto,
)
from .serializers import (
    CategoriaProductoSerializer,
    ConversionUnidadMedidaSerializer,
    CrearOperacionSerializer,
    MovimientoInventarioSerializer,
    OperacionInventarioSerializer,
    PasoOperacionSerializer,
    ProductoSerializer,
    StockActualSerializer,
    StockConsignacionClienteSerializer,
    StockConsignacionProveedorSerializer,
    UnidadMedidaSerializer,
    VarianteProductoSerializer,
)


def _empresas(request):
    return get_empresas_visible(request.user)


# ── Catálogo ──────────────────────────────────────────────────────────────────


class UnidadMedidaViewSet(BaseModelViewSet):
    queryset = UnidadMedida.objects.all()
    serializer_class = UnidadMedidaSerializer

    def get_queryset(self):
        return UnidadMedida.objects.filter(id_empresa__in=_empresas(self.request))


class CategoriaProductoViewSet(BaseModelViewSet):
    queryset = CategoriaProducto.objects.all()
    serializer_class = CategoriaProductoSerializer

    def get_queryset(self):
        return CategoriaProducto.objects.filter(id_empresa__in=_empresas(self.request)).order_by(
            "nombre_categoria"
        )


class ProductoViewSet(BaseModelViewSet):
    queryset = Producto.objects.all()
    serializer_class = ProductoSerializer

    def get_queryset(self):
        qs = Producto.objects.filter(id_empresa__in=_empresas(self.request)).select_related(
            "id_categoria", "id_unidad_medida_base"
        )
        empresa_id = self.request.query_params.get("empresa")
        if empresa_id:
            qs = qs.filter(id_empresa=empresa_id)
        return qs

    @action(detail=True, methods=["get"], url_path="kardex")
    def kardex(self, request, pk=None):
        """
        GET /api/inventario/productos/{pk}/kardex/

        Query params:
          almacen      — UUID de almacén (requerido para saldo corriente)
          fecha_desde  — YYYY-MM-DD (inclusive)
          fecha_hasta  — YYYY-MM-DD (inclusive)
        """
        from .services import delta_para_almacen

        producto = self.get_object()
        almacen_id = request.query_params.get("almacen")
        fecha_desde = request.query_params.get("fecha_desde")
        fecha_hasta = request.query_params.get("fecha_hasta")

        qs = (
            MovimientoInventario.objects.filter(
                id_empresa__in=_empresas(request),
                id_producto=producto,
            )
            .select_related("id_almacen_origen", "id_almacen_destino", "id_usuario_registro")
        )

        if almacen_id:
            qs = qs.filter(Q(id_almacen_origen=almacen_id) | Q(id_almacen_destino=almacen_id))

        if fecha_desde:
            qs = qs.filter(fecha_hora_movimiento__date__gte=fecha_desde)

        if fecha_hasta:
            qs = qs.filter(fecha_hora_movimiento__date__lte=fecha_hasta)

        qs = qs.order_by("fecha_hora_movimiento", "fecha_creacion")

        # Calcular saldo inicial si hay filtro de fecha y almacén
        saldo = Decimal("0")
        if almacen_id and fecha_desde:
            prior_qs = (
                MovimientoInventario.objects.filter(
                    id_empresa__in=_empresas(request),
                    id_producto=producto,
                    fecha_hora_movimiento__date__lt=fecha_desde,
                )
                .filter(Q(id_almacen_origen=almacen_id) | Q(id_almacen_destino=almacen_id))
            )
            for mov in prior_qs:
                saldo += delta_para_almacen(mov, almacen_id)

        kardex_items = []
        for mov in qs:
            saldo_anterior = saldo
            delta = delta_para_almacen(mov, almacen_id) if almacen_id else Decimal("0")
            saldo += delta

            kardex_items.append(
                {
                    "id_movimiento": str(mov.id_movimiento_inventario),
                    "fecha_hora": mov.fecha_hora_movimiento,
                    "tipo_movimiento": mov.tipo_movimiento,
                    "cantidad": str(mov.cantidad),
                    "delta": str(delta),
                    "almacen_origen": (
                        mov.id_almacen_origen.nombre_almacen if mov.id_almacen_origen else None
                    ),
                    "almacen_destino": (
                        mov.id_almacen_destino.nombre_almacen if mov.id_almacen_destino else None
                    ),
                    "costo_unitario": (
                        str(mov.costo_unitario_movimiento)
                        if mov.costo_unitario_movimiento is not None
                        else None
                    ),
                    "saldo_anterior": str(saldo_anterior),
                    "saldo_posterior": str(saldo),
                    "observaciones": mov.observaciones,
                }
            )

        return Response(
            {
                "producto_id": str(producto.id_producto),
                "producto_nombre": producto.nombre_producto,
                "almacen_id": almacen_id,
                "saldo_final": str(saldo),
                "kardex": kardex_items,
            }
        )


class VarianteProductoViewSet(BaseModelViewSet):
    queryset = VarianteProducto.objects.all()
    serializer_class = VarianteProductoSerializer

    def get_queryset(self):
        # R-CODE-1: filtrar vía FK id_producto → id_empresa
        return VarianteProducto.objects.filter(id_producto__id_empresa__in=_empresas(self.request))


# ── Stock ─────────────────────────────────────────────────────────────────────


class StockActualViewSet(BaseModelViewSet):
    queryset = StockActual.objects.all()
    serializer_class = StockActualSerializer

    def get_queryset(self):
        qs = StockActual.objects.filter(id_empresa__in=_empresas(self.request)).select_related(
            "id_producto", "id_almacen"
        )
        producto_id = self.request.query_params.get("producto")
        almacen_id = self.request.query_params.get("almacen")
        empresa_id = self.request.query_params.get("empresa")
        if producto_id:
            qs = qs.filter(id_producto=producto_id)
        if almacen_id:
            qs = qs.filter(id_almacen=almacen_id)
        if empresa_id:
            qs = qs.filter(id_empresa=empresa_id)
        return qs.order_by("id_producto", "id_almacen")


# ── Movimientos ───────────────────────────────────────────────────────────────


class MovimientoInventarioViewSet(BaseModelViewSet):
    queryset = MovimientoInventario.objects.all()
    serializer_class = MovimientoInventarioSerializer

    def get_queryset(self):
        return (
            MovimientoInventario.objects.filter(id_empresa__in=_empresas(self.request))
            .select_related("id_producto", "id_almacen_origen", "id_almacen_destino")
            .order_by("-fecha_hora_movimiento")
        )

    def perform_create(self, serializer):
        from .services import MovimientoInvalidoError, StockInsuficienteError, registrar_movimiento

        vd = serializer.validated_data
        try:
            movimiento = registrar_movimiento(
                empresa=vd["id_empresa"],
                fecha_hora_movimiento=vd["fecha_hora_movimiento"],
                tipo_movimiento=vd["tipo_movimiento"],
                producto=vd["id_producto"],
                variante=vd.get("id_variante"),
                cantidad=vd["cantidad"],
                almacen_origen=vd.get("id_almacen_origen"),
                almacen_destino=vd.get("id_almacen_destino"),
                costo_unitario=vd.get("costo_unitario_movimiento"),
                documento_origen_id=vd.get("id_documento_origen"),
                nombre_modelo_origen=vd.get("nombre_modelo_origen"),
                usuario=self.request.user,
                observaciones=vd.get("observaciones"),
            )
        except (StockInsuficienteError, MovimientoInvalidoError) as exc:
            raise ValidationError(str(exc)) from exc

        serializer.instance = movimiento


# ── Otras tablas de inventario ────────────────────────────────────────────────


class ConversionUnidadMedidaViewSet(BaseModelViewSet):
    queryset = ConversionUnidadMedida.objects.all()
    serializer_class = ConversionUnidadMedidaSerializer

    def get_queryset(self):
        return ConversionUnidadMedida.objects.filter(id_empresa__in=_empresas(self.request))


class StockConsignacionClienteViewSet(BaseModelViewSet):
    queryset = StockConsignacionCliente.objects.all()
    serializer_class = StockConsignacionClienteSerializer

    def get_queryset(self):
        return StockConsignacionCliente.objects.filter(id_empresa__in=_empresas(self.request))


class StockConsignacionProveedorViewSet(BaseModelViewSet):
    queryset = StockConsignacionProveedor.objects.all()
    serializer_class = StockConsignacionProveedorSerializer

    def get_queryset(self):
        return StockConsignacionProveedor.objects.filter(id_empresa__in=_empresas(self.request))


class PasoOperacionViewSet(BaseModelViewSet):
    """CRUD de pasos configurables de operación (recepción/entrega) por almacén."""

    queryset = PasoOperacion.objects.all()
    serializer_class = PasoOperacionSerializer

    def get_queryset(self):
        # R-CODE-1
        qs = PasoOperacion.objects.filter(id_empresa__in=_empresas(self.request))
        almacen_id = self.request.query_params.get("almacen")
        tipo = self.request.query_params.get("tipo_operacion")
        if almacen_id:
            qs = qs.filter(id_almacen=almacen_id)
        if tipo:
            qs = qs.filter(tipo_operacion=tipo)
        return qs.order_by("id_almacen", "tipo_operacion", "secuencia")


class _OperacionInventarioBaseViewSet(BaseModelViewSet):
    """Base de recepciones/entregas con stepper. Las subclases fijan `tipo_operacion`."""

    serializer_class = OperacionInventarioSerializer
    tipo_operacion = None  # "RECEPCION" | "ENTREGA"

    def get_queryset(self):
        # R-CODE-1
        return (
            OperacionInventario.objects.filter(
                id_empresa__in=_empresas(self.request), tipo_operacion=self.tipo_operacion
            )
            .prefetch_related("pasos", "lineas")
            .order_by("-fecha")
        )

    def create(self, request, *args, **kwargs):
        from .models import Producto, VarianteProducto
        from .operaciones import OperacionError, crear_operacion

        entrada = CrearOperacionSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        data = entrada.validated_data

        empresas = _empresas(request)
        almacen = Almacen.objects.filter(id_almacen=data["almacen"], id_empresa__in=empresas).first()
        if almacen is None:
            raise ValidationError({"almacen": "Almacén inexistente o de otra empresa."})
        empresa = almacen.id_empresa

        contraparte = None
        if data.get("almacen_contraparte"):
            contraparte = Almacen.objects.filter(
                id_almacen=data["almacen_contraparte"], id_empresa=empresa
            ).first()
            if contraparte is None:
                raise ValidationError({"almacen_contraparte": "Almacén inexistente o de otra empresa."})

        lineas = []
        for ln in data["lineas"]:
            producto = Producto.objects.filter(id_producto=ln["producto"], id_empresa=empresa).first()
            if producto is None:
                raise ValidationError({"lineas": f"Producto {ln['producto']} inexistente o de otra empresa."})
            variante = None
            if ln.get("variante"):
                variante = VarianteProducto.objects.filter(
                    id_variante=ln["variante"], id_producto=producto
                ).first()
                if variante is None:
                    raise ValidationError({"lineas": "Variante inexistente para el producto."})
            lineas.append({
                "producto": producto, "variante": variante,
                "cantidad": ln["cantidad"], "costo_unitario": ln.get("costo_unitario"),
            })

        try:
            operacion = crear_operacion(
                empresa=empresa, almacen=almacen, tipo_operacion=self.tipo_operacion,
                origen_tipo=data["origen_tipo"], lineas=lineas, usuario=request.user,
                origen_id=data.get("origen_id"), almacen_contraparte=contraparte,
                motivo=data.get("motivo", ""),
            )
        except OperacionError as exc:
            raise ValidationError({"detail": str(exc)})

        salida = OperacionInventarioSerializer(operacion)
        return Response(salida.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path=r"step/(?P<step_id>[^/.]+)/confirm")
    def confirmar_step(self, request, pk=None, step_id=None):
        from .models import OperacionInventarioPaso
        from .operaciones import OperacionError, PasoFueraDeOrdenError, confirmar_paso

        operacion = self.get_object()
        paso = OperacionInventarioPaso.objects.filter(
            id_operacion_paso=step_id, id_operacion=operacion
        ).first()
        if paso is None:
            raise ValidationError({"step_id": "El paso no existe en esta operación."})

        try:
            confirmar_paso(operacion=operacion, paso=paso, usuario=request.user)
        except PasoFueraDeOrdenError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except OperacionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        operacion.refresh_from_db()
        return Response(OperacionInventarioSerializer(operacion).data)


class RecepcionViewSet(_OperacionInventarioBaseViewSet):
    tipo_operacion = "RECEPCION"


class EntregaViewSet(_OperacionInventarioBaseViewSet):
    tipo_operacion = "ENTREGA"


class ReportesInventarioViewSet(viewsets.ViewSet):
    """Reportes de inventario: existencias, movimientos y valoración (R-CODE-1)."""

    def _empresas(self):
        return _empresas(self.request)

    @action(detail=False, methods=["get"], url_path="existencias")
    def existencias(self, request):
        """Existencias por producto/almacén. Filtros: ?producto=&almacen=."""
        qs = StockActual.objects.filter(id_empresa__in=self._empresas()).select_related(
            "id_producto", "id_almacen"
        )
        producto = request.query_params.get("producto")
        almacen = request.query_params.get("almacen")
        if producto:
            qs = qs.filter(id_producto=producto)
        if almacen:
            qs = qs.filter(id_almacen=almacen)
        data = [
            {
                "producto_id": str(s.id_producto_id),
                "producto": s.id_producto.nombre_producto,
                "almacen_id": str(s.id_almacen_id),
                "almacen": s.id_almacen.nombre_almacen,
                "cantidad_disponible": str(s.cantidad_disponible),
                "cantidad_comprometida": str(s.cantidad_comprometida),
            }
            for s in qs.order_by("id_producto__nombre_producto", "id_almacen__nombre_almacen")
        ]
        return Response({"existencias": data})

    @action(detail=False, methods=["get"], url_path="movimientos")
    def movimientos(self, request):
        """Historial de movimientos. Filtros: ?producto=&almacen=&tipo=&fecha_desde=&fecha_hasta=."""
        qs = MovimientoInventario.objects.filter(id_empresa__in=self._empresas()).select_related(
            "id_producto", "id_almacen_origen", "id_almacen_destino"
        )
        producto = request.query_params.get("producto")
        almacen = request.query_params.get("almacen")
        tipo = request.query_params.get("tipo")
        fecha_desde = request.query_params.get("fecha_desde")
        fecha_hasta = request.query_params.get("fecha_hasta")
        if producto:
            qs = qs.filter(id_producto=producto)
        if almacen:
            qs = qs.filter(Q(id_almacen_origen=almacen) | Q(id_almacen_destino=almacen))
        if tipo:
            qs = qs.filter(tipo_movimiento=tipo)
        if fecha_desde:
            qs = qs.filter(fecha_hora_movimiento__date__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha_hora_movimiento__date__lte=fecha_hasta)
        data = [
            {
                "id": str(m.id_movimiento_inventario),
                "fecha": m.fecha_hora_movimiento,
                "tipo": m.tipo_movimiento,
                "producto": m.id_producto.nombre_producto,
                "cantidad": str(m.cantidad),
                "costo_unitario": str(m.costo_unitario_movimiento) if m.costo_unitario_movimiento is not None else None,
                "almacen_origen": m.id_almacen_origen.nombre_almacen if m.id_almacen_origen else None,
                "almacen_destino": m.id_almacen_destino.nombre_almacen if m.id_almacen_destino else None,
            }
            for m in qs.order_by("-fecha_hora_movimiento")[:500]
        ]
        return Response({"movimientos": data})

    @action(detail=False, methods=["get"], url_path="valoracion")
    def valoracion(self, request):
        """
        Valoración de existencias por producto/almacén. Método-agnóstico:
        valor = Σ(ENTRADA.valor_total) − Σ(SALIDA.valor_total); coincide con FIFO
        (capas) y con costo Promedio móvil. Filtros: ?producto=&almacen=.
        """
        from decimal import Decimal as _D

        from django.db.models import Case, DecimalField, Sum, Value, When

        from .models import Producto, ValoracionInventario

        dec = DecimalField(max_digits=22, decimal_places=4)
        cero = Value(_D("0"), output_field=dec)
        qs = ValoracionInventario.objects.filter(id_empresa__in=self._empresas())
        producto = request.query_params.get("producto")
        almacen = request.query_params.get("almacen")
        if producto:
            qs = qs.filter(id_producto=producto)
        if almacen:
            qs = qs.filter(id_almacen=almacen)

        agregado = qs.values("id_producto", "id_almacen").annotate(
            ent_qty=Sum(Case(When(sentido="ENTRADA", then="cantidad"), default=cero, output_field=dec)),
            sal_qty=Sum(Case(When(sentido="SALIDA", then="cantidad"), default=cero, output_field=dec)),
            ent_val=Sum(Case(When(sentido="ENTRADA", then="valor_total"), default=cero, output_field=dec)),
            sal_val=Sum(Case(When(sentido="SALIDA", then="valor_total"), default=cero, output_field=dec)),
        )

        prod_ids = {a["id_producto"] for a in agregado}
        nombres = {
            p.pk: (p.nombre_producto, p.metodo_valoracion)
            for p in Producto.objects.filter(id_producto__in=prod_ids)
        }
        alm_ids = {a["id_almacen"] for a in agregado}
        almacenes = {a.pk: a.nombre_almacen for a in Almacen.objects.filter(id_almacen__in=alm_ids)}

        data = []
        for a in agregado:
            qty = (a["ent_qty"] or _D("0")) - (a["sal_qty"] or _D("0"))
            valor = (a["ent_val"] or _D("0")) - (a["sal_val"] or _D("0"))
            nombre, metodo = nombres.get(a["id_producto"], ("", ""))
            costo_prom = (valor / qty).quantize(_D("0.0001")) if qty > 0 else _D("0")
            data.append({
                "producto_id": str(a["id_producto"]),
                "producto": nombre,
                "almacen_id": str(a["id_almacen"]),
                "almacen": almacenes.get(a["id_almacen"], ""),
                "metodo": metodo,
                "cantidad": str(qty),
                "valor_total": str(valor),
                "costo_promedio": str(costo_prom),
            })
        data.sort(key=lambda d: (d["producto"], d["almacen"]))
        return Response({"valoracion": data})
