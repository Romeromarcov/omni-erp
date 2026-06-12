import logging
from apps.core.serializer_mixins import TenantFKScopeMixin
from decimal import Decimal

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.idempotency import IdempotentCreateMixin, idempotent
from apps.core.viewsets import EmpresaInjectMixin, get_empresas_visible

logger = logging.getLogger(__name__)


def _empresas(request):
    """Shortcut: devuelve empresas visibles para el usuario del request."""
    return get_empresas_visible(request.user)
from .models import (
    ComisionVenta,
    Cotizacion,
    DetalleCotizacion,
    DetalleDevolucionVenta,
    DetalleFacturaFiscal,
    DetalleNotaCreditoFiscal,
    DetalleNotaCreditoVenta,
    DetalleNotaVenta,
    DetallePedido,
    DetallePrecio,
    DevolucionVenta,
    EsquemaComision,
    EsquemaComisionCategoria,
    FacturaFiscal,
    ListaPrecio,
    NotaCreditoFiscal,
    NotaCreditoVenta,
    NotaVenta,
    Pedido,
)
from .serializers import (
    ComisionVentaSerializer,
    CotizacionSerializer,
    DetalleCotizacionSerializer,
    DetalleDevolucionVentaSerializer,
    DetalleFacturaFiscalSerializer,
    DetalleNotaCreditoFiscalSerializer,
    DetalleNotaCreditoVentaSerializer,
    DetalleNotaVentaSerializer,
    DetallePedidoSerializer,
    DetallePrecioSerializer,
    DevolucionVentaSerializer,
    EsquemaComisionCategoriaSerializer,
    EsquemaComisionSerializer,
    FacturaFiscalSerializer,
    ListaPrecioSerializer,
    LiquidarComisionesInputSerializer,
    NotaCreditoFiscalSerializer,
    NotaCreditoVentaSerializer,
    NotaVentaSerializer,
    PedidoSerializer,
)


