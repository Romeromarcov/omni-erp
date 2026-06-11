"""
Backfill de cobertura — apps/tesoreria/views.py + serializers.py
(plan "Cero Dudas", COV/tesoreria). Complementa test_sesion_m_tesoreria.py
(que NO se toca): aquí van las ramas que esa suite no ejercita.

- CajaViewSet (tesorería) list aislado.
- MovimientoInternoFondoSerializer.create: crea el movimiento + los dos
  MovimientoCajaBanco (TRANSFERENCIA_SALIDA/ENTRADA) con montos exactos.
- OperacionCambioDivisaSerializer.create: BUG documentado (CTF-013) — el
  flujo revienta (hoy con ImportError por `DocumentoGasto` inexistente; CTF-013
  describe además el IntegrityError por `monto_base_empresa`). Se testea el
  contrato actual con pytest.raises, SIN enmascararlo.
- MovimientoBancarioViewSet: perform_create (tenant ajeno → 403, propio → 201),
  filtro ?cuenta=, importar-csv (faltan campos 400 / empresa inaccesible 403 /
  cuenta inexistente 404 / éxito 200) y conciliar-auto cuenta inexistente 404.
- ConciliacionBancariaViewSet.perform_create vía POST (iniciar_conciliacion).
"""
import datetime
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.finanzas.models import Caja, CuentaBancariaEmpresa, MovimientoCajaBanco
from apps.tesoreria.models import ConciliacionBancaria, MovimientoBancario, MovimientoInternoFondo

pytestmark = pytest.mark.django_db

URL_CAJAS = "/api/tesoreria/cajas/"
URL_MOV_INT = "/api/tesoreria/movimientos-internos-fondo/"
URL_CAMBIO = "/api/tesoreria/operaciones-cambio-divisa/"
URL_MOV_BANC = "/api/tesoreria/movimientos-bancarios/"
URL_CONC = "/api/tesoreria/conciliaciones-bancarias/"


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
def caja_origen(empresa_a, moneda_usd):
    return Caja.objects.create(
        empresa=empresa_a, nombre="Caja Origen", moneda=moneda_usd, tipo_caja="REGISTRADORA"
    )


@pytest.fixture
def caja_destino(empresa_a, moneda_usd):
    return Caja.objects.create(
        empresa=empresa_a, nombre="Caja Destino", moneda=moneda_usd, tipo_caja="GERENCIA"
    )


@pytest.fixture
def cuenta_a(empresa_a, moneda_usd):
    return CuentaBancariaEmpresa.objects.create(
        id_empresa=empresa_a, nombre_banco="Banco Gap", numero_cuenta="0102-G1",
        tipo_cuenta="CORRIENTE", id_moneda=moneda_usd, saldo_actual=Decimal("1000.00"),
    )


# ── CajaViewSet (tesorería) ───────────────────────────────────────────────────

class TestCajaTesoreria:
    def test_list_aislado_por_empresa(self, client_a, client_b, caja_origen):
        nombres_a = {c["nombre"] for c in client_a.get(URL_CAJAS).json()["results"]}
        assert "Caja Origen" in nombres_a
        nombres_b = {c["nombre"] for c in client_b.get(URL_CAJAS).json()["results"]}
        assert "Caja Origen" not in nombres_b

    def test_sin_auth_401(self):
        assert APIClient().get(URL_CAJAS).status_code == 401


# ── MovimientoInternoFondo ────────────────────────────────────────────────────

class TestMovimientoInternoFondo:
    def test_create_genera_doble_movimiento_caja_banco(
        self, client_a, caja_origen, caja_destino, moneda_usd, user_a
    ):
        resp = client_a.post(URL_MOV_INT, {
            "caja_origen": caja_origen.id_caja,
            "caja_destino": caja_destino.id_caja,
            "id_moneda": str(moneda_usd.id_moneda),
            "monto": "120.50",
            "descripcion": "Traslado a gerencia",
            "usuario": user_a.pk,
        }, format="json")
        assert resp.status_code == 201, resp.content
        mov = MovimientoInternoFondo.objects.get()
        assert mov.monto == Decimal("120.50")

        salida = MovimientoCajaBanco.objects.get(tipo_movimiento="TRANSFERENCIA_SALIDA")
        entrada = MovimientoCajaBanco.objects.get(tipo_movimiento="TRANSFERENCIA_ENTRADA")
        assert salida.id_caja == caja_origen
        assert entrada.id_caja == caja_destino
        assert salida.monto == Decimal("120.50")
        assert entrada.monto == Decimal("120.50")
        assert salida.concepto == "Traslado a gerencia"
        assert salida.id_empresa == caja_origen.empresa

    def test_list_aislado_por_empresa_de_caja_origen(
        self, client_a, client_b, caja_origen, caja_destino, moneda_usd
    ):
        MovimientoInternoFondo.objects.create(
            caja_origen=caja_origen, caja_destino=caja_destino,
            id_moneda=moneda_usd, monto=Decimal("10.00"),
        )
        assert client_a.get(URL_MOV_INT).json()["count"] == 1
        assert client_b.get(URL_MOV_INT).json()["count"] == 0


