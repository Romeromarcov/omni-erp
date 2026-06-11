"""
Backfill de cobertura — apps/ventas/views.py::crear_transaccion_financiera_pago
(plan "Cero Dudas", COV/ventas).

La función es CÓDIGO MUERTO (cero callers en el repo), pero importable y con
mucha lógica de dinero. Se testea DIRECTO como función, con objetos reales de
BD (``finanzas.Pago`` + fixtures del conftest).

Hallazgo clave: la función fue escrita contra una interfaz "legacy" de pago que
NO coincide con el modelo real ``finanzas.Pago``:

- espera ``pago.id_pago_pedido`` (PK legacy) → el modelo real tiene ``id_pago``;
  el f-string del log lo evalúa en la PRIMERA línea útil → AttributeError (BUG).
- espera ``pago.moneda`` (str código ISO) → el modelo real tiene ``id_moneda`` (FK).
  El acceso está envuelto en try/except, así que degrada a la moneda base.
- espera ``pago.metodo`` (str UUID o nombre/tipo) → el modelo real tiene
  ``id_metodo_pago`` (FK). El acceso NO está protegido → AttributeError.

Para cubrir las ramas de dinero se usa un Pago real persistido + los atributos
legacy que la función lee (duck typing), con Decimal y valores exactos.
"""
import datetime
from decimal import Decimal

import pytest

from django.core.exceptions import FieldError
from django.utils import timezone

from apps.finanzas.models import (
    Caja,
    CuentaBancariaEmpresa,
    Datafono,
    MetodoPago,
    Moneda,
    MovimientoCajaBanco,
    Pago,
    TasaCambio,
    TransaccionDatafono,
    TransaccionFinanciera,
)
from apps.ventas.views import crear_transaccion_financiera_pago

pytestmark = pytest.mark.django_db


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def moneda_ves(db):
    return Moneda.objects.create(
        nombre="Bolívar", codigo_iso="VES", simbolo="Bs", tipo_moneda="fiat", es_generica=True
    )


@pytest.fixture
def empresa_bimonetaria(empresa_a, moneda_ves):
    """Empresa A con moneda base USD (conftest) + moneda país VES."""
    empresa_a.id_moneda_pais = moneda_ves
    empresa_a.save(update_fields=["id_moneda_pais"])
    return empresa_a


@pytest.fixture
def cliente(db, empresa_a):
    from apps.crm.models import Cliente

    return Cliente.objects.create(
        id_empresa=empresa_a, razon_social="Cliente Pago", rif="J-22222222-2"
    )


@pytest.fixture
def pedido(db, empresa_a, cliente):
    from apps.ventas.models import Pedido

    return Pedido.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente,
        numero_pedido="PED-PAGO-001",
        fecha_pedido=datetime.date(2026, 6, 9),
    )


@pytest.fixture
def metodo_efectivo(db, empresa_a):
    return MetodoPago.objects.create(
        empresa=empresa_a, nombre_metodo="Efectivo Caja", tipo_metodo="EFECTIVO"
    )


def _pago_real(empresa, pedido, moneda, metodo, monto, tasa=Decimal("1")):
    """Pago REAL persistido en BD (modelo finanzas.Pago)."""
    return Pago.objects.create(
        id_empresa=empresa,
        tipo_operacion="INGRESO",
        tipo_documento="PEDIDO",
        id_documento=pedido.id_pedido,
        id_pedido=pedido,
        fecha_pago=timezone.now(),
        monto=monto,
        id_moneda=moneda,
        tasa=tasa,
        id_metodo_pago=metodo,
        referencia="REF-001",
    )


def _con_interfaz_legacy(pago, *, moneda_iso, metodo_str):
    """
    Adjunta los atributos "legacy" que la función muerta espera y que el modelo
    real no tiene: ``id_pago_pedido`` (PK legacy), ``moneda`` (str ISO) y
    ``metodo`` (str UUID o nombre/tipo).
    """
    pago.id_pago_pedido = pago.id_pago
    pago.moneda = moneda_iso
    pago.metodo = metodo_str
    return pago


