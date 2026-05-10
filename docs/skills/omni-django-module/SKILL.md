---
name: omni-django-module
description: Use this skill whenever you create a new Django app/module or add models, viewsets, serializers, or filters to an existing one in the Omni project. Triggers include any task that touches files under `backend/apps/<module>/`, requests like "create a new module for X", "add model Y to module Z", "create viewset for entity W", or any work involving `BaseModel`, `BaseModelViewSet`, multi-tenant isolation patterns, or new Django apps. Do NOT use for tasks that only modify frontend, only run pre-existing migrations without schema changes, or pure documentation tasks unrelated to module structure.
---

# Skill: Crear o Modificar un Módulo Django en Omni

## Cuándo usar esta skill

Cargá esta skill cuando vas a:
- Crear una app Django nueva (`python manage.py startapp ...`).
- Agregar un modelo nuevo a una app existente.
- Agregar un viewset, serializer, o filter para una entidad de negocio.
- Refactorizar la estructura de una app existente.

No la cargués si solo vas a:
- Modificar lógica interna de un servicio sin tocar modelos ni APIs.
- Trabajar exclusivamente en frontend.
- Crear documentación.

## Estructura estándar de un módulo

Todo módulo de Omni tiene esta estructura:

```
backend/apps/<modulo>/
├── __init__.py
├── apps.py
├── admin.py
├── models.py              # Modelos del dominio
├── serializers.py         # Serializers DRF
├── views.py               # ViewSets
├── urls.py                # Rutas del módulo
├── filters.py             # Filtros para listados
├── permissions.py         # Permisos custom (si aplica)
├── services.py            # Lógica de negocio
├── events.py              # Eventos de dominio (Fase 0+)
├── mcp.py                 # Servidor MCP (Fase 0+)
├── tasks.py               # Tareas Celery (si aplica)
├── signals.py             # Signals (si aplica)
├── factories.py           # Factories para tests
├── migrations/
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_views.py
    ├── test_isolation.py  # OBLIGATORIO: aislamiento multi-tenant
    ├── test_services.py
    └── test_mcp.py        # Si hay capacidades MCP
```

## Plantilla: Modelo

```python
# apps/<modulo>/models.py

from django.db import models
from apps.core.models import BaseModel
from apps.core.utils import uuid_v7


class NuevoModelo(BaseModel):
    """
    Descripción breve del propósito del modelo.

    Eventos que emite (Fase 0+):
    - <modulo>.nuevo_modelo.creado
    - <modulo>.nuevo_modelo.modificado
    - <modulo>.nuevo_modelo.anulado
    """
    # PK con UUIDv7 (decisión inmutable A-002)
    id_nuevo_modelo = models.UUIDField(
        primary_key=True,
        default=uuid_v7,
        editable=False,
    )

    # NO declaramos id_empresa, fecha_creacion, fecha_modificacion, activo
    # porque vienen de BaseModel.

    # Campos del dominio (en español, snake_case)
    nombre = models.CharField(max_length=200)

    # Dinero: SIEMPRE Decimal con max_digits=18, decimal_places=4
    # (Ver skill: omni-decimal-money)
    monto = models.DecimalField(max_digits=18, decimal_places=4)

    estado = models.CharField(
        max_length=30,
        choices=[
            ('PENDIENTE', 'Pendiente'),
            ('APROBADO', 'Aprobado'),
            ('ANULADO', 'Anulado'),
        ],
        default='PENDIENTE',
    )

    # FKs siempre con related_name explícito y on_delete consciente
    cliente = models.ForeignKey(
        'crm.Cliente',
        on_delete=models.PROTECT,  # Casi nunca CASCADE para entidades de negocio
        related_name='nuevos_modelos',
    )

    class Meta:
        verbose_name = 'Nuevo Modelo'
        verbose_name_plural = 'Nuevos Modelos'
        # Unicidad típicamente por empresa
        unique_together = [['id_empresa', 'codigo_unico_por_empresa']]
        # Índices para queries frecuentes (siempre incluyen id_empresa)
        indexes = [
            models.Index(fields=['id_empresa', 'estado']),
            models.Index(fields=['id_empresa', 'fecha_creacion']),
        ]
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f'{self.nombre} ({self.id_empresa.nombre})'
```

