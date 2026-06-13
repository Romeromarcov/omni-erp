"""
Tests: CxC básico (aging, abonos, eventos), WS-2 (evento PEDIDO_CONFIRMADO), MCP tools.
"""

import pytest
from decimal import Decimal
from django.utils import timezone
from rest_framework.test import APIClient
from unittest.mock import patch


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def cliente_a(db, empresa_a):
    from apps.crm.models import Cliente
    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Cliente CxC Test S.A.",
        rif="J-55555555-5",
        tipo_cliente="CREDITO",
        limite_credito=Decimal("20000.00"),
        dias_credito=30,
    )


@pytest.fixture
def cxc_pendiente(db, empresa_a, cliente_a):
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar
    return CuentaPorCobrar.objects.create(
        cliente=cliente_a,
        empresa=empresa_a,
        monto=Decimal("1000.00"),
        fecha_emision=timezone.now().date(),
        fecha_vencimiento=timezone.now().date(),
        estado="pendiente",
        descripcion="CxC test",
    )


@pytest.fixture
def cxc_vencida(db, empresa_a, cliente_a):
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar
    from datetime import timedelta
    return CuentaPorCobrar.objects.create(
        cliente=cliente_a,
        empresa=empresa_a,
        monto=Decimal("500.00"),
        fecha_emision=timezone.now().date() - timedelta(days=60),
        fecha_vencimiento=timezone.now().date() - timedelta(days=45),
        estado="vencida",
        descripcion="CxC vencida test",
    )


@pytest.fixture
def almacen_a(db, empresa_a):
    from apps.almacenes.models import Almacen
    return Almacen.objects.create(
        id_empresa=empresa_a,
        nombre_almacen="Almacén CxC Test",
        codigo_almacen="CXC-001",
    )


@pytest.fixture
def unidad(db, empresa_a):
    from apps.inventario.models import UnidadMedida
    return UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad", abreviatura="UN-CXC", tipo="CANTIDAD"
    )


@pytest.fixture
def categoria(db, empresa_a):
    from apps.inventario.models import CategoriaProducto
    return CategoriaProducto.objects.create(
        id_empresa=empresa_a, nombre_categoria="Cat CxC"
    )


@pytest.fixture
def producto(db, empresa_a, unidad, categoria, moneda_usd):
    from apps.inventario.models import Producto
    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Producto CxC Test",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
    )


@pytest.fixture
def stock_100(db, empresa_a, producto, almacen_a, user_a):
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


# ── CxC: aging ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAging:
    def test_aging_corriente(self, cxc_pendiente, empresa_a, user_a):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get("/api/cxc/cuentas-por-cobrar/aging/", {"empresa": str(empresa_a.id_empresa)})
        assert resp.status_code == 200
        assert int(resp.data["corriente"]["count"]) == 1
        assert Decimal(resp.data["corriente"]["total"]) == Decimal("1000.00")

    def test_aging_vencida_31_60(self, cxc_vencida, empresa_a, user_a):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get("/api/cxc/cuentas-por-cobrar/aging/", {"empresa": str(empresa_a.id_empresa)})
        assert resp.status_code == 200
        # 45 dias vencida → bucket 31-60
        assert int(resp.data["dias_31_60"]["count"]) == 1
        assert Decimal(resp.data["dias_31_60"]["total"]) == Decimal("500.00")

    def test_aging_total_general(self, cxc_pendiente, cxc_vencida, empresa_a, user_a):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get("/api/cxc/cuentas-por-cobrar/aging/", {"empresa": str(empresa_a.id_empresa)})
        assert resp.status_code == 200
        assert Decimal(resp.data["total_general"]) == Decimal("1500.00")

    def test_aging_sin_empresa_retorna_400(self, user_a):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get("/api/cxc/cuentas-por-cobrar/aging/")
        assert resp.status_code == 400

    def test_aging_multi_tenant(self, cxc_pendiente, empresa_a, user_b):
        client = APIClient()
        client.force_authenticate(user=user_b)
        resp = client.get("/api/cxc/cuentas-por-cobrar/aging/", {"empresa": str(empresa_a.id_empresa)})
        assert resp.status_code == 403


