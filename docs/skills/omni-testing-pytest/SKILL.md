---
name: omni-testing-pytest
description: Use this skill whenever you write, run, or fix backend tests in the Omni project. Triggers include adding tests for a new model/service/viewset/MCP tool, writing factories, isolation tests (R-CODE-1), integration tests for critical flows (R-CODE-9), agent eval tests (tests_eval/), debugging a failing or flaky test, raising coverage to satisfy the ratchet gate, or any work under `tests/`, `tests_eval/`, or `pytest.ini`. Apply it to decide what kind of test a change needs and how to structure it. Do NOT use for frontend tests (Vitest), pure non-test code, or infra/CI YAML unrelated to the test gates.
---

# Skill: Estrategia de Tests Backend (pytest)

## Cuándo usar esta skill

Cargá esta skill cuando:
- Agregás tests para un modelo, service, viewset o tool MCP nueva.
- Escribís factories o tests de aislamiento multi-tenant.
- Cubrís un flujo crítico de extremo a extremo.
- Tocás un agente (eval suite).
- Depurás un test que falla o es flaky, o necesitás subir cobertura.

No la cargués para tests de frontend (Vitest), ni para código sin tests.

## Reglas de testing del proyecto

1. **PostgreSQL, nunca SQLite** (R-CODE-2). Los tests corren contra Postgres; constraints parciales y transacciones se comportan distinto en SQLite y ya costaron bugs. No cambies `DJANGO_SETTINGS_MODULE` a un settings con SQLite para "que corra más rápido".
2. **Tests en el mismo cambio** (R-CODE-9), no "después". Sin excepción salvo refactor mecánico marcado.
3. **Todo feature multi-tenant trae test de aislamiento** (R-CODE-1).
4. **Flujo crítico trae test de integración** (R-CODE-9): venta → factura → stock → asiento → CxC debe seguir verde.
5. **Flaky = bug** (R-PROC-4): se arregla la causa raíz, no se reintenta hasta que pase por suerte.
6. **Cobertura con ratchet:** `--cov-fail-under` solo SUBE, nunca baja. Hoy 67% (objetivo por escalones 65→75→85→90).

## Configuración (`pytest.ini`)

- `DJANGO_SETTINGS_MODULE = config.settings`
- `python_files = test_*.py`
- `testpaths = tests pruebas_funcionales apps`
- `addopts` incluye `--cov=apps --cov-fail-under=67 --cov-report=xml` (el XML alimenta diff-cover en CI).

### Markers disponibles

```python
@pytest.mark.unit          # prueba unitaria pura (sin BD)
@pytest.mark.integration   # con BD: services, @transaction.atomic, races
@pytest.mark.tenant        # aislamiento multi-tenant (R-CODE-1)
@pytest.mark.contract      # contrato de API (esquema OpenAPI)
@pytest.mark.e2e           # flujo crítico extremo a extremo
```

Marcá tus tests con el tipo correcto: ayuda a correr subconjuntos y comunica la intención.

## La pirámide de tests por tipo de cambio

| Cambiaste… | Tests mínimos |
|---|---|
| Modelo nuevo | `test_models` (validaciones, `__str__`, constraints) + **factory** |
| Viewset/endpoint | `test_views` (CRUD, permisos) + **`test_isolation`** (R-CODE-1) |
| Service con lógica | `test_services` (casos felices + borde) + atomicidad si escribe varias cosas |
| Tool MCP | token inválido / scope insuficiente / otra empresa (ver `omni-mcp-capacidades`) |
| Flujo crítico | `@pytest.mark.e2e` que recorre venta→factura→stock→asiento→CxC |
| Agente | eval suite con ≥25 casos dorados, precision@1 ≥ 80% (ver `omni-agentes-autonomia`) |
| Cálculo de dinero | casos con muchos decimales y redondeo (ver `omni-decimal-money`) |

## Factories (factory_boy)

Toda entidad testeable tiene su factory. La clave multi-tenant: la empresa del objeto y la del usuario deben ser **consistentes**.

```python
import factory
from factory.django import DjangoModelFactory
from apps.<modulo>.models import NuevoModelo
from apps.core.tests.factories import EmpresaFactory, UsuarioFactory


class NuevoModeloFactory(DjangoModelFactory):
    class Meta:
        model = NuevoModelo

    id_empresa = factory.SubFactory(EmpresaFactory)
    id_usuario_creacion = factory.SubFactory(
        UsuarioFactory,
        empresa=factory.SelfAttribute("..id_empresa"),   # misma empresa que el objeto
    )
    nombre = factory.Sequence(lambda n: f"Modelo {n}")
    monto = Decimal("1000.0000")
```

## Test de aislamiento (obligatorio, R-CODE-1)

Plantilla mínima — la empresa A nunca ve/modifica/borra datos de la empresa B:

