"""Fixtures compartidas de los tests de ``bots_ingest`` (usuario de servicio, bot, catálogo, calendario).

``test_ingest.py`` conserva sus propias definiciones (idénticas): las del módulo tienen prioridad.
Los archivos ``*_ramas.py`` usan estas, así no hay que importar fixtures entre módulos de test.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from tests.factories.comercial import ProductoFactory

from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from apps.activaciones.models import CalendarioActivacion, RecursoActivacion
from apps.bots_ingest.models import BotUsuario
from apps.ventas.models import DetallePrecio, ListaPrecio

from .helpers import TG


@pytest.fixture
def servicio(user_a):
    """Usuario de servicio con el permiso de ingesta."""
    user_a.user_permissions.add(
        Permission.objects.get(codename="ingestar", content_type__app_label="bots_ingest")
    )
    return user_a


@pytest.fixture
def api(servicio):
    c = APIClient()
    c.force_authenticate(user=servicio)
    return c


@pytest.fixture
def bot_usuario(servicio, empresa_a):
    return BotUsuario.objects.create(
        id_empresa=empresa_a, telegram_user_id=TG, usuario=servicio, nombre="Vendedor"
    )


@pytest.fixture
def catalogo(empresa_a, moneda_usd):
    """Lista de referencia con un producto a 12.50."""
    lista = ListaPrecio.objects.create(
        id_empresa=empresa_a,
        nombre="Lista 1",
        codigo="L1",
        es_referencia=True,
        id_moneda=moneda_usd,
    )
    prod = ProductoFactory(id_empresa=empresa_a, nombre_producto="Aceite 20W50", sku="AC-20W50")
    DetallePrecio.objects.create(id_lista=lista, id_producto=prod, precio=Decimal("12.50"))
    return lista, prod


@pytest.fixture
def calendario(empresa_a):
    """Calendario predeterminado con 2 promotoras y 3 igloos."""
    c = CalendarioActivacion.objects.create(
        id_empresa=empresa_a, nombre="Activaciones", es_predeterminado=True
    )
    RecursoActivacion.objects.create(
        id_empresa=empresa_a, calendario=c, codigo="promotoras", nombre="Promotoras", capacidad=2
    )
    RecursoActivacion.objects.create(
        id_empresa=empresa_a, calendario=c, codigo="igloos", nombre="Igloos", capacidad=3
    )
    return c
