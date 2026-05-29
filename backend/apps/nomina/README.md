# App `nomina`

Nómina venezolana (LOTTT): períodos, conceptos (devengados/deducciones), procesos de nómina, recibos por empleado y nómina extrasalarial. Calcula y procesa la nómina con la fiscalidad y parafiscalidad venezolanas.

**Prefijo API:** `/api/nomina/`

## Modelos

| Modelo | Descripción |
|---|---|
| `PeriodoNomina` | Período de nómina. |
| `ConceptoNomina` | Concepto (devengado o deducción). |
| `ProcesoNomina` | Proceso de cálculo de nómina. |
| `Nomina` / `DetalleNomina` | Recibo de nómina por empleado y su detalle. |
| `ProcesoNominaExtrasalarial` / `NominaExtrasalarial` | Nómina extrasalarial (beneficios no salariales). |

## Endpoints

Recursos REST (CRUD vía router): `periodos-nomina/`, `conceptos-nomina/`, `procesos-nomina/`, `nominas/`, `detalles-nomina/`, `procesos-nomina-extrasalarial/`, `nominas-extrasalarial/`.

Acciones personalizadas:

| Ruta | Descripción |
|---|---|
| `GET periodos-nomina/activos/` · `abiertos/` · `POST {id}/cerrar/` | Gestión de períodos. |
| `GET conceptos-nomina/por-tipo/` · `devengados/` · `deducciones/` | Conceptos por tipo. |
| `POST procesos-nomina/{id}/procesar/` · `aprobar/` · `GET resumen/` | Ejecución del proceso. |
| `POST nominas/{id}/aprobar/` · `marcar_pagada/` | Estado del recibo. |
