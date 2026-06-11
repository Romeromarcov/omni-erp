"""
Tests del paquete P0-7 (fix/fugas-y-comandos) — auditoría integral 2026-06-10.

Cubre:
- SEC-M3: el comando `create_initial_data` (admin/admin123) es inejecutable
  fuera de DEBUG (gate `CommandError`).
- SEC-M4: las respuestas de error al cliente no filtran `str(exc)` interno
  (mensaje genérico + logger.exception). Test conductual sobre los PDF 503 y
  verificación estática (grep) sobre los módulos saneados.
- SEC-B2: `fiscal` calcular usa `id_empresa__in` (antes `id__in` → FieldError
  500) y solo aplica configuración de empresas visibles.
- SEC-B3: `monedas_info` valida el query param `?empresa=` contra
  `get_empresas_visible` (empresa ajena o malformada → 404).
"""
import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


APPS_DIR = Path(__file__).resolve().parents[1] / "apps"


@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


def _stub_request(user, **query):
    """Request mínimo para acciones que solo usan query_params/user/data."""
    return SimpleNamespace(query_params=query, user=user, data={})


# ══════════════════════════════════════════════════════════════════════════════
# SEC-M3 — create_initial_data bloqueado fuera de DEBUG
# ══════════════════════════════════════════════════════════════════════════════


class TestCreateInitialDataGate:
    def test_bloqueado_fuera_de_debug(self, settings):
        from apps.core.models import Empresa, Usuarios

        settings.DEBUG = False
        with pytest.raises(CommandError, match="deshabilitado fuera de DEBUG"):
            call_command("create_initial_data")
        # No dejó rastro: ni el superusuario débil ni la empresa demo.
        assert not Usuarios.objects.filter(username="admin").exists()
        assert not Empresa.objects.filter(
            nombre_legal="Innova Systems C.A."
        ).exists()

    def test_permitido_solo_en_debug(self, settings):
        from apps.core.models import Usuarios

        settings.DEBUG = True
        call_command("create_initial_data")
        assert Usuarios.objects.filter(username="admin").exists()


# ══════════════════════════════════════════════════════════════════════════════
# SEC-B2 — fiscal/calcular: empresa_id se resuelve con id_empresa__in
# ══════════════════════════════════════════════════════════════════════════════


class TestFiscalCalcularEmpresaVisible:
    URL = "/api/fiscal/tasas-iva/calcular/"

    def _body(self, empresa_id):
        return {
            "lineas": [{"subtotal": "100", "tipo_iva": "GENERAL"}],
            "metodo_pago": "EFECTIVO_BS",
            "empresa_id": str(empresa_id),
        }

    def test_empresa_propia_aplica_su_tasa_sin_fielderror(
        self, client_a, empresa_a
    ):
        # Antes del fix, `id__in` sobre Empresa (pk = id_empresa) lanzaba
        # FieldError → 500. Ahora resuelve la empresa y usa su tasa configurada.
        from apps.fiscal.models import TasaIVAEmpresa

        TasaIVAEmpresa.objects.create(
            id_empresa=empresa_a, tipo="GENERAL", tasa=Decimal("0.08"), activo=True
        )
        resp = client_a.post(self.URL, self._body(empresa_a.id_empresa), format="json")
        assert resp.status_code == 200
        assert Decimal(resp.json()["iva_general"]) == Decimal("8.00")

    def test_empresa_ajena_se_ignora(self, client_a, empresa_b):
        # user_a no ve empresa_b: su configuración fiscal NO debe aplicarse
        # (cae al default SENIAT 16%).
        from apps.fiscal.models import TasaIVAEmpresa

        TasaIVAEmpresa.objects.create(
            id_empresa=empresa_b, tipo="GENERAL", tasa=Decimal("0.08"), activo=True
        )
        resp = client_a.post(self.URL, self._body(empresa_b.id_empresa), format="json")
        assert resp.status_code == 200
        assert Decimal(resp.json()["iva_general"]) == Decimal("16.00")


# ══════════════════════════════════════════════════════════════════════════════
# SEC-B3 — monedas_info valida ?empresa= contra get_empresas_visible
# ══════════════════════════════════════════════════════════════════════════════


