"""Ramas de error y caminos no cubiertos de apps/manufactura (gate diff-cover ≥95).

Cada test cita en su docstring las líneas objetivo (rama develop d19403a):

- views.py: 94-95 (_parse_decimal inválido), 133 (almacen_id obligatorio),
  182-183 (except de avanzar-etapa), 229-230 (except de costeo), 248 (mrp con
  almacen_id), 254-255 (except de mrp), 354-358 (perform_create de
  EtapaProduccion), 365 (crear-estandar sin empresa), 387 y 389-394
  (perform_create de ConfiguracionManufactura).
- services.py: 202 (etapas ya materializadas), 218 (avance en OF cerrada),
  235 (mano de obra negativa), 245 (observaciones de etapa), 302 (MRP sin BOM),
  319 (MRP filtrado por almacén), 356 (consumo en OF cerrada), 413 (producción
  en OF cerrada).
- mcp.py: 62-63 (cantidad inválida), 71-73 (almacén del tenant), 116 (tenant
  mismatch en costeo), 120 (orden inexistente — R-CODE-1).
- models.py: 267, 316, 340 (__str__ de EtapaProduccion, EtapaOrdenProduccion
  y ConfiguracionManufactura).
"""
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.manufactura import services as mfg
from apps.manufactura.models import (
    ETAPAS_ESTANDAR,
    ConfiguracionManufactura,
    ConsumoMaterial,
    EtapaProduccion,
    ProduccionTerminada,
)

pytestmark = pytest.mark.django_db


def D(x):
    return Decimal(str(x))


BASE = "/api/manufactura/ordenes-produccion"
ETAPAS_BASE = "/api/manufactura/etapas-produccion"
CONFIG_BASE = "/api/manufactura/configuracion"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def escenario(db, empresa_a, moneda_usd):
    """Silla (PT) con BOM 2×Madera@10.00, stock de madera repartido en dos
    almacenes (5 en DC-1, 100 en DC-2) y etapas estándar en el catálogo."""
    from apps.almacenes.models import Almacen
    from apps.inventario.models import (
        CategoriaProducto,
        Producto,
        StockActual,
        UnidadMedida,
    )
    from apps.manufactura.models import ListaMateriales, ListaMaterialesDetalle

    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad DC", abreviatura="UN-DC", tipo="CANTIDAD"
    )
    categoria = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="MFG-DC")
    almacen1 = Almacen.objects.create(
        id_empresa=empresa_a, nombre_almacen="Almacén DC-1", codigo_almacen="DC-1"
    )
    almacen2 = Almacen.objects.create(
        id_empresa=empresa_a, nombre_almacen="Almacén DC-2", codigo_almacen="DC-2"
    )

    def _producto(nombre, costo):
        return Producto.objects.create(
            id_empresa=empresa_a,
            nombre_producto=nombre,
            id_unidad_medida_base=unidad,
            id_categoria=categoria,
            id_moneda_precio=moneda_usd,
            precio_venta_sugerido=D("0"),
            costo_promedio=D(costo),
        )

    silla = _producto("Silla DC", "0")
    madera = _producto("Madera DC", "10.00")
    StockActual.objects.create(
        id_empresa=empresa_a, id_producto=madera, id_almacen=almacen1,
        cantidad_disponible=D("5"), cantidad_comprometida=D("0"),
    )
    StockActual.objects.create(
        id_empresa=empresa_a, id_producto=madera, id_almacen=almacen2,
        cantidad_disponible=D("100"), cantidad_comprometida=D("0"),
    )

    bom = ListaMateriales.objects.create(empresa=empresa_a, producto_final=silla, nombre="BOM Silla DC")
    ListaMaterialesDetalle.objects.create(
        id_lista_materiales=bom, id_producto=madera, cantidad_requerida=D("2"), id_unidad_medida=unidad
    )

    mfg.crear_etapas_estandar(empresa_a)
    return {
        "silla": silla, "madera": madera, "bom": bom,
        "almacen1": almacen1, "almacen2": almacen2,
        "unidad": unidad, "categoria": categoria,
    }


def _orden(empresa, escenario, cantidad="10", con_bom=True):
    """OF de `cantidad` sillas con etapas materializadas (vía service)."""
    return mfg.crear_orden_produccion(
        empresa=empresa,
        producto=escenario["silla"],
        cantidad=D(cantidad),
        lista_materiales=escenario["bom"] if con_bom else None,
    )


