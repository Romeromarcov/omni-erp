"""
Sesión J — Tests Generación PDF

Verifica:
- test_pdf_factura_fiscal_200(): GET /api/ventas/facturas-fiscales/{id}/pdf/ devuelve 200 con PDF
- test_pdf_factura_content_type(): Content-Type es application/pdf
- test_pdf_factura_campos_legales(): El PDF contiene datos del emisor y receptor (bytes no vacíos)
- test_pdf_cotizacion_200(): GET /api/ventas/cotizaciones/{id}/pdf/ devuelve 200
- test_pdf_estado_cuenta_200(): GET /api/cxc/cuentas-por-cobrar/estado-cuenta/{id}/pdf/ devuelve 200
- test_pdf_factura_ajena_404(): Usuario sin acceso recibe 404
"""
import datetime

import pytest
from rest_framework.test import APIClient

from apps.finanzas.models import Moneda
from apps.crm.models import Cliente


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
        razon_social="Cliente PDF Test S.A.",
        rif="J-20000001-0",
    )


@pytest.fixture
def factura_a(db, empresa_a, cliente_a, moneda_usd):
    from apps.ventas.models import FacturaFiscal
    return FacturaFiscal.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente_a,
        numero_control="00001",
        numero_factura="F-001",
        fecha_emision=datetime.date(2026, 5, 24),
        id_moneda=moneda_usd,
        base_imponible="1000.00",
        monto_iva="160.00",
        monto_total="1160.00",
        estado="EMITIDA",
    )


@pytest.fixture
def cotizacion_a(db, empresa_a, cliente_a, moneda_usd):
    from apps.ventas.models import Cotizacion
    return Cotizacion.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente_a,
        numero_cotizacion="C-001",
        fecha_cotizacion=datetime.date(2026, 5, 24),
        fecha_vencimiento=datetime.date(2026, 6, 24),
        id_moneda=moneda_usd,
        monto_total="500.00",
        estado="BORRADOR",
    )


@pytest.fixture
def cxc_a(db, empresa_a, cliente_a):
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar
    return CuentaPorCobrar.objects.create(
        empresa=empresa_a,
        cliente=cliente_a,
        monto="1160.00",
        fecha_emision=datetime.date(2026, 5, 24),
        fecha_vencimiento=datetime.date(2026, 6, 24),
        estado="pendiente",
        descripcion="Factura F-001",
    )


# ── Tests Factura Fiscal PDF ──────────────────────────────────────────────────

class TestPDFFacturaFiscal:
    def test_pdf_factura_fiscal_200(self, client_a, factura_a):
        """GET /api/ventas/facturas-fiscales/{id}/pdf/ retorna 200."""
        resp = client_a.get(f"/api/ventas/facturas-fiscales/{factura_a.pk}/pdf/")
        assert resp.status_code == 200

    def test_pdf_factura_content_type(self, client_a, factura_a):
        """Content-Type es application/pdf."""
        resp = client_a.get(f"/api/ventas/facturas-fiscales/{factura_a.pk}/pdf/")
        assert "application/pdf" in resp["Content-Type"]

    def test_pdf_factura_bytes_no_vacios(self, client_a, factura_a):
        """El PDF retornado tiene contenido (más de 1KB)."""
        resp = client_a.get(f"/api/ventas/facturas-fiscales/{factura_a.pk}/pdf/")
        assert len(resp.content) > 1024

    def test_pdf_factura_comienza_con_magic(self, client_a, factura_a):
        """El PDF comienza con los bytes mágicos del formato PDF (%PDF-)."""
        resp = client_a.get(f"/api/ventas/facturas-fiscales/{factura_a.pk}/pdf/")
        assert resp.content[:5] == b"%PDF-"

    def test_pdf_factura_ajena_404(self, client_b, factura_a):
        """Usuario B no puede descargar factura de empresa A."""
        resp = client_b.get(f"/api/ventas/facturas-fiscales/{factura_a.pk}/pdf/")
        assert resp.status_code == 404

    def test_pdf_factura_sin_auth_401(self, factura_a):
        """Sin autenticación retorna 401."""
        client = APIClient()
        resp = client.get(f"/api/ventas/facturas-fiscales/{factura_a.pk}/pdf/")
        assert resp.status_code == 401


