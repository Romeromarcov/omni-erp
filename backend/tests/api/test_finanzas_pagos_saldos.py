"""
P0-3 (auditoría integral 2026-06-10) — BUG-C2 y BUG-A1.

BUG-C2: los side-effects financieros de un Pago (TransaccionFinanciera +
MovimientoCajaBanco + actualización de saldos) vivían en
``CajaFisicaViewSet.perform_create`` (todo POST de caja física daba 500 por
AttributeError) y ``PagoViewSet`` no los ejecutaba nunca. Ahora viven en
``apps.finanzas.services.registrar_efectos_pago``, invocado por ``PagoViewSet``
dentro de ``transaction.atomic`` con ``select_for_update``.

BUG-A1: ``transferencia_entre_cajas`` no era atómica, no bloqueaba las cajas y
no validaba monto > 0, saldo suficiente ni misma moneda.

Convención del plan: aserciones con valores exactos (sirven de runner de mutación).
"""

import threading
import uuid
from decimal import Decimal

import pytest
from django.db import connections
from django.utils import timezone
from rest_framework.test import APIClient

from apps.finanzas.models import (
    Caja,
    CajaFisica,
    MetodoPago,
    Moneda,
    MovimientoCajaBanco,
    Pago,
    TransaccionFinanciera,
)

pytestmark = pytest.mark.django_db


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def metodo_pago(db):
    return MetodoPago.objects.create(
        nombre_metodo="Efectivo Test", tipo_metodo="EFECTIVO", es_generico=True
    )


@pytest.fixture
def caja_virtual_a(db, empresa_a, moneda_usd):
    return Caja.objects.create(
        empresa=empresa_a,
        nombre="Caja Virtual A",
        tipo_caja="REGISTRADORA",
        moneda=moneda_usd,
        saldo_actual=Decimal("100.00"),
    )


def _payload_pago(empresa, moneda, metodo, caja=None, tipo_operacion="INGRESO", monto="50.00"):
    payload = {
        "id_empresa": str(empresa.id_empresa),
        "tipo_operacion": tipo_operacion,
        "tipo_documento": "FACTURA",
        "id_documento": str(uuid.uuid4()),
        "fecha_pago": timezone.now().isoformat(),
        "monto": monto,
        "id_moneda": str(moneda.id_moneda),
        "id_metodo_pago": str(metodo.id_metodo_pago),
    }
    if caja is not None:
        payload["id_caja_virtual"] = str(caja.id_caja)
    return payload


# ── BUG-C2: POST /api/finanzas/pagos/ genera transacción + movimiento + saldo ─


class TestPagoSideEffects:
    def test_post_pago_ingreso_crea_transaccion_movimiento_y_actualiza_saldo(
        self, client_a, empresa_a, moneda_usd, metodo_pago, caja_virtual_a
    ):
        resp = client_a.post(
            "/api/finanzas/pagos/",
            _payload_pago(empresa_a, moneda_usd, metodo_pago, caja_virtual_a),
            format="json",
        )
        assert resp.status_code == 201, resp.content

        pago = Pago.objects.get(id_pago=resp.data["id_pago"])
        assert pago.id_transaccion_financiera is not None

        transaccion = pago.id_transaccion_financiera
        assert transaccion.tipo_transaccion == "INGRESO"
        assert transaccion.monto_transaccion == Decimal("50.00")
        assert transaccion.id_empresa == empresa_a
        assert transaccion.id_caja == caja_virtual_a

        movimiento = MovimientoCajaBanco.objects.get(id_caja=caja_virtual_a)
        assert movimiento.tipo_movimiento == "INGRESO"
        assert movimiento.monto == Decimal("50.00")
        assert movimiento.saldo_anterior == Decimal("100.00")
        assert movimiento.saldo_nuevo == Decimal("150.00")
        assert movimiento.id_transaccion_financiera == transaccion

        caja_virtual_a.refresh_from_db()
        assert caja_virtual_a.saldo_actual == Decimal("150.00")

    def test_post_pago_egreso_descuenta_saldo(
        self, client_a, empresa_a, moneda_usd, metodo_pago, caja_virtual_a
    ):
        resp = client_a.post(
            "/api/finanzas/pagos/",
            _payload_pago(
                empresa_a, moneda_usd, metodo_pago, caja_virtual_a,
                tipo_operacion="EGRESO", monto="30.00",
            ),
            format="json",
        )
        assert resp.status_code == 201, resp.content

        movimiento = MovimientoCajaBanco.objects.get(id_caja=caja_virtual_a)
        assert movimiento.tipo_movimiento == "EGRESO"
        assert movimiento.saldo_anterior == Decimal("100.00")
        assert movimiento.saldo_nuevo == Decimal("70.00")

        caja_virtual_a.refresh_from_db()
        assert caja_virtual_a.saldo_actual == Decimal("70.00")

    def test_post_pago_sin_caja_ni_cuenta_solo_crea_transaccion(
        self, client_a, empresa_a, moneda_usd, metodo_pago
    ):
        resp = client_a.post(
            "/api/finanzas/pagos/",
            _payload_pago(empresa_a, moneda_usd, metodo_pago),
            format="json",
        )
        assert resp.status_code == 201, resp.content

        pago = Pago.objects.get(id_pago=resp.data["id_pago"])
        assert pago.id_transaccion_financiera is not None
        assert MovimientoCajaBanco.objects.count() == 0

    def test_rollback_total_si_falla_a_mitad(
        self, user_a, empresa_a, moneda_usd, metodo_pago, caja_virtual_a, monkeypatch
    ):
        """Si el movimiento falla, NO quedan ni el pago ni la transacción (atomicidad)."""

        def _boom(*args, **kwargs):
            raise RuntimeError("fallo simulado a mitad del proceso")

        monkeypatch.setattr(
            "apps.finanzas.models.MovimientoCajaBanco.objects.create", _boom
        )

        client = APIClient(raise_request_exception=False)
        client.force_authenticate(user=user_a)
        resp = client.post(
            "/api/finanzas/pagos/",
            _payload_pago(empresa_a, moneda_usd, metodo_pago, caja_virtual_a),
            format="json",
        )
        assert resp.status_code == 500

        assert Pago.objects.count() == 0
        assert TransaccionFinanciera.objects.count() == 0
        caja_virtual_a.refresh_from_db()
        assert caja_virtual_a.saldo_actual == Decimal("100.00")


