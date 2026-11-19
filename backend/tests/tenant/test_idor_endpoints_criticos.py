"""
P1-6 (R7): Suite cross-tenant anti-IDOR por PK directo y acciones @action(detail=True/False).

Verifica que un usuario autenticado de Empresa A NO puede leer, modificar, eliminar ni ejecutar
acciones sobre recursos pertenecientes a Empresa B mediante su PK directo ni explotar endpoints
con filas globales/públicas o validaciones de FK sin scoping tenant.
"""

from datetime import date
from decimal import Decimal
import uuid

from django.utils import timezone
import pytest

from apps.auditoria.models import LogAuditoria
from apps.banca_electronica.models import CuentaBancariaEmpresa as CuentaBancaElectronica
from apps.compras.models import OrdenCompra
from apps.contabilidad.models import AsientoContable
from apps.control_asistencia.models import RegistroAsistencia, ResumenAsistenciaDiario
from apps.core.models import Notificacion, Permisos, Sucursal, Usuarios
from apps.crm.models import Cliente
from apps.cuentas_por_cobrar.models import CuentaPorCobrar
from apps.cuentas_por_pagar.models import CuentaPorPagar
from apps.finanzas.models import (
    Caja,
    CajaFisica,
    CuentaBancariaEmpresa,
    Datafono,
    DepositoDatafono,
    MetodoPago,
    Moneda,
    MovimientoCajaBanco,
    Pago,
    SesionDatafono,
    TasaCambio,
    TransaccionDatafono,
    TransaccionFinanciera,
)
from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida
from apps.proveedores.models import Proveedor
from apps.rrhh.models import Cargo, Empleado
from apps.servicio_cliente.models import CategoriaTicket, InteraccionTicket, TicketSoporte
from apps.tesoreria.models import OperacionCambioDivisa
from apps.ventas.models import Pedido

pytestmark = pytest.mark.tenant


@pytest.fixture
def sucursal_a(db, empresa_a):
    return Sucursal.objects.create(id_empresa=empresa_a, nombre="Sucursal A", codigo_sucursal="SUC-A1")


@pytest.fixture
def sucursal_b(db, empresa_b):
    return Sucursal.objects.create(id_empresa=empresa_b, nombre="Sucursal B", codigo_sucursal="SUC-B1")


@pytest.fixture
def finanzas_b(db, empresa_a, empresa_b, user_a, user_b, sucursal_a, sucursal_b, moneda_usd, metodo_efectivo):
    caja_a = Caja.objects.create(empresa=empresa_a, sucursal=sucursal_a, nombre="Caja A", moneda=moneda_usd)
    caja_b = Caja.objects.create(empresa=empresa_b, sucursal=sucursal_b, nombre="Caja B", moneda=moneda_usd)
    cf_a = CajaFisica.objects.create(
        empresa=empresa_a,
        sucursal=sucursal_a,
        nombre="CF A",
        identificador_dispositivo=f"DEV-A-{uuid.uuid4().hex[:8]}",
    )
    cf_b = CajaFisica.objects.create(
        empresa=empresa_b,
        sucursal=sucursal_b,
        nombre="CF B",
        identificador_dispositivo=f"DEV-B-{uuid.uuid4().hex[:8]}",
    )

    banco_a = CuentaBancariaEmpresa.objects.create(
        id_empresa=empresa_a,
        nombre_banco="Banco A",
        numero_cuenta=f"CTA-A-{uuid.uuid4().hex[:8]}",
        tipo_cuenta="CORRIENTE",
        id_moneda=moneda_usd,
    )
    banco_b = CuentaBancariaEmpresa.objects.create(
        id_empresa=empresa_b,
        nombre_banco="Banco B",
        numero_cuenta=f"CTA-B-{uuid.uuid4().hex[:8]}",
        tipo_cuenta="CORRIENTE",
        id_moneda=moneda_usd,
    )

    df_a = Datafono.objects.create(
        id_empresa=empresa_a,
        id_sucursal=sucursal_a,
        id_caja_fisica=cf_a,
        nombre="DF A",
        serial=f"SER-A-{uuid.uuid4().hex[:8]}",
        id_cuenta_bancaria_asociada=banco_a,
    )
    df_b = Datafono.objects.create(
        id_empresa=empresa_b,
        id_sucursal=sucursal_b,
        id_caja_fisica=cf_b,
        nombre="DF B",
        serial=f"SER-B-{uuid.uuid4().hex[:8]}",
        id_cuenta_bancaria_asociada=banco_b,
    )

    ahora = timezone.now()
    ses_a = SesionDatafono.objects.create(
        datafono=df_a,
        usuario_apertura=user_a,
        estado="CERRADA",
        fecha_cierre=ahora,
        total_transacciones=Decimal("25.00"),
        comision_calculada=Decimal("0.00"),
        neto_esperado=Decimal("25.00"),
    )
    dep_a = DepositoDatafono.objects.create(
        datafono=df_a,
        sesion_datafono=ses_a,
        lote_bancario=f"LOTE-A-{uuid.uuid4().hex[:8]}",
        fecha_envio=ahora,
        total_bruto=Decimal("25.00"),
        comision_banco=Decimal("0.00"),
        total_neto=Decimal("25.00"),
        usuario_envio=user_a,
    )

    ses_b = SesionDatafono.objects.create(
        datafono=df_b,
        usuario_apertura=user_b,
        estado="CERRADA",
        fecha_cierre=ahora,
        total_transacciones=Decimal("50.00"),
        comision_calculada=Decimal("0.00"),
        neto_esperado=Decimal("50.00"),
    )
    dep_b = DepositoDatafono.objects.create(
        datafono=df_b,
        sesion_datafono=ses_b,
        lote_bancario=f"LOTE-B-{uuid.uuid4().hex[:8]}",
        fecha_envio=ahora,
        total_bruto=Decimal("50.00"),
        comision_banco=Decimal("0.00"),
        total_neto=Decimal("50.00"),
        usuario_envio=user_b,
    )

    tx_fin_b = TransaccionFinanciera.objects.create(
        id_empresa=empresa_b,
        fecha_hora_transaccion=timezone.now(),
        tipo_transaccion="INGRESO",
        monto_transaccion=Decimal("50.00"),
        id_moneda_transaccion=moneda_usd,
        id_moneda_base=moneda_usd,
        monto_base_empresa=Decimal("50.00"),
        id_metodo_pago=metodo_efectivo,
        id_usuario_registro=user_b,
    )
    mov_b = MovimientoCajaBanco.objects.create(
        id_empresa=empresa_b,
        fecha_movimiento=date.today(),
        hora_movimiento=timezone.now().time(),
        tipo_movimiento="INGRESO",
        monto=Decimal("50.00"),
        id_moneda=moneda_usd,
        concepto="Mov B",
        id_cuenta_bancaria=banco_b,
        saldo_anterior=Decimal("0.00"),
        saldo_nuevo=Decimal("50.00"),
        id_usuario_registro=user_b,
    )
    pago_b = Pago.objects.create(
        id_empresa=empresa_b,
        tipo_operacion="INGRESO",
        tipo_documento="PEDIDO",
        id_documento=uuid.uuid4(),
        fecha_pago=timezone.now(),
        monto=Decimal("100.00"),
        id_moneda=moneda_usd,
        id_metodo_pago=metodo_efectivo,
    )
    return {
        "caja_a": caja_a,
        "caja_b": caja_b,
        "banco_a": banco_a,
        "banco_b": banco_b,
        "df_a": df_a,
        "df_b": df_b,
        "dep_a": dep_a,
        "dep_b": dep_b,
        "tx_fin_b": tx_fin_b,
        "mov_b": mov_b,
        "pago_b": pago_b,
    }


