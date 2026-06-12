"""1.I — OF con etapas + costeo real + MRP básico (services y API).

Cobertura DoD:
  - Ciclo completo: crear → consumir materiales → avanzar etapas → completar
    → entrada de PT valorada al costo real EXACTO (verificado a mano).
  - Cerrar OF con etapas pendientes → ManufacturaError / HTTP 400.
  - MRP con faltantes correctos (stock neto = disponible − comprometido).
  - Aislamiento multi-tenant de modelos y acciones nuevas (R-CODE-1).
  - El costeo usa el costo del consumo (snapshot), no el costo_promedio vigente.
"""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.manufactura import services as mfg
from apps.manufactura.models import (
    ETAPAS_ESTANDAR,
    ConfiguracionManufactura,
    EtapaProduccion,
)


def D(x):
    return Decimal(str(x))


# ── Núcleo puro (sin BD) ──────────────────────────────────────────────────────


def test_calcular_costo_mano_obra_horas_y_destajo():
    etapas = [
        (D("2"), D("5"), D("0")),     # 10
        (D("0"), D("0"), D("15")),    # destajo puro
        (D("1.5"), D("4"), D("2")),   # 6 + 2
    ]
    assert mfg.calcular_costo_mano_obra(etapas) == D("33")


def test_calcular_overhead_porcentaje():
    assert mfg.calcular_overhead(D("349"), D("10")) == D("34.9000")
    assert mfg.calcular_overhead(D("100"), D("0")) == D("0.0000")


# ── Fixtures de escenario ─────────────────────────────────────────────────────


@pytest.fixture
def base_mfg(db, empresa_a, moneda_usd):
    """Unidad, categoría y almacén de la empresa A."""
    from apps.almacenes.models import Almacen
    from apps.inventario.models import CategoriaProducto, UnidadMedida

    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad 1I", abreviatura="UN-1I", tipo="CANTIDAD"
    )
    categoria = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="MFG-1I")
    almacen = Almacen.objects.create(
        id_empresa=empresa_a, nombre_almacen="Almacén 1I", codigo_almacen="AL-1I"
    )
    return unidad, categoria, almacen


def _producto(empresa, unidad, categoria, moneda, nombre, costo):
    from apps.inventario.models import Producto

    return Producto.objects.create(
        id_empresa=empresa,
        nombre_producto=nombre,
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda,
        precio_venta_sugerido=D("0"),
        costo_promedio=D(costo),
    )


def _stock(empresa, producto, almacen, cantidad, comprometida="0"):
    from apps.inventario.models import StockActual

    return StockActual.objects.create(
        id_empresa=empresa, id_producto=producto, id_almacen=almacen,
        cantidad_disponible=D(cantidad), cantidad_comprometida=D(comprometida),
    )


@pytest.fixture
def escenario(db, empresa_a, moneda_usd, base_mfg):
    """Silla (PT) con BOM 2×Madera@12.50 + 0.5×Tela@8.00, stock de sobra,
    etapas estándar (TAPIZADO a destajo 1.50/u) y overhead 10%."""
    from apps.manufactura.models import ListaMateriales, ListaMaterialesDetalle

    unidad, categoria, almacen = base_mfg
    silla = _producto(empresa_a, unidad, categoria, moneda_usd, "Silla 1I", "0")
    madera = _producto(empresa_a, unidad, categoria, moneda_usd, "Madera 1I", "12.50")
    tela = _producto(empresa_a, unidad, categoria, moneda_usd, "Tela 1I", "8.00")
    _stock(empresa_a, madera, almacen, "100")
    _stock(empresa_a, tela, almacen, "100")

    bom = ListaMateriales.objects.create(empresa=empresa_a, producto_final=silla, nombre="BOM Silla 1I")
    ListaMaterialesDetalle.objects.create(
        id_lista_materiales=bom, id_producto=madera, cantidad_requerida=D("2"), id_unidad_medida=unidad
    )
    ListaMaterialesDetalle.objects.create(
        id_lista_materiales=bom, id_producto=tela, cantidad_requerida=D("0.5"), id_unidad_medida=unidad
    )

    mfg.crear_etapas_estandar(empresa_a)
    EtapaProduccion.objects.filter(empresa=empresa_a, codigo="TAPIZADO").update(tarifa_destajo=D("1.50"))
    ConfiguracionManufactura.objects.create(empresa=empresa_a, porcentaje_overhead=D("10"))

    return {
        "almacen": almacen, "silla": silla, "madera": madera, "tela": tela,
        "bom": bom, "unidad": unidad, "categoria": categoria,
    }


