"""
Backfill de cobertura (gaps) — apps/finanzas (plan "Cero Dudas", COV/finanzas).

Complementa test_finanzas_views_cobertura{,2}.py, test_finanzas_models_cobertura.py
y test_finanzas_serializers_cobertura.py (que NO se tocan) con las ramas que esas
suites no ejercitan:

- utils.py (0%): permisos de caja física, helpers de sesión (BUG corregido:
  importaban el modelo `SesionCaja` inexistente; ahora usan SesionCajaFisica) y
  crear_configuracion_inicial_venezolana (FIX lote 2: la plantilla ya se crea
  con `moneda_base` VES; antes IntegrityError).
- views_extra/tasa_oficial_bcv.py: solo consultas a BD (cero red): fecha
  inválida, monedas por código ISO, tasa global encontrada/no encontrada y el
  flujo por empresa (FIX lote 2: la vista usa `empresa.id_moneda_base`; antes
  el atributo inexistente `moneda_base` hacía 404 siempre).
- views.py: ramas restantes de los ViewSets (superusuario, filtros completos de
  movimientos, buscar_reutilizar con filtros, monedas_info/crear_caja_virtual/
  CajaUsuarioViewSet por invocación directa porque sus rutas están rotas o no
  registradas, perform_create de pagos con doble registro financiero,
  notificación best-effort que revienta, cierre de caja exitoso).
- serializers.py: creates/updates de MetodoPagoEmpresaActiva, MonedaEmpresaActiva,
  TransaccionFinanciera (mapeo monto_base, conversión de UUIDs y MovimientoCajaBanco
  automático) y PlantillaMaestroCajasVirtuales (monedas/metodos_pago custom).
- models.py: __str__ restantes, validación de documentos de Pago por tipo
  (todas las ramas), documento_relacionado, señales de sincronización de cajas
  virtuales automáticas y apertura forzada de sesión.

Dinero siempre con Decimal exacto. Los bugs encontrados se prueban con
pytest.raises + comentario BUG (convención del plan, sin enmascarar).
"""
import datetime
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.finanzas.models import (
    Caja,
    CajaFisica,
    CajaFisicaUsuario,
    CajaUsuario,
    CajaVirtualAuto,
    CajaVirtualUsuario,
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
    TasaCambio,
    TransaccionDatafono,
    TransaccionFinanciera,
)
from apps.finanzas import utils as finanzas_utils

pytestmark = pytest.mark.django_db


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def client_super(user_a):
    """user_a marcado superusuario Omni — ve TODO (rama es_superusuario_omni)."""
    user_a.es_superusuario_omni = True
    user_a.save(update_fields=["es_superusuario_omni"])
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def metodo_a(empresa_a, moneda_usd):
    metodo = MetodoPago.objects.create(
        nombre_metodo="Zelle Gaps", tipo_metodo="ELECTRONICO", empresa=empresa_a
    )
    metodo.monedas.add(moneda_usd)
    return metodo


@pytest.fixture
def caja_virtual_a(empresa_a, moneda_usd):
    return Caja.objects.create(
        empresa=empresa_a, nombre="Caja Gaps", moneda=moneda_usd,
        tipo_caja="REGISTRADORA", saldo_actual=Decimal("50.00"),
    )


@pytest.fixture
def cuenta_a(empresa_a, moneda_usd):
    return CuentaBancariaEmpresa.objects.create(
        id_empresa=empresa_a, nombre_banco="Banco Gaps", numero_cuenta="0102-GAP",
        tipo_cuenta="CORRIENTE", id_moneda=moneda_usd, saldo_actual=Decimal("200.00"),
    )


def _stub_request(user, **query):
    """Request mínimo para acciones que solo usan query_params/user/data."""
    return SimpleNamespace(query_params=query, user=user, data={})


# ══════════════════════════════════════════════════════════════════════════════
# apps/finanzas/utils.py
# ══════════════════════════════════════════════════════════════════════════════

class TestAsignarPermisosCajaFisica:
    def test_crea_asignacion_nueva(self, user_a, caja_fisica_a):
        asignacion, created = finanzas_utils.asignar_permisos_caja_fisica(
            user_a, caja_fisica_a, puede_abrir=True, puede_cerrar=False,
            es_predeterminada=True,
        )
        assert created is True
        assert asignacion.puede_abrir_sesion is True
        assert asignacion.puede_cerrar_sesion is False
        assert asignacion.es_predeterminada is True

    def test_actualiza_asignacion_existente(self, user_a, caja_fisica_a):
        finanzas_utils.asignar_permisos_caja_fisica(user_a, caja_fisica_a)
        asignacion, created = finanzas_utils.asignar_permisos_caja_fisica(
            user_a, caja_fisica_a, puede_abrir=False, puede_cerrar=False,
            es_predeterminada=False,
        )
        assert created is False
        asignacion.refresh_from_db()
        assert asignacion.puede_abrir_sesion is False
        assert asignacion.puede_cerrar_sesion is False
        assert CajaFisicaUsuario.objects.count() == 1


class TestHelpersSesion:
    """Regresión del BUG: utils importaba `SesionCaja` (modelo inexistente —
    el real es SesionCajaFisica) y todos estos helpers reventaban con
    ImportError. Ahora se fija el comportamiento funcional."""

    def test_obtener_sesion_activa_usuario_sin_sesion_retorna_none(self, user_a):
        assert finanzas_utils.obtener_sesion_activa_usuario(user_a) is None

    def test_obtener_sesion_activa_usuario_con_sesion_abierta(
        self, user_a, empresa_a, caja_fisica_a
    ):
        sesion = SesionCajaFisica.objects.create(
            caja_fisica=caja_fisica_a, usuario=user_a, empresa=empresa_a
        )
        encontrada = finanzas_utils.obtener_sesion_activa_usuario(user_a)
        assert encontrada is not None
        assert encontrada.pk == sesion.pk
        assert encontrada.caja_fisica == caja_fisica_a

    def test_obtener_caja_activa_sesion(self, user_a, empresa_a, caja_fisica_a):
        assert finanzas_utils.obtener_caja_activa_sesion(user_a) is None
        SesionCajaFisica.objects.create(
            caja_fisica=caja_fisica_a, usuario=user_a, empresa=empresa_a
        )
        assert finanzas_utils.obtener_caja_activa_sesion(user_a) == caja_fisica_a

    def test_sesion_cerrada_no_cuenta_como_activa(
        self, user_a, empresa_a, caja_fisica_a
    ):
        SesionCajaFisica.objects.create(
            caja_fisica=caja_fisica_a, usuario=user_a, empresa=empresa_a,
            estado="CERRADA",
        )
        assert finanzas_utils.obtener_sesion_activa_usuario(user_a) is None

    def test_validar_acceso_con_asignacion_directa_true(self, user_a, caja_virtual_a):
        CajaUsuario.objects.create(usuario=user_a, caja=caja_virtual_a)
        assert finanzas_utils.validar_acceso_caja_usuario(user_a, caja_virtual_a) is True

    def test_validar_acceso_sin_asignacion_ni_sesion_false(self, user_a, caja_virtual_a):
        assert finanzas_utils.validar_acceso_caja_usuario(user_a, caja_virtual_a) is False


