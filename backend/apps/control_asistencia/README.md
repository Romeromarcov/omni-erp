# App `control_asistencia`

Control de asistencia: horarios de trabajo, asignación de horarios a empleados, registros de marcaje y resúmenes diarios de asistencia. Alimenta el cálculo de nómina.

**Prefijo API:** `/api/control-asistencia/`

## Modelos

| Modelo | Descripción |
|---|---|
| `HorarioTrabajo` | Definición de un horario. |
| `AsignacionHorario` | Asignación de horario a un empleado. |
| `RegistroAsistencia` | Marcaje de entrada/salida. |
| `ResumenAsistenciaDiario` | Resumen diario consolidado por empleado. |

## Endpoints

Recursos REST (CRUD vía router): `horarios-trabajo/`, `asignaciones-horario/`, `registros-asistencia/`, `resumenes-asistencia-diario/`.

Acciones personalizadas:

| Ruta | Descripción |
|---|---|
| `GET horarios-trabajo/activos/` · `POST {id}/desactivar/` | Gestión de horarios. |
| `GET asignaciones-horario/activas/` · `por_empleado/` · `POST {id}/finalizar/` | Gestión de asignaciones. |
| `POST registros-asistencia/marcar_asistencia/` | Marcar asistencia. |
| `GET registros-asistencia/por_empleado_fecha/` · `hoy/` | Consultas de marcaje. |
| `POST resumenes-asistencia-diario/generar_resumen_diario/` · `{id}/aprobar/` | Resúmenes. |
| `GET resumenes-asistencia-diario/pendientes_revision/` · `reporte_mensual/` | Reportes. |
