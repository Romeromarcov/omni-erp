"""
Backfill de cobertura — apps/ventas/serializers.py (plan "Cero Dudas", COV/ventas).

Cubre las ramas no ejercitadas por los tests de flujo:

- ``PedidoSerializer.validate`` (fecha_cierre_estimada < fecha_pedido).
- ``PedidoSerializer.create``: generación atómica del número de pedido
  (prefijo GEN-CAJGEN-, secuencia incremental, regex de 6 dígitos),
  creación de detalles anidados y registro del usuario en documento_json.
- ``to_representation``: cliente anidado en los 7 serializers de documentos,
  producto anidado en ``DetallePedidoNestedSerializer``, usuario desde
  ``documento_json``.
- Validaciones de campo de los serializers de detalle (cantidad, precio).

BUG documentado: la rama de "sesión activa" de ``PedidoSerializer.create`` es
inalcanzable — hace ``select_related("caja_fisica_principal")`` pero
``SesionCajaFisica`` no tiene ese campo (quedó en el modelo legacy
``SesionCaja``); el FieldError se traga en el ``except Exception`` y siempre
cae al fallback GEN-CAJGEN.
"""
import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.ventas.models import (
    Cotizacion,
    DetallePedido,
    DevolucionVenta,
    FacturaFiscal,
    NotaCreditoFiscal,
    NotaCreditoVenta,
    NotaVenta,
    Pedido,
)
from apps.ventas.serializers import (
    CotizacionSerializer,
    DetalleNotaVentaSerializer,
    DetallePedidoNestedSerializer,
    DetallePedidoSerializer,
    DevolucionVentaSerializer,
    FacturaFiscalSerializer,
    NotaCreditoFiscalSerializer,
    NotaCreditoVentaSerializer,
    NotaVentaSerializer,
    PedidoSerializer,
)

pytestmark = pytest.mark.django_db

HOY = datetime.date(2026, 6, 9)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def cliente(db, empresa_a):
    from apps.crm.models import Cliente

    # Nota: el modelo Cliente no tiene campo ``nombre``; los serializers lo leen
    # con getattr(..., "") y devuelven cadena vacía.
    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Cliente Serial",
        rif="J-33333333-3",
        telefono="0414-5555555",
    )


@pytest.fixture
def producto(db, empresa_a, moneda_usd):
    from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida

    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad", abreviatura="UN-VS", tipo="CANTIDAD"
    )
    categoria = CategoriaProducto.objects.create(
        id_empresa=empresa_a, nombre_categoria="General VS"
    )
    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Producto Serial",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        precio_venta_sugerido=Decimal("10.00"),
    )


@pytest.fixture
def pedido(db, empresa_a, cliente):
    return Pedido.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente,
        numero_pedido="PED-S-001",
        fecha_pedido=HOY,
    )


# ── PedidoSerializer.validate ─────────────────────────────────────────────────

class TestPedidoValidate:
    def test_fecha_cierre_anterior_a_pedido_invalida(self, cliente):
        ser = PedidoSerializer(
            data={
                "id_cliente": str(cliente.id_cliente),
                "fecha_pedido": "2026-06-09",
                "fecha_cierre_estimada": "2026-06-01",
            }
        )
        assert not ser.is_valid()
        assert "fecha_cierre_estimada" in ser.errors

    def test_fecha_cierre_posterior_valida(self, cliente):
        ser = PedidoSerializer(
            data={
                "id_cliente": str(cliente.id_cliente),
                "fecha_pedido": "2026-06-09",
                "fecha_cierre_estimada": "2026-06-30",
            }
        )
        assert ser.is_valid(), ser.errors


# ── PedidoSerializer.create — numeración y detalles ──────────────────────────