class TestCrearConfiguracionInicialVenezolana:
    def test_sin_monedas_retorna_error(self, empresa_a):
        resultado = finanzas_utils.crear_configuracion_inicial_venezolana(empresa_a)
        assert resultado == {"error": "Monedas VES y USD no encontradas"}

    @pytest.fixture
    def empresa_ve(self, db):
        """Empresa SIN el USD genérico del conftest — codigo_iso es único
        global en finanzas_moneda, así que las monedas VES/USD deben crearse
        aquí asociadas a la empresa."""
        from apps.core.models import Empresa

        empresa = Empresa.objects.create(
            nombre_legal="Empresa VE C.A.", identificador_fiscal="J-00000001-0"
        )
        Moneda.objects.create(
            nombre="Bolívar VE", codigo_iso="VES", simbolo="Bs",
            tipo_moneda="fiat", empresa=empresa,
        )
        Moneda.objects.create(
            nombre="Dólar VE", codigo_iso="USD", simbolo="$",
            tipo_moneda="fiat", empresa=empresa,
        )
        return empresa

    def test_sin_metodos_retorna_error(self, empresa_ve):
        resultado = finanzas_utils.crear_configuracion_inicial_venezolana(empresa_ve)
        assert resultado == {"error": "Métodos de pago básicos no encontrados"}

    def test_flujo_completo_crea_plantillas_con_moneda_base_ves(self, empresa_ve):
        # FIX (lote 2): el get_or_create no incluía `moneda_base` (FK NOT NULL
        # sin default) → IntegrityError; y luego llamaba `monedas_base.set`,
        # M2M inexistente. Ahora el flujo completo crea ambas plantillas.
        for nombre, tipo in [("EFECTIVO", "EFECTIVO"), ("TARJETA", "TARJETA"), ("CREDITO", "CREDITO")]:
            MetodoPago.objects.create(nombre_metodo=nombre, tipo_metodo=tipo, empresa=empresa_ve)
        resultado = finanzas_utils.crear_configuracion_inicial_venezolana(empresa_ve)
        assert resultado["mensaje"] == "Configuración inicial creada exitosamente"
        plantilla_fisica = resultado["plantilla_fisica"]
        plantilla_movil = resultado["plantilla_movil"]
        assert plantilla_fisica.moneda_base.codigo_iso == "VES"
        assert plantilla_movil.moneda_base.codigo_iso == "VES"
        assert plantilla_fisica.metodos_pago_base.count() == 3
        assert plantilla_movil.metodos_pago_base.count() == 2
        # Idempotente: una segunda llamada no duplica plantillas
        finanzas_utils.crear_configuracion_inicial_venezolana(empresa_ve)
        assert PlantillaMaestroCajasVirtuales.objects.filter(empresa=empresa_ve).count() == 2


# ══════════════════════════════════════════════════════════════════════════════
# apps/finanzas/views_extra/tasa_oficial_bcv.py  (solo BD — CERO red)
# ══════════════════════════════════════════════════════════════════════════════

class TestTasaOficialBCVView:
    URL = "/api/finanzas/tasa-oficial-bcv/"

    @pytest.fixture
    def moneda_ves(self, db):
        return Moneda.objects.create(
            nombre="Bolívar", codigo_iso="VES", simbolo="Bs",
            tipo_moneda="fiat", es_generica=True,
        )

    @pytest.fixture
    def tasa_bcv_hoy(self, moneda_usd, moneda_ves):
        return TasaCambio.objects.create(
            id_empresa=None, id_moneda_origen=moneda_usd, id_moneda_destino=moneda_ves,
            tipo_tasa="OFICIAL_BCV", valor_tasa=Decimal("36.50000000"),
            fecha_tasa=datetime.date.today(),
        )

    def test_fecha_invalida_400(self, client_a):
        resp = client_a.get(self.URL, {"fecha": "09-06-2026"})
        assert resp.status_code == 400
        assert resp.json() == {"detail": "Formato de fecha inválido. Use YYYY-MM-DD."}

    def test_tasa_global_encontrada_200(self, client_a, tasa_bcv_hoy):
        resp = client_a.get(self.URL, {"moneda_origen": "USD", "moneda_destino": "VES"})
        assert resp.status_code == 200, resp.content
        assert Decimal(resp.json()["valor_tasa"]) == Decimal("36.50000000")

    def test_tasa_por_fecha_explicita_200(self, client_a, tasa_bcv_hoy):
        resp = client_a.get(self.URL, {
            "moneda_origen": "USD", "moneda_destino": "VES",
            "fecha": datetime.date.today().isoformat(),
        })
        assert resp.status_code == 200

    def test_moneda_inexistente_404(self, client_a, tasa_bcv_hoy):
        resp = client_a.get(self.URL, {"moneda_origen": "XXX", "moneda_destino": "VES"})
        assert resp.status_code == 404
        assert resp.json() == {"detail": "Moneda no encontrada."}

    def test_sin_tasa_registrada_404(self, client_a, moneda_usd, moneda_ves):
        resp = client_a.get(self.URL, {"moneda_origen": "USD", "moneda_destino": "VES"})
        assert resp.status_code == 404
        assert resp.json() == {"detail": "No hay tasa oficial BCV registrada para esa fecha."}

    def test_flujo_por_empresa_resuelve_moneda_base(self, client_a, empresa_a, moneda_ves, tasa_bcv_hoy):
        # FIX (lote 2): la vista usaba `empresa.moneda_base` (el campo real es
        # `id_moneda_base`) y el AttributeError silenciado devolvía 404 siempre.
        # empresa_a tiene id_moneda_base=USD → origen USD, destino VES → 200.
        resp = client_a.get(self.URL, {
            "id_empresa": str(empresa_a.id_empresa),
            "id_moneda_transaccion": str(moneda_ves.id_moneda),
        })
        assert resp.status_code == 200, resp.content
        assert Decimal(resp.json()["valor_tasa"]) == Decimal("36.50000000")

    def test_flujo_por_empresa_sin_moneda_base_404(self, client_a, moneda_usd, tasa_bcv_hoy):
        from apps.core.models import Empresa

        empresa = Empresa.objects.create(
            nombre_legal="Sin Base C.A.", identificador_fiscal="J-00000002-0"
        )
        resp = client_a.get(self.URL, {
            "id_empresa": str(empresa.id_empresa),
            "id_moneda_transaccion": str(moneda_usd.id_moneda),
        })
        assert resp.status_code == 404
        assert resp.json() == {"detail": "Empresa o moneda base no encontrada."}

    def test_empresa_inexistente_404(self, client_a):
        resp = client_a.get(self.URL, {"id_empresa": str(uuid.uuid4())})
        assert resp.status_code == 404
        assert resp.json() == {"detail": "Empresa o moneda base no encontrada."}


# ══════════════════════════════════════════════════════════════════════════════
# apps/finanzas/views.py — ramas restantes
# ══════════════════════════════════════════════════════════════════════════════

class TestSesionCajaFisicaRamasRotas:
    URL = "/api/finanzas/sesiones-caja/"

    def test_perform_create_consulta_campo_inexistente(self, client_a, caja_virtual_a):
        # BUG (documentado, sin enmascarar): perform_create busca
        # Caja.objects.get(..., es_fisica=True) pero el modelo Caja NO tiene
        # campo `es_fisica` → FieldError (solo se captura Caja.DoesNotExist).
        # Abrir sesión por la API está roto de origen.
        from django.core.exceptions import FieldError

        with pytest.raises(FieldError):
            client_a.post(self.URL, {
                "caja_fisica_principal": str(caja_virtual_a.id_caja),
            }, format="json")

    def test_cerrar_funciona_y_marca_sesion_cerrada(self, client_a, caja_fisica_a, user_a):
        # FIX (hallazgo PR #73): el modelo acepta saldos_reales/usuario/hasta
        # y la acción `cerrar` responde 200 marcando la sesión CERRADA.
        # Flujo completo (cierres por caja, atomicidad, multi-tenant) en
        # test_finanzas_sesion_caja_cierre.py.
        sesion = SesionCajaFisica.abrir_sesion(caja_fisica_a, user_a)
        resp = client_a.post(f"{self.URL}{sesion.id_sesion}/cerrar/", {"saldos_reales": {}}, format="json")
        assert resp.status_code == 200
        assert resp.json()["sesion"]["estado"] == "CERRADA"
        sesion.refresh_from_db()
        assert sesion.estado == "CERRADA"


