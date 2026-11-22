"""Tests integrales de P2-4: caché multi-tenant sobre ``CACHES["default"]``,
invalidación automática por signals, visibilidad BFS de subsidiarias y barrido N+1.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.cache_utils import (
    GLOBAL_TENANT_KEY,
    build_cache_key,
    bump_namespace_version,
    bump_namespaces,
    get_cached_or_set,
    get_namespace_version,
    normalize_namespace,
    normalize_tenant_key,
)
from apps.core.models import CapabilityToken, Contacto, Empresa, Sucursal
from apps.core.viewsets import (
    get_all_subsidiarias,
    get_empresas_visible,
    iniciar_cache_empresas_visible,
    limpiar_cache_empresas_visible,
)
from tests.factories import (
    AlmacenFactory,
    ClienteFactory,
    EmpresaFactory,
    MonedaFactory,
    ProductoFactory,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _limpiar_cache_p24():
    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# 1. Capa cache_utils: aislamiento multi-tenant, versionado y serialización
# ---------------------------------------------------------------------------


class TestCacheUtilsMultiTenant:
    def test_aislamiento_entre_tenants_y_global(self):
        emp_a = uuid.uuid4()
        emp_b = uuid.uuid4()

        val_a = get_cached_or_set("catalogo.test", emp_a, "k1", lambda: {"tenant": "A"})
        val_b = get_cached_or_set("catalogo.test", emp_b, "k1", lambda: {"tenant": "B"})
        val_g = get_cached_or_set("catalogo.test", GLOBAL_TENANT_KEY, "k1", lambda: {"tenant": "G"})

        assert val_a == {"tenant": "A"}
        assert val_b == {"tenant": "B"}
        assert val_g == {"tenant": "G"}

        # Lecturas posteriores devuelven exactamente su tenant sin ejecutar factory
        assert get_cached_or_set("catalogo.test", emp_a, "k1", lambda: {"tenant": "ERR"}) == {"tenant": "A"}
        assert get_cached_or_set("catalogo.test", emp_b, "k1", lambda: {"tenant": "ERR"}) == {"tenant": "B"}
        assert get_cached_or_set("catalogo.test", None, "k1", lambda: {"tenant": "ERR"}) == {"tenant": "G"}

    def test_hit_miss_y_negative_caching_none(self):
        llamadas = {"count": 0}

        def _factory_none():
            llamadas["count"] += 1
            return None

        assert get_cached_or_set("neg.test", "global", "missing", _factory_none) is None
        assert get_cached_or_set("neg.test", "global", "missing", _factory_none) is None
        assert llamadas["count"] == 1

    def test_bump_namespace_version_selectivo_no_afecta_otros_tenants(self):
        emp_a = uuid.uuid4()
        emp_b = uuid.uuid4()
        llamadas = {"a": 0, "b": 0}

        def _fac_a():
            llamadas["a"] += 1
            return f"a-{llamadas['a']}"

        def _fac_b():
            llamadas["b"] += 1
            return f"b-{llamadas['b']}"

        assert get_cached_or_set("ns.iso", emp_a, "clave", _fac_a) == "a-1"
        assert get_cached_or_set("ns.iso", emp_b, "clave", _fac_b) == "b-1"
        assert get_namespace_version("ns.iso", emp_a) == 1
        assert get_namespace_version("ns.iso", emp_b) == 1

        # Invalidar solo emp_a
        nueva_ver = bump_namespace_version("ns.iso", emp_a)
        assert nueva_ver == 2
        assert get_namespace_version("ns.iso", emp_b) == 1

        assert get_cached_or_set("ns.iso", emp_a, "clave", _fac_a) == "a-2"
        assert get_cached_or_set("ns.iso", emp_b, "clave", _fac_b) == "b-1"
        assert llamadas == {"a": 2, "b": 1}

    def test_bump_en_frio_inicializa_en_1_y_subkeys_especiales_no_colisionan(self):
        ver = bump_namespace_version("ns.cold", "global")
        assert ver == 1
        assert bump_namespace_version("ns.cold", "global") == 2

        k1 = build_cache_key("ns.cold", "global", "a:b")
        k2 = build_cache_key("ns.cold", "global", "a/b")
        assert k1 != k2

    def test_rechaza_queryset_e_instancia_orm(self, empresa_a):
        with pytest.raises(TypeError, match="QuerySet"):
            get_cached_or_set("bad.qs", empresa_a.pk, "q", lambda: Empresa.objects.all())

        with pytest.raises(TypeError, match="instancias ORM"):
            get_cached_or_set("bad.orm", empresa_a.pk, "m", lambda: empresa_a)

        with pytest.raises(TypeError, match="colecciones"):
            get_cached_or_set("bad.list", empresa_a.pk, "l", lambda: (empresa_a,))


# ---------------------------------------------------------------------------
# 2. get_empresas_visible & get_all_subsidiarias (BFS + Redis/LocMem + signals)
# ---------------------------------------------------------------------------


class TestEmpresasVisibleCacheYBFS:
    def test_bfs_jerarquia_multinivel_constante_por_profundidad(self, moneda_usd):
        matriz = EmpresaFactory(nombre_legal="Matriz Holding", id_moneda_base=moneda_usd)
        subs = [
            EmpresaFactory(nombre_legal=f"Sub {i}", empresa_matriz=matriz, id_moneda_base=moneda_usd) for i in range(4)
        ]
        nietas = []
        for sub in subs:
            for j in range(3):
                nietas.append(
                    EmpresaFactory(nombre_legal=f"Nieta {sub.pk}-{j}", empresa_matriz=sub, id_moneda_base=moneda_usd)
                )

        # 12 nietas + 4 subs = 16 descendientes, profundidad 2:
        # BFS hace 3 queries (nivel 1, nivel 2, frontera nivel 3 vacía), jamás 1 + 4 + 12.
        with CaptureQueriesContext(connection) as ctx:
            descendientes = get_all_subsidiarias(matriz)
        assert len(descendientes) == 16
        assert len(ctx) == 3

        esperado = {s.pk for s in subs} | {n.pk for n in nietas}
        assert descendientes == esperado

    def test_cache_distribuido_y_signals_empresa_y_m2m(self, empresa_a, empresa_b, user_a, user_b, moneda_usd):
        # 1. Primer call sin ContextVar: consulta BD y pobla CACHES["default"]
        with CaptureQueriesContext(connection) as q_miss:
            visibles_1 = set(get_empresas_visible(user_a).values_list("id_empresa", flat=True))
        assert visibles_1 == {empresa_a.pk}
        assert any("usuarios_empresas" in q["sql"] for q in q_miss)

        # 2. Segundo call sin ContextVar: hit de CACHES["default"] → 0 queries a usuarios_empresas,
        #    solo 1 query final Empresa.objects.filter(id_empresa__in=...)
        with CaptureQueriesContext(connection) as q_hit:
            visibles_2 = set(get_empresas_visible(user_a).values_list("id_empresa", flat=True))
        assert visibles_2 == {empresa_a.pk}
        assert len(q_hit) == 1
        assert "usuarios_empresas" not in q_hit[0]["sql"]

        # 3. Precalentar caché de user_b también
        assert set(get_empresas_visible(user_b).values_list("id_empresa", flat=True)) == {empresa_b.pk}

        # 4. Crear subsidiaria de empresa_a invalida jerarquía vía post_save(Empresa)
        sub_a = EmpresaFactory(nombre_legal="Sub A Nueva", empresa_matriz=empresa_a, id_moneda_base=moneda_usd)
        visibles_post_sub = set(get_empresas_visible(user_a).values_list("id_empresa", flat=True))
        assert visibles_post_sub == {empresa_a.pk, sub_a.pk}
        # Cero fuga cross-tenant
        assert set(get_empresas_visible(user_b).values_list("id_empresa", flat=True)) == {empresa_b.pk}

        # 5. Reparentar sub_a hacia empresa_b invalida de inmediato
        sub_a.empresa_matriz = empresa_b
        sub_a.save()
        assert set(get_empresas_visible(user_a).values_list("id_empresa", flat=True)) == {empresa_a.pk}
        assert set(get_empresas_visible(user_b).values_list("id_empresa", flat=True)) == {empresa_b.pk, sub_a.pk}

        # 6. Borrar sub_a invalida vía post_delete(Empresa)
        sub_a.delete()
        assert set(get_empresas_visible(user_b).values_list("id_empresa", flat=True)) == {empresa_b.pk}

        # 7. Cambiar user_a.empresas invalida solo a user_a (user_b sigue en caché)
        with CaptureQueriesContext(connection) as q_b_warm:
            assert set(get_empresas_visible(user_b).values_list("id_empresa", flat=True)) == {empresa_b.pk}
        assert len(q_b_warm) == 1

        user_a.empresas.add(empresa_b)
        assert set(get_empresas_visible(user_a).values_list("id_empresa", flat=True)) == {empresa_a.pk, empresa_b.pk}
        user_a.empresas.remove(empresa_b)
        assert set(get_empresas_visible(user_a).values_list("id_empresa", flat=True)) == {empresa_a.pk}

    def test_contextvar_l1_evita_incluso_query_cache_hit(self, empresa_a, user_a):
        token = iniciar_cache_empresas_visible()
        try:
            _ = list(get_empresas_visible(user_a))
            with CaptureQueriesContext(connection) as q_l1:
                ids = set(get_empresas_visible(user_a).values_list("id_empresa", flat=True))
            assert ids == {empresa_a.pk}
            assert len(q_l1) == 1
        finally:
            limpiar_cache_empresas_visible(token)


# ---------------------------------------------------------------------------
# 3. Caché caliente en Finanzas y ConfiguracionMotor + invalidación signals
# ---------------------------------------------------------------------------


class TestFinanzasYConfiguracionCache:
    def test_tasa_cambio_hit_aislamiento_y_signals(self, empresa_a, empresa_b, moneda_usd):
        from apps.finanzas.models import Moneda, TasaCambio
        from apps.finanzas.services import TasaCambioError, convertir_monto, obtener_tasa_cambio

        ves = Moneda.objects.create(
            codigo_iso="VES",
            nombre="Bolívar",
            simbolo="Bs",
            tipo_moneda="fiat",
            es_generica=True,
        )
        hoy = timezone.localdate()
        tasa_global = TasaCambio.objects.create(
            id_empresa=None,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=ves,
            tipo_tasa="OFICIAL_BCV",
            valor_tasa=Decimal("36.50000000"),
            fecha_tasa=hoy,
        )
        tasa_a = TasaCambio.objects.create(
            id_empresa=empresa_a,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=ves,
            tipo_tasa="ESPECIAL_USUARIO",
            valor_tasa=Decimal("38.00000000"),
            fecha_tasa=hoy,
        )

        # Primera lectura por código ISO (miss → llena caché de monedas y tasa)
        res_a1 = obtener_tasa_cambio("USD", "VES", empresa=empresa_a, fecha=hoy)
        res_b1 = obtener_tasa_cambio("USD", "VES", empresa=empresa_b, fecha=hoy)
        assert res_a1.valor_tasa == Decimal("38.00000000")
        assert isinstance(res_a1.valor_tasa, Decimal)
        assert res_b1.valor_tasa == Decimal("36.50000000")  # fallback BCV para empresa_b

        # Segunda lectura → 0 queries SQL!
        with CaptureQueriesContext(connection) as q_hit:
            res_a2 = obtener_tasa_cambio("USD", "VES", empresa=empresa_a, fecha=hoy)
            res_b2 = obtener_tasa_cambio("USD", "VES", empresa=empresa_b, fecha=hoy)
            monto = convertir_monto(Decimal("10.00"), "USD", "VES", empresa=empresa_a, fecha=hoy)
        assert len(q_hit) == 0
        assert res_a2.valor_tasa == Decimal("38.00000000")
        assert res_b2.valor_tasa == Decimal("36.50000000")
        assert monto == Decimal("380.0000")

        # Actualizar tasa de empresa_a invalida solo empresa_a (empresa_b sigue en 0 queries)
        tasa_a.valor_tasa = Decimal("39.25000000")
        tasa_a.save()
        with CaptureQueriesContext(connection) as q_b_still_cached:
            assert obtener_tasa_cambio("USD", "VES", empresa=empresa_b, fecha=hoy).valor_tasa == Decimal("36.50000000")
        assert len(q_b_still_cached) == 0
        assert obtener_tasa_cambio("USD", "VES", empresa=empresa_a, fecha=hoy).valor_tasa == Decimal("39.25000000")

        # Actualizar tasa global BCV invalida también el fallback en empresa_b
        tasa_global.valor_tasa = Decimal("37.10000000")
        tasa_global.save()
        assert obtener_tasa_cambio("USD", "VES", empresa=empresa_b, fecha=hoy).valor_tasa == Decimal("37.10000000")
        assert obtener_tasa_cambio("USD", "VES", empresa=None, fecha=hoy).valor_tasa == Decimal("37.10000000")

        # Eliminar tasa global deja a empresa_b sin tasa
        tasa_global.delete()
        with pytest.raises(TasaCambioError):
            obtener_tasa_cambio("USD", "VES", empresa=empresa_b, fecha=hoy)

    def test_tasa_oficial_bcv_endpoint_cache_e_invalidacion(self, client_a, moneda_usd):
        from apps.finanzas.models import Moneda, TasaCambio

        ves = Moneda.objects.create(
            codigo_iso="VES", nombre="Bolívar", simbolo="Bs", tipo_moneda="fiat", es_generica=True
        )
        hoy = timezone.localdate()
        tasa = TasaCambio.objects.create(
            id_empresa=None,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=ves,
            tipo_tasa="OFICIAL_BCV",
            valor_tasa=Decimal("40.00000000"),
            fecha_tasa=hoy,
        )

        url = f"/api/finanzas/tasa-oficial-bcv/?moneda_origen=USD&moneda_destino=VES&fecha={hoy.isoformat()}"
        r1 = client_a.get(url)
        assert r1.status_code == 200
        assert r1.data["valor_tasa"] == "40.00000000"

        with CaptureQueriesContext(connection) as q_hit:
            r2 = client_a.get(url)
        assert r2.status_code == 200
        assert not any("finanzas_tasacambio" in q["sql"] for q in q_hit)

        tasa.valor_tasa = Decimal("42.50000000")
        tasa.save()
        r3 = client_a.get(url)
        assert r3.status_code == 200
        assert r3.data["valor_tasa"] == "42.50000000"

    def test_moneda_y_moneda_activa_cache_aislamiento_e_invalidacion(self, empresa_a, empresa_b, client_a):
        from apps.finanzas.cache import obtener_moneda_por_iso
        from apps.finanzas.models import Moneda, MonedaEmpresaActiva

        mon_a = Moneda.objects.create(
            empresa=empresa_a,
            codigo_iso="PRVA",
            nombre="Privada A",
            simbolo="A",
            tipo_moneda="otro",
        )
        Moneda.objects.create(
            empresa=empresa_b,
            codigo_iso="PRVB",
            nombre="Privada B",
            simbolo="B",
            tipo_moneda="otro",
        )

        # Aislamiento estricto por empresa en monedas privadas
        assert obtener_moneda_por_iso("PRVA", empresa_id=empresa_a.pk) is not None
        assert obtener_moneda_por_iso("PRVB", empresa_id=empresa_a.pk) is None

        with CaptureQueriesContext(connection) as q_hit:
            m2 = obtener_moneda_por_iso("PRVA", empresa_id=empresa_a.pk)
        assert m2 is not None and m2.nombre == "Privada A"
        assert not any("finanzas_moneda" in q["sql"] for q in q_hit)

        mon_a.nombre = "Privada A Editada"
        mon_a.save()
        m3 = obtener_moneda_por_iso("PRVA", empresa_id=empresa_a.pk)
        assert m3 is not None and m3.nombre == "Privada A Editada"

        # MonedaEmpresaActiva cache en endpoint /activas/ (moneda_post_save ya la activa)
        mea = MonedaEmpresaActiva.objects.get(empresa=empresa_a, moneda=mon_a)
        assert mea.activa is True
        r1 = client_a.get("/api/finanzas/monedas/activas/")
        assert r1.status_code == 200
        assert any(row["codigo_iso"] == "PRVA" for row in r1.data["results"])

        with CaptureQueriesContext(connection) as q_activas_hit:
            r2 = client_a.get("/api/finanzas/monedas/activas/")
        assert r2.status_code == 200
        assert not any("finanzas_monedaempresaactiva" in q["sql"] for q in q_activas_hit)

        mea.activa = False
        mea.save()
        r3 = client_a.get("/api/finanzas/monedas/activas/")
        assert not any(row["codigo_iso"] == "PRVA" for row in r3.data["results"])

    def test_metodo_pago_mcp_cache_aislamiento_e_invalidacion(self, empresa_a, empresa_b, metodo_efectivo):
        from apps.finanzas.mcp import finanzas_get_metodos_pago
        from apps.finanzas.models import MetodoPago

        tok_a = str(CapabilityToken.objects.create(empresa=empresa_a, nombre="T-A", scopes=["finanzas:read"]).token)
        tok_b = str(CapabilityToken.objects.create(empresa=empresa_b, nombre="T-B", scopes=["finanzas:read"]).token)

        mp_a = MetodoPago.objects.create(empresa=empresa_a, nombre_metodo="Zelle A", tipo_metodo="ELECTRONICO")
        mp_b = MetodoPago.objects.create(empresa=empresa_b, nombre_metodo="Zelle B", tipo_metodo="ELECTRONICO")

        res_a1 = finanzas_get_metodos_pago(tok_a)
        nombres_a1 = {m["nombre_metodo"] for m in res_a1}
        assert "Zelle A" in nombres_a1
        assert "Zelle B" not in nombres_a1

        # Segundo call → hit de caché (sin tocar finanzas_metodo_pago)
        with CaptureQueriesContext(connection) as q_hit:
            res_a2 = finanzas_get_metodos_pago(tok_a)
        assert res_a2 == res_a1
        assert not any("finanzas_metodo_pago" in q["sql"] for q in q_hit)

        # Empresa B no mezcla resultados con Empresa A
        res_b = finanzas_get_metodos_pago(tok_b)
        nombres_b = {m["nombre_metodo"] for m in res_b}
        assert "Zelle B" in nombres_b
        assert "Zelle A" not in nombres_b

        # Signal invalida tras update y delete
        mp_a.nombre_metodo = "Zelle A Renovado"
        mp_a.save()
        assert "Zelle A Renovado" in {m["nombre_metodo"] for m in finanzas_get_metodos_pago(tok_a)}

        mp_b.delete()
        assert "Zelle B" not in {m["nombre_metodo"] for m in finanzas_get_metodos_pago(tok_b)}

    def test_parametro_sistema_cache_aislamiento_y_signals(self, empresa_a, empresa_b):
        from apps.configuracion_motor.models import ParametroSistema
        from apps.configuracion_motor.services import obtener_parametro
        from apps.cxc.config import CxcConfig

        ParametroSistema.objects.create(
            id_empresa=None,
            nombre_parametro="Stock Negativo Global",
            codigo_parametro="permitir_stock_negativo_pos",
            valor_parametro="false",
            tipo_dato="BOOLEANO",
        )
        p_a = ParametroSistema.objects.create(
            id_empresa=empresa_a,
            nombre_parametro="Datasource A",
            codigo_parametro="cxc.datasource",
            valor_parametro="odoo",
            tipo_dato="TEXTO",
        )
        ParametroSistema.objects.create(
            id_empresa=empresa_b,
            nombre_parametro="Datasource B",
            codigo_parametro="cxc.datasource",
            valor_parametro="native",
            tipo_dato="TEXTO",
        )

        # Primera lectura (miss) + segunda lectura (hit = 0 queries)
        assert obtener_parametro("cxc.datasource", empresa=empresa_a) == "odoo"
        assert obtener_parametro("cxc.datasource", empresa=empresa_b) == "native"
        assert obtener_parametro("permitir_stock_negativo_pos", empresa=empresa_b, incluir_global=True) == "false"

        with CaptureQueriesContext(connection) as q_hit:
            assert obtener_parametro("cxc.datasource", empresa=empresa_a) == "odoo"
            assert obtener_parametro("cxc.datasource", empresa=empresa_b) == "native"
            assert obtener_parametro("permitir_stock_negativo_pos", empresa=empresa_b, incluir_global=True) == "false"
        assert len(q_hit) == 0

        # CxcConfig.para_empresa usa el servicio cacheado
        cfg_a = CxcConfig.para_empresa(empresa_a)
        assert cfg_a.datasource == "odoo"
        with CaptureQueriesContext(connection) as q_cfg_hit:
            assert CxcConfig.para_empresa(empresa_a).datasource == "odoo"
        assert len(q_cfg_hit) == 0

        # Actualizar parámetro de A invalida A sin tocar B
        p_a.valor_parametro = "native"
        p_a.save()
        with CaptureQueriesContext(connection) as q_b_warm:
            assert obtener_parametro("cxc.datasource", empresa=empresa_b) == "native"
        assert len(q_b_warm) == 0
        assert obtener_parametro("cxc.datasource", empresa=empresa_a) == "native"

        # Eliminar parámetro de A cae al default
        p_a.delete()
        assert obtener_parametro("cxc.datasource", empresa=empresa_a, default="native") == "native"


# ---------------------------------------------------------------------------
# 4. Barrido N+1 (O(1) queries para N=2 vs N=8) en ViewSets intervenidos
# ---------------------------------------------------------------------------


def _contar_queries_get(client: APIClient, url: str) -> tuple[int, list[dict]]:
    with CaptureQueriesContext(connection) as ctx:
        resp = client.get(url)
    assert resp.status_code == 200, f"GET {url} falló con {resp.status_code}: {resp.data}"
    data = resp.data
    items = data["results"] if isinstance(data, dict) and "results" in data else data
    return len(ctx), items


class TestBarridoN1ViewSets:
    def test_ventas_pedidos_notas_y_facturas_o1_queries(self, empresa_a, empresa_b, user_a, moneda_usd):
        from apps.ventas.models import DetallePedido, FacturaFiscal, NotaVenta, Pedido

        client = APIClient()
        client.force_authenticate(user=user_a)

        cli_a = ClienteFactory(id_empresa=empresa_a)
        cli_b = ClienteFactory(id_empresa=empresa_b)
        prod_a = ProductoFactory(id_empresa=empresa_a)

        # Registro ajeno en empresa_b para verificar aislamiento en el mismo barrido
        Pedido.objects.create(
            id_empresa=empresa_b,
            id_cliente=cli_b,
            numero_pedido="PED-B-1",
            fecha_pedido=date.today(),
        )

        def _crear_lote_ventas(inicio: int, cantidad: int):
            for idx in range(inicio, inicio + cantidad):
                ped = Pedido.objects.create(
                    id_empresa=empresa_a,
                    id_cliente=cli_a,
                    id_vendedor=user_a,
                    numero_pedido=f"PED-A-{idx}",
                    fecha_pedido=date.today(),
                    documento_json={"id_usuario": str(user_a.id)},
                )
                DetallePedido.objects.create(
                    id_pedido=ped,
                    id_producto=prod_a,
                    cantidad=Decimal("2.0000"),
                    precio_unitario=Decimal("10.0000"),
                    subtotal=Decimal("20.0000"),
                )
                NotaVenta.objects.create(
                    id_empresa=empresa_a,
                    id_cliente=cli_a,
                    numero_nota=f"NV-A-{idx}",
                    fecha_nota=date.today(),
                )
                FacturaFiscal.objects.create(
                    id_empresa=empresa_a,
                    id_cliente=cli_a,
                    id_moneda=moneda_usd,
                    numero_control=f"CTRL-{idx}",
                    numero_factura=f"FAC-{idx}",
                    fecha_emision=date.today(),
                    monto_total=Decimal("116.0000"),
                )

        _crear_lote_ventas(1, 2)
        # Precalienta caché de empresa visible para medir estrictamente el queryset de vista
        _ = _contar_queries_get(client, "/api/ventas/pedidos/")

        q_ped_2, items_ped_2 = _contar_queries_get(client, "/api/ventas/pedidos/")
        q_nv_2, items_nv_2 = _contar_queries_get(client, "/api/ventas/notas-venta/")
        q_fac_2, items_fac_2 = _contar_queries_get(client, "/api/ventas/facturas-fiscales/")
        assert len(items_ped_2) == 2
        assert all(row["numero_pedido"].startswith("PED-A-") for row in items_ped_2)

        _crear_lote_ventas(3, 6)  # Total N = 8
        q_ped_8, items_ped_8 = _contar_queries_get(client, "/api/ventas/pedidos/")
        q_nv_8, items_nv_8 = _contar_queries_get(client, "/api/ventas/notas-venta/")
        q_fac_8, items_fac_8 = _contar_queries_get(client, "/api/ventas/facturas-fiscales/")

        assert len(items_ped_8) == 8
        assert len(items_nv_8) == 8
        assert len(items_fac_8) == 8
        assert q_ped_8 == q_ped_2
        assert q_nv_8 == q_nv_2
        assert q_fac_8 == q_fac_2

    def test_finanzas_viewsets_o1_queries(self, empresa_a, empresa_b, user_a, moneda_usd, metodo_efectivo):
        from apps.finanzas.models import (
            Caja,
            CajaFisica,
            CuentaBancariaEmpresa,
            Datafono,
            MetodoPago,
            Pago,
            SesionCajaFisica,
            SesionDatafono,
            TasaCambio,
            TransaccionDatafono,
            TransaccionFinanciera,
        )

        client = APIClient()
        client.force_authenticate(user=user_a)

        suc_a = Sucursal.objects.create(id_empresa=empresa_a, nombre="Suc A", codigo_sucursal="SA01")
        contacto_a = Contacto.objects.create(id_empresa=empresa_a, nombre="Contacto A")
        mon_ves = MonedaFactory(codigo_iso="VES", nombre="Bolívar", simbolo="Bs")
        cta_a = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_a,
            nombre_banco="Banco A",
            numero_cuenta="0102000000001",
            id_moneda=moneda_usd,
        )
        # Registro ajeno en empresa_b para asegurar filtro tenant
        Pago.objects.create(
            id_empresa=empresa_b,
            tipo_operacion="INGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("99.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
            referencia="AJENO-B",
        )

        def _crear_lote_finanzas(inicio: int, cantidad: int):
            for idx in range(inicio, inicio + cantidad):
                cf = CajaFisica.objects.create(
                    empresa=empresa_a,
                    sucursal=suc_a,
                    nombre=f"CF {idx}",
                    identificador_dispositivo=f"dev-{idx}",
                )
                Caja.objects.create(
                    empresa=empresa_a,
                    sucursal=suc_a,
                    nombre=f"CV {idx}",
                    moneda=moneda_usd,
                    caja_fisica=cf,
                )
                if idx == inicio:
                    SesionCajaFisica.objects.create(
                        empresa=empresa_a,
                        caja_fisica=cf,
                        usuario=user_a,
                        estado="ABIERTA",
                    )
                df = Datafono.objects.create(
                    id_empresa=empresa_a,
                    id_sucursal=suc_a,
                    id_caja_fisica=cf,
                    nombre=f"POS {idx}",
                    serial=f"SER-{idx}",
                    id_cuenta_bancaria_asociada=cta_a,
                )
                sd = SesionDatafono.objects.create(datafono=df, usuario_apertura=user_a)
                TransaccionDatafono.objects.create(id_datafono=df, sesion_datafono=sd, monto=Decimal("5.00"))
                tx = TransaccionFinanciera.objects.create(
                    id_empresa=empresa_a,
                    fecha_hora_transaccion=timezone.now(),
                    tipo_transaccion="INGRESO",
                    monto_transaccion=Decimal("10.00"),
                    id_moneda_transaccion=moneda_usd,
                    id_moneda_base=moneda_usd,
                    monto_base_empresa=Decimal("10.00"),
                    id_metodo_pago=metodo_efectivo,
                    id_usuario_registro=user_a,
                )
                Pago.objects.create(
                    id_empresa=empresa_a,
                    id_contacto=contacto_a,
                    tipo_operacion="INGRESO",
                    tipo_documento="ANTICIPO",
                    fecha_pago=timezone.now(),
                    monto=Decimal("10.0000"),
                    id_moneda=moneda_usd,
                    id_metodo_pago=metodo_efectivo,
                    id_caja_fisica=cf,
                    id_cuenta_bancaria=cta_a,
                    id_datafono=df,
                    id_transaccion_financiera=tx,
                    id_usuario_registro=user_a,
                    referencia=f"PAG-{idx}",
                )
                TasaCambio.objects.create(
                    id_empresa=empresa_a,
                    id_moneda_origen=moneda_usd,
                    id_moneda_destino=mon_ves,
                    tipo_tasa="FIJA",
                    valor_tasa=Decimal("40.00000000"),
                    fecha_tasa=timezone.localdate() - timedelta(days=idx),
                    id_usuario_registro=user_a,
                )
                mp = MetodoPago.objects.create(
                    empresa=empresa_a,
                    nombre_metodo=f"Metodo {idx}",
                    tipo_metodo="ELECTRONICO",
                )
                mp.monedas.add(moneda_usd)

        _crear_lote_finanzas(1, 2)
        # Precalienta caché de empresa visible
        _ = _contar_queries_get(client, "/api/finanzas/pagos/")

        q_pagos_2, items_pagos_2 = _contar_queries_get(client, "/api/finanzas/pagos/")
        q_tx_2, _ = _contar_queries_get(client, "/api/finanzas/transacciones-financieras/")
        q_tasas_2, _ = _contar_queries_get(client, "/api/finanzas/tasas-cambio/")
        q_mp_2, _ = _contar_queries_get(client, "/api/finanzas/metodos-pago/")
        q_cf_2, _ = _contar_queries_get(client, "/api/finanzas/cajas-fisicas/")
        q_sd_2, _ = _contar_queries_get(client, "/api/finanzas/sesiones-datafono/")

        assert all(p["referencia"] != "AJENO-B" for p in items_pagos_2)

        _crear_lote_finanzas(3, 6)  # Total N = 8

        q_pagos_8, items_pagos_8 = _contar_queries_get(client, "/api/finanzas/pagos/")
        q_tx_8, items_tx_8 = _contar_queries_get(client, "/api/finanzas/transacciones-financieras/")
        q_tasas_8, items_tasas_8 = _contar_queries_get(client, "/api/finanzas/tasas-cambio/")
        q_mp_8, items_mp_8 = _contar_queries_get(client, "/api/finanzas/metodos-pago/")
        q_cf_8, items_cf_8 = _contar_queries_get(client, "/api/finanzas/cajas-fisicas/")
        q_sd_8, items_sd_8 = _contar_queries_get(client, "/api/finanzas/sesiones-datafono/")

        assert len(items_pagos_8) == 8
        assert len(items_tx_8) == 8
        assert len(items_tasas_8) == 8
        assert len(items_mp_8) >= 8
        assert len(items_cf_8) == 8
        assert len(items_sd_8) == 8

        assert q_pagos_8 == q_pagos_2
        assert q_tx_8 == q_tx_2
        assert q_tasas_8 == q_tasas_2
        assert q_mp_8 == q_mp_2
        assert q_cf_8 == q_cf_2
        assert q_sd_8 == q_sd_2

    def test_buscar_reutilizar_metodos_pago_o1_queries(self, empresa_a, user_a, monkeypatch):
        import importlib.util
        import sys
        from types import ModuleType

        if importlib.util.find_spec("rapidfuzz") is None:
            # Dependencia opcional en dev local: stub mínimo determinista para ejercer
            # get_aplicado() + caché obtener_metodos_pago_empresa_nombres sin omitir el test.
            rf_mod = ModuleType("rapidfuzz")
            dist_mod = ModuleType("rapidfuzz.distance")
            fuzz_mod = ModuleType("rapidfuzz.fuzz")

            class _Levenshtein:
                @staticmethod
                def distance(a: str, b: str) -> int:
                    return abs(len(a) - len(b)) if a == b else max(len(a), len(b))

            dist_mod.Levenshtein = _Levenshtein  # type: ignore[attr-defined]
            fuzz_mod.ratio = lambda a, b: 100.0 if a == b else 0.0  # type: ignore[attr-defined]
            rf_mod.distance = dist_mod  # type: ignore[attr-defined]
            rf_mod.fuzz = fuzz_mod  # type: ignore[attr-defined]
            monkeypatch.setitem(sys.modules, "rapidfuzz", rf_mod)
            monkeypatch.setitem(sys.modules, "rapidfuzz.distance", dist_mod)
            monkeypatch.setitem(sys.modules, "rapidfuzz.fuzz", fuzz_mod)

        from apps.finanzas.models import MetodoPago

        client = APIClient()
        client.force_authenticate(user=user_a)
        MetodoPago.objects.create(empresa=empresa_a, nombre_metodo="Transferencia Propia", tipo_metodo="ELECTRONICO")

        for i in range(2):
            MetodoPago.objects.create(
                es_publico=True,
                nombre_metodo=f"Publico {i}",
                tipo_metodo="ELECTRONICO",
            )
        url = f"/api/finanzas/metodos-pago/buscar_reutilizar/?id_empresa_actual={empresa_a.pk}"
        _ = _contar_queries_get(client, url)  # precalienta empresa visible + metodos propios
        q_2, items_2 = _contar_queries_get(client, url)

        for i in range(2, 8):
            MetodoPago.objects.create(
                es_publico=True,
                nombre_metodo=f"Publico {i}",
                tipo_metodo="ELECTRONICO",
            )
        q_8, items_8 = _contar_queries_get(client, url)
        assert len(items_8) == len(items_2) + 6
        assert q_8 == q_2

    def test_cxc_inventario_compras_y_contabilidad_o1_queries(self, empresa_a, empresa_b, user_a):
        from apps.compras.models import RequisicionCompra, SolicitudCotizacion
        from apps.contabilidad.models import AsientoContable, DetalleAsiento, DiarioContable, PlanCuentas
        from apps.cuentas_por_cobrar.models import AbonoCxC, CuentaPorCobrar
        from apps.inventario.models import OperacionInventario, OperacionInventarioLinea
        from apps.proveedores.models import Proveedor

        client = APIClient()
        client.force_authenticate(user=user_a)

        cli_a = ClienteFactory(id_empresa=empresa_a)
        cli_b = ClienteFactory(id_empresa=empresa_b)
        alm_a = AlmacenFactory(id_empresa=empresa_a)
        prod_a = ProductoFactory(id_empresa=empresa_a)
        prov_a = Proveedor.objects.create(id_empresa=empresa_a, razon_social="Prov A", rif="J-55555551-1")
        contacto_a = Contacto.objects.create(id_empresa=empresa_a, nombre="Contacto Contab")
        cuenta_a = PlanCuentas.objects.create(
            id_empresa=empresa_a,
            codigo_cuenta="1101",
            nombre_cuenta="Caja",
            tipo_cuenta="ACTIVO",
            naturaleza="DEUDORA",
            nivel=1,
        )
        diario_a = DiarioContable.objects.create(id_empresa=empresa_a, codigo="DI-1", nombre="Diario 1")

        # Registro ajeno en empresa_b para comprobar aislamiento
        CuentaPorCobrar.objects.create(
            empresa=empresa_b,
            cliente=cli_b,
            monto=Decimal("50.00"),
            fecha_emision=date.today(),
            fecha_vencimiento=date.today(),
        )

        def _crear_lote_modulos(inicio: int, cantidad: int):
            for idx in range(inicio, inicio + cantidad):
                cxc = CuentaPorCobrar.objects.create(
                    empresa=empresa_a,
                    cliente=cli_a,
                    monto=Decimal("100.00"),
                    fecha_emision=date.today(),
                    fecha_vencimiento=date.today(),
                )
                AbonoCxC.objects.create(cuenta_por_cobrar=cxc, monto=Decimal("25.00"), usuario=user_a)

                op = OperacionInventario.objects.create(
                    id_empresa=empresa_a,
                    numero=f"REC-{idx}",
                    tipo_operacion="RECEPCION",
                    origen_tipo="PURCHASE",
                    id_almacen=alm_a,
                    fecha=timezone.now(),
                )
                OperacionInventarioLinea.objects.create(
                    id_operacion=op,
                    id_producto=prod_a,
                    cantidad=Decimal("5.0000"),
                    costo_unitario=Decimal("10.0000"),
                )

                req = RequisicionCompra.objects.create(
                    id_empresa=empresa_a,
                    numero_requisicion=f"REQ-{idx}",
                    fecha_requisicion=date.today(),
                    id_solicitante=user_a,
                    fecha_necesidad=date.today(),
                    justificacion="Stock",
                )
                sc = SolicitudCotizacion.objects.create(
                    id_empresa=empresa_a,
                    numero_solicitud=f"RFQ-{idx}",
                    fecha_solicitud=date.today(),
                    fecha_vencimiento=date.today() + timedelta(days=5),
                )
                sc.requisiciones.add(req)
                sc.proveedores_invitados.add(prov_a)

                asiento = AsientoContable.objects.create(
                    id_empresa=empresa_a,
                    id_diario=diario_a,
                    fecha_asiento=date.today(),
                    numero_asiento=f"AS-{idx}",
                    descripcion="Asiento prueba",
                    estado_asiento="BORRADOR",
                )
                DetalleAsiento.objects.create(
                    id_asiento=asiento,
                    id_cuenta_contable=cuenta_a,
                    id_contacto=contacto_a,
                    debe=Decimal("10.00"),
                    haber=Decimal("0.00"),
                )

        _crear_lote_modulos(1, 2)
        _ = _contar_queries_get(client, "/api/cxc/cuentas-por-cobrar/")

        q_cxc_2, items_cxc_2 = _contar_queries_get(client, "/api/cxc/cuentas-por-cobrar/")
        q_rec_2, _ = _contar_queries_get(client, "/api/inventario/recepciones/")
        q_rfq_2, _ = _contar_queries_get(client, "/api/compras/solicitudes-cotizacion/")
        q_asi_2, _ = _contar_queries_get(client, "/api/contabilidad/asientos-contables/")
        assert len(items_cxc_2) == 2

        _crear_lote_modulos(3, 6)  # Total N = 8

        q_cxc_8, items_cxc_8 = _contar_queries_get(client, "/api/cxc/cuentas-por-cobrar/")
        q_rec_8, items_rec_8 = _contar_queries_get(client, "/api/inventario/recepciones/")
        q_rfq_8, items_rfq_8 = _contar_queries_get(client, "/api/compras/solicitudes-cotizacion/")
        q_asi_8, items_asi_8 = _contar_queries_get(client, "/api/contabilidad/asientos-contables/")

        assert len(items_cxc_8) == 8
        assert len(items_rec_8) == 8
        assert len(items_rfq_8) == 8
        assert len(items_asi_8) == 8

        assert q_cxc_8 == q_cxc_2
        assert q_rec_8 == q_rec_2
        assert q_rfq_8 == q_rfq_2
        assert q_asi_8 == q_asi_2


class TestEdgeCasesYGapsCobertura:
    def test_cache_utils_validaciones_pk_bump_batch_y_fallback_carrera(self, empresa_a, monkeypatch):
        from types import SimpleNamespace

        with pytest.raises(ValueError, match="Namespace"):
            normalize_namespace("invalid ns!")
        with pytest.raises(ValueError, match="tenant_key"):
            normalize_tenant_key("")
        with pytest.raises(ValueError, match="pk"):
            normalize_tenant_key(SimpleNamespace(pk=None))
        assert normalize_tenant_key(empresa_a) == str(empresa_a.pk)
        with pytest.raises(ValueError, match="NUL"):
            build_cache_key("ns.test", "global", "bad\x00key")
        with pytest.raises(TypeError, match="dicts"):
            get_cached_or_set("bad.dict", empresa_a.pk, "d", lambda: {"obj": empresa_a})

        bump_namespaces([("ns.batch1", empresa_a.pk), ("ns.batch2", "global")])
        assert get_namespace_version("ns.batch1", empresa_a.pk) >= 1

        # Carrera simulada en get_namespace_version / bump_namespace_version cuando add() compite
        monkeypatch.setattr(cache, "get", lambda *a, **kw: None)
        monkeypatch.setattr(cache, "add", lambda *a, **kw: False)

        def _incr_fail(*a, **kw):
            raise ValueError("not initialized")

        monkeypatch.setattr(cache, "incr", _incr_fail)
        assert get_namespace_version("ns.race", "global") == 1
        assert bump_namespace_version("ns.race", "global") == 1

    def test_empresas_visible_reverse_m2m_y_guarda_rls(self, empresa_a, empresa_b, user_a, settings):
        from apps.core import rls

        assert get_all_subsidiarias(None) == set()

        # Reverse M2M (empresa.usuarios) también invalida la caché del usuario afectado
        assert empresa_b.pk not in set(get_empresas_visible(user_a).values_list("id_empresa", flat=True))
        empresa_b.usuarios.add(user_a)
        assert empresa_b.pk in set(get_empresas_visible(user_a).values_list("id_empresa", flat=True))
        empresa_b.usuarios.clear()
        assert empresa_b.pk not in set(get_empresas_visible(user_a).values_list("id_empresa", flat=True))

        # Con RLS activo sin rls_bypass, evita L2 distribuida y consulta BD directo
        settings.RLS_ENABLED = True
        with rls.rls_tenant_context([empresa_a.pk]):
            assert empresa_a.pk in set(get_empresas_visible(user_a).values_list("id_empresa", flat=True))

    def test_configuracion_motor_edge_y_rls_fallback(self, empresa_a, empresa_b, settings):
        from apps.configuracion_motor.models import ParametroSistema
        from apps.configuracion_motor.services import obtener_parametro
        from apps.core import rls

        assert obtener_parametro("", empresa=empresa_a, default="fallback") == "fallback"
        ParametroSistema.objects.create(
            id_empresa=None,
            nombre_parametro="Global Only",
            codigo_parametro="param.global",
            valor_parametro=" gval ",
            tipo_dato="TEXTO",
        )
        assert obtener_parametro("param.global", empresa=None) == "gval"

        p = ParametroSistema.objects.create(
            id_empresa=empresa_a,
            nombre_parametro="Movible",
            codigo_parametro="param.movil",
            valor_parametro="en_a",
            tipo_dato="TEXTO",
        )
        assert obtener_parametro("param.movil", empresa=str(empresa_a.pk)) == "en_a"

        # Mover parámetro entre empresas invalida origen (A) y destino (B)
        p.id_empresa = empresa_b
        p.valor_parametro = "en_b"
        p.save()
        assert obtener_parametro("param.movil", empresa=empresa_a) is None
        assert obtener_parametro("param.movil", empresa=empresa_b) == "en_b"

        settings.RLS_ENABLED = True
        with rls.rls_bypass():
            assert obtener_parametro("param.movil", empresa=empresa_b) == "en_b"
        # Contexto restringido a empresa_a → empresa_b usa bypass seguro de L2
        with rls.rls_tenant_context([empresa_a.pk]):
            assert obtener_parametro("param.movil", empresa=empresa_b) in ("en_b", None)

    def test_finanzas_signals_cambio_scope_rls_mcp_y_serializers_sin_contexto(
        self, empresa_a, empresa_b, user_a, moneda_usd, settings, monkeypatch
    ):
        from types import SimpleNamespace

        from apps.core import rls
        from apps.finanzas.cache import (
            normalizar_empresa_uuid,
            obtener_metodos_pago_empresa_nombres,
            obtener_metodos_pago_mcp,
            obtener_moneda_por_iso,
            obtener_monedas_activas_ids,
            obtener_tasa_cambio_cacheada,
            obtener_tasa_oficial_bcv_payload,
        )
        from apps.finanzas.mcp import finanzas_get_metodos_pago
        from apps.finanzas.models import MetodoPago, Moneda, TasaCambio
        from apps.finanzas.serializers import MetodoPagoReutilizableSerializer
        from apps.ventas.models import Pedido
        from apps.ventas.serializers import PedidoSerializer

        assert obtener_moneda_por_iso("   ") is None
        assert obtener_moneda_por_iso("ZZZZZ") is None
        assert normalizar_empresa_uuid(SimpleNamespace(pk=None)) is None
        assert obtener_tasa_oficial_bcv_payload(moneda_usd.pk, moneda_usd.pk, date(2000, 1, 1)) is None
        mon_b = Moneda.objects.create(
            empresa=empresa_b,
            codigo_iso="MONB",
            nombre="Moneda B",
            simbolo="B",
            tipo_moneda="otro",
        )
        assert obtener_tasa_cambio_cacheada(moneda_usd, mon_b, empresa_id=empresa_a.pk, fecha=date.today()) is None

        # Cambio de empresa en TasaCambio, Moneda y MetodoPago invalida origen y destino
        tasa = TasaCambio.objects.create(
            id_empresa=empresa_a,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=mon_b,
            tipo_tasa="FIJA",
            valor_tasa=Decimal("10.00000000"),
            fecha_tasa=date.today(),
        )
        assert obtener_tasa_cambio_cacheada(moneda_usd, mon_b, empresa_id=empresa_a.pk, fecha=date.today()) is not None
        tasa.id_empresa = empresa_b
        tasa.save()
        assert obtener_tasa_cambio_cacheada(moneda_usd, mon_b, empresa_id=empresa_a.pk, fecha=date.today()) is None
        assert obtener_tasa_cambio_cacheada(moneda_usd, mon_b, empresa_id=empresa_b.pk, fecha=date.today()) is not None

        mon_b.empresa = empresa_a
        mon_b.save()
        assert obtener_moneda_por_iso("MONB", empresa_id=empresa_a.pk) is not None

        mp = MetodoPago.objects.create(empresa=empresa_a, nombre_metodo="MP Movil", tipo_metodo="ELECTRONICO")
        mp.monedas.add(moneda_usd)
        mp.monedas.clear()
        mp.es_publico = True
        mp.save()

        # MetodoPagoReutilizableSerializer directo sin `metodos_empresa_por_tipo`
        import importlib.util
        import sys
        from types import ModuleType

        if importlib.util.find_spec("rapidfuzz") is None:
            rf_mod = ModuleType("rapidfuzz")
            dist_mod = ModuleType("rapidfuzz.distance")
            fuzz_mod = ModuleType("rapidfuzz.fuzz")

            class _Levenshtein:
                @staticmethod
                def distance(a: str, b: str) -> int:
                    return 0 if a == b else 9

            dist_mod.Levenshtein = _Levenshtein  # type: ignore[attr-defined]
            fuzz_mod.ratio = lambda a, b: 100.0 if a == b else 0.0  # type: ignore[attr-defined]
            rf_mod.distance = dist_mod  # type: ignore[attr-defined]
            rf_mod.fuzz = fuzz_mod  # type: ignore[attr-defined]
            monkeypatch.setitem(sys.modules, "rapidfuzz", rf_mod)
            monkeypatch.setitem(sys.modules, "rapidfuzz.distance", dist_mod)
            monkeypatch.setitem(sys.modules, "rapidfuzz.fuzz", fuzz_mod)

        data_rep = MetodoPagoReutilizableSerializer(mp, context={"id_empresa_actual": str(empresa_a.pk)}).data
        assert data_rep["aplicado"] is True

        # MCP guard con tenant_id inválido
        from contextlib import contextmanager

        @contextmanager
        def _bad_ctx(*a, **kw):
            yield {"tenant_id": None, "actor_id": "x"}

        monkeypatch.setattr("apps.finanzas.mcp._ctx", _bad_ctx)
        with pytest.raises(ValueError, match="tenant_id"):
            finanzas_get_metodos_pago("tok")

        # PedidoListSerializer sin contexto inicial y con id_usuario inválido en documento_json
        cli_a = ClienteFactory(id_empresa=empresa_a)
        ped = Pedido.objects.create(
            id_empresa=empresa_a,
            id_cliente=cli_a,
            numero_pedido="PED-INV-UID",
            fecha_pedido=date.today(),
            documento_json={"id_usuario": "no-es-uuid"},
        )
        serialized = PedidoSerializer([ped], many=True).data
        assert len(serialized) == 1
        assert "id_usuario" not in serialized[0]

        # Finanzas cache con RLS restringido (y bajo rls_bypass)
        settings.RLS_ENABLED = True
        with rls.rls_bypass():
            obtener_moneda_por_iso("MONB", empresa_id=empresa_a.pk)
        with rls.rls_tenant_context([empresa_b.pk]):
            obtener_moneda_por_iso("MONB", empresa_id=empresa_a.pk)
            obtener_tasa_cambio_cacheada(moneda_usd, mon_b, empresa_id=empresa_a.pk, fecha=date.today())
            obtener_monedas_activas_ids(empresa_a.pk)
            obtener_metodos_pago_mcp(empresa_a.pk)
            obtener_metodos_pago_empresa_nombres(empresa_a.pk)

    def test_moneda_iso_global_omite_cache_bajo_rls_sin_bypass(self, empresa_a, empresa_b, settings, rls_test_role):
        from apps.core import rls
        from apps.finanzas.cache import obtener_moneda_por_iso
        from apps.finanzas.models import Moneda

        mon_pub_a = Moneda.objects.create(
            empresa=empresa_a,
            codigo_iso="PUBA",
            nombre="Pública A",
            simbolo="P",
            tipo_moneda="otro",
            es_publica=True,
        )
        settings.RLS_ENABLED = True

        # Precalentar caché L2 global bajo rls_bypass
        with rls.rls_bypass():
            assert obtener_moneda_por_iso("PUBA", empresa_id=empresa_a.pk) is not None
            with CaptureQueriesContext(connection) as q_hit:
                assert obtener_moneda_por_iso("PUBA", empresa_id=empresa_a.pk) is not None
            assert not any("finanzas_moneda" in q["sql"] for q in q_hit)

        if rls_test_role is not None:
            with connection.cursor() as cur:
                cur.execute(f'SET ROLE "{rls_test_role}"')
        try:
            # Bajo rls_tenant_context sin bypass, omite caché L2 global y consulta directo a BD
            with rls.rls_tenant_context([empresa_b.pk]):
                with CaptureQueriesContext(connection) as q_rls:
                    res_b = obtener_moneda_por_iso("PUBA", empresa_id=empresa_b.pk)
                assert any("finanzas_moneda" in q["sql"] for q in q_rls)
                # Bajo RLS real, una moneda pública con empresa=A no es visible para B (no lee caché global)
                assert res_b is None
        finally:
            if rls_test_role is not None:
                with connection.cursor() as cur:
                    cur.execute("RESET ROLE")

        # Tenant B no envenenó ni corrompió la caché L2 global para bypass/empresa_a
        with rls.rls_bypass():
            res_a = obtener_moneda_por_iso("PUBA", empresa_id=empresa_a.pk)
            assert res_a is not None and res_a.pk == mon_pub_a.pk
