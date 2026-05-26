"""
Tests M10 — SaaS Core (M10-T2, M10-T3, M10-T4, M10-T5, M10-T6).

M10-T2: PDF generators (cotización, nota entrega, estado de cuenta)
M10-T3: Email service (SMTP/SendGrid)
M10-T4: Notificaciones in-app
M10-T5: Plan, Suscripcion, middleware
M10-T6: vzla-localization-pack (validators, calendario, formato, zona_horaria)
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# M10-T6: vzla-localization-pack (pure Python — no DB needed)
# ─────────────────────────────────────────────────────────────────────────────


class TestValidadoresVzla:
    """Validadores de RIF, Cédula y Número de Control."""

    def test_rif_j_valido(self):
        from apps.vzla_localizacion.validators import validar_rif
        # Formato correcto: tipo J + 8 dígitos + DV
        assert validar_rif("J-30543012-5") is True

    def test_rif_v_valido(self):
        from apps.vzla_localizacion.validators import validar_rif
        assert validar_rif("V-12345678-3") is True

    def test_rif_todos_tipos_validos(self):
        from apps.vzla_localizacion.validators import validar_rif
        # Todos los prefijos soportados
        assert validar_rif("J-12345678-1") is True
        assert validar_rif("E-12345678-1") is True
        assert validar_rif("G-12345678-1") is True
        assert validar_rif("P-12345678-1") is True

    def test_rif_formato_incorrecto(self):
        from apps.vzla_localizacion.validators import validar_rif
        assert validar_rif("X-12345678-5") is False  # prefijo inválido
        assert validar_rif("") is False
        assert validar_rif("12345678") is False
        assert validar_rif("J-1234-5") is False  # muy pocos dígitos

    def test_rif_sin_guiones(self):
        from apps.vzla_localizacion.validators import validar_rif
        # Debe funcionar con o sin guiones
        assert validar_rif("J305430125") is True

    def test_normalizar_rif(self):
        from apps.vzla_localizacion.validators import normalizar_rif
        assert normalizar_rif("J305430125") == "J-30543012-5"
        assert normalizar_rif("j-30543012-5") == "J-30543012-5"

    def test_normalizar_rif_invalido(self):
        from apps.vzla_localizacion.validators import normalizar_rif
        with pytest.raises(ValueError):
            normalizar_rif("X-123")

    def test_cedula_valida(self):
        from apps.vzla_localizacion.validators import validar_cedula
        assert validar_cedula("V-12345678") is True
        assert validar_cedula("E-87654321") is True
        assert validar_cedula("V12345678") is True

    def test_cedula_invalida(self):
        from apps.vzla_localizacion.validators import validar_cedula
        assert validar_cedula("X-12345678") is False
        assert validar_cedula("") is False

    def test_normalizar_cedula(self):
        from apps.vzla_localizacion.validators import normalizar_cedula
        assert normalizar_cedula("V12345678") == "V-12345678"

    def test_numero_control_valido(self):
        from apps.vzla_localizacion.validators import validar_numero_control
        assert validar_numero_control("00-00000123") is True
        assert validar_numero_control("01-00001000") is True

    def test_numero_control_invalido(self):
        from apps.vzla_localizacion.validators import validar_numero_control
        assert validar_numero_control("") is False
        assert validar_numero_control("0-123") is False

    def test_siguiente_numero_control(self):
        from apps.vzla_localizacion.validators import siguiente_numero_control
        assert siguiente_numero_control("00-00000099") == "00-00000100"
        assert siguiente_numero_control("00-00000001") == "00-00000002"

    def test_validar_email(self):
        from apps.vzla_localizacion.validators import validar_email
        assert validar_email("usuario@empresa.com") is True
        assert validar_email("invalido") is False
        assert validar_email("") is False


class TestCalendarioVzla:
    """Feriados y días hábiles venezolanos."""

    def test_ano_nuevo_es_feriado(self):
        from apps.vzla_localizacion.calendario import es_feriado
        assert es_feriado(date(2026, 1, 1)) is True

    def test_dia_independencia_es_feriado(self):
        from apps.vzla_localizacion.calendario import es_feriado
        assert es_feriado(date(2026, 7, 5)) is True

    def test_navidad_es_feriado(self):
        from apps.vzla_localizacion.calendario import es_feriado
        assert es_feriado(date(2026, 12, 25)) is True

    def test_lunes_laborable_no_feriado(self):
        from apps.vzla_localizacion.calendario import es_feriado
        # Lunes 2 de febrero 2026 no es feriado
        assert es_feriado(date(2026, 2, 2)) is False

    def test_sabado_no_es_habil(self):
        from apps.vzla_localizacion.calendario import es_dia_habil
        # Sábado 3 enero 2026
        assert es_dia_habil(date(2026, 1, 3)) is False

    def test_feriado_no_es_habil(self):
        from apps.vzla_localizacion.calendario import es_dia_habil
        assert es_dia_habil(date(2026, 1, 1)) is False

    def test_dia_habil_normal(self):
        from apps.vzla_localizacion.calendario import es_dia_habil
        # Miércoles 7 enero 2026 no es feriado
        assert es_dia_habil(date(2026, 1, 7)) is True

    def test_feriados_del_año_tiene_entries(self):
        from apps.vzla_localizacion.calendario import feriados_del_año
        feriados = feriados_del_año(2026)
        assert len(feriados) >= 15
        assert date(2026, 1, 1) in feriados
        assert date(2026, 12, 25) in feriados

    def test_dias_habiles_rango(self):
        from apps.vzla_localizacion.calendario import dias_habiles
        # En una semana típica sin feriados debería haber ~5 días hábiles
        # Semana 5-9 enero 2026 (lunes a viernes, sin feriados)
        total = dias_habiles(date(2026, 1, 5), date(2026, 1, 9))
        assert total == 5

    def test_dias_habiles_incluye_feriado(self):
        from apps.vzla_localizacion.calendario import dias_habiles
        # 1 enero (feriado) al 2 enero: solo 1 día hábil (viernes 2)
        total = dias_habiles(date(2026, 1, 1), date(2026, 1, 2))
        assert total == 1  # 1 enero es feriado, 2 enero es viernes hábil

    def test_siguiente_dia_habil_desde_viernes(self):
        from apps.vzla_localizacion.calendario import siguiente_dia_habil
        # Desde viernes 2 enero, el siguiente hábil debe ser lunes 5 enero
        siguiente = siguiente_dia_habil(date(2026, 1, 2))
        assert siguiente == date(2026, 1, 5)

    def test_semana_santa_calculada(self):
        from apps.vzla_localizacion.calendario import feriados_del_año
        # En 2026, el domingo de Pascua es 5 de abril
        # Viernes Santo = 3 de abril, Jueves Santo = 2 de abril
        feriados = feriados_del_año(2026)
        assert date(2026, 4, 3) in feriados  # Viernes Santo 2026
        assert date(2026, 4, 2) in feriados  # Jueves Santo 2026


class TestFormatoVzla:
    """Formateo de montos venezolanos."""

    def test_formatear_bolivares(self):
        from apps.vzla_localizacion.formato import formatear_bolivares
        resultado = formatear_bolivares(Decimal("1234567.89"))
        assert "1.234.567" in resultado
        assert "89" in resultado
        assert "Bs." in resultado

    def test_formatear_bolivares_sin_simbolo(self):
        from apps.vzla_localizacion.formato import formatear_bolivares
        resultado = formatear_bolivares(Decimal("1000"), incluir_simbolo=False)
        assert "Bs." not in resultado
        assert "1.000" in resultado

    def test_formatear_usd(self):
        from apps.vzla_localizacion.formato import formatear_usd
        resultado = formatear_usd(Decimal("1234.50"))
        assert "$" in resultado
        assert "1,234.50" in resultado

    def test_formatear_monto_ves(self):
        from apps.vzla_localizacion.formato import formatear_monto
        resultado = formatear_monto(Decimal("5000"), "VES")
        assert "Bs." in resultado

    def test_formatear_monto_usd(self):
        from apps.vzla_localizacion.formato import formatear_monto
        resultado = formatear_monto(Decimal("100"), "USD")
        assert "$" in resultado

    def test_monto_a_letras_cero(self):
        from apps.vzla_localizacion.formato import monto_a_letras
        resultado = monto_a_letras(0)
        assert "CERO" in resultado

    def test_monto_a_letras_mil(self):
        from apps.vzla_localizacion.formato import monto_a_letras
        resultado = monto_a_letras(1000, "DOLARES")
        assert "MIL" in resultado
        assert "DOLARES" in resultado

    def test_monto_a_letras_con_centavos(self):
        from apps.vzla_localizacion.formato import monto_a_letras
        resultado = monto_a_letras(Decimal("1234.50"))
        assert "CON 50/100" in resultado

    def test_monto_a_letras_millon(self):
        from apps.vzla_localizacion.formato import monto_a_letras
        resultado = monto_a_letras(1_000_000)
        assert "MILLÓN" in resultado or "MILLON" in resultado


class TestZonaHorariaVzla:
    """Zona horaria venezolana VET (UTC-4)."""

    def test_ahora_vet_tiene_tz(self):
        from apps.vzla_localizacion.zona_horaria import ahora_vet
        dt = ahora_vet()
        assert dt.tzinfo is not None
        assert dt.utcoffset().total_seconds() == -4 * 3600

    def test_a_vet_conversion(self):
        from datetime import timezone as tz
        from apps.vzla_localizacion.zona_horaria import a_vet
        import datetime
        # UTC 12:00 → VET 08:00
        dt_utc = datetime.datetime(2026, 6, 15, 12, 0, 0, tzinfo=tz.utc)
        dt_vet = a_vet(dt_utc)
        assert dt_vet.hour == 8

    def test_a_vet_sin_tz_lanza_error(self):
        from apps.vzla_localizacion.zona_horaria import a_vet
        import datetime
        with pytest.raises(ValueError):
            a_vet(datetime.datetime(2026, 1, 1, 12, 0))

    def test_formatear_fecha_ve(self):
        from apps.vzla_localizacion.zona_horaria import formatear_fecha_ve
        fecha = date(2026, 5, 17)
        assert formatear_fecha_ve(fecha) == "17/05/2026"

    def test_inicio_dia_vet(self):
        from apps.vzla_localizacion.zona_horaria import inicio_dia_vet
        dt = inicio_dia_vet(date(2026, 6, 15))
        assert dt.hour == 0
        assert dt.minute == 0
        assert dt.utcoffset().total_seconds() == -4 * 3600


# ─────────────────────────────────────────────────────────────────────────────
# M10-T4: Notificaciones in-app
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestNotificaciones:
    """Modelo Notificacion y helper crear_notificacion."""

    def test_crear_notificacion_info(self, empresa_a, user_a):
        from apps.core.models import Notificacion, crear_notificacion

        n = crear_notificacion(
            empresa=empresa_a,
            titulo="Pedido confirmado",
            mensaje="El pedido #001 fue confirmado.",
            tipo="INFO",
            usuario=user_a,
        )
        assert n.pk is not None
        assert n.leida is False
        assert n.tipo == "INFO"
        assert n.id_empresa == empresa_a

    def test_crear_notificacion_broadcast(self, empresa_a):
        from apps.core.models import Notificacion, crear_notificacion

        n = crear_notificacion(
            empresa=empresa_a,
            titulo="Mantenimiento programado",
            mensaje="El sistema estará en mantenimiento el sábado.",
        )
        assert n.id_usuario is None  # broadcast

    def test_marcar_leida(self, empresa_a, user_a):
        from apps.core.models import Notificacion, crear_notificacion

        n = crear_notificacion(empresa_a, "Test", "Mensaje", usuario=user_a)
        assert n.leida is False
        n.marcar_leida()
        n.refresh_from_db()
        assert n.leida is True
        assert n.fecha_lectura is not None

    def test_notificacion_tiene_metadata(self, empresa_a):
        from apps.core.models import crear_notificacion

        n = crear_notificacion(
            empresa=empresa_a,
            titulo="Reorden sugerido",
            mensaje="Producto X: stock crítico",
            tipo="INVENTARIO",
            metadata={"producto_id": "abc-123", "dias_restantes": 5},
        )
        assert n.metadata["producto_id"] == "abc-123"

    def test_notificacion_url_accion(self, empresa_a):
        from apps.core.models import crear_notificacion

        n = crear_notificacion(
            empresa=empresa_a,
            titulo="CxC vencida",
            mensaje="Revisar CxC #456",
            tipo="COBRANZA",
            url_accion="/cxc/456/",
        )
        assert n.url_accion == "/cxc/456/"

    def test_listado_no_leidas(self, empresa_a, user_a):
        from apps.core.models import Notificacion, crear_notificacion

        crear_notificacion(empresa_a, "Test 1", "Msg 1", usuario=user_a)
        n2 = crear_notificacion(empresa_a, "Test 2", "Msg 2", usuario=user_a)
        n2.marcar_leida()

        no_leidas = Notificacion.objects.filter(
            id_empresa=empresa_a, id_usuario=user_a, leida=False
        )
        assert no_leidas.count() >= 1

    def test_str_notificacion(self, empresa_a):
        from apps.core.models import crear_notificacion
        n = crear_notificacion(empresa_a, "Alerta importante", "Mensaje")
        assert "Alerta importante" in str(n)


# ─────────────────────────────────────────────────────────────────────────────
# M10-T5: Plan, Suscripcion, middleware
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestPlanSuscripcion:
    """Modelos Plan y Suscripcion."""

    @pytest.fixture
    def plan_pro(self, db):
        from apps.saas.models import Plan
        return Plan.objects.create(
            nombre="Pro 2026",
            nivel="PRO",
            precio_mensual=Decimal("50.00"),
            max_usuarios=20,
            permite_ia=True,
            permite_api=True,
        )

    @pytest.fixture
    def suscripcion_activa(self, db, empresa_a, plan_pro):
        from apps.saas.models import Suscripcion
        hoy = date.today()
        return Suscripcion.objects.create(
            id_empresa=empresa_a,
            id_plan=plan_pro,
            estado="ACTIVA",
            fecha_inicio=hoy - timedelta(days=10),
            fecha_fin=hoy + timedelta(days=20),
        )

    def test_crear_plan(self, plan_pro):
        assert plan_pro.pk is not None
        assert plan_pro.nivel == "PRO"
        assert plan_pro.permite_ia is True

    def test_plan_str(self, plan_pro):
        assert "Pro 2026" in str(plan_pro)
        assert "PRO" in str(plan_pro)

    def test_suscripcion_esta_vigente(self, suscripcion_activa):
        assert suscripcion_activa.esta_vigente is True

    def test_suscripcion_vencida_no_vigente(self, db, empresa_a, plan_pro):
        from apps.saas.models import Suscripcion
        hoy = date.today()
        sus = Suscripcion.objects.create(
            id_empresa=empresa_a,
            id_plan=plan_pro,
            estado="ACTIVA",
            fecha_inicio=hoy - timedelta(days=60),
            fecha_fin=hoy - timedelta(days=1),  # venció ayer
        )
        assert sus.esta_vigente is False

    def test_suscripcion_dias_restantes(self, suscripcion_activa):
        dias = suscripcion_activa.dias_restantes
        assert 18 <= dias <= 21  # ~20 días

    def test_suscripcion_cancelar(self, suscripcion_activa):
        suscripcion_activa.cancelar("Cliente solicitó cancelación")
        suscripcion_activa.refresh_from_db()
        assert suscripcion_activa.estado == "CANCELADA"
        assert suscripcion_activa.fecha_cancelacion is not None
        assert "solicitó" in suscripcion_activa.notas

    def test_suscripcion_suspender(self, suscripcion_activa):
        suscripcion_activa.suspender()
        suscripcion_activa.refresh_from_db()
        assert suscripcion_activa.estado == "SUSPENDIDA"

    def test_suscripcion_activa_helper(self, db, empresa_a, suscripcion_activa):
        from apps.saas.models import suscripcion_activa as get_sus
        sus = get_sus(empresa_a)
        assert sus is not None
        assert sus.esta_vigente is True

    def test_suscripcion_activa_sin_suscripcion(self, db, empresa_a):
        from apps.saas.models import suscripcion_activa as get_sus
        # empresa_a sin suscripción → None
        sus = get_sus(empresa_a)
        assert sus is None

    def test_tiene_feature(self, db, empresa_a, suscripcion_activa):
        from apps.saas.models import tiene_feature
        assert tiene_feature(empresa_a, "permite_ia") is True
        assert tiene_feature(empresa_a, "permite_api") is True

    def test_no_tiene_feature_sin_suscripcion(self, db, empresa_a):
        from apps.saas.models import tiene_feature
        assert tiene_feature(empresa_a, "permite_ia") is False

    def test_plan_ilimitado(self, db):
        from apps.saas.models import Plan
        plan = Plan.objects.create(
            nombre="Enterprise Unlimited",
            nivel="ENTERPRISE",
            max_usuarios=0,  # ilimitado
        )
        assert plan.es_ilimitado("max_usuarios") is True
        assert plan.es_ilimitado("max_empresas") is False  # default 1


@pytest.mark.django_db
class TestSuscripcionMiddleware:
    """Middleware de verificación de suscripción."""

    def test_middleware_inactivo_permite_todo(self, empresa_a):
        from apps.saas.middleware import SuscripcionActivaMiddleware
        from django.test import RequestFactory
        from unittest.mock import MagicMock

        factory = RequestFactory()
        request = factory.get("/api/ventas/")
        request.user = MagicMock(is_authenticated=True)

        # Con SAAS_VERIFICAR_SUSCRIPCION=False (default) → permite todo
        get_response = MagicMock(return_value=MagicMock(status_code=200))
        middleware = SuscripcionActivaMiddleware(get_response)
        response = middleware(request)
        assert response.status_code == 200

    def test_middleware_excluye_rutas_admin(self, empresa_a):
        """Rutas de admin nunca deben ser verificadas."""
        from apps.saas.middleware import SuscripcionActivaMiddleware, RUTAS_EXCLUIDAS_DEFAULT
        assert "/admin/" in RUTAS_EXCLUIDAS_DEFAULT
        assert "/api/auth/" in RUTAS_EXCLUIDAS_DEFAULT


@pytest.mark.django_db
class TestSuscripcionMiddlewareActivo:
    """
    Middleware con SAAS_VERIFICAR_SUSCRIPCION=True.

    Verifica que la corrección de id_empresa → empresas.first() funcione
    correctamente: el middleware debe bloquear (402) cuando la empresa del
    usuario tiene únicamente una suscripción vencida, y permitir el paso
    cuando la suscripción está vigente o el usuario no tiene empresa.
    """

    @pytest.fixture
    def plan_free(self, db):
        from apps.saas.models import Plan
        return Plan.objects.create(nombre="Free Middleware Test", nivel="FREE")

    @staticmethod
    def _middleware(get_response):
        from apps.saas.middleware import SuscripcionActivaMiddleware
        return SuscripcionActivaMiddleware(get_response)

    # ------------------------------------------------------------------
    # Caso principal solicitado: suscripción vencida → 402
    # ------------------------------------------------------------------

    def test_bloquea_cuando_suscripcion_vencida(self, user_a, empresa_a, plan_free):
        """
        Regresión: antes del fix, id_empresa siempre era None y el middleware
        dejaba pasar sin verificar. Ahora debe detectar que la empresa sólo
        tiene una suscripción vencida y retornar HTTP 402.
        """
        import json
        from apps.saas.models import Suscripcion
        from django.test import RequestFactory, override_settings

        hoy = date.today()
        Suscripcion.objects.create(
            id_empresa=empresa_a,
            id_plan=plan_free,
            estado="ACTIVA",
            fecha_inicio=hoy - timedelta(days=60),
            fecha_fin=hoy - timedelta(days=1),  # venció ayer
        )

        factory = RequestFactory()
        request = factory.get("/api/ventas/pedidos/")
        request.user = user_a  # usuario real con empresas M2M

        get_response = MagicMock(return_value=MagicMock(status_code=200))

        with override_settings(SAAS_VERIFICAR_SUSCRIPCION=True):
            middleware = self._middleware(get_response)
            response = middleware(request)

        assert response.status_code == 402
        data = json.loads(response.content)
        assert data["codigo"] == "SUSCRIPCION_REQUERIDA"
        # El get_response nunca debe haberse llamado
        get_response.assert_not_called()

    # ------------------------------------------------------------------
    # Caso complementario: suscripción vigente → pasa
    # ------------------------------------------------------------------

    def test_permite_cuando_suscripcion_vigente(self, user_a, empresa_a, plan_free):
        """Empresa con suscripción ACTIVA dentro de fechas → 200."""
        from apps.saas.models import Suscripcion
        from django.test import RequestFactory, override_settings

        hoy = date.today()
        Suscripcion.objects.create(
            id_empresa=empresa_a,
            id_plan=plan_free,
            estado="ACTIVA",
            fecha_inicio=hoy - timedelta(days=5),
            fecha_fin=hoy + timedelta(days=25),
        )

        factory = RequestFactory()
        request = factory.get("/api/ventas/pedidos/")
        request.user = user_a

        get_response = MagicMock(return_value=MagicMock(status_code=200))

        with override_settings(SAAS_VERIFICAR_SUSCRIPCION=True):
            middleware = self._middleware(get_response)
            response = middleware(request)

        assert response.status_code == 200
        get_response.assert_called_once()

    # ------------------------------------------------------------------
    # Caso borde: usuario sin empresa → pasa sin verificar
    # ------------------------------------------------------------------

    def test_permite_usuario_sin_empresa(self, db):
        """Usuario sin empresa asociada no debe ser bloqueado."""
        from django.contrib.auth import get_user_model
        from django.test import RequestFactory, override_settings

        User = get_user_model()
        user_sin_empresa = User.objects.create_user(
            username="user_sin_empresa_mw",
            password="pass",
            is_active=True,
        )
        # Sin user_sin_empresa.empresas.add(...) → queryset vacío

        factory = RequestFactory()
        request = factory.get("/api/ventas/pedidos/")
        request.user = user_sin_empresa

        get_response = MagicMock(return_value=MagicMock(status_code=200))

        with override_settings(SAAS_VERIFICAR_SUSCRIPCION=True):
            middleware = self._middleware(get_response)
            response = middleware(request)

        assert response.status_code == 200
        get_response.assert_called_once()

    # ------------------------------------------------------------------
    # Caso borde: ruta excluida no se verifica aunque la suscrip. esté vencida
    # ------------------------------------------------------------------

    def test_excluye_ruta_api_auth_aunque_suscripcion_vencida(
        self, user_a, empresa_a, plan_free
    ):
        """Rutas excluidas nunca llegan a _verificar_suscripcion."""
        from apps.saas.models import Suscripcion
        from django.test import RequestFactory, override_settings

        hoy = date.today()
        Suscripcion.objects.create(
            id_empresa=empresa_a,
            id_plan=plan_free,
            estado="ACTIVA",
            fecha_inicio=hoy - timedelta(days=60),
            fecha_fin=hoy - timedelta(days=1),
        )

        factory = RequestFactory()
        request = factory.get("/api/auth/login/")
        request.user = user_a

        get_response = MagicMock(return_value=MagicMock(status_code=200))

        with override_settings(SAAS_VERIFICAR_SUSCRIPCION=True):
            middleware = self._middleware(get_response)
            response = middleware(request)

        # Ruta excluida → siempre pasa
        assert response.status_code == 200
        get_response.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# M10-T2: PDF generators
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestPDFGenerators:
    """PDF generators — test de importación y firma de funciones."""

    def test_pdf_cotizacion_importable(self):
        from apps.ventas.pdf_cotizacion import generar_pdf_cotizacion
        assert callable(generar_pdf_cotizacion)

    def test_pdf_nota_entrega_importable(self):
        from apps.despacho.pdf_nota_entrega import generar_pdf_nota_entrega
        assert callable(generar_pdf_nota_entrega)

    def test_pdf_estado_cuenta_importable(self):
        from apps.cuentas_por_cobrar.pdf_estado_cuenta import generar_pdf_estado_cuenta
        assert callable(generar_pdf_estado_cuenta)

    def test_pdf_cotizacion_retorna_bytes(self, db, empresa_a, moneda_usd):
        """Genera PDF de cotización con datos reales mínimos."""
        pytest.importorskip("reportlab", reason="reportlab no instalado")

        from apps.ventas.pdf_cotizacion import generar_pdf_cotizacion
        from apps.ventas.models import Cotizacion
        from apps.crm.models import Cliente

        cliente = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Cliente PDF Test",
            rif="J-99999999-0",
        )
        cot = Cotizacion.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            id_moneda=moneda_usd,
            numero_cotizacion="COT-PDF-001",
            fecha_cotizacion=date.today(),
            fecha_vencimiento=date.today() + timedelta(days=30),
            monto_total=Decimal("1000.00"),
        )
        pdf_bytes = generar_pdf_cotizacion(cot)
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 100
        assert pdf_bytes[:4] == b"%PDF"

    def test_pdf_estado_cuenta_retorna_bytes(self, db, empresa_a):
        """Genera PDF de estado de cuenta con BD vacía."""
        pytest.importorskip("reportlab", reason="reportlab no instalado")

        from apps.cuentas_por_cobrar.pdf_estado_cuenta import generar_pdf_estado_cuenta
        from apps.crm.models import Cliente

        cliente = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Cliente EC Test",
            rif="V-11111111-1",
        )
        pdf_bytes = generar_pdf_estado_cuenta(empresa_a, cliente)
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 100


# ─────────────────────────────────────────────────────────────────────────────
# M10-T3: Email service
# ─────────────────────────────────────────────────────────────────────────────


class TestEmailService:
    """Email service — tests unitarios sin envío real."""

    def test_importar_email_service(self):
        from apps.core.email_service import enviar_email, EmailError
        assert callable(enviar_email)

    def test_html_a_texto(self):
        from apps.core.email_service import _html_a_texto
        html = "<h1>Hola</h1><p>Estimado cliente.</p>"
        texto = _html_a_texto(html)
        assert "Hola" in texto
        assert "Estimado cliente" in texto
        assert "<h1>" not in texto

    def test_enviar_cotizacion_importable(self):
        from apps.core.email_service import enviar_cotizacion_pdf
        assert callable(enviar_cotizacion_pdf)

    def test_enviar_estado_cuenta_importable(self):
        from apps.core.email_service import enviar_estado_cuenta_pdf
        assert callable(enviar_estado_cuenta_pdf)

    def test_email_sin_destinatario_falla(self, db, empresa_a, moneda_usd):
        """Cliente sin email → EmailError."""
        from apps.core.email_service import enviar_cotizacion_pdf, EmailError
        from apps.ventas.models import Cotizacion
        from apps.crm.models import Cliente

        cliente = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Sin Email SA",
            rif="J-88888888-0",
            # email no configurado
        )
        cot = Cotizacion.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            id_moneda=moneda_usd,
            numero_cotizacion="COT-NOEMAIL-001",
            fecha_cotizacion=date.today(),
            fecha_vencimiento=date.today() + timedelta(days=30),
            monto_total=Decimal("500.00"),
        )
        with pytest.raises(EmailError, match="email"):
            enviar_cotizacion_pdf(cot)
