import logging
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import Prefetch
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.exceptions import DomainError, domain_error_response
from apps.core.idempotency import IdempotentCreateMixin, idempotent
from apps.core.serializer_mixins import TenantFKScopeMixin
from apps.core.viewsets import (
    EmpresaInjectMixin,
    NulSafeFilterMixin,
    filtrar_ambito_queryset,
    get_empresas_visible,
)

from .models import (
    ComisionVenta,
    Cotizacion,
    DetalleCotizacion,
    DetalleDevolucionVenta,
    DetalleFacturaFiscal,
    DetalleNotaCreditoFiscal,
    DetalleNotaCreditoVenta,
    DetalleNotaDebitoFiscal,
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
    NotaDebitoFiscal,
    NotaVenta,
    Pedido,
    ReglaPrecioDinamico,
)
from .serializers import (
    ComisionVentaSerializer,
    CotizacionSerializer,
    CotizarPrecioDinamicoInputSerializer,
    DetalleCotizacionSerializer,
    DetalleDevolucionVentaSerializer,
    DetalleFacturaFiscalSerializer,
    DetalleNotaCreditoFiscalSerializer,
    DetalleNotaCreditoVentaSerializer,
    DetalleNotaDebitoFiscalSerializer,
    DetalleNotaVentaSerializer,
    DetallePedidoSerializer,
    DetallePrecioSerializer,
    DevengarComisionCobroInputSerializer,
    DevolucionVentaSerializer,
    EsquemaComisionCategoriaSerializer,
    EsquemaComisionSerializer,
    FacturaFiscalSerializer,
    ListaPrecioSerializer,
    LiquidarComisionesInputSerializer,
    NotaCreditoFiscalSerializer,
    NotaCreditoVentaSerializer,
    NotaDebitoFiscalSerializer,
    NotaVentaSerializer,
    PedidoSerializer,
    ReglaPrecioDinamicoSerializer,
)

logger = logging.getLogger(__name__)


def _empresas(request):
    """Shortcut: devuelve empresas visibles para el usuario del request."""
    return get_empresas_visible(request.user)