class TestPedidoCreate:
    def test_primer_pedido_recibe_secuencia_000001(self, cliente, empresa_a):
        ser = PedidoSerializer(
            data={"id_cliente": str(cliente.id_cliente), "fecha_pedido": "2026-06-09"}
        )
        assert ser.is_valid(), ser.errors
        pedido = ser.save(id_empresa=empresa_a)
        assert pedido.numero_pedido == "GEN-CAJGEN-000001"

    def test_secuencia_incrementa_sobre_el_maximo_existente(self, cliente, empresa_a):
        Pedido.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            numero_pedido="GEN-CAJGEN-000007",
            fecha_pedido=HOY,
        )
        ser = PedidoSerializer(
            data={"id_cliente": str(cliente.id_cliente), "fecha_pedido": "2026-06-09"}
        )
        assert ser.is_valid(), ser.errors
        pedido = ser.save(id_empresa=empresa_a)
        assert pedido.numero_pedido == "GEN-CAJGEN-000008"

    def test_crea_detalles_anidados_con_decimales_exactos(self, cliente, empresa_a, producto):
        ser = PedidoSerializer(
            data={
                "id_cliente": str(cliente.id_cliente),
                "fecha_pedido": "2026-06-09",
                "detalles": [
                    {
                        "id_producto": str(producto.id_producto),
                        "cantidad": "3.0000",
                        "precio_unitario": "12.5000",
                        "subtotal": "37.5000",
                    }
                ],
            }
        )
        assert ser.is_valid(), ser.errors
        pedido = ser.save(id_empresa=empresa_a)
        detalle = DetallePedido.objects.get(id_pedido=pedido)
        assert detalle.cantidad == Decimal("3.0000")
        assert detalle.precio_unitario == Decimal("12.5000")
        assert detalle.subtotal == Decimal("37.5000")

    def test_sesion_abierta_no_cambia_prefijo_y_registra_usuario(
        self, cliente, empresa_a, user_a
    ):
        """
        BUG (documentado): aunque el usuario tenga una SesionCajaFisica ABIERTA,
        el ``select_related("caja_fisica_principal")`` referencia un campo que no
        existe en el modelo → FieldError silenciado → siempre prefijo GEN-CAJGEN.
        El usuario sí queda registrado en documento_json (vía contexto request).
        """
        from apps.finanzas.models import CajaFisica, SesionCajaFisica

        caja_fisica = CajaFisica.objects.create(
            empresa=empresa_a, nombre="Caja Uno", identificador_dispositivo="dev-vs-1"
        )
        SesionCajaFisica.objects.create(
            caja_fisica=caja_fisica, usuario=user_a, empresa=empresa_a, estado="ABIERTA"
        )
        ser = PedidoSerializer(
            data={"id_cliente": str(cliente.id_cliente), "fecha_pedido": "2026-06-09"},
            context={"request": SimpleNamespace(user=user_a)},
        )
        assert ser.is_valid(), ser.errors
        pedido = ser.save(id_empresa=empresa_a)
        # La sesión NO influye en el prefijo (rama muerta)
        assert pedido.numero_pedido == "GEN-CAJGEN-000001"
        assert pedido.documento_json["id_usuario"] == str(user_a.id)

        # to_representation expone el usuario desde documento_json
        rep = PedidoSerializer(pedido).data
        assert rep["id_usuario"]["username"] == "user_empresa_a"

    def test_documento_json_con_sucursal_y_caja_arma_prefijo(
        self, cliente, empresa_a, moneda_usd
    ):
        """
        documento_json está excluido del input del serializer, pero puede llegar
        por kwargs de ``save()`` (como hace código interno) → el prefijo usa el
        código de sucursal y los primeros 6 chars del nombre de la caja virtual.
        """
        from apps.core.models import Sucursal
        from apps.finanzas.models import Caja

        sucursal = Sucursal.objects.create(
            id_empresa=empresa_a, nombre="Sucursal Web", codigo_sucursal="WEB"
        )
        caja = Caja.objects.create(empresa=empresa_a, nombre="Caja Web", moneda=moneda_usd)
        ser = PedidoSerializer(
            data={"id_cliente": str(cliente.id_cliente), "fecha_pedido": "2026-06-09"}
        )
        assert ser.is_valid(), ser.errors
        pedido = ser.save(
            id_empresa=empresa_a,
            documento_json={
                "id_sucursal": str(sucursal.id_sucursal),
                "id_caja": str(caja.id_caja),
            },
        )
        assert pedido.numero_pedido == "WEB-CAJA W-000001"
        assert pedido.documento_json["id_sucursal"] == str(sucursal.id_sucursal)
        assert pedido.documento_json["id_caja"] == str(caja.id_caja)

    def test_documento_json_con_ids_inexistentes_cae_a_gen(self, cliente, empresa_a):
        """Sucursal/caja inexistentes en documento_json → DoesNotExist → GEN-CAJGEN."""
        import uuid as uuid_mod

        ser = PedidoSerializer(
            data={"id_cliente": str(cliente.id_cliente), "fecha_pedido": "2026-06-09"}
        )
        assert ser.is_valid(), ser.errors
        pedido = ser.save(
            id_empresa=empresa_a,
            documento_json={
                "id_sucursal": str(uuid_mod.uuid4()),
                "id_caja": str(uuid_mod.uuid4()),
            },
        )
        assert pedido.numero_pedido == "GEN-CAJGEN-000001"

    def test_usuario_inexistente_en_documento_json_se_ignora(self, pedido):
        """documento_json.id_usuario que no existe → User.DoesNotExist → sin id_usuario."""
        import uuid as uuid_mod

        pedido.documento_json = {"id_usuario": str(uuid_mod.uuid4())}
        pedido.save(update_fields=["documento_json"])
        rep = PedidoSerializer(pedido).data
        assert "id_usuario" not in rep