class TestMetodoPagoEmpresaActivaViewSet:
    URL = "/api/finanzas/metodos-pago-empresa-activas/"

    def test_list_acotado_y_filtros(self, client_a, empresa_a, metodo_a, user_b):
        fila = MetodoPagoEmpresaActiva.objects.get(empresa=empresa_a, metodo_pago=metodo_a)
        resp = client_a.get(self.URL)
        assert resp.status_code == 200
        assert resp.json()["count"] == 1
        resp_e = client_a.get(self.URL, {"empresa": str(empresa_a.id_empresa)})
        assert resp_e.json()["count"] == 1
        resp_m = client_a.get(self.URL, {"metodo_pago": str(metodo_a.id_metodo_pago)})
        assert resp_m.json()["count"] == 1
        resp_otro = client_a.get(self.URL, {"metodo_pago": str(uuid.uuid4())})
        assert resp_otro.json()["count"] == 0
        # tenant ajeno no ve la fila de A
        client_b = APIClient()
        client_b.force_authenticate(user=user_b)
        assert fila.id not in {r["id"] for r in client_b.get(self.URL).json()["results"]}


class TestMonedaSuperusuario:
    def test_superusuario_ve_todas_las_monedas(self, client_super, moneda_usd, empresa_b):
        Moneda.objects.create(
            nombre="Token B", codigo_iso="TKB", simbolo="T", tipo_moneda="otro",
            es_generica=False, es_publica=False, empresa=empresa_b,
        )
        resp = client_super.get("/api/finanzas/monedas/")
        codigos = {m["codigo_iso"] for m in resp.json()["results"]}
        assert {"USD", "TKB"} <= codigos
        # rama superusuario de la acción `activas`
        resp_act = client_super.get("/api/finanzas/monedas/activas/")
        assert resp_act.status_code == 200
        codigos_act = {m["codigo_iso"] for m in resp_act.json()["results"]}
        assert "TKB" in codigos_act

    def test_activas_usuario_sin_empresas(self, db, moneda_usd):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(
            username="sin_empresas_gaps", password="x", email="seg@x.com", is_active=True
        )
        client = APIClient()
        client.force_authenticate(user=user)
        resp = client.get("/api/finanzas/monedas/activas/")
        assert resp.status_code == 200
        codigos = {m["codigo_iso"] for m in resp.json()["results"]}
        assert "USD" in codigos  # genérica visible aunque no tenga empresa


class TestMetodoPagoRamas:
    URL = "/api/finanzas/metodos-pago/"

    def test_retrieve_usa_get_object_normal(self, client_a, metodo_a):
        resp = client_a.get(f"{self.URL}{metodo_a.id_metodo_pago}/")
        assert resp.status_code == 200
        assert resp.json()["nombre_metodo"] == "Zelle Gaps"

    def test_superusuario_lista_todos(self, client_super, empresa_b):
        MetodoPago.objects.create(
            nombre_metodo="Privado B", tipo_metodo="EFECTIVO", empresa=empresa_b
        )
        nombres = {m["nombre_metodo"] for m in client_super.get(self.URL).json()["results"]}
        assert "Privado B" in nombres

    def test_buscar_reutilizar_con_filtros(self, client_a, empresa_a, empresa_b):
        # SEC-A3 (auditoría 2026-06-10): este test fijaba el comportamiento
        # inseguro (un método PRIVADO de B aparecía para A). Ahora solo los
        # métodos públicos/genéricos son reutilizables, así que el método de B
        # debe ser público para listarse; el caso "privado ajeno NO se lista"
        # se cubre en tests/tenant/test_metodos_pago_aislamiento.py.
        MetodoPago.objects.create(
            nombre_metodo="Pago Móvil B", tipo_metodo="ELECTRONICO",
            empresa=empresa_b, es_publico=True,
        )
        # Sin id_empresa_actual los filtros nombre/tipo aplican y la
        # serialización es segura (get_aplicado retorna False sin contexto).
        resp = client_a.get(f"{self.URL}buscar_reutilizar/", {
            "nombre_metodo": "Móvil",
            "tipo_metodo": "ELECTRONICO",
        })
        assert resp.status_code == 200
        data = resp.json()
        results = data["results"] if isinstance(data, dict) else data
        assert {m["nombre_metodo"] for m in results} == {"Pago Móvil B"}
        # Con id_empresa_actual + filtro sin resultados se cubren las ramas de
        # exclusión sin disparar get_aplicado (que requiere rapidfuzz, no
        # disponible en este entorno — limitación ya documentada en cobertura2).
        resp_vacio = client_a.get(f"{self.URL}buscar_reutilizar/", {
            "id_empresa_actual": str(empresa_a.id_empresa),
            "nombre_metodo": "NoExisteEsteNombre",
            "tipo_metodo": "ELECTRONICO",
        })
        assert resp_vacio.status_code == 200
        data_v = resp_vacio.json()
        results_v = data_v["results"] if isinstance(data_v, dict) else data_v
        assert results_v == []

    def test_monedas_info_efectivo_directo(self, user_a, empresa_a, moneda_usd):
        # La ruta de monedas_info está rota (lookup_field vs firma pk — ya
        # documentado en cobertura2); aquí se ejercita la LÓGICA invocando el
        # método directamente.
        from apps.finanzas.views import MetodoPagoViewSet

        publica_fiat = Moneda.objects.create(
            nombre="Euro", codigo_iso="EUR", simbolo="€", tipo_moneda="fiat",
            es_publica=True,
        )
        MonedaEmpresaActiva.objects.get_or_create(empresa=empresa_a, moneda=publica_fiat)
        metodo = MetodoPago.objects.create(
            nombre_metodo="Efectivo Gaps", tipo_metodo="EFECTIVO", empresa=empresa_a
        )
        metodo.monedas.add(publica_fiat)

        vs = MetodoPagoViewSet()
        vs.get_object = lambda: metodo
        request = _stub_request(user_a, empresa=str(empresa_a.id_empresa))
        resp = vs.monedas_info(request)
        body = resp.data
        assert str(publica_fiat.id_moneda) in [str(x) for x in body["asociadas"]]
        assert str(publica_fiat.id_moneda) in [str(x) for x in body["obligatorias"]]
        assert str(publica_fiat.id_moneda) in [str(x) for x in body["sugeridas"]]

    def test_monedas_info_cheque_y_empresa_del_usuario(self, user_a, moneda_usd):
        from apps.finanzas.views import MetodoPagoViewSet

        fiat_publica = Moneda.objects.create(
            nombre="Peso", codigo_iso="COP", simbolo="$", tipo_moneda="fiat",
            es_publica=True,
        )
        metodo = MetodoPago.objects.create(nombre_metodo="Cheque Gaps", tipo_metodo="CHEQUE")
        vs = MetodoPagoViewSet()
        vs.get_object = lambda: metodo
        # sin query param `empresa` → la toma de request.user.empresas
        resp = vs.monedas_info(_stub_request(user_a))
        assert str(fiat_publica.id_moneda) in [str(x) for x in resp.data["obligatorias"]]


