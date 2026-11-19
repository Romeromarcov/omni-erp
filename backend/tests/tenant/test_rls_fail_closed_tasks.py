"""Tests de endurecimiento fail-closed para RLS_ENABLED=True (CTF-012 / Plan 06 tarea 2.1).

Verifica bajo rol no-privilegiado (``rls_test_role``) y ``@override_settings(RLS_ENABLED=True)``:
1. Default fail-closed fuera de request, en ``connection_created`` y en ``pre_migrate``/``post_migrate``.
2. ``rls_tenant_context`` + anidamiento seguro (preserva/restaura GUCs incluso ante excepciones).
3. Tareas Celery (por empresa, lookup PK→tenant y periódicas ``*_todos``) partiendo de fail-closed.
4. Management commands globales y tenant (incl. ``transaction.atomic()`` + ``--dry-run`` rollback).
5. Flujos HTTP reales (``/api/auth/login/`` con dispositivo, ``/api/core/sucursales/``, ``/api/saas/signup/``)
   a través de ``RLSContextMiddleware`` retornando a fail-closed al cerrar.
6. Guardia estática de inventario sobre todos los ``tasks.py`` y ``management/commands/*.py``.
7. Memoización por request de ``get_empresas_visible`` e invalidación por signals de membresía.
"""

from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command
from django.db import connection
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.activaciones.models import CalendarioActivacion, EventoActivacion
from apps.auditoria.models import LogAuditoria
from apps.core import rls
from apps.core.middleware import RLSContextMiddleware
from apps.core.models import Dispositivo, Sucursal, Usuarios
from apps.core.signals import (
    enable_rls_bypass_for_migrate,
    on_usuario_empresa_changed_invalidar_cache,
    restore_rls_default_after_migrate,
    set_default_rls_context,
)
from apps.core.viewsets import (
    get_empresas_visible,
    iniciar_cache_empresas_visible,
    limpiar_cache_empresas_visible,
)
from apps.crm.models import Cliente
from apps.integration_hub.connectors.base import SyncResult
from apps.integration_hub.models import ConectorInstancia, ConectorProveedor, JobSincronizacion
from apps.integration_hub.services.sync_engine import SyncEngine
from apps.notificaciones.models import CanalNotificacion, LogNotificacion, PlantillaNotificacion
from apps.saas.models import Plan, Suscripcion
from apps.tareas.models import PlantillaTareaRecurrente, Tarea

pytestmark = [pytest.mark.django_db, pytest.mark.tenant]


@pytest.fixture(autouse=True)
def _enforce_rls_role(rls_test_role):
    """Fuerza el rol no-privilegiado para que PostgreSQL evalúe las políticas RLS."""
    if rls_test_role is None:
        yield
        return
    with connection.cursor() as cur:
        cur.execute(f'SET ROLE "{rls_test_role}"')
    try:
        yield
    finally:
        with connection.cursor() as cur:
            cur.execute("RESET ROLE")


@pytest.fixture
def dos_sucursales(empresa_a, empresa_b):
    with rls.rls_bypass():
        suc_a = Sucursal.objects.create(id_empresa=empresa_a, nombre="Sucursal Alpha", codigo_sucursal="SA01")
        suc_b = Sucursal.objects.create(id_empresa=empresa_b, nombre="Sucursal Beta", codigo_sucursal="SB01")
    yield {"a": suc_a, "b": suc_b}
    rls.apply_system_default()


@override_settings(RLS_ENABLED=True)
def test_fail_closed_fuera_de_request_y_signals_conexion_y_migrate(dos_sucursales):
    """Con RLS_ENABLED=True, apply_system_default y connection_created dejan bypass='off'."""
    rls.apply_system_default()
    assert rls._get_current_context() == ("off", "")
    assert Sucursal.objects.count() == 0

    # Signal connection_created aplica el mismo estado fail-closed.
    with rls.rls_bypass():
        assert Sucursal.objects.count() == 2
        set_default_rls_context(sender=None, connection=connection)
        assert rls._get_current_context() == ("off", "")
        assert Sucursal.objects.count() == 0

    # Signals pre_migrate / post_migrate envuelven migrate en bypass y restauran fail-closed.
    enable_rls_bypass_for_migrate(sender=None)
    assert Sucursal.objects.count() == 2
    restore_rls_default_after_migrate(sender=None)
    assert rls._get_current_context() == ("off", "")
    assert Sucursal.objects.count() == 0


