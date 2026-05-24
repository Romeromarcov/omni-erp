---
name: omni-multi-tenant-isolation
description: Use this skill whenever you write or modify code that queries the database, creates viewsets, adds endpoints, or touches any data access in the Omni project. Triggers include any work involving Django ORM queries (`.objects.all()`, `.filter()`, `.get()`), DRF viewsets, custom managers, services that read or write data, signals, Celery tasks that operate on tenant data, or any new endpoint exposed via REST or MCP. Apply this skill especially carefully when touching cross-entity logic where one entity references another. Do NOT use for tasks that only modify frontend, only run pre-existing migrations, or work on truly tenant-agnostic code (rare: only system administration of the SaaS itself, like billing of the SaaS provider).
---

# Skill: Aislamiento Multi-Tenant Riguroso

## Cuándo usar esta skill

Cargá esta skill **siempre que toques datos**. En la práctica, casi cualquier tarea que modifique código del backend.

Casos típicos de aplicación:
- Crear un nuevo viewset.
- Modificar lógica de un servicio que lee o escribe.
- Crear o modificar Celery tasks que operan sobre datos de tenants.
- Agregar un signal.
- Crear un manager custom.
- Exponer una capacidad MCP.

No la cargués en:
- Trabajo puramente de frontend.
- Modificaciones a infraestructura (Docker, CI).
- Trabajo en el módulo `core` de gestión del SaaS mismo (tu propia facturación, tu admin).

## Por qué esta skill es crítica

**El leak de datos entre tenants es el bug más caro de detectar después.** Generalmente:

- No se nota en desarrollo (un solo tenant en datos de prueba).
- No se nota en staging si los testers no piensan en aislamiento.
- Se nota en producción cuando un cliente ve datos de otro cliente.
- Cuando se nota, el daño reputacional ya está hecho.

Por eso el aislamiento se construye **de entrada, en cada query, con tests que lo bloquean en CI**. No es opcional, no es algo que arreglás después.

## La regla central

**Toda query a una tabla con `id_empresa` debe filtrar por `id_empresa` de la sesión actual, salvo que tengas razón explícita y justificada para no hacerlo.**

La razón explícita típica es:
- Estás operando en el módulo `core` de gestión del SaaS (no es lógica de tenant).
- Estás haciendo una operación administrativa documentada (con permisos de superuser).
- Estás haciendo un reporte agregado de toda la plataforma para tu propio uso.

En todos los demás casos: filtrá. Siempre.

## Patrones correctos

### Patrón 1: ViewSet heredando de BaseModelViewSet

```python
from apps.core.viewsets import BaseModelViewSet

class ClienteViewSet(BaseModelViewSet):
    serializer_class = ClienteSerializer
    # No hace falta declarar queryset; BaseModelViewSet
    # filtra automáticamente por self.request.user.empresa
```

`BaseModelViewSet` aplica `filter(id_empresa=request.user.empresa)` en `get_queryset()`. **Confiá en él, no lo sobrescribás sin razón.**

### Patrón 2: ViewSet con queryset adicional

```python
class FacturaViewSet(BaseModelViewSet):
    serializer_class = FacturaSerializer

    def get_queryset(self):
        # IMPORTANTE: super() ya filtra por empresa
        qs = super().get_queryset()
        # Filtros adicionales:
        qs = qs.select_related('cliente').prefetch_related('items')
        if self.action == 'list':
            qs = qs.filter(estado__in=['EMITIDA', 'PAGADA'])
        return qs
```

### Patrón 3: Service con empresa explícita

```python
def calcular_totales_mes(empresa, año, mes):
    """
    SIEMPRE recibí la empresa como parámetro explícito en services.
    No la asumas, no la deduzcas.
    """
    return Factura.objects.filter(
        id_empresa=empresa,  # ← Filtro explícito siempre
        fecha_emision__year=año,
        fecha_emision__month=mes,
        estado='PAGADA',
    ).aggregate(total=Sum('monto_total'))
```

### Patrón 4: Celery task con empresa explícita

```python
@shared_task
def procesar_cobranzas_diarias(empresa_id):
    """
    Tasks SIEMPRE reciben empresa_id, no asumen.
    """
    empresa = Empresa.objects.get(id_empresa=empresa_id)
    cuentas = CuentaPorCobrar.objects.filter(
        id_empresa=empresa,  # ← Filtro explícito
        estado='VENCIDA',
    )
    for cuenta in cuentas:
        # Lógica
        pass
```

### Patrón 5: Cross-entity con FK

Cuando una entidad referencia otra, **verificá que la referenciada sea de la misma empresa**.