# ── Ciclo completo por services (costeo verificado a mano) ───────────────────


@pytest.mark.django_db
def test_ciclo_completo_of_etapas_costeo_real(empresa_a, escenario, user_a):
    """OF de 10 sillas. Verificación manual:
    materiales = 20×12.50 + 5×8.00 = 290
    mano de obra = 2×5 + 3×4 + 1.5×4 + 2×5 + (10×1.50 destajo) + 1×6 = 59
    overhead 10% de (290+59) = 34.90
    total = 383.90 → unitario = 38.3900
    """
    from apps.inventario.models import StockActual

    orden = mfg.crear_orden_produccion(
        empresa=empresa_a, producto=escenario["silla"], cantidad=D("10"),
        lista_materiales=escenario["bom"],
    )
    # Las etapas del catálogo se materializan en la OF, en secuencia.
    assert list(orden.etapas.values_list("etapa__codigo", flat=True)) == [c for c, _ in ETAPAS_ESTANDAR]

    res = mfg.consumir_materiales_orden(orden, almacen=escenario["almacen"], usuario=user_a)
    assert res["costo_materiales"] == D("290")

    # Avanzar las 6 etapas con horas/tarifas y destajo en TAPIZADO.
    plan = [
        ("CORTE", D("2"), D("5"), D("0")),
        ("ENSAMBLE", D("3"), D("4"), D("0")),
        ("LIJADO", D("1.5"), D("4"), D("0")),
        ("PINTURA", D("2"), D("5"), D("0")),
        ("TAPIZADO", D("0"), D("0"), D("10")),   # 10 u × 1.50 = 15
        ("CONTROL_FINAL", D("1"), D("6"), D("0")),
    ]
    for codigo, horas, tarifa, cant_destajo in plan:
        etapa = mfg.avanzar_etapa_orden(
            orden, usuario=user_a, horas_trabajadas=horas,
            tarifa_hora=tarifa, cantidad_destajo=cant_destajo,
        )
        assert etapa.etapa.codigo == codigo
        assert etapa.estado == "completada"
        assert etapa.completada_por == user_a       # quién
        assert etapa.fecha_completada is not None   # cuándo

    assert mfg.costo_mano_obra_orden(orden) == D("59")

    out = mfg.registrar_produccion_terminada(
        orden, cantidad=D("10"), almacen=escenario["almacen"], usuario=user_a
    )
    costo = out["costo"]
    assert costo["costo_materiales"] == D("290")
    assert costo["mano_obra"] == D("59")
    assert costo["costos_indirectos"] == D("34.9000")
    assert costo["costo_total"] == D("383.9000")
    assert costo["costo_unitario"] == D("38.3900")

    orden.refresh_from_db()
    assert orden.estado == "finalizada"
    # Entrada de PT al inventario.
    stock_pt = StockActual.objects.get(id_producto=escenario["silla"], id_almacen=escenario["almacen"])
    assert stock_pt.cantidad_disponible == D("10")


@pytest.mark.django_db
def test_no_cerrar_of_con_etapas_pendientes(empresa_a, escenario, user_a):
    orden = mfg.crear_orden_produccion(
        empresa=empresa_a, producto=escenario["silla"], cantidad=D("2"),
        lista_materiales=escenario["bom"],
    )
    mfg.consumir_materiales_orden(orden, almacen=escenario["almacen"], usuario=user_a)
    mfg.avanzar_etapa_orden(orden, usuario=user_a)  # solo CORTE

    with pytest.raises(mfg.ManufacturaError, match="pendiente"):
        mfg.registrar_produccion_terminada(
            orden, cantidad=D("2"), almacen=escenario["almacen"], usuario=user_a
        )
    orden.refresh_from_db()
    assert orden.estado == "en_proceso"  # nada se cerró


@pytest.mark.django_db
def test_costeo_usa_snapshot_del_consumo_no_costo_vigente(empresa_a, escenario, user_a):
    """Si costo_promedio cambia DESPUÉS del consumo, el costeo real no cambia."""
    orden = mfg.crear_orden_produccion(
        empresa=empresa_a, producto=escenario["silla"], cantidad=D("4"),
        lista_materiales=escenario["bom"],
    )
    mfg.consumir_materiales_orden(orden, almacen=escenario["almacen"], usuario=user_a)
    # materiales = 8×12.50 + 2×8.00 = 116
    escenario["madera"].costo_promedio = D("999")
    escenario["madera"].save(update_fields=["costo_promedio"])

    costo = mfg.costeo_real_orden(orden, mano_obra=D("0"), costos_indirectos=D("0"))
    assert costo["costo_materiales"] == D("116")