# ── Tests Cotización PDF ──────────────────────────────────────────────────────

class TestPDFCotizacion:
    def test_pdf_cotizacion_200(self, client_a, cotizacion_a):
        """GET /api/ventas/cotizaciones/{id}/pdf/ retorna 200."""
        resp = client_a.get(f"/api/ventas/cotizaciones/{cotizacion_a.pk}/pdf/")
        assert resp.status_code == 200

    def test_pdf_cotizacion_content_type(self, client_a, cotizacion_a):
        """Content-Type es application/pdf."""
        resp = client_a.get(f"/api/ventas/cotizaciones/{cotizacion_a.pk}/pdf/")
        assert "application/pdf" in resp["Content-Type"]

    def test_pdf_cotizacion_bytes_no_vacios(self, client_a, cotizacion_a):
        """El PDF de cotización tiene contenido."""
        resp = client_a.get(f"/api/ventas/cotizaciones/{cotizacion_a.pk}/pdf/")
        assert len(resp.content) > 1024

    def test_pdf_cotizacion_comienza_con_magic(self, client_a, cotizacion_a):
        """El PDF comienza con %PDF-."""
        resp = client_a.get(f"/api/ventas/cotizaciones/{cotizacion_a.pk}/pdf/")
        assert resp.content[:5] == b"%PDF-"

    def test_pdf_cotizacion_ajena_404(self, client_b, cotizacion_a):
        """Usuario B no puede descargar cotización de empresa A."""
        resp = client_b.get(f"/api/ventas/cotizaciones/{cotizacion_a.pk}/pdf/")
        assert resp.status_code == 404


# ── Tests Estado de Cuenta CxC PDF ───────────────────────────────────────────

class TestPDFEstadoCuenta:
    def test_pdf_estado_cuenta_200(self, client_a, cxc_a, cliente_a):
        """GET /api/cxc/cuentas-por-cobrar/estado-cuenta/{cliente_id}/pdf/ retorna 200."""
        resp = client_a.get(
            f"/api/cxc/cuentas-por-cobrar/estado-cuenta/{cliente_a.pk}/pdf/"
        )
        assert resp.status_code == 200

    def test_pdf_estado_cuenta_content_type(self, client_a, cxc_a, cliente_a):
        """Content-Type es application/pdf."""
        resp = client_a.get(
            f"/api/cxc/cuentas-por-cobrar/estado-cuenta/{cliente_a.pk}/pdf/"
        )
        assert "application/pdf" in resp["Content-Type"]

    def test_pdf_estado_cuenta_bytes_no_vacios(self, client_a, cxc_a, cliente_a):
        """El PDF de estado de cuenta tiene contenido."""
        resp = client_a.get(
            f"/api/cxc/cuentas-por-cobrar/estado-cuenta/{cliente_a.pk}/pdf/"
        )
        assert len(resp.content) > 1024

    def test_pdf_estado_cuenta_comienza_con_magic(self, client_a, cxc_a, cliente_a):
        """El PDF comienza con %PDF-."""
        resp = client_a.get(
            f"/api/cxc/cuentas-por-cobrar/estado-cuenta/{cliente_a.pk}/pdf/"
        )
        assert resp.content[:5] == b"%PDF-"

    def test_pdf_estado_cuenta_cliente_ajeno_404(self, client_b, cliente_a):
        """Usuario B no puede ver estado de cuenta de cliente de empresa A."""
        resp = client_b.get(
            f"/api/cxc/cuentas-por-cobrar/estado-cuenta/{cliente_a.pk}/pdf/"
        )
        assert resp.status_code == 404
