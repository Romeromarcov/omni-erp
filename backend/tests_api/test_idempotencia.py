"""
Tests de idempotencia en endpoints de pago/creación (P1-2 hardening, R9).

Verifica que la cabecera ``Idempotency-Key`` evita duplicar operaciones
financieras (abono CxC y confirmación de pedido), con aislamiento multi-tenant.

Casos cubiertos:
- Misma clave + mismo payload → no duplica, devuelve el mismo resultado.
- Sin cabecera → comportamiento normal (no idempotente).
- Claves distintas → dos operaciones reales.
- Misma clave + payload distinto → 409 conflicto.
- Aislamiento por empresa: la misma cadena de clave en otra empresa no choca
  ni reproduce la respuesta del otro tenant.
- Una respuesta de error (4xx) NO consume la clave.
- Helper a nivel de registro: hash de payload y reproducción.
"""

import pytest
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APIClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def cliente_a(db, empresa_a):
    from apps.crm.models import Cliente
    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Cliente Idem A S.A.",
        rif="J-44444444-4",
        tipo_cliente="CREDITO",
        limite_credito=Decimal("20000.00"),
        dias_credito=30,
    )


@pytest.fixture
def cliente_b(db, empresa_b):
    from apps.crm.models import Cliente
    return Cliente.objects.create(
        id_empresa=empresa_b,
        razon_social="Cliente Idem B S.A.",
        rif="J-33333333-3",
        tipo_cliente="CREDITO",
        limite_credito=Decimal("20000.00"),
        dias_credito=30,
    )


@pytest.fixture
def cxc_a(db, empresa_a, cliente_a):
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar
    return CuentaPorCobrar.objects.create(
        cliente=cliente_a,
        empresa=empresa_a,
        monto=Decimal("1000.00"),
        fecha_emision=timezone.now().date(),
        fecha_vencimiento=timezone.now().date(),
        estado="pendiente",
        descripcion="CxC idem test A",
    )


@pytest.fixture
def cxc_b(db, empresa_b, cliente_b):
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar
    return CuentaPorCobrar.objects.create(
        cliente=cliente_b,
        empresa=empresa_b,
        monto=Decimal("1000.00"),
        fecha_emision=timezone.now().date(),
        fecha_vencimiento=timezone.now().date(),
        estado="pendiente",
        descripcion="CxC idem test B",
    )


def _abonar(client, cxc_pk, monto, key=None):
    headers = {}
    if key is not None:
        headers["HTTP_IDEMPOTENCY_KEY"] = key
    return client.post(
        f"/api/cxc/cuentas-por-cobrar/{cxc_pk}/abonar/",
        {"monto": monto},
        format="json",
        **headers,
    )


# ── Idempotencia en abono CxC ─────────────────────────────────────────────────

@pytest.mark.django_db
class TestIdempotenciaAbono:
    def test_misma_clave_no_duplica(self, cxc_a, user_a):
        from apps.cuentas_por_cobrar.models import AbonoCxC

        client = APIClient()
        client.force_authenticate(user=user_a)

        r1 = _abonar(client, cxc_a.pk, "300.00", key="abc-123")
        assert r1.status_code == 201

        r2 = _abonar(client, cxc_a.pk, "300.00", key="abc-123")
        assert r2.status_code == 201
        # Mismo body reproducido
        assert r2.data["abono_id"] == r1.data["abono_id"]
        assert r2.data["estado_cxc"] == r1.data["estado_cxc"]

        # Solo UN abono real en la BD
        assert AbonoCxC.objects.filter(cuenta_por_cobrar=cxc_a).count() == 1
        cxc_a.refresh_from_db()
        assert cxc_a.estado == "parcial"

    def test_sin_cabecera_no_es_idempotente(self, cxc_a, user_a):
        from apps.cuentas_por_cobrar.models import AbonoCxC

        client = APIClient()
        client.force_authenticate(user=user_a)

        r1 = _abonar(client, cxc_a.pk, "100.00")
        r2 = _abonar(client, cxc_a.pk, "100.00")
        assert r1.status_code == 201
        assert r2.status_code == 201
        # Dos abonos reales (sin idempotencia)
        assert AbonoCxC.objects.filter(cuenta_por_cobrar=cxc_a).count() == 2

    def test_claves_distintas_dos_operaciones(self, cxc_a, user_a):
        from apps.cuentas_por_cobrar.models import AbonoCxC
        from apps.core.models import ClaveIdempotencia

        client = APIClient()
        client.force_authenticate(user=user_a)

        r1 = _abonar(client, cxc_a.pk, "100.00", key="key-1")
        r2 = _abonar(client, cxc_a.pk, "200.00", key="key-2")
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.data["abono_id"] != r2.data["abono_id"]
        assert AbonoCxC.objects.filter(cuenta_por_cobrar=cxc_a).count() == 2
        assert ClaveIdempotencia.objects.filter(scope="cxc:abonar").count() == 2

    def test_misma_clave_payload_distinto_conflicto(self, cxc_a, user_a):
        from apps.cuentas_por_cobrar.models import AbonoCxC

        client = APIClient()
        client.force_authenticate(user=user_a)

        r1 = _abonar(client, cxc_a.pk, "300.00", key="dup-key")
        assert r1.status_code == 201

        # Misma clave, monto distinto → conflicto
        r2 = _abonar(client, cxc_a.pk, "400.00", key="dup-key")
        assert r2.status_code == 409
        # No se registró un segundo abono
        assert AbonoCxC.objects.filter(cuenta_por_cobrar=cxc_a).count() == 1

    def test_error_no_consume_clave(self, cxc_a, user_a):
        """Un abono que excede el saldo (400) no debe consumir la clave."""
        from apps.core.models import ClaveIdempotencia

        client = APIClient()
        client.force_authenticate(user=user_a)

        r1 = _abonar(client, cxc_a.pk, "5000.00", key="retry-key")
        assert r1.status_code == 400
        # La clave no quedó registrada → un reintento legítimo puede reintentar
        assert not ClaveIdempotencia.objects.filter(clave="retry-key").exists()

        r2 = _abonar(client, cxc_a.pk, "500.00", key="retry-key")
        assert r2.status_code == 201

    def test_aislamiento_por_empresa(self, cxc_a, cxc_b, user_a, user_b):
        """La misma cadena de clave en dos empresas no colisiona ni se cruza."""
        from apps.cuentas_por_cobrar.models import AbonoCxC

        client_a = APIClient()
        client_a.force_authenticate(user=user_a)
        client_b = APIClient()
        client_b.force_authenticate(user=user_b)

        ra = _abonar(client_a, cxc_a.pk, "300.00", key="shared-key")
        rb = _abonar(client_b, cxc_b.pk, "700.00", key="shared-key")

        assert ra.status_code == 201
        assert rb.status_code == 201
        # Cada empresa creó su propio abono; no se reprodujo el del otro tenant
        assert ra.data["abono_id"] != rb.data["abono_id"]
        assert AbonoCxC.objects.filter(cuenta_por_cobrar=cxc_a).count() == 1
        assert AbonoCxC.objects.filter(cuenta_por_cobrar=cxc_b).count() == 1
        # El monto reproducido por cada empresa corresponde a su propia operación
        cxc_a.refresh_from_db()
        cxc_b.refresh_from_db()
        assert cxc_a.estado == "parcial"
        assert cxc_b.estado == "parcial"