# ── CxC: abonos ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAbonos:
    def test_abono_parcial(self, cxc_pendiente, user_a):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.post(
            f"/api/cxc/cuentas-por-cobrar/{cxc_pendiente.pk}/abonar/",
            {"monto": "300.00", "descripcion": "Pago parcial"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["estado_cxc"] == "parcial"
        assert Decimal(resp.data["monto_abonado"]) == Decimal("300.00")

        cxc_pendiente.refresh_from_db()
        assert cxc_pendiente.estado == "parcial"

    def test_abono_total_cierra_cxc(self, cxc_pendiente, user_a):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.post(
            f"/api/cxc/cuentas-por-cobrar/{cxc_pendiente.pk}/abonar/",
            {"monto": "1000.00"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["estado_cxc"] == "pagada"

        cxc_pendiente.refresh_from_db()
        assert cxc_pendiente.estado == "pagada"

    def test_abono_excede_saldo_falla(self, cxc_pendiente, user_a):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.post(
            f"/api/cxc/cuentas-por-cobrar/{cxc_pendiente.pk}/abonar/",
            {"monto": "2000.00"},
            format="json",
        )
        assert resp.status_code == 400

    def test_abono_a_cxc_pagada_falla(self, cxc_pendiente, user_a):
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar
        CuentaPorCobrar.objects.filter(pk=cxc_pendiente.pk).update(estado="pagada")

        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.post(
            f"/api/cxc/cuentas-por-cobrar/{cxc_pendiente.pk}/abonar/",
            {"monto": "100.00"},
            format="json",
        )
        assert resp.status_code == 400

    def test_saldo_pendiente_en_listado(self, cxc_pendiente, user_a):
        """El serializer calcula saldo_pendiente correctamente."""
        client = APIClient()
        client.force_authenticate(user=user_a)

        # Hacer abono parcial primero
        client.post(
            f"/api/cxc/cuentas-por-cobrar/{cxc_pendiente.pk}/abonar/",
            {"monto": "400.00"},
            format="json",
        )

        resp = client.get(f"/api/cxc/cuentas-por-cobrar/{cxc_pendiente.pk}/")
        assert resp.status_code == 200
        assert Decimal(resp.data["saldo_pendiente"]) == Decimal("600.00")


# ── WS-2: evento PEDIDO_CONFIRMADO ───────────────────────────────────────────

@pytest.mark.django_db
class TestWS2PedidoConfirmadoEvento:
    def test_confirmar_emite_evento(
        self, empresa_a, cliente_a, almacen_a, producto, user_a, stock_100
    ):
        from apps.ventas.models import DetallePedido, Pedido

        pedido = Pedido.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_a,
            numero_pedido="WS2-001",
            fecha_pedido=timezone.now().date(),
            estado="PENDIENTE",
        )
        DetallePedido.objects.create(
            id_pedido=pedido,
            id_producto=producto,
            cantidad=Decimal("5"),
            precio_unitario=Decimal("100.00"),
            subtotal=Decimal("500.00"),
        )

        with patch("apps.core.events.publish") as mock_publish:
            from apps.ventas.services import confirmar_pedido
            confirmar_pedido(pedido=pedido, almacen=almacen_a, usuario=user_a)

        mock_publish.assert_called_once()
        call_kwargs = mock_publish.call_args.kwargs
        assert call_kwargs["event_type"] == "omni.ventas.pedido.confirmado"
        assert call_kwargs["payload"]["numero_pedido"] == "WS2-001"

    def test_abono_emite_evento_pago_parcial(self, cxc_pendiente, user_a):
        from apps.cuentas_por_cobrar.services import registrar_abono

        with patch("apps.core.events.publish") as mock_publish:
            registrar_abono(cxc=cxc_pendiente, monto=Decimal("300"), usuario=user_a)

        mock_publish.assert_called_once()
        call_kwargs = mock_publish.call_args.kwargs
        assert call_kwargs["event_type"] == "omni.cobranza.pago.parcial"

    def test_abono_total_emite_evento_pago_total(self, cxc_pendiente, user_a):
        from apps.cuentas_por_cobrar.services import registrar_abono

        with patch("apps.core.events.publish") as mock_publish:
            registrar_abono(cxc=cxc_pendiente, monto=Decimal("1000"), usuario=user_a)

        mock_publish.assert_called_once()
        call_kwargs = mock_publish.call_args.kwargs
        assert call_kwargs["event_type"] == "omni.cobranza.pago.total"


# ── MCP tools (WS-3) ─────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestMCPTools:
    @pytest.fixture
    def token(self, db, empresa_a):
        from apps.core.models import CapabilityToken
        from django.utils import timezone
        from datetime import timedelta
        return CapabilityToken.objects.create(
            empresa=empresa_a,
            nombre="Token test MCP",
            scopes=["*"],
            expires_at=timezone.now() + timedelta(hours=1),
        )

    def test_mcp_get_cxc_aging(self, token, cxc_pendiente, empresa_a):
        from apps.core.mcp_server import omni_get_cxc_aging
        resultado = omni_get_cxc_aging(
            capability_token=str(token.token),
            empresa_id=str(empresa_a.id_empresa),
        )
        assert resultado["empresa_id"] == str(empresa_a.id_empresa)
        assert resultado["corriente"]["count"] == 1
        assert resultado["total_general"] == 1000.0

    def test_mcp_get_stock_producto(self, token, empresa_a, producto, almacen_a, stock_100):
        from apps.core.mcp_server import omni_get_stock_producto
        resultado = omni_get_stock_producto(
            capability_token=str(token.token),
            empresa_id=str(empresa_a.id_empresa),
            producto_id=str(producto.id_producto),
        )
        assert len(resultado) == 1
        assert resultado[0]["cantidad_disponible"] == 100.0

    def test_mcp_get_ventas_resumen(self, token, empresa_a, cliente_a, almacen_a, producto, user_a, stock_100):
        from apps.ventas.models import DetallePedido, Pedido
        from apps.ventas.services import confirmar_pedido

        pedido = Pedido.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_a,
            numero_pedido="MCP-001",
            fecha_pedido=timezone.now().date(),
            estado="PENDIENTE",
        )
        DetallePedido.objects.create(
            id_pedido=pedido,
            id_producto=producto,
            cantidad=Decimal("10"),
            precio_unitario=Decimal("200.00"),
            subtotal=Decimal("2000.00"),
        )
        confirmar_pedido(pedido=pedido, almacen=almacen_a, usuario=user_a)

        from apps.core.mcp_server import omni_get_ventas_resumen
        resultado = omni_get_ventas_resumen(
            capability_token=str(token.token),
            empresa_id=str(empresa_a.id_empresa),
        )
        assert resultado["cantidad_pedidos"] >= 1
        assert resultado["total_ventas"] >= 2000.0

    def test_mcp_scope_invalido_falla(self, token, empresa_a):
        from apps.core.models import CapabilityToken
        from django.utils import timezone
        from datetime import timedelta

        token_limitado = CapabilityToken.objects.create(
            empresa=empresa_a,
            nombre="Token limitado test",
            scopes=["core:read"],
            expires_at=timezone.now() + timedelta(hours=1),
        )
        from apps.core.mcp_server import omni_get_cxc_aging
        with pytest.raises(PermissionError):
            omni_get_cxc_aging(
                capability_token=str(token_limitado.token),
                empresa_id=str(empresa_a.id_empresa),
            )
