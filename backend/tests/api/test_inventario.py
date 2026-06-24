"""
Tests para la lógica de inventario — Semana 6.

Cubre:
  1. registrar_movimiento() (capa de servicio):
     - ENTRADA crea StockActual si no existe
     - ENTRADA incrementa stock existente
     - SALIDA decrementa stock
     - SALIDA sin stock suficiente lanza StockInsuficienteError
     - TRANSFERENCIA mueve stock entre almacenes
     - Validaciones de almacén faltante
  2. API REST:
     - POST /api/inventario/movimientos-inventario/ crea movimiento y actualiza stock
     - Error 400 en SALIDA con stock insuficiente
     - GET /api/inventario/productos/{pk}/kardex/ retorna historial con saldo corriente
  3. Aislamiento multi-tenant:
     - user_b no ve stock ni movimientos de empresa_a
"""

from decimal import Decimal

import pytest

from django.utils import timezone
from rest_framework.test import APIClient

from apps.almacenes.models import Almacen
from apps.inventario.models import Producto, CategoriaProducto, UnidadMedida, StockActual
from apps.inventario.services import (
    MovimientoInvalidoError,
    StockInsuficienteError,
    registrar_movimiento,
)

pytestmark = pytest.mark.django_db


# ── Fixtures locales ──────────────────────────────────────────────────────────


@pytest.fixture
def categoria(empresa_a):
    return CategoriaProducto.objects.create(
        id_empresa=empresa_a,
        nombre_categoria="Lubricantes",
    )


@pytest.fixture
def unidad(empresa_a):
    return UnidadMedida.objects.create(
        id_empresa=empresa_a,
        nombre="Litro",
        abreviatura="L",
        tipo="VOLUMEN",
    )


@pytest.fixture
def almacen_a(empresa_a):
    return Almacen.objects.create(
        id_empresa=empresa_a,
        nombre_almacen="Almacén Principal",
        codigo_almacen="MAIN-001",
    )


@pytest.fixture
def almacen_b(empresa_a):
    return Almacen.objects.create(
        id_empresa=empresa_a,
        nombre_almacen="Almacén Secundario",
        codigo_almacen="SEC-001",
    )


@pytest.fixture
def producto(empresa_a, categoria, unidad, moneda_usd):
    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Aceite Motor 5W-30",
        id_categoria=categoria,
        id_unidad_medida_base=unidad,
        id_moneda_precio=moneda_usd,
    )


# ── Tests de la capa de servicio ──────────────────────────────────────────────


