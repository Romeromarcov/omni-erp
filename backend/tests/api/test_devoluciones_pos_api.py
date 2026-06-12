"""
1.G — Devoluciones POS: contrato de la API.

  POST /api/ventas/notas-venta/{pk}/devolver/      (idempotente: es dinero)
  GET  /api/ventas/notas-venta/{pk}/devoluciones/  (estado devolvible por línea)
  GET  /api/ventas/notas-venta/?numero_nota=...    (búsqueda exacta del POS)

Cubre idempotencia por ``Idempotency-Key`` (un reintento NO duplica la
devolución ni el egreso de caja) y aislamiento multi-tenant (R-CODE-1).
"""

from decimal import Decimal

import pytest

from django.utils import timezone

from apps.finanzas.models import CajaFisica, MetodoPago, Pago, SesionCajaFisica
from apps.ventas.models import DetalleNotaVenta, DevolucionVenta, NotaVenta
from apps.ventas.services import confirmar_nota_venta

pytestmark = pytest.mark.django_db


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def cliente_a(db, empresa_a):
    from apps.crm.models import Cliente

    return Cliente.objects.create(
        id_empresa=empresa_a, razon_social="Consumidor Final", rif="V-00000000-0"
    )


@pytest.fixture
def almacen_a(db, empresa_a):
    from apps.almacenes.models import Almacen

    return Almacen.objects.create(
        id_empresa=empresa_a, nombre_almacen="Almacén API", codigo_almacen="ALM-API"
    )


@pytest.fixture
def producto_a(db, empresa_a, moneda_usd):
    from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida

    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad API", abreviatura="UN-API", tipo="CANTIDAD"
    )
    categoria = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="Cat API")
    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Aceite Vatel",
        sku="ACE-001",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        precio_venta_sugerido=Decimal("3.50"),
    )


@pytest.fixture
def metodo_pos(db):
    return MetodoPago.objects.create(
        nombre_metodo="Efectivo API", tipo_metodo="EFECTIVO", es_publico=True
    )


@pytest.fixture
def sesion_a(db, empresa_a, user_a):
    caja = CajaFisica.objects.create(
        empresa=empresa_a, nombre="Caja API", identificador_dispositivo="POS-API-001"
    )
    return SesionCajaFisica.objects.create(
        caja_fisica=caja, usuario=user_a, empresa=empresa_a, estado="ABIERTA"
    )


@pytest.fixture
def venta_entregada(db, empresa_a, cliente_a, producto_a, almacen_a, user_a):
    """Venta de 10 × 3.50 = 35.00, ENTREGADA (stock fuera)."""
    from apps.inventario.services import registrar_movimiento

    registrar_movimiento(
        empresa=empresa_a,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="ENTRADA",
        producto=producto_a,
        cantidad=Decimal("10"),
        almacen_destino=almacen_a,
        usuario=user_a,
        observaciones="Carga inicial",
    )
    nota = NotaVenta.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente_a,
        numero_nota="NV-API-0001",
        fecha_nota=timezone.now().date(),
        estado="BORRADOR",
    )
    DetalleNotaVenta.objects.create(
        id_nota_venta=nota,
        id_producto=producto_a,
        cantidad=Decimal("10"),
        precio_unitario=Decimal("3.50"),
        subtotal=Decimal("35.00"),
    )
    confirmar_nota_venta(nota, almacen_a, user_a)
    nota.refresh_from_db()
    return nota


def _payload(venta, almacen, metodo, cantidad="2"):
    detalle = venta.detalles.first()
    return {
        "almacen_id": str(almacen.pk),
        "id_metodo_pago": str(metodo.pk),
        "lineas": [{"id_detalle": str(detalle.id_detalle_nota_venta), "cantidad": cantidad}],
        "motivo": "CAMBIO_CLIENTE",
    }


def _url(venta, sufijo="devolver"):
    return f"/api/ventas/notas-venta/{venta.id_nota_venta}/{sufijo}/"


# ── POST /devolver/ ──────────────────────────────────────────────────────────