@pytest.mark.django_db
class TestIDORDocumentosOperativos:
    """Anti-IDOR cross-tenant en Ventas, Compras, CxC, CxP, Contabilidad, Tesorería, Banca e Inventario."""

    def test_idor_ventas_pedido_y_acciones_detail(self, client_a, empresa_b):
        cliente_b = Cliente.objects.create(id_empresa=empresa_b, razon_social="Cliente B", rif="J-90000001")
        pedido_b = Pedido.objects.create(
            id_empresa=empresa_b,
            id_cliente=cliente_b,
            numero_pedido="PED-B-001",
            fecha_pedido=date.today(),
        )
        base = f"/api/ventas/pedidos/{pedido_b.pk}/"
        assert client_a.get(base).status_code == 404
        assert client_a.patch(base, {"observaciones": "hack"}, format="json").status_code == 404
        assert client_a.put(base, {"observaciones": "hack"}, format="json").status_code == 404
        assert client_a.delete(base).status_code == 404
        assert client_a.post(f"{base}confirmar/", {}, format="json").status_code == 404
        assert client_a.post(f"{base}convertir-nota-venta/", {}, format="json").status_code == 404

        pedido_b.refresh_from_db()
        assert pedido_b.observaciones is None

    def test_idor_compras_orden_compra_y_aprobar(self, client_a, empresa_b):
        prov_b = Proveedor.objects.create(id_empresa=empresa_b, razon_social="Prov B", rif="J-80000001")
        oc_b = OrdenCompra.objects.create(
            id_empresa=empresa_b,
            id_proveedor=prov_b,
            numero_orden="OC-B-001",
            fecha_orden=date.today(),
        )
        base = f"/api/compras/ordenes-compra/{oc_b.pk}/"
        assert client_a.get(base).status_code == 404
        assert client_a.patch(base, {"observaciones": "hack"}, format="json").status_code == 404
        assert client_a.put(base, {"observaciones": "hack"}, format="json").status_code == 404
        assert client_a.delete(base).status_code == 404
        assert client_a.post(f"{base}aprobar/", {}, format="json").status_code == 404

        oc_b.refresh_from_db()
        assert oc_b.estado == "BORRADOR"

    def test_idor_cxc_y_cxp_por_pk(self, client_a, empresa_b):
        cliente_b = Cliente.objects.create(id_empresa=empresa_b, razon_social="Cliente CxC B", rif="J-90000002")
        cxc_b = CuentaPorCobrar.objects.create(
            empresa=empresa_b,
            cliente=cliente_b,
            monto=Decimal("250.00"),
            fecha_emision=date.today(),
            fecha_vencimiento=date.today(),
        )
        prov_b = Proveedor.objects.create(id_empresa=empresa_b, razon_social="Prov CxP B", rif="J-80000002")
        cxp_b = CuentaPorPagar.objects.create(
            id_empresa=empresa_b,
            id_proveedor=prov_b,
            monto_total=Decimal("400.00"),
            monto_pendiente=Decimal("400.00"),
            fecha_emision=date.today(),
            fecha_vencimiento=date.today(),
        )
        cxc_url = f"/api/cxc/cuentas-por-cobrar/{cxc_b.pk}/"
        assert client_a.get(cxc_url).status_code == 404
        assert client_a.patch(cxc_url, {"descripcion": "hack"}, format="json").status_code in (404, 405)
        assert client_a.put(cxc_url, {"descripcion": "hack"}, format="json").status_code in (404, 405)
        assert client_a.delete(cxc_url).status_code in (404, 405)

        cxp_url = f"/api/cuentas-por-pagar/cuentas-por-pagar/{cxp_b.pk}/"
        assert client_a.get(cxp_url).status_code == 404
        assert client_a.patch(cxp_url, {"descripcion": "hack"}, format="json").status_code in (404, 405)
        assert client_a.put(cxp_url, {"descripcion": "hack"}, format="json").status_code in (404, 405)
        assert client_a.delete(cxp_url).status_code in (404, 405)

        cxc_b.refresh_from_db()
        cxp_b.refresh_from_db()
        assert cxc_b.monto == Decimal("250.00")
        assert cxp_b.monto_pendiente == Decimal("400.00")

    def test_idor_contabilidad_asiento_y_aprobar_anular(self, client_a, empresa_b):
        asiento_b = AsientoContable.objects.create(
            id_empresa=empresa_b,
            fecha_asiento=date.today(),
            numero_asiento="AS-B-001",
            descripcion="Asiento privado B",
            estado_asiento="BORRADOR",
        )
        base = f"/api/contabilidad/asientos-contables/{asiento_b.pk}/"
        assert client_a.get(base).status_code == 404
        assert client_a.patch(base, {"descripcion": "hack"}, format="json").status_code == 404
        assert client_a.put(base, {"descripcion": "hack"}, format="json").status_code == 404
        assert client_a.delete(base).status_code == 404
        assert client_a.post(f"{base}aprobar/", {}, format="json").status_code == 404
        assert client_a.post(f"{base}anular/", {}, format="json").status_code == 404

        asiento_b.refresh_from_db()
        assert asiento_b.estado_asiento == "BORRADOR"

    def test_idor_tesoreria_y_banca_electronica(self, client_a, empresa_b, moneda_usd):
        moneda_dest = Moneda.objects.create(codigo_iso="EURX", nombre="Euro Test", simbolo="E", es_generica=True)
        op_b = OperacionCambioDivisa.objects.create(
            empresa=empresa_b,
            numero_operacion="FX-B-001",
            fecha_operacion=timezone.now(),
            tipo_operacion="COMPRA",
            moneda_origen=moneda_usd,
            moneda_destino=moneda_dest,
            monto_origen=Decimal("100.00"),
            tasa_cambio=Decimal("1.10"),
            monto_destino=Decimal("110.00"),
        )
        cta_b = CuentaBancaElectronica.objects.create(
            empresa=empresa_b,
            banco="Banesco B",
            numero_cuenta=f"0134{uuid.uuid4().hex[:12]}",
            tipo_cuenta="corriente",
            moneda=moneda_usd,
        )
        for url in (
            f"/api/tesoreria/operaciones-cambio-divisa/{op_b.pk}/",
            f"/api/banca-electronica/cuentas-bancarias-empresa/{cta_b.pk}/",
        ):
            assert client_a.get(url).status_code == 404
            assert client_a.patch(url, {"banco": "hack"}, format="json").status_code == 404
            assert client_a.delete(url).status_code == 404

    def test_idor_inventario_producto_y_kardex(self, client_a, empresa_b, moneda_usd):
        cat_b = CategoriaProducto.objects.create(id_empresa=empresa_b, nombre_categoria="Cat B")
        um_b = UnidadMedida.objects.create(id_empresa=empresa_b, nombre="Unidad B", abreviatura="UB", tipo="CANTIDAD")
        prod_b = Producto.objects.create(
            id_empresa=empresa_b,
            nombre_producto="Producto Secreto B",
            sku="SKU-B1",
            id_categoria=cat_b,
            id_unidad_medida_base=um_b,
            id_moneda_precio=moneda_usd,
        )
        base = f"/api/inventario/productos/{prod_b.pk}/"
        assert client_a.get(base).status_code == 404
        assert client_a.patch(base, {"nombre_producto": "Hack"}, format="json").status_code == 404
        assert client_a.delete(base).status_code == 404
        assert client_a.get(f"{base}kardex/").status_code == 404


