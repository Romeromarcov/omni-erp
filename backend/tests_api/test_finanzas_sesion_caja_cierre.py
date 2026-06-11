"""
Integración end-to-end del flujo de sesiones/cierres de caja (fix de 3
endpoints rotos, hallazgos del PR #73 — preexistentes):

1. ``POST /api/finanzas/cajas/{id}/cierre/`` — llamaba ``realizar_cierre``
   sobre ``Caja`` (virtual), que no definía ese método → siempre 400.
   Decisión: implementar el cierre para caja virtual reutilizando el corte
   persistente del PR #73 (helper común ``services.realizar_cierre_caja``);
   además reconcilia ``saldo_actual``.
2. ``POST /api/finanzas/sesiones-caja/{id}/cerrar/`` — la vista llamaba
   ``sesion.cerrar_sesion(saldos_reales=..., usuario=..., hasta=...)`` pero la
   firma del modelo solo aceptaba ``notas_cierre`` → TypeError 500. Ahora el
   modelo cierra las cajas de la sesión (física y/o virtuales, con saldos
   reales) y marca la sesión CERRADA, atómico.
3. ``POST /api/finanzas/cajas-fisicas/{id}/cerrar-sesion/`` (y su simétrico
   ``abrir-sesion/``) — el frontend los llama y las rutas no existían en
   ``CajaFisicaViewSet``. Se agregan delegando en la sesión activa.

Cubre por API: cierre persiste corte por caja + estado de sesión; segundo
cierre solo cuenta lo nuevo; atomicidad (caja ajena → rollback completo);
validaciones de entrada; aislamiento multi-tenant (R-CODE-1 → 404).
"""
import datetime
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.finanzas.models import Caja, MovimientoCajaBanco, SesionCajaFisica

pytestmark = pytest.mark.django_db

URL_CIERRE_VIRTUAL = "/api/finanzas/cajas/{}/cierre/"
URL_ABRIR_SESION = "/api/finanzas/cajas-fisicas/{}/abrir-sesion/"
URL_CERRAR_SESION = "/api/finanzas/cajas-fisicas/{}/cerrar-sesion/"
URL_SESION_CERRAR = "/api/finanzas/sesiones-caja/{}/cerrar/"

DIA = datetime.date(2026, 6, 10)


def _mov(*, caja_virtual=None, caja_fisica=None, user, hora, tipo, monto, moneda, fecha=DIA):
    caja = caja_virtual or caja_fisica
    return MovimientoCajaBanco.objects.create(
        id_empresa=caja.empresa,
        fecha_movimiento=fecha,
        hora_movimiento=hora,
        tipo_movimiento=tipo,
        monto=Decimal(monto),
        id_moneda=moneda,
        concepto="mov sesion e2e",
        id_caja=caja_virtual,
        id_caja_fisica=caja_fisica,
        saldo_anterior=Decimal("0.00"),
        saldo_nuevo=Decimal("0.00"),
        id_usuario_registro=user,
    )


@pytest.fixture
def client_a(user_a):
    client = APIClient()
    client.force_authenticate(user=user_a)
    return client


@pytest.fixture
def caja_virtual_a(empresa_a, moneda_usd, caja_fisica_a):
    """Caja virtual de Empresa A asociada a la caja física de la sesión."""
    return Caja.objects.create(
        empresa=empresa_a,
        nombre="Registradora Virtual Test",
        moneda=moneda_usd,
        caja_fisica=caja_fisica_a,
        saldo_actual=Decimal("0.00"),
    )


