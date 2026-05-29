"""
Migration 0003: Restore real FK to rrhh.Empleado (BUG-05 / TD-03)

Removes the temporary UUID fields (id_empleado_temp, id_licencia_asociada_temp)
and adds proper ForeignKey relations to rrhh.Empleado and rrhh.LicenciaEmpleado.
The FK fields are nullable to avoid data-loss during the transition period.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("control_asistencia", "0002_initial"),
        ("rrhh", "0001_initial"),
    ]

    operations = [
        # ── AsignacionHorario ─────────────────────────────────────────────────
        migrations.RemoveField(
            model_name="asignacionhorario",
            name="id_empleado_temp",
        ),
        migrations.AddField(
            model_name="asignacionhorario",
            name="id_empleado",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="asignaciones_horario",
                to="rrhh.empleado",
            ),
        ),

        # ── RegistroAsistencia ────────────────────────────────────────────────
        migrations.RemoveField(
            model_name="registroasistencia",
            name="id_empleado_temp",
        ),
        migrations.AddField(
            model_name="registroasistencia",
            name="id_empleado",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="registros_asistencia",
                to="rrhh.empleado",
            ),
        ),

        # ── ResumenAsistenciaDiario ───────────────────────────────────────────
        # 1. Remove old unique_together that references id_empleado_temp
        migrations.AlterUniqueTogether(
            name="resumenasistenciadiario",
            unique_together=set(),
        ),
        migrations.RemoveField(
            model_name="resumenasistenciadiario",
            name="id_empleado_temp",
        ),
        migrations.RemoveField(
            model_name="resumenasistenciadiario",
            name="id_licencia_asociada_temp",
        ),
        migrations.AddField(
            model_name="resumenasistenciadiario",
            name="id_empleado",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="resumenes_asistencia",
                to="rrhh.empleado",
            ),
        ),
        migrations.AddField(
            model_name="resumenasistenciadiario",
            name="id_licencia_asociada",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="resumenes_asistencia",
                to="rrhh.licenciaempleado",
            ),
        ),
        # 2. Re-add unique_together with real FK field
        migrations.AlterUniqueTogether(
            name="resumenasistenciadiario",
            unique_together={("id_empleado", "fecha")},
        ),
    ]
