"""
Tests: CRM (buscar_por_rif, historial_ventas, crédito), Fiscal (IVA, IGTF), Ventas (confirmar).
"""

import pytest
from decimal import Decimal
from django.utils import timezone
from rest_framework.test import APIClient


# ── Fixtures locales ──────────────────────────────────────────────────────────

@pytest.fixture
def cliente_a(db, empresa_a):
    from apps.crm.models import Cliente
    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Distribuidora Pérez C.A.",
        rif="J-30123456-7",
        tipo_cliente="CONTADO",
    )


@pytest.fixture
def cliente_credito(db, empresa_a):
    from apps.crm.models import Cliente
    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Cliente Crédito S.A.",
        rif="J-40123456-8",
        tipo_cliente="CREDITO",
        limite_credito=Decimal("10000.00"),
        dias_credito=30,
    )


@pytest.fixture
def almacen_a(db, empresa_a):
    from apps.almacenes.models import Almacen
    return Almacen.objects.create(
        id_empresa=empresa_a,
        nombre_almacen="Almacén Principal",
        codigo_almacen="ALM-001",
    )


@pytest.fixture
def unidad(db, empresa_a):
    from apps.inventario.models import UnidadMedida
    return UnidadMedida.objects.create(
        id_empresa=empresa_a,
        nombre="Unidad",
        abreviatura="UN-CFV",
        tipo="CANTIDAD",
    )


@pytest.fixture
def categoria(db, empresa_a):
    from apps.inventario.models import CategoriaProducto
    return CategoriaProducto.objects.create(
        id_empresa=empresa_a,
        nombre_categoria="Lubricantes CFV",
    )


@pytest.fixture
def producto(db, empresa_a, unidad, categoria, moneda_usd):
    from apps.inventario.models import Producto
    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Aceite Motor 20W-50",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
    )


@pytest.fixture
def stock_inicial(db, empresa_a, producto, almacen_a, user_a):
    from apps.inventario.services import registrar_movimiento
    registrar_movimiento(
        empresa=empresa_a,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="ENTRADA",
        producto=producto,
        cantidad=Decimal("100"),
        almacen_destino=almacen_a,
        usuario=user_a,
    )


@pytest.fixture
def pedido(db, empresa_a, cliente_a):
    from apps.ventas.models import Pedido
    return Pedido.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente_a,
        numero_pedido="PED-001",
        fecha_pedido=timezone.now().date(),
        estado="PENDIENTE",
    )


@pytest.fixture
def pedido_con_detalle(db, pedido, producto):
    from apps.ventas.models import DetallePedido
    DetallePedido.objects.create(
        id_pedido=pedido,
        id_producto=producto,
        cantidad=Decimal("10"),
        precio_unitario=Decimal("50.00"),
        subtotal=Decimal("500.00"),
    )
    return pedido


# ── CRM: buscar por RIF ───────────────────────────────────────────────────────

@pytest.mark.django_db
class TestBuscarPorRif:
    def test_buscar_por_rif_exacto(self, cliente_a, user_a):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get("/api/crm/clientes/buscar-por-rif/", {"rif": "J-30123456-7"})
        assert resp.status_code == 200
        assert len(resp.data) == 1
        assert resp.data[0]["rif"] == "J-30123456-7"

    def test_buscar_por_rif_parcial(self, cliente_a, user_a):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get("/api/crm/clientes/buscar-por-rif/", {"rif": "J-30"})
        assert resp.status_code == 200
        assert len(resp.data) >= 1

    def test_buscar_por_rif_sin_parametro_retorna_400(self, user_a):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get("/api/crm/clientes/buscar-por-rif/")
        assert resp.status_code == 400

    def test_buscar_por_rif_multi_tenant(self, cliente_a, user_b):
        """user_b no ve clientes de empresa_a."""
        client = APIClient()
        client.force_authenticate(user=user_b)
        resp = client.get("/api/crm/clientes/buscar-por-rif/", {"rif": "J-30123456-7"})
        assert resp.status_code == 200
        assert len(resp.data) == 0


# ── CRM: historial de ventas ──────────────────────────────────────────────────

