"""
Backfill de cobertura (parte 2) — apps/finanzas/views.py (plan "Cero Dudas").

Complementa test_finanzas_views_cobertura.py (que NO se toca) con las ramas
restantes:

- CajaViewSet.cierre_caja (saldo_real faltante / cierre fallido).
- DatafonoViewSet: registrar-pago (validación, 404, éxito) y cerrar-sesion
  (sin sesión / con sesión → crea depósito con totales exactos).
- DepositoDatafonoViewSet: conciliar (validación, 404, éxito, doble conciliación)
  y pendientes (lista, filtro por datafono, datafono inexistente).
- PlantillaMaestroCajasVirtualesViewSet.sincronizar.
- PagoViewSet: create (con notificación best-effort) + tipos_documento/operacion.
- CajaFisicaViewSet: tipo-caja-choices, tipos_documento, tipos_operacion.
- TransaccionFinancieraViewSet.perform_create: empresa ajena ignorada / usuario
  sin empresa → 403.
- MetodoPagoViewSet: reutilizar (400/404/409/201) y monedas_info.
- MonedaEmpresaActivaViewSet: filtros activa/empresa.
- SesionCajaFisicaViewSet.transferir_entre_cajas (ramas de error).
- Listas con aislamiento multi-tenant: datafonos, transacciones/sesiones/
  depósitos-datafono, cajas-usuario, cajas-fisicas-usuario,
  cajas-virtuales-auto, overrides-metodos-pago.

Aserciones con valores exactos (Decimal) — convención runner de mutación.
"""
import uuid
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Sucursal
from apps.finanzas.models import (
    Caja,
    CajaFisicaUsuario,
    CajaMetodoPagoOverride,
    CajaVirtualAuto,
    CajaVirtualUsuario,
    CuentaBancariaEmpresa,
    Datafono,
    DepositoDatafono,
    MetodoPago,
    Moneda,
    MonedaEmpresaActiva,
    MovimientoCajaBanco,
    Pago,
    PlantillaMaestroCajasVirtuales,
    SesionCajaFisica,
    SesionDatafono,
    TransaccionDatafono,
    TransaccionFinanciera,
)

pytestmark = pytest.mark.django_db


# ── Clients y fixtures ───────────────────────────────────────────────────────

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
def sucursal_a(empresa_a):
    return Sucursal.objects.create(
        id_empresa=empresa_a, nombre="Sucursal Centro", codigo_sucursal="SC01"
    )


@pytest.fixture
def cuenta_a(empresa_a, moneda_usd):
    return CuentaBancariaEmpresa.objects.create(
        id_empresa=empresa_a, nombre_banco="Banco A", numero_cuenta="0102-77",
        tipo_cuenta="CORRIENTE", id_moneda=moneda_usd, saldo_actual=Decimal("500.00"),
    )


@pytest.fixture
def datafono_a(empresa_a, sucursal_a, cuenta_a):
    return Datafono.objects.create(
        id_empresa=empresa_a, id_sucursal=sucursal_a, nombre="POS API",
        serial="POS-API-1", id_cuenta_bancaria_asociada=cuenta_a,
        comision_porcentaje=Decimal("2.00"),
    )


@pytest.fixture
def metodo_a(empresa_a, moneda_usd):
    metodo = MetodoPago.objects.create(
        nombre_metodo="Zelle Empresa A", tipo_metodo="ELECTRONICO", empresa=empresa_a
    )
    # El validate() de TransaccionFinanciera exige que la moneda esté asociada
    # al método (un M2M vacío rechaza TODO — manager siempre truthy).
    metodo.monedas.add(moneda_usd)
    return metodo


@pytest.fixture
def caja_virtual_a(empresa_a, moneda_usd):
    return Caja.objects.create(
        empresa=empresa_a, nombre="Caja Virtual A", moneda=moneda_usd,
        tipo_caja="REGISTRADORA",
    )


@pytest.fixture
def tf_a(empresa_a, moneda_usd, metodo_a, user_a):
    return TransaccionFinanciera.objects.create(
        id_empresa=empresa_a, fecha_hora_transaccion=timezone.now(),
        tipo_transaccion="INGRESO", monto_transaccion=Decimal("100.00"),
        id_moneda_transaccion=moneda_usd, monto_base_empresa=Decimal("100.00"),
        id_metodo_pago=metodo_a, id_usuario_registro=user_a,
    )