class TestMonedasInfoEmpresaValidada:
    # La ruta HTTP de monedas_info está rota (lookup_field vs firma pk — ya
    # documentado en test_finanzas_views_cobertura2); como en
    # test_finanzas_gaps_cobertura, se invoca la acción directamente.

    def _viewset(self, metodo):
        from apps.finanzas.views import MetodoPagoViewSet

        vs = MetodoPagoViewSet()
        vs.get_object = lambda: metodo
        return vs

    @pytest.fixture
    def metodo(self, empresa_a, moneda_usd):
        from apps.finanzas.models import MetodoPago

        m = MetodoPago.objects.create(
            nombre_metodo="Efectivo P07", tipo_metodo="EFECTIVO", empresa=empresa_a
        )
        m.monedas.add(moneda_usd)
        return m

    def test_empresa_propia_200(self, user_a, empresa_a, metodo):
        resp = self._viewset(metodo).monedas_info(
            _stub_request(user_a, empresa=str(empresa_a.id_empresa))
        )
        assert resp.status_code == 200
        assert "asociadas" in resp.data

    def test_empresa_ajena_404(self, user_a, empresa_b, metodo):
        resp = self._viewset(metodo).monedas_info(
            _stub_request(user_a, empresa=str(empresa_b.id_empresa))
        )
        assert resp.status_code == 404

    def test_empresa_malformada_404(self, user_a, metodo):
        resp = self._viewset(metodo).monedas_info(
            _stub_request(user_a, empresa="no-es-un-uuid")
        )
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# SEC-M4 — sin str(exc) al cliente (R-CODE-8)
# ══════════════════════════════════════════════════════════════════════════════


class TestRespuestasSinDetalleInterno:
    def test_factura_pdf_importerror_mensaje_generico(self, user_a, monkeypatch):
        from apps.ventas.views import FacturaFiscalViewSet

        def _boom(_factura):
            raise ImportError("detalle-interno-secreto: falta libfoo 1.2.3")

        monkeypatch.setattr("apps.fiscal.pdf_factura.generar_pdf_factura", _boom)
        vs = FacturaFiscalViewSet()
        vs.get_object = lambda: SimpleNamespace(numero_factura="F-00000001")
        resp = vs.pdf(_stub_request(user_a))
        assert resp.status_code == 503
        assert "detalle-interno-secreto" not in str(resp.data)
        assert "libfoo" not in str(resp.data)

    def test_cotizacion_pdf_importerror_mensaje_generico(self, user_a, monkeypatch):
        from apps.ventas.views import CotizacionViewSet

        def _boom(_cotizacion):
            raise ImportError("detalle-interno-secreto: falta libbar 4.5.6")

        monkeypatch.setattr(
            "apps.ventas.pdf_cotizacion.generar_pdf_cotizacion", _boom
        )
        vs = CotizacionViewSet()
        vs.get_object = lambda: SimpleNamespace(numero_cotizacion="C-00000001")
        resp = vs.pdf(_stub_request(user_a))
        assert resp.status_code == 503
        assert "detalle-interno-secreto" not in str(resp.data)

    def test_grep_sin_str_exc_en_respuestas(self):
        """Verificación estática (DoD): 0 `str(exc)`/`str(e)` dentro de
        respuestas al cliente en los módulos saneados por SEC-M4."""
        objetivos = [
            APPS_DIR / "integration_hub" / "views.py",
            APPS_DIR / "cxc" / "api" / "agente.py",
            APPS_DIR / "ventas" / "views.py",
            APPS_DIR / "cuentas_por_cobrar" / "views.py",
        ]
        # Línea que arma una Response/yield SSE con str(exc) o str(e).
        patron = re.compile(
            r"(Response\(|yield\s+f?[\"']data:).*str\((exc|e)\)"
        )
        violaciones = []
        for archivo in objetivos:
            for n, linea in enumerate(
                archivo.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if patron.search(linea):
                    violaciones.append(f"{archivo.name}:{n}: {linea.strip()}")
        assert not violaciones, (
            "str(exc) filtrado al cliente (R-CODE-8):\n" + "\n".join(violaciones)
        )

    def test_test_connection_no_filtra_error_crudo(
        self, user_a, empresa_a, monkeypatch
    ):
        """integration_hub test_connection: error del conector → 502 con
        mensaje genérico y mensaje_estado sin el detalle crudo."""
        from apps.integration_hub.models import ConectorInstancia, ConectorProveedor
        from apps.integration_hub.views import ConectorInstanciaViewSet

        proveedor = ConectorProveedor.objects.get_or_create(
            codigo="odoo", defaults={"nombre": "Odoo"}
        )[0]
        instancia = ConectorInstancia.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor,
            nombre="Odoo P07",
        )

        def _boom(_instancia):
            raise RuntimeError("password=supersecreta host=10.0.0.1")

        monkeypatch.setattr(
            "apps.integration_hub.views.registry.get_connector", _boom
        )
        vs = ConectorInstanciaViewSet()
        vs.get_object = lambda: instancia
        resp = vs.test_connection(_stub_request(user_a))
        assert resp.status_code == 502
        assert resp.data["success"] is False
        assert "supersecreta" not in str(resp.data)
        instancia.refresh_from_db()
        assert "supersecreta" not in instancia.mensaje_estado
        assert instancia.estado == "error"
