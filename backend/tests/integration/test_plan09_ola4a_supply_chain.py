"""Tests de integración Plan 09 Ola 4A: Supply Chain, Landed Costs, Conteo Dual, Barcode y Tránsito."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from apps.core import rls

pytestmark = [pytest.mark.django_db]


def _setup_catalogo_y_almacenes(empresa, moneda_usd):
    from apps.almacenes.models import Almacen, UbicacionAlmacen
    from apps.compras.models import DetalleOrdenCompra, OrdenCompra
    from apps.compras.services import aprobar_orden_compra, registrar_recepcion
    from apps.core.models import Usuarios
    from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida
    from apps.proveedores.models import Proveedor

    user = Usuarios.objects.create_user(
        username=f"sc_user_{uuid.uuid4().hex[:8]}",
        email=f"sc_{uuid.uuid4().hex[:6]}@omni.test",
        password="TestPass123!@#",
        is_staff=True,
    )
    user.empresas.add(empresa)

    um = UnidadMedida.objects.create(id_empresa=empresa, nombre="Unidad", abreviatura="UND", tipo="CANTIDAD")
    cat = CategoriaProducto.objects.create(id_empresa=empresa, nombre_categoria="Lubricantes")

    prod_a = Producto.objects.create(
        id_empresa=empresa,
        nombre_producto="Aceite 20W50 Galón",
        sku=f"SKU-A-{uuid.uuid4().hex[:5]}",
        codigo_barras="7591234500011",
        id_categoria=cat,
        id_unidad_medida_base=um,
        id_moneda_precio=moneda_usd,
        costo_promedio=Decimal("10.0000"),
        costo_reposicion_usd=Decimal("12.0000"),
        margen_minimo_pct=Decimal("15.00"),
        margen_alerta_pct=Decimal("25.00"),
        precio_venta_sugerido=Decimal("20.0000"),
        peso_unitario_kg=Decimal("4.0000"),
        volumen_unitario_m3=Decimal("0.010000"),
    )
    prod_b = Producto.objects.create(
        id_empresa=empresa,
        nombre_producto="Filtro Aceite Heavy",
        sku=f"SKU-B-{uuid.uuid4().hex[:5]}",
        codigo_barras="7591234500028",
        id_categoria=cat,
        id_unidad_medida_base=um,
        id_moneda_precio=moneda_usd,
        costo_promedio=Decimal("5.0000"),
        costo_reposicion_usd=Decimal("6.0000"),
        margen_minimo_pct=Decimal("15.00"),
        margen_alerta_pct=Decimal("25.00"),
        precio_venta_sugerido=Decimal("10.0000"),
        peso_unitario_kg=Decimal("1.0000"),
        volumen_unitario_m3=Decimal("0.005000"),
    )

    alm_orig = Almacen.objects.create(
        id_empresa=empresa,
        nombre_almacen="Almacén Central",
        codigo_almacen=f"ALM1-{uuid.uuid4().hex[:4]}",
        usa_ubicaciones=True,
    )
    alm_dest = Almacen.objects.create(
        id_empresa=empresa,
        nombre_almacen="Sucursal Valencia",
        codigo_almacen=f"ALM2-{uuid.uuid4().hex[:4]}",
        usa_ubicaciones=False,
    )
    ubic_pick = UbicacionAlmacen.objects.create(
        id_empresa=empresa,
        id_almacen=alm_orig,
        codigo_ubicacion="PICK-A1",
        nombre_ubicacion="Rack A1",
        tipo_ubicacion="PICKING",
    )
    ubic_trans = UbicacionAlmacen.objects.create(
        id_empresa=empresa,
        id_almacen=alm_orig,
        codigo_ubicacion="TRANS-01",
        nombre_ubicacion="Muelle en Tránsito",
        tipo_ubicacion="TRANSITO",
    )

    prov = Proveedor.objects.create(
        id_empresa=empresa,
        razon_social="Importadora Global SRL",
        nombre_comercial="Importadora Global",
        rif=f"J-{uuid.uuid4().hex[:8].upper()}",
    )

    oc = OrdenCompra.objects.create(
        id_empresa=empresa,
        id_proveedor=prov,
        id_almacen_destino=alm_orig,
        numero_orden=f"OC-{uuid.uuid4().hex[:6]}",
        fecha_orden=date(2026, 11, 20),
        estado="BORRADOR",
    )
    DetalleOrdenCompra.objects.create(
        id_orden_compra=oc,
        id_producto=prod_a,
        cantidad=Decimal("10.0000"),
        precio_unitario=Decimal("10.0000"),
        subtotal=Decimal("100.0000"),
    )
    DetalleOrdenCompra.objects.create(
        id_orden_compra=oc,
        id_producto=prod_b,
        cantidad=Decimal("20.0000"),
        precio_unitario=Decimal("5.0000"),
        subtotal=Decimal("100.0000"),
    )
    aprobar_orden_compra(oc, user)
    rec_res = registrar_recepcion(
        oc,
        alm_orig,
        user,
        items=[
            {"producto": prod_a, "cantidad": Decimal("10"), "costo_unitario": Decimal("10.00")},
            {"producto": prod_b, "cantidad": Decimal("20"), "costo_unitario": Decimal("5.00")},
        ],
    )

    return {
        "user": user,
        "prod_a": prod_a,
        "prod_b": prod_b,
        "alm_orig": alm_orig,
        "alm_dest": alm_dest,
        "ubic_pick": ubic_pick,
        "ubic_trans": ubic_trans,
        "prov": prov,
        "oc": oc,
        "recepcion": rec_res["recepcion"],
    }


# ---------------------------------------------------------------------------
# 1. PostgreSQL RLS en las 7 tablas nuevas + validaciones de modelos
# ---------------------------------------------------------------------------


class TestRLSYModelosSupplyChain:
    def test_rls_siete_tablas_y_validaciones_modelo(self, rls_test_role, empresa_a, empresa_b, moneda_usd):
        from apps.almacenes.models import DetalleTransferenciaTransito, TransferenciaTransito
        from apps.compras.models import AsignacionCostoDestino, CostoDestino, LineaCostoDestino
        from apps.inventario.models import ConteoInventario, LineaConteoInventario

        tablas = (
            "compras_costo_destino",
            "compras_linea_costo_destino",
            "compras_asignacion_costo_destino",
            "inventario_conteo",
            "inventario_linea_conteo",
            "almacenes_transferencia_transito",
            "almacenes_detalle_transferencia_transito",
        )
        with connection.cursor() as cur:
            for tabla in tablas:
                cur.execute(
                    "SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename=%s",
                    [tabla],
                )
                assert cur.fetchone()[0] >= 1, f"Falta política RLS en {tabla}"

        ctx_a = _setup_catalogo_y_almacenes(empresa_a, moneda_usd)
        ctx_b = _setup_catalogo_y_almacenes(empresa_b, moneda_usd)

        cd_a = CostoDestino.objects.create(
            id_empresa=empresa_a,
            id_recepcion=ctx_a["recepcion"],
            numero_documento="CD-RLS-01",
            fecha=date(2026, 11, 22),
            metodo_prorrateo="VALOR",
            nro_expediente_impor="EXP-01",
            nro_planilla_impor="SEN-01",
        )
        CostoDestino.objects.create(
            id_empresa=empresa_b,
            id_recepcion=ctx_b["recepcion"],
            numero_documento="CD-RLS-B",
            fecha=date(2026, 11, 22),
        )
        ln_a = LineaCostoDestino.objects.create(
            id_empresa=empresa_a,
            id_costo_destino=cd_a,
            concepto="FLETE",
            descripcion="Flete marítimo",
            monto=Decimal("50.0000"),
        )
        assert "CD-RLS-01" in str(cd_a)
        assert "FLETE" in str(ln_a)

        cnt_a = ConteoInventario.objects.create(
            id_empresa=empresa_a,
            numero="CNT-RLS-01",
            id_almacen=ctx_a["alm_orig"],
            fecha_conteo=date(2026, 11, 22),
            id_responsable=ctx_a["user"],
        )
        ConteoInventario.objects.create(
            id_empresa=empresa_b,
            numero="CNT-RLS-B",
            id_almacen=ctx_b["alm_orig"],
            fecha_conteo=date(2026, 11, 22),
            id_responsable=ctx_b["user"],
        )
        lcnt_a = LineaConteoInventario.objects.create(
            id_empresa=empresa_a,
            id_conteo=cnt_a,
            id_producto=ctx_a["prod_a"],
            cantidad_sistema=Decimal("10"),
        )
        assert "CNT-RLS-01" in str(cnt_a)
        assert "CNT-RLS-01" in str(lcnt_a)

        trf_a = TransferenciaTransito.objects.create(
            id_empresa=empresa_a,
            numero="TRF-RLS-01",
            id_almacen_origen=ctx_a["alm_orig"],
            id_almacen_destino=ctx_a["alm_dest"],
            fecha_despacho=timezone.now(),
            id_usuario_despacho=ctx_a["user"],
        )
        TransferenciaTransito.objects.create(
            id_empresa=empresa_b,
            numero="TRF-RLS-B",
            id_almacen_origen=ctx_b["alm_orig"],
            id_almacen_destino=ctx_b["alm_dest"],
            fecha_despacho=timezone.now(),
            id_usuario_despacho=ctx_b["user"],
        )
        dtrf_a = DetalleTransferenciaTransito.objects.create(
            id_empresa=empresa_a,
            id_transferencia=trf_a,
            id_producto=ctx_a["prod_a"],
            cantidad_despachada=Decimal("2.0000"),
        )
        assert "TRF-RLS-01" in str(trf_a)
        assert "TRF-RLS-01" in str(dtrf_a)

        # Validaciones cross-tenant clean()
        with pytest.raises(ValidationError):
            CostoDestino(
                id_empresa=empresa_a, id_recepcion=ctx_b["recepcion"], numero_documento="X", fecha=date(2026, 11, 22)
            ).clean()
        with pytest.raises(ValidationError):
            LineaCostoDestino(
                id_empresa=empresa_b, id_costo_destino=cd_a, concepto="FLETE", descripcion="X", monto=Decimal("5")
            ).clean()
        with pytest.raises(ValidationError):
            ConteoInventario(
                id_empresa=empresa_a,
                numero="X",
                id_almacen=ctx_b["alm_orig"],
                fecha_conteo=date(2026, 11, 22),
                id_responsable=ctx_a["user"],
            ).clean()
        with pytest.raises(ValidationError):
            LineaConteoInventario(id_empresa=empresa_a, id_conteo=cnt_a, id_producto=ctx_b["prod_a"]).clean()
        with pytest.raises(ValidationError):
            TransferenciaTransito(
                id_empresa=empresa_a,
                numero="X",
                id_almacen_origen=ctx_a["alm_orig"],
                id_almacen_destino=ctx_a["alm_orig"],
                fecha_despacho=timezone.now(),
                id_usuario_despacho=ctx_a["user"],
            ).clean()
        with pytest.raises(ValidationError):
            TransferenciaTransito(
                id_empresa=empresa_a,
                numero="X",
                id_almacen_origen=ctx_b["alm_orig"],
                id_almacen_destino=ctx_a["alm_dest"],
                fecha_despacho=timezone.now(),
                id_usuario_despacho=ctx_a["user"],
            ).clean()

        det_rec_a = ctx_a["recepcion"].detalles.first()
        asig = AsignacionCostoDestino.objects.create(
            id_empresa=empresa_a,
            id_costo_destino=cd_a,
            id_detalle_recepcion=det_rec_a,
            id_producto=det_rec_a.id_producto,
            base_prorrateo=Decimal("100"),
            porcentaje_prorrateo=Decimal("100"),
            costo_adicional_total=Decimal("10"),
            costo_adicional_unitario=Decimal("1"),
            costo_unitario_anterior=Decimal("10"),
            costo_unitario_nuevo=Decimal("11"),
        )
        assert "+1" in str(asig)

        # Aislamiento RLS real en PostgreSQL bajo rls_test_role
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(f"SET LOCAL ROLE {rls_test_role}")
                cur.execute("SELECT set_config(%s, 'off', true)", [rls.GUC_BYPASS])
                cur.execute("SELECT set_config(%s, %s, true)", [rls.GUC_EMPRESAS, str(empresa_a.pk)])
                assert list(CostoDestino.objects.values_list("numero_documento", flat=True)) == ["CD-RLS-01"]
                assert list(ConteoInventario.objects.values_list("numero", flat=True)) == ["CNT-RLS-01"]
                assert list(TransferenciaTransito.objects.values_list("numero", flat=True)) == ["TRF-RLS-01"]
                assert LineaCostoDestino.objects.count() == 1
                assert AsignacionCostoDestino.objects.count() == 1
                assert LineaConteoInventario.objects.count() == 1
                assert DetalleTransferenciaTransito.objects.count() == 1


# ---------------------------------------------------------------------------
# 2. Costos en Destino (Landed Costs) + 3-Way Matching
# ---------------------------------------------------------------------------


class TestLandedCostsYThreeWayMatching:
    def test_prorrateo_valor_peso_volumen_cantidad_y_contabilidad(self, empresa_a, moneda_usd):
        from apps.compras.models import CostoDestino, LineaCostoDestino
        from apps.compras.services_supply_chain import (
            SupplyChainCompraError,
            anular_costo_destino,
            aplicar_costo_destino,
        )
        from apps.contabilidad.models import DiarioContable, MapeoContable, PlanCuentas
        from apps.inventario.models import ValoracionInventario

        ctx = _setup_catalogo_y_almacenes(empresa_a, moneda_usd)

        # Configurar contabilidad activa + mapeo COSTO_DESTINO
        empresa_a.contabilidad_activa = True
        empresa_a.save(update_fields=["contabilidad_activa"])
        cta_inv = PlanCuentas.objects.create(
            id_empresa=empresa_a,
            codigo_cuenta="1.1.04",
            nombre_cuenta="Inventario",
            tipo_cuenta="ACTIVO",
            naturaleza="DEUDORA",
            nivel=1,
        )
        cta_puente = PlanCuentas.objects.create(
            id_empresa=empresa_a,
            codigo_cuenta="2.1.05",
            nombre_cuenta="Gastos Importación",
            tipo_cuenta="PASIVO",
            naturaleza="ACREEDORA",
            nivel=1,
        )
        diario_comp = DiarioContable.objects.create(
            id_empresa=empresa_a, codigo="COM-SC", nombre="Compras SC", tipo="COMPRAS"
        )
        MapeoContable.objects.create(
            id_empresa=empresa_a,
            tipo_asiento="COSTO_DESTINO",
            id_diario=diario_comp,
            cuenta_debe=cta_inv,
            cuenta_haber=cta_puente,
        )

        # 1) Prorrateo por PESO: prod_a (10 * 4kg = 40kg = 2/3), prod_b (20 * 1kg = 20kg = 1/3)
        cd_peso = CostoDestino.objects.create(
            id_empresa=empresa_a,
            id_recepcion=ctx["recepcion"],
            numero_documento="CD-PESO-01",
            fecha=date(2026, 11, 22),
            metodo_prorrateo="PESO",
            nro_expediente_impor="EXP-2026-88",
            nro_planilla_impor="DUA-991",
        )
        LineaCostoDestino.objects.create(
            id_empresa=empresa_a,
            id_costo_destino=cd_peso,
            concepto="FLETE",
            descripcion="Flete Marítimo",
            monto=Decimal("60.0000"),
        )
        LineaCostoDestino.objects.create(
            id_empresa=empresa_a,
            id_costo_destino=cd_peso,
            concepto="ARANCEL",
            descripcion="Arancel Nacionalización",
            monto=Decimal("30.0000"),
        )

        res = aplicar_costo_destino(cd_peso, ctx["user"])
        assert res["monto_total"] == Decimal("90.0000")
        assert res["asiento_id"] is not None
        # Total asignado cuadra exactamente al centésimo (60.0000 + 30.0000 = 90.0000)
        suma_asig = sum((a.costo_adicional_total for a in res["asignaciones"]), Decimal("0"))
        assert suma_asig == Decimal("90.0000")

        # Verificar revaluación de capa ValoracionInventario y Producto.costo_promedio
        ctx["prod_a"].refresh_from_db()
        ctx["prod_b"].refresh_from_db()
        # prod_a recibió $60 sobre 10u -> +$6/u => $16.0000
        assert ctx["prod_a"].costo_promedio == Decimal("16.0000")
        # prod_b recibió $30 sobre 20u -> +$1.50/u => $6.5000
        assert ctx["prod_b"].costo_promedio == Decimal("6.5000")
        capa_a = ValoracionInventario.objects.get(id_empresa=empresa_a, id_producto=ctx["prod_a"], sentido="ENTRADA")
        assert capa_a.costo_unitario == Decimal("16.0000")

        # No se puede volver a aplicar ni anular
        with pytest.raises(SupplyChainCompraError):
            aplicar_costo_destino(cd_peso, ctx["user"])
        with pytest.raises(SupplyChainCompraError):
            anular_costo_destino(cd_peso)

        # 2) Prorrateo por VOLUMEN, CANTIDAD y VALOR + Anulación en BORRADOR
        cd_vol = CostoDestino.objects.create(
            id_empresa=empresa_a,
            id_recepcion=ctx["recepcion"],
            numero_documento="CD-VOL-01",
            fecha=date(2026, 11, 22),
            metodo_prorrateo="VOLUMEN",
        )
        LineaCostoDestino.objects.create(
            id_empresa=empresa_a,
            id_costo_destino=cd_vol,
            concepto="SEGURO",
            descripcion="Seguro de carga",
            monto=Decimal("20.0000"),
        )
        res_vol = aplicar_costo_destino(cd_vol, ctx["user"])
        assert sum((a.costo_adicional_total for a in res_vol["asignaciones"]), Decimal("0")) == Decimal("20.0000")

        cd_anul = CostoDestino.objects.create(
            id_empresa=empresa_a,
            id_recepcion=ctx["recepcion"],
            numero_documento="CD-ANUL-01",
            fecha=date(2026, 11, 22),
            metodo_prorrateo="CANTIDAD",
        )
        anular_costo_destino(cd_anul)
        cd_anul.refresh_from_db()
        assert cd_anul.estado == "ANULADO"

        # 3) Error cuando PESO suma 0
        ctx["prod_a"].peso_unitario_kg = Decimal("0")
        ctx["prod_b"].peso_unitario_kg = Decimal("0")
        ctx["prod_a"].save(update_fields=["peso_unitario_kg"])
        ctx["prod_b"].save(update_fields=["peso_unitario_kg"])
        cd_err = CostoDestino.objects.create(
            id_empresa=empresa_a,
            id_recepcion=ctx["recepcion"],
            numero_documento="CD-ERR-01",
            fecha=date(2026, 11, 22),
            metodo_prorrateo="PESO",
        )
        LineaCostoDestino.objects.create(
            id_empresa=empresa_a,
            id_costo_destino=cd_err,
            concepto="OTRO",
            descripcion="Gasto sin peso",
            monto=Decimal("10.0000"),
        )
        with pytest.raises(SupplyChainCompraError):
            aplicar_costo_destino(cd_err, ctx["user"])

    def test_api_landed_cost_y_three_way_matching(self, empresa_a, empresa_b, moneda_usd):
        from rest_framework.test import APIClient

        from apps.compras.models import DetalleFacturaCompra, FacturaCompra
        from apps.compras.services_supply_chain import validar_three_way_matching

        ctx = _setup_catalogo_y_almacenes(empresa_a, moneda_usd)
        ctx_b = _setup_catalogo_y_almacenes(empresa_b, moneda_usd)

        client = APIClient()
        client.force_authenticate(user=ctx["user"])
        client_b = APIClient()
        client_b.force_authenticate(user=ctx_b["user"])

        # API Costos en Destino: crear, añadir línea, aplicar con idempotencia
        resp_cd = client.post(
            "/api/compras/costos-destino/",
            {
                "id_recepcion": str(ctx["recepcion"].pk),
                "numero_documento": "CD-API-001",
                "fecha": "2026-11-22",
                "metodo_prorrateo": "VALOR",
                "nro_expediente_impor": "EXP-API-1",
            },
            format="json",
        )
        assert resp_cd.status_code == 201, resp_cd.data
        cd_id = resp_cd.data["id_costo_destino"]

        resp_ln = client.post(
            "/api/compras/lineas-costo-destino/",
            {
                "id_costo_destino": cd_id,
                "concepto": "NACIONALIZACION",
                "descripcion": "Agente aduanal",
                "monto": "40.0000",
            },
            format="json",
        )
        assert resp_ln.status_code == 201

        idem_hdr = {"HTTP_IDEMPOTENCY_KEY": str(uuid.uuid4())}
        resp_ap = client.post(f"/api/compras/costos-destino/{cd_id}/aplicar/", {}, format="json", **idem_hdr)
        assert resp_ap.status_code == 200
        assert resp_ap.data["monto_total"] == "40.0000"
        # Reintento idempotente retorna 200 cacheado
        resp_ap2 = client.post(f"/api/compras/costos-destino/{cd_id}/aplicar/", {}, format="json", **idem_hdr)
        assert resp_ap2.status_code == 200
        # Empresa B aislada -> 404
        assert client_b.get(f"/api/compras/costos-destino/{cd_id}/").status_code == 404
        # NUL bytes -> 400
        assert client.get("/api/compras/costos-destino/?estado=APLI\x00CADO").status_code == 400

        # 3-Way Matching: 1) CONFORME, 2) DISCREPANCIA_PRECIO, 3) DISCREPANCIA_CANTIDAD, 4) SIN_ORDEN
        fac_ok = FacturaCompra.objects.create(
            id_empresa=empresa_a,
            id_orden_compra=ctx["oc"],
            id_proveedor=ctx["prov"],
            id_recepcion=ctx["recepcion"],
            numero_factura="FAC-3WM-OK",
            fecha_emision=date(2026, 11, 22),
            monto_total=Decimal("200.0000"),
        )
        DetalleFacturaCompra.objects.create(
            id_factura_compra=fac_ok,
            id_producto=ctx["prod_a"],
            cantidad=Decimal("10"),
            precio_unitario=Decimal("10.00"),
            subtotal=Decimal("100.00"),
            total_linea=Decimal("100.00"),
        )
        DetalleFacturaCompra.objects.create(
            id_factura_compra=fac_ok,
            id_producto=ctx["prod_b"],
            cantidad=Decimal("20"),
            precio_unitario=Decimal("5.00"),
            subtotal=Decimal("100.00"),
            total_linea=Decimal("100.00"),
        )
        r_3wm = client.post(f"/api/compras/facturas-compra/{fac_ok.pk}/validar-three-way-matching/", {}, format="json")
        assert r_3wm.status_code == 200
        assert r_3wm.data["estado"] == "CONFORME"
        assert r_3wm.data["aprobable_automaticamente"] is True

        # Discrepancia de precio (+10% > 1%)
        det_a = fac_ok.detalles.get(id_producto=ctx["prod_a"])
        det_a.precio_unitario = Decimal("11.00")
        det_a.subtotal = Decimal("110.00")
        det_a.save()
        r_prec = client.get(f"/api/compras/facturas-compra/{fac_ok.pk}/validar-three-way-matching/")
        assert r_prec.status_code == 200
        assert r_prec.data["estado"] == "DISCREPANCIA_PRECIO"
        assert r_prec.data["aprobable_automaticamente"] is False
        # Con tolerancia ampliada a 15% pasa a CONFORME
        r_tol = client.post(
            f"/api/compras/facturas-compra/{fac_ok.pk}/validar-three-way-matching/",
            {"tolerancia_precio_pct": "15.00"},
            format="json",
        )
        assert r_tol.data["estado"] == "CONFORME"

        # Discrepancia de cantidad
        det_a.cantidad = Decimal("12")
        det_a.save()
        res_cant = validar_three_way_matching(fac_ok)
        assert res_cant["estado"] == "DISCREPANCIA_CANTIDAD"

        # Factura sin OC
        fac_sin_oc = FacturaCompra.objects.create(
            id_empresa=empresa_a,
            id_proveedor=ctx["prov"],
            numero_factura="FAC-SIN-OC",
            fecha_emision=date(2026, 11, 22),
            monto_total=Decimal("50.0000"),
        )
        assert validar_three_way_matching(fac_sin_oc)["estado"] == "SIN_ORDEN_COMPRA"


# ---------------------------------------------------------------------------
# 3. Semáforo Margen, Conteo Cíclico Dual, Barcode Pick-Pack-Ship y Dual Summary
# ---------------------------------------------------------------------------


class TestInventarioInteligenteSemaforoConteoYBarcode:
    def test_semaforo_margen_y_busqueda_barcode(self, empresa_a, moneda_usd):
        from rest_framework.test import APIClient

        from apps.inventario.services_supply_chain import evaluar_semaforo_margen_producto
        from apps.ventas.services_precios import calcular_precio_dinamico

        ctx = _setup_catalogo_y_almacenes(empresa_a, moneda_usd)
        prod = ctx["prod_a"]  # costo_reposicion_usd=12.00, min=15%, alerta=25%, sugerido=20.00 (margen=40%)

        assert evaluar_semaforo_margen_producto(prod)["semaforo"] == "VERDE"
        assert evaluar_semaforo_margen_producto(prod, Decimal("15.00"))["semaforo"] == "AMARILLO"  # 20%
        assert evaluar_semaforo_margen_producto(prod, Decimal("13.00"))["semaforo"] == "ROJO"  # 7.69%

        prod.costo_reposicion_usd = None
        prod.costo_promedio = Decimal("0")
        prod.save(update_fields=["costo_reposicion_usd", "costo_promedio"])
        assert evaluar_semaforo_margen_producto(prod)["semaforo"] == "SIN_COSTO"

        # Integración en motor dinámico de precios de ventas
        prod.costo_reposicion_usd = Decimal("18.5000")
        prod.save(update_fields=["costo_reposicion_usd"])
        dyn = calcular_precio_dinamico(producto=prod, empresa=empresa_a, cantidad=Decimal("1"), moneda_pago="USD")
        assert dyn["semaforo_margen"]["semaforo"] == "ROJO"

        client = APIClient()
        client.force_authenticate(user=ctx["user"])
        r_sem = client.get(f"/api/inventario/productos/{prod.pk}/semaforo-margen/?precio_venta_usd=28.00")
        assert r_sem.status_code == 200
        assert r_sem.data["semaforo"] == "VERDE"
        assert (
            client.get(f"/api/inventario/productos/{prod.pk}/semaforo-margen/?precio_venta_usd=1\x00").status_code
            == 400
        )

        r_bc = client.get("/api/inventario/productos/buscar-barcode/?codigo=7591234500011")
        assert r_bc.status_code == 200
        assert r_bc.data["id_producto"] == str(prod.pk)
        assert client.get("/api/inventario/productos/buscar-barcode/?codigo=NO_EXISTE").status_code == 404
        assert client.get("/api/inventario/productos/buscar-barcode/?codigo=A\x00B").status_code == 400

    def test_conteo_ciclico_dual_y_barcode_pick_pack_ship(self, empresa_a, empresa_b, moneda_usd):
        from rest_framework.test import APIClient

        from apps.almacenes.models import StockUbicacion
        from apps.inventario.models import MovimientoInventario, PasoOperacion, StockActual
        from apps.inventario.operaciones import crear_operacion

        ctx = _setup_catalogo_y_almacenes(empresa_a, moneda_usd)
        ctx_b = _setup_catalogo_y_almacenes(empresa_b, moneda_usd)

        # Sembrar StockUbicacion para validar actualización en conteo con ubicación
        StockUbicacion.objects.create(
            id_empresa=empresa_a,
            id_almacen=ctx["alm_orig"],
            id_ubicacion=ctx["ubic_pick"],
            id_producto=ctx["prod_a"],
            cantidad_disponible=Decimal("10.0000"),
        )

        client = APIClient()
        client.force_authenticate(user=ctx["user"])
        client_b = APIClient()
        client_b.force_authenticate(user=ctx_b["user"])

        # Crear conteo cíclico GERENCIAL
        r_cre = client.post(
            "/api/inventario/conteos-inventario/",
            {
                "id_almacen": str(ctx["alm_orig"].pk),
                "tipo_conteo": "CICLICO",
                "ambito": "GERENCIAL",
                "items": [{"producto": str(ctx["prod_a"].pk), "ubicacion": str(ctx["ubic_pick"].pk)}],
            },
            format="json",
        )
        assert r_cre.status_code == 201, r_cre.data
        conteo_id = r_cre.data["id_conteo"]
        assert client_b.get(f"/api/inventario/conteos-inventario/{conteo_id}/").status_code == 404

        # Escaneo incremental por barcode -> 7 + 1 = 8 (sistema 10 => diferencia -2)
        r_scan1 = client.post(
            f"/api/inventario/conteos-inventario/{conteo_id}/escanear/",
            {
                "codigo": "7591234500011",
                "cantidad": "7",
                "modo": "INCREMENTAL",
                "ubicacion": str(ctx["ubic_pick"].pk),
            },
            format="json",
        )
        assert r_scan1.status_code == 200
        assert Decimal(r_scan1.data["cantidad_contada"]) == Decimal("7")

        r_scan2 = client.post(
            f"/api/inventario/conteos-inventario/{conteo_id}/escanear/",
            {
                "codigo": "7591234500011",
                "cantidad": "1",
                "modo": "INCREMENTAL",
                "ubicacion": str(ctx["ubic_pick"].pk),
            },
            format="json",
        )
        assert Decimal(r_scan2.data["diferencia"]) == Decimal("-2")

        # Enviar a aprobación y aprobar-aplicar
        assert (
            client.post(
                f"/api/inventario/conteos-inventario/{conteo_id}/enviar-aprobacion/", {}, format="json"
            ).status_code
            == 200
        )
        r_apr = client.post(
            f"/api/inventario/conteos-inventario/{conteo_id}/aprobar-aplicar/",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert r_apr.status_code == 200
        assert r_apr.data["ajustes_generados"] == 1

        # Verificar ajuste en ámbito GERENCIAL, StockActual (8) y StockUbicacion (8)
        mov = MovimientoInventario.objects.get(pk=r_apr.data["movimientos_ids"][0])
        assert mov.ambito == "GERENCIAL"
        assert mov.tipo_movimiento == "AJUSTE"
        sa = StockActual.objects.get(id_empresa=empresa_a, id_almacen=ctx["alm_orig"], id_producto=ctx["prod_a"])
        assert sa.cantidad_disponible == Decimal("8.0000")
        su = StockUbicacion.objects.get(
            id_empresa=empresa_a,
            id_almacen=ctx["alm_orig"],
            id_ubicacion=ctx["ubic_pick"],
            id_producto=ctx["prod_a"],
        )
        assert su.cantidad_disponible == Decimal("8.0000")

        # Resumen inventario dual refleja ambos ámbitos
        r_res = client.get("/api/inventario/reportes/resumen-dual/")
        assert r_res.status_code == 200
        assert r_res.data["ambitos"]["FISCAL"]["movimientos"] >= 2
        assert r_res.data["ambitos"]["GERENCIAL"]["movimientos"] >= 1

        # Pick-Pack-Ship barcode scan en OperacionInventario
        PasoOperacion.objects.create(
            id_empresa=empresa_a,
            id_almacen=ctx["alm_orig"],
            tipo_operacion="ENTREGA",
            secuencia=1,
            nombre_paso="Picking Barcode",
        )
        op = crear_operacion(
            empresa=empresa_a,
            almacen=ctx["alm_orig"],
            tipo_operacion="ENTREGA",
            origen_tipo="RETURN",
            lineas=[{"producto": ctx["prod_a"], "cantidad": Decimal("3")}],
            usuario=ctx["user"],
            motivo="Devolución proveedor prueba barcode",
        )
        r_op1 = client.post(
            f"/api/inventario/entregas/{op.pk}/escanear/",
            {"codigo": "7591234500011", "cantidad": "2"},
            format="json",
        )
        assert r_op1.status_code == 200
        assert r_op1.data["escaneo_completo"] is False

        # Sobre-escaneo -> 400
        r_op_over = client.post(
            f"/api/inventario/entregas/{op.pk}/escanear/",
            {"codigo": "7591234500011", "cantidad": "2"},
            format="json",
        )
        assert r_op_over.status_code == 400

        r_op2 = client.post(
            f"/api/inventario/entregas/{op.pk}/escanear/",
            {"codigo": "7591234500011", "cantidad": "1"},
            format="json",
        )
        assert r_op2.status_code == 200
        assert r_op2.data["escaneo_completo"] is True


# ---------------------------------------------------------------------------
# 4. Transferencias Inter-Almacén en Tránsito (2 pasos)
# ---------------------------------------------------------------------------


class TestTransferenciaTransitoInterAlmacen:
    def test_flujo_transito_recepcion_parcial_y_cancelacion(self, empresa_a, empresa_b, moneda_usd):
        from rest_framework.test import APIClient

        from apps.inventario.models import MovimientoInventario, StockActual

        ctx = _setup_catalogo_y_almacenes(empresa_a, moneda_usd)
        ctx_b = _setup_catalogo_y_almacenes(empresa_b, moneda_usd)

        client = APIClient()
        client.force_authenticate(user=ctx["user"])
        client_b = APIClient()
        client_b.force_authenticate(user=ctx_b["user"])

        # 1) Despacho de 5 unidades de prod_a en tránsito hacia Sucursal Valencia
        r_desp = client.post(
            "/api/almacenes/transferencias-transito/despachar/",
            {
                "id_almacen_origen": str(ctx["alm_orig"].pk),
                "id_almacen_destino": str(ctx["alm_dest"].pk),
                "id_ubicacion_transito": str(ctx["ubic_trans"].pk),
                "ambito": "FISCAL",
                "items": [{"producto": str(ctx["prod_a"].pk), "cantidad": "5"}],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert r_desp.status_code == 201, r_desp.data
        trf_id = r_desp.data["id_transferencia_transito"]
        det_id = r_desp.data["detalles"][0]["id_detalle"]
        assert r_desp.data["estado"] == "EN_TRANSITO"
        assert client_b.get(f"/api/almacenes/transferencias-transito/{trf_id}/").status_code == 404

        # Stock origen bajó de 10 a 5, destino aún no tiene stock (está en tránsito)
        sa_orig = StockActual.objects.get(id_empresa=empresa_a, id_almacen=ctx["alm_orig"], id_producto=ctx["prod_a"])
        assert sa_orig.cantidad_disponible == Decimal("5.0000")
        assert not StockActual.objects.filter(
            id_empresa=empresa_a, id_almacen=ctx["alm_dest"], id_producto=ctx["prod_a"]
        ).exists()

        # 2) Recepción parcial en destino (4 recibidas, 1 merma)
        r_rec = client.post(
            f"/api/almacenes/transferencias-transito/{trf_id}/recibir/",
            {"cantidades_recibidas": {det_id: "4.0000"}, "observaciones": "1 unidad dañada en ruta"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert r_rec.status_code == 200
        assert len(r_rec.data["mermas"]) == 1
        assert Decimal(r_rec.data["mermas"][0]["diferencia_merma"]) == Decimal("1.0000")
        sa_dest = StockActual.objects.get(id_empresa=empresa_a, id_almacen=ctx["alm_dest"], id_producto=ctx["prod_a"])
        assert sa_dest.cantidad_disponible == Decimal("4.0000")

        # 3) Despacho + cancelación revierte stock a origen
        r_desp2 = client.post(
            "/api/almacenes/transferencias-transito/despachar/",
            {
                "id_almacen_origen": str(ctx["alm_orig"].pk),
                "id_almacen_destino": str(ctx["alm_dest"].pk),
                "ambito": "GERENCIAL",
                "items": [{"producto": str(ctx["prod_a"].pk), "cantidad": "3"}],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert r_desp2.status_code == 201
        trf2_id = r_desp2.data["id_transferencia_transito"]
        sa_orig.refresh_from_db()
        assert sa_orig.cantidad_disponible == Decimal("2.0000")

        r_can = client.post(f"/api/almacenes/transferencias-transito/{trf2_id}/cancelar/", {}, format="json")
        assert r_can.status_code == 200
        assert r_can.data["estado"] == "CANCELADA"
        sa_orig.refresh_from_db()
        assert sa_orig.cantidad_disponible == Decimal("5.0000")

        # Movimiento de cancelación respeta ámbito GERENCIAL
        assert (
            MovimientoInventario.objects.filter(
                id_empresa=empresa_a, id_documento_origen=trf2_id, ambito="GERENCIAL"
            ).count()
            == 2
        )

        # NUL bytes en ?estado= -> 400
        assert client.get("/api/almacenes/transferencias-transito/?estado=EN\x00_TRANSITO").status_code == 400


# ---------------------------------------------------------------------------
# 5. Cobertura exhaustiva de validaciones, errores y casos borde Ola 4A
# ---------------------------------------------------------------------------


class TestEdgeCasesYValidacionesSupplyChain:
    def test_edge_cases_landed_costs_y_3wm(self, empresa_a, empresa_b, moneda_usd):
        from rest_framework.test import APIClient

        from apps.compras.models import CostoDestino, FacturaCompra, LineaCostoDestino, OrdenCompra
        from apps.compras.services_supply_chain import (
            SupplyChainCompraError,
            aplicar_costo_destino,
            validar_three_way_matching,
        )
        from apps.contabilidad.models import MapeoContable, PlanCuentas

        ctx = _setup_catalogo_y_almacenes(empresa_a, moneda_usd)
        ctx_b = _setup_catalogo_y_almacenes(empresa_b, moneda_usd)
        client = APIClient()
        client.force_authenticate(user=ctx["user"])

        # Fallback contable a RECEPCION_MERCANCIA cuando no hay mapeo COSTO_DESTINO
        empresa_a.contabilidad_activa = True
        empresa_a.save(update_fields=["contabilidad_activa"])
        c1 = PlanCuentas.objects.create(
            id_empresa=empresa_a,
            codigo_cuenta="1.1.91",
            nombre_cuenta="Inv Alt",
            tipo_cuenta="ACTIVO",
            naturaleza="DEUDORA",
            nivel=1,
        )
        c2 = PlanCuentas.objects.create(
            id_empresa=empresa_a,
            codigo_cuenta="2.1.91",
            nombre_cuenta="Puente Alt",
            tipo_cuenta="PASIVO",
            naturaleza="ACREEDORA",
            nivel=1,
        )
        MapeoContable.objects.create(
            id_empresa=empresa_a, tipo_asiento="RECEPCION_MERCANCIA", cuenta_debe=c1, cuenta_haber=c2
        )

        # CD sin líneas -> API anular & aplicar (400 en aplicar vacío)
        r_cd = client.post(
            "/api/compras/costos-destino/",
            {
                "id_recepcion": str(ctx["recepcion"].pk),
                "numero_documento": "CD-EDGE-01",
                "fecha": "2026-11-22",
                "metodo_prorrateo": "CANTIDAD",
            },
            format="json",
        )
        assert r_cd.status_code == 201
        cd_id = r_cd.data["id_costo_destino"]
        assert client.post(f"/api/compras/costos-destino/{cd_id}/aplicar/", {}, format="json").status_code == 400
        assert client.post(f"/api/compras/costos-destino/{cd_id}/anular/", {}, format="json").status_code == 200
        assert client.post(f"/api/compras/costos-destino/{cd_id}/anular/", {}, format="json").status_code == 400

        # Intento de añadir línea a CD ANULADO -> 400
        assert (
            client.post(
                "/api/compras/lineas-costo-destino/",
                {"id_costo_destino": cd_id, "concepto": "FLETE", "descripcion": "X", "monto": "10.00"},
                format="json",
            ).status_code
            == 400
        )

        # CD aplicado con fallback RECEPCION_MERCANCIA + subtotal cero fallback + volumen=0 error
        cd_cant = CostoDestino.objects.create(
            id_empresa=empresa_a,
            id_recepcion=ctx["recepcion"],
            numero_documento="CD-EDGE-CANT",
            fecha=date(2026, 11, 22),
            metodo_prorrateo="CANTIDAD",
        )
        LineaCostoDestino.objects.create(
            id_empresa=empresa_a,
            id_costo_destino=cd_cant,
            concepto="ALMACENAJE_ADUANA",
            descripcion="Bodegaje",
            monto=Decimal("10.0000"),
        )
        res_fb = aplicar_costo_destino(cd_cant, ctx["user"])
        assert res_fb["asiento_id"] is not None
        assert client.get(f"/api/compras/lineas-costo-destino/?costo_destino={cd_cant.pk}").status_code == 200
        assert client.get("/api/compras/costos-destino/?estado=APLICADO").status_code == 200

        # Recepcion cross-empresa en serializer -> 400
        assert (
            client.post(
                "/api/compras/costos-destino/",
                {
                    "id_recepcion": str(ctx_b["recepcion"].pk),
                    "numero_documento": "CD-CROSS",
                    "fecha": "2026-11-22",
                },
                format="json",
            ).status_code
            == 400
        )

        # AsientoError propagation (contabilidad_activa=True sin ningún mapeo)
        MapeoContable.objects.filter(id_empresa=empresa_a).delete()
        cd_no_map = CostoDestino.objects.create(
            id_empresa=empresa_a,
            id_recepcion=ctx["recepcion"],
            numero_documento="CD-NOMAP",
            fecha=date(2026, 11, 22),
            metodo_prorrateo="VALOR",
        )
        LineaCostoDestino.objects.create(
            id_empresa=empresa_a, id_costo_destino=cd_no_map, concepto="OTRO", descripcion="X", monto=Decimal("5.00")
        )
        with pytest.raises(SupplyChainCompraError):
            aplicar_costo_destino(cd_no_map, ctx["user"])

        # Volumen=0 -> SupplyChainCompraError
        empresa_a.contabilidad_activa = False
        empresa_a.save(update_fields=["contabilidad_activa"])
        ctx["prod_a"].volumen_unitario_m3 = Decimal("0")
        ctx["prod_b"].volumen_unitario_m3 = Decimal("0")
        ctx["prod_a"].save(update_fields=["volumen_unitario_m3"])
        ctx["prod_b"].save(update_fields=["volumen_unitario_m3"])
        cd_v0 = CostoDestino.objects.create(
            id_empresa=empresa_a,
            id_recepcion=ctx["recepcion"],
            numero_documento="CD-V0",
            fecha=date(2026, 11, 22),
            metodo_prorrateo="VOLUMEN",
        )
        LineaCostoDestino.objects.create(
            id_empresa=empresa_a, id_costo_destino=cd_v0, concepto="FLETE", descripcion="Vol 0", monto=Decimal("5.00")
        )
        with pytest.raises(SupplyChainCompraError):
            aplicar_costo_destino(cd_v0, ctx["user"])

        # 3-Way Matching: OC sin recepción -> SIN_RECEPCION; Factura sin detalles (conforme y discrepancia)
        oc_sin_rec = OrdenCompra.objects.create(
            id_empresa=empresa_a,
            id_proveedor=ctx["prov"],
            numero_orden="OC-SINREC-1",
            fecha_orden=date(2026, 11, 22),
            estado="APROBADA",
        )
        fac_sr = FacturaCompra.objects.create(
            id_empresa=empresa_a,
            id_orden_compra=oc_sin_rec,
            id_proveedor=ctx["prov"],
            numero_factura="FAC-SINREC",
            fecha_emision=date(2026, 11, 22),
            monto_total=Decimal("100.00"),
        )
        assert validar_three_way_matching(fac_sr)["estado"] == "SIN_RECEPCION"

        fac_hdr_ok = FacturaCompra.objects.create(
            id_empresa=empresa_a,
            id_orden_compra=ctx["oc"],
            id_proveedor=ctx["prov"],
            numero_factura="FAC-HDR-OK",
            fecha_emision=date(2026, 11, 22),
            monto_total=Decimal("200.00"),
        )
        assert validar_three_way_matching(fac_hdr_ok)["estado"] == "CONFORME"
        fac_hdr_ok.monto_total = Decimal("260.00")
        fac_hdr_ok.save(update_fields=["monto_total"])
        assert validar_three_way_matching(fac_hdr_ok)["estado"] == "DISCREPANCIA_PRECIO"
        assert (
            client.get(
                f"/api/compras/facturas-compra/{fac_hdr_ok.pk}/validar-three-way-matching/?tolerancia_precio_pct=1\x00"
            ).status_code
            == 400
        )

    def test_edge_cases_inventario_conteo_barcode_y_transito(self, empresa_a, empresa_b, moneda_usd):
        from rest_framework.test import APIClient

        from apps.almacenes.services_transito import TransferenciaTransitoError, despachar_transferencia_transito
        from apps.inventario.models import PasoOperacion, VarianteProducto
        from apps.inventario.operaciones import crear_operacion
        from apps.inventario.services_supply_chain import InventarioSupplyChainError, crear_conteo_inventario

        ctx = _setup_catalogo_y_almacenes(empresa_a, moneda_usd)
        ctx_b = _setup_catalogo_y_almacenes(empresa_b, moneda_usd)
        var_a = VarianteProducto.objects.create(
            id_producto=ctx["prod_a"], codigo_variante="VAR-1L", sku="SKU-A-VAR1", atributos_json={"envase": "1L"}
        )

        client = APIClient()
        client.force_authenticate(user=ctx["user"])

        # Semáforo inválido y resumen dual por almacén
        assert (
            client.get(
                f"/api/inventario/productos/{ctx['prod_a'].pk}/semaforo-margen/?precio_venta_usd=no-num"
            ).status_code
            == 400
        )
        assert client.get(f"/api/inventario/reportes/resumen-dual/?almacen={ctx['alm_orig'].pk}").status_code == 200

        # Conteo TOTAL automático + escaneo REEMPLAZAR + ajuste positivo + anular
        r_tot = client.post(
            "/api/inventario/conteos-inventario/",
            {"id_almacen": str(ctx["alm_orig"].pk), "tipo_conteo": "TOTAL", "ambito": "FISCAL"},
            format="json",
        )
        assert r_tot.status_code == 201
        tot_id = r_tot.data["id_conteo"]
        assert client.get("/api/inventario/conteos-inventario/?estado=EN_PROGRESO").status_code == 200
        assert client.get("/api/inventario/conteos-inventario/?estado=EN\x00").status_code == 400

        # Escaneo con modo REEMPLAZAR (sube de 10 a 12 -> ajuste +2)
        r_rep = client.post(
            f"/api/inventario/conteos-inventario/{tot_id}/escanear/",
            {"codigo": str(ctx["prod_a"].pk), "cantidad": "12", "modo": "REEMPLAZAR", "observaciones": "Reconteo"},
            format="json",
        )
        assert r_rep.status_code == 200
        assert Decimal(r_rep.data["diferencia"]) == Decimal("2")

        # Errores de escaneo: código inválido, variante inválida, ubicación inválida
        assert (
            client.post(
                f"/api/inventario/conteos-inventario/{tot_id}/escanear/",
                {"codigo": "NO-EXISTE-99", "cantidad": "1"},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client.post(
                f"/api/inventario/conteos-inventario/{tot_id}/escanear/",
                {"codigo": "7591234500011", "cantidad": "1", "variante": str(uuid.uuid4())},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client.post(
                f"/api/inventario/conteos-inventario/{tot_id}/escanear/",
                {"codigo": "7591234500011", "cantidad": "1", "ubicacion": str(uuid.uuid4())},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client.post(
                f"/api/inventario/conteos-inventario/{tot_id}/escanear/",
                {"codigo": "7591234500011", "cantidad": "0", "modo": "INCREMENTAL"},
                format="json",
            ).status_code
            == 400
        )

        # Aprobar aplica +2 positivo y omite línea sin cantidad_contada (prod_b)
        r_apr2 = client.post(
            f"/api/inventario/conteos-inventario/{tot_id}/aprobar-aplicar/",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert r_apr2.status_code == 200
        assert r_apr2.data["ajustes_generados"] == 1
        # Ya aplicado -> enviar/aprobar/anular/escanear fallan con 400
        assert (
            client.post(f"/api/inventario/conteos-inventario/{tot_id}/anular/", {}, format="json").status_code == 400
        )
        assert (
            client.post(
                f"/api/inventario/conteos-inventario/{tot_id}/enviar-aprobacion/", {}, format="json"
            ).status_code
            == 400
        )

        # Conteo vacío -> anular OK, enviar-aprobacion falla 400
        r_emp = client.post(
            "/api/inventario/conteos-inventario/",
            {"id_almacen": str(ctx["alm_orig"].pk), "tipo_conteo": "CICLICO"},
            format="json",
        )
        emp_id = r_emp.data["id_conteo"]
        assert (
            client.post(
                f"/api/inventario/conteos-inventario/{emp_id}/enviar-aprobacion/", {}, format="json"
            ).status_code
            == 400
        )
        assert (
            client.post(f"/api/inventario/conteos-inventario/{emp_id}/anular/", {}, format="json").status_code == 200
        )

        # Validaciones de servicio creación conteo
        with pytest.raises(InventarioSupplyChainError):
            crear_conteo_inventario(empresa=empresa_a, almacen=ctx_b["alm_orig"], responsable=ctx["user"])
        with pytest.raises(InventarioSupplyChainError):
            crear_conteo_inventario(
                empresa=empresa_a, almacen=ctx["alm_orig"], responsable=ctx["user"], tipo_conteo="XYZ"
            )

        # Errores de creación conteo API (almacén/producto/variante/ubicación inexistentes o cruzados)
        assert (
            client.post(
                "/api/inventario/conteos-inventario/",
                {"id_almacen": str(ctx_b["alm_orig"].pk)},
                format="json",
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/inventario/conteos-inventario/",
                {"id_almacen": str(ctx["alm_orig"].pk), "items": [{"producto": str(ctx_b["prod_a"].pk)}]},
                format="json",
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/inventario/conteos-inventario/",
                {
                    "id_almacen": str(ctx["alm_orig"].pk),
                    "items": [{"producto": str(ctx["prod_a"].pk), "variante": str(uuid.uuid4())}],
                },
                format="json",
            ).status_code
            == 400
        )

        # Pick-Pack-Ship barcode error cuando operación cancelada o código no está en operación
        PasoOperacion.objects.create(
            id_empresa=empresa_a, id_almacen=ctx["alm_orig"], tipo_operacion="RECEPCION", secuencia=1, nombre_paso="P1"
        )
        op_rec = crear_operacion(
            empresa=empresa_a,
            almacen=ctx["alm_orig"],
            tipo_operacion="RECEPCION",
            origen_tipo="PURCHASE",
            lineas=[
                {
                    "producto": ctx["prod_a"],
                    "variante": var_a,
                    "cantidad": Decimal("2"),
                    "costo_unitario": Decimal("10"),
                }
            ],
            usuario=ctx["user"],
        )
        assert (
            client.post(
                f"/api/inventario/recepciones/{op_rec.pk}/escanear/",
                {"codigo": "NO-ESTA", "cantidad": "1"},
                format="json",
            ).status_code
            == 400
        )
        op_rec.estado = "CANCELADA"
        op_rec.save(update_fields=["estado"])
        assert (
            client.post(
                f"/api/inventario/recepciones/{op_rec.pk}/escanear/",
                {"codigo": "7591234500011", "cantidad": "1"},
                format="json",
            ).status_code
            == 400
        )

        # Tránsito inter-almacén errores: almacén igual, stock insuficiente, recibir cantidad inválida, filtros
        assert (
            client.post(
                "/api/almacenes/transferencias-transito/despachar/",
                {
                    "id_almacen_origen": str(ctx["alm_orig"].pk),
                    "id_almacen_destino": str(ctx["alm_orig"].pk),
                    "items": [{"producto": str(ctx["prod_a"].pk), "cantidad": "1"}],
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/almacenes/transferencias-transito/despachar/",
                {
                    "id_almacen_origen": str(ctx["alm_orig"].pk),
                    "id_almacen_destino": str(ctx["alm_dest"].pk),
                    "items": [{"producto": str(ctx["prod_a"].pk), "cantidad": "9999"}],
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/almacenes/transferencias-transito/despachar/",
                {
                    "id_almacen_origen": str(ctx["alm_orig"].pk),
                    "id_almacen_destino": str(ctx_b["alm_dest"].pk),
                    "items": [{"producto": str(ctx["prod_a"].pk), "cantidad": "1"}],
                },
                format="json",
            ).status_code
            == 404
        )
        trf = despachar_transferencia_transito(
            empresa=empresa_a,
            almacen_origen=ctx["alm_orig"],
            almacen_destino=ctx["alm_dest"],
            usuario=ctx["user"],
            items=[{"producto": ctx["prod_a"], "cantidad": Decimal("2")}],
        )
        det_trf = trf.detalles.first()
        assert (
            client.post(
                f"/api/almacenes/transferencias-transito/{trf.pk}/recibir/",
                {"cantidades_recibidas": {str(det_trf.pk): "10.0000"}},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client.post(
                f"/api/almacenes/transferencias-transito/{trf.pk}/recibir/",
                {},
                format="json",
            ).status_code
            == 200
        )
        # Ya recibida -> cancelar/recibir fallan con 400
        assert (
            client.post(f"/api/almacenes/transferencias-transito/{trf.pk}/cancelar/", {}, format="json").status_code
            == 400
        )
        assert client.get("/api/almacenes/transferencias-transito/?estado=RECIBIDA").status_code == 200
        with pytest.raises(TransferenciaTransitoError):
            despachar_transferencia_transito(
                empresa=empresa_a,
                almacen_origen=ctx["alm_orig"],
                almacen_destino=ctx["alm_dest"],
                usuario=ctx["user"],
                items=[],
            )

    def test_ramas_restantes_serializers_servicios_y_endpoints(self, empresa_a, empresa_b, moneda_usd):
        from rest_framework.test import APIClient

        from apps.almacenes.services_transito import (
            TransferenciaTransitoError,
            cancelar_transferencia_transito,
            despachar_transferencia_transito,
            recibir_transferencia_transito,
        )
        from apps.compras.models import CostoDestino, DetalleFacturaCompra, FacturaCompra, RecepcionMercancia
        from apps.compras.services_supply_chain import (
            SupplyChainCompraError,
            _dec as compra_dec,
            _peso_prorrateo_detalle,
            validar_three_way_matching,
        )
        from apps.inventario.models import PasoOperacion, VarianteProducto
        from apps.inventario.operaciones import crear_operacion
        from apps.inventario.services_supply_chain import (
            InventarioSupplyChainError,
            aprobar_aplicar_conteo,
            buscar_producto_por_barcode,
            crear_conteo_inventario,
            enviar_conteo_aprobacion,
            escanear_linea_operacion,
            evaluar_semaforo_margen_producto,
            registrar_escaneo_conteo,
        )

        ctx = _setup_catalogo_y_almacenes(empresa_a, moneda_usd)
        ctx_b = _setup_catalogo_y_almacenes(empresa_b, moneda_usd)
        var_a = VarianteProducto.objects.create(
            id_producto=ctx["prod_a"], codigo_variante="V-EXTRA", sku="SKU-V-EXTRA", atributos_json={"t": "1"}
        )

        client = APIClient()
        client.force_authenticate(user=ctx["user"])

        # Compras helpers & edge validation
        assert compra_dec(None, Decimal("1")) == Decimal("1")
        with pytest.raises(SupplyChainCompraError):
            compra_dec("no-numero")
        det_rec = ctx["recepcion"].detalles.first()
        det_rec_orig_sub = det_rec.subtotal
        det_rec.subtotal = Decimal("0")
        assert _peso_prorrateo_detalle(det_rec, "VALOR") > Decimal("0")
        det_rec.subtotal = det_rec_orig_sub
        with pytest.raises(SupplyChainCompraError):
            _peso_prorrateo_detalle(det_rec, "METODO_RARO")

        # CostoDestino POST vacío -> dispara serializer validate(); LineaCostoDestino con factura cross-tenant -> 400
        assert client.post("/api/compras/costos-destino/", {}, format="json").status_code == 400
        cd_b = CostoDestino.objects.create(
            id_empresa=empresa_a,
            id_recepcion=ctx["recepcion"],
            numero_documento="CD-REM-LN",
            fecha=date(2026, 11, 22),
        )
        fac_b = FacturaCompra.objects.create(
            id_empresa=empresa_b,
            id_proveedor=ctx_b["prov"],
            numero_factura="FAC-CROSS-B",
            fecha_emision=date(2026, 11, 22),
            monto_total=Decimal("10.00"),
        )
        assert (
            client.post(
                "/api/compras/lineas-costo-destino/",
                {
                    "id_costo_destino": str(cd_b.pk),
                    "concepto": "FLETE",
                    "descripcion": "Cross",
                    "monto": "10.00",
                    "id_factura_compra": str(fac_b.pk),
                },
                format="json",
            ).status_code
            == 400
        )

        # 3WM producto extra en factura no presente en OC + recepción monto 0 + tolerancia negativa + GET tolerancias
        rec_cero = RecepcionMercancia.objects.create(
            id_empresa=empresa_a,
            id_orden_compra=ctx["oc"],
            fecha_recepcion=date(2026, 11, 22),
            monto_total=Decimal("0.00"),
        )
        fac_extra = FacturaCompra.objects.create(
            id_empresa=empresa_a,
            id_orden_compra=ctx["oc"],
            id_proveedor=ctx["prov"],
            id_recepcion=rec_cero,
            numero_factura="FAC-EXTRA-PROD",
            fecha_emision=date(2026, 11, 22),
            monto_total=Decimal("50.00"),
        )
        assert validar_three_way_matching(fac_extra)["estado"] == "DISCREPANCIA_CANTIDAD"
        DetalleFacturaCompra.objects.create(
            id_factura_compra=fac_extra,
            id_producto=ctx["prod_b"],
            cantidad=Decimal("1"),
            precio_unitario=Decimal("10.00"),
            subtotal=Decimal("10.00"),
            total_linea=Decimal("10.00"),
        )
        # prod_b sí estaba en OC, usar producto nuevo fuera de OC:
        from apps.inventario.models import Producto

        prod_fuera = Producto.objects.create(
            id_empresa=empresa_a,
            nombre_producto="Aditivo Extra",
            sku="SKU-FUERA",
            id_categoria=ctx["prod_a"].id_categoria,
            id_unidad_medida_base=ctx["prod_a"].id_unidad_medida_base,
            id_moneda_precio=moneda_usd,
        )
        DetalleFacturaCompra.objects.create(
            id_factura_compra=fac_extra,
            id_producto=prod_fuera,
            cantidad=Decimal("1"),
            precio_unitario=Decimal("10.00"),
            subtotal=Decimal("10.00"),
            total_linea=Decimal("10.00"),
        )
        assert validar_three_way_matching(fac_extra)["estado"] == "DISCREPANCIA_CANTIDAD"
        assert (
            client.get(
                f"/api/compras/facturas-compra/{fac_extra.pk}/validar-three-way-matching/?tolerancia_cantidad_pct=5&tolerancia_precio_pct=5"
            ).status_code
            == 200
        )
        with pytest.raises(SupplyChainCompraError):
            validar_three_way_matching(fac_extra, tolerancia_cantidad_pct=Decimal("-1"))

        # Inventario: semaforo fallback COSTO_PROMEDIO + barcode vacío + conteo errores + diferencia 0
        prod_fuera.costo_promedio = Decimal("10.0000")
        prod_fuera.precio_venta_sugerido = Decimal("0")
        prod_fuera.save(update_fields=["costo_promedio", "precio_venta_sugerido"])
        sem_fb = evaluar_semaforo_margen_producto(prod_fuera)
        assert sem_fb["fuente_costo"] == "COSTO_PROMEDIO" and sem_fb["semaforo"] == "ROJO"
        with pytest.raises(InventarioSupplyChainError):
            buscar_producto_por_barcode(empresa_a, "   ")

        with pytest.raises(InventarioSupplyChainError):
            crear_conteo_inventario(
                empresa=empresa_a, almacen=ctx["alm_orig"], responsable=ctx["user"], ambito="INVALIDO"
            )
        cnt_ok = crear_conteo_inventario(
            empresa=empresa_a,
            almacen=ctx["alm_orig"],
            responsable=ctx["user"],
            items=[{"producto": ctx["prod_a"], "variante": var_a, "ubicacion": ctx["ubic_pick"]}],
        )
        # Escaneo exacto a 0 (sistema 0) -> enviar y aprobar sin generar movimientos
        registrar_escaneo_conteo(
            conteo=cnt_ok,
            codigo_o_producto_id="7591234500011",
            cantidad=Decimal("0"),
            modo="REEMPLAZAR",
            variante_id=str(var_a.pk),
            ubicacion_id=str(ctx["ubic_pick"].pk),
        )
        with pytest.raises(InventarioSupplyChainError):
            registrar_escaneo_conteo(conteo=cnt_ok, codigo_o_producto_id="7591234500011", modo="OTRO")
        with pytest.raises(InventarioSupplyChainError):
            registrar_escaneo_conteo(
                conteo=cnt_ok, codigo_o_producto_id="7591234500011", cantidad=Decimal("-1"), modo="REEMPLAZAR"
            )
        enviar_conteo_aprobacion(cnt_ok)
        res_cero = aprobar_aplicar_conteo(cnt_ok, ctx["user"])
        assert res_cero["ajustes_generados"] == 0
        with pytest.raises(InventarioSupplyChainError):
            aprobar_aplicar_conteo(cnt_ok, ctx["user"])

        PasoOperacion.objects.create(
            id_empresa=empresa_a,
            id_almacen=ctx["alm_dest"],
            tipo_operacion="ENTREGA",
            secuencia=1,
            nombre_paso="Pack",
        )
        op_scan = crear_operacion(
            empresa=empresa_a,
            almacen=ctx["alm_dest"],
            tipo_operacion="ENTREGA",
            origen_tipo="SCRAP",
            lineas=[{"producto": ctx["prod_a"], "cantidad": Decimal("2")}],
            usuario=ctx["user"],
            motivo="Prueba validación scan",
        )
        with pytest.raises(InventarioSupplyChainError):
            escanear_linea_operacion(operacion=op_scan, codigo="7591234500011", cantidad=Decimal("0"))
        with pytest.raises(InventarioSupplyChainError):
            escanear_linea_operacion(operacion=op_scan, codigo="   ", cantidad=Decimal("1"))

        # Almacenes tránsito API errores 400/404 y servicios validaciones
        assert (
            client.post(
                "/api/almacenes/transferencias-transito/despachar/",
                {
                    "id_empresa": str(ctx_b["alm_orig"].id_empresa_id),
                    "id_almacen_origen": str(ctx["alm_orig"].pk),
                    "id_almacen_destino": str(ctx["alm_dest"].pk),
                    "items": [{"producto": str(ctx["prod_a"].pk), "cantidad": "1"}],
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/almacenes/transferencias-transito/despachar/",
                {
                    "id_almacen_origen": str(ctx["alm_orig"].pk),
                    "id_almacen_destino": str(ctx["alm_dest"].pk),
                    "id_ubicacion_transito": str(uuid.uuid4()),
                    "items": [{"producto": str(ctx["prod_a"].pk), "cantidad": "1"}],
                },
                format="json",
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/almacenes/transferencias-transito/despachar/",
                {
                    "id_almacen_origen": str(ctx["alm_orig"].pk),
                    "id_almacen_destino": str(ctx["alm_dest"].pk),
                    "items": [{"producto": str(ctx_b["prod_a"].pk), "cantidad": "1"}],
                },
                format="json",
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/almacenes/transferencias-transito/despachar/",
                {
                    "id_almacen_origen": str(ctx["alm_orig"].pk),
                    "id_almacen_destino": str(ctx["alm_dest"].pk),
                    "items": [{"producto": str(ctx["prod_a"].pk), "variante": str(uuid.uuid4()), "cantidad": "1"}],
                },
                format="json",
            ).status_code
            == 400
        )
        with pytest.raises(TransferenciaTransitoError):
            despachar_transferencia_transito(
                empresa=empresa_a,
                almacen_origen=ctx_b["alm_orig"],
                almacen_destino=ctx["alm_dest"],
                usuario=ctx["user"],
                items=[{"producto": ctx["prod_a"], "cantidad": Decimal("1")}],
            )
        with pytest.raises(TransferenciaTransitoError):
            despachar_transferencia_transito(
                empresa=empresa_a,
                almacen_origen=ctx["alm_orig"],
                almacen_destino=ctx["alm_dest"],
                usuario=ctx["user"],
                ambito="OTRO",
                items=[{"producto": ctx["prod_a"], "cantidad": Decimal("1")}],
            )
        with pytest.raises(TransferenciaTransitoError):
            despachar_transferencia_transito(
                empresa=empresa_a,
                almacen_origen=ctx["alm_orig"],
                almacen_destino=ctx["alm_dest"],
                usuario=ctx["user"],
                ubicacion_transito=ctx_b["ubic_trans"],
                items=[{"producto": ctx["prod_a"], "cantidad": Decimal("1")}],
            )
        with pytest.raises(TransferenciaTransitoError):
            despachar_transferencia_transito(
                empresa=empresa_a,
                almacen_origen=ctx["alm_orig"],
                almacen_destino=ctx["alm_dest"],
                usuario=ctx["user"],
                items=[{"producto": ctx["prod_a"], "cantidad": Decimal("0")}],
            )
        with pytest.raises(TransferenciaTransitoError):
            despachar_transferencia_transito(
                empresa=empresa_a,
                almacen_origen=ctx["alm_orig"],
                almacen_destino=ctx["alm_dest"],
                usuario=ctx["user"],
                items=[{"producto": ctx_b["prod_a"], "cantidad": Decimal("1")}],
            )
        trf_e = despachar_transferencia_transito(
            empresa=empresa_a,
            almacen_origen=ctx["alm_orig"],
            almacen_destino=ctx["alm_dest"],
            usuario=ctx["user"],
            items=[{"producto": ctx["prod_a"], "cantidad": Decimal("1")}],
        )
        cancelar_transferencia_transito(trf_e, ctx["user"])
        with pytest.raises(TransferenciaTransitoError):
            recibir_transferencia_transito(transferencia=trf_e, usuario=ctx["user"])

        # Cobertura adicional helpers _dec, margen_alerta < min, y ubicacion conteo
        from apps.almacenes.services_transito import _dec as trf_dec
        from apps.inventario.services_supply_chain import _dec as inv_dec

        assert trf_dec("", Decimal("2")) == Decimal("2")
        with pytest.raises(TransferenciaTransitoError):
            trf_dec("invalido")
        with pytest.raises(TransferenciaTransitoError):
            trf_dec("NaN")
        assert inv_dec("", Decimal("3")) == Decimal("3")
        with pytest.raises(InventarioSupplyChainError):
            inv_dec(None)
        with pytest.raises(InventarioSupplyChainError):
            inv_dec("NaN")

        prod_fuera.costo_reposicion_usd = Decimal("10.00")
        prod_fuera.margen_minimo_pct = Decimal("30.00")
        prod_fuera.margen_alerta_pct = Decimal("10.00")
        prod_fuera.precio_venta_sugerido = Decimal("15.00")
        prod_fuera.save(
            update_fields=["costo_reposicion_usd", "margen_minimo_pct", "margen_alerta_pct", "precio_venta_sugerido"]
        )
        assert evaluar_semaforo_margen_producto(prod_fuera)["semaforo"] == "VERDE"

        with pytest.raises(InventarioSupplyChainError):
            crear_conteo_inventario(
                empresa=empresa_a,
                almacen=ctx["alm_orig"],
                responsable=ctx["user"],
                items=[{"producto": ctx["prod_a"], "ubicacion": ctx_b["ubic_pick"]}],
            )
        with pytest.raises(InventarioSupplyChainError):
            crear_conteo_inventario(
                empresa=empresa_a,
                almacen=ctx["alm_orig"],
                responsable=ctx["user"],
                items=[{"producto": ctx_b["prod_a"]}],
            )
        from apps.inventario.serializers_supply_chain import resolver_empresa_usuario_inventario
        from rest_framework.exceptions import ValidationError as DRFValidationError
        from rest_framework.test import APIRequestFactory

        req_no_emp = APIRequestFactory().get("/")
        req_no_emp.user = ctx["user"]
        with pytest.raises(DRFValidationError):
            resolver_empresa_usuario_inventario(req_no_emp, str(empresa_b.pk))

        # Nuevas guardas de seguridad (PATCH/DELETE bloqueado en APLICADO + ?empresa=/id_empresa NUL/UUID inválido -> 400)
        assert (
            client.get(
                "/api/inventario/productos/buscar-barcode/?codigo=7591234500011&empresa=no-uuid\x00"
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/almacenes/transferencias-transito/despachar/",
                {
                    "id_empresa": "no-uuid\x00",
                    "id_almacen_origen": str(ctx["alm_orig"].pk),
                    "id_almacen_destino": str(ctx["alm_dest"].pk),
                    "items": [{"producto": str(ctx["prod_a"].pk), "cantidad": "1"}],
                },
                format="json",
            ).status_code
            == 400
        )
        r_cd_edit = client.post(
            "/api/compras/costos-destino/",
            {
                "id_recepcion": str(ctx["recepcion"].pk),
                "numero_documento": "CD-DEL-LOCK",
                "fecha": "2026-11-22",
                "metodo_prorrateo": "VALOR",
            },
            format="json",
        )
        assert r_cd_edit.status_code == 201
        cd_lock_id = r_cd_edit.data["id_costo_destino"]
        r_ln_lock = client.post(
            "/api/compras/lineas-costo-destino/",
            {"id_costo_destino": cd_lock_id, "concepto": "FLETE", "descripcion": "Lock", "monto": "12.00"},
            format="json",
        )
        assert r_ln_lock.status_code == 201
        ln_lock_id = r_ln_lock.data["id_linea_costo_destino"]
        assert (
            client.patch(
                f"/api/compras/costos-destino/{cd_lock_id}/", {"observaciones": "ok"}, format="json"
            ).status_code
            == 200
        )
        assert client.post(f"/api/compras/costos-destino/{cd_lock_id}/aplicar/", {}, format="json").status_code == 200
        assert (
            client.patch(
                f"/api/compras/costos-destino/{cd_lock_id}/", {"observaciones": "nope"}, format="json"
            ).status_code
            == 400
        )
        assert client.delete(f"/api/compras/costos-destino/{cd_lock_id}/").status_code == 400
        assert client.delete(f"/api/compras/lineas-costo-destino/{ln_lock_id}/").status_code == 400

        # BORRADOR sí permite soft-delete
        r_cd_del = client.post(
            "/api/compras/costos-destino/",
            {
                "id_recepcion": str(ctx["recepcion"].pk),
                "numero_documento": "CD-SOFT-DEL",
                "fecha": "2026-11-22",
                "metodo_prorrateo": "VALOR",
            },
            format="json",
        )
        assert r_cd_del.status_code == 201
        cd_del_id = r_cd_del.data["id_costo_destino"]
        r_ln_del = client.post(
            "/api/compras/lineas-costo-destino/",
            {"id_costo_destino": cd_del_id, "concepto": "FLETE", "descripcion": "Del", "monto": "5.00"},
            format="json",
        )
        assert r_ln_del.status_code == 201
        assert (
            client.delete(f"/api/compras/lineas-costo-destino/{r_ln_del.data['id_linea_costo_destino']}/").status_code
            == 204
        )
        assert client.delete(f"/api/compras/costos-destino/{cd_del_id}/").status_code == 204
