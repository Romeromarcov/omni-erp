"""Suite integral para ingesta multi-tenant de extractos bancarios, validación y saldos consolidados."""

from __future__ import annotations

import io
import zipfile
from datetime import date, datetime
from decimal import Decimal as D
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.core.models import CapabilityToken
from apps.finanzas.models import CuentaBancariaEmpresa, Moneda, TasaCambio
from apps.tesoreria.extractos import (
    FORMATOS_BANCO_SOPORTADOS,
    ExtractoBancarioError,
    consolidar_saldos_extractos,
    desactivar_extracto_bancario,
    importar_extracto_bancario,
    inferir_formato_banco,
    preparar_extracto,
    serializar_consolidado,
)
from apps.tesoreria.extractos.clasificacion import clasificar_linea
from apps.tesoreria.extractos.lector_hojas import construir_xlsx_simple, leer_filas_tabular
from apps.tesoreria.extractos.modelos_canonicos import (
    EstadoCuentaCanonico,
    LineaExtractoCanonica,
    validar_estado,
)
from apps.tesoreria.extractos.numeros import limpiar_ref, parse_fecha, parse_monto
from apps.tesoreria.extractos.parsers import extraer_sufijo_cuenta, parsear_extracto
from apps.tesoreria.extractos.saldos import CorteExtracto, consolidar_cortes
from apps.tesoreria.mcp import tesoreria_listar_extractos, tesoreria_saldos_extractos
from apps.tesoreria.models import ExtractoBancarioArchivo, MovimientoBancario


def _xlsx(filas: list[list[Any]]) -> bytes:
    return construir_xlsx_simple([("Movimientos", filas)])


def _linea(
    orden: int,
    deb: str,
    cre: str,
    saldo: str | None,
    *,
    ref: str = "1",
    desc: str = "X",
    fecha: date = date(2026, 9, 1),
    cuenta: str = "CTA-1",
    correlativo: str = "",
) -> LineaExtractoCanonica:
    return LineaExtractoCanonica(
        formato_banco="BANCAMIGA",
        cuenta_clave=cuenta,
        moneda="VES",
        fecha=fecha,
        referencia=ref,
        descripcion=desc,
        debito=D(deb),
        credito=D(cre),
        saldo=None if saldo is None else D(saldo),
        orden=orden,
        correlativo=correlativo,
    )


def _libro_deb_cred(con_inicial: bool = True, footer: str | None = None, codigo: bool = False) -> bytes:
    enc = ["Fecha", "Referencia", "Concepto", "Débito", "Crédito", "Saldo"]
    if codigo:
        enc.append("Código")
    filas: list[list[Any]] = [["ESTADO DE CUENTA"], [], enc]
    if con_inicial:
        filas.append(["", "", "SALDO INICIAL", "", "", "1.000,00"])
    filas += [
        ["01/09/2026", "'123", "TRF CR INM CLIENTE", "", "500,00", "1.500,00"],
        ["02/09/2026", 640065766.0, "COM MANTENIMIENTO DE CUENTA", "54,00", "", "1.446,00"],
        [None, None, None, 0, 0, 0],
    ]
    if codigo:
        for f in filas[3 + int(con_inicial) :]:
            f.append("NC")
    if footer:
        filas.append([footer])
    return _xlsx(filas)


def _html_bancamiga(cuenta: str, filas: list[list[str]], inicial: str, final: str) -> bytes:
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas)
    html = (
        "<table border='1'><tr><th colspan='7'><img src='logo.png'></th></tr>"
        "<tr><th>Bancamiga Banco Universal</th></tr>"
        f"<tr><th>Cuenta: {cuenta}</th></tr>"
        "<tr><th>Movimientos del 01/10/2026-31/10/2026</th></tr>"
        f"<tr><th>Saldo Inicial: {inicial}</th></tr>"
        "<tr><th>Nro.</th><th>Fecha</th><th>Referencia</th><th>Concepto</th>"
        "<th>Débito</th><th>Crédito</th><th>Saldo</th></tr>"
        f"{tr}<tr></tr><tr><td>Creditos Total: 1470</td><td>Debito Total: 46,68</td>"
        f"<td>Saldo Final: {final}</td></tr></table>"
    )
    return html.encode("cp1252")


_FILAS_HTML_USD = [
    ["1", "02/10/26", "'1128899819", "Op. Internac. MasterDebit ME Sub - FACEBK", "45,11", "0", "44762,37"],
    ["2", "02/10/26", "'1128899819", "Comisión Compra Pos M_Debit US Intr Sub", "1,57", "0", "44760,80"],
    ["3", "21/10/26", "'4125410411", "NC Compra USD Intervencion Digital", "0", "1470,00", "46230,80"],
]


def _binance_xlsx(filas: list[list[Any]]) -> bytes:
    enc = [
        None,
        None,
        "ID de usuario",
        "Hora",
        None,
        "Cuenta",
        "Operación",
        None,
        "Moneda",
        "Cambiar",
        None,
        "Comentario",
    ]
    cab: list[list[Any]] = [[None], [None, None, "Historial de transacciones"], [None], enc]
    return _xlsx(cab + [[None, None, "1", *f] for f in filas])


_FILAS_BINANCE = [
    ["2026-10-20 10:08:27", None, "Spot", "Deposit", None, "USD", "9590", None, ""],
    [
        "2026-10-20 11:07:12",
        None,
        "Spot",
        "Buy Crypto With Fiat",
        None,
        "USD",
        "-9590",
        None,
        "Via CashBalance - Wallet/N01809060620077980672102065",
    ],
    [
        "2026-10-20 11:07:18",
        None,
        "Spot",
        "Buy Crypto With Fiat",
        None,
        "USDT",
        "9603.90355958",
        None,
        "Via CashBalance - Wallet/N01809060620077980672102065",
    ],
    [
        "2026-10-15 11:14:34",
        None,
        "Spot",
        "Transfer",
        None,
        "USDT",
        "200",
        None,
        "Binance Pay - P_A251P9QHTYN71116",
    ],
    [
        "2026-10-15 12:49:20",
        None,
        "Spot",
        "Transfer",
        None,
        "USDT",
        "200",
        None,
        "Binance Pay - P_A251QP4XUUD7111R",
    ],
    [
        "2026-10-21 17:21:16",
        None,
        "Spot",
        "Transfer",
        None,
        "USDT",
        "-300",
        None,
        "Binance Pay - P_A255T7M5K1W71112",
    ],
]


# ── Números, fechas y referencias ─────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "esperado"),
    [
        ("1.002.945,86", D("1002945.86")),
        ("16.852,72", D("16852.72")),
        ("58,509.32", D("58509.32")),
        ("  \xa0 58,509.32 ", D("58509.32")),
        ("69161775,62", D("69161775.62")),
        ("1,234,567", D("1234567.00")),
        (810744.25, D("810744.25")),
        (5277.489999999991, D("5277.49")),
        (168200, D("168200.00")),
        (D("99.995"), D("100.00")),
        ("", None),
        ("   ", None),
        (None, None),
        (-5101.98, D("-5101.98")),
        ("0.00", D("0.00")),
        ("1.234", D("1234.00")),
        ("12.50", D("12.50")),
        ("(54,00)", D("-54.00")),
    ],
)
def test_parse_monto_variantes(raw: Any, esperado: D | None) -> None:
    assert parse_monto(raw) == esperado