# ── Idempotencia en confirmar pedido ──────────────────────────────────────────

@pytest.fixture
def almacen_a(db, empresa_a):
    from apps.almacenes.models import Almacen
    return Almacen.objects.create(
        id_empresa=empresa_a,
        nombre_almacen="Almacén Idem Test",
        codigo_almacen="IDEM-001",
    )


@pytest.fixture
def unidad(db, empresa_a):
    from apps.inventario.models import UnidadMedida
    return UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad", abreviatura="UN-IDEM", tipo="CANTIDAD"
    )


@pytest.fixture
def categoria(db, empresa_a):
    from apps.inventario.models import CategoriaProducto
    return CategoriaProducto.objects.create(
        id_empresa=empresa_a, nombre_categoria="Cat Idem"
    )


@pytest.fixture
def producto(db, empresa_a, unidad, categoria, moneda_usd):
    from apps.inventario.models import Producto
    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Producto Idem Test",
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


@pytest.mark.django_db
class TestIdempotenciaConfirmarPedido:
    def _pedido(self, empresa_a, cliente_a, producto):
        from apps.ventas.models import DetallePedido, Pedido
        pedido = Pedido.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_a,
            numero_pedido="IDEM-PED-001",
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
        return pedido

    def test_confirmar_misma_clave_no_duplica_cxc(
        self, empresa_a, cliente_a, almacen_a, producto, user_a, stock_100
    ):
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar

        pedido = self._pedido(empresa_a, cliente_a, producto)
        client = APIClient()
        client.force_authenticate(user=user_a)

        body = {"almacen_id": str(almacen_a.pk), "generar_cxc": True}
        r1 = client.post(
            f"/api/ventas/pedidos/{pedido.pk}/confirmar/",
            body, format="json", HTTP_IDEMPOTENCY_KEY="ped-key-1",
        )
        assert r1.status_code == 200, r1.data
        assert r1.data["cxc_generada"] is True

        # Reintento con misma clave → mismo resultado, sin segunda CxC ni doble descuento
        r2 = client.post(
            f"/api/ventas/pedidos/{pedido.pk}/confirmar/",
            body, format="json", HTTP_IDEMPOTENCY_KEY="ped-key-1",
        )
        assert r2.status_code == 200
        assert r2.data["cxc_id"] == r1.data["cxc_id"]

        # Solo una CxC para este pedido/empresa
        assert CuentaPorCobrar.objects.filter(empresa=empresa_a).count() == 1


# ── Helper a nivel de registro ────────────────────────────────────────────────

@pytest.mark.django_db
class TestRegistroIdempotencia:
    def test_hash_payload_estable(self):
        from apps.core.idempotency import _hash_payload
        a = _hash_payload({"monto": "300.00", "descripcion": "x"})
        b = _hash_payload({"descripcion": "x", "monto": "300.00"})
        assert a == b  # orden de claves no afecta
        c = _hash_payload({"monto": "400.00", "descripcion": "x"})
        assert a != c