class TestRegistrarMovimiento:

    def test_entrada_crea_stock_inicial(self, user_a, empresa_a, almacen_a, producto):
        registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=timezone.now(),
            tipo_movimiento="ENTRADA",
            producto=producto,
            cantidad=Decimal("100"),
            almacen_destino=almacen_a,
            usuario=user_a,
        )
        stock = StockActual.objects.get(id_producto=producto, id_almacen=almacen_a)
        assert stock.cantidad_disponible == Decimal("100")

    def test_entrada_incrementa_stock_existente(self, user_a, empresa_a, almacen_a, producto):
        now = timezone.now()
        registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=now,
            tipo_movimiento="ENTRADA",
            producto=producto,
            cantidad=Decimal("100"),
            almacen_destino=almacen_a,
            usuario=user_a,
        )
        registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=now,
            tipo_movimiento="ENTRADA",
            producto=producto,
            cantidad=Decimal("50"),
            almacen_destino=almacen_a,
            usuario=user_a,
        )
        stock = StockActual.objects.get(id_producto=producto, id_almacen=almacen_a)
        assert stock.cantidad_disponible == Decimal("150")

    def test_salida_decrementa_stock(self, user_a, empresa_a, almacen_a, producto):
        now = timezone.now()
        registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=now,
            tipo_movimiento="ENTRADA",
            producto=producto,
            cantidad=Decimal("100"),
            almacen_destino=almacen_a,
            usuario=user_a,
        )
        registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=now,
            tipo_movimiento="SALIDA",
            producto=producto,
            cantidad=Decimal("30"),
            almacen_origen=almacen_a,
            usuario=user_a,
        )
        stock = StockActual.objects.get(id_producto=producto, id_almacen=almacen_a)
        assert stock.cantidad_disponible == Decimal("70")

    def test_salida_sin_stock_suficiente_lanza_error(self, user_a, empresa_a, almacen_a, producto):
        with pytest.raises(StockInsuficienteError):
            registrar_movimiento(
                empresa=empresa_a,
                fecha_hora_movimiento=timezone.now(),
                tipo_movimiento="SALIDA",
                producto=producto,
                cantidad=Decimal("10"),
                almacen_origen=almacen_a,
                usuario=user_a,
            )

    def test_transferencia_mueve_stock_entre_almacenes(
        self, user_a, empresa_a, almacen_a, almacen_b, producto
    ):
        now = timezone.now()
        registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=now,
            tipo_movimiento="ENTRADA",
            producto=producto,
            cantidad=Decimal("100"),
            almacen_destino=almacen_a,
            usuario=user_a,
        )
        registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=now,
            tipo_movimiento="TRANSFERENCIA",
            producto=producto,
            cantidad=Decimal("40"),
            almacen_origen=almacen_a,
            almacen_destino=almacen_b,
            usuario=user_a,
        )
        stock_a = StockActual.objects.get(id_producto=producto, id_almacen=almacen_a)
        stock_b = StockActual.objects.get(id_producto=producto, id_almacen=almacen_b)
        assert stock_a.cantidad_disponible == Decimal("60")
        assert stock_b.cantidad_disponible == Decimal("40")

    def test_transferencia_mismo_almacen_lanza_error(
        self, user_a, empresa_a, almacen_a, producto
    ):
        with pytest.raises(MovimientoInvalidoError, match="distintos"):
            registrar_movimiento(
                empresa=empresa_a,
                fecha_hora_movimiento=timezone.now(),
                tipo_movimiento="TRANSFERENCIA",
                producto=producto,
                cantidad=Decimal("10"),
                almacen_origen=almacen_a,
                almacen_destino=almacen_a,
                usuario=user_a,
            )

    def test_entrada_sin_almacen_destino_lanza_error(self, user_a, empresa_a, producto):
        with pytest.raises(MovimientoInvalidoError, match="almacen_destino"):
            registrar_movimiento(
                empresa=empresa_a,
                fecha_hora_movimiento=timezone.now(),
                tipo_movimiento="ENTRADA",
                producto=producto,
                cantidad=Decimal("10"),
                usuario=user_a,
            )

    def test_ajuste_positivo_incrementa_stock(self, user_a, empresa_a, almacen_a, producto):
        registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=timezone.now(),
            tipo_movimiento="AJUSTE",
            producto=producto,
            cantidad=Decimal("25"),
            almacen_destino=almacen_a,
            usuario=user_a,
        )
        stock = StockActual.objects.get(id_producto=producto, id_almacen=almacen_a)
        assert stock.cantidad_disponible == Decimal("25")

    def test_ajuste_negativo_decrementa_stock(self, user_a, empresa_a, almacen_a, producto):
        now = timezone.now()
        registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=now,
            tipo_movimiento="ENTRADA",
            producto=producto,
            cantidad=Decimal("100"),
            almacen_destino=almacen_a,
            usuario=user_a,
        )
        registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=now,
            tipo_movimiento="AJUSTE",
            producto=producto,
            cantidad=Decimal("-20"),
            almacen_destino=almacen_a,
            usuario=user_a,
        )
        stock = StockActual.objects.get(id_producto=producto, id_almacen=almacen_a)
        assert stock.cantidad_disponible == Decimal("80")

    def test_movimiento_es_atomico_si_falla_stock(
        self, user_a, empresa_a, almacen_a, almacen_b, producto
    ):
        """Si la segunda actualización de stock falla, el movimiento completo se revierte."""
        with pytest.raises(StockInsuficienteError):
            registrar_movimiento(
                empresa=empresa_a,
                fecha_hora_movimiento=timezone.now(),
                tipo_movimiento="TRANSFERENCIA",
                producto=producto,
                cantidad=Decimal("50"),  # No hay stock en almacén_a
                almacen_origen=almacen_a,
                almacen_destino=almacen_b,
                usuario=user_a,
            )
        from apps.inventario.models import MovimientoInventario
        assert MovimientoInventario.objects.count() == 0


# ── Tests de la API ───────────────────────────────────────────────────────────