class TestTransaccionFinancieraFiltros:
    def test_filtro_id_empresa_solo_estrecha(self, client_a, empresa_a, moneda_usd, metodo_a, user_a):
        TransaccionFinanciera.objects.create(
            id_empresa=empresa_a, fecha_hora_transaccion=timezone.now(),
            tipo_transaccion="INGRESO", monto_transaccion=Decimal("10.00"),
            id_moneda_transaccion=moneda_usd, monto_base_empresa=Decimal("10.00"),
            id_metodo_pago=metodo_a, id_usuario_registro=user_a,
        )
        resp = client_a.get("/api/finanzas/transacciones-financieras/", {
            "id_empresa": str(empresa_a.id_empresa)
        })
        assert resp.status_code == 200
        data = resp.json()
        results = data["results"] if isinstance(data, dict) else data
        assert len(results) == 1


class TestMovimientoCajaBancoList:
    def test_list_aislado(self, client_a, empresa_a, moneda_usd, user_a):
        ahora = timezone.now()
        MovimientoCajaBanco.objects.create(
            id_empresa=empresa_a, fecha_movimiento=ahora.date(), hora_movimiento=ahora.time(),
            tipo_movimiento="INGRESO", monto=Decimal("5.00"), id_moneda=moneda_usd,
            concepto="gap", saldo_anterior=Decimal("0.00"), saldo_nuevo=Decimal("5.00"),
            id_usuario_registro=user_a,
        )
        resp = client_a.get("/api/finanzas/movimientos-caja-banco/")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1


class TestCierreCajaExitoso:
    def test_cierre_devuelve_resultado(self, client_a, caja_virtual_a, monkeypatch):
        # Caja (virtual) no implementa realizar_cierre (hallazgo ya documentado
        # en cobertura2); para cubrir la rama de éxito de la VISTA se inyecta
        # una implementación mínima.
        resultado = {"saldo_real": "100.00", "descuadre": "0.00"}
        monkeypatch.setattr(
            Caja, "realizar_cierre",
            lambda self, saldo_real=None, usuario=None, hasta=None: resultado,
            raising=False,
        )
        resp = client_a.post(
            f"/api/finanzas/cajas/{caja_virtual_a.id_caja}/cierre/",
            {"saldo_real": "100.00", "hasta": "2026-06-09T12:00:00Z"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json() == resultado


class TestFiltrosCompletosMovimientos:
    @pytest.fixture
    def movimiento(self, empresa_a, moneda_usd, user_a, caja_virtual_a, cuenta_a):
        ahora = timezone.now()
        return MovimientoCajaBanco.objects.create(
            id_empresa=empresa_a, fecha_movimiento=ahora.date(), hora_movimiento=ahora.time(),
            tipo_movimiento="INGRESO", monto=Decimal("25.00"), id_moneda=moneda_usd,
            concepto="venta mostrador", referencia="REF-F1", id_caja=caja_virtual_a,
            id_cuenta_bancaria=cuenta_a, saldo_anterior=Decimal("0.00"),
            saldo_nuevo=Decimal("25.00"), id_usuario_registro=user_a,
        )

    FILTROS = {
        "fecha_inicio": "2020-01-01", "fecha_fin": "2030-12-31",
        "tipo": "INGRESO", "moneda": "USD", "concepto": "mostrador",
        "referencia": "REF-F1", "usuario": "user_empresa_a",
    }

    def test_movimientos_caja_todos_los_filtros(self, client_a, caja_virtual_a, movimiento):
        url = f"/api/finanzas/cajas/{caja_virtual_a.id_caja}/movimientos-caja-banco/"
        resp = client_a.get(url, self.FILTROS)
        assert resp.status_code == 200
        body = resp.json()
        results = body["results"] if isinstance(body, dict) else body
        assert len(results) == 1
        assert Decimal(results[0]["monto"]) == Decimal("25.00")

    def test_movimientos_cuenta_todos_los_filtros(self, client_a, cuenta_a, movimiento):
        url = f"/api/finanzas/cuentas-bancarias-empresa/{cuenta_a.id_cuenta_bancaria}/movimientos-cuenta-bancaria/"
        resp = client_a.get(url, self.FILTROS)
        assert resp.status_code == 200
        body = resp.json()
        results = body["results"] if isinstance(body, dict) else body
        assert len(results) == 1


class TestCajaUsuarioViewSetDirecto:
    """CajaUsuarioViewSet no está registrado en el router (la ruta cajas-usuario
    apunta a CajaVirtualUsuarioViewSet) → se ejercita por invocación directa."""

    def _viewset(self, user):
        from apps.finanzas.views import CajaUsuarioViewSet

        vs = CajaUsuarioViewSet()
        vs.request = SimpleNamespace(user=user, data={})
        return vs

    def test_get_queryset_filtra_por_usuario(self, user_a, user_b, caja_virtual_a):
        CajaUsuario.objects.create(usuario=user_a, caja=caja_virtual_a)
        CajaUsuario.objects.create(usuario=user_b, caja=caja_virtual_a)
        vs = self._viewset(user_a)
        assert list(vs.get_queryset().values_list("usuario", flat=True)) == [user_a.pk]

    def test_crear_caja_virtual_sesion_cerrada_400(self, user_a):
        vs = self._viewset(user_a)
        vs.get_object = lambda: SimpleNamespace(estado="CERRADA")
        resp = vs.crear_caja_virtual(SimpleNamespace(user=user_a, data={}))
        assert resp.status_code == 400
        assert resp.data == {"error": "No se pueden crear cajas virtuales en una sesión cerrada"}

    def test_crear_caja_virtual_sin_nombre_400(self, user_a):
        vs = self._viewset(user_a)
        vs.get_object = lambda: SimpleNamespace(estado="ABIERTA")
        resp = vs.crear_caja_virtual(SimpleNamespace(user=user_a, data={}))
        assert resp.status_code == 400
        assert resp.data == {"error": "Debe especificar un nombre para la caja virtual"}

    def test_crear_caja_virtual_exitoso(self, user_a):
        creado = {"id": "x", "nombre": "CV1"}
        sesion = SimpleNamespace(
            estado="ABIERTA",
            crear_caja_virtual=lambda nombre, monedas_ids, metodos_pago_ids, usuario: creado,
        )
        vs = self._viewset(user_a)
        vs.get_object = lambda: sesion
        request = SimpleNamespace(user=user_a, data={"nombre": "CV1", "monedas": [], "metodos_pago": []})
        resp = vs.crear_caja_virtual(request)
        assert resp.status_code == 200
        assert resp.data["caja_virtual"] == creado

    def test_crear_caja_virtual_valueerror_400(self, user_a):
        def _raise(**kwargs):
            raise ValueError("datos inválidos")

        sesion = SimpleNamespace(estado="ABIERTA", crear_caja_virtual=_raise)
        vs = self._viewset(user_a)
        vs.get_object = lambda: sesion
        request = SimpleNamespace(user=user_a, data={"nombre": "CV2"})
        resp = vs.crear_caja_virtual(request)
        assert resp.status_code == 400
        assert "No se pudo crear la caja virtual" in resp.data["error"]


class TestDatafonoFiltroEmpresa:
    def test_filtro_id_empresa(self, client_a, empresa_a, moneda_usd):
        from apps.core.models import Sucursal

        sucursal = Sucursal.objects.create(
            id_empresa=empresa_a, nombre="Suc Gap", codigo_sucursal="SG1"
        )
        cuenta = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_a, nombre_banco="B", numero_cuenta="1",
            tipo_cuenta="CORRIENTE", id_moneda=moneda_usd,
        )
        Datafono.objects.create(
            id_empresa=empresa_a, id_sucursal=sucursal, nombre="POS Gap",
            serial="PG-1", id_cuenta_bancaria_asociada=cuenta,
        )
        resp = client_a.get("/api/finanzas/datafonos/", {"id_empresa": str(empresa_a.id_empresa)})
        assert resp.json()["count"] == 1

    def test_registrar_pago_valueerror_400(
        self, client_a, empresa_a, moneda_usd, metodo_a, user_a, monkeypatch
    ):
        from apps.core.models import Sucursal
        import apps.finanzas.models as finanzas_models

        sucursal = Sucursal.objects.create(
            id_empresa=empresa_a, nombre="Suc Gap2", codigo_sucursal="SG2"
        )
        cuenta = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_a, nombre_banco="B2", numero_cuenta="2",
            tipo_cuenta="CORRIENTE", id_moneda=moneda_usd,
        )
        datafono = Datafono.objects.create(
            id_empresa=empresa_a, id_sucursal=sucursal, nombre="POS Err",
            serial="PE-1", id_cuenta_bancaria_asociada=cuenta,
        )
        tf = TransaccionFinanciera.objects.create(
            id_empresa=empresa_a, fecha_hora_transaccion=timezone.now(),
            tipo_transaccion="INGRESO", monto_transaccion=Decimal("10.00"),
            id_moneda_transaccion=moneda_usd, monto_base_empresa=Decimal("10.00"),
            id_metodo_pago=metodo_a, id_usuario_registro=user_a,
        )

        def _raise(**kwargs):
            raise ValueError("datafono inactivo")

        monkeypatch.setattr(finanzas_models, "registrar_pago_tarjeta", _raise)
        resp = client_a.post(
            f"/api/finanzas/datafonos/{datafono.id_datafono}/registrar-pago/",
            {"monto": "10.00", "referencia_bancaria": "R", "id_transaccion_financiera_origen": str(tf.id_transaccion)},
        )
        assert resp.status_code == 400
        assert resp.json()["success"] is False