@pytest.mark.parametrize("invalido", ["abc", True, False])
def test_parse_monto_invalido_lanza_error(invalido: Any) -> None:
    with pytest.raises(ValueError, match="Monto inválido"):
        parse_monto(invalido)


def test_parse_fecha_y_limpiar_ref() -> None:
    assert parse_fecha("09/09/2026") == date(2026, 9, 9)
    assert parse_fecha("09-09-2026") == date(2026, 9, 9)
    assert parse_fecha("2026-09-09") == date(2026, 9, 9)
    assert parse_fecha("2026/09/09") == date(2026, 9, 9)
    assert parse_fecha("2026-09-09 15:30:00") == date(2026, 9, 9)
    assert parse_fecha("02/10/26") == date(2026, 10, 2)
    assert parse_fecha(46296.0) == date(2026, 10, 1)
    assert parse_fecha(100, datemode=1) == date(1904, 4, 10)
    assert parse_fecha(datetime(2026, 9, 9, 10, 0)) == date(2026, 9, 9)
    assert parse_fecha(date(2026, 9, 9)) == date(2026, 9, 9)
    with pytest.raises(ValueError, match="Fecha inválida"):
        parse_fecha("32/13/2026")
    with pytest.raises(ValueError, match="Fecha inválida"):
        parse_fecha(True)

    assert limpiar_ref("'19763674") == "19763674"
    assert limpiar_ref(640065766.0) == "640065766"
    assert limpiar_ref("640065766.00") == "640065766"
    assert limpiar_ref("") == ""
    assert limpiar_ref(None) == ""
    assert limpiar_ref(True) == ""


# ── Lector seguro de hojas (.xlsx, HTML-.xls, .csv, anti zip-bomb) ────────────


def test_lector_xlsx_shared_strings_date1904_y_columnas_altas() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<workbookPr date1904="1"/><sheets><sheet name="S1" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/custom.xml"/></Relationships>',
        )
        zf.writestr(
            "xl/sharedStrings.xml",
            '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<si><t>Hola</t></si><si><r><t>Mun</t></r><r><t>do</t></r></si></sst>",
        )
        zf.writestr(
            "xl/worksheets/custom.xml",
            '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData><row r="1">'
            '<c r="A1" t="s"><v>0</v></c>'
            '<c r="C1" t="s"><v>1</v></c>'
            '<c r="D1" t="b"><v>1</v></c>'
            '<c r="E1" t="e"><v>#N/A</v></c>'
            '<c r="AA1" t="str"><v>Col27</v></c>'
            "</row></sheetData></worksheet>",
        )
    filas, dm = leer_filas_tabular(buf.getvalue(), "test.xlsx")
    assert dm == 1
    assert filas[0][0] == "Hola"
    assert filas[0][1] is None
    assert filas[0][2] == "Mundo"
    assert filas[0][3] is True
    assert filas[0][4] is None
    assert filas[0][26] == "Col27"