class TestMovimientoInventarioAPI:

    @pytest.fixture(autouse=True)
    def _client(self, user_a):
        self.client = APIClient()
        self.client.force_authenticate(user=user_a)
        self.user_a = user_a

    def test_crear_entrada_via_api(self, empresa_a, almacen_a, producto):
        url = "/api/inventario/movimientos-inventario/"
        payload = {
            "id_empresa": str(empresa_a.pk),
            "fecha_hora_movimiento": "2026-01-15T10:00:00Z",
            "tipo_movimiento": "ENTRADA",
            "id_producto": str(producto.pk),
            "cantidad": "50.0000",
            "id_almacen_destino": str(almacen_a.pk),
        }
        response = self.client.post(url, payload, format="json")
        assert response.status_code == 201

        stock = StockActual.objects.get(id_producto=producto, id_almacen=almacen_a)
        assert stock.cantidad_disponible == Decimal("50")

    def test_api_rechaza_salida_sin_stock(self, empresa_a, almacen_a, producto):
        url = "/api/inventario/movimientos-inventario/"
        payload = {
            "id_empresa": str(empresa_a.pk),
            "fecha_hora_movimiento": "2026-01-15T10:00:00Z",
            "tipo_movimiento": "SALIDA",
            "id_producto": str(producto.pk),
            "cantidad": "10.0000",
            "id_almacen_origen": str(almacen_a.pk),
        }
        response = self.client.post(url, payload, format="json")
        assert response.status_code == 400

    def test_api_usuario_registro_se_asigna_automaticamente(self, empresa_a, almacen_a, producto):
        url = "/api/inventario/movimientos-inventario/"
        payload = {
            "id_empresa": str(empresa_a.pk),
            "fecha_hora_movimiento": "2026-01-15T10:00:00Z",
            "tipo_movimiento": "ENTRADA",
            "id_producto": str(producto.pk),
            "cantidad": "10.0000",
            "id_almacen_destino": str(almacen_a.pk),
        }
        response = self.client.post(url, payload, format="json")
        assert response.status_code == 201
        data = response.json()
        assert str(self.user_a.pk) == str(data["id_usuario_registro"])

    def test_api_aislamiento_empresa_b_no_ve_movimientos(
        self, user_b, empresa_a, almacen_a, producto
    ):
        """user_b pertenece a empresa_b: no debe ver movimientos de empresa_a."""
        registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=timezone.now(),
            tipo_movimiento="ENTRADA",
            producto=producto,
            cantidad=Decimal("100"),
            almacen_destino=almacen_a,
            usuario=self.user_a,
        )
        client_b = APIClient()
        client_b.force_authenticate(user=user_b)
        response = client_b.get("/api/inventario/movimientos-inventario/")
        assert response.status_code == 200
        assert response.json()["count"] == 0


# ── Tests del endpoint kardex ─────────────────────────────────────────────────


class TestKardexEndpoint:

    def test_kardex_retorna_historial_con_saldo_corriente(
        self, user_a, empresa_a, almacen_a, producto
    ):
        client = APIClient()
        client.force_authenticate(user=user_a)
        now = timezone.now()

        registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=now,
            tipo_movimiento="ENTRADA",
            producto=producto,
            cantidad=Decimal("100"),
            almacen_destino=almacen_a,
            usuario=user_a,
        )
        registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=now,
            tipo_movimiento="SALIDA",
            producto=producto,
            cantidad=Decimal("30"),
            almacen_origen=almacen_a,
            usuario=user_a,
        )

        url = f"/api/inventario/productos/{producto.pk}/kardex/?almacen={almacen_a.pk}"
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert data["producto_id"] == str(producto.pk)
        assert len(data["kardex"]) == 2

        entrada, salida = data["kardex"]
        assert Decimal(entrada["saldo_anterior"]) == Decimal("0")
        assert Decimal(entrada["saldo_posterior"]) == Decimal("100")
        assert Decimal(salida["saldo_anterior"]) == Decimal("100")
        assert Decimal(salida["saldo_posterior"]) == Decimal("70")
        assert Decimal(data["saldo_final"]) == Decimal("70")

    def test_kardex_sin_filtro_almacen_retorna_todos_los_movimientos(
        self, user_a, empresa_a, almacen_a, almacen_b, producto
    ):
        client = APIClient()
        client.force_authenticate(user=user_a)
        now = timezone.now()

        registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=now,
            tipo_movimiento="ENTRADA",
            producto=producto,
            cantidad=Decimal("100"),
            almacen_destino=almacen_a,
            usuario=user_a,
        )
        registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=now,
            tipo_movimiento="ENTRADA",
            producto=producto,
            cantidad=Decimal("50"),
            almacen_destino=almacen_b,
            usuario=user_a,
        )

        url = f"/api/inventario/productos/{producto.pk}/kardex/"
        response = client.get(url)

        assert response.status_code == 200
        assert len(response.json()["kardex"]) == 2

    def test_kardex_empresa_b_no_puede_ver_producto_de_empresa_a(
        self, user_b, empresa_a, almacen_a, producto
    ):
        client_b = APIClient()
        client_b.force_authenticate(user=user_b)
        url = f"/api/inventario/productos/{producto.pk}/kardex/"
        response = client_b.get(url)
        assert response.status_code == 404