## Plantilla: ViewSet

```python
# apps/<modulo>/views.py

from rest_framework import permissions
from apps.core.viewsets import BaseModelViewSet
from .models import NuevoModelo
from .serializers import NuevoModeloSerializer
from .filters import NuevoModeloFilter
from .services import crear_nuevo_modelo
from .events import emitir_evento_creado


class NuevoModeloViewSet(BaseModelViewSet):
    """
    ViewSet para NuevoModelo.

    Hereda de BaseModelViewSet que:
    - Filtra automáticamente por id_empresa del usuario.
    - Aplica soft delete en lugar de hard delete.
    - Maneja id_usuario_creacion / id_usuario_modificacion.
    """
    serializer_class = NuevoModeloSerializer
    filterset_class = NuevoModeloFilter
    search_fields = ['nombre']
    ordering_fields = ['fecha_creacion', 'monto', 'nombre']
    ordering = ['-fecha_creacion']
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # BaseModelViewSet ya filtra por empresa, pero podés agregar
        # filtros adicionales acá:
        qs = super().get_queryset()
        # qs = qs.select_related('cliente').prefetch_related('items')
        return qs

    def perform_create(self, serializer):
        # Usar el service, no crear directamente
        instance = crear_nuevo_modelo(
            empresa=self.request.user.empresa,
            usuario=self.request.user,
            datos=serializer.validated_data,
        )
        serializer.instance = instance
```

## Plantilla: Serializer

```python
# apps/<modulo>/serializers.py

from rest_framework import serializers
from .models import NuevoModelo


class NuevoModeloSerializer(serializers.ModelSerializer):
    # Campos calculados o de FK que querés mostrar legibles
    cliente_nombre = serializers.CharField(
        source='cliente.razon_social',
        read_only=True,
    )

    class Meta:
        model = NuevoModelo
        fields = [
            'id_nuevo_modelo',
            'nombre',
            'monto',
            'estado',
            'cliente',
            'cliente_nombre',
            'fecha_creacion',
            'fecha_modificacion',
            'activo',
        ]
        read_only_fields = [
            'id_nuevo_modelo',
            'fecha_creacion',
            'fecha_modificacion',
            'activo',
        ]

    def validate_monto(self, value):
        if value <= 0:
            raise serializers.ValidationError('El monto debe ser mayor a 0.')
        return value
```

## Plantilla: Service

```python
# apps/<modulo>/services.py

from django.db import transaction
from django.core.exceptions import ValidationError
from .models import NuevoModelo
from .events import emitir_evento_creado


@transaction.atomic
def crear_nuevo_modelo(empresa, usuario, datos):
    """
    Crea un NuevoModelo aplicando la lógica de negocio.

    Args:
        empresa: instancia de Empresa.
        usuario: instancia de Usuario.
        datos: dict con datos validados.

    Returns:
        NuevoModelo creado.

    Raises:
        ValidationError: si la lógica de negocio rechaza la creación.
    """
    # Validaciones de negocio
    if datos['monto'] > 1000000:
        raise ValidationError('Monto excede el límite permitido.')

    # Creación
    instancia = NuevoModelo.objects.create(
        id_empresa=empresa,
        id_usuario_creacion=usuario,
        **datos,
    )

    # Eventos
    emitir_evento_creado(instancia, usuario=usuario)

    return instancia
```

## Plantilla: Filter

