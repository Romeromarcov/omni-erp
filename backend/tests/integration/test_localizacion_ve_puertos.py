"""Cobertura integral PR-25: 6/6 puertos localizacion_ve (ADR-007) + REST + MCP."""

from __future__ import annotations

import asyncio
import datetime
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import mcp_server
from apps.core.models import CapabilityToken, Empresa
from apps.crm.models import Cliente
from apps.finanzas.models import MetodoPago, MetodoPagoEmpresaActiva, Moneda, TasaCambio
from apps.fiscal.models import ConfiguracionFiscalEmpresa, PeriodoFiscal
from apps.localizacion import ports, registry, services
from apps.localizacion.mcp import MCP_TOOLS as LOCALIZACION_MCP_TOOLS
from apps.localizacion.mcp import localizacion_estado_empresa
from apps.localizacion_ve.adapters import (
    CalculadoraNominaVE,
    GeneradorDocumentoLegalVE,
    LibroLegalVE,
    MetodosPagoLocalesVE,
    MotorImpuestosVE,
    ProveedorTasasVE,
    _metadatos_metodo_pago_ve,
)
from apps.nomina.calculo_lottt import ResultadoNomina
from apps.ventas.models import FacturaFiscal, NotaCreditoFiscal, NotaCreditoVenta

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

URL_ESTADO = "/api/localizacion/estado/"

TODOS_LOS_PUERTOS = (
    "MotorImpuestos",
    "GeneradorDocumentoLegal",
    "CalculadoraNomina",
    "LibroLegal",
    "ProveedorTasas",
    "MetodosPagoLocales",
)


def _assert_sin_floats(valor) -> None:
    assert not isinstance(valor, float), f"Se encontró float prohibido (R-CODE-4): {valor!r}"
    if isinstance(valor, dict):
        for v in valor.values():
            _assert_sin_floats(v)
    elif isinstance(valor, (list, tuple)):
        for v in valor:
            _assert_sin_floats(v)


def _crear_token(empresa, scopes: list[str], *, creado_por=None) -> str:
    tok = CapabilityToken.objects.create(
        empresa=empresa,
        nombre="tok-l10n",
        scopes=scopes,
        activo=True,
        creado_por=creado_por,
    )
    return str(tok.token)


@pytest.fixture
def moneda_ves(db):
    return Moneda.objects.get_or_create(
        codigo_iso="VES",
        defaults={
            "nombre": "Bolívar",
            "simbolo": "Bs.",
            "tipo_moneda": "fiat",
            "es_generica": True,
            "es_publica": True,
        },
    )[0]


@pytest.fixture
def moneda_usdt(db):
    return Moneda.objects.get_or_create(
        codigo_iso="USDT",
        defaults={
            "nombre": "Tether",
            "simbolo": "USDT",
            "tipo_moneda": "crypto",
            "es_generica": True,
            "es_publica": True,
        },
    )[0]


@pytest.fixture
def empresa_ve(db, moneda_usd):
    return Empresa.objects.create(
        nombre_legal="Comercial Caracas C.A.",
        identificador_fiscal="J-30543012-5",
        id_moneda_base=moneda_usd,
        pais_codigo_iso="VE",
        localizacion_legal_activa=True,
        localizacion_mercado_activa=True,
    )


@pytest.fixture
def empresa_ven(db, moneda_usd):
    return Empresa.objects.create(
        nombre_legal="Distribuidora Valencia S.A.",
        identificador_fiscal="J-40123456-7",
        id_moneda_base=moneda_usd,
        pais_codigo_iso="VEN",
        localizacion_legal_activa=True,
        localizacion_mercado_activa=True,
    )


@pytest.fixture
def cliente_ve(db, empresa_ve):
    return Cliente.objects.create(
        id_empresa=empresa_ve,
        razon_social="Cliente Barquisimeto C.A.",
        rif="J-30999888-1",
    )


# ── 1. Registry, Alias ISO y 6 NoOp ──────────────────────────────────────────


