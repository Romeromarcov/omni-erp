"""
Backfill de diff-coverage (gate ≥95 % en CI) — ramas no cubiertas de:

- apps/core/auth_views.py        L49 (axes deshabilitado → no bloquea) y
                                 L136 (lockout P1-3 → 429 genérico).
- apps/core/idempotency.py       L185 (respuesta no-2xx NO consume la clave).
- apps/core/models.py            L834 (propiedad ``ClaveIdempotencia.expirada``).
- apps/core/serializer_mixins.py L72/74 (rutas nullable a Empresa a 2 saltos),
                                 L115 (guard de recursión), L123 (serializer sin
                                 fields), L136 (RelatedField sin queryset) y
                                 L138 (queryset exótico sin ``model``).
- apps/cuentas_por_cobrar/views.py L144,146-147 (PDF no disponible → 503 sin
                                 filtrar detalle interno, SEC-M4).
- apps/cxc/api/serializers.py    L68, L74, L81, L88-92, L95 (aislamiento
                                 multi-tenant de los FKs cxc/gestion, BUG-M3).
- apps/nomina/services.py        L61-63 (ParametroSistema inválido → default),
                                 L111-112 (salario inválido en documento_json),
                                 L219, L226, L229-230 (validación de
                                 datos_empleados en el proceso de nómina).
- apps/nomina/mcp.py             L117 (empresa ≠ tenant del token) y
                                 L123-124 (proceso inexistente en resumen).
- apps/contabilidad/serializers.py L52 (cuenta de otra empresa en el mapeo).
- apps/integration_hub/services/sync_engine.py L319-320 (precio externo
                                 ilegible → Decimal("0"), nunca crash).

Todos los tests usan los fixtures multi-tenant de conftest (R-CODE-1) y
Decimal para dinero (R-CODE-4).
"""
import datetime
import uuid
from decimal import Decimal
from unittest import mock

import pytest
from django.utils import timezone
from rest_framework import serializers as drf_serializers
from rest_framework.test import APIClient, APIRequestFactory

from apps.core.models import CapabilityToken, ClaveIdempotencia, Empresa
from apps.cuentas_por_cobrar.models import AbonoCxC, CuentaPorCobrar
from apps.cxc.models import AcuerdoPago, CuotaAcuerdo, GestionCobranza
from apps.finanzas.models import CajaFisica, MetodoPago

pytestmark = pytest.mark.django_db


# ── Fixtures locales ──────────────────────────────────────────────────────────


@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def cxc_a(empresa_a):
    return CuentaPorCobrar.objects.create(
        empresa=empresa_a,
        cliente_externo_id="EXT-A",
        cliente_externo_nombre="Deudor A",
        monto=Decimal("100.00"),
        fecha_emision=datetime.date(2026, 6, 1),
        fecha_vencimiento=datetime.date(2026, 7, 1),
    )


@pytest.fixture
def cxc_b(empresa_b):
    return CuentaPorCobrar.objects.create(
        empresa=empresa_b,
        cliente_externo_id="EXT-B",
        cliente_externo_nombre="Deudor B",
        monto=Decimal("100.00"),
        fecha_emision=datetime.date(2026, 6, 1),
        fecha_vencimiento=datetime.date(2026, 7, 1),
    )


def _request_de(user):
    """Request mínimo (con .user) para el context de un serializer."""
    request = APIRequestFactory().post("/")
    request.user = user
    return request


# ══════════════════════════════════════════════════════════════════════════════
# apps/core/auth_views.py — L49 y L136
# ══════════════════════════════════════════════════════════════════════════════


