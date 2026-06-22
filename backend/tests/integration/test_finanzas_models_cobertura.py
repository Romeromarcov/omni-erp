"""
Backfill de cobertura — apps/finanzas/models.py (plan "Cero Dudas", COV/finanzas).

Cubre los métodos de dominio con dinero real (Decimal, aserciones de valor
EXACTO para servir de runner de mutación):

- CajaFisica: propiedades de sesión (esta_abierta, usuario_actual, etc.) y
  ``realizar_cierre`` (cuadre exacto, ajuste positivo/negativo).
- SesionCajaFisica: abrir_sesion / cerrar_sesion / obtener_sesion_activa / duracion.
- Datafono.realizar_cierre: sin cuenta (ValueError), sin transacciones,
  con comisión (crea TransaccionFinanciera de gasto) y segunda corrida
  (rama fecha_ultimo_cierre).
- SesionDatafono.cerrar_sesion y flujo registrar_pago_tarjeta /
  cerrar_sesion_datafono / DepositoDatafono.conciliar / helpers.
- Señales de sincronización Moneda/MetodoPago → *EmpresaActiva.
- PlantillaMaestroCajasVirtuales: señal post_save (creación de cajas virtuales),
  crear_cajas_para_empleado, CajaVirtualAuto.sincronizar_con_plantilla.

NOTA (hallazgo CORREGIDO): ``CajaFisica`` no tiene campos ``saldo_actual`` ni
``fecha_ultimo_cierre`` (eliminados en finanzas/0021) y ``realizar_cierre``
los leía/escribía → AttributeError y corte nunca persistido. El fix re-deriva
el corte de los datos persistentes: el último ``MovimientoCajaBanco`` de tipo
``CIERRE`` aporta el saldo base (``saldo_nuevo``) y el inicio exclusivo de la
ventana (``fecha_movimiento``/``hora_movimiento``). Estos tests crean ese
movimiento CIERRE previo cuando necesitan un saldo base distinto de cero.
"""
import datetime
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.finanzas.models import (
    Caja,
    CajaFisica,
    CajaVirtualAuto,
    CuentaBancariaEmpresa,
    Datafono,
    DepositoDatafono,
    MetodoPago,
    MetodoPagoEmpresaActiva,
    Moneda,
    MonedaEmpresaActiva,
    MovimientoCajaBanco,
    Pago,
    PlantillaMaestroCajasVirtuales,
    SesionCajaFisica,
    SesionDatafono,
    TransaccionDatafono,
    TransaccionFinanciera,
    cerrar_sesion_datafono,
    obtener_depositos_pendientes,
    obtener_sesion_activa_datafono,
    registrar_pago_tarjeta,
    validar_monedas_metodopago,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ── Fixtures locales ──────────────────────────────────────────────────────────

@pytest.fixture
def sucursal_a(empresa_a):
    from apps.core.models import Sucursal

    return Sucursal.objects.create(
        id_empresa=empresa_a, nombre="Sucursal Centro", codigo_sucursal="SC01"
    )


@pytest.fixture
def cuenta_a(empresa_a, moneda_usd):
    return CuentaBancariaEmpresa.objects.create(
        id_empresa=empresa_a,
        nombre_banco="Banco Modelo",
        numero_cuenta="0105-000123",
        tipo_cuenta="CORRIENTE",
        id_moneda=moneda_usd,
        saldo_actual=Decimal("1000.00"),
    )


@pytest.fixture
def datafono_a(empresa_a, sucursal_a, cuenta_a):
    return Datafono.objects.create(
        id_empresa=empresa_a,
        id_sucursal=sucursal_a,
        nombre="POS Principal",
        serial="POS-001",
        id_cuenta_bancaria_asociada=cuenta_a,
        comision_porcentaje=Decimal("2.00"),
    )


@pytest.fixture
def metodo_electronico_a(empresa_a):
    return MetodoPago.objects.create(
        nombre_metodo="Transferencia Modelo", tipo_metodo="ELECTRONICO", empresa=empresa_a
    )


# ── CajaFisica: propiedades de sesión ─────────────────────────────────────────

class TestCajaFisicaPropiedades:
    def test_sin_sesion(self, caja_fisica_a):
        assert caja_fisica_a.sesion_activa is None
        assert caja_fisica_a.esta_abierta is False
        assert caja_fisica_a.usuario_actual is None
        assert caja_fisica_a.nombre_usuario_actual is None
        assert caja_fisica_a.estado_sesion_display == "Cerrada"
        assert caja_fisica_a.cajas_virtuales_asociadas.count() == 0

    def test_con_sesion_abierta(self, caja_fisica_a, user_a):
        sesion = SesionCajaFisica.abrir_sesion(caja_fisica_a, user_a)
        assert caja_fisica_a.sesion_activa == sesion
        assert caja_fisica_a.esta_abierta is True
        assert caja_fisica_a.usuario_actual == user_a
        assert caja_fisica_a.nombre_usuario_actual == "user_empresa_a"
        assert caja_fisica_a.estado_sesion_display == "Abierta por user_empresa_a"


class TestSesionCajaFisica:
    def test_abrir_sesion_asigna_empresa_y_saldo_cero(self, caja_fisica_a, user_a):
        sesion = SesionCajaFisica.abrir_sesion(
            caja_fisica_a, user_a, ip_address="10.0.0.1", user_agent="pytest"
        )
        assert sesion.estado == "ABIERTA"
        assert sesion.empresa == caja_fisica_a.empresa
        assert sesion.sucursal is None
        assert sesion.ip_address == "10.0.0.1"
        assert sesion.user_agent == "pytest"
        # CajaFisica no tiene saldo_actual → rama hasattr False → 0.00
        assert sesion.saldo_inicial == Decimal("0.00")
        assert sesion.esta_activa is True

    def test_abrir_sesion_cierra_la_anterior(self, caja_fisica_a, user_a, user_b):
        primera = SesionCajaFisica.abrir_sesion(caja_fisica_a, user_a)
        segunda = SesionCajaFisica.abrir_sesion(caja_fisica_a, user_b)
        primera.refresh_from_db()
        assert primera.estado == "CERRADA"
        assert primera.notas == "Sesión cerrada automáticamente por nueva apertura"
        assert primera.fecha_cierre is not None
        assert segunda.estado == "ABIERTA"
        assert SesionCajaFisica.objects.filter(
            caja_fisica=caja_fisica_a, estado="ABIERTA"
        ).count() == 1

    def test_cerrar_sesion_con_notas(self, caja_fisica_a, user_a):
        sesion = SesionCajaFisica.abrir_sesion(caja_fisica_a, user_a)
        sesion.cerrar_sesion(notas_cierre="cierre de turno")
        sesion.refresh_from_db()
        assert sesion.estado == "CERRADA"
        assert sesion.notas == "cierre de turno"
        assert sesion.fecha_cierre is not None
        assert sesion.esta_activa is False
        # duracion con fecha_cierre usa el delta cerrado
        assert sesion.duracion == pytest.approx(
            (sesion.fecha_cierre - sesion.fecha_apertura).total_seconds() / 60
        )

    def test_cerrar_sesion_sin_notas_no_pisa_notas(self, caja_fisica_a, user_a):
        sesion = SesionCajaFisica.abrir_sesion(caja_fisica_a, user_a)
        sesion.notas = "nota previa"
        sesion.cerrar_sesion()
        sesion.refresh_from_db()
        assert sesion.notas == "nota previa"

    def test_duracion_sesion_abierta(self, caja_fisica_a, user_a):
        sesion = SesionCajaFisica.abrir_sesion(caja_fisica_a, user_a)
        assert sesion.fecha_cierre is None
        assert sesion.duracion >= 0

    def test_obtener_sesion_activa(self, caja_fisica_a, user_a, user_b):
        assert SesionCajaFisica.obtener_sesion_activa(caja_fisica_a) is None
        sesion = SesionCajaFisica.abrir_sesion(caja_fisica_a, user_a)
        assert SesionCajaFisica.obtener_sesion_activa(caja_fisica_a) == sesion
        assert SesionCajaFisica.obtener_sesion_activa(caja_fisica_a, usuario=user_a) == sesion
        assert SesionCajaFisica.obtener_sesion_activa(caja_fisica_a, usuario=user_b) is None

    def test_str(self, caja_fisica_a, user_a):
        sesion = SesionCajaFisica.abrir_sesion(caja_fisica_a, user_a)
        assert str(sesion) == "Sesión Caja Principal Test - user_empresa_a (Abierta)"


# ── CajaFisica.realizar_cierre ────────────────────────────────────────────────

def _persistir_cierre_previo(caja_fisica, usuario, saldo=Decimal("0.00")):
    """FIX hallazgo P0-8: el corte del cierre anterior es el último
    MovimientoCajaBanco tipo CIERRE (saldo_nuevo = saldo base de la ventana
    siguiente). Se crea fechado ayer para que los movimientos de hoy entren
    en la ventana."""
    ayer = timezone.now() - datetime.timedelta(days=1)
    return MovimientoCajaBanco.objects.create(
        id_empresa=caja_fisica.empresa,
        fecha_movimiento=ayer.date(),
        hora_movimiento=ayer.time(),
        tipo_movimiento="CIERRE",
        monto=Decimal("0.00"),
        concepto="cierre previo (corte persistido)",
        id_caja_fisica=caja_fisica,
        saldo_anterior=Decimal("0.00"),
        saldo_nuevo=saldo,
        id_usuario_registro=usuario,
    )


class TestCajaFisicaRealizarCierre:
    def test_cierre_sin_movimientos_sin_descuadre(self, caja_fisica_a, user_a):
        caja = caja_fisica_a  # sin cierre previo → saldo base 0.00
        resultado = caja.realizar_cierre(saldo_real="0.00", usuario=user_a)
        assert resultado["ingresos"] == Decimal("0.00")
        assert resultado["egresos"] == Decimal("0.00")
        assert resultado["saldo_teorico"] == Decimal("0.00")
        assert resultado["saldo_real"] == Decimal("0.00")
        assert resultado["descuadre"] == Decimal("0.00")
        assert resultado["movimiento_ajuste_id"] is None
        assert resultado["mensaje"] == "Cierre de caja física realizado."
        cierre = MovimientoCajaBanco.objects.get(id_movimiento=resultado["movimiento_cierre_id"])
        assert cierre.tipo_movimiento == "CIERRE"
        assert cierre.monto == Decimal("0.00")
        assert cierre.saldo_nuevo == Decimal("0.00")
        assert cierre.id_usuario_registro == user_a

    def test_cierre_con_movimientos_y_descuadre_negativo(
        self, caja_fisica_a, user_a, empresa_a, moneda_usd
    ):
        caja = caja_fisica_a
        _persistir_cierre_previo(caja, user_a, Decimal("50.00"))
        hoy = timezone.now()
        for tipo, monto in [("INGRESO", "100.00"), ("EGRESO", "30.00")]:
            MovimientoCajaBanco.objects.create(
                id_empresa=empresa_a,
                fecha_movimiento=hoy.date(),
                hora_movimiento=hoy.time(),
                tipo_movimiento=tipo,
                monto=Decimal(monto),
                id_moneda=moneda_usd,
                concepto="mov test",
                id_caja_fisica=caja,
                saldo_anterior=Decimal("0.00"),
                saldo_nuevo=Decimal("0.00"),
                id_usuario_registro=user_a,
            )
        # teórico = 50 + 100 - 30 = 120; contado 100 → descuadre -20 (ajuste NEGATIVO)
        resultado = caja.realizar_cierre(saldo_real="100.00", usuario=user_a)
        assert resultado["ingresos"] == Decimal("100.00")
        assert resultado["egresos"] == Decimal("30.00")
        assert resultado["saldo_teorico"] == Decimal("120.00")
        assert resultado["descuadre"] == Decimal("-20.00")
        assert resultado["mensaje"] == "Cierre de caja física realizado con ajuste."
        ajuste = MovimientoCajaBanco.objects.get(id_movimiento=resultado["movimiento_ajuste_id"])
        assert ajuste.tipo_movimiento == "AJUSTE_NEGATIVO"
        assert ajuste.monto == Decimal("20.00")
        assert ajuste.id_caja_fisica == caja
        # El corte persistido refleja el saldo real contado (FIX P0-8)
        cierre = MovimientoCajaBanco.objects.get(id_movimiento=resultado["movimiento_cierre_id"])
        assert cierre.saldo_anterior == Decimal("50.00")
        assert cierre.saldo_nuevo == Decimal("100.00")
        # El ajuste se fecha en el límite del cierre → pertenece a la ventana
        # cerrada y el siguiente cierre no lo doble-cuenta.
        assert (ajuste.fecha_movimiento, ajuste.hora_movimiento) == (
            cierre.fecha_movimiento,
            cierre.hora_movimiento,
        )

    def test_cierre_con_descuadre_positivo(self, caja_fisica_a, user_a, empresa_a, moneda_usd):
        caja = caja_fisica_a
        _persistir_cierre_previo(caja, user_a, Decimal("10.00"))
        hoy = timezone.now()
        MovimientoCajaBanco.objects.create(
            id_empresa=empresa_a,
            fecha_movimiento=hoy.date(),
            hora_movimiento=hoy.time(),
            tipo_movimiento="AJUSTE_POSITIVO",
            monto=Decimal("5.00"),
            id_moneda=moneda_usd,
            concepto="ajuste previo",
            id_caja_fisica=caja,
            saldo_anterior=Decimal("0.00"),
            saldo_nuevo=Decimal("0.00"),
            id_usuario_registro=user_a,
        )
        # teórico = 10 + 5 = 15; contado 20 → descuadre +5 (ajuste POSITIVO)
        resultado = caja.realizar_cierre(saldo_real="20.00", usuario=user_a)
        assert resultado["ingresos"] == Decimal("5.00")
        assert resultado["saldo_teorico"] == Decimal("15.00")
        assert resultado["descuadre"] == Decimal("5.00")
        ajuste = MovimientoCajaBanco.objects.get(id_movimiento=resultado["movimiento_ajuste_id"])
        assert ajuste.tipo_movimiento == "AJUSTE_POSITIVO"
        assert ajuste.monto == Decimal("5.00")


# ── Datafono.realizar_cierre ──────────────────────────────────────────────────

class TestDatafonoRealizarCierre:
    def test_sin_cuenta_bancaria_value_error(self, empresa_a, sucursal_a):
        datafono = Datafono.objects.create(
            id_empresa=empresa_a, id_sucursal=sucursal_a, nombre="POS sin cuenta",
            serial="POS-NC",
        )
        with pytest.raises(ValueError) as exc:
            datafono.realizar_cierre()
        assert str(exc.value) == "El datafono no tiene cuenta bancaria asociada para el cierre."

    def test_sin_transacciones_no_crea_movimiento(self, datafono_a):
        resultado = datafono_a.realizar_cierre()
        assert resultado["total"] == Decimal("0.00")
        assert resultado["comision"] == Decimal("0.00")
        assert resultado["neto"] == Decimal("0.00")
        assert resultado["movimiento_id"] is None
        assert resultado["transacciones_conciliadas"] == 0
        assert resultado["mensaje"] == "No hay transacciones pendientes de cierre."
        assert MovimientoCajaBanco.objects.count() == 0

    def test_cierre_con_transacciones_y_comision(self, datafono_a, cuenta_a, user_a, empresa_a):
        # Método de pago para registrar la comisión como gasto
        metodo_comision = MetodoPago.objects.create(
            nombre_metodo="Comisión bancaria", tipo_metodo="OTRO", empresa=empresa_a
        )
        for monto in ["100.00", "50.00"]:
            TransaccionDatafono.objects.create(
                id_datafono=datafono_a, monto=Decimal(monto), id_usuario_registro=user_a
            )
        resultado = datafono_a.realizar_cierre(usuario=user_a)
        # total 150, comisión 2% = 3.00, neto 147.00
        assert resultado["total"] == Decimal("150.00")
        assert resultado["comision"] == Decimal("3.0000")
        assert resultado["neto"] == Decimal("147.0000")
        assert resultado["mensaje"] == "Cierre realizado correctamente."
        movimiento = MovimientoCajaBanco.objects.get(id_movimiento=resultado["movimiento_id"])
        assert movimiento.tipo_movimiento == "INGRESO"
        assert movimiento.monto == Decimal("147.00")
        assert movimiento.saldo_anterior == Decimal("1000.00")
        assert movimiento.saldo_nuevo == Decimal("1147.00")
        cuenta_a.refresh_from_db()
        assert cuenta_a.saldo_actual == Decimal("1147.00")
        datafono_a.refresh_from_db()
        assert datafono_a.saldo_temporal == Decimal("0.00")
        assert datafono_a.fecha_ultimo_cierre is not None
        # Transacciones quedan conciliadas (campo legacy)
        assert TransaccionDatafono.objects.filter(conciliada=True).count() == 2
        # Gasto por comisión registrado con monto exacto
        gasto = TransaccionFinanciera.objects.get(tipo_transaccion="EGRESO")
        assert gasto.monto_transaccion == Decimal("3.00")
        assert gasto.id_metodo_pago == metodo_comision
        assert gasto.tipo_documento_asociado == "GASTO"

    def test_cierre_comision_convierte_a_moneda_base(
        self, empresa_a, sucursal_a, user_a, moneda_usd
    ):
        # Deuda FX (models.py:595): la comisión está en la moneda de la cuenta
        # (VES) pero el monto base de la TransaccionFinanciera debe ir en la moneda
        # base de la empresa (USD), convertido con la tasa — no asumir 1:1.
        from django.utils import timezone

        from apps.finanzas.models import Moneda, TasaCambio

        ves = Moneda.objects.create(
            nombre="Bolívar", codigo_iso="VES", simbolo="Bs",
            tipo_moneda="fiat", es_generica=True,
        )
        cuenta_ves = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_a, nombre_banco="Banco VES", numero_cuenta="0102-x",
            tipo_cuenta="CORRIENTE", id_moneda=ves, saldo_actual=Decimal("0.00"),
        )
        datafono = Datafono.objects.create(
            id_empresa=empresa_a, id_sucursal=sucursal_a, nombre="POS VES",
            serial="POS-VES", id_cuenta_bancaria_asociada=cuenta_ves,
            comision_porcentaje=Decimal("2.00"),
        )
        metodo_comision = MetodoPago.objects.create(
            nombre_metodo="Comisión bancaria", tipo_metodo="OTRO", empresa=empresa_a
        )
        TasaCambio.objects.create(
            id_empresa=None, id_moneda_origen=ves, id_moneda_destino=moneda_usd,
            tipo_tasa="OFICIAL_BCV", valor_tasa=Decimal("0.02"),
            fecha_tasa=timezone.now().date(),
        )
        TransaccionDatafono.objects.create(
            id_datafono=datafono, monto=Decimal("100.00"), id_usuario_registro=user_a
        )

        datafono.realizar_cierre(usuario=user_a)

        gasto = TransaccionFinanciera.objects.get(tipo_transaccion="EGRESO")
        # comisión 2% de 100 = 2.00 VES; base USD = 2.00 × 0.02 = 0.0400
        assert gasto.monto_transaccion == Decimal("2.00")
        assert gasto.id_moneda_transaccion == ves
        assert gasto.id_moneda_base == moneda_usd
        assert gasto.monto_base_empresa == Decimal("0.0400")

    def test_cierre_sin_metodo_comision_no_crea_gasto(self, datafono_a, user_a):
        TransaccionDatafono.objects.create(
            id_datafono=datafono_a, monto=Decimal("200.00"), id_usuario_registro=user_a
        )
        resultado = datafono_a.realizar_cierre(usuario=user_a)
        assert resultado["neto"] == Decimal("196.0000")
        assert TransaccionFinanciera.objects.count() == 0

    def test_cierre_fallback_metodo_banco(self, datafono_a, user_a, empresa_a):
        metodo_banco = MetodoPago.objects.create(
            nombre_metodo="Gasto Banco", tipo_metodo="OTRO", empresa=empresa_a
        )
        TransaccionDatafono.objects.create(
            id_datafono=datafono_a, monto=Decimal("100.00"), id_usuario_registro=user_a
        )
        datafono_a.realizar_cierre(usuario=user_a)
        gasto = TransaccionFinanciera.objects.get(tipo_transaccion="EGRESO")
        assert gasto.id_metodo_pago == metodo_banco
        assert gasto.monto_transaccion == Decimal("2.00")

    def test_segunda_corrida_solo_toma_posteriores_al_ultimo_cierre(self, datafono_a, user_a):
        TransaccionDatafono.objects.create(
            id_datafono=datafono_a, monto=Decimal("100.00"), id_usuario_registro=user_a
        )
        datafono_a.realizar_cierre(usuario=user_a)
        datafono_a.refresh_from_db()
        # Nueva transacción tras el cierre
        TransaccionDatafono.objects.create(
            id_datafono=datafono_a, monto=Decimal("40.00"), id_usuario_registro=user_a
        )
        resultado = datafono_a.realizar_cierre(usuario=user_a)
        assert resultado["total"] == Decimal("40.00")
        assert resultado["neto"] == Decimal("39.2000")