class TestPerformCreatePagoDobleRegistro:
    """Cubre los side-effects financieros de un Pago: TransaccionFinanciera +
    TransaccionDatafono + MovimientoCajaBanco y actualización de saldos.
    P0-3 (BUG-C2): esta lógica vivía huérfana en CajaFisicaViewSet.perform_create;
    ahora es el service apps.finanzas.services.registrar_efectos_pago, invocado
    por PagoViewSet.perform_create dentro de transaction.atomic."""

    def _perform(self, pago):
        from apps.finanzas.services import registrar_efectos_pago

        registrar_efectos_pago(pago)
        pago.refresh_from_db()
        return pago

    def test_pago_con_caja_virtual_y_datafono(
        self, empresa_a, moneda_usd, metodo_a, user_a, caja_virtual_a
    ):
        from apps.core.models import Sucursal

        sucursal = Sucursal.objects.create(
            id_empresa=empresa_a, nombre="Suc PC", codigo_sucursal="SPC"
        )
        cuenta = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_a, nombre_banco="BPC", numero_cuenta="3",
            tipo_cuenta="CORRIENTE", id_moneda=moneda_usd,
        )
        datafono = Datafono.objects.create(
            id_empresa=empresa_a, id_sucursal=sucursal, nombre="POS PC",
            serial="PC-1", id_cuenta_bancaria_asociada=cuenta,
        )
        pago = Pago.objects.create(
            id_empresa=empresa_a, tipo_operacion="INGRESO", tipo_documento="AJUSTE",
            id_documento=uuid.uuid4(), fecha_pago=timezone.now(),
            monto=Decimal("80.0000"), id_moneda=moneda_usd, id_metodo_pago=metodo_a,
            referencia="REF-PC", id_caja_virtual=caja_virtual_a, id_datafono=datafono,
            id_usuario_registro=user_a,
        )
        pago = self._perform(pago)
        tf = pago.id_transaccion_financiera
        assert tf is not None
        assert tf.monto_transaccion == Decimal("80.0000")
        assert tf.monto_base_empresa == Decimal("80.0000")
        assert TransaccionDatafono.objects.get().id_transaccion_financiera_origen == tf
        mov = MovimientoCajaBanco.objects.get(tipo_movimiento="INGRESO")
        # saldo 50.00 inicial + 80.00 de ingreso
        assert mov.saldo_anterior == Decimal("50.00")
        assert mov.saldo_nuevo == Decimal("130.0000")
        caja_virtual_a.refresh_from_db()
        assert caja_virtual_a.saldo_actual == Decimal("130.00")

    def test_pago_egreso_con_cuenta_bancaria(self, empresa_a, moneda_usd, metodo_a, user_a, cuenta_a):
        pago = Pago.objects.create(
            id_empresa=empresa_a, tipo_operacion="EGRESO", tipo_documento="AJUSTE",
            id_documento=uuid.uuid4(), fecha_pago=timezone.now(),
            monto=Decimal("30.0000"), id_moneda=moneda_usd, id_metodo_pago=metodo_a,
            id_cuenta_bancaria=cuenta_a, id_usuario_registro=user_a,
        )
        self._perform(pago)
        mov = MovimientoCajaBanco.objects.get(tipo_movimiento="EGRESO")
        assert mov.saldo_anterior == Decimal("200.00")
        assert mov.saldo_nuevo == Decimal("170.0000")
        cuenta_a.refresh_from_db()
        assert cuenta_a.saldo_actual == Decimal("170.00")


class TestPagoNotificacionBestEffort:
    def test_notificacion_rota_no_impide_el_pago(
        self, client_a, empresa_a, moneda_usd, metodo_a, monkeypatch
    ):
        import apps.notificaciones.services as notif

        def _boom(*args, **kwargs):
            raise RuntimeError("canal caído")

        monkeypatch.setattr(notif, "emitir_notificacion", _boom)
        resp = client_a.post("/api/finanzas/pagos/", {
            "id_empresa": str(empresa_a.id_empresa),
            "tipo_operacion": "INGRESO",
            "tipo_documento": "AJUSTE",
            "id_documento": str(uuid.uuid4()),
            "fecha_pago": timezone.now().isoformat(),
            "monto": "15.0000",
            "id_moneda": str(moneda_usd.id_moneda),
            "id_metodo_pago": str(metodo_a.id_metodo_pago),
        })
        assert resp.status_code == 201, resp.content
        assert Pago.objects.get().monto == Decimal("15.0000")


# ══════════════════════════════════════════════════════════════════════════════
# apps/finanzas/serializers.py — creates/updates restantes
# ══════════════════════════════════════════════════════════════════════════════

