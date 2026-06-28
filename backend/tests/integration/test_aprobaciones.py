"""
Tests de aprobaciones configurables por tenant y monto (T03).

Cubre apps/gestion_aprobaciones/services.py y su integración en los flujos de
aprobación de compras (OrdenCompra) y gastos (Gasto).
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.gestion_aprobaciones import services as aprob
from apps.gestion_aprobaciones.models import (
    FlujoAprobacion,
    RegistroAprobacion,
    SolicitudAprobacion,
    TipoAprobacion,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ── Helpers ─────────────────────────────────────────────────────────────────


def _tipo(empresa, codigo="ORDEN_COMPRA"):
    return TipoAprobacion.objects.create(
        id_empresa=empresa, codigo_tipo=codigo, nombre_tipo=codigo,
        modulo_origen=codigo.lower(), activo=True,
    )


def _etapa(tipo, orden=1, minimo=None, maximo=None, usuario=None, activo=True):
    return FlujoAprobacion.objects.create(
        id_tipo_aprobacion=tipo, orden_etapa=orden, nombre_etapa=f"Etapa {orden}",
        monto_minimo=minimo, monto_maximo=maximo, id_usuario_aprobador=usuario,
        activo=activo,
    )


@pytest.fixture
def proveedor(db, empresa_a):
    from apps.proveedores.models import Proveedor

    return Proveedor.objects.create(
        id_empresa=empresa_a, razon_social="Prov Aprob", rif="J-30303030-3"
    )


@pytest.fixture
def producto(db, empresa_a, moneda_usd):
    from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida

    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad Aprob", abreviatura="UN-AP", tipo="CANTIDAD"
    )
    categoria = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="Cat AP")
    return Producto.objects.create(
        id_empresa=empresa_a, nombre_producto="Prod AP", sku="PROD-AP-1",
        id_unidad_medida_base=unidad, id_categoria=categoria, id_moneda_precio=moneda_usd,
    )


_OC_SEQ = []


def _orden(empresa, proveedor, monto, producto, estado="BORRADOR"):
    """Crea una OrdenCompra con una línea cuyo subtotal = ``monto`` (el total de
    la OC se computa sumando los subtotales de sus líneas)."""
    from apps.compras.models import DetalleOrdenCompra, OrdenCompra

    _OC_SEQ.append(1)
    numero = f"OC-AP-{len(_OC_SEQ)}"
    oc = OrdenCompra.objects.create(
        id_empresa=empresa, id_proveedor=proveedor, numero_orden=numero,
        fecha_orden=timezone.now().date(), estado=estado,
    )
    DetalleOrdenCompra.objects.create(
        id_orden_compra=oc, id_producto=producto, cantidad=Decimal("1"),
        precio_unitario=Decimal(monto), subtotal=Decimal(monto),
    )
    return oc


# ── Servicio: evaluar / requiere ────────────────────────────────────────────


class TestEvaluarEtapas:
    def test_sin_tipo_no_requiere(self, empresa_a):
        assert aprob.requiere_aprobacion(empresa_a, "ORDEN_COMPRA", Decimal("1000")) is False

    def test_monto_bajo_umbral_no_requiere(self, empresa_a):
        tipo = _tipo(empresa_a)
        _etapa(tipo, minimo=Decimal("500"))
        assert aprob.requiere_aprobacion(empresa_a, "ORDEN_COMPRA", Decimal("100")) is False

    def test_monto_sobre_umbral_requiere(self, empresa_a):
        tipo = _tipo(empresa_a)
        _etapa(tipo, minimo=Decimal("500"))
        assert aprob.requiere_aprobacion(empresa_a, "ORDEN_COMPRA", Decimal("800")) is True

    def test_etapa_inactiva_no_aplica(self, empresa_a):
        tipo = _tipo(empresa_a)
        _etapa(tipo, minimo=Decimal("500"), activo=False)
        assert aprob.requiere_aprobacion(empresa_a, "ORDEN_COMPRA", Decimal("800")) is False

    def test_rango_con_maximo(self, empresa_a):
        tipo = _tipo(empresa_a)
        _etapa(tipo, minimo=Decimal("100"), maximo=Decimal("500"))
        assert aprob.requiere_aprobacion(empresa_a, "ORDEN_COMPRA", Decimal("300")) is True
        assert aprob.requiere_aprobacion(empresa_a, "ORDEN_COMPRA", Decimal("600")) is False


# ── Servicio: crear_solicitud / registrar_decision ──────────────────────────


class TestSolicitudYDecision:
    def test_crear_solicitud_idempotente(self, empresa_a, user_a, proveedor, producto):
        tipo = _tipo(empresa_a)
        _etapa(tipo, minimo=Decimal("100"))
        oc = _orden(empresa_a, proveedor, "1000", producto)
        s1 = aprob.crear_solicitud(oc, empresa_a, user_a, "ORDEN_COMPRA", Decimal("1000"))
        s2 = aprob.crear_solicitud(oc, empresa_a, user_a, "ORDEN_COMPRA", Decimal("1000"))
        assert s1.pk == s2.pk
        assert SolicitudAprobacion.objects.filter(id_entidad_origen=oc.pk).count() == 1

    def test_crear_solicitud_sin_regla_devuelve_none(self, empresa_a, user_a, proveedor, producto):
        oc = _orden(empresa_a, proveedor, "1000", producto)
        assert aprob.crear_solicitud(oc, empresa_a, user_a, "ORDEN_COMPRA", Decimal("1000")) is None

    def test_aprobar_etapa_unica_marca_aprobada(self, empresa_a, user_a, proveedor, producto):
        tipo = _tipo(empresa_a)
        _etapa(tipo, minimo=Decimal("100"))
        oc = _orden(empresa_a, proveedor, "1000", producto)
        sol = aprob.crear_solicitud(oc, empresa_a, user_a, "ORDEN_COMPRA", Decimal("1000"))
        aprob.registrar_decision(sol, user_a, aprobado=True)
        sol.refresh_from_db()
        assert sol.estado_solicitud == aprob.APROBADA
        assert aprob.esta_aprobada(oc) is True
        assert RegistroAprobacion.objects.filter(id_solicitud_aprobacion=sol).count() == 1

    def test_rechazar_marca_rechazada(self, empresa_a, user_a, proveedor, producto):
        tipo = _tipo(empresa_a)
        _etapa(tipo, minimo=Decimal("100"))
        oc = _orden(empresa_a, proveedor, "1000", producto)
        sol = aprob.crear_solicitud(oc, empresa_a, user_a, "ORDEN_COMPRA", Decimal("1000"))
        aprob.registrar_decision(sol, user_a, aprobado=False, comentarios="Sin presupuesto")
        sol.refresh_from_db()
        assert sol.estado_solicitud == aprob.RECHAZADA
        assert aprob.esta_aprobada(oc) is False

    def test_multietapa_requiere_dos_aprobaciones(self, empresa_a, user_a, proveedor, producto):
        tipo = _tipo(empresa_a)
        _etapa(tipo, orden=1, minimo=Decimal("100"))
        _etapa(tipo, orden=2, minimo=Decimal("100"))
        oc = _orden(empresa_a, proveedor, "1000", producto)
        sol = aprob.crear_solicitud(oc, empresa_a, user_a, "ORDEN_COMPRA", Decimal("1000"))
        aprob.registrar_decision(sol, user_a, aprobado=True)
        sol.refresh_from_db()
        assert sol.estado_solicitud == aprob.PENDIENTE  # falta la segunda etapa
        aprob.registrar_decision(sol, user_a, aprobado=True)
        sol.refresh_from_db()
        assert sol.estado_solicitud == aprob.APROBADA

    def test_decidir_sobre_no_pendiente_error(self, empresa_a, user_a, proveedor, producto):
        tipo = _tipo(empresa_a)
        _etapa(tipo, minimo=Decimal("100"))
        oc = _orden(empresa_a, proveedor, "1000", producto)
        sol = aprob.crear_solicitud(oc, empresa_a, user_a, "ORDEN_COMPRA", Decimal("1000"))
        aprob.registrar_decision(sol, user_a, aprobado=True)
        with pytest.raises(aprob.AprobacionError, match="no está pendiente"):
            aprob.registrar_decision(sol, user_a, aprobado=True)


# ── Integración compras ─────────────────────────────────────────────────────


class TestIntegracionCompras:
    def test_oc_bajo_umbral_aprueba_directo(self, empresa_a, user_a, proveedor, producto):
        from apps.compras.services import aprobar_orden_compra

        tipo = _tipo(empresa_a)
        _etapa(tipo, minimo=Decimal("5000"))  # umbral alto
        oc = _orden(empresa_a, proveedor, "1000", producto)
        aprobar_orden_compra(oc, user_a)
        oc.refresh_from_db()
        assert oc.estado == "APROBADA"

    def test_oc_sobre_umbral_bloquea_y_crea_solicitud(self, empresa_a, user_a, proveedor, producto):
        from apps.compras.services import CompraError, aprobar_orden_compra

        tipo = _tipo(empresa_a)
        _etapa(tipo, minimo=Decimal("500"))
        oc = _orden(empresa_a, proveedor, "1000", producto)
        with pytest.raises(CompraError, match="requiere aprobación"):
            aprobar_orden_compra(oc, user_a)
        oc.refresh_from_db()
        assert oc.estado == "BORRADOR"  # no avanzó
        assert SolicitudAprobacion.objects.filter(id_entidad_origen=oc.pk).count() == 1

    def test_oc_aprueba_tras_solicitud_aprobada(self, empresa_a, user_a, proveedor, producto):
        from apps.compras.services import CompraError, aprobar_orden_compra

        tipo = _tipo(empresa_a)
        _etapa(tipo, minimo=Decimal("500"))
        oc = _orden(empresa_a, proveedor, "1000", producto)
        with pytest.raises(CompraError):
            aprobar_orden_compra(oc, user_a)
        sol = SolicitudAprobacion.objects.get(id_entidad_origen=oc.pk)
        aprob.registrar_decision(sol, user_a, aprobado=True)
        aprobar_orden_compra(oc, user_a)
        oc.refresh_from_db()
        assert oc.estado == "APROBADA"


# ── Integración gastos ──────────────────────────────────────────────────────


class TestIntegracionGastos:
    @pytest.fixture
    def categoria(self, empresa_a):
        from apps.gastos.models import CategoriaGasto

        return CategoriaGasto.objects.create(id_empresa=empresa_a, nombre_categoria="Cat Aprob")

    def _gasto(self, empresa, categoria, moneda, monto):
        from apps.gastos.models import Gasto

        return Gasto.objects.create(
            id_empresa=empresa, fecha_gasto=timezone.now().date(), descripcion="g",
            monto=Decimal(monto), id_moneda=moneda, id_categoria_gasto=categoria,
            tiene_factura=True, estado_gasto="PENDIENTE_APROBACION",
        )

    def test_gasto_sobre_umbral_bloquea(self, empresa_a, user_a, categoria, moneda_usd):
        from apps.gastos.services import GastoError, aprobar_gasto

        tipo = _tipo(empresa_a, "GASTO")
        _etapa(tipo, minimo=Decimal("500"))
        gasto = self._gasto(empresa_a, categoria, moneda_usd, "1000")
        with pytest.raises(GastoError, match="requiere aprobación"):
            aprobar_gasto(gasto, usuario=user_a)
        gasto.refresh_from_db()
        assert gasto.estado_gasto == "PENDIENTE_APROBACION"
        assert SolicitudAprobacion.objects.filter(id_entidad_origen=gasto.pk).count() == 1

    def test_gasto_aprueba_tras_aprobacion(self, empresa_a, user_a, categoria, moneda_usd):
        from apps.gastos.services import GastoError, aprobar_gasto

        tipo = _tipo(empresa_a, "GASTO")
        _etapa(tipo, minimo=Decimal("500"))
        gasto = self._gasto(empresa_a, categoria, moneda_usd, "1000")
        with pytest.raises(GastoError):
            aprobar_gasto(gasto, usuario=user_a)
        sol = SolicitudAprobacion.objects.get(id_entidad_origen=gasto.pk)
        aprob.registrar_decision(sol, user_a, aprobado=True)
        aprobar_gasto(gasto, usuario=user_a)
        gasto.refresh_from_db()
        assert gasto.estado_gasto in ("APROBADO", "CONTABILIZADO")


# ── API: decidir ────────────────────────────────────────────────────────────


class TestDecidirEndpoint:
    @pytest.fixture
    def client_a(self, user_a):
        from rest_framework.test import APIClient

        c = APIClient()
        c.force_authenticate(user=user_a)
        return c

    def test_decidir_aprueba_via_api(self, empresa_a, user_a, proveedor, producto, client_a):
        tipo = _tipo(empresa_a)
        _etapa(tipo, minimo=Decimal("100"))
        oc = _orden(empresa_a, proveedor, "1000", producto)
        sol = aprob.crear_solicitud(oc, empresa_a, user_a, "ORDEN_COMPRA", Decimal("1000"))
        url = f"/api/gestion-aprobaciones/solicitudes-aprobacion/{sol.pk}/decidir/"
        resp = client_a.post(url, {"aprobado": True, "comentarios": "ok"}, format="json")
        assert resp.status_code == 200
        assert resp.data["estado_solicitud"] == aprob.APROBADA

    def test_decidir_sin_campo_400(self, empresa_a, user_a, proveedor, producto, client_a):
        tipo = _tipo(empresa_a)
        _etapa(tipo, minimo=Decimal("100"))
        oc = _orden(empresa_a, proveedor, "1000", producto)
        sol = aprob.crear_solicitud(oc, empresa_a, user_a, "ORDEN_COMPRA", Decimal("1000"))
        url = f"/api/gestion-aprobaciones/solicitudes-aprobacion/{sol.pk}/decidir/"
        resp = client_a.post(url, {}, format="json")
        assert resp.status_code == 400


# ── Authz del aprobador (SEC HIGH) + blindaje de creación (SEC LOW-5) ─────────


def _segundo_usuario(empresa):
    from tests.factories import UsuariosFactory

    return UsuariosFactory(username="user_a2", email="a2@alpha.test", empresa=empresa)


class TestAuthzAprobador:
    def test_solo_usuario_designado_decide(self, empresa_a, user_a, proveedor, producto):
        tipo = _tipo(empresa_a)
        _etapa(tipo, minimo=Decimal("100"), usuario=user_a)  # aprobador designado
        oc = _orden(empresa_a, proveedor, "1000", producto)
        sol = aprob.crear_solicitud(oc, empresa_a, user_a, "ORDEN_COMPRA", Decimal("1000"))
        otro = _segundo_usuario(empresa_a)
        with pytest.raises(aprob.AprobacionError, match="aprobador designado"):
            aprob.registrar_decision(sol, otro, aprobado=True)
        # El designado sí puede.
        aprob.registrar_decision(sol, user_a, aprobado=True)
        sol.refresh_from_db()
        assert sol.estado_solicitud == aprob.APROBADA

    def test_rol_aprobador_requerido(self, empresa_a, user_a, proveedor, producto):
        from apps.core.models import Roles, UsuarioRoles
        from apps.gestion_aprobaciones.models import FlujoAprobacion

        rol = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Aprobador Compras")
        tipo = _tipo(empresa_a)
        FlujoAprobacion.objects.create(
            id_tipo_aprobacion=tipo, orden_etapa=1, nombre_etapa="E", monto_minimo=Decimal("100"),
            rol_aprobador=rol, activo=True,
        )
        oc = _orden(empresa_a, proveedor, "1000", producto)
        sol = aprob.crear_solicitud(oc, empresa_a, user_a, "ORDEN_COMPRA", Decimal("1000"))
        with pytest.raises(aprob.AprobacionError, match="rol aprobador"):
            aprob.registrar_decision(sol, user_a, aprobado=True)
        UsuarioRoles.objects.create(id_usuario=user_a, id_rol=rol)
        aprob.registrar_decision(sol, user_a, aprobado=True)
        sol.refresh_from_db()
        assert sol.estado_solicitud == aprob.APROBADA


class TestCreacionBlindada:
    @pytest.fixture
    def client_a(self, user_a):
        from rest_framework.test import APIClient

        c = APIClient()
        c.force_authenticate(user=user_a)
        return c

    def test_post_directo_solicitud_405(self, empresa_a, user_a, client_a):
        tipo = _tipo(empresa_a)
        resp = client_a.post(
            "/api/gestion-aprobaciones/solicitudes-aprobacion/",
            {
                "id_tipo_aprobacion": str(tipo.id_tipo_aprobacion),
                "id_entidad_origen": str(user_a.pk),
                "nombre_modelo_origen": "OrdenCompra",
                "id_usuario_solicitante": str(user_a.pk),
            },
            format="json",
        )
        assert resp.status_code == 405
