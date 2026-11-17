# Plan 06 — Limpieza y estabilización del proyecto

> Plan de ejecución derivado del trabajo de Omni Connect S1 y del cierre del CI (2026-11-13/14).
> Recoge los problemas que aparecieron al validar esos cambios, con su evidencia, y los ordena en
> fases. Alineado a [`PLAN_MAESTRO_UNICO.md`](../PLAN_MAESTRO_UNICO.md) §2 (R-CODE / R-PROC) y al
> gate de cierre [`DEFINITION_OF_DONE.md`](../DEFINITION_OF_DONE.md).

| Campo        | Valor                                  |
|--------------|----------------------------------------|
| **Estado**   | EN CURSO — Fase 0 cerrada; avances Fase 1/3/4 (Tareas 1.3, 3.5 y 3.6 cerradas) |
| **Fecha**    | 2026-11-14                                |
| **Esfuerzo** | ~3–4 semanas, repartibles en PRs pequeños (R-PROC-2) |
| **Owner**    | equipo-backend / devops (acciones del propietario marcadas con 👤) |

---

## 0. Cómo leer este plan

- **Unidad = PR pequeño y focal.** Cada tarea es un PR a `develop` con el gate completo.
- Los números de la sección 2 salen de búsquedas de texto sobre `origin/develop` y **pueden incluir
  falsos positivos**; la sección 8 da el comando para volver a medirlos.
- Lo que es *inferencia* (no verificado) se marca como tal.

## 1. Decisiones registradas (2026-11-14)

| # | Decisión | Detalle |
|---|----------|---------|
| D1 | **`uuid7()` monótono** — aprobada | RFC 9562 §6.2: contador en `rand_a` dentro del mismo milisegundo. Hoy no lo es y varios desempates por PK (FIFO de inventario, `first()`) dependen del orden temporal. |
| D2 | **Formateador: `ruff`** | `ruff check` + `ruff format` como única herramienta; retirar `black` (hoy está en `requirements.txt` de producción y solo añade avisos de seguridad) e `isort`. El reformateo masivo va en **un PR mecánico aparte**, nunca mezclado con funcionalidad. |
| D3 | **CTF: no se tocan fechas** | Los CTF abiertos se mantienen tal cual para que no se pierdan: **CTF-008, CTF-010, CTF-011** (abiertos) y **CTF-012** (en curso). Algunos tienen la fecha vencida; eso queda visible a propósito. |
| D4 | **Caché de datos: persistir y refrescar al restaurar** | Se conserva la persistencia en IndexedDB (función offline, ADR-001) y se añade `onSuccess` en `PersistQueryClientProvider` que invalida las consultas activas al restaurar: la UI muestra al instante lo guardado y se actualiza en milisegundos. No se baja el `staleTime` global. |
| D5 | **Se empieza por la fase 0** | |

## 2. Hallazgos (con evidencia)

> **Nota de actualización (`2026-11-17`):** los valores mostrados en esta tabla (`H5`, `H12`)
> corresponden a la foto base del `2026-11-14`. Los conteos remedidos sobre código real (`origin/develop @ ff2bdb6`)
> viven en [`docs/tech-debt/INVENTORY.md`](../tech-debt/INVENTORY.md): `38` `Response({...str(e|exc|err)...})`
> en 15 archivos, `201` `# noqa` (51 archivos de `apps/`+`config/`), `40` `eslint-disable` en `.ts`/`.tsx`
> (`38` en producción + `2` en tests) y `0` `TODO`/`FIXME` reales en código de `apps/`/`config/`/`src/`.