# ── BUGs documentados (interfaz legacy vs modelo real) ───────────────────────

class TestInterfazLegacyRota:
    def test_pago_real_sin_atributos_legacy_lanza_attributeerror(
        self, empresa_bimonetaria, pedido, moneda_usd, metodo_efectivo, user_a
    ):
        """
        BUG: la función espera la interfaz legacy (``id_pago_pedido``, ``moneda``,
        ``metodo``) que ``finanzas.Pago`` no tiene. Con un Pago real sin parches
        revienta de inmediato en el f-string del log (``pago.id_pago_pedido``)
        con AttributeError, re-lanzado por el except externo. Confirma que la
        función es inutilizable con el modelo real → código muerto e incompatible.
        """
        pago = _pago_real(empresa_bimonetaria, pedido, moneda_usd, metodo_efectivo, Decimal("100.00"))
        with pytest.raises(AttributeError, match="id_pago_pedido"):
            crear_transaccion_financiera_pago(pago, user_a)
        assert TransaccionFinanciera.objects.count() == 0

    def test_efectivo_sin_caja_seleccionada_lanza_fielderror(
        self, empresa_bimonetaria, pedido, moneda_usd, metodo_efectivo, user_a
    ):
        """
        BUG: la búsqueda automática de caja virtual filtra por
        ``Caja.objects.filter(..., monedas=moneda_pago)`` pero el modelo ``Caja``
        NO tiene M2M ``monedas`` (solo FK ``moneda``) → FieldError. La rama
        EFECTIVO sin caja preseleccionada está rota.
        """
        pago = _con_interfaz_legacy(
            _pago_real(empresa_bimonetaria, pedido, moneda_usd, metodo_efectivo, Decimal("50.00")),
            moneda_iso="USD",
            metodo_str="EFECTIVO",
        )
        with pytest.raises(FieldError):
            crear_transaccion_financiera_pago(pago, user_a)
        # Revienta ANTES de crear la transacción → ningún efecto en BD
        assert TransaccionFinanciera.objects.count() == 0
        assert MovimientoCajaBanco.objects.count() == 0


# ── Ramas de salida temprana (sin efectos) ────────────────────────────────────

class TestSalidasTempranas:
    def test_sin_moneda_pais_retorna_sin_crear_nada(
        self, empresa_a, pedido, moneda_usd, metodo_efectivo, user_a
    ):
        """empresa.id_moneda_pais=None y sin VES → return antes de tocar la BD."""
        assert empresa_a.id_moneda_pais is None
        pago = _con_interfaz_legacy(
            _pago_real(empresa_a, pedido, moneda_usd, metodo_efectivo, Decimal("100.00")),
            moneda_iso="USD",
            metodo_str="EFECTIVO",
        )
        resultado = crear_transaccion_financiera_pago(pago, user_a)
        assert resultado is None
        assert TransaccionFinanciera.objects.count() == 0
        assert MovimientoCajaBanco.objects.count() == 0

    def test_metodo_pago_inexistente_retorna_sin_crear_nada(
        self, empresa_bimonetaria, pedido, moneda_usd, metodo_efectivo, user_a
    ):
        """Método no-UUID que no matchea nombre/tipo → return (cubre además el
        cálculo de montos con fallback a pago.tasa, sin TasaCambio en BD)."""
        pago = _con_interfaz_legacy(
            _pago_real(
                empresa_bimonetaria, pedido, moneda_usd, metodo_efectivo,
                Decimal("100.00"), tasa=Decimal("36.50"),
            ),
            moneda_iso="USD",
            metodo_str="METODO_FANTASMA",
        )
        resultado = crear_transaccion_financiera_pago(pago, user_a)
        assert resultado is None
        assert TransaccionFinanciera.objects.count() == 0


# ── Caminos completos con caja virtual seleccionada por el usuario ───────────

