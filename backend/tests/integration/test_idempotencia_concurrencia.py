"""
P1-2 (hardening, R9) — Race test de idempotencia bajo doble-submit concurrente.

Dos hilos disparan el MISMO POST de abono CxC con la MISMA ``Idempotency-Key``
al mismo tiempo. El registro de la clave se inserta "en vuelo" al inicio de la
transacción: el segundo hilo se bloquea en el índice único de la BD hasta que el
primero commitea y entonces recibe la respuesta de la ganadora (o 409 si aún no
es visible). Invariante: NUNCA se crean dos abonos.

Mismo patrón que ``test_cxc_abono_concurrencia.py``: requiere
``transaction=True`` para que el commit de cada hilo sea visible a los demás.
"""

import threading
from decimal import Decimal

import pytest
from django.db import connections
from django.utils import timezone
from rest_framework.test import APIClient

pytestmark = pytest.mark.integration


@pytest.mark.django_db(transaction=True)
class TestIdempotenciaConcurrencia:
    def test_doble_submit_concurrente_no_duplica_abono(self, empresa_a, user_a):
        from apps.core.models import ClaveIdempotencia
        from apps.crm.models import Cliente
        from apps.cuentas_por_cobrar.models import AbonoCxC, CuentaPorCobrar

        cliente = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Cliente Race Idem",
            rif="J-55555555-5",
            tipo_cliente="CREDITO",
            limite_credito=Decimal("100000.00"),
            dias_credito=30,
        )
        cxc = CuentaPorCobrar.objects.create(
            cliente=cliente,
            empresa=empresa_a,
            monto=Decimal("1000.00"),
            fecha_emision=timezone.now().date(),
            fecha_vencimiento=timezone.now().date(),
            estado="pendiente",
            descripcion="CxC race idempotencia",
        )

        N_HILOS = 4
        resultados = []
        errores = []
        lock = threading.Lock()
        barrera = threading.Barrier(N_HILOS)

        def doble_submit():
            try:
                client = APIClient()
                client.force_authenticate(user=user_a)
                barrera.wait(timeout=10)
                r = client.post(
                    f"/api/cxc/cuentas-por-cobrar/{cxc.pk}/abonar/",
                    {"monto": "250.00"},
                    format="json",
                    HTTP_IDEMPOTENCY_KEY="race-idem-key",
                )
                with lock:
                    resultados.append((r.status_code, dict(r.data) if r.data else {}))
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errores.append(str(exc))
            finally:
                from django.db import connection as _conn

                _conn.close()

        hilos = [threading.Thread(target=doble_submit) for _ in range(N_HILOS)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(timeout=30)
        connections.close_all()

        assert not errores, f"Errores inesperados en hilos: {errores}"
        assert len(resultados) == N_HILOS

        # Invariante crítica: UN solo abono real, por 250.00 exactos.
        abonos = AbonoCxC.objects.filter(cuenta_por_cobrar=cxc)
        assert abonos.count() == 1
        assert abonos.get().monto == Decimal("250.00")

        # Una sola clave consumida, con respuesta persistida.
        registro = ClaveIdempotencia.objects.get(clave="race-idem-key")
        assert registro.status_respuesta == 201
        assert registro.empresa_id == empresa_a.pk

        # Todos los hilos recibieron 201 (respuesta original o reproducida) o,
        # a lo sumo, un 409 transitorio de "operación en curso".
        statuses = [s for s, _ in resultados]
        assert statuses.count(201) >= 1
        assert all(s in (201, 409) for s in statuses), statuses
        # Los 201 reproducen exactamente el mismo abono (mismo id).
        ids = {body.get("abono_id") for s, body in resultados if s == 201}
        assert len(ids) == 1