| # | Hallazgo | Evidencia | Certeza |
|---|----------|-----------|---------|
| H1 | `ci-runner` no se registra: 404 al registrarse | `infra/ci-runner/Dockerfile` fija `RUNNER_VERSION=2.321.0`; la versión vigente es 2.338.2 (binario verificado, HTTP 200). El log enlaza el aviso de "versión mínima de runner autohospedado". | Causa **inferida** (alta) |
| H2 | Monedas sin sembrar → `sync_tasas_ve` no hace nada | `Moneda` es un catálogo global (`codigo_iso` único). La tarea exige `USD` y `VES` (`apps/integration_hub/tasks.py`). `seed_empresa_inicial` solo crea la moneda base indicada, con `nombre = codigo`. Nada siembra `VES`. | **Verificado** (logs del worker: `{'error': 'Monedas no encontradas'}`) |
| H3 | La tarea termina "con éxito" devolviendo `{'error': ...}` | Mismo código: `return {"error": "Monedas no encontradas"}` → Celery la marca `SUCCESS`; el fallo queda invisible. | Verificado |
| H4 | RLS no aplica en entornos reales | [CTF-012](../ctf/CTF-012.md): la app conecta con el rol dueño de las tablas (o superusuario), que se salta RLS aunque esté `FORCE`; además el default de conexión es `bypass='on'`. Los tests pasan porque usan `SET ROLE` a un rol sin privilegios. | Verificado (documento + tests) |
| H5 | 32 respuestas HTTP que incluyen `str(e)` | `git grep -E 'Response\(\{[^}]*str\((e\|exc\|err)\)'` en `backend/apps` | Texto; revisar falsos positivos |
| H6 | Intermitencias por orden temporal | `uuid7` no monótono; `_config_de` ordena solo por `-created_at`; relojes de baja resolución (Windows ~15 ms) dan marcas iguales | Verificado en 4 tests |
| H7 | Dependencias sin versión fija | `mcp>=`, `confluent-kafka>=`, `django-ratelimit>=`, `anthropic>=` en `backend/requirements.txt` | Verificado |
| H8 | Los avisos de seguridad rompen PRs ajenos | `pip-audit`/`npm audit` son bloqueantes en cada PR: un aviso publicado entre dos CI en verde rompió todos los PRs (junio→noviembre) | Verificado |
| H9 | Matrices `mapa_superficie` desactualizadas rompen el CI | Ocurrió en #261 y #266 | Verificado |
| H10 | Un E2E fallido no deja evidencia | No se suben `test-results`/trace; el diagnóstico de la intermitencia de `venta` exigió reproducir en local | Verificado |
| H11 | Ramas remotas ya integradas | Más de 40 con 0 commits por delante de `develop` | Verificado |
| H12 | Deuda y calidad estática | 169 `# noqa`, 38 `eslint-disable`, 47 TODO/FIXME, 5 `print(` y 1 `console.log` fuera de tests, 2 `any`; `docs/tech-debt/INVENTORY.md` (2026-06-10) dice "0 TODO en backend" y hoy hay 28 | Texto |
| H13 | Caché persistida muestra datos de hasta 30 s tras un cambio externo | `staleTime: 30_000` + `idbPersister`; reproducido con experimento controlado en E2E | Verificado |
| H14 | Configuración de staging | `DATABASE_URL`/`REDIS_URL` son valores literales (no referencias) en backend, worker y beat; `DJANGO_ALLOWED_HOSTS` incluye el host de producción | Verificado |

## 3. Fases y tareas

Leyenda: ⬜ pendiente · 🔄 en curso · ✅ hecho. 👤 = requiere acción del propietario.

### Fase 0 — Arreglos acotados (primero)

| # | Tarea | Resuelve | Aceptación |
|---|-------|----------|------------|
| 0.1 | ✅ Subir `RUNNER_VERSION` a 2.338.2 y documentar el síntoma (404) en `infra/ci-runner/README.md` | H1 | El servicio `ci-runner` se registra y `long-tests.yml` lo toma 👤 verifica en Railway |
| 0.2 | ✅ **Monedas**: comando idempotente `seed_catalogo_monedas` (USD, VES, EUR, USDT), llamado desde `entrypoint.sh` y desde `seed_empresa_inicial`; `sync_tasas_ve` lanza una excepción visible si faltan monedas; tests | H2, H3 | Tras el despliegue de staging el worker devuelve `bcv`/`binance_p2p` y hay filas en `TasaCambio`; el comando es idempotente y no pisa ediciones |
| 0.3 | ✅ Subir `frontend/test-results` como artefacto cuando falle el E2E | H10 | Un E2E fallido deja `error-context.md` y trazas descargables |
| 0.4 | ✅ Automatizar las matrices: hook `pre-push` que corre `mapa_superficie --check` + una línea en el DoD | H9 | Un cambio de modelos sin regenerar matrices no sale de la máquina |