class TestAuthViewsAxes:
    URL = "/api/auth/token/"

    def test_login_ok_con_axes_deshabilitado(self, settings, user_a):
        """L48-49: con AXES_ENABLED=False el chequeo de lockout devuelve False
        y el login procede normal (toggle real de configuración por entorno)."""
        settings.AXES_ENABLED = False
        client = APIClient()
        resp = client.post(
            self.URL, {"username": "user_empresa_a", "password": "testpass123"}, format="json"
        )
        assert resp.status_code == 200, resp.content
        assert "access" in resp.data
        assert resp.data["user"]["username"] == "user_empresa_a"

    def test_lockout_axes_devuelve_429_generico(self, settings, user_a):
        """L134-139 (objetivo L136): tras AXES_FAILURE_LIMIT fallos reales de
        login, el siguiente intento responde 429 con el mensaje genérico P1-3
        (sin filtrar si el usuario existe) — lockout de django-axes de verdad,
        sin mocks."""
        from django.core.cache import cache

        from apps.core.auth_views import LOCKOUT_MESSAGE

        client = APIClient()
        for _ in range(settings.AXES_FAILURE_LIMIT):
            # Se limpia la caché del rate-limit SEC-07 (5/min por IP) para que
            # los 10 fallos lleguen a authenticate() y axes (BD) los registre.
            cache.clear()
            r = client.post(
                self.URL, {"username": "user_empresa_a", "password": "incorrecta"}, format="json"
            )
            assert r.status_code == 401

        cache.clear()
        bloqueado = client.post(
            self.URL, {"username": "user_empresa_a", "password": "testpass123"}, format="json"
        )
        assert bloqueado.status_code == 429
        assert bloqueado.json()["error"] == LOCKOUT_MESSAGE
        assert "access" not in bloqueado.json()


# ══════════════════════════════════════════════════════════════════════════════
# apps/core/idempotency.py — L185 (respuesta no-2xx no consume la clave)
# ══════════════════════════════════════════════════════════════════════════════