# ── to_representation: cliente anidado en todos los documentos ───────────────

class TestClienteAnidado:
    def _assert_cliente(self, rep):
        assert rep["id_cliente"]["razon_social"] == "Cliente Serial"
        assert rep["id_cliente"]["rif"] == "J-33333333-3"
        assert rep["id_cliente"]["telefono"] == "0414-5555555"

    def test_pedido(self, pedido):
        self._assert_cliente(PedidoSerializer(pedido).data)

    def test_nota_venta(self, empresa_a, cliente):
        nota = NotaVenta.objects.create(
            id_empresa=empresa_a, id_cliente=cliente, numero_nota="NV-001", fecha_nota=HOY
        )
        rep = NotaVentaSerializer(nota).data
        self._assert_cliente(rep)
        assert "referencia_externa" not in rep  # SEC-NEW-3
        assert "documento_json" not in rep

    def test_factura_fiscal(self, empresa_a, cliente, moneda_usd):
        factura = FacturaFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            numero_control="00-001",
            numero_factura="F-001",
            fecha_emision=HOY,
            monto_total=Decimal("116.0000"),
            id_moneda=moneda_usd,
        )
        self._assert_cliente(FacturaFiscalSerializer(factura).data)

    def test_cotizacion(self, empresa_a, cliente, moneda_usd):
        cot = Cotizacion.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            numero_cotizacion="COT-001",
            fecha_cotizacion=HOY,
            fecha_vencimiento=HOY + datetime.timedelta(days=15),
            id_moneda=moneda_usd,
        )
        self._assert_cliente(CotizacionSerializer(cot).data)

    def test_nota_credito_venta(self, empresa_a, cliente, moneda_usd):
        nc = NotaCreditoVenta.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            numero_nota_credito="NC-001",
            fecha_emision=HOY,
            motivo="DEVOLUCION",
            monto_total=Decimal("50.0000"),
            id_moneda=moneda_usd,
        )
        self._assert_cliente(NotaCreditoVentaSerializer(nc).data)

    def test_devolucion_venta(self, empresa_a, cliente, moneda_usd):
        dev = DevolucionVenta.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            numero_devolucion="DEV-001",
            fecha_devolucion=HOY,
            motivo_devolucion="DEFECTO",
            id_moneda=moneda_usd,
        )
        self._assert_cliente(DevolucionVentaSerializer(dev).data)

    def test_nota_credito_fiscal(self, empresa_a, cliente, moneda_usd):
        factura = FacturaFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            numero_control="00-002",
            numero_factura="F-002",
            fecha_emision=HOY,
            monto_total=Decimal("100.0000"),
            id_moneda=moneda_usd,
        )
        ncf = NotaCreditoFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            id_factura_origen=factura,
            numero_control="00-002",
            numero_nota_credito="NCF-001",
            fecha_emision=HOY,
            monto_total=Decimal("100.0000"),
            id_moneda=moneda_usd,
            motivo="ANULACION",
        )
        self._assert_cliente(NotaCreditoFiscalSerializer(ncf).data)