```python
# apps/<modulo>/filters.py

import django_filters
from .models import NuevoModelo


class NuevoModeloFilter(django_filters.FilterSet):
    fecha_desde = django_filters.DateFilter(
        field_name='fecha_creacion',
        lookup_expr='gte',
    )
    fecha_hasta = django_filters.DateFilter(
        field_name='fecha_creacion',
        lookup_expr='lte',
    )
    monto_min = django_filters.NumberFilter(
        field_name='monto',
        lookup_expr='gte',
    )
    monto_max = django_filters.NumberFilter(
        field_name='monto',
        lookup_expr='lte',
    )

    class Meta:
        model = NuevoModelo
        fields = ['estado', 'cliente', 'fecha_desde', 'fecha_hasta', 'monto_min', 'monto_max']
```

## Plantilla: Tests de aislamiento

```python
# apps/<modulo>/tests/test_isolation.py

from rest_framework.test import APITestCase
from rest_framework import status
from apps.core.tests.factories import EmpresaFactory, UsuarioFactory
from apps.<modulo>.tests.factories import NuevoModeloFactory


class TestNuevoModeloAislamiento(APITestCase):
    """
    Test obligatorio: la empresa A nunca ve datos de la empresa B.
    """

    def setUp(self):
        self.empresa_a = EmpresaFactory.create()
        self.empresa_b = EmpresaFactory.create()
        self.user_a = UsuarioFactory.create(empresa=self.empresa_a)
        self.objeto_a = NuevoModeloFactory.create(id_empresa=self.empresa_a)
        self.objeto_b = NuevoModeloFactory.create(id_empresa=self.empresa_b)

    def test_listado_solo_empresa_propia(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get('/api/v1/<modulo>/nuevo-modelo/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [x['id_nuevo_modelo'] for x in response.data['results']]
        self.assertIn(str(self.objeto_a.id_nuevo_modelo), ids)
        self.assertNotIn(str(self.objeto_b.id_nuevo_modelo), ids)

    def test_detalle_otra_empresa_da_404(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(
            f'/api/v1/<modulo>/nuevo-modelo/{self.objeto_b.id_nuevo_modelo}/'
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_no_puede_modificar_otra_empresa(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.patch(
            f'/api/v1/<modulo>/nuevo-modelo/{self.objeto_b.id_nuevo_modelo}/',
            {'nombre': 'Hackeado'},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_no_puede_eliminar_otra_empresa(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.delete(
            f'/api/v1/<modulo>/nuevo-modelo/{self.objeto_b.id_nuevo_modelo}/'
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
```

## Plantilla: Factory

```python
# apps/<modulo>/tests/factories.py

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
        empresa=factory.SelfAttribute('..id_empresa'),
    )
    nombre = factory.Sequence(lambda n: f'Nuevo Modelo {n}')
    monto = 1000.00
    estado = 'PENDIENTE'
```

## Convenciones de nombres

- **Apps:** snake_case en singular o plural según corresponda. `ventas`, `inventario`, `cuentas_por_cobrar`.
- **Modelos:** PascalCase en singular. `Cliente`, `OrdenFabricacion`, `MovimientoInventario`.
- **Campos:** snake_case en español. `fecha_creacion`, `monto_total`, `id_empresa`.
- **PK:** `id_<modelo_singular>`. Ej: `id_cliente`, `id_orden_fabricacion`.
- **FK:** singular sin `id_`. Ej: `cliente`, `orden_fabricacion`. La columna SQL será `<campo>_id` automáticamente.
- **Choices:** TODO_MAYUSCULAS para los valores; nombres descriptivos para los labels en español.
- **URL routes:** kebab-case. `/api/v1/cuentas-por-cobrar/`.

## Checklist final antes de PR

Revisá uno por uno antes de cerrar tu trabajo:

- [ ] El modelo hereda de `BaseModel`.
- [ ] La PK es `UUIDField` con `default=uuid_v7`.
- [ ] No declaré `id_empresa`, `fecha_creacion`, etc. (vienen de BaseModel).
- [ ] Los campos de dinero usan `DecimalField` con precisión correcta (ver skill omni-decimal-money).
- [ ] Las FKs tienen `on_delete` explícito y `related_name`.
- [ ] El `Meta.indexes` incluye índices con `id_empresa` para queries frecuentes.
- [ ] El ViewSet hereda de `BaseModelViewSet`.
- [ ] La lógica de negocio está en `services.py`, no en el viewset.
- [ ] Hay test de aislamiento multi-tenant en `tests/test_isolation.py`.
- [ ] Hay factory en `tests/factories.py`.
- [ ] El URL está registrado en `urls.py` del módulo y en el router principal.
- [ ] Si la entidad emite eventos de negocio (Fase 0+), hay archivo `events.py`.
- [ ] Si la entidad expone capacidades MCP (Fase 0+), hay archivo `mcp.py`.