class PedidoViewSet(TenantFKScopeMixin, EmpresaInjectMixin, viewsets.ModelViewSet):  # H-API-1
    queryset = Pedido.objects.all()
    serializer_class = PedidoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtrar pedidos por empresas visibles del usuario"""
        from apps.core.viewsets import get_empresas_visible

        user = self.request.user
        empresas_visibles = get_empresas_visible(user)
        return (
            Pedido.objects.filter(id_empresa__in=empresas_visibles)
            .select_related("id_cliente", "id_vendedor")
            .prefetch_related(Prefetch("detalles", queryset=DetallePedido.objects.select_related("id_producto")))
            .order_by("-fecha_pedido", "-fecha_creacion")
        )

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

        omitir_bloqueo = bool(request.data.get("omitir_bloqueo_credito", False))
        if omitir_bloqueo and not (
            getattr(request.user, "es_superusuario_omni", False) or getattr(request.user, "is_staff", False)
        ):
            return domain_error_response(
                DomainError("Solo administradores pueden omitir el bloqueo de crédito."),
                status_code=status.HTTP_403_FORBIDDEN,
                extra={"codigo": "CREDITO_OVERRIDE_DENEGADO"},
            )

        try:
            resultado = confirmar_pedido(
                pedido=pedido,
                almacen=almacen,
                usuario=request.user,
                generar_cxc=generar_cxc,
                validar_credito=bool(request.data.get("validar_credito", False)),
                omitir_bloqueo_credito=omitir_bloqueo,
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

    @action(detail=True, methods=["get"], url_path="evaluar-credito")
    def evaluar_credito(self, request, pk=None):
        """GET /api/ventas/pedidos/{pk}/evaluar-credito/ — Evalúa mora real y límite del cliente."""
        from .services_credito import evaluar_credito_cliente

        pedido = self.get_object()
        subtotal = sum((Decimal(str(d.subtotal)) for d in pedido.detalles.all()), Decimal("0"))
        ev = evaluar_credito_cliente(pedido.id_cliente, pedido.id_empresa, monto_nuevo=subtotal)
        return Response(
            {
                "pedido_id": str(pedido.id_pedido),
                "cliente_id": ev["cliente_id"],
                "monto_pedido": str(subtotal),
                "saldo_pendiente": str(ev["saldo_pendiente"]),
                "monto_vencido": str(ev["monto_vencido"]),
                "cxc_vencidas": ev["cxc_vencidas"],
                "dias_mora_max": ev["dias_mora_max"],
                "limite_credito": str(ev["limite_credito"]),
                "credito_disponible": str(ev["credito_disponible"]) if ev["credito_disponible"] is not None else None,
                "bloqueado_por_mora": ev["bloqueado_por_mora"],
                "excede_limite": ev["excede_limite"],
                "bloqueado": ev["bloqueado"],
                "motivo_bloqueo": ev["motivo_bloqueo"],
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
        qs = (
            NotaVenta.objects.filter(id_empresa__in=_empresas(self.request))
            .select_related("id_cliente")
            .order_by("-fecha_creacion")
        )
        # POS devoluciones (1.G): búsqueda de la venta original por número exacto.
        numero = self.request.query_params.get("numero_nota")
        if numero:
            if "\x00" in numero:
                raise ValidationError("Parámetro 'numero_nota' inválido.")
            qs = qs.filter(numero_nota__iexact=numero.strip())
        return filtrar_ambito_queryset(qs, self.request)

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
                dj_models.Q(empresa=nota.id_empresa) | dj_models.Q(empresa__isnull=True) | dj_models.Q(es_publico=True)
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
            resultado = emitir_factura_fiscal(nota, usuario=request.user)
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
        return (
            FacturaFiscal.objects.filter(id_empresa__in=empresas_visibles)
            .select_related("id_cliente")
            .order_by("-fecha_emision", "-fecha_creacion")
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
            return Response({"error": "Generación de PDF no disponible en este servidor."}, status=503)

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="factura_{factura.numero_factura}.pdf"'
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
        return (
            NotaCreditoVenta.objects.filter(id_empresa__in=empresas_visibles)
            .select_related("id_cliente")
            .order_by("-fecha_emision", "-fecha_creacion")
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
        return (
            DevolucionVenta.objects.filter(id_empresa__in=empresas_visibles)
            .select_related("id_cliente")
            .order_by("-fecha_devolucion", "-fecha_creacion")
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
        return (
            Cotizacion.objects.filter(id_empresa__in=empresas_visibles)
            .select_related("id_cliente")
            .order_by("-fecha_cotizacion", "-fecha_creacion")
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
            return Response({"error": "Generación de PDF no disponible en este servidor."}, status=503)

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="cotizacion_{cotizacion.numero_cotizacion}.pdf"'
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
        return (
            NotaCreditoFiscal.objects.filter(id_empresa__in=empresas_visibles)
            .select_related("id_cliente")
            .order_by("-fecha_emision", "-fecha_creacion")
        )


class DetalleNotaCreditoFiscalViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = DetalleNotaCreditoFiscal.objects.all()
    serializer_class = DetalleNotaCreditoFiscalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleNotaCreditoFiscal.objects.filter(id_nota_credito_fiscal__id_empresa__in=_empresas(self.request))


class NotaDebitoFiscalViewSet(NulSafeFilterMixin, TenantFKScopeMixin, EmpresaInjectMixin, viewsets.ModelViewSet):
    queryset = NotaDebitoFiscal.objects.all()
    serializer_class = NotaDebitoFiscalSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["estado", "motivo", "ambito", "id_cliente", "id_factura_origen"]
    search_fields = ["numero_nota_debito", "numero_control", "observaciones"]
    ordering_fields = ["fecha_emision", "monto_total", "fecha_creacion"]

    def get_queryset(self):
        # R-CODE-1
        qs = (
            NotaDebitoFiscal.objects.filter(id_empresa__in=_empresas(self.request))
            .select_related("id_cliente", "id_factura_origen")
            .order_by("-fecha_emision", "-fecha_creacion")
        )
        return filtrar_ambito_queryset(qs, self.request)

    def update(self, request, *args, **kwargs):
        if self.get_object().estado != "BORRADOR":
            return domain_error_response(
                DomainError("No se puede modificar ni eliminar una nota de débito fiscal fuera de BORRADOR."),
                status_code=status.HTTP_400_BAD_REQUEST,
                extra={"codigo": "NOTA_DEBITO_INMUTABLE"},
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if self.get_object().estado != "BORRADOR":
            return domain_error_response(
                DomainError("No se puede modificar ni eliminar una nota de débito fiscal fuera de BORRADOR."),
                status_code=status.HTTP_400_BAD_REQUEST,
                extra={"codigo": "NOTA_DEBITO_INMUTABLE"},
            )
        return super().destroy(request, *args, **kwargs)

    @idempotent("ventas:emitir-nota-debito")
    @action(detail=True, methods=["post"], url_path="emitir")
    def emitir(self, request, pk=None):
        """
        POST /api/ventas/notas-debito-fiscales/{pk}/emitir/

        Emite la Nota de Débito Fiscal generando correlativo SENIAT ``NOTA_DEBITO``,
        CxC adicional y asientos contables ``NOTA_DEBITO_FISCAL`` / ``NOTA_DEBITO_FISCAL_IVA``.
        """
        from .services import VentaError, emitir_nota_debito_fiscal

        nota_debito = self.get_object()
        try:
            resultado = emitir_nota_debito_fiscal(nota_debito, usuario=request.user)
        except VentaError as exc:
            return domain_error_response(
                exc,
                status_code=status.HTTP_400_BAD_REQUEST,
                extra={"codigo": "NOTA_DEBITO_ERROR"},
            )

        return Response(
            {
                "nota_debito": NotaDebitoFiscalSerializer(resultado["nota_debito"]).data,
                "cxc_id": str(resultado["cxc"].pk),
                "asiento_id": str(resultado["asiento"].pk) if resultado["asiento"] else None,
                "asiento_iva_id": str(resultado["asiento_iva"].pk) if resultado["asiento_iva"] else None,
            },
            status=status.HTTP_200_OK,
        )


class DetalleNotaDebitoFiscalViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = DetalleNotaDebitoFiscal.objects.all()
    serializer_class = DetalleNotaDebitoFiscalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleNotaDebitoFiscal.objects.filter(id_nota_debito_fiscal__id_empresa__in=_empresas(self.request))

    def update(self, request, *args, **kwargs):
        if self.get_object().id_nota_debito_fiscal.estado != "BORRADOR":
            return domain_error_response(
                DomainError("No se pueden modificar detalles de una nota de débito fiscal fuera de BORRADOR."),
                status_code=status.HTTP_400_BAD_REQUEST,
                extra={"codigo": "NOTA_DEBITO_INMUTABLE"},
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if self.get_object().id_nota_debito_fiscal.estado != "BORRADOR":
            return domain_error_response(
                DomainError("No se pueden eliminar detalles de una nota de débito fiscal fuera de BORRADOR."),
                status_code=status.HTTP_400_BAD_REQUEST,
                extra={"codigo": "NOTA_DEBITO_INMUTABLE"},
            )
        return super().destroy(request, *args, **kwargs)


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
            except (Producto.MultipleObjectsReturned, ValueError):
                errores.append(
                    {
                        "fila": idx,
                        "error": "El código de producto es inválido o coincide con más de un producto.",
                    }
                )
                continue
            except Exception:
                logger.exception(
                    "Error inesperado al buscar el producto en la fila %s de importación de precios",
                    idx,
                )
                errores.append({"fila": idx, "error": "Error inesperado al buscar el producto."})
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
            except (
                InvalidOperation,
                ValueError,
                DjangoValidationError,
                ValidationError,
                IntegrityError,
            ) as exc:
                msg = (
                    "Precio o precio mínimo numérico inválido."
                    if isinstance(exc, InvalidOperation)
                    else "Datos inválidos o conflicto al registrar el precio."
                )
                errores.append({"fila": idx, "error": msg})
            except Exception:
                logger.exception(
                    "Error inesperado al procesar la fila %s de importación de precios",
                    idx,
                )
                errores.append({"fila": idx, "error": "Error inesperado al procesar la fila."})

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


class ReglaPrecioDinamicoViewSet(NulSafeFilterMixin, TenantFKScopeMixin, EmpresaInjectMixin, viewsets.ModelViewSet):
    """Reglas componibles de precios dinámicos por brecha cambiaria, moneda de pago, zona, segmento y volumen."""

    queryset = ReglaPrecioDinamico.objects.all()
    serializer_class = ReglaPrecioDinamicoSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["activo", "tipo_factor", "modo_calculo"]
    search_fields = ["codigo", "nombre", "clave_condicion"]
    ordering_fields = ["prioridad", "codigo", "fecha_creacion"]
    ordering = ["prioridad"]

    def get_queryset(self):
        # R-CODE-1
        return ReglaPrecioDinamico.objects.filter(id_empresa__in=_empresas(self.request)).order_by(
            "prioridad", "fecha_creacion"
        )

    @action(detail=False, methods=["post"], url_path="cotizar")
    def cotizar(self, request):
        """POST /api/ventas/reglas-precio-dinamico/cotizar/ — Simula precio dinámico + equivalencias trimonetarias."""
        from apps.core.models import Contacto
        from apps.core.viewsets import get_empresa_primaria
        from apps.inventario.models import Producto

        from .services import VentaError
        from .services_precios import calcular_precio_dinamico

        entrada = CotizarPrecioDinamicoInputSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        vd = entrada.validated_data

        empresas = _empresas(request)
        empresa = get_empresa_primaria(request.user)
        if empresa is None:
            raise ValidationError({"empresa": "El usuario no tiene empresa asignada."})
        producto = Producto.objects.filter(pk=vd["id_producto"], id_empresa__in=empresas).first()
        if producto is None:
            raise ValidationError({"id_producto": "Producto no encontrado en sus empresas."})

        empresa_target = producto.id_empresa or empresa
        contacto = None
        if vd.get("id_contacto"):
            contacto = Contacto.objects.filter(pk=vd["id_contacto"], id_empresa=empresa_target).first()
            if contacto is None:
                raise ValidationError({"id_contacto": "Contacto no encontrado en la empresa del producto."})

        try:
            res = calcular_precio_dinamico(
                producto,
                empresa_target,
                contacto=contacto,
                cantidad=vd["cantidad"],
                moneda_pago=vd.get("moneda_pago", "USD"),
                zona=vd.get("zona", ""),
                segmento=vd.get("segmento", ""),
                fecha=vd.get("fecha"),
                tipo_tasa_referencia=vd.get("tipo_tasa_referencia") or None,
            )
        except VentaError as exc:
            return domain_error_response(
                exc, status_code=status.HTTP_400_BAD_REQUEST, extra={"codigo": "PRECIO_ERROR"}
            )

        eq = res["equivalencias"]
        eq_out = None
        if eq is not None:
            eq_out = {
                "moneda_base_iso": eq["moneda_base_iso"],
                "monto_base": str(eq["monto_base"]) if eq["monto_base"] is not None else None,
                "moneda_pais_iso": eq["moneda_pais_iso"],
                "monto_pais_fiscal": str(eq["monto_pais_fiscal"]) if eq["monto_pais_fiscal"] is not None else None,
                "moneda_referencia_iso": eq["moneda_referencia_iso"],
                "monto_referencia": str(eq["monto_referencia"]) if eq["monto_referencia"] is not None else None,
            }

        return Response(
            {
                "producto_id": res["producto_id"],
                "cantidad": str(res["cantidad"]),
                "moneda_pago": res["moneda_pago"],
                "zona": res["zona"],
                "segmento": res["segmento"],
                "precio_base": str(res["precio_base"]),
                "precio_final": str(res["precio_final"]),
                "total_linea": str(res["total_linea"]),
                "precio_minimo_aplicado": res["precio_minimo_aplicado"],
                "descuento_recargo_pct": str(res["descuento_recargo_pct"]),
                "brecha_cambiaria_pct": str(res["brecha_cambiaria_pct"])
                if res["brecha_cambiaria_pct"] is not None
                else None,
                "reglas_aplicadas": res["reglas_aplicadas"],
                "equivalencias": eq_out,
            },
            status=status.HTTP_200_OK,
        )


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
        return EsquemaComisionCategoria.objects.filter(esquema__id_empresa__in=_empresas(self.request)).select_related(
            "categoria", "esquema"
        )


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

    @idempotent("ventas:comisiones-devengar-cobro")
    @action(detail=False, methods=["post"], url_path="devengar-cobro")
    def devengar_cobro(self, request):
        """POST /api/ventas/comisiones/devengar-cobro/ — Devenga comisión sobre cobro efectivo."""
        from apps.finanzas.models import Pago

        from .services import VentaError, devengar_comision_por_cobro

        entrada = DevengarComisionCobroInputSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        vd = entrada.validated_data

        empresas = _empresas(request)
        nota = NotaVenta.objects.filter(pk=vd["id_nota_venta"], id_empresa__in=empresas).first()
        if nota is None:
            raise ValidationError({"id_nota_venta": "Nota de venta no encontrada en sus empresas."})

        pago = None
        if vd.get("id_pago"):
            pago = Pago.objects.filter(pk=vd["id_pago"], id_empresa__in=empresas).first()
            if pago is None:
                raise ValidationError({"id_pago": "Pago no encontrado en sus empresas."})

        try:
            comision = devengar_comision_por_cobro(
                nota,
                pago=pago,
                moneda_cobro_iso=vd.get("moneda_cobro_iso") or None,
                fecha_cobro=vd.get("fecha_cobro"),
            )
        except VentaError as exc:
            return domain_error_response(
                exc, status_code=status.HTTP_400_BAD_REQUEST, extra={"codigo": "COMISION_ERROR"}
            )

        return Response(
            {
                "devengada": comision is not None,
                "comision": ComisionVentaSerializer(comision).data if comision is not None else None,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="avance-meta")
    def avance_meta(self, request):
        """GET /api/ventas/comisiones/avance-meta/?vendedor=&anio=&mes= — Cumplimiento mensual del vendedor."""
        import uuid as uuid_mod
        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from apps.core.viewsets import get_empresa_primaria

        from .services import calcular_avance_meta_vendedor

        empresas = _empresas(request)
        empresa = get_empresa_primaria(request.user)
        if empresa is None:
            raise ValidationError({"empresa": "El usuario no tiene empresa asignada."})
        vendedor_raw = request.query_params.get("vendedor")
        if vendedor_raw:
            try:
                vendedor_uuid = uuid_mod.UUID(vendedor_raw)
            except ValueError as exc:
                raise ValidationError({"vendedor": "UUID inválido."}) from exc
            vendedor = get_user_model().objects.filter(pk=vendedor_uuid, empresas__in=empresas).distinct().first()
            if vendedor is None:
                raise ValidationError({"vendedor": "Vendedor no encontrado en sus empresas."})
        else:
            vendedor = request.user

        hoy = timezone.localdate()
        try:
            anio = int(request.query_params.get("anio", hoy.year))
            mes = int(request.query_params.get("mes", hoy.month))
            if not (1 <= mes <= 12):
                raise ValueError("mes fuera de 1..12")
        except (TypeError, ValueError) as exc:
            raise ValidationError({"periodo": "Parámetros 'anio' y 'mes' inválidos."}) from exc

        res = calcular_avance_meta_vendedor(empresa, vendedor, anio, mes)
        return Response(
            {
                "vendedor": res["vendedor"],
                "anio": res["anio"],
                "mes": res["mes"],
                "meta_mensual_monto": str(res["meta_mensual_monto"]),
                "bono_meta_porcentaje": str(res["bono_meta_porcentaje"]),
                "acumulado_mes": str(res["acumulado_mes"]),
                "comision_total": str(res["comision_total"]),
                "cantidad_ventas": res["cantidad_ventas"],
                "porcentaje_cumplimiento": str(res["porcentaje_cumplimiento"]),
                "meta_alcanzada": res["meta_alcanzada"],
            },
            status=status.HTTP_200_OK,
        )