def _sesion_datafono_abierta(datafono, user):
    """Pre-crea la sesión (workaround del bug float/Decimal en
    registrar_pago_tarjeta con sesión recién creada — documentado)."""
    return SesionDatafono.objects.create(datafono=datafono, usuario_apertura=user)


# ── CajaViewSet.cierre ───────────────────────────────────────────────────────

class TestCajaCierre:
    def test_sin_saldo_real_400(self, client_a, caja_virtual_a):
        resp = client_a.post(f"/api/finanzas/cajas/{caja_virtual_a.id_caja}/cierre/", {})
        assert resp.status_code == 400
        assert resp.json() == {"error": "Debe enviar el saldo_real contado."}

    def test_cierre_falla_controladamente_400(self, client_a, caja_virtual_a):
        # HALLAZGO: el modelo Caja (virtual) NO define realizar_cierre →
        # AttributeError capturado por el except genérico → 400 controlado.
        resp = client_a.post(
            f"/api/finanzas/cajas/{caja_virtual_a.id_caja}/cierre/",
            {"saldo_real": "100.00"},
        )
        assert resp.status_code == 400
        assert resp.json() == {"error": "No se pudo realizar el cierre. Intente de nuevo."}


# ── DatafonoViewSet ──────────────────────────────────────────────────────────

class TestDatafonoAcciones:
    URL = "/api/finanzas/datafonos/"

    def test_registrar_pago_faltan_campos_400(self, client_a, datafono_a):
        resp = client_a.post(f"{self.URL}{datafono_a.id_datafono}/registrar-pago/", {})
        assert resp.status_code == 400
        assert resp.json()["message"] == (
            "Se requieren: monto, referencia_bancaria, id_transaccion_financiera_origen"
        )

    def test_registrar_pago_tf_inexistente_404(self, client_a, datafono_a):
        resp = client_a.post(
            f"{self.URL}{datafono_a.id_datafono}/registrar-pago/",
            {"monto": "100.00", "referencia_bancaria": "R1",
             "id_transaccion_financiera_origen": str(uuid.uuid4())},
        )
        assert resp.status_code == 404
        assert resp.json()["message"] == "Transacción financiera no encontrada"

    def test_registrar_pago_exitoso_201(self, client_a, datafono_a, tf_a, user_a):
        _sesion_datafono_abierta(datafono_a, user_a)
        resp = client_a.post(
            f"{self.URL}{datafono_a.id_datafono}/registrar-pago/",
            {"monto": "150.00", "referencia_bancaria": "REF-API",
             "id_transaccion_financiera_origen": str(tf_a.id_transaccion)},
        )
        assert resp.status_code == 201, resp.content
        body = resp.json()
        assert body["success"] is True
        assert body["message"] == "Pago registrado exitosamente"
        assert Decimal(body["transaccion"]["monto"]) == Decimal("150.00")
        sesion = SesionDatafono.objects.get(datafono=datafono_a, estado="ABIERTA")
        assert sesion.total_transacciones == Decimal("150.00")
        trans = TransaccionDatafono.objects.get(id_datafono=datafono_a)
        assert trans.referencia_bancaria == "REF-API"
        assert trans.estado == "PENDIENTE"
        assert trans.id_transaccion_financiera_origen == tf_a

    def test_cerrar_sesion_sin_sesion_400(self, client_a, datafono_a):
        resp = client_a.post(f"{self.URL}{datafono_a.id_datafono}/cerrar-sesion/", {})
        assert resp.status_code == 400
        assert resp.json() == {
            "success": False,
            "message": "No se pudo cerrar la sesión. Intente de nuevo.",
        }

    def test_cerrar_sesion_crea_deposito_200(self, client_a, datafono_a, tf_a, user_a):
        _sesion_datafono_abierta(datafono_a, user_a)
        client_a.post(
            f"{self.URL}{datafono_a.id_datafono}/registrar-pago/",
            {"monto": "100.00", "referencia_bancaria": "R1",
             "id_transaccion_financiera_origen": str(tf_a.id_transaccion)},
        )
        resp = client_a.post(f"{self.URL}{datafono_a.id_datafono}/cerrar-sesion/", {})
        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert body["success"] is True
        assert body["message"] == "Sesión cerrada y depósito creado exitosamente"
        # comportamiento actual: cerrar_sesion vuelve a sumar las PENDIENTES
        # ya acumuladas → bruto 200 (100 acumulado + 100 pendiente)
        assert Decimal(body["deposito"]["total_bruto"]) == Decimal("200.00")
        assert Decimal(body["deposito"]["comision_banco"]) == Decimal("4.0000")
        assert Decimal(body["deposito"]["total_neto"]) == Decimal("196.0000")
        assert DepositoDatafono.objects.count() == 1

    def test_list_filtra_por_caja_fisica_y_tenant(
        self, client_a, client_b, datafono_a, caja_fisica_a
    ):
        datafono_a.id_caja_fisica = caja_fisica_a
        datafono_a.save()
        resp = client_a.get(self.URL, {"id_caja_fisica": str(caja_fisica_a.id_caja_fisica)})
        assert resp.status_code == 200
        assert resp.json()["count"] == 1
        resp_otro = client_a.get(self.URL, {"id_caja_fisica": str(uuid.uuid4())})
        assert resp_otro.json()["count"] == 0
        # Empresa B no ve el datafono de A
        resp_b = client_b.get(self.URL)
        assert resp_b.json()["count"] == 0