@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def user_sin_empresa(db):
    """Usuario autenticado pero sin ninguna empresa asignada (CTF-004)."""
    User = get_user_model()
    return User.objects.create_user(
        username="user_sin_empresa_dc",
        password="testpass123",
        email="sin_empresa@test.com",
        is_active=True,
    )


@pytest.fixture
def client_sin_empresa(user_sin_empresa):
    c = APIClient()
    c.force_authenticate(user=user_sin_empresa)
    return c


# ── views.py — acciones de OrdenProduccion ────────────────────────────────────


class TestAccionesOrdenErrores:
    def test_avanzar_etapa_decimal_invalido_devuelve_400(self, client_a, empresa_a, escenario):
        """views.py 94-95 + 182-183: payload no numérico → ValueError → 400
        con mensaje claro, y ninguna etapa se completa."""
        orden = _orden(empresa_a, escenario)
        resp = client_a.post(
            f"{BASE}/{orden.pk}/avanzar-etapa/", {"horas_trabajadas": "abc"}, format="json"
        )
        assert resp.status_code == 400
        assert resp.data["error"] == "El campo 'horas_trabajadas' no es un número válido."
        assert orden.etapas.filter(estado="pendiente").count() == len(ETAPAS_ESTANDAR)

    def test_consumir_materiales_sin_almacen_id_devuelve_400(self, client_a, empresa_a, escenario):
        """views.py 133: sin almacen_id → 400; la OF no cambia de estado ni
        registra consumos."""
        orden = _orden(empresa_a, escenario)
        resp = client_a.post(f"{BASE}/{orden.pk}/consumir-materiales/", {}, format="json")
        assert resp.status_code == 400
        assert resp.data["error"] == "El campo 'almacen_id' es obligatorio."
        orden.refresh_from_db()
        assert orden.estado == "pendiente"
        assert not ConsumoMaterial.objects.filter(orden_produccion=orden).exists()

    def test_avanzar_etapa_orden_cancelada_devuelve_400(self, client_a, empresa_a, escenario):
        """services.py 218 (+ views.py 182-183): una OF cancelada no admite
        avance de etapas."""
        orden = _orden(empresa_a, escenario)
        orden.estado = "cancelada"
        orden.save(update_fields=["estado"])
        resp = client_a.post(f"{BASE}/{orden.pk}/avanzar-etapa/", {}, format="json")
        assert resp.status_code == 400
        assert resp.data["error"] == "La orden está cancelada; no admite avance de etapas."
        assert orden.etapas.filter(estado="completada").count() == 0

    def test_avanzar_etapa_mano_obra_negativa_devuelve_400(self, client_a, empresa_a, escenario):
        """services.py 235: horas/tarifa/destajo negativos → 400 y la etapa
        sigue pendiente."""
        orden = _orden(empresa_a, escenario)
        resp = client_a.post(
            f"{BASE}/{orden.pk}/avanzar-etapa/", {"horas_trabajadas": "-1"}, format="json"
        )
        assert resp.status_code == 400
        assert "no pueden ser negativas" in resp.data["error"]
        assert orden.etapas.filter(estado="pendiente").count() == len(ETAPAS_ESTANDAR)

    def test_avanzar_etapa_guarda_observaciones(self, client_a, empresa_a, escenario):
        """services.py 245: las observaciones del payload quedan registradas
        en la etapa completada."""
        orden = _orden(empresa_a, escenario)
        resp = client_a.post(
            f"{BASE}/{orden.pk}/avanzar-etapa/",
            {"horas_trabajadas": "2", "tarifa_hora": "5", "observaciones": "turno nocturno"},
            format="json",
        )
        assert resp.status_code == 200, resp.content
        assert resp.data["etapa"]["observaciones"] == "turno nocturno"
        etapa = orden.etapas.get(orden=1)
        assert etapa.estado == "completada"
        assert etapa.observaciones == "turno nocturno"
        assert etapa.costo_mano_obra == D("10")  # 2h × 5 (Decimal, R-CODE-4)

    def test_consumir_materiales_orden_cancelada_devuelve_400(self, client_a, empresa_a, escenario):
        """services.py 356: una OF cancelada no admite consumo de materiales;
        el stock queda intacto."""
        from apps.inventario.models import StockActual

        orden = _orden(empresa_a, escenario)
        orden.estado = "cancelada"
        orden.save(update_fields=["estado"])
        resp = client_a.post(
            f"{BASE}/{orden.pk}/consumir-materiales/",
            {"almacen_id": str(escenario["almacen2"].pk)},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"] == "La orden está cancelada; no admite consumo de materiales."
        assert not ConsumoMaterial.objects.filter(orden_produccion=orden).exists()
        stock = StockActual.objects.get(
            id_producto=escenario["madera"], id_almacen=escenario["almacen2"]
        )
        assert stock.cantidad_disponible == D("100")

    def test_completar_orden_cancelada_devuelve_400(self, client_a, empresa_a, escenario):
        """services.py 413: una OF cancelada no admite más producción; no se
        crea ProduccionTerminada ni entra PT al inventario."""
        from apps.inventario.models import StockActual

        orden = _orden(empresa_a, escenario)
        orden.estado = "cancelada"
        orden.save(update_fields=["estado"])
        resp = client_a.post(
            f"{BASE}/{orden.pk}/completar/",
            {"almacen_id": str(escenario["almacen2"].pk)},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"] == "La orden está cancelada; no admite más producción."
        assert not ProduccionTerminada.objects.filter(orden_produccion=orden).exists()
        assert not StockActual.objects.filter(id_producto=escenario["silla"]).exists()
        orden.refresh_from_db()
        assert orden.estado == "cancelada"

    def test_costeo_orden_cantidad_cero_devuelve_400(self, client_a, empresa_a, escenario):
        """views.py 229-230: el costeo de una OF con cantidad 0 (creada vía
        API, que hoy lo permite) responde 400 con el ManufacturaError, no 500."""
        resp = client_a.post(
            f"{BASE}/",
            {
                "producto": str(escenario["silla"].pk),
                "cantidad": "0.00",
                "fecha_inicio": "2026-06-12",
                "lista_materiales": str(escenario["bom"].pk),
            },
            format="json",
        )
        assert resp.status_code == 201, resp.content
        orden_id = resp.data["id"]
        resp = client_a.get(f"{BASE}/{orden_id}/costeo/")
        assert resp.status_code == 400
        assert resp.data["error"] == "La cantidad producida debe ser positiva."


# ── views.py — MRP de la orden ────────────────────────────────────────────────


class TestMrpOrden:
    def test_mrp_filtra_por_almacen(self, client_a, empresa_a, escenario):
        """views.py 248 + services.py 319: ?almacen_id limita el disponible al
        stock de ese almacén (5 en DC-1 vs 105 global)."""
        orden = _orden(empresa_a, escenario)  # 10 sillas → 20 de madera

        resp = client_a.get(f"{BASE}/{orden.pk}/mrp/")
        assert resp.status_code == 200
        falt = resp.data["faltantes"][0]
        assert falt["producto_id"] == str(escenario["madera"].pk)
        assert D(falt["disponible"]) == D("105")
        assert D(falt["a_comprar"]) == D("0")

        resp = client_a.get(
            f"{BASE}/{orden.pk}/mrp/", {"almacen_id": str(escenario["almacen1"].pk)}
        )
        assert resp.status_code == 200
        falt = resp.data["faltantes"][0]
        assert falt["producto"] == "Madera DC"
        assert D(falt["requerido"]) == D("20")
        assert D(falt["disponible"]) == D("5")
        assert D(falt["a_comprar"]) == D("15")

    def test_mrp_almacen_inexistente_devuelve_400(self, client_a, empresa_a, escenario):
        """views.py 248 + 254-255: almacen_id que no pertenece a la empresa de
        la orden → ValueError → 400 (R-CODE-1)."""
        orden = _orden(empresa_a, escenario)
        resp = client_a.get(f"{BASE}/{orden.pk}/mrp/", {"almacen_id": str(uuid.uuid4())})
        assert resp.status_code == 400
        assert resp.data["error"] == "Almacén no encontrado en la empresa de la orden."

    def test_mrp_orden_sin_bom_devuelve_400(self, client_a, empresa_a, escenario):
        """services.py 302 (+ views.py 254-255): OF sin lista de materiales →
        400 con mensaje claro."""
        orden = _orden(empresa_a, escenario, con_bom=False)
        resp = client_a.get(f"{BASE}/{orden.pk}/mrp/")
        assert resp.status_code == 400
        assert resp.data["error"] == "La orden no tiene lista de materiales asociada."


# ── views.py — EtapaProduccion (catálogo) ─────────────────────────────────────


class TestEtapaProduccionCreate:
    def test_crear_etapa_inyecta_empresa_del_usuario(self, client_a, empresa_a, empresa_b):
        """views.py 354-355 y 358: el POST crea la etapa en la empresa del
        usuario; el campo `empresa` del payload se ignora (read-only, R-CODE-1)."""
        resp = client_a.post(
            f"{ETAPAS_BASE}/",
            {"codigo": "BARNIZ", "nombre": "Barnizado", "orden": 7, "empresa": str(empresa_b.pk)},
            format="json",
        )
        assert resp.status_code == 201, resp.content
        etapa = EtapaProduccion.objects.get(codigo="BARNIZ")
        assert etapa.empresa == empresa_a
        assert etapa.orden == 7

    def test_crear_etapa_usuario_sin_empresa_devuelve_403(self, client_sin_empresa):
        """views.py 356-357: usuario autenticado sin empresa asignada →
        PermissionDenied (403) y no se crea nada."""
        resp = client_sin_empresa.post(
            f"{ETAPAS_BASE}/", {"codigo": "HUERFANA", "nombre": "X", "orden": 1}, format="json"
        )
        assert resp.status_code == 403
        assert not EtapaProduccion.objects.filter(codigo="HUERFANA").exists()

    def test_crear_estandar_usuario_sin_empresa_devuelve_403(self, client_sin_empresa):
        """views.py 363-365: crear-estandar sin empresa asignada → 403 con
        error claro y sin sembrar etapas."""
        resp = client_sin_empresa.post(f"{ETAPAS_BASE}/crear-estandar/")
        assert resp.status_code == 403
        assert resp.data["error"] == "El usuario no tiene empresa asignada."
        assert EtapaProduccion.objects.count() == 0


# ── views.py — ConfiguracionManufactura ───────────────────────────────────────


class TestConfiguracionManufacturaCreate:
    def test_crear_configuracion_inyecta_empresa(self, client_a, empresa_a):
        """views.py 387, 389-390, 392 y 394: el POST crea la config para la
        empresa del usuario con overhead Decimal (R-CODE-4)."""
        resp = client_a.post(f"{CONFIG_BASE}/", {"porcentaje_overhead": "12.5"}, format="json")
        assert resp.status_code == 201, resp.content
        config = ConfiguracionManufactura.objects.get(empresa=empresa_a)
        assert config.porcentaje_overhead == D("12.5")

    def test_crear_configuracion_duplicada_devuelve_400(self, client_a, empresa_a):
        """views.py 392-393: la empresa ya tiene configuración (OneToOne) →
        400 y la config original no cambia."""
        ConfiguracionManufactura.objects.create(empresa=empresa_a, porcentaje_overhead=D("10"))
        resp = client_a.post(f"{CONFIG_BASE}/", {"porcentaje_overhead": "20"}, format="json")
        assert resp.status_code == 400
        assert "ya tiene configuración" in str(resp.data)
        assert ConfiguracionManufactura.objects.filter(empresa=empresa_a).count() == 1
        assert ConfiguracionManufactura.objects.get(empresa=empresa_a).porcentaje_overhead == D("10")

    def test_crear_configuracion_usuario_sin_empresa_devuelve_403(self, client_sin_empresa):
        """views.py 391: usuario sin empresa → PermissionDenied (403)."""
        resp = client_sin_empresa.post(
            f"{CONFIG_BASE}/", {"porcentaje_overhead": "5"}, format="json"
        )
        assert resp.status_code == 403
        assert ConfiguracionManufactura.objects.count() == 0


# ── services.py — etapas ──────────────────────────────────────────────────────


class TestServiciosEtapas:
    def test_crear_etapas_para_orden_es_idempotente(self, empresa_a, escenario):
        """services.py 201-202: si la OF ya tiene etapas materializadas, la
        segunda llamada devuelve las existentes sin duplicar."""
        orden = _orden(empresa_a, escenario)
        existentes = sorted(orden.etapas.values_list("pk", flat=True))
        assert len(existentes) == len(ETAPAS_ESTANDAR)

        resultado = mfg.crear_etapas_para_orden(orden)

        assert sorted(e.pk for e in resultado) == existentes
        assert orden.etapas.count() == len(ETAPAS_ESTANDAR)  # sin duplicados


# ── mcp.py — herramientas MCP (R-CODE-7) ──────────────────────────────────────


def _token(empresa, scopes=("manufactura:read",)):
    from apps.core.models import CapabilityToken

    tok = CapabilityToken.objects.create(empresa=empresa, nombre="tok-mfg-dc", scopes=list(scopes))
    return str(tok.token)


class TestMcpManufactura:
    def test_calcular_mrp_cantidad_invalida(self, empresa_a, escenario):
        """mcp.py 62-63: cantidad no numérica → ValueError con mensaje claro."""
        from apps.manufactura.mcp import manufactura_calcular_mrp

        with pytest.raises(ValueError, match="no es un número válido"):
            manufactura_calcular_mrp(
                _token(empresa_a), str(empresa_a.id_empresa), str(escenario["bom"].pk), "diez"
            )

    def test_calcular_mrp_almacen_inexistente(self, empresa_a, escenario):
        """mcp.py 71-73: almacen_id que no pertenece al tenant → ValueError."""
        from apps.manufactura.mcp import manufactura_calcular_mrp

        with pytest.raises(ValueError, match="Almacén no encontrado"):
            manufactura_calcular_mrp(
                _token(empresa_a),
                str(empresa_a.id_empresa),
                str(escenario["bom"].pk),
                "10",
                almacen_id=str(uuid.uuid4()),
            )

    def test_calcular_mrp_filtra_por_almacen(self, empresa_a, escenario):
        """mcp.py 71-72 (rama feliz): el MRP se limita al stock del almacén
        indicado (5 en DC-1 → a comprar 15 de 20)."""
        from apps.manufactura.mcp import manufactura_calcular_mrp

        res = manufactura_calcular_mrp(
            _token(empresa_a),
            str(empresa_a.id_empresa),
            str(escenario["bom"].pk),
            "10",
            almacen_id=str(escenario["almacen1"].pk),
        )
        falt = {f["producto_id"]: f for f in res["faltantes"]}[str(escenario["madera"].pk)]
        assert D(falt["requerido"]) == D("20")
        assert D(falt["disponible"]) == D("5")
        assert D(falt["a_comprar"]) == D("15")

    def test_costeo_orden_empresa_distinta_al_token_rechazada(self, empresa_a, empresa_b, escenario):
        """mcp.py 115-116: empresa_id ≠ tenant del token → PermissionError."""
        from apps.manufactura.mcp import manufactura_get_costeo_orden

        orden = _orden(empresa_a, escenario)
        with pytest.raises(PermissionError, match="no coincide"):
            manufactura_get_costeo_orden(
                _token(empresa_a), str(empresa_b.id_empresa), str(orden.pk)
            )

    def test_costeo_orden_ajena_o_inexistente(self, empresa_a, empresa_b, escenario):
        """mcp.py 118-120: la OF de la empresa A no existe para el token de la
        B (R-CODE-1), igual que un id inexistente → ValueError."""
        from apps.manufactura.mcp import manufactura_get_costeo_orden

        orden_a = _orden(empresa_a, escenario)
        with pytest.raises(ValueError, match="no encontrada"):
            manufactura_get_costeo_orden(
                _token(empresa_b), str(empresa_b.id_empresa), str(orden_a.pk)
            )
        with pytest.raises(ValueError, match="no encontrada"):
            manufactura_get_costeo_orden(
                _token(empresa_a), str(empresa_a.id_empresa), str(uuid.uuid4())
            )


# ── models.py — representaciones ──────────────────────────────────────────────


class TestModelosStr:
    def test_str_etapa_produccion(self, empresa_a):
        """models.py 267: '<orden>. <nombre>' (lo que ve el admin)."""
        etapa = EtapaProduccion.objects.create(
            empresa=empresa_a, codigo="CORTE_DC", nombre="Corte", orden=3
        )
        assert str(etapa) == "3. Corte"

    def test_str_etapa_orden_produccion(self, empresa_a, escenario):
        """models.py 316: 'OP-<id> · <orden>. <etapa> (<estado>)'."""
        orden = _orden(empresa_a, escenario)
        etapa_of = orden.etapas.order_by("orden").first()
        assert str(etapa_of) == f"OP-{orden.pk} · 1. Corte (pendiente)"

    def test_str_configuracion_manufactura(self, empresa_a):
        """models.py 340: identifica la empresa y el % de overhead."""
        config = ConfiguracionManufactura.objects.create(
            empresa=empresa_a, porcentaje_overhead=D("10")
        )
        s = str(config)
        assert s.startswith("Config manufactura ")
        assert "(OH 10%)" in s
        assert str(empresa_a) in s
