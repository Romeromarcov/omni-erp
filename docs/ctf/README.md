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
| CTF-005  | Whitelist explícita de campos (`fields="__all__"`) | 2026-09-01 | equipo-backend     | ABIERTO  |
| CTF-006  | `eslint-plugin-security` en el frontend          | 2026-08-01 | equipo-frontend    | CERRADO  |
| CTF-007  | `picomatch ≤2.3.1` (high) vía typescript-eslint  | 2026-09-01 | equipo-frontend    | CERRADO  |
| CTF-008  | Offline-first real (ADR-001)                     | 2026-10-01 | equipo-frontend        | ABIERTO  |
| CTF-009  | Drift `es_superusuario_innova` vs `_omni`        | 2026-07-15 | equipo-frontend        | CERRADO  |
| CTF-010  | Firma de código + CI de empaquetado de apps      | 2026-09-01 | equipo-frontend/devops | ABIERTO  |
| CTF-011  | Push de cobranza a Odoo (outbound, Plan D D3)    | 2026-09-01 | equipo-integraciones   | ABIERTO  |
| CTF-012  | Rol de BD dedicado no-dueño (activación de RLS)  | 2026-08-01 | equipo-backend/devops  | EN CURSO |
| CTF-013  | TEST-5 cambio-divisa y nómina (features bloqueadas) | 2026-08-15 | equipo-backend         | CERRADO  |
| CTF-014  | Migrar `tests_api/` a estructura por capas `tests/` | 2026-09-30 | equipo-backend         | ABIERTO  |
| CTF-015  | `transferir-entre-cajas` roto + validar `cantidad > 0` en OF | 2026-06-19 | agente (bugs lote 3)   | CERRADO  |

## Proceso

1. Abrir CTF cuando se acepta conscientemente una deuda técnica en un PR.
2. El PR que introduce la deuda debe incluir el archivo CTF correspondiente.
3. Al cerrar la condición, actualizar `Estado` a `CERRADO` y añadir la fecha real.
4. Los CTFs vencidos aparecen en el reporte semanal de calidad y bloquean
   la siguiente release si no se resuelven.
