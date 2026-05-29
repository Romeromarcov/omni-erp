# App `rrhh`

Recursos humanos: maestro de empleados, cargos, beneficios (y su asignación a empleados) y licencias/permisos. Base de personas para nómina y control de asistencia.

**Prefijo API:** `/api/rrhh/`

## Modelos

| Modelo | Descripción |
|---|---|
| `Empleado` | Maestro de empleado. |
| `Cargo` | Cargo/puesto. |
| `Beneficio` / `BeneficioEmpleado` | Beneficios y su asignación. |
| `TipoLicencia` / `LicenciaEmpleado` | Tipos de licencia y licencias otorgadas. |

## Endpoints

Recursos REST (CRUD vía router): `empleados/`, `cargos/`, `beneficios/`, `beneficios-empleado/`, `tipos-licencia/`, `licencias-empleado/`.
