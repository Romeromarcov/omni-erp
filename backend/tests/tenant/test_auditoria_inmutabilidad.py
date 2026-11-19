"""
P1-5 (R13): Tests de inmutabilidad (append-only) para Auditoría en PostgreSQL, ORM, API y Django Admin.

Verifica:
1. INSERT funciona normalmente en ``LogAuditoria`` y ``RegistroAuditoria``.
2. UPDATE (``.save()``, ``QuerySet.update()``, SQL crudo) falla en PostgreSQL con ERRCODE 42501 en ambas tablas.
3. DELETE (``.delete()``, ``QuerySet.delete()``, SQL crudo) falla en PostgreSQL con ERRCODE 42501 en ambas tablas.
4. Triggers y funciones dedicadas existen en PostgreSQL y las migraciones ``0005`` / ``0025`` son reversibles.
5. API ``/api/auditoria/logs-auditoria/`` es ReadOnlyModelViewSet: permite GET solo del tenant propio,
   retorna 404 para PK ajeno y 405 para POST/PUT/PATCH/DELETE (incluso para superusuario Omni).
6. ``LogAuditoriaAdmin`` y ``RegistroAuditoriaAdmin`` prohíben add/change/delete y exponen todos los campos
   como ``readonly_fields``.
"""

from django.contrib import admin
from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory
import pytest
from rest_framework.test import APIClient

from apps.auditoria.models import LogAuditoria
from apps.core.models import RegistroAuditoria, Usuarios

pytestmark = pytest.mark.tenant

URL_LOGS = "/api/auditoria/logs-auditoria/"


def _assert_trigger_42501(exc_info):
    cause = getattr(exc_info.value, "__cause__", None)
    pgcode = getattr(cause, "pgcode", None)
    assert pgcode == "42501" or "inmutable" in str(exc_info.value).lower()


@pytest.fixture
def log_a(db, empresa_a, user_a):
    return LogAuditoria.objects.create(
        id_empresa=empresa_a,
        id_usuario=user_a,
        modulo="VENTAS",
        tipo_accion="CREACION",
        nombre_entidad_afectada="Pedido",
        descripcion_accion="Evento inicial A",
        cambios_json={"estado": "PENDIENTE"},
    )


@pytest.fixture
def log_b(db, empresa_b, user_b):
    return LogAuditoria.objects.create(
        id_empresa=empresa_b,
        id_usuario=user_b,
        modulo="COMPRAS",
        tipo_accion="CREACION",
        nombre_entidad_afectada="OrdenCompra",
        descripcion_accion="Evento inicial B",
        cambios_json={"estado": "BORRADOR"},
    )


@pytest.fixture
def registro_a(db, empresa_a, user_a):
    return RegistroAuditoria.objects.create(
        id_empresa=empresa_a,
        id_usuario=user_a,
        tipo_evento="LOGIN_EXITOSO",
        modulo_afectado="core",
        nombre_modelo_afectado="Usuarios",
        id_registro_afectado=str(user_a.pk),
        descripcion_accion="Inicio de sesión válido",
        cambios_json={"ip": "127.0.0.1"},
        resultado_evento="EXITOSO",
    )