## Errores comunes a evitar

### Error 1: Crear modelo sin BaseModel
**Mal:** `class MiModelo(models.Model):`
**Bien:** `class MiModelo(BaseModel):`
**Por qué:** sin BaseModel no hay multi-tenant ni auditoría.

### Error 2: Usar `uuid.uuid4` en lugar de `uuid_v7`
**Mal:** `default=uuid.uuid4`
**Bien:** `default=uuid_v7` (helper de `core.utils`)
**Por qué:** decisión inmutable A-002. UUIDv7 es ordenable y mejora índices.

### Error 3: Lógica de negocio en el viewset
**Mal:** validaciones complejas dentro de `perform_create`.
**Bien:** validaciones en `services.py`, llamadas desde el viewset.
**Por qué:** los servicios se reusan; la lógica en views queda atada a HTTP.

### Error 4: Hard delete
**Mal:** `instance.delete()` que borra de la BD.
**Bien:** `instance.activo = False; instance.save()` o `instance.anular()`.
**Por qué:** regla R-CODE-6 del proyecto. Ver decisión inmutable A-005.

### Error 5: `null=True, blank=True` en campos lógicamente obligatorios
**Mal:** `cliente = models.ForeignKey('crm.Cliente', null=True, blank=True, ...)` cuando una venta sin cliente no tiene sentido.
**Bien:** `cliente = models.ForeignKey('crm.Cliente', ...)` (obligatorio).
**Por qué:** regla R-CODE-10. Si lo hacés opcional para "evitar problemas", introducís estados inválidos.

### Error 6: Olvidar `on_delete`
**Mal:** Django levanta error en versiones nuevas, pero copiar código viejo lo trae.
**Bien:** siempre `on_delete=models.PROTECT` para entidades de negocio, `CASCADE` solo para hijos verdaderos.
**Por qué:** PROTECT evita borrados accidentales que rompen integridad.

### Error 7: `Model.objects.all()` sin filtrar por empresa
**Mal:** dentro de un service, `NuevoModelo.objects.all()`.
**Bien:** `NuevoModelo.objects.filter(id_empresa=empresa)`.
**Por qué:** leak entre tenants. Ver skill omni-multi-tenant-isolation.

### Error 8: Factory sin SubFactory para empresa
**Mal:** la factory no asigna empresa, o asigna una distinta a la del usuario.
**Bien:** SubFactory con `SelfAttribute('..id_empresa')` para mantener consistencia.
**Por qué:** tests fallan o pasan por la razón equivocada.

### Error 9: Faltan índices con id_empresa
**Mal:** `models.Index(fields=['estado'])` sin id_empresa.
**Bien:** `models.Index(fields=['id_empresa', 'estado'])`.
**Por qué:** queries siempre filtran por empresa primero; los índices deben empezar con id_empresa.

### Error 10: Nombres mezclando español e inglés
**Mal:** `class Customer(BaseModel)` con campos en español.
**Bien:** `class Cliente(BaseModel)` con campos en español.
**Por qué:** consistencia. El proyecto es en español; los modelos también.

## Referencias

- Skill: `omni-multi-tenant-isolation` (para tests de aislamiento más profundos).
- Skill: `omni-decimal-money` (para campos monetarios).
- Skill: `omni-pr-discipline` (para preparar el PR).
- Documento: `OMNI_AI_NATIVE_EXECUTION_PLAN.md` Apéndice A (decisiones inmutables).

## Changelog

### v1.0 — Día 1
- Versión inicial.
