"""Tests de integración Plan 09 Ola 3A: Blindaje Fiscal SENIAT 360° (Fases 2.3, 2.4 y 2.5)."""

from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.db import connection, transaction
from django.utils import timezone

from apps.core import rls
from apps.core.models import Contacto
from tests.factories import AlmacenFactory, MonedaFactory, ProductoFactory

pytestmark = [pytest.mark.django_db]


# ---------------------------------------------------------------------------
# 1. Seed Decreto 1808 + PostgreSQL RLS en las 3 tablas fiscales nuevas
# ---------------------------------------------------------------------------


class TestDecreto1808SeedYRLSSENIAT:
    def test_seed_decreto_1808_y_rls_tres_tablas(self, rls_test_role, client_a, empresa_a, empresa_b, moneda_usd):
        from apps.fiscal.models import (
            ComprobanteRetencionISLR,
            ComprobanteRetencionIVA,
            ConceptoRetencionISLR,
            DocumentoImprentaDigital,
        )

        # >= 35 conceptos Decreto 1808 cubriendo PNR, PNNR, PJDO, PJND
        assert ConceptoRetencionISLR.objects.filter(activo=True).count() >= 35
        tipos = set(ConceptoRetencionISLR.objects.values_list("tipo_persona_fiscal", flat=True))
        assert {"PNR", "PNNR", "PJDO", "PJND"}.issubset(tipos)

        r_cat = client_a.get("/api/fiscal/conceptos-islr/?tipo_persona_fiscal=PNR")
        assert r_cat.status_code == 200
        items_pnr = r_cat.data["results"] if "results" in r_cat.data else r_cat.data
        assert len(items_pnr) >= 1
        assert all(row["tipo_persona_fiscal"] == "PNR" for row in items_pnr)

        # Políticas RLS creadas en PostgreSQL
        with connection.cursor() as cur:
            for tabla in (
                "fiscal_comprobante_retencion_iva",
                "fiscal_comprobante_retencion_islr",
                "fiscal_documento_imprenta_digital",
            ):
                cur.execute("SELECT policyname FROM pg_policies WHERE tablename = %s;", [tabla])
                assert rls.POLICY_NAME in [row[0] for row in cur.fetchall()], f"Falta RLS en {tabla}"

        hoy = timezone.localdate()
        concepto = ConceptoRetencionISLR.objects.get(codigo="003")
        with rls.rls_bypass():
            c_a = Contacto.objects.create(id_empresa=empresa_a, nombre="Prov A", rif="J-30111222-1", es_proveedor=True)
            c_b = Contacto.objects.create(id_empresa=empresa_b, nombre="Prov B", rif="J-30999888-2", es_proveedor=True)

            iva_a = ComprobanteRetencionIVA.objects.create(
                id_empresa=empresa_a,
                numero_comprobante="20261100000001",
                contacto=c_a,
                fecha_emision=hoy,
                periodo_impositivo=f"{hoy:%Y%m}",
                numero_documento="FAC-A1",
                monto_total_documento=Decimal("116"),
                base_imponible=Decimal("100"),
                monto_iva=Decimal("16"),
                monto_retenido=Decimal("12"),
            )
            iva_b = ComprobanteRetencionIVA.objects.create(
                id_empresa=empresa_b,
                numero_comprobante="20261100000001",
                contacto=c_b,
                fecha_emision=hoy,
                periodo_impositivo=f"{hoy:%Y%m}",
                numero_documento="FAC-B1",
                monto_total_documento=Decimal("116"),
                base_imponible=Decimal("100"),
                monto_iva=Decimal("16"),
                monto_retenido=Decimal("12"),
            )
            islr_a = ComprobanteRetencionISLR.objects.create(
                id_empresa=empresa_a,
                numero_comprobante="20261100000001",
                contacto=c_a,
                concepto=concepto,
                fecha_emision=hoy,
                periodo_impositivo=f"{hoy:%Y%m}",
                numero_factura="FAC-A1",
                monto_operacion=Decimal("1000"),
                porcentaje_retencion=Decimal("5.00"),
                monto_retenido=Decimal("50.00"),
            )
            islr_b = ComprobanteRetencionISLR.objects.create(
                id_empresa=empresa_b,
                numero_comprobante="20261100000001",
                contacto=c_b,
                concepto=concepto,
                fecha_emision=hoy,
                periodo_impositivo=f"{hoy:%Y%m}",
                numero_factura="FAC-B1",
                monto_operacion=Decimal("1000"),
                porcentaje_retencion=Decimal("5.00"),
                monto_retenido=Decimal("50.00"),
            )
            imp_a = DocumentoImprentaDigital.objects.create(
                id_empresa=empresa_a,
                tipo_documento="FACTURA",
                referencia_documento="FAC-A1",
                numero_control_asignado="00-00000001",
            )
            imp_b = DocumentoImprentaDigital.objects.create(
                id_empresa=empresa_b,
                tipo_documento="FACTURA",
                referencia_documento="FAC-B1",
                numero_control_asignado="00-00000001",
            )

        if rls_test_role is not None:
            with transaction.atomic():
                with connection.cursor() as cur:
                    cur.execute(f'SET LOCAL ROLE "{rls_test_role}"')
                    cur.execute(f"SELECT set_config('{rls.GUC_BYPASS}', 'off', true)")
                    cur.execute(f"SELECT set_config('{rls.GUC_EMPRESAS}', '', true)")
                    assert ComprobanteRetencionIVA.objects.count() == 0
                    assert ComprobanteRetencionISLR.objects.count() == 0
                    assert DocumentoImprentaDigital.objects.count() == 0

                    cur.execute(f"SELECT set_config('{rls.GUC_EMPRESAS}', %s, true)", [str(empresa_a.id_empresa)])
                    assert list(ComprobanteRetencionIVA.objects.values_list("pk", flat=True)) == [iva_a.pk]
                    assert list(ComprobanteRetencionISLR.objects.values_list("pk", flat=True)) == [islr_a.pk]
                    assert list(DocumentoImprentaDigital.objects.values_list("pk", flat=True)) == [imp_a.pk]
                    assert iva_b.pk not in list(ComprobanteRetencionIVA.objects.values_list("pk", flat=True))
                    assert islr_b.pk not in list(ComprobanteRetencionISLR.objects.values_list("pk", flat=True))
                    assert imp_b.pk not in list(DocumentoImprentaDigital.objects.values_list("pk", flat=True))