class TestMetodoPagoEmpresaActivaSerializer:
    def test_create_asigna_empresa_del_usuario_y_resuelve_uuid(self, user_a, empresa_a):
        from apps.finanzas.serializers import MetodoPagoEmpresaActivaSerializer

        # método sin empresa ni genérico → la señal de sync no crea fila previa
        metodo = MetodoPago.objects.create(nombre_metodo="Suelto", tipo_metodo="OTRO")
        ser = MetodoPagoEmpresaActivaSerializer(context={"request": SimpleNamespace(user=user_a)})
        obj = ser.create({
            "metodo_pago": {"id_metodo_pago": str(metodo.id_metodo_pago)},
            "activa": True,
        })
        assert obj.empresa == empresa_a
        assert obj.metodo_pago == metodo
        assert obj.activa is True

    def test_create_acepta_uuid_plano(self, user_a, empresa_a):
        from apps.finanzas.serializers import MetodoPagoEmpresaActivaSerializer

        metodo = MetodoPago.objects.create(nombre_metodo="Suelto 2", tipo_metodo="OTRO")
        ser = MetodoPagoEmpresaActivaSerializer(context={"request": SimpleNamespace(user=user_a)})
        obj = ser.create({"metodo_pago": str(metodo.id_metodo_pago), "activa": False})
        assert obj.metodo_pago == metodo
        assert obj.activa is False


class TestMonedaEmpresaActivaSerializerMetodos:
    def test_es_base_y_es_pais(self, empresa_a, moneda_usd):
        from apps.finanzas.serializers import MonedaEmpresaActivaSerializer

        fila, _ = MonedaEmpresaActiva.objects.get_or_create(empresa=empresa_a, moneda=moneda_usd)
        ser = MonedaEmpresaActivaSerializer()
        # Empresa no tiene atributo moneda_base_id → None == id_moneda → False
        assert ser.get_es_base(fila) is False
        assert ser.get_es_pais(fila) is False

    def test_es_pais_true_con_moneda_pais(self, empresa_a, moneda_usd):
        from apps.finanzas.serializers import MonedaEmpresaActivaSerializer

        empresa_a.id_moneda_pais = moneda_usd
        empresa_a.save(update_fields=["id_moneda_pais"])
        fila, _ = MonedaEmpresaActiva.objects.get_or_create(empresa=empresa_a, moneda=moneda_usd)
        ser = MonedaEmpresaActivaSerializer()
        assert ser.get_es_pais(fila) is True

    def test_create_resuelve_moneda_por_uuid(self, user_a, empresa_a):
        from apps.finanzas.serializers import MonedaEmpresaActivaSerializer

        nueva = Moneda.objects.create(
            nombre="Yen", codigo_iso="JPY", simbolo="¥", tipo_moneda="fiat",
        )
        # la señal de sync no crea fila (no genérica/pública/sin empresa)
        ser = MonedaEmpresaActivaSerializer(context={"request": SimpleNamespace(user=user_a)})
        obj = ser.create({"moneda": {"id_moneda": str(nueva.id_moneda)}, "activa": True})
        assert obj.empresa == empresa_a
        assert obj.moneda == nueva

    def test_create_moneda_inexistente_validation_error(self, user_a):
        from rest_framework import serializers as drf_serializers

        from apps.finanzas.serializers import MonedaEmpresaActivaSerializer

        ser = MonedaEmpresaActivaSerializer(context={"request": SimpleNamespace(user=user_a)})
        with pytest.raises(drf_serializers.ValidationError):
            ser.create({"moneda": str(uuid.uuid4()), "activa": True})


class TestTransaccionFinancieraSerializerCreate:
    def test_create_mapea_monto_base_y_uuids(self, user_a, empresa_a, moneda_usd, metodo_a):
        from apps.finanzas.serializers import TransaccionFinancieraSerializer

        ser = TransaccionFinancieraSerializer(context={"request": SimpleNamespace(user=user_a)})
        tf = ser.create({
            "fecha_hora_transaccion": timezone.now(),
            "tipo_transaccion": "INGRESO",
            "monto_transaccion": Decimal("60.00"),
            "id_moneda_transaccion": str(moneda_usd.id_moneda),  # como string → se resuelve
            "id_metodo_pago": str(metodo_a.id_metodo_pago),      # como string → se resuelve
            "monto_base": Decimal("60.00"),                       # mapea a monto_base_empresa
            "tasa_cambio": Decimal("1.00"),                       # se descarta (no es campo)
            "descripcion": "TF gaps",
            "referencia_pago": "REF-TF",
        })
        assert tf.id_empresa == empresa_a            # asignada desde el usuario
        assert tf.id_usuario_registro == user_a      # asignado desde el request
        assert tf.monto_base_empresa == Decimal("60.00")
        assert tf.id_moneda_transaccion == moneda_usd
        assert tf.id_metodo_pago == metodo_a
        # MovimientoCajaBanco automático con el mismo monto
        mov = MovimientoCajaBanco.objects.get(id_transaccion_financiera=tf)
        assert mov.tipo_movimiento == "INGRESO"
        assert mov.monto == Decimal("60.00")
        assert mov.concepto == "TF gaps"
        assert mov.referencia == "REF-TF"

    def test_create_moneda_string_inexistente_queda_none(self, user_a, empresa_a, moneda_usd, metodo_a):
        from apps.finanzas.serializers import TransaccionFinancieraSerializer

        ser = TransaccionFinancieraSerializer(context={"request": SimpleNamespace(user=user_a)})
        tf = ser.create({
            "fecha_hora_transaccion": timezone.now(),
            "tipo_transaccion": "EGRESO",
            "monto_transaccion": Decimal("5.00"),
            "id_moneda_transaccion": moneda_usd,
            "id_moneda_base": str(uuid.uuid4()),  # inexistente → None (rama DoesNotExist)
            "id_metodo_pago": metodo_a,
            "monto_base_empresa": Decimal("5.00"),
        })
        assert tf.id_moneda_base is None
        assert MovimientoCajaBanco.objects.filter(
            id_transaccion_financiera=tf, tipo_movimiento="EGRESO"
        ).exists()


class TestPlantillaMaestroSerializerCreateUpdate:
    def _ser(self, user):
        from apps.finanzas.serializers import PlantillaMaestroCajasVirtualesSerializer

        return PlantillaMaestroCajasVirtualesSerializer(
            context={"request": SimpleNamespace(user=user)}
        )

    def test_create_asigna_empresa_creador_monedas_y_metodos(
        self, user_a, empresa_a, moneda_usd, metodo_a
    ):
        ser = self._ser(user_a)
        instancia = ser.create({
            "nombre": "Plantilla Gaps",
            "moneda_base": moneda_usd,  # requerido por el modelo (NOT NULL)
            "monedas": [str(moneda_usd.id_moneda)],
            "metodos_pago": [str(metodo_a.id_metodo_pago)],
        })
        assert instancia.empresa == empresa_a
        assert instancia.creada_por == user_a
        assert instancia.moneda_base == moneda_usd
        assert list(instancia.metodos_pago_base.all()) == [metodo_a]

    def test_create_moneda_inexistente_se_ignora(self, user_a, empresa_a, moneda_usd):
        ser = self._ser(user_a)
        instancia = ser.create({
            "nombre": "Plantilla Gaps 2",
            "moneda_base": moneda_usd,
            "monedas": [str(uuid.uuid4())],  # rama DoesNotExist → pass
            "metodos_pago": [],
        })
        assert instancia.moneda_base == moneda_usd

    def test_update_cambia_moneda_y_metodos(self, user_a, empresa_a, moneda_usd, metodo_a):
        otra_moneda = Moneda.objects.create(
            nombre="Real", codigo_iso="BRL", simbolo="R$", tipo_moneda="fiat",
        )
        plantilla = PlantillaMaestroCajasVirtuales.objects.create(
            empresa=empresa_a, nombre="Para Update", moneda_base=moneda_usd
        )
        ser = self._ser(user_a)
        actualizada = ser.update(plantilla, {
            "nombre": "Actualizada",
            "monedas": [str(otra_moneda.id_moneda)],
            "metodos_pago": [str(metodo_a.id_metodo_pago)],
        })
        assert actualizada.nombre == "Actualizada"
        assert actualizada.moneda_base == otra_moneda
        assert list(actualizada.metodos_pago_base.all()) == [metodo_a]

    def test_update_moneda_inexistente_conserva_la_actual(self, user_a, empresa_a, moneda_usd):
        plantilla = PlantillaMaestroCajasVirtuales.objects.create(
            empresa=empresa_a, nombre="Conserva", moneda_base=moneda_usd
        )
        ser = self._ser(user_a)
        actualizada = ser.update(plantilla, {"monedas": [str(uuid.uuid4())], "metodos_pago": []})
        assert actualizada.moneda_base == moneda_usd


