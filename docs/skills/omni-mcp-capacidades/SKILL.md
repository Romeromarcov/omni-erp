---
name: omni-mcp-capacidades
description: Use this skill whenever you expose, modify, or secure a business capability as an MCP tool in the Omni project. Triggers include any work on `apps/core/mcp_server.py`, a module's `apps/<modulo>/mcp.py`, the `MCP_TOOLS` auto-discovery list, CapabilityToken validation, scopes (e.g. `ventas:read`, `cxc:write`), tenant verification inside tools, or fulfilling R-CODE-7 (API-first = REST + MCP). Apply it every time you add a new business capability, because API-first means the capability must exist as an invocable tool, not only a REST endpoint. Do NOT use for pure frontend work, REST-only viewsets already covered by omni-django-module, or infra changes.
---

# Skill: Exponer Capacidades como Herramientas MCP

## Cuándo usar esta skill

Cargá esta skill cuando:
- Exponés una capacidad de negocio nueva a agentes (consultar saldo, crear pedido, registrar movimiento).
- Agregás o modificás una tool en `apps/<modulo>/mcp.py`.
- Tocás el servidor MCP (`apps/core/mcp_server.py`) o el auto-discovery.
- Trabajás con `CapabilityToken`, scopes o validación de tenant en tools.

No la cargués para frontend, ni para un viewset REST que ya cubre `omni-django-module`.

## Por qué importa (R-CODE-7: API-first = REST + MCP)

En Omni, **toda lógica existe primero como capacidad invocable** antes de tener UI. "Invocable" significa **REST + MCP**: si una capacidad sólo tiene endpoint REST pero ningún agente puede usarla, no es AI-nativa. El MCP es el moat del producto (ADR-003).

Principios del runtime MCP:
- **Sin acceso por defecto:** cada llamada exige un `CapabilityToken` válido.
- **Scope mínimo por herramienta** (`modulo:read` / `modulo:write`).
- **Tenant siempre verificado** dentro de la tool (defense-in-depth).
- **Audit log** de cada llamada.

## Arquitectura: auto-discovery por módulo

El servidor central (`apps/core/mcp_server.py`) descubre automáticamente cualquier módulo `apps.<modulo>.mcp` que exporte una lista `MCP_TOOLS`. **No registres tools a mano en el servidor central**; definilas en el módulo y exportá `MCP_TOOLS`.

Para que un módulo se descubra, su ruta debe estar en `_MCP_DEFAULT_MODULE_PATHS` (o en `MCP_AGENT_CAPABILITIES["module_paths"]` de settings).

## Plantilla: tool de un módulo

```python
# apps/<modulo>/mcp.py
import logging
from typing import Any, Dict, List

logger = logging.getLogger("omni.mcp.<modulo>")
_SCOPE = "<modulo>"


def _ctx(capability_token: str, scope: str) -> dict:
    """Resuelve y valida token + scope. Lanza PermissionError si falla."""
    from apps.core.mcp_server import _require_scope, _resolve_token  # noqa: PLC0415
    context = _resolve_token(capability_token)
    _require_scope(context, scope)
    assert context is not None  # noqa: S101
    return context


def <modulo>_get_entidad(capability_token: str, empresa_id: str, entidad_id: str) -> dict:
    """
    Descripción de una línea de lo que hace.

    Scope requerido: ``<modulo>:read``

    Args:
        capability_token: Token con scope ``<modulo>:read``.
        empresa_id:       ID de la empresa (tenant).
        entidad_id:       UUID de la entidad.

    Returns:
        dict con los campos relevantes.
    """
    from apps.<modulo>.models import Entidad  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:read")
    # 1) Verificación de tenant SIEMPRE, aunque el runtime ya valide:
    if empresa_id != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    try:
        # 2) Query SIEMPRE filtrada por id_empresa:
        obj = Entidad.objects.get(pk=entidad_id, id_empresa=empresa_id)
    except Entidad.DoesNotExist:
        return {"error": f"Entidad {entidad_id} no encontrada."}

    logger.info("<modulo>_get_entidad | actor=%s | tenant=%s | id=%s",
                ctx["actor_id"], ctx["tenant_id"], entidad_id)
    return {"id": str(obj.pk), "total": obj.total}   # Decimal, no float


# ── Auto-discovery: exportar la lista de herramientas ───────────────────────
MCP_TOOLS: List[Dict[str, Any]] = [
    {
        "fn": <modulo>_get_entidad,
        "name": "<modulo>_get_entidad",
        "scope": f"{_SCOPE}:read",
    },
]
```

## Las dos verificaciones que NUNCA se omiten

Toda tool hace, en orden, antes de tocar datos:

1. **Scope:** `_require_scope(context, "<modulo>:read|write")` — vía `_ctx()`.
2. **Tenant:** comparar el `empresa_id` recibido contra `context["empresa_id"]` y **filtrar la query por `id_empresa`**.

Esto es **defense-in-depth**: aunque el runtime ya valida el token, la tool repite la verificación. Un agente comprometido o un bug del runtime no debe poder leer otra empresa.

## Convención de scopes