class TestRegistryYNoOp:
    def test_normalizar_codigo_pais_ve_y_ven(self):
        assert registry.normalizar_codigo_pais("ve") == "VE"
        assert registry.normalizar_codigo_pais("VE") == "VE"
        assert registry.normalizar_codigo_pais("ven") == "VE"
        assert registry.normalizar_codigo_pais(" VEN ") == "VE"
        assert registry.normalizar_codigo_pais("co") == "CO"
        assert registry.normalizar_codigo_pais("") is None
        assert registry.normalizar_codigo_pais("   ") is None
        assert registry.normalizar_codigo_pais(None) is None

    def test_paises_registrados_mantiene_ve_sin_duplicar_ven(self):
        paises = registry.paises_registrados()
        assert "VE" in paises
        assert "VEN" not in paises

        puertos_ve = registry.get("VE")
        puertos_ven = registry.get("ven")
        assert puertos_ve is not None
        assert puertos_ve == puertos_ven
        assert set(puertos_ve.keys()) == set(TODOS_LOS_PUERTOS)

    def test_register_y_get_normaliza_y_rechaza_vacio(self):
        sentinel = {"MotorImpuestos": ports.MotorImpuestosNoOp()}
        try:
            registry.register("xx", sentinel)
            assert registry.get("XX") == sentinel
            assert "XX" in registry.paises_registrados()
        finally:
            registry._LOCALIZACIONES.pop("XX", None)

        with pytest.raises(ValueError, match="vacío"):
            registry.register("", sentinel)
        assert registry.get("") is None
        assert registry.get(None) is None

    def test_seis_implementaciones_noop_explicitas(self, empresa_ve):
        assert isinstance(ports.MotorImpuestosNoOp(), ports.MotorImpuestos)
        assert isinstance(ports.GeneradorDocumentoLegalNoOp(), ports.GeneradorDocumentoLegal)
        assert isinstance(ports.CalculadoraNominaNoOp(), ports.CalculadoraNomina)
        assert isinstance(ports.LibroLegalNoOp(), ports.LibroLegal)
        assert isinstance(ports.ProveedorTasasNoOp(), ports.ProveedorTasas)
        assert isinstance(ports.MetodosPagoLocalesNoOp(), ports.MetodosPagoLocales)

        imp = ports.MotorImpuestosNoOp().calcular(subtotal=Decimal("250.00"), empresa=empresa_ve)
        assert imp == {"iva": Decimal("0"), "igtf": Decimal("0"), "total_impuestos": Decimal("0")}

        doc_obj = ports.GeneradorDocumentoLegalNoOp().emitir(
            documento=SimpleNamespace(tipo_documento="FACTURA"),
            empresa=empresa_ve,
        )
        assert doc_obj["requiere_pie_legal_seniat"] is False
        assert doc_obj["noop"] is True
        assert doc_obj["total"] == Decimal("0")

        doc_dict = ports.GeneradorDocumentoLegalNoOp().emitir(
            documento={"tipo_documento": "NOTA"},
            empresa=empresa_ve,
        )
        assert doc_dict["tipo_documento"] == "NOTA"
        assert doc_dict["noop"] is True

        nom = ports.CalculadoraNominaNoOp().calcular(empleado=None, periodo=None, empresa=empresa_ve)
        assert nom["neto_pagar"] == Decimal("0")
        assert nom["total_deducciones"] == Decimal("0")
        assert nom["noop"] is True
        esperados_nomina = set(ResultadoNomina.__dataclass_fields__.keys())
        assert set(nom.keys()) - {"noop"} == esperados_nomina
        for clave in esperados_nomina:
            assert nom[clave] == Decimal("0")

        assert ports.LibroLegalNoOp().generar(empresa=empresa_ve, periodo="2026-05", tipo="ventas") == ""
        assert (
            ports.LibroLegalNoOp().generar(empresa=empresa_ve, periodo="2026-05", tipo="ventas", formato="pdf") == b""
        )
        assert ports.ProveedorTasasNoOp().obtener_tasa(origen="USD", destino="VES", empresa=empresa_ve) is None
        assert ports.MetodosPagoLocalesNoOp().listar(empresa=empresa_ve) == []

    def test_flags_capas_y_paises_no_ve(self, moneda_usd):
        emp_ven = Empresa.objects.create(
            nombre_legal="VEN Full",
            identificador_fiscal="J-11111111-1",
            id_moneda_base=moneda_usd,
            pais_codigo_iso="VEN",
            localizacion_legal_activa=True,
            localizacion_mercado_activa=True,
        )
        loc_ven = services.get_localizacion(emp_ven)
        assert isinstance(loc_ven["MotorImpuestos"], MotorImpuestosVE)
        assert isinstance(loc_ven["GeneradorDocumentoLegal"], GeneradorDocumentoLegalVE)
        assert isinstance(loc_ven["CalculadoraNomina"], CalculadoraNominaVE)
        assert isinstance(loc_ven["LibroLegal"], LibroLegalVE)
        assert isinstance(loc_ven["ProveedorTasas"], ProveedorTasasVE)
        assert isinstance(loc_ven["MetodosPagoLocales"], MetodosPagoLocalesVE)

        res_ven = services.resumen_localizacion(emp_ven)
        assert res_ven["pais_codigo_iso"] == "VEN"
        assert res_ven["pais_normalizado"] == "VE"
        assert all(
            res_ven["puertos"][p]["activo"] is True and not res_ven["puertos"][p]["es_noop"] for p in TODOS_LOS_PUERTOS
        )

        # Solo capa legal desactivada: 4 legales -> NoOp; 2 de mercado -> VE
        emp_ven.localizacion_legal_activa = False
        emp_ven.localizacion_mercado_activa = True
        loc_sin_legal = services.get_localizacion(emp_ven)
        assert isinstance(loc_sin_legal["MotorImpuestos"], ports.MotorImpuestosNoOp)
        assert isinstance(loc_sin_legal["GeneradorDocumentoLegal"], ports.GeneradorDocumentoLegalNoOp)
        assert isinstance(loc_sin_legal["CalculadoraNomina"], ports.CalculadoraNominaNoOp)
        assert isinstance(loc_sin_legal["LibroLegal"], ports.LibroLegalNoOp)
        assert isinstance(loc_sin_legal["ProveedorTasas"], ProveedorTasasVE)
        assert isinstance(loc_sin_legal["MetodosPagoLocales"], MetodosPagoLocalesVE)

        # Solo capa mercado desactivada: 4 legales -> VE; 2 de mercado -> NoOp
        emp_ven.localizacion_legal_activa = True
        emp_ven.localizacion_mercado_activa = False
        loc_sin_mercado = services.get_localizacion(emp_ven)
        assert isinstance(loc_sin_mercado["MotorImpuestos"], MotorImpuestosVE)
        assert isinstance(loc_sin_mercado["GeneradorDocumentoLegal"], GeneradorDocumentoLegalVE)
        assert isinstance(loc_sin_mercado["CalculadoraNomina"], CalculadoraNominaVE)
        assert isinstance(loc_sin_mercado["LibroLegal"], LibroLegalVE)
        assert isinstance(loc_sin_mercado["ProveedorTasas"], ports.ProveedorTasasNoOp)
        assert isinstance(loc_sin_mercado["MetodosPagoLocales"], ports.MetodosPagoLocalesNoOp)

        # Países no-VE y None -> los 6 en NoOp
        for pais in ("CO", "US", None, ""):
            emp_ext = Empresa.objects.create(
                nombre_legal=f"Ext {pais}",
                identificador_fiscal=f"EXT-{uuid.uuid4().hex[:8]}",
                id_moneda_base=moneda_usd,
                pais_codigo_iso=pais,
                localizacion_legal_activa=True,
                localizacion_mercado_activa=True,
            )
            loc_ext = services.get_localizacion(emp_ext)
            res_ext = services.resumen_localizacion(emp_ext)
            assert set(loc_ext.keys()) == set(TODOS_LOS_PUERTOS)
            assert all(
                res_ext["puertos"][p]["es_noop"] is True and res_ext["puertos"][p]["activo"] is False
                for p in TODOS_LOS_PUERTOS
            )


