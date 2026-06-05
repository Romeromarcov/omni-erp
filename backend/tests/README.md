# `backend/tests/` — Arquitectura de tests "cero dudas"

Estructura por capas de la pirámide de tests (plan
[`docs/PLAN_AUDITORIA_Y_TESTING_CERO_DUDAS.md`](../../docs/PLAN_AUDITORIA_Y_TESTING_CERO_DUDAS.md) §B1).
La suite histórica vive en `tests_api/` y se migra **por capas** hacia aquí; ambas corren
en CI mientras dura la transición (ver `testpaths` en `pytest.ini`).

```
tests/
├── factories/      # factory_boy tenant-aware (Empresa, Moneda, Usuarios, …)
├── conftest.py     # fixtures globales: dos empresas + dos usuarios, clientes API, autouse
├── unit/           # PURO, sin BD (decimal, iva/igtf, aging, scoring, costeo) + property-based
├── integration/    # services.py con BD: @atomic/rollback, select_for_update, R-CODE-11, flujos
├── tenant/         # aislamiento multi-tenant (R-CODE-1) — comportamiento cross-tenant
├── api/            # por endpoint: authz, paginación, forma de error, contrato OpenAPI
└── e2e/            # flujos críticos extremo a extremo (API)
```

## Marcadores pytest

`unit`, `integration`, `tenant`, `contract`, `e2e` (registrados en `pytest.ini`). Filtra con
`-m tenant`, `-m "unit or integration"`, etc.

## Aislamiento multi-tenant (R-CODE-1): dos guards complementarios

- **Estructural** — `tenant/test_aislamiento_cobertura.py` (TEST-1): introspecta el URLconf
  y exige que **todo** ViewSet sobre un modelo con FK a `Empresa` sobreescriba `get_queryset`.
  Falla solo con agregar un ViewSet sin filtrar.
- **De comportamiento** — `tenant/test_aislamiento_comportamiento.py` (TEST-2): tabla declarativa
  `CASES` que, por modelo, verifica contra la API real que A no ve/edita/borra objetos de B
  (list, retrieve→404, patch→404, delete bloqueado). Para cubrir un módulo nuevo, agrega una fila.

## Fixtures clave (`conftest.py`)

`empresa_a` / `empresa_b`, `user_a` / `user_b`, `moneda_usd`, `metodo_efectivo`,
`client_a` / `client_b` (DRF autenticados), `api_client` (anónimo). Construidos sobre
`tests/factories/`. Los autouse neutralizan rate-limit (cache) y Celery/Redis (eager en memoria).