@pytest.mark.django_db
def test_avanzar_etapa_sin_pendientes_falla(empresa_a, escenario, user_a):
    orden = mfg.crear_orden_produccion(
        empresa=empresa_a, producto=escenario["silla"], cantidad=D("1"),
        lista_materiales=escenario["bom"],
    )
    for _ in range(len(ETAPAS_ESTANDAR)):
        mfg.avanzar_etapa_orden(orden, usuario=user_a)
    with pytest.raises(mfg.ManufacturaError, match="pendientes"):
        mfg.avanzar_etapa_orden(orden, usuario=user_a)


@pytest.mark.django_db
def test_orden_sin_etapas_configuradas_opera_flujo_simple(empresa_a, base_mfg, moneda_usd, user_a):
    """Empresa sin catálogo de etapas: la OF se crea sin etapas y puede cerrarse
    (retro-compatibilidad con el flujo existente)."""
    unidad, categoria, almacen = base_mfg
    producto = _producto(empresa_a, unidad, categoria, moneda_usd, "Banco simple", "0")
    orden = mfg.crear_orden_produccion(empresa=empresa_a, producto=producto, cantidad=D("1"))
    assert orden.etapas.count() == 0
    out = mfg.registrar_produccion_terminada(
        orden, cantidad=D("1"), almacen=almacen, usuario=user_a, mano_obra=D("5")
    )
    assert out["costo"]["costo_total"] == D("5")


# ── MRP básico ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_mrp_faltantes_correctos(empresa_a, escenario, user_a):
    """OF de 10 sillas → requiere 20 madera y 5 tela. Stock neto de madera = 10
    (12 disponibles − 2 comprometidas) → a comprar 10. Tela sobra → 0."""
    from apps.inventario.models import StockActual

    StockActual.objects.filter(id_producto=escenario["madera"]).update(
        cantidad_disponible=D("12"), cantidad_comprometida=D("2")
    )
    orden = mfg.crear_orden_produccion(
        empresa=empresa_a, producto=escenario["silla"], cantidad=D("10"),
        lista_materiales=escenario["bom"],
    )
    faltantes = {f["producto_id"]: f for f in mfg.calcular_mrp_orden(orden)}

    madera = faltantes[str(escenario["madera"].pk)]
    assert madera["requerido"] == D("20")
    assert madera["disponible"] == D("10")
    assert madera["a_comprar"] == D("10")
    assert madera["producto"] == "Madera 1I"

    tela = faltantes[str(escenario["tela"].pk)]
    assert tela["requerido"] == D("5")
    assert tela["a_comprar"] == D("0")


@pytest.mark.django_db
def test_mrp_ignora_stock_de_otra_empresa(empresa_a, empresa_b, escenario, moneda_usd):
    """R-CODE-1: el stock de la empresa B no cuenta para el MRP de la empresa A."""
    from apps.almacenes.models import Almacen

    almacen_b = Almacen.objects.create(
        id_empresa=empresa_b, nombre_almacen="Almacén B 1I", codigo_almacen="AL-B1I"
    )
    # Stock enorme del MISMO producto pero en empresa B (caso borde teórico).
    _stock(empresa_b, escenario["madera"], almacen_b, "1000")
    from apps.inventario.models import StockActual
    StockActual.objects.filter(
        id_producto=escenario["madera"], id_empresa=empresa_a
    ).update(cantidad_disponible=D("0"))

    faltantes = {
        f["producto_id"]: f
        for f in mfg.calcular_mrp_lista(escenario["bom"], D("10"))
    }
    assert faltantes[str(escenario["madera"].pk)]["a_comprar"] == D("20")


# ── API (acciones del ViewSet, R-CODE-7) ─────────────────────────────────────


@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def client_b(user_b):
    c = APIClient()
    c.force_authenticate(user=user_b)
    return c


BASE = "/api/manufactura/ordenes-produccion"