class TestCierreCajaVirtual:
    """Bug 1: POST /finanzas/cajas/{id}/cierre/ siempre devolvía 400."""

    def test_flujo_dos_cierres_y_saldo_reconciliado(self, client_a, caja_virtual_a, user_a, moneda_usd):
        caja = caja_virtual_a
        _mov(caja_virtual=caja, user=user_a, hora=datetime.time(9, 0), tipo="INGRESO", monto="100.00", moneda=moneda_usd)
        _mov(caja_virtual=caja, user=user_a, hora=datetime.time(10, 0), tipo="EGRESO", monto="30.00", moneda=moneda_usd)

        resp = client_a.post(
            URL_CIERRE_VIRTUAL.format(caja.id_caja),
            {"saldo_real": "70.00", "hasta": "2026-06-10T12:00:00"},
            format="json",
        )
        assert resp.status_code == 200, resp.data
        assert Decimal(str(resp.data["ingresos"])) == Decimal("100.00")
        assert Decimal(str(resp.data["egresos"])) == Decimal("30.00")
        assert Decimal(str(resp.data["descuadre"])) == Decimal("0.00")
        cierre1 = MovimientoCajaBanco.objects.get(id_movimiento=resp.data["movimiento_cierre_id"])
        assert cierre1.tipo_movimiento == "CIERRE"
        assert cierre1.id_caja_id == caja.id_caja
        assert cierre1.saldo_anterior == Decimal("0.00")
        assert cierre1.saldo_nuevo == Decimal("70.00")
        caja.refresh_from_db()
        assert caja.saldo_actual == Decimal("70.00")

        # Lo nuevo tras el corte: ingreso 25, transferencia entrada 10, egreso 5
        _mov(caja_virtual=caja, user=user_a, hora=datetime.time(14, 0), tipo="INGRESO", monto="25.00", moneda=moneda_usd)
        _mov(caja_virtual=caja, user=user_a, hora=datetime.time(15, 0), tipo="TRANSFERENCIA_ENTRADA", monto="10.00", moneda=moneda_usd)
        _mov(caja_virtual=caja, user=user_a, hora=datetime.time(16, 0), tipo="EGRESO", monto="5.00", moneda=moneda_usd)

        resp2 = client_a.post(
            URL_CIERRE_VIRTUAL.format(caja.id_caja),
            {"saldo_real": "100.00", "hasta": "2026-06-10T18:00:00"},
            format="json",
        )
        assert resp2.status_code == 200, resp2.data
        # Solo cuenta lo nuevo, incluidas transferencias internas
        assert Decimal(str(resp2.data["ingresos"])) == Decimal("35.00")
        assert Decimal(str(resp2.data["egresos"])) == Decimal("5.00")
        assert Decimal(str(resp2.data["saldo_teorico"])) == Decimal("100.00")
        assert Decimal(str(resp2.data["descuadre"])) == Decimal("0.00")
        cierre2 = MovimientoCajaBanco.objects.get(id_movimiento=resp2.data["movimiento_cierre_id"])
        assert cierre2.saldo_anterior == Decimal("70.00")
        assert cierre2.saldo_nuevo == Decimal("100.00")
        assert caja.movimientos.filter(tipo_movimiento="CIERRE").count() == 2

    def test_descuadre_crea_ajuste_y_reconcilia_saldo(self, client_a, caja_virtual_a, user_a, moneda_usd):
        caja = caja_virtual_a
        _mov(caja_virtual=caja, user=user_a, hora=datetime.time(9, 0), tipo="INGRESO", monto="100.00", moneda=moneda_usd)

        resp = client_a.post(
            URL_CIERRE_VIRTUAL.format(caja.id_caja),
            {"saldo_real": "80.00", "hasta": "2026-06-10T12:00:00"},
            format="json",
        )
        assert resp.status_code == 200, resp.data
        assert Decimal(str(resp.data["descuadre"])) == Decimal("-20.00")
        ajuste = MovimientoCajaBanco.objects.get(id_movimiento=resp.data["movimiento_ajuste_id"])
        assert ajuste.tipo_movimiento == "AJUSTE_NEGATIVO"
        assert ajuste.monto == Decimal("20.00")
        assert ajuste.id_caja_id == caja.id_caja
        assert (ajuste.fecha_movimiento, ajuste.hora_movimiento) == (DIA, datetime.time(12, 0))
        caja.refresh_from_db()
        assert caja.saldo_actual == Decimal("80.00")

        # El ajuste quedó dentro de la ventana cerrada: no se recuenta
        resp2 = client_a.post(
            URL_CIERRE_VIRTUAL.format(caja.id_caja),
            {"saldo_real": "80.00", "hasta": "2026-06-10T18:00:00"},
            format="json",
        )
        assert resp2.status_code == 200, resp2.data
        assert Decimal(str(resp2.data["ingresos"])) == Decimal("0.00")
        assert Decimal(str(resp2.data["egresos"])) == Decimal("0.00")
        assert Decimal(str(resp2.data["descuadre"])) == Decimal("0.00")

    def test_validaciones_de_entrada(self, client_a, caja_virtual_a):
        url = URL_CIERRE_VIRTUAL.format(caja_virtual_a.id_caja)
        assert client_a.post(url, {}, format="json").status_code == 400
        assert client_a.post(url, {"saldo_real": "no-numero"}, format="json").status_code == 400
        assert client_a.post(url, {"saldo_real": "10.00", "hasta": "fecha-mala"}, format="json").status_code == 400
        # Límite anterior al último cierre
        assert client_a.post(url, {"saldo_real": "0.00", "hasta": "2026-06-10T12:00:00"}, format="json").status_code == 200
        resp = client_a.post(url, {"saldo_real": "0.00", "hasta": "2026-06-10T08:00:00"}, format="json")
        assert resp.status_code == 400
        assert "anterior al último cierre" in resp.data["error"]

    def test_aislamiento_multi_tenant(self, caja_virtual_a, user_b):
        client_b = APIClient()
        client_b.force_authenticate(user=user_b)
        resp = client_b.post(
            URL_CIERRE_VIRTUAL.format(caja_virtual_a.id_caja), {"saldo_real": "0.00"}, format="json"
        )
        assert resp.status_code == 404
        assert not caja_virtual_a.movimientos.filter(tipo_movimiento="CIERRE").exists()