class TestCajaVirtualSeleccionada:
    def test_misma_moneda_con_tasa_bcv_montos_exactos(
        self, empresa_bimonetaria, pedido, moneda_usd, moneda_ves, metodo_efectivo, user_a
    ):
        """
        Pago USD (= moneda base), caja USD seleccionada, TasaCambio USD→VES de hoy.
        monto_base = monto; monto_pais = monto * tasa_bcv (no la tasa del pago).
        Método referenciado por UUID (rama uuid.UUID válida).
        """
        TasaCambio.objects.create(
            id_empresa=empresa_bimonetaria,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_ves,
            tipo_tasa="OFICIAL_BCV",
            valor_tasa=Decimal("40.00000000"),
            fecha_tasa=datetime.date.today(),
        )
        caja = Caja.objects.create(
            empresa=empresa_bimonetaria, nombre="Caja USD", moneda=moneda_usd,
            activa=True, saldo_actual=Decimal("0.00"),
        )
        pago = _pago_real(
            empresa_bimonetaria, pedido, moneda_usd, metodo_efectivo,
            Decimal("100.00"), tasa=Decimal("36.00"),
        )
        pago.id_caja_virtual = caja
        _con_interfaz_legacy(pago, moneda_iso="USD", metodo_str=str(metodo_efectivo.id_metodo_pago))

        crear_transaccion_financiera_pago(pago, user_a)

        trans = TransaccionFinanciera.objects.get()
        assert trans.tipo_transaccion == "INGRESO"
        assert trans.monto_transaccion == Decimal("100.00")
        assert trans.monto_base_empresa == Decimal("100.00")
        assert trans.monto_moneda_pais == Decimal("4000.00")  # 100 * 40 (BCV), no 36
        assert trans.id_moneda_transaccion == moneda_usd
        assert trans.id_caja == caja
        assert trans.id_cuenta_bancaria is None
        assert trans.nro_documento_asociado == "PED-PAGO-001"

        mov = MovimientoCajaBanco.objects.get()
        assert mov.monto == Decimal("100.00")  # misma moneda → monto directo
        assert mov.saldo_anterior == Decimal("0.00")
        assert mov.saldo_nuevo == Decimal("100.00")
        assert mov.id_moneda == moneda_usd
        caja.refresh_from_db()
        assert caja.saldo_actual == Decimal("100.00")

    def test_caja_en_ves_convierte_con_tasa_del_pago(
        self, empresa_bimonetaria, pedido, moneda_usd, moneda_ves, metodo_efectivo, user_a
    ):
        """
        Pago USD (base) sobre caja VES (país), SIN TasaCambio en BD:
        monto_pais = monto * pago.tasa (fallback) y el movimiento se convierte
        de base a país multiplicando por pago.tasa. Método por tipo (no UUID).
        """
        caja = Caja.objects.create(
            empresa=empresa_bimonetaria, nombre="Caja VES", moneda=moneda_ves,
            activa=True, saldo_actual=Decimal("100.00"),
        )
        pago = _pago_real(
            empresa_bimonetaria, pedido, moneda_usd, metodo_efectivo,
            Decimal("10.00"), tasa=Decimal("36.50"),
        )
        pago.id_caja_virtual = caja
        _con_interfaz_legacy(pago, moneda_iso="USD", metodo_str="EFECTIVO")

        crear_transaccion_financiera_pago(pago, user_a)

        trans = TransaccionFinanciera.objects.get()
        assert trans.monto_base_empresa == Decimal("10.00")
        assert trans.monto_moneda_pais == Decimal("365.00")  # 10 * 36.50

        mov = MovimientoCajaBanco.objects.get()
        assert mov.monto == Decimal("365.00")  # base→país: 10 * 36.50
        assert mov.id_moneda == moneda_ves
        assert mov.saldo_anterior == Decimal("100.00")
        assert mov.saldo_nuevo == Decimal("465.00")
        caja.refresh_from_db()
        assert caja.saldo_actual == Decimal("465.00")

    def test_pago_en_ves_divide_monto_base_por_tasa(
        self, empresa_bimonetaria, pedido, moneda_usd, moneda_ves, metodo_efectivo, user_a
    ):
        """
        Pago en VES (= moneda país): monto_pais = monto directo y
        monto_base = monto / pago.tasa (fallback sin TasaCambio). División Decimal exacta.
        """
        caja = Caja.objects.create(
            empresa=empresa_bimonetaria, nombre="Caja Bs", moneda=moneda_ves,
            activa=True, saldo_actual=Decimal("0.00"),
        )
        pago = _pago_real(
            empresa_bimonetaria, pedido, moneda_ves, metodo_efectivo,
            Decimal("3650.00"), tasa=Decimal("36.50"),
        )
        pago.id_caja_virtual = caja
        _con_interfaz_legacy(pago, moneda_iso="VES", metodo_str="EFECTIVO")

        crear_transaccion_financiera_pago(pago, user_a)

        trans = TransaccionFinanciera.objects.get()
        assert trans.id_moneda_transaccion == moneda_ves
        assert trans.monto_base_empresa == Decimal("100.00")  # 3650 / 36.50 exacto
        assert trans.monto_moneda_pais == Decimal("3650.00")

        mov = MovimientoCajaBanco.objects.get()
        assert mov.monto == Decimal("3650.00")  # misma moneda que la caja
        caja.refresh_from_db()
        assert caja.saldo_actual == Decimal("3650.00")

    def test_moneda_del_pago_desconocida_usa_moneda_base(
        self, empresa_bimonetaria, pedido, moneda_usd, moneda_ves, metodo_efectivo, user_a
    ):
        """``pago.moneda`` con ISO inexistente → degrada a la moneda base (USD)."""
        caja = Caja.objects.create(
            empresa=empresa_bimonetaria, nombre="Caja X", moneda=moneda_usd,
            activa=True, saldo_actual=Decimal("0.00"),
        )
        pago = _pago_real(
            empresa_bimonetaria, pedido, moneda_usd, metodo_efectivo,
            Decimal("5.00"), tasa=Decimal("36.00"),
        )
        pago.id_caja_virtual = caja
        _con_interfaz_legacy(pago, moneda_iso="XXX", metodo_str="EFECTIVO")

        crear_transaccion_financiera_pago(pago, user_a)

        trans = TransaccionFinanciera.objects.get()
        assert trans.id_moneda_transaccion == moneda_usd  # fallback a base
        assert trans.monto_base_empresa == Decimal("5.00")

    def test_tasa_bcv_para_monto_base_cuando_pago_no_es_base(
        self, empresa_bimonetaria, pedido, moneda_usd, moneda_ves, metodo_efectivo, user_a
    ):
        """
        Pago VES con TasaCambio VES→USD de hoy: monto_base = monto / valor_tasa
        (rama de tasa del sistema, no el fallback de pago.tasa).
        """
        TasaCambio.objects.create(
            id_empresa=empresa_bimonetaria,
            id_moneda_origen=moneda_ves,
            id_moneda_destino=moneda_usd,
            tipo_tasa="OFICIAL_BCV",
            valor_tasa=Decimal("36.50000000"),
            fecha_tasa=datetime.date.today(),
        )
        caja = Caja.objects.create(
            empresa=empresa_bimonetaria, nombre="Caja Bs2", moneda=moneda_ves,
            activa=True, saldo_actual=Decimal("0.00"),
        )
        pago = _pago_real(
            empresa_bimonetaria, pedido, moneda_ves, metodo_efectivo,
            Decimal("730.00"), tasa=Decimal("99.00"),  # tasa del pago NO debe usarse
        )
        pago.id_caja_virtual = caja
        _con_interfaz_legacy(pago, moneda_iso="VES", metodo_str="EFECTIVO")

        crear_transaccion_financiera_pago(pago, user_a)

        trans = TransaccionFinanciera.objects.get()
        assert trans.monto_base_empresa == Decimal("20.00")  # 730 / 36.50 (BCV)
        assert trans.monto_moneda_pais == Decimal("730.00")

    def test_caja_de_pago_en_pais_sobre_caja_base_divide_por_tasa(
        self, empresa_bimonetaria, pedido, moneda_usd, moneda_ves, metodo_efectivo, user_a
    ):
        """Movimiento: pago VES (país) sobre caja USD (base) → monto / pago.tasa."""
        caja = Caja.objects.create(
            empresa=empresa_bimonetaria, nombre="Caja USD2", moneda=moneda_usd,
            activa=True, saldo_actual=Decimal("10.00"),
        )
        pago = _pago_real(
            empresa_bimonetaria, pedido, moneda_ves, metodo_efectivo,
            Decimal("365.00"), tasa=Decimal("36.50"),
        )
        pago.id_caja_virtual = caja
        _con_interfaz_legacy(pago, moneda_iso="VES", metodo_str="EFECTIVO")

        crear_transaccion_financiera_pago(pago, user_a)

        mov = MovimientoCajaBanco.objects.get()
        assert mov.monto == Decimal("10.00")  # 365 / 36.50
        assert mov.id_moneda == moneda_usd
        caja.refresh_from_db()
        assert caja.saldo_actual == Decimal("20.00")

    def test_caja_en_moneda_tercera_multiplica_por_tasa(
        self, empresa_bimonetaria, pedido, moneda_usd, moneda_ves, metodo_efectivo, user_a
    ):
        """Conversión "otra" (ni base→país ni país→base) → monto * pago.tasa."""
        moneda_eur = Moneda.objects.create(
            nombre="Euro", codigo_iso="EUR", simbolo="€", tipo_moneda="fiat", es_generica=True
        )
        caja = Caja.objects.create(
            empresa=empresa_bimonetaria, nombre="Caja EUR", moneda=moneda_eur,
            activa=True, saldo_actual=Decimal("0.00"),
        )
        pago = _pago_real(
            empresa_bimonetaria, pedido, moneda_usd, metodo_efectivo,
            Decimal("10.00"), tasa=Decimal("0.90"),
        )
        pago.id_caja_virtual = caja
        _con_interfaz_legacy(pago, moneda_iso="USD", metodo_str="EFECTIVO")

        crear_transaccion_financiera_pago(pago, user_a)

        mov = MovimientoCajaBanco.objects.get()
        assert mov.monto == Decimal("9.00")  # 10 * 0.90
        assert mov.id_moneda == moneda_eur

    def test_caja_seleccionada_inactiva_se_descarta(
        self, empresa_bimonetaria, pedido, moneda_usd, moneda_ves, user_a
    ):
        """
        Caja seleccionada inactiva → no pasa la validación, ni se encuentra por
        ID (activa=True) → para TARJETA cae al flujo de datafono (sin datafono
        configurado: transacción sin caja/cuenta y sin movimiento).
        """
        metodo_tarjeta = MetodoPago.objects.create(
            empresa=empresa_bimonetaria, nombre_metodo="TDC", tipo_metodo="TARJETA"
        )
        caja_inactiva = Caja.objects.create(
            empresa=empresa_bimonetaria, nombre="Caja Muerta", moneda=moneda_usd, activa=False
        )
        pago = _pago_real(
            empresa_bimonetaria, pedido, moneda_usd, metodo_tarjeta,
            Decimal("20.00"), tasa=Decimal("36.00"),
        )
        pago.id_caja_virtual = caja_inactiva
        _con_interfaz_legacy(pago, moneda_iso="USD", metodo_str="TARJETA")

        crear_transaccion_financiera_pago(pago, user_a)

        trans = TransaccionFinanciera.objects.get()
        assert trans.id_caja is None
        assert trans.id_cuenta_bancaria is None
        assert MovimientoCajaBanco.objects.count() == 0


