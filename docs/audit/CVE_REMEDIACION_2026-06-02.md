# Remediación de CVEs de dependencias — 2026-06-02

Fuente: `pip-audit -r backend/requirements.txt` (job de CI `security-scan` + plan
"cero dudas" Fase 1). Frontend: `npm audit` (job CI).

## ✅ Remediado en este PR (bumps patch/minor, bajo riesgo, validados con la suite)

| Paquete | De → A | CVEs cerrados |
|---|---|---|
| Django | 5.2.4 → **5.2.14** | PYSEC-2026-45/47/48/49/51/52/53/54/55, PYSEC-2025-104/105, CVE-2025-59682, CVE-2026-25673/25674 (~14) |
| djangorestframework-simplejwt | 5.5.0 → **5.5.1** | CVE-2024-22513 |
| cryptography | 44.0.0 → **44.0.1** | CVE-2024-12797 |
| python-dotenv | 1.1.1 → **1.2.2** | CVE-2026-28684 |
| sqlparse | 0.5.3 → **0.5.4** | GHSA-27jp-wm6q-gp25 |
| PyJWT | 2.9.0 → **2.13.0** | PYSEC-2025-183, PYSEC-2026-120/175/176/177/178/179 |

Validación: `manage.py check` 0 issues · `makemigrations --check` sin drift ·
suite backend completa verde. PyJWT 2.13.0 validado con 64 tests de auth/JWT/
capability (el bump fue posible porque simplejwt 5.5.1 ya no fija `pyjwt<2.10`).

## ⏳ Pendiente — requieren PR dedicado con pruebas de compatibilidad (CTF)

Estos son bumps **major** o con conflictos de constraints; cambiarlos a ciegas
puede romper APIs. Se rastrean como compromiso técnico fechado:

| Paquete | Actual → fix | CVE | Riesgo del bump |
|---|---|---|---|
| mcp | 1.12.4 → 1.23.0 | CVE-2025-66416 | Major; puede cambiar la API de FastMCP usada en `apps/core/mcp_server.py`. |
| lxml | 5.4.0 → 6.1.0 | PYSEC-2026-87 | Major; usado por scraping/PDF; probar parsing. |
| cryptography | 44.0.1 → 46.x | PYSEC-2026-35, CVE-2026-26007 | Major; revisar `EncryptedJSONField`/Fernet. |
| pytest | 8.2.2 → 9.0.3 | CVE-2025-71176 | Solo dev/CI; major, puede requerir ajustes de fixtures. |

**DoD del seguimiento:** cada bump en su propia rama, con la suite completa verde
y, para mcp/lxml/cryptography, un test específico del camino afectado.

## Política en CI
- `pip-audit` y `npm audit` corren en el job `security-scan` (hoy no-bloqueantes
  para no tumbar el pipeline ante un CVE recién publicado).
- **Criterio "cero dudas":** escalar a **bloqueante en severidad High/Critical**
  una vez cerrados los pendientes de la tabla anterior.
