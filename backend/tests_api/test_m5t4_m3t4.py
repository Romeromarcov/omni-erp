"""
Tests for:
  M5-T4: AjusteInventario → generar_asiento('AJUSTE_INVENTARIO') via registrar_movimiento()
  M3-T4: OrdenCompraViewSet /aprobar/, RecepcionMercanciaViewSet /recepcionar/,
          FacturaCompraViewSet /facturar/
"""
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def almacen_a(db, empresa_a):
    from apps.almacenes.models import Almacen

    return Almacen.objects.create(
        id_empresa=empresa_a,
        nombre_almacen="Almacén Central",
        codigo_almacen="ALM-001",
    )


@pytest.fixture
def categoria_a(db, empresa_a):
    from apps.inventario.models import CategoriaProducto

    return CategoriaProducto.objects.create(
        id_empresa=empresa_a,
        nombre_categoria="General",
    )


@pytest.fixture
def unidad_a(db, empresa_a):
    from apps.inventario.models import UnidadMedida

    return UnidadMedida.objects.create(
        id_empresa=empresa_a,
        nombre="Unidad",
        abreviatura="UN",
        tipo="UNIDAD",
    )


@pytest.fixture
def producto_a(db, empresa_a, categoria_a, unidad_a, moneda_usd):
    from apps.inventario.models import Producto

    return Producto.objects.create(
        id_empresa=empresa_a,
        id_categoria=categoria_a,
        id_unidad_medida_base=unidad_a,
        id_moneda_precio=moneda_usd,
        nombre_producto="Aceite Motor 1L",
        precio_venta_sugerido=Decimal("15.00"),
        costo_promedio=Decimal("10.00"),
    )


@pytest.fixture
def proveedor_a(db, empresa_a):
    from apps.proveedores.models import Proveedor

    return Proveedor.objects.create(
        id_empresa=empresa_a,
        razon_social="Proveedor Test S.A.",
        rif="J-99999999-1",
    )


@pytest.fixture
def orden_compra_aprobada(db, empresa_a, proveedor_a, producto_a, user_a):
    from apps.compras.models import DetalleOrdenCompra, OrdenCompra

    oc = OrdenCompra.objects.create(
        id_empresa=empresa_a,
        id_proveedor=proveedor_a,
        numero_orden="OC-2026-T01",
        fecha_orden=timezone.now().date(),
        estado="APROBADA",
    )
    DetalleOrdenCompra.objects.create(
        id_orden_compra=oc,
        id_producto=producto_a,
        cantidad=Decimal("10"),
        precio_unitario=Decimal("12.00"),
        subtotal=Decimal("120.00"),
    )
    return oc


@pytest.fixture
def mapeo_ajuste(db, empresa_a):
    """MapeoContable para AJUSTE_INVENTARIO — necesario para que generar_asiento no falle."""
    from apps.contabilidad.models import MapeoContable, PlanCuentas

    debe = PlanCuentas.objects.create(
        id_empresa=empresa_a,
        codigo_cuenta="1105",
        nombre_cuenta="Inventario Ajuste Debe",
        tipo_cuenta="ACTIVO",
        naturaleza="DEUDORA",
        nivel=1,
    )
    haber = PlanCuentas.objects.create(
        id_empresa=empresa_a,
        codigo_cuenta="6105",
        nombre_cuenta="Pérdida Ajuste Inventario",
        tipo_cuenta="GASTO",
        naturaleza="DEUDORA",
        nivel=1,
    )
    return MapeoContable.objects.create(
        id_empresa=empresa_a,
        tipo_asiento="AJUSTE_INVENTARIO",
        cuenta_debe=debe,
        cuenta_haber=haber,
        descripcion_plantilla="Ajuste inventario {numero}",
        activo=True,
    )


@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


# ─────────────────────────────────────────────────────────────────────────────
# M5-T4: AJUSTE_INVENTARIO → asiento contable
# ─────────────────────────────────────────────────────────────────────────────