class TestCajaVirtualDisponibleSerializer:
    def _ser(self, user):
        from apps.finanzas.serializers import CajaVirtualDisponibleSerializer

        return CajaVirtualDisponibleSerializer(context={"request": SimpleNamespace(user=user)})

    def test_get_usuario_autenticado(self, user_a, caja_virtual_a):
        assert self._ser(user_a).get_usuario(caja_virtual_a) == str(user_a.id)

    def test_get_es_predeterminada_primera_registradora(
        self, user_a, empresa_a, moneda_usd, caja_fisica_a
    ):
        # Las cajas virtuales "disponibles" salen de la jerarquía física:
        # CajaFisicaUsuario → cajas virtuales con esa caja_fisica.
        CajaFisicaUsuario.objects.create(usuario=user_a, caja_fisica=caja_fisica_a)
        caja = Caja.objects.create(
            empresa=empresa_a, nombre="Registradora F", moneda=moneda_usd,
            tipo_caja="REGISTRADORA", caja_fisica=caja_fisica_a,
        )
        ser = self._ser(user_a)
        assert ser.get_es_predeterminada(caja) is True
        otra = Caja.objects.create(
            empresa=empresa_a, nombre="Registradora G", moneda=moneda_usd,
            tipo_caja="REGISTRADORA", caja_fisica=caja_fisica_a,
        )
        assert ser.get_es_predeterminada(otra) is False

    def test_get_es_predeterminada_sin_cajas_es_falsy(self, user_a, caja_virtual_a):
        ser = self._ser(user_a)
        assert not ser.get_es_predeterminada(caja_virtual_a)

    def test_get_fecha_asignacion_devuelve_iso(self, user_a, caja_virtual_a):
        valor = self._ser(user_a).get_fecha_asignacion(caja_virtual_a)
        assert "T" in valor  # ISO-8601


# ══════════════════════════════════════════════════════════════════════════════
# apps/finanzas/models.py — ramas restantes
# ══════════════════════════════════════════════════════════════════════════════

class TestStrRestantes:
    def test_strs(self, empresa_a, moneda_usd, user_a, caja_virtual_a, cuenta_a, caja_fisica_a):
        tf = TransaccionFinanciera(
            tipo_transaccion="INGRESO", monto_transaccion=Decimal("9.99")
        )
        assert str(tf) == "INGRESO - 9.99"
        assert "Caja Gaps" in str(caja_virtual_a)
        assert str(cuenta_a) == "Banco Gaps - 0102-GAP"
        cfu = CajaFisicaUsuario(usuario=user_a, caja_fisica=caja_fisica_a)
        assert str(cfu) == "user_empresa_a - Caja Principal Test"
        cvu = CajaVirtualUsuario(usuario=user_a, caja_virtual=caja_virtual_a)
        assert str(cvu) == "user_empresa_a - Caja Gaps"
        cu = CajaUsuario(usuario=user_a, caja=caja_virtual_a)
        assert str(cu) == "user_empresa_a - Caja Gaps"
        ahora = timezone.now()
        mov = MovimientoCajaBanco(
            tipo_movimiento="INGRESO", monto=Decimal("3.00"),
            fecha_movimiento=ahora.date(),
        )
        assert str(mov) == f"INGRESO - 3.00 ({ahora.date()})"

    def test_strs_datafono(self, empresa_a, moneda_usd, user_a):
        from apps.core.models import Sucursal

        sucursal = Sucursal.objects.create(
            id_empresa=empresa_a, nombre="Suc Str", codigo_sucursal="SS1"
        )
        cuenta = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_a, nombre_banco="BS", numero_cuenta="9",
            tipo_cuenta="CORRIENTE", id_moneda=moneda_usd,
        )
        datafono = Datafono.objects.create(
            id_empresa=empresa_a, id_sucursal=sucursal, nombre="POS Str",
            serial="ST-1", id_cuenta_bancaria_asociada=cuenta,
        )
        assert str(datafono) == "POS Str - ST-1"
        sesion = SesionDatafono.objects.create(datafono=datafono, usuario_apertura=user_a)
        assert "POS Str" in str(sesion)
        trans = TransaccionDatafono(id_datafono=datafono, monto=Decimal("7.00"), estado="PENDIENTE")
        assert str(trans) == "Transacción en POS Str - 7.00 (Pendiente)"
        deposito = DepositoDatafono(
            datafono=datafono, lote_bancario="L-1", total_neto=Decimal("6.86")
        )
        assert str(deposito) == "Depósito L-1 - POS Str - 6.86"


