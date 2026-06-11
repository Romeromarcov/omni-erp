"""
P0-8 — fix/correctness-medios (auditoría integral 2026-06-10).

Tests de los hallazgos:

- BUG-M2: el aging de CxC calcula los saldos con annotate (1 sola consulta,
  sin N+1) y el serializer del list usa la anotación del queryset.
- BUG-M4: el cierre de caja física clasifica los movimientos por (fecha, hora)
  contra la ventana (último cierre, límite] — los movimientos del mismo día
  anteriores al último cierre NO se vuelven a contar.
- BUG-M5: la conciliación automática bloquea el Pago candidato; dos
  ejecuciones (concurrentes o consecutivas) no concilian el mismo Pago contra
  dos movimientos bancarios.
- BUG-A5: el código muerto ``crear_transaccion_financiera_pago`` (conversión
  de moneda invertida, PedidoPago eliminado en ventas/0008) fue eliminado.

BUG-M1 (promedio de sueldo en resumen de nómina) se cubre en
``test_nomina_views_cobertura.py::test_resumen_exacto``.
"""
import datetime
import threading
import uuid
from decimal import Decimal

import pytest
from django.db import connection
from django.utils import timezone

pytestmark = pytest.mark.django_db


# ── BUG-M2: aging CxC sin N+1 ────────────────────────────────────────────────


@pytest.fixture
def cxc_con_abonos(empresa_a, user_a):
    """5 CxC pendientes con 2 abonos cada una (10 abonos en total)."""
    from apps.cuentas_por_cobrar.models import AbonoCxC, CuentaPorCobrar

    hoy = timezone.now().date()
    cuentas = []
    for i in range(5):
        cxc = CuentaPorCobrar.objects.create(
            cliente_externo_id=f"ext-{i}",
            cliente_externo_nombre=f"Cliente {i}",
            monto=Decimal("100.00"),
            fecha_emision=hoy - datetime.timedelta(days=60),
            # corriente, 1-30, 31-60, 61-90, 90+
            fecha_vencimiento=hoy - datetime.timedelta(days=[-5, 10, 45, 75, 120][i]),
            empresa=empresa_a,
            estado="parcial",
        )
        for monto in ("10.00", "15.00"):
            AbonoCxC.objects.create(
                cuenta_por_cobrar=cxc, monto=Decimal(monto), usuario=user_a
            )
        cuentas.append(cxc)
    return cuentas


class TestAgingSinNMasUno:
    def test_aging_una_sola_consulta(self, cxc_con_abonos, empresa_a, django_assert_num_queries):
        """BUG-M2: el aging no dispara un aggregate por CxC (N+1)."""
        from apps.cuentas_por_cobrar.services import calcular_aging

        with django_assert_num_queries(1):
            resultado = calcular_aging(empresa_a.id_empresa)

        # Saldo por cuenta: 100 - 25 = 75; una cuenta por tramo
        for bucket in ("corriente", "dias_1_30", "dias_31_60", "dias_61_90", "dias_90_mas"):
            assert resultado[bucket]["count"] == 1
            assert resultado[bucket]["total"] == Decimal("75.00")
        assert resultado["total_general"] == Decimal("375.00")

    def test_aging_excluye_saldo_cero(self, empresa_a, user_a):
        """Una CxC totalmente abonada (saldo 0) no aparece en ningún tramo."""
        from apps.cuentas_por_cobrar.models import AbonoCxC, CuentaPorCobrar
        from apps.cuentas_por_cobrar.services import calcular_aging

        hoy = timezone.now().date()
        cxc = CuentaPorCobrar.objects.create(
            cliente_externo_id="ext-full",
            monto=Decimal("50.00"),
            fecha_emision=hoy,
            fecha_vencimiento=hoy - datetime.timedelta(days=10),
            empresa=empresa_a,
            estado="parcial",
        )
        AbonoCxC.objects.create(cuenta_por_cobrar=cxc, monto=Decimal("50.00"), usuario=user_a)

        resultado = calcular_aging(empresa_a.id_empresa)
        assert resultado["total_general"] == Decimal("0")
        assert resultado["dias_1_30"]["count"] == 0

    def test_list_serializer_usa_anotacion(self, cxc_con_abonos, user_a):
        """El list del ViewSet no dispara un aggregate por fila para el saldo."""
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get("/api/cxc/cuentas-por-cobrar/", {"empresa": str(cxc_con_abonos[0].empresa_id)})
        assert resp.status_code == 200
        data = resp.data.get("results", resp.data)
        assert len(data) == 5
        for fila in data:
            assert Decimal(str(fila["saldo_pendiente"])) == Decimal("75.00")

    def test_serializer_fallback_sin_anotacion(self, cxc_con_abonos):
        """Instancia suelta (sin anotación) sigue calculando el saldo correcto."""
        from apps.cuentas_por_cobrar.serializers import CuentaPorCobrarSerializer

        data = CuentaPorCobrarSerializer(cxc_con_abonos[0]).data
        assert Decimal(str(data["saldo_pendiente"])) == Decimal("75.00")