# ── BUG-C2 (regresión): POST de caja física ya no revienta con 500 ───────────


class TestCajaFisicaCreate:
    def test_post_caja_fisica_retorna_201(self, client_a, empresa_a):
        """Antes: el perform_create trataba la CajaFisica como Pago → AttributeError 500."""
        resp = client_a.post(
            "/api/finanzas/cajas-fisicas/",
            {
                "empresa": str(empresa_a.id_empresa),
                "nombre": "Caja POS 1",
                "tipo_caja": "REGISTRADORA",
                "nombre_dispositivo": "PC Caja 1",
                "identificador_dispositivo": "disp-p03-001",
            },
            format="json",
        )
        assert resp.status_code == 201, resp.content
        caja = CajaFisica.objects.get(id_caja_fisica=resp.data["id_caja_fisica"])
        assert caja.nombre == "Caja POS 1"
        # No se generaron side-effects financieros espurios
        assert TransaccionFinanciera.objects.count() == 0
        assert MovimientoCajaBanco.objects.count() == 0


# ── BUG-A1: transferencia_entre_cajas — validaciones y atomicidad ─────────────


class TestTransferenciaValidaciones:
    @pytest.fixture
    def cajas(self, empresa_a, moneda_usd):
        origen = Caja.objects.create(
            empresa=empresa_a, nombre="Origen", tipo_caja="REGISTRADORA",
            moneda=moneda_usd, saldo_actual=Decimal("100.00"),
        )
        destino = Caja.objects.create(
            empresa=empresa_a, nombre="Destino", tipo_caja="GERENCIA",
            moneda=moneda_usd, saldo_actual=Decimal("20.00"),
        )
        return origen, destino

    def test_monto_no_positivo_rechazado(self, cajas):
        from apps.finanzas.utils_transferencias import transferencia_entre_cajas

        origen, destino = cajas
        with pytest.raises(ValueError, match="mayor a cero"):
            transferencia_entre_cajas(origen, destino, Decimal("0"))
        with pytest.raises(ValueError, match="mayor a cero"):
            transferencia_entre_cajas(origen, destino, Decimal("-5"))
        assert MovimientoCajaBanco.objects.count() == 0

    def test_saldo_insuficiente_rechazado_sin_efectos(self, cajas):
        from apps.finanzas.utils_transferencias import transferencia_entre_cajas

        origen, destino = cajas
        with pytest.raises(ValueError, match="insuficiente"):
            transferencia_entre_cajas(origen, destino, Decimal("100.01"))
        origen.refresh_from_db()
        destino.refresh_from_db()
        assert origen.saldo_actual == Decimal("100.00")
        assert destino.saldo_actual == Decimal("20.00")
        # Atomicidad: no quedó el movimiento de salida "huérfano"
        assert MovimientoCajaBanco.objects.count() == 0

    def test_monedas_distintas_rechazadas(self, cajas, empresa_a):
        from apps.finanzas.utils_transferencias import transferencia_entre_cajas

        origen, _ = cajas
        moneda_ves = Moneda.objects.create(
            nombre="Bolívar", codigo_iso="VES", simbolo="Bs",
            tipo_moneda="fiat", es_generica=True,
        )
        destino_ves = Caja.objects.create(
            empresa=empresa_a, nombre="Destino VES", tipo_caja="GERENCIA",
            moneda=moneda_ves, saldo_actual=Decimal("0.00"),
        )
        with pytest.raises(ValueError, match="misma moneda"):
            transferencia_entre_cajas(origen, destino_ves, Decimal("10.00"))
        assert MovimientoCajaBanco.objects.count() == 0

    def test_misma_caja_rechazada(self, cajas):
        from apps.finanzas.utils_transferencias import transferencia_entre_cajas

        origen, _ = cajas
        with pytest.raises(ValueError, match="distintas"):
            transferencia_entre_cajas(origen, origen, Decimal("10.00"))

    def test_transferencia_valida_mueve_saldos_exactos(self, cajas, user_a):
        from apps.finanzas.utils_transferencias import transferencia_entre_cajas

        origen, destino = cajas
        mov_salida, mov_entrada = transferencia_entre_cajas(
            origen, destino, Decimal("40.00"), usuario=user_a, referencia="ref-p03"
        )
        origen.refresh_from_db()
        destino.refresh_from_db()
        assert origen.saldo_actual == Decimal("60.00")
        assert destino.saldo_actual == Decimal("60.00")
        assert mov_salida.tipo_movimiento == "TRANSFERENCIA_SALIDA"
        assert mov_salida.saldo_anterior == Decimal("100.00")
        assert mov_salida.saldo_nuevo == Decimal("60.00")
        assert mov_entrada.tipo_movimiento == "TRANSFERENCIA_ENTRADA"
        assert mov_entrada.saldo_anterior == Decimal("20.00")
        assert mov_entrada.saldo_nuevo == Decimal("60.00")


