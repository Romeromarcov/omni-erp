"""
Backfill de cobertura — apps/cxc/api/acuerdos.py + apps/cxc/config.py
(plan "Cero Dudas", COV/cxc).

Cubre por la API real (`/api/cobranza/acuerdos/`):
- perform_create: empresa derivada del usuario (H-SEC-12), generación de cuotas
  (semanal con ajuste de redondeo) y PermissionDenied si el usuario no tiene empresa.
- registrar-pago: cuota inexistente (404), cuota ya pagada (400), moneda/método
  inexistente (400 con código), pago total (cuota→pagado, acuerdo→cumplido),
  pago parcial, fallback de tasa=1 sin TasaCambio (M-BUG-9) y asiento contable
  obligatorio fallido → 422 + rollback (M-BUG-10 / R-CODE-11).
- vencimientos-proximos con filtro de días.
- perform_destroy → soft delete (deleted_at) y aislamiento multi-tenant A/B.

Y para CxcConfig (config.py): defaults seguros, lectura desde ParametroSistema,
_to_bool, fallback de max_plazo_dias y to_dict().
"""
import datetime
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.cxc.config import CxcConfig, _get_param, _to_bool
from apps.cxc.models import AcuerdoPago
from apps.finanzas.models import MetodoPago, Moneda, Pago

pytestmark = pytest.mark.django_db

URL = "/api/cobranza/acuerdos/"


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
def metodo_a(empresa_a, moneda_usd):
    metodo = MetodoPago.objects.create(
        nombre_metodo="Transferencia A", tipo_metodo="ELECTRONICO", empresa=empresa_a
    )
    metodo.monedas.add(moneda_usd)
    return metodo


def _payload_acuerdo(**overrides):
    base = {
        "cliente_id": "CLI-001",
        "cliente_nombre": "Cliente Uno",
        "monto_total": "300.0000",
        "periodicidad": "semanal",
        "plazo_total_dias": 21,
        "fecha_inicio": "2026-06-10",
        "moneda_codigo": "USD",
    }
    base.update(overrides)
    return base


@pytest.fixture
def acuerdo_a(client_a):
    resp = client_a.post(URL, _payload_acuerdo(), format="json")
    assert resp.status_code == 201, resp.content
    return AcuerdoPago.objects.get()


# ── perform_create ────────────────────────────────────────────────────────────

class TestCrearAcuerdo:
    def test_crea_acuerdo_con_cuotas_semanales(self, client_a, empresa_a):
        resp = client_a.post(URL, _payload_acuerdo(), format="json")
        assert resp.status_code == 201, resp.content
        acuerdo = AcuerdoPago.objects.get()
        # H-SEC-12: la empresa sale del usuario, no del payload
        assert acuerdo.empresa == empresa_a
        cuotas = list(acuerdo.cuotas.order_by("numero_cuota"))
        assert len(cuotas) == 3  # 21 días / semanal
        assert sum(c.monto for c in cuotas) == Decimal("300.0000")
        assert cuotas[0].monto == Decimal("100.0000")
        # la primera cuota vence el mismo día de inicio (n=0 semanas)
        assert cuotas[0].fecha_vencimiento == datetime.date(2026, 6, 10)
        assert cuotas[2].fecha_vencimiento == datetime.date(2026, 6, 24)
        assert all(c.estado == "pendiente" for c in cuotas)

    def test_usuario_sin_empresa_403(self, db):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(
            username="cxc_sin_empresa", password="x", email="cxc@x.com", is_active=True
        )
        client = APIClient()
        client.force_authenticate(user=user)
        resp = client.post(URL, _payload_acuerdo(), format="json")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "El usuario no tiene empresa asignada."
        assert AcuerdoPago.objects.count() == 0

    def test_list_aislado_por_empresa(self, client_a, client_b, acuerdo_a):
        ids_a = {a["id"] for a in client_a.get(URL).json()["results"]}
        assert str(acuerdo_a.id) in ids_a
        ids_b = {a["id"] for a in client_b.get(URL).json()["results"]}
        assert str(acuerdo_a.id) not in ids_b

    def test_destroy_es_soft_delete(self, client_a, acuerdo_a):
        resp = client_a.delete(f"{URL}{acuerdo_a.id}/")
        assert resp.status_code == 204
        acuerdo_a.refresh_from_db()
        assert acuerdo_a.deleted_at is not None
        # ya no aparece en el list (filtro deleted_at__isnull=True)
        assert client_a.get(URL).json()["count"] == 0

    def test_sin_auth_401(self):
        assert APIClient().get(URL).status_code == 401