# ── SesionDatafono / flujo de pagos con datafono ─────────────────────────────

def _abrir_sesion_datafono(datafono, user):
    """Pre-crea la sesión abierta y la devuelve releída de BD.

    HALLAZGO (bug documentado): registrar_pago_tarjeta lanza TypeError
    ('float' += Decimal) cuando get_or_create CREA la sesión, porque el default
    del campo total_transacciones es el float 0.00. Solo funciona si la sesión
    ya existe en BD (donde llega como Decimal). Por eso los tests pre-crean la
    sesión: ejercitan la rama de reutilización, la única que funciona hoy.
    """
    SesionDatafono.objects.create(datafono=datafono, usuario_apertura=user)
    return SesionDatafono.objects.get(datafono=datafono, estado="ABIERTA")


class TestSesionDatafono:
    def test_registrar_pago_tarjeta_bug_sesion_nueva(self, datafono_a, user_a):
        # Comportamiento actual (bug): primera transacción sin sesión previa
        # revienta por el default float del campo total_transacciones.
        with pytest.raises(TypeError):
            registrar_pago_tarjeta(datafono_a, Decimal("10.00"), "REF-0", None, user_a)

    def test_registrar_pago_tarjeta_crea_y_reutiliza_sesion(self, datafono_a, user_a):
        _abrir_sesion_datafono(datafono_a, user_a)
        t1 = registrar_pago_tarjeta(datafono_a, Decimal("100.00"), "REF-1", None, user_a)
        assert t1.estado == "PENDIENTE"
        assert t1.sesion_datafono.estado == "ABIERTA"
        assert t1.sesion_datafono.usuario_apertura == user_a
        t2 = registrar_pago_tarjeta(datafono_a, Decimal("60.00"), "REF-2", None, user_a)
        assert t2.sesion_datafono == t1.sesion_datafono
        sesion = SesionDatafono.objects.get(pk=t1.sesion_datafono.pk)
        assert sesion.total_transacciones == Decimal("160.00")

    def test_cerrar_sesion_calcula_totales_exactos(self, datafono_a, user_a):
        _abrir_sesion_datafono(datafono_a, user_a)
        registrar_pago_tarjeta(datafono_a, Decimal("100.00"), "REF-1", None, user_a)
        registrar_pago_tarjeta(datafono_a, Decimal("60.00"), "REF-2", None, user_a)
        sesion = SesionDatafono.objects.get(datafono=datafono_a, estado="ABIERTA")
        sesion.cerrar_sesion()
        sesion.refresh_from_db()
        assert sesion.estado == "CERRADA"
        # 160 ya acumulado + 160 de pendientes (las transacciones siguen PENDIENTE
        # cuando se acumularon en total_transacciones) → comportamiento actual:
        # total_transacciones se duplica al sumar de nuevo las pendientes.
        assert sesion.total_transacciones == Decimal("320.00")
        assert sesion.comision_calculada == Decimal("6.4000")
        assert sesion.neto_esperado == Decimal("313.6000")
        assert sesion.transacciones_datafono.filter(estado="CERRADO_EN_DATAFONO").count() == 2

    def test_cerrar_sesion_ya_cerrada_value_error(self, datafono_a, user_a):
        sesion = SesionDatafono.objects.create(
            datafono=datafono_a, usuario_apertura=user_a, estado="CERRADA"
        )
        with pytest.raises(ValueError) as exc:
            sesion.cerrar_sesion()
        assert str(exc.value) == "La sesión ya está cerrada"

    def test_cerrar_sesion_datafono_sin_sesion_abierta(self, datafono_a, user_a):
        with pytest.raises(ValueError) as exc:
            cerrar_sesion_datafono(datafono_a, user_a)
        assert str(exc.value) == "No hay sesión abierta para este datafono"

    def test_cerrar_sesion_datafono_crea_deposito(self, datafono_a, user_a):
        _abrir_sesion_datafono(datafono_a, user_a)
        registrar_pago_tarjeta(datafono_a, Decimal("100.00"), "REF-1", None, user_a)
        deposito = cerrar_sesion_datafono(datafono_a, user_a)
        sesion = deposito.sesion_datafono
        assert deposito.lote_bancario == (
            f"POS-001_{sesion.fecha_cierre.strftime('%Y%m%d_%H%M%S')}"
        )
        assert deposito.total_bruto == Decimal("200.00")  # 100 acumulado + 100 pendiente
        assert deposito.comision_banco == Decimal("4.0000")
        assert deposito.total_neto == Decimal("196.0000")
        assert deposito.usuario_envio == user_a
        assert deposito.estado == "PENDIENTE"
        trans = sesion.transacciones_datafono.get()
        assert trans.estado == "ENVIADO_A_BANCO"
        assert trans.lote_bancario == deposito.lote_bancario

    def test_obtener_sesion_activa_datafono(self, datafono_a, user_a):
        assert obtener_sesion_activa_datafono(datafono_a) is None
        sesion = SesionDatafono.objects.create(datafono=datafono_a, usuario_apertura=user_a)
        assert obtener_sesion_activa_datafono(datafono_a) == sesion