@override_settings(RLS_ENABLED=True)
def test_rls_tenant_context_anidamiento_y_restauracion_en_excepcion(dos_sucursales, empresa_a, empresa_b):
    """Anidar rls_tenant_context y rls_bypass preserva y restaura siempre el GUC previo."""
    rls.apply_system_default()
    assert Sucursal.objects.count() == 0

    with rls.rls_tenant_context([empresa_a.pk]):
        assert set(Sucursal.objects.values_list("id_sucursal", flat=True)) == {dos_sucursales["a"].pk}

        with rls.rls_tenant_context([empresa_b.pk]):
            assert set(Sucursal.objects.values_list("id_sucursal", flat=True)) == {dos_sucursales["b"].pk}

        # Al salir del contexto interno B se restaura exactamente A.
        assert set(Sucursal.objects.values_list("id_sucursal", flat=True)) == {dos_sucursales["a"].pk}

        with rls.rls_bypass():
            assert set(Sucursal.objects.values_list("id_sucursal", flat=True)) == {
                dos_sucursales["a"].pk,
                dos_sucursales["b"].pk,
            }
        # Al salir de rls_bypass() dentro de contexto tenant A se restaura A.
        assert set(Sucursal.objects.values_list("id_sucursal", flat=True)) == {dos_sucursales["a"].pk}

        # Incluso ante excepción en bloque anidado, restaura contexto previo A.
        with pytest.raises(RuntimeError):
            with rls.rls_tenant_context([empresa_b.pk]):
                assert set(Sucursal.objects.values_list("id_sucursal", flat=True)) == {dos_sucursales["b"].pk}
                raise RuntimeError("fallo simulado")

        assert set(Sucursal.objects.values_list("id_sucursal", flat=True)) == {dos_sucursales["a"].pk}

    with pytest.raises(TypeError):
        with rls.rls_tenant_context(empresa_a.pk):
            pass

    # Al salir del contexto externo restaura fail-closed.
    assert rls._get_current_context() == ("off", "")
    assert Sucursal.objects.count() == 0