```python
def crear_factura_para_cliente(empresa, cliente_id, datos):
    # Buscá el cliente DENTRO de la empresa
    try:
        cliente = Cliente.objects.get(
            id_cliente=cliente_id,
            id_empresa=empresa,  # ← Crítico
        )
    except Cliente.DoesNotExist:
        # Tratar como 404, no como cliente de otra empresa
        raise NotFound('Cliente no encontrado.')

    factura = Factura.objects.create(
        id_empresa=empresa,
        cliente=cliente,
        # ...
    )
    return factura
```

**¿Por qué es crítico esto?** Si un usuario malicioso pasa un `cliente_id` de otra empresa en su request, sin ese filtro doble, podrías crear facturas atadas a clientes de otras empresas. **Un agujero clásico.**

### Patrón 6: Signal con tenant awareness

```python
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Factura)
def recalcular_saldo_cliente(sender, instance, created, **kwargs):
    """
    instance.id_empresa ya viene seteado.
    Operá DENTRO de esa empresa.
    """
    if created:
        actualizar_saldo_cliente(
            empresa=instance.id_empresa,  # ← La empresa de la instancia
            cliente=instance.cliente,
            monto=instance.monto_total,
        )
```

### Patrón 7: MCP capability con autorización

```python
from apps.mcp_runtime import register_capability

@register_capability(
    name='consultar_cuentas_vencidas',
    description='Devuelve cuentas por cobrar vencidas de la empresa actual.',
    requires_capability_token='cuentas_por_cobrar.leer',
)
def mcp_consultar_vencidas(empresa_id):
    """
    El MCP runtime ya validó que el token tiene la capacidad
    Y que es para la empresa correcta. Pero filtramos igual.
    """
    return CuentaPorCobrar.objects.filter(
        id_empresa=empresa_id,  # ← Filtro explícito redundante
        estado='VENCIDA',
    ).values('id_cuenta', 'monto', 'cliente__razon_social')
```

**Notar el filtro redundante:** aunque el MCP runtime valida, filtramos igual. Es defense-in-depth.

## Anti-patrones (lo que NO hacés)

### Anti-patrón 1: `objects.all()` en código de negocio

```python
# MAL
def listar_facturas():
    return Factura.objects.all()

# BIEN
def listar_facturas(empresa):
    return Factura.objects.filter(id_empresa=empresa)
```

### Anti-patrón 2: `objects.get(pk=...)` sin filtro

```python
# MAL
factura = Factura.objects.get(pk=factura_id)

# BIEN
factura = Factura.objects.get(pk=factura_id, id_empresa=empresa)
```

### Anti-patrón 3: Asumir empresa por la sesión sin pasarla

```python
# MAL — fácil de romper en background tasks o tests
def procesar_factura(factura_id):
    request_local.user.empresa  # frágil
    # ...

# BIEN
def procesar_factura(factura_id, empresa):
    # ...
```

### Anti-patrón 4: Confiar solo en el viewset

```python
# MAL — el service asume que viene con empresa filtrada, pero podés llamarlo desde otros lados
def aprobar_factura(factura_id):
    factura = Factura.objects.get(pk=factura_id)  # Sin filtro

# BIEN
def aprobar_factura(empresa, factura_id):
    factura = Factura.objects.get(pk=factura_id, id_empresa=empresa)
```

### Anti-patrón 5: Cross-entity sin verificación

```python
# MAL
def crear_pago(empresa, cuenta_id, monto):
    cuenta = CuentaPorCobrar.objects.get(pk=cuenta_id)  # No verifica empresa
    # Si cuenta_id es de otra empresa, lo aceptás silenciosamente

# BIEN
def crear_pago(empresa, cuenta_id, monto):
    cuenta = CuentaPorCobrar.objects.get(pk=cuenta_id, id_empresa=empresa)
    # Si no es de esta empresa, da DoesNotExist (404)
```

### Anti-patrón 6: Reportes globales sin restricción

```python
# MAL
def reporte_ventas_mensuales():
    return Factura.objects.filter(estado='PAGADA').aggregate(total=Sum('monto'))
    # Suma TODAS las empresas

# BIEN
def reporte_ventas_mensuales(empresa):
    return Factura.objects.filter(
        id_empresa=empresa,
        estado='PAGADA',
    ).aggregate(total=Sum('monto'))
```

### Anti-patrón 7: Logs con datos cross-tenant

```python
# MAL — puede loguear datos de otra empresa si la consulta leakea
logger.info(f'Procesando factura {factura.id_factura} de cliente {factura.cliente.razon_social}')
# Si factura es de otra empresa por bug, queda en logs

# BIEN — incluí id_empresa siempre en logs
logger.info(
    f'Procesando factura',
    extra={
        'id_empresa': str(factura.id_empresa.id_empresa),
        'id_factura': str(factura.id_factura),
    }
)
```

## Tests de aislamiento obligatorios

**Todo PR que modifique data access debe incluir o actualizar tests de aislamiento.**

Plantilla mínima por viewset:

