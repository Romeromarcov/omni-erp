"""
Tests para las tareas Celery de Omni ERP.

Usa CELERY_TASK_ALWAYS_EAGER=True para ejecutar tareas en el mismo proceso
(sin broker real), lo que permite tests rápidos sin Redis levantado.

Convenciones:
- Cada test verifica el resultado retornado por la tarea.
- Las tareas no deben tener efectos secundarios difíciles de revertir en tests.
- Fixtures de DB provienen de conftest.py (empresa_a, user_a, etc.).
"""
import pytest
from unittest.mock import patch


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def celery_eager(settings):
    """
    Fuerza ejecución síncrona de tareas Celery durante los tests.
    CELERY_TASK_ALWAYS_EAGER hace que .delay() y .apply_async() se ejecuten
    inmediatamente en el mismo thread, sin necesidad de broker ni worker.
    """
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True


# ── Tests core.ping ──────────────────────────────────────────────────────────

class TestCorePing:
    """core.ping — smoke-test del worker."""

    def test_ping_retorna_pong(self):
        """La tarea ping debe retornar status='pong'."""
        from apps.core.tasks import ping
        result = ping.apply()
        assert result.successful()
        assert result.get()['status'] == 'pong'

    def test_ping_retorna_task_id(self):
        """El resultado incluye un task_id (no vacío)."""
        from apps.core.tasks import ping
        result = ping.apply()
        data = result.get()
        assert 'task_id' in data
        assert data['task_id']  # no vacío

    def test_ping_via_delay(self):
        """ping.delay() también funciona en modo eager."""
        from apps.core.tasks import ping
        result = ping.delay()
        assert result.get()['status'] == 'pong'


# ── Tests core.log_evento ────────────────────────────────────────────────────

class TestCoreLogEvento:
    """core.log_evento — registro asíncrono de eventos de aplicación."""

    def test_log_evento_info(self):
        """Tarea con nivel info retorna el mismo nivel."""
        from apps.core.tasks import log_evento
        result = log_evento.apply(kwargs={
            'nivel': 'info',
            'mensaje': 'Test de evento info',
            'modulo': 'ventas',
        })
        assert result.successful()
        data = result.get()
        assert data['nivel'] == 'info'
        assert data['modulo'] == 'ventas'
        assert data['mensaje'] == 'Test de evento info'

    def test_log_evento_warning(self):
        """Nivel warning propagado correctamente."""
        from apps.core.tasks import log_evento
        result = log_evento.apply(kwargs={
            'nivel': 'warning',
            'mensaje': 'Alerta de inventario bajo',
            'modulo': 'inventario',
        })
        assert result.get()['nivel'] == 'warning'

    def test_log_evento_incluye_task_id(self):
        """El resultado siempre incluye task_id."""
        from apps.core.tasks import log_evento
        result = log_evento.apply(kwargs={
            'nivel': 'info',
            'mensaje': 'Msg',
        })
        data = result.get()
        assert 'task_id' in data

    def test_log_evento_modulo_default_es_core(self):
        """Si no se pasa modulo, el default es 'core'."""
        from apps.core.tasks import log_evento
        result = log_evento.apply(kwargs={
            'nivel': 'info',
            'mensaje': 'Sin modulo explícito',
        })
        assert result.get()['modulo'] == 'core'

    def test_log_evento_nivel_desconocido_no_falla(self):
        """Un nivel desconocido no debe levantar excepción — usa logger.info."""
        from apps.core.tasks import log_evento
        result = log_evento.apply(kwargs={
            'nivel': 'verbose',   # no existe → fallback a info
            'mensaje': 'Nivel custom',
        })
        assert result.successful()


# ── Tests auditoria.registrar_evento ────────────────────────────────────────

class TestAuditoriaRegistrarEvento:
    """auditoria.registrar_evento — persiste LogAuditoria en DB."""

    def test_registrar_evento_crea_log(self, db, empresa_a, user_a):
        """La tarea debe crear un registro en LogAuditoria."""
        from apps.auditoria.tasks import registrar_evento
        from apps.auditoria.models import LogAuditoria

        count_antes = LogAuditoria.objects.count()

        result = registrar_evento.apply(kwargs={
            'empresa_id': str(empresa_a.pk),
            'modulo': 'ventas',
            'tipo_accion': 'CREAR',
            'descripcion': 'Cotización creada en test',
            'usuario_id': user_a.pk,
        })

        assert result.successful()
        assert LogAuditoria.objects.count() == count_antes + 1

    def test_registrar_evento_retorna_log_id(self, db, empresa_a):
        """El resultado incluye el id del log creado."""
        from apps.auditoria.tasks import registrar_evento

        result = registrar_evento.apply(kwargs={
            'empresa_id': str(empresa_a.pk),
            'modulo': 'inventario',
            'tipo_accion': 'EDITAR',
        })

        data = result.get()
        assert 'log_id' in data
        assert data['log_id']   # no vacío
        assert data['modulo'] == 'inventario'

    def test_registrar_evento_sin_usuario(self, db, empresa_a):
        """El campo usuario es opcional — la tarea no debe fallar si es None."""
        from apps.auditoria.tasks import registrar_evento
        from apps.auditoria.models import LogAuditoria

        result = registrar_evento.apply(kwargs={
            'empresa_id': str(empresa_a.pk),
            'modulo': 'core',
            'tipo_accion': 'LOGIN',
            'usuario_id': None,
        })

        assert result.successful()
        log = LogAuditoria.objects.get(pk=result.get()['log_id'])
        assert log.id_usuario is None

    def test_registrar_evento_empresa_inexistente_falla(self, db):
        """Si la empresa no existe la tarea debe lanzar excepción (no reintentar).

        Con CELERY_TASK_EAGER_PROPAGATES=True la excepción se propaga
        directamente al llamar a apply(), por eso usamos pytest.raises.
        """
        from apps.auditoria.tasks import registrar_evento
        from apps.core.models import Empresa
        import uuid

        with pytest.raises(Empresa.DoesNotExist):
            registrar_evento.apply(kwargs={
                'empresa_id': str(uuid.uuid4()),  # UUID que no existe
                'modulo': 'core',
                'tipo_accion': 'TEST',
            })

    def test_registrar_evento_con_cambios_json(self, db, empresa_a):
        """El campo cambios_json se persiste correctamente."""
        from apps.auditoria.tasks import registrar_evento
        from apps.auditoria.models import LogAuditoria

        cambios = {'antes': {'estado': 'BORRADOR'}, 'despues': {'estado': 'CONFIRMADA'}}
        result = registrar_evento.apply(kwargs={
            'empresa_id': str(empresa_a.pk),
            'modulo': 'ventas',
            'tipo_accion': 'EDITAR',
            'cambios': cambios,
        })

        log = LogAuditoria.objects.get(pk=result.get()['log_id'])
        assert log.cambios_json == cambios