class TestPlantillaYCajasVirtualesAuto:
    @pytest.fixture
    def plantilla(self, empresa_a, moneda_usd, metodo_a):
        plantilla = PlantillaMaestroCajasVirtuales.objects.create(
            empresa=empresa_a, nombre="Plantilla Auto", moneda_base=moneda_usd
        )
        plantilla.metodos_pago_base.add(metodo_a)
        return plantilla

    def test_crear_cajas_para_caja_fisica_crea_cajas_virtuales(self, plantilla, caja_fisica_a, metodo_a):
        # FIX (lote 2): CajaFisica.metodo_pago_deshabilitado no existía →
        # AttributeError. Ahora consulta los overrides y la creación funciona.
        creadas = plantilla.crear_cajas_para_caja_fisica(caja_fisica_a)
        assert len(creadas) == 1
        auto = creadas[0]
        assert auto.caja_fisica == caja_fisica_a
        assert auto.metodo_pago == metodo_a
        assert auto.activa is True
        # Idempotente: una segunda llamada no duplica
        assert plantilla.crear_cajas_para_caja_fisica(caja_fisica_a) == []

    def test_crear_cajas_respeta_override_deshabilitado(
        self, plantilla, caja_fisica_a, metodo_a, empresa_a
    ):
        from apps.core.models import Sucursal
        from apps.finanzas.models import CajaMetodoPagoOverride

        sucursal = Sucursal.objects.create(
            id_empresa=empresa_a, nombre="Suc Override", codigo_sucursal="SOV"
        )
        CajaMetodoPagoOverride.objects.create(
            caja_fisica=caja_fisica_a, metodo_pago=metodo_a,
            sucursal=sucursal, deshabilitado=True,
        )
        assert plantilla.crear_cajas_para_caja_fisica(caja_fisica_a) == []

    def test_sincronizar_con_plantilla_empleado(self, plantilla, user_a, moneda_usd, metodo_a):
        auto = CajaVirtualAuto.objects.create(
            empleado=user_a, plantilla_maestro=plantilla,
            moneda=moneda_usd, metodo_pago=metodo_a,
        )
        # __str__ rama "Empleado"
        assert "Plantilla Auto" in str(auto)
        auto.sincronizar_con_plantilla()
        auto.refresh_from_db()
        assert auto.activa is True
        plantilla.activa = False
        plantilla.save()
        auto.sincronizar_con_plantilla()
        auto.refresh_from_db()
        assert auto.activa is False

    def test_sincronizar_con_caja_fisica(self, plantilla, caja_fisica_a, moneda_usd, metodo_a):
        # FIX (lote 2, x2): el FK CajaVirtualAuto.caja_fisica apuntaba a Caja
        # (virtual) — ahora apunta a CajaFisica (migración 0039) — y
        # metodo_pago_deshabilitado ya existe en CajaFisica.
        auto = CajaVirtualAuto.objects.create(
            caja_fisica=caja_fisica_a, plantilla_maestro=plantilla,
            moneda=moneda_usd, metodo_pago=metodo_a,
        )
        assert "Plantilla Auto" in str(auto)  # __str__ rama "Física"
        auto.sincronizar_con_plantilla()
        auto.refresh_from_db()
        assert auto.activa is True
        plantilla.activa = False
        plantilla.save()
        auto.sincronizar_con_plantilla()
        auto.refresh_from_db()
        assert auto.activa is False

    def test_crear_caja_virtual_en_sesion_delegacion(self, plantilla, user_a, moneda_usd, metodo_a):
        auto = CajaVirtualAuto.objects.create(
            empleado=user_a, plantilla_maestro=plantilla,
            moneda=moneda_usd, metodo_pago=metodo_a,
        )
        capturado = {}

        def _crear(nombre, monedas_ids, metodos_pago_ids, usuario):
            capturado.update(nombre=nombre, monedas=monedas_ids, metodos=metodos_pago_ids, usuario=usuario)
            return "caja-creada"

        sesion = SimpleNamespace(crear_caja_virtual=_crear, usuario=user_a)
        assert auto.crear_caja_virtual_en_sesion(sesion) == "caja-creada"
        assert capturado["monedas"] == [str(moneda_usd.id_moneda)]
        assert capturado["metodos"] == [str(metodo_a.id_metodo_pago)]

    def test_override_post_save_sin_cajas_no_revienta(self, plantilla, caja_fisica_a):
        from apps.finanzas.models import override_post_save

        # invocación directa; sin CajaVirtualAuto asociadas el loop es vacío y
        # no falla. FIX (lote 2): el FK ya apunta a CajaFisica.
        override_post_save(None, SimpleNamespace(caja_fisica=caja_fisica_a), created=True)

    def test_senal_caja_fisica_crea_caja_virtual(self, plantilla, empresa_a, moneda_usd, metodo_a):
        nueva_fisica = CajaFisica.objects.create(
            empresa=empresa_a, nombre="Física Señal",
            identificador_dispositivo="disp-señal",
        )
        caja = Caja.objects.get(caja_fisica=nueva_fisica)
        assert caja.nombre == "Plantilla Auto - Física Señal"
        assert caja.moneda == moneda_usd
        assert list(caja.metodos_pago.all()) == [metodo_a]


class TestAbrirSesionForzada:
    def test_apertura_fuerza_cierre_residual(self, caja_fisica_a, user_a, monkeypatch):
        sesion_previa = SesionCajaFisica.abrir_sesion(caja_fisica_a, user_a)
        # Simular que cerrar_sesion no cierra (p. ej. raza) → se ejercita el
        # cierre forzado vía UPDATE masivo.
        monkeypatch.setattr(SesionCajaFisica, "cerrar_sesion", lambda self, notas=None: None)
        nueva = SesionCajaFisica.abrir_sesion(caja_fisica_a, user_a)
        assert nueva.estado == "ABIERTA"
        sesion_previa.refresh_from_db()
        assert sesion_previa.estado == "CERRADA"
        assert "forzado" in sesion_previa.notas


class TestPagoValidarDocumento:
    """Cubre todas las ramas de Pago._validar_documento y documento_relacionado
    con instancias FK no persistidas (DoesNotExist → ValueError)."""

    def _pago(self, **kwargs):
        return Pago(tipo_operacion="INGRESO", monto=Decimal("1.00"), **kwargs)

    def test_pedido_inexistente(self):
        from apps.ventas.models import Pedido

        pago = self._pago(tipo_documento="PEDIDO", id_pedido=Pedido())
        with pytest.raises(ValueError, match="no existe"):
            pago._validar_documento()
        assert pago.documento_relacionado is pago.id_pedido

    def test_nota_venta_inexistente(self):
        from apps.ventas.models import NotaVenta

        pago = self._pago(tipo_documento="NOTA_VENTA", id_nota_venta=NotaVenta())
        with pytest.raises(ValueError, match="no existe"):
            pago._validar_documento()
        assert pago.documento_relacionado is pago.id_nota_venta

    def test_factura_inexistente(self):
        # FIX (lote 2): la rama importaba FacturaFiscal desde apps.fiscal,
        # pero vive en apps.ventas → ImportError. Ahora valida normal.
        from apps.ventas.models import FacturaFiscal

        pago = self._pago(tipo_documento="FACTURA", id_factura=FacturaFiscal())
        with pytest.raises(ValueError, match="no existe"):
            pago._validar_documento()
        assert pago.documento_relacionado is pago.id_factura

    def test_cxp_inexistente(self):
        from apps.cuentas_por_pagar.models import CuentaPorPagar

        pago = self._pago(tipo_documento="CXP", id_cxp=CuentaPorPagar())
        with pytest.raises(ValueError, match="no existe"):
            pago._validar_documento()
        assert pago.documento_relacionado is pago.id_cxp

    def test_gasto_inexistente(self):
        from apps.gastos.models import Gasto

        pago = self._pago(tipo_documento="GASTO", id_gasto=Gasto())
        with pytest.raises(ValueError, match="no existe"):
            pago._validar_documento()
        assert pago.documento_relacionado is pago.id_gasto

    def test_reembolso_inexistente(self):
        # FIX (lote 2): la rama usaba `id_reembolso_gasto` como PK, pero la PK
        # real es `id_reembolso` → AttributeError. Ahora valida normal.
        from apps.gastos.models import ReembolsoGasto

        pago = self._pago(tipo_documento="REEMBOLSO_GASTO", id_reembolso_gasto=ReembolsoGasto())
        with pytest.raises(ValueError, match="no existe"):
            pago._validar_documento()
        assert pago.documento_relacionado is pago.id_reembolso_gasto

    def test_nomina_inexistente(self):
        from apps.nomina.models import Nomina

        pago = self._pago(tipo_documento="NOMINA", id_nomina=Nomina())
        with pytest.raises(ValueError, match="no existe"):
            pago._validar_documento()
        assert pago.documento_relacionado is pago.id_nomina

    def test_impuesto_inexistente(self):
        # FIX (lote 2): la rama usaba `id_contribucion.id_contribucion`,
        # atributo inexistente (la PK es la implícita `pk`) → AttributeError.
        from apps.fiscal.models import ContribucionParafiscal

        pago = self._pago(tipo_documento="IMPUESTO", id_contribucion=ContribucionParafiscal())
        with pytest.raises(ValueError, match="no existe"):
            pago._validar_documento()
        assert pago.documento_relacionado is pago.id_contribucion

    def test_sin_documento_no_valida_y_relacionado_none(self):
        pago = self._pago(tipo_documento="AJUSTE")
        pago._validar_documento()  # no levanta
        assert pago.documento_relacionado is None
