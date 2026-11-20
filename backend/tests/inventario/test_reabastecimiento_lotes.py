"""Tests de Reabastecimiento Automático, Lotes Opt-in (FIFO/FEFO), RLS y MCP (PR-16)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.agentes.reorden import ReordenSugeridorAgent
from apps.almacenes.models import Almacen
from apps.core import rls
from apps.core.mcp_server import _DISCOVERED_TOOLS as CORE_MCP_TOOLS
from apps.core.models import CapabilityToken, Empresa
from apps.inventario.mcp import (
    MCP_TOOLS as INVENTARIO_MCP_TOOLS,
    inventario_consultar_lotes,
    inventario_evaluar_reabastecimiento,
)
from apps.inventario.models import (
    LoteProducto,
    MovimientoInventario,
    MovimientoLote,
    OperacionInventario,
    PasoOperacion,
    Producto,
    ReglaReabastecimiento,
    StockActual,
    VarianteProducto,
)
from apps.inventario.services import (
    MovimientoInvalidoError,
    StockInsuficienteError,
    registrar_movimiento,
)
from apps.inventario.services_reabastecimiento import (
    ReabastecimientoError,
    evaluar_reabastecimiento,
    generar_borrador_reabastecimiento,
)
from apps.manufactura.models import ListaMateriales, OrdenProduccion
from apps.proveedores.models import Proveedor
from tests.factories import (
    AlmacenFactory,
    CategoriaProductoFactory,
    EmpresaFactory,
    ProductoFactory,
    UnidadMedidaFactory,
    UsuariosFactory,
)

pytestmark = pytest.mark.django_db


def _assert_no_floats(payload):
    if isinstance(payload, dict):
        for val in payload.values():
            _assert_no_floats(val)
    elif isinstance(payload, list):
        for item in payload:
            _assert_no_floats(item)
    else:
        assert not isinstance(payload, float), f"Float prohibido en respuesta: {payload!r}"


def _token(empresa, scopes: list[str]) -> str:
    tok = CapabilityToken.objects.create(empresa=empresa, nombre="tok-inv-b4", scopes=scopes)
    return str(tok.token)


@pytest.fixture
def setup_inv_a(db, empresa_a, user_a, moneda_usd):
    unidad = UnidadMedidaFactory(id_empresa=empresa_a, nombre="Unidad", abreviatura="UND")
    categoria = CategoriaProductoFactory(id_empresa=empresa_a, nombre_categoria="General")
    prod_compra = ProductoFactory(
        id_empresa=empresa_a,
        nombre_producto="Filtro Aceite",
        sku="FIL-001",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        costo_promedio=Decimal("12.50"),
        es_comprable=True,
        es_vendible=True,
        maneja_lotes=False,
    )
    prod_lote_fifo = ProductoFactory(
        id_empresa=empresa_a,
        nombre_producto="Resina FIFO",
        sku="RES-FIFO",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        costo_promedio=Decimal("20.00"),
        maneja_lotes=True,
        estrategia_salida="FIFO",
    )
    prod_lote_fefo = ProductoFactory(
        id_empresa=empresa_a,
        nombre_producto="Reactivo FEFO",
        sku="REA-FEFO",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        costo_promedio=Decimal("30.00"),
        maneja_lotes=True,
        estrategia_salida="FEFO",
    )
    alm_principal = AlmacenFactory(id_empresa=empresa_a, nombre_almacen="Principal", codigo_almacen="ALM-P")
    alm_secundario = AlmacenFactory(id_empresa=empresa_a, nombre_almacen="Secundario", codigo_almacen="ALM-S")
    proveedor = Proveedor.objects.create(
        id_empresa=empresa_a,
        razon_social="Proveedor Alfa C.A.",
        rif="J-10020030-1",
    )
    return SimpleNamespace(
        empresa=empresa_a,
        user=user_a,
        unidad=unidad,
        categoria=categoria,
        prod_compra=prod_compra,
        prod_lote_fifo=prod_lote_fifo,
        prod_lote_fefo=prod_lote_fefo,
        alm_principal=alm_principal,
        alm_secundario=alm_secundario,
        proveedor=proveedor,
    )


class TestEvaluarYGenerarReabastecimiento:
    def test_evaluar_reabastecimiento_calcula_stock_proyectado_y_multiplo(self, setup_inv_a):
        s = setup_inv_a
        StockActual.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_compra,
            id_almacen=s.alm_principal,
            cantidad_disponible=Decimal("10.0000"),
            cantidad_comprometida=Decimal("4.0000"),
            cantidad_en_transito=Decimal("1.0000"),
        )
        # stock_libre = 6, stock_proyectado = 7 <= min 10 -> deficit = 23 - 7? max=20 -> deficit=13 -> ceil(13/5)*5 = 15
        regla = ReglaReabastecimiento.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_compra,
            id_almacen=s.alm_principal,
            stock_minimo=Decimal("10.0000"),
            stock_maximo=Decimal("20.0000"),
            cantidad_multiplo=Decimal("5.0000"),
            ruta="COMPRA",
            id_proveedor_preferido=s.proveedor,
        )
        # Regla OK en almacén secundario (sin stock actual -> 0, min 0? min 0 max 0 no requiere si no? Wait: 0 <= 0!)
        # Ponemos stock suficiente en secundario para probar incluir_ok
        StockActual.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_lote_fifo,
            id_almacen=s.alm_secundario,
            cantidad_disponible=Decimal("50.0000"),
        )
        ReglaReabastecimiento.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_lote_fifo,
            id_almacen=s.alm_secundario,
            stock_minimo=Decimal("10.0000"),
            stock_maximo=Decimal("40.0000"),
            cantidad_multiplo=Decimal("1.0000"),
            ruta="COMPRA",
        )

        solo_req = evaluar_reabastecimiento(s.empresa, incluir_ok=False)
        assert len(solo_req) == 1
        item = solo_req[0]
        assert item["id_regla"] == str(regla.id_regla)
        assert item["stock_libre"] == Decimal("6.0000")
        assert item["stock_proyectado"] == Decimal("7.0000")
        assert item["deficit"] == Decimal("13.0000")
        assert item["cantidad_sugerida"] == Decimal("15.0000")
        assert item["requiere_reabastecimiento"] is True

        todos = evaluar_reabastecimiento(s.empresa, incluir_ok=True)
        assert len(todos) == 2
        ok_item = next(r for r in todos if r["id_producto"] == str(s.prod_lote_fifo.id_producto))
        assert ok_item["requiere_reabastecimiento"] is False
        assert ok_item["cantidad_sugerida"] == Decimal("0.0000")

        filtrado_alm = evaluar_reabastecimiento(s.empresa, almacen=s.alm_secundario, incluir_ok=True)
        assert len(filtrado_alm) == 1
        assert filtrado_alm[0]["id_almacen"] == str(s.alm_secundario.id_almacen)

    def test_evaluar_sin_stock_actual_y_con_variante(self, setup_inv_a):
        s = setup_inv_a
        var = VarianteProducto.objects.create(
            id_producto=s.prod_compra,
            codigo_variante="ROJO",
            sku="FIL-001-ROJO",
        )
        ReglaReabastecimiento.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_compra,
            id_variante=var,
            id_almacen=s.alm_principal,
            stock_minimo=Decimal("5.0000"),
            stock_maximo=Decimal("12.0000"),
            cantidad_multiplo=Decimal("1.0000"),
            ruta="COMPRA",
        )
        res = evaluar_reabastecimiento(s.empresa)
        assert len(res) == 1
        assert res[0]["id_variante"] == str(var.id_variante)
        assert res[0]["stock_proyectado"] == Decimal("0.0000")
        assert res[0]["cantidad_sugerida"] == Decimal("12.0000")

    def test_generar_borrador_compra(self, setup_inv_a):
        s = setup_inv_a
        regla = ReglaReabastecimiento.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_compra,
            id_almacen=s.alm_principal,
            stock_minimo=Decimal("5.0000"),
            stock_maximo=Decimal("20.0000"),
            cantidad_multiplo=Decimal("5.0000"),
            ruta="COMPRA",
            id_proveedor_preferido=s.proveedor,
        )
        res = generar_borrador_reabastecimiento(regla, usuario=s.user)
        assert res["ruta"] == "COMPRA"
        assert res["tipo_documento"] == "RequisicionCompra"
        assert res["estado"] == "BORRADOR"
        assert res["cantidad"] == "20.0000"

        # Producto no comprable falla
        s.prod_compra.es_comprable = False
        s.prod_compra.save(update_fields=["es_comprable"])
        with pytest.raises(ReabastecimientoError, match="es_comprable=False"):
            generar_borrador_reabastecimiento(regla, usuario=s.user, cantidad=Decimal("5"))

    def test_generar_borrador_manufactura_con_y_sin_bom(self, setup_inv_a):
        s = setup_inv_a
        regla = ReglaReabastecimiento.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_compra,
            id_almacen=s.alm_principal,
            stock_minimo=Decimal("4.0000"),
            stock_maximo=Decimal("10.0000"),
            cantidad_multiplo=Decimal("2.0000"),
            ruta="MANUFACTURA",
        )
        res_sin_bom = generar_borrador_reabastecimiento(regla, usuario=s.user)
        assert res_sin_bom["ruta"] == "MANUFACTURA"
        assert res_sin_bom["tipo_documento"] == "OrdenProduccion"
        assert res_sin_bom["estado"] == "pendiente"
        assert res_sin_bom["lista_materiales_id"] is None

        bom = ListaMateriales.objects.create(
            empresa=s.empresa,
            producto_final=s.prod_compra,
            nombre="BOM Filtro",
        )
        res_con_bom = generar_borrador_reabastecimiento(
            regla,
            usuario=s.user,
            cantidad=Decimal("8.0000"),
            fecha_necesidad=date.today() + timedelta(days=5),
        )
        assert res_con_bom["lista_materiales_id"] == str(bom.pk)
        op = OrdenProduccion.objects.get(pk=res_con_bom["id_documento"])
        assert op.cantidad == Decimal("8.00")
        assert op.lista_materiales_id == bom.pk

    def test_generar_borrador_transferencia_con_y_sin_pasos(self, setup_inv_a):
        s = setup_inv_a
        regla = ReglaReabastecimiento.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_compra,
            id_almacen=s.alm_principal,
            stock_minimo=Decimal("5.0000"),
            stock_maximo=Decimal("15.0000"),
            cantidad_multiplo=Decimal("5.0000"),
            ruta="TRANSFERENCIA",
            id_almacen_origen=s.alm_secundario,
        )
        # Sin pasos configurados -> crea OperacionInventario EN_PROCESO
        res_sin_paso = generar_borrador_reabastecimiento(regla, usuario=s.user)
        assert res_sin_paso["ruta"] == "TRANSFERENCIA"
        assert res_sin_paso["tipo_documento"] == "OperacionInventario"
        assert res_sin_paso["estado"] == "EN_PROCESO"
        op_sin = OperacionInventario.objects.get(pk=res_sin_paso["id_documento"])
        assert op_sin.id_almacen_id == s.alm_secundario.id_almacen
        assert op_sin.id_almacen_contraparte_id == s.alm_principal.id_almacen
        assert op_sin.lineas.count() == 1

        # Con PasoOperacion activo -> usa operaciones.crear_operacion -> crea pasos (estado EN_PROCESO)
        PasoOperacion.objects.create(
            id_empresa=s.empresa,
            id_almacen=s.alm_secundario,
            tipo_operacion="ENTREGA",
            nombre_paso="Picking",
            secuencia=1,
        )
        res_con_paso = generar_borrador_reabastecimiento(regla, usuario=s.user, cantidad=Decimal("10"))
        assert res_con_paso["estado"] == "EN_PROCESO"
        op_con = OperacionInventario.objects.get(pk=res_con_paso["id_documento"])
        assert op_con.pasos.count() == 1

    def test_generar_borrador_errores_validacion(self, setup_inv_a):
        s = setup_inv_a
        StockActual.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_compra,
            id_almacen=s.alm_principal,
            cantidad_disponible=Decimal("100.0000"),
        )
        regla = ReglaReabastecimiento.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_compra,
            id_almacen=s.alm_principal,
            stock_minimo=Decimal("5.0000"),
            stock_maximo=Decimal("20.0000"),
            cantidad_multiplo=Decimal("1.0000"),
            ruta="COMPRA",
        )
        with pytest.raises(ReabastecimientoError, match="no presenta déficit de stock"):
            generar_borrador_reabastecimiento(regla, usuario=s.user)
        with pytest.raises(ReabastecimientoError, match="mayor a cero"):
            generar_borrador_reabastecimiento(regla, usuario=s.user, cantidad=Decimal("0"))

        regla_transf_mala = ReglaReabastecimiento.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_lote_fifo,
            id_almacen=s.alm_principal,
            stock_minimo=Decimal("5.0000"),
            stock_maximo=Decimal("10.0000"),
            ruta="TRANSFERENCIA",
            id_almacen_origen=s.alm_principal,
        )
        with pytest.raises(ReabastecimientoError, match="deben ser distintos"):
            generar_borrador_reabastecimiento(regla_transf_mala, usuario=s.user, cantidad=Decimal("5"))

        regla.activo = False
        regla.save(update_fields=["activo"])
        with pytest.raises(ReabastecimientoError, match="está inactiva"):
            generar_borrador_reabastecimiento(regla, usuario=s.user, cantidad=Decimal("5"))


class TestAgenteReordenConReglas:
    def test_reorden_usa_regla_reabastecimiento_si_existe_y_fallback_stock_actual(self, setup_inv_a):
        s = setup_inv_a
        # Consumo reciente de 30 uds en 30 días -> consumo_diario = 1.0 para que aplique stock_maximo
        MovimientoInventario.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_compra,
            id_almacen_origen=s.alm_principal,
            tipo_movimiento="SALIDA",
            cantidad=Decimal("30.0000"),
            fecha_hora_movimiento=timezone.now() - timedelta(days=3),
            id_usuario_registro=s.user,
        )
        MovimientoInventario.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_lote_fifo,
            id_almacen_origen=s.alm_secundario,
            tipo_movimiento="SALIDA",
            cantidad=Decimal("30.0000"),
            fecha_hora_movimiento=timezone.now() - timedelta(days=3),
            id_usuario_registro=s.user,
        )
        # StockActual con min=2, max=5, pero la regla fija min=10, max=25!
        StockActual.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_compra,
            id_almacen=s.alm_principal,
            cantidad_disponible=Decimal("8.0000"),
            cantidad_minima=Decimal("2.0000"),
            cantidad_maxima=Decimal("5.0000"),
        )
        ReglaReabastecimiento.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_compra,
            id_almacen=s.alm_principal,
            stock_minimo=Decimal("10.0000"),
            stock_maximo=Decimal("25.0000"),
            cantidad_multiplo=Decimal("1.0000"),
            ruta="COMPRA",
        )
        # Otro stock sin regla: conserva StockActual.cantidad_minima = 15, max = 30
        StockActual.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_lote_fifo,
            id_almacen=s.alm_secundario,
            cantidad_disponible=Decimal("12.0000"),
            cantidad_minima=Decimal("15.0000"),
            cantidad_maxima=Decimal("30.0000"),
        )

        agente = ReordenSugeridorAgent(empresa=s.empresa)
        sugerencias = agente.analizar(persistir=False)
        por_prod = {sug.producto_id: sug for sug in sugerencias}

        sug_regla = por_prod[str(s.prod_compra.id_producto)]
        assert sug_regla.cantidad_minima == Decimal("10.0000")
        assert sug_regla.cantidad_sugerida_reorden == Decimal("17.00")  # min(30-8, 25-8)

        sug_legacy = por_prod[str(s.prod_lote_fifo.id_producto)]
        assert sug_legacy.cantidad_minima == Decimal("15.0000")
        assert sug_legacy.cantidad_sugerida_reorden == Decimal("18.00")  # min(30-12, 30-12)

    def test_reorden_llm_path_aplica_regla(self, setup_inv_a):
        import json

        s = setup_inv_a
        StockActual.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_compra,
            id_almacen=s.alm_principal,
            cantidad_disponible=Decimal("6.0000"),
            cantidad_minima=Decimal("1.0000"),
            cantidad_maxima=Decimal("5.0000"),
        )
        ReglaReabastecimiento.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_compra,
            id_almacen=s.alm_principal,
            stock_minimo=Decimal("12.0000"),
            stock_maximo=Decimal("30.0000"),
            ruta="COMPRA",
        )

        class _FakeGateway:
            def disponible(self):
                return True

            def generate(self, *, prompt, system, max_tokens, uso, empresa):
                assert "Stock mínimo: 12.0000" in prompt
                return SimpleNamespace(
                    text=json.dumps(
                        {
                            "estado": "REORDENAR",
                            "cantidad_sugerida_reorden": "24.00",
                            "razonamiento": "Bajo el mínimo de la regla",
                        }
                    ),
                    model="claude-test",
                )

        agente = ReordenSugeridorAgent(empresa=s.empresa, gateway=_FakeGateway())
        sugerencias = agente.analizar(persistir=False)
        assert len(sugerencias) == 1
        assert sugerencias[0].cantidad_minima == Decimal("12.0000")
        assert sugerencias[0].estado == "REORDENAR"
        assert sugerencias[0].cantidad_sugerida_reorden == Decimal("24.00")
        assert sugerencias[0].modelo_llm == "claude-test"


class TestLotesOptInFIFOYFEFO:
    def test_producto_sin_lotes_no_toca_lote_producto(self, setup_inv_a):
        s = setup_inv_a
        now = timezone.now()
        registrar_movimiento(
            empresa=s.empresa,
            fecha_hora_movimiento=now,
            tipo_movimiento="ENTRADA",
            producto=s.prod_compra,
            cantidad=Decimal("10.0000"),
            almacen_destino=s.alm_principal,
            costo_unitario=Decimal("12.50"),
            usuario=s.user,
        )
        assert LoteProducto.objects.filter(id_producto=s.prod_compra).count() == 0

    def test_entrada_con_maneja_lotes_requiere_lote_y_completa_fechas(self, setup_inv_a):
        s = setup_inv_a
        now = timezone.now()
        with pytest.raises(MovimientoInvalidoError, match="debe especificar 'lote'"):
            registrar_movimiento(
                empresa=s.empresa,
                fecha_hora_movimiento=now,
                tipo_movimiento="ENTRADA",
                producto=s.prod_lote_fifo,
                cantidad=Decimal("5"),
                almacen_destino=s.alm_principal,
                costo_unitario=Decimal("20.00"),
                usuario=s.user,
            )

        mov1 = registrar_movimiento(
            empresa=s.empresa,
            fecha_hora_movimiento=now,
            tipo_movimiento="ENTRADA",
            producto=s.prod_lote_fifo,
            cantidad=Decimal("5.0000"),
            almacen_destino=s.alm_principal,
            costo_unitario=Decimal("20.00"),
            usuario=s.user,
            lote="LOTE-A",
        )
        assert mov1.id_lote is not None
        assert mov1.id_lote.cantidad_disponible == Decimal("5.0000")

        # Segunda entrada al mismo lote con fechas vacía -> actualiza fechas si estaban null
        f_fab = date.today() - timedelta(days=2)
        f_ven = date.today() + timedelta(days=90)
        mov2 = registrar_movimiento(
            empresa=s.empresa,
            fecha_hora_movimiento=now + timedelta(minutes=1),
            tipo_movimiento="ENTRADA",
            producto=s.prod_lote_fifo,
            cantidad=Decimal("3.0000"),
            almacen_destino=s.alm_principal,
            costo_unitario=Decimal("20.00"),
            usuario=s.user,
            lote="LOTE-A",
            fecha_fabricacion=f_fab,
            fecha_vencimiento=f_ven,
        )
        lote = mov2.id_lote
        lote.refresh_from_db()
        assert lote.cantidad_disponible == Decimal("8.0000")
        assert lote.fecha_fabricacion == f_fab
        assert lote.fecha_vencimiento == f_ven

    def test_salida_automatica_fifo_descarga_multiples_lotes_y_registra_trazabilidad(self, setup_inv_a):
        s = setup_inv_a
        t0 = timezone.now()
        m_a = registrar_movimiento(
            empresa=s.empresa,
            fecha_hora_movimiento=t0,
            tipo_movimiento="ENTRADA",
            producto=s.prod_lote_fifo,
            cantidad=Decimal("4.0000"),
            almacen_destino=s.alm_principal,
            costo_unitario=Decimal("20.00"),
            usuario=s.user,
            lote="FIFO-1",
            fecha_vencimiento=date.today() + timedelta(days=200),
        )
        m_b = registrar_movimiento(
            empresa=s.empresa,
            fecha_hora_movimiento=t0 + timedelta(minutes=1),
            tipo_movimiento="ENTRADA",
            producto=s.prod_lote_fifo,
            cantidad=Decimal("6.0000"),
            almacen_destino=s.alm_principal,
            costo_unitario=Decimal("20.00"),
            usuario=s.user,
            lote="FIFO-2",
            fecha_vencimiento=date.today() + timedelta(days=30),
        )

        mov_salida = registrar_movimiento(
            empresa=s.empresa,
            fecha_hora_movimiento=t0 + timedelta(minutes=5),
            tipo_movimiento="SALIDA",
            producto=s.prod_lote_fifo,
            cantidad=Decimal("7.0000"),
            almacen_origen=s.alm_principal,
            usuario=s.user,
        )
        lote_1 = m_a.id_lote
        lote_2 = m_b.id_lote
        lote_1.refresh_from_db()
        lote_2.refresh_from_db()
        # FIFO: primero FIFO-1 (4), luego 3 de FIFO-2
        assert lote_1.cantidad_disponible == Decimal("0.0000")
        assert lote_2.cantidad_disponible == Decimal("3.0000")
        assert mov_salida.id_lote_id == lote_1.id_lote

        trazas = list(MovimientoLote.objects.filter(id_movimiento=mov_salida).order_by("-cantidad"))
        assert [(t.id_lote_id, t.cantidad) for t in trazas] == [
            (lote_1.id_lote, Decimal("4.0000")),
            (lote_2.id_lote, Decimal("3.0000")),
        ]

    def test_salida_automatica_fefo_prioriza_fecha_vencimiento(self, setup_inv_a):
        s = setup_inv_a
        t0 = timezone.now()
        # Lote 1 vence más tarde, Lote 2 vence antes, Lote 3 sin vencimiento
        l_lejos = registrar_movimiento(
            empresa=s.empresa,
            fecha_hora_movimiento=t0,
            tipo_movimiento="ENTRADA",
            producto=s.prod_lote_fefo,
            cantidad=Decimal("5.0000"),
            almacen_destino=s.alm_principal,
            costo_unitario=Decimal("30.00"),
            usuario=s.user,
            lote="FEFO-LEJOS",
            fecha_vencimiento=date.today() + timedelta(days=120),
        ).id_lote
        l_cerca = registrar_movimiento(
            empresa=s.empresa,
            fecha_hora_movimiento=t0 + timedelta(minutes=1),
            tipo_movimiento="ENTRADA",
            producto=s.prod_lote_fefo,
            cantidad=Decimal("4.0000"),
            almacen_destino=s.alm_principal,
            costo_unitario=Decimal("30.00"),
            usuario=s.user,
            lote="FEFO-CERCA",
            fecha_vencimiento=date.today() + timedelta(days=10),
        ).id_lote
        l_sin_v = registrar_movimiento(
            empresa=s.empresa,
            fecha_hora_movimiento=t0 + timedelta(minutes=2),
            tipo_movimiento="ENTRADA",
            producto=s.prod_lote_fefo,
            cantidad=Decimal("3.0000"),
            almacen_destino=s.alm_principal,
            costo_unitario=Decimal("30.00"),
            usuario=s.user,
            lote="FEFO-SIN",
        ).id_lote

        mov_sal = registrar_movimiento(
            empresa=s.empresa,
            fecha_hora_movimiento=t0 + timedelta(minutes=3),
            tipo_movimiento="SALIDA",
            producto=s.prod_lote_fefo,
            cantidad=Decimal("6.0000"),
            almacen_origen=s.alm_principal,
            usuario=s.user,
        )
        l_cerca.refresh_from_db()
        l_lejos.refresh_from_db()
        l_sin_v.refresh_from_db()
        assert l_cerca.cantidad_disponible == Decimal("0.0000")
        assert l_lejos.cantidad_disponible == Decimal("3.0000")
        assert l_sin_v.cantidad_disponible == Decimal("3.0000")
        assert mov_sal.id_lote_id == l_cerca.id_lote

    def test_transferencia_entre_almacenes_propaga_lotes_y_respeta_stock_insuficiente(self, setup_inv_a):
        s = setup_inv_a
        t0 = timezone.now()
        f_ven = date.today() + timedelta(days=25)
        registrar_movimiento(
            empresa=s.empresa,
            fecha_hora_movimiento=t0,
            tipo_movimiento="ENTRADA",
            producto=s.prod_lote_fefo,
            cantidad=Decimal("10.0000"),
            almacen_destino=s.alm_principal,
            costo_unitario=Decimal("30.00"),
            usuario=s.user,
            lote="TR-001",
            fecha_vencimiento=f_ven,
        )
        mov_tr = registrar_movimiento(
            empresa=s.empresa,
            fecha_hora_movimiento=t0 + timedelta(minutes=1),
            tipo_movimiento="TRANSFERENCIA",
            producto=s.prod_lote_fefo,
            cantidad=Decimal("4.0000"),
            almacen_origen=s.alm_principal,
            almacen_destino=s.alm_secundario,
            usuario=s.user,
            lote="TR-001",
        )
        assert mov_tr.id_lote is not None
        lote_orig = LoteProducto.objects.get(id_almacen=s.alm_principal, numero_lote="TR-001")
        lote_dest = LoteProducto.objects.get(id_almacen=s.alm_secundario, numero_lote="TR-001")
        assert lote_orig.cantidad_disponible == Decimal("6.0000")
        assert lote_dest.cantidad_disponible == Decimal("4.0000")
        assert lote_dest.fecha_vencimiento == f_ven

        # Agregamos un segundo lote de 5 uds -> StockActual=11, lote TR-001=6
        registrar_movimiento(
            empresa=s.empresa,
            fecha_hora_movimiento=t0 + timedelta(minutes=2),
            tipo_movimiento="ENTRADA",
            producto=s.prod_lote_fefo,
            cantidad=Decimal("5.0000"),
            almacen_destino=s.alm_principal,
            costo_unitario=Decimal("30.00"),
            usuario=s.user,
            lote="TR-002",
        )
        # Salida de 8 uds pidiendo explícitamente lote TR-001 (solo tiene 6) falla en _descontar_lotes
        with pytest.raises(StockInsuficienteError, match="Stock insuficiente en lote"):
            registrar_movimiento(
                empresa=s.empresa,
                fecha_hora_movimiento=t0 + timedelta(minutes=3),
                tipo_movimiento="SALIDA",
                producto=s.prod_lote_fefo,
                cantidad=Decimal("8.0000"),
                almacen_origen=s.alm_principal,
                usuario=s.user,
                lote=lote_orig,
            )

        # Con permitir_negativo=True respeta CHECK >= 0 en BD (queda en 0)
        registrar_movimiento(
            empresa=s.empresa,
            fecha_hora_movimiento=t0 + timedelta(minutes=4),
            tipo_movimiento="SALIDA",
            producto=s.prod_lote_fefo,
            cantidad=Decimal("8.0000"),
            almacen_origen=s.alm_principal,
            usuario=s.user,
            lote="TR-001",
            permitir_negativo=True,
        )
        lote_orig.refresh_from_db()
        assert lote_orig.cantidad_disponible == Decimal("0.0000")


class TestAPIRestReabastecimientoYLotes:
    def test_crud_regla_reabastecimiento_evaluar_y_generar_borrador(self, client_a, setup_inv_a):
        s = setup_inv_a
        base = "/api/inventario/reglas-reabastecimiento/"

        # Producto patch estrategia_salida FEFO
        r_prod = client_a.patch(
            f"/api/inventario/productos/{s.prod_lote_fifo.id_producto}/",
            {"estrategia_salida": "FEFO"},
            format="json",
        )
        assert r_prod.status_code == 200, r_prod.content
        assert r_prod.json()["estrategia_salida"] == "FEFO"

        # Validaciones en regla
        r_bad = client_a.post(
            base,
            {
                "id_producto": str(s.prod_compra.id_producto),
                "id_almacen": str(s.alm_principal.id_almacen),
                "stock_minimo": "20.0000",
                "stock_maximo": "10.0000",
                "cantidad_multiplo": "1.0000",
                "ruta": "COMPRA",
            },
            format="json",
        )
        assert r_bad.status_code == 400

        r_bad_tr = client_a.post(
            base,
            {
                "id_producto": str(s.prod_compra.id_producto),
                "id_almacen": str(s.alm_principal.id_almacen),
                "stock_minimo": "5.0000",
                "stock_maximo": "15.0000",
                "cantidad_multiplo": "1.0000",
                "ruta": "TRANSFERENCIA",
            },
            format="json",
        )
        assert r_bad_tr.status_code == 400

        # Crear regla válida sin variante
        r_ok = client_a.post(
            base,
            {
                "id_producto": str(s.prod_compra.id_producto),
                "id_almacen": str(s.alm_principal.id_almacen),
                "stock_minimo": "5.0000",
                "stock_maximo": "20.0000",
                "cantidad_multiplo": "5.0000",
                "ruta": "COMPRA",
                "id_proveedor_preferido": str(s.proveedor.id_proveedor),
            },
            format="json",
        )
        assert r_ok.status_code == 201, r_ok.content
        regla_id = r_ok.json()["id_regla"]

        # Duplicado sin variante debe fallar 400
        r_dup = client_a.post(
            base,
            {
                "id_producto": str(s.prod_compra.id_producto),
                "id_almacen": str(s.alm_principal.id_almacen),
                "stock_minimo": "1.0000",
                "stock_maximo": "10.0000",
                "cantidad_multiplo": "1.0000",
                "ruta": "COMPRA",
            },
            format="json",
        )
        assert r_dup.status_code == 400

        # PATCH sobre la misma regla debe funcionar sin chocar con unique constraint
        r_patch = client_a.patch(f"{base}{regla_id}/", {"stock_maximo": "25.0000"}, format="json")
        assert r_patch.status_code == 200, r_patch.content

        # Evaluar y generar borrador via API
        r_eval = client_a.post(f"{base}evaluar/", {"incluir_ok": True}, format="json")
        assert r_eval.status_code == 200, r_eval.content
        assert len(r_eval.json()["resultados"]) == 1
        assert r_eval.json()["resultados"][0]["cantidad_sugerida"] == "25.0000"

        r_gen = client_a.post(f"{base}{regla_id}/generar-borrador/", {}, format="json")
        assert r_gen.status_code == 201, r_gen.content
        assert r_gen.json()["tipo_documento"] == "RequisicionCompra"
        assert r_gen.json()["estado"] == "BORRADOR"

    def test_api_lotes_filtros_movimiento_y_nul_guard(self, client_a, setup_inv_a):
        s = setup_inv_a
        base_lotes = "/api/inventario/lotes-producto/"

        # Movimiento ENTRADA creando lote por API
        r_mov = client_a.post(
            "/api/inventario/movimientos-inventario/",
            {
                "id_empresa": str(s.empresa.id_empresa),
                "id_producto": str(s.prod_lote_fefo.id_producto),
                "id_almacen_destino": str(s.alm_principal.id_almacen),
                "tipo_movimiento": "ENTRADA",
                "cantidad": "10.0000",
                "costo_unitario_movimiento": "30.00",
                "fecha_hora_movimiento": timezone.now().isoformat(),
                "numero_lote": "API-LOTE-1",
                "fecha_vencimiento": (date.today() + timedelta(days=15)).isoformat(),
            },
            format="json",
        )
        assert r_mov.status_code == 201, r_mov.content
        assert r_mov.json()["lote_numero"] == "API-LOTE-1"
        lote_id = r_mov.json()["id_lote"]

        # Lote lejano (120 días) con stock 0 después o directo vía API POST
        r_lote2 = client_a.post(
            base_lotes,
            {
                "id_producto": str(s.prod_lote_fefo.id_producto),
                "id_almacen": str(s.alm_secundario.id_almacen),
                "numero_lote": "API-LOTE-2",
                "fecha_vencimiento": (date.today() + timedelta(days=120)).isoformat(),
                "cantidad_disponible": "0.0000",
            },
            format="json",
        )
        assert r_lote2.status_code == 201, r_lote2.content

        # Filtrar por_vencer_dias=30 & solo_con_stock=true
        r_list = client_a.get(
            f"{base_lotes}?almacen={s.alm_principal.id_almacen}&producto={s.prod_lote_fefo.id_producto}&por_vencer_dias=30&solo_con_stock=true"
        )
        assert r_list.status_code == 200
        rows = r_list.json()["results"] if "results" in r_list.json() else r_list.json()
        assert [row["id_lote"] for row in rows] == [lote_id]

        # por_vencer_dias inválido -> 400; NUL -> 400
        assert client_a.get(f"{base_lotes}?por_vencer_dias=abc").status_code == 400
        assert client_a.get(f"{base_lotes}?por_vencer_dias=-5").status_code == 400
        assert client_a.get("/api/inventario/lotes-producto/?search=abc%00").status_code == 400
        assert client_a.get("/api/inventario/reglas-reabastecimiento/?search=abc%00").status_code == 400


@pytest.mark.tenant
class TestAislamientoRLSMatrizYMCPInventarioB4:
    def test_idor_cross_tenant_y_matriz_subsidiaria(self, client_a, client_b, setup_inv_a, empresa_b, user_a):
        s = setup_inv_a
        regla_a = ReglaReabastecimiento.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_compra,
            id_almacen=s.alm_principal,
            stock_minimo=Decimal("5"),
            stock_maximo=Decimal("10"),
            ruta="COMPRA",
        )
        lote_a = LoteProducto.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_lote_fifo,
            id_almacen=s.alm_principal,
            numero_lote="TEN-A-01",
            cantidad_disponible=Decimal("4"),
        )

        # Tenant B recibe 404 en retrieve/patch/delete/generar-borrador y vacío en list/evaluar
        assert client_b.get(f"/api/inventario/reglas-reabastecimiento/{regla_a.pk}/").status_code == 404
        assert (
            client_b.post(f"/api/inventario/reglas-reabastecimiento/{regla_a.pk}/generar-borrador/", {}).status_code
            == 404
        )
        assert client_b.get(f"/api/inventario/lotes-producto/{lote_a.pk}/").status_code == 404
        assert client_b.patch(f"/api/inventario/lotes-producto/{lote_a.pk}/", {"numero_lote": "X"}).status_code == 404

        r_eval_b = client_b.post(
            "/api/inventario/reglas-reabastecimiento/evaluar/", {"incluir_ok": True}, format="json"
        )
        assert r_eval_b.status_code == 200
        assert r_eval_b.json()["resultados"] == []

        # Crear regla apuntando a producto de otra empresa -> 400
        r_cross = client_b.post(
            "/api/inventario/reglas-reabastecimiento/",
            {
                "id_producto": str(s.prod_compra.id_producto),
                "id_almacen": str(s.alm_principal.id_almacen),
                "stock_minimo": "1",
                "stock_maximo": "5",
                "ruta": "COMPRA",
            },
            format="json",
        )
        assert r_cross.status_code == 400

        # Matriz-Subsidiaria: usuario en matriz + subsidiaria intentando mezclar FK entre ambas -> 400
        sub = EmpresaFactory(empresa_matriz=s.empresa)
        alm_sub = AlmacenFactory(id_empresa=sub)
        user_a.empresas.add(sub)
        r_mix = client_a.post(
            "/api/inventario/reglas-reabastecimiento/",
            {
                "id_producto": str(s.prod_compra.id_producto),
                "id_almacen": str(alm_sub.id_almacen),
                "stock_minimo": "1",
                "stock_maximo": "5",
                "ruta": "COMPRA",
            },
            format="json",
        )
        assert r_mix.status_code == 400

    def test_rls_postgresql_en_reglas_y_lotes(self, rls_test_role, setup_inv_a, empresa_b, moneda_usd):
        s = setup_inv_a
        regla_a = ReglaReabastecimiento.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_compra,
            id_almacen=s.alm_principal,
            stock_minimo=Decimal("5"),
            stock_maximo=Decimal("10"),
        )
        lote_a = LoteProducto.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_lote_fifo,
            id_almacen=s.alm_principal,
            numero_lote="RLS-A",
            cantidad_disponible=Decimal("2"),
        )
        u_b = UnidadMedidaFactory(id_empresa=empresa_b)
        c_b = CategoriaProductoFactory(id_empresa=empresa_b)
        p_b = ProductoFactory(
            id_empresa=empresa_b,
            id_unidad_medida_base=u_b,
            id_categoria=c_b,
            id_moneda_precio=moneda_usd,
        )
        a_b = AlmacenFactory(id_empresa=empresa_b)
        regla_b = ReglaReabastecimiento.objects.create(
            id_empresa=empresa_b,
            id_producto=p_b,
            id_almacen=a_b,
            stock_minimo=Decimal("5"),
            stock_maximo=Decimal("10"),
        )
        lote_b = LoteProducto.objects.create(
            id_empresa=empresa_b,
            id_producto=p_b,
            id_almacen=a_b,
            numero_lote="RLS-B",
            cantidad_disponible=Decimal("3"),
        )

        with connection.cursor() as cur:
            if rls_test_role is not None:
                cur.execute(f'SET ROLE "{rls_test_role}"')
            try:
                rls.apply_context([s.empresa.id_empresa], bypass=False)
                assert list(ReglaReabastecimiento.objects.values_list("pk", flat=True)) == [regla_a.pk]
                assert list(LoteProducto.objects.values_list("pk", flat=True)) == [lote_a.pk]

                rls.apply_context([empresa_b.id_empresa], bypass=False)
                assert list(ReglaReabastecimiento.objects.values_list("pk", flat=True)) == [regla_b.pk]
                assert list(LoteProducto.objects.values_list("pk", flat=True)) == [lote_b.pk]

                rls.apply_context([], bypass=False)
                assert ReglaReabastecimiento.objects.count() == 0
                assert LoteProducto.objects.count() == 0
            finally:
                rls.apply_system_default()
                if rls_test_role is not None:
                    cur.execute("RESET ROLE")

    def test_mcp_tools_registradas_scopes_rls_y_decimal_sin_floats(self, setup_inv_a, empresa_b):
        s = setup_inv_a
        nombres = {t["name"] for t in INVENTARIO_MCP_TOOLS}
        assert {"inventario_evaluar_reabastecimiento", "inventario_consultar_lotes"}.issubset(nombres)
        assert {"inventario_evaluar_reabastecimiento", "inventario_consultar_lotes"}.issubset(CORE_MCP_TOOLS.keys())

        ReglaReabastecimiento.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_compra,
            id_almacen=s.alm_principal,
            stock_minimo=Decimal("10"),
            stock_maximo=Decimal("25"),
            cantidad_multiplo=Decimal("5"),
        )
        LoteProducto.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_lote_fefo,
            id_almacen=s.alm_principal,
            numero_lote="MCP-L1",
            fecha_vencimiento=date.today() + timedelta(days=7),
            cantidad_disponible=Decimal("9.0000"),
            cantidad_reservada=Decimal("2.0000"),
        )

        tok_read = _token(s.empresa, ["inventario:read"])
        tok_wrong_scope = _token(s.empresa, ["inventario:write"])
        tok_b = _token(empresa_b, ["inventario:read"])
        emp_id = str(s.empresa.id_empresa)

        with override_settings(RLS_ENABLED=True):
            res_reab = inventario_evaluar_reabastecimiento(tok_read, emp_id)
            assert isinstance(res_reab, list) and len(res_reab) == 1
            assert res_reab[0]["cantidad_sugerida"] == "25.0000"
            _assert_no_floats(res_reab)

            res_lotes = inventario_consultar_lotes(tok_read, emp_id, por_vencer_dias=15)
            assert isinstance(res_lotes, list) and len(res_lotes) == 1
            assert res_lotes[0]["numero_lote"] == "MCP-L1"
            assert res_lotes[0]["cantidad_libre"] == "7.0000"
            _assert_no_floats(res_lotes)

            # Scope incorrecto o empresa ajena -> PermissionError
            with pytest.raises(PermissionError):
                inventario_evaluar_reabastecimiento(tok_wrong_scope, emp_id)
            with pytest.raises(PermissionError):
                inventario_consultar_lotes(tok_b, emp_id)

            # UUID / params inválidos -> {"error": ...}
            assert "error" in inventario_evaluar_reabastecimiento(tok_read, emp_id, almacen_id="no-uuid")
            assert "error" in inventario_consultar_lotes(tok_read, emp_id, producto_id="no-uuid")
            assert "error" in inventario_consultar_lotes(tok_read, emp_id, por_vencer_dias=-1)


class TestCoberturaRamasReabastecimientoLotesYMCP:
    def test_ramas_edge_services_reabastecimiento(self, setup_inv_a):
        from datetime import datetime

        s = setup_inv_a
        regla = ReglaReabastecimiento.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_compra,
            id_almacen=s.alm_principal,
            stock_minimo=Decimal("5.0000"),
            stock_maximo=Decimal("10.0000"),
            cantidad_multiplo=Decimal("1.0000"),
            ruta="COMPRA",
        )
        assert s.prod_compra.nombre_producto in str(regla)

        with pytest.raises(ReabastecimientoError, match="obligatorio"):
            generar_borrador_reabastecimiento(regla, usuario=None)

        for bad_qty in (True, "abc", Decimal("NaN")):
            with pytest.raises(ReabastecimientoError):
                generar_borrador_reabastecimiento(regla, usuario=s.user, cantidad=bad_qty)

        for bad_date in ("no-fecha", 12345):
            with pytest.raises(ReabastecimientoError):
                generar_borrador_reabastecimiento(
                    regla, usuario=s.user, cantidad=Decimal("2"), fecha_necesidad=bad_date
                )

        res_dt = generar_borrador_reabastecimiento(
            regla,
            usuario=s.user,
            cantidad=Decimal("2.0000"),
            fecha_necesidad=datetime.now() + timedelta(days=2),
        )
        assert res_dt["estado"] == "BORRADOR"

        res_str_dt = generar_borrador_reabastecimiento(
            regla,
            usuario=s.user,
            cantidad="3.0000",
            fecha_necesidad=(date.today() + timedelta(days=3)).isoformat(),
        )
        assert res_str_dt["cantidad"] == "3.0000"

        # MANUFACTURA con cantidad que redondea a 0.00 -> error
        regla_mfg = ReglaReabastecimiento.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_lote_fifo,
            id_almacen=s.alm_principal,
            stock_minimo=Decimal("5.0000"),
            stock_maximo=Decimal("10.0000"),
            ruta="MANUFACTURA",
        )
        with pytest.raises(ReabastecimientoError, match="OrdenProduccion"):
            generar_borrador_reabastecimiento(regla_mfg, usuario=s.user, cantidad=Decimal("0.0010"))

    def test_ramas_edge_lotes_entrada_salida_y_permitir_negativo(self, setup_inv_a):
        s = setup_inv_a
        t0 = timezone.now()
        lote_inactivo = LoteProducto.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_lote_fifo,
            id_almacen=s.alm_principal,
            numero_lote="REACTIVAR-1",
            cantidad_disponible=Decimal("0.0000"),
            activo=False,
        )
        assert "REACTIVAR-1" in str(lote_inactivo)

        # Entrada pasando instancia LoteProducto reactiva y suma
        mov_in = registrar_movimiento(
            empresa=s.empresa,
            fecha_hora_movimiento=t0,
            tipo_movimiento="ENTRADA",
            producto=s.prod_lote_fifo,
            cantidad=Decimal("5.0000"),
            almacen_destino=s.alm_principal,
            costo_unitario=Decimal("20.00"),
            usuario=s.user,
            lote=lote_inactivo,
        )
        lote_inactivo.refresh_from_db()
        assert lote_inactivo.activo is True
        assert lote_inactivo.cantidad_disponible == Decimal("5.0000")
        assert MovimientoLote.objects.filter(id_movimiento=mov_in).count() == 1

        # Lote de otro almacén falla tanto en ENTRADA como en SALIDA
        lote_otro_alm = LoteProducto.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_lote_fifo,
            id_almacen=s.alm_secundario,
            numero_lote="OTRO-ALM",
            cantidad_disponible=Decimal("5.0000"),
        )
        with pytest.raises(MovimientoInvalidoError, match="almacén destino"):
            registrar_movimiento(
                empresa=s.empresa,
                fecha_hora_movimiento=t0 + timedelta(minutes=1),
                tipo_movimiento="ENTRADA",
                producto=s.prod_lote_fifo,
                cantidad=Decimal("2.0000"),
                almacen_destino=s.alm_principal,
                costo_unitario=Decimal("20.00"),
                usuario=s.user,
                lote=lote_otro_alm,
            )
        with pytest.raises(MovimientoInvalidoError, match="almacén origen"):
            registrar_movimiento(
                empresa=s.empresa,
                fecha_hora_movimiento=t0 + timedelta(minutes=1),
                tipo_movimiento="SALIDA",
                producto=s.prod_lote_fifo,
                cantidad=Decimal("2.0000"),
                almacen_origen=s.alm_principal,
                usuario=s.user,
                lote=lote_otro_alm,
            )

        # Parámetro lote con tipo inválido
        with pytest.raises(MovimientoInvalidoError, match="Parámetro 'lote' inválido"):
            registrar_movimiento(
                empresa=s.empresa,
                fecha_hora_movimiento=t0 + timedelta(minutes=1),
                tipo_movimiento="ENTRADA",
                producto=s.prod_lote_fifo,
                cantidad=Decimal("1.0000"),
                almacen_destino=s.alm_principal,
                costo_unitario=Decimal("20.00"),
                usuario=s.user,
                lote=12345,  # type: ignore[arg-type]
            )
        with pytest.raises(MovimientoInvalidoError, match="Parámetro 'lote' inválido"):
            registrar_movimiento(
                empresa=s.empresa,
                fecha_hora_movimiento=t0 + timedelta(minutes=1),
                tipo_movimiento="SALIDA",
                producto=s.prod_lote_fifo,
                cantidad=Decimal("1.0000"),
                almacen_origen=s.alm_principal,
                usuario=s.user,
                lote=12345,  # type: ignore[arg-type]
            )

        # Lote inactivo en SALIDA
        lote_off = LoteProducto.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_lote_fifo,
            id_almacen=s.alm_principal,
            numero_lote="OFF-1",
            cantidad_disponible=Decimal("4.0000"),
            activo=False,
        )
        with pytest.raises(MovimientoInvalidoError, match="inactivo"):
            registrar_movimiento(
                empresa=s.empresa,
                fecha_hora_movimiento=t0 + timedelta(minutes=2),
                tipo_movimiento="SALIDA",
                producto=s.prod_lote_fifo,
                cantidad=Decimal("1.0000"),
                almacen_origen=s.alm_principal,
                usuario=s.user,
                lote=lote_off,
            )

        # Lote inexistente string en SALIDA -> error sin permitir_negativo, permitido con permitir_negativo
        with pytest.raises(StockInsuficienteError, match="no existe"):
            registrar_movimiento(
                empresa=s.empresa,
                fecha_hora_movimiento=t0 + timedelta(minutes=2),
                tipo_movimiento="SALIDA",
                producto=s.prod_lote_fifo,
                cantidad=Decimal("1.0000"),
                almacen_origen=s.alm_principal,
                usuario=s.user,
                lote="NO-EXISTE",
            )
        registrar_movimiento(
            empresa=s.empresa,
            fecha_hora_movimiento=t0 + timedelta(minutes=3),
            tipo_movimiento="SALIDA",
            producto=s.prod_lote_fifo,
            cantidad=Decimal("1.0000"),
            almacen_origen=s.alm_principal,
            usuario=s.user,
            lote="NO-EXISTE",
            permitir_negativo=True,
        )

        # Agotar los 5 de lote_inactivo + 2 más con permitir_negativo (sin lote) para cubrir clamp negativo FIFO
        registrar_movimiento(
            empresa=s.empresa,
            fecha_hora_movimiento=t0 + timedelta(minutes=4),
            tipo_movimiento="SALIDA",
            producto=s.prod_lote_fifo,
            cantidad=Decimal("6.0000"),
            almacen_origen=s.alm_principal,
            usuario=s.user,
            permitir_negativo=True,
        )

        # AJUSTE positivo y negativo con lote genera trazabilidad y actualiza LoteProducto
        doc_aj = uuid.uuid4()
        mov_aj_pos = registrar_movimiento(
            empresa=s.empresa,
            fecha_hora_movimiento=t0 + timedelta(minutes=5),
            tipo_movimiento="AJUSTE",
            producto=s.prod_lote_fifo,
            cantidad=Decimal("6.0000"),
            almacen_destino=s.alm_principal,
            costo_unitario=Decimal("20.00"),
            documento_origen_id=doc_aj,
            nombre_modelo_origen="ConteoFisico",
            usuario=s.user,
            lote="AJ-1",
            fecha_fabricacion=date.today() - timedelta(days=5),
            fecha_vencimiento=date.today() + timedelta(days=60),
        )
        assert mov_aj_pos.id_lote is not None
        assert "AJ-1" in str(MovimientoLote.objects.get(id_movimiento=mov_aj_pos))

        mov_aj_neg = registrar_movimiento(
            empresa=s.empresa,
            fecha_hora_movimiento=t0 + timedelta(minutes=6),
            tipo_movimiento="AJUSTE",
            producto=s.prod_lote_fifo,
            cantidad=Decimal("-1.5000"),
            almacen_destino=s.alm_principal,
            documento_origen_id=doc_aj,
            nombre_modelo_origen="ConteoFisico",
            usuario=s.user,
            lote="AJ-1",
        )
        assert mov_aj_neg.id_lote_id == mov_aj_pos.id_lote_id

        # Transferencia hacia lote inactivo sin fechas en destino: reactiva y propaga fechas
        lote_dest_inact = LoteProducto.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_lote_fifo,
            id_almacen=s.alm_secundario,
            numero_lote="AJ-1",
            cantidad_disponible=Decimal("0.0000"),
            activo=False,
        )
        registrar_movimiento(
            empresa=s.empresa,
            fecha_hora_movimiento=t0 + timedelta(minutes=7),
            tipo_movimiento="TRANSFERENCIA",
            producto=s.prod_lote_fifo,
            cantidad=Decimal("1.0000"),
            almacen_origen=s.alm_principal,
            almacen_destino=s.alm_secundario,
            usuario=s.user,
            lote="AJ-1",
        )
        lote_dest_inact.refresh_from_db()
        assert lote_dest_inact.activo is True
        assert lote_dest_inact.fecha_fabricacion is not None
        assert lote_dest_inact.fecha_vencimiento is not None

        # Stock insuficiente agregado en lotes aunque StockActual tenga saldo artificial
        StockActual.objects.filter(
            id_empresa=s.empresa, id_producto=s.prod_lote_fifo, id_almacen=s.alm_principal
        ).update(cantidad_disponible=Decimal("50.0000"))
        with pytest.raises(StockInsuficienteError, match="Stock insuficiente en lotes"):
            registrar_movimiento(
                empresa=s.empresa,
                fecha_hora_movimiento=t0 + timedelta(minutes=8),
                tipo_movimiento="SALIDA",
                producto=s.prod_lote_fifo,
                cantidad=Decimal("20.0000"),
                almacen_origen=s.alm_principal,
                usuario=s.user,
            )

    def test_ramas_edge_api_serializers_y_views(self, client_a, setup_inv_a, empresa_b):
        s = setup_inv_a
        base_reglas = "/api/inventario/reglas-reabastecimiento/"
        base_lotes = "/api/inventario/lotes-producto/"

        # Filtros válidos y UUID inválido
        assert (
            client_a.get(
                f"{base_reglas}?almacen={s.alm_principal.id_almacen}&producto={s.prod_compra.id_producto}"
            ).status_code
            == 200
        )
        assert client_a.get(f"{base_reglas}?almacen=bad-uuid").status_code == 400
        assert client_a.get(f"{base_lotes}?almacen=bad-uuid").status_code == 400
        assert client_a.get(f"{base_lotes}?por_vencer_dias=abc%00").status_code == 400

        # Validaciones de ReglaReabastecimientoSerializer
        var_otro = VarianteProducto.objects.create(id_producto=s.prod_lote_fifo, codigo_variante="X", sku="X1")
        assert (
            client_a.post(
                base_reglas,
                {
                    "id_producto": str(s.prod_compra.id_producto),
                    "id_variante": str(var_otro.id_variante),
                    "id_almacen": str(s.alm_principal.id_almacen),
                    "stock_minimo": "-1",
                    "stock_maximo": "10",
                    "cantidad_multiplo": "0",
                    "ruta": "COMPRA",
                },
                format="json",
            ).status_code
            == 400
        )

        # Evaluar con almacén válido y almacén ajeno (404)
        assert (
            client_a.post(
                f"{base_reglas}evaluar/",
                {"almacen": str(s.alm_principal.id_almacen), "incluir_ok": True},
                format="json",
            ).status_code
            == 200
        )
        assert (
            client_a.post(
                f"{base_reglas}evaluar/",
                {"almacen": str(uuid.uuid4())},
                format="json",
            ).status_code
            == 404
        )

        # generar-borrador 400 cuando falla regla
        s.prod_compra.es_comprable = False
        s.prod_compra.save(update_fields=["es_comprable"])
        regla = ReglaReabastecimiento.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_compra,
            id_almacen=s.alm_principal,
            stock_minimo=Decimal("5"),
            stock_maximo=Decimal("10"),
            ruta="COMPRA",
        )
        assert client_a.post(f"{base_reglas}{regla.pk}/generar-borrador/", {}, format="json").status_code == 400

        # Validaciones LoteProductoSerializer (numero_lote vacío, fecha_vencimiento < fecha_fab, variante ajena, duplicado, PATCH)
        assert (
            client_a.post(
                base_lotes,
                {
                    "id_producto": str(s.prod_lote_fifo.id_producto),
                    "id_almacen": str(s.alm_principal.id_almacen),
                    "numero_lote": "   ",
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                base_lotes,
                {
                    "id_producto": str(s.prod_lote_fifo.id_producto),
                    "id_almacen": str(s.alm_principal.id_almacen),
                    "numero_lote": "FECHAS-ERR",
                    "fecha_fabricacion": date.today().isoformat(),
                    "fecha_vencimiento": (date.today() - timedelta(days=1)).isoformat(),
                },
                format="json",
            ).status_code
            == 400
        )
        var_fefo = VarianteProducto.objects.create(id_producto=s.prod_lote_fefo, codigo_variante="VF", sku="VF-1")
        assert (
            client_a.post(
                base_lotes,
                {
                    "id_producto": str(s.prod_lote_fifo.id_producto),
                    "id_variante": str(var_fefo.id_variante),
                    "id_almacen": str(s.alm_principal.id_almacen),
                    "numero_lote": "VAR-ERR",
                },
                format="json",
            ).status_code
            == 400
        )
        r_l1 = client_a.post(
            base_lotes,
            {
                "id_producto": str(s.prod_lote_fifo.id_producto),
                "id_almacen": str(s.alm_principal.id_almacen),
                "numero_lote": "UNICO-1",
                "cantidad_disponible": "99",  # read_only: debe quedar en 0.0000
            },
            format="json",
        )
        assert r_l1.status_code == 201
        assert r_l1.json()["cantidad_disponible"] == "0.0000"
        l1_id = r_l1.json()["id_lote"]
        assert (
            client_a.post(
                base_lotes,
                {
                    "id_producto": str(s.prod_lote_fifo.id_producto),
                    "id_almacen": str(s.alm_principal.id_almacen),
                    "numero_lote": "UNICO-1",
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.patch(
                f"{base_lotes}{l1_id}/",
                {"fecha_vencimiento": (date.today() + timedelta(days=45)).isoformat()},
                format="json",
            ).status_code
            == 200
        )

        # MovimientoInventarioSerializer con id_lote incongruente -> 400; con id_lote válido -> 201
        lote_otro_prod = LoteProducto.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_lote_fefo,
            id_almacen=s.alm_principal,
            numero_lote="OTRO-PROD",
            cantidad_disponible=Decimal("4"),
        )
        assert (
            client_a.post(
                "/api/inventario/movimientos-inventario/",
                {
                    "id_empresa": str(s.empresa.id_empresa),
                    "id_producto": str(s.prod_lote_fifo.id_producto),
                    "id_almacen_destino": str(s.alm_principal.id_almacen),
                    "tipo_movimiento": "ENTRADA",
                    "cantidad": "2.0000",
                    "costo_unitario_movimiento": "20.00",
                    "fecha_hora_movimiento": timezone.now().isoformat(),
                    "id_lote": str(lote_otro_prod.id_lote),
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/inventario/movimientos-inventario/",
                {
                    "id_empresa": str(empresa_b.id_empresa),
                    "id_producto": str(s.prod_lote_fifo.id_producto),
                    "id_almacen_destino": str(s.alm_principal.id_almacen),
                    "tipo_movimiento": "ENTRADA",
                    "cantidad": "1.0000",
                    "costo_unitario_movimiento": "20.00",
                    "fecha_hora_movimiento": timezone.now().isoformat(),
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/inventario/movimientos-inventario/",
                {
                    "id_empresa": str(s.empresa.id_empresa),
                    "id_producto": str(s.prod_lote_fifo.id_producto),
                    "id_variante": str(var_fefo.id_variante),
                    "id_almacen_destino": str(s.alm_principal.id_almacen),
                    "tipo_movimiento": "ENTRADA",
                    "cantidad": "1.0000",
                    "costo_unitario_movimiento": "20.00",
                    "fecha_hora_movimiento": timezone.now().isoformat(),
                },
                format="json",
            ).status_code
            == 400
        )
        var_fifo = VarianteProducto.objects.create(id_producto=s.prod_lote_fifo, codigo_variante="VFI", sku="VFI-1")
        assert (
            client_a.post(
                "/api/inventario/movimientos-inventario/",
                {
                    "id_empresa": str(s.empresa.id_empresa),
                    "id_producto": str(s.prod_lote_fifo.id_producto),
                    "id_variante": str(var_fifo.id_variante),
                    "id_almacen_destino": str(s.alm_principal.id_almacen),
                    "tipo_movimiento": "ENTRADA",
                    "cantidad": "1.0000",
                    "costo_unitario_movimiento": "20.00",
                    "fecha_hora_movimiento": timezone.now().isoformat(),
                    "id_lote": str(l1_id),
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/inventario/movimientos-inventario/",
                {
                    "id_empresa": str(s.empresa.id_empresa),
                    "id_producto": str(s.prod_lote_fifo.id_producto),
                    "id_almacen_destino": str(s.alm_principal.id_almacen),
                    "tipo_movimiento": "ENTRADA",
                    "cantidad": "1.0000",
                    "costo_unitario_movimiento": "20.00",
                    "fecha_hora_movimiento": timezone.now().isoformat(),
                    "id_lote": str(l1_id),
                    "numero_lote": "OTRO-TEXTO",
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/inventario/movimientos-inventario/",
                {
                    "id_empresa": str(s.empresa.id_empresa),
                    "id_producto": str(s.prod_lote_fifo.id_producto),
                    "id_almacen_destino": str(s.alm_principal.id_almacen),
                    "tipo_movimiento": "ENTRADA",
                    "cantidad": "2.0000",
                    "costo_unitario_movimiento": "20.00",
                    "fecha_hora_movimiento": timezone.now().isoformat(),
                    "id_lote": str(l1_id),
                },
                format="json",
            ).status_code
            == 201
        )
        r_search = client_a.get("/api/inventario/productos/?search=Resina&ordering=sku")
        assert r_search.status_code == 200
        assert any(p["sku"] == "RES-FIFO" for p in r_search.json()["results"])
        assert client_a.get("/api/inventario/productos/?search=%00").status_code == 400

    def test_ramas_edge_mcp_tools(self, setup_inv_a):
        s = setup_inv_a
        tok_read = _token(s.empresa, ["inventario:read"])
        emp_id = str(s.empresa.id_empresa)
        alm_id = str(s.alm_principal.id_almacen)
        prod_id = str(s.prod_lote_fefo.id_producto)

        LoteProducto.objects.create(
            id_empresa=s.empresa,
            id_producto=s.prod_lote_fefo,
            id_almacen=s.alm_principal,
            numero_lote="MCP-EDGE",
            cantidad_disponible=Decimal("5"),
        )

        with override_settings(RLS_ENABLED=True):
            assert isinstance(inventario_evaluar_reabastecimiento(tok_read, emp_id, almacen_id=alm_id), list)
            assert "error" in inventario_evaluar_reabastecimiento(tok_read, emp_id, almacen_id=str(uuid.uuid4()))
            assert "error" in inventario_evaluar_reabastecimiento(tok_read, emp_id, solo_requieren="yes")  # type: ignore[arg-type]

            assert isinstance(
                inventario_consultar_lotes(
                    tok_read, emp_id, producto_id=prod_id, almacen_id=alm_id, solo_con_stock=False
                ),
                list,
            )
            assert "error" in inventario_consultar_lotes(tok_read, emp_id, producto_id=str(uuid.uuid4()))
            assert "error" in inventario_consultar_lotes(tok_read, emp_id, almacen_id=str(uuid.uuid4()))
            assert "error" in inventario_consultar_lotes(tok_read, emp_id, por_vencer_dias=True)  # type: ignore[arg-type]
            assert "error" in inventario_consultar_lotes(tok_read, emp_id, por_vencer_dias="abc")  # type: ignore[arg-type]
            assert "error" in inventario_consultar_lotes(tok_read, emp_id, solo_con_stock="no")  # type: ignore[arg-type]

            s.empresa.activo = False
            s.empresa.save(update_fields=["activo"])
            assert "error" in inventario_evaluar_reabastecimiento(tok_read, emp_id)
            assert "error" in inventario_consultar_lotes(tok_read, emp_id)
