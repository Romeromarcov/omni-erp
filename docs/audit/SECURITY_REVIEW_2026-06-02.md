# Security Review — Omni ERP — 2026-06-02 (consolidado A2)

> **DoD A2.** Reporte consolidado de la auditoría de seguridad adversarial, con cada
> hallazgo por **severidad + CWE + archivo:línea + estado**, y por cada uno un **fix
> mergeado** o **riesgo aceptado con dueño** (CTF). Fuente extensa: [`docs/AUDITORIA_2026-06-02.md`](../AUDITORIA_2026-06-02.md).
> Estado verificado al **2026-06-03** (auditoría plan cero-dudas).

## Veredicto

**0 hallazgos CRÍTICOS o ALTOS de seguridad abiertos.** Los 2 ALTA de seguridad y los 2 MEDIA
de seguridad de la re-auditoría 2026-06-02 están **resueltos y verificados línea por línea**.
Quedan 2 BAJA de defensa-en-profundidad (aceptados, mitigados). Re-ejecutable: `/security-review`
+ `bandit`/`semgrep` (incl. reglas Omni) + `gitleaks`/`pip-audit`/`trivy` corren en cada PR.

## Hallazgos de seguridad y su estado

| ID | Sev | CWE | Archivo:línea | Hallazgo | Estado (2026-06-03) |
|---|---|---|---|---|---|
| SEC-NEW-4 | ALTA | CWE-269 (gestión de privilegios) | `core/mcp_server.py` | Token de empresa con `scopes=["*"]` podía conceder acceso MCP total al tenant. | ✅ **RESUELTO** — `mcp_server.py:115-121` filtra `*` salvo `comodin_autorizado` (sistema/superusuario); `_require_scope` ya no concede `*` a tokens de empresa. Verificado. |
| SEC-NEW-1 | ALTA | CWE-295 (validación de certificado) | `finanzas/management/commands/update_bcv_exchange.py` | Scraper BCV legacy con `requests.get(verify=False)` + tasa como `float`, fuera del Hub (MITM sobre tasa fiscal). | ✅ **RESUELTO** — el command fue **eliminado** (lo reemplaza `bcv_scrape.py` vía Integration Hub con verificación TLS). `semgrep omni-no-tls-verify-disabled`: 0 findings. |
| SEC-NEW-2 | MEDIA | CWE-639 (autorización por dato controlable) | `cxc/*`, `integration_hub/*`, `agentes/*` | `request.user.empresa` (= `empresas.first()`) rompía el aislamiento para usuario multi-empresa. | ✅ **RESUELTO** — 0 usos de `user.empresa` singular en el código. El asistente IA migró a empresa de trabajo validada (SEC-1, `agentes/api/chat.py`); cxc usa `get_empresas_visible`. |
| SEC-NEW-5 | MEDIA | CWE-209 (exposición de info por mensaje de error) | `agentes/views.py` | `Response({"detail": str(exc)}, 500)` filtraba el mensaje interno. | ✅ **RESUELTO** — 0 `str(exc)` en respuestas de `agentes/views.py`; el chat usa `logger.exception` + mensaje genérico. |
| SEC-NEW-3 | BAJA | CWE-915 (asignación masiva) | `ventas/serializers.py` (17×), `compras/serializers.py` (12×) | `fields="__all__"`. | 🟡 **ACEPTADO (mitigado).** Inyección de tenant ya bloqueada por `read_only_fields` + `EmpresaInjectMixin`; la whitelist explícita es defensa-en-profundidad. **CTF-005**. |
| SEC-NEW-6 | BAJA | CWE-915 | `core/serializers.py:55` | `EmpresaSerializer` con `fields="__all__"` (modelo sin secretos). | 🟡 **ACEPTADO (mitigado).** Riesgo bajo (sin campos sensibles). **CTF-005**. |

## Cobertura de los 10 puntos A2 (OWASP ASVS adaptado)

| # | Punto | Estado |
|---|---|---|
| 1 | AuthN (JWT: access 15 min, refresh httpOnly rotado + blacklist, rate-limit login) | 🟢 |
| 2 | AuthZ / multi-tenant (R-CODE-1: `get_queryset` por empresa; guard auto-descubierto TEST-1) | 🟢 |
| 3 | Inyección (sin `.raw()/.extra()`; **semgrep `omni-no-raw-sql` bloqueante**) | 🟢 |
| 4 | Secretos y config (`settings_prod` fail-closed; sin secretos en código — `gitleaks`) | 🟢 |
| 5 | SSRF / externo (Integration Hub con TLS; **`omni-no-tls-verify-disabled` bloqueante**) | 🟢 |
| 6 | Carga de archivos (S3/MinIO, validación) | 🟢 |
| 7 | CORS/CSRF/headers (CSP, COOP/CORP en ambos nginx — SEC-2 verificado) | 🟢 (CSP `unsafe-inline` → nonces diferido) |
| 8 | MCP / capability tokens (scope enforcement incl. gate `*` — SEC-NEW-4) | 🟢 |
| 9 | DoS (paginación 20/página; rate limits) | 🟢 |
| 10 | Dependencias (`pip-audit`/`npm audit`/`trivy` en CI; CVEs remediados — `CVE_REMEDIACION_2026-06-02.md`) | 🟢 |

## Fuera de alcance A2 (otras fases)

- **Frontend ALTA** (FE-NEW-1 PDF 401, FE-HIGH-7 `Number()*Number()` monetario, FE-HIGH-6 cargas fuera de TanStack): pertenecen a la **Fase 4 (frontend)**, no a A2. Rastreados en `AUDITORIA_2026-06-02.md` §2.
