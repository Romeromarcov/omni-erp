"""
Tests para M5 — Control de Salidas Internas de Inventario.

Cubre:
  - RequisicionInterna + DetalleRequisicion (modelo y ciclo de vida)
  - aprobar_requisicion()
  - despachar_requisicion_interna()
  - Validación: SALIDA_INTERNA requiere RequisicionInterna APROBADA
  - Aislamiento multi-tenant
"""

import uuid
from decimal import Decimal

import pytest


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def almacen(db, empresa_a):
    from apps.almacenes.models import Almacen

    return Almacen.objects.create(
        id_empresa=empresa_a,
        nombre_almacen="Almacén Central SI",
        codigo_almacen="AC-SI",
    )


@pytest.fixture
def unidad(db, empresa_a):
    from apps.inventario.models import UnidadMedida

    return UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad SI", abreviatura="UN-SI", tipo="CANTIDAD"
    )


@pytest.fixture
def categoria(db, empresa_a):
    from apps.inventario.models import CategoriaProducto

    return CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="General SI")


@pytest.fixture
def producto(db, empresa_a, unidad, categoria, moneda_usd):
    from apps.inventario.models import Producto

    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Producto SI",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        precio_venta_sugerido=Decimal("10.00"),
    )


@pytest.fixture
def stock_con_cantidad(db, empresa_a, producto, almacen):
    """Crea StockActual con 100 unidades disponibles."""
    from apps.inventario.models import StockActual

    return StockActual.objects.create(
        id_empresa=empresa_a,
        id_producto=producto,
        id_almacen=almacen,
        cantidad_disponible=Decimal("100"),
    )


@pytest.fixture
def requisicion(db, empresa_a, almacen, user_a):
    from apps.inventario.models import RequisicionInterna

    return RequisicionInterna.objects.create(
        id_empresa=empresa_a,
        numero_requisicion="REQ-001",
        id_almacen_origen=almacen,
        solicitado_por=user_a,
    )


@pytest.fixture
def requisicion_con_detalle(db, requisicion, producto):
    from apps.inventario.models import DetalleRequisicion

    DetalleRequisicion.objects.create(
        id_requisicion=requisicion,
        id_producto=producto,
        cantidad_solicitada=Decimal("10"),
    )
    return requisicion


# ── Modelo ────────────────────────────────────────────────────────────────────


class TestRequisicionModelo:
    def test_estado_inicial_es_borrador(self, requisicion):
        assert requisicion.estado == "BORRADOR"

    def test_str_incluye_numero_y_estado(self, requisicion):
        assert "REQ-001" in str(requisicion)
        assert "BORRADOR" in str(requisicion)

    def test_unique_numero_por_empresa(self, db, empresa_a, almacen, user_a):
        from django.db import IntegrityError

        from apps.inventario.models import RequisicionInterna

        RequisicionInterna.objects.create(
            id_empresa=empresa_a,
            numero_requisicion="REQ-DUP",
            id_almacen_origen=almacen,
            solicitado_por=user_a,
        )
        with pytest.raises(IntegrityError):
            RequisicionInterna.objects.create(
                id_empresa=empresa_a,
                numero_requisicion="REQ-DUP",
                id_almacen_origen=almacen,
                solicitado_por=user_a,
            )

    def test_aislamiento_tenant_mismo_numero(self, db, empresa_a, empresa_b, almacen, user_a, user_b, moneda_usd):
        """Mismo número de requisición puede existir en empresas distintas."""
        from apps.almacenes.models import Almacen
        from apps.inventario.models import RequisicionInterna

        almacen_b = Almacen.objects.create(id_empresa=empresa_b, nombre_almacen="Almacén B", codigo_almacen="AB-SI")

        r1 = RequisicionInterna.objects.create(
            id_empresa=empresa_a,
            numero_requisicion="REQ-SHARED",
            id_almacen_origen=almacen,
            solicitado_por=user_a,
        )
        r2 = RequisicionInterna.objects.create(
            id_empresa=empresa_b,
            numero_requisicion="REQ-SHARED",
            id_almacen_origen=almacen_b,
            solicitado_por=user_b,
        )
        assert r1.pk != r2.pk