- Formato: `modulo:accion` → `ventas:read`, `ventas:write`, `cxc:read`, `inventario:write`, `fiscal:read`, `finanzas:read`, `contactos:read`.
- `read` para consultas, `write` para mutaciones.
- El comodín `*` solo es efectivo para tokens de sistema/superusuario (`CapabilityToken.comodin_autorizado`); un token de empresa con `scopes=["*"]` auto-otorgado NO concede acceso total (se filtra en `_resolve_token`).

## Naming de tools

- Prefijo con el módulo: `ventas_get_facturas`, `cxc_get_cartera_vencida`, `inventario_registrar_movimiento`.
- `get_` para lectura, verbo de acción para escritura (`crear_`, `registrar_`).
- El `name` en `MCP_TOOLS` coincide exactamente con el nombre de la función.

## Mutaciones (tools de escritura)

```python
def <modulo>_crear_algo(capability_token, empresa_id, ...):
    from django.db import transaction  # noqa: PLC0415
    ctx = _ctx(capability_token, f"{_SCOPE}:write")
    if empresa_id != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")
    try:
        with transaction.atomic():
            obj = Modelo.objects.create(id_empresa_id=empresa_id, ...)
        return {"id": str(obj.pk), "estado": obj.estado}
    except Exception as exc:
        logger.exception("<modulo>_crear_algo | error: %s", exc)
        return {"error": str(exc)}   # ← ver nota de seguridad abajo
```

> **Nota de seguridad:** devolver `str(exc)` al cliente está prohibido en REST 500 (R-CODE-8). En tools MCP el patrón existente lo usa para feedback al agente, pero **no incluyas secretos ni detalles internos sensibles** en el mensaje. Preferí mensajes de error de negocio (`"stock insuficiente"`) sobre el `str(exc)` crudo cuando puedas distinguir el caso.

## Dinero y precisión

Devolvé montos como **Decimal** (o `str` de Decimal), nunca `float` — `float(...)` en un payload pierde precisión (ver bugs BUG-NEW-2 corregidos en el código). Ver skill `omni-decimal-money`.

## Tests de tools MCP

Las tools son funciones de módulo importables; testealas directo:

```python
class TestMcpVentas(TestCase):
    def setUp(self):
        self.empresa = EmpresaFactory()
        self.token = CapabilityTokenFactory(empresa=self.empresa, scopes=["ventas:read"])

    def test_requiere_token_valido(self):
        with self.assertRaises(PermissionError):
            ventas_get_facturas("token-basura", str(self.empresa.id_empresa))

    def test_scope_insuficiente(self):
        tok = CapabilityTokenFactory(empresa=self.empresa, scopes=["cxc:read"])
        with self.assertRaises(PermissionError):
            ventas_get_facturas(str(tok.token), str(self.empresa.id_empresa))

    def test_no_lee_otra_empresa(self):
        otra = EmpresaFactory()
        with self.assertRaises(PermissionError):
            ventas_get_facturas(str(self.token.token), str(otra.id_empresa))
```

## Anti-patrones

### Anti-patrón 1: query sin filtro de empresa
```python
# MAL — confía solo en el token
obj = Modelo.objects.get(pk=entidad_id)

# BIEN — defense-in-depth
obj = Modelo.objects.get(pk=entidad_id, id_empresa=empresa_id)
```

### Anti-patrón 2: olvidar comparar empresa_id vs token
```python
# MAL — el agente pasa cualquier empresa_id
ctx = _ctx(token, "ventas:read")
qs = Modelo.objects.filter(id_empresa=empresa_id)   # empresa_id no verificado

# BIEN
if empresa_id != ctx["empresa_id"]:
    raise PermissionError("empresa_id no coincide con el tenant del token.")
```

### Anti-patrón 3: registrar a mano en el servidor central
```python
# MAL — agregar la tool dentro de mcp_server.py
# BIEN — definirla en apps/<modulo>/mcp.py y exportarla en MCP_TOOLS (auto-discovery)
```

### Anti-patrón 4: float en el retorno
```python
# MAL
return {"total": float(factura.total)}
# BIEN
return {"total": factura.total}   # Decimal
```

## Checklist final

- [ ] La tool valida scope con `_require_scope` (vía `_ctx`).
- [ ] Compara `empresa_id` recibido contra `context["empresa_id"]`.
- [ ] Toda query filtra por `id_empresa` (defense-in-depth).
- [ ] El scope sigue `modulo:read|write`.
- [ ] La tool está en `MCP_TOOLS` con `fn`, `name`, `scope`; el módulo está en los `module_paths`.
- [ ] Montos como Decimal, sin `float`.
- [ ] Logueo con `actor`, `tenant` y datos no sensibles.
- [ ] Tests: token inválido → PermissionError; scope insuficiente → PermissionError; otra empresa → PermissionError.
- [ ] Si la capacidad es nueva, también existe (o existirá) su endpoint REST (API-first, R-CODE-7).

## Referencias

- Código: `apps/core/mcp_server.py` (runtime, `_resolve_token`, `_require_scope`, auto-discovery), `apps/ventas/mcp.py` (ejemplo de módulo).
- Modelo: `apps/core.CapabilityToken` (scopes, expiración, `comodin_autorizado`).
- Skill: `omni-multi-tenant-isolation`, `omni-decimal-money`, `omni-django-module`.
- ADR-003 (Integration Hub + MCP), Plan Maestro §3.5.

## Changelog

### v1.0
- Versión inicial, basada en `mcp_server.py` y `apps/ventas/mcp.py`.