@pytest.mark.django_db
class TestIDORFinanzasYCerradosEnPR9:
    """Cobertura directa de finanzas/pagos/datafonos y todos los huecos IDOR corregidos."""

    def test_idor_pagos_cajas_bancos_datafonos(self, client_a, finanzas_b):
        pago_b = finanzas_b["pago_b"]
        caja_b = finanzas_b["caja_b"]
        banco_b = finanzas_b["banco_b"]
        df_b = finanzas_b["df_b"]

        for url in (
            f"/api/finanzas/pagos/{pago_b.pk}/",
            f"/api/finanzas/cajas/{caja_b.pk}/",
            f"/api/finanzas/cajas/{caja_b.pk}/movimientos-caja-banco/",
            f"/api/finanzas/cuentas-bancarias/{banco_b.pk}/",
            f"/api/finanzas/cuentas-bancarias/{banco_b.pk}/movimientos-cuenta-bancaria/",
            f"/api/finanzas/datafonos/{df_b.pk}/",
        ):
            assert client_a.get(url).status_code == 404

        assert (
            client_a.patch(f"/api/finanzas/pagos/{pago_b.pk}/", {"referencia": "x"}, format="json").status_code == 404
        )
        assert client_a.delete(f"/api/finanzas/pagos/{pago_b.pk}/").status_code == 404
        assert client_a.post(f"/api/finanzas/datafonos/{df_b.pk}/cerrar-sesion/", {}, format="json").status_code == 404

    def test_datafono_registrar_pago_rechaza_transaccion_financiera_ajena(self, client_a, finanzas_b):
        df_a = finanzas_b["df_a"]
        tx_fin_b = finanzas_b["tx_fin_b"]
        antes = TransaccionDatafono.objects.filter(id_datafono=df_a).count()

        resp = client_a.post(
            f"/api/finanzas/datafonos/{df_a.pk}/registrar-pago/",
            {
                "monto": "25.00",
                "referencia_bancaria": "HACK",
                "id_transaccion_financiera_origen": str(tx_fin_b.pk),
            },
            format="json",
        )
        assert resp.status_code == 404
        assert TransaccionDatafono.objects.filter(id_datafono=df_a).count() == antes

    def test_deposito_conciliar_y_pendientes_no_fugan_ni_cruzan_tenant(self, client_a, finanzas_b):
        dep_a = finanzas_b["dep_a"]
        dep_b = finanzas_b["dep_b"]
        df_b = finanzas_b["df_b"]
        mov_b = finanzas_b["mov_b"]

        # Conciliar depósito propio con movimiento bancario de Empresa B -> 404
        resp_conc = client_a.post(
            f"/api/finanzas/depositos-datafono/{dep_a.pk}/conciliar/",
            {"id_movimiento_banco": str(mov_b.pk)},
            format="json",
        )
        assert resp_conc.status_code == 404
        dep_a.refresh_from_db()
        assert dep_a.estado == "PENDIENTE"

        # Pendientes sin datafono_id NO debe incluir dep_b
        resp_pend = client_a.get("/api/finanzas/depositos-datafono/pendientes/")
        assert resp_pend.status_code == 200
        ids = {str(d["id_deposito"]) for d in resp_pend.data["depositos"]}
        assert str(dep_a.pk) in ids
        assert str(dep_b.pk) not in ids

        # Pendientes filtrando por datafono_id de Empresa B -> 404
        resp_df_b = client_a.get(f"/api/finanzas/depositos-datafono/pendientes/?datafono_id={df_b.pk}")
        assert resp_df_b.status_code == 404

    def test_ajustes_caja_banco_bloquea_empresa_caja_banco_y_usuario_ajeno(
        self, client_a, empresa_a, empresa_b, user_a, user_b, moneda_usd, finanzas_b
    ):
        url = "/api/finanzas/ajustes-caja-banco/crear_ajuste/"
        # Empresa B directamente -> 403
        r1 = client_a.post(
            url,
            {
                "empresa": str(empresa_b.pk),
                "monto": "100.00",
                "moneda": str(moneda_usd.pk),
                "caja": str(finanzas_b["caja_b"].pk),
                "usuario": str(user_a.pk),
                "tipo_ajuste": "POSITIVO",
            },
            format="json",
        )
        assert r1.status_code == 403
        assert not MovimientoCajaBanco.objects.filter(id_empresa=empresa_b, tipo_movimiento="AJUSTE_POSITIVO").exists()

        # Empresa A + Caja B -> 403
        r2 = client_a.post(
            url,
            {
                "empresa": str(empresa_a.pk),
                "monto": "100.00",
                "moneda": str(moneda_usd.pk),
                "caja": str(finanzas_b["caja_b"].pk),
                "usuario": str(user_a.pk),
                "tipo_ajuste": "POSITIVO",
            },
            format="json",
        )
        assert r2.status_code == 403

        # Empresa A + CuentaBancaria B -> 403
        r3 = client_a.post(
            url,
            {
                "empresa": str(empresa_a.pk),
                "monto": "100.00",
                "moneda": str(moneda_usd.pk),
                "cuenta_bancaria": str(finanzas_b["banco_b"].pk),
                "usuario": str(user_a.pk),
                "tipo_ajuste": "POSITIVO",
            },
            format="json",
        )
        assert r3.status_code == 403

        # Empresa A + Usuario B -> 403
        r4 = client_a.post(
            url,
            {
                "empresa": str(empresa_a.pk),
                "monto": "100.00",
                "moneda": str(moneda_usd.pk),
                "caja": str(finanzas_b["caja_a"].pk),
                "usuario": str(user_b.pk),
                "tipo_ajuste": "POSITIVO",
            },
            format="json",
        )
        assert r4.status_code == 403

        # Empresa A + Moneda privada de Empresa B -> 403
        moneda_priv_b = Moneda.objects.create(
            codigo_iso="AJB",
            nombre="Ajuste Priv B",
            simbolo="A",
            es_generica=False,
            es_publica=False,
            empresa=empresa_b,
        )
        r5 = client_a.post(
            url,
            {
                "empresa": str(empresa_a.pk),
                "monto": "100.00",
                "moneda": str(moneda_priv_b.pk),
                "caja": str(finanzas_b["caja_a"].pk),
                "usuario": str(user_a.pk),
                "tipo_ajuste": "POSITIVO",
            },
            format="json",
        )
        assert r5.status_code == 403

        # Ajuste válido en Empresa A -> 201
        r_ok = client_a.post(
            url,
            {
                "empresa": str(empresa_a.pk),
                "monto": "15.00",
                "moneda": str(moneda_usd.pk),
                "caja": str(finanzas_b["caja_a"].pk),
                "usuario": str(user_a.pk),
                "tipo_ajuste": "POSITIVO",
            },
            format="json",
        )
        assert r_ok.status_code == 201

        # Superusuario puede validar empresa pero sigue recibiendo 400 si caja/banco/moneda no coinciden con la empresa
        from rest_framework.test import APIClient

        superuser = Usuarios.objects.create_user(
            username=f"super_aj_{uuid.uuid4().hex[:6]}",
            password="PasswordSegura123!",
            email="super_aj@test.local",
            es_superusuario_omni=True,
            is_superuser=True,
            is_staff=True,
        )
        client_super = APIClient()
        client_super.force_authenticate(user=superuser)
        assert (
            client_super.post(
                url,
                {
                    "empresa": str(empresa_a.pk),
                    "monto": "10.00",
                    "moneda": str(moneda_usd.pk),
                    "caja": str(finanzas_b["caja_b"].pk),
                    "usuario": str(user_a.pk),
                    "tipo_ajuste": "POSITIVO",
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_super.post(
                url,
                {
                    "empresa": str(empresa_a.pk),
                    "monto": "10.00",
                    "moneda": str(moneda_usd.pk),
                    "cuenta_bancaria": str(finanzas_b["banco_b"].pk),
                    "usuario": str(user_a.pk),
                    "tipo_ajuste": "POSITIVO",
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_super.post(
                url,
                {
                    "empresa": str(empresa_a.pk),
                    "monto": "10.00",
                    "moneda": str(moneda_priv_b.pk),
                    "caja": str(finanzas_b["caja_a"].pk),
                    "usuario": str(user_a.pk),
                    "tipo_ajuste": "POSITIVO",
                },
                format="json",
            ).status_code
            == 400
        )

        # Listados adicionales en finanzas usan get_empresas_visible sin fugas
        for list_url in (
            "/api/finanzas/monedas/activas/",
            "/api/finanzas/plantillas-maestro-cajas/",
            "/api/finanzas/cajas-virtuales-auto/",
            "/api/finanzas/overrides-metodos-pago/",
            "/api/finanzas/transacciones-datafono/",
            "/api/finanzas/sesiones-datafono/",
        ):
            assert client_a.get(list_url).status_code == 200

    def test_tasa_oficial_bcv_rechaza_empresa_o_moneda_privada_ajena(self, client_a, empresa_b, moneda_usd):
        moneda_priv_b = Moneda.objects.create(
            codigo_iso="PVB", nombre="Privada B", simbolo="P", es_generica=False, es_publica=False, empresa=empresa_b
        )
        assert client_a.get(f"/api/finanzas/tasa-oficial-bcv/?id_empresa={empresa_b.pk}").status_code == 404
        assert (
            client_a.get(f"/api/finanzas/tasa-oficial-bcv/?id_moneda_transaccion={moneda_priv_b.pk}").status_code
            == 404
        )

        from rest_framework.test import APIClient

        superuser = Usuarios.objects.create_user(
            username=f"super_bcv_{uuid.uuid4().hex[:6]}",
            password="PasswordSegura123!",
            email="super_bcv@test.local",
            es_superusuario_omni=True,
            is_superuser=True,
            is_staff=True,
        )
        client_super = APIClient()
        client_super.force_authenticate(user=superuser)
        assert client_super.get(
            f"/api/finanzas/tasa-oficial-bcv/?id_moneda_transaccion={moneda_priv_b.pk}"
        ).status_code in (200, 404)

    def test_objetos_globales_y_publicos_ajenos_no_editables_por_usuario_normal(
        self, client_a, empresa_a, empresa_b, moneda_usd, metodo_efectivo
    ):
        moneda_pub_b = Moneda.objects.create(
            codigo_iso="PUB", nombre="Publica B", simbolo="PB", es_generica=False, es_publica=True, empresa=empresa_b
        )
        moneda_a = Moneda.objects.create(
            codigo_iso="PVA", nombre="Propia A", simbolo="PA", es_generica=False, es_publica=False, empresa=empresa_a
        )
        metodo_generico = MetodoPago.objects.create(
            empresa=None, nombre_metodo="Efectivo Global", tipo_metodo="EFECTIVO", es_generico=True, es_publico=False
        )
        metodo_pub_b = MetodoPago.objects.create(
            empresa=empresa_b, nombre_metodo="Publico B", tipo_metodo="OTRO", es_generico=False, es_publico=True
        )
        metodo_a = MetodoPago.objects.create(
            empresa=empresa_a, nombre_metodo="Propio A", tipo_metodo="OTRO", es_generico=False, es_publico=False
        )
        tasa_global = TasaCambio.objects.create(
            id_empresa=None,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_pub_b,
            tipo_tasa="OFICIAL_BCV",
            valor_tasa=Decimal("36.50"),
            fecha_tasa=date.today(),
        )

        # Monedas globales o públicas de Empresa B -> 403
        assert (
            client_a.patch(f"/api/finanzas/monedas/{moneda_usd.pk}/", {"nombre": "Hack"}, format="json").status_code
            == 403
        )
        assert client_a.delete(f"/api/finanzas/monedas/{moneda_usd.pk}/").status_code == 403
        assert (
            client_a.patch(f"/api/finanzas/monedas/{moneda_pub_b.pk}/", {"nombre": "Hack"}, format="json").status_code
            == 403
        )
        assert client_a.delete(f"/api/finanzas/monedas/{moneda_pub_b.pk}/").status_code == 403
        assert (
            client_a.post(
                "/api/finanzas/monedas/",
                {
                    "codigo_iso": "GLB",
                    "nombre": "Global",
                    "simbolo": "G",
                    "es_generica": True,
                    "empresa": str(empresa_a.pk),
                },
                format="json",
            ).status_code
            == 403
        )
        assert (
            client_a.post(
                "/api/finanzas/metodos-pago/",
                {
                    "nombre_metodo": "Global Hack",
                    "tipo_metodo": "OTRO",
                    "es_generico": True,
                    "empresa": str(empresa_a.pk),
                },
                format="json",
            ).status_code
            == 403
        )
        assert (
            client_a.post(
                "/api/finanzas/tasas-cambio/",
                {
                    "id_moneda_origen": str(moneda_usd.pk),
                    "id_moneda_destino": str(moneda_pub_b.pk),
                    "tipo_tasa": "OFICIAL_BCV",
                    "valor_tasa": "50.00",
                    "fecha_tasa": str(date.today()),
                    "id_empresa": None,
                },
                format="json",
            ).status_code
            == 403
        )
        # Propia sigue editable y eliminable, pero no puede escalarse a global
        assert (
            client_a.patch(
                f"/api/finanzas/monedas/{moneda_a.pk}/", {"nombre": "Propia A v2"}, format="json"
            ).status_code
            == 200
        )
        assert (
            client_a.patch(f"/api/finanzas/monedas/{moneda_a.pk}/", {"es_generica": True}, format="json").status_code
            == 403
        )
        assert client_a.delete(f"/api/finanzas/monedas/{moneda_a.pk}/").status_code in (200, 204)

        # Métodos de pago globales o públicos de Empresa B -> 403 (y privado sin empresa -> 404)
        assert (
            client_a.patch(
                f"/api/finanzas/metodos-pago/{metodo_efectivo.pk}/", {"nombre_metodo": "Hack"}, format="json"
            ).status_code
            == 404
        )
        assert (
            client_a.patch(
                f"/api/finanzas/metodos-pago/{metodo_generico.pk}/", {"nombre_metodo": "Hack"}, format="json"
            ).status_code
            == 403
        )
        assert client_a.delete(f"/api/finanzas/metodos-pago/{metodo_generico.pk}/").status_code == 403
        assert (
            client_a.patch(
                f"/api/finanzas/metodos-pago/{metodo_pub_b.pk}/", {"nombre_metodo": "Hack"}, format="json"
            ).status_code
            == 403
        )
        assert client_a.delete(f"/api/finanzas/metodos-pago/{metodo_pub_b.pk}/").status_code == 403
        # Propio sigue editable y eliminable, pero no puede escalarse a global
        assert (
            client_a.patch(
                f"/api/finanzas/metodos-pago/{metodo_a.pk}/",
                {"nombre_metodo": "Propio A v2", "monedas": []},
                format="json",
            ).status_code
            == 200
        )
        assert (
            client_a.patch(
                f"/api/finanzas/metodos-pago/{metodo_a.pk}/", {"es_generico": True}, format="json"
            ).status_code
            == 403
        )
        assert client_a.delete(f"/api/finanzas/metodos-pago/{metodo_a.pk}/").status_code in (200, 204)

        # Tasas globales (id_empresa=None) -> 403; propia sigue editable/eliminable
        tasa_propia_a = TasaCambio.objects.create(
            id_empresa=empresa_a,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_pub_b,
            tipo_tasa="ESPECIAL_USUARIO",
            valor_tasa=Decimal("40.00"),
            fecha_tasa=date.today(),
        )
        assert (
            client_a.patch(
                f"/api/finanzas/tasas-cambio/{tasa_propia_a.pk}/", {"valor_tasa": "41.00"}, format="json"
            ).status_code
            == 200
        )
        assert (
            client_a.patch(
                f"/api/finanzas/tasas-cambio/{tasa_propia_a.pk}/", {"id_empresa": None}, format="json"
            ).status_code
            == 403
        )
        assert client_a.delete(f"/api/finanzas/tasas-cambio/{tasa_propia_a.pk}/").status_code in (200, 204)
        assert (
            client_a.patch(
                f"/api/finanzas/tasas-cambio/{tasa_global.pk}/", {"valor_tasa": "999.00"}, format="json"
            ).status_code
            == 403
        )
        assert client_a.delete(f"/api/finanzas/tasas-cambio/{tasa_global.pk}/").status_code == 403

        # Propia creada vía API funciona y superusuario mantiene control de globales
        moneda_tasa_a = Moneda.objects.create(
            codigo_iso="PTA", nombre="Para Tasa A", simbolo="T", es_generica=False, es_publica=False, empresa=empresa_a
        )
        resp_tasa_ok = client_a.post(
            "/api/finanzas/tasas-cambio/",
            {
                "id_moneda_origen": str(moneda_usd.pk),
                "id_moneda_destino": str(moneda_tasa_a.pk),
                "tipo_tasa": "ESPECIAL_USUARIO",
                "valor_tasa": "42.00",
                "fecha_tasa": str(date.today()),
                "id_empresa": str(empresa_a.pk),
            },
            format="json",
        )
        assert resp_tasa_ok.status_code == 201, resp_tasa_ok.content
        from rest_framework.test import APIClient

        superuser = Usuarios.objects.create_user(
            username=f"super_cat_{uuid.uuid4().hex[:6]}",
            password="PasswordSegura123!",
            email="super_cat@test.local",
            es_superusuario_omni=True,
            is_superuser=True,
            is_staff=True,
        )
        client_super = APIClient()
        client_super.force_authenticate(user=superuser)
        assert client_super.get("/api/finanzas/monedas/activas/").status_code == 200
        assert (
            client_super.patch(
                f"/api/finanzas/tasas-cambio/{tasa_global.pk}/", {"valor_tasa": "37.00"}, format="json"
            ).status_code
            == 200
        )

    def test_rrhh_cargo_global_y_ajeno_protegidos(self, client_a, empresa_a, empresa_b):
        cargo_global = Cargo.objects.create(empresa=None, nombre="Director Global")
        cargo_b = Cargo.objects.create(empresa=empresa_b, nombre="Analista B")
        cargo_a = Cargo.objects.create(empresa=empresa_a, nombre="Analista A")

        assert (
            client_a.post("/api/rrhh/cargos/", {"nombre": "Hack Global", "empresa": None}, format="json").status_code
            == 403
        )
        assert (
            client_a.patch(f"/api/rrhh/cargos/{cargo_global.pk}/", {"nombre": "Hack"}, format="json").status_code
            == 403
        )
        assert client_a.delete(f"/api/rrhh/cargos/{cargo_global.pk}/").status_code == 403
        assert client_a.get(f"/api/rrhh/cargos/{cargo_b.pk}/").status_code == 404
        assert client_a.patch(f"/api/rrhh/cargos/{cargo_b.pk}/", {"nombre": "Hack"}, format="json").status_code == 404

        assert (
            client_a.post(
                "/api/rrhh/cargos/", {"nombre": "Cargo A API", "empresa": empresa_a.pk}, format="json"
            ).status_code
            == 201
        )
        assert (
            client_a.patch(f"/api/rrhh/cargos/{cargo_a.pk}/", {"nombre": "Analista A v2"}, format="json").status_code
            == 200
        )
        assert client_a.patch(f"/api/rrhh/cargos/{cargo_a.pk}/", {"empresa": None}, format="json").status_code == 403
        assert client_a.delete(f"/api/rrhh/cargos/{cargo_a.pk}/").status_code in (200, 204)

    def test_control_asistencia_generar_resumen_diario_no_cruza_empresa(self, client_a, empresa_b):
        emp_b = Empleado.objects.create(
            empresa=empresa_b,
            nombre="Carlos",
            apellido="Beta",
            cedula=f"V-{uuid.uuid4().hex[:8]}",
            fecha_ingreso=date.today(),
        )
        RegistroAsistencia.objects.create(
            id_empleado=emp_b,
            fecha_hora_marcado=timezone.now(),
            tipo_marcado="ENTRADA",
            metodo_marcado="MANUAL",
        )
        url = "/api/control-asistencia/resumenes-asistencia-diario/generar_resumen_diario/"
        assert client_a.post(url, {"empleado_id": emp_b.pk}, format="json").status_code == 404
        assert client_a.post(url, {"empleado_id": "no-numerico"}, format="json").status_code == 404
        assert client_a.post(url, {"fecha": str(date.today())}, format="json").status_code == 200
        assert not ResumenAsistenciaDiario.objects.filter(id_empleado=emp_b).exists()

    def test_servicio_cliente_agregar_comentario_bloquea_ticket_ajeno(self, client_a, empresa_b):
        cat_b = CategoriaTicket.objects.create(id_empresa=empresa_b, nombre_categoria="Soporte B")
        ticket_b = TicketSoporte.objects.create(
            id_empresa=empresa_b,
            numero_ticket="TCK-B-001",
            asunto="Asunto B",
            descripcion="Privado B",
            id_categoria_ticket=cat_b,
            prioridad="MEDIA",
            estado_ticket="ABIERTO",
        )
        resp = client_a.post(
            "/api/servicio-cliente/interacciones-ticket/agregar_comentario/",
            {"ticket_id": str(ticket_b.pk), "contenido": "Comentario intruso"},
            format="json",
        )
        assert resp.status_code == 404
        assert not InteraccionTicket.objects.filter(id_ticket=ticket_b).exists()

    def test_core_y_auditoria_empresa_usuarios_sucursal_notificacion_permisos(
        self, client_a, empresa_a, empresa_b, user_b, sucursal_a, sucursal_b
    ):
        # Empresa B por PK -> 404
        assert client_a.get(f"/api/core/empresas/{empresa_b.pk}/").status_code == 404
        assert (
            client_a.patch(
                f"/api/core/empresas/{empresa_b.pk}/", {"nombre_comercial": "Hack"}, format="json"
            ).status_code
            == 404
        )

        # Usuario B por PK -> 404
        assert client_a.get(f"/api/core/usuarios/{user_b.pk}/").status_code == 404
        assert (
            client_a.patch(f"/api/core/usuarios/{user_b.pk}/", {"first_name": "Hack"}, format="json").status_code
            == 404
        )

        # SucursalSerializer anti-IDOR en POST (ajena/inexistente) y PATCH -> 400
        resp_post_suc = client_a.post(
            "/api/core/sucursales/",
            {"id_empresa": str(empresa_b.pk), "nombre": "Sucursal Hack", "codigo_sucursal": "HACK1"},
            format="json",
        )
        assert resp_post_suc.status_code == 400
        assert (
            client_a.post(
                "/api/core/sucursales/",
                {"id_empresa": str(uuid.uuid4()), "nombre": "Sucursal Ghost", "codigo_sucursal": "HACK2"},
                format="json",
            ).status_code
            == 400
        )
        assert not Sucursal.objects.filter(id_empresa=empresa_b, codigo_sucursal="HACK1").exists()

        resp_patch_suc = client_a.patch(
            f"/api/core/sucursales/{sucursal_a.pk}/",
            {"id_empresa": str(empresa_b.pk)},
            format="json",
        )
        assert resp_patch_suc.status_code == 400
        sucursal_a.refresh_from_db()
        assert sucursal_a.id_empresa_id == empresa_a.pk

        assert client_a.get(f"/api/core/sucursales/{sucursal_b.pk}/").status_code == 404

        # Notificaciones (core y app notificaciones) por PK -> 404
        notif_b = Notificacion.objects.create(
            id_empresa=empresa_b,
            id_usuario=user_b,
            titulo="Secreto B",
            mensaje="Mensaje B",
        )
        assert client_a.get(f"/api/core/notificaciones/{notif_b.pk}/").status_code == 404
        assert (
            client_a.post(f"/api/core/notificaciones/{notif_b.pk}/marcar_leida/", {}, format="json").status_code == 404
        )
        assert (
            client_a.patch(
                f"/api/notificaciones/notificaciones/{notif_b.pk}/marcar-leida/", {}, format="json"
            ).status_code
            == 404
        )
        notif_b.refresh_from_db()
        assert notif_b.leida is False

        # Permisos globales: activar/desactivar bloqueados para usuario normal -> 403
        perm = Permisos.objects.create(
            codigo_permiso=f"perm_test_{uuid.uuid4().hex[:6]}",
            nombre_permiso="Perm Test",
            modulo="core",
        )
        assert client_a.post(f"/api/core/permisos/{perm.pk}/desactivar/", {}, format="json").status_code == 403
        assert client_a.post(f"/api/core/permisos/{perm.pk}/activar/", {}, format="json").status_code == 403
        perm.refresh_from_db()
        assert perm.activo is True

        from rest_framework.test import APIClient

        superuser = Usuarios.objects.create_user(
            username=f"super_perm_{uuid.uuid4().hex[:6]}",
            password="PasswordSegura123!",
            email="super_perm@test.local",
            es_superusuario_omni=True,
            is_superuser=True,
            is_staff=True,
        )
        client_super = APIClient()
        client_super.force_authenticate(user=superuser)
        assert client_super.post(f"/api/core/permisos/{perm.pk}/desactivar/", {}, format="json").status_code == 200
        assert client_super.post(f"/api/core/permisos/{perm.pk}/activar/", {}, format="json").status_code == 200

        # Auditoría por PK ajeno -> 404 / mutación -> 405
        log_b = LogAuditoria.objects.create(
            id_empresa=empresa_b,
            id_usuario=user_b,
            modulo="CORE",
            tipo_accion="LOGIN",
            descripcion_accion="Privado B",
        )
        assert client_a.get(f"/api/auditoria/logs-auditoria/{log_b.pk}/").status_code == 404
        assert client_a.delete(f"/api/auditoria/logs-auditoria/{log_b.pk}/").status_code == 405
