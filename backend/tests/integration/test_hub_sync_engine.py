"""
Tests del SyncEngine (apps/integration_hub/services/sync_engine.py).

Usa un conector fake registrado en el registry — CERO red real.
Cubre: pull happy-path, dedup por checksum, actualización, errores de
conector, errores por registro, direcciones, _calcular_desde y upserts.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from django.utils import timezone

from apps.integration_hub.connectors.base import (
    BaseConnector,
    ConnectorConnectionError,
    SyncResult,
    TestConnectionResult,
)
from apps.integration_hub.connectors.registry import registry
from apps.integration_hub.models import (
    ConectorInstancia,
    ConectorProveedor,
    EntidadSincronizada,
    JobSincronizacion,
    LogDetalleSincronizacion,
)
from apps.integration_hub.services.sync_engine import SyncEngine

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class FakeConnector(BaseConnector):
    """Conector de prueba — datos controlados por atributos de clase."""

    PROVIDER_CODE = "fake_test"
    PROVIDER_NAME = "FakeTest"
    SUPPORTED_ENTITIES = ["contactos", "productos", "pagos", "empleados"]

    # Estado controlado por cada test
    registros: list = []
    error: Exception | None = None
    ultimo_desde = "NO_LLAMADO"

    def test_connection(self) -> TestConnectionResult:
        return TestConnectionResult(success=True, message="ok")

    def get_version_info(self) -> dict:
        return {}

    def _pull(self, desde=None):
        FakeConnector.ultimo_desde = desde
        if FakeConnector.error is not None:
            raise FakeConnector.error
        return list(FakeConnector.registros)

    def pull_contactos(self, desde=None, limite=500):
        return self._pull(desde)

    def pull_productos(self, desde=None, limite=500):
        return self._pull(desde)

    def pull_pagos(self, desde=None, limite=300):
        return self._pull(desde)


@pytest.fixture
def fake_registry():
    """Registra FakeConnector y limpia su estado al terminar."""
    registry.register(FakeConnector)
    FakeConnector.registros = []
    FakeConnector.error = None
    FakeConnector.ultimo_desde = "NO_LLAMADO"
    yield registry
    registry._registry.pop("fake_test", None)
    FakeConnector.registros = []
    FakeConnector.error = None


@pytest.fixture
def proveedor_fake(db):
    return ConectorProveedor.objects.create(
        codigo="fake_test",
        nombre="Fake Test",
        capacidades=["contactos", "productos", "pagos"],
    )


@pytest.fixture
def instancia_fake(db, empresa_a, proveedor_fake):
    return ConectorInstancia.objects.create(
        id_empresa=empresa_a,
        id_proveedor=proveedor_fake,
        nombre="Conector Fake",
        configuracion={"host": "fake.local", "user": "u", "api_key": "k"},
        estado="activo",
        entidades_activas=["contactos"],
    )


def _job(instancia, tipo="contactos", direccion="inbound", parametros=None):
    return JobSincronizacion.objects.create(
        id_instancia=instancia,
        tipo_entidad=tipo,
        direccion=direccion,
        estado="pendiente",
        parametros=parametros or {},
    )


def _contacto(idx, checksum="chk-1"):
    return {
        "id_externo": str(idx),
        "nombre": f"Contacto {idx}",
        "email": f"c{idx}@test.com",
        "_checksum": checksum,
    }


class TestEjecutarJobPullHappyPath:
    def test_pull_crea_registros_y_completa_job(self, fake_registry, instancia_fake):
        FakeConnector.registros = [_contacto(1), _contacto(2)]
        job = _job(instancia_fake)

        resultado = SyncEngine().ejecutar_job(job)

        assert resultado.total == 2
        assert resultado.creados == 2
        assert resultado.actualizados == 0
        assert resultado.omitidos == 0
        assert resultado.fallidos == 0
        assert resultado.procesados == 2
        assert resultado.exitoso is True

        job.refresh_from_db()
        assert job.estado == "completado"
        assert job.total_registros == 2
        assert job.creados == 2
        assert job.completado_en is not None
        assert job.iniciado_en is not None
        assert job.resumen_errores == []

        instancia_fake.refresh_from_db()
        assert instancia_fake.estado == "activo"
        assert instancia_fake.ultimo_sync is not None

    def test_pull_crea_mappings_entidad_sincronizada(self, fake_registry, instancia_fake):
        from apps.core.models import Contacto

        FakeConnector.registros = [_contacto(7, checksum="abc")]
        SyncEngine().ejecutar_job(_job(instancia_fake))

        mapping = EntidadSincronizada.objects.get(
            id_instancia=instancia_fake, tipo_entidad="contactos", id_externo="7"
        )
        # El upsert real crea un core.Contacto y el mapping apunta a su pk.
        contacto = Contacto.objects.get(
            id_empresa=instancia_fake.id_empresa, email="c7@test.com"
        )
        assert mapping.id_omni == str(contacto.pk)
        assert mapping.checksum == "abc"

    def test_pull_crea_logs_detalle_operacion_crear(self, fake_registry, instancia_fake):
        FakeConnector.registros = [_contacto(1)]
        job = _job(instancia_fake)
        SyncEngine().ejecutar_job(job)

        logs = list(LogDetalleSincronizacion.objects.filter(id_job=job))
        assert len(logs) == 1
        assert logs[0].operacion == "crear"
        assert logs[0].id_externo == "1"
        assert logs[0].resumen_externo == {"nombre": "Contacto 1"}


class TestDeduplicacionPorChecksum:
    def test_segunda_corrida_sin_cambios_completa_con_todo_omitido(
        self, fake_registry, instancia_fake
    ):
        """Regresión del BUG 'procesados': cuando TODOS los registros están sin
        cambios (estado estable de un sync incremental), el job completa con
        procesados == omitidos en vez de crashear y quedar 'en_progreso'.
        ``SyncResult.procesados`` ahora es una property derivada de los
        contadores y no puede quedar sin inicializar.
        """
        FakeConnector.registros = [_contacto(1, "chk-a"), _contacto(2, "chk-b")]
        SyncEngine().ejecutar_job(_job(instancia_fake))

        job2 = _job(instancia_fake)
        resultado = SyncEngine().ejecutar_job(job2)

        assert resultado.omitidos == 2
        assert resultado.procesados == 2
        ops = list(
            LogDetalleSincronizacion.objects.filter(id_job=job2).values_list(
                "operacion", flat=True
            )
        )
        assert ops == ["omitir", "omitir"]
        job2.refresh_from_db()
        assert job2.estado == "completado"
        assert job2.procesados == 2
        assert job2.omitidos == 2

    def test_omitido_mas_nuevo_completa_y_cuenta(self, fake_registry, instancia_fake):
        """Si el último registro de la corrida NO es omitido, 'procesados' sí se
        asigna y el job completa: cubre el branch 'omitir' sin gatillar el bug."""
        FakeConnector.registros = [_contacto(1, "chk-a")]
        SyncEngine().ejecutar_job(_job(instancia_fake))

        FakeConnector.registros = [_contacto(1, "chk-a"), _contacto(2, "chk-b")]
        job2 = _job(instancia_fake)
        resultado = SyncEngine().ejecutar_job(job2)

        assert resultado.omitidos == 1
        assert resultado.creados == 1
        assert resultado.procesados == 2
        job2.refresh_from_db()
        assert job2.estado == "completado"
        assert job2.omitidos == 1
        assert job2.creados == 1

    def test_checksum_cambiado_actualiza_registro(self, fake_registry, instancia_fake):
        FakeConnector.registros = [_contacto(1, "chk-v1")]
        SyncEngine().ejecutar_job(_job(instancia_fake))

        FakeConnector.registros = [_contacto(1, "chk-v2")]
        job2 = _job(instancia_fake)
        resultado = SyncEngine().ejecutar_job(job2)

        assert resultado.creados == 0
        assert resultado.actualizados == 1
        mapping = EntidadSincronizada.objects.get(
            id_instancia=instancia_fake, id_externo="1"
        )
        assert mapping.checksum == "chk-v2"
        log = LogDetalleSincronizacion.objects.get(id_job=job2)
        assert log.operacion == "actualizar"


class TestErroresDeConector:
    def test_proveedor_sin_conector_marca_fallido(self, fake_registry, empresa_a):
        proveedor = ConectorProveedor.objects.create(
            codigo="sin_conector", nombre="Sin Conector"
        )
        instancia = ConectorInstancia.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor,
            nombre="Sin Conector Inst",
            configuracion={},
        )
        job = _job(instancia)

        resultado = SyncEngine().ejecutar_job(job)

        assert resultado.creados == 0
        job.refresh_from_db()
        assert job.estado == "fallido"
        assert "No hay conector registrado" in job.resumen_errores[0]["error"]
        instancia.refresh_from_db()
        assert instancia.estado == "error"
        assert "No hay conector registrado" in instancia.mensaje_estado

    def test_entidad_no_soportada_marca_fallido(self, fake_registry, instancia_fake):
        job = _job(instancia_fake, tipo="inventario")

        SyncEngine().ejecutar_job(job)

        job.refresh_from_db()
        assert job.estado == "fallido"
        assert "no soporta" in job.resumen_errores[0]["error"]

    def test_direccion_outbound_no_implementada(self, fake_registry, instancia_fake):
        job = _job(instancia_fake, direccion="outbound")

        SyncEngine().ejecutar_job(job)

        job.refresh_from_db()
        assert job.estado == "fallido"
        assert "outbound no implementada" in job.resumen_errores[0]["error"]

    def test_entidad_soportada_sin_metodo_pull_marca_fallido(
        self, fake_registry, instancia_fake
    ):
        # "empleados" está en SUPPORTED_ENTITIES del fake pero no en PULL_METHODS.
        # Regresión del BUG 'procesados': el job ya no queda colgado en
        # 'en_progreso' — se marca fallido con el error registrado.
        job = _job(instancia_fake, tipo="empleados")

        SyncEngine().ejecutar_job(job)

        job.refresh_from_db()
        assert job.estado == "fallido"
        assert "sin método pull" in job.resumen_errores[0]["error"]

    def test_error_de_conexion_en_pull_marca_fallido(self, fake_registry, instancia_fake):
        # Regresión del BUG 'procesados': un fallo de conexión marca el job
        # fallido (y la instancia en error) en vez de dejarlo 'en_progreso'.
        FakeConnector.error = ConnectorConnectionError("Odoo caído")
        job = _job(instancia_fake)

        resultado = SyncEngine().ejecutar_job(job)

        assert resultado.fallidos == 1
        job.refresh_from_db()
        assert job.estado == "fallido"
        assert "Odoo caído" in job.resumen_errores[0]["error"]
        job.id_instancia.refresh_from_db()
        assert job.id_instancia.estado == "error"

    def test_error_inesperado_en_pull_marca_fallido(self, fake_registry, instancia_fake):
        # Mismo tratamiento para excepciones no tipadas del conector.
        FakeConnector.error = RuntimeError("kaboom")
        job = _job(instancia_fake)

        SyncEngine().ejecutar_job(job)

        job.refresh_from_db()
        assert job.estado == "fallido"
        assert "kaboom" in job.resumen_errores[0]["error"]

    def test_pull_vacio_completa_con_cero_procesados(self, fake_registry, instancia_fake):
        # Regresión del BUG 'procesados': pull vacío (nada que sincronizar)
        # completa el job con contadores en cero, sin AttributeError.
        FakeConnector.registros = []
        job = _job(instancia_fake)

        resultado = SyncEngine().ejecutar_job(job)

        assert resultado.procesados == 0
        job.refresh_from_db()
        assert job.estado == "completado"
        assert job.procesados == 0


class TestErroresPorRegistro:
    def test_excepcion_en_upsert_registra_fallido_y_log_error(
        self, fake_registry, instancia_fake
    ):
        FakeConnector.registros = [_contacto(1)]
        job = _job(instancia_fake)

        with patch.object(
            SyncEngine, "_upsert_en_omni", side_effect=RuntimeError("upsert roto")
        ):
            resultado = SyncEngine().ejecutar_job(job)

        assert resultado.fallidos == 1
        assert resultado.creados == 0
        assert resultado.errores[0] == {"id": "1", "error": "upsert roto"}

        job.refresh_from_db()
        assert job.estado == "completado_con_errores"
        assert job.fallidos == 1
        assert job.resumen_errores == [{"id": "1", "error": "upsert roto"}]

        log = LogDetalleSincronizacion.objects.get(id_job=job)
        assert log.operacion == "error"
        assert log.mensaje_error == "upsert roto"

    def test_upsert_retorna_none_cuenta_como_omitido(self, fake_registry, instancia_fake):
        FakeConnector.registros = [_contacto(1)]
        job = _job(instancia_fake)

        with patch.object(SyncEngine, "_upsert_en_omni", return_value=None):
            resultado = SyncEngine().ejecutar_job(job)

        assert resultado.omitidos == 1
        assert resultado.creados == 0
        assert resultado.fallidos == 0


class TestCalcularDesde:
    def test_desde_en_parametros_iso(self, fake_registry, instancia_fake):
        job = _job(instancia_fake, parametros={"desde": "2024-06-01T00:00:00"})
        desde = SyncEngine()._calcular_desde(job)
        assert desde == datetime(2024, 6, 1, 0, 0, 0)

    def test_desde_invalido_cae_a_ultimo_job(self, fake_registry, instancia_fake):
        previo = _job(instancia_fake)
        momento = timezone.now() - timedelta(hours=3)
        JobSincronizacion.objects.filter(pk=previo.pk).update(
            estado="completado", completado_en=momento
        )

        job = _job(instancia_fake, parametros={"desde": "no-es-fecha"})
        desde = SyncEngine()._calcular_desde(job)
        assert desde == momento

    def test_sin_historial_retorna_none(self, fake_registry, instancia_fake):
        job = _job(instancia_fake)
        assert SyncEngine()._calcular_desde(job) is None

    def test_pull_incremental_usa_completado_en_del_ultimo_job(
        self, fake_registry, instancia_fake
    ):
        FakeConnector.registros = [_contacto(1)]
        job1 = _job(instancia_fake)
        SyncEngine().ejecutar_job(job1)
        job1.refresh_from_db()

        FakeConnector.registros = [_contacto(2)]
        job2 = _job(instancia_fake)
        SyncEngine().ejecutar_job(job2)

        assert FakeConnector.ultimo_desde == job1.completado_en

    def test_jobs_fallidos_no_cuentan_para_incremental(self, fake_registry, instancia_fake):
        previo = _job(instancia_fake)
        JobSincronizacion.objects.filter(pk=previo.pk).update(
            estado="fallido", completado_en=timezone.now()
        )
        job = _job(instancia_fake)
        assert SyncEngine()._calcular_desde(job) is None


class TestUpsertEnOmni:
    def test_entidad_sin_handler_retorna_id_externo(self, fake_registry, instancia_fake):
        engine = SyncEngine()
        resultado = engine._upsert_en_omni("pagos", {"id_externo": "77"}, instancia_fake)
        assert resultado == "77"

    def test_entidad_sin_handler_y_sin_id_retorna_vacio(self, fake_registry, instancia_fake):
        engine = SyncEngine()
        assert engine._upsert_en_omni("pagos", {}, instancia_fake) == ""

    def test_upsert_contacto_crea_y_actualiza_core_contacto(
        self, fake_registry, instancia_fake
    ):
        """Regresión del BUG de upserts: antes importaba apps.crm.models.Contacto
        (inexistente) y degradaba a placeholder; ahora upsertea core.Contacto."""
        from apps.core.models import Contacto

        engine = SyncEngine()
        datos = {
            "id_externo": "5",
            "nombre": "Proveedor X",
            "email": "prov@x.com",
            "identificador_fiscal": "J-12345678",
            "es_proveedor": True,
        }
        pk = engine._upsert_contacto(datos, instancia_fake)
        contacto = Contacto.objects.get(pk=pk)
        assert contacto.id_empresa == instancia_fake.id_empresa
        assert contacto.nombre == "Proveedor X"
        assert contacto.rif == "J-12345678"
        assert contacto.es_proveedor is True

        # Segunda corrida con el mismo RIF: actualiza, no duplica.
        datos["nombre"] = "Proveedor X Renombrado"
        pk2 = engine._upsert_contacto(datos, instancia_fake)
        assert pk2 == pk
        assert Contacto.objects.filter(id_empresa=instancia_fake.id_empresa).count() == 1
        contacto.refresh_from_db()
        assert contacto.nombre == "Proveedor X Renombrado"

    def test_upsert_producto_crea_con_fks_reales_y_actualiza(
        self, fake_registry, instancia_fake, moneda_usd
    ):
        """Regresión del BUG de upserts: _upsert_producto usaba campos
        inexistentes (codigo_interno/precio_venta/costo) — ahora mapea al
        modelo real con Decimal y resuelve las FKs obligatorias."""
        from decimal import Decimal

        from apps.inventario.models import Producto

        engine = SyncEngine()
        datos = {
            "id_externo": "9",
            "nombre": "Widget",
            "codigo_interno": "SKU-9",
            "precio_venta": "12.50",
            "costo": "7.25",
        }
        pk = engine._upsert_producto(datos, instancia_fake)
        producto = Producto.objects.get(pk=pk)
        assert producto.id_empresa == instancia_fake.id_empresa
        assert producto.nombre_producto == "Widget"
        assert producto.sku == "SKU-9"
        assert producto.precio_venta_sugerido == Decimal("12.50")
        assert producto.costo_promedio == Decimal("7.25")
        assert producto.id_categoria_id is not None
        assert producto.id_unidad_medida_base_id is not None
        assert producto.id_moneda_precio_id is not None

        datos["precio_venta"] = "15.00"
        pk2 = engine._upsert_producto(datos, instancia_fake)
        assert pk2 == pk
        producto.refresh_from_db()
        assert producto.precio_venta_sugerido == Decimal("15.00")
        assert Producto.objects.filter(id_empresa=instancia_fake.id_empresa).count() == 1

    def test_upsert_producto_sin_sku_es_idempotente_por_nombre(
        self, fake_registry, instancia_fake, moneda_usd
    ):
        """Sin SKU externo, la clave de idempotencia cae al nombre dentro del
        tenant: re-sincronizar no duplica el producto (y sku queda None sin
        violar el unique_together, que en Postgres admite múltiples NULL)."""
        from decimal import Decimal

        from apps.inventario.models import Producto

        engine = SyncEngine()
        datos = {
            "id_externo": "10",
            "nombre": "Widget sin SKU",
            "precio_venta": "5.00",
            "costo": "2.00",
        }
        pk = engine._upsert_producto(datos, instancia_fake)
        producto = Producto.objects.get(pk=pk)
        assert producto.sku is None

        datos["precio_venta"] = "6.00"
        pk2 = engine._upsert_producto(datos, instancia_fake)
        assert pk2 == pk
        producto.refresh_from_db()
        assert producto.precio_venta_sugerido == Decimal("6.00")
        assert (
            Producto.objects.filter(
                id_empresa=instancia_fake.id_empresa, nombre_producto="Widget sin SKU"
            ).count()
            == 1
        )

    def test_upsert_producto_sin_moneda_se_omite(self, fake_registry, instancia_fake):
        """Sin ninguna Moneda configurada no se puede satisfacer la FK
        obligatoria id_moneda_precio: el registro se omite (None)."""
        from apps.finanzas.models import Moneda

        Moneda.objects.all().delete()
        engine = SyncEngine()
        resultado = engine._upsert_producto(
            {"id_externo": "9", "nombre": "Widget", "codigo_interno": "SKU-9"},
            instancia_fake,
        )
        assert resultado is None


class TestSyncResult:
    def test_agregar_error_limita_a_100_pero_cuenta_todos(self):
        resultado = SyncResult(tipo_entidad="contactos")
        for i in range(105):
            resultado.agregar_error(str(i), "e")
        assert len(resultado.errores) == 100
        assert resultado.fallidos == 105
        assert resultado.exitoso is False

    def test_exitoso_sin_fallidos(self):
        resultado = SyncResult(tipo_entidad="contactos", creados=3)
        assert resultado.exitoso is True


class TestUpsertPedidoVenta:
    """Fase 2 — persistencia de pedidos de venta en ventas.Pedido."""

    def _pedido(self, **over):
        datos = {
            "id_externo": "55",
            "numero": "SO0001",
            "cliente_id_externo": "42",
            "cliente_nombre": "Cliente Test",
            "fecha_pedido": "2024-03-15",
            "estado": "confirmado",
            "lineas": [],
        }
        datos.update(over)
        return datos

    def test_crea_pedido_y_autocrea_cliente(self, instancia_fake):
        from apps.crm.models import Cliente
        from apps.ventas.models import Pedido

        pk = SyncEngine()._upsert_pedido_venta(self._pedido(), instancia_fake)

        assert pk
        ped = Pedido.objects.get(pk=pk)
        assert ped.numero_pedido == "SO0001"
        assert ped.estado == "APROBADO"  # 'confirmado' → APROBADO
        cli = Cliente.objects.get(
            id_empresa=instancia_fake.id_empresa, referencia_externa="42"
        )
        assert cli.razon_social == "Cliente Test"
        assert ped.id_cliente_id == cli.pk

    def test_idempotente_por_numero(self, instancia_fake):
        from apps.crm.models import Cliente
        from apps.ventas.models import Pedido

        eng = SyncEngine()
        eng._upsert_pedido_venta(self._pedido(), instancia_fake)
        eng._upsert_pedido_venta(self._pedido(estado="cancelado"), instancia_fake)

        assert (
            Pedido.objects.filter(
                id_empresa=instancia_fake.id_empresa, numero_pedido="SO0001"
            ).count()
            == 1
        )
        assert (
            Cliente.objects.filter(
                id_empresa=instancia_fake.id_empresa, referencia_externa="42"
            ).count()
            == 1
        )
        ped = Pedido.objects.get(
            id_empresa=instancia_fake.id_empresa, numero_pedido="SO0001"
        )
        assert ped.estado == "ANULADO"  # se actualizó

    def test_sin_numero_omite(self, instancia_fake):
        assert SyncEngine()._upsert_pedido_venta(
            self._pedido(numero=""), instancia_fake
        ) is None

    def test_sin_cliente_omite(self, instancia_fake):
        assert SyncEngine()._upsert_pedido_venta(
            self._pedido(cliente_id_externo="", cliente_nombre=""), instancia_fake
        ) is None

    def test_linea_con_producto_no_sincronizado_se_omite(self, instancia_fake):
        from apps.ventas.models import Pedido

        datos = self._pedido(
            lineas=[{
                "product_id": [10, "X"],
                "product_uom_qty": 2,
                "price_unit": "5",
                "price_subtotal": "10",
            }]
        )
        pk = SyncEngine()._upsert_pedido_venta(datos, instancia_fake)
        ped = Pedido.objects.get(pk=pk)
        assert ped.detalles.count() == 0  # producto no sincronizado → línea omitida

    def test_linea_con_producto_sincronizado_se_crea(self, instancia_fake):
        from decimal import Decimal

        from apps.finanzas.models import Moneda
        from apps.ventas.models import Pedido

        Moneda.objects.get_or_create(
            codigo_iso="USD",
            defaults={
                "nombre": "Dólar",
                "simbolo": "$",
                "empresa": instancia_fake.id_empresa,
            },
        )
        eng = SyncEngine()
        # Sembrar producto: crea inventario.Producto + mapping productos:10
        eng.ingerir_en_omni(
            instancia_fake,
            "productos",
            [{"id_externo": "10", "nombre": "Prod 10", "codigo_interno": "P10", "_checksum": "p"}],
        )
        datos = self._pedido(
            lineas=[{
                "product_id": [10, "Prod 10"],
                "product_uom_qty": 2,
                "price_unit": "5",
                "price_subtotal": "10",
            }]
        )
        pk = eng._upsert_pedido_venta(datos, instancia_fake)
        ped = Pedido.objects.get(pk=pk)
        assert ped.detalles.count() == 1
        det = ped.detalles.first()
        assert det.cantidad == Decimal("2")
        assert det.subtotal == Decimal("10")


class TestUpsertPedidoVentaRamas:
    """Cobertura de ramas de resolución de cliente/producto (Fase 2)."""

    def _pedido(self, **over):
        datos = {
            "id_externo": "55", "numero": "SO0009",
            "cliente_id_externo": "42", "cliente_nombre": "Cliente Test",
            "fecha_pedido": "2024-03-15", "estado": "confirmado", "lineas": [],
        }
        datos.update(over)
        return datos

    def test_safe_decimal_money_invalido_es_cero(self):
        from decimal import Decimal

        assert SyncEngine._safe_decimal_money("no-num") == Decimal("0")
        assert SyncEngine._safe_decimal_money(None) == Decimal("0")
        assert SyncEngine._safe_decimal_money("12.5") == Decimal("12.5")

    def test_autocrea_cliente_desde_contacto_sincronizado(self, instancia_fake):
        """Si el contacto ya fue sincronizado, enlaza y reutiliza su RIF."""
        from apps.crm.models import Cliente
        from apps.ventas.models import Pedido

        eng = SyncEngine()
        # Sembrar contacto sincronizado (mapping contactos:42 → core.Contacto con RIF)
        eng.ingerir_en_omni(
            instancia_fake,
            "contactos",
            [{
                "id_externo": "42",
                "nombre": "Cliente Test",
                "identificador_fiscal": "J-12345678-9",
                "email": "c@x.com",
                "_checksum": "c",
            }],
        )
        pk = eng._upsert_pedido_venta(self._pedido(), instancia_fake)
        ped = Pedido.objects.get(pk=pk)
        cli = Cliente.objects.get(pk=ped.id_cliente_id)
        assert cli.contacto is not None           # enlazado al contacto
        assert cli.rif == "J-12345678-9"          # RIF reutilizado del contacto

    def test_reutiliza_cliente_existente_por_contacto(self, instancia_fake):
        """Si ya existe un Cliente enlazado al contacto, se reutiliza (no duplica)."""
        from apps.core.models import Contacto
        from apps.crm.models import Cliente
        from apps.integration_hub.models import EntidadSincronizada

        empresa = instancia_fake.id_empresa
        eng = SyncEngine()
        eng.ingerir_en_omni(
            instancia_fake,
            "contactos",
            [{"id_externo": "42", "nombre": "Cliente Test",
              "identificador_fiscal": "J-1", "_checksum": "c"}],
        )
        mapping = EntidadSincronizada.objects.get(
            id_instancia=instancia_fake, tipo_entidad="contactos", id_externo="42"
        )
        contacto = Contacto.objects.get(pk=mapping.id_omni)
        # Cliente pre-existente enlazado al contacto, SIN referencia_externa.
        pre = Cliente.objects.create(
            id_empresa=empresa, razon_social="Pre", rif="J-1", contacto=contacto
        )

        cli = eng._resolver_o_crear_cliente(self._pedido(), instancia_fake)
        assert cli.pk == pre.pk  # reutilizado por enlace de contacto

    def test_resolver_producto_escalar_y_vacio(self, instancia_fake):
        eng = SyncEngine()
        # product_id escalar (no lista) y sin mapeo → None
        assert eng._resolver_producto_mapeado(10, instancia_fake) is None
        # product_id vacío/ausente → None
        assert eng._resolver_producto_mapeado(None, instancia_fake) is None
        assert eng._resolver_producto_mapeado([], instancia_fake) is None


class TestUpsertPedidoCompra:
    """Fase 2 — persistencia de órdenes de compra en compras.OrdenCompra."""

    def _orden(self, **over):
        datos = {
            "id_externo": "77", "numero": "PO0001",
            "proveedor_id_externo": "88", "proveedor_nombre": "Prov Test",
            "fecha_pedido": "2024-04-01", "estado": "purchase", "lineas": [],
        }
        datos.update(over)
        return datos

    def test_crea_orden_y_autocrea_proveedor(self, instancia_fake):
        from apps.compras.models import OrdenCompra
        from apps.proveedores.models import Proveedor

        pk = SyncEngine()._upsert_pedido_compra(self._orden(), instancia_fake)
        assert pk
        oc = OrdenCompra.objects.get(pk=pk)
        assert oc.numero_orden == "PO0001"
        assert oc.estado == "APROBADA"  # 'purchase' → APROBADA
        prov = Proveedor.objects.get(
            id_empresa=instancia_fake.id_empresa, referencia_externa="88"
        )
        assert prov.razon_social == "Prov Test"
        assert oc.id_proveedor_id == prov.pk

    def test_idempotente_por_numero(self, instancia_fake):
        from apps.compras.models import OrdenCompra
        from apps.proveedores.models import Proveedor

        eng = SyncEngine()
        eng._upsert_pedido_compra(self._orden(), instancia_fake)
        eng._upsert_pedido_compra(self._orden(estado="cancel"), instancia_fake)
        assert OrdenCompra.objects.filter(
            id_empresa=instancia_fake.id_empresa, numero_orden="PO0001"
        ).count() == 1
        assert Proveedor.objects.filter(
            id_empresa=instancia_fake.id_empresa, referencia_externa="88"
        ).count() == 1
        oc = OrdenCompra.objects.get(
            id_empresa=instancia_fake.id_empresa, numero_orden="PO0001"
        )
        assert oc.estado == "ANULADA"

    def test_sin_numero_omite(self, instancia_fake):
        assert SyncEngine()._upsert_pedido_compra(
            self._orden(numero=""), instancia_fake
        ) is None

    def test_sin_proveedor_omite(self, instancia_fake):
        assert SyncEngine()._upsert_pedido_compra(
            self._orden(proveedor_id_externo="", proveedor_nombre=""), instancia_fake
        ) is None

    def test_linea_producto_no_sincronizado_se_omite(self, instancia_fake):
        from apps.compras.models import OrdenCompra

        datos = self._orden(
            lineas=[{"product_id": [10, "X"], "product_qty": 3,
                     "price_unit": "4", "price_subtotal": "12"}]
        )
        pk = SyncEngine()._upsert_pedido_compra(datos, instancia_fake)
        assert OrdenCompra.objects.get(pk=pk).detalles.count() == 0

    def test_linea_producto_sincronizado_se_crea(self, instancia_fake):
        from decimal import Decimal

        from apps.compras.models import OrdenCompra
        from apps.finanzas.models import Moneda

        Moneda.objects.get_or_create(
            codigo_iso="USD",
            defaults={"nombre": "Dólar", "simbolo": "$",
                      "empresa": instancia_fake.id_empresa},
        )
        eng = SyncEngine()
        eng.ingerir_en_omni(
            instancia_fake, "productos",
            [{"id_externo": "10", "nombre": "Prod 10", "codigo_interno": "P10", "_checksum": "p"}],
        )
        datos = self._orden(
            lineas=[{"product_id": [10, "Prod 10"], "product_qty": 3,
                     "price_unit": "4", "price_subtotal": "12"}]
        )
        oc = OrdenCompra.objects.get(pk=eng._upsert_pedido_compra(datos, instancia_fake))
        assert oc.detalles.count() == 1
        det = oc.detalles.first()
        assert det.cantidad == Decimal("3")
        assert det.subtotal == Decimal("12")

    def test_autocrea_proveedor_desde_contacto_sincronizado(self, instancia_fake):
        from apps.compras.models import OrdenCompra
        from apps.proveedores.models import Proveedor

        eng = SyncEngine()
        eng.ingerir_en_omni(
            instancia_fake, "contactos",
            [{"id_externo": "88", "nombre": "Prov Test",
              "identificador_fiscal": "J-77777777-7", "_checksum": "c"}],
        )
        oc = OrdenCompra.objects.get(pk=eng._upsert_pedido_compra(self._orden(), instancia_fake))
        prov = Proveedor.objects.get(pk=oc.id_proveedor_id)
        assert prov.contacto is not None
        assert prov.rif == "J-77777777-7"

    def test_reutiliza_proveedor_existente_por_contacto(self, instancia_fake):
        from apps.core.models import Contacto
        from apps.integration_hub.models import EntidadSincronizada
        from apps.proveedores.models import Proveedor

        empresa = instancia_fake.id_empresa
        eng = SyncEngine()
        eng.ingerir_en_omni(
            instancia_fake, "contactos",
            [{"id_externo": "88", "nombre": "Prov Test",
              "identificador_fiscal": "J-7", "_checksum": "c"}],
        )
        mapping = EntidadSincronizada.objects.get(
            id_instancia=instancia_fake, tipo_entidad="contactos", id_externo="88"
        )
        contacto = Contacto.objects.get(pk=mapping.id_omni)
        pre = Proveedor.objects.create(
            id_empresa=empresa, razon_social="Pre", rif="J-7", contacto=contacto
        )
        prov = eng._resolver_o_crear_proveedor(self._orden(), instancia_fake)
        assert prov.pk == pre.pk
