"""
P0-4 / BUG-A2 — Race test del endpoint registrar-pago de cuotas de acuerdo.

Antes del fix, la verificación "ya pagada" ocurría FUERA de `transaction.atomic`
y sin lock: dos requests simultáneos por el total de la cuota pasaban ambos el
check y se registraban DOS pagos completos (doble cobro).

Con `select_for_update` + verificación dentro de la transacción, los requests se
serializan: exactamente uno tiene éxito y el resto recibe 400 "ya pagada".

Mismo patrón que tests/integration/test_cxc_abono_concurrencia.py: requiere
``transaction=True`` para que el commit de cada hilo sea visible a los demás.
"""

import threading
from decimal import Decimal

import pytest
from django.db import connections
from django.utils import timezone
from rest_framework.test import APIClient

from apps.cxc.models import AcuerdoPago, CuotaAcuerdo

pytestmark = pytest.mark.integration


@pytest.mark.django_db(transaction=True)
class TestRegistrarPagoConcurrencia:
    def test_doble_pago_concurrente_solo_uno_cobra(
        self, empresa_a, user_a, moneda_usd, metodo_efectivo
    ):
        """2 hilos pagan la misma cuota de 100 por el total: 1 éxito, 1 rechazo."""
        from apps.finanzas.models import Pago

        acuerdo = AcuerdoPago.objects.create(
            empresa=empresa_a,
            cliente_id="CLI-RACE-ACU",
            cliente_nombre="Cliente Race Acuerdo",
            monto_total=Decimal("100.00"),
            periodicidad="unico",
            fecha_inicio=timezone.now().date(),
            moneda_codigo="USD",
        )
        cuota = CuotaAcuerdo.objects.create(
            acuerdo=acuerdo,
            numero_cuota=1,
            fecha_vencimiento=timezone.now().date(),
            monto=Decimal("100.00"),
            estado="pendiente",
        )

        N_HILOS = 2
        resultados = []
        errores = []
        lock = threading.Lock()
        barrera = threading.Barrier(N_HILOS)

        def pagar():
            try:
                client = APIClient()
                client.force_authenticate(user=user_a)
                barrera.wait(timeout=10)
                resp = client.post(
                    f"/api/cobranza/acuerdos/{acuerdo.pk}/registrar-pago/",
                    {
                        "cuota_id": str(cuota.pk),
                        "monto": "100.00",
                        "moneda_id": str(moneda_usd.pk),
                        "metodo_pago_id": str(metodo_efectivo.pk),
                    },
                    format="json",
                )
                with lock:
                    resultados.append(resp.status_code)
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errores.append(repr(exc))
            finally:
                from django.db import connection as _conn

                _conn.close()

        hilos = [threading.Thread(target=pagar) for _ in range(N_HILOS)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(timeout=20)
        connections.close_all()

        assert not errores, f"Errores inesperados en hilos: {errores}"
        assert sorted(resultados) == [200, 400], (
            f"DOBLE COBRO: se esperaba exactamente un 200 y un 400, hubo {resultados}"
        )

        cuota.refresh_from_db()
        assert cuota.estado == "pagado"
        # Invariante crítica: monto_pagado == monto de la cuota (no 200).
        assert cuota.monto_pagado == Decimal("100.00")
        assert Pago.objects.filter(id_empresa=empresa_a).count() == 1
        acuerdo.refresh_from_db()
        assert acuerdo.estado == "cumplido"