class TestDepositoDatafonoConciliar:
    @pytest.fixture
    def deposito(self, datafono_a, user_a):
        _abrir_sesion_datafono(datafono_a, user_a)
        registrar_pago_tarjeta(datafono_a, Decimal("100.00"), "REF-1", None, user_a)
        return cerrar_sesion_datafono(datafono_a, user_a)

    def _movimiento(self, empresa, moneda, user):
        ahora = timezone.now()
        return MovimientoCajaBanco.objects.create(
            id_empresa=empresa,
            fecha_movimiento=ahora.date(),
            hora_movimiento=ahora.time(),
            tipo_movimiento="INGRESO",
            monto=Decimal("196.00"),
            id_moneda=moneda,
            concepto="depósito banco",
            saldo_anterior=Decimal("0.00"),
            saldo_nuevo=Decimal("196.00"),
            id_usuario_registro=user,
        )

    def test_conciliar_actualiza_deposito_sesion_y_transacciones(
        self, deposito, empresa_a, moneda_usd, user_a
    ):
        movimiento = self._movimiento(empresa_a, moneda_usd, user_a)
        deposito.conciliar(movimiento, user_a)
        deposito.refresh_from_db()
        assert deposito.estado == "CONCILIADO"
        assert deposito.movimiento_banco == movimiento
        assert deposito.usuario_conciliacion == user_a
        assert deposito.fecha_conciliacion is not None
        sesion = deposito.sesion_datafono
        sesion.refresh_from_db()
        assert sesion.estado == "CONCILIADA"
        trans = sesion.transacciones_datafono.get()
        assert trans.estado == "CONCILIADO"
        assert trans.fecha_conciliacion == deposito.fecha_conciliacion

    def test_conciliar_dos_veces_value_error(self, deposito, empresa_a, moneda_usd, user_a):
        movimiento = self._movimiento(empresa_a, moneda_usd, user_a)
        deposito.conciliar(movimiento, user_a)
        with pytest.raises(ValueError) as exc:
            deposito.conciliar(movimiento, user_a)
        assert str(exc.value) == "El depósito ya está conciliado"

    def test_obtener_depositos_pendientes(self, deposito, datafono_a, empresa_a, sucursal_a):
        otro_datafono = Datafono.objects.create(
            id_empresa=empresa_a, id_sucursal=sucursal_a, nombre="POS 2", serial="POS-002"
        )
        pendientes = obtener_depositos_pendientes()
        assert list(pendientes) == [deposito]
        assert list(obtener_depositos_pendientes(datafono=datafono_a)) == [deposito]
        assert list(obtener_depositos_pendientes(datafono=otro_datafono)) == []