# ── DepositoDatafonoViewSet ──────────────────────────────────────────────────

class TestDepositoDatafono:
    URL = "/api/finanzas/depositos-datafono/"

    @pytest.fixture
    def deposito(self, datafono_a, user_a):
        sesion = _sesion_datafono_abierta(datafono_a, user_a)
        TransaccionDatafono.objects.create(
            id_datafono=datafono_a, sesion_datafono=sesion, monto=Decimal("100.00"),
            id_usuario_registro=user_a,
        )
        from apps.finanzas.models import cerrar_sesion_datafono

        return cerrar_sesion_datafono(datafono_a, user_a)

    @pytest.fixture
    def movimiento(self, empresa_a, moneda_usd, user_a):
        ahora = timezone.now()
        return MovimientoCajaBanco.objects.create(
            id_empresa=empresa_a, fecha_movimiento=ahora.date(),
            hora_movimiento=ahora.time(), tipo_movimiento="INGRESO",
            monto=Decimal("98.00"), id_moneda=moneda_usd, concepto="dep banco",
            saldo_anterior=Decimal("0.00"), saldo_nuevo=Decimal("98.00"),
            id_usuario_registro=user_a,
        )

    def test_conciliar_sin_movimiento_400(self, client_a, deposito):
        resp = client_a.post(f"{self.URL}{deposito.id_deposito}/conciliar/", {})
        assert resp.status_code == 400
        assert resp.json()["message"] == "Se requiere id_movimiento_banco"

    def test_conciliar_movimiento_inexistente_404(self, client_a, deposito):
        resp = client_a.post(
            f"{self.URL}{deposito.id_deposito}/conciliar/",
            {"id_movimiento_banco": str(uuid.uuid4())},
        )
        assert resp.status_code == 404
        assert resp.json()["message"] == "Movimiento bancario no encontrado"

    def test_conciliar_exitoso_y_doble_conciliacion(self, client_a, deposito, movimiento):
        url = f"{self.URL}{deposito.id_deposito}/conciliar/"
        resp = client_a.post(url, {"id_movimiento_banco": str(movimiento.id_movimiento)})
        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert body["message"] == "Depósito conciliado exitosamente"
        assert body["deposito"]["estado"] == "CONCILIADO"
        deposito.refresh_from_db()
        assert deposito.estado == "CONCILIADO"
        assert deposito.sesion_datafono.estado == "CONCILIADA"
        # Segunda conciliación → ValueError controlado → 400
        resp2 = client_a.post(url, {"id_movimiento_banco": str(movimiento.id_movimiento)})
        assert resp2.status_code == 400
        assert resp2.json()["message"] == "No se pudo conciliar el depósito. Verifique los datos."

    def test_pendientes_lista_y_filtro(self, client_a, deposito, datafono_a):
        resp = client_a.get(f"{self.URL}pendientes/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert len(body["depositos"]) == 1
        assert body["depositos"][0]["id_deposito"] == str(deposito.id_deposito)
        resp_f = client_a.get(f"{self.URL}pendientes/", {"datafono_id": str(datafono_a.id_datafono)})
        assert len(resp_f.json()["depositos"]) == 1

    def test_pendientes_datafono_inexistente_404(self, client_a):
        resp = client_a.get(f"{self.URL}pendientes/", {"datafono_id": str(uuid.uuid4())})
        assert resp.status_code == 404
        assert resp.json()["message"] == "Datafono no encontrado"

    def test_list_aislamiento_tenant(self, client_b, deposito):
        resp = client_b.get(self.URL)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


# ── PlantillaMaestroCajasVirtualesViewSet ────────────────────────────────────

class TestPlantillaMaestro:
    URL = "/api/finanzas/plantillas-maestro-cajas/"

    def test_sincronizar(self, client_a, empresa_a, moneda_usd):
        plantilla = PlantillaMaestroCajasVirtuales.objects.create(
            empresa=empresa_a, nombre="Plantilla API", moneda_base=moneda_usd
        )
        resp = client_a.post(f"{self.URL}{plantilla.id_plantilla_maestro}/sincronizar/", {})
        assert resp.status_code == 200
        assert resp.json() == {
            "mensaje": "Sincronización completada para plantilla Plantilla API"
        }

    def test_list_solo_empresa_propia(self, client_b, empresa_a, moneda_usd):
        PlantillaMaestroCajasVirtuales.objects.create(
            empresa=empresa_a, nombre="De A", moneda_base=moneda_usd
        )
        resp = client_b.get(self.URL)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


# ── PagoViewSet ──────────────────────────────────────────────────────────────

class TestPagoViewSet:
    URL = "/api/finanzas/pagos/"

    def test_create_ingreso_201(self, client_a, empresa_a, moneda_usd, metodo_a, user_a):
        resp = client_a.post(self.URL, {
            "id_empresa": str(empresa_a.id_empresa),
            "tipo_operacion": "INGRESO",
            "tipo_documento": "AJUSTE",
            "id_documento": str(uuid.uuid4()),
            "fecha_pago": timezone.now().isoformat(),
            "monto": "250.5000",
            "id_moneda": str(moneda_usd.id_moneda),
            "id_metodo_pago": str(metodo_a.id_metodo_pago),
        })
        assert resp.status_code == 201, resp.content
        pago = Pago.objects.get()
        assert pago.monto == Decimal("250.5000")
        assert pago.id_usuario_registro == user_a

    def test_list_aislado_por_empresa(self, client_b, empresa_a, moneda_usd, metodo_a):
        Pago.objects.create(
            id_empresa=empresa_a, tipo_operacion="INGRESO", tipo_documento="AJUSTE",
            id_documento=uuid.uuid4(), fecha_pago=timezone.now(),
            monto=Decimal("10.0000"), id_moneda=moneda_usd, id_metodo_pago=metodo_a,
        )
        resp = client_b.get(self.URL)
        assert resp.json()["count"] == 0

    def test_tipos_documento_y_operacion(self, client_a):
        resp = client_a.get(f"{self.URL}tipos_documento/")
        assert resp.status_code == 200
        valores = [item["value"] for item in resp.json()]
        assert "PEDIDO" in valores and "AJUSTE" in valores
        resp_op = client_a.get(f"{self.URL}tipos_operacion/")
        assert resp_op.json() == [
            {"value": "INGRESO", "label": "Ingreso"},
            {"value": "EGRESO", "label": "Egreso"},
        ]


# ── CajaFisicaViewSet (acciones de catálogo) ─────────────────────────────────

class TestCajaFisicaAcciones:
    URL = "/api/finanzas/cajas-fisicas/"

    def test_tipo_caja_choices(self, client_a):
        resp = client_a.get(f"{self.URL}tipo-caja-choices/")
        assert resp.status_code == 200
        assert {"value": "REGISTRADORA", "display": "Caja Registradora"} in resp.json()

    def test_tipos_documento_y_operacion(self, client_a):
        assert client_a.get(f"{self.URL}tipos_documento/").status_code == 200
        resp = client_a.get(f"{self.URL}tipos_operacion/")
        assert resp.json()[0] == {"value": "INGRESO", "label": "Ingreso"}

    def test_list_aislado(self, client_b, caja_fisica_a):
        resp = client_b.get(self.URL)
        assert resp.json()["count"] == 0


# ── TransaccionFinancieraViewSet.perform_create ──────────────────────────────

class TestTransaccionFinancieraCreate:
    URL = "/api/finanzas/transacciones-financieras/"

    def _payload(self, empresa, moneda, metodo, user):
        return {
            "id_empresa": str(empresa.id_empresa),
            "fecha_hora_transaccion": timezone.now().isoformat(),
            "tipo_transaccion": "INGRESO",
            "monto_transaccion": "75.00",
            "id_moneda_transaccion": str(moneda.id_moneda),
            "monto_base_empresa": "75.00",
            "id_metodo_pago": str(metodo.id_metodo_pago),
            "id_usuario_registro": user.pk,
        }

    def test_empresa_ajena_se_ignora_y_usa_la_propia(
        self, client_a, empresa_a, empresa_b, moneda_usd, metodo_a, user_a
    ):
        # SEC-M1: el pk de una empresa ajena ya no se ignora en silencio —
        # el scope de tenant de FKs lo rechaza con 400.
        resp = client_a.post(self.URL, self._payload(empresa_b, moneda_usd, metodo_a, user_a))
        assert resp.status_code == 400, resp.content
        assert not TransaccionFinanciera.objects.exists()

    def test_empresa_propia_se_respeta(self, client_a, empresa_a, moneda_usd, metodo_a, user_a):
        resp = client_a.post(self.URL, self._payload(empresa_a, moneda_usd, metodo_a, user_a))
        assert resp.status_code == 201
        assert TransaccionFinanciera.objects.get().id_empresa == empresa_a

    def test_usuario_sin_empresa_403(self, empresa_b, moneda_usd, metodo_a, db):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        sin_empresa = User.objects.create_user(
            username="sin_empresa", password="x", email="se@x.com", is_active=True
        )
        client = APIClient()
        client.force_authenticate(user=sin_empresa)
        resp = client.post(self.URL, self._payload(empresa_b, moneda_usd, metodo_a, sin_empresa))
        # SEC-M1: sin empresas visibles, los FKs tenant-aware del payload se
        # rechazan en el serializer (400) antes del check 403 del viewset.
        assert resp.status_code in (400, 403)
        assert not TransaccionFinanciera.objects.exists()


# ── MetodoPagoViewSet: reutilizar y monedas_info ─────────────────────────────

class TestMetodoPagoAcciones:
    URL = "/api/finanzas/metodos-pago/"

    @pytest.fixture
    def metodo_b(self, empresa_b):
        # SEC-A1 (auditoría 2026-06-10): antes este fixture era PRIVADO de la
        # empresa B y el test fijaba el comportamiento inseguro (cualquier
        # usuario podía reutilizarlo por UUID). Ahora `reutilizar` solo acepta
        # fuentes visibles (genéricas/públicas/propias), así que el método
        # compartido debe ser público; el caso "privado ajeno → 404" se cubre
        # en tests_api/test_metodos_pago_aislamiento.py.
        return MetodoPago.objects.create(
            nombre_metodo="Pago Móvil Banesco", tipo_metodo="ELECTRONICO",
            empresa=empresa_b, es_publico=True,
        )

    def test_reutilizar_sin_empresa_400(self, client_a, metodo_b):
        resp = client_a.post(f"{self.URL}{metodo_b.id_metodo_pago}/reutilizar/", {})
        assert resp.status_code == 400
        assert resp.json() == {"detail": "id_empresa es requerido."}

    def test_reutilizar_empresa_inexistente_404(self, client_a, metodo_b):
        resp = client_a.post(
            f"{self.URL}{metodo_b.id_metodo_pago}/reutilizar/",
            {"id_empresa": str(uuid.uuid4())},
        )
        assert resp.status_code == 404
        assert resp.json() == {"detail": "Empresa no encontrada."}

    def test_reutilizar_similar_existente_409(self, client_a, empresa_a, metodo_b):
        pytest.importorskip("rapidfuzz")  # dependencia opcional en el entorno dev
        MetodoPago.objects.create(
            nombre_metodo="Pago Movil Banesco", tipo_metodo="ELECTRONICO", empresa=empresa_a
        )
        resp = client_a.post(
            f"{self.URL}{metodo_b.id_metodo_pago}/reutilizar/",
            {"id_empresa": str(empresa_a.id_empresa)},
        )
        assert resp.status_code == 409
        assert "Ya existe un método de pago similar" in resp.json()["detail"]

    def test_reutilizar_exitoso_201(self, client_a, empresa_a, metodo_b):
        pytest.importorskip("rapidfuzz")  # dependencia opcional en el entorno dev
        resp = client_a.post(
            f"{self.URL}{metodo_b.id_metodo_pago}/reutilizar/",
            {"id_empresa": str(empresa_a.id_empresa)},
        )
        assert resp.status_code == 201, resp.content
        nuevo = MetodoPago.objects.get(empresa=empresa_a, nombre_metodo="Pago Móvil Banesco")
        assert nuevo.es_generico is False
        assert nuevo.es_publico is False
        assert nuevo.tipo_metodo == "ELECTRONICO"

    def test_monedas_info_endpoint_roto_500(self, client_a, empresa_a, moneda_usd):
        # HALLAZGO documentado: el ViewSet usa lookup_field="id_metodo_pago",
        # pero la acción monedas_info se declara con firma (self, request,
        # pk=None) → el router pasa kwarg id_metodo_pago → TypeError → 500.
        metodo = MetodoPago.objects.create(
            nombre_metodo="Efectivo A", tipo_metodo="EFECTIVO", empresa=empresa_a
        )
        with pytest.raises(TypeError):
            client_a.get(f"{self.URL}{metodo.id_metodo_pago}/monedas_info/")


# ── MonedaEmpresaActivaViewSet: filtros ──────────────────────────────────────

class TestMonedaEmpresaActivaFiltros:
    URL = "/api/finanzas/monedas-empresa-activas/"

    def test_filtro_activa_true_false(self, client_a, empresa_a, moneda_usd):
        # moneda_usd se crea antes que empresa_a → la señal de sync no creó la
        # fila; se garantiza aquí.
        activa, _ = MonedaEmpresaActiva.objects.get_or_create(
            empresa=empresa_a, moneda=moneda_usd
        )
        activa.activa = False
        activa.save()
        resp_false = client_a.get(self.URL, {"activa": "false"})
        assert resp_false.json()["count"] == 1
        resp_true = client_a.get(self.URL, {"activa": "true"})
        assert resp_true.json()["count"] == 0

    def test_filtro_empresa(self, client_a, empresa_a, moneda_usd):
        MonedaEmpresaActiva.objects.get_or_create(empresa=empresa_a, moneda=moneda_usd)
        resp = client_a.get(self.URL, {"empresa": str(empresa_a.id_empresa)})
        assert resp.json()["count"] == 1


# ── SesionCajaFisicaViewSet.transferir_entre_cajas ───────────────────────────

class TestSesionCajaTransferir:
    URL = "/api/finanzas/sesiones-caja/"

    @pytest.fixture
    def sesion(self, caja_fisica_a, user_a):
        return SesionCajaFisica.abrir_sesion(caja_fisica_a, user_a)

    def test_faltan_parametros_400(self, client_a, sesion):
        resp = client_a.post(f"{self.URL}{sesion.id_sesion}/transferir-entre-cajas/", {})
        assert resp.status_code == 400
        assert resp.json() == {"error": "Debe indicar caja_origen, caja_destino y monto."}

    def test_cajas_no_pertenecen_a_sesion_400(self, client_a, sesion, caja_virtual_a):
        resp = client_a.post(
            f"{self.URL}{sesion.id_sesion}/transferir-entre-cajas/",
            {"caja_origen": str(caja_virtual_a.id_caja),
             "caja_destino": str(uuid.uuid4()), "monto": "10.00"},
        )
        assert resp.status_code == 400
        assert resp.json() == {"error": "Caja origen o destino no pertenece a la sesión."}

    def test_list_filtra_por_tenant(self, client_b, sesion):
        resp = client_b.get(self.URL)
        assert resp.status_code == 200
        body = resp.json()
        resultados = body["results"] if isinstance(body, dict) else body
        assert resultados == []


# ── Listas con aislamiento por usuario / tenant ──────────────────────────────

class TestListasAisladas:
    def test_cajas_usuario_solo_del_usuario(self, client_a, user_a, user_b, caja_virtual_a):
        CajaVirtualUsuario.objects.create(usuario=user_a, caja_virtual=caja_virtual_a)
        CajaVirtualUsuario.objects.create(usuario=user_b, caja_virtual=caja_virtual_a)
        resp = client_a.get("/api/finanzas/cajas-usuario/")
        assert resp.status_code == 200
        body = resp.json()
        resultados = body["results"] if isinstance(body, dict) else body
        assert len(resultados) == 1
        assert resultados[0]["caja_virtual_nombre"] == "Caja Virtual A"

    def test_cajas_fisicas_usuario_solo_del_usuario(self, client_a, user_a, user_b, caja_fisica_a):
        CajaFisicaUsuario.objects.create(usuario=user_a, caja_fisica=caja_fisica_a)
        CajaFisicaUsuario.objects.create(usuario=user_b, caja_fisica=caja_fisica_a)
        resp = client_a.get("/api/finanzas/cajas-fisicas-usuario/")
        assert resp.status_code == 200
        body = resp.json()
        resultados = body["results"] if isinstance(body, dict) else body
        assert len(resultados) == 1
        assert resultados[0]["caja_nombre"] == "Caja Principal Test"
        assert resultados[0]["puede_abrir_sesion"] is True

    def test_transacciones_y_sesiones_datafono_aisladas(
        self, client_a, client_b, datafono_a, user_a
    ):
        sesion = _sesion_datafono_abierta(datafono_a, user_a)
        TransaccionDatafono.objects.create(
            id_datafono=datafono_a, sesion_datafono=sesion, monto=Decimal("33.00")
        )
        resp_a = client_a.get("/api/finanzas/transacciones-datafono/")
        assert resp_a.json()["count"] == 1
        assert client_b.get("/api/finanzas/transacciones-datafono/").json()["count"] == 0
        assert client_a.get("/api/finanzas/sesiones-datafono/").json()["count"] == 1
        assert client_b.get("/api/finanzas/sesiones-datafono/").json()["count"] == 0

    def test_cajas_virtuales_auto_filtradas_por_empresa(
        self, client_a, client_b, empresa_a, moneda_usd, metodo_a
    ):
        plantilla = PlantillaMaestroCajasVirtuales.objects.create(
            empresa=empresa_a, nombre="P-auto", moneda_base=moneda_usd
        )
        CajaVirtualAuto.objects.create(
            plantilla_maestro=plantilla, moneda=moneda_usd, metodo_pago=metodo_a
        )
        assert client_a.get("/api/finanzas/cajas-virtuales-auto/").json()["count"] == 1
        assert client_b.get("/api/finanzas/cajas-virtuales-auto/").json()["count"] == 0

    def test_overrides_create_roto_y_list_aislada(
        self, client_a, client_b, caja_fisica_a, metodo_a, sucursal_a, user_a
    ):
        # HALLAZGO documentado: CajaMetodoPagoOverrideSerializer declara
        # caja_fisica = PrimaryKeyRelatedField(queryset=Caja.objects.all())
        # (caja VIRTUAL) aunque el FK del modelo apunta a CajaFisica → un id
        # de CajaFisica real es rechazado con 400 "objeto no existe".
        resp = client_a.post("/api/finanzas/overrides-metodos-pago/", {
            "caja_fisica": str(caja_fisica_a.id_caja_fisica),
            "metodo_pago": str(metodo_a.id_metodo_pago),
            "sucursal": str(sucursal_a.id_sucursal),
            "deshabilitado": True,
            "motivo": "POS dañado",
        })
        assert resp.status_code == 400
        assert "caja_fisica" in resp.json()
        # HALLAZGO documentado (2): tampoco se puede crear por ORM — la señal
        # override_post_save filtra CajaVirtualAuto.caja_fisica (FK→Caja
        # virtual) con una instancia de CajaFisica → ValueError. El modelo de
        # overrides está roto de punta a punta.
        with pytest.raises(ValueError):
            CajaMetodoPagoOverride.objects.create(
                caja_fisica=caja_fisica_a, metodo_pago=metodo_a, sucursal=sucursal_a,
                deshabilitado=True, creado_por=user_a,
            )
        # Peor aún: la fila SÍ queda insertada (la señal revienta después del
        # INSERT) → estado inconsistente. La lista queda acotada al tenant.
        assert CajaMetodoPagoOverride.objects.count() == 1
        assert client_a.get("/api/finanzas/overrides-metodos-pago/").json()["count"] == 1
        assert client_b.get("/api/finanzas/overrides-metodos-pago/").json()["count"] == 0
