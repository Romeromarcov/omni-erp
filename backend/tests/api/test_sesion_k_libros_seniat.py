"""
Sesión K — Tests Libros SENIAT

Verifica:
- test_libro_ventas_txt_200(): GET /api/fiscal/libro-ventas/?empresa=&periodo= devuelve 200
- test_libro_ventas_txt_content(): La respuesta contiene pipe-delimited con cabecera correcta
- test_libro_ventas_txt_lineas(): Hay una línea por cada factura emitida
- test_libro_ventas_pdf_200(): GET /api/fiscal/libro-ventas-pdf/ devuelve PDF válido
- test_libro_ventas_pdf_magic(): El PDF empieza con %PDF-
- test_libro_ventas_aislamiento(): Empresa B no puede ver libros de Empresa A
- test_libro_ventas_sin_auth_401(): Sin autenticación retorna 401
- test_periodo_rango_directo(): ?desde=...&hasta=... también funciona
- test_periodo_invalido_400(): ?periodo=xxx retorna 400
- test_empresa_requerida_400(): Sin ?empresa retorna 400
- test_libro_compras_txt_200(): GET /api/fiscal/libro-compras/ devuelve 200
- test_libro_compras_pdf_200(): GET /api/fiscal/libro-compras-pdf/ devuelve PDF válido
- test_periodos_fiscales_list(): GET /api/fiscal/periodos-fiscales/ lista períodos
- test_cerrar_periodo_fiscal(): POST cierra el período y queda registrado
- test_cerrar_periodo_idempotente(): Cerrar dos veces no falla
- test_libro_ventas_solo_estados_validos(): Borradores NO aparecen en el libro
"""
import datetime

import pytest
from rest_framework.test import APIClient

from apps.crm.models import Cliente
from apps.finanzas.models import Moneda


# ── Fixtures ──────────────────────────────────────────────────────────────────

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


@pytest.fixture
def cliente_a(db, empresa_a):
    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Cliente SENIAT Test S.A.",
        rif="J-30000001-0",
    )


@pytest.fixture
def factura_emitida(db, empresa_a, cliente_a, moneda_usd):
    from apps.ventas.models import FacturaFiscal
    return FacturaFiscal.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente_a,
        numero_control="00100",
        numero_factura="F-2026-001",
        fecha_emision=datetime.date(2026, 5, 10),
        id_moneda=moneda_usd,
        base_imponible="1000.00",
        monto_iva="160.00",
        monto_total="1160.00",
        estado="EMITIDA",
    )


@pytest.fixture
def factura_borrador(db, empresa_a, cliente_a, moneda_usd):
    """Esta factura NO debe aparecer en el libro (estado=BORRADOR)."""
    from apps.ventas.models import FacturaFiscal
    return FacturaFiscal.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente_a,
        numero_control="00200",
        numero_factura="F-2026-002",
        fecha_emision=datetime.date(2026, 5, 15),
        id_moneda=moneda_usd,
        base_imponible="500.00",
        monto_iva="80.00",
        monto_total="580.00",
        estado="BORRADOR",
    )


PERIODO = "2026-05"
URL_VENTAS_TXT = "/api/fiscal/libro-ventas/"
URL_VENTAS_PDF = "/api/fiscal/libro-ventas-pdf/"
URL_COMPRAS_TXT = "/api/fiscal/libro-compras/"
URL_COMPRAS_PDF = "/api/fiscal/libro-compras-pdf/"
URL_PERIODOS = "/api/fiscal/periodos-fiscales/"


def _eid(empresa):
    return str(empresa.id_empresa)


# ── Libro de Ventas TXT ───────────────────────────────────────────────────────

