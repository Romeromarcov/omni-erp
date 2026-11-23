"""Tests de integración Plan 09 Ola 2A: Motor Comercial VE (Fases 3.1, 3.2 y 3.3)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.utils import ProgrammingError
from django.utils import timezone

from apps.core import rls
from tests.factories import (
    AlmacenFactory,
    CategoriaProductoFactory,
    ClienteFactory,
    MonedaFactory,
    ProductoFactory,
)

pytestmark = [pytest.mark.django_db]


# ---------------------------------------------------------------------------
# 1. Precios Dinámicos por Brecha, Moneda de Pago, Zona, Segmento y Volumen
# ---------------------------------------------------------------------------


class TestPreciosDinamicosVE:
    def test_crud_validaciones_rls_y_motor_composicion_brecha(
        self, rls_test_role, client_a, client_b, empresa_a, empresa_b, user_a, moneda_usd
    ):
        from apps.core.models import CapabilityToken, Contacto
        from apps.finanzas.models import MonedaEmpresaActiva, TasaCambio, TipoTasaCambio
        from apps.ventas.mcp import ventas_cotizar_precio_dinamico
        from apps.ventas.models import (
            DetallePrecio,
            ListaPrecio,
            ReglaPrecioDinamico,
        )

        hoy = timezone.localdate()
        moneda_ves = MonedaFactory(codigo_iso="VES", nombre="Bolívar", simbolo="Bs")
        moneda_usdt = MonedaFactory(codigo_iso="USDT", nombre="Tether", simbolo="USDT")
        empresa_a.id_moneda_pais = moneda_ves
        empresa_a.save(update_fields=["id_moneda_pais"])
        MonedaEmpresaActiva.objects.create(
            empresa=empresa_a,
            moneda=moneda_usdt,
            activa=True,
            es_moneda_referencia=True,
        )

        # Tasas BCV (40 Bs/USD), Paralelo (50 Bs/USD -> 25% brecha), y USD->USDT (1.02)
        tipo_bcv = TipoTasaCambio.objects.create(
            id_empresa=empresa_a,
            codigo="OFICIAL_BCV",
            nombre="BCV Oficial",
            es_oficial_fiscal=True,
        )
        tipo_par = TipoTasaCambio.objects.create(
            id_empresa=empresa_a,
            codigo="PARALELO",
            nombre="Paralelo Mercado",
            es_oficial_fiscal=False,
        )
        TasaCambio.objects.create(
            id_empresa=empresa_a,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_ves,
            tipo_tasa="OFICIAL_BCV",
            id_tipo_tasa=tipo_bcv,
            valor_tasa=Decimal("40.00000000"),
            fecha_tasa=hoy,
        )
        TasaCambio.objects.create(
            id_empresa=empresa_a,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_ves,
            tipo_tasa="PERSONALIZADA",
            id_tipo_tasa=tipo_par,
            valor_tasa=Decimal("50.00000000"),
            fecha_tasa=hoy,
        )
        TasaCambio.objects.create(
            id_empresa=empresa_a,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_usdt,
            tipo_tasa="PERSONALIZADA",
            valor_tasa=Decimal("1.02000000"),
            fecha_tasa=hoy,
        )

        cat = CategoriaProductoFactory(id_empresa=empresa_a, nombre_categoria="Lubricantes")
        prod = ProductoFactory(
            id_empresa=empresa_a,
            id_categoria=cat,
            precio_venta_sugerido=Decimal("100.00"),
        )
        lista_ref = ListaPrecio.objects.create(
            id_empresa=empresa_a,
            nombre="Lista 1 Referencia",
            codigo="LISTA1",
            es_referencia=True,
            id_moneda=moneda_usd,
        )
        DetallePrecio.objects.create(
            id_lista=lista_ref,
            id_producto=prod,
            precio=Decimal("100.0000"),
            precio_minimo=Decimal("85.0000"),
        )
        contacto = Contacto.objects.create(
            id_empresa=empresa_a,
            nombre="Distribuidora Centro C.A.",
            rif="J-40100100-1",
            estado="Carabobo",
            es_cliente=True,
        )

        # Crear reglas vía API:
        # 1) Brecha cambiaria cuando pagan en VES (traslada 100% de la brecha 25%: 100 -> 125)
        r_brecha = client_a.post(
            "/api/ventas/reglas-precio-dinamico/",
            {
                "nombre": "Ajuste brecha pagos Bs BCV",
                "codigo": "BRECHA-VES",
                "tipo_factor": "BRECHA_CAMBIARIA",
                "clave_condicion": "VES",
                "modo_calculo": "BRECHA_TASA",
                "valor_factor": "100.000000",
                "codigo_tipo_tasa_referencia": "PARALELO",
                "prioridad": 10,
                "acumulable": True,
            },
            format="json",
        )
        assert r_brecha.status_code == 201, r_brecha.data

        # 2) Descuento por zona CARABOBO (-4%): 125 * 0.96 = 120
        assert (
            client_a.post(
                "/api/ventas/reglas-precio-dinamico/",
                {
                    "nombre": "Descuento ruta Carabobo",
                    "codigo": "ZONA-CARABOBO",
                    "tipo_factor": "ZONA",
                    "clave_condicion": "CARABOBO",
                    "modo_calculo": "PORCENTAJE",
                    "valor_factor": "-4.000000",
                    "prioridad": 20,
                    "acumulable": True,
                },
                format="json",
            ).status_code
            == 201
        )

        # 3) Volumen >= 10 unidades multiplicador 0.95 -> 120 * 0.95 = 114
        assert (
            client_a.post(
                "/api/ventas/reglas-precio-dinamico/",
                {
                    "nombre": "Descuento volumen mayor 10+",
                    "codigo": "VOL-10",
                    "tipo_factor": "VOLUMEN",
                    "cantidad_minima": "10.0000",
                    "modo_calculo": "MULTIPLICADOR",
                    "valor_factor": "0.950000",
                    "prioridad": 30,
                    "acumulable": True,
                },
                format="json",
            ).status_code
            == 201
        )

        # Validaciones de serializer: código duplicado, multiplicador <= 0, rango fechas inválido
        assert (
            client_a.post(
                "/api/ventas/reglas-precio-dinamico/",
                {
                    "nombre": "Dup",
                    "codigo": "VOL-10",
                    "tipo_factor": "VOLUMEN",
                    "modo_calculo": "PORCENTAJE",
                    "valor_factor": "0",
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/ventas/reglas-precio-dinamico/",
                {
                    "nombre": "Mult cero",
                    "codigo": "BAD-MULT",
                    "tipo_factor": "MONEDA_PAGO",
                    "modo_calculo": "MULTIPLICADOR",
                    "valor_factor": "0",
                    "vigente_desde": "2026-12-31",
                    "vigente_hasta": "2026-01-01",
                },
                format="json",
            ).status_code
            == 400
        )

        # Cotizar VES (cantidad 10, contacto Carabobo) vía REST -> 114.0000 + trimonetario
        r_cot = client_a.post(
            "/api/ventas/reglas-precio-dinamico/cotizar/",
            {
                "id_producto": str(prod.id_producto),
                "cantidad": "10.0000",
                "moneda_pago": "VES",
                "id_contacto": str(contacto.id_contacto),
                "tipo_tasa_referencia": "PARALELO",
            },
            format="json",
        )
        assert r_cot.status_code == 200, r_cot.data
        assert Decimal(r_cot.data["precio_base"]) == Decimal("100.0000")
        assert Decimal(r_cot.data["precio_final"]) == Decimal("114.0000")
        assert Decimal(r_cot.data["total_linea"]) == Decimal("1140.0000")
        assert Decimal(r_cot.data["brecha_cambiaria_pct"]) == Decimal("25.0000")
        assert [r["codigo"] for r in r_cot.data["reglas_aplicadas"]] == [
            "BRECHA-VES",
            "ZONA-CARABOBO",
            "VOL-10",
        ]
        assert Decimal(r_cot.data["equivalencias"]["monto_pais_fiscal"]) == Decimal("4560.0000")
        assert Decimal(r_cot.data["equivalencias"]["monto_referencia"]) == Decimal("116.2800")

        # Regla no acumulable y piso precio_minimo (85.0000) cuando pagan en USD
        assert (
            client_a.post(
                "/api/ventas/reglas-precio-dinamico/",
                {
                    "nombre": "Promo agresiva USD (-30%)",
                    "codigo": "PROMO-USD-PISO",
                    "tipo_factor": "MONEDA_PAGO",
                    "clave_condicion": "USD",
                    "modo_calculo": "PORCENTAJE",
                    "valor_factor": "-30.000000",
                    "prioridad": 5,
                    "acumulable": False,
                },
                format="json",
            ).status_code
            == 201
        )
        r_piso = client_a.post(
            "/api/ventas/reglas-precio-dinamico/cotizar/",
            {
                "id_producto": str(prod.id_producto),
                "cantidad": "10.0000",
                "moneda_pago": "USD",
                "zona": "CARABOBO",
            },
            format="json",
        )
        assert r_piso.status_code == 200, r_piso.data
        # Sin piso sería 70.0000; precio_minimo=85.0000 lo detiene en 85 y acumulable=False detiene ZONA/VOL
        assert Decimal(r_piso.data["precio_final"]) == Decimal("85.0000")
        assert r_piso.data["precio_minimo_aplicado"] is True
        assert [r["codigo"] for r in r_piso.data["reglas_aplicadas"]] == ["PROMO-USD-PISO"]

        # Error cantidad <= 0 retorna 400 domain_error_response
        r_bad_qty = client_a.post(
            "/api/ventas/reglas-precio-dinamico/cotizar/",
            {"id_producto": str(prod.id_producto), "cantidad": "0"},
            format="json",
        )
        assert r_bad_qty.status_code == 400
        assert r_bad_qty.data["codigo"] == "PRECIO_ERROR"

        # Aislamiento B + MCP ventas_cotizar_precio_dinamico
        assert len(client_b.get("/api/ventas/reglas-precio-dinamico/").data["results"]) == 0
        tok = CapabilityToken.objects.create(
            empresa=empresa_a, nombre="tok-precio", scopes=["ventas:read"], activo=True, creado_por=user_a
        )
        res_mcp = ventas_cotizar_precio_dinamico(
            str(tok.token), str(empresa_a.id_empresa), str(prod.id_producto), cantidad="10", moneda_pago="USD"
        )
        assert res_mcp["precio_final"] == Decimal("85.0000")

        # Verificar política RLS en PostgreSQL
        with connection.cursor() as cur:
            cur.execute("SELECT policyname FROM pg_policies WHERE tablename = 'ventas_regla_precio_dinamico';")
            assert rls.POLICY_NAME in [row[0] for row in cur.fetchall()]

        if rls_test_role is not None:
            regla_b = ReglaPrecioDinamico.objects.create(
                id_empresa=empresa_b,
                nombre="Regla B",
                codigo="REGLA-B",
                tipo_factor="SEGMENTO",
                modo_calculo="PORCENTAJE",
                valor_factor=Decimal("-5"),
            )
            with transaction.atomic():
                with connection.cursor() as cur:
                    cur.execute(f'SET LOCAL ROLE "{rls_test_role}"')
                    cur.execute(f"SELECT set_config('{rls.GUC_BYPASS}', 'off', true)")
                    cur.execute(f"SELECT set_config('{rls.GUC_EMPRESAS}', %s, true)", [str(empresa_a.id_empresa)])
                    ids = {str(x) for x in ReglaPrecioDinamico.objects.values_list("id_regla", flat=True)}
                    assert str(regla_b.id_regla) not in ids
                    with pytest.raises((IntegrityError, ProgrammingError, Exception)), transaction.atomic():
                        cur.execute(
                            """
                            INSERT INTO ventas_regla_precio_dinamico (
                                id_regla, id_empresa_id, nombre, codigo, tipo_factor, clave_condicion,
                                cantidad_minima, modo_calculo, valor_factor, codigo_tipo_tasa_referencia,
                                prioridad, acumulable, activo, fecha_creacion
                            ) VALUES (
                                gen_random_uuid(), %s, 'Hack', 'HACK', 'ZONA', '', 0, 'PORCENTAJE',
                                0, '', 10, true, true, NOW()
                            )
                            """,
                            [str(empresa_b.id_empresa)],
                        )


# ---------------------------------------------------------------------------
# 2. Flujo Dual Nota de Venta Gerencial (CxC real, Inv y Asiento GERENCIAL)
# ---------------------------------------------------------------------------


class TestFlujoDualNotaVentaGerencial:
    def test_confirmar_nota_venta_gerencial_no_toca_libros_seniat(self, empresa_a, user_a, moneda_usd):
        from apps.contabilidad.models import AsientoContable, MapeoContable, PeriodoContable, PlanCuentas
        from apps.fiscal.libros_seniat import generar_libro_ventas_txt
        from apps.inventario.models import MovimientoInventario, StockActual
        from apps.ventas.models import DetalleNotaVenta, NotaVenta
        from apps.ventas.services import confirmar_nota_venta

        hoy = timezone.localdate()
        cta_cxc = PlanCuentas.objects.create(
            id_empresa=empresa_a,
            codigo_cuenta="1.1.02.99",
            nombre_cuenta="CxC NV",
            tipo_cuenta="ACTIVO",
            naturaleza="DEUDORA",
            nivel=4,
        )
        cta_ing = PlanCuentas.objects.create(
            id_empresa=empresa_a,
            codigo_cuenta="4.1.01.99",
            nombre_cuenta="Ingresos NV",
            tipo_cuenta="INGRESO",
            naturaleza="ACREEDORA",
            nivel=4,
        )
        PeriodoContable.objects.create(id_empresa=empresa_a, anio=hoy.year, mes=hoy.month, estado="ABIERTO")
        MapeoContable.objects.create(
            id_empresa=empresa_a, tipo_asiento="NOTA_VENTA", cuenta_debe=cta_cxc, cuenta_haber=cta_ing
        )

        almacen = AlmacenFactory(id_empresa=empresa_a)
        prod = ProductoFactory(id_empresa=empresa_a)
        StockActual.objects.create(
            id_empresa=empresa_a, id_producto=prod, id_almacen=almacen, cantidad_disponible=Decimal("20.0000")
        )
        cliente = ClienteFactory(id_empresa=empresa_a, rif="J-31000222-1")

        nv = NotaVenta.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            numero_nota="NV-DUAL-001",
            fecha_nota=hoy,
        )
        assert nv.ambito == "GERENCIAL"
        DetalleNotaVenta.objects.create(
            id_nota_venta=nv,
            id_producto=prod,
            cantidad=Decimal("2.0000"),
            precio_unitario=Decimal("50.0000"),
            subtotal=Decimal("100.0000"),
        )

        res = confirmar_nota_venta(nv, almacen, user_a)
        assert res["cxc"].documento_json["ambito"] == "GERENCIAL"
        mov = MovimientoInventario.objects.get(pk=res["movimientos"][0].pk)
        assert mov.ambito == "GERENCIAL"
        asiento = AsientoContable.objects.get(pk=res["asiento"].pk)
        assert asiento.ambito == "GERENCIAL"
        assert "NV-DUAL-001" not in generar_libro_ventas_txt(empresa_a, hoy, hoy)


# ---------------------------------------------------------------------------
# 3. Crédito por Mora Real y Comisiones por Cobro Efectivo + Metas
# ---------------------------------------------------------------------------


class TestCreditoMoraYComisionesCobroEfectivo:
    def test_bloqueo_mora_descuenta_abonos_y_asignacion_pago(self, client_a, empresa_a, user_a, moneda_usd):
        from apps.core.models import Contacto
        from apps.cuentas_por_cobrar.models import AbonoCxC, CuentaPorCobrar
        from apps.finanzas.models import AsignacionPago, MetodoPago, Pago
        from apps.inventario.models import StockActual
        from apps.ventas.models import DetallePedido, Pedido
        from apps.ventas.services import VentaError, confirmar_pedido
        from apps.ventas.services_credito import evaluar_credito_cliente

        hoy = timezone.localdate()
        contacto = Contacto.objects.create(
            id_empresa=empresa_a, nombre="Cliente Mora S.A.", rif="J-50111222-3", es_cliente=True
        )
        cliente = ClienteFactory(
            id_empresa=empresa_a,
            razon_social="Cliente Mora S.A.",
            rif="J-50111222-3",
            tipo_cliente="CREDITO",
            limite_credito=Decimal("500.00"),
            dias_credito=15,
            dias_gracia_mora=3,
            bloquear_por_mora=True,
            contacto=contacto,
        )
        almacen = AlmacenFactory(id_empresa=empresa_a)
        prod = ProductoFactory(id_empresa=empresa_a)
        StockActual.objects.create(
            id_empresa=empresa_a, id_producto=prod, id_almacen=almacen, cantidad_disponible=Decimal("20.0000")
        )

        # CxC vencida hace 5 días (> 3 días de gracia) por $100
        cxc = CuentaPorCobrar.objects.create(
            cliente=cliente,
            empresa=empresa_a,
            monto=Decimal("100.00"),
            fecha_emision=hoy - timedelta(days=20),
            fecha_vencimiento=hoy - timedelta(days=5),
            estado="vencida",
        )
        ped = Pedido.objects.create(
            id_empresa=empresa_a, id_cliente=cliente, numero_pedido="PED-MORA-1", fecha_pedido=hoy
        )
        DetallePedido.objects.create(
            id_pedido=ped,
            id_producto=prod,
            cantidad=Decimal("1.0000"),
            precio_unitario=Decimal("50.0000"),
            subtotal=Decimal("50.0000"),
        )

        # Pedido bloqueado por mora real
        with pytest.raises(VentaError, match="vencida"):
            confirmar_pedido(ped, almacen, user_a)

        r_eval = client_a.get(f"/api/ventas/pedidos/{ped.id_pedido}/evaluar-credito/")
        assert r_eval.status_code == 200
        assert r_eval.data["bloqueado_por_mora"] is True

        # Abono parcial ($60) + AsignacionPago por saldo restante ($40) dejan saldo neto = 0 -> desbloquea!
        AbonoCxC.objects.create(cuenta_por_cobrar=cxc, monto=Decimal("60.00"), usuario=user_a)
        metodo = MetodoPago.objects.create(nombre_metodo="Zelle Mora Test", tipo_metodo="DIGITAL")
        pago = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto,
            tipo_operacion="INGRESO",
            fecha_pago=timezone.now(),
            monto=Decimal("40.00"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo,
        )
        AsignacionPago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto,
            id_pago=pago,
            tipo_documento="CUENTA_POR_COBRAR",
            id_cxc=cxc,
            monto_asignado_pago=Decimal("40.0000"),
            monto_asignado_documento=Decimal("40.0000"),
            id_moneda_documento=moneda_usd,
            estado="ACTIVA",
        )
        r_cred = client_a.get(f"/api/crm/clientes/{cliente.id_cliente}/credito-disponible/")
        assert r_cred.status_code == 200
        assert Decimal(r_cred.data["saldo_pendiente"]) == Decimal("0.00")
        assert r_cred.data["bloqueado"] is False
        assert evaluar_credito_cliente(cliente, empresa_a)["monto_vencido"] == Decimal("0.00")

        # Ahora el pedido confirma limpio
        res_conf = confirmar_pedido(ped, almacen, user_a)
        assert res_conf["cxc"] is not None

    def test_comision_por_cobro_efectivo_divisa_vs_bs_y_bono_meta(self, client_a, empresa_a, user_a, moneda_usd):
        from apps.finanzas.models import MetodoPago, Pago
        from apps.inventario.models import StockActual
        from apps.ventas.models import ComisionVenta, DetalleNotaVenta, EsquemaComision, NotaVenta
        from apps.ventas.services import entregar_nota_venta

        hoy = timezone.localdate()
        moneda_ves = MonedaFactory(codigo_iso="VES", nombre="Bolívar", simbolo="Bs")
        empresa_a.id_moneda_pais = moneda_ves
        empresa_a.save(update_fields=["id_moneda_pais"])

        almacen = AlmacenFactory(id_empresa=empresa_a)
        prod = ProductoFactory(id_empresa=empresa_a)
        StockActual.objects.create(
            id_empresa=empresa_a, id_producto=prod, id_almacen=almacen, cantidad_disponible=Decimal("50.0000")
        )
        cliente = ClienteFactory(id_empresa=empresa_a, rif="J-61000222-9")

        # Crear esquema COBRO_EFECTIVO vía API: 5% divisa, 2% Bs, meta $1000 + bono 1%
        r_esq = client_a.post(
            "/api/ventas/esquemas-comision/",
            {
                "vendedor": str(user_a.pk),
                "porcentaje_base": "3.0000",
                "modalidad_devengo": "COBRO_EFECTIVO",
                "porcentaje_cobro_divisa": "5.0000",
                "porcentaje_cobro_bs": "2.0000",
                "meta_mensual_monto": "1000.0000",
                "bono_meta_porcentaje": "1.0000",
            },
            format="json",
        )
        assert r_esq.status_code == 201, r_esq.data
        assert EsquemaComision.objects.filter(id_empresa=empresa_a, modalidad_devengo="COBRO_EFECTIVO").exists()

        # Venta 1 ($600): al entregar NO devenga todavía porque modalidad == COBRO_EFECTIVO
        nv1 = NotaVenta.objects.create(
            id_empresa=empresa_a, id_cliente=cliente, id_vendedor=user_a, numero_nota="NV-COB-1", fecha_nota=hoy
        )
        DetalleNotaVenta.objects.create(
            id_nota_venta=nv1,
            id_producto=prod,
            cantidad=Decimal("1.0000"),
            precio_unitario=Decimal("600.0000"),
            subtotal=Decimal("600.0000"),
        )
        res1 = entregar_nota_venta(nv1, almacen, user_a)
        assert res1["comision"] is None

        # Cobrar NV-1 en Bs (VES) -> aplica 2% ($12.0000); aún no alcanza meta $1000
        metodo = MetodoPago.objects.create(nombre_metodo="Pago Móvil Test", tipo_metodo="TRANSFERENCIA")
        pago_bs = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="INGRESO",
            fecha_pago=timezone.now(),
            monto=Decimal("24000.00"),
            id_moneda=moneda_ves,
            id_metodo_pago=metodo,
        )
        r_c1 = client_a.post(
            "/api/ventas/comisiones/devengar-cobro/",
            {"id_nota_venta": str(nv1.id_nota_venta), "id_pago": str(pago_bs.id_pago), "fecha_cobro": str(hoy)},
            format="json",
            HTTP_IDEMPOTENCY_KEY="cobro-nv1-key",
        )
        assert r_c1.status_code == 200, r_c1.data
        assert r_c1.data["comision"]["origen_devengo"] == "COBRO_EFECTIVO"
        assert r_c1.data["comision"]["moneda_cobro_tipo"] == "MONEDA_LOCAL"
        assert Decimal(r_c1.data["comision"]["monto"]) == Decimal("12.0000")

        # Venta 2 ($500): al cobrar en DIVISA (USD) acumulado=$1100 >= $1000 -> 5% ($25) + 1% bono ($5) = $30.0000
        nv2 = NotaVenta.objects.create(
            id_empresa=empresa_a, id_cliente=cliente, id_vendedor=user_a, numero_nota="NV-COB-2", fecha_nota=hoy
        )
        DetalleNotaVenta.objects.create(
            id_nota_venta=nv2,
            id_producto=prod,
            cantidad=Decimal("1.0000"),
            precio_unitario=Decimal("500.0000"),
            subtotal=Decimal("500.0000"),
        )
        entregar_nota_venta(nv2, almacen, user_a)
        r_c2 = client_a.post(
            "/api/ventas/comisiones/devengar-cobro/",
            {"id_nota_venta": str(nv2.id_nota_venta), "moneda_cobro_iso": "USD", "fecha_cobro": str(hoy)},
            format="json",
            HTTP_IDEMPOTENCY_KEY="cobro-nv2-key",
        )
        assert r_c2.status_code == 200, r_c2.data
        assert r_c2.data["comision"]["moneda_cobro_tipo"] == "DIVISA"
        assert Decimal(r_c2.data["comision"]["monto"]) == Decimal("30.0000")
        assert ComisionVenta.objects.filter(id_empresa=empresa_a).count() == 2

        # Avance de meta mensual -> 110.00% alcanzada!
        r_meta = client_a.get(f"/api/ventas/comisiones/avance-meta/?anio={hoy.year}&mes={hoy.month}")
        assert r_meta.status_code == 200, r_meta.data
        assert Decimal(r_meta.data["acumulado_mes"]) == Decimal("1100.0000")
        assert Decimal(r_meta.data["porcentaje_cumplimiento"]) == Decimal("110.00")
        assert r_meta.data["meta_alcanzada"] is True


class TestValidacionesYRutasNegativasOla2A:
    def test_validaciones_reglas_cotizar_y_comisiones_cobro(
        self, client_a, empresa_a, empresa_b, user_a, user_b, moneda_usd
    ):
        import uuid

        from apps.core.models import CapabilityToken, Contacto
        from apps.finanzas.models import MetodoPago, Pago
        from apps.ventas.mcp import ventas_cotizar_precio_dinamico
        from apps.ventas.models import (
            ComisionVenta,
            DetallePrecio,
            EsquemaComision,
            ListaPrecio,
            NotaVenta,
            ReglaPrecioDinamico,
        )
        from apps.ventas.services import VentaError, devengar_comision_por_cobro
        from apps.ventas.services_precios import calcular_precio_dinamico

        hoy = timezone.localdate()
        cat_a = CategoriaProductoFactory(id_empresa=empresa_a, nombre_categoria="Cat A Neg")
        cat_b = CategoriaProductoFactory(id_empresa=empresa_b, nombre_categoria="Cat B Neg")
        prod_a = ProductoFactory(id_empresa=empresa_a, id_categoria=cat_a, precio_venta_sugerido=Decimal("50.00"))
        prod_a_otro = ProductoFactory(id_empresa=empresa_a, precio_venta_sugerido=Decimal("40.00"))
        prod_b = ProductoFactory(id_empresa=empresa_b, id_categoria=cat_b, precio_venta_sugerido=Decimal("50.00"))

        # Validaciones ReglaPrecioDinamicoSerializer: empresa cruzada, cantidad_minima < 0, vigencia y PATCH
        assert (
            client_a.post(
                "/api/ventas/reglas-precio-dinamico/",
                {
                    "nombre": "Prod B",
                    "codigo": "R-CROSS-P",
                    "tipo_factor": "VOLUMEN",
                    "producto": str(prod_b.id_producto),
                    "valor_factor": "0",
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/ventas/reglas-precio-dinamico/",
                {
                    "nombre": "Cat B",
                    "codigo": "R-CROSS-C",
                    "tipo_factor": "VOLUMEN",
                    "categoria": str(cat_b.pk),
                    "valor_factor": "0",
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/ventas/reglas-precio-dinamico/",
                {
                    "nombre": "Cant Neg",
                    "codigo": "R-NEG-Q",
                    "tipo_factor": "VOLUMEN",
                    "cantidad_minima": "-1",
                    "valor_factor": "0",
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/ventas/reglas-precio-dinamico/",
                {
                    "nombre": "Fechas",
                    "codigo": "R-FECHAS",
                    "tipo_factor": "SEGMENTO",
                    "modo_calculo": "PORCENTAJE",
                    "valor_factor": "-5",
                    "vigente_desde": "2026-12-01",
                    "vigente_hasta": "2026-01-01",
                },
                format="json",
            ).status_code
            == 400
        )

        r_ok = client_a.post(
            "/api/ventas/reglas-precio-dinamico/",
            {
                "nombre": "Segmento VIP",
                "codigo": "R-SEG-VIP",
                "tipo_factor": "SEGMENTO",
                "clave_condicion": "VIP",
                "categoria": str(cat_a.pk),
                "cantidad_minima": "2.0000",
                "modo_calculo": "PORCENTAJE",
                "valor_factor": "-10.000000",
            },
            format="json",
        )
        assert r_ok.status_code == 201
        r_patch = client_a.patch(
            f"/api/ventas/reglas-precio-dinamico/{r_ok.data['id_regla']}/",
            {"nombre": "Segmento VIP Renombrado"},
            format="json",
        )
        assert r_patch.status_code == 200

        # Lista asignada al contacto + filtro producto/categoria/cantidad_minima/SEGMENTO + brecha sin tasas
        lista_cli = ListaPrecio.objects.create(
            id_empresa=empresa_a, nombre="Lista VIP", codigo="VIP1", id_moneda=moneda_usd
        )
        DetallePrecio.objects.create(id_lista=lista_cli, id_producto=prod_a, precio=Decimal("60.0000"))
        contacto_cli = Contacto.objects.create(
            id_empresa=empresa_a, nombre="VIP S.A.", rif="J-10101010-1", lista_precio=lista_cli
        )
        ReglaPrecioDinamico.objects.create(
            id_empresa=empresa_a,
            nombre="Prod específico",
            codigo="R-PROD-A-OTRO",
            tipo_factor="MONEDA_PAGO",
            producto=prod_a_otro,
            modo_calculo="PORCENTAJE",
            valor_factor=Decimal("-5"),
            prioridad=5,
        )
        ReglaPrecioDinamico.objects.create(
            id_empresa=empresa_a,
            nombre="Brecha sin moneda pais",
            codigo="R-BRECHA-NOTASA",
            tipo_factor="BRECHA_CAMBIARIA",
            modo_calculo="BRECHA_TASA",
            valor_factor=Decimal("100"),
            prioridad=6,
        )
        # prod_a con cantidad=1 (no cumple cantidad_minima=2 de R-SEG-VIP), R-BRECHA se omite sin 500
        res_precio = calcular_precio_dinamico(
            prod_a,
            empresa_a,
            contacto=contacto_cli,
            cantidad=Decimal("1"),
            segmento="VIP",
        )
        assert res_precio["precio_base"] == Decimal("60.0000")
        assert res_precio["equivalencias"] is not None  # sin moneda pais o tasa, retorna USD base o None

        # Rutas negativas en /cotizar/ y MCP
        assert (
            client_a.post(
                "/api/ventas/reglas-precio-dinamico/cotizar/",
                {"id_producto": str(prod_b.id_producto)},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/ventas/reglas-precio-dinamico/cotizar/",
                {"id_producto": str(prod_a.id_producto), "id_contacto": str(uuid.uuid4())},
                format="json",
            ).status_code
            == 400
        )
        tok = CapabilityToken.objects.create(
            empresa=empresa_a, nombre="tok-neg", scopes=["ventas:read"], activo=True, creado_por=user_a
        )
        with pytest.raises(ValueError, match="no encontrado"):
            ventas_cotizar_precio_dinamico(str(tok.token), str(empresa_a.id_empresa), str(uuid.uuid4()))

        # Validaciones EsquemaComisionSerializer y endpoints /devengar-cobro/ + /avance-meta/
        assert (
            client_a.post(
                "/api/ventas/esquemas-comision/",
                {
                    "vendedor": str(user_a.pk),
                    "porcentaje_base": "5.0000",
                    "meta_mensual_monto": "-10.0000",
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/ventas/comisiones/devengar-cobro/",
                {"id_nota_venta": str(uuid.uuid4())},
                format="json",
            ).status_code
            == 400
        )
        cliente = ClienteFactory(id_empresa=empresa_a, rif="J-71717171-7")
        nv_borrador = NotaVenta.objects.create(
            id_empresa=empresa_a, id_cliente=cliente, id_vendedor=user_a, numero_nota="NV-NEG-1", fecha_nota=hoy
        )
        assert (
            client_a.post(
                "/api/ventas/comisiones/devengar-cobro/",
                {"id_nota_venta": str(nv_borrador.id_nota_venta), "id_pago": str(uuid.uuid4())},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/ventas/comisiones/devengar-cobro/",
                {"id_nota_venta": str(nv_borrador.id_nota_venta)},
                format="json",
            ).status_code
            == 400
        )

        # Guardas directas en devengar_comision_por_cobro
        nv_sin_vend = NotaVenta.objects.create(
            id_empresa=empresa_a, id_cliente=cliente, numero_nota="NV-NEG-2", fecha_nota=hoy, estado="ENTREGADA"
        )
        with pytest.raises(VentaError, match="vendedor"):
            devengar_comision_por_cobro(nv_sin_vend)

        nv_ent = NotaVenta.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            id_vendedor=user_a,
            numero_nota="NV-NEG-3",
            fecha_nota=hoy,
            estado="ENTREGADA",
        )
        assert devengar_comision_por_cobro(nv_ent) is None  # sin esquema retorna None

        metodo = MetodoPago.objects.create(nombre_metodo="Efectivo Neg", tipo_metodo="EFECTIVO")
        pago_b = Pago.objects.create(
            id_empresa=empresa_b,
            tipo_operacion="INGRESO",
            fecha_pago=timezone.now(),
            monto=Decimal("10"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo,
        )
        with pytest.raises(VentaError, match="empresa"):
            devengar_comision_por_cobro(nv_ent, pago=pago_b)

        esq_entrega = EsquemaComision.objects.create(
            id_empresa=empresa_a, vendedor=user_a, porcentaje_base=Decimal("4"), modalidad_devengo="ENTREGA"
        )
        with pytest.raises(VentaError, match="COBRO_EFECTIVO"):
            devengar_comision_por_cobro(nv_ent)
        com_exist = ComisionVenta.objects.create(
            id_empresa=empresa_a,
            vendedor=user_a,
            nota_venta=nv_ent,
            esquema=esq_entrega,
            base_comisionable=Decimal("100"),
            monto=Decimal("4"),
            fecha_devengo=hoy,
        )
        assert devengar_comision_por_cobro(nv_ent).pk == com_exist.pk

        # Filtros /avance-meta/ válidos e inválidos
        assert client_a.get(f"/api/ventas/comisiones/avance-meta/?vendedor={user_a.pk}").status_code == 200
        assert client_a.get("/api/ventas/comisiones/avance-meta/?vendedor=no-uuid").status_code == 400
        assert client_a.get(f"/api/ventas/comisiones/avance-meta/?vendedor={user_b.pk}").status_code == 400
        assert client_a.get("/api/ventas/comisiones/avance-meta/?anio=2026&mes=13").status_code == 400

        # Override de bloqueo de crédito en PedidoViewSet.confirmar exige admin/staff (403 -> 200)
        from datetime import timedelta

        from apps.cuentas_por_cobrar.models import CuentaPorCobrar
        from apps.inventario.models import StockActual
        from apps.ventas.models import DetallePedido, Pedido

        almacen = AlmacenFactory(id_empresa=empresa_a)
        StockActual.objects.create(
            id_empresa=empresa_a, id_producto=prod_a, id_almacen=almacen, cantidad_disponible=Decimal("10")
        )
        cli_mora = ClienteFactory(
            id_empresa=empresa_a,
            rif="J-71717172-0",
            tipo_cliente="CREDITO",
            limite_credito=Decimal("500"),
            bloquear_por_mora=True,
        )
        CuentaPorCobrar.objects.create(
            cliente=cli_mora,
            empresa=empresa_a,
            monto=Decimal("50.00"),
            fecha_emision=hoy - timedelta(days=10),
            fecha_vencimiento=hoy - timedelta(days=3),
            estado="vencida",
        )
        ped_ovr = Pedido.objects.create(
            id_empresa=empresa_a, id_cliente=cli_mora, numero_pedido="PED-OVR-1", fecha_pedido=hoy
        )
        DetallePedido.objects.create(
            id_pedido=ped_ovr,
            id_producto=prod_a,
            cantidad=Decimal("1"),
            precio_unitario=Decimal("20"),
            subtotal=Decimal("20"),
        )
        r_forbid = client_a.post(
            f"/api/ventas/pedidos/{ped_ovr.id_pedido}/confirmar/",
            {"almacen_id": str(almacen.id_almacen), "omitir_bloqueo_credito": True},
            format="json",
        )
        assert r_forbid.status_code == 403
        assert r_forbid.data["codigo"] == "CREDITO_OVERRIDE_DENEGADO"

        user_a.is_staff = True
        user_a.save(update_fields=["is_staff"])
        r_allow = client_a.post(
            f"/api/ventas/pedidos/{ped_ovr.id_pedido}/confirmar/",
            {"almacen_id": str(almacen.id_almacen), "omitir_bloqueo_credito": True},
            format="json",
        )
        assert r_allow.status_code == 200, r_allow.data

    def test_regresion_revision_pr340(self, client_a, empresa_a, empresa_b, user_a, user_b, moneda_usd):
        from calendar import monthrange
        from datetime import date

        from apps.cuentas_por_cobrar.models import CuentaPorCobrar
        from apps.finanzas.models import TasaCambio, TipoTasaCambio
        from apps.inventario.models import StockActual
        from apps.ventas.models import (
            ComisionVenta,
            DetallePedido,
            EsquemaComision,
            NotaVenta,
            Pedido,
            ReglaPrecioDinamico,
        )
        from apps.ventas.services import (
            confirmar_pedido,
            convertir_pedido_a_nota_venta,
            entregar_nota_venta,
        )
        from apps.ventas.services_precios import calcular_precio_dinamico

        hoy = timezone.localdate()

        # 1. BRECHA_TASA con valor_factor=0 no debe revertir a 100% de la brecha
        moneda_ves = MonedaFactory(codigo_iso="VES", nombre="Bolívar", simbolo="Bs")
        empresa_a.id_moneda_pais = moneda_ves
        empresa_a.save(update_fields=["id_moneda_pais"])
        tipo_bcv = TipoTasaCambio.objects.create(
            id_empresa=empresa_a, codigo="OFICIAL_BCV", nombre="BCV Oficial", es_oficial_fiscal=True
        )
        tipo_par = TipoTasaCambio.objects.create(
            id_empresa=empresa_a, codigo="PARALELO", nombre="Paralelo Mercado", es_oficial_fiscal=False
        )
        TasaCambio.objects.create(
            id_empresa=empresa_a,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_ves,
            tipo_tasa="OFICIAL_BCV",
            id_tipo_tasa=tipo_bcv,
            valor_tasa=Decimal("40.00000000"),
            fecha_tasa=hoy,
        )
        TasaCambio.objects.create(
            id_empresa=empresa_a,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_ves,
            tipo_tasa="PERSONALIZADA",
            id_tipo_tasa=tipo_par,
            valor_tasa=Decimal("50.00000000"),
            fecha_tasa=hoy,
        )
        prod = ProductoFactory(id_empresa=empresa_a, precio_venta_sugerido=Decimal("100.0000"))
        ReglaPrecioDinamico.objects.create(
            id_empresa=empresa_a,
            nombre="Brecha Cero",
            codigo="R-BRECHA-ZERO",
            tipo_factor="BRECHA_CAMBIARIA",
            modo_calculo="BRECHA_TASA",
            valor_factor=Decimal("0"),
        )
        res_zero = calcular_precio_dinamico(prod, empresa_a)
        assert res_zero["precio_final"] == Decimal("100.0000")

        # 2. EsquemaComision a mitad de mes + /avance-meta/?id_empresa= autorizado vs 400 ajeno
        assert (
            client_a.get(
                f"/api/ventas/comisiones/avance-meta/?id_empresa={empresa_b.id_empresa}&vendedor={user_b.pk}"
            ).status_code
            == 400
        )
        dia_mitad = min(15, monthrange(hoy.year, hoy.month)[1])
        fecha_mid = date(hoy.year, hoy.month, dia_mitad)
        esq_mid = EsquemaComision.objects.create(
            id_empresa=empresa_b,
            vendedor=user_b,
            porcentaje_base=Decimal("5.0000"),
            modalidad_devengo="COBRO_EFECTIVO",
            meta_mensual_monto=Decimal("200.0000"),
            vigente_desde=fecha_mid,
        )
        cli_b = ClienteFactory(id_empresa=empresa_b, rif="J-99990000-1")
        nv_b = NotaVenta.objects.create(
            id_empresa=empresa_b,
            id_cliente=cli_b,
            id_vendedor=user_b,
            numero_nota="NV-REG-B1",
            fecha_nota=fecha_mid,
        )
        ComisionVenta.objects.create(
            id_empresa=empresa_b,
            vendedor=user_b,
            nota_venta=nv_b,
            esquema=esq_mid,
            base_comisionable=Decimal("100.0000"),
            monto=Decimal("5.0000"),
            fecha_devengo=fecha_mid,
        )
        user_a.empresas.add(empresa_b)
        r_meta_b = client_a.get(
            f"/api/ventas/comisiones/avance-meta/?id_empresa={empresa_b.id_empresa}&vendedor={user_b.pk}&anio={hoy.year}&mes={hoy.month}"
        )
        assert r_meta_b.status_code == 200, r_meta_b.data
        assert Decimal(r_meta_b.data["meta_mensual_monto"]) == Decimal("200.0000")
        assert Decimal(r_meta_b.data["porcentaje_cumplimiento"]) == Decimal("50.00")

        # 3. confirmar_pedido -> convertir_pedido_a_nota_venta -> entregar_nota_venta actualiza CxC existente + ambito inmutable
        almacen = AlmacenFactory(id_empresa=empresa_a)
        StockActual.objects.create(
            id_empresa=empresa_a, id_producto=prod, id_almacen=almacen, cantidad_disponible=Decimal("20.0000")
        )
        cli_cred = ClienteFactory(
            id_empresa=empresa_a,
            rif="J-88889999-1",
            tipo_cliente="CREDITO",
            limite_credito=Decimal("1000.00"),
        )
        ped = Pedido.objects.create(
            id_empresa=empresa_a, id_cliente=cli_cred, id_vendedor=user_a, numero_pedido="PED-REG-1", fecha_pedido=hoy
        )
        DetallePedido.objects.create(
            id_pedido=ped,
            id_producto=prod,
            cantidad=Decimal("2"),
            precio_unitario=Decimal("50"),
            subtotal=Decimal("100"),
        )
        confirmar_pedido(ped, almacen=almacen, generar_cxc=True, usuario=user_a)
        nv = convertir_pedido_a_nota_venta(ped, usuario=user_a)
        cxc_pre = CuentaPorCobrar.objects.get(empresa=empresa_a, documento_json__id_pedido=str(ped.id_pedido))
        res_ent = entregar_nota_venta(nv, almacen, usuario=user_a)
        cxc_pre.refresh_from_db()
        assert res_ent["cxc"].pk == cxc_pre.pk
        assert cxc_pre.documento_json["id_nota_venta"] == str(nv.id_nota_venta)
        assert cxc_pre.documento_json["ambito"] == "GERENCIAL"

        r_patch_amb = client_a.patch(
            f"/api/ventas/notas-venta/{nv.id_nota_venta}/",
            {"ambito": "FISCAL"},
            format="json",
        )
        assert r_patch_amb.status_code == 400

        # 4. omitir_bloqueo_credito="false" string no activa el 403 de override
        assert not user_a.is_staff
        ped_str = Pedido.objects.create(
            id_empresa=empresa_a, id_cliente=cli_cred, numero_pedido="PED-REG-2", fecha_pedido=hoy
        )
        DetallePedido.objects.create(
            id_pedido=ped_str,
            id_producto=prod,
            cantidad=Decimal("1"),
            precio_unitario=Decimal("25"),
            subtotal=Decimal("25"),
        )
        r_ok_str = client_a.post(
            f"/api/ventas/pedidos/{ped_str.id_pedido}/confirmar/",
            {"almacen_id": str(almacen.id_almacen), "omitir_bloqueo_credito": "false"},
            format="json",
        )
        assert r_ok_str.status_code == 200, r_ok_str.data