@override_settings(RLS_ENABLED=True)
def test_celery_tasks_aisladas_con_rls_enabled(empresa_a, empresa_b, user_a):
    """Tareas por empresa, lookup PK→tenant y periódicas *_todos funcionan desde fail-closed."""
    from apps.auditoria.tasks import registrar_evento
    from apps.integration_hub.tasks import ejecutar_job_sincronizacion
    from apps.tareas.tasks import ejecutar_ciclo_empresa, ejecutar_ciclo_todos

    ayer = date.today() - timedelta(days=1)
    with rls.rls_bypass():
        PlantillaTareaRecurrente.objects.create(
            id_empresa=empresa_a,
            titulo="Cierre diario A",
            frecuencia=PlantillaTareaRecurrente.Frecuencia.DIARIA,
            proxima_ejecucion=ayer,
            creado_por=user_a,
        )
        PlantillaTareaRecurrente.objects.create(
            id_empresa=empresa_b,
            titulo="Cierre diario B",
            frecuencia=PlantillaTareaRecurrente.Frecuencia.DIARIA,
            proxima_ejecucion=ayer,
        )
        prov = ConectorProveedor.objects.create(codigo="odoo-rls", nombre="Odoo RLS")
        inst_a = ConectorInstancia.objects.create(
            id_empresa=empresa_a,
            id_proveedor=prov,
            nombre="Inst A",
            estado="activo",
            configuracion={"host": "http://odoo.local", "user": "u", "api_key": "k"},
            entidades_activas=["contactos"],
        )
        inst_b = ConectorInstancia.objects.create(
            id_empresa=empresa_b,
            id_proveedor=prov,
            nombre="Inst B",
            estado="activo",
            configuracion={"host": "http://odoo.local", "user": "u", "api_key": "k"},
            entidades_activas=["contactos"],
        )
        job_a = JobSincronizacion.objects.create(
            id_instancia=inst_a,
            tipo_entidad="contactos",
            estado="pendiente",
        )
        ConectorInstancia.objects.filter(pk=inst_b.pk).update(nombre="Inst B Visibilidad")

    # 1. Tarea por empresa (arranca fail-closed y vuelve a fail-closed)
    rls.apply_system_default()
    assert PlantillaTareaRecurrente.objects.count() == 0
    res_emp = ejecutar_ciclo_empresa(str(empresa_a.pk))
    assert res_emp["recurrentes_creadas"] == 1
    assert rls._get_current_context() == ("off", "")
    assert Tarea.objects.count() == 0

    with rls.rls_bypass():
        assert Tarea.objects.filter(id_empresa=empresa_a).count() == 1
        assert Tarea.objects.filter(id_empresa=empresa_b).count() == 0

    # 2. Tarea con lookup PK -> tenant (ejecutar_job_sincronizacion) solo ve su tenant
    observed_instancias = []

    def fake_ejecutar_job(_self, job):
        observed_instancias.append(set(ConectorInstancia.objects.values_list("id_empresa_id", flat=True)))
        job.estado = "completado"
        job.save(update_fields=["estado"])
        return SyncResult(tipo_entidad=job.tipo_entidad, creados=1, actualizados=0, omitidos=0, fallidos=0)

    rls.apply_system_default()
    with patch.object(SyncEngine, "ejecutar_job", fake_ejecutar_job):
        res_job = ejecutar_job_sincronizacion.apply(args=[str(job_a.pk)]).get()
    assert res_job["estado"] == "completado"
    assert observed_instancias == [{empresa_a.pk}]
    assert rls._get_current_context() == ("off", "")

    # 3. Tarea auditoria.registrar_evento
    rls.apply_system_default()
    res_aud = registrar_evento.apply(
        kwargs={
            "empresa_id": str(empresa_a.pk),
            "modulo": "ventas",
            "tipo_accion": "CREAR",
            "usuario_id": user_a.pk,
        }
    ).get()
    assert res_aud["empresa_id"] == str(empresa_a.pk)
    assert rls._get_current_context() == ("off", "")
    with rls.rls_bypass():
        assert LogAuditoria.objects.filter(pk=res_aud["log_id"], id_empresa=empresa_a).exists()

    # 4. Tarea periódica *_todos: procesa empresa_a y empresa_b aislando cada iteración
    rls.apply_system_default()
    res_todos = ejecutar_ciclo_todos()
    assert res_todos["empresas_procesadas"] >= 2
    assert res_todos["errores"] == 0
    assert rls._get_current_context() == ("off", "")
    with rls.rls_bypass():
        assert Tarea.objects.filter(id_empresa=empresa_a).count() >= 1
        assert Tarea.objects.filter(id_empresa=empresa_b).count() == 1


@override_settings(RLS_ENABLED=True)
def test_management_commands_con_rls_fail_closed(empresa_a, empresa_b):
    """Comandos seed globales y comandos tenant (incl. dry-run con set_rollback) funcionan desde fail-closed."""
    with rls.rls_bypass():
        cli_a = Cliente.objects.create(id_empresa=empresa_a, razon_social="Cliente Migrar", rif="J-90000001-1")
        Cliente.objects.create(id_empresa=empresa_b, razon_social="Ajeno Beta", rif="J-90000002-2")

    rls.apply_system_default()
    call_command("seed_catalogo_monedas")
    assert rls._get_current_context() == ("off", "")

    rls.apply_system_default()
    call_command("seed_proveedores_integracion")
    assert rls._get_current_context() == ("off", "")

    rls.apply_system_default()
    call_command(
        "crear_usuario_bot",
        "--empresa-rif",
        empresa_a.identificador_fiscal,
        "--username",
        "bot_service_rls",
        "--password",
        "BotServiceRls#2026!",
    )
    assert rls._get_current_context() == ("off", "")
    with rls.rls_bypass():
        bot_user = Usuarios.objects.get(username="bot_service_rls")
        assert set(bot_user.empresas.values_list("id_empresa", flat=True)) == {empresa_a.pk}

    # migrar_contactos --dry-run usa rls_tenant_context fuera de transaction.atomic() + set_rollback(True)
    rls.apply_system_default()
    call_command(
        "migrar_contactos",
        "--origen",
        str(empresa_a.pk),
        "--destino",
        str(empresa_b.pk),
        "--dry-run",
    )
    assert rls._get_current_context() == ("off", "")
    with rls.rls_bypass():
        cli_a.refresh_from_db()
        assert cli_a.id_empresa_id == empresa_a.pk


