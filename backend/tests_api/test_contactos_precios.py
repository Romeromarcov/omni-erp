"""
Tests para M1 (Contactos Unificados) y M4 (Listas de Precios).
"""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient


# ── Fixtures compartidas ──────────────────────────────────────────────────────


@pytest.fixture
def unidad(db, empresa_a):
    from apps.inventario.models import UnidadMedida

    return UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad", abreviatura="UN-CP", tipo="CANTIDAD"
    )


@pytest.fixture
def categoria(db, empresa_a):
    from apps.inventario.models import CategoriaProducto

    return CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="General CP")


@pytest.fixture
def producto(db, empresa_a, unidad, categoria, moneda_usd):
    from apps.inventario.models import Producto

    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Producto Test CP",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        precio_venta_sugerido=Decimal("50.00"),
    )


@pytest.fixture
def capability_token(db, empresa_a):
    from apps.core.models import CapabilityToken

    return CapabilityToken.objects.create(
        empresa=empresa_a,
        nombre="Token test contactos",
        scopes=["*"],
        expires_at=timezone.now() + timedelta(hours=1),
    )


# ── Fixtures propias ──────────────────────────────────────────────────────────


@pytest.fixture
def moneda(db, empresa_a):
    from apps.finanzas.models import Moneda

    moneda, _ = Moneda.objects.get_or_create(
        codigo_iso="VED",
        defaults={
            "empresa": empresa_a,
            "nombre": "Bolívar Digital",
            "simbolo": "Bs.",
            "tipo_moneda": "fiat",
        },
    )
    return moneda


@pytest.fixture
def lista_referencia(db, empresa_a, moneda):
    from apps.ventas.models import ListaPrecio

    return ListaPrecio.objects.create(
        id_empresa=empresa_a,
        nombre="Lista 1",
        codigo="LISTA1",
        es_referencia=True,
        id_moneda=moneda,
    )


@pytest.fixture
def lista_mayoreo(db, empresa_a, moneda):
    from apps.ventas.models import ListaPrecio

    return ListaPrecio.objects.create(
        id_empresa=empresa_a,
        nombre="Mayoreo",
        codigo="MAYOREO",
        es_referencia=False,
        id_moneda=moneda,
    )


@pytest.fixture
def contacto_cliente(db, empresa_a):
    from apps.core.models import Contacto

    return Contacto.objects.create(
        id_empresa=empresa_a,
        tipo_persona="JURIDICA",
        nombre="Distribuidora Ejemplo",
        rif="J-12345678",
        es_cliente=True,
        tipo_credito="CREDITO",
        limite_credito=Decimal("50000.00"),
        dias_credito=30,
    )


@pytest.fixture
def contacto_proveedor(db, empresa_a):
    from apps.core.models import Contacto

    return Contacto.objects.create(
        id_empresa=empresa_a,
        tipo_persona="JURIDICA",
        nombre="Proveedor ABC",
        rif="J-98765432",
        es_proveedor=True,
    )


@pytest.fixture
def contacto_dual(db, empresa_a):
    """Un contacto que es cliente Y proveedor simultáneamente."""
    from apps.core.models import Contacto

    return Contacto.objects.create(
        id_empresa=empresa_a,
        tipo_persona="JURIDICA",
        nombre="Empresa Dual",
        rif="J-11111111",
        es_cliente=True,
        es_proveedor=True,
    )


# ── M1: Modelo Contacto ───────────────────────────────────────────────────────