class TestM5T4AjusteAsiento:
    def test_ajuste_sin_costo_no_lanza_error(self, db, empresa_a, producto_a, almacen_a, user_a):
        """Sin costo_unitario el monto_total es 0 → no se intenta crear asiento."""
        from apps.inventario.services import registrar_movimiento

        # Should not raise — monto_total=0 so generar_asiento is skipped
        movimiento = registrar_movimiento(
            empresa=empresa_a,
            tipo_movimiento="AJUSTE",
            producto=producto_a,
            fecha_hora_movimiento=timezone.now(),
            cantidad=Decimal("5"),
            almacen_destino=almacen_a,
            usuario=user_a,
        )
        assert movimiento.pk is not None
        assert movimiento.monto_total == Decimal("0")

    def test_ajuste_con_costo_sin_mapeo_no_falla(self, db, empresa_a, producto_a, almacen_a, user_a):
        """Con costo pero sin MapeoContable → movimiento se registra igual (permisivo)."""
        from apps.inventario.services import registrar_movimiento

        movimiento = registrar_movimiento(
            empresa=empresa_a,
            tipo_movimiento="AJUSTE",
            producto=producto_a,
            fecha_hora_movimiento=timezone.now(),
            cantidad=Decimal("3"),
            almacen_destino=almacen_a,
            usuario=user_a,
            costo_unitario=Decimal("10.00"),
        )
        assert movimiento.pk is not None
        assert movimiento.monto_total == Decimal("30.0000")

    def test_ajuste_con_costo_y_mapeo_crea_asiento(
        self, db, empresa_a, producto_a, almacen_a, user_a, mapeo_ajuste
    ):
        """Con MapeoContable configurado → asiento se crea automáticamente."""
        from apps.contabilidad.models import AsientoContable
        from apps.inventario.services import registrar_movimiento

        antes = AsientoContable.objects.count()
        registrar_movimiento(
            empresa=empresa_a,
            tipo_movimiento="AJUSTE",
            producto=producto_a,
            fecha_hora_movimiento=timezone.now(),
            cantidad=Decimal("5"),
            almacen_destino=almacen_a,
            usuario=user_a,
            costo_unitario=Decimal("10.00"),
        )
        assert AsientoContable.objects.count() == antes + 1

    def test_monto_total_property(self, db, empresa_a, producto_a, almacen_a, user_a):
        """MovimientoInventario.monto_total = |cantidad| × costo_unitario."""
        from apps.inventario.services import registrar_movimiento

        # Use positive quantity so AJUSTE doesn't hit StockInsuficienteError
        mov = registrar_movimiento(
            empresa=empresa_a,
            tipo_movimiento="AJUSTE",
            producto=producto_a,
            fecha_hora_movimiento=timezone.now(),
            cantidad=Decimal("4"),
            almacen_destino=almacen_a,
            usuario=user_a,
            costo_unitario=Decimal("15.00"),
        )
        assert mov.monto_total == Decimal("60.0000")


# ─────────────────────────────────────────────────────────────────────────────
# M3-T4: Compras ViewSet actions
# ─────────────────────────────────────────────────────────────────────────────


