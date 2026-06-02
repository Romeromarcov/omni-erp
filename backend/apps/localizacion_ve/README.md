# App `vzla_localizacion`

Paquete de localización de Venezuela (capa activable/desactivable). Provee utilidades puras —validación, formato, calendario y zona horaria— que el núcleo agnóstico consume cuando la localización VE está activa. No define modelos ni endpoints HTTP.

**App de infraestructura/librería — sin router HTTP.**

## Componentes

| Archivo | Funciones principales |
|---|---|
| `validators.py` | `validar_rif`, `verificar_digito_rif`, `normalizar_rif`, `validar_cedula`, `normalizar_cedula`, `validar_numero_control`, `siguiente_numero_control`, `validar_email`. |
| `formato.py` | `formatear_bolivares`, `formatear_usd`, `formatear_monto`, `monto_a_letras` (número a letras). |
| `calendario.py` | `feriados_del_año`, `es_feriado`, `es_dia_habil`, `dias_habiles`, `siguiente_dia_habil` (incluye cálculo de Semana Santa). |
| `zona_horaria.py` | `ahora_vet`, `a_vet`, `a_utc`, `formatear_fecha_ve`, `inicio_dia_vet`, `fin_dia_vet` (zona horaria de Venezuela). |

> Filosofía: "Venezuela-first, no Venezuela-hardcoded". Toda regla específica de Venezuela vive aquí o en `fiscal`, nunca en el núcleo (ver [`docs/PLAN_MAESTRO_UNICO.md`](../../../docs/PLAN_MAESTRO_UNICO.md) §3.7).