class TestContactoModelo:
    def test_contacto_puede_tener_multiples_roles(self, contacto_dual):
        assert contacto_dual.es_cliente is True
        assert contacto_dual.es_proveedor is True
        assert contacto_dual.es_empleado is False

    def test_str_juridica_usa_nombre(self, contacto_cliente):
        assert str(contacto_cliente) == "Distribuidora Ejemplo"

    def test_str_natural_usa_nombre_apellido(self, db, empresa_a):
        from apps.core.models import Contacto

        c = Contacto.objects.create(
            id_empresa=empresa_a,
            tipo_persona="NATURAL",
            nombre="Juan",
            apellido="Pérez",
            cedula="V-12345678",
            es_empleado=True,
        )
        assert str(c) == "Juan Pérez"
        assert c.nombre_completo == "Juan Pérez"

    def test_nombre_comercial_tiene_prioridad_en_str(self, db, empresa_a):
        from apps.core.models import Contacto

        c = Contacto.objects.create(
            id_empresa=empresa_a,
            nombre="Empresa S.A.",
            nombre_comercial="Marca Famosa",
            rif="J-22222222",
        )
        assert str(c) == "Marca Famosa"

    def test_aislamiento_multi_tenant(self, db, empresa_a, empresa_b):
        from apps.core.models import Contacto

        c_a = Contacto.objects.create(id_empresa=empresa_a, nombre="Cliente A", rif="J-11111111")
        c_b = Contacto.objects.create(id_empresa=empresa_b, nombre="Cliente B", rif="J-22222222")

        assert Contacto.objects.filter(id_empresa=empresa_a).count() >= 1
        assert not Contacto.objects.filter(id_empresa=empresa_a, id_contacto=c_b.id_contacto).exists()

    def test_contacto_enlaza_cliente_legacy(self, db, empresa_a, contacto_cliente):
        from apps.crm.models import Cliente

        cliente = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Distribuidora Ejemplo",
            rif="J-12345678",
            tipo_cliente="CREDITO",
            dias_credito=30,
            contacto=contacto_cliente,
        )
        assert cliente.contacto == contacto_cliente
        assert contacto_cliente.cliente == cliente

    def test_contacto_enlaza_proveedor_legacy(self, db, empresa_a, contacto_proveedor):
        from apps.proveedores.models import Proveedor

        proveedor = Proveedor.objects.create(
            id_empresa=empresa_a,
            razon_social="Proveedor ABC",
            rif="J-98765432",
            contacto=contacto_proveedor,
        )
        assert proveedor.contacto == contacto_proveedor
        assert contacto_proveedor.proveedor == proveedor


# ── M1: ContactoViewSet ───────────────────────────────────────────────────────


