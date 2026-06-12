"""
Tests de idempotencia en endpoints de pago/creación (P1-2 hardening, R9).

Verifica que la cabecera ``Idempotency-Key`` evita duplicar operaciones
financieras (abono CxC y confirmación de pedido), con aislamiento multi-tenant.

Casos cubiertos:
- Misma clave + mismo payload → no duplica, devuelve el mismo resultado.
- Sin cabecera → comportamiento normal (no idempotente).
- Claves distintas → dos operaciones reales.
- Misma clave + payload distinto → 422.
- Clave expirada (TTL 24h) → se trata como inexistente y se purga.
- Idempotencia en POST /finanzas/pagos/ (mixin) y registrar-pago de acuerdos.
- Aislamiento por empresa: la misma cadena de clave en otra empresa no choca
  ni reproduce la respuesta del otro tenant.
- Una respuesta de error (4xx) NO consume la clave.
- Helper a nivel de registro: hash de payload y reproducción.
"""

from decimal import Decimal

import pytest

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
        from apps.core.models import ClaveIdempotencia
        from apps.cuentas_por_cobrar.models import AbonoCxC

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

        # Misma clave, monto distinto → 422 (la clave ya identifica otra operación)
        r2 = _abonar(client, cxc_a.pk, "400.00", key="dup-key")
        assert r2.status_code == 422
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
            body,
            format="json",
            HTTP_IDEMPOTENCY_KEY="ped-key-1",
        )
        assert r1.status_code == 200, r1.data
        assert r1.data["cxc_generada"] is True

        # Reintento con misma clave → mismo resultado, sin segunda CxC ni doble descuento
        r2 = client.post(
            f"/api/ventas/pedidos/{pedido.pk}/confirmar/",
            body,
            format="json",
            HTTP_IDEMPOTENCY_KEY="ped-key-1",
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


# ── Cobertura de ramas: helpers, clave inválida, sin empresa, carrera ─────────


@pytest.mark.django_db
class TestIdempotenciaRamas:
    def test_hash_payload_no_serializable_cae_a_repr(self):
        """Un payload no serializable a JSON (referencia circular) usa repr()."""
        from apps.core.idempotency import _hash_payload

        circular: dict = {}
        circular["yo"] = circular
        h = _hash_payload(circular)
        assert isinstance(h, str) and len(h) == 64

    def test_json_safe_no_serializable_devuelve_none(self):
        """_json_safe devuelve None si el cuerpo no es serializable (defensa)."""
        from apps.core.idempotency import _json_safe

        circular: dict = {}
        circular["yo"] = circular
        assert _json_safe(circular) is None

    def test_str_clave_idempotencia(self, empresa_a):
        from apps.core.models import ClaveIdempotencia

        reg = ClaveIdempotencia.objects.create(
            empresa=empresa_a,
            scope="cxc:abonar",
            clave="K" * 20,
            payload_hash="h",
            status_respuesta=201,
            cuerpo_respuesta={"ok": True},
        )
        assert "cxc:abonar" in str(reg)

    def test_clave_demasiado_larga_400(self, cxc_a, user_a):
        client = APIClient()
        client.force_authenticate(user=user_a)
        r = _abonar(client, cxc_a.pk, "100.00", key="x" * 256)
        assert r.status_code == 400

    def test_clave_en_blanco_400(self, cxc_a, user_a):
        client = APIClient()
        client.force_authenticate(user=user_a)
        r = _abonar(client, cxc_a.pk, "100.00", key="   ")
        assert r.status_code == 400

    def test_sin_empresa_delega_a_la_vista(self, cxc_a, db):
        """Sin empresa resoluble, el decorador delega en la vista (no scoping)."""
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(
            username="idem_sin_empresa", password="x", is_active=True
        )
        client = APIClient()
        client.force_authenticate(user=user)
        r = _abonar(client, cxc_a.pk, "100.00", key="k-sin-emp")
        # empresa None → delega; la vista no ve la CxC de otro tenant.
        assert r.status_code in (403, 404)

    def _mock_objects(self, ganadora):
        """Mock del manager acorde al flujo: purga → fast-path → create → select_for_update."""
        from unittest.mock import MagicMock

        from django.db import IntegrityError

        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.delete.return_value = (0, {})
        mock_qs.first.side_effect = [None, ganadora]  # fast-path=None; luego ganadora
        mock_objects = MagicMock()
        mock_objects.filter.return_value = mock_qs
        mock_objects.select_for_update.return_value = mock_objects
        mock_objects.create.side_effect = IntegrityError("carrera simulada")
        return mock_objects

    def test_carrera_integrityerror_reproduce_ganadora(self, cxc_a, user_a):
        """Carrera: el INSERT de la clave choca; se reproduce la respuesta ganadora."""
        from unittest.mock import MagicMock, patch

        from apps.core.idempotency import _hash_payload
        from apps.core.models import ClaveIdempotencia

        ganadora = MagicMock()
        ganadora.payload_hash = _hash_payload({"monto": "100.00"})
        ganadora.cuerpo_respuesta = {"reproducido": True}
        ganadora.status_respuesta = 201

        client = APIClient()
        client.force_authenticate(user=user_a)
        with patch.object(ClaveIdempotencia, "objects", self._mock_objects(ganadora)):
            r = _abonar(client, cxc_a.pk, "100.00", key="race-key")
        assert r.status_code == 201
        assert r.data == {"reproducido": True}

    def test_carrera_integrityerror_sin_ganadora_409(self, cxc_a, user_a):
        """Carrera sin registro visible aún → 409 (reintentar)."""
        from unittest.mock import patch

        from apps.core.models import ClaveIdempotencia

        client = APIClient()
        client.force_authenticate(user=user_a)
        with patch.object(ClaveIdempotencia, "objects", self._mock_objects(None)):
            r = _abonar(client, cxc_a.pk, "100.00", key="race-key-2")
        assert r.status_code == 409

    def test_clave_expirada_se_purga_y_reejecuta(self, cxc_a, user_a):
        """Una clave vencida (TTL) se trata como inexistente: el reintento re-ejecuta."""
        from datetime import timedelta

        from django.utils import timezone

        from apps.core.models import ClaveIdempotencia
        from apps.cuentas_por_cobrar.models import AbonoCxC

        client = APIClient()
        client.force_authenticate(user=user_a)

        r1 = _abonar(client, cxc_a.pk, "100.00", key="ttl-key")
        assert r1.status_code == 201

        # Simula el paso del tiempo: la clave vence.
        ClaveIdempotencia.objects.filter(clave="ttl-key").update(
            expira_en=timezone.now() - timedelta(seconds=1)
        )

        r2 = _abonar(client, cxc_a.pk, "100.00", key="ttl-key")
        assert r2.status_code == 201
        # Se re-ejecutó de verdad (dos abonos) y la clave vencida fue purgada.
        assert AbonoCxC.objects.filter(cuenta_por_cobrar=cxc_a).count() == 2
        assert ClaveIdempotencia.objects.filter(clave="ttl-key").count() == 1
        total = sum(a.monto for a in AbonoCxC.objects.filter(cuenta_por_cobrar=cxc_a))
        assert total == Decimal("200.00")

    def test_registro_en_vuelo_devuelve_409(self, cxc_a, user_a):
        """Un registro visible sin respuesta (en vuelo) responde 409, no body vacío."""
        from datetime import timedelta

        from django.utils import timezone

        from apps.core.idempotency import _hash_payload
        from apps.core.models import ClaveIdempotencia

        ClaveIdempotencia.objects.create(
            empresa=cxc_a.empresa,
            usuario=user_a,
            scope="cxc:abonar",
            clave="vuelo-key",
            payload_hash=_hash_payload({"monto": "100.00"}),
            status_respuesta=None,
            expira_en=timezone.now() + timedelta(hours=1),
        )
        client = APIClient()
        client.force_authenticate(user=user_a)
        r = _abonar(client, cxc_a.pk, "100.00", key="vuelo-key")
        assert r.status_code == 409


# ── Idempotencia en POST /finanzas/pagos/ (IdempotentCreateMixin) ─────────────


@pytest.fixture
def metodo_pago_generico(db):
    from apps.finanzas.models import MetodoPago

    return MetodoPago.objects.create(
        nombre_metodo="Efectivo Idem", tipo_metodo="EFECTIVO", es_generico=True
    )


@pytest.fixture
def caja_a(db, empresa_a, moneda_usd):
    from apps.finanzas.models import Caja

    return Caja.objects.create(
        empresa=empresa_a,
        nombre="Caja Idem A",
        tipo_caja="REGISTRADORA",
        moneda=moneda_usd,
        saldo_actual=Decimal("100.00"),
    )


def _payload_pago(empresa, moneda, metodo, caja, monto="50.00", documento=None):
    import uuid as _uuid

    return {
        "id_empresa": str(empresa.id_empresa),
        "tipo_operacion": "INGRESO",
        "tipo_documento": "FACTURA",
        "id_documento": documento or str(_uuid.uuid4()),
        "fecha_pago": timezone.now().isoformat(),
        "monto": monto,
        "id_moneda": str(moneda.id_moneda),
        "id_metodo_pago": str(metodo.id_metodo_pago),
        "id_caja_virtual": str(caja.id_caja),
    }


@pytest.mark.django_db
class TestIdempotenciaPago:
    URL = "/api/finanzas/pagos/"

    def test_reintento_misma_clave_no_duplica_pago_ni_saldo(
        self, empresa_a, user_a, moneda_usd, metodo_pago_generico, caja_a
    ):
        from apps.finanzas.models import Pago

        client = APIClient()
        client.force_authenticate(user=user_a)
        payload = _payload_pago(empresa_a, moneda_usd, metodo_pago_generico, caja_a)

        r1 = client.post(self.URL, payload, format="json", HTTP_IDEMPOTENCY_KEY="pago-1")
        assert r1.status_code == 201, r1.content

        r2 = client.post(self.URL, payload, format="json", HTTP_IDEMPOTENCY_KEY="pago-1")
        assert r2.status_code == 201
        assert r2.data["id_pago"] == r1.data["id_pago"]

        # Un solo pago real, y el saldo de la caja se movió UNA sola vez.
        assert Pago.objects.filter(id_empresa=empresa_a).count() == 1
        caja_a.refresh_from_db()
        assert caja_a.saldo_actual == Decimal("150.00")

    def test_misma_clave_payload_distinto_422(
        self, empresa_a, user_a, moneda_usd, metodo_pago_generico, caja_a
    ):
        from apps.finanzas.models import Pago

        client = APIClient()
        client.force_authenticate(user=user_a)
        payload = _payload_pago(
            empresa_a, moneda_usd, metodo_pago_generico, caja_a, documento="7e0a4b1c-0000-4000-8000-000000000001"
        )

        r1 = client.post(self.URL, payload, format="json", HTTP_IDEMPOTENCY_KEY="pago-2")
        assert r1.status_code == 201, r1.content

        payload["monto"] = "75.00"
        r2 = client.post(self.URL, payload, format="json", HTTP_IDEMPOTENCY_KEY="pago-2")
        assert r2.status_code == 422
        assert Pago.objects.filter(id_empresa=empresa_a).count() == 1
        caja_a.refresh_from_db()
        assert caja_a.saldo_actual == Decimal("150.00")

    def test_sin_cabecera_dos_pagos(
        self, empresa_a, user_a, moneda_usd, metodo_pago_generico, caja_a
    ):
        from apps.finanzas.models import Pago

        client = APIClient()
        client.force_authenticate(user=user_a)
        payload = _payload_pago(
            empresa_a, moneda_usd, metodo_pago_generico, caja_a, documento="7e0a4b1c-0000-4000-8000-000000000002"
        )
        r1 = client.post(self.URL, payload, format="json")
        r2 = client.post(self.URL, payload, format="json")
        assert r1.status_code == 201 and r2.status_code == 201
        assert Pago.objects.filter(id_empresa=empresa_a).count() == 2


# ── Idempotencia en registrar-pago de acuerdos CxC ────────────────────────────


@pytest.mark.django_db
class TestIdempotenciaAcuerdoRegistrarPago:
    URL = "/api/cobranza/acuerdos/"

    @pytest.fixture
    def metodo_a(self, empresa_a, moneda_usd):
        from apps.finanzas.models import MetodoPago

        metodo = MetodoPago.objects.create(
            nombre_metodo="Transferencia Idem", tipo_metodo="ELECTRONICO", empresa=empresa_a
        )
        metodo.monedas.add(moneda_usd)
        return metodo

    @pytest.fixture
    def acuerdo_a(self, empresa_a, user_a):
        from apps.cxc.models import AcuerdoPago, CuotaAcuerdo

        acuerdo = AcuerdoPago.objects.create(
            empresa=empresa_a,
            cliente_id="CLI-IDEM",
            cliente_nombre="Cliente Idem Acuerdo",
            monto_total=Decimal("100.00"),
            periodicidad="unico",
            fecha_inicio=timezone.now().date(),
            moneda_codigo="USD",
        )
        CuotaAcuerdo.objects.create(
            acuerdo=acuerdo,
            numero_cuota=1,
            fecha_vencimiento=timezone.now().date(),
            monto=Decimal("100.00"),
            estado="pendiente",
        )
        return acuerdo

    def _pagar(self, client, acuerdo, cuota, monto, moneda, metodo, key=None):
        headers = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
        return client.post(
            f"{self.URL}{acuerdo.id}/registrar-pago/",
            {
                "cuota_id": str(cuota.id),
                "monto": str(monto),
                "moneda_id": str(moneda.id_moneda),
                "metodo_pago_id": str(metodo.id_metodo_pago),
            },
            format="json",
            **headers,
        )

    def test_reintento_misma_clave_no_duplica_pago_de_cuota(
        self, user_a, acuerdo_a, moneda_usd, metodo_a
    ):
        from apps.finanzas.models import Pago

        client = APIClient()
        client.force_authenticate(user=user_a)
        cuota = acuerdo_a.cuotas.get()

        r1 = self._pagar(client, acuerdo_a, cuota, "40.0000", moneda_usd, metodo_a, key="acu-1")
        assert r1.status_code == 200, r1.content

        r2 = self._pagar(client, acuerdo_a, cuota, "40.0000", moneda_usd, metodo_a, key="acu-1")
        assert r2.status_code == 200

        # Un solo Pago real; el parcial NO se duplicó (40, no 80).
        assert Pago.objects.filter(id_empresa=acuerdo_a.empresa).count() == 1
        cuota.refresh_from_db()
        assert cuota.monto_pagado == Decimal("40.0000")
        assert cuota.estado == "parcial"

    def test_misma_clave_monto_distinto_422(self, user_a, acuerdo_a, moneda_usd, metodo_a):
        from apps.finanzas.models import Pago

        client = APIClient()
        client.force_authenticate(user=user_a)
        cuota = acuerdo_a.cuotas.get()

        r1 = self._pagar(client, acuerdo_a, cuota, "40.0000", moneda_usd, metodo_a, key="acu-2")
        assert r1.status_code == 200, r1.content
        r2 = self._pagar(client, acuerdo_a, cuota, "60.0000", moneda_usd, metodo_a, key="acu-2")
        assert r2.status_code == 422
        assert Pago.objects.filter(id_empresa=acuerdo_a.empresa).count() == 1