# ── aprobar_requisicion ───────────────────────────────────────────────────────


class TestAprobarRequisicion:
    def test_aprueba_borrador(self, db, requisicion, user_a):
        from apps.inventario.services import aprobar_requisicion

        aprobar_requisicion(requisicion, aprobado_por=user_a)
        requisicion.refresh_from_db()
        assert requisicion.estado == "APROBADA"
        assert requisicion.aprobado_por == user_a
        assert requisicion.fecha_aprobacion is not None

    def test_no_aprueba_ya_aprobada(self, db, requisicion, user_a):
        from apps.inventario.services import RequisicionError, aprobar_requisicion

        aprobar_requisicion(requisicion, aprobado_por=user_a)
        with pytest.raises(RequisicionError, match="BORRADOR"):
            aprobar_requisicion(requisicion, aprobado_por=user_a)

    def test_no_aprueba_cancelada(self, db, requisicion, user_a):
        from apps.inventario.services import RequisicionError, aprobar_requisicion

        requisicion.estado = "CANCELADA"
        requisicion.save(update_fields=["estado"])
        with pytest.raises(RequisicionError):
            aprobar_requisicion(requisicion, aprobado_por=user_a)


# ── despachar_requisicion_interna ─────────────────────────────────────────────


class TestDespacharRequisicion:
    def test_despacho_mueve_stock(self, db, empresa_a, requisicion_con_detalle, stock_con_cantidad, user_a):
        from apps.inventario.models import StockActual
        from apps.inventario.services import aprobar_requisicion, despachar_requisicion_interna

        aprobar_requisicion(requisicion_con_detalle, aprobado_por=user_a)
        disponible_antes = stock_con_cantidad.cantidad_disponible

        movimientos = despachar_requisicion_interna(requisicion_con_detalle, usuario=user_a)

        stock_con_cantidad.refresh_from_db()
        assert len(movimientos) == 1
        assert movimientos[0].tipo_movimiento == "SALIDA_INTERNA"
        assert stock_con_cantidad.cantidad_disponible == disponible_antes - Decimal("10")

    def test_despacho_actualiza_cantidad_despachada(
        self, db, empresa_a, requisicion_con_detalle, stock_con_cantidad, user_a
    ):
        from apps.inventario.models import DetalleRequisicion
        from apps.inventario.services import aprobar_requisicion, despachar_requisicion_interna

        aprobar_requisicion(requisicion_con_detalle, aprobado_por=user_a)
        despachar_requisicion_interna(requisicion_con_detalle, usuario=user_a)

        detalle = DetalleRequisicion.objects.get(id_requisicion=requisicion_con_detalle)
        assert detalle.cantidad_despachada == Decimal("10")

    def test_despacho_transiciona_a_despachada(
        self, db, empresa_a, requisicion_con_detalle, stock_con_cantidad, user_a
    ):
        from apps.inventario.services import aprobar_requisicion, despachar_requisicion_interna

        aprobar_requisicion(requisicion_con_detalle, aprobado_por=user_a)
        despachar_requisicion_interna(requisicion_con_detalle, usuario=user_a)

        requisicion_con_detalle.refresh_from_db()
        assert requisicion_con_detalle.estado == "DESPACHADA"

    def test_no_despacha_sin_aprobar(self, db, requisicion_con_detalle, user_a):
        from apps.inventario.services import RequisicionError, despachar_requisicion_interna

        with pytest.raises(RequisicionError, match="APROBADA"):
            despachar_requisicion_interna(requisicion_con_detalle, usuario=user_a)

    def test_no_despacha_sin_stock(self, db, empresa_a, requisicion_con_detalle, user_a):
        from apps.inventario.services import RequisicionError, aprobar_requisicion, despachar_requisicion_interna

        # Sin stock creado → StockActual en 0
        aprobar_requisicion(requisicion_con_detalle, aprobado_por=user_a)
        with pytest.raises(RequisicionError, match="[Ss]tock"):
            despachar_requisicion_interna(requisicion_con_detalle, usuario=user_a)

    def test_no_despacha_sin_detalles(self, db, requisicion, user_a):
        from apps.inventario.services import RequisicionError, aprobar_requisicion, despachar_requisicion_interna

        aprobar_requisicion(requisicion, aprobado_por=user_a)
        with pytest.raises(RequisicionError, match="detalle"):
            despachar_requisicion_interna(requisicion, usuario=user_a)