class TestLibroVentasTXT:
    def test_libro_ventas_txt_200(self, client_a, empresa_a, factura_emitida):
        resp = client_a.get(URL_VENTAS_TXT, {"empresa": _eid(empresa_a), "periodo": PERIODO})
        assert resp.status_code == 200

    def test_libro_ventas_txt_content_type(self, client_a, empresa_a, factura_emitida):
        resp = client_a.get(URL_VENTAS_TXT, {"empresa": _eid(empresa_a), "periodo": PERIODO})
        assert "text/plain" in resp["Content-Type"]

    def test_libro_ventas_txt_cabecera(self, client_a, empresa_a, factura_emitida):
        """La primera línea es la cabecera esperada."""
        resp = client_a.get(URL_VENTAS_TXT, {"empresa": _eid(empresa_a), "periodo": PERIODO})
        primera = resp.content.decode("utf-8").splitlines()[0]
        assert primera == "RIF_EMISOR|RIF_RECEPTOR|FECHA|NRO_CTRL|NRO_FAC|BASE_IMPONIBLE|IVA|TOTAL"

    def test_libro_ventas_txt_lineas(self, client_a, empresa_a, factura_emitida):
        """Hay 2 líneas: cabecera + 1 factura."""
        resp = client_a.get(URL_VENTAS_TXT, {"empresa": _eid(empresa_a), "periodo": PERIODO})
        lineas = resp.content.decode("utf-8").splitlines()
        assert len(lineas) == 2

    def test_libro_ventas_txt_contiene_numero_factura(self, client_a, empresa_a, factura_emitida):
        resp = client_a.get(URL_VENTAS_TXT, {"empresa": _eid(empresa_a), "periodo": PERIODO})
        assert "F-2026-001" in resp.content.decode("utf-8")

    def test_libro_ventas_solo_estados_validos(self, client_a, empresa_a, factura_emitida, factura_borrador):
        """Solo facturas EMITIDA/PAGADA/VENCIDA aparecen en el libro."""
        resp = client_a.get(URL_VENTAS_TXT, {"empresa": _eid(empresa_a), "periodo": PERIODO})
        contenido = resp.content.decode("utf-8")
        assert "F-2026-001" in contenido
        assert "F-2026-002" not in contenido

    def test_periodo_rango_directo(self, client_a, empresa_a, factura_emitida):
        """?desde=...&hasta=... también funciona."""
        resp = client_a.get(
            URL_VENTAS_TXT,
            {"empresa": _eid(empresa_a), "desde": "2026-05-01", "hasta": "2026-05-31"},
        )
        assert resp.status_code == 200

    def test_periodo_invalido_400(self, client_a, empresa_a):
        resp = client_a.get(URL_VENTAS_TXT, {"empresa": _eid(empresa_a), "periodo": "2026/05"})
        assert resp.status_code == 400

    def test_empresa_requerida_400(self, client_a):
        resp = client_a.get(URL_VENTAS_TXT, {"periodo": PERIODO})
        assert resp.status_code == 400

    def test_libro_ventas_sin_auth_401(self, empresa_a):
        resp = APIClient().get(URL_VENTAS_TXT, {"empresa": _eid(empresa_a), "periodo": PERIODO})
        assert resp.status_code == 401

    def test_libro_ventas_aislamiento(self, client_b, empresa_a, factura_emitida):
        """Usuario B no puede ver libros de empresa A."""
        resp = client_b.get(URL_VENTAS_TXT, {"empresa": _eid(empresa_a), "periodo": PERIODO})
        assert resp.status_code == 404


# ── Libro de Ventas PDF ───────────────────────────────────────────────────────

class TestLibroVentasPDF:
    def test_libro_ventas_pdf_200(self, client_a, empresa_a, factura_emitida):
        resp = client_a.get(URL_VENTAS_PDF, {"empresa": _eid(empresa_a), "periodo": PERIODO})
        assert resp.status_code == 200

    def test_libro_ventas_pdf_content_type(self, client_a, empresa_a, factura_emitida):
        resp = client_a.get(URL_VENTAS_PDF, {"empresa": _eid(empresa_a), "periodo": PERIODO})
        assert "application/pdf" in resp["Content-Type"]

    def test_libro_ventas_pdf_magic(self, client_a, empresa_a, factura_emitida):
        resp = client_a.get(URL_VENTAS_PDF, {"empresa": _eid(empresa_a), "periodo": PERIODO})
        assert resp.content[:5] == b"%PDF-"

    def test_libro_ventas_pdf_bytes_no_vacios(self, client_a, empresa_a, factura_emitida):
        resp = client_a.get(URL_VENTAS_PDF, {"empresa": _eid(empresa_a), "periodo": PERIODO})
        assert len(resp.content) > 1024

    def test_libro_ventas_pdf_aislamiento(self, client_b, empresa_a, factura_emitida):
        resp = client_b.get(URL_VENTAS_PDF, {"empresa": _eid(empresa_a), "periodo": PERIODO})
        assert resp.status_code == 404

    def test_libro_ventas_pdf_vacio_igual_pdf_valido(self, client_a, empresa_a):
        """Un período sin facturas igual genera un PDF válido (no error)."""
        resp = client_a.get(URL_VENTAS_PDF, {"empresa": _eid(empresa_a), "periodo": "2020-01"})
        assert resp.status_code == 200
        assert resp.content[:5] == b"%PDF-"