def test_lector_bloquea_zip_corrupto_zip_bomb_y_xls_binario() -> None:
    with pytest.raises(ExtractoBancarioError, match="corrupto"):
        leer_filas_tabular(b"PK\x03\x04basura", "malo.xlsx")

    # Muchos archivos internos (> MAX_ENTRADAS_ZIP)
    buf_muchos = io.BytesIO()
    with zipfile.ZipFile(buf_muchos, "w") as zf:
        for i in range(205):
            zf.writestr(f"xl/f{i}.xml", "<x/>")
    with pytest.raises(ExtractoBancarioError, match="máximo permitido"):
        leer_filas_tabular(buf_muchos.getvalue(), "muchos.xlsx")

    # Binario OLE2 .xls antiguo
    with pytest.raises(ExtractoBancarioError, match="formato binario .xls"):
        leer_filas_tabular(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1resto", "viejo.xls")


def test_lector_csv_detecta_punto_y_coma() -> None:
    csv_bytes = "Fecha;Referencia;Concepto;Monto\n01/09/2026;99;Cobro;150,00\n".encode("utf-8-sig")
    filas, dm = leer_filas_tabular(csv_bytes, "extracto.csv")
    assert dm == 0
    assert filas[0] == ["Fecha", "Referencia", "Concepto", "Monto"]
    assert filas[1][3] == "150,00"


# ── Validación de cadena, huellas y clasificación ─────────────────────────────


def test_cadena_saldos_ok_salto_y_duplicado() -> None:
    est = EstadoCuentaCanonico(
        "BANCAMIGA",
        "CTA-1",
        "VES",
        "corte.xlsx",
        [_linea(1, "0", "100", "1100"), _linea(2, "50", "0", "1050")],
        saldo_inicial=D("1000"),
    )
    assert validar_estado(est).ok

    est.movimientos.append(_linea(3, "10", "0", "900"))
    r = validar_estado(est)
    assert not r.ok and "#3" in r.saltos[0]

    est2 = EstadoCuentaCanonico(
        "BANCAMIGA",
        "CTA-1",
        "VES",
        "corte2.xlsx",
        [_linea(1, "0", "100", "1100"), _linea(2, "0", "100", "1100")],
        saldo_inicial=D("1000"),
        saldo_final=D("999"),
    )
    r2 = validar_estado(est2)
    assert not r2.ok
    assert any("saldo final declarado" in s for s in r2.saltos)
    assert len(r2.duplicados) == 1


def test_huella_estable_por_cuenta_y_saldo() -> None:
    a = _linea(1, "0", "5", "10", cuenta="CTA-A")
    b = _linea(9, "0", "5", "10", cuenta="CTA-A")
    otra_cta = _linea(1, "0", "5", "10", cuenta="CTA-B")
    assert a.huella == b.huella
    assert a.huella != otra_cta.huella
    assert _linea(1, "54", "0", None).huella != _linea(2, "54", "0", None).huella


@pytest.mark.parametrize(
    ("desc", "deb", "cre", "cat"),
    [
        ("ND PERCEPCION IGTF 3%", "30", "0", "impuesto_igtf"),
        ("COM MANTENIMIENTO DE CUENTA", "54", "0", "comision_bancaria"),
        ("Comisión servicio pago de nomina", "172.03", "0", "comision_bancaria"),
        ("Comisi\ufffdn servicio pago de nomina", "21.5", "0", "comision_bancaria"),
        ("Pago mixto nomina", "68814.02", "0", "nomina"),
        ("NOMINA DEVUELTO LOTE 4", "0", "1200", "nomina_devuelta"),
        ("TD POS J0507836142001", "0", "100", "cobro_pos"),
        ("INV.PLATCO PNCCOB 00002", "5101.98", "0", "operacion_pos"),
        ("TRF CR INM 0102 CLIENTE", "0", "310000", "cobro_candidato"),
        ("ZELLE RECIBIDO CLIENTE", "0", "250", "cobro_candidato"),
        ("ZELLE ENVIADO PROVEEDOR", "250", "0", "pago_a_terceros"),
        ("PAGO A TERCEROS BDV PROVEEDOR", "28987.88", "0", "pago_a_terceros"),
        ("ND Compra USD Intervencion Digital Bs", "813736.1", "0", "operacion_cambiaria"),
        ("PAGO IMPUESTOS SENIAT", "500", "0", "impuesto"),
        ("APORTE IVSS MENSUAL", "120", "0", "parafiscal"),
        ("MOVIMIENTO DESCONOCIDO", "0", "10", "ingreso_por_revisar"),
        ("MOVIMIENTO DESCONOCIDO", "10", "0", "por_revisar"),
    ],
)
def test_clasificacion_deterministica(desc: str, deb: str, cre: str, cat: str) -> None:
    assert clasificar_linea(_linea(1, deb, cre, "0", desc=desc))[0] == cat


# ── Parsers multi-banco desacoplados ──────────────────────────────────────────


def test_inferir_formato_y_extraer_sufijo() -> None:
    assert inferir_formato_banco("Bancamiga Banco Universal") == "BANCAMIGA"
    assert inferir_formato_banco("Banesco") == "BANESCO"
    assert inferir_formato_banco("Banco de Venezuela BDV") == "VENEZUELA"
    assert inferir_formato_banco("Banco del Tesoro") == "BDT"
    assert inferir_formato_banco("BBVA Provincial") == "PROVINCIAL"
    assert inferir_formato_banco("Mercantil") == "MERCANTIL"
    assert inferir_formato_banco("Binance Pay") == "BINANCE"
    assert inferir_formato_banco("Banco Exterior") == "GENERICO_DEB_CRED"
    assert extraer_sufijo_cuenta("0172-0110-75-1101276747") == "6747"
    assert extraer_sufijo_cuenta("12") is None


def test_parsers_venezuela_bdt_bancamiga_provincial_binance_y_generico() -> None:
    # Venezuela con saldo inicial explícito
    e_bdv = parsear_extracto(_libro_deb_cred(), "bdv.xlsx", "VENEZUELA", cuenta_clave="C1")
    assert e_bdv.saldo_inicial == D("1000.00") and not e_bdv.saldo_inicial_derivado
    assert validar_estado(e_bdv).ok

    # Dos cortes pegados que no empalman avisan
    dos_cortes = _xlsx(
        [
            ["Nro.", "Fecha", "Referencia", "Concepto", "Débito", "Crédito", "Saldo"],
            [1, "29/09/2026", "11", "TRF CR INM CLIENTE", "", "500,00", "1.500,00"],
            [1, "01/10/2026", "", "SALDO INICIAL", "", "", "1.400,00"],
            [2, "01/10/2026", "13", "TRF CR INM CLIENTE", "", "100,00", "1.500,00"],
        ]
    )
    e_dos = parsear_extracto(dos_cortes, "dos.xlsx", "VENEZUELA", cuenta_clave="C1")
    assert any("a mitad de archivo" in a for a in e_dos.avisos)

    # BDT con columna Código
    e_bdt = parsear_extracto(_libro_deb_cred(codigo=True), "bdt.xlsx", "BDT", cuenta_clave="C2")
    assert {m.codigo for m in e_bdt.movimientos} == {"NC"}

    # Bancamiga HTML con validación dinámica de sufijo (sin hardcoding de empresa)
    html_usd = _html_bancamiga("01720110759999881122", _FILAS_HTML_USD, "44807.48", "46230,80")
    e_bm = parsear_extracto(
        html_usd,
        "Movimientos.xls",
        "BANCAMIGA",
        cuenta_clave="C-USD",
        moneda="USD",
        cuenta_sufijo="1122",
    )
    assert e_bm.saldo_inicial == D("44807.48") and e_bm.saldo_final == D("46230.80")
    assert validar_estado(e_bm).ok

    # Rechaza archivo cuando el sufijo de la cuenta seleccionada es distinto
    with pytest.raises(ExtractoBancarioError, match="no coincide con la cuenta seleccionada"):
        parsear_extracto(
            html_usd,
            "Movimientos.xls",
            "BANCAMIGA",
            cuenta_clave="C-OTRA",
            moneda="VES",
            cuenta_sufijo="9999",
        )

    # Provincial descendente: otro rango renumerado conserva las huellas
    prov_a = _xlsx(
        [
            ["Fecha", "Referencia", "Descripción", "Importe", "Saldo"],
            ["15/08/2026", 33, "COM MTTO POS", -3521.60, "  92,989.27"],
            ["13/08/2026", 32, "TC POS J0507836142001", 96510.87, "  96,510.87"],
        ]
    )
    prov_b = _xlsx(
        [
            ["Fecha", "Referencia", "Descripción", "Importe", "Saldo"],
            ["20/08/2026", 3, "TD POS J0507836142001", 10.73, "  93,000.00"],
            ["15/08/2026", 2, "COM MTTO POS", -3521.60, "  92,989.27"],
            ["13/08/2026", 1, "TC POS J0507836142001", 96510.87, "  96,510.87"],
        ]
    )
    ea = parsear_extracto(prov_a, "pa.xlsx", "PROVINCIAL", cuenta_clave="CP")
    eb = parsear_extracto(prov_b, "pb.xlsx", "PROVINCIAL", cuenta_clave="CP")
    assert {m.huella for m in ea.movimientos} <= {m.huella for m in eb.movimientos}

    # Binance con columnas dispersas y ordenamiento por timestamp
    ebn = parsear_extracto(_binance_xlsx(_FILAS_BINANCE), "bn.xlsx", "BINANCE", cuenta_clave="CBN", moneda="USD")
    assert len(ebn.movimientos) == 6
    assert ebn.movimientos[0].referencia == "P_A251P9QHTYN71116"
    assert any("1:1" in a for a in ebn.avisos)

    # Genérico con columna firmada Monto y sin columna Saldo
    csv_gen = (
        b"Fecha,Detalle,Monto\n" b"2026-09-01,TRF CR INM PAGO CLIENTE,250.00\n" b"2026-09-02,COMISION BANCARIA,-5.50\n"
    )
    egen = parsear_extracto(csv_gen, "generico.csv", "GENERICO_DEB_CRED", cuenta_clave="CG", moneda="USD")
    assert len(egen.movimientos) == 2
    assert egen.movimientos[0].credito == D("250.00")
    assert egen.movimientos[1].debito == D("5.50")


def test_preparar_extracto_errores_borde() -> None:
    with pytest.raises(ExtractoBancarioError, match="vacío"):
        preparar_extracto(b"", "x.xlsx", formato_banco="BANESCO", cuenta_clave="C1")
    with pytest.raises(ExtractoBancarioError, match="MB"):
        preparar_extracto(b"x" * (10 * 1024 * 1024 + 1), "x.xlsx", formato_banco="BANESCO", cuenta_clave="C1")
    with pytest.raises(ExtractoBancarioError, match="no soportado"):
        preparar_extracto(b"Fecha\n", "x.csv", formato_banco="INEXISTENTE", cuenta_clave="C1")
    vacio = _xlsx([["Fecha", "Referencia", "Concepto", "Débito", "Crédito", "Saldo"]])
    with pytest.raises(ExtractoBancarioError, match="ningún movimiento"):
        preparar_extracto(vacio, "vacio.xlsx", formato_banco="BANESCO", cuenta_clave="C1")


def test_consolidar_cortes_continuidad_y_huecos() -> None:
    cortes = [
        CorteExtracto(
            "1",
            "C1",
            "BDV",
            "0102-1111",
            "VES",
            "ago.xlsx",
            date(2026, 8, 1),
            date(2026, 8, 31),
            D("0"),
            D("100"),
            True,
            datetime(2026, 9, 1, 10, 0),
        ),
        CorteExtracto(
            "2",
            "C1",
            "BDV",
            "0102-1111",
            "VES",
            "sep.xlsx",
            date(2026, 9, 1),
            date(2026, 9, 30),
            D("100"),
            D("300"),
            True,
            datetime(2026, 10, 1, 10, 0),
        ),
        CorteExtracto(
            "3",
            "C1",
            "BDV",
            "0102-1111",
            "VES",
            "oct.xlsx",
            date(2026, 10, 2),
            date(2026, 10, 31),
            D("350"),
            D("400"),
            False,
            datetime(2026, 11, 1, 10, 0),
        ),
    ]
    cons = consolidar_cortes(cortes, lambda _f: D("100"))
    cta = cons.cuentas[0]
    assert cta.saldo == D("400.00")
    assert cta.saldo_usd == D("4.00")
    assert cta.cortes_sin_cuadrar == 1
    assert "no cuadra" in cta.alertas[0]
    assert "hueco entre 2026-09-30 y 2026-10-02" in cta.alertas[1]


# ── Integración con PostgreSQL, RLS, REST API y MCP (multi-tenant) ────────────


@pytest.fixture
def moneda_ves(db) -> Moneda:
    moneda, _ = Moneda.objects.get_or_create(
        codigo_iso="VES",
        defaults={"nombre": "Bolívar", "simbolo": "Bs", "tipo_moneda": "fiat", "es_generica": True},
    )
    return moneda


@pytest.fixture
def cuenta_ves_a(db, empresa_a, moneda_ves) -> CuentaBancariaEmpresa:
    return CuentaBancariaEmpresa.objects.create(
        id_empresa=empresa_a,
        nombre_banco="Bancamiga",
        numero_cuenta="0172-0110-79-1105554321",
        tipo_cuenta="CORRIENTE",
        id_moneda=moneda_ves,
    )


@pytest.fixture
def cuenta_usd_a(db, empresa_a, moneda_usd) -> CuentaBancariaEmpresa:
    return CuentaBancariaEmpresa.objects.create(
        id_empresa=empresa_a,
        nombre_banco="Binance",
        numero_cuenta="BINANCE-SPOT-A",
        tipo_cuenta="CORRIENTE",
        id_moneda=moneda_usd,
    )


@pytest.fixture
def cuenta_ves_b(db, empresa_b, moneda_ves) -> CuentaBancariaEmpresa:
    return CuentaBancariaEmpresa.objects.create(
        id_empresa=empresa_b,
        nombre_banco="Banesco",
        numero_cuenta="0134-0000-00-9999998888",
        tipo_cuenta="CORRIENTE",
        id_moneda=moneda_ves,
    )


@pytest.fixture
def api_a(user_a) -> APIClient:
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def api_b(user_b) -> APIClient:
    c = APIClient()
    c.force_authenticate(user=user_b)
    return c


@pytest.mark.django_db
class TestIngestaYConsolidacionBD:
    def test_idempotencia_archivo_solapamiento_y_borrado_logico(self, empresa_a, cuenta_ves_a, user_a) -> None:
        corte_1 = _xlsx(
            [
                ["Cuenta: 0172-0110-79-1105554321"],
                ["Saldo Inicial: 1.000,00"],
                ["Fecha", "Referencia", "Concepto", "Débito", "Crédito", "Saldo"],
                ["01/09/2026", "101", "TRF CR INM CLIENTE UNO", "", "500,00", "1.500,00"],
                ["02/09/2026", "102", "COM MANTENIMIENTO DE CUENTA", "50,00", "", "1.450,00"],
            ]
        )
        r1 = importar_extracto_bancario(
            empresa=empresa_a,
            cuenta_bancaria=cuenta_ves_a,
            contenido=corte_1,
            nombre_archivo="sep_parte1.xlsx",
            usuario=user_a,
        )
        assert not r1.ya_existia_archivo
        assert r1.lineas_nuevas == 2 and r1.lineas_duplicadas == 0 and r1.cuadra

        # Re-importar los mismos bytes exactos no duplica
        r_dup = importar_extracto_bancario(
            empresa=empresa_a,
            cuenta_bancaria=cuenta_ves_a,
            contenido=corte_1,
            nombre_archivo="sep_parte1_copia.xlsx",
            usuario=user_a,
        )
        assert r_dup.ya_existia_archivo
        assert r_dup.lineas_nuevas == 0
        assert MovimientoBancario.objects.filter(id_cuenta_bancaria=cuenta_ves_a, activo=True).count() == 2

        # Corte solapado con 1 línea vieja + 1 línea nueva solo inserta la nueva
        corte_solapado = _xlsx(
            [
                ["Cuenta: 0172-0110-79-1105554321"],
                ["Saldo Inicial: 1.500,00"],
                ["Fecha", "Referencia", "Concepto", "Débito", "Crédito", "Saldo"],
                ["02/09/2026", "102", "COM MANTENIMIENTO DE CUENTA", "50,00", "", "1.450,00"],
                ["05/09/2026", "103", "ND PERCEPCION IGTF", "15,00", "", "1.435,00"],
            ]
        )
        r2 = importar_extracto_bancario(
            empresa=empresa_a,
            cuenta_bancaria=cuenta_ves_a,
            contenido=corte_solapado,
            nombre_archivo="sep_parte2.xlsx",
            usuario=user_a,
        )
        assert r2.lineas_nuevas == 1 and r2.lineas_duplicadas == 1
        assert MovimientoBancario.objects.filter(id_cuenta_bancaria=cuenta_ves_a, activo=True).count() == 3

        # Desactivar lógicamente r2 marca inactivo el corte y su movimiento pendiente
        n_desact = desactivar_extracto_bancario(r2.archivo)
        assert n_desact == 1
        assert MovimientoBancario.objects.filter(id_cuenta_bancaria=cuenta_ves_a, activo=True).count() == 2

        # Si un movimiento está CONCILIADO, se bloquea la desactivación del corte
        mov_conc = r1.archivo.movimientos.first()
        assert mov_conc is not None
        mov_conc.estado = "CONCILIADO"
        mov_conc.save(update_fields=["estado"])
        with pytest.raises(ExtractoBancarioError, match="movimientos conciliados"):
            desactivar_extracto_bancario(r1.archivo)

    def test_saldos_consolidados_con_tasa_bcv_y_tasa_inversa(
        self, empresa_a, cuenta_ves_a, cuenta_usd_a, moneda_usd, moneda_ves
    ) -> None:
        TasaCambio.objects.create(
            id_empresa=None,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_ves,
            tipo_tasa="OFICIAL_BCV",
            valor_tasa=D("50.00000000"),
            fecha_tasa=date(2026, 9, 1),
        )
        corte = _xlsx(
            [
                ["Cuenta: 0172-0110-79-1105554321"],
                ["Saldo Inicial: 0,00"],
                ["Fecha", "Referencia", "Concepto", "Débito", "Crédito", "Saldo"],
                ["02/09/2026", "101", "TRF CR INM CLIENTE", "", "5.000,00", "5.000,00"],
            ]
        )
        importar_extracto_bancario(
            empresa=empresa_a,
            cuenta_bancaria=cuenta_ves_a,
            contenido=corte,
            nombre_archivo="sep.xlsx",
        )
        importar_extracto_bancario(
            empresa=empresa_a,
            cuenta_bancaria=cuenta_usd_a,
            contenido=_binance_xlsx(_FILAS_BINANCE[:1]),
            nombre_archivo="binance.xlsx",
        )

        cons = consolidar_saldos_extractos(empresa_a)
        data = serializar_consolidado(cons)
        assert data["total_usd"] == "100.00"
        assert data["total_ves"] == "5000.00"
        assert len(data["cuentas"]) == 2


@pytest.mark.tenant
@pytest.mark.django_db
class TestAislamientoMultiTenantEndpointsYMCP:
    URL = "/api/tesoreria/extractos-bancarios/"

    def test_importar_listar_saldos_borrado_y_aislamiento_entre_empresas(
        self, api_a, api_b, empresa_a, empresa_b, cuenta_ves_a, cuenta_ves_b, moneda_usd, moneda_ves
    ) -> None:
        # Sin autenticación -> 401
        assert APIClient().get(self.URL).status_code == 401

        # Validaciones 400 / 403 / 404 en /importar/
        assert api_a.post(f"{self.URL}importar/", {}).status_code == 400
        f_dummy = SimpleUploadedFile("x.xlsx", _libro_deb_cred())
        assert (
            api_a.post(f"{self.URL}importar/", {"cuenta_bancaria": "no-uuid", "archivo": f_dummy}).status_code == 400
        )
        # Empresa B no puede importar sobre cuenta de Empresa A -> 404 (sin filtrar existencia)
        f_b = SimpleUploadedFile("x.xlsx", _libro_deb_cred())
        assert (
            api_b.post(
                f"{self.URL}importar/",
                {"cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria), "archivo": f_b},
            ).status_code
            == 404
        )
        # Empresa B pasando explícitamente empresa_a -> 403
        f_b2 = SimpleUploadedFile("x.xlsx", _libro_deb_cred())
        assert (
            api_b.post(
                f"{self.URL}importar/",
                {
                    "empresa": str(empresa_a.id_empresa),
                    "cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria),
                    "archivo": f_b2,
                },
            ).status_code
            == 403
        )

        # Empresa A importa su extracto -> 201 Created
        corte_a = _xlsx(
            [
                ["Cuenta: 0172-0110-79-1105554321"],
                ["Saldo Inicial: 1.000,00"],
                ["Fecha", "Referencia", "Concepto", "Débito", "Crédito", "Saldo"],
                ["02/09/2026", "501", "TRF CR INM CLIENTE A", "", "2.000,00", "3.000,00"],
            ]
        )
        resp = api_a.post(
            f"{self.URL}importar/",
            {
                "cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria),
                "archivo": SimpleUploadedFile("bancamiga_a.xlsx", corte_a),
            },
        )
        assert resp.status_code == 201, resp.content
        archivo_id = resp.json()["archivo"]["id"]

        # Re-subir idéntico vía API -> 200 OK idempotente
        resp_dup = api_a.post(
            f"{self.URL}importar/",
            {
                "cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria),
                "archivo": SimpleUploadedFile("bancamiga_a.xlsx", corte_a),
            },
        )
        assert resp_dup.status_code == 200
        assert resp_dup.json()["ya_existia_archivo"] is True

        # Aislamiento en listado, detalle, movimientos y saldos consolidados
        assert api_a.get(self.URL, {"cuadra": "true"}).json()["count"] == 1
        assert api_b.get(self.URL).json()["count"] == 0
        assert api_b.get(f"{self.URL}{archivo_id}/").status_code == 404

        movs_a = api_a.get(
            "/api/tesoreria/movimientos-bancarios/",
            {"categoria": "cobro_candidato", "archivo": archivo_id},
        ).json()
        assert movs_a["count"] == 1
        assert movs_a["results"][0]["saldo_posterior"] == "3000.00"

        TasaCambio.objects.create(
            id_empresa=empresa_a,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_ves,
            tipo_tasa="OFICIAL_BCV",
            valor_tasa=D("60.00000000"),
            fecha_tasa=date(2026, 9, 2),
        )
        saldos_a = api_a.get(f"{self.URL}saldos-consolidados/").json()
        assert saldos_a["total_usd"] == "50.00"
        assert saldos_a["total_ves"] == "3000.00"
        assert set(FORMATOS_BANCO_SOPORTADOS) <= set(saldos_a["formatos_soportados"])

        saldos_b = api_b.get(f"{self.URL}saldos-consolidados/").json()
        assert saldos_b["cuentas"] == [] and saldos_b["total_usd"] == "0.00"

        # MCP tools: scope, filtros y aislamiento por CapabilityToken
        tok_a = CapabilityToken.objects.create(
            empresa=empresa_a,
            nombre="MCP Tesorería A",
            scopes=["tesoreria:read"],
        )
        tok_sin_scope = CapabilityToken.objects.create(
            empresa=empresa_a,
            nombre="MCP Ventas A",
            scopes=["ventas:read"],
        )
        lista_mcp = tesoreria_listar_extractos(
            str(tok_a.token),
            str(empresa_a.id_empresa),
            cuenta_id=str(cuenta_ves_a.id_cuenta_bancaria),
        )
        assert len(lista_mcp) == 1 and lista_mcp[0]["id"] == archivo_id
        resumen_mcp = tesoreria_saldos_extractos(
            str(tok_a.token),
            str(empresa_a.id_empresa),
            cuenta_id=str(cuenta_ves_a.id_cuenta_bancaria),
        )
        assert resumen_mcp["total_usd"] == "50.00"

        with pytest.raises(PermissionError, match="scope"):
            tesoreria_saldos_extractos(str(tok_sin_scope.token), str(empresa_a.id_empresa))
        with pytest.raises(PermissionError, match="no coincide"):
            tesoreria_saldos_extractos(str(tok_a.token), str(empresa_b.id_empresa))
        with pytest.raises(ValueError, match="UUID"):
            tesoreria_saldos_extractos(str(tok_a.token), str(empresa_a.id_empresa), cuenta_id="malo")
        with pytest.raises(PermissionError, match="no coincide"):
            tesoreria_listar_extractos(str(tok_a.token), str(empresa_b.id_empresa))
        with pytest.raises(ValueError, match="UUID"):
            tesoreria_listar_extractos(str(tok_a.token), str(empresa_a.id_empresa), cuenta_id="malo")

        # Verificación de modelos (__str__), filtros adicionales y validaciones HTTP
        archivo_obj = ExtractoBancarioArchivo.objects.get(pk=archivo_id)
        assert "bancamiga_a.xlsx" in str(archivo_obj)
        assert api_a.get(self.URL, {"cuenta": str(cuenta_ves_a.id_cuenta_bancaria)}).json()["count"] == 1
        assert api_b.get(f"{self.URL}saldos-consolidados/", {"empresa": str(empresa_a.id_empresa)}).status_code == 403
        assert (
            api_a.post(
                "/api/tesoreria/movimientos-bancarios/conciliar-auto/",
                {"cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria), "tolerancia_dias": "abc"},
                format="json",
            ).status_code
            == 400
        )

        # Defensa en profundidad RLS a nivel de PostgreSQL sobre ExtractoBancarioArchivo
        from apps.core.rls import apply_context, apply_system_default, current_role_bypasses_rls

        if not current_role_bypasses_rls():
            try:
                apply_context([empresa_b.id_empresa], bypass=False)
                assert ExtractoBancarioArchivo.objects.filter(pk=archivo_id).count() == 0
                apply_context([empresa_a.id_empresa], bypass=False)
                assert ExtractoBancarioArchivo.objects.filter(pk=archivo_id).count() == 1
            finally:
                apply_system_default()

        # Bloqueo de DELETE en movimiento y corte cuando existe línea CONCILIADA
        mov_id = movs_a["results"][0]["id"]
        MovimientoBancario.objects.filter(pk=mov_id).update(estado="CONCILIADO")
        assert api_a.delete(f"/api/tesoreria/movimientos-bancarios/{mov_id}/").status_code == 400
        assert api_a.delete(f"{self.URL}{archivo_id}/").status_code == 400

        # Al volver a PENDIENTE, DELETE en movimiento hace soft-delete y DELETE en corte desactiva
        MovimientoBancario.objects.filter(pk=mov_id).update(estado="PENDIENTE")
        assert api_a.delete(f"/api/tesoreria/movimientos-bancarios/{mov_id}/").status_code == 204
        assert MovimientoBancario.objects.get(pk=mov_id).activo is False

        resp_del = api_a.delete(f"{self.URL}{archivo_id}/")
        assert resp_del.status_code == 204
        assert ExtractoBancarioArchivo.objects.get(pk=archivo_id).activo is False
        assert api_a.get(self.URL).json()["count"] == 0
        assert api_a.get(self.URL, {"incluir_inactivos": "true"}).json()["count"] == 1

    def test_importar_con_empresa_explicita_error_formato_y_tasas_borde(
        self, api_a, empresa_a, empresa_b, cuenta_ves_a, moneda_usd, moneda_ves
    ) -> None:
        from apps.tesoreria.extractos.servicio_ingesta import obtener_tasa_usd_ves
        from apps.tesoreria.mcp import _empresa_activa

        # Error al subir archivo vacío vía endpoint -> 400
        resp_err = api_a.post(
            f"{self.URL}importar/",
            {
                "empresa": str(empresa_a.id_empresa),
                "cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria),
                "archivo": SimpleUploadedFile("vacio.xlsx", b""),
            },
        )
        assert resp_err.status_code == 400

        # Subida exitosa pasando empresa explícita y duplicado interno para cubrir observaciones
        corte_dup = _xlsx(
            [
                ["Fecha", "Referencia", "Concepto", "Débito", "Crédito", "Saldo"],
                ["03/09/2026", "777", "TRF CR INM CLIENTE", "", "100,00", "1.100,00"],
                ["03/09/2026", "777", "TRF CR INM CLIENTE", "", "100,00", "1.100,00"],
            ]
        )
        resp_ok = api_a.post(
            f"{self.URL}importar/",
            {
                "empresa": str(empresa_a.id_empresa),
                "cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria),
                "archivo": SimpleUploadedFile("dup_interno.xlsx", corte_dup),
            },
        )
        assert resp_ok.status_code == 201
        obs = resp_ok.json()["archivo"]["observaciones"]
        assert "huella(s) repetida(s)" in obs
        assert "saldo inicial derivado" in obs

        # Servicio rechaza cuenta de otra empresa
        with pytest.raises(ExtractoBancarioError, match="no pertenece"):
            importar_extracto_bancario(
                empresa=empresa_b,
                cuenta_bancaria=cuenta_ves_a,
                contenido=corte_dup,
                nombre_archivo="x.xlsx",
            )

        # obtener_tasa_usd_ves: sin tasa -> None; con tasa inversa VES->USD -> recíproco
        assert obtener_tasa_usd_ves(empresa_a, date(2020, 1, 1)) is None
        TasaCambio.objects.create(
            id_empresa=empresa_a,
            id_moneda_origen=moneda_ves,
            id_moneda_destino=moneda_usd,
            tipo_tasa="OFICIAL_BCV",
            valor_tasa=D("0.02000000"),
            fecha_tasa=date(2026, 9, 10),
        )
        assert obtener_tasa_usd_ves(empresa_a, date(2026, 9, 10)) == D("50.00000000")

        # Validaciones defensivas de _empresa_activa en MCP
        with pytest.raises(PermissionError, match="inválido"):
            _empresa_activa("no-es-uuid")
        with pytest.raises(PermissionError, match="inactiva"):
            _empresa_activa("00000000-0000-0000-0000-000000000000")


def test_parsers_validaciones_de_encabezado_y_montos_invalidos() -> None:
    sin_fecha = _xlsx([["Col1", "Col2"], ["a", "b"]])
    for fmt in ("BANESCO", "PROVINCIAL", "BINANCE"):
        with pytest.raises(ExtractoBancarioError, match="encabezado"):
            parsear_extracto(sin_fecha, "sin.xlsx", fmt, cuenta_clave="C1")

    # Saldo inválido y monto faltante en modo flexible
    mal_saldo = _xlsx(
        [
            ["Fecha", "Referencia", "Concepto", "Débito", "Crédito", "Saldo"],
            ["01/09/2026", "1", "PAGO", "10,00", "", "malo"],
        ]
    )
    with pytest.raises(ExtractoBancarioError, match="saldo inválido"):
        parsear_extracto(mal_saldo, "ms.xlsx", "BANESCO", cuenta_clave="C1")

    sin_imp_gen = b"Fecha,Concepto,Monto\n2026-09-01,PAGO,\n"
    with pytest.raises(ExtractoBancarioError, match="sin monto"):
        parsear_extracto(sin_imp_gen, "g.csv", "GENERICO_DEB_CRED", cuenta_clave="C1")

    mal_deb = _xlsx(
        [
            ["Fecha", "Referencia", "Concepto", "Débito", "Crédito", "Saldo"],
            ["01/09/2026", "1", "PAGO", "abc", "", "100,00"],
        ]
    )
    with pytest.raises(ExtractoBancarioError, match="Monto inválido"):
        parsear_extracto(mal_deb, "md.xlsx", "BANESCO", cuenta_clave="C1")

    # Provincial sin importe / fecha inválida
    prov_sin_imp = _xlsx([["Fecha", "Referencia", "Descripción", "Importe", "Saldo"], ["01/09/2026", 1, "X", "", 10]])
    with pytest.raises(ExtractoBancarioError, match="sin importe"):
        parsear_extracto(prov_sin_imp, "p.xlsx", "PROVINCIAL", cuenta_clave="C1")

    prov_mal_fecha = _xlsx(
        [
            ["Fecha", "Referencia", "Descripción", "Importe", "Saldo"],
            ["fecha-mala", 1, "X", 10, 10],
        ]
    )
    with pytest.raises(ExtractoBancarioError, match="Fecha inválida"):
        parsear_extracto(prov_mal_fecha, "p2.xlsx", "PROVINCIAL", cuenta_clave="C1")

    # Binance: hora inválida, monto inválido, sin monto y moneda incompatible
    with pytest.raises(ExtractoBancarioError, match="hora inválida"):
        parsear_extracto(
            _binance_xlsx([["hora-mala", None, "Spot", "Deposit", None, "USD", "10", None, ""]]),
            "b1.xlsx",
            "BINANCE",
            cuenta_clave="CB",
            moneda="USD",
        )
    with pytest.raises(ExtractoBancarioError, match="Monto inválido"):
        parsear_extracto(
            _binance_xlsx([["2026-10-20 10:00:00", None, "Spot", "Deposit", None, "USD", "abc", None, ""]]),
            "b2.xlsx",
            "BINANCE",
            cuenta_clave="CB",
            moneda="USD",
        )
    with pytest.raises(ExtractoBancarioError, match="sin monto"):
        parsear_extracto(
            _binance_xlsx([["2026-10-20 10:00:00", None, "Spot", "Deposit", None, "USD", "", None, ""]]),
            "b3.xlsx",
            "BINANCE",
            cuenta_clave="CB",
            moneda="USD",
        )
    with pytest.raises(ExtractoBancarioError, match="no compatible"):
        parsear_extracto(
            _binance_xlsx([["2026-10-20 10:00:00", None, "Spot", "Deposit", None, "BTC", "1", None, ""]]),
            "b4.xlsx",
            "BINANCE",
            cuenta_clave="CB",
            moneda="USD",
        )

    # Alias legacy BANCAMIGA_USD ajusta moneda a USD cuando el default era VES
    html_usd = _html_bancamiga("01720110759999881122", _FILAS_HTML_USD, "44807.48", "46230,80")
    est_alias = parsear_extracto(html_usd, "m.xls", "BANCAMIGA_USD", cuenta_clave="C-USD")
    assert est_alias.formato_banco == "BANCAMIGA" and est_alias.moneda == "USD"


def test_regresion_b1_montos_menores_a_uno_binance_3_decimales_y_overflow() -> None:
    # B-1.1: '0.125' y '-0.500' jamás son separador de miles (ROUND_HALF_EVEN: 0.12 y -0.50)
    assert parse_monto("0.125") == D("0.12")
    assert parse_monto("0.135") == D("0.14")
    assert parse_monto("-0.500") == D("-0.50")
    assert parse_monto("0,500") == D("0.50")

    # B-1.2: punto_miles=False preserva 3 decimales anglosajones en Binance ('1.250' -> 1.25)
    assert parse_monto("1.250", punto_miles=False) == D("1.25")
    ebn = parsear_extracto(
        _binance_xlsx([["2026-10-20 10:08:27", None, "Spot", "Transfer", None, "USDT", "1.250", None, ""]]),
        "bn3.xlsx",
        "BINANCE",
        cuenta_clave="CBN",
        moneda="USD",
    )
    assert ebn.movimientos[0].credito == D("1.25")

    # B-1.3: precisión exacta en int > 2^53 (sin float) y rechazo limpio de NaN/Inf/Overflow
    entero_grande = 10**20 + 7
    assert parse_monto(entero_grande) == D(entero_grande).quantize(D("0.01"))
    for invalido in (float("nan"), float("inf"), float("-inf"), D("NaN"), D("Infinity")):
        with pytest.raises(ValueError, match="Monto inválido"):
            parse_monto(invalido)
    for f_inv in (float("nan"), float("inf"), 10**20):
        with pytest.raises(ValueError, match="Fecha inválida"):
            parse_fecha(f_inv)
    assert limpiar_ref(float("inf")) == ""
    assert limpiar_ref("123\x0045") == "12345"

    # Provincial con correlativo desbordado lanza ExtractoBancarioError (no OverflowError 500)
    prov_inf = _xlsx(
        [
            ["Fecha", "Referencia", "Descripción", "Importe", "Saldo"],
            ["01/09/2026", "1e400", "PAGO", 10, 10],
        ]
    )
    with pytest.raises(ExtractoBancarioError):
        parsear_extracto(prov_inf, "p_inf.xlsx", "PROVINCIAL", cuenta_clave="CP")


def test_regresion_b2_defensa_oom_zipbomb_cabecera_falsa_xml_pdf_y_nul(monkeypatch) -> None:
    from apps.tesoreria.extractos import lector_hojas

    # Coordenada dispersa gigante ZZZZZZZ1 bloqueada antes de expandir lista en RAM
    buf_oom = io.BytesIO()
    with zipfile.ZipFile(buf_oom, "w") as zf:
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData><row r="1"><c r="ZZZZZZZ1"><v>1</v></c></row></sheetData></worksheet>',
        )
    with pytest.raises(ExtractoBancarioError, match="excede el máximo permitido"):
        leer_filas_tabular(buf_oom.getvalue(), "oom.xlsx")

    # XML malformado en .xlsx -> ExtractoBancarioError
    buf_bad_xml = io.BytesIO()
    with zipfile.ZipFile(buf_bad_xml, "w") as zf:
        zf.writestr("xl/worksheets/sheet1.xml", "<worksheet><sin_cerrar>")
    with pytest.raises(ExtractoBancarioError, match="XML malformado"):
        leer_filas_tabular(buf_bad_xml.getvalue(), "mal_xml.xlsx")

    # Anti zip-bomb midiendo bytes reales descomprimidos (incluso si file_size fuera pequeño)
    monkeypatch.setattr(lector_hojas, "TAMANO_MAXIMO_XML_DESCOMPRIMIDO", 128)
    buf_big = io.BytesIO()
    with zipfile.ZipFile(buf_big, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            "<worksheet>" + ("A" * 1024) + "</worksheet>",
        )
    # Simulamos cabecera falsificada poniendo file_size=10 en memoria vía lectura acotada directa
    with zipfile.ZipFile(io.BytesIO(buf_big.getvalue())) as zf_check:
        with pytest.raises(ExtractoBancarioError, match="32 MB"):
            lector_hojas._leer_entrada_zip_acotada(zf_check, "xl/worksheets/sheet1.xml", [64])
    with pytest.raises(ExtractoBancarioError, match="32 MB"):
        leer_filas_tabular(buf_big.getvalue(), "big.xlsx")
    monkeypatch.undo()

    # PDF rechazado explícitamente con mensaje accionable
    with pytest.raises(ExtractoBancarioError, match="PDF"):
        leer_filas_tabular(b"%PDF-1.7\n1 0 obj\n", "estado.pdf")
    with pytest.raises(ExtractoBancarioError, match="PDF"):
        leer_filas_tabular(b"%PDF-1.7\n1 0 obj\n", "enganoso.csv")

    # Bytes NUL (\x00), comillas en nombre de hoja y cotas de columnas en HTML/CSV
    filas_nul, _ = leer_filas_tabular(b"Fecha,Concepto,Monto\n2026-09-01,PA\x00GO,10.00\n", "a\x00.csv")
    assert filas_nul[1][1] == "PAGO"
    libro_comillas = construir_xlsx_simple([('Hoja "1"\x00', [["A", True]])])
    filas_q, _ = leer_filas_tabular(libro_comillas, "q.xlsx")
    assert filas_q[0] == ["A", True]
    with pytest.raises(ExtractoBancarioError, match="columnas"):
        leer_filas_tabular(("c," * 260 + "\n").encode(), "ancho.csv")
    with pytest.raises(ExtractoBancarioError, match="columnas"):
        leer_filas_tabular(("<table><tr>" + "<td>x</td>" * 260 + "</tr></table>").encode(), "a.xls")
    with pytest.raises(ValueError, match="Monto inválido"):
        parse_monto("Infinity")


@pytest.mark.tenant
@pytest.mark.django_db
def test_regresion_b3_m1_m2_s1_savepoint_integridad_multiempresa_e_inmutabilidad(
    user_a, api_a, empresa_a, empresa_b, cuenta_ves_a, cuenta_ves_b, moneda_usd, moneda_ves
) -> None:
    from unittest.mock import patch

    from apps.tesoreria.extractos.servicio_ingesta import obtener_tasa_usd_ves

    # B-3: si ocurre IntegrityError al crear ExtractoBancarioArchivo (carrera concurrente),
    # el savepoint interno evita TransactionManagementError y recupera el corte ganador.
    corte = _xlsx(
        [
            ["Cuenta: 0172-0110-79-1105554321"],
            ["Saldo Inicial: 100,00"],
            ["Fecha", "Referencia", "Concepto", "Débito", "Crédito", "Saldo"],
            ["04/09/2026", "901", "TRF CR INM CLIENT\x00E", "", "50,00", "150,00"],
        ]
    )
    primero = importar_extracto_bancario(
        empresa=empresa_a,
        cuenta_bancaria=cuenta_ves_a,
        contenido=corte,
        nombre_archivo="corte\x00_1.xlsx",
        usuario=user_a,
    )
    assert primero.archivo.nombre_archivo == "corte_1.xlsx"

    qs_vacio = ExtractoBancarioArchivo.objects.none()
    with patch.object(ExtractoBancarioArchivo.objects, "select_for_update", return_value=qs_vacio):
        recuperado = importar_extracto_bancario(
            empresa=empresa_a,
            cuenta_bancaria=cuenta_ves_a,
            contenido=corte,
            nombre_archivo="corte_carrera.xlsx",
            usuario=user_a,
        )
    assert recuperado.ya_existia_archivo is True
    assert recuperado.archivo.pk == primero.archivo.pk

    # M-1: usuario multi-empresa NO puede vincular movimiento de Empresa A con cuenta de Empresa B
    user_a.empresas.add(empresa_b)
    url_mov = "/api/tesoreria/movimientos-bancarios/"
    resp_cruzado = api_a.post(
        url_mov,
        {
            "id_empresa": str(empresa_a.id_empresa),
            "id_cuenta_bancaria": str(cuenta_ves_b.id_cuenta_bancaria),
            "fecha_mov": "2026-09-05",
            "descripcion": "Intento cruzado",
            "tipo": "CREDITO",
            "monto": "100.00",
        },
        format="json",
    )
    assert resp_cruzado.status_code == 400
    assert "id_cuenta_bancaria" in resp_cruzado.json()

    # Monto <= 0 rechazado
    resp_cero = api_a.post(
        url_mov,
        {
            "id_empresa": str(empresa_a.id_empresa),
            "id_cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria),
            "fecha_mov": "2026-09-05",
            "descripcion": "Monto cero",
            "tipo": "CREDITO",
            "monto": "0.00",
        },
        format="json",
    )
    assert resp_cero.status_code == 400

    # Inmutabilidad contable en movimiento importado desde EXTRACTO (no permite mutar monto, sí descripción)
    mov_ext = primero.archivo.movimientos.first()
    assert mov_ext is not None
    assert api_a.patch(f"{url_mov}{mov_ext.pk}/", {"monto": "999.00"}, format="json").status_code == 400
    assert api_a.patch(f"{url_mov}{mov_ext.pk}/", {"descripcion": "Nota auditada"}, format="json").status_code == 200

    # Filtro ?empresa= en ambos endpoints
    assert (
        api_a.get("/api/tesoreria/extractos-bancarios/", {"empresa": str(empresa_a.id_empresa)}).json()["count"] == 1
    )
    assert (
        api_a.get("/api/tesoreria/extractos-bancarios/", {"empresa": str(empresa_b.id_empresa)}).json()["count"] == 0
    )
    assert api_a.get(url_mov, {"empresa": str(empresa_a.id_empresa)}).json()["count"] == 1

    # M-2: precedencia determinística en tasa inversa (propia del tenant gana sobre global NULL)
    TasaCambio.objects.create(
        id_empresa=None,
        id_moneda_origen=moneda_ves,
        id_moneda_destino=moneda_usd,
        tipo_tasa="OFICIAL_BCV",
        valor_tasa=D("0.01000000"),  # recíproco = 100
        fecha_tasa=date(2026, 9, 20),
    )
    TasaCambio.objects.create(
        id_empresa=empresa_a,
        id_moneda_origen=moneda_ves,
        id_moneda_destino=moneda_usd,
        tipo_tasa="OFICIAL_BCV",
        valor_tasa=D("0.02000000"),  # recíproco = 50
        fecha_tasa=date(2026, 9, 20),
    )
    assert obtener_tasa_usd_ves(empresa_a, date(2026, 9, 20)) == D("50.00000000")

    # S-1: validación de limite inválido en MCP
    tok_a = CapabilityToken.objects.create(empresa=empresa_a, nombre="MCP Limite", scopes=["tesoreria:read"])
    with pytest.raises(ValueError, match="entero válido"):
        tesoreria_listar_extractos(str(tok_a.token), str(empresa_a.id_empresa), limite="abc")  # type: ignore[arg-type]