class TestDetallePedidoNested:
    def test_producto_anidado_en_representacion(self, pedido, producto):
        detalle = DetallePedido.objects.create(
            id_pedido=pedido,
            id_producto=producto,
            cantidad=Decimal("2.0000"),
            precio_unitario=Decimal("10.0000"),
            subtotal=Decimal("20.0000"),
        )
        rep = DetallePedidoNestedSerializer(detalle).data
        assert rep["id_producto"]["nombre_producto"] == "Producto Serial"
        assert rep["id_producto"]["id_producto"] == str(producto.id_producto)


# ── Validaciones de campo de los detalles ─────────────────────────────────────

class TestValidacionesDetalle:
    def _data_detalle(self, pedido, producto, cantidad="1", precio="10"):
        return {
            "id_pedido": str(pedido.id_pedido),
            "id_producto": str(producto.id_producto),
            "cantidad": cantidad,
            "precio_unitario": precio,
            "subtotal": "10.0000",
        }

    def test_cantidad_cero_invalida(self, pedido, producto):
        ser = DetallePedidoSerializer(data=self._data_detalle(pedido, producto, cantidad="0"))
        assert not ser.is_valid()
        assert "cantidad" in ser.errors

    def test_precio_negativo_invalido(self, pedido, producto):
        ser = DetallePedidoSerializer(data=self._data_detalle(pedido, producto, precio="-1"))
        assert not ser.is_valid()
        assert "precio_unitario" in ser.errors

    def test_detalle_valido_pasa(self, pedido, producto):
        ser = DetallePedidoSerializer(data=self._data_detalle(pedido, producto))
        assert ser.is_valid(), ser.errors

    def test_precio_cero_es_valido(self, pedido, producto):
        """Borde: el precio puede ser exactamente cero (>= 0)."""
        ser = DetallePedidoSerializer(data=self._data_detalle(pedido, producto, precio="0"))
        assert ser.is_valid(), ser.errors


class TestValidacionesNotaVenta:
    def test_numero_nota_vacio_invalido(self):
        from rest_framework import serializers as drf_serializers

        ser = NotaVentaSerializer()
        with pytest.raises(drf_serializers.ValidationError):
            ser.validate_numero_nota("")

    def test_numero_nota_valido_pasa(self):
        assert NotaVentaSerializer().validate_numero_nota("NV-9") == "NV-9"

    def test_detalle_cantidad_negativa_invalida(self, empresa_a, cliente, producto):
        nota = NotaVenta.objects.create(
            id_empresa=empresa_a, id_cliente=cliente, numero_nota="NV-V01", fecha_nota=HOY
        )
        ser = DetalleNotaVentaSerializer(
            data={
                "id_nota_venta": str(nota.id_nota_venta),
                "id_producto": str(producto.id_producto),
                "cantidad": "-2",
                "precio_unitario": "5.0000",
                "subtotal": "-10.0000",
            }
        )
        assert not ser.is_valid()
        assert "cantidad" in ser.errors

    def test_detalle_precio_negativo_invalido(self, empresa_a, cliente, producto):
        nota = NotaVenta.objects.create(
            id_empresa=empresa_a, id_cliente=cliente, numero_nota="NV-V02", fecha_nota=HOY
        )
        ser = DetalleNotaVentaSerializer(
            data={
                "id_nota_venta": str(nota.id_nota_venta),
                "id_producto": str(producto.id_producto),
                "cantidad": "1",
                "precio_unitario": "-5",
                "subtotal": "-5.0000",
            }
        )
        assert not ser.is_valid()
        assert "precio_unitario" in ser.errors