class TestContactoViewSet:
    def test_crear_contacto(self, db, empresa_a, user_a, moneda):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.post(
            "/api/core/contactos/",
            {
                "nombre": "Nuevo Cliente",
                "rif": "J-99999999",
                "tipo_persona": "JURIDICA",
                "es_cliente": True,
                "tipo_credito": "CONTADO",
            },
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["nombre"] == "Nuevo Cliente"
        assert resp.data["es_cliente"] is True

    def test_listar_solo_empresa_propia(self, db, empresa_a, empresa_b, user_a, contacto_cliente, contacto_proveedor):
        from apps.core.models import Contacto

        Contacto.objects.create(id_empresa=empresa_b, nombre="Otro Tenant", rif="J-99999999")

        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get("/api/core/contactos/")
        assert resp.status_code == 200
        ids = [r["id_contacto"] for r in resp.data["results"]]
        assert str(contacto_cliente.id_contacto) in ids
        assert not any(str(empresa_b.id_empresa) in str(i) for i in ids)

    def test_filtrar_por_rol_cliente(self, db, empresa_a, user_a, contacto_cliente, contacto_proveedor):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get("/api/core/contactos/?es_cliente=true")
        assert resp.status_code == 200
        nombres = [r["nombre"] for r in resp.data["results"]]
        assert "Distribuidora Ejemplo" in nombres
        assert "Proveedor ABC" not in nombres

    def test_filtrar_por_rol_proveedor(self, db, empresa_a, user_a, contacto_cliente, contacto_proveedor):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get("/api/core/contactos/?es_proveedor=true")
        assert resp.status_code == 200
        nombres = [r["nombre"] for r in resp.data["results"]]
        assert "Proveedor ABC" in nombres
        assert "Distribuidora Ejemplo" not in nombres

    def test_busqueda_por_rif(self, db, empresa_a, user_a, contacto_cliente):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get("/api/core/contactos/?search=J-12345678")
        assert resp.status_code == 200
        assert resp.data["count"] >= 1
        assert resp.data["results"][0]["rif"] == "J-12345678"


# ── M4: Listas de Precios ─────────────────────────────────────────────────────


class TestListaPrecios:
    def test_crear_lista_referencia_y_detalle(self, db, lista_referencia, producto):
        from apps.ventas.models import DetallePrecio

        dp = DetallePrecio.objects.create(
            id_lista=lista_referencia,
            id_producto=producto,
            precio=Decimal("100.00"),
            precio_minimo=Decimal("90.00"),
        )
        assert dp.precio == Decimal("100.00")
        assert dp.id_lista.es_referencia is True

    def test_unique_together_lista_producto(self, db, lista_referencia, producto):
        from django.db import IntegrityError

        from apps.ventas.models import DetallePrecio

        DetallePrecio.objects.create(id_lista=lista_referencia, id_producto=producto, precio=Decimal("100.00"))
        with pytest.raises(IntegrityError):
            DetallePrecio.objects.create(id_lista=lista_referencia, id_producto=producto, precio=Decimal("200.00"))


class TestObtenerPrecio:
    def test_fallback_precio_sugerido(self, db, empresa_a, producto):
        """Sin listas configuradas, retorna precio_venta_sugerido del producto."""
        from apps.ventas.services import obtener_precio

        precio = obtener_precio(producto, empresa_a)
        assert precio == Decimal(str(producto.precio_venta_sugerido))

    def test_usa_lista_referencia(self, db, empresa_a, producto, lista_referencia):
        from apps.ventas.models import DetallePrecio
        from apps.ventas.services import obtener_precio

        DetallePrecio.objects.create(
            id_lista=lista_referencia, id_producto=producto, precio=Decimal("150.00")
        )
        precio = obtener_precio(producto, empresa_a)
        assert precio == Decimal("150.00")

    def test_lista_contacto_tiene_prioridad_sobre_referencia(
        self, db, empresa_a, producto, lista_referencia, lista_mayoreo, contacto_cliente
    ):
        from apps.ventas.models import DetallePrecio
        from apps.ventas.services import obtener_precio

        DetallePrecio.objects.create(id_lista=lista_referencia, id_producto=producto, precio=Decimal("150.00"))
        DetallePrecio.objects.create(id_lista=lista_mayoreo, id_producto=producto, precio=Decimal("120.00"))

        contacto_cliente.lista_precio = lista_mayoreo
        contacto_cliente.save(update_fields=["lista_precio"])

        precio = obtener_precio(producto, empresa_a, contacto=contacto_cliente)
        assert precio == Decimal("120.00")  # lista del contacto, no la referencia

    def test_fallback_a_referencia_si_contacto_sin_lista(
        self, db, empresa_a, producto, lista_referencia, contacto_cliente
    ):
        from apps.ventas.models import DetallePrecio
        from apps.ventas.services import obtener_precio

        DetallePrecio.objects.create(id_lista=lista_referencia, id_producto=producto, precio=Decimal("150.00"))
        # contacto_cliente.lista_precio es None por defecto

        precio = obtener_precio(producto, empresa_a, contacto=contacto_cliente)
        assert precio == Decimal("150.00")

    def test_precio_vencido_no_aplica(self, db, empresa_a, producto, lista_referencia):
        from datetime import date, timedelta

        from apps.ventas.models import DetallePrecio
        from apps.ventas.services import obtener_precio

        # Precio vencido ayer
        DetallePrecio.objects.create(
            id_lista=lista_referencia,
            id_producto=producto,
            precio=Decimal("999.00"),
            vigente_desde=date(2020, 1, 1),
            vigente_hasta=date(2020, 12, 31),
        )
        # No hay precio vigente → cae al precio sugerido del producto
        precio = obtener_precio(producto, empresa_a)
        assert precio == Decimal(str(producto.precio_venta_sugerido))


# ── MCP Tool: omni_buscar_contacto ────────────────────────────────────────────


class TestMCPBuscarContacto:
    def test_buscar_por_nombre(self, db, empresa_a, contacto_cliente, capability_token):
        from apps.core.mcp_server import omni_buscar_contacto

        resultado = omni_buscar_contacto(
            capability_token=str(capability_token.token),
            empresa_id=str(empresa_a.id_empresa),
            query="Distribuidora",
        )
        assert len(resultado) >= 1
        assert resultado[0]["nombre"] == "Distribuidora Ejemplo"

    def test_filtrar_por_rol_proveedor(
        self, db, empresa_a, contacto_cliente, contacto_proveedor, capability_token
    ):
        from apps.core.mcp_server import omni_buscar_contacto

        resultado = omni_buscar_contacto(
            capability_token=str(capability_token.token),
            empresa_id=str(empresa_a.id_empresa),
            rol="proveedor",
        )
        ids = [r["id_contacto"] for r in resultado]
        assert str(contacto_proveedor.id_contacto) in ids
        assert str(contacto_cliente.id_contacto) not in ids

    def test_aislamiento_tenant_en_busqueda(
        self, db, empresa_a, empresa_b, contacto_cliente, capability_token
    ):
        from apps.core.models import Contacto
        from apps.core.mcp_server import omni_buscar_contacto

        Contacto.objects.create(id_empresa=empresa_b, nombre="Distribuidora Otro Tenant", rif="J-99999999")

        resultado = omni_buscar_contacto(
            capability_token=str(capability_token.token),
            empresa_id=str(empresa_a.id_empresa),
            query="Distribuidora",
        )
        # Solo retorna la de empresa_a, no la de empresa_b
        assert all(r["id_contacto"] == str(contacto_cliente.id_contacto) for r in resultado)
