"""
Tests del SyncEngine (apps/integration_hub/services/sync_engine.py).

Usa un conector fake registrado en el registry — CERO red real.
Cubre: pull happy-path, dedup por checksum, actualización, errores de
conector, errores por registro, direcciones, _calcular_desde y upserts.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from django.utils import timezone

from apps.integration_hub.connectors.base import (
    BaseConnector,
    ConnectorConnectionError,
    SyncResult,
    TestConnectionResult,
)
from apps.integration_hub.connectors.registry import registry
from apps.integration_hub.models import (
    ConectorInstancia,
    ConectorProveedor,
    EntidadSincronizada,
    JobSincronizacion,
    LogDetalleSincronizacion,
)
from apps.integration_hub.services.sync_engine import SyncEngine

pytestmark = pytest.mark.django_db


class FakeConnector(BaseConnector):
    """Conector de prueba — datos controlados por atributos de clase."""

    PROVIDER_CODE = "fake_test"
    PROVIDER_NAME = "FakeTest"
    SUPPORTED_ENTITIES = ["contactos", "productos", "pagos", "empleados"]

    # Estado controlado por cada test
    registros: list = []
    error: Exception | None = None
    ultimo_desde = "NO_LLAMADO"

    def test_connection(self) -> TestConnectionResult:
        return TestConnectionResult(success=True, message="ok")

    def get_version_info(self) -> dict:
        return {}

    def _pull(self, desde=None):
        FakeConnector.ultimo_desde = desde
        if FakeConnector.error is not None:
            raise FakeConnector.error
        return list(FakeConnector.registros)

    def pull_contactos(self, desde=None, limite=500):
        return self._pull(desde)

    def pull_productos(self, desde=None, limite=500):
        return self._pull(desde)

    def pull_pagos(self, desde=None, limite=300):
        return self._pull(desde)


@pytest.fixture
def fake_registry():
    """Registra FakeConnector y limpia su estado al terminar."""
    registry.register(FakeConnector)
    FakeConnector.registros = []
    FakeConnector.error = None
    FakeConnector.ultimo_desde = "NO_LLAMADO"
    yield registry
    registry._registry.pop("fake_test", None)
    FakeConnector.registros = []
    FakeConnector.error = None


@pytest.fixture
def proveedor_fake(db):
    return ConectorProveedor.objects.create(
        codigo="fake_test",
        nombre="Fake Test",
        capacidades=["contactos", "productos", "pagos"],
    )


@pytest.fixture
def instancia_fake(db, empresa_a, proveedor_fake):
    return ConectorInstancia.objects.create(
        id_empresa=empresa_a,
        id_proveedor=proveedor_fake,
        nombre="Conector Fake",
        configuracion={"host": "fake.local", "user": "u", "api_key": "k"},
        estado="activo",
        entidades_activas=["contactos"],
    )


def _job(instancia, tipo="contactos", direccion="inbound", parametros=None):
    return JobSincronizacion.objects.create(
        id_instancia=instancia,
        tipo_entidad=tipo,
        direccion=direccion,
        estado="pendiente",
        parametros=parametros or {},
    )


def _contacto(idx, checksum="chk-1"):
    return {
        "id_externo": str(idx),
        "nombre": f"Contacto {idx}",
        "email": f"c{idx}@test.com",
        "_checksum": checksum,
    }


class TestEjecutarJobPullHappyPath:
    def test_pull_crea_registros_y_completa_job(self, fake_registry, instancia_fake):
        FakeConnector.registros = [_contacto(1), _contacto(2)]
        job = _job(instancia_fake)

        resultado = SyncEngine().ejecutar_job(job)

        assert resultado.total == 2
        assert resultado.creados == 2
        assert resultado.actualizados == 0
        assert resultado.omitidos == 0
        assert resultado.fallidos == 0
        assert resultado.procesados == 2
        assert resultado.exitoso is True

        job.refresh_from_db()
        assert job.estado == "completado"
        assert job.total_registros == 2
        assert job.creados == 2
        assert job.completado_en is not None
        assert job.iniciado_en is not None
        assert job.resumen_errores == []

        instancia_fake.refresh_from_db()
        assert instancia_fake.estado == "activo"
        assert instancia_fake.ultimo_sync is not None

    def test_pull_crea_mappings_entidad_sincronizada(self, fake_registry, instancia_fake):
        FakeConnector.registros = [_contacto(7, checksum="abc")]
        SyncEngine().ejecutar_job(_job(instancia_fake))

        mapping = EntidadSincronizada.objects.get(
            id_instancia=instancia_fake, tipo_entidad="contactos", id_externo="7"
        )
        # Sin apps.crm.models.Contacto, el handler retorna el id_externo
        assert mapping.id_omni == "7"
        assert mapping.checksum == "abc"

    def test_pull_crea_logs_detalle_operacion_crear(self, fake_registry, instancia_fake):
        FakeConnector.registros = [_contacto(1)]
        job = _job(instancia_fake)
        SyncEngine().ejecutar_job(job)

        logs = list(LogDetalleSincronizacion.objects.filter(id_job=job))
        assert len(logs) == 1
        assert logs[0].operacion == "crear"
        assert logs[0].id_externo == "1"
        assert logs[0].resumen_externo == {"nombre": "Contacto 1"}


class TestDeduplicacionPorChecksum:
    def test_segunda_corrida_sin_cambios_crashea_por_bug_procesados(
        self, fake_registry, instancia_fake
    ):
        """BUG REAL (reportado, no enmascarado): SyncResult no define el campo
        'procesados'; _ejecutar_pull solo lo asigna al final de iteraciones NO
        omitidas (el branch 'omitir' hace continue antes). Si TODOS los registros
        están sin cambios — el estado estable de un sync incremental —
        _marcar_completado lanza AttributeError y el job queda 'en_progreso'.
        """
        FakeConnector.registros = [_contacto(1, "chk-a"), _contacto(2, "chk-b")]
        SyncEngine().ejecutar_job(_job(instancia_fake))

        job2 = _job(instancia_fake)
        with pytest.raises(AttributeError, match="procesados"):
            SyncEngine().ejecutar_job(job2)

        # Los logs 'omitir' sí se escribieron antes del crash…
        ops = list(
            LogDetalleSincronizacion.objects.filter(id_job=job2).values_list(
                "operacion", flat=True
            )
        )
        assert ops == ["omitir", "omitir"]
        # …pero el job queda colgado en 'en_progreso' (consecuencia del bug).
        job2.refresh_from_db()
        assert job2.estado == "en_progreso"

    def test_omitido_mas_nuevo_completa_y_cuenta(self, fake_registry, instancia_fake):
        """Si el último registro de la corrida NO es omitido, 'procesados' sí se
        asigna y el job completa: cubre el branch 'omitir' sin gatillar el bug."""
        FakeConnector.registros = [_contacto(1, "chk-a")]
        SyncEngine().ejecutar_job(_job(instancia_fake))

        FakeConnector.registros = [_contacto(1, "chk-a"), _contacto(2, "chk-b")]
        job2 = _job(instancia_fake)
        resultado = SyncEngine().ejecutar_job(job2)

        assert resultado.omitidos == 1
        assert resultado.creados == 1
        assert resultado.procesados == 2
        job2.refresh_from_db()
        assert job2.estado == "completado"
        assert job2.omitidos == 1
        assert job2.creados == 1

    def test_checksum_cambiado_actualiza_registro(self, fake_registry, instancia_fake):
        FakeConnector.registros = [_contacto(1, "chk-v1")]
        SyncEngine().ejecutar_job(_job(instancia_fake))

        FakeConnector.registros = [_contacto(1, "chk-v2")]
        job2 = _job(instancia_fake)
        resultado = SyncEngine().ejecutar_job(job2)

        assert resultado.creados == 0
        assert resultado.actualizados == 1
        mapping = EntidadSincronizada.objects.get(
            id_instancia=instancia_fake, id_externo="1"
        )
        assert mapping.checksum == "chk-v2"
        log = LogDetalleSincronizacion.objects.get(id_job=job2)
        assert log.operacion == "actualizar"


class TestErroresDeConector:
    def test_proveedor_sin_conector_marca_fallido(self, fake_registry, empresa_a):
        proveedor = ConectorProveedor.objects.create(
            codigo="sin_conector", nombre="Sin Conector"
        )
        instancia = ConectorInstancia.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor,
            nombre="Sin Conector Inst",
            configuracion={},
        )
        job = _job(instancia)

        resultado = SyncEngine().ejecutar_job(job)

        assert resultado.creados == 0
        job.refresh_from_db()
        assert job.estado == "fallido"
        assert "No hay conector registrado" in job.resumen_errores[0]["error"]
        instancia.refresh_from_db()
        assert instancia.estado == "error"
        assert "No hay conector registrado" in instancia.mensaje_estado

    def test_entidad_no_soportada_marca_fallido(self, fake_registry, instancia_fake):
        job = _job(instancia_fake, tipo="inventario")

        SyncEngine().ejecutar_job(job)

        job.refresh_from_db()
        assert job.estado == "fallido"
        assert "no soporta" in job.resumen_errores[0]["error"]

    def test_direccion_outbound_no_implementada(self, fake_registry, instancia_fake):
        job = _job(instancia_fake, direccion="outbound")

        SyncEngine().ejecutar_job(job)

        job.refresh_from_db()
        assert job.estado == "fallido"
        assert "outbound no implementada" in job.resumen_errores[0]["error"]

    def test_entidad_soportada_sin_metodo_pull(self, fake_registry, instancia_fake):
        # "empleados" está en SUPPORTED_ENTITIES del fake pero no en PULL_METHODS.
        # BUG 'procesados' (ver TestDeduplicacionPorChecksum): _ejecutar_pull
        # retorna sin asignar resultado.procesados → _marcar_completado crashea.
        job = _job(instancia_fake, tipo="empleados")

        with pytest.raises(AttributeError, match="procesados"):
            SyncEngine().ejecutar_job(job)

        job.refresh_from_db()
        assert job.estado == "en_progreso"  # job colgado — consecuencia del bug

    def test_error_de_conexion_en_pull(self, fake_registry, instancia_fake):
        # BUG 'procesados': el error de pull se registra en resultado.errores,
        # pero _marcar_completado crashea antes de persistir contadores.
        FakeConnector.error = ConnectorConnectionError("Odoo caído")
        job = _job(instancia_fake)

        with pytest.raises(AttributeError, match="procesados"):
            SyncEngine().ejecutar_job(job)

        job.refresh_from_db()
        assert job.estado == "en_progreso"

    def test_error_inesperado_en_pull(self, fake_registry, instancia_fake):
        # Mismo BUG 'procesados' para excepciones no tipadas del conector.
        FakeConnector.error = RuntimeError("kaboom")
        job = _job(instancia_fake)

        with pytest.raises(AttributeError, match="procesados"):
            SyncEngine().ejecutar_job(job)

    def test_pull_vacio_crashea_por_bug_procesados(self, fake_registry, instancia_fake):
        # BUG 'procesados': con pull que retorna lista vacía, el for nunca corre
        # y resultado.procesados no existe al llegar a _marcar_completado.
        FakeConnector.registros = []
        job = _job(instancia_fake)

        with pytest.raises(AttributeError, match="procesados"):
            SyncEngine().ejecutar_job(job)


class TestErroresPorRegistro:
    def test_excepcion_en_upsert_registra_fallido_y_log_error(
        self, fake_registry, instancia_fake
    ):
        FakeConnector.registros = [_contacto(1)]
        job = _job(instancia_fake)

        with patch.object(
            SyncEngine, "_upsert_en_omni", side_effect=RuntimeError("upsert roto")
        ):
            resultado = SyncEngine().ejecutar_job(job)

        assert resultado.fallidos == 1
        assert resultado.creados == 0
        assert resultado.errores[0] == {"id": "1", "error": "upsert roto"}

        job.refresh_from_db()
        assert job.estado == "completado_con_errores"
        assert job.fallidos == 1
        assert job.resumen_errores == [{"id": "1", "error": "upsert roto"}]

        log = LogDetalleSincronizacion.objects.get(id_job=job)
        assert log.operacion == "error"
        assert log.mensaje_error == "upsert roto"

    def test_upsert_retorna_none_cuenta_como_omitido(self, fake_registry, instancia_fake):
        FakeConnector.registros = [_contacto(1)]
        job = _job(instancia_fake)

        with patch.object(SyncEngine, "_upsert_en_omni", return_value=None):
            resultado = SyncEngine().ejecutar_job(job)

        assert resultado.omitidos == 1
        assert resultado.creados == 0
        assert resultado.fallidos == 0


class TestCalcularDesde:
    def test_desde_en_parametros_iso(self, fake_registry, instancia_fake):
        job = _job(instancia_fake, parametros={"desde": "2024-06-01T00:00:00"})
        desde = SyncEngine()._calcular_desde(job)
        assert desde == datetime(2024, 6, 1, 0, 0, 0)

    def test_desde_invalido_cae_a_ultimo_job(self, fake_registry, instancia_fake):
        previo = _job(instancia_fake)
        momento = timezone.now() - timedelta(hours=3)
        JobSincronizacion.objects.filter(pk=previo.pk).update(
            estado="completado", completado_en=momento
        )

        job = _job(instancia_fake, parametros={"desde": "no-es-fecha"})
        desde = SyncEngine()._calcular_desde(job)
        assert desde == momento

    def test_sin_historial_retorna_none(self, fake_registry, instancia_fake):
        job = _job(instancia_fake)
        assert SyncEngine()._calcular_desde(job) is None

    def test_pull_incremental_usa_completado_en_del_ultimo_job(
        self, fake_registry, instancia_fake
    ):
        FakeConnector.registros = [_contacto(1)]
        job1 = _job(instancia_fake)
        SyncEngine().ejecutar_job(job1)
        job1.refresh_from_db()

        FakeConnector.registros = [_contacto(2)]
        job2 = _job(instancia_fake)
        SyncEngine().ejecutar_job(job2)

        assert FakeConnector.ultimo_desde == job1.completado_en

    def test_jobs_fallidos_no_cuentan_para_incremental(self, fake_registry, instancia_fake):
        previo = _job(instancia_fake)
        JobSincronizacion.objects.filter(pk=previo.pk).update(
            estado="fallido", completado_en=timezone.now()
        )
        job = _job(instancia_fake)
        assert SyncEngine()._calcular_desde(job) is None


class TestUpsertEnOmni:
    def test_entidad_sin_handler_retorna_id_externo(self, fake_registry, instancia_fake):
        engine = SyncEngine()
        resultado = engine._upsert_en_omni("pagos", {"id_externo": "77"}, instancia_fake)
        assert resultado == "77"

    def test_entidad_sin_handler_y_sin_id_retorna_vacio(self, fake_registry, instancia_fake):
        engine = SyncEngine()
        assert engine._upsert_en_omni("pagos", {}, instancia_fake) == ""

    def test_upsert_contacto_sin_modelo_crm_retorna_id_externo(
        self, fake_registry, instancia_fake
    ):
        # apps.crm.models NO define Contacto (aún) → rama ImportError
        engine = SyncEngine()
        resultado = engine._upsert_contacto({"id_externo": "5"}, instancia_fake)
        assert resultado == "5"


class TestSyncResult:
    def test_agregar_error_limita_a_100_pero_cuenta_todos(self):
        resultado = SyncResult(tipo_entidad="contactos")
        for i in range(105):
            resultado.agregar_error(str(i), "e")
        assert len(resultado.errores) == 100
        assert resultado.fallidos == 105
        assert resultado.exitoso is False

    def test_exitoso_sin_fallidos(self):
        resultado = SyncResult(tipo_entidad="contactos", creados=3)
        assert resultado.exitoso is True