class TestSesionCajaFisicaPorCajaFisica:
    """Bug 3: rutas abrir-sesion/cerrar-sesion que el frontend llama sobre
    /finanzas/cajas-fisicas/{id}/ no existían."""

    def test_abrir_y_cerrar_sesion_con_cierres_por_caja(
        self, client_a, caja_fisica_a, caja_virtual_a, user_a, moneda_usd
    ):
        resp = client_a.post(URL_ABRIR_SESION.format(caja_fisica_a.id_caja_fisica), {}, format="json")
        assert resp.status_code == 200, resp.data
        assert resp.data["sesion"]["estado"] == "ABIERTA"
        id_sesion = resp.data["sesion"]["id_sesion"]

        _mov(caja_fisica=caja_fisica_a, user=user_a, hora=datetime.time(9, 0), tipo="INGRESO", monto="100.00", moneda=moneda_usd)
        _mov(caja_fisica=caja_fisica_a, user=user_a, hora=datetime.time(10, 0), tipo="EGRESO", monto="30.00", moneda=moneda_usd)
        _mov(caja_virtual=caja_virtual_a, user=user_a, hora=datetime.time(11, 0), tipo="INGRESO", monto="50.00", moneda=moneda_usd)

        resp = client_a.post(
            URL_CERRAR_SESION.format(caja_fisica_a.id_caja_fisica),
            {
                "notas_cierre": "cierre de turno",
                "saldos_reales": {
                    str(caja_fisica_a.id_caja_fisica): "70.00",
                    str(caja_virtual_a.id_caja): "50.00",
                },
                "hasta": "2026-06-10T12:00:00",
            },
            format="json",
        )
        assert resp.status_code == 200, resp.data
        assert resp.data["sesion"]["estado"] == "CERRADA"
        assert resp.data["sesion"]["fecha_cierre"] is not None

        # Cierres por caja persistidos
        cierres = resp.data["cierres"]
        assert set(cierres.keys()) == {str(caja_fisica_a.id_caja_fisica), str(caja_virtual_a.id_caja)}
        assert Decimal(str(cierres[str(caja_fisica_a.id_caja_fisica)]["saldo_teorico"])) == Decimal("70.00")
        assert Decimal(str(cierres[str(caja_virtual_a.id_caja)]["saldo_teorico"])) == Decimal("50.00")
        assert caja_fisica_a.movimientos.filter(tipo_movimiento="CIERRE").count() == 1
        assert caja_virtual_a.movimientos.filter(tipo_movimiento="CIERRE").count() == 1

        # Estado de sesión persistido
        sesion = SesionCajaFisica.objects.get(id_sesion=id_sesion)
        assert sesion.estado == "CERRADA"
        assert sesion.notas == "cierre de turno"
        assert sesion.fecha_cierre is not None

    def test_segundo_cierre_solo_cuenta_lo_nuevo(
        self, client_a, caja_fisica_a, user_a, moneda_usd
    ):
        # Primera sesión: ingreso 100 → cierre con 100
        client_a.post(URL_ABRIR_SESION.format(caja_fisica_a.id_caja_fisica), {}, format="json")
        _mov(caja_fisica=caja_fisica_a, user=user_a, hora=datetime.time(9, 0), tipo="INGRESO", monto="100.00", moneda=moneda_usd)
        resp = client_a.post(
            URL_CERRAR_SESION.format(caja_fisica_a.id_caja_fisica),
            {"saldos_reales": {str(caja_fisica_a.id_caja_fisica): "100.00"}, "hasta": "2026-06-10T12:00:00"},
            format="json",
        )
        assert resp.status_code == 200, resp.data

        # Segunda sesión: solo lo nuevo (25) sobre la base del corte (100)
        client_a.post(URL_ABRIR_SESION.format(caja_fisica_a.id_caja_fisica), {}, format="json")
        _mov(caja_fisica=caja_fisica_a, user=user_a, hora=datetime.time(14, 0), tipo="INGRESO", monto="25.00", moneda=moneda_usd)
        resp2 = client_a.post(
            URL_CERRAR_SESION.format(caja_fisica_a.id_caja_fisica),
            {"saldos_reales": {str(caja_fisica_a.id_caja_fisica): "125.00"}, "hasta": "2026-06-10T18:00:00"},
            format="json",
        )
        assert resp2.status_code == 200, resp2.data
        cierre = resp2.data["cierres"][str(caja_fisica_a.id_caja_fisica)]
        assert Decimal(str(cierre["ingresos"])) == Decimal("25.00")
        assert Decimal(str(cierre["saldo_teorico"])) == Decimal("125.00")
        assert Decimal(str(cierre["descuadre"])) == Decimal("0.00")
        assert caja_fisica_a.movimientos.filter(tipo_movimiento="CIERRE").count() == 2

    def test_cerrar_sin_sesion_abierta(self, client_a, caja_fisica_a):
        resp = client_a.post(URL_CERRAR_SESION.format(caja_fisica_a.id_caja_fisica), {}, format="json")
        assert resp.status_code == 400
        assert "sesión abierta" in resp.data["error"]

    def test_caja_ajena_a_la_sesion_rollback_atomico(
        self, client_a, caja_fisica_a, user_a, moneda_usd, empresa_a
    ):
        """Si una caja de saldos_reales no pertenece a la sesión, NADA se
        persiste (ni el cierre válido previo, ni el estado de la sesión)."""
        otra_caja = Caja.objects.create(
            empresa=empresa_a, nombre="Caja Suelta", moneda=moneda_usd, saldo_actual=Decimal("0.00")
        )
        client_a.post(URL_ABRIR_SESION.format(caja_fisica_a.id_caja_fisica), {}, format="json")
        _mov(caja_fisica=caja_fisica_a, user=user_a, hora=datetime.time(9, 0), tipo="INGRESO", monto="10.00", moneda=moneda_usd)
        resp = client_a.post(
            URL_CERRAR_SESION.format(caja_fisica_a.id_caja_fisica),
            {
                "saldos_reales": {
                    str(caja_fisica_a.id_caja_fisica): "10.00",
                    str(otra_caja.id_caja): "5.00",
                }
            },
            format="json",
        )
        assert resp.status_code == 400
        assert "no pertenece a esta sesión" in resp.data["error"]
        # Atomicidad: ni cierre parcial ni sesión cerrada
        assert not caja_fisica_a.movimientos.filter(tipo_movimiento="CIERRE").exists()
        assert SesionCajaFisica.objects.get(caja_fisica=caja_fisica_a).estado == "ABIERTA"

    def test_saldo_invalido_en_saldos_reales(self, client_a, caja_fisica_a):
        client_a.post(URL_ABRIR_SESION.format(caja_fisica_a.id_caja_fisica), {}, format="json")
        resp = client_a.post(
            URL_CERRAR_SESION.format(caja_fisica_a.id_caja_fisica),
            {"saldos_reales": {str(caja_fisica_a.id_caja_fisica): "no-numero"}},
            format="json",
        )
        assert resp.status_code == 400
        assert "no es un número válido" in resp.data["error"]

    def test_aislamiento_multi_tenant(self, client_a, caja_fisica_a, user_b):
        client_a.post(URL_ABRIR_SESION.format(caja_fisica_a.id_caja_fisica), {}, format="json")
        client_b = APIClient()
        client_b.force_authenticate(user=user_b)
        assert client_b.post(URL_ABRIR_SESION.format(caja_fisica_a.id_caja_fisica), {}, format="json").status_code == 404
        resp = client_b.post(
            URL_CERRAR_SESION.format(caja_fisica_a.id_caja_fisica),
            {"saldos_reales": {str(caja_fisica_a.id_caja_fisica): "0.00"}},
            format="json",
        )
        assert resp.status_code == 404
        assert SesionCajaFisica.objects.get(caja_fisica=caja_fisica_a).estado == "ABIERTA"

    def test_requiere_autenticacion(self, caja_fisica_a):
        client = APIClient()
        assert client.post(URL_ABRIR_SESION.format(caja_fisica_a.id_caja_fisica), {}, format="json").status_code in (401, 403)
        assert client.post(URL_CERRAR_SESION.format(caja_fisica_a.id_caja_fisica), {}, format="json").status_code in (401, 403)