# ── BUG-A1: carrera — transferencias concurrentes no pierden saldo ───────────


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
class TestTransferenciaConcurrencia:
    def test_transferencias_concurrentes_no_pierden_saldo(self):
        """
        Saldo origen = 100. 5 hilos transfieren 30 c/u (total 150 > 100).
        Solo 3 deben tener éxito (90 ≤ 100); el resto, saldo insuficiente.
        Invariante: la suma de saldos se conserva (no hay updates perdidos).
        """
        from django.contrib.auth import get_user_model

        from apps.core.models import Empresa
        from apps.finanzas.utils_transferencias import transferencia_entre_cajas

        usuario = get_user_model().objects.create_user(
            username="user_concurrencia", password="testpass123", is_active=True
        )
        moneda = Moneda.objects.create(
            nombre="Dólar", codigo_iso="USD", simbolo="$",
            tipo_moneda="fiat", es_generica=True,
        )
        empresa = Empresa.objects.create(
            nombre_legal="Empresa Concurrencia C.A.",
            identificador_fiscal="J-00000003-3",
            id_moneda_base=moneda,
        )
        origen = Caja.objects.create(
            empresa=empresa, nombre="Origen Conc", tipo_caja="REGISTRADORA",
            moneda=moneda, saldo_actual=Decimal("100.00"),
        )
        destino = Caja.objects.create(
            empresa=empresa, nombre="Destino Conc", tipo_caja="GERENCIA",
            moneda=moneda, saldo_actual=Decimal("0.00"),
        )

        N_HILOS = 5
        MONTO = Decimal("30.00")
        exitos = []
        insuficientes = []
        otros_errores = []
        lock = threading.Lock()

        def transferir():
            try:
                transferencia_entre_cajas(origen, destino, MONTO, usuario=usuario)
                with lock:
                    exitos.append(1)
            except ValueError as exc:
                with lock:
                    if "insuficiente" in str(exc):
                        insuficientes.append(1)
                    else:
                        otros_errores.append(str(exc))
            except Exception as exc:  # noqa: BLE001
                with lock:
                    otros_errores.append(str(exc))
            finally:
                from django.db import connection as _conn

                _conn.close()

        hilos = [threading.Thread(target=transferir) for _ in range(N_HILOS)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(timeout=15)
        connections.close_all()

        assert not otros_errores, f"Errores inesperados en hilos: {otros_errores}"

        origen.refresh_from_db()
        destino.refresh_from_db()
        # Conservación de saldo total: nada se pierde ni se duplica.
        assert origen.saldo_actual + destino.saldo_actual == Decimal("100.00")
        # Serialización exacta: 3 transferencias caben (90 ≤ 100), 2 se rechazan.
        assert len(exitos) == 3, f"Esperados 3 éxitos, hubo {len(exitos)}"
        assert len(insuficientes) == 2, f"Esperados 2 rechazos, hubo {len(insuficientes)}"
        assert origen.saldo_actual == Decimal("10.00")
        assert destino.saldo_actual == Decimal("90.00")
        # Cada éxito dejó su par de movimientos (salida + entrada).
        assert MovimientoCajaBanco.objects.filter(
            tipo_movimiento="TRANSFERENCIA_SALIDA"
        ).count() == 3
        assert MovimientoCajaBanco.objects.filter(
            tipo_movimiento="TRANSFERENCIA_ENTRADA"
        ).count() == 3