@pytest.mark.django_db
class TestInmutabilidadPostgreSQL:
    """Inmutabilidad a nivel base de datos (triggers PostgreSQL) y ORM Django."""

    def test_insert_funciona_en_ambas_tablas(self, log_a, registro_a):
        assert LogAuditoria.objects.filter(pk=log_a.pk).exists()
        assert RegistroAuditoria.objects.filter(pk=registro_a.pk).exists()

    def test_triggers_y_funciones_registrados_en_postgres(self, db):
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT t.tgname, c.relname
                FROM pg_trigger t
                JOIN pg_class c ON c.oid = t.tgrelid
                WHERE NOT t.tgisinternal
                  AND t.tgname IN (
                      'trg_prevent_logauditoria_mutation',
                      'trg_prevent_registro_auditoria_mutation'
                  )
                ORDER BY t.tgname
                """
            )
            filas = cur.fetchall()
        assert filas == [
            ("trg_prevent_logauditoria_mutation", "auditoria_logauditoria"),
            ("trg_prevent_registro_auditoria_mutation", "registro_auditoria"),
        ]

    def test_log_auditoria_bloquea_update_save_queryset_y_sql(self, log_a):
        # 1. ORM .save()
        log_a.descripcion_accion = "Alterado via save"
        with pytest.raises(DatabaseError) as exc_save, transaction.atomic():
            log_a.save()
        _assert_trigger_42501(exc_save)

        # 2. ORM QuerySet.update()
        with pytest.raises(DatabaseError) as exc_qs, transaction.atomic():
            LogAuditoria.objects.filter(pk=log_a.pk).update(descripcion_accion="Alterado via update")
        _assert_trigger_42501(exc_qs)

        # 3. SQL crudo
        with pytest.raises(DatabaseError) as exc_sql, transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "UPDATE auditoria_logauditoria SET descripcion_accion = %s WHERE id_log_auditoria = %s",
                    ["Alterado via SQL", str(log_a.pk)],
                )
        _assert_trigger_42501(exc_sql)

        log_a.refresh_from_db()
        assert log_a.descripcion_accion == "Evento inicial A"

    def test_log_auditoria_bloquea_delete_instancia_queryset_y_sql(self, log_a):
        # 1. ORM instancia.delete()
        with pytest.raises(DatabaseError) as exc_del, transaction.atomic():
            log_a.delete()
        _assert_trigger_42501(exc_del)

        # 2. ORM QuerySet.delete()
        with pytest.raises(DatabaseError) as exc_qs, transaction.atomic():
            LogAuditoria.objects.filter(pk=log_a.pk).delete()
        _assert_trigger_42501(exc_qs)

        # 3. SQL crudo
        with pytest.raises(DatabaseError) as exc_sql, transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "DELETE FROM auditoria_logauditoria WHERE id_log_auditoria = %s",
                    [str(log_a.pk)],
                )
        _assert_trigger_42501(exc_sql)

        assert LogAuditoria.objects.filter(pk=log_a.pk).exists()

    def test_registro_auditoria_bloquea_update_save_queryset_y_sql(self, registro_a):
        # 1. ORM .save()
        registro_a.descripcion_accion = "Alterado via save"
        with pytest.raises(DatabaseError) as exc_save, transaction.atomic():
            registro_a.save()
        _assert_trigger_42501(exc_save)

        # 2. ORM QuerySet.update()
        with pytest.raises(DatabaseError) as exc_qs, transaction.atomic():
            RegistroAuditoria.objects.filter(pk=registro_a.pk).update(descripcion_accion="Alterado via update")
        _assert_trigger_42501(exc_qs)

        # 3. SQL crudo
        with pytest.raises(DatabaseError) as exc_sql, transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "UPDATE registro_auditoria SET descripcion_accion = %s WHERE id_log_auditoria = %s",
                    ["Alterado via SQL", str(registro_a.pk)],
                )
        _assert_trigger_42501(exc_sql)

        registro_a.refresh_from_db()
        assert registro_a.descripcion_accion == "Inicio de sesión válido"

    def test_registro_auditoria_bloquea_delete_instancia_queryset_y_sql(self, registro_a):
        # 1. ORM instancia.delete()
        with pytest.raises(DatabaseError) as exc_del, transaction.atomic():
            registro_a.delete()
        _assert_trigger_42501(exc_del)

        # 2. ORM QuerySet.delete()
        with pytest.raises(DatabaseError) as exc_qs, transaction.atomic():
            RegistroAuditoria.objects.filter(pk=registro_a.pk).delete()
        _assert_trigger_42501(exc_qs)

        # 3. SQL crudo
        with pytest.raises(DatabaseError) as exc_sql, transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "DELETE FROM registro_auditoria WHERE id_log_auditoria = %s",
                    [str(registro_a.pk)],
                )
        _assert_trigger_42501(exc_sql)

        assert RegistroAuditoria.objects.filter(pk=registro_a.pk).exists()


@pytest.mark.django_db
class TestLogAuditoriaAPIReadOnly:
    """API /api/auditoria/logs-auditoria/ solo lectura y aislada por empresa."""

    def test_anonimo_401(self, api_client):
        assert api_client.get(URL_LOGS).status_code == 401

    def test_list_y_retrieve_solo_empresa_propia(self, client_a, log_a, log_b):
        resp = client_a.get(URL_LOGS)
        assert resp.status_code == 200
        resultados = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
        ids = {str(r["id_log_auditoria"]) for r in resultados}
        assert str(log_a.pk) in ids
        assert str(log_b.pk) not in ids

        assert client_a.get(f"{URL_LOGS}{log_a.pk}/").status_code == 200
        assert client_a.get(f"{URL_LOGS}{log_b.pk}/").status_code == 404

    def test_metodos_escritura_retornan_405_incluso_para_superusuario(self, db, client_a, empresa_a, log_a):
        superuser = Usuarios.objects.create_user(
            username="super_auditoria_test",
            password="PasswordSegura123!",
            email="super_aud@test.local",
            es_superusuario_omni=True,
            is_superuser=True,
            is_staff=True,
        )
        client_super = APIClient()
        client_super.force_authenticate(user=superuser)

        payload = {
            "id_empresa": str(empresa_a.pk),
            "modulo": "CORE",
            "tipo_accion": "FORJADO",
            "descripcion_accion": "No permitido",
        }
        for client in (client_a, client_super):
            assert client.post(URL_LOGS, payload, format="json").status_code == 405
            assert client.put(f"{URL_LOGS}{log_a.pk}/", {"descripcion_accion": "x"}, format="json").status_code == 405
            assert (
                client.patch(f"{URL_LOGS}{log_a.pk}/", {"descripcion_accion": "x"}, format="json").status_code == 405
            )
            assert client.delete(f"{URL_LOGS}{log_a.pk}/").status_code == 405

        log_a.refresh_from_db()
        assert log_a.descripcion_accion == "Evento inicial A"


@pytest.mark.django_db
class TestAdminAuditoriaReadOnly:
    """Django Admin de LogAuditoria y RegistroAuditoria es estrictamente append/read-only."""

    def test_admins_prohiben_add_change_delete_y_marcan_todos_los_campos_readonly(self):
        superuser = Usuarios.objects.create_user(
            username="admin_auditoria_test",
            password="PasswordSegura123!",
            email="admin_aud@test.local",
            es_superusuario_omni=True,
            is_superuser=True,
            is_staff=True,
        )
        request = RequestFactory().get("/admin/")
        request.user = superuser

        for model_cls in (LogAuditoria, RegistroAuditoria):
            model_admin = admin.site._registry[model_cls]
            assert model_admin.has_add_permission(request) is False
            assert model_admin.has_change_permission(request) is False
            assert model_admin.has_delete_permission(request) is False
            concrete_names = {f.name for f in model_cls._meta.concrete_fields}
            assert concrete_names <= set(model_admin.readonly_fields)


@pytest.mark.django_db
class TestMigracionesInmutabilidadReversibles:
    """Verifica reversibilidad completa (R-PROC-5) de 0005 y 0025."""

    def test_reverse_y_reaplicacion_de_migraciones_de_inmutabilidad(self):
        def _existe_trigger(nombre):
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname = %s AND NOT tgisinternal)",
                    [nombre],
                )
                return cur.fetchone()[0]

        assert _existe_trigger("trg_prevent_logauditoria_mutation") is True
        assert _existe_trigger("trg_prevent_registro_auditoria_mutation") is True

        try:
            executor = MigrationExecutor(connection)
            executor.migrate([("auditoria", "0004_rls_lote3_auditoria")])
            assert _existe_trigger("trg_prevent_logauditoria_mutation") is False

            executor = MigrationExecutor(connection)
            executor.migrate([("core", "0024_contacto_gps")])
            assert _existe_trigger("trg_prevent_registro_auditoria_mutation") is False
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(
                [
                    ("auditoria", "0005_inmutabilidad_logauditoria"),
                    ("core", "0025_inmutabilidad_registro_auditoria"),
                ]
            )

        assert _existe_trigger("trg_prevent_logauditoria_mutation") is True
        assert _existe_trigger("trg_prevent_registro_auditoria_mutation") is True