# ── Cuenta bancaria automática (métodos electrónicos) ────────────────────────

class TestCuentaBancaria:
    def test_electronico_encuentra_cuenta_y_actualiza_saldo(
        self, empresa_bimonetaria, pedido, moneda_usd, moneda_ves, user_a
    ):
        metodo = MetodoPago.objects.create(
            empresa=empresa_bimonetaria, nombre_metodo="Transferencia", tipo_metodo="ELECTRONICO"
        )
        cuenta = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_bimonetaria,
            nombre_banco="Banco Uno",
            numero_cuenta="0102-0001-0001",
            tipo_cuenta="CORRIENTE",
            id_moneda=moneda_usd,
            saldo_actual=Decimal("50.00"),
            activo=True,
        )
        cuenta.metodos_pago.add(metodo)
        cuenta.monedas.add(moneda_usd)
        TasaCambio.objects.create(
            id_empresa=empresa_bimonetaria,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_ves,
            tipo_tasa="OFICIAL_BCV",
            valor_tasa=Decimal("40.00000000"),
            fecha_tasa=datetime.date.today(),
        )
        pago = _pago_real(
            empresa_bimonetaria, pedido, moneda_usd, metodo, Decimal("25.00"), tasa=Decimal("40.00")
        )
        # Cubre también la rama de cuenta preseleccionada por el usuario
        pago.id_cuenta_bancaria = cuenta
        _con_interfaz_legacy(pago, moneda_iso="USD", metodo_str="Transferencia")

        crear_transaccion_financiera_pago(pago, user_a)

        trans = TransaccionFinanciera.objects.get()
        assert trans.id_cuenta_bancaria == cuenta
        assert trans.id_caja is None
        assert trans.monto_moneda_pais == Decimal("1000.00")  # 25 * 40

        mov = MovimientoCajaBanco.objects.get()
        assert mov.monto == Decimal("25.00")
        assert mov.saldo_anterior == Decimal("50.00")
        assert mov.saldo_nuevo == Decimal("75.00")
        cuenta.refresh_from_db()
        assert cuenta.saldo_actual == Decimal("75.00")

    def test_fallback_cuenta_solo_por_metodo_convierte_a_moneda_cuenta(
        self, empresa_bimonetaria, pedido, moneda_usd, moneda_ves, user_a
    ):
        """
        Sin cuenta que matchee método+moneda → fallback por método. La cuenta
        está en VES (país) y el pago en USD (base) → movimiento = monto * tasa.
        """
        metodo = MetodoPago.objects.create(
            empresa=empresa_bimonetaria, nombre_metodo="Pago Móvil", tipo_metodo="ELECTRONICO"
        )
        cuenta = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_bimonetaria,
            nombre_banco="Banco Bs",
            numero_cuenta="0102-0003-0003",
            tipo_cuenta="CORRIENTE",
            id_moneda=moneda_ves,
            saldo_actual=Decimal("0.00"),
            activo=True,
        )
        cuenta.metodos_pago.add(metodo)  # sin M2M de monedas
        pago = _pago_real(
            empresa_bimonetaria, pedido, moneda_usd, metodo, Decimal("2.00"), tasa=Decimal("36.50")
        )
        _con_interfaz_legacy(pago, moneda_iso="USD", metodo_str="Pago Móvil")

        crear_transaccion_financiera_pago(pago, user_a)

        mov = MovimientoCajaBanco.objects.get()
        assert mov.id_cuenta_bancaria == cuenta
        assert mov.monto == Decimal("73.00")  # 2 * 36.50 (base→país)
        assert mov.id_moneda == moneda_ves
        cuenta.refresh_from_db()
        assert cuenta.saldo_actual == Decimal("73.00")

    def test_fallback_cuenta_solo_por_moneda(
        self, empresa_bimonetaria, pedido, moneda_usd, moneda_ves, user_a
    ):
        """Sin cuenta por método → fallback por moneda del pago."""
        metodo = MetodoPago.objects.create(
            empresa=empresa_bimonetaria, nombre_metodo="Zelle", tipo_metodo="ELECTRONICO"
        )
        cuenta = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_bimonetaria,
            nombre_banco="Banco USD",
            numero_cuenta="0102-0004-0004",
            tipo_cuenta="AHORRO",
            id_moneda=moneda_usd,
            saldo_actual=Decimal("0.00"),
            activo=True,
        )
        cuenta.monedas.add(moneda_usd)  # sin M2M de métodos
        pago = _pago_real(
            empresa_bimonetaria, pedido, moneda_usd, metodo, Decimal("7.00"), tasa=Decimal("36.00")
        )
        _con_interfaz_legacy(pago, moneda_iso="USD", metodo_str="Zelle")

        crear_transaccion_financiera_pago(pago, user_a)

        trans = TransaccionFinanciera.objects.get()
        assert trans.id_cuenta_bancaria == cuenta
        mov = MovimientoCajaBanco.objects.get()
        assert mov.monto == Decimal("7.00")

    def test_electronico_sin_cuenta_no_crea_movimiento(
        self, empresa_bimonetaria, pedido, moneda_usd, moneda_ves, user_a
    ):
        """Sin ninguna cuenta bancaria → transacción sin cuenta y sin movimiento."""
        metodo = MetodoPago.objects.create(
            empresa=empresa_bimonetaria, nombre_metodo="Cripto", tipo_metodo="ELECTRONICO"
        )
        pago = _pago_real(
            empresa_bimonetaria, pedido, moneda_usd, metodo, Decimal("9.00"), tasa=Decimal("36.00")
        )
        _con_interfaz_legacy(pago, moneda_iso="USD", metodo_str="Cripto")

        crear_transaccion_financiera_pago(pago, user_a)

        trans = TransaccionFinanciera.objects.get()
        assert trans.id_cuenta_bancaria is None and trans.id_caja is None
        assert MovimientoCajaBanco.objects.count() == 0

    def test_cuenta_seleccionada_inactiva_se_descarta(
        self, empresa_bimonetaria, pedido, moneda_usd, moneda_ves, user_a
    ):
        """Cuenta preseleccionada inactiva → no pasa validación ni lookup por ID."""
        metodo = MetodoPago.objects.create(
            empresa=empresa_bimonetaria, nombre_metodo="Transferencia2", tipo_metodo="ELECTRONICO"
        )
        cuenta_inactiva = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_bimonetaria,
            nombre_banco="Banco Cerrado",
            numero_cuenta="0102-0005-0005",
            tipo_cuenta="CORRIENTE",
            id_moneda=moneda_usd,
            activo=False,
        )
        pago = _pago_real(
            empresa_bimonetaria, pedido, moneda_usd, metodo, Decimal("4.00"), tasa=Decimal("36.00")
        )
        pago.id_cuenta_bancaria = cuenta_inactiva
        _con_interfaz_legacy(pago, moneda_iso="USD", metodo_str="Transferencia2")

        crear_transaccion_financiera_pago(pago, user_a)

        trans = TransaccionFinanciera.objects.get()
        assert trans.id_cuenta_bancaria is None  # la inactiva no se usa
        assert MovimientoCajaBanco.objects.count() == 0