### Fase 1 — Fiabilidad

| # | Tarea | Resuelve | Aceptación |
|---|-------|----------|------------|
| 1.1 | ⬜ Auditar los 32 `str(e)`: clasificar (mensaje de dominio seguro vs excepción genérica), helper común y reemplazo por app | H5 | Ninguna respuesta expone una excepción no controlada; test por app |
| 1.2 | ✅ `uuid7` monótono (D1) y desempate por `created_at` + pk en `_config_de`; corregir `test_tolerancia_custom_cambia_resultado` | H6 | Los tests dejan de variar; tests de monotonicidad (mismo ms, hilos) |
| 1.3 | ✅ Fijar versión exacta de las 4 dependencias; Dependabot semanal; mover `pip-audit`/`npm audit` a un job nocturno que abra un aviso y bloquee solo en la rama de release | H7, H8 | Un aviso nuevo no bloquea un PR no relacionado |

### Fase 2 — RLS real (CTF-012)

| # | Tarea | Aceptación |
|---|-------|------------|
| 2.1 | ⬜ Runbook + código: rol `omni_app` (sin `SUPERUSER`/`BYPASSRLS`, no dueño), migraciones con el dueño, default de conexión `bypass='off'` con `rls_bypass()` explícito en tareas Celery y comandos | Tests: tarea/comando sin contexto no ve filas de otra empresa |
| 2.2 | 👤 Crear el rol y cambiar `DATABASE_URL` en staging (secretos) | Consulta sin contexto contra staging devuelve 0 filas |
| 2.3 | 👤 Repetir en producción tras validar staging | Suite RLS verde con `RLS_ENABLED=True` |

> Mientras 2.2/2.3 no estén hechas, el aislamiento entre empresas descansa solo en el filtrado de
> aplicación (`get_empresas_visible`); las políticas RLS de Connect S1 existen pero no se imponen.

### Fase 3 — Higiene del repositorio

| # | Tarea | Resuelve |
|---|-------|----------|
| 3.1 | 👤 Borrar ramas integradas y activar *Automatically delete head branches* | H11 |
| 3.2 | ✅ Revisar `frontend/test-import.js`; ignorar carpetas locales basura (`backend/%SystemDrive%`, `backend/sqlite-tools`, `.venv*`) | H12 |
| 3.3 | ⬜ D2: migrar a `ruff` (config en `setup.cfg`/`pyproject`), quitar `black`/`isort`, PR mecánico de reformateo | H12 |
| 3.4 | ⬜ Barrido: justificar o quitar `# noqa`/`eslint-disable`, imports sin usar, TODOs | H12 |
| 3.5 | ✅ Actualizar `docs/tech-debt/INVENTORY.md`; unificar `docs/archive` y `docs/_archive`. **No** se modifican fechas de CTF (D3) *(cerrado en PR `#288` `docs/gobernanza-graphify-y-planes-v13`)* | H12 |
| 3.6 | ✅ Actions con aviso de Node 20: subir versiones *(cerrado en PR `#289`)* | — |

### Fase 4 — Producto

