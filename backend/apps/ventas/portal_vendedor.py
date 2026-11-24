"""Portal / App Independiente de Vendedores SFA (Plan 09 Fase 7.2).

Provee:
- ``GET /api/ventas/portal-vendedor/cartera/``: clientes asignados con saldo CxC y mora real.
- ``GET /api/ventas/portal-vendedor/catalogo/``: catálogo vendible con stock disponible y precios trimonetarios.
- ``POST /api/ventas/portal-vendedor/checkin/``: check-in GPS con cálculo de distancia Haversine al cliente.
- ``POST /api/ventas/portal-vendedor/pedidos/``: levantamiento rápido de pedido móvil/offline-capable.
- ``POST /api/ventas/portal-vendedor/cobros/``: captura en campo de comprobante de cobro.
- ``GET /api/ventas/portal-vendedor/metas-comisiones/``: resumen de comisiones devengadas/liquidadas y metas.
"""

from __future__ import annotations

import logging
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from drf_yasg.utils import swagger_auto_schema
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.exceptions import domain_error_response
from apps.core.idempotency import idempotent
from apps.core.throttling import EscrituraRateThrottle
from apps.core.viewsets import get_empresa_primaria, get_empresas_visible, validar_uuid_param
from apps.crm.models import Cliente, DireccionCliente, VisitaGPSVendedor
from apps.cuentas_por_cobrar.models import CuentaPorCobrar
from apps.despacho.services_vrp import distancia_haversine_km
from apps.finanzas.models import MetodoPago, Moneda
from apps.finanzas.services import TasaCambioError
from apps.finanzas.services_trimonetario import calcular_equivalencias_trimonetarias
from apps.inventario.models import Producto, StockActual

from .models import ComisionVenta, DetallePedido, EsquemaComision, PagoPortalCliente, Pedido
from .services import obtener_precio

logger = logging.getLogger(__name__)

_Q4 = Decimal("0.0001")
_Q2 = Decimal("0.01")
_CERO = Decimal("0")


class PortalVendedorError(Exception):
    """Error de dominio en el Portal de Vendedores SFA."""


def _no_nul(valor: str | None, campo: str) -> str | None:
    if valor is None or valor == "":
        return None
    if "\x00" in str(valor):
        raise ValidationError({campo: "Parámetro inválido."})
    return str(valor).strip()


def _resolver_empresa_vendedor(request):
    visibles = get_empresas_visible(request.user)
    raw_emp = request.data.get("id_empresa") if isinstance(request.data, dict) else None
    raw_emp = raw_emp or request.query_params.get("empresa")
    if raw_emp:
        uid = validar_uuid_param(str(raw_emp), "id_empresa")
        emp = visibles.filter(pk=uid).first()
        if emp is None:
            raise ValidationError({"id_empresa": "Empresa fuera de su alcance."})
        return emp
    emp = get_empresa_primaria(request.user) or visibles.first()
    if emp is None:
        raise ValidationError({"id_empresa": "Usuario sin empresa asignada."})
    return emp


def _equivalencias_seguras(monto: Decimal, moneda_origen: Moneda | None, empresa) -> dict[str, Any]:
    if moneda_origen is None:
        return {"monto_origen": str(monto.quantize(_Q4, rounding=ROUND_HALF_UP))}
    try:
        eq = calcular_equivalencias_trimonetarias(monto, moneda_origen, empresa=empresa)
        return {
            "base": str(eq["monto_base"]) if eq.get("monto_base") is not None else None,
            "base_iso": eq.get("moneda_base_iso"),
            "pais_fiscal": str(eq["monto_pais_fiscal"]) if eq.get("monto_pais_fiscal") is not None else None,
            "pais_fiscal_iso": eq.get("moneda_pais_iso"),
            "referencia": str(eq["monto_referencia"]) if eq.get("monto_referencia") is not None else None,
            "referencia_iso": eq.get("moneda_referencia_iso"),
        }
    except (TasaCambioError, ValueError):
        return {
            "base": str(monto.quantize(_Q4, rounding=ROUND_HALF_UP)),
            "base_iso": moneda_origen.codigo_iso,
            "pais_fiscal": None,
            "pais_fiscal_iso": None,
            "referencia": None,
            "referencia_iso": None,
        }


def _scope_metodos_empresa(empresa):
    return MetodoPago.objects.filter(activo=True).filter(
        Q(es_generico=True) | Q(es_publico=True) | Q(empresa__isnull=True) | Q(empresa=empresa)
    )


def _scope_monedas_empresa(empresa):
    return Moneda.objects.filter(activo=True).filter(
        Q(es_generica=True) | Q(es_publica=True) | Q(empresa__isnull=True) | Q(empresa=empresa)
    )


