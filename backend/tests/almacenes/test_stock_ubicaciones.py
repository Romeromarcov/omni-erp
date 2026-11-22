"""Tests de Almacén con Ubicaciones Opt-in, StockUbicacion, Autorización y RLS (PR-16)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db import connection
from rest_framework.test import APIClient

from apps.almacenes.models import Almacen, StockUbicacion, UbicacionAlmacen
from apps.almacenes.services import (
    AutorizacionUbicacionError,
    UbicacionOperacionError,
    reservar_ubicacion,
    transferir_entre_ubicaciones,
)
from apps.core import rls
from apps.inventario.models import MovimientoInventario, StockActual, VarianteProducto
from apps.inventario.services import delta_para_almacen
from tests.factories import (
    AlmacenFactory,
    CategoriaProductoFactory,
    EmpresaFactory,
    ProductoFactory,
    UnidadMedidaFactory,
    UsuariosFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup_alm_a(db, empresa_a, user_a, moneda_usd):
    unidad = UnidadMedidaFactory(id_empresa=empresa_a, nombre="Caja", abreviatura="CAJ")
    categoria = CategoriaProductoFactory(id_empresa=empresa_a, nombre_categoria="Repuestos")
    producto = ProductoFactory(
        id_empresa=empresa_a,
        nombre_producto="Bujía Industrial",
        sku="BUJ-100",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        costo_promedio=Decimal("8.00"),
    )
    alm_simple = AlmacenFactory(
        id_empresa=empresa_a,
        nombre_almacen="Almacén Simple",
        codigo_almacen="ALM-SIM",
        usa_ubicaciones=False,
    )
    alm_ubic = AlmacenFactory(
        id_empresa=empresa_a,
        nombre_almacen="Almacén Zonificado",
        codigo_almacen="ALM-ZONA",
        usa_ubicaciones=True,
    )
    alm_otro = AlmacenFactory(
        id_empresa=empresa_a,
        nombre_almacen="Otro Zonificado",
        codigo_almacen="ALM-OTRO",
        usa_ubicaciones=True,
    )
    u_pick = UbicacionAlmacen.objects.create(
        id_empresa=empresa_a,
        id_almacen=alm_ubic,
        codigo_ubicacion="A-01-01",
        nombre_ubicacion="Pasillo A Picking",
        tipo_ubicacion="PICKING",
        requiere_autorizacion=False,
    )
    u_res = UbicacionAlmacen.objects.create(
        id_empresa=empresa_a,
        id_almacen=alm_ubic,
        codigo_ubicacion="B-01-01",
        nombre_ubicacion="Bóveda Restringida",
        tipo_ubicacion="CUARENTENA",
        requiere_autorizacion=True,
    )
    u_simple = UbicacionAlmacen.objects.create(
        id_empresa=empresa_a,
        id_almacen=alm_simple,
        codigo_ubicacion="S-01",
        nombre_ubicacion="Estante Simple",
        tipo_ubicacion="ESTANTERIA",
    )
    u_otro = UbicacionAlmacen.objects.create(
        id_empresa=empresa_a,
        id_almacen=alm_otro,
        codigo_ubicacion="O-01",
        nombre_ubicacion="Estante Otro",
        tipo_ubicacion="ESTANTERIA",
    )
    return SimpleNamespace(
        empresa=empresa_a,
        user=user_a,
        producto=producto,
        alm_simple=alm_simple,
        alm_ubic=alm_ubic,
        alm_otro=alm_otro,
        u_pick=u_pick,
        u_res=u_res,
        u_simple=u_simple,
        u_otro=u_otro,
    )


class TestServiciosStockUbicacion:
    def test_almacen_sin_usa_ubicaciones_bloquea_transferencia_y_reserva(self, setup_alm_a):
        s = setup_alm_a
        with pytest.raises(UbicacionOperacionError, match="no tiene habilitado el manejo por ubicaciones"):
            transferir_entre_ubicaciones(
                empresa=s.empresa,
                almacen=s.alm_simple,
                ubicacion_origen=s.u_simple,
                ubicacion_destino=s.u_simple,
                producto=s.producto,
                cantidad=Decimal("1"),
                usuario=s.user,
            )
        with pytest.raises(UbicacionOperacionError, match="no tiene habilitado el manejo por ubicaciones"):
            reservar_ubicacion(
                empresa=s.empresa,
                almacen=s.alm_simple,
                ubicacion=s.u_simple,
                producto=s.producto,
                cantidad=Decimal("1"),
            )

    def test_transferencia_entre_ubicaciones_no_altera_stock_actual_y_audita_kardex(self, setup_alm_a):
        s = setup_alm_a
        stock_global = StockActual.objects.create(
            id_empresa=s.empresa,
            id_producto=s.producto,
            id_almacen=s.alm_ubic,
            cantidad_disponible=Decimal("20.0000"),
        )
        u_dest = UbicacionAlmacen.objects.create(
            id_empresa=s.empresa,
            id_almacen=s.alm_ubic,
            codigo_ubicacion="A-02-01",
            nombre_ubicacion="Estantería 2",
            tipo_ubicacion="ESTANTERIA",
            requiere_autorizacion=False,
        )
        StockUbicacion.objects.create(
            id_empresa=s.empresa,
            id_almacen=s.alm_ubic,
            id_ubicacion=s.u_pick,
            id_producto=s.producto,
            cantidad_disponible=Decimal("15.0000"),
        )

        orig, dest, mov = transferir_entre_ubicaciones(
            empresa=s.empresa,
            almacen=s.alm_ubic,
            ubicacion_origen=s.u_pick,
            ubicacion_destino=u_dest,
            producto=s.producto,
            cantidad=Decimal("6.0000"),
            usuario=s.user,
            observaciones="Reacomodo de picking",
        )
        assert orig.cantidad_disponible == Decimal("9.0000")
        assert dest.cantidad_disponible == Decimal("6.0000")
        assert mov.tipo_movimiento == "TRANSFERENCIA_UBICACION"
        assert mov.id_almacen_origen_id == s.alm_ubic.id_almacen
        assert mov.id_almacen_destino_id == s.alm_ubic.id_almacen
        assert delta_para_almacen(mov, s.alm_ubic.id_almacen) == Decimal("0")

        stock_global.refresh_from_db()
        assert stock_global.cantidad_disponible == Decimal("20.0000")

        # Errores de validación de ubicación / cantidad
        with pytest.raises(UbicacionOperacionError, match="deben ser distintas"):
            transferir_entre_ubicaciones(
                empresa=s.empresa,
                almacen=s.alm_ubic,
                ubicacion_origen=s.u_pick,
                ubicacion_destino=s.u_pick,
                producto=s.producto,
                cantidad=Decimal("1"),
                usuario=s.user,
            )
        with pytest.raises(UbicacionOperacionError, match="no pertenece al almacén"):
            transferir_entre_ubicaciones(
                empresa=s.empresa,
                almacen=s.alm_ubic,
                ubicacion_origen=s.u_pick,
                ubicacion_destino=s.u_otro,
                producto=s.producto,
                cantidad=Decimal("1"),
                usuario=s.user,
            )
        with pytest.raises(UbicacionOperacionError, match="Stock libre insuficiente"):
            transferir_entre_ubicaciones(
                empresa=s.empresa,
                almacen=s.alm_ubic,
                ubicacion_origen=s.u_pick,
                ubicacion_destino=u_dest,
                producto=s.producto,
                cantidad=Decimal("100.0000"),
                usuario=s.user,
            )

    def test_requiere_autorizacion_valida_usuario_supervisor_y_staff(self, setup_alm_a, user_b):
        s = setup_alm_a
        StockUbicacion.objects.create(
            id_empresa=s.empresa,
            id_almacen=s.alm_ubic,
            id_ubicacion=s.u_pick,
            id_producto=s.producto,
            cantidad_disponible=Decimal("10.0000"),
        )
        # Usuario normal sin autorizado_por -> bloqueado al tocar destino restringido
        with pytest.raises(AutorizacionUbicacionError):
            transferir_entre_ubicaciones(
                empresa=s.empresa,
                almacen=s.alm_ubic,
                ubicacion_origen=s.u_pick,
                ubicacion_destino=s.u_res,
                producto=s.producto,
                cantidad=Decimal("3.0000"),
                usuario=s.user,
            )

        # Auto-aprobación o supervisor sin privilegios (is_staff=False) -> bloqueado
        regular_otro = UsuariosFactory(empresa=s.empresa, is_staff=False)
        for cand in (s.user, regular_otro):
            with pytest.raises(AutorizacionUbicacionError):
                transferir_entre_ubicaciones(
                    empresa=s.empresa,
                    almacen=s.alm_ubic,
                    ubicacion_origen=s.u_pick,
                    ubicacion_destino=s.u_res,
                    producto=s.producto,
                    cantidad=Decimal("3.0000"),
                    usuario=s.user,
                    autorizado_por=cand,
                )

        # Supervisor staff inactivo o de otra empresa -> bloqueado
        staff_inactivo = UsuariosFactory(empresa=s.empresa, is_staff=True, is_active=False)
        with pytest.raises(AutorizacionUbicacionError):
            transferir_entre_ubicaciones(
                empresa=s.empresa,
                almacen=s.alm_ubic,
                ubicacion_origen=s.u_pick,
                ubicacion_destino=s.u_res,
                producto=s.producto,
                cantidad=Decimal("3.0000"),
                usuario=s.user,
                autorizado_por=staff_inactivo,
            )

        user_b.is_staff = True
        user_b.save(update_fields=["is_staff"])
        with pytest.raises(AutorizacionUbicacionError):
            transferir_entre_ubicaciones(
                empresa=s.empresa,
                almacen=s.alm_ubic,
                ubicacion_origen=s.u_pick,
                ubicacion_destino=s.u_res,
                producto=s.producto,
                cantidad=Decimal("3.0000"),
                usuario=s.user,
                autorizado_por=user_b,
            )

        # Supervisor staff activo de la misma empresa -> permitido con traza en observaciones
        supervisor = UsuariosFactory(empresa=s.empresa, is_staff=True, is_active=True)
        orig, dest, mov_sup = transferir_entre_ubicaciones(
            empresa=s.empresa,
            almacen=s.alm_ubic,
            ubicacion_origen=s.u_pick,
            ubicacion_destino=s.u_res,
            producto=s.producto,
            cantidad=Decimal("3.0000"),
            usuario=s.user,
            autorizado_por=supervisor,
        )
        assert dest.cantidad_disponible == Decimal("3.0000")
        assert orig.cantidad_disponible == Decimal("7.0000")
        assert f"(autorizado por {supervisor.username})" in mov_sup.observaciones

        # Origen restringido con usuario staff -> permitido sin autorizado_por explícito + traza
        staff_user = UsuariosFactory(empresa=s.empresa, is_staff=True, is_active=True)
        dest_after, orig_after, mov_staff = transferir_entre_ubicaciones(
            empresa=s.empresa,
            almacen=s.alm_ubic,
            ubicacion_origen=s.u_res,
            ubicacion_destino=s.u_pick,
            producto=s.producto,
            cantidad=Decimal("1.0000"),
            usuario=staff_user,
        )
        assert dest_after.cantidad_disponible == Decimal("2.0000")
        assert orig_after.cantidad_disponible == Decimal("8.0000")
        assert f"(autorizado por {staff_user.username})" in mov_staff.observaciones

    def test_reservar_y_liberar_ubicacion(self, setup_alm_a):
        s = setup_alm_a
        StockUbicacion.objects.create(
            id_empresa=s.empresa,
            id_almacen=s.alm_ubic,
            id_ubicacion=s.u_pick,
            id_producto=s.producto,
            cantidad_disponible=Decimal("10.0000"),
        )
        su = reservar_ubicacion(
            empresa=s.empresa,
            almacen=s.alm_ubic,
            ubicacion=s.u_pick,
            producto=s.producto,
            cantidad=Decimal("4.0000"),
        )
        assert su.cantidad_reservada == Decimal("4.0000")

        with pytest.raises(UbicacionOperacionError, match="Stock libre insuficiente"):
            reservar_ubicacion(
                empresa=s.empresa,
                almacen=s.alm_ubic,
                ubicacion=s.u_pick,
                producto=s.producto,
                cantidad=Decimal("7.0000"),
            )

        su = reservar_ubicacion(
            empresa=s.empresa,
            almacen=s.alm_ubic,
            ubicacion=s.u_pick,
            producto=s.producto,
            cantidad=Decimal("2.5000"),
            liberar=True,
        )
        assert su.cantidad_reservada == Decimal("1.5000")

        with pytest.raises(UbicacionOperacionError, match="Reserva insuficiente para liberar"):
            reservar_ubicacion(
                empresa=s.empresa,
                almacen=s.alm_ubic,
                ubicacion=s.u_pick,
                producto=s.producto,
                cantidad=Decimal("5.0000"),
                liberar=True,
            )


class TestAPIRestStockUbicaciones:
    def test_api_ubicaciones_toggle_crud_transferir_y_reservar(self, client_a, setup_alm_a):
        s = setup_alm_a
        base = "/api/almacenes/stock-ubicaciones/"

        # Toggle usa_ubicaciones en almacén
        r_alm = client_a.patch(
            f"/api/almacenes/almacenes/{s.alm_simple.id_almacen}/",
            {"usa_ubicaciones": False},
            format="json",
        )
        assert r_alm.status_code == 200
        assert r_alm.json()["usa_ubicaciones"] is False

        # Almacén sin usa_ubicaciones rechaza POST en stock-ubicaciones
        r_no_ubic = client_a.post(
            base,
            {
                "id_almacen": str(s.alm_simple.id_almacen),
                "id_ubicacion": str(s.u_simple.id_ubicacion),
                "id_producto": str(s.producto.id_producto),
                "cantidad_disponible": "5.0000",
            },
            format="json",
        )
        assert r_no_ubic.status_code == 400

        # Carga inicial en almacén zonificado + variante support
        r_create = client_a.post(
            base,
            {
                "id_almacen": str(s.alm_ubic.id_almacen),
                "id_ubicacion": str(s.u_pick.id_ubicacion),
                "id_producto": str(s.producto.id_producto),
                "cantidad_disponible": "14.0000",
            },
            format="json",
        )
        assert r_create.status_code == 201, r_create.content
        stock_id = r_create.json()["id_stock_ubicacion"]

        # Duplicado sin variante -> 400; PATCH directo está bloqueado (405, solo transferir/reservar)
        r_dup = client_a.post(
            base,
            {
                "id_almacen": str(s.alm_ubic.id_almacen),
                "id_ubicacion": str(s.u_pick.id_ubicacion),
                "id_producto": str(s.producto.id_producto),
                "cantidad_disponible": "3.0000",
            },
            format="json",
        )
        assert r_dup.status_code == 400
        assert (
            client_a.patch(f"{base}{stock_id}/", {"cantidad_disponible": "99.0000"}, format="json").status_code == 405
        )

        # Con variante en la misma ubicación sí convive
        var = VarianteProducto.objects.create(id_producto=s.producto, codigo_variante="V1", sku="BUJ-V1")
        r_var = client_a.post(
            base,
            {
                "id_almacen": str(s.alm_ubic.id_almacen),
                "id_ubicacion": str(s.u_pick.id_ubicacion),
                "id_producto": str(s.producto.id_producto),
                "id_variante": str(var.id_variante),
                "cantidad_disponible": "5.0000",
            },
            format="json",
        )
        assert r_var.status_code == 201, r_var.content

        # Transferencia hacia ubicación con requiere_autorizacion como usuario regular
        # (incluso intentando suplantar id_autorizado_por en el JSON) -> 403
        staff_user = UsuariosFactory(empresa=s.empresa, is_staff=True, is_active=True)
        r_403 = client_a.post(
            f"{base}transferir/",
            {
                "id_almacen": str(s.alm_ubic.id_almacen),
                "id_ubicacion_origen": str(s.u_pick.id_ubicacion),
                "id_ubicacion_destino": str(s.u_res.id_ubicacion),
                "id_producto": str(s.producto.id_producto),
                "cantidad": "4.0000",
                "id_autorizado_por": str(staff_user.pk),
            },
            format="json",
        )
        assert r_403.status_code == 403

        # Transferencia realizada por usuario staff autenticado -> 200 y traza en observaciones
        client_staff = APIClient()
        client_staff.force_authenticate(user=staff_user)
        r_200 = client_staff.post(
            f"{base}transferir/",
            {
                "id_almacen": str(s.alm_ubic.id_almacen),
                "id_ubicacion_origen": str(s.u_pick.id_ubicacion),
                "id_ubicacion_destino": str(s.u_res.id_ubicacion),
                "id_producto": str(s.producto.id_producto),
                "cantidad": "4.0000",
                "observaciones": "Ingreso a cuarentena",
            },
            format="json",
        )
        assert r_200.status_code == 200, r_200.content
        assert r_200.json()["tipo_movimiento"] == "TRANSFERENCIA_UBICACION"
        assert r_200.json()["destino"]["cantidad_disponible"] == "4.0000"
        mov_aut = MovimientoInventario.objects.get(pk=r_200.json()["id_movimiento"])
        assert f"(autorizado por {staff_user.username})" in mov_aut.observaciones

        # Reservar y liberar via API
        r_res = client_a.post(
            f"{base}reservar/",
            {
                "id_almacen": str(s.alm_ubic.id_almacen),
                "id_ubicacion": str(s.u_pick.id_ubicacion),
                "id_producto": str(s.producto.id_producto),
                "cantidad": "3.0000",
                "liberar": False,
            },
            format="json",
        )
        assert r_res.status_code == 200, r_res.content
        assert r_res.json()["cantidad_reservada"] == "3.0000"
        assert r_res.json()["cantidad_libre"] == "7.0000"

        # Filtros y NUL guards
        r_list = client_a.get(
            f"{base}?almacen={s.alm_ubic.id_almacen}&ubicacion={s.u_res.id_ubicacion}&producto={s.producto.id_producto}"
        )
        assert r_list.status_code == 200
        assert client_a.get(f"{base}?search=x%00").status_code == 400
        assert client_a.get(f"/api/almacenes/ubicaciones-almacen/?almacen={s.alm_ubic.id_almacen}").status_code == 200
        assert client_a.get("/api/almacenes/ubicaciones-almacen/?search=x%00").status_code == 400


@pytest.mark.tenant
class TestAislamientoRLSMatrizStockUbicacion:
    def test_idor_cross_tenant_y_matriz_subsidiaria(
        self, client_a, client_b, setup_alm_a, empresa_b, user_a, user_b, moneda_usd
    ):
        s = setup_alm_a
        su_a = StockUbicacion.objects.create(
            id_empresa=s.empresa,
            id_almacen=s.alm_ubic,
            id_ubicacion=s.u_pick,
            id_producto=s.producto,
            cantidad_disponible=Decimal("10.0000"),
        )
        assert client_b.get(f"/api/almacenes/stock-ubicaciones/{su_a.pk}/").status_code == 404
        assert (
            client_b.post(
                "/api/almacenes/stock-ubicaciones/transferir/",
                {
                    "id_almacen": str(s.alm_ubic.id_almacen),
                    "id_ubicacion_origen": str(s.u_pick.id_ubicacion),
                    "id_ubicacion_destino": str(s.u_res.id_ubicacion),
                    "id_producto": str(s.producto.id_producto),
                    "cantidad": "1",
                },
                format="json",
            ).status_code
            == 404
        )
        assert (
            client_b.post(
                "/api/almacenes/stock-ubicaciones/reservar/",
                {
                    "id_almacen": str(s.alm_ubic.id_almacen),
                    "id_ubicacion": str(s.u_pick.id_ubicacion),
                    "id_producto": str(s.producto.id_producto),
                    "cantidad": "1",
                },
                format="json",
            ).status_code
            == 404
        )

        r_cross = client_b.post(
            "/api/almacenes/stock-ubicaciones/",
            {
                "id_almacen": str(s.alm_ubic.id_almacen),
                "id_ubicacion": str(s.u_pick.id_ubicacion),
                "id_producto": str(s.producto.id_producto),
                "cantidad_disponible": "5",
            },
            format="json",
        )
        assert r_cross.status_code == 400

        # Matriz-Subsidiaria: usuario en matriz + subsidiaria no puede mezclar FKs
        sub = EmpresaFactory(empresa_matriz=s.empresa)
        alm_sub = AlmacenFactory(id_empresa=sub, usa_ubicaciones=True)
        u_sub = UbicacionAlmacen.objects.create(
            id_empresa=sub,
            id_almacen=alm_sub,
            codigo_ubicacion="SUB-01",
            nombre_ubicacion="Sub",
            tipo_ubicacion="ESTANTERIA",
        )
        user_a.empresas.add(sub)
        r_mix = client_a.post(
            "/api/almacenes/stock-ubicaciones/",
            {
                "id_almacen": str(alm_sub.id_almacen),
                "id_ubicacion": str(u_sub.id_ubicacion),
                "id_producto": str(s.producto.id_producto),
                "cantidad_disponible": "5",
            },
            format="json",
        )
        assert r_mix.status_code == 400

        # is_staff de otra empresa ajena (empresa_b) NO puede transferir sobre ubicación restringida de empresa_a
        user_b.is_staff = True
        user_b.save(update_fields=["is_staff"])
        assert (
            client_b.post(
                "/api/almacenes/stock-ubicaciones/transferir/",
                {
                    "id_almacen": str(s.alm_ubic.id_almacen),
                    "id_ubicacion_origen": str(s.u_pick.id_ubicacion),
                    "id_ubicacion_destino": str(s.u_res.id_ubicacion),
                    "id_producto": str(s.producto.id_producto),
                    "cantidad": "1",
                },
                format="json",
            ).status_code
            == 404
        )

        # is_staff de Matriz SÍ puede autorizar transferencia en almacén de Subsidiaria -> 200
        u_sub_res = UbicacionAlmacen.objects.create(
            id_empresa=sub,
            id_almacen=alm_sub,
            codigo_ubicacion="SUB-RES",
            nombre_ubicacion="Sub Restringida",
            tipo_ubicacion="CUARENTENA",
            requiere_autorizacion=True,
        )
        u_sub_un = UnidadMedidaFactory(id_empresa=sub)
        cat_sub = CategoriaProductoFactory(id_empresa=sub)
        prod_sub = ProductoFactory(
            id_empresa=sub,
            id_unidad_medida_base=u_sub_un,
            id_categoria=cat_sub,
            id_moneda_precio=moneda_usd,
        )
        StockUbicacion.objects.create(
            id_empresa=sub,
            id_almacen=alm_sub,
            id_ubicacion=u_sub,
            id_producto=prod_sub,
            cantidad_disponible=Decimal("6.0000"),
        )
        matriz_staff = UsuariosFactory(empresa=s.empresa, is_staff=True, is_active=True)
        client_ms = APIClient()
        client_ms.force_authenticate(user=matriz_staff)
        r_ms = client_ms.post(
            "/api/almacenes/stock-ubicaciones/transferir/",
            {
                "id_almacen": str(alm_sub.id_almacen),
                "id_ubicacion_origen": str(u_sub.id_ubicacion),
                "id_ubicacion_destino": str(u_sub_res.id_ubicacion),
                "id_producto": str(prod_sub.id_producto),
                "cantidad": "2.0000",
            },
            format="json",
        )
        assert r_ms.status_code == 200, r_ms.content
        mov_ms = MovimientoInventario.objects.get(pk=r_ms.json()["id_movimiento"])
        assert f"(autorizado por {matriz_staff.username})" in mov_ms.observaciones

    def test_rls_postgresql_en_stock_ubicacion(self, rls_test_role, setup_alm_a, empresa_b, moneda_usd):
        s = setup_alm_a
        su_a = StockUbicacion.objects.create(
            id_empresa=s.empresa,
            id_almacen=s.alm_ubic,
            id_ubicacion=s.u_pick,
            id_producto=s.producto,
            cantidad_disponible=Decimal("8.0000"),
        )
        u_b = UnidadMedidaFactory(id_empresa=empresa_b)
        c_b = CategoriaProductoFactory(id_empresa=empresa_b)
        p_b = ProductoFactory(
            id_empresa=empresa_b,
            id_unidad_medida_base=u_b,
            id_categoria=c_b,
            id_moneda_precio=moneda_usd,
        )
        alm_b = AlmacenFactory(id_empresa=empresa_b, usa_ubicaciones=True)
        ub_b = UbicacionAlmacen.objects.create(
            id_empresa=empresa_b,
            id_almacen=alm_b,
            codigo_ubicacion="B-01",
            nombre_ubicacion="B1",
            tipo_ubicacion="ESTANTERIA",
        )
        su_b = StockUbicacion.objects.create(
            id_empresa=empresa_b,
            id_almacen=alm_b,
            id_ubicacion=ub_b,
            id_producto=p_b,
            cantidad_disponible=Decimal("4.0000"),
        )

        with connection.cursor() as cur:
            if rls_test_role is not None:
                cur.execute(f'SET ROLE "{rls_test_role}"')
            try:
                rls.apply_context([s.empresa.id_empresa], bypass=False)
                assert list(StockUbicacion.objects.values_list("pk", flat=True)) == [su_a.pk]

                rls.apply_context([empresa_b.id_empresa], bypass=False)
                assert list(StockUbicacion.objects.values_list("pk", flat=True)) == [su_b.pk]

                rls.apply_context([], bypass=False)
                assert StockUbicacion.objects.count() == 0
            finally:
                rls.apply_system_default()
                if rls_test_role is not None:
                    cur.execute("RESET ROLE")


class TestCoberturaRamasStockUbicaciones:
    def test_ramas_edge_servicios_y_modelos_ubicacion(self, setup_alm_a, empresa_b, moneda_usd):
        s = setup_alm_a
        su = StockUbicacion.objects.create(
            id_empresa=s.empresa,
            id_almacen=s.alm_ubic,
            id_ubicacion=s.u_pick,
            id_producto=s.producto,
            cantidad_disponible=Decimal("10.0000"),
            activo=True,
        )
        assert s.producto.nombre_producto in str(su)

        with pytest.raises(UbicacionOperacionError, match="obligatorio"):
            transferir_entre_ubicaciones(
                empresa=s.empresa,
                almacen=s.alm_ubic,
                ubicacion_origen=s.u_pick,
                ubicacion_destino=s.u_res,
                producto=s.producto,
                cantidad=Decimal("1"),
                usuario=None,
            )

        for bad in (None, True, "abc", Decimal("0"), Decimal("-2")):
            with pytest.raises(UbicacionOperacionError):
                reservar_ubicacion(
                    empresa=s.empresa,
                    almacen=s.alm_ubic,
                    ubicacion=s.u_pick,
                    producto=s.producto,
                    cantidad=bad,
                )

        # No existe stock en ubicación destino -> error tanto en transferir como en reservar
        staff_aut = UsuariosFactory(empresa=s.empresa, is_staff=True, is_active=True)
        with pytest.raises(UbicacionOperacionError, match="Sin existencias"):
            transferir_entre_ubicaciones(
                empresa=s.empresa,
                almacen=s.alm_ubic,
                ubicacion_origen=s.u_res,
                ubicacion_destino=s.u_pick,
                producto=s.producto,
                cantidad=Decimal("1"),
                usuario=s.user,
                autorizado_por=staff_aut,
            )
        with pytest.raises(UbicacionOperacionError, match="No existe stock"):
            reservar_ubicacion(
                empresa=s.empresa,
                almacen=s.alm_ubic,
                ubicacion=s.u_res,
                producto=s.producto,
                cantidad=Decimal("1"),
            )

        # Ubicación inactiva, almacén de otra empresa, producto de otra empresa, variante ajena
        u_inact = UbicacionAlmacen.objects.create(
            id_empresa=s.empresa,
            id_almacen=s.alm_ubic,
            codigo_ubicacion="INACT-1",
            nombre_ubicacion="Inactiva",
            tipo_ubicacion="ESTANTERIA",
            activo=False,
        )
        with pytest.raises(UbicacionOperacionError, match="inactiva"):
            reservar_ubicacion(
                empresa=s.empresa,
                almacen=s.alm_ubic,
                ubicacion=u_inact,
                producto=s.producto,
                cantidad=Decimal("1"),
            )
        with pytest.raises(UbicacionOperacionError, match="no pertenece a la empresa"):
            reservar_ubicacion(
                empresa=empresa_b,
                almacen=s.alm_ubic,
                ubicacion=s.u_pick,
                producto=s.producto,
                cantidad=Decimal("1"),
            )

        # Reactivar StockUbicacion inactivo en destino al transferir
        u_dest_inact = UbicacionAlmacen.objects.create(
            id_empresa=s.empresa,
            id_almacen=s.alm_ubic,
            codigo_ubicacion="DEST-RE",
            nombre_ubicacion="Dest Reactivar",
            tipo_ubicacion="ESTANTERIA",
        )
        StockUbicacion.objects.create(
            id_empresa=s.empresa,
            id_almacen=s.alm_ubic,
            id_ubicacion=u_dest_inact,
            id_producto=s.producto,
            cantidad_disponible=Decimal("0.0000"),
            activo=False,
        )
        _, dest, _ = transferir_entre_ubicaciones(
            empresa=s.empresa,
            almacen=s.alm_ubic,
            ubicacion_origen=s.u_pick,
            ubicacion_destino=u_dest_inact,
            producto=s.producto,
            cantidad=Decimal("2.0000"),
            usuario=s.user,
        )
        assert dest.activo is True
        assert dest.cantidad_disponible == Decimal("2.0000")

    def test_ramas_edge_api_almacenes_y_stock_ubicaciones(self, client_a, setup_alm_a, empresa_b):
        import uuid

        s = setup_alm_a
        base = "/api/almacenes/stock-ubicaciones/"

        # Código duplicado de almacén y ubicación -> 400
        assert (
            client_a.post(
                "/api/almacenes/almacenes/",
                {
                    "id_empresa": str(s.empresa.id_empresa),
                    "nombre_almacen": "Dup",
                    "codigo_almacen": s.alm_ubic.codigo_almacen,
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/almacenes/ubicaciones-almacen/",
                {
                    "id_empresa": str(s.empresa.id_empresa),
                    "id_almacen": str(s.alm_ubic.id_almacen),
                    "codigo_ubicacion": s.u_pick.codigo_ubicacion,
                    "nombre_ubicacion": "Dup",
                    "tipo_ubicacion": "ESTANTERIA",
                },
                format="json",
            ).status_code
            == 400
        )

        # Validaciones StockUbicacionSerializer (negativo, reservada > disponible, ubicacion otro almacen, variante ajena)
        assert (
            client_a.post(
                base,
                {
                    "id_almacen": str(s.alm_ubic.id_almacen),
                    "id_ubicacion": str(s.u_pick.id_ubicacion),
                    "id_producto": str(s.producto.id_producto),
                    "cantidad_disponible": "-1",
                },
                format="json",
            ).status_code
            == 400
        )
        # cantidad_reservada es read_only: no se puede inyectar por POST; variante de otro producto -> 400
        r_ro = client_a.post(
            base,
            {
                "id_almacen": str(s.alm_ubic.id_almacen),
                "id_ubicacion": str(s.u_pick.id_ubicacion),
                "id_producto": str(s.producto.id_producto),
                "cantidad_disponible": "3",
                "cantidad_reservada": "5",
            },
            format="json",
        )
        assert r_ro.status_code == 201
        assert r_ro.json()["cantidad_reservada"] == "0.0000"

        otro_prod = ProductoFactory(id_empresa=s.empresa)
        var_ajena = VarianteProducto.objects.create(id_producto=otro_prod, codigo_variante="VA", sku="VA-1")
        assert (
            client_a.post(
                base,
                {
                    "id_almacen": str(s.alm_ubic.id_almacen),
                    "id_ubicacion": str(s.u_pick.id_ubicacion),
                    "id_producto": str(s.producto.id_producto),
                    "id_variante": str(var_ajena.id_variante),
                    "cantidad_disponible": "2",
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                base,
                {
                    "id_almacen": str(s.alm_ubic.id_almacen),
                    "id_ubicacion": str(s.u_otro.id_ubicacion),
                    "id_producto": str(s.producto.id_producto),
                    "cantidad_disponible": "5",
                },
                format="json",
            ).status_code
            == 400
        )

        # Endpoints transferir/reservar 404 con UUID inexistentes, 400 en error negocio, uuid param inválido
        assert client_a.get(f"{base}?almacen=bad-uuid").status_code == 400
        assert client_a.get("/api/almacenes/ubicaciones-almacen/?almacen=bad-uuid").status_code == 400
        assert (
            client_a.post(
                f"{base}transferir/",
                {
                    "id_almacen": str(uuid.uuid4()),
                    "id_ubicacion_origen": str(s.u_pick.id_ubicacion),
                    "id_ubicacion_destino": str(s.u_res.id_ubicacion),
                    "id_producto": str(s.producto.id_producto),
                    "cantidad": "1",
                },
                format="json",
            ).status_code
            == 404
        )
        assert (
            client_a.post(
                f"{base}transferir/",
                {
                    "id_almacen": str(s.alm_ubic.id_almacen),
                    "id_ubicacion_origen": str(s.u_pick.id_ubicacion),
                    "id_ubicacion_destino": str(uuid.uuid4()),
                    "id_producto": str(s.producto.id_producto),
                    "cantidad": "1",
                },
                format="json",
            ).status_code
            == 404
        )
        assert (
            client_a.post(
                f"{base}transferir/",
                {
                    "id_almacen": str(s.alm_ubic.id_almacen),
                    "id_ubicacion_origen": str(s.u_pick.id_ubicacion),
                    "id_ubicacion_destino": str(s.u_pick.id_ubicacion),
                    "id_producto": str(s.producto.id_producto),
                    "cantidad": "1",
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                f"{base}reservar/",
                {
                    "id_almacen": str(s.alm_ubic.id_almacen),
                    "id_ubicacion": str(uuid.uuid4()),
                    "id_producto": str(s.producto.id_producto),
                    "cantidad": "1",
                },
                format="json",
            ).status_code
            == 404
        )
        assert (
            client_a.post(
                f"{base}reservar/",
                {
                    "id_almacen": str(s.alm_ubic.id_almacen),
                    "id_ubicacion": str(s.u_res.id_ubicacion),
                    "id_producto": str(s.producto.id_producto),
                    "cantidad": "1",
                },
                format="json",
            ).status_code
            == 400
        )

        # Producto / variante no encontrados en transferir -> 404
        assert (
            client_a.post(
                f"{base}transferir/",
                {
                    "id_almacen": str(s.alm_ubic.id_almacen),
                    "id_ubicacion_origen": str(s.u_pick.id_ubicacion),
                    "id_ubicacion_destino": str(s.u_res.id_ubicacion),
                    "id_producto": str(uuid.uuid4()),
                    "cantidad": "1",
                },
                format="json",
            ).status_code
            == 404
        )
        assert (
            client_a.post(
                f"{base}transferir/",
                {
                    "id_almacen": str(s.alm_ubic.id_almacen),
                    "id_ubicacion_origen": str(s.u_pick.id_ubicacion),
                    "id_ubicacion_destino": str(s.u_res.id_ubicacion),
                    "id_producto": str(s.producto.id_producto),
                    "id_variante": str(uuid.uuid4()),
                    "cantidad": "1",
                },
                format="json",
            ).status_code
            == 404
        )

        # UbicacionAlmacen CRUD PATCH y duplicado PATCH
        r_ub = client_a.post(
            "/api/almacenes/ubicaciones-almacen/",
            {
                "id_empresa": str(s.empresa.id_empresa),
                "id_almacen": str(s.alm_ubic.id_almacen),
                "codigo_ubicacion": "Z-99",
                "nombre_ubicacion": "Zona 99",
                "tipo_ubicacion": "ESTANTERIA",
            },
            format="json",
        )
        assert r_ub.status_code == 201
        ub_id = r_ub.json()["id_ubicacion"]
        assert (
            client_a.patch(
                f"/api/almacenes/ubicaciones-almacen/{ub_id}/",
                {"nombre_ubicacion": "Zona 99 Mod"},
                format="json",
            ).status_code
            == 200
        )
        assert (
            client_a.patch(
                f"/api/almacenes/ubicaciones-almacen/{ub_id}/",
                {"codigo_ubicacion": s.u_pick.codigo_ubicacion},
                format="json",
            ).status_code
            == 400
        )

        # [BLOQUEANTE #2] AlmacenSerializer y UbicacionAlmacenSerializer bloquean cambio de id_empresa en PATCH
        assert (
            client_a.patch(
                f"/api/almacenes/almacenes/{s.alm_ubic.id_almacen}/",
                {"id_empresa": str(empresa_b.id_empresa)},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.patch(
                f"/api/almacenes/ubicaciones-almacen/{ub_id}/",
                {"id_empresa": str(empresa_b.id_empresa)},
                format="json",
            ).status_code
            == 400
        )
        # UbicacionAlmacen sin stock sí permite cambiar de almacén; con StockUbicacion registrado -> 400
        assert (
            client_a.patch(
                f"/api/almacenes/ubicaciones-almacen/{ub_id}/",
                {"id_almacen": str(s.alm_simple.id_almacen)},
                format="json",
            ).status_code
            == 200
        )
        ub_con_stock = UbicacionAlmacen.objects.create(
            id_empresa=s.empresa,
            id_almacen=s.alm_ubic,
            codigo_ubicacion="STK-99",
            nombre_ubicacion="Con Stock",
            tipo_ubicacion="ESTANTERIA",
        )
        StockUbicacion.objects.create(
            id_empresa=s.empresa,
            id_almacen=s.alm_ubic,
            id_ubicacion=ub_con_stock,
            id_producto=s.producto,
            cantidad_disponible=Decimal("1.0000"),
        )
        assert (
            client_a.patch(
                f"/api/almacenes/ubicaciones-almacen/{ub_con_stock.id_ubicacion}/",
                {"id_almacen": str(s.alm_simple.id_almacen)},
                format="json",
            ).status_code
            == 400
        )
