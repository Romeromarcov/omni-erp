"""
Tests de integración para PR-18 (Ola B6 · Plan 08 §B.4.2 + §B.4.3):
  1. ``compras.FacturaCompra`` con ``id_orden_compra`` opcional + ``id_proveedor``,
     ``FacturaCompraSerializer`` (whitelist explícita, Matriz-Subsidiaria, coherencia)
     y backfill de migración 0013.
  2. ``finanzas.services_conciliacion_pagos`` y ``views_conciliacion_pagos``:
     soporte de ``FacturaCompra`` sin OC y ``modo_historico_externo=True``
     (fail-closed, sin duplicar AbonoCxC/AbonoCxP, respeta saldos Odoo).
  3. ``OdooXMLRPCClient`` + ``OdooConnector`` (Odoo 18 ``memo``/``payment_reference`` sin ``ref``,
     ``pull_facturas_compra``, ``get_reconciliaciones_pagos`` batch sin N+1).
  4. ``SyncEngine._upsert_factura_compra`` y ``_upsert_pago`` (N:M ``AsignacionPago``,
     anticipos, outbound proveedor -> CxP/FacturaCompra, multimoneda, idempotencia,
     history-only sin asientos ni movimientos, aislamiento multi-tenant + RLS).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.banca_electronica.services import _resolver_proveedor_de_pago
from apps.compras.models import FacturaCompra, OrdenCompra
from apps.contabilidad.models import AsientoContable
from apps.core import rls
from apps.core.models import Contacto, Empresa
from apps.crm.models import Cliente
from apps.cuentas_por_cobrar.models import AbonoCxC, CuentaPorCobrar
from apps.cuentas_por_pagar.models import AbonoCxP, CuentaPorPagar
from apps.finanzas.models import AsignacionPago, MetodoPago, Moneda, Pago
from apps.finanzas.services_conciliacion_pagos import (
    ConciliacionPagoError,
    aplicar_pago_a_documentos,
    saldo_a_favor_contacto,
    saldo_disponible_pago,
    saldo_pendiente_documento,
    sugerir_distribucion_fifo,
)
from apps.integration_hub.models import ConectorInstancia, ConectorProveedor, EntidadSincronizada, JobSincronizacion
from apps.integration_hub.seed_data import PROVEEDORES_BASE
from apps.integration_hub.services.sync_engine import SyncEngine
from apps.inventario.models import Producto
from apps.proveedores.models import Proveedor
from apps.ventas.models import FacturaFiscal

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _hoy() -> date:
    return timezone.localdate()


def _client(user) -> APIClient:
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _instancia_odoo(empresa, nombre="Odoo QA") -> ConectorInstancia:
    prov, _ = ConectorProveedor.objects.get_or_create(
        codigo="odoo",
        defaults={
            "nombre": "Odoo",
            "estado": "activo",
            "activo": True,
            "capacidades": [
                "contactos",
                "productos",
                "pedidos_venta",
                "pedidos_compra",
                "facturas_venta",
                "facturas_compra",
                "pagos",
                "inventario",
            ],
        },
    )
    return ConectorInstancia.objects.create(
        id_empresa=empresa,
        id_proveedor=prov,
        nombre=nombre,
        configuracion={"host": "https://qa.odoo.com", "db": "qa", "user": "api@qa.com", "api_key": "k"},
        estado="activo",
        entidades_activas=["contactos", "productos", "facturas_venta", "facturas_compra", "pagos"],
    )


def _seed_producto(eng: SyncEngine, instancia: ConectorInstancia, ext_id="10", sku="SKU-10") -> Producto:
    eng.ingerir_en_omni(
        instancia,
        "productos",
        [
            {
                "id_externo": ext_id,
                "nombre": f"Producto {ext_id}",
                "codigo_interno": sku,
                "precio_venta": "20.00",
                "costo": "10.00",
                "_checksum": f"p-{ext_id}",
            }
        ],
    )
    return Producto.objects.get(id_empresa=instancia.id_empresa, sku=sku)


class TestFacturaCompraSinOrdenYSerializer:
    def test_crear_factura_sin_orden_y_serializer_whitelist_y_matriz_subsidiaria(
        self, empresa_a, empresa_b, user_a, moneda_usd
    ):
        contacto_prov = Contacto.objects.create(
            id_empresa=empresa_a,
            nombre="Prov Directo C.A.",
            rif="J-50000001-1",
            es_proveedor=True,
        )
        prov_a = Proveedor.objects.create(
            id_empresa=empresa_a,
            razon_social="Prov Directo C.A.",
            rif="J-50000001-1",
            contacto=contacto_prov,
        )
        prov_a2 = Proveedor.objects.create(
            id_empresa=empresa_a,
            razon_social="Otro Prov A",
            rif="J-50000002-2",
        )
        oc_a = OrdenCompra.objects.create(
            id_empresa=empresa_a,
            id_proveedor=prov_a,
            numero_orden="OC-DIR-1",
            fecha_orden=_hoy(),
            estado="APROBADA",
        )
        prov_b = Proveedor.objects.create(
            id_empresa=empresa_b,
            razon_social="Prov Ajeno B",
            rif="J-50000009-9",
        )
        subsidiaria = Empresa.objects.create(
            nombre_legal="Subsidiaria Test",
            identificador_fiscal="J-77700001-1",
            empresa_matriz=empresa_a,
            id_moneda_base=moneda_usd,
        )
        prov_sub = Proveedor.objects.create(
            id_empresa=subsidiaria,
            razon_social="Prov Subsidiaria",
            rif="J-77700002-2",
        )

        client = _client(user_a)

        # 1. POST sin id_orden_compra (solo id_proveedor) -> 201
        r_direct = client.post(
            "/api/compras/facturas-compra/",
            {
                "id_proveedor": str(prov_a.pk),
                "numero_factura": "FC-DIR-001",
                "fecha_emision": _hoy().isoformat(),
                "monto_total": "250.00",
                "referencia_externa": "INJECT-IGNORADO",
            },
            format="json",
        )
        assert r_direct.status_code == 201, r_direct.json()
        fc_dir = FacturaCompra.objects.get(pk=r_direct.json()["id_factura_compra"])
        assert fc_dir.id_orden_compra is None
        assert fc_dir.id_proveedor_id == prov_a.pk
        assert fc_dir.referencia_externa is None  # whitelist CTF-005 ignora campo interno

        # 2. POST solo con id_orden_compra -> 201 e inyecta id_proveedor automáticamente
        r_oc = client.post(
            "/api/compras/facturas-compra/",
            {
                "id_orden_compra": str(oc_a.pk),
                "numero_factura": "FC-OC-001",
                "fecha_emision": _hoy().isoformat(),
                "monto_total": "100.00",
            },
            format="json",
        )
        assert r_oc.status_code == 201, r_oc.json()
        fc_oc = FacturaCompra.objects.get(pk=r_oc.json()["id_factura_compra"])
        assert fc_oc.id_proveedor_id == prov_a.pk

        # 3. POST sin proveedor ni orden -> 400
        r_vacio = client.post(
            "/api/compras/facturas-compra/",
            {
                "numero_factura": "FC-VACIA",
                "fecha_emision": _hoy().isoformat(),
                "monto_total": "10.00",
            },
            format="json",
        )
        assert r_vacio.status_code == 400

        # 4. POST con proveedor distinto al de la OC -> 400
        r_mismatch = client.post(
            "/api/compras/facturas-compra/",
            {
                "id_orden_compra": str(oc_a.pk),
                "id_proveedor": str(prov_a2.pk),
                "numero_factura": "FC-MISMATCH",
                "fecha_emision": _hoy().isoformat(),
                "monto_total": "10.00",
            },
            format="json",
        )
        assert r_mismatch.status_code == 400

        # 5. POST con proveedor de otro tenant (empresa_b) o subsidiaria distinta -> 400
        r_cross = client.post(
            "/api/compras/facturas-compra/",
            {
                "id_proveedor": str(prov_b.pk),
                "numero_factura": "FC-CROSS",
                "fecha_emision": _hoy().isoformat(),
                "monto_total": "10.00",
            },
            format="json",
        )
        assert r_cross.status_code == 400

        r_sub = client.post(
            "/api/compras/facturas-compra/",
            {
                "id_proveedor": str(prov_sub.pk),
                "numero_factura": "FC-SUB",
                "fecha_emision": _hoy().isoformat(),
                "monto_total": "10.00",
            },
            format="json",
        )
        assert r_sub.status_code == 400

        # 6. PATCH parcial conserva id_proveedor / id_orden_compra del instance
        r_patch = client.patch(
            f"/api/compras/facturas-compra/{fc_dir.pk}/",
            {"observaciones": "Actualizada sin tocar proveedor"},
            format="json",
        )
        assert r_patch.status_code == 200, r_patch.json()
        fc_dir.refresh_from_db()
        assert fc_dir.observaciones == "Actualizada sin tocar proveedor"
        assert fc_dir.id_proveedor_id == prov_a.pk

    def test_conciliacion_fifo_estado_contacto_y_banca_resuelven_factura_sin_oc(
        self, empresa_a, user_a, moneda_usd, metodo_efectivo
    ):
        contacto = Contacto.objects.create(
            id_empresa=empresa_a,
            nombre="Prov Directo Concil",
            rif="J-50000010-1",
            es_proveedor=True,
        )
        prov = Proveedor.objects.create(
            id_empresa=empresa_a,
            razon_social="Prov Directo Concil",
            rif="J-50000010-1",
            contacto=contacto,
        )
        fc = FacturaCompra.objects.create(
            id_empresa=empresa_a,
            id_orden_compra=None,
            id_proveedor=prov,
            numero_factura="FC-DIRECTA-99",
            fecha_emision=_hoy(),
            monto_total=Decimal("120.0000"),
        )
        pago = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto,
            tipo_operacion="EGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("120.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )

        fifo = sugerir_distribucion_fifo(pago, tipo_documento="FACTURA_COMPRA")
        assert len(fifo["propuestas"]) == 1
        assert fifo["propuestas"][0]["id_documento"] == str(fc.pk)

        resp = _client(user_a).get(f"/api/finanzas/contactos/{contacto.pk}/estado-conciliacion/")
        assert resp.status_code == 200
        docs_fc = [d for d in resp.json()["obligaciones_abiertas"] if d["tipo_documento"] == "FACTURA_COMPRA"]
        assert len(docs_fc) == 1
        assert docs_fc[0]["id_documento"] == str(fc.pk)

        asigs = aplicar_pago_a_documentos(
            pago,
            [{"tipo_documento": "FACTURA_COMPRA", "id_documento": fc.pk, "monto_asignado_pago": "120.00"}],
            usuario=user_a,
            generar_asiento=False,
        )
        assert len(asigs) == 1
        assert _resolver_proveedor_de_pago(pago, empresa_a) == prov


class TestConciliacionModoHistoricoExterno:
    def test_guard_fail_closed_exige_generar_asiento_false(self, empresa_a, moneda_usd, metodo_efectivo):
        contacto = Contacto.objects.create(id_empresa=empresa_a, nombre="Cli Hist", es_cliente=True)
        cli = Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Cli Hist", rif="J-60000001-1", contacto=contacto
        )
        fv = FacturaFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cli,
            numero_control="C-HIST-1",
            numero_factura="F-HIST-1",
            fecha_emision=_hoy(),
            monto_total=Decimal("50.0000"),
            id_moneda=moneda_usd,
            estado="PAGADA",
        )
        pago = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto,
            tipo_operacion="INGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("50.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        with pytest.raises(ConciliacionPagoError, match="generar_asiento=False"):
            aplicar_pago_a_documentos(
                pago,
                [{"tipo_documento": "FACTURA_VENTA", "id_documento": fv.pk, "monto_asignado_pago": "50.00"}],
                generar_asiento=True,
                modo_historico_externo=True,
            )

    def test_concilia_cxc_y_cxp_ya_pagadas_sin_abonos_duplicados_ni_negativos(
        self, empresa_a, moneda_usd, metodo_efectivo
    ):
        contacto = Contacto.objects.create(
            id_empresa=empresa_a, nombre="Tercero Mix", es_cliente=True, es_proveedor=True
        )
        cli = Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Tercero Mix", rif="J-60000002-2", contacto=contacto
        )
        prov = Proveedor.objects.create(
            id_empresa=empresa_a, razon_social="Tercero Mix", rif="J-60000002-2", contacto=contacto
        )
        cxc = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cli,
            monto=Decimal("80.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy(),
            estado="pagada",
        )
        cxp = CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=prov,
            monto_total=Decimal("90.0000"),
            monto_pendiente=Decimal("0.0000"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy(),
            estado="PAGADA",
        )
        pago_in = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto,
            tipo_operacion="INGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("80.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        pago_out = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto,
            tipo_operacion="EGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("90.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )

        aplicar_pago_a_documentos(
            pago_in,
            [{"tipo_documento": "CUENTA_POR_COBRAR", "id_documento": cxc.pk, "monto_asignado_pago": "80.00"}],
            generar_asiento=False,
            modo_historico_externo=True,
        )
        aplicar_pago_a_documentos(
            pago_out,
            [{"tipo_documento": "CUENTA_POR_PAGAR", "id_documento": cxp.pk, "monto_asignado_pago": "90.00"}],
            generar_asiento=False,
            modo_historico_externo=True,
        )

        cxp.refresh_from_db()
        cxc.refresh_from_db()
        assert cxp.monto_pendiente == Decimal("0.0000")
        assert cxp.estado == "PAGADA"
        assert cxc.estado == "pagada"
        assert AbonoCxC.objects.filter(cuenta_por_cobrar=cxc).count() == 0
        assert AbonoCxP.objects.filter(cuenta_por_pagar=cxp).count() == 0
        assert AsientoContable.objects.count() == 0


class TestSyncEngineFacturasCompraYPagosNM:
    def test_seed_y_serializer_incluyen_facturas_compra(self):
        odoo_seed = next(p for p in PROVEEDORES_BASE if p["codigo"] == "odoo")
        sheets_seed = next(p for p in PROVEEDORES_BASE if p["codigo"] == "google_sheets")
        assert "facturas_compra" in odoo_seed["capacidades"]
        assert "facturas_compra" in sheets_seed["capacidades"]

    def test_upsert_factura_compra_sin_oc_y_con_oc_y_cxp_history_only(self, empresa_a):
        eng = SyncEngine()
        inst = _instancia_odoo(empresa_a)
        prod = _seed_producto(eng, inst, ext_id="10", sku="ACEITE-10")

        # 1. Factura de compra sin OC en Omni -> id_orden_compra=None, crea Proveedor + Contacto + CxP
        datos_fc = {
            "id_externo": "501",
            "numero": "BILL/2026/001",
            "referencia": "FAC-PROV-1",
            "origen_pedido": "PO-NO-EXISTE",
            "proveedor_id_externo": "70",
            "proveedor_nombre": "Lubricantes Externos S.A.",
            "fecha_factura": "2026-06-10",
            "fecha_vencimiento": "2026-07-10",
            "subtotal": "100.00",
            "impuestos": "16.00",
            "total": "116.00",
            "saldo_pendiente": "40.00",
            "moneda": "USD",
            "estado_pago": "parcial",
            "lineas": [
                {
                    "product_id": [10, "Producto 10"],
                    "quantity": 2,
                    "price_unit": "50.00",
                    "discount": 0,
                    "price_subtotal": "100.00",
                    "price_total": "116.00",
                },
                {
                    # Producto no sincronizado: se omite sin romper factura
                    "product_id": [999, "Desconocido"],
                    "quantity": 1,
                    "price_unit": "10.00",
                    "price_subtotal": "10.00",
                    "price_total": "10.00",
                },
            ],
            "_checksum": "fc-501",
        }
        pk1 = eng._upsert_factura_compra(datos_fc, inst)
        assert pk1
        fc1 = FacturaCompra.objects.get(pk=pk1)
        assert fc1.id_orden_compra is None
        assert fc1.id_proveedor is not None
        assert fc1.id_proveedor.contacto is not None
        assert fc1.id_proveedor.contacto.es_proveedor is True
        assert fc1.referencia_externa == "odoo:in_invoice:501"
        assert fc1.detalles.count() == 1
        det = fc1.detalles.first()
        assert det.id_producto_id == prod.pk
        assert det.monto_impuesto == Decimal("16.0000")

        cxp1 = CuentaPorPagar.objects.get(id_empresa=empresa_a, id_factura_compra=fc1)
        assert cxp1.estado == "PARCIAL"
        assert cxp1.monto_total == Decimal("116.0000")
        assert cxp1.monto_pendiente == Decimal("40.0000")
        assert AsientoContable.objects.count() == 0

        # 2. Re-sync ahora con OrdenCompra existente y estado pagado -> idempotente y enlaza OC
        oc = OrdenCompra.objects.create(
            id_empresa=empresa_a,
            id_proveedor=fc1.id_proveedor,
            numero_orden="PO-EXISTE",
            fecha_orden=date(2026, 6, 1),
            estado="APROBADA",
        )
        datos_fc["origen_pedido"] = "PO-EXISTE"
        datos_fc["estado_pago"] = "pagado"
        datos_fc["saldo_pendiente"] = "0.00"
        pk2 = eng._upsert_factura_compra(datos_fc, inst)
        assert pk2 == pk1
        fc1.refresh_from_db()
        cxp1.refresh_from_db()
        assert fc1.id_orden_compra_id == oc.pk
        assert cxp1.estado == "PAGADA"
        assert cxp1.monto_pendiente == Decimal("0.0000")
        assert FacturaCompra.objects.filter(id_empresa=empresa_a).count() == 1
        assert CuentaPorPagar.objects.filter(id_empresa=empresa_a).count() == 1

    def test_pago_inbound_multifactura_parcial_anticipo_y_resync_idempotente(self, empresa_a):
        eng = SyncEngine()
        inst = _instancia_odoo(empresa_a)
        eng.ingerir_en_omni(
            inst,
            "facturas_venta",
            [
                {
                    "id_externo": "900",
                    "numero": "FAC-V-900",
                    "cliente_id_externo": "42",
                    "cliente_nombre": "Cliente Multi",
                    "fecha_factura": "2026-06-01",
                    "subtotal": "100.00",
                    "impuestos": "0.00",
                    "total": "100.00",
                    "moneda": "USD",
                    "estado_pago": "pendiente",
                    "lineas": [],
                    "_checksum": "fv900",
                },
                {
                    "id_externo": "901",
                    "numero": "FAC-V-901",
                    "cliente_id_externo": "42",
                    "cliente_nombre": "Cliente Multi",
                    "fecha_factura": "2026-06-02",
                    "subtotal": "200.00",
                    "impuestos": "0.00",
                    "total": "200.00",
                    "moneda": "USD",
                    "estado_pago": "pendiente",
                    "lineas": [],
                    "_checksum": "fv901",
                },
            ],
        )
        fv1 = FacturaFiscal.objects.get(id_empresa=empresa_a, numero_factura="FAC-V-900")
        fv2 = FacturaFiscal.objects.get(id_empresa=empresa_a, numero_factura="FAC-V-901")

        # Pago de $150 que concilia $100 a fv1 y $30 a fv2 (quedan $20 como saldo a favor!)
        pago_payload = {
            "id_externo": "801",
            "numero": "PAY/801",
            "tipo": "inbound",
            "tipo_socio": "customer",
            "socio_id_externo": "42",
            "socio_nombre": "Cliente Multi",
            "monto": "150.00",
            "fecha": "2026-06-15",
            "estado": "in_process",
            "moneda": "USD",
            "facturas_externas": ["900", "901"],
            "reconciliaciones": [
                {
                    "partial_reconcile_id": "7001",
                    "move_id_externo": "900",
                    "move_type": "out_invoice",
                    "monto_base": "100.00",
                    "monto_pago": "100.00",
                    "monto_documento": "100.00",
                    "moneda_pago": "USD",
                    "moneda_documento": "USD",
                },
                {
                    "partial_reconcile_id": "7002",
                    "move_id_externo": "901",
                    "move_type": "out_invoice",
                    "monto_base": "30.00",
                    "monto_pago": "30.00",
                    "monto_documento": "30.00",
                    "moneda_pago": "USD",
                    "moneda_documento": "USD",
                },
            ],
            "referencia": "Pago mixto",
            "_checksum": "p801-v1",
        }
        eng.ingerir_en_omni(inst, "pagos", [pago_payload])
        pago = Pago.objects.get(id_empresa=empresa_a, referencia__startswith="odoo:801")
        assert pago.tipo_operacion == "INGRESO"
        assert pago.tipo_documento == "CONCILIACION_MULTIPLE"
        assert pago.id_documento is None
        assert pago.id_transaccion_financiera is None
        assert pago.id_contacto is not None
        assert AsientoContable.objects.count() == 0

        fv1.refresh_from_db()
        fv2.refresh_from_db()
        assert fv1.estado == "PAGADA"
        assert fv2.estado == "EMITIDA"
        assert saldo_pendiente_documento(fv1) == Decimal("0.0000")
        assert saldo_pendiente_documento(fv2) == Decimal("170.0000")
        assert saldo_disponible_pago(pago) == Decimal("20.0000")

        # Re-sync con una nueva conciliación parcial (7003 por $20 más sobre fv2) -> no duplica 7001/7002!
        pago_payload["reconciliaciones"].append(
            {
                "partial_reconcile_id": "7003",
                "move_id_externo": "901",
                "move_type": "out_invoice",
                "monto_base": "20.00",
                "monto_pago": "20.00",
                "monto_documento": "20.00",
                "moneda_pago": "USD",
                "moneda_documento": "USD",
            }
        )
        pago_payload["_checksum"] = "p801-v2"
        eng.ingerir_en_omni(inst, "pagos", [pago_payload])
        assert AsignacionPago.objects.filter(id_pago=pago, estado="ACTIVA").count() == 3
        assert saldo_disponible_pago(pago) == Decimal("0.0000")
        assert saldo_pendiente_documento(fv2) == Decimal("150.0000")

        # Anticipo puro sin facturas reconciliadas -> tipo_documento="ANTICIPO", suma al saldo a favor
        eng.ingerir_en_omni(
            inst,
            "pagos",
            [
                {
                    "id_externo": "802",
                    "numero": "PAY/802",
                    "tipo": "inbound",
                    "tipo_socio": "customer",
                    "socio_id_externo": "42",
                    "socio_nombre": "Cliente Multi",
                    "monto": "75.00",
                    "fecha": "2026-06-16",
                    "estado": "paid",
                    "moneda": "USD",
                    "facturas_externas": [],
                    "reconciliaciones": [],
                    "referencia": "Anticipo puro",
                    "_checksum": "p802",
                }
            ],
        )
        anticipo = Pago.objects.get(id_empresa=empresa_a, referencia__startswith="odoo:802")
        assert anticipo.tipo_documento == "ANTICIPO"
        assert anticipo.id_documento is None
        saldo = saldo_a_favor_contacto(empresa_a, pago.id_contacto, tipo_operacion="INGRESO")
        assert saldo["total_por_moneda"]["USD"]["INGRESO"] == Decimal("75.0000")
        assert saldo["por_operacion"]["INGRESO"]["USD"] == Decimal("75.0000")

    def test_pago_outbound_proveedor_y_n_a_1_multimoneda(self, empresa_a, moneda_usd):
        Moneda.objects.get_or_create(
            codigo_iso="EUR",
            defaults={"nombre": "Euro", "simbolo": "€", "tipo_moneda": "fiat", "es_publica": True},
        )
        eng = SyncEngine()
        inst = _instancia_odoo(empresa_a)

        eng.ingerir_en_omni(
            inst,
            "facturas_compra",
            [
                {
                    "id_externo": "601",
                    "numero": "BILL/601",
                    "proveedor_id_externo": "88",
                    "proveedor_nombre": "Prov Outbound",
                    "fecha_factura": "2026-06-05",
                    "fecha_vencimiento": "2026-07-05",
                    "total": "200.00",
                    "saldo_pendiente": "0.00",
                    "moneda": "USD",
                    "estado_pago": "pagado",
                    "lineas": [],
                    "_checksum": "fc601",
                },
                {
                    "id_externo": "602",
                    "numero": "BILL/602",
                    "proveedor_id_externo": "88",
                    "proveedor_nombre": "Prov Outbound",
                    "fecha_factura": "2026-06-06",
                    "fecha_vencimiento": "2026-07-06",
                    "total": "100.00",
                    "saldo_pendiente": "100.00",
                    "moneda": "USD",
                    "estado_pago": "pendiente",
                    "lineas": [],
                    "_checksum": "fc602",
                },
            ],
        )
        fc1 = FacturaCompra.objects.get(id_empresa=empresa_a, numero_factura="BILL/601")
        cxp1 = CuentaPorPagar.objects.get(id_empresa=empresa_a, id_factura_compra=fc1)
        fc2 = FacturaCompra.objects.get(id_empresa=empresa_a, numero_factura="BILL/602")
        cxp2 = CuentaPorPagar.objects.get(id_empresa=empresa_a, id_factura_compra=fc2)

        # Dos pagos distintos saldan BILL/601 (N -> 1): P1=120 USD + P2=80 USD
        eng.ingerir_en_omni(
            inst,
            "pagos",
            [
                {
                    "id_externo": "901",
                    "tipo": "outbound",
                    "tipo_socio": "supplier",
                    "socio_id_externo": "88",
                    "socio_nombre": "Prov Outbound",
                    "monto": "120.00",
                    "fecha": "2026-06-10",
                    "moneda": "USD",
                    "facturas_externas": ["601"],
                    "reconciliaciones": [
                        {
                            "partial_reconcile_id": "8101",
                            "move_id_externo": "601",
                            "move_type": "in_invoice",
                            "monto_base": "120.00",
                            "monto_pago": "120.00",
                            "monto_documento": "120.00",
                            "moneda_pago": "USD",
                            "moneda_documento": "USD",
                        }
                    ],
                    "_checksum": "p901",
                },
                {
                    "id_externo": "902",
                    "tipo": "outbound",
                    "tipo_socio": "supplier",
                    "socio_id_externo": "88",
                    "socio_nombre": "Prov Outbound",
                    "monto": "80.00",
                    "fecha": "2026-06-12",
                    "moneda": "USD",
                    "facturas_externas": ["601"],
                    "reconciliaciones": [
                        {
                            "partial_reconcile_id": "8102",
                            "move_id_externo": "601",
                            "move_type": "in_invoice",
                            "monto_base": "80.00",
                            "monto_pago": "80.00",
                            "monto_documento": "80.00",
                            "moneda_pago": "USD",
                            "moneda_documento": "USD",
                        }
                    ],
                    "_checksum": "p902",
                },
            ],
        )

        p1 = Pago.objects.get(id_empresa=empresa_a, referencia__startswith="odoo:901")
        p2 = Pago.objects.get(id_empresa=empresa_a, referencia__startswith="odoo:902")
        assert p1.tipo_operacion == "EGRESO"
        assert p1.tipo_documento == "CXP"
        assert p1.id_cxp_id == cxp1.pk
        assert p2.id_cxp_id == cxp1.pk
        assert AsignacionPago.objects.filter(id_cxp=cxp1, estado="ACTIVA").count() == 2
        cxp1.refresh_from_db()
        assert cxp1.monto_pendiente == Decimal("0.0000")
        assert cxp1.estado == "PAGADA"

        # Pago en EUR (50 EUR -> 55 USD) sobre BILL/602
        eng.ingerir_en_omni(
            inst,
            "pagos",
            [
                {
                    "id_externo": "903",
                    "tipo": "outbound",
                    "tipo_socio": "supplier",
                    "socio_id_externo": "88",
                    "socio_nombre": "Prov Outbound",
                    "monto": "50.00",
                    "fecha": "2026-06-15",
                    "moneda": "EUR",
                    "facturas_externas": ["602"],
                    "reconciliaciones": [
                        {
                            "partial_reconcile_id": "8103",
                            "move_id_externo": "602",
                            "move_type": "in_invoice",
                            "monto_base": "55.00",
                            "monto_pago": "50.00",
                            "monto_documento": "55.00",
                            "moneda_pago": "EUR",
                            "moneda_documento": "USD",
                        }
                    ],
                    "_checksum": "p903",
                }
            ],
        )
        cxp2.refresh_from_db()
        assert cxp2.monto_pendiente == Decimal("45.0000")
        assert cxp2.estado == "PARCIAL"
        assert AbonoCxP.objects.count() == 0
        assert AsientoContable.objects.count() == 0

    def test_ejecutar_job_odoo18_e2e_facturas_compra_y_pagos_y_rls_aislado(self, empresa_a, empresa_b, rls_test_role):
        inst_a = _instancia_odoo(empresa_a, nombre="Odoo A")
        inst_b = _instancia_odoo(empresa_b, nombre="Odoo B")

        def _fake_server_proxy(url, allow_none=True):
            proxy = MagicMock()
            if url.endswith("/common"):
                proxy.version.return_value = {"server_version": "18.0+e"}
                proxy.authenticate.return_value = 9
                return proxy

            def _exec(db, uid, key, model, method, args, kwargs):
                if model == "res.lang":
                    return 1
                if model == "account.move" and method == "search_read":
                    return [
                        {
                            "id": 303,
                            "name": "BILL/O18/001",
                            "ref": "PROV-18",
                            "invoice_origin": "",
                            "partner_id": [71, "Prov Odoo 18"],
                            "invoice_date": "2026-06-01",
                            "invoice_date_due": "2026-07-01",
                            "amount_untaxed": 100.0,
                            "amount_tax": 0.0,
                            "amount_total": 100.0,
                            "amount_residual": 0.0,
                            "currency_id": [2, "USD"],
                            "payment_state": "paid",
                            "state": "posted",
                            "move_type": "in_invoice",
                        }
                    ]
                if model == "account.move.line" and method == "search_read":
                    domain = args[0] if args else []
                    # get_lineas_factura vs get_reconciliaciones_pagos
                    if any(cond[0] == "account_type" for cond in domain if isinstance(cond, list)):
                        return [
                            {
                                "id": 1002,
                                "move_id": [200, "PAGO/O18/1"],
                                "account_type": "liability_payable",
                                "matched_debit_ids": [],
                                "matched_credit_ids": [503],
                                "currency_id": [2, "USD"],
                            }
                        ]
                    return []
                if model == "account.payment" and method == "fields_get":
                    return {
                        "id": {"string": "ID"},
                        "name": {"string": "Name"},
                        "partner_id": {"string": "Partner"},
                        "payment_type": {"string": "Type"},
                        "partner_type": {"string": "Partner Type"},
                        "amount": {"string": "Amount"},
                        "date": {"string": "Date"},
                        "state": {"string": "State"},
                        "journal_id": {"string": "Journal"},
                        "currency_id": {"string": "Currency"},
                        "memo": {"string": "Memo"},
                        "payment_reference": {"string": "Payment Reference"},
                        "move_id": {"string": "Move"},
                        "reconciled_invoice_ids": {"string": "Invoices"},
                        "reconciled_bill_ids": {"string": "Bills"},
                    }
                if model == "account.payment" and method == "search_read":
                    # Simular Odoo 18: fallaría si el cliente pidiera 'ref'
                    assert "ref" not in kwargs.get("fields", []), "Odoo 18 NO tiene campo ref en account.payment"
                    return [
                        {
                            "id": 950,
                            "name": "PAGO/O18/1",
                            "partner_id": [71, "Prov Odoo 18"],
                            "payment_type": "outbound",
                            "partner_type": "supplier",
                            "amount": 100.0,
                            "date": "2026-06-05",
                            "state": "in_process",
                            "journal_id": [5, "Banco"],
                            "currency_id": [2, "USD"],
                            "memo": "Pago factura 18",
                            "payment_reference": "REF-18",
                            "move_id": [200, "PAGO/O18/1"],
                            "reconciled_invoice_ids": [],
                            "reconciled_bill_ids": [303],
                        }
                    ]
                if model == "account.partial.reconcile" and method == "read":
                    return [
                        {
                            "id": 503,
                            "debit_move_id": [1002, "PAGO/O18/1"],
                            "credit_move_id": [2003, "BILL/O18/001"],
                            "amount": 100.0,
                            "debit_amount_currency": 100.0,
                            "credit_amount_currency": 100.0,
                            "debit_currency_id": [2, "USD"],
                            "credit_currency_id": [2, "USD"],
                        }
                    ]
                if model == "account.move.line" and method == "read":
                    return [{"id": 2003, "move_id": [303, "BILL/O18/001"], "currency_id": [2, "USD"]}]
                if model == "account.move" and method == "read":
                    return [{"id": 303, "move_type": "in_invoice", "name": "BILL/O18/001", "currency_id": [2, "USD"]}]
                return []

            proxy.execute_kw.side_effect = _exec
            return proxy

        eng = SyncEngine()
        with patch("xmlrpc.client.ServerProxy", side_effect=_fake_server_proxy):
            job_fc = JobSincronizacion.objects.create(
                id_instancia=inst_a, tipo_entidad="facturas_compra", direccion="inbound"
            )
            res_fc = eng.ejecutar_job(job_fc)
            assert res_fc.exitoso and res_fc.creados == 1

            job_pagos = JobSincronizacion.objects.create(
                id_instancia=inst_a, tipo_entidad="pagos", direccion="inbound"
            )
            res_p = eng.ejecutar_job(job_pagos)
            assert res_p.exitoso and res_p.creados == 1

        # Verificar creación en empresa_a y aislamiento total respecto a empresa_b + RLS real
        fc_a = FacturaCompra.objects.get(id_empresa=empresa_a, numero_factura="BILL/O18/001")
        asig_a = AsignacionPago.objects.get(id_empresa=empresa_a, referencia_externa="odoo:pr:503")
        assert asig_a.id_cxp is not None
        assert asig_a.id_cxp.id_factura_compra_id == fc_a.pk
        assert FacturaCompra.objects.filter(id_empresa=empresa_b).count() == 0
        assert AsignacionPago.objects.filter(id_empresa=empresa_b).count() == 0
        assert EntidadSincronizada.objects.filter(id_instancia=inst_b).count() == 0

        with connection.cursor() as cur:
            if rls_test_role is not None:
                cur.execute(f'SET ROLE "{rls_test_role}"')
            try:
                rls.apply_context([empresa_a.id_empresa], bypass=False)
                assert list(FacturaCompra.objects.values_list("pk", flat=True)) == [fc_a.pk]
                assert list(AsignacionPago.objects.values_list("pk", flat=True)) == [asig_a.pk]

                rls.apply_context([empresa_b.id_empresa], bypass=False)
                assert FacturaCompra.objects.count() == 0
                assert AsignacionPago.objects.count() == 0
            finally:
                rls.apply_system_default()
                if rls_test_role is not None:
                    cur.execute("RESET ROLE")


class TestCoberturaBordesPR18:
    """Pruebas focalizadas de bordes, fallbacks y validaciones para cobertura >=95%."""

    def test_base_connector_pull_facturas_compra_no_soportado(self, empresa_a):
        from apps.integration_hub.connectors.base import BaseConnector, ConnectorNotSupportedError

        inst = _instancia_odoo(empresa_a)

        class _Dummy(BaseConnector):
            PROVIDER_NAME = "Dummy"

            def test_connection(self):
                return None

            def get_version_info(self):
                return {}

        dummy = _Dummy(inst)
        with pytest.raises(ConnectorNotSupportedError):
            dummy.pull_facturas_compra()

    def test_odoo_client_fields_cache_y_reconciliaciones_bordes(self):
        from apps.integration_hub.connectors.odoo.client import OdooCallError, OdooXMLRPCClient

        with patch.object(OdooXMLRPCClient, "_authenticate", return_value=1):
            client = OdooXMLRPCClient("https://qa.odoo.com", "qa", "user", "key")
            # 1. fields_get válido -> cacheado en segunda llamada
            with patch.object(
                client,
                "call",
                side_effect=[
                    {
                        "id": {"string": "ID"},
                        "name": {"string": "Name"},
                        "partner_id": {"string": "Partner"},
                        "payment_type": {"string": "Type"},
                        "partner_type": {"string": "Partner Type"},
                        "amount": {"string": "Amount"},
                        "date": {"string": "Date"},
                        "state": {"string": "State"},
                        "journal_id": {"string": "Journal"},
                        "currency_id": {"string": "Currency"},
                        "ref": {"string": "Ref"},
                    },
                    [{"id": 1, "name": "P1"}],
                ],
            ) as mock_call:
                pagos = client.get_pagos()
                assert len(pagos) == 1
                assert "ref" in mock_call.call_args_list[1].args[3]["fields"]
                assert client._get_model_fields("account.payment") == {
                    "id",
                    "name",
                    "partner_id",
                    "payment_type",
                    "partner_type",
                    "amount",
                    "date",
                    "state",
                    "journal_id",
                    "currency_id",
                    "ref",
                }
                assert mock_call.call_count == 2  # cache hit

            # 2. fields_get no-dict y OdooCallError -> retorna set vacío sin romper
            client._fields_cache.clear()
            with patch.object(client, "call", return_value=["no-dict"]):
                assert client._get_model_fields("account.payment") == set()
            client._fields_cache.clear()
            with patch.object(client, "call", side_effect=OdooCallError("boom")):
                assert client._get_model_fields("account.payment") == set()

            # 3. get_pagos cuando _get_model_fields es vacío usa campos estándar sin romper
            with patch.object(client, "call", return_value=[]):
                assert client.get_pagos(limite=5) == []

            # 4. get_reconciliaciones_pagos cortos y bordes
            assert client.get_reconciliaciones_pagos([]) == {}
            with patch.object(client, "call", return_value=[]):
                assert client.get_reconciliaciones_pagos([100]) == {}
            with patch.object(
                client,
                "call",
                return_value=[{"id": 1, "move_id": [100, "P1"], "matched_debit_ids": [], "matched_credit_ids": []}],
            ):
                assert client.get_reconciliaciones_pagos([100]) == {}

            # 5. get_reconciliaciones_pagos inbound (credit), no-factura (entry) filtrada y duplicado ignorado
            def _call_side(model, method, args, kwargs):
                if model == "account.move.line" and method == "search_read":
                    return [
                        {
                            "id": 10,
                            "move_id": [100, "PAY/IN"],
                            "account_type": "asset_receivable",
                            "matched_debit_ids": [50, 51, 50],
                            "matched_credit_ids": [],
                            "currency_id": [2, "USD"],
                        }
                    ]
                if model == "account.partial.reconcile" and method == "read":
                    return [
                        {
                            "id": 50,
                            "credit_move_id": [10, "PAY/IN"],
                            "debit_move_id": [20, "INV/1"],
                            "amount": 60.0,
                            "credit_amount_currency": 60.0,
                            "debit_amount_currency": 60.0,
                            "credit_currency_id": [2, "USD"],
                            "debit_currency_id": [2, "USD"],
                        },
                        {
                            "id": 51,
                            "credit_move_id": [10, "PAY/IN"],
                            "debit_move_id": [21, "ENTRY/1"],
                            "amount": 10.0,
                        },
                    ]
                if model == "account.move.line" and method == "read":
                    return [
                        {"id": 20, "move_id": [300, "INV/1"], "currency_id": [2, "USD"]},
                        {"id": 21, "move_id": [301, "ENTRY/1"], "currency_id": [2, "USD"]},
                        {"id": False, "move_id": None},
                    ]
                if model == "account.move" and method == "read":
                    return [
                        {"id": 300, "move_type": "out_invoice", "name": "INV/1", "currency_id": [2, "USD"]},
                        {"id": 301, "move_type": "entry", "name": "MISC/1", "currency_id": [2, "USD"]},
                    ]
                return []

            with patch.object(client, "call", side_effect=_call_side):
                recs = client.get_reconciliaciones_pagos([100])
                assert len(recs[100]) == 1
                assert recs[100][0]["move_id_externo"] == "300"
                assert recs[100][0]["monto_pago"] == Decimal("60.0")

            # 6. get_reconciliaciones_pagos cuando partial.read retorna []
            with patch.object(
                client,
                "call",
                side_effect=[
                    [{"id": 10, "move_id": [100, "P"], "matched_debit_ids": [50], "matched_credit_ids": []}],
                    [],
                ],
            ):
                assert client.get_reconciliaciones_pagos([100]) == {}

    def test_odoo_connector_tolera_error_en_get_reconciliaciones(self, empresa_a):
        from apps.integration_hub.connectors.odoo.client import OdooCallError
        from apps.integration_hub.connectors.odoo.connector import OdooConnector

        inst = _instancia_odoo(empresa_a)
        conn = OdooConnector(inst)
        fake_client = MagicMock()
        fake_client.get_pagos.return_value = [
            {
                "id": 77,
                "name": "P77",
                "partner_id": [5, "Cli"],
                "payment_type": "inbound",
                "partner_type": "customer",
                "amount": 10.0,
                "date": "2026-06-01",
                "state": "posted",
                "currency_id": [2, "USD"],
                "move_id": [770, "P77"],
                "reconciled_invoice_ids": [880],
            }
        ]
        fake_client.get_reconciliaciones_pagos.side_effect = OdooCallError("no partial access")
        conn._client = fake_client

        pagos = conn.pull_pagos()
        assert len(pagos) == 1
        assert pagos[0]["reconciliaciones"] == []
        assert pagos[0]["facturas_externas"] == ["880"]

    def test_banca_y_compras_serializer_y_conciliacion_historico_bordes(
        self, empresa_a, user_a, moneda_usd, metodo_efectivo
    ):
        from apps.finanzas.services_conciliacion_pagos import _resolver_contacto_documento

        contacto = Contacto.objects.create(
            id_empresa=empresa_a, nombre="Prov Mix Borde", rif="J-90000001-1", es_proveedor=True, es_cliente=True
        )
        prov = Proveedor.objects.create(
            id_empresa=empresa_a, razon_social="Prov Mix Borde", rif="J-90000001-1", contacto=contacto
        )
        cli = Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Prov Mix Borde", rif="J-90000001-1", contacto=contacto
        )
        oc = OrdenCompra.objects.create(
            id_empresa=empresa_a, id_proveedor=prov, numero_orden="OC-BORDE-1", fecha_orden=_hoy(), estado="APROBADA"
        )
        # FacturaCompra legacy sin id_proveedor (solo id_orden_compra)
        fc_legacy = FacturaCompra.objects.create(
            id_empresa=empresa_a,
            id_orden_compra=oc,
            id_proveedor=None,
            numero_factura="FC-LEG-1",
            fecha_emision=_hoy(),
            monto_total=Decimal("100.0000"),
        )
        assert _resolver_contacto_documento(empresa_a, fc_legacy) == contacto

        pago_eg = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto,
            tipo_operacion="EGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("100.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        aplicar_pago_a_documentos(
            pago_eg,
            [{"tipo_documento": "FACTURA_COMPRA", "id_documento": fc_legacy.pk, "monto_asignado_pago": "100.00"}],
            generar_asiento=False,
            modo_historico_externo=True,
        )
        assert _resolver_proveedor_de_pago(pago_eg, empresa_a) == prov

        # PATCH quitando id_orden_compra pero con id_proveedor -> 200; quitando ambos -> 400
        fc_ambos = FacturaCompra.objects.create(
            id_empresa=empresa_a,
            id_orden_compra=oc,
            id_proveedor=prov,
            numero_factura="FC-AMBOS-1",
            fecha_emision=_hoy(),
            monto_total=Decimal("80.0000"),
        )
        client = _client(user_a)
        assert (
            client.patch(
                f"/api/compras/facturas-compra/{fc_ambos.pk}/",
                {"id_orden_compra": None},
                format="json",
            ).status_code
            == 200
        )
        assert (
            client.patch(
                f"/api/compras/facturas-compra/{fc_ambos.pk}/",
                {"id_orden_compra": None, "id_proveedor": None},
                format="json",
            ).status_code
            == 400
        )

        # Histórico parcial -> pagada en CxC/CxP + FacturaFiscal + overpayment rechazado
        fv_hist = FacturaFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cli,
            numero_control="C-BORDE-1",
            numero_factura="F-BORDE-1",
            fecha_emision=_hoy(),
            monto_total=Decimal("100.0000"),
            id_moneda=moneda_usd,
            estado="PAGADA",
        )
        cxc = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cli,
            monto=Decimal("100.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy(),
            estado="emitida",
        )
        cxp = CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=prov,
            monto_total=Decimal("100.0000"),
            monto_pendiente=Decimal("100.0000"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy(),
            estado="PENDIENTE",
        )
        p_in = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto,
            tipo_operacion="INGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("250.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        aplicar_pago_a_documentos(
            p_in,
            [
                {"tipo_documento": "FACTURA_VENTA", "id_documento": fv_hist.pk, "monto_asignado_pago": "60.00"},
                {"tipo_documento": "CUENTA_POR_COBRAR", "id_documento": cxc.pk, "monto_asignado_pago": "40.00"},
            ],
            generar_asiento=False,
            modo_historico_externo=True,
        )
        cxc.refresh_from_db()
        assert cxc.estado == "parcial"
        # Overpayment sobre fv_hist (> 40 restante) debe fallar
        with pytest.raises(ConciliacionPagoError):
            aplicar_pago_a_documentos(
                p_in,
                [{"tipo_documento": "FACTURA_VENTA", "id_documento": fv_hist.pk, "monto_asignado_pago": "50.00"}],
                generar_asiento=False,
                modo_historico_externo=True,
            )
        # Completa cxc sin crear AbonoCxC
        aplicar_pago_a_documentos(
            p_in,
            [{"tipo_documento": "CUENTA_POR_COBRAR", "id_documento": cxc.pk, "monto_asignado_pago": "60.00"}],
            generar_asiento=False,
            modo_historico_externo=True,
        )
        cxc.refresh_from_db()
        assert cxc.estado == "pagada"
        assert AbonoCxC.objects.filter(cuenta_por_cobrar=cxc).count() == 0

        p_out = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto,
            tipo_operacion="EGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("100.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        aplicar_pago_a_documentos(
            p_out,
            [{"tipo_documento": "CUENTA_POR_PAGAR", "id_documento": cxp.pk, "monto_asignado_pago": "40.00"}],
            generar_asiento=False,
            modo_historico_externo=True,
        )
        cxp.refresh_from_db()
        assert cxp.estado == "PARCIAL"
        assert cxp.monto_pendiente == Decimal("60.0000")
        aplicar_pago_a_documentos(
            p_out,
            [{"tipo_documento": "CUENTA_POR_PAGAR", "id_documento": cxp.pk, "monto_asignado_pago": "60.00"}],
            generar_asiento=False,
            modo_historico_externo=True,
        )
        cxp.refresh_from_db()
        assert cxp.estado == "PAGADA"
        assert cxp.monto_pendiente == Decimal("0.0000")
        assert AbonoCxP.objects.filter(cuenta_por_pagar=cxp).count() == 0

    def test_sync_engine_omisiones_cxc_cxp_compra_y_moneda_fallback(self, empresa_a, moneda_usd):
        from apps.finanzas.models import TasaCambio

        eur, _ = Moneda.objects.get_or_create(
            codigo_iso="EUR",
            defaults={"nombre": "Euro", "simbolo": "€", "tipo_moneda": "fiat", "es_publica": True},
        )
        TasaCambio.objects.create(
            id_empresa=empresa_a,
            id_moneda_origen=eur,
            id_moneda_destino=moneda_usd,
            tipo_tasa="FIJA",
            valor_tasa=Decimal("1.10000000"),
            fecha_tasa=date(2026, 6, 15),
        )
        eng = SyncEngine()
        inst = _instancia_odoo(empresa_a)

        # Moneda desconocida cae a id_moneda_base de empresa
        assert eng._resolver_moneda_para_empresa(empresa_a, "ZZZ") == empresa_a.id_moneda_base

        # _upsert_factura_compra sin id_externo -> None
        assert eng._upsert_factura_compra({"id_externo": ""}, inst) is None

        # _upsert_pago omisiones esperadas
        assert eng._upsert_pago({"id_externo": "x1", "tipo": "internal", "tipo_socio": "customer"}, inst) is None
        assert (
            eng._upsert_pago(
                {
                    "id_externo": "x2",
                    "tipo": "inbound",
                    "tipo_socio": "customer",
                    "facturas_externas": ["99999"],
                },
                inst,
            )
            is None
        )
        assert (
            eng._upsert_pago(
                {"id_externo": "x3", "tipo": "inbound", "tipo_socio": "customer", "monto": "10.00"},
                inst,
            )
            is None
        )

        # Con moneda None -> None
        with patch.object(eng, "_resolver_moneda_para_empresa", return_value=None):
            assert (
                eng._upsert_pago(
                    {"id_externo": "x4", "tipo": "inbound", "tipo_socio": "customer", "monto": "10.00"},
                    inst,
                )
                is None
            )

        # Contacto creado desde Cliente / Proveedor existentes sin mapping previo + upgrade es_cliente/es_proveedor
        cli_ext = Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Cli Ext", rif="J-91000001-1", referencia_externa="c-ext"
        )
        prov_ext = Proveedor.objects.create(
            id_empresa=empresa_a, razon_social="Prov Ext", rif="J-91000002-2", referencia_externa="p-ext"
        )
        cxc_fb = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cli_ext,
            monto=Decimal("110.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy(),
            referencia_externa="odoo:out_invoice:7001",
        )
        cxp_fb = CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=prov_ext,
            monto_total=Decimal("80.0000"),
            monto_pendiente=Decimal("80.0000"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy(),
            referencia_externa="odoo:in_invoice:7002",
        )

        # Single invoice legacy path cross-currency (EUR -> USD vía TasaCambio) sobre CxC
        pk_in = eng._upsert_pago(
            {
                "id_externo": "9501",
                "tipo": "inbound",
                "tipo_socio": "customer",
                "socio_id_externo": "c-ext",
                "monto": "100.00",
                "fecha": "2026-06-15",
                "moneda": "EUR",
                "facturas_externas": ["7001"],
                "reconciliaciones": [],
            },
            inst,
        )
        pago_in = Pago.objects.get(pk=pk_in)
        assert pago_in.tipo_documento == "CXC"
        cxc_fb.refresh_from_db()
        assert cxc_fb.estado == "pagada"

        # Single invoice legacy path same-currency sobre CxP fallback
        pk_out = eng._upsert_pago(
            {
                "id_externo": "9502",
                "tipo": "outbound",
                "tipo_socio": "supplier",
                "socio_id_externo": "p-ext",
                "monto": "80.00",
                "fecha": "2026-06-15",
                "moneda": "USD",
                "facturas_externas": ["7002"],
                "reconciliaciones": [],
            },
            inst,
        )
        pago_out = Pago.objects.get(pk=pk_out)
        assert pago_out.tipo_documento == "CXP"
        assert pago_out.id_cxp_id == cxp_fb.pk
        prov_ext.refresh_from_db()

        # FacturaCompra sin CxP -> tipo_documento="COMPRA" + pago preexistente por referencia sin EntidadSincronizada
        fc_sin_cxp = FacturaCompra.objects.create(
            id_empresa=empresa_a,
            id_proveedor=prov_ext,
            numero_factura="FC-NOCXP",
            fecha_emision=_hoy(),
            monto_total=Decimal("50.0000"),
            referencia_externa="odoo:in_invoice:7003",
        )
        EntidadSincronizada.objects.create(
            id_instancia=inst,
            tipo_entidad="facturas_compra",
            id_externo="7003",
            id_omni=str(fc_sin_cxp.pk),
            modelo_omni="apps.compras.models.FacturaCompra",
        )
        contacto_prov = Contacto.objects.get(pk=prov_ext.contacto_id)
        Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_prov,
            tipo_operacion="EGRESO",
            tipo_documento="COMPRA",
            id_documento=fc_sin_cxp.pk,
            fecha_pago=timezone.now(),
            monto=Decimal("50.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=MetodoPago.objects.create(
                empresa=empresa_a, nombre_metodo="Import Test", tipo_metodo="OTRO"
            ),
            referencia="odoo:9503 Legacy",
        )
        pk_comp = eng._upsert_pago(
            {
                "id_externo": "9503",
                "tipo": "outbound",
                "tipo_socio": "supplier",
                "socio_id_externo": "p-ext",
                "monto": "50.00",
                "fecha": "2026-06-15",
                "moneda": "USD",
                "facturas_externas": ["7003"],
                "reconciliaciones": [
                    {
                        "partial_reconcile_id": "",
                        "move_id_externo": "no-existe",
                        "monto_pago": "10.00",
                        "monto_documento": "10.00",
                    },
                    {
                        "partial_reconcile_id": "z0",
                        "move_id_externo": "7003",
                        "monto_pago": "0.00",
                        "monto_documento": "0.00",
                    },
                    {
                        "partial_reconcile_id": "ok1",
                        "move_id_externo": "7003",
                        "monto_pago": "50.00",
                        "monto_documento": "50.00",
                        "moneda_documento": "USD",
                    },
                ],
                "referencia": "Legacy",
            },
            inst,
        )
        pago_comp = Pago.objects.get(pk=pk_comp)
        assert pago_comp.tipo_documento == "COMPRA"
        assert AsignacionPago.objects.filter(id_pago=pago_comp, estado="ACTIVA").count() == 1

        # Multiple docs sin reconciliaciones -> None
        cxc2 = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cli_ext,
            monto=Decimal("20.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy(),
            referencia_externa="odoo:out_invoice:7004",
        )
        assert cxc2.pk is not None
        assert (
            eng._upsert_pago(
                {
                    "id_externo": "9504",
                    "tipo": "inbound",
                    "tipo_socio": "customer",
                    "monto": "30.00",
                    "moneda": "USD",
                    "facturas_externas": ["7001", "7004"],
                    "reconciliaciones": [],
                },
                inst,
            )
            is None
        )

    def test_extra_banca_serializer_conciliacion_y_sync_bordes(
        self, empresa_a, empresa_b, user_a, moneda_usd, metodo_efectivo
    ):
        from apps.compras.models import RecepcionMercancia
        from apps.compras.serializers import FacturaCompraSerializer
        from apps.integration_hub.connectors.odoo.client import OdooXMLRPCClient

        # 1. _resolver_proveedor_de_pago cuando Pago.id_contacto=None (hits id_factura_compra paths)
        contacto = Contacto.objects.create(
            id_empresa=empresa_a, nombre="Prov Banca Sin Contacto", rif="J-92000001-1", es_proveedor=True
        )
        prov = Proveedor.objects.create(
            id_empresa=empresa_a, razon_social="Prov Banca Sin Contacto", rif="J-92000001-1", contacto=contacto
        )
        oc = OrdenCompra.objects.create(
            id_empresa=empresa_a, id_proveedor=prov, numero_orden="OC-BANCA-1", fecha_orden=_hoy(), estado="APROBADA"
        )
        fc_dir = FacturaCompra.objects.create(
            id_empresa=empresa_a,
            id_orden_compra=None,
            id_proveedor=prov,
            numero_factura="FC-B-1",
            fecha_emision=_hoy(),
            monto_total=Decimal("50.00"),
        )
        fc_oc = FacturaCompra.objects.create(
            id_empresa=empresa_a,
            id_orden_compra=oc,
            id_proveedor=None,
            numero_factura="FC-B-2",
            fecha_emision=_hoy(),
            monto_total=Decimal("50.00"),
        )
        p_sin_c1 = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=None,
            tipo_operacion="EGRESO",
            tipo_documento="COMPRA",
            id_documento=fc_dir.pk,
            fecha_pago=timezone.now(),
            monto=Decimal("50.00"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        AsignacionPago.objects.create(
            id_empresa=empresa_a,
            id_pago=p_sin_c1,
            id_contacto=contacto,
            tipo_documento="FACTURA_COMPRA",
            id_documento=str(fc_dir.pk),
            id_factura_compra=fc_dir,
            monto_asignado_pago=Decimal("50.00"),
            monto_asignado_documento=Decimal("50.00"),
            id_moneda_documento=moneda_usd,
            tasa_aplicada=Decimal("1.0"),
        )
        assert _resolver_proveedor_de_pago(p_sin_c1, empresa_a) == prov

        p_sin_c2 = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=None,
            tipo_operacion="EGRESO",
            tipo_documento="COMPRA",
            id_documento=fc_oc.pk,
            fecha_pago=timezone.now(),
            monto=Decimal("50.00"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        AsignacionPago.objects.create(
            id_empresa=empresa_a,
            id_pago=p_sin_c2,
            id_contacto=contacto,
            tipo_documento="FACTURA_COMPRA",
            id_documento=str(fc_oc.pk),
            id_factura_compra=fc_oc,
            monto_asignado_pago=Decimal("50.00"),
            monto_asignado_documento=Decimal("50.00"),
            id_moneda_documento=moneda_usd,
            tasa_aplicada=Decimal("1.0"),
        )
        assert _resolver_proveedor_de_pago(p_sin_c2, empresa_a) == prov

        # 2. FacturaCompraSerializer sin context (cubre inferencia empresa_ref por orden/prov/recepcion)
        rec = RecepcionMercancia.objects.create(id_empresa=empresa_a, id_orden_compra=oc, fecha_recepcion=_hoy())
        assert (
            FacturaCompraSerializer(
                data={
                    "id_orden_compra": str(oc.pk),
                    "numero_factura": "FC-SC-1",
                    "fecha_emision": _hoy().isoformat(),
                    "monto_total": "10.00",
                }
            ).is_valid()
            is True
        )
        assert (
            FacturaCompraSerializer(
                data={
                    "id_proveedor": str(prov.pk),
                    "numero_factura": "FC-SC-2",
                    "fecha_emision": _hoy().isoformat(),
                    "monto_total": "10.00",
                }
            ).is_valid()
            is True
        )
        assert (
            FacturaCompraSerializer(
                data={
                    "id_recepcion": str(rec.pk),
                    "numero_factura": "FC-SC-3",
                    "fecha_emision": _hoy().isoformat(),
                    "monto_total": "10.00",
                }
            ).is_valid()
            is False
        )

        # 3. _validar_estado_abierto_documento + modo_historico_externo=False en CxC
        cli = Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Cli Hist 2", rif="J-92000002-2", contacto=contacto
        )
        cxc_anulada = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cli,
            monto=Decimal("20.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy(),
            estado="anulada",
        )
        p_in = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto,
            tipo_operacion="INGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("50.00"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        with pytest.raises(ConciliacionPagoError):
            aplicar_pago_a_documentos(
                p_in,
                [
                    {
                        "tipo_documento": "CUENTA_POR_COBRAR",
                        "id_documento": cxc_anulada.pk,
                        "monto_asignado_pago": "10.00",
                    }
                ],
                generar_asiento=False,
                modo_historico_externo=True,
            )

        cxc_open = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cli,
            monto=Decimal("30.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy(),
            estado="emitida",
        )
        aplicar_pago_a_documentos(
            p_in,
            [{"tipo_documento": "CUENTA_POR_COBRAR", "id_documento": cxc_open.pk, "monto_asignado_pago": "30.00"}],
            generar_asiento=False,
            modo_historico_externo=False,
        )
        cxc_open.refresh_from_db()
        assert cxc_open.estado == "pagada"
        assert AbonoCxC.objects.filter(cuenta_por_cobrar=cxc_open).count() == 1

        # 4. SyncEngine bordes: contacto cross-tenant en tercero, mapping vacío, documento ya saldado, tasa faltante, preview/sync facturas_compra
        eng = SyncEngine()
        inst = _instancia_odoo(empresa_a)
        contacto_ajeno = Contacto.objects.create(
            id_empresa=empresa_b, nombre="Ajeno", rif="J-99990001-1", es_cliente=True
        )
        cli_cross = Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Cli Cross C", rif="J-92000003-3", contacto=contacto_ajeno
        )
        EntidadSincronizada.objects.create(
            id_instancia=inst, tipo_entidad="contactos", id_externo="map-c", id_omni=str(contacto.pk)
        )
        assert eng._asegurar_contacto_de_tercero(cli_cross, inst, id_externo="map-c", es_cliente=True) == contacto

        # Reconciliación sobre doc ya 100% saldado y doc con saldo menor que monto_doc_pr multimoneda
        eur, _ = Moneda.objects.get_or_create(
            codigo_iso="EUR", defaults={"nombre": "Euro", "simbolo": "€", "tipo_moneda": "fiat", "es_publica": True}
        )
        fv_full = FacturaFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cli,
            numero_control="C-FULL-1",
            numero_factura="F-FULL-1",
            fecha_emision=_hoy(),
            monto_total=Decimal("10.0000"),
            id_moneda=moneda_usd,
            estado="EMITIDA",
        )
        EntidadSincronizada.objects.create(
            id_instancia=inst, tipo_entidad="facturas_venta", id_externo="8801", id_omni=str(fv_full.pk)
        )
        EntidadSincronizada.objects.create(
            id_instancia=inst, tipo_entidad="contactos", id_externo="c-vacio", id_omni=""
        )
        # Pago 1 salda fv_full, Pago 2 intenta conciliar fv_full otra vez -> omite línea saldada
        eng._upsert_pago(
            {
                "id_externo": "9601",
                "tipo": "inbound",
                "tipo_socio": "customer",
                "socio_id_externo": "c-vacio",
                "socio_nombre": "Cli Nuevo",
                "monto": "10.00",
                "moneda": "USD",
                "facturas_externas": ["8801"],
                "reconciliaciones": [
                    {
                        "partial_reconcile_id": "p-f1",
                        "move_id_externo": "8801",
                        "monto_pago": "10.00",
                        "monto_documento": "10.00",
                        "moneda_documento": "USD",
                    }
                ],
            },
            inst,
        )
        eng._upsert_pago(
            {
                "id_externo": "9602",
                "tipo": "inbound",
                "tipo_socio": "customer",
                "socio_id_externo": "c-vacio",
                "monto": "10.00",
                "moneda": "USD",
                "facturas_externas": ["8801"],
                "reconciliaciones": [
                    {
                        "partial_reconcile_id": "p-f2",
                        "move_id_externo": "8801",
                        "monto_pago": "10.00",
                        "monto_documento": "10.00",
                        "moneda_documento": "USD",
                    }
                ],
            },
            inst,
        )

        # Single-doc legacy sin tasa de cambio (EUR vs USD sin TasaCambio en esa fecha) -> no revienta
        fv_eur_miss = FacturaFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cli,
            numero_control="C-EUR-M",
            numero_factura="F-EUR-M",
            fecha_emision=date(2025, 1, 1),
            monto_total=Decimal("25.0000"),
            id_moneda=moneda_usd,
            estado="EMITIDA",
        )
        EntidadSincronizada.objects.create(
            id_instancia=inst, tipo_entidad="facturas_venta", id_externo="8802", id_omni=str(fv_eur_miss.pk)
        )
        pk_no_tasa = eng._upsert_pago(
            {
                "id_externo": "9603",
                "tipo": "inbound",
                "tipo_socio": "customer",
                "socio_id_externo": "c-vacio",
                "monto": "20.00",
                "fecha": "2025-01-01",
                "moneda": eur.codigo_iso,
                "facturas_externas": ["8802"],
                "reconciliaciones": [],
            },
            inst,
        )
        assert Pago.objects.get(pk=pk_no_tasa).asignaciones.count() == 0

        # OdooXMLRPCClient get_reconciliaciones_pagos cuando no hay counterpart lines/moves y cuando move_type falta
        with patch.object(OdooXMLRPCClient, "_authenticate", return_value=1):
            cli_odoo = OdooXMLRPCClient("https://qa.odoo.com", "qa", "user", "key")
            with patch.object(
                cli_odoo,
                "call",
                side_effect=[
                    [{"id": 10, "move_id": [100, "P"], "matched_debit_ids": [55], "matched_credit_ids": []}],
                    [{"id": 55, "credit_move_id": [10, "P"], "debit_move_id": [10, "P"], "amount": 5.0}],
                ],
            ):
                assert cli_odoo.get_reconciliaciones_pagos([100]) == {}

        # API preview/sync facturas_compra con conector mockeado (cero red)
        from apps.integration_hub.connectors.registry import registry

        fake_conn = MagicMock()
        fake_conn.supports.return_value = True
        fake_conn.pull_facturas_compra.return_value = []
        with patch.object(registry, "get_connector", return_value=fake_conn):
            resp_prev = _client(user_a).get(f"/api/integration-hub/instancias/{inst.pk}/preview/facturas_compra/")
            assert resp_prev.status_code == 200
            resp_sync = _client(user_a).post(
                f"/api/integration-hub/instancias/{inst.pk}/sync/",
                {"tipo_entidad": "facturas_compra"},
                format="json",
            )
            assert resp_sync.status_code == 202

        # 5. Cobertura adicional de bordes internos en services_conciliacion_pagos y SyncEngine
        from types import SimpleNamespace
        from apps.finanzas.services_conciliacion_pagos import (
            _resolver_contacto_documento,
            _saldo_aplicable_historico_documento,
        )

        with pytest.raises(ConciliacionPagoError, match="no tiene proveedor ni orden de compra"):
            _resolver_contacto_documento(
                empresa_a,
                FacturaCompra(
                    id_empresa=empresa_a, numero_factura="FC-HUERF", fecha_emision=_hoy(), monto_total=Decimal("10")
                ),
            )
        with pytest.raises(ConciliacionPagoError, match="no soportado para cálculo histórico"):
            _saldo_aplicable_historico_documento(empresa_a.pk, "DESCONOCIDO", object())

        # _asegurar_contacto_de_tercero rellena mapping vacío + _asegurar_contacto_de_documento FacturaFiscal/FacturaCompra OC/None
        EntidadSincronizada.objects.create(
            id_instancia=inst, tipo_entidad="contactos", id_externo="map-vacio", id_omni=""
        )
        cli_sin_c = Cliente.objects.create(id_empresa=empresa_a, razon_social="Cli Sin C", rif="J-92000088-1")
        c_gen = eng._asegurar_contacto_de_tercero(cli_sin_c, inst, id_externo="map-vacio", es_cliente=True)
        assert EntidadSincronizada.objects.get(
            id_instancia=inst, tipo_entidad="contactos", id_externo="map-vacio"
        ).id_omni == str(c_gen.pk)

        cli_ff_legacy = Cliente.objects.create(id_empresa=empresa_a, razon_social="Cli FF Legacy", rif="J-92000089-1")
        ff_leg = FacturaFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cli_ff_legacy,
            numero_control="C-LEG-1",
            numero_factura="F-LEG-1",
            fecha_emision=_hoy(),
            monto_total=Decimal("10.00"),
            id_moneda=moneda_usd,
            estado="EMITIDA",
        )
        assert eng._asegurar_contacto_de_documento(ff_leg, inst, id_externo="") is not None

        prov_oc_leg = Proveedor.objects.create(id_empresa=empresa_a, razon_social="Prov OC Leg", rif="J-92000090-1")
        oc_leg = OrdenCompra.objects.create(
            id_empresa=empresa_a,
            id_proveedor=prov_oc_leg,
            numero_orden="OC-LEG-1",
            fecha_orden=_hoy(),
            estado="APROBADA",
        )
        fc_oc_leg = FacturaCompra.objects.create(
            id_empresa=empresa_a,
            id_orden_compra=oc_leg,
            id_proveedor=None,
            numero_factura="FC-LEG-1",
            fecha_emision=_hoy(),
            monto_total=Decimal("10.00"),
        )
        assert eng._asegurar_contacto_de_documento(fc_oc_leg, inst, id_externo="") is not None
        assert eng._asegurar_contacto_de_documento(SimpleNamespace(), inst) is None

        # _upsert_factura_compra con proveedor no resoluble -> None, y sin saldo_pendiente explícito
        assert (
            eng._upsert_factura_compra(
                {"id_externo": "9900", "numero": "BILL/SINPROV", "total": "10.00"},
                inst,
            )
            is None
        )
        fc_pag_pk = eng._upsert_factura_compra(
            {
                "id_externo": "9901",
                "numero": "BILL/AUTOSALDO",
                "proveedor_id_externo": "",
                "proveedor_nombre": "Prov AutoSaldo",
                "total": "40.00",
                "estado_pago": "paid",
                "saldo_pendiente": None,
            },
            inst,
        )
        cxp_pag = CuentaPorPagar.objects.get(id_factura_compra_id=fc_pag_pk)
        assert cxp_pag.estado == "PAGADA"
        assert cxp_pag.monto_pendiente == Decimal("0")

        # _resolver_o_crear_contacto_desde_pago vía Cliente/Proveedor(referencia_externa), solo nombre, y upgrade de roles
        Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Cli Ref Ext", rif="J-92000091-1", referencia_externa="ext-cli-91"
        )
        c_ext_cli = eng._resolver_o_crear_contacto_desde_pago(
            {"socio_id_externo": "ext-cli-91"},
            inst,
            es_cliente=True,
            es_proveedor=True,
            docs_resueltos=[],
        )
        assert c_ext_cli is not None and c_ext_cli.es_cliente and c_ext_cli.es_proveedor

        Proveedor.objects.create(
            id_empresa=empresa_a, razon_social="Prov Ref Ext", rif="J-92000092-1", referencia_externa="ext-prov-92"
        )
        c_ext_prov = eng._resolver_o_crear_contacto_desde_pago(
            {"socio_id_externo": "ext-prov-92"},
            inst,
            es_cliente=False,
            es_proveedor=True,
            docs_resueltos=[],
        )
        assert c_ext_prov is not None and c_ext_prov.es_proveedor

        c_solo_nom = eng._resolver_o_crear_contacto_desde_pago(
            {"socio_id_externo": "", "socio_nombre": "Socio Solo Nombre"},
            inst,
            es_cliente=True,
            es_proveedor=False,
            docs_resueltos=[],
        )
        assert c_solo_nom is not None and c_solo_nom.nombre == "Socio Solo Nombre"

        # _upsert_pago multimoneda capado por saldo_doc_rest (monto_doc_eff < monto_doc_pr) y disponible_restante agotado
        ves, _ = Moneda.objects.get_or_create(
            codigo_iso="VES",
            defaults={"nombre": "Bolívar", "simbolo": "Bs", "tipo_moneda": "fiat", "es_publica": True},
        )
        fv_ves = FacturaFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cli,
            numero_control="C-VES-CAP",
            numero_factura="F-VES-CAP",
            fecha_emision=_hoy(),
            monto_total=Decimal("500.0000"),
            id_moneda=ves,
            estado="EMITIDA",
        )
        fv_usd_2 = FacturaFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cli,
            numero_control="C-USD-CAP",
            numero_factura="F-USD-CAP",
            fecha_emision=_hoy(),
            monto_total=Decimal("20.0000"),
            id_moneda=moneda_usd,
            estado="EMITIDA",
        )
        EntidadSincronizada.objects.create(
            id_instancia=inst, tipo_entidad="facturas_venta", id_externo="8810", id_omni=str(fv_ves.pk)
        )
        EntidadSincronizada.objects.create(
            id_instancia=inst, tipo_entidad="facturas_venta", id_externo="8811", id_omni=str(fv_usd_2.pk)
        )
        pk_cap_multi = eng._upsert_pago(
            {
                "id_externo": "9610",
                "tipo": "inbound",
                "tipo_socio": "customer",
                "socio_id_externo": "c-vacio",
                "monto": "20.00",
                "moneda": "USD",
                "facturas_externas": ["8810", "8811"],
                "reconciliaciones": [
                    {
                        "partial_reconcile_id": "p-cap-1",
                        "move_id_externo": "8810",
                        "monto_pago": "20.00",
                        "monto_documento": "1000.00",  # capado por saldo 500 VES -> monto_pago_eff = 10 USD
                        "moneda_documento": "VES",
                    },
                    {
                        "partial_reconcile_id": "p-cap-2",
                        "move_id_externo": "8811",
                        "monto_pago": "10.00",
                        "monto_documento": "10.00",
                        "moneda_documento": "USD",
                    },
                    {
                        "partial_reconcile_id": "p-cap-3",
                        "move_id_externo": "8811",
                        "monto_pago": "5.00",  # disponible_restante == 0 -> continue l.1481
                        "monto_documento": "5.00",
                        "moneda_documento": "USD",
                    },
                ],
            },
            inst,
        )
        asigs_cap = list(Pago.objects.get(pk=pk_cap_multi).asignaciones.order_by("id_asignacion"))
        assert len(asigs_cap) == 2
        assert asigs_cap[0].monto_asignado_pago == Decimal("10.0000")
        assert asigs_cap[0].monto_asignado_documento == Decimal("500.0000")
        assert asigs_cap[1].monto_asignado_pago == Decimal("10.0000")


@pytest.mark.django_db(transaction=True)
class TestMigracion0013FacturaCompra:
    def test_migracion_0013_backfill_forward_idempotente_y_reversible(self, empresa_a, empresa_b):
        import importlib
        from django.apps import apps as django_apps
        from django.db.migrations.executor import MigrationExecutor

        prov_a = Proveedor.objects.create(id_empresa=empresa_a, razon_social="Prov Mig A", rif="J-93000001-1")
        prov_a2 = Proveedor.objects.create(id_empresa=empresa_a, razon_social="Prov Mig A2", rif="J-93000002-2")
        prov_b = Proveedor.objects.create(id_empresa=empresa_b, razon_social="Prov Mig B", rif="J-93000003-3")
        oc_a = OrdenCompra.objects.create(
            id_empresa=empresa_a, id_proveedor=prov_a, numero_orden="OC-MIG-A", fecha_orden=_hoy(), estado="APROBADA"
        )
        oc_b = OrdenCompra.objects.create(
            id_empresa=empresa_b, id_proveedor=prov_b, numero_orden="OC-MIG-B", fecha_orden=_hoy(), estado="APROBADA"
        )

        executor = MigrationExecutor(connection)
        executor.migrate([("compras", "0012_trazabilidad_procurement")])
        try:
            targets_0012 = [
                ("compras", "0012_trazabilidad_procurement") if app == "compras" else (app, name)
                for app, name in executor.loader.graph.leaf_nodes()
            ]
            old_apps = executor.loader.project_state(targets_0012).apps
            OldFactura = old_apps.get_model("compras", "FacturaCompra")
            with rls.rls_bypass():
                fc_ok = OldFactura.objects.create(
                    id_empresa_id=empresa_a.pk,
                    id_orden_compra_id=oc_a.pk,
                    numero_factura="FC-MIG-OK",
                    fecha_emision=_hoy(),
                    monto_total=Decimal("120.0000"),
                )
                fc_cruz = OldFactura.objects.create(
                    id_empresa_id=empresa_a.pk,
                    id_orden_compra_id=oc_b.pk,
                    numero_factura="FC-MIG-CRUZ",
                    fecha_emision=_hoy(),
                    monto_total=Decimal("10.0000"),
                )

            executor = MigrationExecutor(connection)
            executor.migrate([("compras", "0013_facturacompra_orden_opcional_y_proveedor")])

            fc_ok_new = FacturaCompra.objects.get(pk=fc_ok.pk)
            fc_cruz_new = FacturaCompra.objects.get(pk=fc_cruz.pk)
            assert fc_ok_new.id_proveedor_id == prov_a.pk
            assert fc_cruz_new.id_proveedor_id is None

            # Preserva id_proveedor existente en corrida idempotente
            fc_pres = FacturaCompra.objects.create(
                id_empresa=empresa_a,
                id_orden_compra=oc_a,
                id_proveedor=prov_a2,
                numero_factura="FC-MIG-PRES",
                fecha_emision=_hoy(),
                monto_total=Decimal("30.0000"),
            )
            mod = importlib.import_module("apps.compras.migrations.0013_facturacompra_orden_opcional_y_proveedor")
            with connection.schema_editor() as editor:
                mod._backfill_proveedor_factura_compra(django_apps, editor)
            fc_pres.refresh_from_db()
            assert fc_pres.id_proveedor_id == prov_a2.pk
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