```python
class TestModeloAislamiento(APITestCase):
    def setUp(self):
        self.empresa_a = EmpresaFactory.create()
        self.empresa_b = EmpresaFactory.create()
        self.user_a = UsuarioFactory.create(empresa=self.empresa_a)
        self.user_b = UsuarioFactory.create(empresa=self.empresa_b)
        self.objeto_a = ModeloFactory.create(id_empresa=self.empresa_a)
        self.objeto_b = ModeloFactory.create(id_empresa=self.empresa_b)

    def test_listado_solo_empresa_propia(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get('/api/v1/modelo/')
        ids = [r['id'] for r in response.data['results']]
        self.assertIn(str(self.objeto_a.id), ids)
        self.assertNotIn(str(self.objeto_b.id), ids)

    def test_get_otra_empresa_da_404(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(f'/api/v1/modelo/{self.objeto_b.id}/')
        self.assertEqual(response.status_code, 404)

    def test_no_puede_modificar_otra_empresa(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.patch(
            f'/api/v1/modelo/{self.objeto_b.id}/',
            {'campo': 'hackeado'},
        )
        self.assertEqual(response.status_code, 404)

    def test_no_puede_eliminar_otra_empresa(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.delete(f'/api/v1/modelo/{self.objeto_b.id}/')
        self.assertEqual(response.status_code, 404)

    def test_no_puede_referenciar_fk_de_otra_empresa(self):
        """
        Crítico para entidades con FK a otras entidades.
        """
        # Por ejemplo, si Factura tiene FK a Cliente:
        cliente_b = ClienteFactory.create(id_empresa=self.empresa_b)
        self.client.force_authenticate(user=self.user_a)
        response = self.client.post('/api/v1/factura/', {
            'cliente': cliente_b.id_cliente,  # cliente de otra empresa
            'monto': 1000,
        })
        # Debe rechazarse
        self.assertIn(response.status_code, [400, 404])
```

## Cómo detectar leaks en code review

Cuando revisás código (tuyo o ajeno), buscá estas señales:

1. **`Model.objects.all()`** sin filter posterior por id_empresa.
2. **`Model.objects.get(pk=...)`** sin id_empresa.
3. **Services que no reciben `empresa` como parámetro.**
4. **Tasks de Celery que no reciben `empresa_id`.**
5. **Cross-entity sin verificación** (FK que no se valida que sea de la misma empresa).
6. **Reportes agregados** que no tienen id_empresa en el WHERE.
7. **Custom managers** sin override que filtre por empresa.

Si ves alguna de estas, es probable leak. Pedí explicación o corrección.

## Excepciones legítimas

Hay casos donde **NO** filtrás por empresa, pero deben ser explícitos y documentados:

### Caso 1: Gestión del SaaS mismo

```python
# El modelo Empresa es el modelo "tenant" mismo, no tiene id_empresa
def listar_todas_las_empresas_del_saas():
    """Solo accesible para superuser del SaaS."""
    return Empresa.objects.filter(activo=True)
```

### Caso 2: Métricas agregadas para tu uso interno

```python
def metrica_usuarios_activos_global():
    """
    SOLO PARA ADMIN DE OMNI (vos).
    Métrica sobre todo el SaaS.
    """
    return Usuario.objects.filter(activo=True).count()
```

### Caso 3: Búsqueda federada en Platform Spaces (Fase 4+)

Cuando llegues a Platform Spaces, va a haber operaciones cross-tenant deliberadas. Pero esas se hacen con primitivas explícitas (`PlatformSpace.federated_query()`), no con `objects.all()` raw.

## Checklist final

Antes de cerrar PR que toca data access:

- [ ] Todas las queries explícitas filtran por `id_empresa`.
- [ ] Los services reciben `empresa` como parámetro.
- [ ] Las Celery tasks reciben `empresa_id`.
- [ ] Las FKs cross-entity están verificadas para misma empresa.
- [ ] Hay test de aislamiento que falla si el filtro se quita.
- [ ] Los logs no exponen datos cross-tenant.
- [ ] Si hay alguna excepción legítima, está comentada en código y justificada.

## Errores históricos del proyecto

Esta sección se actualiza cada vez que detectamos un leak real en code review. Sirve como memoria institucional.

### Error #1 (placeholder, agregar cuando suceda)

[Cuando ocurra el primer leak detectado en review, documentarlo acá con: archivo, qué se hizo mal, cómo se corrigió, qué test se agregó.]

## Referencias

- Skill: `omni-django-module` (estructura general de módulos).
- Skill: `omni-pr-discipline` (auto-checklist incluye verificación multi-tenant).
- Decisión inmutable A-004: Multi-tenant Row-Level con `id_empresa`.
- Regla R-CODE-1: Multi-tenant siempre.

## Changelog

### v1.0 — Día 1
- Versión inicial.