# ── Tests del endpoint stock-actual ──────────────────────────────────────────


class TestStockActualAPI:

    def test_filtro_por_producto(self, user_a, empresa_a, almacen_a, almacen_b, producto):
        client = APIClient()
        client.force_authenticate(user=user_a)
        now = timezone.now()

        registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=now,
            tipo_movimiento="ENTRADA",
            producto=producto,
            cantidad=Decimal("100"),
            almacen_destino=almacen_a,
            usuario=user_a,
        )
        registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=now,
            tipo_movimiento="ENTRADA",
            producto=producto,
            cantidad=Decimal("50"),
            almacen_destino=almacen_b,
            usuario=user_a,
        )

        url = f"/api/inventario/stock-actual/?producto={producto.pk}"
        response = client.get(url)

        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) == 2
        assert all(r["id_producto"] == str(producto.pk) for r in results)

    def test_filtro_por_almacen(self, user_a, empresa_a, almacen_a, almacen_b, producto):
        client = APIClient()
        client.force_authenticate(user=user_a)
        now = timezone.now()

        for alm in [almacen_a, almacen_b]:
            registrar_movimiento(
                empresa=empresa_a,
                fecha_hora_movimiento=now,
                tipo_movimiento="ENTRADA",
                producto=producto,
                cantidad=Decimal("10"),
                almacen_destino=alm,
                usuario=user_a,
            )

        url = f"/api/inventario/stock-actual/?almacen={almacen_a.pk}"
        response = client.get(url)

        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) == 1
        assert results[0]["id_almacen"] == str(almacen_a.pk)


# ── Tests de la API de Producto (CRUD + metodo_valoracion) ────────────────────


class TestProductoAPI:
    """Cubre el CRUD de productos que consume ProductosPage del frontend, en
    particular que `metodo_valoracion` (FIFO/PROMEDIO) viaje en la whitelist del
    serializer tanto al crear como al leer."""

    @pytest.fixture(autouse=True)
    def _client(self, user_a):
        self.client = APIClient()
        self.client.force_authenticate(user=user_a)

    def test_crear_producto_con_metodo_valoracion_fifo(
        self, empresa_a, categoria, unidad, moneda_usd
    ):
        url = "/api/inventario/productos/"
        payload = {
            "id_empresa": str(empresa_a.pk),
            "nombre_producto": "Filtro de aceite",
            "sku": "FIL-001",
            "id_categoria": str(categoria.pk),
            "id_unidad_medida_base": str(unidad.pk),
            "tipo_producto": "PRODUCTO_FISICO",
            "maneja_lotes": False,
            "maneja_seriales": False,
            "costo_promedio": "5.5000",
            "precio_venta_sugerido": "9.9900",
            "punto_reorden": "10.0000",
            "metodo_valoracion": "FIFO",
            "id_moneda_precio": str(moneda_usd.pk),
        }
        response = self.client.post(url, payload, format="json")
        assert response.status_code == 201, response.content
        data = response.json()
        assert data["metodo_valoracion"] == "FIFO"

        creado = Producto.objects.get(pk=data["id_producto"])
        assert creado.metodo_valoracion == "FIFO"
        assert creado.costo_promedio == Decimal("5.5000")

    def test_listar_productos_incluye_metodo_valoracion(self, producto):
        response = self.client.get("/api/inventario/productos/")
        assert response.status_code == 200
        fila = next(
            p for p in response.json()["results"] if p["id_producto"] == str(producto.pk)
        )
        # default del modelo
        assert fila["metodo_valoracion"] == "PROMEDIO"

    def test_actualizar_metodo_valoracion(self, producto):
        url = f"/api/inventario/productos/{producto.pk}/"
        response = self.client.patch(url, {"metodo_valoracion": "FIFO"}, format="json")
        assert response.status_code == 200, response.content
        producto.refresh_from_db()
        assert producto.metodo_valoracion == "FIFO"
