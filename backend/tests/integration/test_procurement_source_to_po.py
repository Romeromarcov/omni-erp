"""
Tests de integración y API REST para el flujo Source-to-PO de Compras (Plan 08 §B.2).

Cubre:
  - RequisicionCompra → SolicitudAprobacion (REQUISICION_COMPRA) → APROBADA / auto-aprobación
  - Consolidación de múltiples requisiciones aprobadas → SolicitudCotizacion (RFQ)
  - Matriz comparativa lado a lado (comparar_ofertas_rfq) con Decimal estricto
  - Adjudicación total y parcial (split multi-proveedor) → OrdenCompra en BORRADOR
  - Todas las acciones REST nuevas + serializers cross-tenant + guardas \x00/ordering/search
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
import uuid

import pytest
from django.utils import timezone

from apps.almacenes.models import Almacen
from apps.compras.models import (
    DetalleOfertaProveedor,
    DetalleRequisicionCompra,
    OfertaProveedor,
    OrdenCompra,
    RequisicionCompra,
)
from apps.compras.services import CompraError
from apps.compras.services_procurement import (
    adjudicar_oferta_a_orden_compra,
    comparar_ofertas_rfq,
    confirmar_aprobacion_requisicion,
    crear_rfq_desde_requisiciones,
    enviar_requisicion_aprobacion,
)
from apps.core.models import Departamento, Roles, UsuarioRoles
from apps.gestion_aprobaciones.models import FlujoAprobacion, SolicitudAprobacion, TipoAprobacion
from apps.gestion_aprobaciones.services import registrar_decision
from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida
from apps.proveedores.models import Proveedor

pytestmark = [pytest.mark.django_db]


def _hoy():
    return timezone.localdate()


@pytest.fixture
def almacen_a(db, empresa_a):
    return Almacen.objects.create(
        id_empresa=empresa_a,
        nombre_almacen="Almacén Central Procurement",
        codigo_almacen="ALM-PROC-1",
    )


@pytest.fixture
def almacen_b(db, empresa_b):
    return Almacen.objects.create(
        id_empresa=empresa_b,
        nombre_almacen="Almacén Privado B",
        codigo_almacen="ALM-PROC-B",
    )


@pytest.fixture
def proveedor_1(db, empresa_a):
    return Proveedor.objects.create(
        id_empresa=empresa_a,
        razon_social="Suministros Alfa C.A.",
        rif="J-11111111-1",
        activo=True,
    )


@pytest.fixture
def proveedor_2(db, empresa_a):
    return Proveedor.objects.create(
        id_empresa=empresa_a,
        razon_social="Distribuidora Beta S.A.",
        rif="J-22222222-2",
        activo=True,
    )


@pytest.fixture
def proveedor_b(db, empresa_b):
    return Proveedor.objects.create(
        id_empresa=empresa_b,
        razon_social="Proveedor Ajeno B S.A.",
        rif="J-99999999-9",
        activo=True,
    )


@pytest.fixture
def productos_a(db, empresa_a, moneda_usd):
    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a,
        nombre="Unidad Procurement",
        abreviatura="UND-P",
        tipo="CANTIDAD",
    )
    categoria = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="Insumos")
    prod_1 = Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Resma Carta",
        sku="RES-001",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        activo=True,
    )
    prod_2 = Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Tóner Láser",
        sku="TON-002",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        activo=True,
    )
    prod_3 = Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Cable Red Cat6",
        sku="CAB-003",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        activo=True,
    )
    return prod_1, prod_2, prod_3


@pytest.fixture
def producto_b(db, empresa_b, moneda_usd):
    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_b,
        nombre="Unidad B",
        abreviatura="UND-B",
        tipo="CANTIDAD",
    )
    categoria = CategoriaProducto.objects.create(id_empresa=empresa_b, nombre_categoria="Insumos B")
    return Producto.objects.create(
        id_empresa=empresa_b,
        nombre_producto="Producto Ajeno B",
        sku="AJN-001",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        activo=True,
    )


def _crear_req(empresa, usuario, numero, prod, cantidad, precio_est, *, dep=None, estado="BORRADOR", just="Operación"):
    req = RequisicionCompra.objects.create(
        id_empresa=empresa,
        id_solicitante=usuario,
        id_departamento=dep,
        numero_requisicion=numero,
        fecha_requisicion=_hoy(),
        fecha_necesidad=_hoy() + timedelta(days=5),
        estado=estado,
        prioridad="ALTA",
        justificacion=just,
    )
    if prod is not None:
        DetalleRequisicionCompra.objects.create(
            id_requisicion=req,
            id_producto=prod,
            cantidad_solicitada=Decimal(cantidad),
            precio_estimado=Decimal(precio_est) if precio_est is not None else None,
            justificacion="Requerido área",
            observaciones="Urgente",
        )
    return req


class TestSourceToPOServicios:
    def test_requisicion_sin_regla_aprobacion_se_autoaprueba(self, empresa_a, user_a, productos_a):
        prod_1, _prod_2, _prod_3 = productos_a
        req = _crear_req(empresa_a, user_a, "REQ-AUTO-1", prod_1, "5.0000", "20.0000")

        actualizada = enviar_requisicion_aprobacion(req, user_a)
        assert actualizada.estado == "APROBADA"
        assert SolicitudAprobacion.objects.count() == 0

    def test_requisicion_con_regla_aprobacion_pasa_pendiente_y_confirma(self, empresa_a, user_a, productos_a):
        prod_1, _prod_2, _prod_3 = productos_a
        dep = Departamento.objects.create(id_empresa=empresa_a, nombre_departamento="Compras IT")
        rol = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Gerente Compras")
        UsuarioRoles.objects.create(id_usuario=user_a, id_rol=rol)
        tipo = TipoAprobacion.objects.create(
            id_empresa=empresa_a,
            codigo_tipo="REQUISICION_COMPRA",
            nombre_tipo="Aprobación Requisiciones",
            modulo_origen="compras",
            activo=True,
        )
        FlujoAprobacion.objects.create(
            id_tipo_aprobacion=tipo,
            id_departamento=dep,
            orden_etapa=1,
            nombre_etapa="Gerencia IT",
            rol_aprobador=rol,
            monto_minimo=Decimal("50.00"),
            activo=True,
        )

        req = _crear_req(empresa_a, user_a, "REQ-APR-1", prod_1, "10.0000", "25.0000", dep=dep)
        pendiente = enviar_requisicion_aprobacion(req, user_a)
        assert pendiente.estado == "PENDIENTE"

        sol = SolicitudAprobacion.objects.get(id_entidad_origen=pendiente.pk, nombre_modelo_origen="RequisicionCompra")
        assert sol.id_departamento == dep
        assert sol.monto == Decimal("250.00")

        with pytest.raises(CompraError, match="aún no ha sido aprobada"):
            confirmar_aprobacion_requisicion(pendiente, user_a)

        registrar_decision(sol, user_a, aprobado=True, comentarios="Conforme")
        aprobada = confirmar_aprobacion_requisicion(pendiente, user_a)
        assert aprobada.estado == "APROBADA"

        with pytest.raises(CompraError, match="PENDIENTE"):
            confirmar_aprobacion_requisicion(aprobada, user_a)

    def test_enviar_requisicion_errores_validacion(self, empresa_a, empresa_b, user_a, productos_a):
        prod_1, _p2, _p3 = productos_a
        req_aprobada = _crear_req(empresa_a, user_a, "REQ-BAD-1", prod_1, "1", "10", estado="APROBADA")
        with pytest.raises(CompraError, match="BORRADOR"):
            enviar_requisicion_aprobacion(req_aprobada, user_a)

        req_vacia = _crear_req(empresa_a, user_a, "REQ-EMPTY-1", None, "0", "0")
        with pytest.raises(CompraError, match="al menos una línea"):
            enviar_requisicion_aprobacion(req_vacia, user_a)

        dep_b = Departamento.objects.create(id_empresa=empresa_b, nombre_departamento="Dep Ajeno")
        TipoAprobacion.objects.create(
            id_empresa=empresa_a,
            codigo_tipo="REQUISICION_COMPRA",
            nombre_tipo="Req",
            modulo_origen="compras",
            activo=True,
        )
        req_dep_b = _crear_req(empresa_a, user_a, "REQ-DEPB-1", prod_1, "2", "100", dep=dep_b)
        with pytest.raises(CompraError, match="departamento no pertenece"):
            enviar_requisicion_aprobacion(req_dep_b, user_a)

    def test_consolidar_rfq_comparar_y_adjudicar_total_y_parcial(
        self,
        empresa_a,
        empresa_b,
        user_a,
        almacen_a,
        almacen_b,
        proveedor_1,
        proveedor_2,
        proveedor_b,
        productos_a,
        producto_b,
    ):
        prod_1, prod_2, prod_3 = productos_a
        req1 = _crear_req(empresa_a, user_a, "REQ-C1", prod_1, "6.0000", "10.0000", estado="APROBADA")
        req2 = _crear_req(empresa_a, user_a, "REQ-C2", prod_1, "4.0000", "10.0000", estado="APROBADA")
        DetalleRequisicionCompra.objects.create(
            id_requisicion=req2,
            id_producto=prod_2,
            cantidad_solicitada=Decimal("5.0000"),
            precio_estimado=Decimal("40.0000"),
        )

        hoy = _hoy()
        # Errores de creación RFQ
        with pytest.raises(CompraError, match="al menos una requisición"):
            crear_rfq_desde_requisiciones(empresa_a, [], [proveedor_1.pk], hoy + timedelta(days=5))
        with pytest.raises(CompraError, match="al menos un proveedor"):
            crear_rfq_desde_requisiciones(empresa_a, [req1.pk], [], hoy + timedelta(days=5))
        with pytest.raises(CompraError, match="formato ISO"):
            crear_rfq_desde_requisiciones(empresa_a, [req1.pk], [proveedor_1.pk], "not-a-date")
        with pytest.raises(CompraError, match="anterior a la fecha de solicitud"):
            crear_rfq_desde_requisiciones(empresa_a, [req1.pk], [proveedor_1.pk], hoy - timedelta(days=1))
        with pytest.raises(CompraError, match="no existen"):
            crear_rfq_desde_requisiciones(empresa_a, [uuid.uuid4()], [proveedor_1.pk], hoy + timedelta(days=3))

        req_borrador = _crear_req(empresa_a, user_a, "REQ-BOR", prod_1, "1", "10", estado="BORRADOR")
        with pytest.raises(CompraError, match="no está APROBADA"):
            crear_rfq_desde_requisiciones(empresa_a, [req_borrador.pk], [proveedor_1.pk], hoy + timedelta(days=3))

        req_b = _crear_req(empresa_b, user_a, "REQ-EMP-B", producto_b, "1", "10", estado="APROBADA")
        with pytest.raises(CompraError, match="pertenecer a la empresa"):
            crear_rfq_desde_requisiciones(empresa_a, [req_b.pk], [proveedor_1.pk], hoy + timedelta(days=3))

        with pytest.raises(CompraError, match="inactivos o pertenecen a otra empresa"):
            crear_rfq_desde_requisiciones(empresa_a, [req1.pk], [proveedor_b.pk], hoy + timedelta(days=3))

        req_sin_det = _crear_req(empresa_a, user_a, "REQ-SIN-DET", None, "0", "0", estado="APROBADA")
        with pytest.raises(CompraError, match="no tienen líneas"):
            crear_rfq_desde_requisiciones(empresa_a, [req_sin_det.pk], [proveedor_1.pk], hoy + timedelta(days=3))

        # Creación consolidada válida
        rfq = crear_rfq_desde_requisiciones(
            empresa_a,
            [req1.pk, req2.pk],
            [proveedor_1.pk, proveedor_2.pk],
            (hoy + timedelta(days=7)).isoformat(),
            usuario=user_a,
            observaciones="Licitación consolidada",
            numero_solicitud="RFQ-CONS-01",
        )
        assert rfq.estado == "ENVIADA"
        assert set(rfq.requisiciones.values_list("pk", flat=True)) == {req1.pk, req2.pk}
        assert set(rfq.proveedores_invitados.values_list("pk", flat=True)) == {proveedor_1.pk, proveedor_2.pk}
        det_rfq_p1 = rfq.detalles.get(id_producto=prod_1)
        assert det_rfq_p1.cantidad == Decimal("10.0000")

        with pytest.raises(CompraError, match="Ya existe una solicitud"):
            crear_rfq_desde_requisiciones(
                empresa_a,
                [req1.pk],
                [proveedor_1.pk],
                hoy + timedelta(days=5),
                numero_solicitud="RFQ-CONS-01",
            )

        # Oferta 1 (Proveedor 1 más barato en prod_1, monto_total=0 para ejercitar fallback suma_dets)
        of1 = OfertaProveedor.objects.create(
            id_solicitud_cotizacion=rfq,
            id_proveedor=proveedor_1,
            numero_oferta="OF-P1-01",
            fecha_oferta=hoy,
            fecha_vencimiento=hoy + timedelta(days=5),
            estado="RECIBIDA",
            monto_total=Decimal("0.0000"),
            tiempo_entrega="3 días",
        )
        DetalleOfertaProveedor.objects.create(
            id_oferta=of1,
            id_producto=prod_1,
            cantidad=Decimal("10.0000"),
            precio_unitario=Decimal("8.0000"),
            subtotal=Decimal("80.0000"),
        )
        DetalleOfertaProveedor.objects.create(
            id_oferta=of1,
            id_producto=prod_2,
            cantidad=Decimal("5.0000"),
            precio_unitario=Decimal("50.0000"),
            subtotal=Decimal("250.0000"),
        )

        # Oferta 2 (Proveedor 2 más caro en prod_1, más barato en prod_2, más producto extra prod_3)
        of2 = OfertaProveedor.objects.create(
            id_solicitud_cotizacion=rfq,
            id_proveedor=proveedor_2,
            numero_oferta="OF-P2-01",
            fecha_oferta=hoy,
            fecha_vencimiento=hoy + timedelta(days=5),
            estado="EVALUADA",
            monto_total=Decimal("270.0000"),
            tiempo_entrega="5 días",
        )
        DetalleOfertaProveedor.objects.create(
            id_oferta=of2,
            id_producto=prod_1,
            cantidad=Decimal("10.0000"),
            precio_unitario=Decimal("10.0000"),
            subtotal=Decimal("100.0000"),
        )
        DetalleOfertaProveedor.objects.create(
            id_oferta=of2,
            id_producto=prod_2,
            cantidad=Decimal("5.0000"),
            precio_unitario=Decimal("32.0000"),
            subtotal=Decimal("160.0000"),
        )
        DetalleOfertaProveedor.objects.create(
            id_oferta=of2,
            id_producto=prod_3,
            cantidad=Decimal("1.0000"),
            precio_unitario=Decimal("10.0000"),
            subtotal=Decimal("10.0000"),
        )

        matriz = comparar_ofertas_rfq(rfq)
        assert matriz["rfq_id"] == str(rfq.pk)
        assert matriz["mejor_oferta_id"] == str(of2.pk)  # 270 < 330
        assert isinstance(matriz["ofertas"][0]["monto_total"], str)
        assert matriz["ofertas"][0]["monto_total"] == "270.0000"
        assert matriz["ofertas"][0]["es_mejor_total"] is True
        assert matriz["ofertas"][1]["monto_total"] == "330.0000"
        prods_by_id = {p["id_producto"]: p for p in matriz["productos"]}
        assert str(prod_3.pk) in prods_by_id
        assert prods_by_id[str(prod_1.pk)]["mejor_precio_unitario"] == "8.0000"
        assert prods_by_id[str(prod_2.pk)]["mejor_precio_unitario"] == "32.0000"

        # Validaciones previas a adjudicar
        with pytest.raises(CompraError, match="almacén destino no pertenece"):
            adjudicar_oferta_a_orden_compra(of1, almacen_b, user_a)
        with pytest.raises(CompraError, match="al menos un producto"):
            adjudicar_oferta_a_orden_compra(of1, almacen_a, user_a, adjudicacion_parcial=[])
        with pytest.raises(CompraError, match="producto único"):
            adjudicar_oferta_a_orden_compra(
                of1,
                almacen_a,
                user_a,
                adjudicacion_parcial=[
                    {"id_producto": str(prod_1.pk), "cantidad": "1"},
                    {"id_producto": str(prod_1.pk), "cantidad": "2"},
                ],
            )
        with pytest.raises(CompraError, match="no pertenece a la oferta"):
            adjudicar_oferta_a_orden_compra(
                of1,
                almacen_a,
                user_a,
                adjudicacion_parcial=[{"id_producto": str(prod_3.pk), "cantidad": "1"}],
            )
        with pytest.raises(CompraError, match="Cantidad inválida"):
            adjudicar_oferta_a_orden_compra(
                of1,
                almacen_a,
                user_a,
                adjudicacion_parcial=[{"id_producto": str(prod_1.pk), "cantidad": "abc"}],
            )
        with pytest.raises(CompraError, match="mayor que cero"):
            adjudicar_oferta_a_orden_compra(
                of1,
                almacen_a,
                user_a,
                adjudicacion_parcial=[{"id_producto": str(prod_1.pk), "cantidad": "0"}],
            )
        with pytest.raises(CompraError, match="supera la ofertada"):
            adjudicar_oferta_a_orden_compra(
                of1,
                almacen_a,
                user_a,
                adjudicacion_parcial=[{"id_producto": str(prod_1.pk), "cantidad": "999"}],
            )

        # Adjudicación parcial dividida (split):
        # 1) Adjudicamos prod_1 al Proveedor 1 SIN rechazar competidoras
        res_split_1 = adjudicar_oferta_a_orden_compra(
            of1,
            almacen_a,
            user_a,
            adjudicacion_parcial=[{"id_producto": str(prod_1.pk), "cantidad": "6.0000"}],
            rechazar_competidoras=False,
        )
        oc1 = res_split_1["orden_compra"]
        assert oc1.estado == "BORRADOR"
        assert oc1.id_oferta_origen == of1
        assert oc1.id_almacen_destino == almacen_a
        assert res_split_1["monto_total"] == Decimal("48.0000")
        assert res_split_1["lineas"] == 1
        of1.refresh_from_db()
        of2.refresh_from_db()
        rfq.refresh_from_db()
        req1.refresh_from_db()
        assert of1.estado == "ACEPTADA"
        assert of2.estado == "EVALUADA"
        assert rfq.estado == "ENVIADA"  # Sigue abierta porque of2 sigue abierta
        assert req1.estado == "APROBADA"

        # 2) Adjudicamos prod_2 al Proveedor 2 cerrando las demás
        res_split_2 = adjudicar_oferta_a_orden_compra(
            of2,
            almacen_a,
            user_a,
            adjudicacion_parcial=[{"id_producto": str(prod_2.pk), "cantidad": "5.0000"}],
            rechazar_competidoras=True,
        )
        assert res_split_2["monto_total"] == Decimal("160.0000")
        rfq.refresh_from_db()
        req1.refresh_from_db()
        req2.refresh_from_db()
        assert rfq.estado == "RESPONDIDA"
        assert req1.estado == "PROCESADA"
        assert req2.estado == "PROCESADA"

        # Re-adjudicar oferta o RFQ ya cerrada falla
        with pytest.raises(CompraError, match="ENVIADA o RESPONDIDA|RECIBIDA o EVALUADA"):
            adjudicar_oferta_a_orden_compra(of2, almacen_a, user_a)

        rfq.estado = "VENCIDA"
        rfq.save(update_fields=["estado"])
        with pytest.raises(CompraError, match="ENVIADA o RESPONDIDA"):
            adjudicar_oferta_a_orden_compra(of1, almacen_a, user_a)

    def test_adjudicacion_total_y_errores_oferta_sin_lineas_y_cruce_tenant(
        self, empresa_a, empresa_b, user_a, almacen_a, proveedor_1, proveedor_b, productos_a, producto_b
    ):
        prod_1, _p2, _p3 = productos_a
        hoy = _hoy()
        req = _crear_req(empresa_a, user_a, "REQ-TOT-1", prod_1, "3.0000", "15.0000", estado="APROBADA")
        rfq = crear_rfq_desde_requisiciones(empresa_a, [req.pk], [proveedor_1.pk], hoy + timedelta(days=3))

        of_vacia = OfertaProveedor.objects.create(
            id_solicitud_cotizacion=rfq,
            id_proveedor=proveedor_1,
            numero_oferta="OF-EMPTY",
            fecha_oferta=hoy,
            fecha_vencimiento=hoy + timedelta(days=3),
            estado="RECIBIDA",
        )
        with pytest.raises(CompraError, match="no tiene líneas"):
            adjudicar_oferta_a_orden_compra(of_vacia, almacen_a, user_a)

        of_prov_b = OfertaProveedor.objects.create(
            id_solicitud_cotizacion=rfq,
            id_proveedor=proveedor_b,
            numero_oferta="OF-PROVB",
            fecha_oferta=hoy,
            fecha_vencimiento=hoy + timedelta(days=3),
            estado="RECIBIDA",
        )
        with pytest.raises(CompraError, match="proveedor de la oferta no pertenece"):
            adjudicar_oferta_a_orden_compra(of_prov_b, almacen_a, user_a)

        of_prod_b = OfertaProveedor.objects.create(
            id_solicitud_cotizacion=rfq,
            id_proveedor=proveedor_1,
            numero_oferta="OF-PRODB",
            fecha_oferta=hoy,
            fecha_vencimiento=hoy + timedelta(days=3),
            estado="RECIBIDA",
        )
        DetalleOfertaProveedor.objects.create(
            id_oferta=of_prod_b,
            id_producto=producto_b,
            cantidad=Decimal("2.0000"),
            precio_unitario=Decimal("10.0000"),
            subtotal=Decimal("20.0000"),
        )
        with pytest.raises(CompraError, match="Todos los productos adjudicados"):
            adjudicar_oferta_a_orden_compra(of_prod_b, almacen_a, user_a)

        # Oferta válida completa + competidora que debe quedar RECHAZADA
        DetalleOfertaProveedor.objects.create(
            id_oferta=of_vacia,
            id_producto=prod_1,
            cantidad=Decimal("3.0000"),
            precio_unitario=Decimal("12.0000"),
            subtotal=Decimal("36.0000"),
        )
        of_comp = OfertaProveedor.objects.create(
            id_solicitud_cotizacion=rfq,
            id_proveedor=proveedor_1,
            numero_oferta="OF-COMP",
            fecha_oferta=hoy,
            fecha_vencimiento=hoy + timedelta(days=3),
            estado="RECIBIDA",
        )
        res = adjudicar_oferta_a_orden_compra(of_vacia, almacen_a, user_a)
        of_comp.refresh_from_db()
        assert of_comp.estado == "RECHAZADA"
        assert res["monto_total"] == Decimal("36.0000")


class TestSourceToPORestAPI:
    def test_flujo_completo_por_api_y_filtros_seguros(
        self,
        client_a,
        empresa_a,
        empresa_b,
        user_a,
        almacen_a,
        almacen_b,
        proveedor_1,
        proveedor_2,
        proveedor_b,
        productos_a,
    ):
        prod_1, prod_2, _p3 = productos_a
        hoy = _hoy()
        rol = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Aprobador API Compras")
        UsuarioRoles.objects.create(id_usuario=user_a, id_rol=rol)
        tipo = TipoAprobacion.objects.create(
            id_empresa=empresa_a,
            codigo_tipo="REQUISICION_COMPRA",
            nombre_tipo="Req API",
            modulo_origen="compras",
            activo=True,
        )
        FlujoAprobacion.objects.create(
            id_tipo_aprobacion=tipo,
            orden_etapa=1,
            nombre_etapa="Etapa API",
            rol_aprobador=rol,
            monto_minimo=Decimal("10.00"),
            activo=True,
        )

        # Crear requisición vía API
        r_req = client_a.post(
            "/api/compras/requisiciones-compra/",
            {
                "id_solicitante": str(user_a.pk),
                "numero_requisicion": "REQ-API-1",
                "fecha_requisicion": hoy.isoformat(),
                "fecha_necesidad": (hoy + timedelta(days=5)).isoformat(),
                "estado": "BORRADOR",
                "prioridad": "ALTA",
                "justificacion": "Prueba API Source-to-PO",
            },
            format="json",
        )
        assert r_req.status_code == 201, r_req.json()
        req_id = r_req.json()["id_requisicion"]

        # Sin líneas -> enviar-aprobacion retorna 400 detail
        r_env_bad = client_a.post(f"/api/compras/requisiciones-compra/{req_id}/enviar-aprobacion/", {}, format="json")
        assert r_env_bad.status_code == 400
        assert "detail" in r_env_bad.json()

        r_det = client_a.post(
            "/api/compras/detalles-requisicion-compra/",
            {
                "id_requisicion": req_id,
                "id_producto": str(prod_1.pk),
                "cantidad_solicitada": "4.0000",
                "precio_estimado": "50.0000",
            },
            format="json",
        )
        assert r_det.status_code == 201

        r_env = client_a.post(f"/api/compras/requisiciones-compra/{req_id}/enviar-aprobacion/", {}, format="json")
        assert r_env.status_code == 200
        assert r_env.json()["estado"] == "PENDIENTE"

        # Confirmar antes de aprobar -> 400 detail
        r_conf_bad = client_a.post(
            f"/api/compras/requisiciones-compra/{req_id}/confirmar-aprobacion/", {}, format="json"
        )
        assert r_conf_bad.status_code == 400

        sol = SolicitudAprobacion.objects.get(id_entidad_origen=req_id, nombre_modelo_origen="RequisicionCompra")
        r_dec = client_a.post(
            f"/api/gestion-aprobaciones/solicitudes-aprobacion/{sol.pk}/decidir/",
            {"aprobado": True, "comentarios": "OK API"},
            format="json",
        )
        assert r_dec.status_code == 200
        assert r_dec.json()["estado_solicitud"] == "APROBADA"

        r_conf = client_a.post(f"/api/compras/requisiciones-compra/{req_id}/confirmar-aprobacion/", {}, format="json")
        assert r_conf.status_code == 200
        assert r_conf.json()["estado"] == "APROBADA"

        # Generar RFQ desde requisiciones (error fecha pasada -> 400)
        r_rfq_bad = client_a.post(
            "/api/compras/solicitudes-cotizacion/desde-requisiciones/",
            {
                "requisicion_ids": [req_id],
                "proveedores_ids": [str(proveedor_1.pk)],
                "fecha_vencimiento": (hoy - timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        assert r_rfq_bad.status_code == 400

        r_rfq = client_a.post(
            "/api/compras/solicitudes-cotizacion/desde-requisiciones/",
            {
                "requisicion_ids": [req_id],
                "proveedores_ids": [str(proveedor_1.pk), str(proveedor_2.pk)],
                "fecha_vencimiento": (hoy + timedelta(days=7)).isoformat(),
                "observaciones": "Consolidado vía REST",
            },
            format="json",
        )
        assert r_rfq.status_code == 201, r_rfq.json()
        rfq_id = r_rfq.json()["id_solicitud_cotizacion"]

        # Registrar oferta vía API
        r_of = client_a.post(
            "/api/compras/ofertas-proveedor/",
            {
                "id_solicitud_cotizacion": rfq_id,
                "id_proveedor": str(proveedor_1.pk),
                "numero_oferta": "OF-API-1",
                "fecha_oferta": hoy.isoformat(),
                "fecha_vencimiento": (hoy + timedelta(days=5)).isoformat(),
                "estado": "RECIBIDA",
                "monto_total": "180.0000",
            },
            format="json",
        )
        assert r_of.status_code == 201
        of_id = r_of.json()["id_oferta"]
        client_a.post(
            "/api/compras/detalles-oferta-proveedor/",
            {
                "id_oferta": of_id,
                "id_producto": str(prod_1.pk),
                "cantidad": "4.0000",
                "precio_unitario": "45.0000",
                "subtotal": "180.0000",
            },
            format="json",
        )

        # Comparar ofertas
        r_comp = client_a.get(f"/api/compras/solicitudes-cotizacion/{rfq_id}/comparar-ofertas/")
        assert r_comp.status_code == 200
        assert r_comp.json()["mejor_oferta_id"] == of_id

        # Adjudicar con almacén ajeno -> 404
        r_adj_b = client_a.post(
            f"/api/compras/ofertas-proveedor/{of_id}/adjudicar/",
            {"id_almacen_destino": str(almacen_b.pk)},
            format="json",
        )
        assert r_adj_b.status_code == 404

        # Adjudicar válido -> 201 OrdenCompra BORRADOR
        r_adj = client_a.post(
            f"/api/compras/ofertas-proveedor/{of_id}/adjudicar/",
            {
                "id_almacen_destino": str(almacen_a.pk),
                "adjudicacion_parcial": [{"id_producto": str(prod_1.pk), "cantidad": "4.0000"}],
                "rechazar_competidoras": True,
            },
            format="json",
        )
        assert r_adj.status_code == 201, r_adj.json()
        assert r_adj.json()["estado_orden"] == "BORRADOR"
        assert r_adj.json()["rfq_estado"] == "RESPONDIDA"
        oc = OrdenCompra.objects.get(pk=r_adj.json()["id_orden_compra"])
        assert oc.id_oferta_origen_id == uuid.UUID(of_id)
        assert oc.id_almacen_destino_id == almacen_a.pk

        # Adjudicar oferta ya ACEPTADA vía API -> 400 CompraError (cubre except CompraError en adjudicar)
        r_adj_dup = client_a.post(
            f"/api/compras/ofertas-proveedor/{of_id}/adjudicar/",
            {"id_almacen_destino": str(almacen_a.pk)},
            format="json",
        )
        assert r_adj_dup.status_code == 400
        assert "detail" in r_adj_dup.json()

        # Filtros, búsqueda, ordenamiento y guarda \x00 en ViewSets
        assert (
            client_a.get(
                "/api/compras/requisiciones-compra/?estado=PROCESADA&search=API&ordering=-fecha_creacion"
            ).status_code
            == 200
        )
        assert (
            client_a.get(
                "/api/compras/solicitudes-cotizacion/?estado=RESPONDIDA&search=RFQ&ordering=-fecha_creacion"
            ).status_code
            == 200
        )
        assert (
            client_a.get(
                f"/api/compras/ofertas-proveedor/?estado=ACEPTADA&solicitud={rfq_id}&search=OF-API"
            ).status_code
            == 200
        )
        assert client_a.get("/api/compras/ofertas-proveedor/?solicitud=not-uuid").status_code == 400
        assert client_a.get("/api/compras/requisiciones-compra/?search=a%00b").status_code == 400
        assert client_a.get("/api/compras/requisiciones-compra/?a%00b=1").status_code == 400

        # Validaciones de SolicitudCotizacionSerializer & OrdenCompraSerializer (cross-tenant + fechas + update)
        from apps.compras.serializers import OrdenCompraSerializer, SolicitudCotizacionSerializer

        req_b = _crear_req(empresa_b, user_a, "REQ-SC-B", None, "0", "0", estado="APROBADA")
        r_sc_bad_fecha = client_a.post(
            "/api/compras/solicitudes-cotizacion/",
            {
                "numero_solicitud": "RFQ-BAD-FEC",
                "fecha_solicitud": hoy.isoformat(),
                "fecha_vencimiento": (hoy - timedelta(days=2)).isoformat(),
            },
            format="json",
        )
        assert r_sc_bad_fecha.status_code == 400

        r_sc_req_b = client_a.post(
            "/api/compras/solicitudes-cotizacion/",
            {
                "numero_solicitud": "RFQ-REQB",
                "fecha_solicitud": hoy.isoformat(),
                "fecha_vencimiento": (hoy + timedelta(days=2)).isoformat(),
                "requisiciones": [str(req_b.pk)],
            },
            format="json",
        )
        assert r_sc_req_b.status_code == 400

        r_sc_prov_b = client_a.post(
            "/api/compras/solicitudes-cotizacion/",
            {
                "numero_solicitud": "RFQ-PROVB",
                "fecha_solicitud": hoy.isoformat(),
                "fecha_vencimiento": (hoy + timedelta(days=2)).isoformat(),
                "proveedores_invitados": [str(proveedor_b.pk)],
            },
            format="json",
        )
        assert r_sc_prov_b.status_code == 400

        # Validación serializer directa (sin request context → cubre empresa_ref y mezcla cross-tenant)
        sc_ser_mix_req = SolicitudCotizacionSerializer(
            data={
                "numero_solicitud": "RFQ-MIX-R",
                "fecha_solicitud": hoy.isoformat(),
                "fecha_vencimiento": (hoy + timedelta(days=2)).isoformat(),
                "requisiciones": [req_id, str(req_b.pk)],
            }
        )
        assert not sc_ser_mix_req.is_valid()
        assert "requisiciones" in sc_ser_mix_req.errors

        sc_ser_mix_prov = SolicitudCotizacionSerializer(
            data={
                "numero_solicitud": "RFQ-MIX-P",
                "fecha_solicitud": hoy.isoformat(),
                "fecha_vencimiento": (hoy + timedelta(days=2)).isoformat(),
                "requisiciones": [req_id],
                "proveedores_invitados": [str(proveedor_b.pk)],
            }
        )
        assert not sc_ser_mix_prov.is_valid()
        assert "proveedores_invitados" in sc_ser_mix_prov.errors

        r_oc_alm_b = client_a.post(
            "/api/compras/ordenes-compra/",
            {
                "id_proveedor": str(proveedor_1.pk),
                "id_almacen_destino": str(almacen_b.pk),
                "numero_orden": "OC-ALMB",
                "fecha_orden": hoy.isoformat(),
            },
            format="json",
        )
        assert r_oc_alm_b.status_code == 400

        r_oc_ofe_b = client_a.post(
            "/api/compras/ordenes-compra/",
            {
                "id_proveedor": str(proveedor_1.pk),
                "id_oferta_origen": of_id,
                "numero_orden": "OC-OFEA",
                "fecha_orden": hoy.isoformat(),
            },
            format="json",
        )
        assert r_oc_ofe_b.status_code == 201

        oc_ser_bad_alm = OrdenCompraSerializer(
            data={
                "id_proveedor": str(proveedor_1.pk),
                "id_almacen_destino": str(almacen_b.pk),
                "numero_orden": "OC-SER-ALM",
                "fecha_orden": hoy.isoformat(),
            }
        )
        assert not oc_ser_bad_alm.is_valid()
        assert "id_almacen_destino" in oc_ser_bad_alm.errors

        # PATCH OrdenCompra
        r_oc_patch = client_a.patch(
            f"/api/compras/ordenes-compra/{oc.pk}/",
            {"observaciones": "Editada"},
            format="json",
        )
        assert r_oc_patch.status_code == 200

        # Unicidad por empresa vía API devuelve 400 limpio (no IntegrityError 500)
        assert (
            client_a.post(
                "/api/compras/solicitudes-cotizacion/",
                {
                    "numero_solicitud": r_rfq.json()["numero_solicitud"],
                    "fecha_solicitud": hoy.isoformat(),
                    "fecha_vencimiento": (hoy + timedelta(days=3)).isoformat(),
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/compras/requisiciones-compra/",
                {
                    "id_solicitante": str(user_a.pk),
                    "numero_requisicion": "REQ-API-1",
                    "fecha_requisicion": hoy.isoformat(),
                    "fecha_necesidad": (hoy + timedelta(days=3)).isoformat(),
                    "justificacion": "Duplicado",
                },
                format="json",
            ).status_code
            == 400
        )