| # | Tarea | Resuelve |
|---|-------|----------|
| 4.1 | ✅ D4: `PersistQueryClientProvider onSuccess` → invalidar consultas activas; test | H13 |
| 4.2 | ⬜ Montos, segunda pasada (R-CODE-4): otros formularios con `number`, `utils/formatCurrency`, volver a tipar `D()`, alias `XFormValues` redundantes | — |
| 4.3 | 👤 Railway: `DATABASE_URL`/`REDIS_URL` como referencias; quitar el host de producción de `DJANGO_ALLOWED_HOSTS`; no usar *Sync* con entornos de PR | H14 |
| 4.4 | ⬜ Connect S2 en adelante, **después de la fase 2** (perfil público con `rls.rls_bypass()` acotado y solo tarjetas `ACTIVA`) | — |

## 4. Detalle — Monedas (tarea 0.2)

- **Dónde**: `apps/finanzas/management/commands/seed_catalogo_monedas.py` con la lógica en una función
  reutilizable (el comando no llama a otro comando).
- **Catálogo**: `USD`, `VES`, `EUR`, `USDT` con `nombre`, `simbolo`, `pais_codigo_iso`, `pais_nombre`,
  `tipo_moneda` (`fiat`/`crypto`), `decimales` y visibilidad pública, igual que el resto del catálogo global.
- **Idempotencia sin pisar ediciones**: `get_or_create` por `codigo_iso`; si ya existe, solo se completan
  los campos que sigan con el valor placeholder (`nombre == codigo`, `simbolo == codigo[:5]`, país vacío).
- **Cuándo corre**: en `entrypoint.sh` junto a `seed_proveedores_integracion` (solo en el servicio web,
  no en worker/beat) y dentro de `seed_empresa_inicial`. Así el siguiente despliegue de staging lo siembra
  **sin escribir datos a mano**.
- **`sync_tasas_ve`**: si faltan monedas, `logger.error` y **excepción** (Celery marca `FAILURE`; Sentry avisa)
  en lugar de `return {"error": ...}`. Se actualiza el test que hoy asegura el retorno con error.
- **Dependientes**: `cxc_lubrikca/services/captura.py` hace `Moneda.objects.get(...)` de USD/VES y hoy
  fallaría en un entorno nuevo.

## 5. Acciones del propietario 👤 (resumen)

1. Verificar que `ci-runner` se registra tras 0.1.
2. Activar *Automatically delete head branches* y borrar las ramas integradas (3.1).
3. Crear el rol de aplicación en Railway y cambiar `DATABASE_URL` (2.2, 2.3).
4. Ajustes de variables de staging (4.3).

## 6. Riesgos

- **2.1 cambia el default de RLS**: una tarea o comando que hoy "funciona" por correr con `bypass='on'`
  fallará hasta que se marque su contexto. Mitigación: inventario previo de tareas/comandos y tests por cada uno.
- **D1 cambia la generación de claves de todo el sistema**: se mantiene el formato UUIDv7 válido; los
  existentes no se tocan.
- **3.3 (reformateo masivo)** genera un diff grande: se hace con pocos PRs abiertos y sin mezclar cambios.

## 7. Fuera de alcance

- Cambiar el comportamiento offline de la PWA (`NetworkFirst`, 5 s): decisión de diseño de ADR-001.
- Renegociar fechas de CTF (D3).

## 8. Cómo volver a medir

```bash
# Conteos de la sección 2 (sobre develop)
git grep -I -c -E 'TODO|FIXME|HACK|XXX' origin/develop -- backend/apps frontend/src
git grep -I -c '# noqa' origin/develop -- backend/apps
git grep -I -n -E 'Response\(\{[^}]*str\((e|exc|err)\)' origin/develop -- backend/apps ':!*test*'
git ls-tree -r --name-only origin/develop frontend | grep test-import

# Ramas remotas ya integradas
for b in $(git for-each-ref --format='%(refname:short)' refs/remotes/origin | grep -v 'HEAD\|develop\|main'); do
  echo "$(git rev-list --count origin/develop..$b) $b"; done | sort -n

# Estado de Railway (solo lectura)
railway deployment list -e staging -s ci-runner
railway logs -e staging -s omni-erp-worker -d --lines 40
```