# ── Validación SALIDA_INTERNA en registrar_movimiento ─────────────────────────


class TestValidacionSalidaInterna:
    def test_salida_interna_sin_documento_origen_falla(
        self, db, empresa_a, producto, almacen, stock_con_cantidad, user_a
    ):
        from django.utils import timezone

        from apps.inventario.services import MovimientoInvalidoError, registrar_movimiento

        with pytest.raises(MovimientoInvalidoError, match="documento_origen_id"):
            registrar_movimiento(
                empresa=empresa_a,
                fecha_hora_movimiento=timezone.now(),
                tipo_movimiento="SALIDA_INTERNA",
                producto=producto,
                cantidad=Decimal("5"),
                almacen_origen=almacen,
                usuario=user_a,
            )

    def test_salida_interna_con_requisicion_no_aprobada_falla(
        self, db, empresa_a, producto, almacen, stock_con_cantidad, requisicion_con_detalle, user_a
    ):
        from django.utils import timezone

        from apps.inventario.services import MovimientoInvalidoError, registrar_movimiento

        # Estado BORRADOR — no APROBADA
        with pytest.raises(MovimientoInvalidoError, match="APROBADA"):
            registrar_movimiento(
                empresa=empresa_a,
                fecha_hora_movimiento=timezone.now(),
                tipo_movimiento="SALIDA_INTERNA",
                producto=producto,
                cantidad=Decimal("5"),
                almacen_origen=almacen,
                documento_origen_id=requisicion_con_detalle.id_requisicion,
                nombre_modelo_origen="RequisicionInterna",
                usuario=user_a,
            )

    def test_salida_interna_con_requisicion_aprobada_ok(
        self, db, empresa_a, producto, almacen, stock_con_cantidad, requisicion_con_detalle, user_a
    ):
        from django.utils import timezone

        from apps.inventario.services import aprobar_requisicion, registrar_movimiento

        aprobar_requisicion(requisicion_con_detalle, aprobado_por=user_a)

        mov = registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=timezone.now(),
            tipo_movimiento="SALIDA_INTERNA",
            producto=producto,
            cantidad=Decimal("5"),
            almacen_origen=almacen,
            documento_origen_id=requisicion_con_detalle.id_requisicion,
            nombre_modelo_origen="RequisicionInterna",
            usuario=user_a,
        )
        assert mov.tipo_movimiento == "SALIDA_INTERNA"

    def test_salida_interna_con_uuid_inexistente_falla(
        self, db, empresa_a, producto, almacen, stock_con_cantidad, user_a
    ):
        from django.utils import timezone

        from apps.inventario.services import MovimientoInvalidoError, registrar_movimiento

        with pytest.raises(MovimientoInvalidoError, match="no existe"):
            registrar_movimiento(
                empresa=empresa_a,
                fecha_hora_movimiento=timezone.now(),
                tipo_movimiento="SALIDA_INTERNA",
                producto=producto,
                cantidad=Decimal("5"),
                almacen_origen=almacen,
                documento_origen_id=uuid.uuid4(),
                nombre_modelo_origen="RequisicionInterna",
                usuario=user_a,
            )