# ── BUG-M4: ventana del cierre de caja física ────────────────────────────────


def _crear_mov(caja, user, fecha, hora, tipo, monto, moneda):
    from apps.finanzas.models import MovimientoCajaBanco

    return MovimientoCajaBanco.objects.create(
        id_empresa=caja.empresa,
        fecha_movimiento=fecha,
        hora_movimiento=hora,
        tipo_movimiento=tipo,
        monto=Decimal(monto),
        id_moneda=moneda,
        concepto="mov p0-8",
        id_caja_fisica=caja,
        saldo_anterior=Decimal("0.00"),
        saldo_nuevo=Decimal("0.00"),
        id_usuario_registro=user,
    )


class TestCierreCajaVentana:
    def test_no_recuenta_movimientos_anteriores_al_ultimo_cierre(
        self, caja_fisica_a, user_a, moneda_usd
    ):
        """BUG-M4: con último cierre a las 12:00, un movimiento del mismo día a
        las 10:00 (ya contado en ese cierre) NO entra en el cierre siguiente;
        el de las 14:00 sí. El límite (16:00) es inclusivo y lo posterior queda
        fuera."""
        dia = datetime.date(2026, 6, 10)
        caja = caja_fisica_a
        # CajaFisica no persiste estos campos (hallazgo documentado); se
        # inyectan como atributos para ejercitar la aritmética del cierre.
        caja.saldo_actual = Decimal("100.00")
        caja.fecha_ultimo_cierre = datetime.datetime(2026, 6, 10, 12, 0, 0)

        m = moneda_usd
        _crear_mov(caja, user_a, dia, datetime.time(10, 0), "INGRESO", "50.00", m)   # antes del cierre previo → fuera
        _crear_mov(caja, user_a, dia, datetime.time(12, 0), "INGRESO", "7.00", m)    # exactamente en el cierre previo → fuera
        _crear_mov(caja, user_a, dia, datetime.time(14, 0), "INGRESO", "30.00", m)   # dentro de la ventana
        _crear_mov(caja, user_a, dia, datetime.time(15, 0), "EGRESO", "4.00", m)     # dentro de la ventana
        _crear_mov(caja, user_a, dia, datetime.time(16, 0), "INGRESO", "5.00", m)    # límite inclusivo → dentro
        _crear_mov(caja, user_a, dia, datetime.time(17, 0), "INGRESO", "99.00", m)   # después del límite → fuera
        _crear_mov(
            caja, user_a, dia + datetime.timedelta(days=1), datetime.time(9, 0), "INGRESO", "88.00", m
        )  # otro día posterior → fuera

        resultado = caja.realizar_cierre(
            saldo_real="131.00",
            usuario=user_a,
            hasta=datetime.datetime(2026, 6, 10, 16, 0, 0),
        )

        assert resultado["ingresos"] == Decimal("35.00")   # 30 + 5
        assert resultado["egresos"] == Decimal("4.00")
        assert resultado["saldo_teorico"] == Decimal("131.00")  # 100 + 35 - 4
        assert resultado["descuadre"] == Decimal("0.00")
        assert resultado["movimiento_ajuste_id"] is None

    def test_primer_cierre_cuenta_todo_hasta_el_limite(self, caja_fisica_a, user_a, moneda_usd):
        """Sin cierre previo, entran todos los movimientos hasta el límite."""
        dia = datetime.date(2026, 6, 10)
        caja = caja_fisica_a
        caja.saldo_actual = Decimal("0.00")
        caja.fecha_ultimo_cierre = None

        _crear_mov(caja, user_a, dia, datetime.time(8, 0), "INGRESO", "20.00", moneda_usd)
        _crear_mov(caja, user_a, dia, datetime.time(18, 0), "INGRESO", "9.00", moneda_usd)  # tras el límite

        resultado = caja.realizar_cierre(
            saldo_real="20.00",
            usuario=user_a,
            hasta=datetime.datetime(2026, 6, 10, 16, 0, 0),
        )
        assert resultado["ingresos"] == Decimal("20.00")
        assert resultado["descuadre"] == Decimal("0.00")


# ── BUG-M5: conciliación automática con lock ─────────────────────────────────


@pytest.fixture
def cuenta_bancaria_a(empresa_a, moneda_usd):
    from apps.finanzas.models import CuentaBancariaEmpresa

    return CuentaBancariaEmpresa.objects.create(
        id_empresa=empresa_a,
        nombre_banco="Banco P08",
        numero_cuenta="0102-P08-0001",
        tipo_cuenta="CORRIENTE",
        id_moneda=moneda_usd,
        saldo_actual=Decimal("10000.00"),
    )