# ── Datafono (tarjeta) ────────────────────────────────────────────────────────

class TestDatafono:
    def test_tarjeta_crea_transaccion_datafono_sin_movimiento(
        self, empresa_bimonetaria, pedido, moneda_usd, moneda_ves, user_a
    ):
        from apps.core.models import Sucursal

        metodo = MetodoPago.objects.create(
            empresa=empresa_bimonetaria, nombre_metodo="Punto de Venta", tipo_metodo="TARJETA"
        )
        sucursal = Sucursal.objects.create(
            id_empresa=empresa_bimonetaria, nombre="Principal", codigo_sucursal="SUC1"
        )
        cuenta_asociada = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_bimonetaria,
            nombre_banco="Banco POS",
            numero_cuenta="0102-0002-0002",
            tipo_cuenta="CORRIENTE",
            id_moneda=moneda_usd,
            activo=True,
        )
        datafono = Datafono.objects.create(
            id_empresa=empresa_bimonetaria,
            id_sucursal=sucursal,
            nombre="POS-1",
            serial="SER-001",
            id_cuenta_bancaria_asociada=cuenta_asociada,
            activo=True,
        )
        pago = _pago_real(
            empresa_bimonetaria, pedido, moneda_usd, metodo, Decimal("80.00"), tasa=Decimal("36.00")
        )
        _con_interfaz_legacy(pago, moneda_iso="USD", metodo_str="TARJETA")

        crear_transaccion_financiera_pago(pago, user_a)

        trans = TransaccionFinanciera.objects.get()
        assert trans.monto_transaccion == Decimal("80.00")
        assert trans.monto_moneda_pais == Decimal("2880.00")  # fallback 80 * 36
        assert trans.id_caja is None and trans.id_cuenta_bancaria is None

        td = TransaccionDatafono.objects.get()
        assert td.id_datafono == datafono
        assert td.monto == Decimal("80.00")
        assert td.referencia_bancaria == "REF-001"
        assert td.id_transaccion_financiera_origen == trans

        # Sin caja ni cuenta → no se crea movimiento ni se toca saldo
        assert MovimientoCajaBanco.objects.count() == 0
        cuenta_asociada.refresh_from_db()
        assert cuenta_asociada.saldo_actual == Decimal("0.00")

    def test_datafono_seleccionado_por_usuario_y_banco_destino(
        self, empresa_bimonetaria, pedido, moneda_usd, moneda_ves, user_a
    ):
        """Datafono y banco destino preseleccionados válidos → se usan tal cual."""
        from apps.core.models import Sucursal

        metodo = MetodoPago.objects.create(
            empresa=empresa_bimonetaria, nombre_metodo="POS Manual", tipo_metodo="TARJETA"
        )
        sucursal = Sucursal.objects.create(
            id_empresa=empresa_bimonetaria, nombre="Sucursal Dos", codigo_sucursal="SUC2"
        )
        banco = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_bimonetaria,
            nombre_banco="Banco Destino",
            numero_cuenta="0102-0006-0006",
            tipo_cuenta="CORRIENTE",
            id_moneda=moneda_usd,
            activo=True,
        )
        datafono = Datafono.objects.create(
            id_empresa=empresa_bimonetaria,
            id_sucursal=sucursal,
            nombre="POS-Manual",
            serial="SER-002",
            activo=True,
        )
        pago = _pago_real(
            empresa_bimonetaria, pedido, moneda_usd, metodo, Decimal("15.00"), tasa=Decimal("36.00")
        )
        pago.id_datafono = datafono
        pago.banco_destino = banco
        _con_interfaz_legacy(pago, moneda_iso="USD", metodo_str="TARJETA")

        crear_transaccion_financiera_pago(pago, user_a)

        td = TransaccionDatafono.objects.get()
        assert td.id_datafono == datafono
        assert td.monto == Decimal("15.00")

    def test_datafono_seleccionado_inactivo_lanza_validationerror(
        self, empresa_bimonetaria, pedido, moneda_usd, moneda_ves, user_a
    ):
        """
        BUG: con un datafono preseleccionado inválido (inactivo), el "fallback"
        hace ``Datafono.objects.get(id_datafono=pago.id_datafono, ...)`` pasando
        la INSTANCIA (no el ID) al lookup UUID → django ValidationError
        («no es un UUID válido»), que el except (DoesNotExist, ValueError) no
        captura → revienta en vez de caer al datafono automático.
        """
        from django.core.exceptions import ValidationError

        from apps.core.models import Sucursal

        metodo = MetodoPago.objects.create(
            empresa=empresa_bimonetaria, nombre_metodo="POS Auto", tipo_metodo="TARJETA"
        )
        sucursal = Sucursal.objects.create(
            id_empresa=empresa_bimonetaria, nombre="Sucursal Tres", codigo_sucursal="SUC3"
        )
        datafono_inactivo = Datafono.objects.create(
            id_empresa=empresa_bimonetaria,
            id_sucursal=sucursal,
            nombre="POS-Roto",
            serial="SER-003",
            activo=False,
        )
        Datafono.objects.create(
            id_empresa=empresa_bimonetaria,
            id_sucursal=sucursal,
            nombre="POS-Vivo",
            serial="SER-004",
            activo=True,
        )
        pago = _pago_real(
            empresa_bimonetaria, pedido, moneda_usd, metodo, Decimal("30.00"), tasa=Decimal("36.00")
        )
        pago.id_datafono = datafono_inactivo
        _con_interfaz_legacy(pago, moneda_iso="USD", metodo_str="TARJETA")

        with pytest.raises(ValidationError):
            crear_transaccion_financiera_pago(pago, user_a)
        # Nunca llega a usar el datafono activo ni a crear nada
        assert TransaccionDatafono.objects.count() == 0
        assert TransaccionFinanciera.objects.count() == 0