# ── Señales de sincronización multi-tenant ───────────────────────────────────

class TestSincronizacionEmpresaActiva:
    def test_moneda_publica_se_activa_para_todas_las_empresas(self, empresa_a, empresa_b):
        moneda = Moneda.objects.create(
            nombre="Euro", codigo_iso="EUR", simbolo="€", tipo_moneda="fiat", es_publica=True
        )
        assert MonedaEmpresaActiva.objects.filter(moneda=moneda, empresa=empresa_a).exists()
        assert MonedaEmpresaActiva.objects.filter(moneda=moneda, empresa=empresa_b).exists()

    def test_moneda_privada_solo_para_su_empresa(self, empresa_a, empresa_b):
        moneda = Moneda.objects.create(
            nombre="Token A", codigo_iso="TKA", simbolo="T", tipo_moneda="otro",
            empresa=empresa_a,
        )
        assert MonedaEmpresaActiva.objects.filter(moneda=moneda, empresa=empresa_a).exists()
        assert not MonedaEmpresaActiva.objects.filter(moneda=moneda, empresa=empresa_b).exists()

    def test_metodo_publico_se_activa_para_todas(self, empresa_a, empresa_b):
        metodo = MetodoPago.objects.create(
            nombre_metodo="Pago Móvil Global", tipo_metodo="ELECTRONICO", es_publico=True
        )
        assert MetodoPagoEmpresaActiva.objects.filter(metodo_pago=metodo, empresa=empresa_a).exists()
        assert MetodoPagoEmpresaActiva.objects.filter(metodo_pago=metodo, empresa=empresa_b).exists()

    def test_metodo_privado_solo_su_empresa(self, empresa_a, empresa_b, metodo_electronico_a):
        assert MetodoPagoEmpresaActiva.objects.filter(
            metodo_pago=metodo_electronico_a, empresa=empresa_a
        ).exists()
        assert not MetodoPagoEmpresaActiva.objects.filter(
            metodo_pago=metodo_electronico_a, empresa=empresa_b
        ).exists()

    def test_validar_monedas_metodopago_rechaza_crypto_en_efectivo(self, empresa_a):
        metodo = MetodoPago.objects.create(
            nombre_metodo="Efectivo Caja", tipo_metodo="EFECTIVO", empresa=empresa_a
        )
        crypto = Moneda.objects.create(
            nombre="Tether", codigo_iso="USDT", simbolo="₮", tipo_moneda="crypto"
        )
        with pytest.raises(ValidationError) as exc:
            validar_monedas_metodopago(metodo, [crypto])
        assert "Solo monedas fiat están permitidas" in str(exc.value)

    def test_validar_monedas_metodopago_acepta_fiat(self, empresa_a, moneda_usd):
        metodo = MetodoPago.objects.create(
            nombre_metodo="Efectivo OK", tipo_metodo="EFECTIVO", empresa=empresa_a
        )
        # No lanza
        validar_monedas_metodopago(metodo, [moneda_usd])