def _crear_pago(empresa, cuenta, moneda, monto, referencia=None):
    from apps.finanzas.models import MetodoPago, Pago

    metodo, _ = MetodoPago.objects.get_or_create(
        nombre_metodo="Transferencia P08", tipo_metodo="ELECTRONICO", empresa=empresa
    )
    return Pago.objects.create(
        id_empresa=empresa,
        tipo_operacion="INGRESO",
        tipo_documento="FACTURA",
        id_documento=uuid.uuid4(),
        fecha_pago=timezone.make_aware(datetime.datetime(2026, 5, 10, 10, 0)),
        monto=monto,
        id_moneda=moneda,
        id_metodo_pago=metodo,
        id_cuenta_bancaria=cuenta,
        referencia=referencia,
    )


def _crear_mov_bancario(empresa, cuenta, monto, referencia=""):
    from apps.tesoreria.models import MovimientoBancario

    return MovimientoBancario.objects.create(
        id_empresa=empresa,
        id_cuenta_bancaria=cuenta,
        fecha_mov=datetime.date(2026, 5, 10),
        descripcion="Crédito P08",
        tipo="CREDITO",
        monto=monto,
        referencia=referencia,
        estado="PENDIENTE",
    )


class TestConciliacionLock:
    def test_dos_movimientos_un_pago_solo_un_match(self, empresa_a, cuenta_bancaria_a, moneda_usd):
        """Dos movimientos del mismo monto y un solo Pago → un solo conciliado."""
        from apps.tesoreria.models import MovimientoBancario
        from apps.tesoreria.services import conciliar_automatico

        pago = _crear_pago(empresa_a, cuenta_bancaria_a, moneda_usd, Decimal("1500.0000"))
        _crear_mov_bancario(empresa_a, cuenta_bancaria_a, Decimal("1500.00"))
        _crear_mov_bancario(empresa_a, cuenta_bancaria_a, Decimal("1500.00"))

        resultado = conciliar_automatico(empresa_a, cuenta_bancaria_a)
        assert resultado["conciliados"] == 1
        assert resultado["sin_match"] == 1
        assert MovimientoBancario.objects.filter(id_pago_conciliado=pago).count() == 1

        # Segunda corrida: el Pago ya está tomado, nada nuevo se concilia
        resultado2 = conciliar_automatico(empresa_a, cuenta_bancaria_a)
        assert resultado2["conciliados"] == 0
        assert MovimientoBancario.objects.filter(id_pago_conciliado=pago).count() == 1

    @pytest.mark.django_db(transaction=True)
    def test_carrera_dos_conciliaciones_concurrentes(self, empresa_a, cuenta_bancaria_a, moneda_usd):
        """BUG-M5: dos ejecuciones concurrentes no concilian el mismo Pago
        contra dos movimientos distintos (select_for_update serializa)."""
        from apps.tesoreria.models import MovimientoBancario
        from apps.tesoreria.services import conciliar_automatico

        pago = _crear_pago(empresa_a, cuenta_bancaria_a, moneda_usd, Decimal("1500.0000"))
        _crear_mov_bancario(empresa_a, cuenta_bancaria_a, Decimal("1500.00"))
        _crear_mov_bancario(empresa_a, cuenta_bancaria_a, Decimal("1500.00"))

        resultados = []
        errores = []
        barrera = threading.Barrier(2, timeout=10)

        def worker():
            try:
                barrera.wait()
                resultados.append(conciliar_automatico(empresa_a, cuenta_bancaria_a))
            except Exception as exc:  # pragma: no cover - diagnóstico del test
                errores.append(exc)
            finally:
                connection.close()

        hilos = [threading.Thread(target=worker) for _ in range(2)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(timeout=30)

        assert not errores, f"Errores en hilos: {errores}"
        assert len(resultados) == 2
        total_conciliados = sum(r["conciliados"] for r in resultados)
        assert total_conciliados == 1
        assert MovimientoBancario.objects.filter(id_pago_conciliado=pago).count() == 1
        assert MovimientoBancario.objects.filter(estado="CONCILIADO").count() == 1


# ── BUG-A5: código muerto eliminado ──────────────────────────────────────────


class TestCodigoMuertoEliminado:
    def test_crear_transaccion_financiera_pago_no_existe(self):
        """BUG-A5: la función muerta (conversión de moneda invertida, basada en
        PedidoPago eliminado en ventas/0008) ya no existe en apps.ventas.views."""
        import apps.ventas.views as ventas_views

        assert not hasattr(ventas_views, "crear_transaccion_financiera_pago")
