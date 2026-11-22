"""
E2E multi-país para el strangler fig de localización (Ola 6 PR-32 · ADR-007).

Verifica que `fiscal`, `ventas` y `nomina` enrutan sus reglas a través de
``get_localizacion(empresa, default_pais="VE")``:
  - Una empresa no-VE (``pais_codigo_iso="US"`` / ``"CO"``) o con
    ``localizacion_legal_activa=False, localizacion_mercado_activa=False``
    completa el ciclo comercial completo (Cotización → Pedido → Entrega →
    Factura → PDF → Cobro → Asiento + Libros) y de nómina usando los puertos
    ``NoOp``, sin IVA 16 %, sin IGTF 3 %, sin pie SENIAT ni reglas LOTTT.
  - Una empresa venezolana (``pais_codigo_iso="VE"``, capa legal activa)
    conserva 100 % la fiscalidad SENIAT (IVA 16 %, IGTF 3 %, pie legal y libros)
    y el cálculo LOTTT.
  - Aislamiento multi-tenant (R-CODE-1) estricto entre empresas VE y no-VE.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.almacenes.models import Almacen
from apps.contabilidad.models import AsientoContable, DetalleAsiento, MapeoContable, PlanCuentas
from apps.core.models import Empresa, Usuarios
from apps.crm.models import Cliente
from apps.cuentas_por_cobrar.services import registrar_abono
from apps.fiscal.models import ConfiguracionFiscalEmpresa
from apps.fiscal.pdf_factura import generar_pdf_factura
from apps.fiscal.services import calcular_igtf, calcular_impuestos, calcular_iva
from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida
from apps.inventario.services import registrar_movimiento
from apps.nomina.models import DetalleNomina, Nomina, PeriodoNomina, ProcesoNomina
from apps.nomina.services import procesar_proceso_nomina
from apps.rrhh.models import Empleado
from apps.ventas.models import (
    Cotizacion,
    DetalleCotizacion,
    DetallePedido,
    Pedido,
)
from apps.ventas.services import (
    confirmar_pedido,
    convertir_pedido_a_nota_venta,
    emitir_factura_fiscal,
    entregar_nota_venta,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _setup_contabilidad_basica(empresa) -> None:
    """Configura plan de cuentas y mapeos contables mínimos para ventas/CxC/nómina."""
    activo = PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta="1101",
        nombre_cuenta="Cuentas por Cobrar / Caja",
        tipo_cuenta="ACTIVO",
        naturaleza="DEUDORA",
        nivel=1,
    )
    ingreso = PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta="4101",
        nombre_cuenta="Ingresos por Ventas",
        tipo_cuenta="INGRESO",
        naturaleza="ACREEDORA",
        nivel=1,
    )
    iva_pasivo = PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta="2101",
        nombre_cuenta="IVA por Pagar",
        tipo_cuenta="PASIVO",
        naturaleza="ACREEDORA",
        nivel=1,
    )
    gasto_nom = PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta="5101",
        nombre_cuenta="Gasto Nómina",
        tipo_cuenta="GASTO",
        naturaleza="DEUDORA",
        nivel=1,
    )
    nom_pagar = PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta="2102",
        nombre_cuenta="Nómina por Pagar",
        tipo_cuenta="PASIVO",
        naturaleza="ACREEDORA",
        nivel=1,
    )

    for tipo_asiento, debe, haber in (
        ("NOTA_VENTA", activo, ingreso),
        ("FACTURA_VENTA", activo, ingreso),
        ("FACTURA_VENTA_IVA", activo, iva_pasivo),
        ("NOMINA", gasto_nom, nom_pagar),
    ):
        MapeoContable.objects.create(
            id_empresa=empresa,
            tipo_asiento=tipo_asiento,
            cuenta_debe=debe,
            cuenta_haber=haber,
            descripcion_plantilla=f"Asiento {tipo_asiento} {{numero}}",
            activo=True,
        )


def _setup_catalogo_y_stock(empresa, moneda_usd, usuario):
    unidad = UnidadMedida.objects.create(
        id_empresa=empresa,
        nombre="Unidad",
        abreviatura="UND",
        tipo="CANTIDAD",
    )
    categoria = CategoriaProducto.objects.create(
        id_empresa=empresa,
        nombre_categoria="General",
    )
    producto = Producto.objects.create(
        id_empresa=empresa,
        nombre_producto="Servicio / Bien E2E",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        precio_venta_sugerido=Decimal("500.00"),
        costo_promedio=Decimal("200.00"),
    )
    almacen = Almacen.objects.create(
        id_empresa=empresa,
        nombre_almacen="Almacén Principal",
        codigo_almacen=f"ALM-{str(empresa.pk)[:8]}",
    )
    registrar_movimiento(
        empresa=empresa,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="ENTRADA",
        producto=producto,
        cantidad=Decimal("50"),
        almacen_destino=almacen,
        usuario=usuario,
    )
    cliente = Cliente.objects.create(
        id_empresa=empresa,
        razon_social=f"Cliente {empresa.nombre_legal}",
        rif="J-40123456-7",
        tipo_cliente="CREDITO",
        dias_credito=30,
    )
    return cliente, producto, almacen


def _crear_usuario_con_empresa(username: str, empresa: Empresa) -> Usuarios:
    user = Usuarios.objects.create_user(
        username=username,
        email=f"{username}@test.local",
        password="TestUser#Strangler2026!",
        is_active=True,
    )
    user.empresas.add(empresa)
    return user


def _ejecutar_ciclo_comercial(empresa, cliente, producto, almacen, moneda_usd, usuario):
    """Cotización → Pedido → Conversión → Entrega → Factura → PDF → Cobro."""
    hoy = timezone.localdate()
    cot = Cotizacion.objects.create(
        id_empresa=empresa,
        id_cliente=cliente,
        id_moneda=moneda_usd,
        numero_cotizacion=f"COT-{str(empresa.pk)[:6]}",
        fecha_cotizacion=hoy,
        fecha_vencimiento=hoy + datetime.timedelta(days=15),
        estado="ACEPTADA",
    )
    DetalleCotizacion.objects.create(
        id_cotizacion=cot,
        id_producto=producto,
        cantidad=Decimal("2"),
        precio_unitario=Decimal("500.00"),
        subtotal=Decimal("1000.00"),
    )
    pedido = Pedido.objects.create(
        id_empresa=empresa,
        id_cliente=cliente,
        id_cotizacion_origen=cot,
        numero_pedido=f"PED-{str(empresa.pk)[:6]}",
        fecha_pedido=hoy,
        estado="PENDIENTE",
    )
    DetallePedido.objects.create(
        id_pedido=pedido,
        id_producto=producto,
        cantidad=Decimal("2"),
        precio_unitario=Decimal("500.00"),
        subtotal=Decimal("1000.00"),
    )

    confirmar_pedido(pedido, almacen, usuario)
    nota = convertir_pedido_a_nota_venta(pedido, usuario)
    entregar_nota_venta(nota, almacen, usuario)
    res_fac = emitir_factura_fiscal(nota, moneda=moneda_usd, usuario=usuario)
    factura = res_fac["factura"]
    cxc = res_fac["cxc"]
    pdf_bytes = generar_pdf_factura(factura)
    abono = registrar_abono(cxc, factura.monto_total, usuario, descripcion="Cobro total E2E")
    cxc.refresh_from_db()
    return res_fac, factura, cxc, abono, pdf_bytes


@pytest.mark.parametrize(
    ("pais", "legal_activa", "mercado_activa"),
    [
        ("US", True, True),
        ("VE", False, False),
    ],
)
def test_e2e_ciclo_comercial_no_ve_usa_noop_sin_iva_ni_igtf(
    moneda_usd,
    pais,
    legal_activa,
    mercado_activa,
):
    """
    Empresa no-VE (``US`` o VE con flags desactivados) completa todo el ciclo
    comercial con NoOp: sin IVA 16%, sin IGTF 3%, PDF sin pie SENIAT y libros vacíos.
    """
    empresa = Empresa.objects.create(
        nombre_legal=f"Global Corp ({pais}/{legal_activa})",
        identificador_fiscal="US-98765432",
        id_moneda_base=moneda_usd,
        pais_codigo_iso=pais,
        localizacion_legal_activa=legal_activa,
        localizacion_mercado_activa=mercado_activa,
    )
    ConfiguracionFiscalEmpresa.objects.create(
        id_empresa=empresa,
        contribuyente_iva=True,
        aplica_igtf=True,
    )
    _setup_contabilidad_basica(empresa)
    usuario = _crear_usuario_con_empresa(f"user_nove_{pais}_{int(legal_activa)}", empresa)
    cliente, producto, almacen = _setup_catalogo_y_stock(empresa, moneda_usd, usuario)

    # Helpers fiscales también respetan NoOp
    iva_calc = calcular_iva(Decimal("1000.00"), "GENERAL", empresa=empresa)
    igtf_calc = calcular_igtf(Decimal("1000.00"), "DIVISA_EFECTIVO", empresa=empresa)
    imp_calc = calcular_impuestos(Decimal("1000.00"), empresa, moneda=moneda_usd)
    assert iva_calc["monto_iva"] == Decimal("0")
    assert igtf_calc["aplica"] is False
    assert igtf_calc["monto_igtf"] == Decimal("0")
    assert imp_calc["monto_iva"] == Decimal("0")
    assert imp_calc["monto_igtf"] == Decimal("0")
    assert imp_calc["total"] == Decimal("1000.00")

    res_fac, factura, cxc, abono, pdf_bytes = _ejecutar_ciclo_comercial(
        empresa, cliente, producto, almacen, moneda_usd, usuario
    )

    assert factura.base_imponible == Decimal("1000.00")
    assert factura.monto_iva == Decimal("0.00")
    assert factura.monto_igtf == Decimal("0.00")
    assert factura.monto_total == Decimal("1000.00")
    assert res_fac["documento_legal"]["noop"] is True
    assert res_fac["documento_legal"]["requiere_pie_legal_seniat"] is False
    assert res_fac["asiento"] is not None
    assert res_fac["asiento_iva"] is None
    assert AsientoContable.objects.filter(id_empresa=empresa, id_documento_origen=factura.id_factura).exists()
    assert abono.monto == Decimal("1000.00")
    assert cxc.estado == "pagada"

    # PDF válido y sin texto legal SENIAT (uncompressed stream check sobre contenido / estructura)
    assert pdf_bytes.startswith(b"%PDF")
    assert b"Ley del SENIAT" not in pdf_bytes

    # Libros legales por HTTP devuelven vacío vía LibroLegalNoOp
    client = APIClient()
    client.force_authenticate(user=usuario)
    periodo = timezone.localdate().strftime("%Y-%m")
    for endpoint in ("libro-ventas", "libro-compras"):
        resp_txt = client.get(f"/api/fiscal/{endpoint}/?empresa={empresa.pk}&periodo={periodo}")
        assert resp_txt.status_code == 200
        assert resp_txt.content == b""
        resp_pdf = client.get(f"/api/fiscal/{endpoint}-pdf/?empresa={empresa.pk}&periodo={periodo}")
        assert resp_pdf.status_code == 200
        assert resp_pdf.content == b""


def test_e2e_ciclo_comercial_ve_mantiene_iva_igtf_y_libros_seniat(moneda_usd):
    """Control VE: empresa venezolana activa sigue aplicando IVA 16% + IGTF 3%, pie SENIAT y libros."""
    empresa_ve = Empresa.objects.create(
        nombre_legal="Distribuidora Venezuela C.A.",
        identificador_fiscal="J-30543012-5",
        id_moneda_base=moneda_usd,
        pais_codigo_iso="VE",
        localizacion_legal_activa=True,
        localizacion_mercado_activa=True,
    )
    ConfiguracionFiscalEmpresa.objects.create(
        id_empresa=empresa_ve,
        contribuyente_iva=True,
        aplica_igtf=True,
    )
    _setup_contabilidad_basica(empresa_ve)
    usuario = _crear_usuario_con_empresa("user_ve_control", empresa_ve)
    cliente, producto, almacen = _setup_catalogo_y_stock(empresa_ve, moneda_usd, usuario)

    res_fac, factura, cxc, abono, pdf_bytes = _ejecutar_ciclo_comercial(
        empresa_ve, cliente, producto, almacen, moneda_usd, usuario
    )

    # 1000 base + 16% IVA (160) + 3% IGTF en USD (30) = 1190.00
    assert factura.base_imponible == Decimal("1000.00")
    assert factura.monto_iva == Decimal("160.00")
    assert factura.monto_igtf == Decimal("30.00")
    assert factura.monto_total == Decimal("1190.00")
    assert res_fac["documento_legal"]["requiere_pie_legal_seniat"] is True
    assert res_fac["asiento"] is not None
    assert res_fac["asiento_iva"] is not None
    assert abono.monto == Decimal("1190.00")
    assert cxc.estado == "pagada"
    assert pdf_bytes.startswith(b"%PDF")

    client = APIClient()
    client.force_authenticate(user=usuario)
    periodo = timezone.localdate().strftime("%Y-%m")
    resp_txt = client.get(f"/api/fiscal/libro-ventas/?empresa={empresa_ve.pk}&periodo={periodo}")
    assert resp_txt.status_code == 200
    assert factura.numero_factura.encode() in resp_txt.content

    resp_pdf = client.get(f"/api/fiscal/libro-ventas-pdf/?empresa={empresa_ve.pk}&periodo={periodo}")
    assert resp_pdf.status_code == 200
    assert resp_pdf.content.startswith(b"%PDF")


def test_nomina_multipais_ve_vs_no_ve(moneda_usd):
    """
    ``procesar_proceso_nomina`` enruta por ``CalculadoraNomina``:
      - VE aplica SSO 4% + FAOV 1% + RPE 0.5% + aportes patronales LOTTT.
      - No-VE (CO o flags desactivados) usa CalculadoraNominaNoOp: 0 deducciones LOTTT.
    """
    empresa_ve = Empresa.objects.create(
        nombre_legal="Nómina VE C.A.",
        identificador_fiscal="J-30111222-3",
        id_moneda_base=moneda_usd,
        pais_codigo_iso="VE",
        localizacion_legal_activa=True,
    )
    empresa_co = Empresa.objects.create(
        nombre_legal="Nómina CO S.A.S.",
        identificador_fiscal="CO-900888777",
        id_moneda_base=moneda_usd,
        pais_codigo_iso="CO",
        localizacion_legal_activa=True,
    )
    _setup_contabilidad_basica(empresa_ve)
    _setup_contabilidad_basica(empresa_co)

    def _correr_nomina(empresa, numero, cedula):
        periodo = PeriodoNomina.objects.create(
            id_empresa=empresa,
            nombre_periodo=f"Periodo {numero}",
            fecha_inicio=datetime.date(2026, 7, 1),
            fecha_fin=datetime.date(2026, 7, 31),
            fecha_pago=datetime.date(2026, 8, 1),
        )
        Empleado.objects.create(
            empresa=empresa,
            nombre="Luis",
            apellido="Rojas",
            cedula=cedula,
            fecha_ingreso=datetime.date(2025, 1, 1),
            documento_json={"salario_mensual": "1000.00"},
        )
        proceso = ProcesoNomina.objects.create(
            id_empresa=empresa,
            id_periodo_nomina=periodo,
            numero_proceso=numero,
            fecha_proceso=timezone.now(),
            estado="EN_PROCESO",
        )
        proc, asiento, adv = procesar_proceso_nomina(proceso)
        recibo = Nomina.objects.get(id_proceso_nomina=proc)
        detalles = list(DetalleNomina.objects.filter(id_nomina=recibo).select_related("id_concepto_nomina"))
        codigos = {d.id_concepto_nomina.codigo_concepto for d in detalles}
        return proc, recibo, codigos, asiento

    proc_ve, recibo_ve, codigos_ve, asiento_ve = _correr_nomina(empresa_ve, "PROC-VE-001", "V-11111111")
    assert recibo_ve.total_devengado == Decimal("1000.00")
    # VE: 4% SSO (40) + 1% FAOV (10) + 0.5% RPE (5) = 55.00
    assert recibo_ve.total_deducciones == Decimal("55.00")
    assert recibo_ve.total_neto == Decimal("945.00")
    assert {"SUELDO", "SSO", "FAOV", "RPE", "AP_SSO"} <= codigos_ve
    assert asiento_ve is not None

    proc_co, recibo_co, codigos_co, asiento_co = _correr_nomina(empresa_co, "PROC-CO-001", "CC-22222222")
    assert recibo_co.total_devengado == Decimal("1000.00")
    assert recibo_co.total_deducciones == Decimal("0.00")
    assert recibo_co.total_neto == Decimal("1000.00")
    assert codigos_co == {"SUELDO"}
    assert asiento_co is not None
    assert DetalleAsiento.objects.filter(id_asiento=asiento_co, debe=Decimal("1000.00")).exists()


def test_aislamiento_cross_tenant_ve_vs_us(moneda_usd):
    """R-CODE-1: usuario de Empresa VE no puede consultar libros fiscales de Empresa US (404)."""
    empresa_ve = Empresa.objects.create(
        nombre_legal="Tenant VE",
        identificador_fiscal="J-10000001-1",
        id_moneda_base=moneda_usd,
        pais_codigo_iso="VE",
    )
    empresa_us = Empresa.objects.create(
        nombre_legal="Tenant US",
        identificador_fiscal="US-10000002",
        id_moneda_base=moneda_usd,
        pais_codigo_iso="US",
    )
    user_ve = _crear_usuario_con_empresa("user_tenant_ve_l10n", empresa_ve)
    client = APIClient()
    client.force_authenticate(user=user_ve)

    resp = client.get(f"/api/fiscal/libro-ventas/?empresa={empresa_us.pk}&periodo=2026-11")
    assert resp.status_code == 404


def test_fallback_sin_empresa_y_documento_ve_rif_legacy(moneda_usd):
    """
    Cubre el fallback de ``calcular_impuestos(..., empresa=None)`` y el fallback
    seguro cuando un fixture/registro VE tiene RIF no canónico en emisión/PDF.
    """
    res_none = calcular_impuestos(Decimal("100.00"), None)
    assert res_none["monto_iva"] == Decimal("16.00")
    assert res_none["total"] == Decimal("116.00")

    empresa_ve = Empresa.objects.create(
        nombre_legal="Legacy VE C.A.",
        identificador_fiscal="SIN-RIF-VALIDO",
        id_moneda_base=moneda_usd,
        pais_codigo_iso="VE",
        localizacion_legal_activa=True,
    )
    _setup_contabilidad_basica(empresa_ve)
    usuario = _crear_usuario_con_empresa("user_ve_legacy_rif", empresa_ve)
    cliente, producto, almacen = _setup_catalogo_y_stock(empresa_ve, moneda_usd, usuario)
    cliente.rif = ""
    cliente.save(update_fields=["rif"])

    res_fac, factura, _cxc, _abono, pdf_bytes = _ejecutar_ciclo_comercial(
        empresa_ve, cliente, producto, almacen, moneda_usd, usuario
    )
    assert res_fac["documento_legal"]["requiere_pie_legal_seniat"] is True
    assert res_fac["documento_legal"]["noop"] is False
    assert factura.monto_iva == Decimal("160.00")
    assert pdf_bytes.startswith(b"%PDF")