# ── 2. Los 6 Puertos VE ──────────────────────────────────────────────────────


class TestSeisPuertosVE:
    def test_motor_impuestos_ve_decimal_exacto(self, empresa_ve):
        motor = services.get_localizacion(empresa_ve)["MotorImpuestos"]
        res = motor.calcular(subtotal=Decimal("100.00"), empresa=empresa_ve)
        _assert_sin_floats(res)
        assert res["base_imponible"] == Decimal("100.00")
        assert res["tasa_iva"] == Decimal("0.16")
        assert res["monto_iva"] == Decimal("16.00")
        assert res["total"] == Decimal("116.00")
        with pytest.raises(ValidationError):
            motor.calcular(subtotal=True, empresa=empresa_ve)

    def test_generador_documento_legal_ve_con_modelos_y_dto(self, empresa_ve, empresa_b, cliente_ve, moneda_usd):
        gen = services.get_localizacion(empresa_ve)["GeneradorDocumentoLegal"]
        fecha = datetime.date(2026, 5, 10)

        # FacturaFiscal real
        factura = FacturaFiscal.objects.create(
            id_empresa=empresa_ve,
            id_cliente=cliente_ve,
            numero_control="00-00000101",
            numero_factura="FAC-000101",
            fecha_emision=fecha,
            id_moneda=moneda_usd,
            base_imponible=Decimal("200.0000"),
            monto_iva=Decimal("32.0000"),
            monto_igtf=Decimal("6.9600"),
            monto_total=Decimal("238.9600"),
            estado="EMITIDA",
        )
        out_fac = gen.emitir(documento=factura, empresa=empresa_ve)
        _assert_sin_floats(out_fac)
        assert out_fac["tipo_documento"] == "FACTURA_FISCAL"
        assert out_fac["numero_documento"] == "FAC-000101"
        assert out_fac["numero_control"] == "00-00000101"
        assert out_fac["fecha_emision"] == "2026-05-10"
        assert out_fac["moneda"] == "USD"
        assert out_fac["rif_emisor"] == "J-30543012-5"
        assert out_fac["rif_receptor"] == "J-30999888-1"
        assert out_fac["subtotal"] == Decimal("200.0000")
        assert out_fac["iva"] == Decimal("32.0000")
        assert out_fac["igtf"] == Decimal("6.9600")
        assert out_fac["exento"] == Decimal("0")
        assert out_fac["total"] == Decimal("238.9600")
        assert out_fac["requiere_pie_legal_seniat"] is True
        assert out_fac["pais"] == "VE"

        # NotaCreditoFiscal real
        nc_fiscal = NotaCreditoFiscal.objects.create(
            id_empresa=empresa_ve,
            id_cliente=cliente_ve,
            id_factura_origen=factura,
            numero_control=factura.numero_control,
            numero_nota_credito="NCF-0001",
            fecha_emision=fecha,
            base_imponible=Decimal("50.0000"),
            monto_iva=Decimal("8.0000"),
            monto_total=Decimal("58.0000"),
            id_moneda=moneda_usd,
            motivo="DEVOLUCION",
            estado="EMITIDA",
        )
        out_ncf = gen.emitir(documento=nc_fiscal, empresa=empresa_ve)
        _assert_sin_floats(out_ncf)
        assert out_ncf["tipo_documento"] == "NOTA_CREDITO_FISCAL"
        assert out_ncf["numero_documento"] == "NCF-0001"
        assert out_ncf["numero_control"] == "00-00000101"
        assert out_ncf["total"] == Decimal("58.0000")
        assert out_ncf["requiere_pie_legal_seniat"] is True

        # NotaCreditoVenta real (hereda numero_control de id_factura_origen)
        nc_venta = NotaCreditoVenta.objects.create(
            id_empresa=empresa_ve,
            id_cliente=cliente_ve,
            id_factura_origen=factura,
            numero_nota_credito="NCV-0001",
            fecha_emision=fecha,
            motivo="DESCUENTO",
            monto_total=Decimal("25.0000"),
            id_moneda=moneda_usd,
            estado="EMITIDA",
        )
        out_ncv = gen.emitir(documento=nc_venta, empresa=empresa_ve)
        _assert_sin_floats(out_ncv)
        assert out_ncv["tipo_documento"] == "NOTA_CREDITO_VENTA"
        assert out_ncv["numero_control"] == "00-00000101"
        assert out_ncv["subtotal"] == Decimal("25.0000")
        assert out_ncv["total"] == Decimal("25.0000")

        # DTO dict con RIF sin guiones para verificar normalización y casos borde
        out_dto = gen.emitir(
            documento={
                "tipo_documento": "FACTURA_FISCAL",
                "numero_documento": "F-DTO-1",
                "numero_control": "00-00000999",
                "fecha_emision": datetime.datetime(2026, 5, 11, 14, 30),
                "moneda": "ves",
                "rif_receptor": "v123456783",
                "subtotal": "100.00",
                "iva": "16.00",
                "igtf": "0.00",
                "exento": "20.00",
            },
            empresa=empresa_ve,
        )
        assert out_dto["rif_receptor"] == "V-12345678-3"
        assert out_dto["fecha_emision"] == "2026-05-11"
        assert out_dto["moneda"] == "VES"
        assert out_dto["total"] == Decimal("136.00")

        # DTO mínimo sin cliente explícito ni montos -> fallback a id_moneda_base y ceros
        out_min = gen.emitir(documento=SimpleNamespace(fecha_emision="2026-05-12"), empresa=empresa_ve)
        assert out_min["tipo_documento"] == "DOCUMENTO_FISCAL"
        assert out_min["rif_receptor"] == ""
        assert out_min["moneda"] == "USD"
        assert out_min["subtotal"] == Decimal("0")
        assert out_min["total"] == Decimal("0")

        # Casos negativos: documento ajeno (R-CODE-1), ORM fail-closed, anidados cross-tenant,
        # RIF inválido/faltante, montos negativos/descuadrados e inválidos
        with pytest.raises(ValidationError, match="no pertenece"):
            gen.emitir(documento=factura, empresa=empresa_b)

        with pytest.raises(PermissionError, match="no pertenece"):
            gen.emitir(documento={"empresa_id": str(empresa_b.pk), "rif_receptor": "J-30999888-1"}, empresa=empresa_ve)

        emp_sin_pk = SimpleNamespace(identificador_fiscal="J-30543012-5")
        with pytest.raises(ValidationError, match="no pertenece"):
            gen.emitir(documento=SimpleNamespace(empresa=SimpleNamespace()), empresa=emp_sin_pk)

        # ORM sin empresa asociada debe fallar cerrado (ValidationError)
        factura_huerfana = FacturaFiscal(
            id_cliente=cliente_ve,
            numero_control="00-00000777",
            numero_factura="FAC-HUERFANA",
            fecha_emision=fecha,
            id_moneda=moneda_usd,
            base_imponible=Decimal("10.00"),
            monto_iva=Decimal("1.60"),
            monto_total=Decimal("11.60"),
        )
        with pytest.raises(ValidationError, match="sin empresa asociada"):
            gen.emitir(documento=factura_huerfana, empresa=empresa_ve)

        # Cliente de otra empresa en documento de empresa_ve (cross-tenant anidado)
        cliente_ajeno = Cliente.objects.create(id_empresa=empresa_b, razon_social="Ajeno S.A.", rif="J-90111222-3")
        with pytest.raises(ValidationError, match="no pertenece"):
            gen.emitir(
                documento={"id_empresa": empresa_ve, "id_cliente": cliente_ajeno, "subtotal": "10.00"},
                empresa=empresa_ve,
            )

        # Cliente ORM sin empresa asociada en DTO
        with pytest.raises(ValidationError, match="sin empresa asociada"):
            gen.emitir(
                documento={"id_empresa": empresa_ve, "cliente": Cliente(rif="J-30999888-1"), "subtotal": "10.00"},
                empresa=empresa_ve,
            )

        # Factura origen de otra empresa en NotaCreditoFiscal con numero_control explícito (cross-tenant anidado)
        factura_b = FacturaFiscal.objects.create(
            id_empresa=empresa_b,
            id_cliente=cliente_ajeno,
            numero_control="00-00000888",
            numero_factura="FAC-B-888",
            fecha_emision=fecha,
            id_moneda=moneda_usd,
            base_imponible=Decimal("100.00"),
            monto_iva=Decimal("16.00"),
            monto_total=Decimal("116.00"),
            estado="EMITIDA",
        )
        nc_origen_ajeno = NotaCreditoFiscal(
            id_empresa=empresa_ve,
            id_cliente=cliente_ve,
            id_factura_origen=factura_b,
            numero_control="00-00000888",
            numero_nota_credito="NCF-AJENA",
            fecha_emision=fecha,
            base_imponible=Decimal("10.00"),
            monto_iva=Decimal("1.60"),
            monto_total=Decimal("11.60"),
            id_moneda=moneda_usd,
            motivo="DEVOLUCION",
            estado="EMITIDA",
        )
        with pytest.raises(ValidationError, match="no pertenece"):
            gen.emitir(documento=nc_origen_ajeno, empresa=empresa_ve)

        # Montos negativos rechazados con ValidationError
        for campo_neg in ("subtotal", "iva", "igtf", "exento", "total"):
            payload_neg = {"rif_receptor": "J-30999888-1", campo_neg: "-1.00"}
            if campo_neg != "total" and campo_neg != "subtotal":
                payload_neg["subtotal"] = "10.00"
            with pytest.raises(ValidationError, match="negativo"):
                gen.emitir(documento=payload_neg, empresa=empresa_ve)

        # Descuadre entre componentes explícitos y total rechazado con ValidationError
        with pytest.raises(ValidationError, match="no cuadra"):
            gen.emitir(
                documento={
                    "rif_receptor": "J-30999888-1",
                    "subtotal": "100.00",
                    "iva": "16.00",
                    "igtf": "3.00",
                    "exento": "10.00",
                    "total": "200.00",
                },
                empresa=empresa_ve,
            )

        with pytest.raises(ValueError, match="RIF"):
            gen.emitir(
                documento={"rif_receptor": "INVALIDO-123", "subtotal": "10"},
                empresa=empresa_ve,
            )

        with pytest.raises(ValueError, match="RIF del cliente"):
            gen.emitir(documento={"rif_receptor": "", "subtotal": "10"}, empresa=empresa_ve)

        for monto_malo in (True, "no-num", Decimal("NaN")):
            with pytest.raises(ValidationError):
                gen.emitir(documento={"subtotal": monto_malo}, empresa=empresa_ve)

        with pytest.raises(ValueError):
            gen.emitir(documento=None, empresa=empresa_ve)

        with pytest.raises(ValueError):
            gen.emitir(documento=factura, empresa=None)

    def test_calculadora_nomina_ve(self, empresa_ve):
        calc = services.get_localizacion(empresa_ve)["CalculadoraNomina"]
        empleado = SimpleNamespace(salario_mensual=Decimal("1000.00"), fecha_ingreso=datetime.date(2023, 1, 1))
        periodo = SimpleNamespace(fecha_fin=datetime.date(2026, 5, 15))
        res = calc.calcular(empleado=empleado, periodo=periodo, empresa=empresa_ve)
        _assert_sin_floats(res)
        assert isinstance(res["salario_periodo"], Decimal)
        assert isinstance(res["sso"], Decimal)
        assert res["neto_pagar"] > Decimal("0")
        assert res["total_deducciones"] > Decimal("0")

    def test_libro_legal_ve_ventas_compras_formatos_y_aislamiento(self, empresa_ve, empresa_b, cliente_ve, moneda_usd):
        libro = services.get_localizacion(empresa_ve)["LibroLegal"]
        cliente_b = Cliente.objects.create(id_empresa=empresa_b, razon_social="Cli B", rif="J-90000001-1")

        FacturaFiscal.objects.create(
            id_empresa=empresa_ve,
            id_cliente=cliente_ve,
            numero_control="00-00000001",
            numero_factura="FAC-VE-MAY",
            fecha_emision=datetime.date(2026, 5, 12),
            id_moneda=moneda_usd,
            base_imponible=Decimal("100.00"),
            monto_iva=Decimal("16.00"),
            monto_total=Decimal("116.00"),
            estado="EMITIDA",
        )
        # Borrador excluido y factura de otra empresa excluida (R-CODE-1)
        FacturaFiscal.objects.create(
            id_empresa=empresa_ve,
            id_cliente=cliente_ve,
            numero_control="00-00000002",
            numero_factura="FAC-VE-BORR",
            fecha_emision=datetime.date(2026, 5, 14),
            id_moneda=moneda_usd,
            base_imponible=Decimal("50.00"),
            monto_iva=Decimal("8.00"),
            monto_total=Decimal("58.00"),
            estado="BORRADOR",
        )
        FacturaFiscal.objects.create(
            id_empresa=empresa_b,
            id_cliente=cliente_b,
            numero_control="00-00000099",
            numero_factura="FAC-B-AJENA",
            fecha_emision=datetime.date(2026, 5, 14),
            id_moneda=moneda_usd,
            base_imponible=Decimal("500.00"),
            monto_iva=Decimal("80.00"),
            monto_total=Decimal("580.00"),
            estado="EMITIDA",
        )

        # Diversos formatos de período válidos
        periodo_obj = PeriodoFiscal(id_empresa=empresa_ve, año=2026, mes=5)
        for fmt_periodo in (
            "2026-05",
            (5, 2026),
            (2026, 5),
            {"anio": 2026, "mes": 5},
            {"fecha_inicio": "2026-05-01", "fecha_fin": "2026-05-31"},
            SimpleNamespace(fecha_inicio=datetime.datetime(2026, 5, 1, 8, 0), fecha_fin=datetime.date(2026, 5, 31)),
            datetime.date(2026, 5, 20),
            datetime.datetime(2026, 5, 20, 9, 0),
            periodo_obj,
            (datetime.date(2026, 5, 1), datetime.date(2026, 5, 31)),
        ):
            txt = libro.generar(empresa=empresa_ve, periodo=fmt_periodo, tipo="ventas")
            assert "FAC-VE-MAY" in txt
            assert "FAC-VE-BORR" not in txt
            assert "FAC-B-AJENA" not in txt

        compras_txt = libro.generar(empresa=empresa_ve, periodo="2026-05", tipo="compras")
        assert compras_txt.startswith("RIF_EMISOR|RIF_RECEPTOR|")

        ventas_pdf = libro.generar(empresa=empresa_ve, periodo="2026-05", tipo="ventas", formato="pdf")
        assert isinstance(ventas_pdf, bytes) and ventas_pdf.startswith(b"%PDF-")

        compras_pdf = libro.generar(empresa=empresa_ve, periodo="2026-05", tipo="compras", formato="pdf")
        assert isinstance(compras_pdf, bytes) and compras_pdf.startswith(b"%PDF-")

        # Casos negativos
        with pytest.raises(ValueError, match="empresa"):
            libro.generar(empresa=None, periodo="2026-05", tipo="ventas")

        with pytest.raises(ValueError, match="inválido"):
            libro.generar(empresa=empresa_ve, periodo="2026-05", tipo="nomina")

        with pytest.raises(ValueError, match="Formato"):
            libro.generar(empresa=empresa_ve, periodo="2026-05", tipo="ventas", formato="csv")

        for malo in (
            "2026-13",
            (13, 2026),
            (5, 1800),
            {"anio": 2200, "mes": 5},
            (2026,),
            (True, 2026),
            ("abc", 2026),
            (datetime.date(2026, 5, 31), datetime.date(2026, 5, 1)),
            {"fecha_inicio": "2026-05-31", "fecha_fin": "2026-05-01"},
            {"fecha_inicio": "fecha-mala", "fecha_fin": "2026-05-31"},
            {"fecha_inicio": 123, "fecha_fin": "2026-05-31"},
            None,
            {"anio": 2026},
            202605,
        ):
            with pytest.raises(ValueError):
                libro.generar(empresa=empresa_ve, periodo=malo, tipo="ventas")

    def test_proveedor_tasas_ve_sin_http_y_aislamiento(self, empresa_ve, empresa_b, moneda_usd, moneda_ves):
        prov = services.get_localizacion(empresa_ve)["ProveedorTasas"]
        hoy = timezone.localdate()

        # Sin tasas aún -> None
        assert prov.obtener_tasa(origen="USD", destino="VES", empresa=empresa_ve) is None
        assert prov.obtener_tasa(origen="", destino="VES") is None
        assert prov.obtener_tasa(origen="usd", destino="USD") == Decimal("1")

        # Tasa global OFICIAL_BCV
        TasaCambio.objects.create(
            id_empresa=None,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_ves,
            tipo_tasa="OFICIAL_BCV",
            valor_tasa=Decimal("36.50000000"),
            fecha_tasa=hoy,
        )
        tasa_global = prov.obtener_tasa(origen=" usd ", destino="ves")
        assert isinstance(tasa_global, Decimal)
        assert not isinstance(tasa_global, float)
        assert tasa_global == Decimal("36.50000000")

        # Tasa privada de empresa_ve tiene prioridad sobre global; empresa_b NO la ve
        TasaCambio.objects.create(
            id_empresa=empresa_ve,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_ves,
            tipo_tasa="ESPECIAL_USUARIO",
            valor_tasa=Decimal("41.25000000"),
            fecha_tasa=hoy,
        )
        tasa_emp = prov.obtener_tasa(origen="USD", destino="VES", empresa=empresa_ve)
        tasa_b = prov.obtener_tasa(origen="USD", destino="VES", empresa=empresa_b)
        assert tasa_emp == Decimal("41.25000000")
        assert tasa_b == Decimal("36.50000000")

        # Moneda inexistente -> None
        assert prov.obtener_tasa(origen="USD", destino="XYZ", empresa=empresa_ve) is None

        # Tasa sin valor_tasa -> None
        with mock.patch("apps.finanzas.services.obtener_tasa_cambio", return_value=SimpleNamespace(valor_tasa=None)):
            assert prov.obtener_tasa(origen="USD", destino="VES", empresa=empresa_ve) is None

    def test_metodos_pago_locales_ve_igtf_y_aislamiento(
        self, empresa_ve, empresa_b, moneda_usd, moneda_ves, moneda_usdt
    ):
        puerto = services.get_localizacion(empresa_ve)["MetodosPagoLocales"]

        m_bs = MetodoPago.objects.create(
            nombre_metodo="Efectivo Bs VE",
            tipo_metodo="EFECTIVO",
            activo=True,
            es_generico=True,
        )
        m_bs.monedas.add(moneda_ves)

        m_zelle = MetodoPago.objects.create(
            nombre_metodo="Zelle Corporativo",
            tipo_metodo="ELECTRONICO",
            empresa=empresa_ve,
            activo=True,
        )
        m_zelle.monedas.add(moneda_usd)

        m_pm = MetodoPago.objects.create(
            nombre_metodo="Pago Móvil Instantáneo",
            tipo_metodo="ELECTRONICO",
            empresa=empresa_ve,
            activo=True,
        )
        m_pm.monedas.add(moneda_ves)

        m_crypto = MetodoPago.objects.create(
            nombre_metodo="Binance Pay USDT",
            tipo_metodo="ELECTRONICO",
            empresa=empresa_ve,
            activo=True,
        )
        m_crypto.monedas.add(moneda_usdt)

        m_usd_cash = MetodoPago.objects.create(
            nombre_metodo="Efectivo Divisa",
            tipo_metodo="EFECTIVO",
            empresa=empresa_ve,
            activo=True,
        )
        m_usd_cash.monedas.add(moneda_usd)

        m_transf_usd = MetodoPago.objects.create(
            nombre_metodo="Wire USD",
            tipo_metodo="ELECTRONICO",
            empresa=empresa_ve,
            activo=True,
        )
        m_transf_usd.monedas.add(moneda_usd)

        m_transf_bs = MetodoPago.objects.create(
            nombre_metodo="Transferencia Nacional",
            tipo_metodo="ELECTRONICO",
            empresa=empresa_ve,
            activo=True,
        )
        m_transf_bs.monedas.add(moneda_ves)

        MetodoPago.objects.create(
            nombre_metodo="Punto TDD",
            tipo_metodo="TARJETA",
            empresa=empresa_ve,
            activo=True,
        )
        MetodoPago.objects.create(
            nombre_metodo="Crédito Directo",
            tipo_metodo="CREDITO",
            empresa=empresa_ve,
            activo=True,
        )
        MetodoPago.objects.create(
            nombre_metodo="Custom Override",
            tipo_metodo="OTRO",
            empresa=empresa_ve,
            activo=True,
            documento_json={"es_divisa": False, "categoria_ve": "ESPECIAL_VE", "aplica_igtf": False},
        )

        # Privado de empresa_b: jamás visible para empresa_ve (R-CODE-1)
        MetodoPago.objects.create(
            nombre_metodo="Zelle Secreto Empresa B",
            tipo_metodo="ELECTRONICO",
            empresa=empresa_b,
            activo=True,
            es_generico=False,
            es_publico=False,
            documento_json={"secreto": "NO_FILTRAR"},
        )

        # Método sin empresa y sin es_generico/es_publico NO debe ser expuesto (alineado a MetodoPagoViewSet)
        MetodoPago.objects.create(
            nombre_metodo="Método Huérfano Sin Flags",
            tipo_metodo="OTRO",
            empresa=None,
            activo=True,
            es_generico=False,
            es_publico=False,
        )

        # Método desactivado por empresa_ve vía MetodoPagoEmpresaActiva
        m_desact = MetodoPago.objects.create(
            nombre_metodo="Cheque Desactivado",
            tipo_metodo="CHEQUE",
            empresa=empresa_ve,
            activo=True,
        )
        MetodoPagoEmpresaActiva.objects.filter(empresa=empresa_ve, metodo_pago=m_desact).update(activa=False)

        lista = puerto.listar(empresa=empresa_ve)
        nombres = [item["nombre_metodo"] for item in lista]
        assert nombres == sorted(nombres)  # determinista
        assert "Zelle Secreto Empresa B" not in nombres
        assert "Método Huérfano Sin Flags" not in nombres
        assert "Cheque Desactivado" not in nombres
        assert "secreto" not in str(lista)

        por_nombre = {item["nombre_metodo"]: item for item in lista}
        assert por_nombre["Efectivo Bs VE"]["aplica_igtf"] is False
        assert por_nombre["Efectivo Bs VE"]["categoria_ve"] == "EFECTIVO_BS"
        assert por_nombre["Efectivo Bs VE"]["es_divisa"] is False

        assert por_nombre["Pago Móvil Instantáneo"]["aplica_igtf"] is False
        assert por_nombre["Pago Móvil Instantáneo"]["categoria_ve"] == "PAGO_MOVIL"

        assert por_nombre["Zelle Corporativo"]["aplica_igtf"] is True
        assert por_nombre["Zelle Corporativo"]["es_divisa"] is True
        assert por_nombre["Zelle Corporativo"]["categoria_ve"] == "ZELLE"

        assert por_nombre["Binance Pay USDT"]["aplica_igtf"] is True
        assert por_nombre["Binance Pay USDT"]["categoria_ve"] == "CRYPTO"
        assert por_nombre["Efectivo Divisa"]["categoria_ve"] == "DIVISA_EFECTIVO"
        assert por_nombre["Wire USD"]["categoria_ve"] == "DIVISA_TRANSFERENCIA"
        assert por_nombre["Transferencia Nacional"]["categoria_ve"] == "TRANSFERENCIA_BS"
        assert por_nombre["Punto TDD"]["categoria_ve"] == "TARJETA"
        assert por_nombre["Crédito Directo"]["categoria_ve"] == "CREDITO"
        assert por_nombre["Custom Override"]["categoria_ve"] == "ESPECIAL_VE"
        assert por_nombre["Custom Override"]["aplica_igtf"] is False

        # Si ConfiguracionFiscalEmpresa desactiva aplica_igtf -> aplica_igtf pasa a False
        ConfiguracionFiscalEmpresa.objects.create(id_empresa=empresa_ve, contribuyente_iva=True, aplica_igtf=False)
        lista_sin_igtf = {item["nombre_metodo"]: item for item in puerto.listar(empresa=empresa_ve)}
        assert lista_sin_igtf["Zelle Corporativo"]["aplica_igtf"] is False

        with pytest.raises(ValueError):
            puerto.listar(empresa=None)
        with pytest.raises(ValueError):
            puerto.listar(empresa=SimpleNamespace(pais_codigo_iso="VE"))

        # Atributos booleanos directos es_divisa / aplica_igtf en el objeto método
        metodo_stub = SimpleNamespace(
            id_metodo_pago=uuid.uuid4(),
            nombre_metodo="Stub Directo",
            tipo_metodo="OTRO",
            documento_json=None,
            es_divisa=True,
            aplica_igtf=False,
            es_generico=False,
            es_publico=False,
            monedas=SimpleNamespace(all=lambda: []),
        )
        meta_stub = _metadatos_metodo_pago_ve(
            metodo_stub,
            empresa_permite_igtf=True,
            metodos_igtf=frozenset({"DIVISA_EFECTIVO"}),
        )
        assert meta_stub["es_divisa"] is True
        assert meta_stub["aplica_igtf"] is False