# ── registrar-pago ────────────────────────────────────────────────────────────

class TestRegistrarPago:
    def _pagar(self, client, acuerdo, cuota_id, monto, moneda, metodo, **extra):
        payload = {
            "cuota_id": str(cuota_id),
            "monto": str(monto),
            "moneda_id": str(moneda.id_moneda),
            "metodo_pago_id": str(metodo.id_metodo_pago),
        }
        payload.update(extra)
        return client.post(f"{URL}{acuerdo.id}/registrar-pago/", payload, format="json")

    def test_cuota_inexistente_404(self, client_a, acuerdo_a, moneda_usd, metodo_a):
        import uuid

        resp = self._pagar(client_a, acuerdo_a, uuid.uuid4(), "100.0000", moneda_usd, metodo_a)
        assert resp.status_code == 404
        assert resp.json() == {"error": "Cuota no encontrada en este acuerdo"}

    def test_moneda_inexistente_400(self, client_a, acuerdo_a, moneda_usd, metodo_a):
        import uuid

        cuota = acuerdo_a.cuotas.first()
        resp = client_a.post(
            f"{URL}{acuerdo_a.id}/registrar-pago/",
            {
                "cuota_id": str(cuota.id),
                "monto": "100.0000",
                "moneda_id": str(uuid.uuid4()),
                "metodo_pago_id": str(metodo_a.id_metodo_pago),
            },
            format="json",
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "moneda_no_encontrada"

    def test_metodo_pago_inexistente_400(self, client_a, acuerdo_a, moneda_usd):
        import uuid

        cuota = acuerdo_a.cuotas.first()
        resp = client_a.post(
            f"{URL}{acuerdo_a.id}/registrar-pago/",
            {
                "cuota_id": str(cuota.id),
                "monto": "100.0000",
                "moneda_id": str(moneda_usd.id_moneda),
                "metodo_pago_id": str(uuid.uuid4()),
            },
            format="json",
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "metodo_pago_no_encontrado"

    def test_pago_total_marca_cuota_pagada(self, client_a, acuerdo_a, moneda_usd, metodo_a):
        cuota = acuerdo_a.cuotas.order_by("numero_cuota").first()
        resp = self._pagar(
            client_a, acuerdo_a, cuota.id, "100.0000", moneda_usd, metodo_a,
            referencia="REF-CXC-1",
        )
        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert body["estado"] == "pagado"
        assert Decimal(body["monto_pagado"]) == Decimal("100.0000")
        cuota.refresh_from_db()
        assert cuota.estado == "pagado"
        pago = Pago.objects.get()
        assert pago.monto == Decimal("100.0000")
        # moneda del pago == moneda base → no se busca tasa, queda 1
        assert pago.tasa == Decimal("1.0000")
        assert pago.referencia == "REF-CXC-1"
        # Quedan 2 cuotas pendientes → el acuerdo sigue vigente
        acuerdo_a.refresh_from_db()
        assert acuerdo_a.estado == "vigente"

    def test_pago_parcial_marca_parcial(self, client_a, acuerdo_a, moneda_usd, metodo_a):
        cuota = acuerdo_a.cuotas.order_by("numero_cuota").first()
        resp = self._pagar(client_a, acuerdo_a, cuota.id, "40.0000", moneda_usd, metodo_a)
        assert resp.status_code == 200, resp.content
        cuota.refresh_from_db()
        assert cuota.estado == "parcial"
        assert cuota.monto_pagado == Decimal("40.0000")

    def test_cuota_ya_pagada_400(self, client_a, acuerdo_a, moneda_usd, metodo_a):
        cuota = acuerdo_a.cuotas.first()
        assert self._pagar(client_a, acuerdo_a, cuota.id, "100.0000", moneda_usd, metodo_a).status_code == 200
        resp = self._pagar(client_a, acuerdo_a, cuota.id, "100.0000", moneda_usd, metodo_a)
        assert resp.status_code == 400
        assert resp.json() == {"error": "Esta cuota ya está pagada"}

    def test_todas_pagadas_completa_el_acuerdo(self, client_a, moneda_usd, metodo_a):
        resp = client_a.post(URL, _payload_acuerdo(periodicidad="unico"), format="json")
        assert resp.status_code == 201
        acuerdo = AcuerdoPago.objects.get()
        cuota = acuerdo.cuotas.get()  # pago único → 1 cuota
        assert cuota.monto == Decimal("300.0000")
        resp = self._pagar(client_a, acuerdo, cuota.id, "300.0000", moneda_usd, metodo_a)
        assert resp.status_code == 200, resp.content
        acuerdo.refresh_from_db()
        assert acuerdo.estado == "cumplido"

    def test_pago_misma_moneda_acuerdo_sin_tasa_base_usa_fallback_1(self, client_a, metodo_a):
        """M-BUG-9: si la moneda del pago coincide con la del acuerdo pero no hay
        TasaCambio moneda→base de la empresa, la tasa del Pago cae a 1 (fallback
        conservador) sin bloquear el pago. (BUG-A2: si la moneda difiere de la del
        acuerdo y no hay tasa, el pago se RECHAZA — ver test_cxc_acuerdos_p04.)"""
        ves = Moneda.objects.create(
            nombre="Bolívar", codigo_iso="VES", simbolo="Bs",
            tipo_moneda="fiat", es_generica=True,
        )
        resp = client_a.post(URL, _payload_acuerdo(moneda_codigo="VES"), format="json")
        assert resp.status_code == 201, resp.content
        acuerdo = AcuerdoPago.objects.get()
        cuota = acuerdo.cuotas.first()
        resp = self._pagar(client_a, acuerdo, cuota.id, "100.0000", ves, metodo_a)
        assert resp.status_code == 200, resp.content
        pago = Pago.objects.get()
        assert pago.id_moneda == ves
        assert pago.tasa == Decimal("1.0000")

    def test_moneda_distinta_con_tasa_usa_la_tasa(self, client_a, acuerdo_a, metodo_a, moneda_usd):
        from apps.finanzas.models import TasaCambio

        ves = Moneda.objects.create(
            nombre="Bolívar", codigo_iso="VES", simbolo="Bs",
            tipo_moneda="fiat", es_generica=True,
        )
        TasaCambio.objects.create(
            id_empresa=None, id_moneda_origen=ves, id_moneda_destino=moneda_usd,
            tipo_tasa="OFICIAL_BCV", valor_tasa=Decimal("0.02740000"),
            fecha_tasa=timezone.now().date(),
        )
        cuota = acuerdo_a.cuotas.first()
        resp = self._pagar(client_a, acuerdo_a, cuota.id, "100.0000", ves, metodo_a)
        assert resp.status_code == 200, resp.content
        pago = Pago.objects.get()
        assert pago.tasa == Decimal("0.0274")

    def test_asiento_obligatorio_falla_422_y_rollback(
        self, client_a, empresa_a, acuerdo_a, moneda_usd, metodo_a
    ):
        """R-CODE-11 / M-BUG-10: con contabilidad activa y sin MapeoContable,
        el pago NO debe persistir (rollback total) y responde 422."""
        empresa_a.contabilidad_activa = True
        empresa_a.save(update_fields=["contabilidad_activa"])
        cuota = acuerdo_a.cuotas.first()
        resp = self._pagar(client_a, acuerdo_a, cuota.id, "100.0000", moneda_usd, metodo_a)
        assert resp.status_code == 422, resp.content
        assert resp.json()["code"] == "asiento_contable_requerido"
        # rollback: ni pago ni cuota actualizada
        assert Pago.objects.count() == 0
        cuota.refresh_from_db()
        assert cuota.estado == "pendiente"
        assert cuota.monto_pagado == Decimal("0.0000")


# ── vencimientos-proximos ─────────────────────────────────────────────────────

class TestVencimientosProximos:
    def test_filtra_por_dias(self, client_a):
        hoy = datetime.date.today()
        resp = client_a.post(
            URL,
            _payload_acuerdo(
                periodicidad="unico",
                fecha_inicio=(hoy + datetime.timedelta(days=3)).isoformat(),
            ),
            format="json",
        )
        assert resp.status_code == 201
        # Vence en 3 días → entra con dias=7, no con dias=1
        resp7 = client_a.get(f"{URL}vencimientos-proximos/", {"dias": 7})
        assert resp7.status_code == 200
        assert len(resp7.json()) == 1
        assert Decimal(resp7.json()[0]["monto"]) == Decimal("300.0000")
        resp1 = client_a.get(f"{URL}vencimientos-proximos/", {"dias": 1})
        assert resp1.json() == []

    def test_no_ve_cuotas_de_otra_empresa(self, client_b, client_a):
        hoy = datetime.date.today()
        client_a.post(
            URL,
            _payload_acuerdo(periodicidad="unico", fecha_inicio=hoy.isoformat()),
            format="json",
        )
        resp = client_b.get(f"{URL}vencimientos-proximos/")
        assert resp.json() == []


# ── CxcConfig (apps/cxc/config.py) ────────────────────────────────────────────

def _param(empresa, codigo, valor, activo=True):
    from apps.configuracion_motor.models import ParametroSistema

    return ParametroSistema.objects.create(
        id_empresa=empresa,
        nombre_parametro=codigo,
        codigo_parametro=codigo,
        valor_parametro=valor,
        activo=activo,
    )


class TestCxcConfig:
    def test_defaults_sin_parametros(self, empresa_a):
        cfg = CxcConfig.para_empresa(empresa_a)
        assert cfg.datasource == "native"
        assert cfg.enabled is True
        assert cfg.agente_ia_enabled is False
        assert cfg.fraccionamiento_enabled is False
        assert cfg.max_plazo_dias == 365
        assert cfg.moneda_display == "USD"
        assert cfg.canales == ["whatsapp", "email", "llamada", "visita", "carta"]

    def test_lee_parametros_del_tenant(self, empresa_a):
        _param(empresa_a, "cxc.datasource", "odoo")
        _param(empresa_a, "cxc.enabled", "false")
        _param(empresa_a, "cxc.agente_ia.enabled", "TRUE")
        _param(empresa_a, "cxc.fraccionamiento.enabled", "si")
        _param(empresa_a, "cxc.acuerdos.max_plazo_dias", " 180 ")
        _param(empresa_a, "cxc.tasas.moneda_display", "VES")
        _param(empresa_a, "cxc.canales", "whatsapp, email , ,llamada")
        cfg = CxcConfig.para_empresa(empresa_a)
        assert cfg.datasource == "odoo"
        assert cfg.enabled is False
        assert cfg.agente_ia_enabled is True
        assert cfg.fraccionamiento_enabled is True
        assert cfg.max_plazo_dias == 180
        assert cfg.moneda_display == "VES"
        assert cfg.canales == ["whatsapp", "email", "llamada"]

    def test_parametro_inactivo_usa_default(self, empresa_a):
        _param(empresa_a, "cxc.datasource", "odoo", activo=False)
        assert CxcConfig.para_empresa(empresa_a).datasource == "native"

    def test_config_aislada_por_empresa(self, empresa_a, empresa_b):
        _param(empresa_b, "cxc.datasource", "odoo")
        assert CxcConfig.para_empresa(empresa_a).datasource == "native"
        assert CxcConfig.para_empresa(empresa_b).datasource == "odoo"

    def test_max_plazo_vacio_usa_365(self, empresa_a):
        # valor en blanco → strip() == "" → fallback "365"
        _param(empresa_a, "cxc.acuerdos.max_plazo_dias", "   ")
        assert CxcConfig.para_empresa(empresa_a).max_plazo_dias == 365

    def test_get_param_directo(self, empresa_a):
        assert _get_param(empresa_a, "no.existe", "def") == "def"
        _param(empresa_a, "cxc.x", "  valor  ")
        assert _get_param(empresa_a, "cxc.x") == "valor"

    @pytest.mark.parametrize("val,esperado", [
        ("true", True), ("1", True), ("yes", True), ("si", True), ("sí", True),
        ("TRUE", True), ("false", False), ("0", False), ("", False), ("nope", False),
    ])
    def test_to_bool(self, val, esperado):
        assert _to_bool(val) is esperado

    def test_to_dict(self, empresa_a):
        d = CxcConfig.para_empresa(empresa_a).to_dict()
        assert d == {
            "datasource": "native",
            "enabled": True,
            "agente_ia_enabled": False,
            "fraccionamiento_enabled": False,
            "max_plazo_dias": 365,
            "moneda_display": "USD",
            "canales": ["whatsapp", "email", "llamada", "visita", "carta"],
        }