@override_settings(RLS_ENABLED=True)
def test_http_login_signup_y_requests_autenticados_bajo_rls(dos_sucursales, empresa_a, empresa_b, user_a):
    """Login JWT + dispositivo, request tenant y SignupView funcionan con RLS_ENABLED=True y restauran fail-closed."""
    with rls.rls_bypass():
        user_a.set_password("LoginRlsPass#2026!")
        user_a.sucursales.add(dos_sucursales["a"])
        user_a.id_sucursal_predeterminada = dos_sucursales["a"]
        user_a.save(update_fields=["password", "id_sucursal_predeterminada"])
        Plan.objects.create(nombre="Starter RLS", nivel="STARTER", activo=True)

    rls.apply_system_default()
    client = APIClient()

    # 1. Login con fingerprint (serializa UsuariosSerializer + crea Dispositivo)
    login_resp = client.post(
        "/api/auth/login/",
        {
            "username": user_a.username,
            "password": "LoginRlsPass#2026!",
            "device_fingerprint": "fp-rls-e2e-001",
            "device_user_agent": "pytest-rls",
        },
        format="json",
    )
    assert login_resp.status_code == 200
    body = login_resp.json()
    assert "access" in body
    assert body["user"]["username"] == user_a.username
    assert body["dispositivo"]["creado"] is True
    # Middleware deja conexión fail-closed tras terminar el request.
    assert rls._get_current_context() == ("off", "")
    assert Sucursal.objects.count() == 0
    assert Dispositivo.objects.count() == 0

    # 2. Request autenticado ve solo la empresa del token y vuelve a fail-closed.
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access']}")
    suc_resp = client.get("/api/core/sucursales/")
    assert suc_resp.status_code == 200
    suc_payload = suc_resp.json()
    items = suc_payload["results"] if isinstance(suc_payload, dict) and "results" in suc_payload else suc_payload
    assert {row["id_sucursal"] for row in items} == {str(dos_sucursales["a"].pk)}
    assert rls._get_current_context() == ("off", "")
    assert Sucursal.objects.count() == 0

    # 3. SignupView público crea Empresa + usuario + Suscripcion TRIAL bajo contexto aislado.
    anon_client = APIClient()
    signup_resp = anon_client.post(
        "/api/saas/signup/",
        {
            "empresa_nombre_legal": "Nueva Tenant RLS C.A.",
            "empresa_identificador_fiscal": "J-55555555-5",
            "username": "admin_nuevo_rls",
            "email": "admin_nuevo_rls@tenant.test",
            "password": "SignupRlsPass#2026!",
            "plan_nivel": "STARTER",
        },
        format="json",
    )
    assert signup_resp.status_code == 201
    assert rls._get_current_context() == ("off", "")
    assert Suscripcion.objects.count() == 0
    with rls.rls_bypass():
        assert Suscripcion.objects.filter(id_empresa=signup_resp.json()["empresa_id"]).exists()


def test_inventario_estatico_tasks_y_management_commands():
    """Todo tasks.py y management/command debe declarar contexto RLS o documentar Nota RLS no-BD."""
    apps_dir = Path(__file__).resolve().parents[2] / "apps"
    rls_markers = ("rls_tenant_context", "rls_bypass", "Nota RLS:")

    task_files = sorted(apps_dir.glob("*/tasks.py"))
    assert task_files
    faltantes_tasks = [
        str(p.relative_to(apps_dir))
        for p in task_files
        if not any(m in p.read_text(encoding="utf-8") for m in rls_markers)
    ]
    assert faltantes_tasks == [], f"tasks.py sin contexto RLS explícito: {faltantes_tasks}"

    importador_base = apps_dir / "migracion_datos" / "management" / "commands" / "_importador_base.py"
    assert "rls_tenant_context" in importador_base.read_text(encoding="utf-8")

    cmd_files = [
        p
        for p in sorted(apps_dir.glob("*/management/commands/*.py"))
        if p.name != "__init__.py" and not p.name.startswith("_")
    ]
    assert cmd_files
    faltantes_cmds = []
    for p in cmd_files:
        text = p.read_text(encoding="utf-8")
        if any(m in text for m in rls_markers):
            continue
        if "ImportadorBaseCommand" in text:
            continue
        faltantes_cmds.append(str(p.relative_to(apps_dir)))
    assert faltantes_cmds == [], f"management commands sin contexto RLS explícito: {faltantes_cmds}"


