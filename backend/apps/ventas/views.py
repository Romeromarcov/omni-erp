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
    FacturaFiscal,
    ListaPrecio,
    NotaCreditoFiscal,
    NotaCreditoVenta,
    NotaVenta,
    Pedido,
)
from .serializers import (
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
    FacturaFiscalSerializer,
    ListaPrecioSerializer,
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
        qs = NotaVenta.objects.filter(id_empresa__in=_empresas(self.request)).order_by("-fecha_creacion")
        # POS devoluciones (1.G): búsqueda de la venta original por número exacto.
        numero = self.request.query_params.get("numero_nota")
        if numero:
            qs = qs.filter(numero_nota__iexact=numero.strip())
        return qs

    @idempotent("ventas:devolver")
    @action(detail=True, methods=["post"], url_path="devolver")
    def devolver(self, request, pk=None):
        """
        POST /api/ventas/notas-venta/{pk}/devolver/   (1.G — devolución POS)

        Body:
            {
              "almacen_id": "uuid",            # almacén que recibe el stock
              "id_metodo_pago": "uuid",        # método con el que se reembolsa
              "lineas": [{"id_detalle": "uuid", "cantidad": "2"}, ...],
              "motivo": "CAMBIO_CLIENTE",      # opcional (choice de DevolucionVenta)
              "observaciones": "..."           # opcional
            }

        Atómico (R-CODE-11): reingreso de stock + nota de crédito (fiscal si la
        venta fue fiscal) + Pago EGRESO en la caja de la sesión abierta del
        cajero + asiento de reverso. Idempotente con ``Idempotency-Key``: un
        reintento con la misma clave no duplica la devolución (es dinero).
        """
        from apps.almacenes.models import Almacen
        from apps.finanzas.models import MetodoPago
        from django.db import models as dj_models

        from .services import VentaError, registrar_devolucion_pos

        nota = self.get_object()

        almacen_id = request.data.get("almacen_id")
        if not almacen_id:
            raise ValidationError({"almacen_id": "Este campo es requerido."})
        try:
            almacen = Almacen.objects.get(pk=almacen_id, id_empresa=nota.id_empresa)
        except Almacen.DoesNotExist:
            raise ValidationError({"almacen_id": "Almacén no encontrado en esta empresa."})

        metodo_id = request.data.get("id_metodo_pago")
        if not metodo_id:
            raise ValidationError({"id_metodo_pago": "Este campo es requerido."})
        # R-CODE-1: método propio de la empresa, genérico global o público.
        metodo = (
            MetodoPago.objects.filter(pk=metodo_id, activo=True)
            .filter(
                dj_models.Q(empresa=nota.id_empresa)
                | dj_models.Q(empresa__isnull=True)
                | dj_models.Q(es_publico=True)
            )
            .first()
        )
        if metodo is None:
            raise ValidationError({"id_metodo_pago": "Método de pago no disponible en esta empresa."})

        lineas = request.data.get("lineas")
        if not isinstance(lineas, list) or not lineas:
            raise ValidationError({"lineas": "Indica al menos una línea a devolver."})

        kwargs_devolucion = {}
        if request.data.get("motivo"):
            kwargs_devolucion["motivo"] = request.data["motivo"]

        try:
            resultado = registrar_devolucion_pos(
                nota_venta=nota,
                lineas=lineas,
                almacen=almacen,
                usuario=request.user,
                metodo_pago=metodo,
                observaciones=request.data.get("observaciones") or None,
                **kwargs_devolucion,
            )
        except VentaError as exc:
            raise ValidationError(str(exc)) from exc

        devolucion = resultado["devolucion"]
        ncf = resultado["nota_credito_fiscal"]
        ncv = resultado["nota_credito_venta"]
        # R-CODE-4: el dinero viaja como string, nunca float.
        return Response(
            {
                "devolucion": {
                    "id_devolucion": str(devolucion.id_devolucion),
                    "numero_devolucion": devolucion.numero_devolucion,
                    "fecha_devolucion": str(devolucion.fecha_devolucion),
                    "estado": devolucion.estado,
                    "motivo": devolucion.motivo_devolucion,
                    "monto_total": str(devolucion.monto_total),
                },
                "nota_credito_fiscal": (
                    {
                        "id_nota_credito_fiscal": str(ncf.id_nota_credito_fiscal),
                        "numero_nota_credito": ncf.numero_nota_credito,
                        "numero_control": ncf.numero_control,
                        "base_imponible": str(ncf.base_imponible),
                        "monto_iva": str(ncf.monto_iva),
                        "monto_total": str(ncf.monto_total),
                    }
                    if ncf
                    else None
                ),
                "nota_credito_venta": (
                    {
                        "id_nota_credito": str(ncv.id_nota_credito),
                        "numero_nota_credito": ncv.numero_nota_credito,
                        "monto_total": str(ncv.monto_total),
                    }
                    if ncv
                    else None
                ),
                "pago_id": str(resultado["pago"].id_pago),
                "monto_reembolsado": str(resultado["pago"].monto),
                "caja_fisica": resultado["sesion_caja"].caja_fisica.nombre,
                "movimientos_inventario": len(resultado["movimientos"]),
                "asiento_id": str(resultado["asiento"].pk) if resultado["asiento"] else None,
                "asiento_iva_id": str(resultado["asiento_iva"].pk) if resultado["asiento_iva"] else None,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="devoluciones")
    def devoluciones(self, request, pk=None):
        """
        GET /api/ventas/notas-venta/{pk}/devoluciones/   (1.G — devolución POS)

        Devuelve las devoluciones de la venta y el estado devolvible por línea
        (vendido / ya devuelto / disponible) para que el POS limite cantidades.
        """
        from .services import _cantidades_devueltas_por_producto, _factura_de_la_venta

        nota = self.get_object()
        detalles = list(nota.detalles.select_related("id_producto"))
        devuelto_por_producto = dict(_cantidades_devueltas_por_producto(nota))

        lineas = []
        for d in detalles:
            ya = devuelto_por_producto.get(d.id_producto_id, Decimal("0"))
            # Reparto voraz del acumulado devuelto entre líneas del mismo producto
            # (el POS normalmente consolida una línea por producto).
            devuelta_linea = min(d.cantidad, ya)
            devuelto_por_producto[d.id_producto_id] = ya - devuelta_linea
            lineas.append(
                {
                    "id_detalle": str(d.id_detalle_nota_venta),
                    "id_producto": str(d.id_producto_id),
                    "nombre_producto": d.id_producto.nombre_producto,
                    "sku": getattr(d.id_producto, "sku", "") or "",
                    "precio_unitario": str(d.precio_unitario),
                    "cantidad_vendida": str(d.cantidad),
                    "cantidad_devuelta": str(devuelta_linea),
                    "cantidad_disponible": str(d.cantidad - devuelta_linea),
                }
            )

        factura = _factura_de_la_venta(nota)
        devoluciones = [
            {
                "id_devolucion": str(dev.id_devolucion),
                "numero_devolucion": dev.numero_devolucion,
                "fecha_devolucion": str(dev.fecha_devolucion),
                "motivo": dev.motivo_devolucion,
                "estado": dev.estado,
                "monto_total": str(dev.monto_total),
            }
            for dev in nota.devoluciones.order_by("fecha_creacion")
        ]
        return Response(
            {
                "venta": {
                    "id_nota_venta": str(nota.id_nota_venta),
                    "numero_nota": nota.numero_nota,
                    "estado": nota.estado,
                    "fecha_nota": str(nota.fecha_nota),
                    "fiscal": factura is not None,
                    "numero_factura": factura.numero_factura if factura else None,
                },
                "lineas": lineas,
                "devoluciones": devoluciones,
            }
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
