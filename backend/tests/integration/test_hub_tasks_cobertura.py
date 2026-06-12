"""
Tests de cobertura de las tareas Celery del Integration Hub
(apps/integration_hub/tasks.py).

CELERY_TASK_ALWAYS_EAGER está activo en conftest — las tareas corren
sincrónicamente. Todo acceso externo (Odoo, BCV, Binance) se mockea.
"""
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from django.core.cache import cache
from django.utils import timezone

from apps.integration_hub.connectors.registry import registry
from apps.integration_hub.models import (
    ConectorInstancia,
    ConectorProveedor,
    JobSincronizacion,
    LogDetalleSincronizacion,
)
from apps.integration_hub.tasks import (
    ejecutar_job_sincronizacion,
    limpiar_logs_antiguos,
    sync_automatico_todos,
    sync_cartera_odoo,
    sync_cartera_odoo_todos,
    sync_tasas_ve,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def proveedor(db):
    return ConectorProveedor.objects.create(
        codigo="fake_tasks", nombre="Fake Tasks", capacidades=["contactos"]
    )


@pytest.fixture
def instancia(db, empresa_a, proveedor):
    return ConectorInstancia.objects.create(
        id_empresa=empresa_a,
        id_proveedor=proveedor,
        nombre="Conector Tasks",
        configuracion={"host": "fake.local", "user": "u", "api_key": "k"},
        estado="activo",
        intervalo_sync_minutos=15,
        entidades_activas=["contactos"],
    )


def _mock_conector(registros=None):
    conector = MagicMock()
    conector.PROVIDER_NAME = "MockProv"
    conector.supports.return_value = True
    conector.pull_contactos.return_value = registros or []
    return conector


class TestEjecutarJobSincronizacion:
    def test_job_inexistente_retorna_error(self):
        fake_id = str(uuid.uuid4())
        resultado = ejecutar_job_sincronizacion(fake_id)
        assert resultado == {"error": f"Job {fake_id} no encontrado"}

    def test_job_ya_procesado_se_omite(self, instancia):
        job = JobSincronizacion.objects.create(
            id_instancia=instancia, tipo_entidad="contactos", estado="completado"
        )
        resultado = ejecutar_job_sincronizacion(str(job.id_job))
        assert resultado == {"estado": "completado", "mensaje": "Job ya procesado"}

    def test_job_cancelado_se_omite(self, instancia):
        job = JobSincronizacion.objects.create(
            id_instancia=instancia, tipo_entidad="contactos", estado="cancelado"
        )
        resultado = ejecutar_job_sincronizacion(str(job.id_job))
        assert resultado["mensaje"] == "Job ya procesado"

    def test_job_pendiente_se_ejecuta_y_retorna_contadores(self, instancia):
        job = JobSincronizacion.objects.create(
            id_instancia=instancia, tipo_entidad="contactos", estado="pendiente"
        )
        conector = _mock_conector(
            registros=[{"id_externo": "1", "nombre": "X", "_checksum": "c1"}]
        )
        with patch.object(registry, "get_connector", return_value=conector):
            resultado = ejecutar_job_sincronizacion(str(job.id_job))

        assert resultado == {
            "job_id": str(job.id_job),
            "estado": "completado",
            "creados": 1,
            "actualizados": 0,
            "omitidos": 0,
            "fallidos": 0,
        }
        job.refresh_from_db()
        assert job.estado == "completado"


class TestSyncAutomaticoTodos:
    def test_dispara_un_job_por_entidad_activa(self, instancia):
        instancia.entidades_activas = ["contactos", "productos"]
        instancia.ultimo_sync = None  # nunca sincronizado → dispara ya
        instancia.save()

        with patch(
            "apps.integration_hub.tasks.ejecutar_job_sincronizacion.delay"
        ) as mock_delay:
            resultado = sync_automatico_todos()

        assert resultado == {"jobs_disparados": 2}
        assert mock_delay.call_count == 2
        jobs = JobSincronizacion.objects.filter(id_instancia=instancia)
        assert jobs.count() == 2
        assert set(jobs.values_list("tipo_entidad", flat=True)) == {
            "contactos", "productos",
        }
        # Automáticos: sin usuario iniciador
        assert all(j.iniciado_por is None for j in jobs)

    def test_no_dispara_si_intervalo_no_vencido(self, instancia):
        instancia.ultimo_sync = timezone.now() - timedelta(minutes=5)  # < 15 min
        instancia.save()
        with patch(
            "apps.integration_hub.tasks.ejecutar_job_sincronizacion.delay"
        ) as mock_delay:
            resultado = sync_automatico_todos()
        assert resultado == {"jobs_disparados": 0}
        mock_delay.assert_not_called()

    def test_dispara_si_intervalo_vencido(self, instancia):
        instancia.ultimo_sync = timezone.now() - timedelta(minutes=20)  # > 15 min
        instancia.save()
        with patch(
            "apps.integration_hub.tasks.ejecutar_job_sincronizacion.delay"
        ) as mock_delay:
            resultado = sync_automatico_todos()
        assert resultado == {"jobs_disparados": 1}
        mock_delay.assert_called_once()

    def test_omite_entidad_con_job_en_progreso(self, instancia):
        JobSincronizacion.objects.create(
            id_instancia=instancia, tipo_entidad="contactos", estado="en_progreso"
        )
        with patch(
            "apps.integration_hub.tasks.ejecutar_job_sincronizacion.delay"
        ) as mock_delay:
            resultado = sync_automatico_todos()
        assert resultado == {"jobs_disparados": 0}
        mock_delay.assert_not_called()

    def test_omite_conector_solo_manual(self, instancia):
        instancia.intervalo_sync_minutos = 0
        instancia.save()
        resultado = sync_automatico_todos()
        assert resultado == {"jobs_disparados": 0}

    def test_omite_conector_en_estado_error(self, instancia):
        instancia.estado = "error"
        instancia.save()
        resultado = sync_automatico_todos()
        assert resultado == {"jobs_disparados": 0}


class TestLimpiarLogsAntiguos:
    def test_elimina_solo_logs_anteriores_al_corte(self, instancia):
        job = JobSincronizacion.objects.create(
            id_instancia=instancia, tipo_entidad="contactos", estado="completado"
        )
        log_viejo = LogDetalleSincronizacion.objects.create(
            id_job=job, id_externo="1", operacion="crear"
        )
        log_reciente = LogDetalleSincronizacion.objects.create(
            id_job=job, id_externo="2", operacion="crear"
        )
        # creado_en es auto_now_add → forzar antigüedad vía update()
        LogDetalleSincronizacion.objects.filter(pk=log_viejo.pk).update(
            creado_en=timezone.now() - timedelta(days=45)
        )

        resultado = limpiar_logs_antiguos(dias=30)

        assert resultado == {"eliminados": 1}
        restantes = LogDetalleSincronizacion.objects.filter(id_job=job)
        assert list(restantes.values_list("pk", flat=True)) == [log_reciente.pk]
        # El job se mantiene
        assert JobSincronizacion.objects.filter(pk=job.pk).exists()

    def test_sin_logs_antiguos_retorna_cero(self, instancia):
        assert limpiar_logs_antiguos(dias=30) == {"eliminados": 0}


class TestSyncTasasVe:
    @pytest.fixture
    def monedas(self, db, moneda_usd):
        from apps.finanzas.models import Moneda

        ves = Moneda.objects.create(
            nombre="Bolívar", codigo_iso="VES", simbolo="Bs", tipo_moneda="fiat"
        )
        return moneda_usd, ves

    def test_persiste_tasas_bcv_y_binance(self, monedas):
        from apps.finanzas.models import TasaCambio

        usd, ves = monedas
        mock_connector = MagicMock()
        mock_connector.pull_tasa_bcv.return_value = Decimal("36.50")
        mock_connector.pull_tasa_binance_p2p.return_value = Decimal("40.10")

        with patch(
            "apps.integration_hub.connectors.tasas_ve.connector.TasasVeConnector",
            return_value=mock_connector,
        ):
            resultado = sync_tasas_ve.apply().get()

        assert resultado["bcv"] == {"tasa": "36.50", "created": True}
        assert resultado["binance_p2p"] == {"tasa": "40.10", "created": True}

        bcv = TasaCambio.objects.get(tipo_tasa="OFICIAL_BCV")
        assert bcv.id_empresa is None
        assert bcv.id_moneda_origen_id == usd.pk
        assert bcv.id_moneda_destino_id == ves.pk
        assert bcv.valor_tasa == Decimal("36.50")
        assert bcv.referencia_externa == "hub:sync_tasas_ve"

        binance = TasaCambio.objects.get(tipo_tasa="PROMEDIO_MERCADO")
        assert binance.valor_tasa == Decimal("40.10")
        assert binance.referencia_externa == "hub:binance_p2p"

    def test_binance_no_disponible_solo_persiste_bcv(self, monedas):
        from apps.finanzas.models import TasaCambio

        mock_connector = MagicMock()
        mock_connector.pull_tasa_bcv.return_value = Decimal("36.50")
        mock_connector.pull_tasa_binance_p2p.return_value = None

        with patch(
            "apps.integration_hub.connectors.tasas_ve.connector.TasasVeConnector",
            return_value=mock_connector,
        ):
            resultado = sync_tasas_ve.apply().get()

        assert "bcv" in resultado
        assert "binance_p2p" not in resultado
        assert TasaCambio.objects.filter(tipo_tasa="PROMEDIO_MERCADO").count() == 0

    def test_monedas_faltantes_retorna_error(self, db):
        # Sin USD/VES en BD
        mock_connector = MagicMock()
        with patch(
            "apps.integration_hub.connectors.tasas_ve.connector.TasasVeConnector",
            return_value=mock_connector,
        ):
            resultado = sync_tasas_ve.apply().get()
        assert resultado == {"error": "Monedas no encontradas"}

    def test_bcv_no_disponible_reintenta(self, monedas):
        from celery.exceptions import Retry

        mock_connector = MagicMock()
        mock_connector.pull_tasa_bcv.return_value = None

        with patch(
            "apps.integration_hub.connectors.tasas_ve.connector.TasasVeConnector",
            return_value=mock_connector,
        ):
            with pytest.raises(Retry):
                sync_tasas_ve.apply(throw=True).get()


class TestSyncCarteraOdooTodos:
    def test_encola_solo_tenants_con_datasource_odoo(self, empresa_a, empresa_b):
        from apps.configuracion_motor.models import ParametroSistema

        ParametroSistema.objects.create(
            id_empresa=empresa_a,
            codigo_parametro="cxc.datasource",
            valor_parametro="odoo",
        )
        ParametroSistema.objects.create(
            id_empresa=empresa_b,
            codigo_parametro="cxc.datasource",
            valor_parametro="local",
        )

        with patch(
            "apps.integration_hub.tasks.sync_cartera_odoo.delay"
        ) as mock_delay:
            resultado = sync_cartera_odoo_todos()

        assert resultado == {"tenants_odoo": 1}
        mock_delay.assert_called_once_with(str(empresa_a.pk))

    def test_ignora_parametros_globales_e_inactivos(self, empresa_a):
        from apps.configuracion_motor.models import ParametroSistema

        # Global (id_empresa=None) — excluido por id_empresa__isnull=False
        ParametroSistema.objects.create(
            id_empresa=None,
            codigo_parametro="cxc.datasource",
            valor_parametro="odoo",
        )
        # Inactivo
        ParametroSistema.objects.create(
            id_empresa=empresa_a,
            codigo_parametro="cxc.datasource",
            valor_parametro="odoo",
            activo=False,
        )

        with patch(
            "apps.integration_hub.tasks.sync_cartera_odoo.delay"
        ) as mock_delay:
            resultado = sync_cartera_odoo_todos()

        assert resultado == {"tenants_odoo": 0}
        mock_delay.assert_not_called()


class TestSyncCarteraOdoo:
    def test_refresca_cache_de_aging(self, empresa_a):
        partidas = [{"monto": "10"}, {"monto": "20"}]
        resumen = {"total": "30"}

        mock_provider = MagicMock()
        mock_provider.get_partidas.return_value = partidas

        with patch(
            "apps.cuentas_por_cobrar.services_cartera_provider.get_cartera_provider",
            return_value=mock_provider,
        ), patch(
            "apps.cuentas_por_cobrar.services_aging.calcular_aging",
            return_value=resumen,
        ) as mock_aging:
            resultado = sync_cartera_odoo(str(empresa_a.pk))

        assert resultado == {"empresa_id": str(empresa_a.pk), "partidas": 2}
        mock_aging.assert_called_once_with(partidas)
        assert cache.get(f"cxc:aging:{empresa_a.pk}") == resumen

    def test_empresa_inexistente_retorna_error(self, db):
        resultado = sync_cartera_odoo(str(uuid.uuid4()))
        assert "error" in resultado

    def test_error_del_provider_retorna_error(self, empresa_a):
        with patch(
            "apps.cuentas_por_cobrar.services_cartera_provider.get_cartera_provider",
            side_effect=RuntimeError("Odoo inaccesible"),
        ):
            resultado = sync_cartera_odoo(str(empresa_a.pk))
        assert resultado == {"error": "Odoo inaccesible"}