```python
@pytest.mark.tenant
class TestNuevoModeloAislamiento(APITestCase):
    def setUp(self):
        self.empresa_a = EmpresaFactory()
        self.empresa_b = EmpresaFactory()
        self.user_a = UsuarioFactory(empresa=self.empresa_a)
        self.obj_a = NuevoModeloFactory(id_empresa=self.empresa_a)
        self.obj_b = NuevoModeloFactory(id_empresa=self.empresa_b)

    def test_listado_solo_empresa_propia(self):
        self.client.force_authenticate(self.user_a)
        r = self.client.get("/api/.../nuevo-modelo/")
        ids = [x["id_nuevo_modelo"] for x in r.data["results"]]
        self.assertIn(str(self.obj_a.pk), ids)
        self.assertNotIn(str(self.obj_b.pk), ids)

    def test_detalle_otra_empresa_da_404(self):
        self.client.force_authenticate(self.user_a)
        r = self.client.get(f"/api/.../nuevo-modelo/{self.obj_b.pk}/")
        self.assertEqual(r.status_code, 404)
```

Un buen test de aislamiento **falla si alguien quita el filtro por empresa**. Ver `omni-multi-tenant-isolation` para el catálogo completo (PATCH, DELETE, FK cross-entity).

## Test de integración / atomicidad

Cuando un service escribe varias cosas (documento + stock + asiento), testeá que **todo-o-nada**:

```python
@pytest.mark.integration
def test_factura_falla_revierte_stock_y_asiento(self):
    stock_inicial = stock_actual(self.producto)
    with self.assertRaises(AsientoError):
        emitir_factura(self.empresa_sin_mapeo, self.user, datos)  # asiento falla
    self.assertEqual(stock_actual(self.producto), stock_inicial)  # stock intacto
    self.assertFalse(FacturaFiscal.objects.filter(...).exists())  # factura no quedó
```

## Eval de agentes (`tests_eval/`)

Corre **sin BD ni LLM** (fallback determinístico) y valida precision@1 ≥ 80%. Se ejecuta con `pytest tests_eval/ --no-cov` (su propio job en CI). Detalle en `omni-agentes-autonomia`.

## Comandos

```bash
cd backend
python -m pytest tests/ -v --tb=short --no-header         # suite principal
python -m pytest tests_eval/ -v --no-cov                  # eval de agentes
python -m pytest -m tenant                                # solo aislamiento
python -m pytest path/test_x.py::TestY::test_z -x         # uno, frenar al primer fallo
python manage.py makemigrations --check --dry-run         # sin drift de migraciones
```

## Depurar flaky tests

Un test flaky es un **bug**, no ruido. Causas comunes:
- **Orden/tiempo:** dependencia de `now()` o de orden de creación. Fijá fechas explícitas; ordená queries.
- **Estado compartido:** datos que sobreviven entre tests. Usá factories por test, no fixtures globales mutables.
- **Concurrencia/race:** falta `select_for_update`. Reproducí con un test `@pytest.mark.integration`.
- **Aleatoriedad:** `Sequence` en vez de valores random; sembrá si usás random.

## Anti-patrones

### Anti-patrón 1: cambiar a SQLite para acelerar
```python
# MAL — settings con SQLite en tests; oculta bugs de Postgres (R-CODE-2)
# BIEN — correr contra Postgres siempre
```

### Anti-patrón 2: test que pasa por la razón equivocada
```python
# MAL — factory no fija la empresa; el aislamiento "pasa" porque no hay datos
# BIEN — SubFactory con SelfAttribute para empresa consistente
```

### Anti-patrón 3: "los tests vienen en el próximo PR"
```python
# MAL — viola R-CODE-9; los tests del próximo PR nunca llegan
# BIEN — tests en el mismo cambio
```

### Anti-patrón 4: reintentar un flaky hasta que pase
```python
# MAL — @pytest.mark.flaky(reruns=3)
# BIEN — encontrar y arreglar la causa raíz (R-PROC-4)
```

### Anti-patrón 5: bajar el umbral de cobertura
```python
# MAL — --cov-fail-under=60 porque "no me da el tiempo"
# BIEN — el ratchet solo sube; agregá los tests que faltan
```

## Checklist final

- [ ] Corre contra PostgreSQL, no SQLite.
- [ ] El cambio trae sus tests en el mismo PR.
- [ ] Hay factory para toda entidad nueva, con empresa consistente.
- [ ] Cambio multi-tenant → test de aislamiento que falla si se quita el filtro.
- [ ] Flujo crítico → test de integración/e2e atómico.
- [ ] Tool MCP → tests de token/scope/tenant.
- [ ] Agente → eval suite precision@1 ≥ 80%.
- [ ] Tests marcados con el marker correcto.
- [ ] Sin flaky; cobertura no baja del umbral.

## Referencias

- Config: `backend/pytest.ini`, suites en `tests/` (por capas) y `tests_eval/`.
- Skill: `omni-multi-tenant-isolation`, `omni-agentes-autonomia`, `omni-mcp-capacidades`, `omni-decimal-money`, `omni-asientos-contables`, `omni-definition-of-done`.
- Reglas R-CODE-1, R-CODE-2, R-CODE-9, R-PROC-4.

## Changelog

### v1.0
- Versión inicial, basada en `pytest.ini` y las suites del repo.