class TestSesionCajaFisicaViewSetCerrar:
    """Bug 2: POST /finanzas/sesiones-caja/{id}/cerrar/ reventaba con
    TypeError 500 por firma incompatible del modelo."""

    def _abrir(self, caja_fisica, user):
        return SesionCajaFisica.abrir_sesion(caja_fisica=caja_fisica, usuario=user)

    def test_cerrar_persiste_cierres_y_estado(
        self, client_a, caja_fisica_a, caja_virtual_a, user_a, moneda_usd
    ):
        sesion = self._abrir(caja_fisica_a, user_a)
        _mov(caja_fisica=caja_fisica_a, user=user_a, hora=datetime.time(9, 0), tipo="INGRESO", monto="40.00", moneda=moneda_usd)
        _mov(caja_virtual=caja_virtual_a, user=user_a, hora=datetime.time(10, 0), tipo="INGRESO", monto="15.00", moneda=moneda_usd)

        resp = client_a.post(
            URL_SESION_CERRAR.format(sesion.id_sesion),
            {
                "saldos_reales": {
                    str(caja_fisica_a.id_caja_fisica): "40.00",
                    str(caja_virtual_a.id_caja): "15.00",
                },
                "hasta": "2026-06-10T12:00:00",
            },
            format="json",
        )
        assert resp.status_code == 200, resp.data
        assert resp.data["sesion"]["estado"] == "CERRADA"
        assert len(resp.data["cierres"]) == 2
        sesion.refresh_from_db()
        assert sesion.estado == "CERRADA"
        assert sesion.fecha_cierre is not None
        assert caja_fisica_a.movimientos.filter(tipo_movimiento="CIERRE").count() == 1
        assert caja_virtual_a.movimientos.filter(tipo_movimiento="CIERRE").count() == 1

    def test_cerrar_sesion_ya_cerrada(self, client_a, caja_fisica_a, user_a):
        sesion = self._abrir(caja_fisica_a, user_a)
        assert client_a.post(URL_SESION_CERRAR.format(sesion.id_sesion), {}, format="json").status_code == 200
        resp = client_a.post(URL_SESION_CERRAR.format(sesion.id_sesion), {}, format="json")
        assert resp.status_code == 400
        assert "ya está cerrada" in resp.data["error"]

    def test_saldos_reales_no_dict(self, client_a, caja_fisica_a, user_a):
        sesion = self._abrir(caja_fisica_a, user_a)
        resp = client_a.post(
            URL_SESION_CERRAR.format(sesion.id_sesion), {"saldos_reales": ["x"]}, format="json"
        )
        assert resp.status_code == 400

    def test_aislamiento_multi_tenant(self, caja_fisica_a, user_a, user_b):
        sesion = self._abrir(caja_fisica_a, user_a)
        client_b = APIClient()
        client_b.force_authenticate(user=user_b)
        resp = client_b.post(URL_SESION_CERRAR.format(sesion.id_sesion), {}, format="json")
        assert resp.status_code == 404
        sesion.refresh_from_db()
        assert sesion.estado == "ABIERTA"