# ── Libro de Compras ──────────────────────────────────────────────────────────

class TestLibroCompras:
    def test_libro_compras_txt_200(self, client_a, empresa_a):
        resp = client_a.get(URL_COMPRAS_TXT, {"empresa": _eid(empresa_a), "periodo": PERIODO})
        assert resp.status_code == 200

    def test_libro_compras_txt_cabecera(self, client_a, empresa_a):
        resp = client_a.get(URL_COMPRAS_TXT, {"empresa": _eid(empresa_a), "periodo": PERIODO})
        primera = resp.content.decode("utf-8").splitlines()[0]
        assert primera == "RIF_EMISOR|RIF_RECEPTOR|FECHA|NRO_CTRL|NRO_FAC|BASE_IMPONIBLE|IVA|TOTAL"

    def test_libro_compras_pdf_200(self, client_a, empresa_a):
        resp = client_a.get(URL_COMPRAS_PDF, {"empresa": _eid(empresa_a), "periodo": PERIODO})
        assert resp.status_code == 200

    def test_libro_compras_pdf_magic(self, client_a, empresa_a):
        resp = client_a.get(URL_COMPRAS_PDF, {"empresa": _eid(empresa_a), "periodo": PERIODO})
        assert resp.content[:5] == b"%PDF-"

    def test_libro_compras_aislamiento(self, client_b, empresa_a):
        resp = client_b.get(URL_COMPRAS_TXT, {"empresa": _eid(empresa_a), "periodo": PERIODO})
        assert resp.status_code == 404


# ── Períodos Fiscales ─────────────────────────────────────────────────────────

class TestPeriodosFiscales:
    def test_periodos_fiscales_list_200(self, client_a, empresa_a):
        resp = client_a.get(URL_PERIODOS, {"empresa": _eid(empresa_a)})
        assert resp.status_code == 200
        assert isinstance(resp.data, list)

    def test_cerrar_periodo_fiscal(self, client_a, empresa_a):
        resp = client_a.post(
            f"{URL_PERIODOS}2026/5/cerrar/",
            {"empresa": _eid(empresa_a)},
            QUERY_STRING=f"empresa={_eid(empresa_a)}",
        )
        assert resp.status_code == 200
        assert resp.data["cerrado"] is True

    def test_cerrar_periodo_idempotente(self, client_a, empresa_a):
        url = f"{URL_PERIODOS}2026/4/cerrar/?empresa={_eid(empresa_a)}"
        r1 = client_a.post(url)
        r2 = client_a.post(url)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r2.data["cerrado"] is True

    def test_periodo_cerrado_aparece_en_lista(self, client_a, empresa_a):
        client_a.post(f"{URL_PERIODOS}2026/3/cerrar/?empresa={_eid(empresa_a)}")
        resp = client_a.get(URL_PERIODOS, {"empresa": _eid(empresa_a)})
        assert any(p["año"] == 2026 and p["mes"] == 3 and p["cerrado"] for p in resp.data)

    def test_periodos_sin_auth_401(self, empresa_a):
        resp = APIClient().get(URL_PERIODOS, {"empresa": _eid(empresa_a)})
        assert resp.status_code == 401

    def test_periodo_aislamiento(self, client_b, empresa_a):
        resp = client_b.get(URL_PERIODOS, {"empresa": _eid(empresa_a)})
        assert resp.status_code == 404