# ── 3. Endpoint REST y Tool MCP (R-CODE-7) ───────────────────────────────────


class TestLocalizacionRESTyMCP:
    def test_rest_estado_sin_auth_401(self):
        resp = APIClient().get(URL_ESTADO)
        assert resp.status_code == 401

    def test_rest_estado_multi_tenant_matriz_subsidiaria_y_validaciones(
        self, empresa_ve, empresa_b, user_a, moneda_usd
    ):
        user_a.empresas.add(empresa_ve)
        subsidiaria_co = Empresa.objects.create(
            nombre_legal="Sucursal Bogotá SAS",
            identificador_fiscal="CO-900111",
            empresa_matriz=empresa_ve,
            id_moneda_base=moneda_usd,
            pais_codigo_iso="CO",
            localizacion_legal_activa=False,
            localizacion_mercado_activa=False,
        )

        client = APIClient()
        client.force_authenticate(user=user_a)

        # Con user.id_empresa seteado a empresa_ve resuelve empresa_ve por defecto
        user_a.id_empresa = empresa_ve
        resp_default = client.get(URL_ESTADO)
        assert resp_default.status_code == 200
        body = resp_default.json()
        assert body["empresa_id"] == str(empresa_ve.pk)
        assert body["pais_normalizado"] == "VE"
        assert body["localizacion_legal_activa"] is True
        assert body["localizacion_mercado_activa"] is True
        assert set(body["puertos"].keys()) == set(TODOS_LOS_PUERTOS)
        assert all(info["activo"] is True and info["es_noop"] is False for info in body["puertos"].values())

        # Sin user.id_empresa explícito resuelve primera empresa M2M visible
        delattr(user_a, "id_empresa")
        resp_m2m = client.get(URL_ESTADO)
        assert resp_m2m.status_code == 200

        # Matriz -> Subsidiaria visible vía ?empresa_id=
        resp_sub = client.get(URL_ESTADO, {"empresa_id": str(subsidiaria_co.pk)})
        assert resp_sub.status_code == 200
        body_sub = resp_sub.json()
        assert body_sub["empresa_id"] == str(subsidiaria_co.pk)
        assert body_sub["pais_normalizado"] == "CO"
        assert all(info["activo"] is False and info["es_noop"] is True for info in body_sub["puertos"].values())

        # Empresa ajena -> 403
        resp_ajena = client.get(URL_ESTADO, {"empresa_id": str(empresa_b.pk)})
        assert resp_ajena.status_code == 403

        # UUID inválido -> 400
        assert client.get(URL_ESTADO, {"empresa_id": "no-es-uuid"}).status_code == 400
        assert client.get(URL_ESTADO, {"empresa_id": ""}).status_code == 400

        # NUL bytes en valor o llave -> 400
        assert client.get(f"{URL_ESTADO}?empresa_id=abc%00").status_code == 400
        assert client.get(f"{URL_ESTADO}?search=test%00").status_code == 400
        assert client.get(f"{URL_ESTADO}?foo%00bar=1").status_code == 400

    def test_rest_estado_superusuario_omni_y_usuario_sin_empresa(self, empresa_b):
        User = get_user_model()
        super_u = User.objects.create_user(
            username="super_omni_l10n",
            password="x",
            email="super_l10n@omni.test",
            is_active=True,
            es_superusuario_omni=True,
        )
        c_super = APIClient()
        c_super.force_authenticate(user=super_u)

        # Superusuario sin empresa propia y sin ?empresa_id= -> 400
        assert c_super.get(URL_ESTADO).status_code == 400

        # Superusuario con ?empresa_id= -> 200
        resp_ok = c_super.get(URL_ESTADO, {"empresa_id": str(empresa_b.pk)})
        assert resp_ok.status_code == 200
        assert resp_ok.json()["empresa_id"] == str(empresa_b.pk)

        # Superusuario con UUID de empresa inexistente -> 403
        assert c_super.get(URL_ESTADO, {"empresa_id": str(uuid.uuid4())}).status_code == 403

        # Usuario normal sin ninguna empresa -> 403
        sin_emp = User.objects.create_user(username="sin_emp_l10n", password="x", is_active=True)
        c_sin = APIClient()
        c_sin.force_authenticate(user=sin_emp)
        assert c_sin.get(URL_ESTADO).status_code == 403

        # Usuario autenticado vía capability_token (sin M2M empresas) usa fallback empresas.first() -> 200
        tok = CapabilityToken.objects.create(
            empresa=empresa_b,
            nombre="tok-rest-fallback",
            scopes=["localizacion:read"],
            activo=True,
        )
        user_tok = User.objects.create_user(username="tok_user_l10n", password="x", is_active=True)
        user_tok.capability_token = tok
        c_tok = APIClient()
        c_tok.force_authenticate(user=user_tok)
        resp_tok = c_tok.get(URL_ESTADO)
        assert resp_tok.status_code == 200
        assert resp_tok.json()["empresa_id"] == str(empresa_b.pk)

    def test_mcp_autodiscovery_scope_y_ejecucion(self, empresa_ven, empresa_b):
        assert {item["name"] for item in LOCALIZACION_MCP_TOOLS} == {"localizacion_estado_empresa"}
        assert "localizacion_estado_empresa" in mcp_server._DISCOVERED_TOOLS
        assert "apps.localizacion.mcp" in settings.MCP_AGENT_CAPABILITIES["module_paths"]
        assert "localizacion:read" in settings.MCP_AGENT_CAPABILITIES["scopes"]
        assert "apps.localizacion.mcp" in mcp_server._MCP_DEFAULT_MODULE_PATHS

        registradas = {tool.name for tool in asyncio.run(mcp_server.mcp.list_tools())}
        assert "localizacion_estado_empresa" in registradas

        tok_ok = _crear_token(empresa_ven, ["localizacion:read"])
        tok_otro_scope = _crear_token(empresa_ven, ["finanzas:read"])

        res = localizacion_estado_empresa(tok_ok, str(empresa_ven.pk))
        _assert_sin_floats(res)
        assert res["empresa_id"] == str(empresa_ven.pk)
        assert res["pais_codigo_iso"] == "VEN"
        assert res["pais_normalizado"] == "VE"
        assert set(res["puertos"].keys()) == set(TODOS_LOS_PUERTOS)
        assert all(p["activo"] is True for p in res["puertos"].values())

        # Sin empresa_id usa el tenant del token
        res_omiso = localizacion_estado_empresa(tok_ok)
        assert res_omiso == res

        # Errores de seguridad/validación
        with pytest.raises(PermissionError):
            localizacion_estado_empresa("no-es-token", str(empresa_ven.pk))

        with pytest.raises(PermissionError):
            localizacion_estado_empresa(tok_otro_scope, str(empresa_ven.pk))

        with pytest.raises(PermissionError):
            localizacion_estado_empresa(tok_ok, str(empresa_b.pk))

        with pytest.raises(ValueError, match="UUID"):
            localizacion_estado_empresa(tok_ok, "no-uuid")

        with pytest.raises(ValueError, match="UUID"):
            localizacion_estado_empresa(tok_ok, "   ")

        with pytest.raises(ValueError, match="inválidos"):
            localizacion_estado_empresa(tok_ok, f"{empresa_ven.pk}\x00")

        empresa_ven.activo = False
        empresa_ven.save(update_fields=["activo"])
        with pytest.raises(PermissionError, match="inactiva"):
            localizacion_estado_empresa(tok_ok)