class TestOrdenCompraAprobarAction:
    def test_aprobar_oc_borrador(self, db, empresa_a, proveedor_a, user_a, client_a):
        from apps.compras.models import OrdenCompra

        oc = OrdenCompra.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor_a,
            numero_orden="OC-2026-001",
            fecha_orden=timezone.now().date(),
            estado="BORRADOR",
        )
        url = f"/api/compras/ordenes-compra/{oc.pk}/aprobar/"
        resp = client_a.post(url)
        assert resp.status_code == 200
        oc.refresh_from_db()
        assert oc.estado == "APROBADA"

    def test_aprobar_oc_ya_aprobada_retorna_400(self, db, orden_compra_aprobada, client_a):
        url = f"/api/compras/ordenes-compra/{orden_compra_aprobada.pk}/aprobar/"
        resp = client_a.post(url)
        assert resp.status_code == 400

    def test_aprobar_oc_otra_empresa_retorna_404(self, db, empresa_b, proveedor_a, client_a, moneda_usd):
        """OC de empresa_b no es visible para client_a (empresa_a)."""
        from apps.compras.models import OrdenCompra
        from apps.proveedores.models import Proveedor

        prov_b = Proveedor.objects.create(
            id_empresa=empresa_b,
            razon_social="Proveedor B",
            rif="J-88888888-1",
        )
        oc_b = OrdenCompra.objects.create(
            id_empresa=empresa_b,
            id_proveedor=prov_b,
            numero_orden="OC-B-001",
            fecha_orden=timezone.now().date(),
            estado="BORRADOR",
        )
        url = f"/api/compras/ordenes-compra/{oc_b.pk}/aprobar/"
        resp = client_a.post(url)
        assert resp.status_code == 404


class TestRecepcionarAction:
    def test_recepcionar_crea_recepcion_y_cxp(
        self, db, orden_compra_aprobada, almacen_a, producto_a, user_a, client_a
    ):
        url = "/api/compras/recepciones-mercancia/recepcionar/"
        payload = {
            "orden_compra_id": str(orden_compra_aprobada.pk),
            "almacen_id": str(almacen_a.pk),
            "items": [
                {
                    "producto_id": str(producto_a.pk),
                    "cantidad": "5",
                    "costo_unitario": "12.00",
                }
            ],
        }
        resp = client_a.post(url, payload, format="json")
        assert resp.status_code == 201
        assert "recepcion_id" in resp.data
        assert resp.data["movimientos"] == 1
        assert resp.data["cxp_id"] is not None

    def test_recepcionar_sin_items_retorna_400(
        self, db, orden_compra_aprobada, almacen_a, client_a
    ):
        url = "/api/compras/recepciones-mercancia/recepcionar/"
        resp = client_a.post(
            url,
            {"orden_compra_id": str(orden_compra_aprobada.pk), "almacen_id": str(almacen_a.pk), "items": []},
            format="json",
        )
        assert resp.status_code == 400

    def test_recepcionar_oc_no_aprobada_retorna_400(
        self, db, empresa_a, proveedor_a, almacen_a, producto_a, client_a
    ):
        from apps.compras.models import OrdenCompra

        oc = OrdenCompra.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor_a,
            numero_orden="OC-2026-PEND",
            fecha_orden=timezone.now().date(),
            estado="BORRADOR",
        )
        url = "/api/compras/recepciones-mercancia/recepcionar/"
        payload = {
            "orden_compra_id": str(oc.pk),
            "almacen_id": str(almacen_a.pk),
            "items": [{"producto_id": str(producto_a.pk), "cantidad": "5", "costo_unitario": "10"}],
        }
        resp = client_a.post(url, payload, format="json")
        assert resp.status_code == 400


class TestFacturarAction:
    def test_facturar_crea_factura_compra(
        self, db, orden_compra_aprobada, almacen_a, producto_a, user_a, client_a
    ):
        from apps.compras.services import registrar_recepcion

        recepcion_resultado = registrar_recepcion(
            orden_compra_aprobada,
            almacen_a,
            user_a,
            [{"producto": producto_a, "cantidad": Decimal("5"), "costo_unitario": "12.00"}],
        )
        recepcion = recepcion_resultado["recepcion"]

        url = "/api/compras/facturas-compra/facturar/"
        resp = client_a.post(
            url,
            {"recepcion_id": str(recepcion.pk), "numero_factura": "FAC-PROV-001"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["numero_factura"] == "FAC-PROV-001"

    def test_facturar_sin_numero_retorna_400(self, db, client_a):
        url = "/api/compras/facturas-compra/facturar/"
        resp = client_a.post(url, {"recepcion_id": "00000000-0000-0000-0000-000000000000"}, format="json")
        assert resp.status_code == 400