@override_settings(RLS_ENABLED=True)
def test_memoizacion_get_empresas_visible_e_invalidacion_signals(empresa_a, empresa_b, user_a):
    """get_empresas_visible memoiza por ciclo de request y los signals invalidan al cambiar membresía."""
    rls.apply_system_default()

    # 1. Cache activo evita re-consultar usuarios_empresas dentro de un mismo ciclo.
    token = iniciar_cache_empresas_visible()
    try:
        with rls.rls_bypass():
            with CaptureQueriesContext(connection) as q_miss:
                ids_1 = set(get_empresas_visible(user_a).values_list("id_empresa", flat=True))
            assert any("usuarios_empresas" in q["sql"] for q in q_miss)
            assert ids_1 == {empresa_a.pk}

            with CaptureQueriesContext(connection) as q_hit:
                ids_2 = set(get_empresas_visible(user_a).values_list("id_empresa", flat=True))
            assert not any("usuarios_empresas" in q["sql"] for q in q_hit)
            assert ids_2 == {empresa_a.pk}

            # Cambio de membresía debe invalidar el cache inmediatamente vía signal m2m_changed.
            user_a.empresas.add(empresa_b)
            ids_3 = set(get_empresas_visible(user_a).values_list("id_empresa", flat=True))
            assert ids_3 == {empresa_a.pk, empresa_b.pk}
    finally:
        limpiar_cache_empresas_visible(token)

    # 2. Fuera del ciclo de request no hay cache obsoleto (remoción visible al instante).
    with rls.rls_bypass():
        user_a.empresas.remove(empresa_b)
        assert set(get_empresas_visible(user_a).values_list("id_empresa", flat=True)) == {empresa_a.pk}

    # 3. Dentro de RLSContextMiddleware, _apply_context precalienta el cache del request.
    seen_queries = []

    def get_response(request):
        with CaptureQueriesContext(connection) as q_view:
            ids = set(get_empresas_visible(user_a).values_list("id_empresa", flat=True))
        seen_queries.extend(q["sql"] for q in q_view)
        assert ids == {empresa_a.pk}
        return HttpResponse("ok")

    mw = RLSContextMiddleware(get_response)
    req = RequestFactory().get("/api/core/sucursales/")
    req.user = user_a
    resp = mw(req)
    assert resp.status_code == 200
    assert not any("usuarios_empresas" in sql for sql in seen_queries)
    assert rls._get_current_context() == ("off", "")