@pytest.mark.django_db
def test_api_ciclo_completo_of(client_a, empresa_a, escenario, user_a):
    """Ciclo completo vía API: crear → consumir → avanzar etapas → completar
    → costeo. Mismo escenario verificado a mano que el test de services."""
    resp = client_a.post(
        "/api/manufactura/ordenes-produccion/",
        {
            "producto": str(escenario["silla"].pk),
            "cantidad": "10.00",
            "fecha_inicio": "2026-06-11",
            "lista_materiales": str(escenario["bom"].pk),
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    orden_id = resp.data["id"]
    almacen_id = str(escenario["almacen"].pk)

    # Etapas materializadas
    resp = client_a.get(f"{BASE}/{orden_id}/etapas/")
    assert resp.status_code == 200
    assert [e["etapa_codigo"] for e in resp.data] == [c for c, _ in ETAPAS_ESTANDAR]

    # MRP antes de consumir (stock 100/100 → sin faltantes)
    resp = client_a.get(f"{BASE}/{orden_id}/mrp/")
    assert resp.status_code == 200
    assert all(D(f["a_comprar"]) == 0 for f in resp.data["faltantes"])

    # Consumir materiales
    resp = client_a.post(
        f"{BASE}/{orden_id}/consumir-materiales/", {"almacen_id": almacen_id}, format="json"
    )
    assert resp.status_code == 200, resp.content
    assert resp.data["costo_materiales"] == "290.0000"
    assert resp.data["estado"] == "en_proceso"

    # Completar con etapas pendientes → 400
    resp = client_a.post(f"{BASE}/{orden_id}/completar/", {"almacen_id": almacen_id}, format="json")
    assert resp.status_code == 400
    assert "pendiente" in resp.data["error"]

    # Avanzar las 6 etapas
    plan = [
        {"horas_trabajadas": "2", "tarifa_hora": "5"},
        {"horas_trabajadas": "3", "tarifa_hora": "4"},
        {"horas_trabajadas": "1.5", "tarifa_hora": "4"},
        {"horas_trabajadas": "2", "tarifa_hora": "5"},
        {"cantidad_destajo": "10"},  # TAPIZADO a destajo: 10 × 1.50
        {"horas_trabajadas": "1", "tarifa_hora": "6"},
    ]
    for body in plan:
        resp = client_a.post(f"{BASE}/{orden_id}/avanzar-etapa/", body, format="json")
        assert resp.status_code == 200, resp.content
    assert resp.data["etapas_pendientes"] == 0
    assert resp.data["etapa"]["completada_por"] == user_a.pk

    # Completar → entrada de PT valorada al costo real
    resp = client_a.post(f"{BASE}/{orden_id}/completar/", {"almacen_id": almacen_id}, format="json")
    assert resp.status_code == 200, resp.content
    assert resp.data["estado"] == "finalizada"
    assert resp.data["costo"]["costo_total"] == "383.9000"
    assert resp.data["costo"]["costo_unitario"] == "38.3900"

    # Costeo consultable después del cierre
    resp = client_a.get(f"{BASE}/{orden_id}/costeo/")
    assert resp.status_code == 200
    assert resp.data["costo"]["costo_unitario"] == "38.3900"
    assert len(resp.data["etapas"]) == len(ETAPAS_ESTANDAR)


@pytest.mark.django_db
def test_api_almacen_de_otra_empresa_rechazado(client_a, empresa_a, empresa_b, escenario, user_a):
    """R-CODE-1: no se puede consumir contra un almacén de otra empresa."""
    from apps.almacenes.models import Almacen

    almacen_b = Almacen.objects.create(
        id_empresa=empresa_b, nombre_almacen="Almacén ajeno", codigo_almacen="AL-X"
    )
    orden = mfg.crear_orden_produccion(
        empresa=empresa_a, producto=escenario["silla"], cantidad=D("1"),
        lista_materiales=escenario["bom"],
    )
    resp = client_a.post(
        f"{BASE}/{orden.pk}/consumir-materiales/", {"almacen_id": str(almacen_b.pk)}, format="json"
    )
    assert resp.status_code == 400
    assert "no encontrado" in resp.data["error"].lower()


@pytest.mark.django_db
def test_api_aislamiento_ordenes_y_etapas(client_b, empresa_a, escenario, user_a):
    """R-CODE-1: el usuario de la empresa B no ve ni opera la OF de la A,
    ni su catálogo de etapas."""
    orden = mfg.crear_orden_produccion(
        empresa=empresa_a, producto=escenario["silla"], cantidad=D("1"),
        lista_materiales=escenario["bom"],
    )
    for url in (
        f"{BASE}/{orden.pk}/",
        f"{BASE}/{orden.pk}/etapas/",
        f"{BASE}/{orden.pk}/costeo/",
        f"{BASE}/{orden.pk}/mrp/",
    ):
        assert client_b.get(url).status_code == 404, url
    assert client_b.post(f"{BASE}/{orden.pk}/avanzar-etapa/", {}, format="json").status_code == 404
    assert client_b.post(f"{BASE}/{orden.pk}/completar/", {}, format="json").status_code == 404

    # Catálogo de etapas: la empresa B no ve las etapas de la A.
    resp = client_b.get("/api/manufactura/etapas-produccion/")
    assert resp.status_code == 200
    nombres = [e["codigo"] for e in resp.data["results"]]
    assert nombres == []


@pytest.mark.django_db
def test_api_crear_estandar_y_soft_delete_etapa(client_a, empresa_a):
    resp = client_a.post("/api/manufactura/etapas-produccion/crear-estandar/")
    assert resp.status_code == 201
    assert len(resp.data["creadas"]) == len(ETAPAS_ESTANDAR)
    # Idempotente
    resp = client_a.post("/api/manufactura/etapas-produccion/crear-estandar/")
    assert resp.status_code == 200
    assert resp.data["creadas"] == []

    etapa_id = str(EtapaProduccion.objects.filter(empresa=empresa_a, codigo="PINTURA").get().pk)
    # DELETE = soft-delete (R-CODE-6)
    resp = client_a.delete(f"/api/manufactura/etapas-produccion/{etapa_id}/")
    assert resp.status_code == 204
    etapa = EtapaProduccion.objects.get(pk=etapa_id)
    assert etapa.activo is False

    # Las nuevas OF ya no materializan la etapa desactivada.
    assert EtapaProduccion.objects.filter(empresa=empresa_a, activo=True).count() == len(ETAPAS_ESTANDAR) - 1


# ── Tools MCP (R-CODE-7) ──────────────────────────────────────────────────────


def _token(empresa, scopes):
    from apps.core.models import CapabilityToken

    tok = CapabilityToken.objects.create(empresa=empresa, nombre="tok-mfg", scopes=scopes)
    return str(tok.token)


@pytest.mark.django_db
def test_mcp_manufactura_calcular_mrp(empresa_a, escenario):
    from apps.inventario.models import StockActual
    from apps.manufactura.mcp import manufactura_calcular_mrp

    StockActual.objects.filter(id_producto=escenario["madera"]).update(
        cantidad_disponible=D("12"), cantidad_comprometida=D("2")
    )
    res = manufactura_calcular_mrp(
        _token(empresa_a, ["manufactura:read"]),
        str(empresa_a.id_empresa),
        str(escenario["bom"].pk),
        "10",
    )
    faltantes = {f["producto_id"]: f for f in res["faltantes"]}
    assert D(faltantes[str(escenario["madera"].pk)]["a_comprar"]) == D("10")
    assert D(faltantes[str(escenario["tela"].pk)]["a_comprar"]) == D("0")


@pytest.mark.django_db
def test_mcp_manufactura_mrp_rechaza_tenant_ajeno(empresa_a, empresa_b, escenario):
    from apps.manufactura.mcp import manufactura_calcular_mrp

    # Token de la empresa B no puede consultar la BOM de la A (R-CODE-1).
    with pytest.raises(PermissionError):
        manufactura_calcular_mrp(
            _token(empresa_b, ["manufactura:read"]),
            str(empresa_a.id_empresa),
            str(escenario["bom"].pk),
            "10",
        )
    # Aunque pase su propio empresa_id, la BOM ajena no existe para él.
    with pytest.raises(ValueError, match="no encontrada"):
        manufactura_calcular_mrp(
            _token(empresa_b, ["manufactura:read"]),
            str(empresa_b.id_empresa),
            str(escenario["bom"].pk),
            "10",
        )


@pytest.mark.django_db
def test_mcp_manufactura_get_costeo_orden(empresa_a, escenario, user_a):
    from apps.manufactura.mcp import manufactura_get_costeo_orden

    orden = mfg.crear_orden_produccion(
        empresa=empresa_a, producto=escenario["silla"], cantidad=D("10"),
        lista_materiales=escenario["bom"],
    )
    mfg.consumir_materiales_orden(orden, almacen=escenario["almacen"], usuario=user_a)
    res = manufactura_get_costeo_orden(
        _token(empresa_a, ["manufactura:read"]),
        str(empresa_a.id_empresa),
        str(orden.pk),
    )
    assert res["costo"]["costo_materiales"] == "290.0000"
    assert len(res["etapas"]) == len(ETAPAS_ESTANDAR)
