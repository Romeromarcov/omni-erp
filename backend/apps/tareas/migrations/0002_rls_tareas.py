"""RLS de las 11 tablas tenant de ``apps.tareas`` (política ``omni_rls_tenant`` + FORCE; ver ``apps/core/rls.py``)."""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = [
    ("tareas_area_operativa", "id_empresa_id", False),
    ("tareas_miembro_area", "id_empresa_id", False),
    ("tareas_proyecto", "id_empresa_id", False),
    ("tareas_seccion_proyecto", "id_empresa_id", False),
    ("tareas_plantilla_recurrente", "id_empresa_id", False),
    ("tareas_minuta_reunion", "id_empresa_id", False),
    ("tareas_tarea", "id_empresa_id", False),
    ("tareas_dependencia", "id_empresa_id", False),
    ("tareas_comentario", "id_empresa_id", False),
    ("tareas_configuracion_seguimiento", "id_empresa_id", False),
    ("tareas_registro_alerta", "id_empresa_id", False),
]


def _enable() -> str:
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable() -> str:
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):
    dependencies = [("tareas", "0001_inicial")]

    operations = [migrations.RunSQL(sql=_enable(), reverse_sql=_disable())]
