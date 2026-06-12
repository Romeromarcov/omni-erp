"""
Diff-coverage ≥95 — ramas reales no cubiertas de finanzas / tesorería / ventas
(rama develop d19403a). Cada test cita la(s) línea(s) objetivo que ejercita.

Objetivos cubiertos aquí:
- apps/finanzas/views.py: SesionCajaFisicaViewSet (cerrar, transferir-entre-cajas
  reparado en CTF-015.1, perform_create reparado en bugs lote 3),
  buscar_reutilizar, CajaFisicaViewSet cierre/cerrar-sesion, scope de tenant del
  serializer de overrides (CajaMetodoPagoOverride).
- apps/finanzas/serializers.py: 43
- apps/finanzas/utils_transferencias.py: 22-23, 25, 50
- apps/tesoreria/serializers.py: 89, 106, 110-111, 118-119, 122, 129-130, 133, 191
- apps/tesoreria/services.py: 251-253
- apps/ventas/services.py: 642

No-cubribles (justificación en cada clase):
- apps/finanzas/views.py 368 (paginación global siempre activa).
- apps/tesoreria/services.py 242, 245 (defensa de carreras BUG-M5; solo
  alcanzable con interleaving concurrente real).

Nota CTF-015.1: las líneas del flujo de transferencia (antes 152-159,
documentadas como no-cubribles por el AttributeError fosilizado) quedaron
cubiertas al reparar el endpoint — ver TestSesionCajaTransferirEntreCajas.
"""
import datetime
import uuid
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.finanzas.models import (
    Caja,
    CuentaBancariaEmpresa,
    MetodoPago,
    MetodoPagoEmpresaActiva,
    Moneda,
    MovimientoCajaBanco,
    Pago,
    SesionCajaFisica,
    TasaCambio,
    TransaccionFinanciera,
)
from apps.finanzas.utils_transferencias import transferencia_entre_cajas
from apps.tesoreria.models import MovimientoBancario, OperacionCambioDivisa

pytestmark = pytest.mark.django_db

URL_SESIONES = "/api/finanzas/sesiones-caja/"
URL_SESION_CERRAR = "/api/finanzas/sesiones-caja/{}/cerrar/"
URL_SESION_TRANSFERIR = "/api/finanzas/sesiones-caja/{}/transferir-entre-cajas/"
URL_OVERRIDES = "/api/finanzas/overrides-metodos-pago/"
URL_CF_CIERRE = "/api/finanzas/cajas-fisicas/{}/cierre/"
URL_CF_CERRAR_SESION = "/api/finanzas/cajas-fisicas/{}/cerrar-sesion/"
URL_BUSCAR_REUTILIZAR = "/api/finanzas/metodos-pago/buscar_reutilizar/"
URL_MPEA = "/api/finanzas/metodos-pago-empresa-activas/"
URL_CAMBIO = "/api/tesoreria/operaciones-cambio-divisa/"

# Saldo numéricamente válido (Decimal lo parsea) pero que desborda los
# DecimalField(18, 2) al persistir → excepción NO-ValueError (InvalidOperation
# o DataError) que debe traducirse a 400 controlado, nunca a 500.
SALDO_DESBORDADO = "1E+30"


@pytest.fixture
def client_a(user_a):
    client = APIClient()
    client.force_authenticate(user=user_a)
    return client


@pytest.fixture
def caja_virtual_a(empresa_a, moneda_usd, caja_fisica_a):
    return Caja.objects.create(
        empresa=empresa_a,
        nombre="Registradora DC95",
        moneda=moneda_usd,
        caja_fisica=caja_fisica_a,
        saldo_actual=Decimal("0.00"),
    )


@pytest.fixture
def sesion_abierta(caja_fisica_a, user_a):
    return SesionCajaFisica.abrir_sesion(caja_fisica=caja_fisica_a, usuario=user_a)


# ── apps/finanzas/views.py — SesionCajaFisicaViewSet.cerrar ──────────────────


