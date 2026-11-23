"""Tests de integración Plan 09 Ola 1B-2: Ámbito documental, Perfil Fiscal VE y Nota de Débito Fiscal."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.utils import ProgrammingError
from django.utils import timezone

from apps.core import rls
from tests.factories import (
    AlmacenFactory,
    ClienteFactory,
    ProductoFactory,
)

pytestmark = [pytest.mark.django_db]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_contabilidad_nd(empresa):
    """Crea cuentas contables, período abierto y mapeos NOTA_DEBITO_FISCAL* para la empresa."""
    from apps.contabilidad.models import MapeoContable, PeriodoContable, PlanCuentas

    cta_cxc = PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta="1.1.02.01",
        nombre_cuenta="Cuentas por Cobrar Clientes",
        tipo_cuenta="ACTIVO",
        naturaleza="DEUDORA",
        nivel=4,
    )
    cta_nd = PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta="4.1.01.05",
        nombre_cuenta="Notas de Débito e Intereses",
        tipo_cuenta="INGRESO",
        naturaleza="ACREEDORA",
        nivel=4,
    )
    cta_iva = PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta="2.1.04.01",
        nombre_cuenta="IVA Débito Fiscal",
        tipo_cuenta="PASIVO",
        naturaleza="ACREEDORA",
        nivel=4,
    )

    hoy = timezone.localdate()
    PeriodoContable.objects.create(
        id_empresa=empresa,
        anio=hoy.year,
        mes=hoy.month,
        estado="ABIERTO",
    )

    MapeoContable.objects.create(
        id_empresa=empresa,
        tipo_asiento="NOTA_DEBITO_FISCAL",
        cuenta_debe=cta_cxc,
        cuenta_haber=cta_nd,
    )
    MapeoContable.objects.create(
        id_empresa=empresa,
        tipo_asiento="NOTA_DEBITO_FISCAL_IVA",
        cuenta_debe=cta_cxc,
        cuenta_haber=cta_iva,
    )
    return cta_cxc, cta_nd, cta_iva


def _crear_mcp_token(empresa, user, scopes=None):
    from apps.core.models import CapabilityToken

    return CapabilityToken.objects.create(
        empresa=empresa,
        nombre="MCP Ventas ND Test",
        scopes=scopes or ["ventas:read"],
        activo=True,
        creado_por=user,
    )


# ---------------------------------------------------------------------------
# 1. Perfil Fiscal VE en core.Contacto + Filtros ViewSet
# ---------------------------------------------------------------------------


class TestPerfilFiscalContactoVE:
    def test_crear_contacto_con_perfil_fiscal_y_filtros(self, client_a, empresa_a):
        payload_esp = {
            "id_empresa": str(empresa_a.id_empresa),
            "nombre": "Inversiones Los Llanos C.A.",
            "razon_social": "Inversiones Los Llanos C.A.",
            "rif": "J-40123456-0",
            "es_cliente": True,
            "tipo_contribuyente": "ESPECIAL",
            "tipo_persona_fiscal": "PJDO",
            "es_agente_retencion_iva": True,
            "porcentaje_retencion_iva": "75.00",
            "es_agente_retencion_islr": True,
            "exento_islr": False,
            "estado": "Carabobo",
            "municipio": "Valencia",
        }
        resp = client_a.post("/api/core/contactos/", payload_esp, format="json")
        assert resp.status_code == 201, resp.data
        assert resp.data["tipo_contribuyente"] == "ESPECIAL"
        assert resp.data["tipo_persona_fiscal"] == "PJDO"
        assert resp.data["es_agente_retencion_iva"] is True
        assert Decimal(str(resp.data["porcentaje_retencion_iva"])) == Decimal("75.00")
        assert resp.data["es_agente_retencion_islr"] is True
        assert resp.data["estado"] == "Carabobo"

        # Segundo contacto: ordinario exento ISLR
        payload_ord = {
            "id_empresa": str(empresa_a.id_empresa),
            "nombre": "Fundación Cultural Sur",
            "razon_social": "Fundación Cultural Sur",
            "rif": "J-30111222-3",
            "es_cliente": True,
            "tipo_contribuyente": "ORDINARIO",
            "tipo_persona_fiscal": "PNR",
            "es_agente_retencion_iva": False,
            "porcentaje_retencion_iva": "0.00",
            "es_agente_retencion_islr": False,
            "exento_islr": True,
            "estado": "Miranda",
            "municipio": "Chacao",
        }
        resp2 = client_a.post("/api/core/contactos/", payload_ord, format="json")
        assert resp2.status_code == 201, resp2.data

        # Filtros en ContactoViewSet
        r_esp = client_a.get("/api/core/contactos/?tipo_contribuyente=ESPECIAL")
        assert r_esp.status_code == 200
        assert [c["nombre"] for c in r_esp.data["results"]] == ["Inversiones Los Llanos C.A."]

        r_ret_iva = client_a.get("/api/core/contactos/?es_agente_retencion_iva=true")
        assert r_ret_iva.status_code == 200
        assert len(r_ret_iva.data["results"]) == 1

        r_ret_islr = client_a.get("/api/core/contactos/?es_agente_retencion_islr=true")
        assert r_ret_islr.status_code == 200
        assert len(r_ret_islr.data["results"]) == 1

        r_exento = client_a.get("/api/core/contactos/?exento_islr=true")
        assert r_exento.status_code == 200
        assert [c["nombre"] for c in r_exento.data["results"]] == ["Fundación Cultural Sur"]

    @pytest.mark.parametrize("pct_invalido", ["-0.01", "100.01", "150.00"])
    def test_porcentaje_retencion_iva_fuera_de_rango_400(self, client_a, empresa_a, pct_invalido):
        resp = client_a.post(
            "/api/core/contactos/",
            {
                "id_empresa": str(empresa_a.id_empresa),
                "nombre": "Contacto Rango Mal",
                "razon_social": "Contacto Rango Mal",
                "rif": "J-40999888-1",
                "es_agente_retencion_iva": True,
                "porcentaje_retencion_iva": pct_invalido,
            },
            format="json",
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 2. NotaDebitoFiscal: CRUD, Emitir, RLS, Libros SENIAT y MCP
# ---------------------------------------------------------------------------


class TestNotaDebitoFiscalFlujoCompleto:
    def test_emitir_nota_debito_genera_cxc_asientos_y_libros_seniat(
        self, client_a, client_b, empresa_a, empresa_b, user_a, moneda_usd
    ):
        from apps.contabilidad.models import AsientoContable
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar
        from apps.fiscal.libros_seniat import (
            generar_libro_ventas_pdf,
            generar_libro_ventas_txt,
        )
        from apps.ventas.mcp import ventas_listar_notas_debito_fiscales
        from apps.ventas.models import FacturaFiscal, NotaDebitoFiscal, NotaVenta

        _setup_contabilidad_nd(empresa_a)
        cliente_a = ClienteFactory(id_empresa=empresa_a, razon_social="Cliente ND S.A.", rif="J-22334455-6")
        hoy = timezone.localdate()

        factura = FacturaFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_a,
            numero_control="CTRL-FAC-ND-01",
            numero_factura="FAC-ND-0001",
            fecha_emision=hoy,
            base_imponible=Decimal("1000.00"),
            monto_iva=Decimal("160.00"),
            monto_total=Decimal("1160.00"),
            id_moneda=moneda_usd,
            estado="EMITIDA",
        )

        # NotaVenta GERENCIAL entregada NO debe aparecer en Libro de Ventas
        NotaVenta.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_a,
            numero_nota="NV-GER-EXCL-01",
            fecha_nota=hoy,
            estado="ENTREGADA",
        )

        # Crear NotaDebitoFiscal vía API en BORRADOR
        resp_create = client_a.post(
            "/api/ventas/notas-debito-fiscales/",
            {
                "id_empresa": str(empresa_a.id_empresa),
                "id_cliente": str(cliente_a.id_cliente),
                "id_factura_origen": str(factura.id_factura),
                "fecha_emision": str(hoy),
                "base_imponible": "100.00",
                "monto_iva": "16.00",
                "monto_total": "116.00",
                "id_moneda": str(moneda_usd.id_moneda),
                "tasa_cambio": "1.000000",
                "motivo": "INTERES_MORA",
                "observaciones": "Recargo por mora contractual",
            },
            format="json",
        )
        assert resp_create.status_code == 201, resp_create.data
        nd_id = resp_create.data["id_nota_debito_fiscal"]
        assert resp_create.data["estado"] == "BORRADOR"
        assert resp_create.data["ambito"] == "FISCAL"

        # Crear línea de detalle vía API
        resp_det = client_a.post(
            "/api/ventas/detalles-nota-debito-fiscal/",
            {
                "id_nota_debito_fiscal": nd_id,
                "descripcion": "Interés moratorio mes vencido",
                "cantidad": "1.0000",
                "precio_unitario": "100.0000",
                "alicuota_iva": "16.00",
                "subtotal": "100.0000",
                "monto_impuesto": "16.0000",
                "total_linea": "116.0000",
            },
            format="json",
        )
        assert resp_det.status_code == 201, resp_det.data

        # Aislamiento B no ve ni puede emitir ND de A
        assert client_b.get(f"/api/ventas/notas-debito-fiscales/{nd_id}/").status_code == 404

        # Emitir con idempotencia
        idem_headers = {"HTTP_IDEMPOTENCY_KEY": "nd-emitir-key-001"}
        resp_emit = client_a.post(
            f"/api/ventas/notas-debito-fiscales/{nd_id}/emitir/",
            {},
            format="json",
            **idem_headers,
        )
        assert resp_emit.status_code == 200, resp_emit.data
        assert resp_emit.data["nota_debito"]["estado"] == "EMITIDA"
        nro_nd = resp_emit.data["nota_debito"]["numero_nota_debito"]
        assert nro_nd
        assert resp_emit.data["cxc_id"]
        assert resp_emit.data["asiento_id"]
        assert resp_emit.data["asiento_iva_id"]

        # Reintento idempotente retorna exactamente lo mismo sin duplicar CxC/asientos
        resp_replay = client_a.post(
            f"/api/ventas/notas-debito-fiscales/{nd_id}/emitir/",
            {},
            format="json",
            **idem_headers,
        )
        assert resp_replay.status_code == 200
        assert resp_replay.data["cxc_id"] == resp_emit.data["cxc_id"]
        assert CuentaPorCobrar.objects.filter(empresa=empresa_a, tipo_operacion="NOTA_DEBITO_FISCAL").count() == 1

        # Segundo emitir SIN misma Idempotency-Key falla controlado con domain_error_response
        resp_double = client_a.post(
            f"/api/ventas/notas-debito-fiscales/{nd_id}/emitir/",
            {},
            format="json",
        )
        assert resp_double.status_code == 400
        assert resp_double.data["codigo"] == "NOTA_DEBITO_ERROR"

        # Inmutabilidad fiscal tras emitir: PATCH/DELETE ND y POST/DELETE Detalle rechazados (400)
        resp_patch = client_a.patch(
            f"/api/ventas/notas-debito-fiscales/{nd_id}/",
            {"observaciones": "Intento post emisión"},
            format="json",
        )
        assert resp_patch.status_code == 400
        assert resp_patch.data["codigo"] == "NOTA_DEBITO_INMUTABLE"

        resp_del = client_a.delete(f"/api/ventas/notas-debito-fiscales/{nd_id}/")
        assert resp_del.status_code == 400
        assert resp_del.data["codigo"] == "NOTA_DEBITO_INMUTABLE"

        det_id = resp_det.data["id_detalle_nota_debito"]
        resp_det_del = client_a.delete(f"/api/ventas/detalles-nota-debito-fiscal/{det_id}/")
        assert resp_det_del.status_code == 400
        assert resp_det_del.data["codigo"] == "NOTA_DEBITO_INMUTABLE"

        resp_det_post = client_a.post(
            "/api/ventas/detalles-nota-debito-fiscal/",
            {
                "id_nota_debito_fiscal": nd_id,
                "descripcion": "Extra inválido",
                "cantidad": "1.0000",
                "precio_unitario": "10.0000",
                "alicuota_iva": "16.00",
                "subtotal": "10.0000",
                "monto_impuesto": "1.6000",
                "total_linea": "11.6000",
            },
            format="json",
        )
        assert resp_det_post.status_code == 400

        # Múltiples borradores sin número asignado no colisionan en unique constraint parcial
        draft_ids = []
        for idx in range(2):
            r_draft = client_a.post(
                "/api/ventas/notas-debito-fiscales/",
                {
                    "id_empresa": str(empresa_a.id_empresa),
                    "id_cliente": str(cliente_a.id_cliente),
                    "id_factura_origen": str(factura.id_factura),
                    "fecha_emision": str(hoy),
                    "base_imponible": "10.00",
                    "monto_iva": "1.60",
                    "monto_total": "11.60",
                    "id_moneda": str(moneda_usd.id_moneda),
                    "motivo": "CARGO_ADICIONAL",
                    "observaciones": f"Borrador paralelo {idx}",
                },
                format="json",
            )
            assert r_draft.status_code == 201, r_draft.data
            draft_ids.append(r_draft.data["id_nota_debito_fiscal"])

        # En BORRADOR sí se permite editar/eliminar nota y detalles; validar líneas negativas
        draft_id = draft_ids[0]
        r_det_bad_qty = client_a.post(
            "/api/ventas/detalles-nota-debito-fiscal/",
            {
                "id_nota_debito_fiscal": draft_id,
                "descripcion": "Cantidad cero",
                "cantidad": "0.0000",
                "precio_unitario": "10.0000",
                "alicuota_iva": "16.00",
                "subtotal": "0.0000",
                "monto_impuesto": "0.0000",
                "total_linea": "0.0000",
            },
            format="json",
        )
        assert r_det_bad_qty.status_code == 400
        r_det_bad_price = client_a.post(
            "/api/ventas/detalles-nota-debito-fiscal/",
            {
                "id_nota_debito_fiscal": draft_id,
                "descripcion": "Precio negativo",
                "cantidad": "1.0000",
                "precio_unitario": "-1.0000",
                "alicuota_iva": "-5.00",
                "subtotal": "0.0000",
                "monto_impuesto": "0.0000",
                "total_linea": "0.0000",
            },
            format="json",
        )
        assert r_det_bad_price.status_code == 400

        r_det_ok = client_a.post(
            "/api/ventas/detalles-nota-debito-fiscal/",
            {
                "id_nota_debito_fiscal": draft_id,
                "descripcion": "Detalle borrable",
                "cantidad": "1.0000",
                "precio_unitario": "10.0000",
                "alicuota_iva": "16.00",
                "subtotal": "10.0000",
                "monto_impuesto": "1.6000",
                "total_linea": "11.6000",
            },
            format="json",
        )
        assert r_det_ok.status_code == 201
        assert (
            client_a.delete(
                f"/api/ventas/detalles-nota-debito-fiscal/{r_det_ok.data['id_detalle_nota_debito']}/"
            ).status_code
            == 204
        )
        assert (
            client_a.patch(
                f"/api/ventas/notas-debito-fiscales/{draft_id}/",
                {"observaciones": "Editada en borrador"},
                format="json",
            ).status_code
            == 200
        )
        assert client_a.delete(f"/api/ventas/notas-debito-fiscales/{draft_id}/").status_code == 204

        # Validaciones de serializer: cliente mismatch, monto negativo y monto total <= 0
        cliente_otro = ClienteFactory(id_empresa=empresa_a, rif="J-22339999-0")
        r_mismatch = client_a.post(
            "/api/ventas/notas-debito-fiscales/",
            {
                "id_empresa": str(empresa_a.id_empresa),
                "id_cliente": str(cliente_otro.id_cliente),
                "id_factura_origen": str(factura.id_factura),
                "fecha_emision": str(hoy),
                "base_imponible": "10.00",
                "monto_iva": "1.60",
                "monto_total": "11.60",
                "id_moneda": str(moneda_usd.id_moneda),
            },
            format="json",
        )
        assert r_mismatch.status_code == 400
        assert "id_cliente" in r_mismatch.data

        r_neg = client_a.post(
            "/api/ventas/notas-debito-fiscales/",
            {
                "id_empresa": str(empresa_a.id_empresa),
                "id_cliente": str(cliente_a.id_cliente),
                "id_factura_origen": str(factura.id_factura),
                "fecha_emision": str(hoy),
                "base_imponible": "-5.00",
                "monto_iva": "0.00",
                "monto_total": "1.00",
                "id_moneda": str(moneda_usd.id_moneda),
            },
            format="json",
        )
        assert r_neg.status_code == 400
        assert "base_imponible" in r_neg.data

        r_zero = client_a.post(
            "/api/ventas/notas-debito-fiscales/",
            {
                "id_empresa": str(empresa_a.id_empresa),
                "id_cliente": str(cliente_a.id_cliente),
                "id_factura_origen": str(factura.id_factura),
                "fecha_emision": str(hoy),
                "base_imponible": "0.00",
                "monto_iva": "0.00",
                "monto_total": "0.00",
                "id_moneda": str(moneda_usd.id_moneda),
            },
            format="json",
        )
        assert r_zero.status_code == 400
        assert "monto_total" in r_zero.data

        # Asientos generados en ámbito FISCAL
        asiento_base = AsientoContable.objects.get(pk=resp_emit.data["asiento_id"])
        asiento_iva = AsientoContable.objects.get(pk=resp_emit.data["asiento_iva_id"])
        assert asiento_base.ambito == "FISCAL"
        assert asiento_iva.ambito == "FISCAL"

        # Libros de Ventas TXT y PDF incluyen factura + ND y excluyen NV gerencial
        txt_ventas = generar_libro_ventas_txt(empresa_a, hoy, hoy)
        assert "FAC-ND-0001" in txt_ventas
        assert nro_nd in txt_ventas
        assert "NV-GER-EXCL-01" not in txt_ventas

        pdf_bytes = generar_libro_ventas_pdf(empresa_a, hoy, hoy)
        assert pdf_bytes.startswith(b"%PDF-")

        # Tool MCP ventas_listar_notas_debito_fiscales
        tok = _crear_mcp_token(empresa_a, user_a)
        res_mcp = ventas_listar_notas_debito_fiscales(str(tok.token), str(empresa_a.id_empresa), estado="EMITIDA")
        assert len(res_mcp) == 1
        assert res_mcp[0]["id_nota_debito_fiscal"] == nd_id
        assert res_mcp[0]["numero_nota_debito"] == nro_nd

        # __str__ de NotaDebitoFiscal y DetalleNotaDebitoFiscal
        nd_obj = NotaDebitoFiscal.objects.get(pk=nd_id)
        assert nro_nd in str(nd_obj)
        assert nro_nd in str(nd_obj.detalles.first())

    def test_validaciones_emision_nota_debito(self, client_a, empresa_a, empresa_b, moneda_usd):
        from apps.fiscal.models import PeriodoFiscal
        from apps.ventas.models import FacturaFiscal, NotaDebitoFiscal
        from apps.ventas.services import VentaError, emitir_nota_debito_fiscal

        cliente_a = ClienteFactory(id_empresa=empresa_a, rif="J-22000111-1")
        cliente_b = ClienteFactory(id_empresa=empresa_b, rif="J-22000222-2")
        hoy = timezone.localdate()

        fac_b = FacturaFiscal.objects.create(
            id_empresa=empresa_b,
            id_cliente=cliente_b,
            numero_control="CTRL-B-1",
            numero_factura="FAC-B-1",
            fecha_emision=hoy,
            base_imponible=Decimal("100.00"),
            monto_iva=Decimal("16.00"),
            monto_total=Decimal("116.00"),
            id_moneda=moneda_usd,
            estado="EMITIDA",
        )
        nd_cross = NotaDebitoFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_a,
            id_factura_origen=fac_b,
            fecha_emision=hoy,
            base_imponible=Decimal("50.00"),
            monto_iva=Decimal("8.00"),
            monto_total=Decimal("58.00"),
            id_moneda=moneda_usd,
        )
        with pytest.raises(VentaError, match="no pertenece a la empresa"):
            emitir_nota_debito_fiscal(nd_cross)

        fac_anulada = FacturaFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_a,
            numero_control="CTRL-A-ANU",
            numero_factura="FAC-A-ANU",
            fecha_emision=hoy,
            base_imponible=Decimal("100.00"),
            monto_iva=Decimal("16.00"),
            monto_total=Decimal("116.00"),
            id_moneda=moneda_usd,
            estado="ANULADA",
        )
        nd_anu = NotaDebitoFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_a,
            id_factura_origen=fac_anulada,
            fecha_emision=hoy,
            base_imponible=Decimal("10.00"),
            monto_iva=Decimal("1.60"),
            monto_total=Decimal("11.60"),
            id_moneda=moneda_usd,
        )
        with pytest.raises(VentaError, match="debe estar emitida"):
            emitir_nota_debito_fiscal(nd_anu)

        fac_ok = FacturaFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_a,
            numero_control="CTRL-A-OK",
            numero_factura="FAC-A-OK",
            fecha_emision=hoy,
            base_imponible=Decimal("100.00"),
            monto_iva=Decimal("16.00"),
            monto_total=Decimal("116.00"),
            id_moneda=moneda_usd,
            estado="EMITIDA",
        )
        nd_zero = NotaDebitoFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_a,
            id_factura_origen=fac_ok,
            fecha_emision=hoy,
            base_imponible=Decimal("0.00"),
            monto_iva=Decimal("0.00"),
            monto_total=Decimal("0.00"),
            id_moneda=moneda_usd,
        )
        with pytest.raises(VentaError, match="mayor que cero"):
            emitir_nota_debito_fiscal(nd_zero)

        # Período fiscal cerrado bloquea emisión
        PeriodoFiscal.objects.create(
            id_empresa=empresa_a,
            año=hoy.year,
            mes=hoy.month,
            cerrado=True,
        )
        nd_closed = NotaDebitoFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_a,
            id_factura_origen=fac_ok,
            fecha_emision=hoy,
            base_imponible=Decimal("25.00"),
            monto_iva=Decimal("4.00"),
            monto_total=Decimal("29.00"),
            id_moneda=moneda_usd,
        )
        with pytest.raises(VentaError):
            emitir_nota_debito_fiscal(nd_closed)

    def test_rls_postgresql_nota_debito_fiscal(self, rls_test_role, empresa_a, empresa_b, moneda_usd):
        from apps.ventas.models import FacturaFiscal, NotaDebitoFiscal

        cliente_a = ClienteFactory(id_empresa=empresa_a, rif="J-33111222-3")
        cliente_b = ClienteFactory(id_empresa=empresa_b, rif="J-33111222-4")
        hoy = timezone.localdate()

        fac_a = FacturaFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_a,
            numero_control="CTRL-RLS-A",
            numero_factura="FAC-RLS-A",
            fecha_emision=hoy,
            base_imponible=Decimal("100.00"),
            monto_iva=Decimal("16.00"),
            monto_total=Decimal("116.00"),
            id_moneda=moneda_usd,
            estado="EMITIDA",
        )
        nd_a = NotaDebitoFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_a,
            id_factura_origen=fac_a,
            fecha_emision=hoy,
            base_imponible=Decimal("10.00"),
            monto_iva=Decimal("1.60"),
            monto_total=Decimal("11.60"),
            id_moneda=moneda_usd,
        )
        fac_b = FacturaFiscal.objects.create(
            id_empresa=empresa_b,
            id_cliente=cliente_b,
            numero_control="CTRL-RLS-B",
            numero_factura="FAC-RLS-B",
            fecha_emision=hoy,
            base_imponible=Decimal("100.00"),
            monto_iva=Decimal("16.00"),
            monto_total=Decimal("116.00"),
            id_moneda=moneda_usd,
            estado="EMITIDA",
        )
        nd_b = NotaDebitoFiscal.objects.create(
            id_empresa=empresa_b,
            id_cliente=cliente_b,
            id_factura_origen=fac_b,
            fecha_emision=hoy,
            base_imponible=Decimal("20.00"),
            monto_iva=Decimal("3.20"),
            monto_total=Decimal("23.20"),
            id_moneda=moneda_usd,
        )

        # Verificar política registrada en pg_policies y FORCE RLS activo
        with connection.cursor() as cur:
            cur.execute("SELECT policyname FROM pg_policies WHERE tablename = 'ventas_nota_debito_fiscal';")
            policies = [row[0] for row in cur.fetchall()]
            assert rls.POLICY_NAME in policies

        if rls_test_role is None:
            return

        # Validar SELECT y WITH CHECK bajo rol no-dueño
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(f'SET LOCAL ROLE "{rls_test_role}"')
                cur.execute(f"SELECT set_config('{rls.GUC_BYPASS}', 'off', true)")
                cur.execute(
                    f"SELECT set_config('{rls.GUC_EMPRESAS}', %s, true)",
                    [str(empresa_a.id_empresa)],
                )
                ids = {str(x) for x in NotaDebitoFiscal.objects.values_list("id_nota_debito_fiscal", flat=True)}
                assert str(nd_a.id_nota_debito_fiscal) in ids
                assert str(nd_b.id_nota_debito_fiscal) not in ids

                # INSERT para empresa_b con contexto de empresa_a debe fallar por WITH CHECK
                with pytest.raises((IntegrityError, ProgrammingError, Exception)), transaction.atomic():
                    cur.execute(
                        """
                        INSERT INTO ventas_nota_debito_fiscal (
                            id_nota_debito_fiscal, id_empresa_id, id_cliente_id, id_factura_origen_id,
                            numero_control, numero_nota_debito, fecha_emision, base_imponible,
                            monto_iva, monto_total, id_moneda_id, tasa_cambio, motivo, estado,
                            ambito, activo, fecha_creacion
                        ) VALUES (
                            gen_random_uuid(), %s, %s, %s, 'X', 'ND-X', %s, 1, 0, 1, %s, 1,
                            'INTERES_MORA', 'BORRADOR', 'FISCAL', true, NOW()
                        )
                        """,
                        [
                            str(empresa_b.id_empresa),
                            str(cliente_b.id_cliente),
                            str(fac_b.id_factura),
                            str(hoy),
                            str(moneda_usd.id_moneda),
                        ],
                    )


# ---------------------------------------------------------------------------
# 3. Ámbito FISCAL / GERENCIAL en documentos origen + SENIAT Libro Compras
# ---------------------------------------------------------------------------


class TestAmbitoDocumentosOrigen:
    def test_nota_venta_ambito_default_y_filtro_api(self, client_a, empresa_a):
        from apps.ventas.models import NotaVenta

        cliente = ClienteFactory(id_empresa=empresa_a, rif="J-44556677-8")
        hoy = timezone.localdate()

        nv_ger = NotaVenta.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            numero_nota="NV-AMB-GER",
            fecha_nota=hoy,
        )
        assert nv_ger.ambito == "GERENCIAL"

        nv_fis = NotaVenta.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            numero_nota="NV-AMB-FIS",
            fecha_nota=hoy,
            ambito="FISCAL",
        )

        r_ger = client_a.get("/api/ventas/notas-venta/?ambito=GERENCIAL")
        assert r_ger.status_code == 200
        assert [x["numero_nota"] for x in r_ger.data["results"]] == ["NV-AMB-GER"]

        r_fis = client_a.get("/api/ventas/notas-venta/?ambito=fiscal")
        assert r_fis.status_code == 200
        assert [x["numero_nota"] for x in r_fis.data["results"]] == [nv_fis.numero_nota]

        r_nul = client_a.get("/api/ventas/notas-venta/?ambito=FISCAL%00")
        assert r_nul.status_code == 400

        r_bad = client_a.get("/api/ventas/notas-venta/?ambito=OTRO")
        assert r_bad.status_code == 400

    def test_factura_compra_ambito_en_libro_compras_seniat(self, client_a, empresa_a):
        from apps.compras.models import FacturaCompra, OrdenCompra
        from apps.fiscal.libros_seniat import (
            generar_libro_compras_pdf,
            generar_libro_compras_txt,
        )
        from apps.proveedores.models import Proveedor

        hoy = timezone.localdate()
        prov = Proveedor.objects.create(
            id_empresa=empresa_a,
            razon_social="Proveedor Dual S.A.",
            rif="J-55667788-9",
        )
        oc = OrdenCompra.objects.create(
            id_empresa=empresa_a,
            id_proveedor=prov,
            numero_orden="OC-DUAL-001",
            fecha_orden=hoy,
            estado="APROBADA",
        )
        fc_fiscal = FacturaCompra.objects.create(
            id_empresa=empresa_a,
            id_orden_compra=oc,
            id_proveedor=prov,
            numero_factura="FC-FIS-001",
            fecha_emision=hoy,
            monto_total=Decimal("500.00"),
        )
        assert fc_fiscal.ambito == "FISCAL"

        fc_ger = FacturaCompra.objects.create(
            id_empresa=empresa_a,
            id_orden_compra=oc,
            id_proveedor=prov,
            numero_factura="FC-GER-001",
            fecha_emision=hoy,
            monto_total=Decimal("250.00"),
            ambito="GERENCIAL",
        )
        assert fc_ger.ambito == "GERENCIAL"

        txt_compras = generar_libro_compras_txt(empresa_a, hoy, hoy)
        assert "FC-FIS-001" in txt_compras
        assert "FC-GER-001" not in txt_compras

        pdf_compras = generar_libro_compras_pdf(empresa_a, hoy, hoy)
        assert pdf_compras.startswith(b"%PDF-")

        r_ger = client_a.get("/api/compras/facturas-compra/?ambito=GERENCIAL")
        assert r_ger.status_code == 200
        assert [x["numero_factura"] for x in r_ger.data["results"]] == ["FC-GER-001"]

    def test_movimiento_inventario_gasto_y_nomina_con_ambito(self, client_a, empresa_a, user_a, moneda_usd):
        from apps.gastos.models import CategoriaGasto, Gasto
        from apps.inventario.services import registrar_movimiento
        from apps.nomina.models import PeriodoNomina, ProcesoNomina

        almacen = AlmacenFactory(id_empresa=empresa_a)
        producto = ProductoFactory(id_empresa=empresa_a)
        ahora = timezone.now()

        mov_fis = registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=ahora,
            tipo_movimiento="ENTRADA",
            producto=producto,
            cantidad=Decimal("5.0000"),
            almacen_destino=almacen,
            costo_unitario=Decimal("10.0000"),
            usuario=user_a,
        )
        assert mov_fis.ambito == "FISCAL"

        resp_mov = client_a.post(
            "/api/inventario/movimientos-inventario/",
            {
                "id_empresa": str(empresa_a.id_empresa),
                "fecha_hora_movimiento": ahora.isoformat(),
                "tipo_movimiento": "ENTRADA",
                "id_producto": str(producto.id_producto),
                "cantidad": "3.0000",
                "id_almacen_destino": str(almacen.id_almacen),
                "costo_unitario_movimiento": "12.0000",
                "ambito": "GERENCIAL",
            },
            format="json",
        )
        assert resp_mov.status_code == 201, resp_mov.data
        assert resp_mov.data["ambito"] == "GERENCIAL"

        r_mov_ger = client_a.get("/api/inventario/movimientos-inventario/?ambito=GERENCIAL")
        assert r_mov_ger.status_code == 200
        assert len(r_mov_ger.data["results"]) == 1

        # Gasto default FISCAL + filtro GERENCIAL
        cat = CategoriaGasto.objects.create(id_empresa=empresa_a, nombre_categoria="Viáticos")
        hoy = timezone.localdate()
        g_fis = Gasto.objects.create(
            id_empresa=empresa_a,
            fecha_gasto=hoy,
            descripcion="Gasto fiscal",
            monto=Decimal("50.00"),
            id_moneda=moneda_usd,
            id_categoria_gasto=cat,
        )
        assert g_fis.ambito == "FISCAL"
        Gasto.objects.create(
            id_empresa=empresa_a,
            fecha_gasto=hoy,
            descripcion="Bono caja chica gerencial",
            monto=Decimal("20.00"),
            id_moneda=moneda_usd,
            id_categoria_gasto=cat,
            ambito="GERENCIAL",
        )
        r_gastos = client_a.get("/api/gastos/gastos/?ambito=GERENCIAL")
        assert r_gastos.status_code == 200
        assert [x["descripcion"] for x in r_gastos.data["results"]] == ["Bono caja chica gerencial"]

        # ProcesoNomina default FISCAL + filtro GERENCIAL
        per = PeriodoNomina.objects.create(
            id_empresa=empresa_a,
            nombre_periodo="Nov 2026 Dual",
            fecha_inicio=hoy.replace(day=1),
            fecha_fin=hoy,
            fecha_pago=hoy,
            tipo_periodo="MENSUAL",
        )
        pn_fis = ProcesoNomina.objects.create(
            id_empresa=empresa_a,
            id_periodo_nomina=per,
            numero_proceso="NOM-FIS-001",
            fecha_proceso=ahora,
            estado="EN_PROCESO",
        )
        assert pn_fis.ambito == "FISCAL"
        ProcesoNomina.objects.create(
            id_empresa=empresa_a,
            id_periodo_nomina=per,
            numero_proceso="NOM-GER-001",
            fecha_proceso=ahora,
            estado="EN_PROCESO",
            ambito="GERENCIAL",
        )
        r_nom = client_a.get("/api/nomina/procesos-nomina/?ambito=GERENCIAL")
        assert r_nom.status_code == 200
        assert [x["numero_proceso"] for x in r_nom.data["results"]] == ["NOM-GER-001"]