class TestIdempotenciaNo2xxNoConsumeClave:
    URL = "/api/cobranza/acuerdos/"

    @pytest.fixture
    def acuerdo_a(self, empresa_a):
        acuerdo = AcuerdoPago.objects.create(
            empresa=empresa_a,
            cliente_id="CLI-DC",
            cliente_nombre="Cliente DiffCov",
            monto_total=Decimal("100.0000"),
            periodicidad="unico",
            fecha_inicio=timezone.now().date(),
            moneda_codigo="USD",
        )
        CuotaAcuerdo.objects.create(
            acuerdo=acuerdo,
            numero_cuota=1,
            fecha_vencimiento=timezone.now().date(),
            monto=Decimal("100.0000"),
        )
        return acuerdo

    @pytest.fixture
    def metodo_a(self, empresa_a, moneda_usd):
        metodo = MetodoPago.objects.create(
            nombre_metodo="Transferencia DC", tipo_metodo="ELECTRONICO", empresa=empresa_a
        )
        metodo.monedas.add(moneda_usd)
        return metodo

    def test_respuesta_404_borra_la_clave_y_permite_reintentar(
        self, client_a, acuerdo_a, moneda_usd, metodo_a
    ):
        """L180-185 (objetivo L185): si la vista devuelve 4xx, el registro de
        idempotencia se borra (no se consume la clave) y un reintento legítimo
        con la MISMA clave puede ejecutar la operación corregida."""
        cuota = acuerdo_a.cuotas.get()

        r1 = client_a.post(
            f"{self.URL}{acuerdo_a.id}/registrar-pago/",
            {
                "cuota_id": str(uuid.uuid4()),  # cuota que no pertenece al acuerdo
                "monto": "100.0000",
                "moneda_id": str(moneda_usd.id_moneda),
                "metodo_pago_id": str(metodo_a.id_metodo_pago),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="clave-no-consumida",
        )
        assert r1.status_code == 404
        # La clave NO quedó consumida (L185 la borró).
        assert ClaveIdempotencia.objects.count() == 0

        r2 = client_a.post(
            f"{self.URL}{acuerdo_a.id}/registrar-pago/",
            {
                "cuota_id": str(cuota.id),
                "monto": "100.0000",
                "moneda_id": str(moneda_usd.id_moneda),
                "metodo_pago_id": str(metodo_a.id_metodo_pago),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="clave-no-consumida",
        )
        assert r2.status_code == 200, r2.content
        cuota.refresh_from_db()
        assert cuota.estado == "pagado"
        assert cuota.monto_pagado == Decimal("100.0000")
        # Ahora sí: la clave quedó consumida por la ejecución exitosa.
        assert ClaveIdempotencia.objects.filter(scope="cxc:acuerdo-registrar-pago").count() == 1


# ══════════════════════════════════════════════════════════════════════════════
# apps/core/models.py — L834 (ClaveIdempotencia.expirada)
# ══════════════════════════════════════════════════════════════════════════════


class TestClaveIdempotenciaExpirada:
    def test_expirada_segun_ttl(self, empresa_a):
        """L831-834: la clave es 'expirada' si expira_en quedó en el pasado."""
        vencida = ClaveIdempotencia.objects.create(
            empresa=empresa_a,
            scope="test:diffcov",
            clave="clave-vieja",
            payload_hash="a" * 64,
            expira_en=timezone.now() - datetime.timedelta(minutes=1),
        )
        vigente = ClaveIdempotencia.objects.create(
            empresa=empresa_a,
            scope="test:diffcov",
            clave="clave-nueva",
            payload_hash="b" * 64,
            expira_en=timezone.now() + datetime.timedelta(hours=1),
        )
        assert vencida.expirada is True
        assert vigente.expirada is False


# ══════════════════════════════════════════════════════════════════════════════
# apps/core/serializer_mixins.py — L72, L74, L115, L123, L136, L138
# ══════════════════════════════════════════════════════════════════════════════


class TestSerializerMixins:
    def test_tenant_scope_cond_primer_salto_nullable(self):
        """L66-75 (objetivo L72): para un modelo cuyo camino a Empresa pasa por
        una FK nullable (Usuarios → id_sucursal_predeterminada → Empresa), la
        condición incluye esa FK como ruta que habilita filas globales."""
        from django.contrib.auth import get_user_model

        from apps.core.serializer_mixins import _tenant_scope_cond

        path, nulls = _tenant_scope_cond(get_user_model())
        assert path == "id_sucursal_predeterminada__id_empresa"
        assert nulls == ["id_sucursal_predeterminada"]

    def test_scoped_queryset_dos_saltos_con_empresa_padre_nullable(
        self, empresa_a, empresa_b, cxc_a, cxc_b
    ):
        """L73-74 + L100-104 (objetivo L74): AbonoCxC llega a Empresa vía
        CuentaPorCobrar.empresa (nullable). El scope debe excluir los abonos
        del tenant ajeno y conservar los de filas globales (empresa=None)."""
        from apps.core.serializer_mixins import _scoped_queryset

        cxc_global = CuentaPorCobrar.objects.create(
            empresa=None,
            cliente_externo_id="EXT-GLOBAL",
            monto=Decimal("10.00"),
            fecha_emision=datetime.date(2026, 6, 1),
            fecha_vencimiento=datetime.date(2026, 7, 1),
        )
        abono_a = AbonoCxC.objects.create(cuenta_por_cobrar=cxc_a, monto=Decimal("5.00"))
        abono_b = AbonoCxC.objects.create(cuenta_por_cobrar=cxc_b, monto=Decimal("5.00"))
        abono_global = AbonoCxC.objects.create(cuenta_por_cobrar=cxc_global, monto=Decimal("5.00"))

        visibles = Empresa.objects.filter(pk=empresa_a.pk)
        scoped = _scoped_queryset(AbonoCxC.objects.all(), visibles)

        assert set(scoped) == {abono_a, abono_global}
        assert abono_b not in scoped

    def test_scope_tenant_fks_guard_de_recursion(self, empresa_a, empresa_b, caja_fisica_a):
        """L112-116 (objetivo L115): un serializer ya visitado NO se vuelve a
        escopear (guard anti-ciclos); sin el guard, el mismo serializer sí
        queda restringido al tenant."""
        from apps.core.serializer_mixins import scope_tenant_fks

        caja_b = CajaFisica.objects.create(
            empresa=empresa_b, nombre="Caja B", identificador_dispositivo="disp-b"
        )

        class _CajaSerializer(drf_serializers.Serializer):
            caja = drf_serializers.PrimaryKeyRelatedField(queryset=CajaFisica.objects.all())

        visibles = Empresa.objects.filter(pk=empresa_a.pk)

        ya_visto = _CajaSerializer()
        scope_tenant_fks(ya_visto, visibles, _seen={id(ya_visto)})
        assert caja_b in ya_visto.fields["caja"].queryset  # quedó SIN escopear

        nuevo = _CajaSerializer()
        scope_tenant_fks(nuevo, visibles)
        qs = nuevo.fields["caja"].queryset
        assert caja_fisica_a in qs
        assert caja_b not in qs

    def test_scope_tenant_fks_campos_exoticos_no_rompen_el_scope(
        self, empresa_a, empresa_b, caja_fisica_a
    ):
        """L121-123, L134-138 (objetivos L123, L136, L138): un nested serializer
        sin ``fields``, un RelatedField sin queryset (override de get_queryset,
        patrón documentado de DRF) y un queryset exótico sin ``model`` se
        saltan sin error — y los campos normales SÍ quedan escopeados."""
        from apps.core.serializer_mixins import scope_tenant_fks

        caja_b = CajaFisica.objects.create(
            empresa=empresa_b, nombre="Caja B2", identificador_dispositivo="disp-b2"
        )

        class _QuerysetExotico:
            def all(self):  # tiene .all pero no .model → no introspeccionable
                return self

        class _FKSinQueryset(drf_serializers.PrimaryKeyRelatedField):
            def get_queryset(self):
                return CajaFisica.objects.all()

        class _SinFields(drf_serializers.BaseSerializer):
            pass

        class _BordeSerializer(drf_serializers.Serializer):
            exotico = drf_serializers.PrimaryKeyRelatedField(queryset=_QuerysetExotico())
            sin_qs = _FKSinQueryset()
            anidado = _SinFields()
            caja = drf_serializers.PrimaryKeyRelatedField(queryset=CajaFisica.objects.all())

        s = _BordeSerializer()
        scope_tenant_fks(s, Empresa.objects.filter(pk=empresa_a.pk))

        # Los campos exóticos quedaron intactos (sin crash y sin marcar):
        assert isinstance(s.fields["exotico"].queryset, _QuerysetExotico)
        assert not hasattr(s.fields["exotico"], "_tenant_fk_scoped")
        assert s.fields["sin_qs"].queryset is None
        # …y el campo normal posterior SÍ se escopeó al tenant (el loop siguió).
        assert getattr(s.fields["caja"], "_tenant_fk_scoped", False) is True
        assert caja_fisica_a in s.fields["caja"].queryset
        assert caja_b not in s.fields["caja"].queryset


# ══════════════════════════════════════════════════════════════════════════════
# apps/cuentas_por_cobrar/views.py — L144, L146-147 (PDF no disponible → 503)
# ══════════════════════════════════════════════════════════════════════════════


class TestEstadoCuentaPdfNoDisponible:
    def test_importerror_de_reportlab_responde_503_sin_detalle_interno(
        self, client_a, empresa_a
    ):
        """L142-149 (objetivos L144, L146-147): si la generación del PDF lanza
        ImportError (reportlab ausente en el servidor), la API responde 503 con
        mensaje seguro y NO filtra el detalle interno (SEC-M4 / R-CODE-8)."""
        from apps.crm.models import Cliente

        cliente = Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Cliente PDF", rif="V-11222333"
        )
        with mock.patch(
            "apps.cuentas_por_cobrar.pdf_estado_cuenta.generar_pdf_estado_cuenta",
            side_effect=ImportError("reportlab no está instalado"),
        ):
            resp = client_a.get(
                f"/api/cxc/cuentas-por-cobrar/estado-cuenta/{cliente.id_cliente}/pdf/"
            )
        assert resp.status_code == 503
        assert resp.json() == {"error": "Generación de PDF no disponible en este servidor."}
        assert "reportlab" not in resp.content.decode()


# ══════════════════════════════════════════════════════════════════════════════
# apps/cxc/api/serializers.py — L68, L74, L81, L88-92, L95 (BUG-M3)
# ══════════════════════════════════════════════════════════════════════════════


class TestAcuerdoPagoCreateSerializer:
    URL = "/api/cobranza/acuerdos/"

    @staticmethod
    def _payload(**overrides):
        base = {
            "cliente_id": "CLI-DC",
            "cliente_nombre": "Cliente DiffCov",
            "monto_total": "100.0000",
            "periodicidad": "unico",
            "plazo_total_dias": 30,
            "fecha_inicio": "2026-06-12",
            "moneda_codigo": "USD",
        }
        base.update(overrides)
        return base

    @pytest.fixture
    def gestion_a(self, empresa_a):
        return GestionCobranza.objects.create(
            empresa=empresa_a,
            cliente_id="CLI-DC",
            cliente_nombre="Cliente DiffCov",
            canal="llamada",
            resultado="promesa_pago",
            fecha_gestion=datetime.date(2026, 6, 10),
        )

    @pytest.fixture
    def gestion_b(self, empresa_b):
        return GestionCobranza.objects.create(
            empresa=empresa_b,
            cliente_id="CLI-B",
            cliente_nombre="Cliente B",
            canal="llamada",
            resultado="promesa_pago",
            fecha_gestion=datetime.date(2026, 6, 10),
        )

    def test_crear_con_cxc_y_gestion_null_es_valido(self, client_a):
        """L73-74 y L88-89: cxc/gestion explícitamente null pasan la validación
        (acuerdo sin CxC nativa ni gestión de origen)."""
        resp = client_a.post(self.URL, self._payload(cxc=None, gestion=None), format="json")
        assert resp.status_code == 201, resp.content
        acuerdo = AcuerdoPago.objects.get()
        assert acuerdo.cxc is None
        assert acuerdo.gestion is None

    def test_crear_con_gestion_propia_es_valido(self, client_a, gestion_a):
        """L86-91 → L95: una gestión del MISMO tenant pasa la validación y queda
        enlazada al acuerdo."""
        resp = client_a.post(
            self.URL, self._payload(gestion=str(gestion_a.pk)), format="json"
        )
        assert resp.status_code == 201, resp.content
        acuerdo = AcuerdoPago.objects.get()
        assert acuerdo.gestion_id == gestion_a.pk

    def test_sin_request_en_context_rechaza_cxc(self, cxc_a):
        """L66-69 (objetivo L68) + L76-81: sin request autenticado en el context
        no hay empresas visibles → el FK cxc se rechaza (fail-closed)."""
        from apps.cxc.api.serializers import AcuerdoPagoCreateSerializer

        serializer = AcuerdoPagoCreateSerializer(data=self._payload(cxc=str(cxc_a.pk)))
        assert not serializer.is_valid()
        assert "no existe o no pertenece a su empresa" in str(serializer.errors["cxc"][0])

    def test_cxc_de_otra_empresa_rechazada(self, user_a, cxc_b):
        """L76-81 (objetivo L81): una CxC de OTRA empresa se rechaza con el
        mensaje neutro (R-CODE-1: no revela existencia)."""
        from apps.cxc.api.serializers import AcuerdoPagoCreateSerializer

        serializer = AcuerdoPagoCreateSerializer(
            data=self._payload(cxc=str(cxc_b.pk)),
            context={"request": _request_de(user_a)},
        )
        assert not serializer.is_valid()
        assert "no existe o no pertenece a su empresa" in str(serializer.errors["cxc"][0])

    def test_gestion_de_otra_empresa_rechazada(self, user_a, gestion_b):
        """L86-94 (objetivos L90-92): una gestión de OTRA empresa se rechaza
        con mensaje neutro."""
        from apps.cxc.api.serializers import AcuerdoPagoCreateSerializer

        serializer = AcuerdoPagoCreateSerializer(
            data=self._payload(gestion=str(gestion_b.pk)),
            context={"request": _request_de(user_a)},
        )
        assert not serializer.is_valid()
        assert "no existe o no pertenece a su empresa" in str(serializer.errors["gestion"][0])


# ══════════════════════════════════════════════════════════════════════════════
# apps/nomina/services.py — L61-63, L111-112, L219, L226, L229-230
# ══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def periodo_a(empresa_a):
    from apps.nomina.models import PeriodoNomina

    return PeriodoNomina.objects.create(
        id_empresa=empresa_a,
        nombre_periodo="Junio 2026 DiffCov",
        fecha_inicio=datetime.date(2026, 6, 1),
        fecha_fin=datetime.date(2026, 6, 30),
        fecha_pago=datetime.date(2026, 7, 1),
        tipo_periodo="MENSUAL",
    )


@pytest.fixture
def proceso_a(empresa_a, periodo_a):
    from apps.nomina.models import ProcesoNomina

    return ProcesoNomina.objects.create(
        id_empresa=empresa_a,
        id_periodo_nomina=periodo_a,
        numero_proceso="PROC-DIFFCOV-001",
        fecha_proceso=timezone.now(),
        estado="EN_PROCESO",
    )


@pytest.fixture
def empleado_a(empresa_a):
    from apps.rrhh.models import Empleado

    return Empleado.objects.create(
        empresa=empresa_a,
        nombre="Diana",
        apellido="Cova",
        cedula="V-44444444",
        fecha_ingreso=datetime.date(2024, 1, 1),
        documento_json={"salario_mensual": "600.00"},
    )


class TestNominaServices:
    def test_parametro_sistema_invalido_usa_default(self, empresa_a):
        """L59-63 (objetivo L61-63): un ParametroSistema no numérico no rompe el
        cálculo — se usa el default del motor LOTTT (con warning)."""
        from apps.configuracion_motor.models import ParametroSistema
        from apps.nomina.calculo_lottt import ParametrosLOTTT
        from apps.nomina.services import config_nomina_de_empresa

        ParametroSistema.objects.create(
            id_empresa=empresa_a,
            nombre_parametro="Valor UT",
            codigo_parametro="nomina.valor_ut",
            valor_parametro="no-es-un-numero",
            tipo_dato="NUMERO",
        )
        config = config_nomina_de_empresa(empresa_a)
        assert config.parametros.valor_ut == ParametrosLOTTT().valor_ut

    def test_salario_invalido_en_documento_json_revienta_el_proceso(
        self, proceso_a, empleado_a
    ):
        """L105-113 (objetivo L111-112): un salario ilegible en documento_json
        cae a 0 (con warning) y, sin salario mínimo configurado, el proceso
        falla con error de negocio y NO persiste nóminas parciales."""
        from apps.nomina.models import Nomina
        from apps.nomina.services import NominaProcesoError, procesar_proceso_nomina

        empleado_a.documento_json = {"salario_mensual": "seiscientos"}
        empleado_a.save(update_fields=["documento_json"])

        with pytest.raises(NominaProcesoError, match="no tiene salario"):
            procesar_proceso_nomina(proceso_a)
        assert Nomina.objects.count() == 0
        proceso_a.refresh_from_db()
        assert proceso_a.estado == "EN_PROCESO"

    def test_datos_empleado_que_no_es_objeto_da_error(self, proceso_a, empleado_a):
        """L218-219 (objetivo L219): datos_empleados[pk] que no es un dict →
        error de negocio explícito (la API lo traduce a 400)."""
        from apps.nomina.services import NominaProcesoError, procesar_proceso_nomina

        with pytest.raises(NominaProcesoError, match="se esperaba un objeto"):
            procesar_proceso_nomina(proceso_a, datos_empleados={str(empleado_a.pk): "15"})

    def test_dias_trabajados_se_aplican_al_calculo(self, proceso_a, empleado_a):
        """L224-228 (objetivo L226): dias_trabajados se convierte a int y el
        recibo se calcula proporcional (600 × 15/30 = 300; deducciones 5.5 % →
        neto 283.50, Decimal end-to-end)."""
        from apps.nomina.models import Nomina
        from apps.nomina.services import procesar_proceso_nomina

        proceso, _asiento, _adv = procesar_proceso_nomina(
            proceso_a, datos_empleados={str(empleado_a.pk): {"dias_trabajados": "15"}}
        )
        nomina = Nomina.objects.get(id_proceso_nomina=proceso)
        assert nomina.dias_trabajados == 15
        assert nomina.total_devengado == Decimal("300.00")
        assert nomina.total_deducciones == Decimal("16.50")  # SSO 12 + FAOV 3 + RPE 1.50
        assert nomina.total_neto == Decimal("283.50")

    def test_dias_trabajados_invalido_da_error(self, proceso_a, empleado_a):
        """L224-232 (objetivo L229-230): un valor no convertible en
        datos_empleados produce error de negocio con el campo señalado."""
        from apps.nomina.services import NominaProcesoError, procesar_proceso_nomina

        with pytest.raises(NominaProcesoError, match="Valor inválido en 'dias_trabajados'"):
            procesar_proceso_nomina(
                proceso_a, datos_empleados={str(empleado_a.pk): {"dias_trabajados": "quince"}}
            )


# ══════════════════════════════════════════════════════════════════════════════
# apps/nomina/mcp.py — L117 y L123-124
# ══════════════════════════════════════════════════════════════════════════════


class TestNominaMcpResumen:
    @staticmethod
    def _token(empresa, scopes):
        return CapabilityToken.objects.create(
            empresa=empresa, nombre="tok-diffcov", scopes=scopes
        )

    def test_resumen_empresa_distinta_al_token(self, empresa_a, empresa_b, proceso_a):
        """L116-117 (objetivo L117): el resumen exige que empresa_id coincida
        con el tenant del token (R-CODE-1)."""
        from apps.nomina.mcp import nomina_resumen_proceso

        tok = self._token(empresa_a, ["nomina:read"])
        with pytest.raises(PermissionError, match="no coincide con el tenant"):
            nomina_resumen_proceso(str(tok.token), str(empresa_b.id_empresa), str(proceso_a.pk))

    def test_resumen_proceso_inexistente(self, empresa_a):
        """L119-124 (objetivo L123-124): un proceso inexistente devuelve un
        error controlado, no una excepción."""
        from apps.nomina.mcp import nomina_resumen_proceso

        tok = self._token(empresa_a, ["nomina:read"])
        proceso_id = str(uuid.uuid4())
        res = nomina_resumen_proceso(str(tok.token), str(empresa_a.id_empresa), proceso_id)
        assert res == {"error": f"Proceso de nómina {proceso_id} no encontrado."}


# ══════════════════════════════════════════════════════════════════════════════
# apps/contabilidad/serializers.py — L52
# ══════════════════════════════════════════════════════════════════════════════


class TestMapeoContableSerializer:
    def test_cuenta_de_otra_empresa_rechazada(self, empresa_a, empresa_b):
        """L46-53 (objetivo L52): las cuentas del mapeo deben ser de la MISMA
        empresa del mapeo; una cuenta ajena se rechaza por campo."""
        from apps.contabilidad.models import PlanCuentas
        from apps.contabilidad.serializers import MapeoContableSerializer

        cuenta_a = PlanCuentas.objects.create(
            id_empresa=empresa_a, codigo_cuenta="5.1", nombre_cuenta="Gasto Nómina",
            tipo_cuenta="GASTO", naturaleza="DEUDORA", nivel=1,
        )
        cuenta_a2 = PlanCuentas.objects.create(
            id_empresa=empresa_a, codigo_cuenta="2.1", nombre_cuenta="Nómina por Pagar",
            tipo_cuenta="PASIVO", naturaleza="ACREEDORA", nivel=1,
        )
        cuenta_b = PlanCuentas.objects.create(
            id_empresa=empresa_b, codigo_cuenta="5.1", nombre_cuenta="Gasto Ajeno",
            tipo_cuenta="GASTO", naturaleza="DEUDORA", nivel=1,
        )

        invalido = MapeoContableSerializer(data={
            "id_empresa": empresa_a.pk,
            "tipo_asiento": "NOMINA",
            "cuenta_debe": cuenta_b.pk,   # ← de empresa B
            "cuenta_haber": cuenta_a2.pk,
        })
        assert not invalido.is_valid()
        assert (
            str(invalido.errors["cuenta_debe"][0])
            == "La cuenta no pertenece a la empresa del mapeo."
        )

        valido = MapeoContableSerializer(data={
            "id_empresa": empresa_a.pk,
            "tipo_asiento": "NOMINA",
            "cuenta_debe": cuenta_a.pk,
            "cuenta_haber": cuenta_a2.pk,
        })
        assert valido.is_valid(), valido.errors


# ══════════════════════════════════════════════════════════════════════════════
# apps/integration_hub/services/sync_engine.py — L319-320
# ══════════════════════════════════════════════════════════════════════════════


class TestSyncEngineDecimalDefensivo:
    def test_precio_externo_ilegible_cae_a_cero(self, empresa_a, moneda_usd):
        """L316-320 (objetivo L319-320): un precio externo no numérico no rompe
        la sincronización — el producto se crea con Decimal('0')."""
        from apps.integration_hub.models import ConectorInstancia, ConectorProveedor
        from apps.integration_hub.services.sync_engine import SyncEngine
        from apps.inventario.models import Producto

        proveedor = ConectorProveedor.objects.create(codigo="odoo-dc", nombre="Odoo DiffCov")
        instancia = ConectorInstancia.objects.create(
            id_empresa=empresa_a, id_proveedor=proveedor, nombre="Odoo Test DC"
        )

        pk = SyncEngine()._upsert_producto(
            {
                "codigo_interno": "SKU-DC-1",
                "nombre": "Producto Externo DC",
                "precio_venta": "no-es-un-precio",  # InvalidOperation → 0
                "costo": ["12"],                    # InvalidOperation → 0
            },
            instancia,
        )
        assert pk is not None
        producto = Producto.objects.get(pk=pk)
        assert producto.id_empresa == empresa_a
        assert producto.precio_venta_sugerido == Decimal("0")
        assert producto.costo_promedio == Decimal("0")
        assert producto.id_moneda_precio == moneda_usd