@pytest.mark.django_db
class TestHistorialVentas:
    def test_historial_vacio(self, cliente_a, user_a):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get(f"/api/crm/clientes/{cliente_a.id_cliente}/historial-ventas/")
        assert resp.status_code == 200
        assert resp.data["rif"] == "J-30123456-7"
        assert resp.data["pedidos"] == []

    def test_historial_con_pedido(self, cliente_a, pedido, user_a):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get(f"/api/crm/clientes/{cliente_a.id_cliente}/historial-ventas/")
        assert resp.status_code == 200
        assert len(resp.data["pedidos"]) == 1
        assert resp.data["pedidos"][0]["numero_pedido"] == "PED-001"


# ── CRM: crédito disponible ───────────────────────────────────────────────────

@pytest.mark.django_db
class TestCreditoDisponible:
    def test_cliente_contado_sin_credito(self, cliente_a, user_a):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get(f"/api/crm/clientes/{cliente_a.id_cliente}/credito-disponible/")
        assert resp.status_code == 200
        assert resp.data["credito_disponible"] is None

    def test_cliente_credito_sin_deuda(self, cliente_credito, user_a):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get(f"/api/crm/clientes/{cliente_credito.id_cliente}/credito-disponible/")
        assert resp.status_code == 200
        assert Decimal(resp.data["credito_disponible"]) == Decimal("10000.00")
        assert resp.data["bloqueado"] is False


# ── Fiscal: servicios IVA / IGTF ─────────────────────────────────────────────

@pytest.mark.django_db
class TestServiciosFiscales:
    def test_iva_general_16(self):
        from apps.fiscal.services import calcular_iva
        resultado = calcular_iva(Decimal("100"), "GENERAL")
        assert resultado["tasa"] == Decimal("0.16")
        assert resultado["monto_iva"] == Decimal("16.00")
        assert resultado["total"] == Decimal("116.00")

    def test_iva_reducido_8(self):
        from apps.fiscal.services import calcular_iva
        resultado = calcular_iva(Decimal("100"), "REDUCIDO")
        assert resultado["tasa"] == Decimal("0.08")
        assert resultado["monto_iva"] == Decimal("8.00")

    def test_iva_exento_0(self):
        from apps.fiscal.services import calcular_iva
        resultado = calcular_iva(Decimal("100"), "EXENTO")
        assert resultado["monto_iva"] == Decimal("0")
        assert resultado["total"] == Decimal("100")

    def test_igtf_aplica_en_divisa(self):
        from apps.fiscal.services import calcular_igtf
        resultado = calcular_igtf(Decimal("1000"), "DIVISA_EFECTIVO")
        assert resultado["aplica"] is True
        assert resultado["tasa"] == Decimal("0.03")
        assert resultado["monto_igtf"] == Decimal("30.00")
        assert resultado["total_con_igtf"] == Decimal("1030.00")

    def test_igtf_no_aplica_en_bs(self):
        from apps.fiscal.services import calcular_igtf
        resultado = calcular_igtf(Decimal("1000"), "EFECTIVO_BS")
        assert resultado["aplica"] is False
        assert resultado["monto_igtf"] == Decimal("0")

    def test_calcular_impuestos_pedido_completo(self):
        from apps.fiscal.services import calcular_impuestos_pedido
        lineas = [
            {"subtotal": Decimal("100"), "tipo_iva": "GENERAL"},
            {"subtotal": Decimal("50"), "tipo_iva": "EXENTO"},
        ]
        resultado = calcular_impuestos_pedido(lineas, metodo_pago="EFECTIVO_BS")
        assert resultado["subtotal"] == Decimal("150")
        assert resultado["base_general"] == Decimal("100")
        assert resultado["base_exenta"] == Decimal("50")
        assert resultado["iva_general"] == Decimal("16.00")
        assert resultado["total_iva"] == Decimal("16.00")
        assert resultado["igtf"]["aplica"] is False

    def test_igtf_en_pedido_con_divisa(self):
        from apps.fiscal.services import calcular_impuestos_pedido
        lineas = [{"subtotal": Decimal("100"), "tipo_iva": "GENERAL"}]
        resultado = calcular_impuestos_pedido(lineas, metodo_pago="DIVISA_EFECTIVO")
        # 100 + 16 IVA = 116, IGTF 3% de 116 = 3.48
        assert resultado["igtf"]["aplica"] is True
        assert resultado["igtf"]["monto_igtf"] == Decimal("3.48")
        assert resultado["total"] == Decimal("119.48")

    def test_tasa_iva_configurable_por_empresa(self, empresa_a):
        from apps.fiscal.models import TasaIVAEmpresa
        from apps.fiscal.services import calcular_iva
        TasaIVAEmpresa.objects.create(
            id_empresa=empresa_a,
            tipo="GENERAL",
            nombre="IVA General 16%",
            tasa=Decimal("0.12"),
        )
        resultado = calcular_iva(Decimal("100"), "GENERAL", empresa=empresa_a)
        assert resultado["tasa"] == Decimal("0.12")
        assert resultado["monto_iva"] == Decimal("12.00")