class TestDevolverAPI:
    def test_devolver_201_con_montos_como_string(
        self, client_a, venta_entregada, almacen_a, metodo_pos, sesion_a
    ):
        resp = client_a.post(
            _url(venta_entregada), _payload(venta_entregada, almacen_a, metodo_pos), format="json"
        )
        assert resp.status_code == 201, resp.data
        data = resp.data
        # R-CODE-4: dinero como string. 2 × 3.50 = 7.00 (sin IVA: no fiscal).
        assert data["devolucion"]["monto_total"] == "7.0000"
        assert isinstance(data["devolucion"]["monto_total"], str)
        assert data["monto_reembolsado"] == "7.0000"
        assert data["nota_credito_fiscal"] is None
        assert data["nota_credito_venta"] is not None
        assert data["caja_fisica"] == "Caja API"
        assert data["movimientos_inventario"] == 1
        assert data["asiento_id"] is None  # sin mapeo y contabilidad inactiva

    def test_idempotencia_reintento_no_duplica(
        self, client_a, venta_entregada, almacen_a, metodo_pos, sesion_a
    ):
        payload = _payload(venta_entregada, almacen_a, metodo_pos)
        headers = {"HTTP_IDEMPOTENCY_KEY": "devolucion-pos-1"}

        r1 = client_a.post(_url(venta_entregada), payload, format="json", **headers)
        assert r1.status_code == 201, r1.data
        r2 = client_a.post(_url(venta_entregada), payload, format="json", **headers)
        assert r2.status_code == 201

        # Misma respuesta reproducida y UNA sola devolución/egreso en BD.
        assert r2.data["devolucion"]["id_devolucion"] == r1.data["devolucion"]["id_devolucion"]
        assert DevolucionVenta.objects.filter(id_nota_venta_origen=venta_entregada).count() == 1
        assert Pago.objects.filter(
            id_empresa=venta_entregada.id_empresa, tipo_operacion="EGRESO"
        ).count() == 1

    def test_idempotencia_misma_clave_payload_distinto_422(
        self, client_a, venta_entregada, almacen_a, metodo_pos, sesion_a
    ):
        headers = {"HTTP_IDEMPOTENCY_KEY": "devolucion-pos-2"}
        r1 = client_a.post(
            _url(venta_entregada),
            _payload(venta_entregada, almacen_a, metodo_pos, cantidad="2"),
            format="json",
            **headers,
        )
        assert r1.status_code == 201
        r2 = client_a.post(
            _url(venta_entregada),
            _payload(venta_entregada, almacen_a, metodo_pos, cantidad="3"),
            format="json",
            **headers,
        )
        assert r2.status_code == 422
        assert DevolucionVenta.objects.count() == 1

    def test_sobre_devolucion_400(self, client_a, venta_entregada, almacen_a, metodo_pos, sesion_a):
        r1 = client_a.post(
            _url(venta_entregada),
            _payload(venta_entregada, almacen_a, metodo_pos, cantidad="8"),
            format="json",
        )
        assert r1.status_code == 201
        r2 = client_a.post(
            _url(venta_entregada),
            _payload(venta_entregada, almacen_a, metodo_pos, cantidad="3"),
            format="json",
        )
        assert r2.status_code == 400
        assert "más de lo vendido" in str(r2.data)

    def test_validaciones_400(self, client_a, venta_entregada, almacen_a, metodo_pos, sesion_a):
        base = _payload(venta_entregada, almacen_a, metodo_pos)

        sin_almacen = {**base}
        sin_almacen.pop("almacen_id")
        assert client_a.post(_url(venta_entregada), sin_almacen, format="json").status_code == 400

        sin_metodo = {**base}
        sin_metodo.pop("id_metodo_pago")
        assert client_a.post(_url(venta_entregada), sin_metodo, format="json").status_code == 400

        sin_lineas = {**base, "lineas": []}
        assert client_a.post(_url(venta_entregada), sin_lineas, format="json").status_code == 400

        almacen_falso = {**base, "almacen_id": "00000000-0000-0000-0000-000000000000"}
        assert client_a.post(_url(venta_entregada), almacen_falso, format="json").status_code == 400

    def test_aislamiento_user_b_no_devuelve_venta_de_a(
        self, client_b, venta_entregada, almacen_a, metodo_pos
    ):
        """R-CODE-1: la venta de A es invisible para B (404, ni siquiera 403)."""
        resp = client_b.post(
            _url(venta_entregada), _payload(venta_entregada, almacen_a, metodo_pos), format="json"
        )
        assert resp.status_code == 404
        assert DevolucionVenta.objects.count() == 0

    def test_almacen_de_otra_empresa_400(
        self, client_a, venta_entregada, metodo_pos, sesion_a, empresa_b
    ):
        from apps.almacenes.models import Almacen

        almacen_b = Almacen.objects.create(
            id_empresa=empresa_b, nombre_almacen="Almacén B", codigo_almacen="ALM-B-API"
        )
        resp = client_a.post(
            _url(venta_entregada), _payload(venta_entregada, almacen_b, metodo_pos), format="json"
        )
        assert resp.status_code == 400
        assert "almacen_id" in resp.data

    def test_metodo_privado_de_otra_empresa_400(
        self, client_a, venta_entregada, almacen_a, sesion_a, empresa_b
    ):
        metodo_b = MetodoPago.objects.create(
            nombre_metodo="Privado B", tipo_metodo="EFECTIVO", empresa=empresa_b
        )
        resp = client_a.post(
            _url(venta_entregada), _payload(venta_entregada, almacen_a, metodo_b), format="json"
        )
        assert resp.status_code == 400
        assert "id_metodo_pago" in resp.data

    def test_requiere_autenticacion(self, api_client, venta_entregada, almacen_a, metodo_pos):
        resp = api_client.post(
            _url(venta_entregada), _payload(venta_entregada, almacen_a, metodo_pos), format="json"
        )
        assert resp.status_code == 401