class CheckinVendedorInputSerializer(serializers.Serializer):
    id_cliente = serializers.UUIDField()
    latitud = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=Decimal("-90"), max_value=Decimal("90")
    )
    longitud = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=Decimal("-180"), max_value=Decimal("180")
    )
    precision_m = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, allow_null=True)
    resultado = serializers.ChoiceField(
        choices=[c[0] for c in VisitaGPSVendedor.RESULTADOS], required=False, default="EFECTIVA"
    )
    notas = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class LineaPedidoPortalInputSerializer(serializers.Serializer):
    id_producto = serializers.UUIDField()
    cantidad = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=Decimal("0.0001"))


class PedidoVendedorInputSerializer(serializers.Serializer):
    id_cliente = serializers.UUIDField()
    observaciones = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    referencia_externa = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    lineas = LineaPedidoPortalInputSerializer(many=True, allow_empty=False)


class CobroVendedorInputSerializer(serializers.Serializer):
    id_cliente = serializers.UUIDField()
    monto = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=Decimal("0.0001"))
    id_moneda = serializers.UUIDField()
    id_metodo_pago = serializers.UUIDField()
    tasa = serializers.DecimalField(
        max_digits=18, decimal_places=4, required=False, default=Decimal("1.0000"), min_value=Decimal("0.0001")
    )
    referencia = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    comprobante_url = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    observaciones = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class PortalVendedorViewSet(viewsets.ViewSet):
    """Portal operativo de Vendedores (SFA): cartera, catálogo trimonetario, check-in GPS, pedidos, cobros y metas."""

    permission_classes = [permissions.IsAuthenticated]

    def _cartera_clientes_qs(self, request, empresa):
        qs = Cliente.objects.filter(id_empresa=empresa, activo=True)
        incluir_todos = _no_nul(request.query_params.get("todos"), "todos") == "1"
        es_admin = bool(
            getattr(request.user, "es_superusuario_omni", False)
            or getattr(request.user, "is_superuser", False)
            or getattr(request.user, "is_staff", False)
        )
        if not (incluir_todos and es_admin):
            qs = qs.filter(Q(id_vendedor_asignado=request.user) | Q(id_vendedor_asignado__isnull=True))
        return qs.order_by("razon_social")

    @action(detail=False, methods=["get"], url_path="cartera")
    def cartera(self, request):
        """Cartera propia del vendedor con saldo CxC pendiente y mora real."""
        empresa = _resolver_empresa_vendedor(request)
        clientes = list(self._cartera_clientes_qs(request, empresa)[:200])
        hoy = timezone.localdate()
        resultado = []
        for cli in clientes:
            cxc_qs = CuentaPorCobrar.objects.filter(
                empresa=empresa, cliente=cli, estado__in=("pendiente", "vencida", "parcial")
            )
            agg = cxc_qs.aggregate(total_pendiente=Sum("monto"))
            vencidas = cxc_qs.filter(fecha_vencimiento__lt=hoy).count()
            resultado.append(
                {
                    "id_cliente": str(cli.pk),
                    "razon_social": cli.razon_social,
                    "rif": cli.rif,
                    "tipo_cliente": cli.tipo_cliente,
                    "limite_credito": str(cli.limite_credito),
                    "saldo_pendiente": str((agg["total_pendiente"] or _CERO).quantize(_Q2, rounding=ROUND_HALF_UP)),
                    "cuentas_vencidas": vencidas,
                    "bloquear_por_mora": bool(cli.bloquear_por_mora and vencidas > 0),
                }
            )
        return Response({"empresa_id": str(empresa.pk), "clientes": resultado})

    @action(detail=False, methods=["get"], url_path="catalogo")
    def catalogo(self, request):
        """Catálogo de productos con stock neto disponible y equivalencias trimonetarias."""
        empresa = _resolver_empresa_vendedor(request)
        q = _no_nul(request.query_params.get("q"), "q")
        qs = (
            Producto.objects.filter(id_empresa=empresa, activo=True, es_vendible=True)
            .select_related("id_moneda_precio")
            .order_by("nombre_producto")
        )
        if q:
            qs = qs.filter(Q(nombre_producto__icontains=q) | Q(sku__icontains=q) | Q(codigo_barras__icontains=q))
        productos = list(qs[:100])
        stock_map = {
            row["id_producto"]: max(
                (row["disp"] or _CERO) - (row["comp"] or _CERO),
                _CERO,
            )
            for row in StockActual.objects.filter(id_empresa=empresa, id_producto__in=[p.pk for p in productos])
            .values("id_producto")
            .annotate(disp=Sum("cantidad_disponible"), comp=Sum("cantidad_comprometida"))
        }
        items = []
        for prod in productos:
            precio = Decimal(str(obtener_precio(prod, empresa)))
            items.append(
                {
                    "id_producto": str(prod.pk),
                    "sku": prod.sku or "",
                    "codigo_barras": prod.codigo_barras or "",
                    "nombre_producto": prod.nombre_producto,
                    "stock_disponible": str(stock_map.get(prod.pk, _CERO).quantize(_Q4, rounding=ROUND_HALF_UP)),
                    "precio": str(precio.quantize(_Q4, rounding=ROUND_HALF_UP)),
                    "moneda_precio": prod.id_moneda_precio.codigo_iso,
                    "equivalencias_trimonetarias": _equivalencias_seguras(precio, prod.id_moneda_precio, empresa),
                }
            )
        return Response({"empresa_id": str(empresa.pk), "productos": items})

    @swagger_auto_schema(request_body=CheckinVendedorInputSerializer)
    @idempotent(scope="portal_vendedor:checkin")
    @action(
        detail=False,
        methods=["post"],
        url_path="checkin",
        throttle_classes=[*viewsets.ViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def checkin(self, request):
        """Registra un check-in GPS del vendedor en campo calculando distancia al cliente."""
        empresa = _resolver_empresa_vendedor(request)
        ser = CheckinVendedorInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data

        cliente = Cliente.objects.filter(pk=vd["id_cliente"], id_empresa=empresa, activo=True).first()
        if cliente is None:
            return Response({"id_cliente": "Cliente no encontrado en la empresa."}, status=status.HTTP_404_NOT_FOUND)

        dist_m: Decimal | None = None
        dir_cli = (
            DireccionCliente.objects.filter(
                id_empresa=empresa,
                id_cliente=cliente,
                activo=True,
                latitud__isnull=False,
                longitud__isnull=False,
            )
            .order_by("-es_direccion_principal", "-fecha_actualizacion")
            .first()
        )
        if dir_cli is not None:
            dist_km = distancia_haversine_km(vd["latitud"], vd["longitud"], dir_cli.latitud, dir_cli.longitud)
            dist_m = (dist_km * Decimal("1000")).quantize(_Q2, rounding=ROUND_HALF_UP)

        visita = VisitaGPSVendedor.objects.create(
            id_empresa=empresa,
            id_vendedor=request.user,
            id_cliente=cliente,
            latitud=vd["latitud"],
            longitud=vd["longitud"],
            precision_m=vd.get("precision_m"),
            distancia_cliente_m=dist_m,
            resultado=vd["resultado"],
            notas=vd["notas"],
        )
        return Response(
            {
                "id_visita": str(visita.pk),
                "id_cliente": str(cliente.pk),
                "distancia_cliente_m": str(dist_m) if dist_m is not None else None,
                "resultado": visita.resultado,
                "fecha_visita": visita.fecha_visita.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )

    @swagger_auto_schema(request_body=PedidoVendedorInputSerializer)
    @idempotent(scope="portal_vendedor:pedidos")
    @action(
        detail=False,
        methods=["post"],
        url_path="pedidos",
        throttle_classes=[*viewsets.ViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def pedidos(self, request):
        """Crea un pedido PENDIENTE desde campo atribuido al vendedor autenticado."""
        empresa = _resolver_empresa_vendedor(request)
        ser = PedidoVendedorInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data

        cliente = Cliente.objects.filter(pk=vd["id_cliente"], id_empresa=empresa, activo=True).first()
        if cliente is None:
            return Response({"id_cliente": "Cliente no encontrado en la empresa."}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            prods = {
                p.pk: p
                for p in Producto.objects.filter(
                    id_empresa=empresa,
                    activo=True,
                    es_vendible=True,
                    pk__in=[line["id_producto"] for line in vd["lineas"]],
                )
            }
            if len(prods) != len({line["id_producto"] for line in vd["lineas"]}):
                return Response(
                    {"lineas": "Uno o más productos no existen, están inactivos o no son vendibles."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            num_pedido = f"PED-SFA-{uuid.uuid4().hex[:8].upper()}"
            ped = Pedido.objects.create(
                id_empresa=empresa,
                id_cliente=cliente,
                id_vendedor=request.user,
                numero_pedido=num_pedido,
                fecha_pedido=timezone.localdate(),
                estado="PENDIENTE",
                observaciones=vd["observaciones"] or "Pedido creado desde Portal Vendedores SFA",
                referencia_externa=vd["referencia_externa"] or None,
            )
            total = _CERO
            detalles = []
            for line in vd["lineas"]:
                prod = prods[line["id_producto"]]
                pu = Decimal(str(obtener_precio(prod, empresa, contacto=cliente.contacto))).quantize(
                    _Q4, rounding=ROUND_HALF_UP
                )
                sub = (line["cantidad"] * pu).quantize(_Q4, rounding=ROUND_HALF_UP)
                total += sub
                detalles.append(
                    DetallePedido(
                        id_pedido=ped,
                        id_producto=prod,
                        cantidad=line["cantidad"],
                        precio_unitario=pu,
                        subtotal=sub,
                    )
                )
            DetallePedido.objects.bulk_create(detalles)

        return Response(
            {
                "id_pedido": str(ped.pk),
                "numero_pedido": ped.numero_pedido,
                "estado": ped.estado,
                "total_estimado": str(total.quantize(_Q4, rounding=ROUND_HALF_UP)),
            },
            status=status.HTTP_201_CREATED,
        )

    @swagger_auto_schema(request_body=CobroVendedorInputSerializer)
    @idempotent(scope="portal_vendedor:cobros")
    @action(
        detail=False,
        methods=["post"],
        url_path="cobros",
        throttle_classes=[*viewsets.ViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def cobros(self, request):
        """Registra un cobro reportado en campo con foto/comprobante pendiente de validación."""
        empresa = _resolver_empresa_vendedor(request)
        ser = CobroVendedorInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data

        cliente = Cliente.objects.filter(pk=vd["id_cliente"], id_empresa=empresa, activo=True).first()
        if cliente is None:
            return Response({"id_cliente": "Cliente no encontrado en la empresa."}, status=status.HTTP_404_NOT_FOUND)

        moneda = _scope_monedas_empresa(empresa).filter(pk=vd["id_moneda"]).first()
        metodo = _scope_metodos_empresa(empresa).filter(pk=vd["id_metodo_pago"]).first()
        if moneda is None or metodo is None:
            return domain_error_response(
                PortalVendedorError("Moneda o método de pago inválido o inactivo para la empresa."),
                status_code=status.HTTP_400_BAD_REQUEST,
                key="detail",
            )

        url = (vd.get("comprobante_url") or "").strip()
        if url and not url.startswith(("https://", "http://")):
            return domain_error_response(
                PortalVendedorError("La URL del comprobante debe iniciar con http:// o https://."),
                status_code=status.HTTP_400_BAD_REQUEST,
                key="detail",
            )

        pago_portal = PagoPortalCliente.objects.create(
            id_empresa=empresa,
            id_cliente=cliente,
            id_vendedor_reporta=request.user,
            monto=vd["monto"],
            id_moneda=moneda,
            id_metodo_pago=metodo,
            tasa=vd["tasa"],
            referencia=vd["referencia"],
            comprobante_url=url,
            observaciones=vd["observaciones"],
        )
        return Response(
            {
                "id_pago_portal": str(pago_portal.pk),
                "estado": pago_portal.estado,
                "monto": str(pago_portal.monto),
                "moneda": moneda.codigo_iso,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"], url_path="metas-comisiones")
    def metas_comisiones(self, request):
        """Tablero de metas y comisiones devengadas/liquidadas del vendedor."""
        empresa = _resolver_empresa_vendedor(request)
        esquemas = list(
            EsquemaComision.objects.filter(id_empresa=empresa, vendedor=request.user, activo=True).values(
                "id_esquema_comision",
                "porcentaje_base",
                "meta_mensual_monto",
                "bono_meta_porcentaje",
                "modalidad_devengo",
            )
        )
        com_qs = ComisionVenta.objects.filter(id_empresa=empresa, vendedor=request.user)
        devengada = com_qs.filter(estado="DEVENGADA").aggregate(total=Sum("monto"))["total"] or _CERO
        liquidada = com_qs.filter(estado="LIQUIDADA").aggregate(total=Sum("monto"))["total"] or _CERO
        recientes = [
            {
                "id_comision_venta": str(c.pk),
                "nota_venta": c.nota_venta.numero_nota,
                "monto": str(c.monto),
                "estado": c.estado,
                "origen_devengo": c.origen_devengo,
                "fecha_devengo": c.fecha_devengo.isoformat(),
            }
            for c in com_qs.select_related("nota_venta")[:20]
        ]
        return Response(
            {
                "empresa_id": str(empresa.pk),
                "total_devengado": str(devengada.quantize(_Q4, rounding=ROUND_HALF_UP)),
                "total_liquidado": str(liquidada.quantize(_Q4, rounding=ROUND_HALF_UP)),
                "esquemas": [
                    {
                        "id_esquema_comision": str(e["id_esquema_comision"]),
                        "porcentaje_base": str(e["porcentaje_base"]),
                        "meta_mensual_monto": str(e["meta_mensual_monto"]),
                        "bono_meta_porcentaje": str(e["bono_meta_porcentaje"]),
                        "modalidad_devengo": e["modalidad_devengo"],
                    }
                    for e in esquemas
                ],
                "comisiones": recientes,
            }
        )