# ── Ventas: confirmar pedido ──────────────────────────────────────────────────

@pytest.mark.django_db
class TestConfirmarPedido:
    def test_confirmar_reserva_stock_sin_mover_fisico(
        self, pedido_con_detalle, almacen_a, producto, empresa_a, user_a, stock_inicial
    ):
        """confirmar_pedido solo reserva (cantidad_comprometida), no mueve stock físico."""
        from apps.inventario.models import StockActual

        stock_antes = StockActual.objects.get(id_producto=producto, id_almacen=almacen_a)
        disponible_antes = stock_antes.cantidad_disponible
        comprometida_antes = stock_antes.cantidad_comprometida

        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.post(
            f"/api/ventas/pedidos/{pedido_con_detalle.id_pedido}/confirmar/",
            {"almacen_id": str(almacen_a.id_almacen)},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["estado"] == "APROBADO"
        assert resp.data["reservas_creadas"] == 1

        stock_despues = StockActual.objects.get(id_producto=producto, id_almacen=almacen_a)
        # Stock físico NO cambia en confirmación
        assert stock_despues.cantidad_disponible == disponible_antes
        # Reserva aumenta en la cantidad del pedido (10 unidades del fixture)
        assert stock_despues.cantidad_comprometida - comprometida_antes == Decimal("10")

    def test_confirmar_genera_cxc_para_cliente_credito(
        self, empresa_a, cliente_credito, almacen_a, producto, user_a, stock_inicial
    ):
        from apps.ventas.models import DetallePedido, Pedido
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar

        pedido = Pedido.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_credito,
            numero_pedido="PED-CRED-001",
            fecha_pedido=timezone.now().date(),
            estado="PENDIENTE",
        )
        DetallePedido.objects.create(
            id_pedido=pedido,
            id_producto=producto,
            cantidad=Decimal("5"),
            precio_unitario=Decimal("50.00"),
            subtotal=Decimal("250.00"),
        )

        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.post(
            f"/api/ventas/pedidos/{pedido.id_pedido}/confirmar/",
            {"almacen_id": str(almacen_a.id_almacen)},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["cxc_generada"] is True

        cxc = CuentaPorCobrar.objects.get(pk=resp.data["cxc_id"])
        assert cxc.monto == Decimal("250.00")
        assert cxc.estado == "pendiente"

    def test_confirmar_sin_stock_suficiente_falla_atomico(
        self, pedido_con_detalle, almacen_a, producto, empresa_a, user_a
    ):
        """Sin stock_inicial, el pedido no debe quedar en APROBADO."""
        from apps.ventas.models import Pedido

        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.post(
            f"/api/ventas/pedidos/{pedido_con_detalle.id_pedido}/confirmar/",
            {"almacen_id": str(almacen_a.id_almacen)},
            format="json",
        )
        assert resp.status_code == 400
        # Pedido debe seguir en PENDIENTE
        pedido_con_detalle.refresh_from_db()
        assert pedido_con_detalle.estado == "PENDIENTE"

    def test_confirmar_requiere_almacen_id(self, pedido_con_detalle, user_a):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.post(
            f"/api/ventas/pedidos/{pedido_con_detalle.id_pedido}/confirmar/",
            {},
            format="json",
        )
        assert resp.status_code == 400

    def test_confirmar_ya_aprobado_falla(
        self, pedido_con_detalle, almacen_a, user_a, stock_inicial
    ):
        from apps.ventas.models import Pedido
        Pedido.objects.filter(pk=pedido_con_detalle.pk).update(estado="APROBADO")

        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.post(
            f"/api/ventas/pedidos/{pedido_con_detalle.id_pedido}/confirmar/",
            {"almacen_id": str(almacen_a.id_almacen)},
            format="json",
        )
        assert resp.status_code == 400
