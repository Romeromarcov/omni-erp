"""
Backfill de cobertura — apps/finanzas/serializers.py (plan "Cero Dudas", COV/finanzas).

Ejercita los serializers directamente (sin pasar por la vista) con un request
mínimo en el contexto, cubriendo:

- MonedaSerializer: validaciones de código ISO (crypto/fiat), permisos de
  superusuario, unicidad por empresa, create/update que fuerzan empresa y flags,
  to_representation que oculta campos sensibles.
- MetodoPagoSerializer: validaciones de genéricos/públicos, unicidad, reglas de
  monedas (EFECTIVO/CHEQUE), create con sincronización de MetodoPagoEmpresaActiva,
  get_aplicado (fuzzy matching).
- TransaccionFinancieraSerializer: validate (métodos/monedas permitidos por caja
  y cuenta), create completo (mapeo monto_base, cálculo de monto_moneda_pais con
  tasa del día, creación de MovimientoCajaBanco) — todo con Decimal exacto.
- MonedaEmpresaActivaSerializer / MetodoPagoEmpresaActivaSerializer: create por
  UUID, es_base/es_pais.
- Serializers de lectura: Pago, Deposito/Sesion/TransaccionDatafono,
  CajaFisica, SesionCajaFisica, CajaVirtualAsociada, DatafonoAsociado,
  CajaUsuario/CajaVirtualUsuario, PlantillaMaestro, CajaVirtualDisponible.
"""
import datetime
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone
from rest_framework import serializers as drf_serializers