# ── PlantillaMaestroCajasVirtuales ───────────────────────────────────────────

class TestPlantillaMaestro:
    def test_post_save_crea_cajas_virtuales_en_cajas_fisicas(
        self, empresa_a, moneda_usd, caja_fisica_a, user_a
    ):
        plantilla = PlantillaMaestroCajasVirtuales.objects.create(
            empresa=empresa_a, nombre="Plantilla USD", moneda_base=moneda_usd,
            creada_por=user_a,
        )
        caja = Caja.objects.get(caja_fisica=caja_fisica_a, plantilla_maestro=plantilla)
        assert caja.nombre == "Plantilla USD - Caja Principal Test"
        assert caja.moneda == moneda_usd
        assert caja.empresa == empresa_a
        assert caja.tipo_caja == "REGISTRADORA"
        assert caja.activa is True

    def test_post_save_no_duplica_si_ya_existe_misma_configuracion(
        self, empresa_a, moneda_usd, caja_fisica_a
    ):
        Caja.objects.create(
            empresa=empresa_a, caja_fisica=caja_fisica_a, nombre="Preexistente",
            moneda=moneda_usd, activa=True,
        )
        PlantillaMaestroCajasVirtuales.objects.create(
            empresa=empresa_a, nombre="Plantilla 2", moneda_base=moneda_usd
        )
        # La caja preexistente (sin métodos) coincide con la plantilla (sin métodos) → no crea otra
        assert Caja.objects.filter(caja_fisica=caja_fisica_a).count() == 1

    def test_update_dispara_sincronizacion(self, empresa_a, moneda_usd, metodo_electronico_a):
        plantilla = PlantillaMaestroCajasVirtuales.objects.create(
            empresa=empresa_a, nombre="Plantilla sync", moneda_base=moneda_usd
        )
        plantilla.metodos_pago_base.add(metodo_electronico_a)
        auto = CajaVirtualAuto.objects.create(
            plantilla_maestro=plantilla, moneda=moneda_usd,
            metodo_pago=metodo_electronico_a, activa=False,
        )
        plantilla.nombre = "Plantilla sync v2"
        plantilla.save()  # created=False → sincronizar_cajas_virtuales()
        auto.refresh_from_db()
        assert auto.activa is True

    def test_sincronizar_con_plantilla_desactiva_si_metodo_fuera_de_base(
        self, empresa_a, moneda_usd, metodo_electronico_a
    ):
        plantilla = PlantillaMaestroCajasVirtuales.objects.create(
            empresa=empresa_a, nombre="Plantilla x", moneda_base=moneda_usd
        )
        auto = CajaVirtualAuto.objects.create(
            plantilla_maestro=plantilla, moneda=moneda_usd,
            metodo_pago=metodo_electronico_a, activa=True,
        )
        auto.sincronizar_con_plantilla()  # metodo no está en metodos_pago_base
        auto.refresh_from_db()
        assert auto.activa is False

    def test_crear_cajas_para_empleado_con_rol(
        self, empresa_a, moneda_usd, metodo_electronico_a, user_a
    ):
        grupo = Group.objects.create(name="cajero")
        user_a.groups.add(grupo)
        plantilla = PlantillaMaestroCajasVirtuales.objects.create(
            empresa=empresa_a, nombre="Plantilla móvil", moneda_base=moneda_usd,
            aplicar_a_empleados_con_rol="cajero",
        )
        plantilla.metodos_pago_base.add(metodo_electronico_a)
        creadas = plantilla.crear_cajas_para_empleado(user_a)
        assert len(creadas) == 1
        assert creadas[0].empleado == user_a
        assert creadas[0].metodo_pago == metodo_electronico_a
        assert creadas[0].creada_automaticamente is True
        # Idempotente: segunda corrida no crea más
        assert plantilla.crear_cajas_para_empleado(user_a) == []

    def test_crear_cajas_para_empleado_sin_rol_configurado(self, empresa_a, moneda_usd, user_a):
        plantilla = PlantillaMaestroCajasVirtuales.objects.create(
            empresa=empresa_a, nombre="Sin rol", moneda_base=moneda_usd
        )
        assert plantilla.crear_cajas_para_empleado(user_a) == []

    def test_crear_cajas_para_caja_fisica_sin_metodos(self, empresa_a, moneda_usd, caja_fisica_a):
        plantilla = PlantillaMaestroCajasVirtuales.objects.create(
            empresa=empresa_a, nombre="Sin métodos", moneda_base=moneda_usd
        )
        # Sin metodos_pago_base el loop no itera (no llega al método inexistente
        # caja_fisica.metodo_pago_deshabilitado — bug documentado)
        assert plantilla.crear_cajas_para_caja_fisica(caja_fisica_a) == []

    def test_str(self, empresa_a, moneda_usd):
        plantilla = PlantillaMaestroCajasVirtuales.objects.create(
            empresa=empresa_a, nombre="P", moneda_base=moneda_usd
        )
        assert str(plantilla) == f"Plantilla Maestro: P ({empresa_a})"


# ── Pago ─────────────────────────────────────────────────────────────────────

class TestPagoModel:
    def test_pago_ajuste_se_guarda_y_documento_relacionado_none(
        self, empresa_a, moneda_usd, metodo_electronico_a, user_a
    ):
        import uuid

        pago = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="INGRESO",
            tipo_documento="AJUSTE",
            id_documento=uuid.uuid4(),
            fecha_pago=timezone.now(),
            monto=Decimal("123.4567"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_electronico_a,
            id_usuario_registro=user_a,
        )
        assert pago.monto == Decimal("123.4567")
        assert pago.documento_relacionado is None
        assert str(pago) == "INGRESO - 123.4567 (Ajuste Manual)"

    def test_pago_pedido_sin_fk_no_valida_nada(self, empresa_a, moneda_usd, metodo_electronico_a):
        import uuid

        # tipo PEDIDO pero id_pedido None → _validar_documento no consulta nada
        pago = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="EGRESO",
            tipo_documento="PEDIDO",
            id_documento=uuid.uuid4(),
            fecha_pago=timezone.now(),
            monto=Decimal("10.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_electronico_a,
        )
        assert pago.documento_relacionado is None
