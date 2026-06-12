"""
Pagos de contribuciones parafiscales — Capa B §6.7 (tropicalización VE).

Cobertura de integración del ciclo completo:

- declarar (pendiente) con validaciones de período/monto/contribución/proceso.
- no doble pago: segunda declaración del mismo período+contribución → 400
  (y constraint condicional en BD como backstop); anular libera el período.
- pagar: egreso REAL en el libro de caja (saldo de la caja/cuenta baja por el
  monto exacto + MovimientoCajaBanco EGRESO + Pago genérico IMPUESTO) y asiento
  PAGO_PARAFISCAL balanceado (montos verificados a mano).
- R-CODE-11: contabilidad activa sin MapeoContable PAGO_PARAFISCAL → 422 y
  rollback TOTAL (ni Pago, ni movimiento, ni saldo tocado, ni cambio de estado).
- Transiciones inválidas → 400; recursos de otra empresa → 404 (R-CODE-1).
- Idempotencia opt-in (cabecera ``Idempotency-Key``) en create y pagar.
- Tool MCP ``fiscal_parafiscales_pendientes`` (scope fiscal:read).
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.contabilidad.models import AsientoContable, DetalleAsiento
from apps.finanzas.models import Caja, CuentaBancariaEmpresa, MetodoPago, MovimientoCajaBanco, Pago
from apps.fiscal.models import ContribucionParafiscal, PagoContribucionParafiscal

pytestmark = pytest.mark.django_db

BASE_URL = "/api/fiscal/pagos-parafiscales/"


def _today():
    return timezone.now().date()


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────


@pytest.fixture
def contribucion_a(db, empresa_a):
    return ContribucionParafiscal.objects.create(
        nombre="Seguro Social Obligatorio",
        codigo="IVSS-A",
        tipo="IVSS",
        porcentaje=Decimal("9.00"),
        base_calculo="NOMINA",
        empresa=empresa_a,
    )


@pytest.fixture
def contribucion_b(db, empresa_b):
    return ContribucionParafiscal.objects.create(
        nombre="FAOV ajeno",
        codigo="FAOV-B",
        tipo="FAOV",
        porcentaje=Decimal("2.00"),
        base_calculo="NOMINA",
        empresa=empresa_b,
    )


@pytest.fixture
def contribucion_global(db):
    return ContribucionParafiscal.objects.create(
        nombre="INCES",
        codigo="INCES-G",
        tipo="INCES",
        porcentaje=Decimal("2.00"),
        base_calculo="NOMINA",
        empresa=None,
    )


@pytest.fixture
def caja_usd_a(db, empresa_a, moneda_usd):
    return Caja.objects.create(
        empresa=empresa_a,
        nombre="Caja Matriz USD",
        tipo_caja="MATRIZ",
        moneda=moneda_usd,
        saldo_actual=Decimal("5000.00"),
    )


@pytest.fixture
def cuenta_bancaria_a(db, empresa_a, moneda_usd):
    return CuentaBancariaEmpresa.objects.create(
        id_empresa=empresa_a,
        nombre_banco="Banco Test",
        numero_cuenta="0102-0000-0000000001",
        tipo_cuenta="CORRIENTE",
        id_moneda=moneda_usd,
        saldo_actual=Decimal("9000.00"),
    )


@pytest.fixture
def metodo_pago_a(db, empresa_a):
    return MetodoPago.objects.create(
        empresa=empresa_a, nombre_metodo="Transferencia USD", tipo_metodo="ELECTRONICO"
    )


@pytest.fixture
def pago_parafiscal_a(db, empresa_a, contribucion_a, moneda_usd):
    """Declaración pendiente de IVSS por 1234.56 USD del período 2026-05."""
    return PagoContribucionParafiscal.objects.create(
        id_empresa=empresa_a,
        contribucion=contribucion_a,
        periodo_año=2026,
        periodo_mes=5,
        monto=Decimal("1234.56"),
        id_moneda=moneda_usd,
    )


@pytest.fixture
def mapeo_pago_parafiscal(db, empresa_a):
    """PlanCuentas + MapeoContable PAGO_PARAFISCAL para la empresa A."""
    from apps.contabilidad.models import MapeoContable, PlanCuentas

    debe = PlanCuentas.objects.create(
        id_empresa=empresa_a,
        codigo_cuenta="6.1.01",
        nombre_cuenta="Gasto contribuciones parafiscales",
        tipo_cuenta="GASTO",
        naturaleza="DEUDORA",
        nivel=1,
    )
    haber = PlanCuentas.objects.create(
        id_empresa=empresa_a,
        codigo_cuenta="1.1.10",
        nombre_cuenta="Caja y bancos",
        tipo_cuenta="ACTIVO",
        naturaleza="DEUDORA",
        nivel=1,
    )
    return MapeoContable.objects.create(
        id_empresa=empresa_a,
        tipo_asiento="PAGO_PARAFISCAL",
        cuenta_debe=debe,
        cuenta_haber=haber,
    )


@pytest.fixture
def client_a(user_a):
    from rest_framework.test import APIClient

    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def client_b(user_b):
    from rest_framework.test import APIClient

    c = APIClient()
    c.force_authenticate(user=user_b)
    return c


def _asiento_de(pago_parafiscal):
    return AsientoContable.objects.filter(
        id_documento_origen=pago_parafiscal.pk,
        nombre_modelo_origen="PagoContribucionParafiscal",
    )


def _payload_crear(empresa, contribucion, moneda, **extra):
    data = {
        "id_empresa": str(empresa.id_empresa),
        "contribucion": contribucion.pk,
        "periodo_año": 2026,
        "periodo_mes": 5,
        "monto": "1234.56",
        "id_moneda": str(moneda.id_moneda),
    }
    data.update(extra)
    return data


# ─────────────────────────────────────────────
# Declarar (creación tenant-safe + período)
# ─────────────────────────────────────────────


class TestCrearPagoParafiscal:
    def test_crear_pendiente(self, client_a, empresa_a, contribucion_a, moneda_usd):
        resp = client_a.post(
            BASE_URL, _payload_crear(empresa_a, contribucion_a, moneda_usd), format="json"
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["estado"] == "pendiente"
        assert resp.data["periodo"] == "2026-05"
        assert Decimal(resp.data["monto"]) == Decimal("1234.56")
        assert resp.data["contribucion_codigo"] == "IVSS-A"

    def test_crear_con_contribucion_global(self, client_a, empresa_a, contribucion_global, moneda_usd):
        """Las contribuciones globales (empresa=None) son usables por cualquier tenant."""
        resp = client_a.post(
            BASE_URL, _payload_crear(empresa_a, contribucion_global, moneda_usd), format="json"
        )
        assert resp.status_code == 201, resp.data

    def test_crear_con_contribucion_de_otra_empresa_retorna_400(
        self, client_a, empresa_a, contribucion_b, moneda_usd
    ):
        resp = client_a.post(
            BASE_URL, _payload_crear(empresa_a, contribucion_b, moneda_usd), format="json"
        )
        assert resp.status_code == 400

    def test_crear_con_empresa_ajena_retorna_400(self, client_a, empresa_b, contribucion_b, moneda_usd):
        """SEC-M1 / R-CODE-1: la FK de empresa está acotada a empresas visibles."""
        resp = client_a.post(
            BASE_URL, _payload_crear(empresa_b, contribucion_b, moneda_usd), format="json"
        )
        assert resp.status_code == 400

    def test_monto_cero_retorna_400(self, client_a, empresa_a, contribucion_a, moneda_usd):
        resp = client_a.post(
            BASE_URL,
            _payload_crear(empresa_a, contribucion_a, moneda_usd, monto="0.00"),
            format="json",
        )
        assert resp.status_code == 400

    def test_mes_invalido_retorna_400(self, client_a, empresa_a, contribucion_a, moneda_usd):
        resp = client_a.post(
            BASE_URL,
            _payload_crear(empresa_a, contribucion_a, moneda_usd, periodo_mes=13),
            format="json",
        )
        assert resp.status_code == 400

    def test_año_fuera_de_rango_retorna_400(self, client_a, empresa_a, contribucion_a, moneda_usd):
        resp = client_a.post(
            BASE_URL,
            _payload_crear(empresa_a, contribucion_a, moneda_usd, periodo_año=1999),
            format="json",
        )
        assert resp.status_code == 400

    def test_proceso_nomina_propio_ok(self, client_a, empresa_a, contribucion_a, moneda_usd):
        from apps.nomina.models import PeriodoNomina, ProcesoNomina

        periodo = PeriodoNomina.objects.create(
            id_empresa=empresa_a,
            nombre_periodo="Mayo 2026",
            fecha_inicio=_today(),
            fecha_fin=_today(),
            fecha_pago=_today(),
            tipo_periodo="MENSUAL",
        )
        proceso = ProcesoNomina.objects.create(
            id_empresa=empresa_a,
            id_periodo_nomina=periodo,
            numero_proceso="NOM-2026-05",
            fecha_proceso=timezone.now(),
        )
        resp = client_a.post(
            BASE_URL,
            _payload_crear(empresa_a, contribucion_a, moneda_usd, id_proceso_nomina=str(proceso.pk)),
            format="json",
        )
        assert resp.status_code == 201, resp.data
        # DRF representa las FKs como UUID (no str) en resp.data
        assert str(resp.data["id_proceso_nomina"]) == str(proceso.pk)

    def test_proceso_nomina_de_otra_empresa_retorna_400(
        self, client_a, empresa_a, empresa_b, contribucion_a, moneda_usd
    ):
        from apps.nomina.models import PeriodoNomina, ProcesoNomina

        periodo_b = PeriodoNomina.objects.create(
            id_empresa=empresa_b,
            nombre_periodo="Mayo 2026 B",
            fecha_inicio=_today(),
            fecha_fin=_today(),
            fecha_pago=_today(),
            tipo_periodo="MENSUAL",
        )
        proceso_b = ProcesoNomina.objects.create(
            id_empresa=empresa_b,
            id_periodo_nomina=periodo_b,
            numero_proceso="NOM-B-2026-05",
            fecha_proceso=timezone.now(),
        )
        resp = client_a.post(
            BASE_URL,
            _payload_crear(
                empresa_a, contribucion_a, moneda_usd, id_proceso_nomina=str(proceso_b.pk)
            ),
            format="json",
        )
        assert resp.status_code == 400

    def test_estado_no_es_escribible_por_payload(self, client_a, empresa_a, contribucion_a, moneda_usd):
        resp = client_a.post(
            BASE_URL,
            _payload_crear(empresa_a, contribucion_a, moneda_usd, estado="pagado"),
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["estado"] == "pendiente"


# ─────────────────────────────────────────────
# No doble pago del mismo período + contribución
# ─────────────────────────────────────────────


class TestNoDoblePago:
    def test_doble_declaracion_mismo_periodo_retorna_400(
        self, client_a, empresa_a, contribucion_a, moneda_usd, pago_parafiscal_a
    ):
        resp = client_a.post(
            BASE_URL, _payload_crear(empresa_a, contribucion_a, moneda_usd), format="json"
        )
        assert resp.status_code == 400
        assert "doble pago" in str(resp.data)

    def test_otro_mes_si_se_permite(self, client_a, empresa_a, contribucion_a, moneda_usd, pago_parafiscal_a):
        resp = client_a.post(
            BASE_URL,
            _payload_crear(empresa_a, contribucion_a, moneda_usd, periodo_mes=6),
            format="json",
        )
        assert resp.status_code == 201, resp.data

    def test_otra_contribucion_mismo_periodo_si_se_permite(
        self, client_a, empresa_a, contribucion_global, moneda_usd, pago_parafiscal_a
    ):
        resp = client_a.post(
            BASE_URL, _payload_crear(empresa_a, contribucion_global, moneda_usd), format="json"
        )
        assert resp.status_code == 201, resp.data

    def test_anular_libera_el_periodo(
        self, client_a, empresa_a, contribucion_a, moneda_usd, pago_parafiscal_a
    ):
        resp = client_a.post(f"{BASE_URL}{pago_parafiscal_a.pk}/anular/", {}, format="json")
        assert resp.status_code == 200
        resp = client_a.post(
            BASE_URL, _payload_crear(empresa_a, contribucion_a, moneda_usd), format="json"
        )
        assert resp.status_code == 201, resp.data

    def test_constraint_de_bd_es_el_backstop(self, empresa_a, contribucion_a, moneda_usd, pago_parafiscal_a):
        """Aunque se salte la API, la BD rechaza la segunda fila no anulada."""
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            PagoContribucionParafiscal.objects.create(
                id_empresa=empresa_a,
                contribucion=contribucion_a,
                periodo_año=2026,
                periodo_mes=5,
                monto=Decimal("1.00"),
                id_moneda=moneda_usd,
            )

    def test_misma_empresa_distinto_tenant_no_colisiona(
        self, empresa_b, contribucion_b, moneda_usd, pago_parafiscal_a
    ):
        """El mismo período en OTRA empresa es independiente (R-CODE-1)."""
        otro = PagoContribucionParafiscal.objects.create(
            id_empresa=empresa_b,
            contribucion=contribucion_b,
            periodo_año=2026,
            periodo_mes=5,
            monto=Decimal("99.00"),
            id_moneda=moneda_usd,
        )
        assert otro.pk is not None


# ─────────────────────────────────────────────
# Pagar (egreso en caja + asiento balanceado)
# ─────────────────────────────────────────────


class TestPagar:
    def test_ciclo_pagar_con_caja(
        self, client_a, pago_parafiscal_a, caja_usd_a, metodo_pago_a, mapeo_pago_parafiscal
    ):
        url = f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/"
        resp = client_a.post(
            url,
            {
                "metodo_pago": str(metodo_pago_a.pk),
                "caja": str(caja_usd_a.pk),
                "referencia": "PLANILLA-IVSS-0526",
            },
            format="json",
        )
        assert resp.status_code == 200, resp.data

        # Estado y trazabilidad del registro
        pago_parafiscal_a.refresh_from_db()
        assert pago_parafiscal_a.estado == "pagado"
        assert pago_parafiscal_a.referencia == "PLANILLA-IVSS-0526"
        assert pago_parafiscal_a.fecha_pago == _today()
        assert pago_parafiscal_a.id_pago is not None

        # Pago genérico de finanzas (EGRESO/IMPUESTO) con FK a la contribución
        pago = Pago.objects.get(pk=pago_parafiscal_a.id_pago_id)
        assert pago.tipo_operacion == "EGRESO"
        assert pago.tipo_documento == "IMPUESTO"
        assert pago.monto == Decimal("1234.56")
        assert pago.id_contribucion_id == pago_parafiscal_a.contribucion_id
        assert pago.id_documento == pago_parafiscal_a.pk

        # Egreso en el libro de caja: saldo 5000.00 − 1234.56 = 3765.44 (a mano)
        caja_usd_a.refresh_from_db()
        assert caja_usd_a.saldo_actual == Decimal("3765.44")
        mov = MovimientoCajaBanco.objects.get(id_caja=caja_usd_a)
        assert mov.tipo_movimiento == "EGRESO"
        assert mov.monto == Decimal("1234.56")
        assert mov.saldo_anterior == Decimal("5000.00")
        assert mov.saldo_nuevo == Decimal("3765.44")

        # Asiento PAGO_PARAFISCAL balanceado: debe == haber == 1234.56
        asiento = _asiento_de(pago_parafiscal_a).get()
        detalles = DetalleAsiento.objects.filter(id_asiento=asiento)
        assert detalles.count() == 2
        assert sum(d.debe for d in detalles) == Decimal("1234.56")
        assert sum(d.haber for d in detalles) == Decimal("1234.56")

        # Respuesta: dinero como string (R-CODE-4) + saldo de la caja
        assert resp.data["caja_saldo_actual"] == "3765.44"
        assert resp.data["pago_id"] == str(pago.pk)

    def test_pagar_con_cuenta_bancaria(
        self, client_a, pago_parafiscal_a, cuenta_bancaria_a, metodo_pago_a, mapeo_pago_parafiscal
    ):
        url = f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/"
        resp = client_a.post(
            url,
            {"metodo_pago": str(metodo_pago_a.pk), "cuenta_bancaria": str(cuenta_bancaria_a.pk)},
            format="json",
        )
        assert resp.status_code == 200, resp.data
        cuenta_bancaria_a.refresh_from_db()
        # 9000.00 − 1234.56 = 7765.44 (a mano)
        assert cuenta_bancaria_a.saldo_actual == Decimal("7765.44")
        assert resp.data["cuenta_saldo_actual"] == "7765.44"
        mov = MovimientoCajaBanco.objects.get(id_cuenta_bancaria=cuenta_bancaria_a)
        assert mov.tipo_movimiento == "EGRESO"
        assert mov.monto == Decimal("1234.56")

    def test_pagar_con_fecha_explicita(
        self, client_a, pago_parafiscal_a, caja_usd_a, metodo_pago_a, mapeo_pago_parafiscal
    ):
        resp = client_a.post(
            f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/",
            {
                "metodo_pago": str(metodo_pago_a.pk),
                "caja": str(caja_usd_a.pk),
                "fecha_pago": "2026-06-01",
            },
            format="json",
        )
        assert resp.status_code == 200, resp.data
        pago_parafiscal_a.refresh_from_db()
        assert str(pago_parafiscal_a.fecha_pago) == "2026-06-01"

    def test_pagar_metodo_publico_de_otro_tenant_ok(
        self, client_a, empresa_b, pago_parafiscal_a, caja_usd_a, mapeo_pago_parafiscal
    ):
        metodo_publico = MetodoPago.objects.create(
            empresa=empresa_b, nombre_metodo="Zelle público", tipo_metodo="ELECTRONICO", es_publico=True
        )
        resp = client_a.post(
            f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/",
            {"metodo_pago": str(metodo_publico.pk), "caja": str(caja_usd_a.pk)},
            format="json",
        )
        assert resp.status_code == 200, resp.data

    def test_pagar_sin_metodo_retorna_400(self, client_a, pago_parafiscal_a, caja_usd_a):
        resp = client_a.post(
            f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/", {"caja": str(caja_usd_a.pk)}, format="json"
        )
        assert resp.status_code == 400

    def test_pagar_metodo_privado_de_otro_tenant_retorna_404(
        self, client_a, empresa_b, pago_parafiscal_a, caja_usd_a
    ):
        metodo_b = MetodoPago.objects.create(
            empresa=empresa_b, nombre_metodo="Privado B", tipo_metodo="EFECTIVO"
        )
        resp = client_a.post(
            f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/",
            {"metodo_pago": str(metodo_b.pk), "caja": str(caja_usd_a.pk)},
            format="json",
        )
        assert resp.status_code == 404

    def test_pagar_sin_origen_de_fondos_retorna_400(self, client_a, pago_parafiscal_a, metodo_pago_a):
        resp = client_a.post(
            f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/",
            {"metodo_pago": str(metodo_pago_a.pk)},
            format="json",
        )
        assert resp.status_code == 400

    def test_pagar_con_caja_y_cuenta_retorna_400(
        self, client_a, pago_parafiscal_a, caja_usd_a, cuenta_bancaria_a, metodo_pago_a
    ):
        resp = client_a.post(
            f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/",
            {
                "metodo_pago": str(metodo_pago_a.pk),
                "caja": str(caja_usd_a.pk),
                "cuenta_bancaria": str(cuenta_bancaria_a.pk),
            },
            format="json",
        )
        assert resp.status_code == 400

    def test_pagar_cuenta_de_otra_empresa_retorna_404(
        self, client_a, empresa_b, moneda_usd, pago_parafiscal_a, metodo_pago_a
    ):
        cuenta_b = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_b,
            nombre_banco="Banco B",
            numero_cuenta="0102-3333-0000000004",
            tipo_cuenta="CORRIENTE",
            id_moneda=moneda_usd,
            saldo_actual=Decimal("500.00"),
        )
        resp = client_a.post(
            f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/",
            {"metodo_pago": str(metodo_pago_a.pk), "cuenta_bancaria": str(cuenta_b.pk)},
            format="json",
        )
        assert resp.status_code == 404
        cuenta_b.refresh_from_db()
        assert cuenta_b.saldo_actual == Decimal("500.00")

    def test_pagar_caja_de_otra_empresa_retorna_404(
        self, client_a, empresa_b, moneda_usd, pago_parafiscal_a, metodo_pago_a
    ):
        caja_b = Caja.objects.create(
            empresa=empresa_b, nombre="Caja B", moneda=moneda_usd, saldo_actual=Decimal("100.00")
        )
        resp = client_a.post(
            f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/",
            {"metodo_pago": str(metodo_pago_a.pk), "caja": str(caja_b.pk)},
            format="json",
        )
        assert resp.status_code == 404
        caja_b.refresh_from_db()
        assert caja_b.saldo_actual == Decimal("100.00")

    def test_pagar_caja_moneda_distinta_retorna_400(
        self, client_a, empresa_a, pago_parafiscal_a, metodo_pago_a
    ):
        from apps.finanzas.models import Moneda

        ves = Moneda.objects.create(nombre="Bolívar", codigo_iso="VES", simbolo="Bs", tipo_moneda="fiat")
        caja_ves = Caja.objects.create(
            empresa=empresa_a, nombre="Caja VES", moneda=ves, saldo_actual=Decimal("0.00")
        )
        resp = client_a.post(
            f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/",
            {"metodo_pago": str(metodo_pago_a.pk), "caja": str(caja_ves.pk)},
            format="json",
        )
        assert resp.status_code == 400
        assert "moneda" in str(resp.data).lower()

    def test_pagar_caja_inactiva_retorna_400(
        self, client_a, empresa_a, moneda_usd, pago_parafiscal_a, metodo_pago_a
    ):
        caja_inactiva = Caja.objects.create(
            empresa=empresa_a, nombre="Caja vieja", moneda=moneda_usd, activa=False
        )
        resp = client_a.post(
            f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/",
            {"metodo_pago": str(metodo_pago_a.pk), "caja": str(caja_inactiva.pk)},
            format="json",
        )
        assert resp.status_code == 400

    def test_pagar_dos_veces_retorna_400(
        self, client_a, pago_parafiscal_a, caja_usd_a, metodo_pago_a, mapeo_pago_parafiscal
    ):
        url = f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/"
        body = {"metodo_pago": str(metodo_pago_a.pk), "caja": str(caja_usd_a.pk)}
        assert client_a.post(url, body, format="json").status_code == 200
        resp = client_a.post(url, body, format="json")
        assert resp.status_code == 400
        # Solo UN egreso quedó registrado: el saldo no baja dos veces
        caja_usd_a.refresh_from_db()
        assert caja_usd_a.saldo_actual == Decimal("3765.44")
        assert Pago.objects.count() == 1


# ─────────────────────────────────────────────
# R-CODE-11: rollback total si falta mapeo (422)
# ─────────────────────────────────────────────


class TestRollbackSinMapeo:
    def test_pagar_sin_mapeo_contabilidad_activa_422_y_rollback(
        self, client_a, empresa_a, pago_parafiscal_a, caja_usd_a, metodo_pago_a
    ):
        empresa_a.contabilidad_activa = True
        empresa_a.save(update_fields=["contabilidad_activa"])

        resp = client_a.post(
            f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/",
            {"metodo_pago": str(metodo_pago_a.pk), "caja": str(caja_usd_a.pk)},
            format="json",
        )
        assert resp.status_code == 422

        # Rollback TOTAL: ni Pago, ni movimiento, ni saldo tocado, ni estado
        pago_parafiscal_a.refresh_from_db()
        caja_usd_a.refresh_from_db()
        assert pago_parafiscal_a.estado == "pendiente"
        assert pago_parafiscal_a.id_pago is None
        assert caja_usd_a.saldo_actual == Decimal("5000.00")
        assert Pago.objects.count() == 0
        assert MovimientoCajaBanco.objects.count() == 0
        assert _asiento_de(pago_parafiscal_a).count() == 0

    def test_pagar_sin_mapeo_contabilidad_inactiva_procede_sin_asiento(
        self, client_a, empresa_a, pago_parafiscal_a, caja_usd_a, metodo_pago_a
    ):
        """R-PROD-3 (bodega informal): sin contabilidad activa, la operación procede."""
        assert empresa_a.contabilidad_activa is False
        resp = client_a.post(
            f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/",
            {"metodo_pago": str(metodo_pago_a.pk), "caja": str(caja_usd_a.pk)},
            format="json",
        )
        assert resp.status_code == 200, resp.data
        pago_parafiscal_a.refresh_from_db()
        assert pago_parafiscal_a.estado == "pagado"
        assert _asiento_de(pago_parafiscal_a).count() == 0
        caja_usd_a.refresh_from_db()
        assert caja_usd_a.saldo_actual == Decimal("3765.44")


# ─────────────────────────────────────────────
# Transiciones inválidas / inmutabilidad
# ─────────────────────────────────────────────


class TestTransicionesInvalidas:
    def test_anular_pendiente_ok_y_reanular_400(self, client_a, pago_parafiscal_a):
        url = f"{BASE_URL}{pago_parafiscal_a.pk}/anular/"
        assert client_a.post(url, {}, format="json").status_code == 200
        pago_parafiscal_a.refresh_from_db()
        assert pago_parafiscal_a.estado == "anulado"
        assert client_a.post(url, {}, format="json").status_code == 400

    def test_anular_pagado_retorna_400(
        self, client_a, pago_parafiscal_a, caja_usd_a, metodo_pago_a, mapeo_pago_parafiscal
    ):
        client_a.post(
            f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/",
            {"metodo_pago": str(metodo_pago_a.pk), "caja": str(caja_usd_a.pk)},
            format="json",
        )
        resp = client_a.post(f"{BASE_URL}{pago_parafiscal_a.pk}/anular/", {}, format="json")
        assert resp.status_code == 400

    def test_pagar_anulado_retorna_400(self, client_a, pago_parafiscal_a, caja_usd_a, metodo_pago_a):
        client_a.post(f"{BASE_URL}{pago_parafiscal_a.pk}/anular/", {}, format="json")
        resp = client_a.post(
            f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/",
            {"metodo_pago": str(metodo_pago_a.pk), "caja": str(caja_usd_a.pk)},
            format="json",
        )
        assert resp.status_code == 400

    def test_patch_sobre_pagado_retorna_400(
        self, client_a, pago_parafiscal_a, caja_usd_a, metodo_pago_a, mapeo_pago_parafiscal
    ):
        """La historia financiera es inmutable: PATCH tras pagar → 400."""
        client_a.post(
            f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/",
            {"metodo_pago": str(metodo_pago_a.pk), "caja": str(caja_usd_a.pk)},
            format="json",
        )
        resp = client_a.patch(f"{BASE_URL}{pago_parafiscal_a.pk}/", {"monto": "1.00"}, format="json")
        assert resp.status_code == 400
        pago_parafiscal_a.refresh_from_db()
        assert pago_parafiscal_a.monto == Decimal("1234.56")

    def test_patch_sobre_pendiente_si_es_editable(self, client_a, pago_parafiscal_a):
        resp = client_a.patch(
            f"{BASE_URL}{pago_parafiscal_a.pk}/", {"monto": "1500.00"}, format="json"
        )
        assert resp.status_code == 200, resp.data
        pago_parafiscal_a.refresh_from_db()
        assert pago_parafiscal_a.monto == Decimal("1500.00")

    def test_delete_retorna_405(self, client_a, pago_parafiscal_a):
        """R-CODE-6: los documentos financieros se anulan, nunca se borran."""
        resp = client_a.delete(f"{BASE_URL}{pago_parafiscal_a.pk}/")
        assert resp.status_code == 405
        assert PagoContribucionParafiscal.objects.filter(pk=pago_parafiscal_a.pk).exists()


# ─────────────────────────────────────────────
# R-CODE-1: aislamiento multi-tenant → 404
# ─────────────────────────────────────────────


class TestAislamientoTenant:
    def test_usuario_b_no_ve_pago_de_empresa_a(self, client_b, pago_parafiscal_a):
        resp = client_b.get(f"{BASE_URL}{pago_parafiscal_a.pk}/")
        assert resp.status_code == 404

    def test_listado_no_filtra_pagos_ajenos(self, client_b, pago_parafiscal_a):
        resp = client_b.get(BASE_URL)
        assert resp.status_code == 200
        ids = [p["id_pago_parafiscal"] for p in resp.data["results"]]
        assert str(pago_parafiscal_a.pk) not in ids

    def test_usuario_b_no_puede_pagar_pago_de_empresa_a(
        self, client_b, pago_parafiscal_a, caja_usd_a, metodo_pago_a
    ):
        resp = client_b.post(
            f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/",
            {"metodo_pago": str(metodo_pago_a.pk), "caja": str(caja_usd_a.pk)},
            format="json",
        )
        assert resp.status_code == 404
        pago_parafiscal_a.refresh_from_db()
        assert pago_parafiscal_a.estado == "pendiente"

    def test_usuario_b_no_puede_anular_pago_de_empresa_a(self, client_b, pago_parafiscal_a):
        resp = client_b.post(f"{BASE_URL}{pago_parafiscal_a.pk}/anular/", {}, format="json")
        assert resp.status_code == 404

    def test_filtros_de_listado(self, client_a, pago_parafiscal_a, empresa_a, contribucion_global, moneda_usd):
        otro = PagoContribucionParafiscal.objects.create(
            id_empresa=empresa_a,
            contribucion=contribucion_global,
            periodo_año=2026,
            periodo_mes=4,
            monto=Decimal("10.00"),
            id_moneda=moneda_usd,
            estado="pagado",
        )
        resp = client_a.get(BASE_URL, {"estado": "pendiente"})
        ids = [p["id_pago_parafiscal"] for p in resp.data["results"]]
        assert str(pago_parafiscal_a.pk) in ids
        assert str(otro.pk) not in ids

        resp = client_a.get(BASE_URL, {"periodo_mes": "4", "periodo_año": "2026"})
        ids = [p["id_pago_parafiscal"] for p in resp.data["results"]]
        assert ids == [str(otro.pk)]

        resp = client_a.get(BASE_URL, {"contribucion": str(contribucion_global.pk)})
        ids = [p["id_pago_parafiscal"] for p in resp.data["results"]]
        assert ids == [str(otro.pk)]


# ─────────────────────────────────────────────
# Idempotencia (P1-2) en los POST de dinero
# ─────────────────────────────────────────────


class TestIdempotencia:
    def test_pagar_reintento_con_misma_clave_no_duplica(
        self, client_a, pago_parafiscal_a, caja_usd_a, metodo_pago_a, mapeo_pago_parafiscal
    ):
        url = f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/"
        body = {"metodo_pago": str(metodo_pago_a.pk), "caja": str(caja_usd_a.pk)}
        r1 = client_a.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY="parafiscal-pago-001")
        assert r1.status_code == 200, r1.data
        r2 = client_a.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY="parafiscal-pago-001")
        assert r2.status_code == 200

        # La respuesta se reproduce y NO se re-ejecuta la lógica de negocio
        assert r2.data["pago_id"] == r1.data["pago_id"]
        assert Pago.objects.count() == 1
        assert MovimientoCajaBanco.objects.count() == 1
        caja_usd_a.refresh_from_db()
        assert caja_usd_a.saldo_actual == Decimal("3765.44")
        assert _asiento_de(pago_parafiscal_a).count() == 1

    def test_misma_clave_con_payload_distinto_retorna_422(
        self, client_a, pago_parafiscal_a, caja_usd_a, metodo_pago_a, mapeo_pago_parafiscal
    ):
        url = f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/"
        r1 = client_a.post(
            url,
            {"metodo_pago": str(metodo_pago_a.pk), "caja": str(caja_usd_a.pk)},
            format="json",
            HTTP_IDEMPOTENCY_KEY="clave-paraf",
        )
        assert r1.status_code == 200
        r2 = client_a.post(
            url,
            {"metodo_pago": str(metodo_pago_a.pk), "caja": str(caja_usd_a.pk), "referencia": "X"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="clave-paraf",
        )
        assert r2.status_code == 422

    def test_create_reintento_con_misma_clave_no_duplica(
        self, client_a, empresa_a, contribucion_a, moneda_usd
    ):
        body = _payload_crear(empresa_a, contribucion_a, moneda_usd)
        r1 = client_a.post(BASE_URL, body, format="json", HTTP_IDEMPOTENCY_KEY="parafiscal-decl-1")
        assert r1.status_code == 201, r1.data
        r2 = client_a.post(BASE_URL, body, format="json", HTTP_IDEMPOTENCY_KEY="parafiscal-decl-1")
        assert r2.status_code == 201
        assert r2.data["id_pago_parafiscal"] == r1.data["id_pago_parafiscal"]
        assert PagoContribucionParafiscal.objects.count() == 1

    def test_clave_fallida_no_se_consume(self, client_a, pago_parafiscal_a, caja_usd_a, metodo_pago_a):
        """Un 4xx no consume la clave: el reintento corregido puede ejecutarse."""
        url = f"{BASE_URL}{pago_parafiscal_a.pk}/pagar/"
        r1 = client_a.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY="clave-fail")
        assert r1.status_code == 400
        r2 = client_a.post(
            url,
            {"metodo_pago": str(metodo_pago_a.pk), "caja": str(caja_usd_a.pk)},
            format="json",
            HTTP_IDEMPOTENCY_KEY="clave-fail",
        )
        assert r2.status_code == 200, r2.data


# ─────────────────────────────────────────────
# Service directo: validaciones extra
# ─────────────────────────────────────────────


class TestServiceDirecto:
    def test_pagar_caja_de_otra_empresa_falla_en_service(
        self, empresa_b, moneda_usd, pago_parafiscal_a, metodo_pago_a, user_a
    ):
        """Defensa en profundidad: aunque una vista no filtre, el service exige tenant."""
        from apps.fiscal.services_parafiscales import (
            PagoParafiscalError,
            pagar_contribucion_parafiscal,
        )

        caja_ajena = Caja.objects.create(
            empresa=empresa_b, nombre="Caja ajena", moneda=moneda_usd
        )
        with pytest.raises(PagoParafiscalError):
            pagar_contribucion_parafiscal(
                pago_parafiscal=pago_parafiscal_a,
                usuario=user_a,
                metodo_pago=metodo_pago_a,
                caja_virtual=caja_ajena,
            )

    def test_pagar_cuenta_de_otra_empresa_falla_en_service(
        self, empresa_b, moneda_usd, pago_parafiscal_a, metodo_pago_a, user_a
    ):
        from apps.fiscal.services_parafiscales import (
            PagoParafiscalError,
            pagar_contribucion_parafiscal,
        )

        cuenta_ajena = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_b,
            nombre_banco="Banco B",
            numero_cuenta="0102-9999-0000000009",
            tipo_cuenta="CORRIENTE",
            id_moneda=moneda_usd,
        )
        with pytest.raises(PagoParafiscalError):
            pagar_contribucion_parafiscal(
                pago_parafiscal=pago_parafiscal_a,
                usuario=user_a,
                metodo_pago=metodo_pago_a,
                cuenta_bancaria=cuenta_ajena,
            )

    def test_pagar_metodo_inactivo_falla_en_service(
        self, empresa_a, pago_parafiscal_a, caja_usd_a, user_a
    ):
        from apps.fiscal.services_parafiscales import (
            PagoParafiscalError,
            pagar_contribucion_parafiscal,
        )

        metodo_inactivo = MetodoPago.objects.create(
            empresa=empresa_a, nombre_metodo="Viejo", tipo_metodo="EFECTIVO", activo=False
        )
        with pytest.raises(PagoParafiscalError):
            pagar_contribucion_parafiscal(
                pago_parafiscal=pago_parafiscal_a,
                usuario=user_a,
                metodo_pago=metodo_inactivo,
                caja_virtual=caja_usd_a,
            )

    def test_cuenta_moneda_distinta_falla_en_service(
        self, empresa_a, pago_parafiscal_a, metodo_pago_a, user_a
    ):
        from apps.finanzas.models import Moneda
        from apps.fiscal.services_parafiscales import (
            PagoParafiscalError,
            pagar_contribucion_parafiscal,
        )

        ves = Moneda.objects.create(nombre="Bolívar", codigo_iso="VES", simbolo="Bs", tipo_moneda="fiat")
        cuenta_ves = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_a,
            nombre_banco="Banco VES",
            numero_cuenta="0102-1111-0000000002",
            tipo_cuenta="CORRIENTE",
            id_moneda=ves,
        )
        with pytest.raises(PagoParafiscalError):
            pagar_contribucion_parafiscal(
                pago_parafiscal=pago_parafiscal_a,
                usuario=user_a,
                metodo_pago=metodo_pago_a,
                cuenta_bancaria=cuenta_ves,
            )

    def test_cuenta_inactiva_falla_en_service(
        self, empresa_a, moneda_usd, pago_parafiscal_a, metodo_pago_a, user_a
    ):
        from apps.fiscal.services_parafiscales import (
            PagoParafiscalError,
            pagar_contribucion_parafiscal,
        )

        cuenta_inactiva = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_a,
            nombre_banco="Banco Cerrado",
            numero_cuenta="0102-2222-0000000003",
            tipo_cuenta="CORRIENTE",
            id_moneda=moneda_usd,
            activo=False,
        )
        with pytest.raises(PagoParafiscalError):
            pagar_contribucion_parafiscal(
                pago_parafiscal=pago_parafiscal_a,
                usuario=user_a,
                metodo_pago=metodo_pago_a,
                cuenta_bancaria=cuenta_inactiva,
            )

    def test_metodo_privado_de_otro_tenant_falla_en_service(
        self, empresa_b, pago_parafiscal_a, caja_usd_a, user_a
    ):
        """Defensa en profundidad: aunque la vista no filtre, el service exige tenant."""
        from apps.fiscal.services_parafiscales import (
            PagoParafiscalError,
            pagar_contribucion_parafiscal,
        )

        metodo_b = MetodoPago.objects.create(
            empresa=empresa_b, nombre_metodo="Privado B", tipo_metodo="EFECTIVO"
        )
        with pytest.raises(PagoParafiscalError):
            pagar_contribucion_parafiscal(
                pago_parafiscal=pago_parafiscal_a,
                usuario=user_a,
                metodo_pago=metodo_b,
                caja_virtual=caja_usd_a,
            )

    def test_contribucion_ajena_creada_por_fuera_falla_al_pagar(
        self, empresa_a, contribucion_b, moneda_usd, caja_usd_a, metodo_pago_a, user_a
    ):
        """Pago._validar_documento (ValueError) se traduce a PagoParafiscalError."""
        from apps.fiscal.services_parafiscales import (
            PagoParafiscalError,
            pagar_contribucion_parafiscal,
        )

        # Registro inconsistente creado por fuera de la API (sin serializer):
        # la contribución pertenece a la empresa B.
        declarado = PagoContribucionParafiscal.objects.create(
            id_empresa=empresa_a,
            contribucion=contribucion_b,
            periodo_año=2026,
            periodo_mes=2,
            monto=Decimal("50.00"),
            id_moneda=moneda_usd,
        )
        with pytest.raises(PagoParafiscalError):
            pagar_contribucion_parafiscal(
                pago_parafiscal=declarado,
                usuario=user_a,
                metodo_pago=metodo_pago_a,
                caja_virtual=caja_usd_a,
            )
        declarado.refresh_from_db()
        assert declarado.estado == "pendiente"
        caja_usd_a.refresh_from_db()
        assert caja_usd_a.saldo_actual == Decimal("5000.00")

    def test_monto_no_positivo_falla_en_service(
        self, empresa_a, contribucion_global, moneda_usd, caja_usd_a, metodo_pago_a, user_a
    ):
        from apps.fiscal.services_parafiscales import (
            PagoParafiscalError,
            pagar_contribucion_parafiscal,
        )

        declarado = PagoContribucionParafiscal.objects.create(
            id_empresa=empresa_a,
            contribucion=contribucion_global,
            periodo_año=2026,
            periodo_mes=1,
            monto=Decimal("0.00"),  # creado por fuera de la API (sin serializer)
            id_moneda=moneda_usd,
        )
        with pytest.raises(PagoParafiscalError):
            pagar_contribucion_parafiscal(
                pago_parafiscal=declarado,
                usuario=user_a,
                metodo_pago=metodo_pago_a,
                caja_virtual=caja_usd_a,
            )


# ─────────────────────────────────────────────
# Serializer directo y carrera de doble declaración
# ─────────────────────────────────────────────


class TestSerializerYCarrera:
    def test_serializer_rechaza_contribucion_ajena(self, empresa_a, contribucion_b, moneda_usd):
        """Sin el scoping del ViewSet, validate() también cierra la puerta."""
        from apps.fiscal.serializers_parafiscales import PagoContribucionParafiscalSerializer

        ser = PagoContribucionParafiscalSerializer(
            data={
                "id_empresa": str(empresa_a.id_empresa),
                "contribucion": contribucion_b.pk,
                "periodo_año": 2026,
                "periodo_mes": 5,
                "monto": "10.00",
                "id_moneda": str(moneda_usd.id_moneda),
            }
        )
        assert not ser.is_valid()
        assert "contribucion" in ser.errors

    def test_serializer_rechaza_proceso_nomina_ajeno(
        self, empresa_a, empresa_b, contribucion_a, moneda_usd
    ):
        from apps.nomina.models import PeriodoNomina, ProcesoNomina
        from apps.fiscal.serializers_parafiscales import PagoContribucionParafiscalSerializer

        periodo_b = PeriodoNomina.objects.create(
            id_empresa=empresa_b,
            nombre_periodo="P-B",
            fecha_inicio=_today(),
            fecha_fin=_today(),
            fecha_pago=_today(),
            tipo_periodo="MENSUAL",
        )
        proceso_b = ProcesoNomina.objects.create(
            id_empresa=empresa_b,
            id_periodo_nomina=periodo_b,
            numero_proceso="NOM-B-1",
            fecha_proceso=timezone.now(),
        )
        ser = PagoContribucionParafiscalSerializer(
            data={
                "id_empresa": str(empresa_a.id_empresa),
                "contribucion": contribucion_a.pk,
                "periodo_año": 2026,
                "periodo_mes": 5,
                "monto": "10.00",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_proceso_nomina": str(proceso_b.pk),
            }
        )
        assert not ser.is_valid()
        assert "id_proceso_nomina" in ser.errors

    def test_carrera_de_doble_declaracion_retorna_400(
        self, empresa_a, contribucion_a, moneda_usd, pago_parafiscal_a
    ):
        """
        Simula la carrera que validate() no alcanza a ver (dos POST simultáneos):
        el constraint condicional de BD dispara IntegrityError y el ViewSet lo
        traduce a un 400 de negocio (no un 500).
        """
        from rest_framework.exceptions import ValidationError as DRFValidationError

        from apps.fiscal.views_parafiscales import PagoContribucionParafiscalViewSet

        class _SerializerGanadoPorLaCarrera:
            def save(self, **kwargs):
                # El "otro" request ya insertó pago_parafiscal_a: este INSERT
                # golpea uniq_pago_parafiscal_periodo_no_anulado de verdad.
                return PagoContribucionParafiscal.objects.create(
                    id_empresa=empresa_a,
                    contribucion=contribucion_a,
                    periodo_año=2026,
                    periodo_mes=5,
                    monto=Decimal("1.00"),
                    id_moneda=moneda_usd,
                )

        viewset = PagoContribucionParafiscalViewSet()
        with pytest.raises(DRFValidationError) as exc_info:
            viewset.perform_create(_SerializerGanadoPorLaCarrera())
        assert "doble pago" in str(exc_info.value)
        # Solo la fila original sobrevive
        assert PagoContribucionParafiscal.objects.count() == 1


# ─────────────────────────────────────────────
# Tool MCP: fiscal_parafiscales_pendientes
# ─────────────────────────────────────────────


class TestMCPParafiscalesPendientes:
    @pytest.fixture
    def token_a(self, empresa_a):
        from apps.core.models import CapabilityToken

        return CapabilityToken.objects.create(
            empresa=empresa_a,
            nombre="tok-fiscal",
            scopes=["fiscal:read"],
            activo=True,
        )

    def test_lista_solo_pendientes(
        self, token_a, empresa_a, contribucion_a, contribucion_global, moneda_usd, pago_parafiscal_a
    ):
        from apps.fiscal.mcp import fiscal_parafiscales_pendientes

        # Uno pagado (cerrado) que NO debe aparecer
        PagoContribucionParafiscal.objects.create(
            id_empresa=empresa_a,
            contribucion=contribucion_global,
            periodo_año=2026,
            periodo_mes=4,
            monto=Decimal("80.00"),
            id_moneda=moneda_usd,
            estado="pagado",
        )

        resultado = fiscal_parafiscales_pendientes(str(token_a.token), str(empresa_a.id_empresa))
        assert len(resultado) == 1
        fila = resultado[0]
        assert fila["id_pago_parafiscal"] == str(pago_parafiscal_a.pk)
        assert fila["contribucion_codigo"] == "IVSS-A"
        assert fila["periodo"] == "2026-05"
        assert fila["estado"] == "pendiente"
        # R-CODE-4: el monto viaja como Decimal, nunca float
        assert isinstance(fila["monto"], Decimal)
        assert fila["monto"] == Decimal("1234.56")

    def test_tenant_distinto_lanza_permission_error(self, token_a, empresa_b):
        from apps.fiscal.mcp import fiscal_parafiscales_pendientes

        with pytest.raises(PermissionError):
            fiscal_parafiscales_pendientes(str(token_a.token), str(empresa_b.id_empresa))

    def test_scope_insuficiente_lanza_permission_error(self, empresa_a):
        from apps.core.models import CapabilityToken
        from apps.fiscal.mcp import fiscal_parafiscales_pendientes

        token = CapabilityToken.objects.create(
            empresa=empresa_a, nombre="tok-crm", scopes=["crm:read"], activo=True
        )
        with pytest.raises(PermissionError):
            fiscal_parafiscales_pendientes(str(token.token), str(empresa_a.id_empresa))