# ── OperacionCambioDivisa — contrato actual ROTO (CTF-013) ───────────────────

class TestOperacionCambioDivisa:
    def test_create_revienta_antes_de_registrar_nada(
        self, client_a, empresa_a, moneda_usd, caja_origen, caja_destino
    ):
        """
        BUG (documentado en docs/ctf/CTF-013.md, NO se enmascara):
        OperacionCambioDivisaSerializer.create está roto. CTF-013 describe el
        IntegrityError por `monto_base_empresa` NOT NULL, pero el código actual
        revienta incluso ANTES: `from apps.gastos.models import DocumentoGasto`
        (línea 72 del serializer) — ese modelo NO existe en apps.gastos →
        ImportError. El flujo de cambio de divisa nunca completa; cuando se
        arregle la feature, este test debe reemplazarse por el flujo feliz +
        atomicidad.
        """
        from apps.finanzas.models import Moneda

        ves = Moneda.objects.create(
            nombre="Bolívar", codigo_iso="VES", simbolo="Bs",
            tipo_moneda="fiat", es_generica=True,
        )
        payload = {
            "empresa": empresa_a.id_empresa,
            "numero_operacion": "OP-001",
            "fecha_operacion": "2026-06-09T10:00:00Z",
            "tipo_operacion": "VENTA",
            "moneda_origen": str(moneda_usd.id_moneda),
            "moneda_destino": str(ves.id_moneda),
            "monto_origen": "100.0000",
            "tasa_cambio": "36.500000",
            "monto_destino": "3650.0000",
            "caja_origen": caja_origen.id_caja,
            "caja_destino": caja_destino.id_caja,
        }
        with pytest.raises(ImportError, match="DocumentoGasto"):
            client_a.post(URL_CAMBIO, payload, format="json")
        # Nada queda persistido: revienta en el import, antes del doble registro
        from apps.tesoreria.models import OperacionCambioDivisa

        assert OperacionCambioDivisa.objects.count() == 0

    def test_list_aislado_por_empresa(self, client_a, client_b, empresa_a, moneda_usd):
        from apps.finanzas.models import Moneda
        from apps.tesoreria.models import OperacionCambioDivisa

        ves = Moneda.objects.create(
            nombre="Bolívar", codigo_iso="VES", simbolo="Bs",
            tipo_moneda="fiat", es_generica=True,
        )
        OperacionCambioDivisa.objects.create(
            empresa=empresa_a, numero_operacion="OP-LIST",
            fecha_operacion=datetime.datetime(2026, 6, 9, 10, 0, tzinfo=datetime.timezone.utc),
            tipo_operacion="COMPRA", moneda_origen=moneda_usd, moneda_destino=ves,
            monto_origen=Decimal("50.0000"), tasa_cambio=Decimal("36.500000"),
            monto_destino=Decimal("1825.0000"),
        )
        assert client_a.get(URL_CAMBIO).json()["count"] == 1
        assert client_b.get(URL_CAMBIO).json()["count"] == 0


# ── MovimientoBancarioViewSet ─────────────────────────────────────────────────

