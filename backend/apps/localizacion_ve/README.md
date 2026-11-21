# Paquete `localizacion_ve`

Paquete de localización de Venezuela bajo la arquitectura en dos capas ([ADR-007](../../../docs/decisions/ADR-007-arquitectura-localizacion-dos-capas.md)). Implementa los **6 puertos** definidos en `apps/localizacion/ports.py` siguiendo el patrón *strangler fig* (delegando de forma perezosa en `apps/fiscal`, `apps/nomina` y `apps/finanzas`) y provee utilidades puras venezolanas.

**Paquete de localización — se descubre vía `apps.localizacion.registry` (`"VE"` / alias `"VEN"`).**
La superficie HTTP/MCP vive en el módulo agnóstico `apps/localizacion`:
- `GET /api/localizacion/estado/` (opcional `?empresa_id=<uuid>`)
- Tool MCP `localizacion_estado_empresa` (scope `localizacion:read`)

## Adaptadores (6/6 puertos ADR-007)

| Puerto (`apps.localizacion.ports`) | Adaptador VE (`adapters.py`) | Capa | Delegación / Responsabilidad |
|---|---|---|---|
| `MotorImpuestos` | `MotorImpuestosVE` | Legal | Delega en `apps.fiscal.services.calcular_impuestos` (IVA + IGTF). |
| `GeneradorDocumentoLegal` | `GeneradorDocumentoLegalVE` | Legal | Verifica pertenencia multi-tenant, valida/normaliza RIFs y extrae metadatos fiscales SENIAT (`requiere_pie_legal_seniat=True`). |
| `CalculadoraNomina` | `CalculadoraNominaVE` | Legal | Delega en `apps.nomina.services.calcular_nomina_empleado` (LOTTT). |
| `LibroLegal` | `LibroLegalVE` | Legal | Delega en `apps.fiscal.libros_seniat` (`ventas` / `compras`, TXT y PDF). |
| `ProveedorTasas` | `ProveedorTasasVE` | Mercado | Consulta tasa vigente en BD/caché vía `apps.finanzas.services.obtener_tasa_cambio` (`Decimal \| None`, sin I/O HTTP). |
| `MetodosPagoLocales` | `MetodosPagoLocalesVE` | Mercado | Lista `finanzas.MetodoPago` visibles activos con metadatos VE (`aplica_igtf`, `categoria_ve`, `es_divisa`). |

## Utilidades puras

| Archivo | Funciones principales |
|---|---|
| `validators.py` | `validar_rif`, `verificar_digito_rif`, `normalizar_rif`, `validar_cedula`, `normalizar_cedula`, `validar_numero_control`, `siguiente_numero_control`, `validar_email`. |
| `formato.py` | `formatear_bolivares`, `formatear_usd`, `formatear_monto`, `monto_a_letras` (número a letras). |
| `calendario.py` | `feriados_del_año`, `es_feriado`, `es_dia_habil`, `dias_habiles`, `siguiente_dia_habil` (incluye cálculo de Semana Santa). |
| `zona_horaria.py` | `ahora_vet`, `a_vet`, `a_utc`, `formatear_fecha_ve`, `inicio_dia_vet`, `fin_dia_vet` (zona horaria de Venezuela). |

> Filosofía: "Venezuela-first, no Venezuela-hardcoded". Toda regla específica de Venezuela vive aquí o detrás de los puertos de `apps/localizacion`, nunca hardcodeada en el núcleo (ver [`docs/PLAN_MAESTRO_UNICO.md`](../../../docs/PLAN_MAESTRO_UNICO.md) §3.7).
