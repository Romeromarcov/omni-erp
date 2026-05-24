# Compromisos Técnicos Fechados (CTF)

Los CTF documentan deuda técnica conocida que fue deliberadamente diferida
con una fecha límite y un responsable claro (R-PROC-6).

Un CTF **no es un TODO**. Es un contrato: si la fecha de vencimiento pasa
sin que la condición de cierre se cumpla, el item bloquea el siguiente hito.

## CTFs activos

| ID       | Título                                          | Vence      | Owner              | Estado   |
|----------|-------------------------------------------------|------------|--------------------|----------|
| CTF-001  | Asientos contables automáticos (R-CODE-11)      | 2026-08-01 | equipo-finanzas    | CERRADO  |
| CTF-002  | DSL runtime completo (entidades/estados/reglas) | 2026-08-01 | equipo-plataforma  | CERRADO  |
| CTF-003  | Shadow mode agents — eval suite en CI           | 2026-09-01 | equipo-agentes     | CERRADO  |
| CTF-004  | Multi-tenancy completo en manufactura           | 2026-07-01 | equipo-manufactura | CERRADO  |

## Proceso

1. Abrir CTF cuando se acepta conscientemente una deuda técnica en un PR.
2. El PR que introduce la deuda debe incluir el archivo CTF correspondiente.
3. Al cerrar la condición, actualizar `Estado` a `CERRADO` y añadir la fecha real.
4. Los CTFs vencidos aparecen en el reporte semanal de calidad y bloquean
   la siguiente release si no se resuelven.