class TestSesionCajaCerrarValidaciones:
    def test_hasta_invalido_devuelve_400(self, client_a, sesion_abierta):
        """views.py:114 — 'hasta' no parseable → 400 con mensaje de negocio."""
        resp = client_a.post(
            URL_SESION_CERRAR.format(sesion_abierta.id_sesion),
            {"hasta": "esto-no-es-fecha"},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"] == "El parámetro 'hasta' no tiene un formato de fecha/hora válido."
        sesion_abierta.refresh_from_db()
        assert sesion_abierta.estado == "ABIERTA"

    def test_error_no_de_negocio_devuelve_400_generico(
        self, client_a, sesion_abierta, caja_fisica_a
    ):
        """views.py:127-129 — excepción NO-ValueError durante el cierre
        (desborde numérico al persistir el corte) → 400 genérico sin detalles
        internos, y nada queda persistido."""
        resp = client_a.post(
            URL_SESION_CERRAR.format(sesion_abierta.id_sesion),
            {"saldos_reales": {str(caja_fisica_a.id_caja_fisica): SALDO_DESBORDADO}},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"] == "No se pudo cerrar la sesión. Intente de nuevo."
        sesion_abierta.refresh_from_db()
        assert sesion_abierta.estado == "ABIERTA"
        assert not caja_fisica_a.movimientos.filter(tipo_movimiento="CIERRE").exists()


class TestSesionCajaTransferirEntreCajas:
    """CTF-015.1 — transferir-entre-cajas REPARADO: antes ``sesion.cajas`` no
    existía (la relación real es ``caja_fisica.cajas_virtuales``), el
    AttributeError caía en un ``except Exception`` y el endpoint respondía 400
    SIEMPRE. Estos tests exigen el comportamiento correcto: camino feliz 200
    con efectos en BD y ramas de error reales (caja ajena/inexistente/
    malformada, monto inválido, saldo insuficiente)."""

    @pytest.fixture
    def caja_gerencia_a(self, empresa_a, moneda_usd, caja_fisica_a):
        """Segunda caja virtual de la MISMA sesión, con saldo para transferir."""
        return Caja.objects.create(
            empresa=empresa_a,
            nombre="Gerencia DC95",
            moneda=moneda_usd,
            caja_fisica=caja_fisica_a,
            saldo_actual=Decimal("50.00"),
        )

    def test_transferencia_feliz_200_con_efectos_en_bd(
        self, client_a, sesion_abierta, caja_virtual_a, caja_gerencia_a
    ):
        """Camino feliz: 200, doble movimiento persistido y saldos Decimal
        actualizados en ambas cajas de la sesión."""
        resp = client_a.post(
            URL_SESION_TRANSFERIR.format(sesion_abierta.id_sesion),
            {
                "caja_origen": str(caja_gerencia_a.id_caja),
                "caja_destino": str(caja_virtual_a.id_caja),
                "monto": "10.50",
            },
            format="json",
        )
        assert resp.status_code == 200, resp.content
        assert resp.data["monto"] == "10.50"
        mov_salida = MovimientoCajaBanco.objects.get(tipo_movimiento="TRANSFERENCIA_SALIDA")
        mov_entrada = MovimientoCajaBanco.objects.get(tipo_movimiento="TRANSFERENCIA_ENTRADA")
        assert resp.data["movimiento_salida_id"] == mov_salida.id_movimiento
        assert resp.data["movimiento_entrada_id"] == mov_entrada.id_movimiento
        assert mov_salida.monto == Decimal("10.50")
        assert mov_salida.id_caja_id == caja_gerencia_a.pk
        assert mov_entrada.id_caja_id == caja_virtual_a.pk
        caja_gerencia_a.refresh_from_db()
        caja_virtual_a.refresh_from_db()
        assert caja_gerencia_a.saldo_actual == Decimal("39.50")
        assert caja_virtual_a.saldo_actual == Decimal("10.50")

    def test_caja_destino_inexistente_400_sin_efectos(
        self, client_a, sesion_abierta, caja_gerencia_a
    ):
        resp = client_a.post(
            URL_SESION_TRANSFERIR.format(sesion_abierta.id_sesion),
            {
                "caja_origen": str(caja_gerencia_a.id_caja),
                "caja_destino": str(uuid.uuid4()),
                "monto": "10.00",
            },
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"] == "Caja origen o destino no pertenece a la sesión."
        assert not MovimientoCajaBanco.objects.filter(
            tipo_movimiento__in=["TRANSFERENCIA_SALIDA", "TRANSFERENCIA_ENTRADA"]
        ).exists()

    def test_caja_de_otra_empresa_400_sin_filtrar_existencia(
        self, client_a, sesion_abierta, caja_gerencia_a, empresa_b, moneda_usd
    ):
        """R-CODE-1: una caja virtual REAL de otra empresa (otra caja física)
        no es transferible desde esta sesión — mismo mensaje que inexistente."""
        from apps.finanzas.models import CajaFisica

        caja_fisica_b = CajaFisica.objects.create(
            empresa=empresa_b, nombre="Caja B", identificador_dispositivo="dev-b-transf"
        )
        caja_b = Caja.objects.create(
            empresa=empresa_b,
            nombre="Registradora B",
            moneda=moneda_usd,
            caja_fisica=caja_fisica_b,
            saldo_actual=Decimal("500.00"),
        )
        resp = client_a.post(
            URL_SESION_TRANSFERIR.format(sesion_abierta.id_sesion),
            {
                "caja_origen": str(caja_gerencia_a.id_caja),
                "caja_destino": str(caja_b.id_caja),
                "monto": "10.00",
            },
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"] == "Caja origen o destino no pertenece a la sesión."
        caja_b.refresh_from_db()
        assert caja_b.saldo_actual == Decimal("500.00")
        assert MovimientoCajaBanco.objects.count() == 0

    def test_caja_malformada_400_controlado(self, client_a, sesion_abierta, caja_gerencia_a):
        """Un id no-UUID no revienta en 500: la ValidationError del lookup se
        traduce al mismo 400 de negocio."""
        resp = client_a.post(
            URL_SESION_TRANSFERIR.format(sesion_abierta.id_sesion),
            {
                "caja_origen": "no-es-un-uuid",
                "caja_destino": str(caja_gerencia_a.id_caja),
                "monto": "10.00",
            },
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"] == "Caja origen o destino no pertenece a la sesión."

    def test_monto_invalido_400_mensaje_de_negocio(
        self, client_a, sesion_abierta, caja_virtual_a, caja_gerencia_a
    ):
        """Rama ValueError del helper: monto no numérico → 400 con mensaje de
        negocio, sin detalles internos y sin efectos en BD."""
        resp = client_a.post(
            URL_SESION_TRANSFERIR.format(sesion_abierta.id_sesion),
            {
                "caja_origen": str(caja_gerencia_a.id_caja),
                "caja_destino": str(caja_virtual_a.id_caja),
                "monto": "abc",
            },
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"] == "El monto de la transferencia no es un número válido."
        assert MovimientoCajaBanco.objects.count() == 0

    def test_saldo_insuficiente_400_sin_efectos(
        self, client_a, sesion_abierta, caja_virtual_a, caja_gerencia_a
    ):
        resp = client_a.post(
            URL_SESION_TRANSFERIR.format(sesion_abierta.id_sesion),
            {
                "caja_origen": str(caja_virtual_a.id_caja),  # saldo 0.00
                "caja_destino": str(caja_gerencia_a.id_caja),
                "monto": "10.00",
            },
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"] == "Saldo insuficiente en la caja origen para la transferencia."
        caja_gerencia_a.refresh_from_db()
        assert caja_gerencia_a.saldo_actual == Decimal("50.00")
        assert MovimientoCajaBanco.objects.count() == 0


# ── apps/finanzas/views.py — SesionCajaFisicaViewSet.perform_create ──────────


class TestSesionCajaFisicaCreacion:
    """Bug lote 3 — POST /sesiones-caja/ reventaba con FieldError 500: buscaba
    ``Caja`` (virtual) con el campo inexistente ``es_fisica``; además pasaba
    kwargs que ``abrir_sesion`` no acepta y llamaba un método inexistente, y la
    búsqueda no estaba acotada al tenant. Estos tests exigen la creación feliz
    y el aislamiento R-CODE-1."""

    @pytest.fixture
    def caja_fisica_b(self, empresa_b):
        from apps.finanzas.models import CajaFisica

        return CajaFisica.objects.create(
            empresa=empresa_b, nombre="Caja B", identificador_dispositivo="dev-b-sesion"
        )

    def test_creacion_feliz_201_con_sesion_abierta(self, client_a, caja_fisica_a, user_a, empresa_a):
        resp = client_a.post(
            URL_SESIONES,
            {
                "caja_fisica_principal": str(caja_fisica_a.id_caja_fisica),
                "observaciones": "apertura turno mañana",
            },
            format="json",
        )
        assert resp.status_code == 201, resp.content
        sesion = SesionCajaFisica.objects.get(caja_fisica=caja_fisica_a)
        assert sesion.estado == "ABIERTA"
        assert sesion.usuario == user_a
        assert sesion.empresa == empresa_a  # R-CODE-1: derivada de la caja, no del payload
        assert sesion.notas == "apertura turno mañana"
        # La respuesta refleja la sesión REAL creada (no el eco del payload).
        assert resp.data["id_sesion"] == str(sesion.id_sesion)
        assert resp.data["estado"] == "ABIERTA"
        assert resp.data["caja_fisica_principal"]["id_caja"] == str(caja_fisica_a.id_caja_fisica)

    def test_sin_caja_fisica_principal_400(self, client_a):
        resp = client_a.post(URL_SESIONES, {}, format="json")
        assert resp.status_code == 400
        assert resp.data["caja_fisica_principal"] == (
            "Debe especificar la caja física para abrir la sesión"
        )
        assert SesionCajaFisica.objects.count() == 0

    def test_caja_de_otra_empresa_400_sin_filtrar_existencia(self, client_a, caja_fisica_b):
        """R-CODE-1: una caja física REAL de otra empresa responde el mismo 400
        que una inexistente — no se puede abrir sesión ni inferir existencia."""
        resp = client_a.post(
            URL_SESIONES,
            {"caja_fisica_principal": str(caja_fisica_b.id_caja_fisica)},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["caja_fisica_principal"] == "Caja física no encontrada o no válida"
        assert SesionCajaFisica.objects.count() == 0

    def test_caja_inexistente_400(self, client_a, empresa_a):
        resp = client_a.post(
            URL_SESIONES, {"caja_fisica_principal": str(uuid.uuid4())}, format="json"
        )
        assert resp.status_code == 400
        assert resp.data["caja_fisica_principal"] == "Caja física no encontrada o no válida"
        assert SesionCajaFisica.objects.count() == 0

    def test_caja_malformada_400_controlado(self, client_a, empresa_a):
        """Un id no-UUID no revienta en 500: ValidationError del lookup → 400."""
        resp = client_a.post(
            URL_SESIONES, {"caja_fisica_principal": "no-es-un-uuid"}, format="json"
        )
        assert resp.status_code == 400
        assert resp.data["caja_fisica_principal"] == "Caja física no encontrada o no válida"
        assert SesionCajaFisica.objects.count() == 0

    def test_caja_inactiva_400(self, client_a, caja_fisica_a):
        caja_fisica_a.activa = False
        caja_fisica_a.save(update_fields=["activa"])
        resp = client_a.post(
            URL_SESIONES,
            {"caja_fisica_principal": str(caja_fisica_a.id_caja_fisica)},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["caja_fisica_principal"] == "Caja física no encontrada o no válida"
        assert SesionCajaFisica.objects.count() == 0


# ── apps/finanzas/serializers.py — CajaMetodoPagoOverrideSerializer (tenant) ──


class TestCajaMetodoPagoOverrideScopeTenant:
    """Revisión bugs lote 3 — scoping multi-tenant del serializer de overrides.

    El serializer declara querysets SIN filtrar (``CajaFisica.objects.all()``,
    ``MetodoPago.objects.all()``, ``Sucursal.objects.all()``), pero el ViewSet
    hereda de BaseModelViewSet → TenantFKScopeMixin (SEC-M1), que en
    ``get_serializer`` acota TODO RelatedField writable a las empresas
    visibles del usuario. Estos tests fijan ese comportamiento como contrato:
    un id de la Empresa B debe responder 400 para un usuario de la Empresa A
    (sin persistir nada) y el camino feliz same-tenant sigue funcionando."""

    @pytest.fixture
    def setup_b(self, empresa_b):
        from apps.core.models import Sucursal
        from apps.finanzas.models import CajaFisica

        sucursal_b = Sucursal.objects.create(
            id_empresa=empresa_b, nombre="Sucursal B", codigo_sucursal="SB-OV"
        )
        caja_fisica_b = CajaFisica.objects.create(
            empresa=empresa_b, nombre="Caja B Override", identificador_dispositivo="dev-b-override"
        )
        metodo_b = MetodoPago.objects.create(
            nombre_metodo="Zelle Privado B",
            tipo_metodo="ELECTRONICO",
            empresa=empresa_b,
            es_generico=False,
            es_publico=False,
        )
        return {"sucursal": sucursal_b, "caja_fisica": caja_fisica_b, "metodo": metodo_b}

    def test_post_con_fks_de_otra_empresa_400_y_nada_persiste(self, client_a, setup_b):
        from apps.finanzas.models import CajaMetodoPagoOverride

        resp = client_a.post(
            URL_OVERRIDES,
            {
                "caja_fisica": str(setup_b["caja_fisica"].id_caja_fisica),
                "metodo_pago": str(setup_b["metodo"].id_metodo_pago),
                "sucursal": str(setup_b["sucursal"].id_sucursal),
                "deshabilitado": True,
                "motivo": "intento cross-tenant",
            },
            format="json",
        )
        assert resp.status_code == 400, resp.content
        # Los tres FKs ajenos deben rechazarse como inexistentes (no se filtra
        # que el objeto exista en otra empresa).
        for campo in ("caja_fisica", "metodo_pago", "sucursal"):
            assert campo in resp.data, resp.data
            assert "no existe" in str(resp.data[campo][0])
        assert CajaMetodoPagoOverride.objects.count() == 0

    def test_post_same_tenant_201_con_creado_por_del_request(
        self, client_a, user_a, empresa_a, caja_fisica_a
    ):
        from apps.core.models import Sucursal
        from apps.finanzas.models import CajaMetodoPagoOverride

        sucursal_a = Sucursal.objects.create(
            id_empresa=empresa_a, nombre="Sucursal A", codigo_sucursal="SA-OV"
        )
        metodo_a = MetodoPago.objects.create(
            nombre_metodo="Efectivo A Override", tipo_metodo="EFECTIVO", empresa=empresa_a
        )
        resp = client_a.post(
            URL_OVERRIDES,
            {
                "caja_fisica": str(caja_fisica_a.id_caja_fisica),
                "metodo_pago": str(metodo_a.id_metodo_pago),
                "sucursal": str(sucursal_a.id_sucursal),
                "deshabilitado": True,
                "motivo": "POS dañado",
            },
            format="json",
        )
        assert resp.status_code == 201, resp.content
        override = CajaMetodoPagoOverride.objects.get()
        assert override.caja_fisica == caja_fisica_a
        assert override.creado_por == user_a  # inyectado del request, no del payload


# ── apps/finanzas/views.py — MetodoPagoViewSet.buscar_reutilizar ─────────────


class TestBuscarReutilizar:
    def test_id_empresa_actual_malformado_404(self, client_a):
        """views.py:349-350 — id_empresa_actual no-UUID → DjangoValidationError
        capturada → empresa_visible=False → 404 sin filtrar existencia."""
        resp = client_a.get(URL_BUSCAR_REUTILIZAR, {"id_empresa_actual": "no-es-un-uuid"})
        assert resp.status_code == 404
        assert resp.data == {"detail": "Empresa no encontrada."}

    def test_empresa_ajena_404_sin_filtrar_existencia(self, client_a, empresa_b):
        """views.py:351-352 (complemento de 349-350) — empresa real pero NO
        visible para el usuario → mismo 404 (no es un oráculo cross-tenant).
        Nota: la rama 368 (respuesta sin paginar) es no-cubrible: la paginación
        global PageNumberPagination con PAGE_SIZE=20 nunca devuelve page=None."""
        resp = client_a.get(URL_BUSCAR_REUTILIZAR, {"id_empresa_actual": str(empresa_b.id_empresa)})
        assert resp.status_code == 404
        assert resp.data == {"detail": "Empresa no encontrada."}


# ── apps/finanzas/views.py — CajaFisicaViewSet cierre / cerrar-sesion ────────


class TestCajaFisicaCierreYSesion:
    def test_cierre_con_saldo_desbordado_400_controlado(self, client_a, caja_fisica_a):
        """views.py:1121-1123 — excepción NO-ValueError en realizar_cierre
        (desborde numérico al persistir) → 400 genérico y sin corte persistido."""
        resp = client_a.post(
            URL_CF_CIERRE.format(caja_fisica_a.id_caja_fisica),
            {"saldo_real": SALDO_DESBORDADO},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"] == "No se pudo realizar el cierre. Intente de nuevo."
        assert not caja_fisica_a.movimientos.filter(tipo_movimiento="CIERRE").exists()

    def test_cerrar_sesion_saldos_reales_no_dict_400(self, client_a, caja_fisica_a, sesion_abierta):
        """views.py:1179 — saldos_reales no-dict → 400 con mensaje claro."""
        resp = client_a.post(
            URL_CF_CERRAR_SESION.format(caja_fisica_a.id_caja_fisica),
            {"saldos_reales": ["100.00"]},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"] == "saldos_reales debe ser un objeto {id_caja: saldo_real}."
        sesion_abierta.refresh_from_db()
        assert sesion_abierta.estado == "ABIERTA"

    def test_cerrar_sesion_hasta_invalido_400(self, client_a, caja_fisica_a, sesion_abierta):
        """views.py:1183 — 'hasta' no parseable → 400 y la sesión sigue abierta."""
        resp = client_a.post(
            URL_CF_CERRAR_SESION.format(caja_fisica_a.id_caja_fisica),
            {"hasta": "31/12/no-fecha"},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"] == "El parámetro 'hasta' no tiene un formato de fecha/hora válido."
        sesion_abierta.refresh_from_db()
        assert sesion_abierta.estado == "ABIERTA"

    def test_cerrar_sesion_error_no_de_negocio_400_controlado(
        self, client_a, caja_fisica_a, sesion_abierta
    ):
        """views.py:1194-1196 — excepción NO-ValueError al cerrar (desborde
        numérico) → 400 genérico; sesión y cortes intactos (rollback)."""
        resp = client_a.post(
            URL_CF_CERRAR_SESION.format(caja_fisica_a.id_caja_fisica),
            {"saldos_reales": {str(caja_fisica_a.id_caja_fisica): SALDO_DESBORDADO}},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"] == "No se pudo cerrar la sesión. Intente de nuevo."
        sesion_abierta.refresh_from_db()
        assert sesion_abierta.estado == "ABIERTA"
        assert not caja_fisica_a.movimientos.filter(tipo_movimiento="CIERRE").exists()


# ── apps/finanzas/serializers.py — MetodoPagoEmpresaActivaSerializer ─────────


class TestMetodoPagoEmpresaActivaSinEmpresa:
    def test_usuario_autenticado_sin_empresa_400(self, db):
        """serializers.py:43 — usuario sin empresa asignada → 400 con error de
        negocio y nada creado (la empresa se inyecta SIEMPRE del usuario)."""
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(
            username="sin_empresa_dc95", password="x12345678", is_active=True
        )
        metodo = MetodoPago.objects.create(nombre_metodo="Pago Móvil DC95", tipo_metodo="ELECTRONICO")
        client = APIClient()
        client.force_authenticate(user=user)

        resp = client.post(
            URL_MPEA,
            {"metodo_pago": str(metodo.id_metodo_pago), "activa": True},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["empresa"] == "El usuario no tiene empresa asignada."
        assert MetodoPagoEmpresaActiva.objects.count() == 0


# ── apps/finanzas/utils_transferencias.py ────────────────────────────────────


class TestTransferenciaEntreCajasUtils:
    @pytest.fixture
    def cajas_ab(self, empresa_a, moneda_usd):
        origen = Caja.objects.create(
            empresa=empresa_a, nombre="Origen DC95", moneda=moneda_usd, saldo_actual=Decimal("100.00")
        )
        destino = Caja.objects.create(
            empresa=empresa_a, nombre="Destino DC95", moneda=moneda_usd, saldo_actual=Decimal("20.00")
        )
        return origen, destino

    def test_monto_no_numerico_valueerror(self, cajas_ab):
        """utils_transferencias.py:22-23 — Decimal('abc') → InvalidOperation
        capturada y traducida a ValueError de negocio."""
        origen, destino = cajas_ab
        with pytest.raises(ValueError, match="no es un número válido"):
            transferencia_entre_cajas(origen, destino, "abc")
        assert MovimientoCajaBanco.objects.count() == 0

    def test_monto_no_finito_valueerror(self, cajas_ab):
        """utils_transferencias.py:25 — 'NaN' parsea como Decimal pero no es
        finito → ValueError de negocio (no mueve saldo)."""
        origen, destino = cajas_ab
        with pytest.raises(ValueError, match="no es un número válido"):
            transferencia_entre_cajas(origen, destino, "NaN")
        assert MovimientoCajaBanco.objects.count() == 0

    def test_empresa_removida_entre_chequeo_y_lock_valueerror(self, cajas_ab):
        """utils_transferencias.py:50 — re-validación TOCTOU sobre las filas
        lockeadas: la instancia en memoria aún tiene empresa, pero la fila en
        BD quedó sin empresa (cambio concurrente simulado vía .update()) →
        ValueError y cero movimientos."""
        origen, destino = cajas_ab
        Caja.objects.filter(pk=origen.pk).update(empresa=None)
        assert origen.empresa_id is not None  # pre-chequeo (línea 28) pasa con el valor viejo
        with pytest.raises(ValueError, match="deben tener empresa asignada"):
            transferencia_entre_cajas(origen, destino, "10.00")
        assert MovimientoCajaBanco.objects.count() == 0
        destino.refresh_from_db()
        assert destino.saldo_actual == Decimal("20.00")

    def test_transferencia_feliz_doble_movimiento_y_saldos(self, cajas_ab, user_a):
        """Camino feliz del helper: doble movimiento atómico y saldos Decimal."""
        origen, destino = cajas_ab
        mov_salida, mov_entrada = transferencia_entre_cajas(origen, destino, "30.50", usuario=user_a)
        assert mov_salida.tipo_movimiento == "TRANSFERENCIA_SALIDA"
        assert mov_entrada.tipo_movimiento == "TRANSFERENCIA_ENTRADA"
        assert mov_salida.monto == Decimal("30.50")
        assert mov_salida.saldo_nuevo == Decimal("69.50")
        assert mov_entrada.saldo_nuevo == Decimal("50.50")
        origen.refresh_from_db()
        destino.refresh_from_db()
        assert origen.saldo_actual == Decimal("69.50")
        assert destino.saldo_actual == Decimal("50.50")


# ── apps/tesoreria/serializers.py — OperacionCambioDivisaSerializer ──────────


@pytest.fixture
def moneda_ves(db):
    return Moneda.objects.create(
        nombre="Bolívar", codigo_iso="VES", simbolo="Bs", tipo_moneda="fiat", es_generica=True
    )


@pytest.fixture
def moneda_eur(db):
    return Moneda.objects.create(
        nombre="Euro", codigo_iso="EUR", simbolo="€", tipo_moneda="fiat", es_generica=True
    )


@pytest.fixture
def metodo_efectivo(db):
    return MetodoPago.objects.create(nombre_metodo="Efectivo DC95", tipo_metodo="EFECTIVO")


@pytest.fixture
def cajas_cambio(empresa_a, moneda_usd):
    origen = Caja.objects.create(empresa=empresa_a, nombre="Caja Cambio O", moneda=moneda_usd)
    destino = Caja.objects.create(empresa=empresa_a, nombre="Caja Cambio D", moneda=moneda_usd)
    return origen, destino


def _payload_cambio(empresa, m_origen, m_destino, metodo, cajas, **extra):
    origen, destino = cajas
    payload = {
        "empresa": empresa.id_empresa,
        "numero_operacion": extra.pop("numero_operacion", "DC95-OP1"),
        "fecha_operacion": "2026-06-09T10:00:00Z",
        "tipo_operacion": "COMPRA",
        "moneda_origen": str(m_origen.id_moneda),
        "moneda_destino": str(m_destino.id_moneda),
        "monto_origen": "4000.0000",
        "tasa_cambio": "0.025000",
        "monto_destino": "100.0000",
        "caja_origen": origen.id_caja,
        "caja_destino": destino.id_caja,
        "metodo_pago_origen": str(metodo.id_metodo_pago),
        "metodo_pago_destino": str(metodo.id_metodo_pago),
    }
    payload.update(extra)
    return payload


class TestOperacionCambioDivisaSerializer:
    def test_sin_metodo_pago_destino_400(
        self, client_a, empresa_a, moneda_ves, moneda_usd, metodo_efectivo, cajas_cambio
    ):
        """tesoreria/serializers.py:89 — falta metodo_pago_destino → 400 (el
        ingreso genera una TransaccionFinanciera que lo exige) y nada persiste."""
        payload = _payload_cambio(empresa_a, moneda_ves, moneda_usd, metodo_efectivo, cajas_cambio)
        payload.pop("metodo_pago_destino")
        resp = client_a.post(URL_CAMBIO, payload, format="json")
        assert resp.status_code == 400
        assert "metodo_pago_destino" in resp.data
        assert OperacionCambioDivisa.objects.count() == 0
        assert TransaccionFinanciera.objects.count() == 0

    def test_monto_base_usa_la_tasa_de_la_operacion_origen_a_base(
        self, client_a, empresa_a, moneda_ves, moneda_usd, metodo_efectivo, cajas_cambio
    ):
        """tesoreria/serializers.py:106 — moneda del monto = moneda_origen y
        moneda_destino = moneda base ⇒ se usa la tasa de la propia operación
        (multiplicación), sin requerir TasaCambio registrada."""
        payload = _payload_cambio(empresa_a, moneda_ves, moneda_usd, metodo_efectivo, cajas_cambio)
        resp = client_a.post(URL_CAMBIO, payload, format="json")
        assert resp.status_code == 201, resp.content
        egreso = TransaccionFinanciera.objects.get(tipo_transaccion="EGRESO")
        ingreso = TransaccionFinanciera.objects.get(tipo_transaccion="INGRESO")
        # Egreso 4000 VES * 0.025 (tasa de la operación) = 100.00 USD base
        assert egreso.monto_base_empresa == Decimal("100.00")
        # Ingreso ya está en la moneda base
        assert ingreso.monto_base_empresa == Decimal("100.00")

    def test_monto_base_via_tasa_cambio_directa_e_inversa(
        self, client_a, empresa_a, moneda_ves, moneda_eur, moneda_usd, metodo_efectivo, cajas_cambio
    ):
        """tesoreria/serializers.py:110-111 + 118-119 (TasaCambio directa
        VES→USD para el egreso) y 122 + 129-130 (tasa inversa USD→EUR para el
        ingreso EUR): cambio VES→EUR cuando la base de la empresa es USD."""
        TasaCambio.objects.create(
            id_moneda_origen=moneda_ves,
            id_moneda_destino=moneda_usd,
            tipo_tasa="FIJA",
            valor_tasa=Decimal("0.02500000"),
            fecha_tasa=datetime.date(2026, 6, 1),
        )
        # Solo existe USD→EUR: para convertir EUR→USD debe usarse la inversa.
        TasaCambio.objects.create(
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_eur,
            tipo_tasa="FIJA",
            valor_tasa=Decimal("0.88000000"),
            fecha_tasa=datetime.date(2026, 6, 1),
        )
        payload = _payload_cambio(
            empresa_a,
            moneda_ves,
            moneda_eur,
            metodo_efectivo,
            cajas_cambio,
            numero_operacion="DC95-OP2",
            tasa_cambio="0.022000",
            monto_destino="88.0000",
        )
        resp = client_a.post(URL_CAMBIO, payload, format="json")
        assert resp.status_code == 201, resp.content
        egreso = TransaccionFinanciera.objects.get(tipo_transaccion="EGRESO")
        ingreso = TransaccionFinanciera.objects.get(tipo_transaccion="INGRESO")
        # 4000 VES * 0.025 (TasaCambio directa VES→USD) = 100.00
        assert egreso.monto_base_empresa == Decimal("100.00")
        # 88 EUR / 0.88 (inversa de USD→EUR) = 100.00
        assert ingreso.monto_base_empresa == Decimal("100.00")

    def test_sin_tasa_hacia_la_base_400_y_rollback_total(
        self, client_a, empresa_a, moneda_ves, moneda_eur, metodo_efectivo, cajas_cambio
    ):
        """tesoreria/serializers.py:133 — sin TasaCambio que conecte la moneda
        con la base → 400 pidiendo registrar la tasa, y TODO el doble registro
        se revierte (R-CODE-11)."""
        payload = _payload_cambio(
            empresa_a,
            moneda_ves,
            moneda_eur,
            metodo_efectivo,
            cajas_cambio,
            numero_operacion="DC95-OP3",
            tasa_cambio="0.022000",
            monto_destino="88.0000",
        )
        resp = client_a.post(URL_CAMBIO, payload, format="json")
        assert resp.status_code == 400
        assert "tasa_cambio" in resp.data
        assert "No hay TasaCambio" in str(resp.data["tasa_cambio"])
        assert OperacionCambioDivisa.objects.count() == 0
        assert TransaccionFinanciera.objects.count() == 0
        assert MovimientoCajaBanco.objects.count() == 0

    def test_create_directo_sin_usuario_autenticado_validationerror(
        self, empresa_a, moneda_ves, moneda_usd, metodo_efectivo, cajas_cambio
    ):
        """tesoreria/serializers.py:191 — uso programático del serializer sin
        request autenticado en el contexto → ValidationError de negocio y nada
        persistido (CTF-013: el usuario sale del request)."""
        from rest_framework import serializers as drf_serializers

        from apps.tesoreria.serializers import OperacionCambioDivisaSerializer

        data = _payload_cambio(empresa_a, moneda_ves, moneda_usd, metodo_efectivo, cajas_cambio)
        ser = OperacionCambioDivisaSerializer(data=data)
        assert ser.is_valid(), ser.errors
        with pytest.raises(drf_serializers.ValidationError) as exc_info:
            ser.save()
        assert "usuario" in exc_info.value.detail
        assert OperacionCambioDivisa.objects.count() == 0


# ── apps/tesoreria/services.py — conciliación por referencia ─────────────────


class TestConciliarAutomaticoPorReferencia:
    """tesoreria/services.py:251-253 — prioridad 1: match por referencia
    exacta (lock + verificación + return).

    Las líneas 242 y 245 son NO-CUBRIBLES en single-thread: son la defensa
    BUG-M5 contra conciliaciones concurrentes (el candidato deja de estar
    libre entre la query y el lock); el queryset base ya excluye conciliados,
    así que solo un interleaving real entre transacciones puede activarlas.
    """

    def test_prioriza_referencia_exacta_sobre_fecha(
        self, empresa_a, moneda_usd, metodo_efectivo
    ):
        from apps.tesoreria.services import conciliar_automatico

        cuenta = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_a,
            nombre_banco="Banco DC95",
            numero_cuenta="0102-DC95",
            tipo_cuenta="CORRIENTE",
            id_moneda=moneda_usd,
        )
        ahora = timezone.now()

        def _pago(referencia, fecha_pago):
            return Pago.objects.create(
                id_empresa=empresa_a,
                tipo_operacion="INGRESO",
                tipo_documento="FACTURA",
                id_documento=uuid.uuid4(),
                fecha_pago=fecha_pago,
                monto=Decimal("350.00"),
                id_moneda=moneda_usd,
                id_metodo_pago=metodo_efectivo,
                id_cuenta_bancaria=cuenta,
                referencia=referencia,
            )

        # Señuelo: mismo monto, fecha MÁS cercana al inicio (ganaría por
        # prioridad 2), pero referencia distinta.
        senuelo = _pago("OTRA-REF", ahora - datetime.timedelta(days=2))
        correcto = _pago("REF-DC95", ahora)

        mov = MovimientoBancario.objects.create(
            id_empresa=empresa_a,
            id_cuenta_bancaria=cuenta,
            fecha_mov=ahora.date(),
            descripcion="Depósito cliente DC95",
            tipo="CREDITO",
            monto=Decimal("350.00"),
            referencia="REF-DC95",
            estado="PENDIENTE",
        )

        resultado = conciliar_automatico(empresa_a, cuenta, tolerancia_dias=3)

        assert resultado == {"conciliados": 1, "sin_match": 0, "total_procesados": 1}
        mov.refresh_from_db()
        assert mov.estado == "CONCILIADO"
        assert mov.id_pago_conciliado == correcto, (
            "Debe ganar el pago con referencia exacta, no el más cercano por fecha"
        )
        senuelo.refresh_from_db()
        assert not senuelo.movimientos_bancarios_conciliados.exists()


# ── apps/ventas/services.py — CxC reutilizada queda 'pagada' ──────────────────


class TestEmitirFacturaFiscalCxCPagada:
    @pytest.fixture
    def mapeo_factura_venta(self, empresa_a):
        from apps.contabilidad.models import MapeoContable, PlanCuentas

        def _cuenta(codigo, nombre, tipo, naturaleza):
            return PlanCuentas.objects.create(
                id_empresa=empresa_a,
                codigo_cuenta=codigo,
                nombre_cuenta=nombre,
                tipo_cuenta=tipo,
                naturaleza=naturaleza,
                nivel=1,
            )

        return MapeoContable.objects.create(
            id_empresa=empresa_a,
            tipo_asiento="FACTURA_VENTA",
            cuenta_debe=_cuenta("DC95-1201", "CxC DC95", "ACTIVO", "DEUDORA"),
            cuenta_haber=_cuenta("DC95-4101", "Ingresos DC95", "INGRESO", "ACREEDORA"),
            descripcion_plantilla="FAC {numero}",
            activo=True,
        )

    @pytest.fixture
    def venta_entregada(self, empresa_a, moneda_usd, user_a):
        """Venta directa CONTADO ya ENTREGADA, con su CxC creada en la entrega."""
        from apps.almacenes.models import Almacen
        from apps.crm.models import Cliente
        from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida
        from apps.inventario.services import registrar_movimiento
        from apps.ventas.models import DetalleNotaVenta, NotaVenta
        from apps.ventas.services import entregar_nota_venta

        cliente = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Cliente DC95",
            rif="J-95959595-9",
            tipo_cliente="CONTADO",
        )
        unidad = UnidadMedida.objects.create(
            id_empresa=empresa_a, nombre="Unidad", abreviatura="UN-DC95", tipo="CANTIDAD"
        )
        categoria = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="Cat DC95")
        producto = Producto.objects.create(
            id_empresa=empresa_a,
            nombre_producto="Producto DC95",
            id_unidad_medida_base=unidad,
            id_categoria=categoria,
            id_moneda_precio=moneda_usd,
            precio_venta_sugerido=Decimal("100.00"),
        )
        almacen = Almacen.objects.create(
            id_empresa=empresa_a, nombre_almacen="Almacén DC95", codigo_almacen="ALM-DC95"
        )
        registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=timezone.now(),
            tipo_movimiento="ENTRADA",
            producto=producto,
            cantidad=Decimal("10"),
            almacen_destino=almacen,
            usuario=user_a,
        )
        nota = NotaVenta.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            numero_nota="NV-DC95-1",
            fecha_nota=timezone.now().date(),
            estado="BORRADOR",
        )
        DetalleNotaVenta.objects.create(
            id_nota_venta=nota,
            id_producto=producto,
            cantidad=Decimal("2"),
            precio_unitario=Decimal("100.00"),
            subtotal=Decimal("200.00"),
        )
        resultado = entregar_nota_venta(nota, almacen, user_a)
        return nota, resultado["cxc"]

    def test_abono_total_previo_marca_cxc_pagada_al_facturar(
        self, empresa_a, moneda_usd, user_a, mapeo_factura_venta, venta_entregada
    ):
        """ventas/services.py:642 — al refacturar el flujo, si los abonos
        previos cubren el nuevo total fiscal, la CxC reutilizada queda
        'pagada' (no 'parcial' ni 'pendiente')."""
        from apps.cuentas_por_cobrar.models import AbonoCxC, CuentaPorCobrar
        from apps.fiscal.services import calcular_impuestos
        from apps.ventas.services import emitir_factura_fiscal

        nota, cxc = venta_entregada
        total_fiscal = calcular_impuestos(Decimal("200.00"), empresa_a, moneda_usd)["total"]
        AbonoCxC.objects.create(cuenta_por_cobrar=cxc, monto=total_fiscal, usuario=user_a)

        r = emitir_factura_fiscal(
            nota, numero_control="DC95-C1", numero_factura="DC95-F1", moneda=moneda_usd
        )

        cxc_final = r["cxc"]
        assert cxc_final.pk == cxc.pk, "Debe reutilizar la CxC del flujo (BUG-A4)"
        assert cxc_final.estado == "pagada"
        assert cxc_final.monto == r["factura"].monto_total.quantize(Decimal("0.01"))
        assert cxc_final.abonos.count() == 1
        cxc_db = CuentaPorCobrar.objects.get(pk=cxc.pk)
        assert cxc_db.estado == "pagada"
        assert CuentaPorCobrar.objects.filter(empresa=empresa_a).count() == 1