@override_settings(RLS_ENABLED=True)
def test_activaciones_notificaciones_eventos_y_comandos_extra(empresa_a, empresa_b, user_b):
    """Cubre rutas adicionales de RLS en tasks (activaciones, notificaciones), consumer, signals y comandos."""
    from celery.exceptions import Retry

    from apps.activaciones.tasks import sincronizar_google_task
    from apps.cxc_lubrikca.services.sync import SyncError
    from apps.eventos import consumers
    from apps.notificaciones.tasks import enviar_notificacion_email

    # 1. activaciones.sincronizar_google con UUID real resuelve empresa_id via rls_bypass y aisla el tenant
    ahora = timezone.now()
    with rls.rls_bypass():
        cal = CalendarioActivacion.objects.create(id_empresa=empresa_a, nombre="Cal A", es_predeterminado=True)
        ev = EventoActivacion.objects.create(
            id_empresa=empresa_a,
            calendario=cal,
            cliente_nombre="Cliente EV",
            ubicacion="Sede",
            inicio=ahora + timedelta(hours=1),
            fin=ahora + timedelta(hours=2),
        )
    rls.apply_system_default()
    seen_ev_ctx = []
    with patch("apps.activaciones.services.sincronizar_google") as mock_sync_google:
        mock_sync_google.side_effect = lambda _eid: seen_ev_ctx.append(rls._get_current_context())
        sincronizar_google_task(str(ev.pk))
    assert seen_ev_ctx == [("off", str(empresa_a.pk))]
    assert rls._get_current_context() == ("off", "")

    # 2. notificaciones.enviar_notificacion_email guarda estado FALLIDO si falla envio con id_log
    with rls.rls_bypass():
        tpl = PlantillaNotificacion.objects.create(
            codigo_plantilla="TPL_RLS",
            asunto="Hola {{ nombre }}",
            cuerpo_html="<p>{{ nombre }}</p>",
            canal=CanalNotificacion.EMAIL,
        )
        log = LogNotificacion.objects.create(
            id_plantilla=tpl,
            destinatario="dest@test.com",
            canal=CanalNotificacion.EMAIL,
        )
    rls.apply_system_default()
    with patch("apps.notificaciones.tasks.send_mail", side_effect=RuntimeError("SMTP caído")):
        with pytest.raises((Retry, RuntimeError)):
            enviar_notificacion_email.apply(args=[str(tpl.pk), "dest@test.com", {"nombre": "Ana"}, str(log.pk)]).get()
    with rls.rls_bypass():
        log.refresh_from_db()
        assert log.estado == "FALLIDO"

    # 3. eventos.consumers._process_message aplica rls_tenant_context por envelope
    seen_evt_ctx = []

    def _tmp_handler(envelope):
        seen_evt_ctx.append((envelope.get("empresa_id"), rls._get_current_context()))

    rls.apply_system_default()
    consumers._handlers.setdefault("rls.test.evento", []).append(_tmp_handler)
    try:
        payload = json.dumps({"event_type": "rls.test.evento", "empresa_id": str(empresa_a.pk)}).encode("utf-8")
        consumers._process_message(payload)
    finally:
        consumers._handlers["rls.test.evento"].remove(_tmp_handler)
    assert seen_evt_ctx == [(str(empresa_a.pk), ("off", str(empresa_a.pk)))]
    assert rls._get_current_context() == ("off", "")

    # 4. sincronizar_cxc_lubrikca command bajo rls_tenant_context
    rls.apply_system_default()
    with patch(
        "apps.cxc_lubrikca.services.sync.sincronizar_empresa",
        return_value={"pedidos": 1, "lineas": 2, "pagos": 0, "precios": 0, "facturas": 1},
    ):
        call_command("sincronizar_cxc_lubrikca", "--empresa", str(empresa_a.pk))
    with patch("apps.cxc_lubrikca.services.sync.sincronizar_empresa", side_effect=SyncError("sin conector")):
        with pytest.raises(CommandError):
            call_command("sincronizar_cxc_lubrikca", "--empresa", str(empresa_a.pk))
    assert rls._get_current_context() == ("off", "")

    # 5. migrar_contactos real + validaciones y crear_usuario_bot rechazo cross-empresa
    with rls.rls_bypass():
        cli_mig = Cliente.objects.create(id_empresa=empresa_a, razon_social="Cli Mover", rif="J-88888888-8")
    rls.apply_system_default()
    call_command("migrar_contactos", "--origen", str(empresa_a.pk), "--destino", str(empresa_b.pk))
    with rls.rls_bypass():
        cli_mig.refresh_from_db()
        assert cli_mig.id_empresa_id == empresa_b.pk
    with pytest.raises(CommandError):
        call_command("migrar_contactos", "--fusionar-duplicados")
    with pytest.raises(CommandError):
        call_command(
            "crear_usuario_bot",
            "--empresa-rif",
            empresa_a.identificador_fiscal,
            "--username",
            user_b.username,
        )

    # 6. _restore_context omite SQL si needs_rollback=True y signals ignoran vendor no-postgresql
    with patch.object(connection, "needs_rollback", True):
        rls._restore_context("off", "")
    with patch.object(connection, "vendor", "sqlite"):
        enable_rls_bypass_for_migrate(sender=None)
        restore_rls_default_after_migrate(sender=None)
    on_usuario_empresa_changed_invalidar_cache(sender=None)
    assert rls._get_current_context() == ("off", "")