# ---------------------------------------------------------------------------
# 2. Retenciones IVA (.txt 16 columnas, PDF, Anulación, Asiento R-CODE-11)
# ---------------------------------------------------------------------------


class TestRetencionesIVAExportadorYPDF:
    def test_flujo_completo_retencion_iva_txt_pdf_y_asiento(self, client_a, empresa_a, user_a):
        from apps.contabilidad.models import MapeoContable, PeriodoContable, PlanCuentas

        hoy = timezone.localdate()
        periodo = f"{hoy:%Y%m}"
        empresa_a.identificador_fiscal = "J-40100100-9"
        empresa_a.contabilidad_activa = True
        empresa_a.save(update_fields=["identificador_fiscal", "contabilidad_activa"])

        prov = Contacto.objects.create(
            id_empresa=empresa_a,
            nombre="Suplidora Norte C.A.",
            rif="J-50222333-4",
            es_proveedor=True,
            porcentaje_retencion_iva=Decimal("75.00"),
        )

        # Sin mapeo con contabilidad_activa=True -> 422
        r_no_map = client_a.post(
            "/api/fiscal/retenciones-iva/emitir/",
            {
                "contacto": str(prov.id_contacto),
                "fecha_emision": hoy.isoformat(),
                "numero_documento": "FAC-00101",
                "numero_control": "00-00101",
                "base_imponible": "1000.0000",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="ret-iva-nomap",
        )
        assert r_no_map.status_code == 422

        # Configurar MapeoContable RETENCION_IVA_COMPRA
        PeriodoContable.objects.create(id_empresa=empresa_a, anio=hoy.year, mes=hoy.month, estado="ABIERTO")
        cta_debe = PlanCuentas.objects.create(
            id_empresa=empresa_a,
            codigo_cuenta="2.1.01.01",
            nombre_cuenta="CxP Proveedores",
            tipo_cuenta="PASIVO",
            naturaleza="ACREEDORA",
            nivel=4,
        )
        cta_haber = PlanCuentas.objects.create(
            id_empresa=empresa_a,
            codigo_cuenta="2.1.03.05",
            nombre_cuenta="Retención IVA por Enterar",
            tipo_cuenta="PASIVO",
            naturaleza="ACREEDORA",
            nivel=4,
        )
        MapeoContable.objects.create(
            id_empresa=empresa_a,
            tipo_asiento="RETENCION_IVA_COMPRA",
            cuenta_debe=cta_debe,
            cuenta_haber=cta_haber,
        )

        # Emitir retención IVA 75% de 160 = 120.00
        r_emit = client_a.post(
            "/api/fiscal/retenciones-iva/emitir/",
            {
                "contacto": str(prov.id_contacto),
                "fecha_emision": hoy.isoformat(),
                "numero_documento": "FAC-00101",
                "numero_control": "00-00101",
                "base_imponible": "1000.0000",
                "monto_exento": "50.0000",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="ret-iva-ok-1",
        )
        assert r_emit.status_code == 201, r_emit.data
        comp_id = r_emit.data["id_comprobante"]
        assert r_emit.data["numero_comprobante"].startswith(periodo)
        assert len(r_emit.data["numero_comprobante"]) == 14
        assert Decimal(r_emit.data["monto_iva"]) == Decimal("160.0000")
        assert Decimal(r_emit.data["monto_retenido"]) == Decimal("120.0000")
        assert Decimal(r_emit.data["monto_total_documento"]) == Decimal("1210.0000")
        assert r_emit.data["asiento_contable"] is not None

        # TXT 16 columnas tab-separated
        r_txt = client_a.get(f"/api/fiscal/retenciones-iva/exportar-txt/?periodo={periodo}")
        assert r_txt.status_code == 200
        lineas = [ln for ln in r_txt.content.decode("utf-8").splitlines() if ln.strip()]
        assert len(lineas) == 1
        cols = lineas[0].split("\t")
        assert len(cols) == 16
        assert cols[0] == "J401001009"
        assert cols[1] == periodo
        assert cols[3] == "C"
        assert cols[5] == "J502223334"
        assert cols[8] == "1210.00"
        assert cols[9] == "1000.00"
        assert cols[10] == "120.00"
        assert cols[12] == r_emit.data["numero_comprobante"]
        assert cols[13] == "50.00"
        assert cols[14] == "16.00"

        # PDF
        r_pdf = client_a.get(f"/api/fiscal/retenciones-iva/{comp_id}/pdf/")
        assert r_pdf.status_code == 200
        assert r_pdf.content.startswith(b"%PDF")

        # Anular y verificar exclusión del TXT
        r_anu = client_a.post(f"/api/fiscal/retenciones-iva/{comp_id}/anular/", {}, format="json")
        assert r_anu.status_code == 200
        assert r_anu.data["estado"] == "ANULADO"
        assert client_a.post(f"/api/fiscal/retenciones-iva/{comp_id}/anular/", {}, format="json").status_code == 400

        r_txt_vacio = client_a.get(f"/api/fiscal/retenciones-iva/exportar-txt/?periodo={periodo}")
        assert r_txt_vacio.status_code == 200
        assert r_txt_vacio.content.decode("utf-8").strip() == ""


# ---------------------------------------------------------------------------
# 3. Retenciones ISLR (Sustraendo Decreto 1808, XML SENIAT, PDF) + IGTF/ITF
# ---------------------------------------------------------------------------


class TestRetencionesISLRYIGTFITF:
    def test_retencion_islr_sustraendo_xml_pdf_y_igtf_itf(self, client_a, empresa_a):
        from apps.fiscal.models import ConceptoRetencionISLR

        hoy = timezone.localdate()
        periodo = f"{hoy:%Y%m}"
        empresa_a.identificador_fiscal = "J-40100100-9"
        empresa_a.save(update_fields=["identificador_fiscal"])

        pnr = Contacto.objects.create(
            id_empresa=empresa_a,
            nombre="Consultor PNR",
            rif="V-15222333-0",
            tipo_persona_fiscal="PNR",
            es_proveedor=True,
        )
        exento = Contacto.objects.create(
            id_empresa=empresa_a,
            nombre="Ente Exento",
            rif="G-20000001-0",
            exento_islr=True,
            es_proveedor=True,
        )
        c_hon_pnr = ConceptoRetencionISLR.objects.get(codigo="001")  # 3%, sustraendo 83.3334 UT

        # Sujeto exento rechazado sin omitir_exencion
        assert (
            client_a.post(
                "/api/fiscal/retenciones-islr/emitir/",
                {
                    "contacto": str(exento.id_contacto),
                    "concepto": str(c_hon_pnr.id),
                    "fecha_emision": hoy.isoformat(),
                    "numero_factura": "FAC-EX-1",
                    "monto_operacion": "1000.0000",
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY="ret-islr-exento",
            ).status_code
            == 400
        )

        # Emisión con sustraendo: UT=9.00, 10000 * 3% = 300.00; sust = 83.3334 * 9 * 0.03 = 22.5000 -> ret = 277.5000
        r_emit = client_a.post(
            "/api/fiscal/retenciones-islr/emitir/",
            {
                "contacto": str(pnr.id_contacto),
                "concepto": str(c_hon_pnr.id),
                "fecha_emision": hoy.isoformat(),
                "numero_factura": "FAC-ISLR-1",
                "numero_control": "00-00555",
                "monto_operacion": "10000.0000",
                "valor_ut": "9.0000",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="ret-islr-ok-1",
        )
        assert r_emit.status_code == 201, r_emit.data
        comp_id = r_emit.data["id_comprobante"]
        assert Decimal(r_emit.data["sustraendo"]) == Decimal("22.5000")
        assert Decimal(r_emit.data["monto_retenido"]) == Decimal("277.5000")

        # Exportar XML SENIAT y validar estructura XML bien formada
        r_xml = client_a.get(f"/api/fiscal/retenciones-islr/exportar-xml/?periodo={periodo}")
        assert r_xml.status_code == 200
        root = ET.fromstring(r_xml.content.decode("utf-8"))
        assert root.tag == "RelacionRetencionesISLR"
        assert root.attrib["RifAgente"] == "J401001009"
        assert root.attrib["Periodo"] == periodo
        detalles = root.findall("DetalleRetencion")
        assert len(detalles) == 1
        assert detalles[0].findtext("RifRetenido") == "V152223330"
        assert detalles[0].findtext("CodigoConcepto") == "001"
        assert detalles[0].findtext("MontoOperacion") == "10000.00"
        assert detalles[0].findtext("PorcentajeRetencion") == "3.00"

        # PDF y anulación
        r_pdf = client_a.get(f"/api/fiscal/retenciones-islr/{comp_id}/pdf/")
        assert r_pdf.status_code == 200
        assert r_pdf.content.startswith(b"%PDF")

        assert client_a.post(f"/api/fiscal/retenciones-islr/{comp_id}/anular/", {}, format="json").status_code == 200
        assert client_a.post(f"/api/fiscal/retenciones-islr/{comp_id}/anular/", {}, format="json").status_code == 400

        # Calculadora IGTF 3% + ITF bancario 2%
        r_igtf = client_a.post(
            "/api/fiscal/calcular-igtf-itf/",
            {"monto": "500.0000", "moneda_iso": "USD"},
            format="json",
        )
        assert r_igtf.status_code == 200
        assert r_igtf.data["aplica_igtf"] is True
        assert Decimal(r_igtf.data["igtf"]) == Decimal("15.0000")
        assert Decimal(r_igtf.data["itf_bancario"]) == Decimal("0.0000")

        r_itf = client_a.post(
            "/api/fiscal/calcular-igtf-itf/",
            {
                "monto": "1000.0000",
                "moneda_iso": "VES",
                "es_contribuyente_especial": True,
                "es_debito_bancario": True,
            },
            format="json",
        )
        assert r_itf.status_code == 200
        assert r_itf.data["aplica_igtf"] is False
        assert r_itf.data["aplica_itf_bancario"] is True
        assert Decimal(r_itf.data["itf_bancario"]) == Decimal("20.0000")


# ---------------------------------------------------------------------------
# 4. Imprenta Digital (Simulado + Unidigital) y Libro Inventario Art. 177
# ---------------------------------------------------------------------------


class TestImprentaDigitalYLibroInventarioArt177:
    def test_imprenta_digital_simulado_y_unidigital(self, client_a, empresa_a):
        from apps.localizacion_ve.imprenta_digital import (
            ImprentaDigitalError,
            UnidigitalImprentaAdapter,
            emitir_en_imprenta_digital,
            obtener_proveedor_imprenta_digital,
        )

        # Emisión vía REST para Guía de Despacho y Factura (Simulado)
        r_guia = client_a.post(
            "/api/fiscal/imprenta-digital/emitir/",
            {
                "tipo_documento": "GUIA_DESPACHO",
                "referencia_documento": "GD-0001",
                "payload": {"destino": "Valencia"},
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="imprenta-guia-1",
        )
        assert r_guia.status_code == 201, r_guia.data
        assert r_guia.data["tipo_documento"] == "GUIA_DESPACHO"
        assert r_guia.data["numero_control_asignado"].startswith("00-")
        assert len(r_guia.data["codigo_validacion"]) == 32

        r_list = client_a.get("/api/fiscal/imprenta-digital/?tipo_documento=GUIA_DESPACHO")
        assert r_list.status_code == 200
        items = r_list.data["results"] if "results" in r_list.data else r_list.data
        assert len(items) == 1

        # Anulación vía REST
        em_id = r_guia.data["id_emision"]
        assert client_a.post(f"/api/fiscal/imprenta-digital/{em_id}/anular/", {"motivo": "Error"}).status_code == 200
        assert client_a.post(f"/api/fiscal/imprenta-digital/{em_id}/anular/", {}).status_code == 400

        # Adaptador Unidigital con transporte HTTPS simulado inyectable
        llamadas: list[tuple[str, dict]] = []

        def fake_transport(url, payload, headers, timeout=15):
            llamadas.append((url, payload))
            if url.endswith("emitir"):
                return {
                    "numero_control": "UNI-00004567",
                    "codigo_validacion": "HASH-UNIDIGITAL",
                    "url_verificacion": "https://unidigital.test/v/4567",
                }
            return {"estado": "EMITIDO"}

        from apps.fiscal.models import ConfiguracionFiscalEmpresa

        ConfiguracionFiscalEmpresa.objects.create(
            id_empresa=empresa_a,
            imprenta_digital_proveedor="UNIDIGITAL",
            imprenta_digital_url="https://api.unidigital.test",
        )
        doc_uni = emitir_en_imprenta_digital(
            empresa=empresa_a,
            tipo_documento="NOTA_DEBITO",
            referencia_documento="ND-009",
            payload={"monto": "50.00"},
            transport=fake_transport,
        )
        assert doc_uni.proveedor == "UNIDIGITAL"
        assert doc_uni.numero_control_asignado == "UNI-00004567"
        assert llamadas[0][1]["tipo_documento_seniat"] == "02"

        adapter = obtener_proveedor_imprenta_digital(
            empresa_a, proveedor_override="UNIDIGITAL", transport=fake_transport
        )
        assert adapter.consultar_estado(empresa=empresa_a, numero_control="UNI-00004567")["estado"] == "EMITIDO"
        assert adapter.anular_documento(empresa=empresa_a, numero_control="UNI-00004567")["estado"] == "ANULADO"

        # Errores de configuración en imprenta
        with pytest.raises(ImprentaDigitalError):
            UnidigitalImprentaAdapter(base_url="").emitir_documento(
                empresa=None, tipo_documento="FACTURA", referencia_documento="F-1", payload={}
            )
        with pytest.raises(ImprentaDigitalError):
            obtener_proveedor_imprenta_digital(empresa_a, proveedor_override="THE_FACTORY_HKA")

    def test_libro_inventario_art177_excluye_gerencial_y_convierte_moneda_pais(
        self, client_a, empresa_a, user_a, moneda_usd
    ):
        from apps.finanzas.models import TasaCambio, TipoTasaCambio
        from apps.inventario.models import MovimientoInventario

        hoy = timezone.localdate()
        ayer = hoy - timedelta(days=5)
        moneda_ves = MonedaFactory(codigo_iso="VES", nombre="Bolívar", simbolo="Bs")
        empresa_a.id_moneda_pais = moneda_ves
        empresa_a.save(update_fields=["id_moneda_pais"])
        tipo_bcv = TipoTasaCambio.objects.create(
            id_empresa=empresa_a, codigo="OFICIAL_BCV", nombre="BCV Oficial", es_oficial_fiscal=True
        )
        TasaCambio.objects.create(
            id_empresa=empresa_a,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_ves,
            tipo_tasa="OFICIAL_BCV",
            id_tipo_tasa=tipo_bcv,
            valor_tasa=Decimal("45.00000000"),
            fecha_tasa=hoy,
        )

        almacen = AlmacenFactory(id_empresa=empresa_a)
        prod = ProductoFactory(
            id_empresa=empresa_a,
            nombre_producto="Filtro Aceite Art177",
            costo_promedio=Decimal("10.0000"),
        )
        tz = timezone.get_current_timezone()

        # Inventario inicial previo (20 uds FISCAL)
        MovimientoInventario.objects.create(
            id_empresa=empresa_a,
            fecha_hora_movimiento=timezone.make_aware(datetime.combine(ayer, time(10, 0)), tz),
            tipo_movimiento="ENTRADA",
            id_producto=prod,
            id_almacen_destino=almacen,
            cantidad=Decimal("20.0000"),
            costo_unitario_movimiento=Decimal("10.0000"),
            id_usuario_registro=user_a,
            ambito="FISCAL",
        )
        # Entrada en el período (+10 uds FISCAL a $10.00)
        MovimientoInventario.objects.create(
            id_empresa=empresa_a,
            fecha_hora_movimiento=timezone.make_aware(datetime.combine(hoy, time(9, 0)), tz),
            tipo_movimiento="RECEPCION_COMPRA",
            id_producto=prod,
            id_almacen_destino=almacen,
            cantidad=Decimal("10.0000"),
            costo_unitario_movimiento=Decimal("10.0000"),
            id_usuario_registro=user_a,
            ambito="FISCAL",
        )
        # Despacho venta FISCAL (-5 uds) y retiro autoconsumo FISCAL (-2 uds) -> Final = 23 uds
        MovimientoInventario.objects.create(
            id_empresa=empresa_a,
            fecha_hora_movimiento=timezone.make_aware(datetime.combine(hoy, time(11, 0)), tz),
            tipo_movimiento="DESPACHO_VENTA",
            id_producto=prod,
            id_almacen_origen=almacen,
            cantidad=Decimal("5.0000"),
            id_usuario_registro=user_a,
            ambito="FISCAL",
        )
        MovimientoInventario.objects.create(
            id_empresa=empresa_a,
            fecha_hora_movimiento=timezone.make_aware(datetime.combine(hoy, time(12, 0)), tz),
            tipo_movimiento="SALIDA_INTERNA",
            id_producto=prod,
            id_almacen_origen=almacen,
            cantidad=Decimal("2.0000"),
            id_usuario_registro=user_a,
            ambito="FISCAL",
        )
        # Movimiento GERENCIAL NO debe alterar el Art. 177 LISLR
        MovimientoInventario.objects.create(
            id_empresa=empresa_a,
            fecha_hora_movimiento=timezone.make_aware(datetime.combine(hoy, time(13, 0)), tz),
            tipo_movimiento="ENTRADA",
            id_producto=prod,
            id_almacen_destino=almacen,
            cantidad=Decimal("500.0000"),
            id_usuario_registro=user_a,
            ambito="GERENCIAL",
        )

        r_art = client_a.get(
            f"/api/fiscal/libro-inventario-art177/?empresa={empresa_a.id_empresa}&desde={hoy.isoformat()}&hasta={hoy.isoformat()}"
        )
        assert r_art.status_code == 200, r_art.data
        assert r_art.data["ambito"] == "FISCAL"
        assert r_art.data["moneda_pais"] == "VES"
        assert Decimal(r_art.data["tasa_fiscal_aplicada"]) == Decimal("45.0000")
        assert len(r_art.data["items"]) == 1
        it = r_art.data["items"][0]
        assert Decimal(it["existencia_inicial"]) == Decimal("20.0000")
        assert Decimal(it["entradas"]) == Decimal("10.0000")
        assert Decimal(it["salidas"]) == Decimal("5.0000")
        assert Decimal(it["retiros_autoconsumo"]) == Decimal("2.0000")
        assert Decimal(it["existencia_final"]) == Decimal("23.0000")
        assert Decimal(it["costo_unitario_fiscal"]) == Decimal("450.0000")
        assert Decimal(it["valor_final_fiscal"]) == Decimal("10350.0000")


# ---------------------------------------------------------------------------
# 5. Validaciones negativas, período cerrado y aislamiento cross-tenant
# ---------------------------------------------------------------------------


class TestValidacionesNegativasSENIAT360:
    def test_validaciones_periodo_cerrado_cross_tenant_y_nul_bytes(self, client_a, empresa_a, empresa_b):
        from apps.fiscal.models import ConceptoRetencionISLR, PeriodoFiscal

        hoy = timezone.localdate()
        PeriodoFiscal.objects.create(id_empresa=empresa_a, año=hoy.year, mes=hoy.month, cerrado=True)
        prov_a = Contacto.objects.create(id_empresa=empresa_a, nombre="Prov A", rif="J-11111111-1")
        prov_b = Contacto.objects.create(id_empresa=empresa_b, nombre="Prov B", rif="J-22222222-2")
        concepto = ConceptoRetencionISLR.objects.get(codigo="003")

        # Período cerrado bloquea emisión IVA e ISLR
        assert (
            client_a.post(
                "/api/fiscal/retenciones-iva/emitir/",
                {
                    "contacto": str(prov_a.id_contacto),
                    "fecha_emision": hoy.isoformat(),
                    "numero_documento": "F-CER-1",
                    "base_imponible": "100.00",
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/fiscal/retenciones-islr/emitir/",
                {
                    "contacto": str(prov_a.id_contacto),
                    "concepto": str(concepto.id),
                    "fecha_emision": hoy.isoformat(),
                    "numero_factura": "F-CER-2",
                    "monto_operacion": "100.00",
                },
                format="json",
            ).status_code
            == 400
        )

        # Contacto/empresa ajena -> 400
        assert (
            client_a.post(
                "/api/fiscal/retenciones-iva/emitir/",
                {
                    "contacto": str(prov_b.id_contacto),
                    "numero_documento": "F-X",
                    "base_imponible": "100.00",
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/fiscal/retenciones-islr/emitir/",
                {
                    "id_empresa": str(empresa_b.id_empresa),
                    "contacto": str(prov_b.id_contacto),
                    "concepto": str(concepto.id),
                    "numero_factura": "F-X",
                    "monto_operacion": "100.00",
                },
                format="json",
            ).status_code
            == 400
        )

        # Períodos inválidos, rangos invertidos y NUL bytes -> 400 / 404
        assert client_a.get("/api/fiscal/retenciones-iva/exportar-txt/?periodo=202613").status_code == 400
        assert client_a.get("/api/fiscal/retenciones-islr/exportar-xml/?periodo=abc").status_code == 400
        assert (
            client_a.get(
                f"/api/fiscal/libro-inventario-art177/?empresa={empresa_a.id_empresa}&desde=2026-12-31&hasta=2026-01-01"
            ).status_code
            == 400
        )
        assert client_a.get(f"/api/fiscal/retenciones-iva/?periodo={uuid.uuid4()}\x00").status_code == 400
        assert client_a.get("/api/fiscal/retenciones-islr/?estado=EMI\x00TIDO").status_code == 400
        assert client_a.get("/api/fiscal/imprenta-digital/?tipo_documento=FAC\x00TURA").status_code == 400
        assert (
            client_a.get(
                f"/api/fiscal/libro-inventario-art177/?empresa={empresa_b.id_empresa}&periodo=2026-11"
            ).status_code
            == 404
        )


class TestRamasYValidacionesSENIAT360:
    def test_modelos_clean_str_y_servicios_error_branches(
        self, client_a, empresa_a, empresa_b, user_a, moneda_usd, monkeypatch
    ):
        from types import SimpleNamespace
        from urllib.error import URLError

        from django.core.exceptions import ValidationError

        from apps.compras.models import FacturaCompra
        from apps.contabilidad.models import MapeoContable, PeriodoContable, PlanCuentas
        from apps.fiscal.models import (
            ComprobanteRetencionISLR,
            ComprobanteRetencionIVA,
            ConceptoRetencionISLR,
            ConfiguracionFiscalEmpresa,
            DocumentoImprentaDigital,
        )
        from apps.ventas.models import FacturaFiscal
        from apps.fiscal.services_retenciones import (
            RetencionFiscalError,
            calcular_igtf_y_itf_bancario,
            emitir_retencion_islr,
            emitir_retencion_iva,
            generar_libro_inventario_art177,
        )
        from apps.inventario.models import MovimientoInventario
        from apps.localizacion_ve.imprenta_digital import (
            ImprentaDigitalError,
            SimuladoImprentaAdapter,
            UnidigitalImprentaAdapter,
            _default_https_transport,
            emitir_en_imprenta_digital,
        )

        hoy = timezone.localdate()
        ayer = hoy - timedelta(days=5)
        prov_a = Contacto.objects.create(
            id_empresa=empresa_a, nombre="Prov A Ramas", rif="J-60000001-1", es_proveedor=True
        )
        prov_b = Contacto.objects.create(
            id_empresa=empresa_b, nombre="Prov B Ramas", rif="J-60000002-2", es_proveedor=True
        )
        concepto = ConceptoRetencionISLR.objects.filter(activo=True, aplica_sustraendo=True).first()
        assert concepto is not None

        # __str__ de los 4 modelos nuevos
        assert concepto.codigo in str(concepto)
        ret_iva = ComprobanteRetencionIVA(
            id_empresa=empresa_a,
            numero_comprobante="20261100000999",
            contacto=prov_a,
            fecha_emision=hoy,
            periodo_impositivo=f"{hoy:%Y%m}",
            numero_documento="F-STR-1",
            monto_total_documento=Decimal("116.0000"),
            base_imponible=Decimal("100.0000"),
            monto_iva=Decimal("16.0000"),
            porcentaje_retencion=Decimal("75.00"),
            monto_retenido=Decimal("12.0000"),
        )
        assert "RetIVA 20261100000999" in str(ret_iva)
        ret_islr = ComprobanteRetencionISLR(
            id_empresa=empresa_a,
            numero_comprobante="20261100000888",
            contacto=prov_a,
            concepto=concepto,
            fecha_emision=hoy,
            periodo_impositivo=f"{hoy:%Y%m}",
            numero_factura="F-STR-2",
            monto_operacion=Decimal("1000.0000"),
            porcentaje_retencion=Decimal("1.00"),
            monto_retenido=Decimal("10.0000"),
        )
        assert "RetISLR 20261100000888" in str(ret_islr)
        doc_imp = DocumentoImprentaDigital(
            id_empresa=empresa_a,
            proveedor="SIMULADO",
            tipo_documento="FACTURA",
            referencia_documento="F-STR-3",
            numero_control_asignado="SIM-0001",
        )
        assert "Imprenta(SIMULADO)" in str(doc_imp)

        # ValidationError cross-empresa en clean() de ComprobanteRetencionIVA e ISLR
        fc_b = FacturaCompra(id_empresa=empresa_b)
        fv_b = FacturaFiscal(id_empresa=empresa_b)
        with pytest.raises(ValidationError):
            ComprobanteRetencionIVA(id_empresa=empresa_a, contacto=prov_b).clean()
        with pytest.raises(ValidationError):
            ComprobanteRetencionIVA(id_empresa=empresa_a, contacto=prov_a, factura_compra=fc_b).clean()
        with pytest.raises(ValidationError):
            ComprobanteRetencionIVA(id_empresa=empresa_a, contacto=prov_a, factura_venta=fv_b).clean()
        with pytest.raises(ValidationError):
            ComprobanteRetencionISLR(id_empresa=empresa_a, contacto=prov_b, concepto=concepto).clean()
        with pytest.raises(ValidationError):
            ComprobanteRetencionISLR(
                id_empresa=empresa_a, contacto=prov_a, concepto=concepto, factura_compra=fc_b
            ).clean()

        # Errores de validación en emitir_retencion_iva
        with pytest.raises(RetencionFiscalError):
            emitir_retencion_iva(
                empresa=empresa_a,
                contacto=prov_b,
                fecha_emision=hoy,
                numero_documento="F-1",
                base_imponible=Decimal("100"),
            )
        with pytest.raises(RetencionFiscalError):
            emitir_retencion_iva(
                empresa=empresa_a,
                contacto=prov_a,
                fecha_emision=hoy,
                numero_documento="F-1",
                base_imponible=Decimal("100"),
                factura_compra=SimpleNamespace(id_empresa_id=empresa_b.pk),
            )
        with pytest.raises(RetencionFiscalError):
            emitir_retencion_iva(
                empresa=empresa_a,
                contacto=prov_a,
                fecha_emision=hoy,
                numero_documento="F-1",
                base_imponible=Decimal("100"),
                factura_venta=SimpleNamespace(id_empresa_id=empresa_b.pk),
            )
        with pytest.raises(RetencionFiscalError):
            emitir_retencion_iva(
                empresa=empresa_a,
                contacto=prov_a,
                fecha_emision=hoy,
                numero_documento="F-1",
                base_imponible=Decimal("-5"),
            )
        with pytest.raises(RetencionFiscalError):
            emitir_retencion_iva(
                empresa=empresa_a,
                contacto=prov_a,
                fecha_emision=hoy,
                numero_documento="F-1",
                base_imponible=Decimal("100"),
                porcentaje_retencion=Decimal("120"),
            )

        # Errores y asiento contable en emitir_retencion_islr (valor_ut=None lee ConfiguracionFiscalEmpresa)
        ConfiguracionFiscalEmpresa.objects.create(id_empresa=empresa_a, valor_unidad_tributaria=Decimal("9.0000"))
        with pytest.raises(RetencionFiscalError):
            emitir_retencion_islr(
                empresa=empresa_a,
                contacto=prov_b,
                concepto=concepto,
                fecha_emision=hoy,
                numero_factura="F-1",
                monto_operacion=Decimal("100"),
            )
        with pytest.raises(RetencionFiscalError):
            emitir_retencion_islr(
                empresa=empresa_a,
                contacto=prov_a,
                concepto=concepto,
                fecha_emision=hoy,
                numero_factura="F-1",
                monto_operacion=Decimal("100"),
                factura_compra=SimpleNamespace(id_empresa_id=empresa_b.pk),
            )
        with pytest.raises(RetencionFiscalError):
            emitir_retencion_islr(
                empresa=empresa_a,
                contacto=prov_a,
                concepto=concepto,
                fecha_emision=hoy,
                numero_factura="F-1",
                monto_operacion=Decimal("0"),
            )

        empresa_a.contabilidad_activa = True
        empresa_a.save(update_fields=["contabilidad_activa"])
        # Sin MapeoContable RETENCION_ISLR -> view retorna 422 (AsientoError)
        r_islr_nomap = client_a.post(
            "/api/fiscal/retenciones-islr/emitir/",
            {
                "id_empresa": str(empresa_a.id_empresa),
                "contacto": str(prov_a.id_contacto),
                "concepto": str(concepto.id),
                "fecha_emision": hoy.isoformat(),
                "numero_factura": "F-NOMAP",
                "monto_operacion": "5000.00",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="islr-nomap-422",
        )
        assert r_islr_nomap.status_code == 422

        PeriodoContable.objects.create(id_empresa=empresa_a, anio=hoy.year, mes=hoy.month, estado="ABIERTO")
        cta_d = PlanCuentas.objects.create(
            id_empresa=empresa_a,
            codigo_cuenta="2.1.01.90",
            nombre_cuenta="CxP ISLR",
            tipo_cuenta="PASIVO",
            naturaleza="ACREEDORA",
            nivel=4,
        )
        cta_h = PlanCuentas.objects.create(
            id_empresa=empresa_a,
            codigo_cuenta="2.1.03.90",
            nombre_cuenta="ISLR Retenido",
            tipo_cuenta="PASIVO",
            naturaleza="ACREEDORA",
            nivel=4,
        )
        MapeoContable.objects.create(
            id_empresa=empresa_a, tipo_asiento="RETENCION_ISLR", cuenta_debe=cta_d, cuenta_haber=cta_h
        )
        comp_islr = emitir_retencion_islr(
            empresa=empresa_a,
            contacto=prov_a,
            concepto=concepto,
            fecha_emision=hoy,
            numero_factura="F-ASIENTO",
            monto_operacion=Decimal("5000.0000"),
            valor_ut=None,
            usuario=user_a,
        )
        assert comp_islr.asiento_contable is not None

        # IGTF negativo
        with pytest.raises(RetencionFiscalError):
            calcular_igtf_y_itf_bancario(Decimal("-1.00"), "USD")
        assert (
            client_a.post(
                "/api/fiscal/calcular-igtf-itf/", {"monto": "-10.00", "moneda_iso": "USD"}, format="json"
            ).status_code
            == 400
        )

        # Art. 177 sin tasa BCV (fallback 1.0000) + movimientos previos SALIDA/RETIRO/AJUSTE y AJUSTE pos/neg
        moneda_ves = MonedaFactory(codigo_iso="VES", nombre="Bolívar", simbolo="Bs")
        empresa_a.id_moneda_pais = moneda_ves
        empresa_a.save(update_fields=["id_moneda_pais"])
        almacen = AlmacenFactory(id_empresa=empresa_a)
        prod = ProductoFactory(
            id_empresa=empresa_a, nombre_producto="Prod Ramas Art177", costo_promedio=Decimal("8.0000")
        )
        tz = timezone.get_current_timezone()
        for tipo, cant, dt_base in [
            ("SALIDA_INTERNA", Decimal("2.0000"), ayer),
            ("DESPACHO_VENTA", Decimal("3.0000"), ayer),
            ("AJUSTE", Decimal("15.0000"), ayer),
            ("AJUSTE", Decimal("4.0000"), hoy),
            ("AJUSTE", Decimal("-1.0000"), hoy),
        ]:
            MovimientoInventario.objects.create(
                id_empresa=empresa_a,
                fecha_hora_movimiento=timezone.make_aware(datetime.combine(dt_base, time(8, 0)), tz),
                tipo_movimiento=tipo,
                id_producto=prod,
                id_almacen_origen=almacen,
                id_almacen_destino=almacen,
                cantidad=cant,
                id_usuario_registro=user_a,
                ambito="FISCAL",
            )
        libro = generar_libro_inventario_art177(empresa_a, hoy, hoy)
        assert Decimal(libro["tasa_fiscal_aplicada"]) == Decimal("1.0000")
        assert Decimal(libro["items"][0]["existencia_final"]) == Decimal("13.0000")

        # Filtros y errores 400 en endpoints SENIAT
        periodo = f"{hoy:%Y%m}"
        assert (
            client_a.get(
                f"/api/fiscal/retenciones-iva/?periodo={periodo}&estado=EMITIDO&tipo_operacion=COMPRA"
            ).status_code
            == 200
        )
        assert client_a.get(f"/api/fiscal/retenciones-islr/?periodo={periodo}&estado=EMITIDO").status_code == 200
        assert (
            client_a.get(
                f"/api/fiscal/libro-inventario-art177/?empresa={empresa_a.id_empresa}&desde=bad-date"
            ).status_code
            == 400
        )

        bad_uuid = str(uuid.uuid4())
        assert (
            client_a.post(
                "/api/fiscal/retenciones-iva/emitir/",
                {
                    "contacto": str(prov_a.id_contacto),
                    "factura_compra": bad_uuid,
                    "numero_documento": "F-1",
                    "base_imponible": "10.00",
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/fiscal/retenciones-iva/emitir/",
                {
                    "contacto": str(prov_a.id_contacto),
                    "factura_venta": bad_uuid,
                    "numero_documento": "F-1",
                    "base_imponible": "10.00",
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/fiscal/retenciones-islr/emitir/",
                {
                    "contacto": bad_uuid,
                    "concepto": str(concepto.id),
                    "numero_factura": "F-1",
                    "monto_operacion": "10.00",
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/fiscal/retenciones-islr/emitir/",
                {
                    "contacto": str(prov_a.id_contacto),
                    "concepto": bad_uuid,
                    "numero_factura": "F-1",
                    "monto_operacion": "10.00",
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/fiscal/retenciones-islr/emitir/",
                {
                    "contacto": str(prov_a.id_contacto),
                    "concepto": str(concepto.id),
                    "factura_compra": bad_uuid,
                    "numero_factura": "F-1",
                    "monto_operacion": "10.00",
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/fiscal/imprenta-digital/emitir/",
                {"tipo_documento": "FACTURA", "referencia_documento": "F-X", "proveedor": "THE_FACTORY_HKA"},
                format="json",
            ).status_code
            == 400
        )

        # Imprenta Digital: consultar_estado SIMULADO, tipo inválido y _default_https_transport
        assert (
            SimuladoImprentaAdapter().consultar_estado(empresa=empresa_a, numero_control="SIM-1")["estado"]
            == "EMITIDO"
        )
        with pytest.raises(ImprentaDigitalError):
            emitir_en_imprenta_digital(empresa=empresa_a, tipo_documento="INVALIDO", referencia_documento="X-1")
        with pytest.raises(ImprentaDigitalError):
            _default_https_transport("http://insecure.local/emitir", {"a": 1}, {})

        class _FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"numero_control": "HTTPS-001"}'

        monkeypatch.setattr("apps.localizacion_ve.imprenta_digital.urlopen", lambda req, timeout=15: _FakeResp())
        assert (
            _default_https_transport("https://api.unidigital.test/v1/emitir", {"ok": True}, {})["numero_control"]
            == "HTTPS-001"
        )

        def _fail_urlopen(req, timeout=15):
            raise URLError("timeout")

        monkeypatch.setattr("apps.localizacion_ve.imprenta_digital.urlopen", _fail_urlopen)
        with pytest.raises(ImprentaDigitalError):
            _default_https_transport("https://api.unidigital.test/v1/emitir", {"ok": True}, {})

        cfg = ConfiguracionFiscalEmpresa.objects.get(id_empresa=empresa_a)
        cfg.imprenta_digital_url = "https://cfg.unidigital.test"
        cfg.save(update_fields=["imprenta_digital_url"])
        uni = UnidigitalImprentaAdapter(transport=lambda u, p, h, timeout=15: {"sin_numero": True})
        assert uni._endpoint(empresa_a, "v1/ok") == "https://cfg.unidigital.test/v1/ok"
        with pytest.raises(ImprentaDigitalError):
            uni.emitir_documento(empresa=empresa_a, tipo_documento="FACTURA", referencia_documento="F-ERR", payload={})