class PedidoViewSet(TenantFKScopeMixin, EmpresaInjectMixin, viewsets.ModelViewSet):  # H-API-1
    queryset = Pedido.objects.all()
    serializer_class = PedidoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtrar pedidos por empresas visibles del usuario"""
        from apps.core.viewsets import get_empresas_visible

        user = self.request.user
        empresas_visibles = get_empresas_visible(user)
        return Pedido.objects.filter(id_empresa__in=empresas_visibles).order_by("-fecha_pedido", "-fecha_creacion")

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        # Asegurarse de que el número de pedido esté en la respuesta
        if hasattr(response, "data") and "numero_pedido" not in response.data:
            # Buscar el objeto creado y agregar el número
            instance = self.get_object() if hasattr(self, "get_object") else None
            if instance and hasattr(instance, "numero_pedido"):
                response.data["numero_pedido"] = instance.numero_pedido
        return response

    @idempotent("ventas:confirmar")
    @action(detail=True, methods=["post"], url_path="confirmar")
    def confirmar(self, request, pk=None):
        """
        POST /api/ventas/pedidos/{pk}/confirmar/
        Body: {"almacen_id": "uuid", "generar_cxc": true|false (opcional)}

        Cambia estado a APROBADO, descuenta stock e (opcionalmente) genera CxC.

        Idempotente: con la cabecera ``Idempotency-Key``, un reintento con la misma
        clave devuelve el mismo resultado sin volver a descontar stock ni duplicar
        la CxC generada.
        """
        from apps.almacenes.models import Almacen
        from .services import PedidoConfirmacionError, confirmar_pedido

        pedido = self.get_object()
        almacen_id = request.data.get("almacen_id")
        if not almacen_id:
            raise ValidationError({"almacen_id": "Este campo es requerido."})

        try:
            almacen = Almacen.objects.get(pk=almacen_id, id_empresa=pedido.id_empresa)
        except Almacen.DoesNotExist:
            raise ValidationError({"almacen_id": "Almacén no encontrado en esta empresa."})

        generar_cxc = request.data.get("generar_cxc")
        if generar_cxc is not None:
            generar_cxc = bool(generar_cxc)

        try:
            resultado = confirmar_pedido(
                pedido=pedido,
                almacen=almacen,
                usuario=request.user,
                generar_cxc=generar_cxc,
            )
        except PedidoConfirmacionError as exc:
            raise ValidationError(str(exc)) from exc

        return Response(
            {
                "pedido_id": str(pedido.id_pedido),
                "numero_pedido": pedido.numero_pedido,
                "estado": pedido.estado,
                "reservas_creadas": len(resultado["reservas"]),
                "cxc_generada": resultado["cxc"] is not None,
                "cxc_id": str(resultado["cxc"].pk) if resultado["cxc"] else None,
            },
            status=status.HTTP_200_OK,
        )

    @idempotent("ventas:convertir-nota-venta")
    @action(detail=True, methods=["post"], url_path="convertir-nota-venta")
    def convertir_nota_venta(self, request, pk=None):
        """
        POST /api/ventas/pedidos/{pk}/convertir-nota-venta/

        Crea la NotaVenta (BORRADOR) desde un pedido APROBADO copiando sus
        detalles, y marca el pedido como convertido. Gap E2E (PR #76): el
        botón del frontend llamaba a este endpoint y no existía (404).
        """
        from .services import VentaError, convertir_pedido_a_nota_venta

        pedido = self.get_object()
        try:
            nota = convertir_pedido_a_nota_venta(pedido, usuario=request.user)
        except VentaError as exc:
            raise ValidationError(str(exc)) from exc

        return Response(NotaVentaSerializer(nota).data, status=status.HTTP_201_CREATED)


class DetallePedidoViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = DetallePedido.objects.all()
    serializer_class = DetallePedidoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetallePedido.objects.filter(id_pedido__id_empresa__in=_empresas(self.request))


class NotaVentaViewSet(
    IdempotentCreateMixin, TenantFKScopeMixin, EmpresaInjectMixin, viewsets.ModelViewSet
):  # H-API-1
    queryset = NotaVenta.objects.all()
    serializer_class = NotaVentaSerializer
    permission_classes = [IsAuthenticated]
    # POS/web: un reintento de creación con la misma Idempotency-Key no
    # duplica la nota (opt-in del cliente, PR #86).
    idempotency_scope = "ventas:nota-venta-create"


    def get_queryset(self):
        # R-CODE-1
        return NotaVenta.objects.filter(id_empresa__in=_empresas(self.request)).order_by("-fecha_creacion")

    def perform_update(self, serializer):
        """
        1.G — Comisiones: la anulación de la venta (PATCH estado→ANULADA, único
        camino de anulación de notas hoy) anula su comisión devengada EN LA
        MISMA transacción. Si la comisión ya fue LIQUIDADA, la anulación se
        rechaza (400) y nada cambia.
        """
        from django.db import transaction

        from .services import VentaError, anular_comision_de_nota_venta

        estado_previo = serializer.instance.estado
        with transaction.atomic():
            nota = serializer.save()
            if estado_previo != "ANULADA" and nota.estado == "ANULADA":
                try:
                    anular_comision_de_nota_venta(nota)
                except VentaError as exc:
                    raise ValidationError(str(exc)) from exc

    @idempotent("ventas:entregar")
    @action(detail=True, methods=["post"], url_path="entregar")
    def entregar(self, request, pk=None):
        """
        POST /api/ventas/notas-venta/{pk}/entregar/
        Body: {"almacen_id": "uuid"}

        Entrega la nota delegando en ``confirmar_nota_venta`` (despacho de
        stock + CxC del flujo + asiento NOTA_VENTA + devengo de comisión del
        vendedor — todo en una transacción, R-CODE-11). Gap 1.G: el service
        existía pero ningún endpoint lo invocaba; la entrega por PATCH de
        estado no movía stock ni devengaba nada.

        Idempotente vía cabecera ``Idempotency-Key`` (un reintento no
        despacha stock dos veces).
        """
        from apps.almacenes.models import Almacen

        from .services import VentaError, confirmar_nota_venta

        nota = self.get_object()
        almacen_id = request.data.get("almacen_id")
        if not almacen_id:
            raise ValidationError({"almacen_id": "Este campo es requerido."})
        try:
            almacen = Almacen.objects.get(pk=almacen_id, id_empresa=nota.id_empresa)
        except Almacen.DoesNotExist:
            raise ValidationError({"almacen_id": "Almacén no encontrado en esta empresa."})

        try:
            resultado = confirmar_nota_venta(nota, almacen, request.user)
        except VentaError as exc:
            raise ValidationError(str(exc)) from exc

        comision = resultado.get("comision")
        return Response(
            {
                "nota_venta_id": str(nota.id_nota_venta),
                "numero_nota": nota.numero_nota,
                "estado": nota.estado,
                "movimientos": len(resultado["movimientos"]),
                "cxc_id": str(resultado["cxc"].pk) if resultado.get("cxc") else None,
                "asiento_generado": resultado.get("asiento") is not None,
                "comision_devengada": comision is not None,
                "comision_id": str(comision.pk) if comision else None,
                "comision_monto": str(comision.monto) if comision else None,
            },
            status=status.HTTP_200_OK,
        )

    @idempotent("ventas:convertir-factura")
    @action(detail=True, methods=["post"], url_path="convertir-factura")
    def convertir_factura(self, request, pk=None):
        """
        POST /api/ventas/notas-venta/{pk}/convertir-factura/

        Emite la FacturaFiscal desde una nota ENTREGADA delegando en
        ``emitir_factura_fiscal`` (asiento contable R-CODE-11 + CxC única del
        flujo, BUG-A4). Gap E2E (PR #76): el botón "Convertir a Factura" del
        frontend llamaba a este endpoint y no existía (404).
        """
        from .services import VentaError, emitir_factura_fiscal

        nota = self.get_object()
        try:
            resultado = emitir_factura_fiscal(nota)
        except VentaError as exc:
            raise ValidationError(str(exc)) from exc

        return Response(
            FacturaFiscalSerializer(resultado["factura"]).data,
            status=status.HTTP_201_CREATED,
        )


class DetalleNotaVentaViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = DetalleNotaVenta.objects.all()
    serializer_class = DetalleNotaVentaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleNotaVenta.objects.filter(id_nota_venta__id_empresa__in=_empresas(self.request))


class FacturaFiscalViewSet(TenantFKScopeMixin, EmpresaInjectMixin, viewsets.ModelViewSet):  # H-API-1
    queryset = FacturaFiscal.objects.all()
    serializer_class = FacturaFiscalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtrar facturas por empresas visibles del usuario"""
        from apps.core.viewsets import get_empresas_visible

        user = self.request.user
        empresas_visibles = get_empresas_visible(user)
        return FacturaFiscal.objects.filter(id_empresa__in=empresas_visibles).order_by(
            "-fecha_emision", "-fecha_creacion"
        )

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        """GET /api/ventas/facturas-fiscales/{id}/pdf/ — devuelve el PDF de la factura."""
        from django.http import HttpResponse
        from apps.fiscal.pdf_factura import generar_pdf_factura

        factura = self.get_object()
        try:
            pdf_bytes = generar_pdf_factura(factura)
        except ImportError:
            # SEC-M4 (R-CODE-8): no filtrar el detalle interno al cliente.
            logger.exception("Generación de PDF de factura no disponible")
            return Response(
                {"error": "Generación de PDF no disponible en este servidor."}, status=503
            )

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="factura_{factura.numero_factura}.pdf"'
        )
        return response


class DetalleFacturaFiscalViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = DetalleFacturaFiscal.objects.all()
    serializer_class = DetalleFacturaFiscalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleFacturaFiscal.objects.filter(id_factura__id_empresa__in=_empresas(self.request))


class NotaCreditoVentaViewSet(TenantFKScopeMixin, EmpresaInjectMixin, viewsets.ModelViewSet):  # H-API-1
    queryset = NotaCreditoVenta.objects.all()
    serializer_class = NotaCreditoVentaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtrar notas de crédito por empresas visibles del usuario"""
        from apps.core.viewsets import get_empresas_visible

        user = self.request.user
        empresas_visibles = get_empresas_visible(user)
        return NotaCreditoVenta.objects.filter(id_empresa__in=empresas_visibles).order_by(
            "-fecha_emision", "-fecha_creacion"
        )


class DetalleNotaCreditoVentaViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = DetalleNotaCreditoVenta.objects.all()
    serializer_class = DetalleNotaCreditoVentaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleNotaCreditoVenta.objects.filter(id_nota_credito__id_empresa__in=_empresas(self.request))


class DevolucionVentaViewSet(TenantFKScopeMixin, EmpresaInjectMixin, viewsets.ModelViewSet):  # H-API-1
    queryset = DevolucionVenta.objects.all()
    serializer_class = DevolucionVentaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtrar devoluciones por empresas visibles del usuario"""
        from apps.core.viewsets import get_empresas_visible

        user = self.request.user
        empresas_visibles = get_empresas_visible(user)
        return DevolucionVenta.objects.filter(id_empresa__in=empresas_visibles).order_by(
            "-fecha_devolucion", "-fecha_creacion"
        )


class DetalleDevolucionVentaViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = DetalleDevolucionVenta.objects.all()
    serializer_class = DetalleDevolucionVentaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleDevolucionVenta.objects.filter(id_devolucion__id_empresa__in=_empresas(self.request))


class CotizacionViewSet(TenantFKScopeMixin, EmpresaInjectMixin, viewsets.ModelViewSet):  # H-API-1
    queryset = Cotizacion.objects.all()
    serializer_class = CotizacionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtrar cotizaciones por empresas visibles del usuario"""
        from apps.core.viewsets import get_empresas_visible

        user = self.request.user
        empresas_visibles = get_empresas_visible(user)
        return Cotizacion.objects.filter(id_empresa__in=empresas_visibles).order_by(
            "-fecha_cotizacion", "-fecha_creacion"
        )

    def perform_create(self, serializer):
        # FE-HIGH-5: el número de cotización se asigna en el backend de forma
        # atómica (select_for_update en siguiente_numero), evitando la condición
        # de carrera del cálculo en el cliente (dos usuarios → mismo número).
        from apps.core.viewsets import get_empresa_primaria
        from apps.fiscal.services import siguiente_numero

        empresa = get_empresa_primaria(self.request.user)
        if empresa is None:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("El usuario no tiene empresa asignada.")
        numero = siguiente_numero(empresa, "COTIZACION")
        serializer.save(id_empresa=empresa, numero_cotizacion=numero)

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        """GET /api/ventas/cotizaciones/{id}/pdf/ — devuelve el PDF de la cotización."""
        from django.http import HttpResponse
        from apps.ventas.pdf_cotizacion import generar_pdf_cotizacion

        cotizacion = self.get_object()
        try:
            pdf_bytes = generar_pdf_cotizacion(cotizacion)
        except ImportError:
            # SEC-M4 (R-CODE-8): no filtrar el detalle interno al cliente.
            logger.exception("Generación de PDF de cotización no disponible")
            return Response(
                {"error": "Generación de PDF no disponible en este servidor."}, status=503
            )

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'inline; filename="cotizacion_{cotizacion.numero_cotizacion}.pdf"'
        )
        return response


class DetalleCotizacionViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = DetalleCotizacion.objects.all()
    serializer_class = DetalleCotizacionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleCotizacion.objects.filter(id_cotizacion__id_empresa__in=_empresas(self.request))


class NotaCreditoFiscalViewSet(TenantFKScopeMixin, EmpresaInjectMixin, viewsets.ModelViewSet):  # H-API-1
    queryset = NotaCreditoFiscal.objects.all()
    serializer_class = NotaCreditoFiscalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtrar notas de crédito fiscal por empresas visibles del usuario"""
        from apps.core.viewsets import get_empresas_visible

        user = self.request.user
        empresas_visibles = get_empresas_visible(user)
        return NotaCreditoFiscal.objects.filter(id_empresa__in=empresas_visibles).order_by(
            "-fecha_emision", "-fecha_creacion"
        )


class DetalleNotaCreditoFiscalViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = DetalleNotaCreditoFiscal.objects.all()
    serializer_class = DetalleNotaCreditoFiscalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleNotaCreditoFiscal.objects.filter(
            id_nota_credito_fiscal__id_empresa__in=_empresas(self.request)
        )


class ListaPrecioViewSet(TenantFKScopeMixin, EmpresaInjectMixin, viewsets.ModelViewSet):  # H-API-1
    queryset = ListaPrecio.objects.all()
    serializer_class = ListaPrecioSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["activo", "es_referencia", "id_empresa"]
    search_fields = ["nombre", "codigo"]
    ordering_fields = ["nombre", "codigo", "fecha_creacion"]
    ordering = ["codigo"]

    def get_queryset(self):
        # R-CODE-1
        return ListaPrecio.objects.filter(id_empresa__in=_empresas(self.request))

    @action(detail=True, methods=["post"], url_path="importar-masivo")
    def importar_masivo(self, request, pk=None):
        """
        Importa precios masivamente desde un CSV.

        Formato esperado del CSV:
            codigo_producto,precio,precio_minimo,vigente_desde,vigente_hasta
            PROD-001,15.50,12.00,2026-01-01,2026-12-31
        """
        import csv
        import io

        lista = self.get_object()
        archivo = request.FILES.get("archivo")

        if not archivo:
            return Response(
                {"error": "Debe adjuntar un archivo CSV en el campo 'archivo'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.inventario.models import Producto

        content = archivo.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))

        creados = 0
        actualizados = 0
        errores = []

        for idx, row in enumerate(reader, start=2):  # start=2 porque fila 1 es cabecera
            codigo = (row.get("codigo_producto") or "").strip()
            if not codigo:
                errores.append({"fila": idx, "error": "codigo_producto vacío"})
                continue

            try:
                producto = Producto.objects.get(codigo_producto=codigo, id_empresa=lista.id_empresa)
            except Producto.DoesNotExist:
                errores.append({"fila": idx, "error": f"Producto '{codigo}' no encontrado en esta empresa"})
                continue
            except Exception as exc:
                errores.append({"fila": idx, "error": str(exc)})
                continue

            try:
                precio = Decimal(str(row.get("precio", 0) or 0))
                precio_minimo = Decimal(str(row.get("precio_minimo", 0) or 0))
                vigente_desde = row.get("vigente_desde") or None
                vigente_hasta = row.get("vigente_hasta") or None

                detalle, created = DetallePrecio.objects.update_or_create(
                    id_lista=lista,
                    id_producto=producto,
                    defaults={
                        "precio": precio,
                        "precio_minimo": precio_minimo,
                        "vigente_desde": vigente_desde,
                        "vigente_hasta": vigente_hasta,
                        "activo": True,
                    },
                )
                if created:
                    creados += 1
                else:
                    actualizados += 1
            except Exception as exc:
                errores.append({"fila": idx, "error": str(exc)})

        return Response(
            {
                "lista": str(lista),
                "creados": creados,
                "actualizados": actualizados,
                "errores": errores,
                "total_errores": len(errores),
            },
            status=status.HTTP_200_OK if not errores else status.HTTP_207_MULTI_STATUS,
        )


class DetallePrecioViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = DetallePrecio.objects.all()
    serializer_class = DetallePrecioSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["activo", "id_lista", "id_producto"]
    ordering_fields = ["id_lista", "id_producto"]
    ordering = ["id_lista"]

    def get_queryset(self):
        # R-CODE-1 via ListaPrecio → id_empresa
        return DetallePrecio.objects.filter(id_lista__id_empresa__in=_empresas(self.request))


# ── Comisiones de vendedores (1.G) ────────────────────────────────────────────


class EsquemaComisionViewSet(TenantFKScopeMixin, EmpresaInjectMixin, viewsets.ModelViewSet):
    """
    CRUD de esquemas de comisión por vendedor.

    GET/POST  /api/ventas/esquemas-comision/
    El % base aplica al subtotal sin impuestos; overrides por categoría en
    /api/ventas/esquemas-comision-categorias/.
    """

    queryset = EsquemaComision.objects.all()
    serializer_class = EsquemaComisionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1
        return (
            EsquemaComision.objects.filter(id_empresa__in=_empresas(self.request))
            .select_related("vendedor")
            .prefetch_related("overrides_categoria__categoria")
            .order_by("-fecha_creacion")
        )


class EsquemaComisionCategoriaViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    """Overrides de % por categoría de producto de un esquema de comisión."""

    queryset = EsquemaComisionCategoria.objects.all()
    serializer_class = EsquemaComisionCategoriaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1 via EsquemaComision → id_empresa
        return EsquemaComisionCategoria.objects.filter(
            esquema__id_empresa__in=_empresas(self.request)
        ).select_related("categoria", "esquema")


class ComisionVentaViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Consulta de comisiones devengadas/liquidadas/anuladas + liquidación.

    GET  /api/ventas/comisiones/?vendedor=&estado=&desde=&hasta=
    GET  /api/ventas/comisiones/resumen/   (mismos filtros, agregado por vendedor)
    POST /api/ventas/comisiones/liquidar/  {vendedor, desde, hasta}

    Solo lectura por diseño: las comisiones nacen al entregar la venta
    (services.devengar_comision_venta) y solo mutan vía /liquidar/ o por la
    anulación de la venta.
    """

    queryset = ComisionVenta.objects.all()
    serializer_class = ComisionVentaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        from rest_framework.fields import DateField

        # R-CODE-1
        qs = (
            ComisionVenta.objects.filter(id_empresa__in=_empresas(self.request))
            .select_related("vendedor", "nota_venta")
            .order_by("-fecha_devengo", "-fecha_creacion")
        )
        params = self.request.query_params
        if params.get("vendedor"):
            import uuid as uuid_mod

            try:
                qs = qs.filter(vendedor=uuid_mod.UUID(params["vendedor"]))
            except ValueError as exc:
                raise ValidationError({"vendedor": "UUID inválido."}) from exc
        if params.get("estado"):
            qs = qs.filter(estado=params["estado"].upper())
        for nombre, lookup in (("desde", "fecha_devengo__gte"), ("hasta", "fecha_devengo__lte")):
            valor = params.get(nombre)
            if valor:
                try:
                    qs = qs.filter(**{lookup: DateField().to_internal_value(valor)})
                except ValidationError as exc:
                    raise ValidationError({nombre: "Fecha inválida (use YYYY-MM-DD)."}) from exc
        return qs

    @action(detail=False, methods=["get"], url_path="resumen")
    def resumen(self, request):
        """
        Totales por vendedor y estado para el período filtrado (R-CODE-4: los
        montos viajan como string, nunca float).
        """
        from django.db.models import Count, Sum

        filas = (
            self.get_queryset()
            # .order_by() limpia el ordering del queryset: si quedara, Django lo
            # suma al GROUP BY y parte los grupos por fecha (filas duplicadas).
            .order_by()
            .values("vendedor", "vendedor__username", "estado")
            .annotate(total=Sum("monto"), cantidad=Count("id_comision_venta"))
        )
        resumen: dict[str, dict] = {}
        for fila in filas:
            clave = str(fila["vendedor"])
            vendedor = resumen.setdefault(
                clave,
                {
                    "vendedor": clave,
                    "vendedor_username": fila["vendedor__username"],
                    "devengada": "0",
                    "liquidada": "0",
                    "anulada": "0",
                    "cantidad": 0,
                },
            )
            vendedor[fila["estado"].lower()] = str(fila["total"] or Decimal("0"))
            vendedor["cantidad"] += fila["cantidad"]
        return Response({"resultados": list(resumen.values())})

    @idempotent("ventas:comisiones-liquidar")
    @action(detail=False, methods=["post"], url_path="liquidar")
    def liquidar(self, request):
        """
        POST /api/ventas/comisiones/liquidar/
        Body: {"vendedor": uuid, "desde": "YYYY-MM-DD", "hasta": "YYYY-MM-DD"}

        Marca DEVENGADA → LIQUIDADA las comisiones del vendedor en el período.
        Idempotente vía cabecera ``Idempotency-Key`` (un reintento devuelve la
        misma respuesta sin re-liquidar) y, de fondo, naturalmente idempotente:
        una segunda corrida del mismo rango encuentra 0 pendientes.
        """
        from django.contrib.auth import get_user_model

        from .services import VentaError, liquidar_comisiones

        entrada = LiquidarComisionesInputSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)

        empresas = _empresas(request)
        # R-CODE-1: el vendedor debe pertenecer a una empresa visible.
        vendedor = (
            get_user_model()
            .objects.filter(pk=entrada.validated_data["vendedor"], empresas__in=empresas)
            .distinct()
            .first()
        )
        if vendedor is None:
            raise ValidationError({"vendedor": "Vendedor no encontrado en sus empresas."})

        try:
            resultado = liquidar_comisiones(
                empresas=empresas,
                vendedor=vendedor,
                desde=entrada.validated_data["desde"],
                hasta=entrada.validated_data["hasta"],
                usuario=request.user,
            )
        except VentaError as exc:
            raise ValidationError(str(exc)) from exc

        return Response(
            {
                "vendedor": str(vendedor.pk),
                "desde": str(entrada.validated_data["desde"]),
                "hasta": str(entrada.validated_data["hasta"]),
                "liquidadas": resultado["liquidadas"],
                "monto_total": str(resultado["monto_total"]),
            },
            status=status.HTTP_200_OK,
        )
