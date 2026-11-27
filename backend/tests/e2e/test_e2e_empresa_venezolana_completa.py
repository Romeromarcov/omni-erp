"""
E2E Completo — Empresa Venezolana Desde Cero (Escenarios 1 al 8).

Simula la operación integral de un equipo multirrol en ``Distribuidora & Servicios El Ávila, C.A.``:
  1. Constitución, equipo multirrol (RBAC/ABAC), motor trimonetario (USD/VES/USDT) y multi-tasa (BCV/Paralelo/USDT).
  2. Maestros completos: 5 perfiles de producto/servicio/consumo interno/kit, 2 almacenes + transferencia,
     CRM pipeline + prospecto + conversión atómica, clientes, proveedores y contacto dual.
  3. Compras duales (FISCAL vs GERENCIAL), guards es_comprable/es_vendible, inventario dual (Real vs Fiscal),
     consumo interno (SALIDA_INTERNA), Landed Costs, semáforo margen, conteo dual y CxP con diferencial cambiario.
  4. Ventas duales (FISCAL vs GERENCIAL), precios brecha, bloqueo mora real, IVA 16%, IGTF 3%, Imprenta Digital,
     ND, NC/devolución, comisiones por cobro, Caja, conciliación N:M y diferencial cambiario CxC.
  5. Gastos duales (FISCAL vs GERENCIAL), aprobaciones, OperacionCambioDivisa y conciliación bancaria.
  6. Nómina mixta VE (Formal LOTTT Bs + Bonificaciones USD gerenciales + préstamo + TXT + arqueo USD).
  7. Doble contabilidad trimonetaria (P&L, Balance General, Balance Comprobación, Mayor), libros SENIAT e Art. 177,
     reversión de asiento y cierre de período.
  8. Logística TMS + ePOD, Portales (Vendedor, Cliente OTP, Conductor), Chatter/WhatsApp, 5 Agentes IA, RBAC y
     aislamiento multi-tenant.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

pytestmark = [pytest.mark.django_db, pytest.mark.e2e]


def _registrar_hallazgo(hallazgos: list[str], codigo: str, modulo: str, detalle: str) -> None:
    hallazgos.append(f"[{codigo}] ({modulo}) {detalle}")


def test_e2e_empresa_venezolana_completa_desde_cero(db, moneda_usd, empresa_b):
    from apps.agentes.operativos import AGENTES_OPERATIVOS, ejecutar_agente_operativo
    from apps.almacenes.models import Almacen, UbicacionAlmacen
    from apps.compras.models import (
        CostoDestino,
        DetalleOfertaProveedor,
        DetalleOrdenCompra,
        DetalleRequisicionCompra,
        DetalleSolicitudCotizacion,
        LineaCostoDestino,
        OfertaProveedor,
        OrdenCompra,
        RequisicionCompra,
        SolicitudCotizacion,
    )
    from apps.compras.services import CompraError, aprobar_orden_compra, registrar_factura_compra, registrar_recepcion
    from apps.compras.services_procurement import adjudicar_oferta_a_orden_compra
    from apps.compras.services_supply_chain import aplicar_costo_destino, validar_three_way_matching
    from apps.contabilidad.models import (
        AsientoContable,
        CentroCosto,
        DiarioContable,
        MapeoContable,
        PeriodoContable,
        PlanCuentas,
    )
    from apps.contabilidad.services import AsientoError, cerrar_periodo_contable, revertir_asiento
    from apps.contabilidad.services_reportes import (
        generar_balance_comprobacion,
        generar_balance_general,
        generar_estado_resultados,
        generar_libro_mayor_auxiliar,
    )
    from apps.core.models import Contacto, Empresa, PoliticaAccesoRol, Roles, Sucursal, UsuarioRoles, Usuarios
    from apps.crm.models import Actividad, Cliente, Etapa, Lead, Pipeline
    from apps.crm.services_conversion import convertir_lead_a_cliente
    from apps.cuentas_por_cobrar.services import registrar_abono as registrar_abono_cxc
    from apps.cuentas_por_pagar.models import DiferenciaCambiaria
    from apps.cuentas_por_pagar.services import registrar_abono_cxp
    from apps.despacho.models import Conductor, Despacho, ParadaEntrega, RutaDespacho, Vehiculo
    from apps.despacho.services_tms import emitir_guia_despacho_seniat, iniciar_ruta_despacho, registrar_epod_parada
    from apps.finanzas.models import (
        Caja,
        CajaFisica,
        CuentaBancariaEmpresa,
        MetodoPago,
        Moneda,
        MonedaEmpresaActiva,
        Pago,
        SesionCajaFisica,
        TasaCambio,
        TipoTasaCambio,
    )
    from apps.finanzas.services_conciliacion_pagos import aplicar_pago_a_documentos
    from apps.finanzas.services_trimonetario import (
        calcular_equivalencias_trimonetarias,
        obtener_tasa_por_tipo,
    )
    from apps.fiscal.libros_seniat import generar_libro_compras_txt, generar_libro_ventas_txt
    from apps.fiscal.models import (
        ConceptoRetencionISLR,
        ConfiguracionFiscalEmpresa,
    )
    from apps.fiscal.services_retenciones import (
        emitir_retencion_islr,
        emitir_retencion_iva,
        generar_libro_inventario_art177,
        generar_txt_retenciones_iva_seniat,
        generar_xml_retenciones_islr_seniat,
    )
    from apps.gastos.models import CategoriaGasto, Gasto
    from apps.gastos.services import GastoError, aprobar_gasto
    from apps.inventario.models import (
        CategoriaProducto,
        DetalleRequisicion,
        MovimientoInventario,
        Producto,
        RequisicionInterna,
        StockActual,
        UnidadMedida,
    )
    from apps.inventario.services import aprobar_requisicion, despachar_requisicion_interna, registrar_movimiento
    from apps.inventario.services_supply_chain import (
        aprobar_aplicar_conteo,
        crear_conteo_inventario,
        evaluar_semaforo_margen_producto,
        registrar_escaneo_conteo,
    )
    from apps.nomina.models import DispersionPagoNomina, FichaSalarialDual, PeriodoNomina, PrestamoEmpleado
    from apps.nomina.services_dual import calcular_arqueo_efectivo_usd, procesar_nomina_dual
    from apps.notificaciones.models import MensajeChatterDocumento
    from apps.notificaciones.whatsapp import enviar_whatsapp_documento
    from apps.proveedores.models import Proveedor
    from apps.rrhh.models import Empleado
    from apps.tesoreria.services import cerrar_conciliacion, conciliar_automatico, iniciar_conciliacion
    from apps.ventas.models import (
        DetalleNotaVenta,
        DetallePedido,
        DetallePrecio,
        ListaPrecio,
        NotaDebitoFiscal,
        NotaVenta,
        Pedido,
        ReglaPrecioDinamico,
    )
    from apps.ventas.services import (
        VentaError,
        confirmar_nota_venta,
        confirmar_pedido,
        emitir_factura_fiscal,
        emitir_nota_debito_fiscal,
        registrar_devolucion_pos,
    )
    from apps.ventas.services_precios import calcular_precio_dinamico

    hallazgos: list[str] = []
    hoy = timezone.localdate()
    f_t0 = hoy - timedelta(days=10)
    f_t1 = hoy - timedelta(days=4)
    f_t2 = hoy

    # =========================================================================
    # ESCENARIO 1 — Constitución, Equipo Multirrol RBAC/ABAC, Trimonetario & Multi-Tasa
    # =========================================================================
    moneda_ves, _ = Moneda.objects.get_or_create(
        codigo_iso="VES",
        defaults={"nombre": "Bolívar Digital", "simbolo": "Bs.", "es_generica": True, "es_publica": True},
    )
    moneda_usdt, _ = Moneda.objects.get_or_create(
        codigo_iso="USDT",
        defaults={
            "nombre": "Tether USD",
            "simbolo": "USDT",
            "tipo_moneda": "crypto",
            "es_generica": True,
            "es_publica": True,
        },
    )

    empresa = Empresa.objects.create(
        nombre_legal="Distribuidora & Servicios El Ávila, C.A.",
        nombre_comercial="El Ávila VE",
        identificador_fiscal="J-409876543",
        pais_codigo_iso="VE",
        localizacion_legal_activa=True,
        localizacion_mercado_activa=True,
        contabilidad_activa=True,
        contabilidad_auto_aprobar=True,
        id_moneda_base=moneda_usd,
        id_moneda_pais=moneda_ves,
        activo=True,
    )
    ConfiguracionFiscalEmpresa.objects.create(
        id_empresa=empresa,
        contribuyente_iva=True,
        aplica_igtf=True,
        tasa_igtf=Decimal("0.03"),
        imprenta_digital_proveedor="SIMULADO",
    )
    MonedaEmpresaActiva.objects.update_or_create(empresa=empresa, moneda=moneda_usd, defaults={"activa": True})
    MonedaEmpresaActiva.objects.update_or_create(empresa=empresa, moneda=moneda_ves, defaults={"activa": True})
    MonedaEmpresaActiva.objects.update_or_create(
        empresa=empresa, moneda=moneda_usdt, defaults={"activa": True, "es_moneda_referencia": True}
    )

    sucursal = Sucursal.objects.create(
        id_empresa=empresa,
        nombre="Casa Matriz Caracas",
        codigo_sucursal="CCS-01",
    )

    # Roles + Usuarios + RBAC/ABAC
    roles = {
        k: Roles.objects.create(id_empresa=empresa, nombre_rol=k)
        for k in (
            "GERENTE",
            "VENDEDOR",
            "CONTADOR_FISCAL",
            "TESORERO",
            "ALMACENISTA",
            "RRHH",
            "COMPRADOR",
            "CONDUCTOR",
        )
    }
    usuarios: dict[str, Usuarios] = {}
    for k, rol in roles.items():
        u = Usuarios.objects.create_user(
            username=f"avila_{k.lower()}_{uuid.uuid4().hex[:5]}",
            email=f"{k.lower()}@elavila.ve",
            password="AvilaPass123!@#",
            id_sucursal_predeterminada=sucursal,
        )
        u.empresas.add(empresa)
        u.sucursales.add(sucursal)
        UsuarioRoles.objects.create(id_usuario=u, id_rol=rol)
        usuarios[k] = u

    # Políticas RBAC/ABAC: Contador Fiscal solo FISCAL; Vendedor solo PROPIO en ventas
    PoliticaAccesoRol.objects.create(
        id_empresa=empresa,
        id_rol=roles["CONTADOR_FISCAL"],
        modulo="contabilidad",
        accion="VER",
        ambito="FISCAL",
        alcance="EMPRESA",
        permitido=True,
    )
    PoliticaAccesoRol.objects.create(
        id_empresa=empresa,
        id_rol=roles["VENDEDOR"],
        modulo="ventas",
        accion="CREAR",
        ambito="AMBOS",
        alcance="PROPIO",
        permitido=True,
    )
    PoliticaAccesoRol.objects.create(
        id_empresa=empresa,
        id_rol=roles["VENDEDOR"],
        modulo="nomina",
        accion="VER",
        ambito="AMBOS",
        alcance="PROPIO",
        permitido=False,
    )

    # Multi-tasa across t0, t1, t2
    tipo_bcv = TipoTasaCambio.objects.create(
        id_empresa=empresa, codigo="OFICIAL_BCV", nombre="BCV Oficial", es_oficial_fiscal=True
    )
    tipo_par = TipoTasaCambio.objects.create(
        id_empresa=empresa, codigo="PARALELO", nombre="Paralelo Mercado", es_oficial_fiscal=False
    )
    tipo_usdt = TipoTasaCambio.objects.create(
        id_empresa=empresa, codigo="USDT", nombre="Binance P2P USDT", es_oficial_fiscal=False
    )

    for fecha_t, bcv_v, par_v, usdt_v in (
        (f_t0, "45.00000000", "56.00000000", "1.02000000"),
        (f_t1, "50.00000000", "62.00000000", "1.03000000"),
        (f_t2, "54.00000000", "67.50000000", "1.04000000"),
    ):
        TasaCambio.objects.create(
            id_empresa=empresa,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_ves,
            tipo_tasa="OFICIAL_BCV",
            id_tipo_tasa=tipo_bcv,
            valor_tasa=Decimal(bcv_v),
            fecha_tasa=fecha_t,
        )
        TasaCambio.objects.create(
            id_empresa=empresa,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_ves,
            tipo_tasa="PERSONALIZADA",
            id_tipo_tasa=tipo_par,
            valor_tasa=Decimal(par_v),
            fecha_tasa=fecha_t,
        )
        TasaCambio.objects.create(
            id_empresa=empresa,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_usdt,
            tipo_tasa="PERSONALIZADA",
            id_tipo_tasa=tipo_usdt,
            valor_tasa=Decimal(usdt_v),
            fecha_tasa=fecha_t,
        )

    eq_t2 = calcular_equivalencias_trimonetarias(Decimal("100.00"), moneda_usd, empresa=empresa, fecha=f_t2)
    assert Decimal(str(eq_t2["monto_pais_fiscal"])) == Decimal("5400.00")
    assert Decimal(str(eq_t2["monto_referencia"])) == Decimal("104.00")
    tasa_par_t2 = obtener_tasa_por_tipo(
        moneda_usd, moneda_ves, empresa=empresa, codigo_tipo_tasa="PARALELO", fecha=f_t2
    )
    assert Decimal(str(tasa_par_t2.valor_tasa)) == Decimal("67.50000000")

    # Métodos de pago, Bancos, Caja, Contabilidad Dual
    mp_ef_usd = MetodoPago.objects.create(empresa=empresa, nombre_metodo="Efectivo USD", tipo_metodo="EFECTIVO")
    mp_ef_usd.monedas.add(moneda_usd)
    mp_ef_ves = MetodoPago.objects.create(empresa=empresa, nombre_metodo="Efectivo VES", tipo_metodo="EFECTIVO")
    mp_ef_ves.monedas.add(moneda_ves)
    mp_pago_movil = MetodoPago.objects.create(empresa=empresa, nombre_metodo="Pago Móvil", tipo_metodo="ELECTRONICO")
    mp_pago_movil.monedas.add(moneda_ves)
    mp_zelle = MetodoPago.objects.create(empresa=empresa, nombre_metodo="Zelle USD", tipo_metodo="ELECTRONICO")
    mp_zelle.monedas.add(moneda_usd)
    mp_binance = MetodoPago.objects.create(empresa=empresa, nombre_metodo="Binance USDT", tipo_metodo="ELECTRONICO")
    mp_binance.monedas.add(moneda_usdt)
    mp_transf_ves = MetodoPago.objects.create(
        empresa=empresa, nombre_metodo="Transferencia Bancaria VES", tipo_metodo="ELECTRONICO"
    )
    mp_transf_ves.monedas.add(moneda_ves)

    banco_ves = CuentaBancariaEmpresa.objects.create(
        id_empresa=empresa,
        nombre_banco="Banesco",
        numero_cuenta="01340001001234567890",
        tipo_cuenta="CORRIENTE",
        id_moneda=moneda_ves,
        saldo_actual=Decimal("100000.00"),
    )
    CuentaBancariaEmpresa.objects.create(
        id_empresa=empresa,
        nombre_banco="Bofa Zelle",
        numero_cuenta="BOFA00011223344",
        tipo_cuenta="CORRIENTE",
        id_moneda=moneda_usd,
        saldo_actual=Decimal("5000.00"),
    )
    caja_fisica = CajaFisica.objects.create(
        empresa=empresa,
        sucursal=sucursal,
        nombre="Caja Registradora Principal",
        tipo_caja="MATRIZ",
    )
    caja_principal = Caja.objects.create(
        empresa=empresa,
        nombre="Caja Principal El Ávila",
        tipo_caja="MATRIZ",
        moneda=moneda_usd,
        sucursal=sucursal,
        caja_fisica=caja_fisica,
        saldo_actual=Decimal("1000.00"),
    )
    SesionCajaFisica.objects.create(
        empresa=empresa,
        caja_fisica=caja_fisica,
        sucursal=sucursal,
        usuario=usuarios["TESORERO"],
        estado="ABIERTA",
        saldo_inicial=Decimal("1000.00"),
    )

    # Plan de Cuentas + Diarios Duales + Mapeos Contables + CentroCosto + Período
    ctas = {
        "BANCOS": PlanCuentas.objects.create(
            id_empresa=empresa,
            codigo_cuenta="1.1.01",
            nombre_cuenta="Bancos y Caja",
            tipo_cuenta="ACTIVO",
            naturaleza="DEUDORA",
            nivel=3,
        ),
        "CXC": PlanCuentas.objects.create(
            id_empresa=empresa,
            codigo_cuenta="1.1.02",
            nombre_cuenta="Cuentas por Cobrar",
            tipo_cuenta="ACTIVO",
            naturaleza="DEUDORA",
            nivel=3,
        ),
        "INV": PlanCuentas.objects.create(
            id_empresa=empresa,
            codigo_cuenta="1.1.04",
            nombre_cuenta="Inventario Mercancía",
            tipo_cuenta="ACTIVO",
            naturaleza="DEUDORA",
            nivel=3,
        ),
        "IVA_CRED": PlanCuentas.objects.create(
            id_empresa=empresa,
            codigo_cuenta="1.1.05",
            nombre_cuenta="IVA Crédito Fiscal",
            tipo_cuenta="ACTIVO",
            naturaleza="DEUDORA",
            nivel=3,
        ),
        "CXP": PlanCuentas.objects.create(
            id_empresa=empresa,
            codigo_cuenta="2.1.01",
            nombre_cuenta="Cuentas por Pagar",
            tipo_cuenta="PASIVO",
            naturaleza="ACREEDORA",
            nivel=3,
        ),
        "IVA_DEB": PlanCuentas.objects.create(
            id_empresa=empresa,
            codigo_cuenta="2.1.04",
            nombre_cuenta="IVA Débito Fiscal",
            tipo_cuenta="PASIVO",
            naturaleza="ACREEDORA",
            nivel=3,
        ),
        "RET_PAS": PlanCuentas.objects.create(
            id_empresa=empresa,
            codigo_cuenta="2.1.05",
            nombre_cuenta="Retenciones por Enterar",
            tipo_cuenta="PASIVO",
            naturaleza="ACREEDORA",
            nivel=3,
        ),
        "PATRIMONIO": PlanCuentas.objects.create(
            id_empresa=empresa,
            codigo_cuenta="3.1.01",
            nombre_cuenta="Capital Social",
            tipo_cuenta="PATRIMONIO",
            naturaleza="ACREEDORA",
            nivel=3,
        ),
        "INGRESOS": PlanCuentas.objects.create(
            id_empresa=empresa,
            codigo_cuenta="4.1.01",
            nombre_cuenta="Ventas",
            tipo_cuenta="INGRESO",
            naturaleza="ACREEDORA",
            nivel=3,
        ),
        "GAN_FX": PlanCuentas.objects.create(
            id_empresa=empresa,
            codigo_cuenta="4.2.01",
            nombre_cuenta="Ganancia Cambiaria",
            tipo_cuenta="INGRESO",
            naturaleza="ACREEDORA",
            nivel=3,
        ),
        "COGS": PlanCuentas.objects.create(
            id_empresa=empresa,
            codigo_cuenta="5.1.01",
            nombre_cuenta="Costo de Ventas",
            tipo_cuenta="COSTO",
            naturaleza="DEUDORA",
            nivel=3,
        ),
        "GASTOS": PlanCuentas.objects.create(
            id_empresa=empresa,
            codigo_cuenta="6.1.01",
            nombre_cuenta="Gastos Operativos",
            tipo_cuenta="GASTO",
            naturaleza="DEUDORA",
            nivel=3,
        ),
        "NOMINA": PlanCuentas.objects.create(
            id_empresa=empresa,
            codigo_cuenta="6.1.02",
            nombre_cuenta="Sueldos y Bonificaciones",
            tipo_cuenta="GASTO",
            naturaleza="DEUDORA",
            nivel=3,
        ),
        "PER_FX": PlanCuentas.objects.create(
            id_empresa=empresa,
            codigo_cuenta="6.2.01",
            nombre_cuenta="Pérdida Cambiaria",
            tipo_cuenta="GASTO",
            naturaleza="DEUDORA",
            nivel=3,
        ),
    }

    for amb in ("FISCAL", "GERENCIAL"):
        for tipo_d in ("VENTAS", "COMPRAS", "BANCO", "CAJA", "NOMINA", "VARIOS"):
            DiarioContable.objects.create(
                id_empresa=empresa,
                codigo=f"{tipo_d[:3]}-{amb[:3]}",
                nombre=f"Diario {tipo_d} {amb}",
                tipo=tipo_d,
                ambito=amb,
                prefijo_secuencia=f"{tipo_d[:2]}{amb[0]}-",
            )

    cc_comercial = CentroCosto.objects.create(
        id_empresa=empresa, codigo="CC-COM", nombre="Comercial CCS", tipo="COMERCIAL"
    )
    assert cc_comercial.pk is not None
    PeriodoContable.objects.create(id_empresa=empresa, anio=hoy.year, mes=hoy.month, estado="ABIERTO")

    mapeos_spec = [
        ("FACTURA_VENTA", "CXC", "INGRESOS"),
        ("FACTURA_VENTA_IVA", "CXC", "IVA_DEB"),
        ("NOTA_VENTA", "CXC", "INGRESOS"),
        ("NOTA_DEBITO_FISCAL", "CXC", "INGRESOS"),
        ("NOTA_DEBITO_FISCAL_IVA", "CXC", "IVA_DEB"),
        ("DEVOLUCION_VENTA", "INGRESOS", "BANCOS"),
        ("DEVOLUCION_VENTA_IVA", "IVA_DEB", "BANCOS"),
        ("COSTO_VENTA", "COGS", "INV"),
        ("RECEPCION_MERCANCIA", "INV", "CXP"),
        ("FACTURA_COMPRA", "CXP", "CXP"),
        ("PAGO_CXC", "BANCOS", "CXC"),
        ("PAGO_CXP", "CXP", "BANCOS"),
        ("GANANCIA_CAMBIARIA", "CXP", "GAN_FX"),
        ("PERDIDA_CAMBIARIA", "PER_FX", "CXP"),
        ("GASTO", "GASTOS", "BANCOS"),
        ("GASTO_IVA", "IVA_CRED", "BANCOS"),
        ("NOMINA", "NOMINA", "BANCOS"),
        ("NOMINA_GERENCIAL", "NOMINA", "BANCOS"),
        ("PROVISION_NOMINA", "NOMINA", "RET_PAS"),
        ("RETENCION_IVA_COMPRA", "CXP", "RET_PAS"),
        ("RETENCION_ISLR", "CXP", "RET_PAS"),
        ("COSTO_DESTINO", "INV", "CXP"),
        ("AJUSTE_CONTEO", "INV", "GASTOS"),
        ("AJUSTE_INVENTARIO", "INV", "GASTOS"),
        ("SALIDA_INTERNA", "GASTOS", "INV"),
        ("CAMBIO_DIVISA", "BANCOS", "BANCOS"),
    ]
    for tipo_as, d_key, h_key in mapeos_spec:
        MapeoContable.objects.create(
            id_empresa=empresa,
            tipo_asiento=tipo_as,
            cuenta_debe=ctas[d_key],
            cuenta_haber=ctas[h_key],
            activo=True,
        )

    # =========================================================================
    # ESCENARIO 2 — Maestros: 5 Productos, Almacenes, CRM Lead→Cliente, Proveedores
    # =========================================================================
    cat_lub = CategoriaProducto.objects.create(id_empresa=empresa, nombre_categoria="Lubricantes")
    cat_srv = CategoriaProducto.objects.create(id_empresa=empresa, nombre_categoria="Servicios")
    cat_ins = CategoriaProducto.objects.create(id_empresa=empresa, nombre_categoria="Insumos Internos")
    un_und = UnidadMedida.objects.create(id_empresa=empresa, nombre="Unidad", abreviatura="UND", tipo="CANTIDAD")
    un_srv = UnidadMedida.objects.create(id_empresa=empresa, nombre="Servicio", abreviatura="SRV", tipo="CANTIDAD")

    prod_vc = Producto.objects.create(
        id_empresa=empresa,
        sku="AV-PROD-01",
        codigo_barras="7591234000011",
        nombre_producto="Aceite Sintético 5W30 Galón",
        id_categoria=cat_lub,
        id_unidad_medida_base=un_und,
        id_moneda_precio=moneda_usd,
        tipo_producto="PRODUCTO_FISICO",
        es_vendible=True,
        es_comprable=True,
        costo_promedio=Decimal("20.0000"),
        costo_reposicion_usd=Decimal("22.0000"),
        precio_venta_sugerido=Decimal("35.0000"),
        margen_minimo_pct=Decimal("15.00"),
        margen_alerta_pct=Decimal("25.00"),
        punto_reorden=Decimal("5.0000"),
    )
    prod_srv = Producto.objects.create(
        id_empresa=empresa,
        sku="AV-SRV-01",
        nombre_producto="Servicio Cambio de Aceite y Diagnóstico",
        id_categoria=cat_srv,
        id_unidad_medida_base=un_srv,
        id_moneda_precio=moneda_usd,
        tipo_producto="SERVICIO",
        es_vendible=True,
        es_comprable=False,
        precio_venta_sugerido=Decimal("25.0000"),
    )
    prod_solo_compra = Producto.objects.create(
        id_empresa=empresa,
        sku="AV-SC-01",
        nombre_producto="Materia Prima Aditivo Base",
        id_categoria=cat_lub,
        id_unidad_medida_base=un_und,
        id_moneda_precio=moneda_usd,
        tipo_producto="PRODUCTO_FISICO",
        es_vendible=False,
        es_comprable=True,
        costo_promedio=Decimal("15.0000"),
        precio_venta_sugerido=Decimal("0.0000"),
    )
    prod_interno = Producto.objects.create(
        id_empresa=empresa,
        sku="AV-INT-01",
        nombre_producto="Papelería y Guantes Uso Interno",
        id_categoria=cat_ins,
        id_unidad_medida_base=un_und,
        id_moneda_precio=moneda_usd,
        tipo_producto="PRODUCTO_FISICO",
        es_vendible=False,
        es_comprable=True,
        costo_promedio=Decimal("10.0000"),
    )
    prod_kit = Producto.objects.create(
        id_empresa=empresa,
        sku="AV-KIT-01",
        nombre_producto="Kit Mantenimiento Preventivo",
        id_categoria=cat_lub,
        id_unidad_medida_base=un_und,
        id_moneda_precio=moneda_usd,
        tipo_producto="KIT",
        es_vendible=True,
        es_comprable=True,
        costo_promedio=Decimal("30.0000"),
        precio_venta_sugerido=Decimal("55.0000"),
    )

    alm_ppal = Almacen.objects.create(
        id_empresa=empresa,
        nombre_almacen="Almacén Principal Caracas",
        codigo_almacen="ALM-PPAL",
        id_sucursal=sucursal,
        usa_ubicaciones=True,
    )
    alm_sec = Almacen.objects.create(
        id_empresa=empresa, nombre_almacen="Almacén Secundario", codigo_almacen="ALM-SEC", id_sucursal=sucursal
    )
    UbicacionAlmacen.objects.create(
        id_empresa=empresa,
        id_almacen=alm_ppal,
        codigo_ubicacion="RACK-A1",
        nombre_ubicacion="Rack A1",
        tipo_ubicacion="ESTANTERIA",
    )

    # CRM Lead -> Convert to Cliente + Contacto Fiscal VE
    pipe = Pipeline.objects.create(id_empresa=empresa, nombre="B2B Autopartes", activo=True)
    etapa_1 = Etapa.objects.create(
        id_empresa=empresa, pipeline=pipe, nombre="Calificado", orden=1, tipo=Etapa.Tipo.ABIERTA
    )
    Etapa.objects.create(id_empresa=empresa, pipeline=pipe, nombre="Ganado", orden=2, tipo=Etapa.Tipo.GANADA)
    lead = Lead.objects.create(
        id_empresa=empresa,
        pipeline=pipe,
        etapa=etapa_1,
        propietario=usuarios["VENDEDOR"],
        nombre="Flota Transporte",
        apellido="Mirandino",
        empresa_nombre="Transporte Mirandino C.A.",
        email="compras@mirandino.ve",
        telefono="+584141112233",
    )
    Actividad.objects.create(
        id_empresa=empresa,
        lead=lead,
        tipo="LLAMADA",
        asunto="Confirmar requerimiento mensual de lubricantes",
        asignado_a=usuarios["VENDEDOR"],
    )
    conv_res = convertir_lead_a_cliente(
        lead_id=lead.pk,
        usuario=usuarios["VENDEDOR"],
        datos_conversion={
            "rif": "J-401239991",
            "razon_social": "Transporte Mirandino C.A.",
            "crear_cotizacion": False,
        },
    )
    cliente_esp = conv_res["cliente"]
    cliente_esp.tipo_cliente = "CREDITO"
    cliente_esp.limite_credito = Decimal("5000.00")
    cliente_esp.dias_credito = 15
    cliente_esp.bloquear_por_mora = True
    cliente_esp.id_vendedor_asignado = usuarios["VENDEDOR"]
    cliente_esp.save()
    cliente_esp.contacto.tipo_contribuyente = "ESPECIAL"
    cliente_esp.contacto.es_agente_retencion_iva = True
    cliente_esp.contacto.porcentaje_retencion_iva = Decimal("75.00")
    cliente_esp.contacto.save()

    contacto_dual = Contacto.objects.create(
        id_empresa=empresa,
        nombre="AutoRepuestos Central C.A.",
        nombre_comercial="AutoRepuestos Central C.A.",
        rif="J-305556667",
        es_cliente=True,
        es_proveedor=True,
        tipo_contribuyente="ORDINARIO",
    )
    cliente_contado = Cliente.objects.create(
        id_empresa=empresa,
        razon_social="AutoRepuestos Central C.A.",
        rif="J-305556667",
        tipo_cliente="CONTADO",
        contacto=contacto_dual,
        id_vendedor_asignado=usuarios["VENDEDOR"],
    )
    proveedor_esp = Proveedor.objects.create(
        id_empresa=empresa,
        razon_social="Lubricantes Nacionales Especial C.A.",
        rif="J-301112228",
        contacto=Contacto.objects.create(
            id_empresa=empresa,
            nombre="Lubricantes Nacionales Especial C.A.",
            nombre_comercial="Lubricantes Nacionales Especial C.A.",
            rif="J-301112228",
            es_proveedor=True,
            tipo_contribuyente="ESPECIAL",
            tipo_persona_fiscal="PJDO",
            es_agente_retencion_islr=True,
        ),
    )

    # =========================================================================
    # ESCENARIO 3 — Compras Duales, Inventario Dual, Consumo Interno, Guards & FX CxP
    # =========================================================================
    # 3.0 Procurement chain (Requisición -> RFQ -> Oferta -> Adjudicar OC)
    req_c = RequisicionCompra.objects.create(
        id_empresa=empresa,
        numero_requisicion="RC-001",
        fecha_requisicion=f_t0,
        id_solicitante=usuarios["COMPRADOR"],
        estado="APROBADA",
        fecha_necesidad=hoy,
        justificacion="Reposición kit preventivo",
    )
    DetalleRequisicionCompra.objects.create(
        id_requisicion=req_c, id_producto=prod_kit, cantidad_solicitada=Decimal("5"), precio_estimado=Decimal("30")
    )
    rfq = SolicitudCotizacion.objects.create(
        id_empresa=empresa,
        numero_solicitud="RFQ-001",
        fecha_solicitud=f_t0,
        fecha_vencimiento=hoy,
        estado="ENVIADA",
    )
    rfq.requisiciones.add(req_c)
    rfq.proveedores_invitados.add(proveedor_esp)
    DetalleSolicitudCotizacion.objects.create(id_solicitud_cotizacion=rfq, id_producto=prod_kit, cantidad=Decimal("5"))
    oferta = OfertaProveedor.objects.create(
        id_solicitud_cotizacion=rfq,
        id_proveedor=proveedor_esp,
        numero_oferta="OF-001",
        fecha_oferta=f_t0,
        fecha_vencimiento=hoy,
        estado="EVALUADA",
        monto_total=Decimal("150.00"),
    )
    DetalleOfertaProveedor.objects.create(
        id_oferta=oferta,
        id_producto=prod_kit,
        cantidad=Decimal("5"),
        precio_unitario=Decimal("30"),
        subtotal=Decimal("150"),
    )
    oc_proc = adjudicar_oferta_a_orden_compra(oferta, alm_ppal, usuario=usuarios["COMPRADOR"])
    assert oc_proc["orden_compra"].pk is not None

    # 3A. Compra FISCAL: OC(FISCAL) -> Recepción -> Landed Cost -> 3-Way Match -> FacturaCompra(FISCAL) + Retenciones
    oc_kwargs_fis = {
        "id_empresa": empresa,
        "id_proveedor": proveedor_esp,
        "id_almacen_destino": alm_ppal,
        "numero_orden": "OC-FIS-001",
        "fecha_orden": f_t0,
        "estado": "BORRADOR",
    }
    if any(f.name == "ambito" for f in OrdenCompra._meta.fields):
        oc_kwargs_fis["ambito"] = "FISCAL"
    else:
        _registrar_hallazgo(
            hallazgos,
            "E2E-000",
            "compras/models.OrdenCompra",
            "OrdenCompra y RecepcionMercancia carecen de campo 'ambito' (FISCAL/GERENCIAL); imposible distinguir compras informales desde la OC/Recepción.",
        )
    oc_fiscal = OrdenCompra.objects.create(**oc_kwargs_fis)
    DetalleOrdenCompra.objects.create(
        id_orden_compra=oc_fiscal,
        id_producto=prod_vc,
        cantidad=Decimal("20.0000"),
        precio_unitario=Decimal("20.0000"),
        subtotal=Decimal("400.0000"),
    )
    aprobar_orden_compra(oc_fiscal, usuarios["COMPRADOR"])
    rec_fis = registrar_recepcion(
        oc_fiscal,
        alm_ppal,
        usuarios["ALMACENISTA"],
        [{"producto": prod_vc, "cantidad": 20, "costo_unitario": "20.00"}],
    )
    # Costos en destino (Landed Cost) sobre la recepción fiscal
    cd_fis = CostoDestino.objects.create(
        id_empresa=empresa,
        id_recepcion=rec_fis["recepcion"],
        numero_documento="CD-FIS-001",
        fecha=f_t0,
        ambito="FISCAL",
        metodo_prorrateo="VALOR",
    )
    LineaCostoDestino.objects.create(
        id_empresa=empresa,
        id_costo_destino=cd_fis,
        concepto="FLETE",
        descripcion="Flete puerto",
        monto=Decimal("20.00"),
    )
    res_cd = aplicar_costo_destino(cd_fis, usuarios["COMPRADOR"])
    assert res_cd["costo_destino"].estado == "APLICADO"

    res_fac_c = registrar_factura_compra(
        rec_fis["recepcion"],
        numero_factura="FC-FIS-0001",
        fecha_emision=f_t0,
        usuario=usuarios["CONTADOR_FISCAL"],
        ambito="FISCAL",
    )
    # 3-Way Matching debería pasar cleanly
    match_res = validar_three_way_matching(res_fac_c["factura"])
    assert match_res["aprobable_automaticamente"] is True, match_res

    # Retenciones IVA e ISLR sobre FacturaCompra fiscal
    conc_islr, _ = ConceptoRetencionISLR.objects.get_or_create(
        codigo="028",
        defaults={
            "nombre": "Compra de bienes PJDO",
            "tipo_persona_fiscal": "PJDO",
            "base_imponible_pct": Decimal("100.00"),
            "porcentaje_retencion": Decimal("2.00"),
            "aplica_sustraendo": False,
        },
    )
    emitir_retencion_iva(
        empresa=empresa,
        contacto=proveedor_esp.contacto,
        fecha_emision=f_t0,
        numero_documento="FC-FIS-0001",
        base_imponible=Decimal("400.00"),
        porcentaje_retencion=Decimal("75.00"),
        factura_compra=res_fac_c["factura"],
        usuario=usuarios["CONTADOR_FISCAL"],
    )
    emitir_retencion_islr(
        empresa=empresa,
        contacto=proveedor_esp.contacto,
        concepto=conc_islr,
        fecha_emision=f_t0,
        numero_factura="FC-FIS-0001",
        monto_operacion=Decimal("400.00"),
        factura_compra=res_fac_c["factura"],
        usuario=usuarios["CONTADOR_FISCAL"],
    )

    # 3B. Compra GERENCIAL (sin factura fiscal): debe mover inventario REAL pero NUNCA tocar contabilidad FISCAL ni Libros SENIAT ni Art. 177
    oc_kwargs_ger = {
        "id_empresa": empresa,
        "id_proveedor": proveedor_esp,
        "id_almacen_destino": alm_ppal,
        "numero_orden": "OC-GER-001",
        "fecha_orden": f_t0,
        "estado": "BORRADOR",
    }
    if any(f.name == "ambito" for f in OrdenCompra._meta.fields):
        oc_kwargs_ger["ambito"] = "GERENCIAL"
    oc_ger = OrdenCompra.objects.create(**oc_kwargs_ger)
    DetalleOrdenCompra.objects.create(
        id_orden_compra=oc_ger,
        id_producto=prod_vc,
        cantidad=Decimal("10.0000"),
        precio_unitario=Decimal("19.0000"),
        subtotal=Decimal("190.0000"),
    )
    aprobar_orden_compra(oc_ger, usuarios["COMPRADOR"])
    rec_ger = registrar_recepcion(
        oc_ger,
        alm_ppal,
        usuarios["ALMACENISTA"],
        [{"producto": prod_vc, "cantidad": 10, "costo_unitario": "19.00"}],
    )
    # Auditar propagación de ambito en OC GERENCIAL -> MovimientoInventario / Asiento / CxP
    for mv in rec_ger["movimientos"]:
        if mv.ambito != "GERENCIAL":
            _registrar_hallazgo(
                hallazgos,
                "E2E-001",
                "compras/services.registrar_recepcion",
                f"OC GERENCIAL {oc_ger.numero_orden} creó MovimientoInventario {mv.pk} con ambito={mv.ambito!r} (esperado 'GERENCIAL').",
            )
    if rec_ger["asiento"] is not None and rec_ger["asiento"].ambito != "GERENCIAL":
        _registrar_hallazgo(
            hallazgos,
            "E2E-002",
            "compras/services.registrar_recepcion",
            f"OC GERENCIAL {oc_ger.numero_orden} creó AsientoContable {rec_ger['asiento'].numero_asiento} en ambito={rec_ger['asiento'].ambito!r} (esperado 'GERENCIAL').",
        )
    if (rec_ger["cxp"].documento_json or {}).get("ambito") != "GERENCIAL":
        _registrar_hallazgo(
            hallazgos,
            "E2E-003",
            "compras/services.registrar_recepcion",
            f"OC GERENCIAL {oc_ger.numero_orden} creó CxP sin documento_json['ambito']=='GERENCIAL' ({rec_ger['cxp'].documento_json!r}).",
        )

    # Guard: intentar emitir FacturaCompra FISCAL sobre OC GERENCIAL debería bloquearse
    try:
        registrar_factura_compra(
            rec_ger["recepcion"],
            numero_factura="FC-ILEGAL-GER",
            fecha_emision=f_t0,
            usuario=usuarios["CONTADOR_FISCAL"],
            ambito="FISCAL",
        )
        _registrar_hallazgo(
            hallazgos,
            "E2E-004",
            "compras/services.registrar_factura_compra",
            "Permitió emitir FacturaCompra FISCAL sobre una RecepcionMercancia de OrdenCompra GERENCIAL.",
        )
    except CompraError:
        pass

    # Guard: FacturaCompra con ámbito inválido y RecepcionMercancia con ámbito inconsistente
    from django.core.exceptions import ValidationError as DjangoValidationError
    from apps.compras.models import RecepcionMercancia
    from apps.core.base_models import resolver_ambito_documento

    assert resolver_ambito_documento(None) == "FISCAL"
    with pytest.raises(CompraError, match="inválido"):
        registrar_factura_compra(
            rec_ger["recepcion"],
            numero_factura="FC-INV-AMB",
            fecha_emision=f_t0,
            usuario=usuarios["CONTADOR_FISCAL"],
            ambito="INVALIDO",
        )
    rec_incons = RecepcionMercancia(
        id_empresa=empresa,
        id_orden_compra=oc_fiscal,
        fecha_recepcion=f_t0,
        monto_total=Decimal("10.00"),
        ambito="GERENCIAL",
    )
    with pytest.raises(DjangoValidationError, match="ámbito"):
        rec_incons.full_clean()

    # Recepción de servicio comprable (no debe exigir ni mover stock) + filtro HTTP ?ambito=GERENCIAL
    prod_srv_comp = Producto.objects.create(
        id_empresa=empresa,
        sku="AV-SRV-COMP-01",
        nombre_producto="Servicio Flete Contratado",
        id_categoria=cat_srv,
        id_unidad_medida_base=un_srv,
        id_moneda_precio=moneda_usd,
        tipo_producto="SERVICIO",
        es_vendible=False,
        es_comprable=True,
        costo_promedio=Decimal("50.0000"),
    )
    oc_srv_c = OrdenCompra.objects.create(
        id_empresa=empresa,
        id_proveedor=proveedor_esp,
        id_almacen_destino=alm_ppal,
        numero_orden="OC-SRV-001",
        fecha_orden=f_t0,
        estado="BORRADOR",
        ambito="GERENCIAL",
    )
    DetalleOrdenCompra.objects.create(
        id_orden_compra=oc_srv_c,
        id_producto=prod_srv_comp,
        cantidad=Decimal("1.0000"),
        precio_unitario=Decimal("50.0000"),
        subtotal=Decimal("50.0000"),
    )
    aprobar_orden_compra(oc_srv_c, usuarios["COMPRADOR"])
    rec_srv_c = registrar_recepcion(
        oc_srv_c,
        alm_ppal,
        usuarios["ALMACENISTA"],
        [{"producto": prod_srv_comp, "cantidad": 1, "costo_unitario": "50.00"}],
    )
    assert rec_srv_c["movimientos"] == []

    c_compras = APIClient()
    c_compras.force_authenticate(user=usuarios["GERENTE"])
    r_ocs_ger = c_compras.get("/api/compras/ordenes-compra/?ambito=GERENCIAL")
    assert r_ocs_ger.status_code == 200
    r_recs_ger = c_compras.get("/api/compras/recepciones-mercancia/?ambito=GERENCIAL")
    assert r_recs_ger.status_code == 200

    # Guard: producto es_comprable=False (SERV-01) no debe aprobarse en OC
    oc_no_comp_kwargs = {
        "id_empresa": empresa,
        "id_proveedor": proveedor_esp,
        "id_almacen_destino": alm_ppal,
        "numero_orden": "OC-BAD-SERV",
        "fecha_orden": f_t0,
        "estado": "BORRADOR",
    }
    if any(f.name == "ambito" for f in OrdenCompra._meta.fields):
        oc_no_comp_kwargs["ambito"] = "FISCAL"
    oc_no_comp = OrdenCompra.objects.create(**oc_no_comp_kwargs)
    DetalleOrdenCompra.objects.create(
        id_orden_compra=oc_no_comp,
        id_producto=prod_srv,
        cantidad=Decimal("1"),
        precio_unitario=Decimal("25"),
        subtotal=Decimal("25"),
    )
    try:
        aprobar_orden_compra(oc_no_comp, usuarios["COMPRADOR"])
        _registrar_hallazgo(
            hallazgos,
            "E2E-005",
            "compras/services.aprobar_orden_compra",
            "Permitió aprobar OrdenCompra con producto es_comprable=False (AV-SRV-01).",
        )
    except CompraError:
        pass

    # Cargar inventario de consumo interno + kit + Transferencia inter-almacén + Consumo Interno SALIDA_INTERNA
    registrar_movimiento(
        empresa=empresa,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="ENTRADA",
        producto=prod_interno,
        cantidad=Decimal("10"),
        almacen_destino=alm_ppal,
        costo_unitario=Decimal("10.00"),
        usuario=usuarios["ALMACENISTA"],
        ambito="FISCAL",
    )
    req_int = RequisicionInterna.objects.create(
        id_empresa=empresa,
        numero_requisicion="REQ-INT-001",
        solicitado_por=usuarios["ALMACENISTA"],
        id_almacen_origen=alm_ppal,
        fecha_solicitud=hoy,
    )
    DetalleRequisicion.objects.create(
        id_requisicion=req_int, id_producto=prod_interno, cantidad_solicitada=Decimal("3")
    )
    aprobar_requisicion(req_int, usuarios["GERENTE"])
    movs_int = despachar_requisicion_interna(req_int, usuarios["ALMACENISTA"])
    assert len(movs_int) == 1
    assert StockActual.objects.get(
        id_empresa=empresa, id_producto=prod_interno, id_almacen=alm_ppal
    ).cantidad_disponible == Decimal("7")

    # Transferencia entre almacenes ALM-PPAL -> ALM-SEC (2 uds)
    registrar_movimiento(
        empresa=empresa,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="TRANSFERENCIA",
        producto=prod_vc,
        cantidad=Decimal("2"),
        almacen_origen=alm_ppal,
        almacen_destino=alm_sec,
        usuario=usuarios["ALMACENISTA"],
        ambito="FISCAL",
    )

    # Semáforo margen & Conteo Cíclico Dual GERENCIAL
    sem = evaluar_semaforo_margen_producto(prod_vc)
    assert sem["semaforo"] == "VERDE"
    conteo_ger = crear_conteo_inventario(
        empresa=empresa,
        almacen=alm_ppal,
        responsable=usuarios["ALMACENISTA"],
        tipo_conteo="CICLICO",
        ambito="GERENCIAL",
        observaciones="Conteo real nocturno",
    )
    registrar_escaneo_conteo(
        conteo=conteo_ger,
        codigo_o_producto_id=prod_vc.codigo_barras or prod_vc.sku,
        cantidad=Decimal("28"),
        modo="REEMPLAZAR",
    )
    from apps.inventario.services_supply_chain import enviar_conteo_aprobacion

    enviar_conteo_aprobacion(conteo_ger)
    aprobar_aplicar_conteo(conteo_ger, aprobador=usuarios["GERENTE"])

    # Pago CxP GERENCIAL con diferencial cambiario: no debe filtrar a FISCAL (E2E-012)
    as_fis_pre_cxp_ger = AsientoContable.objects.filter(id_empresa=empresa, ambito="FISCAL").count()
    registrar_abono_cxp(
        rec_ger["cxp"],
        Decimal("50.00"),
        usuarios["TESORERO"],
        descripcion="Abono CxP gerencial tasa t1",
        tasa_original=Decimal("45.00"),
        tasa_pago=Decimal("50.00"),
    )
    if AsientoContable.objects.filter(id_empresa=empresa, ambito="FISCAL").count() > as_fis_pre_cxp_ger:
        _registrar_hallazgo(
            hallazgos,
            "E2E-012",
            "cuentas_por_pagar/services.registrar_abono_cxp",
            "Abono + DiferenciaCambiaria a CxP originada en compra GERENCIAL generó asiento(s) en ámbito FISCAL.",
        )

    # Pago CxP con diferencial cambiario (tasa original 45 -> tasa pago 50 = PERDIDA)
    cxp_fis = rec_fis["cxp"]
    # Ajuste pendiente por retenciones: pagamos monto_pendiente completo en CxP para probar Dif Cambiaria
    abono_cxp = registrar_abono_cxp(
        cxp_fis,
        cxp_fis.monto_pendiente,
        usuarios["TESORERO"],
        descripcion="Pago factura compra tasa t1",
        tasa_original=Decimal("45.00"),
        tasa_pago=Decimal("50.00"),
    )
    dif_cxp = DiferenciaCambiaria.objects.filter(id_abono_cxp=abono_cxp).first()
    assert dif_cxp is not None and dif_cxp.tipo == "PERDIDA"

    # =========================================================================
    # ESCENARIO 4 — Ventas Duales, Precios Brecha, Bloqueo Mora, IGTF 3%,
    #                Conciliación N:M y Diferencial Cambiario CxC
    # =========================================================================
    lista_ref = ListaPrecio.objects.create(
        id_empresa=empresa, nombre="Lista 1 USD", codigo="L1", es_referencia=True, id_moneda=moneda_usd
    )
    DetallePrecio.objects.create(
        id_lista=lista_ref, id_producto=prod_vc, precio=Decimal("35.0000"), precio_minimo=Decimal("28.0000")
    )
    ReglaPrecioDinamico.objects.create(
        id_empresa=empresa,
        codigo="BRECHA_VES",
        nombre="Recargo Brecha Efectivo VES",
        tipo_factor="BRECHA_CAMBIARIA",
        modo_calculo="BRECHA_TASA",
        valor_factor=Decimal("100.00"),
        codigo_tipo_tasa_referencia="PARALELO",
        prioridad=1,
    )
    cot_brecha = calcular_precio_dinamico(
        prod_vc,
        empresa,
        contacto=cliente_contado.contacto,
        cantidad=Decimal("2"),
        moneda_pago=moneda_ves.codigo_iso,
        fecha=f_t2,
        tipo_tasa_referencia="PARALELO",
    )
    assert Decimal(str(cot_brecha["brecha_cambiaria_pct"])) == Decimal("25.00")

    # 4A. Venta FISCAL: Pedido(CONTADO) -> NotaVenta(FISCAL) -> FacturaFiscal USD (IVA 16% + IGTF 3%) + ND + Devolución
    ped_fis = Pedido.objects.create(
        id_empresa=empresa,
        id_cliente=cliente_contado,
        numero_pedido="PED-FIS-001",
        fecha_pedido=hoy,
        estado="PENDIENTE",
    )
    DetallePedido.objects.create(
        id_pedido=ped_fis,
        id_producto=prod_vc,
        cantidad=Decimal("4"),
        precio_unitario=Decimal("35.0000"),
        subtotal=Decimal("140.0000"),
    )
    confirmar_pedido(ped_fis, alm_ppal, usuarios["VENDEDOR"])
    nv_fis = NotaVenta.objects.create(
        id_empresa=empresa,
        id_cliente=cliente_contado,
        id_pedido_origen=ped_fis,
        numero_nota="NV-FIS-001",
        fecha_nota=hoy,
        ambito="FISCAL",
        estado="BORRADOR",
    )
    DetalleNotaVenta.objects.create(
        id_nota_venta=nv_fis,
        id_producto=prod_vc,
        cantidad=Decimal("4"),
        precio_unitario=Decimal("35.0000"),
        subtotal=Decimal("140.0000"),
    )
    confirmar_nota_venta(nv_fis, alm_ppal, usuarios["VENDEDOR"])
    res_ff = emitir_factura_fiscal(nv_fis, moneda=moneda_usd, usuario=usuarios["CONTADOR_FISCAL"])
    factura_fis = res_ff["factura"]
    assert factura_fis.monto_iva == Decimal("22.40")
    assert factura_fis.monto_igtf == Decimal("4.20")

    # Nota Débito Fiscal
    nd_fis = NotaDebitoFiscal.objects.create(
        id_empresa=empresa,
        id_cliente=cliente_contado,
        id_factura_origen=factura_fis,
        fecha_emision=hoy,
        id_moneda=moneda_usd,
        base_imponible=Decimal("10.00"),
        monto_iva=Decimal("1.60"),
        monto_total=Decimal("11.60"),
        motivo="CARGO_ADICIONAL",
        observaciones="Cargo flete express",
        ambito="FISCAL",
    )
    emitir_nota_debito_fiscal(nd_fis, usuario=usuarios["CONTADOR_FISCAL"])

    # 4B. Venta GERENCIAL: NotaVenta(GERENCIAL) -> debe bajar stock REAL, crear CxC, asiento GERENCIAL,
    #     bloquear FacturaFiscal, Y NO contaminar Contabilidad Fiscal ni Libro Ventas al cobrarla/devolverla
    nv_ger = NotaVenta.objects.create(
        id_empresa=empresa,
        id_cliente=cliente_esp,
        numero_nota="NV-GER-001",
        fecha_nota=hoy,
        ambito="GERENCIAL",
        estado="BORRADOR",
        documento_json={"bloquear_facturacion": True},
    )
    DetalleNotaVenta.objects.create(
        id_nota_venta=nv_ger,
        id_producto=prod_vc,
        cantidad=Decimal("2"),
        precio_unitario=Decimal("35.0000"),
        subtotal=Decimal("70.0000"),
    )
    res_nv_ger = confirmar_nota_venta(nv_ger, alm_ppal, usuarios["VENDEDOR"])
    cxc_ger = res_nv_ger["cxc"]
    assert cxc_ger.documento_json["ambito"] == "GERENCIAL"
    assert res_nv_ger["asiento"].ambito == "GERENCIAL"

    # Guard: emitir_factura_fiscal sobre NotaVenta GERENCIAL bloqueada o con permitir_desde_gerencial=False debe bloquearse!
    try:
        emitir_factura_fiscal(nv_ger, moneda=moneda_usd, usuario=usuarios["CONTADOR_FISCAL"])
        _registrar_hallazgo(
            hallazgos,
            "E2E-006",
            "ventas/services.emitir_factura_fiscal",
            "Permitió emitir FacturaFiscal SENIAT desde una NotaVenta con ambito='GERENCIAL' y bloquear_facturacion=True.",
        )
    except VentaError:
        pass

    # Cobro parcial de cxc_ger vía abono directo -> verificar si Asiento PAGO_CXC quedó en GERENCIAL!
    asientos_fis_antes = AsientoContable.objects.filter(id_empresa=empresa, ambito="FISCAL").count()
    registrar_abono_cxc(cxc_ger, Decimal("20.00"), usuarios["TESORERO"], "Abono efectivo USD NV gerencial")
    asientos_fis_despues = AsientoContable.objects.filter(id_empresa=empresa, ambito="FISCAL").count()
    if asientos_fis_despues > asientos_fis_antes:
        _registrar_hallazgo(
            hallazgos,
            "E2E-007",
            "cuentas_por_cobrar/services.registrar_abono",
            "Abono directo a CxC con documento_json['ambito']=='GERENCIAL' generó asiento PAGO_CXC en ámbito FISCAL.",
        )

    # Cobro restante vía Pago VES (tasa t2=54 vs tasa t0=45) + aplicar_pago_a_documentos (conciliación N:M + FX CxC)
    pago_cxc_ves = Pago.objects.create(
        id_empresa=empresa,
        id_contacto=cliente_esp.contacto,
        tipo_operacion="INGRESO",
        tipo_documento="CXC",
        id_documento=cxc_ger.pk,
        fecha_pago=timezone.now(),
        monto=Decimal("2700.00"),  # 50 USD * 54
        id_moneda=moneda_ves,
        tasa=Decimal("54.000000"),
        id_metodo_pago=mp_pago_movil,
        referencia="PM-998877",
        id_cuenta_bancaria=banco_ves,
        id_caja_fisica=caja_fisica,
        id_usuario_registro=usuarios["TESORERO"],
    )
    asientos_fis_pre_nm = AsientoContable.objects.filter(id_empresa=empresa, ambito="FISCAL").count()
    asigs_ger = aplicar_pago_a_documentos(
        pago_cxc_ves,
        [
            {
                "tipo_documento": "CUENTA_POR_COBRAR",
                "id_documento": str(cxc_ger.pk),
                "monto_asignado_pago": "2700.00",
                "tasa_aplicada": "0.01851852",
                "monto_asignado_documento": "50.00",
                "tasa_original": "45.00",
                "tasa_liquidacion": "50.00",
            }
        ],
        usuario=usuarios["TESORERO"],
    )
    asientos_fis_post_nm = AsientoContable.objects.filter(id_empresa=empresa, ambito="FISCAL").count()
    if asientos_fis_post_nm > asientos_fis_pre_nm:
        _registrar_hallazgo(
            hallazgos,
            "E2E-008",
            "finanzas/services_conciliacion_pagos.aplicar_pago_a_documentos",
            "aplicar_pago_a_documentos sobre CxC GERENCIAL posteó asiento(s) PAGO_CXC / diferencial cambiario en FISCAL.",
        )
    assert asigs_ger[0].diferencia_cambiaria > Decimal("0")

    # Devolución parcial de NotaVenta GERENCIAL -> no debe tocar MovimientoInventario/Asiento FISCAL
    nv_ger_dev = NotaVenta.objects.create(
        id_empresa=empresa,
        id_cliente=cliente_contado,
        numero_nota="NV-GER-002",
        fecha_nota=hoy,
        ambito="GERENCIAL",
        estado="BORRADOR",
    )
    det_nv_dev = DetalleNotaVenta.objects.create(
        id_nota_venta=nv_ger_dev,
        id_producto=prod_vc,
        cantidad=Decimal("2"),
        precio_unitario=Decimal("35.0000"),
        subtotal=Decimal("70.0000"),
    )
    confirmar_nota_venta(nv_ger_dev, alm_ppal, usuarios["VENDEDOR"])
    mov_fis_pre_dev = MovimientoInventario.objects.filter(id_empresa=empresa, ambito="FISCAL").count()
    as_fis_pre_dev = AsientoContable.objects.filter(id_empresa=empresa, ambito="FISCAL").count()
    res_dev = registrar_devolucion_pos(
        nv_ger_dev,
        lineas=[{"id_detalle": det_nv_dev.pk, "cantidad": 1}],
        almacen=alm_ppal,
        usuario=usuarios["TESORERO"],
        metodo_pago=mp_ef_usd,
        motivo="CAMBIO_CLIENTE",
    )
    assert res_dev["devolucion"].pk is not None
    with pytest.raises(VentaError, match="exclusivamente GERENCIAL"):
        emitir_factura_fiscal(
            nv_ger_dev,
            moneda=moneda_usd,
            usuario=usuarios["CONTADOR_FISCAL"],
            permitir_desde_gerencial=False,
        )
    if MovimientoInventario.objects.filter(id_empresa=empresa, ambito="FISCAL").count() > mov_fis_pre_dev:
        _registrar_hallazgo(
            hallazgos,
            "E2E-009",
            "ventas/services.registrar_devolucion_pos",
            "Devolución de NotaVenta GERENCIAL creó MovimientoInventario(ENTRADA) con ambito='FISCAL'.",
        )
    if AsientoContable.objects.filter(id_empresa=empresa, ambito="FISCAL").count() > as_fis_pre_dev:
        _registrar_hallazgo(
            hallazgos,
            "E2E-010",
            "ventas/services.registrar_devolucion_pos",
            "Devolución de NotaVenta GERENCIAL creó AsientoContable(DEVOLUCION_VENTA) en ambito='FISCAL'.",
        )

    # Venta de SERVICIO vendible=True + rechazo de producto solo-compra (es_vendible=False)
    ped_solo_comp = Pedido.objects.create(
        id_empresa=empresa,
        id_cliente=cliente_contado,
        numero_pedido="PED-BAD-SC",
        fecha_pedido=hoy,
        estado="PENDIENTE",
    )
    DetallePedido.objects.create(
        id_pedido=ped_solo_comp,
        id_producto=prod_solo_compra,
        cantidad=Decimal("1"),
        precio_unitario=Decimal("10"),
        subtotal=Decimal("10"),
    )
    with pytest.raises(VentaError, match="solo-compra"):
        confirmar_pedido(ped_solo_comp, alm_ppal, usuarios["VENDEDOR"])

    # Bloqueo por mora real en cliente_esp (CxC vencida con saldo pendiente -> bloquea nuevo pedido)
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar

    CuentaPorCobrar.objects.create(
        cliente=cliente_esp,
        empresa=empresa,
        monto=Decimal("100.00"),
        fecha_emision=hoy - timedelta(days=25),
        fecha_vencimiento=hoy - timedelta(days=5),
        estado="vencida",
        referencia_externa="CXC-VENC-001",
    )
    ped_mora = Pedido.objects.create(
        id_empresa=empresa,
        id_cliente=cliente_esp,
        numero_pedido="PED-MORA-01",
        fecha_pedido=hoy,
        estado="PENDIENTE",
    )
    DetallePedido.objects.create(
        id_pedido=ped_mora,
        id_producto=prod_vc,
        cantidad=Decimal("1"),
        precio_unitario=Decimal("35"),
        subtotal=Decimal("35"),
    )
    with pytest.raises(VentaError, match="vencida"):
        confirmar_pedido(ped_mora, alm_ppal, usuarios["VENDEDOR"])

    # Servicio vendible=True: no debe exigir stock físico en Almacén Principal
    nv_srv = NotaVenta.objects.create(
        id_empresa=empresa,
        id_cliente=cliente_contado,
        numero_nota="NV-SRV-001",
        fecha_nota=hoy,
        ambito="FISCAL",
        estado="BORRADOR",
    )
    det_nv_srv = DetalleNotaVenta.objects.create(
        id_nota_venta=nv_srv,
        id_producto=prod_srv,
        cantidad=Decimal("1"),
        precio_unitario=Decimal("25.0000"),
        subtotal=Decimal("25.0000"),
    )
    try:
        confirmar_nota_venta(nv_srv, alm_ppal, usuarios["VENDEDOR"])
        ped_srv = Pedido.objects.create(
            id_empresa=empresa,
            id_cliente=cliente_contado,
            numero_pedido="PED-SRV-01",
            fecha_pedido=hoy,
            estado="PENDIENTE",
        )
        DetallePedido.objects.create(
            id_pedido=ped_srv,
            id_producto=prod_srv,
            cantidad=Decimal("1"),
            precio_unitario=Decimal("25.0000"),
            subtotal=Decimal("25.0000"),
        )
        res_ped_srv = confirmar_pedido(ped_srv, alm_ppal, usuarios["VENDEDOR"])
        assert res_ped_srv["reservas"] == []
        res_dev_srv = registrar_devolucion_pos(
            nv_srv,
            lineas=[{"id_detalle": det_nv_srv.pk, "cantidad": 1}],
            almacen=alm_ppal,
            usuario=usuarios["TESORERO"],
            metodo_pago=mp_ef_usd,
            motivo="CAMBIO_CLIENTE",
        )
        assert res_dev_srv["movimientos"] == []
    except VentaError as exc:
        _registrar_hallazgo(
            hallazgos,
            "E2E-013",
            "ventas/services.entregar_nota_venta",
            f"Venta de producto tipo_producto='SERVICIO' (AV-SRV-01) falló al confirmar NotaVenta por exigir stock físico: {exc}",
        )

    # =========================================================================
    # ESCENARIO 5 — Gastos Duales, OperacionCambioDivisa y Conciliación Bancaria
    # =========================================================================
    cat_gasto = CategoriaGasto.objects.create(
        id_empresa=empresa,
        nombre_categoria="Fletes y Viáticos",
        id_cuenta_contable=ctas["GASTOS"],
        requiere_factura=False,
    )
    gasto_fis = Gasto.objects.create(
        id_empresa=empresa,
        fecha_gasto=hoy,
        descripcion="Flete fiscal con IVA",
        monto=Decimal("116.00"),
        monto_iva=Decimal("16.00"),
        id_moneda=moneda_usd,
        id_categoria_gasto=cat_gasto,
        id_proveedor=proveedor_esp,
        tiene_factura=True,
        numero_factura="G-FIS-01",
        ambito="FISCAL",
        id_usuario_registro=usuarios["CONTADOR_FISCAL"],
    )
    res_gf = aprobar_gasto(gasto_fis, usuario=usuarios["GERENTE"])
    assert res_gf["asiento"].ambito == "FISCAL"
    assert res_gf["asiento_iva"].ambito == "FISCAL"

    gasto_ger = Gasto.objects.create(
        id_empresa=empresa,
        fecha_gasto=hoy,
        descripcion="Bono logístico efectivo USD",
        monto=Decimal("50.00"),
        monto_iva=Decimal("0.00"),
        id_moneda=moneda_usd,
        id_categoria_gasto=cat_gasto,
        tiene_factura=False,
        ambito="GERENCIAL",
        id_usuario_registro=usuarios["GERENTE"],
    )
    res_gg = aprobar_gasto(gasto_ger, usuario=usuarios["GERENTE"])
    assert res_gg["asiento"].ambito == "GERENCIAL"

    # Operación cambio divisa + conciliación bancaria vía HTTP
    client_admin = APIClient()
    client_admin.force_authenticate(user=usuarios["TESORERO"])
    resp_cambio = client_admin.post(
        "/api/tesoreria/operaciones-cambio-divisa/",
        {
            "empresa": str(empresa.pk),
            "numero_operacion": "CAM-AV-001",
            "fecha_operacion": timezone.now().isoformat(),
            "tipo_operacion": "VENTA",
            "moneda_origen": str(moneda_usd.pk),
            "moneda_destino": str(moneda_ves.pk),
            "monto_origen": "100.0000",
            "tasa_cambio": "54.000000",
            "monto_destino": "5400.0000",
            "caja_origen": str(caja_principal.pk),
            "banco_destino": str(banco_ves.pk),
            "metodo_pago_origen": str(mp_ef_usd.pk),
            "metodo_pago_destino": str(mp_transf_ves.pk),
        },
        format="json",
    )
    assert resp_cambio.status_code == 201, resp_cambio.data

    # Conciliación bancaria contra pago VES
    csv_banco = (
        "fecha,descripcion,tipo,monto,referencia\n"
        f"{hoy.isoformat()},Pago Movil Mirandino,CREDITO,2700.00,PM-998877\n"
    ).encode("utf-8")
    resp_imp = client_admin.post(
        "/api/tesoreria/movimientos-bancarios/importar-csv/",
        {
            "empresa": str(empresa.pk),
            "cuenta_bancaria": str(banco_ves.pk),
            "archivo": SimpleUploadedFile("extracto.csv", csv_banco),
        },
        format="multipart",
    )
    assert resp_imp.status_code in (200, 201), resp_imp.data
    conc_res = conciliar_automatico(empresa, banco_ves)
    assert conc_res["conciliados"] >= 1
    conc_obj = iniciar_conciliacion(
        empresa,
        banco_ves,
        f_t0,
        f_t2,
        Decimal("102700.00"),
        Decimal("102700.00"),
        usuario=usuarios["TESORERO"],
    )
    cerrar_conciliacion(conc_obj, usuario=usuarios["TESORERO"])

    # =========================================================================
    # ESCENARIO 6 — Nómina Mixta VE (Formal LOTTT Bs + Bonificaciones USD)
    # =========================================================================
    emp_1 = Empleado.objects.create(
        empresa=empresa,
        nombre="María",
        apellido="González",
        cedula="V-18123456",
        fecha_ingreso=date(2022, 1, 15),
    )
    FichaSalarialDual.objects.create(
        id_empresa=empresa,
        id_empleado=emp_1,
        salario_base_formal_ves=Decimal("4500.0000"),
        cestaticket_mensual_ves=Decimal("2160.0000"),
        paquete_objetivo_mensual=Decimal("500.0000"),
        moneda_paquete=moneda_usd,
        bono_fijo_gerencial=Decimal("50.0000"),
        cuenta_bancaria_formal="01340001009998887766",
    )
    PrestamoEmpleado.objects.create(
        id_empresa=empresa,
        id_empleado=emp_1,
        ambito_descuento="GERENCIAL",
        moneda=moneda_usd,
        monto_principal=Decimal("100.0000"),
        cuotas_totales=2,
        monto_cuota=Decimal("50.0000"),
        saldo_pendiente=Decimal("100.0000"),
        fecha_otorgamiento=f_t0,
    )
    per_nom = PeriodoNomina.objects.create(
        id_empresa=empresa,
        nombre_periodo="Quincena Nov Ávila",
        fecha_inicio=hoy - timedelta(days=14),
        fecha_fin=hoy,
        fecha_pago=hoy,
        tipo_periodo="QUINCENAL",
    )
    res_nom = procesar_nomina_dual(
        empresa=empresa,
        periodo=per_nom,
        usuario=usuarios["RRHH"],
        tasa_bcv=Decimal("54.00"),
    )
    assert res_nom["proceso_fiscal"].ambito == "FISCAL"
    assert res_nom["proceso_gerencial"].ambito == "GERENCIAL"
    assert AsientoContable.objects.get(pk=res_nom["asiento_fiscal_id"]).ambito == "FISCAL"
    assert AsientoContable.objects.get(pk=res_nom["asiento_gerencial_id"]).ambito == "GERENCIAL"
    disp_ger_netos = [
        {"empleado": emp_1.nombre, "monto": d.monto}
        for d in DispersionPagoNomina.objects.filter(
            id_proceso_nomina=res_nom["proceso_gerencial"], ambito="GERENCIAL"
        )
    ]
    arq = calcular_arqueo_efectivo_usd(disp_ger_netos)
    assert Decimal(arq["total_efectivo_usd"]) >= Decimal("0")

    # =========================================================================
    # ESCENARIO 7 — Doble Contabilidad Trimonetaria, Libros SENIAT, Art. 177 & Cierre
    # =========================================================================
    for amb in ("FISCAL", "GERENCIAL", "CONSOLIDADO"):
        for mon_rep in ("BASE", "PAIS", "REFERENCIA"):
            bc = generar_balance_comprobacion(empresa, fecha_desde=f_t0, fecha_hasta=f_t2, ambito=amb, moneda=mon_rep)
            pnl = generar_estado_resultados(empresa, fecha_desde=f_t0, fecha_hasta=f_t2, ambito=amb, moneda=mon_rep)
            bg = generar_balance_general(empresa, fecha_corte=f_t2, ambito=amb, moneda=mon_rep)
            assert Decimal(str(bc["total_debe"])) == Decimal(
                str(bc["total_haber"])
            ), f"Descuadre BC {amb}/{mon_rep}: {bc['total_debe']} vs {bc['total_haber']}"
            assert bc["cuadrado"] is True, f"BC no cuadrado en {amb}/{mon_rep}: {bc}"
            assert bg["ecuacion_cuadrada"] is True, f"Ecuación contable descuadrada en {amb}/{mon_rep}: {bg}"
            assert pnl is not None
    mayor = generar_libro_mayor_auxiliar(empresa, id_cuenta_contable=ctas["CXC"], ambito="FISCAL", moneda="BASE")
    assert mayor is not None

    # Libros Fiscales SENIAT — verificar 0 fugas gerenciales
    lv_txt = generar_libro_ventas_txt(empresa, f_t0, f_t2)
    lc_txt = generar_libro_compras_txt(empresa, f_t0, f_t2)
    assert "NV-GER-001" not in lv_txt
    assert "OC-GER-001" not in lc_txt
    assert factura_fis.numero_factura in lv_txt
    assert "FC-FIS-0001" in lc_txt

    ret_iva_txt = generar_txt_retenciones_iva_seniat(empresa, f"{hoy:%Y%m}")
    ret_islr_xml = generar_xml_retenciones_islr_seniat(empresa, f"{hoy:%Y%m}")
    assert "FC-FIS-0001" in ret_iva_txt
    assert "FC-FIS-0001" in ret_islr_xml

    lib_art177 = generar_libro_inventario_art177(empresa, f_t0, f_t2)
    item_vc_art = next((x for x in lib_art177["items"] if x["sku"] == "AV-PROD-01"), None)
    assert item_vc_art is not None
    # En inventario FISCAL entraron solo 20 uds (OC-FIS-001), NO las 10 uds de OC-GER-001!
    if Decimal(item_vc_art["entradas"]) != Decimal("20.0000"):
        _registrar_hallazgo(
            hallazgos,
            "E2E-011",
            "fiscal/services_retenciones.generar_libro_inventario_art177",
            f"Libro Inv. Art. 177 muestra entradas={item_vc_art['entradas']} para AV-PROD-01 (esperado 20.0000; contaminado por OC/Devolución GERENCIAL).",
        )

    # Reversión de asiento + cierre período contable
    as_rev = revertir_asiento(res_gf["asiento"], usuario=usuarios["CONTADOR_FISCAL"], motivo="Reverso prueba E2E")
    assert as_rev.asiento_revertido == res_gf["asiento"]

    cerrar_periodo_contable(empresa, hoy.year, hoy.month, usuario=usuarios["CONTADOR_FISCAL"])
    with pytest.raises((AsientoError, GastoError)):
        aprobar_gasto(
            Gasto.objects.create(
                id_empresa=empresa,
                fecha_gasto=hoy,
                descripcion="Gasto tras cierre",
                monto=Decimal("10.00"),
                id_moneda=moneda_usd,
                id_categoria_gasto=cat_gasto,
                ambito="FISCAL",
                id_usuario_registro=usuarios["CONTADOR_FISCAL"],
            ),
            usuario=usuarios["GERENTE"],
        )

    # =========================================================================
    # ESCENARIO 8 — TMS Logística, Portales, Chatter/WhatsApp, 5 Agentes IA, RBAC & Isolation
    # =========================================================================
    desp = Despacho.objects.create(
        id_empresa=empresa,
        numero_despacho="DESP-AV-001",
        id_nota_venta=nv_fis,
        fecha_despacho=timezone.now(),
        id_almacen_origen=alm_ppal,
        direccion_destino="Av. Principal Las Mercedes, Caracas",
        id_transportista=emp_1,
        estado_despacho="PENDIENTE",
    )
    veh = Vehiculo.objects.create(
        id_empresa=empresa, placa="AV0123VE", marca_modelo="Ford Cargo", capacidad_kg=Decimal("3500")
    )
    cond = Conductor.objects.create(
        id_empresa=empresa,
        nombre_completo="Pedro Pérez",
        cedula="V-14555666",
        telefono="+584145556677",
        licencia_grado="5TA",
        id_usuario=usuarios["CONDUCTOR"],
        id_vehiculo_asignado=veh,
    )
    ruta = RutaDespacho.objects.create(
        id_empresa=empresa,
        codigo="RUTA-AV-01",
        fecha_ruta=hoy,
        id_almacen_origen=alm_ppal,
        origen_lat=Decimal("10.480594"),
        origen_lng=Decimal("-66.903606"),
        id_vehiculo=veh,
        id_conductor=cond,
    )
    parada = ParadaEntrega.objects.create(
        id_empresa=empresa,
        id_ruta=ruta,
        id_despacho=desp,
        secuencia=1,
        direccion_texto="Las Mercedes",
        latitud=Decimal("10.478000"),
        longitud=Decimal("-66.859000"),
    )
    guia = emitir_guia_despacho_seniat(ruta=ruta)
    assert guia.get("numero_control")
    iniciar_ruta_despacho(ruta, usuarios["CONDUCTOR"])
    parada.refresh_from_db()
    registrar_epod_parada(
        parada=parada,
        usuario=usuarios["CONDUCTOR"],
        receptor_nombre="Juan Receptor",
        receptor_cedula="V-19111222",
        firma_base64="<svg></svg>",
    )

    # Chatter + WhatsApp
    msg_wa = enviar_whatsapp_documento(
        empresa=empresa,
        tipo_documento="FACTURA",
        documento_id=factura_fis.pk,
        telefono="+584141112233",
        plantilla="cobranza",
        contexto={
            "numero": factura_fis.numero_factura,
            "saldo": str(factura_fis.monto_total),
            "cliente": cliente_contado.razon_social,
        },
        autor=usuarios["VENDEDOR"],
    )
    assert isinstance(msg_wa, MensajeChatterDocumento)

    # 5 Agentes IA Operativos
    for ag_cod in AGENTES_OPERATIVOS:
        ej = ejecutar_agente_operativo(empresa, ag_cod, usuario=usuarios["GERENTE"])
        assert ej["agente_codigo"] == ag_cod

    # Portales HTTP + RBAC + Aislamiento Cross-Tenant vs empresa_b
    c_cond = APIClient()
    c_cond.force_authenticate(user=usuarios["CONDUCTOR"])
    assert c_cond.get("/api/despacho/portal-conductor/mis-rutas/").status_code == 200

    c_vend = APIClient()
    c_vend.force_authenticate(user=usuarios["VENDEDOR"])
    assert c_vend.get("/api/ventas/portal-vendedor/cartera/").status_code == 200
    assert c_vend.get("/api/ventas/portal-vendedor/catalogo/").status_code == 200

    # Portal Cliente OTP -> Login -> Cartera
    c_pub = APIClient()
    r_otp = c_pub.post(
        "/api/ventas/portal-cliente/auth/solicitar-otp/",
        {"id_empresa": str(empresa.pk), "rif": cliente_esp.rif, "canal": "WHATSAPP"},
        format="json",
    )
    assert r_otp.status_code in (200, 201), r_otp.data

    # Verificar que Vendedor (no pertenece a empresa_b) no accede a empresa_b
    assert c_vend.get(f"/api/contabilidad/reportes/estado-resultados/?empresa={empresa_b.pk}").status_code in (
        400,
        403,
        404,
    )

    assert not hallazgos, "Se detectaron los siguientes errores en el flujo E2E:\n- " + "\n- ".join(hallazgos)
