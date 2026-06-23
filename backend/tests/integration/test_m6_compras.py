"""
Tests de integración — Módulo Compras (M6).

Cubre apps/compras/services.py al 100%:
  - aprobar_orden_compra()     — transiciones de estado
  - registrar_recepcion()      — crea RecepcionMercancia + MovimientoInventario
                                  + CuentaPorPagar + AsientoContable opcional
  - registrar_factura_compra() — crea FacturaCompra + AsientoContable opcional

Dependencias completadas en CTF-004 (multi-tenant manufactura) y CTF-001
(asientos contables R-CODE-11) que este módulo integra.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.compras.services import CompraError, aprobar_orden_compra, registrar_factura_compra, registrar_recepcion

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ── Helpers contables ──────────────────────────────────────────────────────────


def _crear_cuenta(empresa, codigo, nombre, tipo="ACTIVO", naturaleza="DEUDORA"):
    from apps.contabilidad.models import PlanCuentas

    return PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta=codigo,
        nombre_cuenta=nombre,
        tipo_cuenta=tipo,
        naturaleza=naturaleza,
        nivel=1,
    )


def _crear_mapeo(empresa, tipo_asiento, debe, haber):
    from apps.contabilidad.models import MapeoContable

    return MapeoContable.objects.create(
        id_empresa=empresa,
        tipo_asiento=tipo_asiento,
        cuenta_debe=debe,
        cuenta_haber=haber,
        descripcion_plantilla=f"Asiento {tipo_asiento}",
        activo=True,
    )


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def proveedor(db, empresa_a):
    from apps.proveedores.models import Proveedor

    return Proveedor.objects.create(
        id_empresa=empresa_a,
        razon_social="Proveedor Test M6 S.A.",
        rif="J-10001000-1",
    )


@pytest.fixture
def almacen(db, empresa_a):
    from apps.almacenes.models import Almacen

    return Almacen.objects.create(
        id_empresa=empresa_a,
        nombre_almacen="Almacén M6",
        codigo_almacen="AC-M6",
    )


@pytest.fixture
def unidad(db, empresa_a):
    from apps.inventario.models import UnidadMedida

    return UnidadMedida.objects.create(
        id_empresa=empresa_a,
        nombre="Unidad M6",
        abreviatura="UN-M6",
        tipo="CANTIDAD",
    )


@pytest.fixture
def categoria(db, empresa_a):
    from apps.inventario.models import CategoriaProducto

    return CategoriaProducto.objects.create(
        id_empresa=empresa_a,
        nombre_categoria="Cat M6",
    )


@pytest.fixture
def producto(db, empresa_a, unidad, categoria, moneda_usd):
    from apps.inventario.models import Producto

    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Producto M6",
        sku="PROD-M6-001",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        precio_venta_sugerido=Decimal("50.00"),
    )


@pytest.fixture
def orden_borrador(db, empresa_a, proveedor):
    from apps.compras.models import OrdenCompra

    return OrdenCompra.objects.create(
        id_empresa=empresa_a,
        id_proveedor=proveedor,
        numero_orden="OC-M6-001",
        fecha_orden=timezone.now().date(),
        estado="BORRADOR",
    )


@pytest.fixture
def orden_aprobada(db, empresa_a, proveedor):
    from apps.compras.models import OrdenCompra

    return OrdenCompra.objects.create(
        id_empresa=empresa_a,
        id_proveedor=proveedor,
        numero_orden="OC-M6-002",
        fecha_orden=timezone.now().date(),
        estado="APROBADA",
    )


@pytest.fixture
def usuario(db, user_a):
    return user_a


# ── TestAprobarOrdenCompra ─────────────────────────────────────────────────────


class TestAprobarOrdenCompra:
    def test_aprueba_desde_borrador(self, orden_borrador, usuario):
        aprobar_orden_compra(orden_borrador, usuario)
        orden_borrador.refresh_from_db()
        assert orden_borrador.estado == "APROBADA"

    def test_aprueba_desde_enviada(self, db, empresa_a, proveedor, usuario):
        from apps.compras.models import OrdenCompra

        oc = OrdenCompra.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor,
            numero_orden="OC-M6-ENVIADA",
            fecha_orden=timezone.now().date(),
            estado="ENVIADA",
        )
        aprobar_orden_compra(oc, usuario)
        oc.refresh_from_db()
        assert oc.estado == "APROBADA"

    def test_aprobada_no_puede_re_aprobarse(self, orden_aprobada, usuario):
        with pytest.raises(CompraError, match="BORRADOR o ENVIADA"):
            aprobar_orden_compra(orden_aprobada, usuario)

    def test_rechazada_no_puede_aprobarse(self, db, empresa_a, proveedor, usuario):
        from apps.compras.models import OrdenCompra

        oc = OrdenCompra.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor,
            numero_orden="OC-M6-RECHAZADA",
            fecha_orden=timezone.now().date(),
            estado="RECHAZADA",
        )
        with pytest.raises(CompraError, match="BORRADOR o ENVIADA"):
            aprobar_orden_compra(oc, usuario)

    def test_anulada_no_puede_aprobarse(self, db, empresa_a, proveedor, usuario):
        from apps.compras.models import OrdenCompra

        oc = OrdenCompra.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor,
            numero_orden="OC-M6-ANULADA",
            fecha_orden=timezone.now().date(),
            estado="ANULADA",
        )
        with pytest.raises(CompraError):
            aprobar_orden_compra(oc, usuario)


# ── TestRegistrarRecepcion ─────────────────────────────────────────────────────


class TestRegistrarRecepcion:
    def _items(self, producto, cantidad="10", costo="25.00"):
        return [{"producto": producto, "cantidad": cantidad, "costo_unitario": costo}]

    def test_crea_recepcion(self, orden_aprobada, almacen, producto, usuario):
        resultado = registrar_recepcion(orden_aprobada, almacen, usuario, self._items(producto))
        assert resultado["recepcion"] is not None
        assert resultado["recepcion"].monto_total == Decimal("250.00")  # 10 × 25

    def test_crea_movimiento_inventario(self, orden_aprobada, almacen, producto, usuario):
        resultado = registrar_recepcion(orden_aprobada, almacen, usuario, self._items(producto))
        movs = resultado["movimientos"]
        assert len(movs) == 1
        assert movs[0].tipo_movimiento == "RECEPCION_COMPRA"
        assert movs[0].cantidad == Decimal("10")

    def test_crea_cxp(self, orden_aprobada, almacen, producto, usuario):
        resultado = registrar_recepcion(orden_aprobada, almacen, usuario, self._items(producto))
        cxp = resultado["cxp"]
        assert cxp is not None
        assert cxp.monto_total == Decimal("250.00")
        assert cxp.estado == "PENDIENTE"

    def test_incrementa_stock(self, orden_aprobada, almacen, producto, usuario):
        from apps.inventario.models import StockActual

        registrar_recepcion(orden_aprobada, almacen, usuario, self._items(producto, "15", "10.00"))
        stock = StockActual.objects.get(
            id_empresa=orden_aprobada.id_empresa,
            id_producto=producto,
            id_almacen=almacen,
        )
        assert stock.cantidad_disponible == Decimal("15")

    def test_multiples_items(self, orden_aprobada, almacen, usuario, empresa_a, unidad, categoria, moneda_usd):
        from apps.inventario.models import Producto

        producto2 = Producto.objects.create(
            id_empresa=empresa_a,
            nombre_producto="Producto M6 B",
            sku="PROD-M6-002",
            id_unidad_medida_base=unidad,
            id_categoria=categoria,
            id_moneda_precio=moneda_usd,
        )
        producto1 = Producto.objects.create(
            id_empresa=empresa_a,
            nombre_producto="Producto M6 A",
            sku="PROD-M6-003",
            id_unidad_medida_base=unidad,
            id_categoria=categoria,
            id_moneda_precio=moneda_usd,
        )
        items = [
            {"producto": producto1, "cantidad": "5", "costo_unitario": "10.00"},
            {"producto": producto2, "cantidad": "3", "costo_unitario": "20.00"},
        ]
        resultado = registrar_recepcion(orden_aprobada, almacen, usuario, items)
        assert len(resultado["movimientos"]) == 2
        assert resultado["recepcion"].monto_total == Decimal("110.00")  # 50 + 60

    def test_oc_no_aprobada_lanza_error(self, orden_borrador, almacen, producto, usuario):
        with pytest.raises(CompraError, match="APROBADA"):
            registrar_recepcion(orden_borrador, almacen, usuario, self._items(producto))

    def test_items_vacios_lanza_error(self, orden_aprobada, almacen, usuario):
        with pytest.raises(CompraError, match="al menos un ítem"):
            registrar_recepcion(orden_aprobada, almacen, usuario, [])

    def test_genera_asiento_con_mapeo(self, orden_aprobada, almacen, producto, usuario, empresa_a):
        debe = _crear_cuenta(empresa_a, "1401", "Inventario M6", "ACTIVO", "DEUDORA")
        haber = _crear_cuenta(empresa_a, "2101", "CxP Proveedores M6", "PASIVO", "ACREEDORA")
        _crear_mapeo(empresa_a, "RECEPCION_MERCANCIA", debe, haber)

        resultado = registrar_recepcion(orden_aprobada, almacen, usuario, self._items(producto))
        asiento = resultado["asiento"]
        assert asiento is not None
        # AsientoContable guarda el modelo origen (no el tipo_asiento)
        assert asiento.nombre_modelo_origen == "RecepcionMercancia"
        # Deuda auditoría 2026-06-21: el asiento registra el usuario que lo originó.
        assert asiento.id_usuario_registro == usuario

    def test_sin_mapeo_no_falla(self, orden_aprobada, almacen, producto, usuario):
        # Sin mapeo configurado → best-effort: recepcion procede sin asiento
        resultado = registrar_recepcion(orden_aprobada, almacen, usuario, self._items(producto))
        assert resultado["asiento"] is None
        assert resultado["recepcion"] is not None


# ── TestRegistrarFacturaCompra ─────────────────────────────────────────────────


class TestRegistrarFacturaCompra:
    @pytest.fixture
    def recepcion(self, orden_aprobada, almacen, producto, usuario):
        resultado = registrar_recepcion(
            orden_aprobada, almacen, usuario,
            [{"producto": producto, "cantidad": "10", "costo_unitario": "30.00"}],
        )
        return resultado["recepcion"]

    def test_crea_factura(self, recepcion):
        resultado = registrar_factura_compra(recepcion, "FAC-PROV-0001")
        assert resultado["factura"] is not None
        assert resultado["factura"].numero_factura == "FAC-PROV-0001"
        assert resultado["factura"].monto_total == Decimal("300.00")

    def test_genera_asiento_con_mapeo(self, recepcion, empresa_a):
        debe = _crear_cuenta(empresa_a, "5101", "Gasto Compras M6", "GASTO", "DEUDORA")
        haber = _crear_cuenta(empresa_a, "2102", "Factura Pagar M6", "PASIVO", "ACREEDORA")
        _crear_mapeo(empresa_a, "FACTURA_COMPRA", debe, haber)

        resultado = registrar_factura_compra(recepcion, "FAC-PROV-0002")
        asiento = resultado["asiento"]
        assert asiento is not None
        assert asiento.nombre_modelo_origen == "FacturaCompra"
        # Sin usuario explícito el asiento queda sin usuario (no rompe).
        assert asiento.id_usuario_registro is None

    def test_asiento_factura_registra_usuario(self, recepcion, empresa_a, usuario):
        # Deuda auditoría 2026-06-21: al pasar usuario, el asiento lo registra.
        debe = _crear_cuenta(empresa_a, "5103", "Gasto Compras Usr", "GASTO", "DEUDORA")
        haber = _crear_cuenta(empresa_a, "2104", "Factura Pagar Usr", "PASIVO", "ACREEDORA")
        _crear_mapeo(empresa_a, "FACTURA_COMPRA", debe, haber)

        resultado = registrar_factura_compra(recepcion, "FAC-PROV-USR", usuario=usuario)
        assert resultado["asiento"] is not None
        assert resultado["asiento"].id_usuario_registro == usuario

    def test_sin_mapeo_no_falla(self, recepcion):
        # Sin mapeo → best-effort
        resultado = registrar_factura_compra(recepcion, "FAC-PROV-0003")
        assert resultado["factura"] is not None
        assert resultado["asiento"] is None

    def test_fecha_emision_personalizada(self, recepcion):
        fecha = timezone.now().date() - timezone.timedelta(days=5)
        resultado = registrar_factura_compra(recepcion, "FAC-PROV-0004", fecha_emision=fecha)
        assert resultado["factura"].fecha_emision == fecha

    def test_factura_enlazada_a_recepcion_y_oc(self, recepcion):
        resultado = registrar_factura_compra(recepcion, "FAC-PROV-0005")
        factura = resultado["factura"]
        assert factura.id_recepcion == recepcion
        assert factura.id_orden_compra == recepcion.id_orden_compra

    def test_cxp_de_recepcion_se_revincula_a_la_factura(self, recepcion):
        # Deuda auditoría 2026-06-21: la CxP nace en la recepción con
        # id_factura_compra=None y debe quedar enlazada al registrar la factura.
        from apps.cuentas_por_pagar.models import CuentaPorPagar

        cxp = CuentaPorPagar.objects.get(id_recepcion=recepcion)
        assert cxp.id_factura_compra is None  # antes de la factura

        resultado = registrar_factura_compra(recepcion, "FAC-PROV-0006")
        factura = resultado["factura"]

        cxp.refresh_from_db()
        assert cxp.id_factura_compra == factura
        assert resultado["cxp"] == cxp

    def test_revinculacion_no_pisa_cxp_ya_enlazada(self, recepcion, empresa_a, proveedor):
        # Idempotencia/seguridad: si la CxP de la recepción ya tiene factura,
        # una segunda factura sobre la misma recepción no la re-vincula.
        from apps.compras.models import FacturaCompra
        from apps.cuentas_por_pagar.models import CuentaPorPagar

        primera = registrar_factura_compra(recepcion, "FAC-PROV-0007")["factura"]
        cxp = CuentaPorPagar.objects.get(id_recepcion=recepcion)
        assert cxp.id_factura_compra == primera

        # Una segunda factura (caso anómalo) no debe robar el enlace existente.
        registrar_factura_compra(recepcion, "FAC-PROV-0008")
        cxp.refresh_from_db()
        assert cxp.id_factura_compra == primera
        assert FacturaCompra.objects.filter(id_recepcion=recepcion).count() == 2


# ── TestFlujoCompletoCompras ───────────────────────────────────────────────────


class TestFlujoCompletoCompras:
    """Flujo end-to-end: BORRADOR → APROBADA → Recepción → Factura + Asientos."""

    def test_flujo_completo_con_asientos(self, orden_borrador, almacen, producto, usuario, empresa_a):
        # Mapeos contables
        inv = _crear_cuenta(empresa_a, "1410", "Inventario FC", "ACTIVO", "DEUDORA")
        cxp = _crear_cuenta(empresa_a, "2110", "CxP FC", "PASIVO", "ACREEDORA")
        gasto = _crear_cuenta(empresa_a, "5110", "Gasto FC", "GASTO", "DEUDORA")
        _crear_mapeo(empresa_a, "RECEPCION_MERCANCIA", inv, cxp)
        _crear_mapeo(empresa_a, "FACTURA_COMPRA", gasto, cxp)

        # Aprobar
        aprobar_orden_compra(orden_borrador, usuario)
        orden_borrador.refresh_from_db()
        assert orden_borrador.estado == "APROBADA"

        # Recepcionar
        items = [{"producto": producto, "cantidad": "20", "costo_unitario": "15.00"}]
        res_rec = registrar_recepcion(orden_borrador, almacen, usuario, items)
        assert res_rec["asiento"].nombre_modelo_origen == "RecepcionMercancia"
        assert res_rec["cxp"].monto_total == Decimal("300.00")

        # Facturar
        res_fac = registrar_factura_compra(res_rec["recepcion"], "FAC-FLUJO-001")
        assert res_fac["asiento"].nombre_modelo_origen == "FacturaCompra"
        assert res_fac["factura"].numero_factura == "FAC-FLUJO-001"