from apps.finanzas.models import (
    Caja,
    CajaUsuario,
    CajaVirtualUsuario,
    CuentaBancariaEmpresa,
    Datafono,
    MetodoPago,
    MetodoPagoEmpresaActiva,
    Moneda,
    MonedaEmpresaActiva,
    MovimientoCajaBanco,
    Pago,
    PlantillaMaestroCajasVirtuales,
    SesionCajaFisica,
    SesionDatafono,
    TasaCambio,
    TransaccionDatafono,
    TransaccionFinanciera,
    cerrar_sesion_datafono,
    registrar_pago_tarjeta,
)
from apps.finanzas.serializers import (
    CajaFisicaSerializer,
    CajaSerializer,
    CajaUsuarioSerializer,
    CajaVirtualAsociadaSerializer,
    CajaVirtualDisponibleSerializer,
    CajaVirtualUsuarioSerializer,
    DatafonoAsociadoSerializer,
    DatafonoSerializer,
    DepositoDatafonoSerializer,
    MetodoPagoEmpresaActivaSerializer,
    MetodoPagoSerializer,
    MonedaEmpresaActivaSerializer,
    MonedaSerializer,
    PagoSerializer,
    PlantillaMaestroCajasVirtualesSerializer,
    SesionCajaFisicaSerializer,
    SesionDatafonoSerializer,
    TransaccionDatafonoSerializer,
    TransaccionFinancieraSerializer,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def ctx(user):
    """Contexto de serializer con un request real (reverse() necesita
    build_absolute_uri) y el usuario autenticado inyectado."""
    from rest_framework.test import APIRequestFactory

    request = APIRequestFactory().get("/")
    request.user = user
    return {"request": request}


@pytest.fixture
def superuser(db, empresa_a):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.create_user(
        username="super_omni", password="x", email="super@omni.com", is_active=True
    )
    user.es_superusuario_omni = True
    user.save()
    return user


@pytest.fixture
def sucursal_a(empresa_a):
    from apps.core.models import Sucursal

    return Sucursal.objects.create(
        id_empresa=empresa_a, nombre="Sucursal Centro", codigo_sucursal="SC01"
    )


@pytest.fixture
def metodo_a(empresa_a):
    return MetodoPago.objects.create(
        nombre_metodo="Zelle Empresa A", tipo_metodo="ELECTRONICO", empresa=empresa_a
    )


# ── MonedaSerializer ─────────────────────────────────────────────────────────

class TestMonedaSerializer:
    def test_crypto_codigo_iso_corto_invalido(self, user_a):
        s = MonedaSerializer(
            data={"nombre": "Bitcoin", "codigo_iso": "BTC", "simbolo": "₿",
                  "tipo_moneda": "crypto"},
            context=ctx(user_a),
        )
        assert not s.is_valid()
        assert s.errors["codigo_iso"] == [
            "Para monedas cripto, el código ISO debe tener 4 o 5 caracteres."
        ]

    def test_fiat_codigo_iso_largo_invalido(self, user_a):
        s = MonedaSerializer(
            data={"nombre": "Dólar Largo", "codigo_iso": "USDX", "simbolo": "$",
                  "tipo_moneda": "fiat"},
            context=ctx(user_a),
        )
        assert not s.is_valid()
        assert s.errors["codigo_iso"] == [
            "Para monedas fiat u otro, el código ISO debe tener máximo 3 caracteres."
        ]

    def test_usuario_normal_no_puede_marcar_publica(self, user_a):
        s = MonedaSerializer(
            data={"nombre": "Euro", "codigo_iso": "EUR", "simbolo": "€",
                  "tipo_moneda": "fiat", "es_publica": True},
            context=ctx(user_a),
        )
        assert not s.is_valid()
        assert s.errors["non_field_errors"] == [
            "Solo el superusuario puede crear o modificar monedas genéricas, públicas o de otra empresa."
        ]

    def test_usuario_normal_no_modifica_moneda_generica(self, user_a, moneda_usd):
        s = MonedaSerializer(
            instance=moneda_usd, data={"nombre": "Dólar Hackeado"}, partial=True,
            context=ctx(user_a),
        )
        assert not s.is_valid()
        assert s.errors["non_field_errors"] == [
            "No puede modificar una moneda genérica del sistema."
        ]

    def test_codigo_iso_duplicado_misma_empresa(self, superuser, empresa_a):
        # El UniqueValidator de campo (codigo_iso unique=True en el modelo)
        # corta antes que validate() vía is_valid(); se invoca validate()
        # directo para cubrir la regla de unicidad por empresa.
        Moneda.objects.create(
            nombre="Peso A", codigo_iso="PSA", simbolo="P", tipo_moneda="fiat",
            empresa=empresa_a,
        )
        s = MonedaSerializer(context=ctx(superuser))
        with pytest.raises(drf_serializers.ValidationError) as exc:
            s.validate({"nombre": "Peso A bis", "codigo_iso": "PSA",
                        "tipo_moneda": "fiat", "empresa": empresa_a})
        assert exc.value.detail == {
            "codigo_iso": "Ya existe una moneda con este código ISO para esta empresa."
        }

    def test_create_usuario_normal_fuerza_empresa_y_flags(self, user_a, empresa_a):
        s = MonedaSerializer(
            data={"nombre": "Peso Local", "codigo_iso": "PSL", "simbolo": "P",
                  "tipo_moneda": "fiat"},
            context=ctx(user_a),
        )
        assert s.is_valid(), s.errors
        moneda = s.save()
        assert moneda.empresa == empresa_a
        assert moneda.es_generica is False
        assert moneda.es_publica is False

    def test_to_representation_oculta_campos_para_usuario_normal(self, user_a, moneda_usd):
        rep = MonedaSerializer(moneda_usd, context=ctx(user_a)).data
        assert "es_generica" not in rep
        assert "empresa" not in rep
        assert rep["codigo_iso"] == "USD"

    def test_to_representation_muestra_campos_para_superusuario(self, superuser, moneda_usd):
        rep = MonedaSerializer(moneda_usd, context=ctx(superuser)).data
        assert rep["es_generica"] is True
        assert rep["empresa"] is None

    def test_update_usuario_normal_no_puede_cambiar_empresa(
        self, user_a, empresa_a, empresa_b
    ):
        moneda = Moneda.objects.create(
            nombre="Privada", codigo_iso="PRV", simbolo="P", tipo_moneda="fiat",
            empresa=empresa_a,
        )
        s = MonedaSerializer(context=ctx(user_a))
        actualizada = s.update(moneda, {"empresa": empresa_b, "es_publica": True,
                                        "nombre": "Privada v2"})
        assert actualizada.nombre == "Privada v2"
        assert actualizada.empresa == empresa_a
        assert actualizada.es_publica is False


# ── MetodoPagoSerializer ─────────────────────────────────────────────────────

class TestMetodoPagoSerializer:
    def test_usuario_normal_no_modifica_generico(self, user_a):
        generico = MetodoPago.objects.create(
            nombre_metodo="Efectivo Global", tipo_metodo="EFECTIVO", es_generico=True
        )
        s = MetodoPagoSerializer(
            instance=generico, data={"nombre_metodo": "Hack"}, partial=True,
            context=ctx(user_a),
        )
        assert not s.is_valid()
        assert s.errors["non_field_errors"] == [
            "No puede modificar un método de pago genérico del sistema."
        ]

    def test_usuario_normal_no_puede_marcar_publico(self, user_a):
        s = MetodoPagoSerializer(
            data={"nombre_metodo": "Nuevo", "tipo_metodo": "OTRO", "es_publico": True},
            context=ctx(user_a),
        )
        assert not s.is_valid()
        assert s.errors["non_field_errors"] == [
            "Solo el superusuario puede crear o modificar métodos de pago genéricos, públicos o de otra empresa."
        ]

    def test_nombre_duplicado_misma_empresa_y_tipo(self, superuser, empresa_a, metodo_a):
        s = MetodoPagoSerializer(
            data={"nombre_metodo": "Zelle Empresa A", "tipo_metodo": "ELECTRONICO",
                  "empresa": str(empresa_a.id_empresa)},
            context=ctx(superuser),
        )
        assert not s.is_valid()
        assert s.errors["nombre_metodo"] == [
            "Ya existe un método de pago con este nombre para esta empresa y tipo."
        ]

    def test_efectivo_no_acepta_crypto(self, user_a):
        crypto = Moneda.objects.create(
            nombre="Tether", codigo_iso="USDT", simbolo="₮", tipo_moneda="crypto"
        )
        s = MetodoPagoSerializer(
            data={"nombre_metodo": "Efectivo X", "tipo_metodo": "EFECTIVO",
                  "monedas": [str(crypto.id_moneda)]},
            context=ctx(user_a),
        )
        assert not s.is_valid()
        assert s.errors["non_field_errors"] == [
            "No se puede asociar la moneda Tether (USDT) a 'EFECTIVO'. Solo monedas fiat están permitidas."
        ]

    def test_efectivo_debe_incluir_todas_las_fiat_publicas(self, user_a, moneda_usd):
        fiat_publica = Moneda.objects.create(
            nombre="Bolívar", codigo_iso="VES", simbolo="Bs", tipo_moneda="fiat",
            es_publica=True,
        )
        otra_fiat = Moneda.objects.create(
            nombre="Peso", codigo_iso="COP", simbolo="$", tipo_moneda="fiat"
        )
        s = MetodoPagoSerializer(
            data={"nombre_metodo": "Efectivo Y", "tipo_metodo": "EFECTIVO",
                  "monedas": [str(otra_fiat.id_moneda)]},
            context=ctx(user_a),
        )
        assert not s.is_valid()
        assert s.errors["non_field_errors"] == [
            "El método de pago 'Efectivo' debe estar asociado a todas las monedas fiat públicas."
        ]

    def test_cheque_solo_fiat(self, user_a):
        otra = Moneda.objects.create(
            nombre="Token Raro", codigo_iso="TKR", simbolo="T", tipo_moneda="otro"
        )
        s = MetodoPagoSerializer(
            data={"nombre_metodo": "Cheque X", "tipo_metodo": "CHEQUE",
                  "monedas": [str(otra.id_moneda)]},
            context=ctx(user_a),
        )
        assert not s.is_valid()
        assert s.errors["non_field_errors"] == [
            "No se puede asociar la moneda Token Raro a 'Cheque'. Solo monedas fiat están permitidas."
        ]

    def test_create_fuerza_empresa_y_sincroniza_activos(self, user_a, empresa_a):
        s = MetodoPagoSerializer(
            data={"nombre_metodo": "Pago Móvil A", "tipo_metodo": "ELECTRONICO"},
            context=ctx(user_a),
        )
        assert s.is_valid(), s.errors
        metodo = s.save()
        assert metodo.empresa == empresa_a
        activa = MetodoPagoEmpresaActiva.objects.get(empresa=empresa_a, metodo_pago=metodo)
        assert activa.activa is True

    def test_update_resincroniza_activos(self, user_a, empresa_a, metodo_a):
        MetodoPagoEmpresaActiva.objects.filter(metodo_pago=metodo_a).delete()
        # NOTA: hay que enviar monedas=[] — si el payload no trae monedas,
        # validate() itera el ManyRelatedManager y revienta con TypeError
        # (bug documentado en el reporte).
        s = MetodoPagoSerializer(
            instance=metodo_a, data={"nombre_metodo": "Zelle A v2", "monedas": []},
            partial=True, context=ctx(user_a),
        )
        assert s.is_valid(), s.errors
        metodo = s.save()
        assert metodo.nombre_metodo == "Zelle A v2"
        assert MetodoPagoEmpresaActiva.objects.filter(
            empresa=empresa_a, metodo_pago=metodo
        ).exists()

    def test_get_aplicado_sin_contexto_devuelve_false(self, user_a, metodo_a):
        rep = MetodoPagoSerializer(metodo_a, context=ctx(user_a)).data
        assert rep["aplicado"] is False

    def test_get_aplicado_fuzzy_true_y_false(self, user_a, empresa_a, empresa_b, metodo_a):
        pytest.importorskip("rapidfuzz")  # dependencia opcional en el entorno dev
        metodo_b = MetodoPago.objects.create(
            nombre_metodo="Zelle Empresa B", tipo_metodo="ELECTRONICO", empresa=empresa_b
        )
        context = ctx(user_a)
        context["id_empresa_actual"] = str(empresa_a.id_empresa)
        # "Zelle Empresa B" ~ "Zelle Empresa A" → fuzzy match → aplicado True
        rep = MetodoPagoSerializer(metodo_b, context=context).data
        assert rep["aplicado"] is True
        distinto = MetodoPago.objects.create(
            nombre_metodo="Criptopago XYZ", tipo_metodo="OTRO", empresa=empresa_b
        )
        rep2 = MetodoPagoSerializer(distinto, context=context).data
        assert rep2["aplicado"] is False


# ── TransaccionFinancieraSerializer ──────────────────────────────────────────

@pytest.fixture
def caja_virtual_a(empresa_a, moneda_usd):
    return Caja.objects.create(
        empresa=empresa_a, nombre="Caja Virtual A", moneda=moneda_usd,
        tipo_caja="REGISTRADORA",
    )


@pytest.fixture
def cuenta_a(empresa_a, moneda_usd):
    return CuentaBancariaEmpresa.objects.create(
        id_empresa=empresa_a, nombre_banco="Banco A", numero_cuenta="0102-99",
        tipo_cuenta="CORRIENTE", id_moneda=moneda_usd,
    )


def _tf_data(empresa, moneda, metodo, user, **extra):
    data = {
        "id_empresa": str(empresa.id_empresa),
        "fecha_hora_transaccion": timezone.now().isoformat(),
        "tipo_transaccion": "INGRESO",
        "monto_transaccion": "100.00",
        "id_moneda_transaccion": str(moneda.id_moneda),
        "monto_base_empresa": "100.00",
        "id_metodo_pago": str(metodo.id_metodo_pago),
        "id_usuario_registro": user.pk,
    }
    data.update(extra)
    return data


class TestTransaccionFinancieraSerializer:
    def test_metodo_no_permitido_en_caja(self, user_a, empresa_a, moneda_usd,
                                          metodo_a, caja_virtual_a):
        otro_metodo = MetodoPago.objects.create(
            nombre_metodo="Solo Caja", tipo_metodo="EFECTIVO", empresa=empresa_a
        )
        caja_virtual_a.metodos_pago.add(otro_metodo)
        s = TransaccionFinancieraSerializer(
            data=_tf_data(empresa_a, moneda_usd, metodo_a, user_a,
                          id_caja=str(caja_virtual_a.id_caja)),
            context=ctx(user_a),
        )
        assert not s.is_valid()
        assert s.errors["id_metodo_pago"] == [
            "El método de pago no está permitido para la caja seleccionada."
        ]

    def test_moneda_distinta_a_la_caja(self, user_a, empresa_a, moneda_usd,
                                        metodo_a, caja_virtual_a):
        otra_moneda = Moneda.objects.create(
            nombre="Bolívar", codigo_iso="VES", simbolo="Bs", tipo_moneda="fiat"
        )
        caja_virtual_a.metodos_pago.add(metodo_a)  # pasa el check de método
        s = TransaccionFinancieraSerializer(
            data=_tf_data(empresa_a, otra_moneda, metodo_a, user_a,
                          id_caja=str(caja_virtual_a.id_caja)),
            context=ctx(user_a),
        )
        assert not s.is_valid()
        assert s.errors["id_moneda_transaccion"] == [
            "La moneda no coincide con la moneda de la caja."
        ]

    def test_metodo_no_permitido_en_cuenta_bancaria(self, user_a, empresa_a, moneda_usd,
                                                     metodo_a, cuenta_a):
        otro_metodo = MetodoPago.objects.create(
            nombre_metodo="Solo Banco", tipo_metodo="ELECTRONICO", empresa=empresa_a
        )
        cuenta_a.metodos_pago.add(otro_metodo)
        s = TransaccionFinancieraSerializer(
            data=_tf_data(empresa_a, moneda_usd, metodo_a, user_a,
                          id_cuenta_bancaria=str(cuenta_a.id_cuenta_bancaria)),
            context=ctx(user_a),
        )
        assert not s.is_valid()
        assert s.errors["id_metodo_pago"] == [
            "El método de pago no está permitido para la cuenta bancaria seleccionada."
        ]

    def test_moneda_distinta_a_la_cuenta_bancaria(self, user_a, empresa_a, metodo_a, cuenta_a):
        otra_moneda = Moneda.objects.create(
            nombre="Euro", codigo_iso="EUR", simbolo="€", tipo_moneda="fiat"
        )
        cuenta_a.metodos_pago.add(metodo_a)  # pasa el check de método
        s = TransaccionFinancieraSerializer(
            data=_tf_data(empresa_a, otra_moneda, metodo_a, user_a,
                          id_cuenta_bancaria=str(cuenta_a.id_cuenta_bancaria)),
            context=ctx(user_a),
        )
        assert not s.is_valid()
        assert s.errors["id_moneda_transaccion"] == [
            "La moneda no coincide con la moneda de la cuenta bancaria."
        ]

    def test_moneda_no_permitida_para_el_metodo(self, user_a, empresa_a, moneda_usd, metodo_a):
        otra_moneda = Moneda.objects.create(
            nombre="Euro", codigo_iso="EUR", simbolo="€", tipo_moneda="fiat"
        )
        metodo_a.monedas.add(otra_moneda)
        s = TransaccionFinancieraSerializer(
            data=_tf_data(empresa_a, moneda_usd, metodo_a, user_a),
            context=ctx(user_a),
        )
        assert not s.is_valid()
        assert s.errors["id_moneda_transaccion"] == [
            "La moneda no está permitida para el método de pago seleccionado."
        ]

    def test_create_calcula_monto_moneda_pais_con_tasa_del_dia(
        self, user_a, empresa_a, moneda_usd, metodo_a
    ):
        metodo_a.monedas.add(moneda_usd)  # el método debe aceptar la moneda
        moneda_ves = Moneda.objects.create(
            nombre="Bolívar", codigo_iso="VES", simbolo="Bs", tipo_moneda="fiat"
        )
        empresa_a.id_moneda_pais = moneda_ves
        empresa_a.save()
        TasaCambio.objects.create(
            id_empresa=empresa_a, id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_ves, tipo_tasa="OFICIAL_BCV",
            valor_tasa=Decimal("36.50000000"), fecha_tasa=datetime.date.today(),
        )
        s = TransaccionFinancieraSerializer(
            data=_tf_data(empresa_a, moneda_usd, metodo_a, user_a,
                          monto_base="99.00", descripcion="venta del día"),
            context=ctx(user_a),
        )
        assert s.is_valid(), s.errors
        tf = s.save()
        tf.refresh_from_db()
        # monto_base (write_only) pisa monto_base_empresa
        assert tf.monto_base_empresa == Decimal("99.00")
        assert tf.id_moneda_pais_empresa == moneda_ves
        assert tf.monto_moneda_pais == Decimal("3650.00")
        # Se crea el MovimientoCajaBanco asociado, con valores exactos
        mov = MovimientoCajaBanco.objects.get(id_transaccion_financiera=tf)
        assert mov.tipo_movimiento == "INGRESO"
        assert mov.monto == Decimal("100.00")
        assert mov.concepto == "venta del día"
        assert mov.id_usuario_registro == user_a

    def test_create_sin_tasa_deja_monto_pais_none(self, user_a, empresa_a, moneda_usd, metodo_a):
        metodo_a.monedas.add(moneda_usd)
        moneda_ves = Moneda.objects.create(
            nombre="Bolívar", codigo_iso="VES", simbolo="Bs", tipo_moneda="fiat"
        )
        empresa_a.id_moneda_pais = moneda_ves
        empresa_a.save()
        s = TransaccionFinancieraSerializer(
            data=_tf_data(empresa_a, moneda_usd, metodo_a, user_a,
                          tipo_transaccion="EGRESO"),
            context=ctx(user_a),
        )
        assert s.is_valid(), s.errors
        tf = s.save()
        assert tf.monto_moneda_pais is None
        mov = MovimientoCajaBanco.objects.get(id_transaccion_financiera=tf)
        assert mov.tipo_movimiento == "EGRESO"

    def test_create_respeta_monto_moneda_pais_del_frontend(
        self, user_a, empresa_a, moneda_usd, metodo_a
    ):
        metodo_a.monedas.add(moneda_usd)
        s = TransaccionFinancieraSerializer(
            data=_tf_data(empresa_a, moneda_usd, metodo_a, user_a,
                          monto_moneda_pais="777.77"),
            context=ctx(user_a),
        )
        assert s.is_valid(), s.errors
        tf = s.save()
        assert tf.monto_moneda_pais == Decimal("777.77")
        # Empresa sin id_moneda_pais → campo en None
        assert tf.id_moneda_pais_empresa is None


# ── MonedaEmpresaActiva / MetodoPagoEmpresaActiva ────────────────────────────

class TestMonedaEmpresaActivaSerializer:
    def test_create_por_uuid_y_empresa_del_usuario(self, user_a, empresa_a, moneda_usd):
        MonedaEmpresaActiva.objects.all().delete()
        s = MonedaEmpresaActivaSerializer(
            data={"empresa": str(empresa_a.id_empresa),
                  "moneda": str(moneda_usd.id_moneda), "activa": True},
            context=ctx(user_a),
        )
        assert s.is_valid(), s.errors
        instancia = s.save()
        assert instancia.empresa == empresa_a
        assert instancia.moneda == moneda_usd

    def test_create_moneda_inexistente(self, user_a, empresa_a):
        s = MonedaEmpresaActivaSerializer(
            data={"empresa": str(empresa_a.id_empresa),
                  "moneda": str(uuid.uuid4()), "activa": True},
            context=ctx(user_a),
        )
        assert s.is_valid(), s.errors
        with pytest.raises(drf_serializers.ValidationError) as exc:
            s.save()
        assert exc.value.detail == {"moneda": "Moneda no encontrada"}

    def test_es_base_y_es_pais(self, empresa_a, moneda_usd):
        moneda_ves = Moneda.objects.create(
            nombre="Bolívar", codigo_iso="VES", simbolo="Bs", tipo_moneda="fiat"
        )
        empresa_a.id_moneda_pais = moneda_ves
        empresa_a.save()
        activa_ves = MonedaEmpresaActiva.objects.get(empresa=empresa_a, moneda=moneda_ves) \
            if MonedaEmpresaActiva.objects.filter(empresa=empresa_a, moneda=moneda_ves).exists() \
            else MonedaEmpresaActiva.objects.create(empresa=empresa_a, moneda=moneda_ves)
        rep = MonedaEmpresaActivaSerializer(activa_ves).data
        assert rep["es_pais"] is True
        assert rep["moneda_codigo_iso"] == "VES"
        # es_base usa empresa.moneda_base_id, que NO existe en Empresa
        # (el campo real es id_moneda_base) → siempre False (bug documentado)
        assert rep["es_base"] is False

    def test_es_pais_false_para_otra_moneda(self, empresa_a, moneda_usd):
        activa = MonedaEmpresaActiva.objects.get_or_create(
            empresa=empresa_a, moneda=moneda_usd
        )[0]
        rep = MonedaEmpresaActivaSerializer(activa).data
        assert rep["es_pais"] is False


class TestMetodoPagoEmpresaActivaSerializer:
    def test_create_por_uuid(self, user_a, empresa_a, metodo_a):
        MetodoPagoEmpresaActiva.objects.all().delete()
        s = MetodoPagoEmpresaActivaSerializer(
            data={"empresa": str(empresa_a.id_empresa),
                  "metodo_pago": str(metodo_a.id_metodo_pago), "activa": False},
            context=ctx(user_a),
        )
        assert s.is_valid(), s.errors
        instancia = s.save()
        assert instancia.empresa == empresa_a
        assert instancia.metodo_pago == metodo_a
        assert instancia.activa is False
        rep = MetodoPagoEmpresaActivaSerializer(instancia).data
        assert rep["nombre"] == "Zelle Empresa A"


# ── Serializers de lectura: cajas, sesiones, datafonos ───────────────────────

@pytest.fixture
def datafono_a(empresa_a, sucursal_a, cuenta_a):
    return Datafono.objects.create(
        id_empresa=empresa_a, id_sucursal=sucursal_a, nombre="POS 1", serial="POS-S1",
        id_cuenta_bancaria_asociada=cuenta_a, comision_porcentaje=Decimal("2.00"),
        saldo_temporal=Decimal("55.00"),
    )


def _abrir_sesion_datafono(datafono, user):
    """Pre-crea la sesión: registrar_pago_tarjeta revienta con sesión nueva
    (default float del campo total_transacciones — bug documentado)."""
    SesionDatafono.objects.create(datafono=datafono, usuario_apertura=user)


class TestSerializersDeLectura:
    def test_caja_serializer_campos_relacionados(self, caja_virtual_a, caja_fisica_a):
        caja_virtual_a.caja_fisica = caja_fisica_a
        caja_virtual_a.save()
        rep = CajaSerializer(caja_virtual_a).data
        assert rep["empresa_nombre"] is None  # Empresa Alpha sin nombre_comercial
        assert rep["moneda_codigo_iso"] == "USD"
        assert rep["tipo_caja_display"] == "Caja Registradora Virtual"
        assert rep["caja_fisica_nombre"] == "Caja Principal Test"

    def test_caja_fisica_serializer_campos_calculados(
        self, caja_fisica_a, caja_virtual_a, datafono_a, user_a
    ):
        caja_virtual_a.caja_fisica = caja_fisica_a
        caja_virtual_a.save()
        datafono_a.id_caja_fisica = caja_fisica_a
        datafono_a.save()
        SesionCajaFisica.abrir_sesion(caja_fisica_a, user_a)
        rep = CajaFisicaSerializer(caja_fisica_a).data
        assert rep["esta_abierta"] is True
        assert rep["estado_sesion_display"] == "Abierta por user_empresa_a"
        assert rep["nombre_usuario_actual"] == "user_empresa_a"
        assert len(rep["cajas_virtuales"]) == 1
        assert rep["cajas_virtuales"][0]["nombre"] == "Caja Virtual A"
        assert len(rep["datafonos"]) == 1
        assert rep["datafonos"][0]["serial"] == "POS-S1"
        assert rep["tipo_caja_display"] == "Caja Registradora"
        assert rep["tipo_dispositivo_display"] == "Computadora Personal"

    def test_sesion_caja_fisica_serializer(self, caja_fisica_a, user_a, sucursal_a):
        caja_fisica_a.sucursal = sucursal_a
        caja_fisica_a.save()
        sesion = SesionCajaFisica.abrir_sesion(caja_fisica_a, user_a)
        rep = SesionCajaFisicaSerializer(sesion).data
        assert rep["usuario"]["username"] == "user_empresa_a"
        principal = rep["caja_fisica_principal"]
        assert principal["nombre"] == "Caja Principal Test"
        assert principal["sucursal"]["nombre"] == "Sucursal Centro"
        assert principal["sucursal"]["empresa"]["id_empresa"] == str(
            caja_fisica_a.empresa.id_empresa
        )

    def test_sesion_caja_fisica_serializer_sin_sucursal(self, caja_fisica_a, user_a):
        sesion = SesionCajaFisica.abrir_sesion(caja_fisica_a, user_a)
        rep = SesionCajaFisicaSerializer(sesion).data
        assert rep["caja_fisica_principal"]["sucursal"]["id_sucursal"] is None
        assert rep["caja_fisica_principal"]["sucursal"]["nombre"] is None

    def test_transaccion_datafono_info_de_sesion(self, datafono_a, user_a):
        _abrir_sesion_datafono(datafono_a, user_a)
        trans = registrar_pago_tarjeta(datafono_a, Decimal("10.00"), "R1", None, user_a)
        rep = TransaccionDatafonoSerializer(trans).data
        assert rep["sesion_datafono_info"]["estado"] == "ABIERTA"
        assert rep["datafono_nombre"] == "POS 1"
        assert rep["estado_display"] == "Pendiente"
        sin_sesion = TransaccionDatafono.objects.create(
            id_datafono=datafono_a, monto=Decimal("5.00")
        )
        assert TransaccionDatafonoSerializer(sin_sesion).data["sesion_datafono_info"] is None

    def test_sesion_datafono_serializer_cuenta_transacciones(self, datafono_a, user_a):
        _abrir_sesion_datafono(datafono_a, user_a)
        registrar_pago_tarjeta(datafono_a, Decimal("10.00"), "R1", None, user_a)
        registrar_pago_tarjeta(datafono_a, Decimal("20.00"), "R2", None, user_a)
        sesion = SesionDatafono.objects.get(datafono=datafono_a, estado="ABIERTA")
        rep = SesionDatafonoSerializer(sesion).data
        assert rep["cantidad_transacciones"] == 2
        assert rep["datafono_nombre"] == "POS 1"
        assert rep["usuario_apertura_nombre"] == "user_empresa_a"
        assert rep["estado_display"] == "Abierta"

    def test_deposito_datafono_serializer_infos(
        self, datafono_a, user_a, empresa_a, moneda_usd
    ):
        _abrir_sesion_datafono(datafono_a, user_a)
        registrar_pago_tarjeta(datafono_a, Decimal("100.00"), "R1", None, user_a)
        deposito = cerrar_sesion_datafono(datafono_a, user_a)
        rep = DepositoDatafonoSerializer(deposito).data
        assert rep["movimiento_banco_info"] is None
        assert rep["sesion_datafono_info"]["id_sesion"] == str(
            deposito.sesion_datafono.id_sesion
        )
        ahora = timezone.now()
        mov = MovimientoCajaBanco.objects.create(
            id_empresa=empresa_a, fecha_movimiento=ahora.date(),
            hora_movimiento=ahora.time(), tipo_movimiento="INGRESO",
            monto=Decimal("196.00"), id_moneda=moneda_usd, concepto="dep",
            saldo_anterior=Decimal("0.00"), saldo_nuevo=Decimal("196.00"),
            id_usuario_registro=user_a,
        )
        deposito.conciliar(mov, user_a)
        rep2 = DepositoDatafonoSerializer(deposito).data
        assert rep2["movimiento_banco_info"]["monto"] == Decimal("196.00")
        assert rep2["usuario_conciliacion_nombre"] == "user_empresa_a"
        assert rep2["estado_display"] == "Conciliado"

    def test_datafono_asociado_serializer(self, datafono_a):
        rep = DatafonoAsociadoSerializer(datafono_a).data
        assert rep["saldo_actual"] == Decimal("55.00")
        # Sin fecha_ultimo_cierre → usa fecha_creacion
        assert rep["ultima_conexion"] == datafono_a.fecha_creacion
        datafono_a.fecha_ultimo_cierre = timezone.now()
        rep2 = DatafonoAsociadoSerializer(datafono_a).data
        assert rep2["ultima_conexion"] == datafono_a.fecha_ultimo_cierre

    def test_caja_virtual_asociada_serializer(self, caja_virtual_a):
        rep = CajaVirtualAsociadaSerializer(caja_virtual_a).data
        assert rep["saldo_actual"] == 0
        assert rep["moneda_codigo_iso"] == "USD"
        assert rep["tipo_caja_display"] == "Caja Registradora Virtual"

    def test_caja_usuario_serializers(self, user_a, caja_virtual_a, sucursal_a):
        caja_virtual_a.sucursal = sucursal_a
        caja_virtual_a.save()
        asignacion = CajaUsuario.objects.create(usuario=user_a, caja=caja_virtual_a)
        rep = CajaUsuarioSerializer(asignacion).data
        assert rep["caja_nombre"] == "Caja Virtual A"
        assert rep["caja_moneda"] == "USD"
        assert rep["caja_sucursal"] == "Sucursal Centro"
        asignacion_v = CajaVirtualUsuario.objects.create(
            usuario=user_a, caja_virtual=caja_virtual_a, es_predeterminada=True
        )
        rep_v = CajaVirtualUsuarioSerializer(asignacion_v).data
        assert rep_v["caja_virtual_nombre"] == "Caja Virtual A"
        assert rep_v["es_predeterminada"] is True

    def test_caja_virtual_disponible_serializer_sin_request(
        self, caja_virtual_a, caja_fisica_a
    ):
        caja_virtual_a.caja_fisica = caja_fisica_a
        caja_virtual_a.save()
        rep = CajaVirtualDisponibleSerializer(caja_virtual_a, context={}).data
        assert rep["usuario"] is None
        assert rep["es_predeterminada"] is False
        assert rep["caja_nombre"] == "Caja Virtual A"
        assert rep["caja_fisica_nombre"] == "Caja Principal Test"
        assert rep["monedas"] == [str(caja_virtual_a.moneda.id_moneda)]
        assert rep["fecha_asignacion"] is not None


# ── PlantillaMaestroCajasVirtualesSerializer ─────────────────────────────────

class TestPlantillaMaestroSerializer:
    def test_representacion_monedas_y_metodos(self, empresa_a, moneda_usd, metodo_a):
        plantilla = PlantillaMaestroCajasVirtuales.objects.create(
            empresa=empresa_a, nombre="P1", moneda_base=moneda_usd
        )
        plantilla.metodos_pago_base.add(metodo_a)
        rep = PlantillaMaestroCajasVirtualesSerializer(plantilla).data
        assert rep["monedas"] == [str(moneda_usd.id_moneda)]
        assert rep["metodos_pago"] == [str(metodo_a.id_metodo_pago)]
        assert rep["nombre"] == "P1"

    def test_update_simple(self, user_a, empresa_a, moneda_usd):
        plantilla = PlantillaMaestroCajasVirtuales.objects.create(
            empresa=empresa_a, nombre="P2", moneda_base=moneda_usd
        )
        s = PlantillaMaestroCajasVirtualesSerializer(
            instance=plantilla, data={"nombre": "P2 actualizada"}, partial=True,
            context=ctx(user_a),
        )
        assert s.is_valid(), s.errors
        actualizada = s.save()
        assert actualizada.nombre == "P2 actualizada"
        # moneda_base intacta (monedas es read-only → rama monedas None)
        assert actualizada.moneda_base == moneda_usd


# ── PagoSerializer ───────────────────────────────────────────────────────────

class TestPagoSerializer:
    def test_create_asigna_usuario_registro(self, user_a, empresa_a, moneda_usd, metodo_a):
        s = PagoSerializer(
            data={
                "id_empresa": str(empresa_a.id_empresa),
                "tipo_operacion": "INGRESO",
                "tipo_documento": "AJUSTE",
                "id_documento": str(uuid.uuid4()),
                "fecha_pago": timezone.now().isoformat(),
                "monto": "150.2500",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_a.id_metodo_pago),
            },
            context={"request": SimpleNamespace(user=user_a)},
        )
        assert s.is_valid(), s.errors
        pago = s.save()
        assert pago.id_usuario_registro == user_a
        assert pago.id_empresa == empresa_a
        assert pago.monto == Decimal("150.2500")
        rep = PagoSerializer(pago).data
        assert rep["metodo_pago_nombre"] == "Zelle Empresa A"
        assert rep["moneda_codigo"] == "USD"
        assert rep["transaccion_financiera_info"] is None
        assert rep["documento_info"] is None

    def test_transaccion_financiera_info(self, user_a, empresa_a, moneda_usd, metodo_a):
        tf = TransaccionFinanciera.objects.create(
            id_empresa=empresa_a, fecha_hora_transaccion=timezone.now(),
            tipo_transaccion="INGRESO", monto_transaccion=Decimal("99.00"),
            id_moneda_transaccion=moneda_usd, monto_base_empresa=Decimal("99.00"),
            id_metodo_pago=metodo_a, id_usuario_registro=user_a,
        )
        pago = Pago.objects.create(
            id_empresa=empresa_a, tipo_operacion="INGRESO", tipo_documento="AJUSTE",
            id_documento=uuid.uuid4(), fecha_pago=timezone.now(),
            monto=Decimal("99.0000"), id_moneda=moneda_usd, id_metodo_pago=metodo_a,
            id_transaccion_financiera=tf,
        )
        info = PagoSerializer(pago).data["transaccion_financiera_info"]
        assert info["tipo_transaccion"] == "INGRESO"
        assert info["monto"] == Decimal("99.00")
        assert info["id_transaccion"] == str(tf.id_transaccion)


# ── DatafonoSerializer ───────────────────────────────────────────────────────

class TestDatafonoSerializer:
    def test_campos_relacionados(self, datafono_a, caja_fisica_a):
        datafono_a.id_caja_fisica = caja_fisica_a
        datafono_a.save()
        rep = DatafonoSerializer(datafono_a).data
        # caja_fisica_nombre tiene source correcto (id_caja_fisica.nombre)
        assert rep["caja_fisica_nombre"] == "Caja Principal Test"
        # HALLAZGO documentado: empresa_nombre / sucursal_nombre /
        # cuenta_bancaria_nombre apuntan a sources inexistentes
        # (empresa, sucursal, id_cuenta_bancaria vs los campos reales
        # id_empresa, id_sucursal, id_cuenta_bancaria_asociada) →
        # DRF los omite silenciosamente (SkipField) en la representación.
        assert "empresa_nombre" not in rep
        assert "sucursal_nombre" not in rep
        assert "cuenta_bancaria_nombre" not in rep
        assert rep["serial"] == "POS-S1"