class TestMovimientoBancarioCreate:
    def _payload(self, empresa, cuenta):
        return {
            "id_empresa": str(empresa.id_empresa),
            "id_cuenta_bancaria": str(cuenta.id_cuenta_bancaria),
            "fecha_mov": "2026-06-01",
            "descripcion": "Depósito manual",
            "tipo": "CREDITO",
            "monto": "350.00",
            "referencia": "REF-M1",
        }

    def test_create_propio_201(self, client_a, empresa_a, cuenta_a):
        resp = client_a.post(URL_MOV_BANC, self._payload(empresa_a, cuenta_a), format="json")
        assert resp.status_code == 201, resp.content
        mov = MovimientoBancario.objects.get()
        assert mov.monto == Decimal("350.00")
        assert mov.estado == "PENDIENTE"  # estado es read-only en el serializer

    def test_create_empresa_ajena_403(self, client_b, empresa_a, cuenta_a):
        # SEC-M1: el scope de tenant de FKs rechaza el pk ajeno en el
        # serializer (400, sin revelar existencia) antes del check 403 viejo.
        resp = client_b.post(URL_MOV_BANC, self._payload(empresa_a, cuenta_a), format="json")
        assert resp.status_code == 400
        assert MovimientoBancario.objects.count() == 0

    def test_filtro_por_cuenta(self, client_a, empresa_a, cuenta_a, moneda_usd):
        otra = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_a, nombre_banco="Banco 2", numero_cuenta="0102-G2",
            tipo_cuenta="AHORRO", id_moneda=moneda_usd,
        )
        MovimientoBancario.objects.create(
            id_empresa=empresa_a, id_cuenta_bancaria=cuenta_a,
            fecha_mov=datetime.date(2026, 6, 1), descripcion="En cuenta A",
            tipo="CREDITO", monto=Decimal("10.00"),
        )
        resp = client_a.get(URL_MOV_BANC, {"cuenta": str(otra.id_cuenta_bancaria)})
        assert resp.json()["count"] == 0
        resp = client_a.get(URL_MOV_BANC, {"cuenta": str(cuenta_a.id_cuenta_bancaria)})
        assert resp.json()["count"] == 1


class TestImportarCSV:
    URL = f"{URL_MOV_BANC}importar-csv/"

    def _archivo(self, contenido=None):
        contenido = contenido or (
            "fecha,descripcion,tipo,monto,referencia\n"
            "2026-05-01,Pago cliente,CREDITO,1000.00,R1\n"
            "2026-05-02,Comision,DEBITO,25.00,\n"
        )
        return SimpleUploadedFile("extracto.csv", contenido.encode("utf-8"), content_type="text/csv")

    def test_faltan_campos_400(self, client_a):
        resp = client_a.post(self.URL, {})
        assert resp.status_code == 400
        assert resp.json() == {"error": "Se requieren: cuenta_bancaria y archivo."}

    def test_empresa_no_accesible_403(self, client_a, empresa_b, cuenta_a):
        resp = client_a.post(self.URL, {
            "empresa": str(empresa_b.id_empresa),
            "cuenta_bancaria": str(cuenta_a.id_cuenta_bancaria),
            "archivo": self._archivo(),
        }, format="multipart")
        assert resp.status_code == 403
        assert resp.json() == {"error": "Sin empresa accesible."}

    def test_cuenta_inexistente_404(self, client_a, empresa_a):
        import uuid

        resp = client_a.post(self.URL, {
            "cuenta_bancaria": str(uuid.uuid4()),
            "archivo": self._archivo(),
        }, format="multipart")
        assert resp.status_code == 404
        assert resp.json() == {"error": "Cuenta bancaria no encontrada."}

    def test_importa_ok_200(self, client_a, empresa_a, cuenta_a):
        resp = client_a.post(self.URL, {
            "empresa": str(empresa_a.id_empresa),
            "cuenta_bancaria": str(cuenta_a.id_cuenta_bancaria),
            "archivo": self._archivo(),
        }, format="multipart")
        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert body["importados"] == 2
        assert body["errores"] == 0
        assert MovimientoBancario.objects.count() == 2
        credito = MovimientoBancario.objects.get(tipo="CREDITO")
        assert credito.monto == Decimal("1000.00")
        assert credito.origen == "CSV"


class TestConciliarAutoCuentaInexistente:
    def test_404(self, client_a):
        import uuid

        resp = client_a.post(
            f"{URL_MOV_BANC}conciliar-auto/",
            {"cuenta_bancaria": str(uuid.uuid4())},
            format="json",
        )
        assert resp.status_code == 404
        assert resp.json() == {"error": "Cuenta bancaria no encontrada."}


# ── ConciliacionBancariaViewSet.perform_create ───────────────────────────────

class TestCrearConciliacionPorAPI:
    def test_post_inicia_conciliacion(self, client_a, empresa_a, cuenta_a, user_a):
        resp = client_a.post(URL_CONC, {
            "id_empresa": str(empresa_a.id_empresa),
            "id_cuenta_bancaria": str(cuenta_a.id_cuenta_bancaria),
            "periodo_inicio": "2026-05-01",
            "periodo_fin": "2026-05-31",
            "saldo_banco": "1500.00",
            "saldo_libro": "1000.00",
        }, format="json")
        assert resp.status_code == 201, resp.content
        conc = ConciliacionBancaria.objects.get()
        assert conc.estado == "ABIERTA"
        assert conc.diferencia == Decimal("500.00")
        assert conc.realizada_por == user_a
        assert Decimal(resp.json()["diferencia"]) == Decimal("500.00")