# ── GET /devoluciones/ y búsqueda por número ─────────────────────────────────


class TestConsultaDevolucionesAPI:
    def test_estado_devolvible_por_linea(
        self, client_a, venta_entregada, almacen_a, metodo_pos, sesion_a
    ):
        client_a.post(
            _url(venta_entregada),
            _payload(venta_entregada, almacen_a, metodo_pos, cantidad="4"),
            format="json",
        )
        resp = client_a.get(_url(venta_entregada, "devoluciones"))
        assert resp.status_code == 200
        data = resp.data
        assert data["venta"]["numero_nota"] == "NV-API-0001"
        assert data["venta"]["fiscal"] is False
        linea = data["lineas"][0]
        assert linea["cantidad_vendida"] == "10.0000"
        assert linea["cantidad_devuelta"] == "4.0000"
        assert linea["cantidad_disponible"] == "6.0000"
        assert linea["precio_unitario"] == "3.5000"
        assert len(data["devoluciones"]) == 1
        assert data["devoluciones"][0]["monto_total"] == "14.0000"  # 4 × 3.50

    def test_aislamiento_get_devoluciones(self, client_b, venta_entregada):
        assert client_b.get(_url(venta_entregada, "devoluciones")).status_code == 404

    def test_busqueda_por_numero_exacto(self, client_a, client_b, venta_entregada):
        resp = client_a.get("/api/ventas/notas-venta/?numero_nota=nv-api-0001")
        assert resp.status_code == 200
        resultados = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        assert len(resultados) == 1
        assert resultados[0]["numero_nota"] == "NV-API-0001"

        # Sin coincidencia → lista vacía (no error).
        resp = client_a.get("/api/ventas/notas-venta/?numero_nota=NO-EXISTE")
        resultados = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        assert len(resultados) == 0

        # R-CODE-1: B no encuentra la venta de A ni buscándola por número.
        resp = client_b.get("/api/ventas/notas-venta/?numero_nota=NV-API-0001")
        resultados = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        assert len(resultados) == 0
