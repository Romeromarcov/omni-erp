"""
TEST-2 — Aislamiento multi-tenant de COMPORTAMIENTO, parametrizado (R-CODE-1).

Complementa al guard ESTRUCTURAL ``tests_api/test_aislamiento_cobertura.py`` (TEST-1),
que sólo verifica que cada ViewSet tenant sobreescribe ``get_queryset``. Aquí ejercemos
el comportamiento real contra la API: un usuario de Empresa A **no puede ver, modificar
ni borrar** objetos de Empresa B, y el listado de A nunca incluye objetos de B.

Diseño declarativo: una sola tabla ``CASES`` describe, por modelo tenant, cómo construir
una instancia para una empresa dada y qué campo intentar mutar. Añadir un módulo nuevo =
una fila más, no otra clase de ~50 líneas. Esta tabla **reemplaza y amplía** (añade DELETE)
los antiguos ``test_aislamiento_base.py`` / ``_modulos.py`` / ``_multimodulo.py``.

Severidad: un FAIL aquí = fuga de datos entre tenants → bloquea el merge.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from rest_framework.test import APIClient

from apps.almacenes.models import Almacen
from apps.auditoria.models import LogAuditoria
from apps.banca_electronica.models import CuentaBancariaEmpresa
from apps.compras.models import OrdenCompra
from apps.contabilidad.models import PlanCuentas
from apps.control_asistencia.models import HorarioTrabajo
from apps.crm.models import Cliente
from apps.finanzas.models import Caja, Pago
from apps.gastos.models import CategoriaGasto
from apps.gestion_aprobaciones.models import TipoAprobacion
from apps.integracion_b2b.models import ConfiguracionIntegracion
from apps.inventario.models import CategoriaProducto
from apps.manufactura.models import CentroTrabajo
from apps.nomina.models import PeriodoNomina
from apps.personalizacion.models import PersonalizacionConfig
from apps.proveedores.models import Proveedor
from apps.servicio_cliente.models import CategoriaTicket
from apps.ventas.models import Cotizacion

pytestmark = [pytest.mark.django_db, pytest.mark.tenant]


@dataclass
class IsolationCase:
    """Receta declarativa de aislamiento para un modelo tenant-aware."""

    id: str
    url: str
    pk_attr: str
    build: Callable[[Any, str, SimpleNamespace], Any]
    patch_payload: dict
    unchanged_attr: str
    # False para ViewSets de solo lectura (auditoría): se omite el test de escritura,
    # pero el de list/retrieve sigue aplicando.
    writable: bool = True
    extra: dict = field(default_factory=dict)


def _build_cliente(empresa, label, env):
    return Cliente.objects.create(
        id_empresa=empresa,
        razon_social=f"Cliente {label} S.A.",
        rif=f"J-1111111{label}-1"[:12],
    )


def _build_plan_cuentas(empresa, label, env):
    return PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta="1.0.0",
        nombre_cuenta=f"Activos {label}",
        tipo_cuenta="ACTIVO",
        naturaleza="DEUDORA",
        nivel=1,
    )


def _build_horario(empresa, label, env):
    return HorarioTrabajo.objects.create(
        id_empresa=empresa,
        nombre_horario=f"Horario {label}",
        total_horas_semanales=40,
    )


def _build_categoria_ticket(empresa, label, env):
    return CategoriaTicket.objects.create(
        id_empresa=empresa,
        nombre_categoria=f"Soporte {label}",
    )


def _build_almacen(empresa, label, env):
    return Almacen.objects.create(
        id_empresa=empresa,
        nombre_almacen=f"Almacén {label}",
        codigo_almacen=f"ALM-{label}",
    )


def _build_centro_trabajo(empresa, label, env):
    return CentroTrabajo.objects.create(
        id_empresa=empresa,
        codigo_centro=f"CT-{label}",
        nombre_centro=f"Centro {label}",
        tipo_centro="MANUAL",
    )


def _build_tipo_aprobacion(empresa, label, env):
    return TipoAprobacion.objects.create(
        id_empresa=empresa,
        codigo_tipo=f"APRO-{label}",
        nombre_tipo=f"Aprobación {label}",
        modulo_origen="ventas",
    )


def _build_config_integracion(empresa, label, env):
    return ConfiguracionIntegracion.objects.create(
        id_empresa=empresa,
        nombre_integracion=f"Integración {label}",
        tipo_integracion="REST",
        formato_datos="JSON",
    )


def _build_cuenta_bancaria(empresa, label, env):
    return CuentaBancariaEmpresa.objects.create(
        empresa=empresa,  # FK se llama `empresa`, no `id_empresa`
        banco=f"Banco {label}",
        numero_cuenta=f"0102-{label}-00-0000000000",
        tipo_cuenta="corriente",
        moneda=env.moneda,
    )


def _build_personalizacion(empresa, label, env):
    return PersonalizacionConfig.objects.create(
        id_empresa=empresa,
        version=1,
        config_yaml=f"campos: [{label}]",
        config_dict={},
        activo=True,
    )


def _build_caja(empresa, label, env):
    return Caja.objects.create(
        empresa=empresa,  # FK se llama `empresa`, no `id_empresa`
        nombre=f"Caja {label}",
        tipo_caja="REGISTRADORA",
        moneda=env.moneda,
    )


def _build_cotizacion(empresa, label, env):
    cliente = _build_cliente(empresa, label, env)
    hoy = date.today()
    return Cotizacion.objects.create(
        id_empresa=empresa,
        id_cliente=cliente,
        id_moneda=env.moneda,
        numero_cotizacion=f"COT-{label}-001",
        fecha_cotizacion=hoy,
        fecha_vencimiento=hoy + timedelta(days=30),
        estado="BORRADOR",
    )


def _build_categoria_producto(empresa, label, env):
    return CategoriaProducto.objects.create(
        id_empresa=empresa,
        nombre_categoria=f"Categoría {label}",
    )


def _build_pago(empresa, label, env):
    return Pago.objects.create(
        id_empresa=empresa,
        tipo_operacion="INGRESO",
        tipo_documento="PEDIDO",
        id_documento=uuid.uuid4(),
        fecha_pago="2026-01-15T10:00:00Z",
        monto=Decimal("100.00") if label == "A" else Decimal("200.00"),
        id_moneda=env.moneda,
        tasa=Decimal("1.0"),
        id_metodo_pago=env.metodo_pago,
    )


def _build_orden_compra(empresa, label, env):
    proveedor = Proveedor.objects.create(
        id_empresa=empresa,
        razon_social=f"Proveedor {label} S.A.",
        rif=f"J-3333333{label}-3"[:12],
    )
    return OrdenCompra.objects.create(
        id_empresa=empresa,
        id_proveedor=proveedor,
        numero_orden=f"OC-{label}-001",
        fecha_orden=date.today(),
        estado="BORRADOR",
    )


def _build_proveedor(empresa, label, env):
    return Proveedor.objects.create(
        id_empresa=empresa,
        razon_social=f"Proveedor {label} C.A.",
        rif=f"J-4444444{label}-4"[:12],
    )


def _build_categoria_gasto(empresa, label, env):
    return CategoriaGasto.objects.create(
        id_empresa=empresa,
        nombre_categoria=f"Gastos {label}",
    )


def _build_log_auditoria(empresa, label, env):
    return LogAuditoria.objects.create(
        id_empresa=empresa,
        modulo="Test",
        tipo_accion="CREATE",
        descripcion_accion=f"log {label}",
    )


def _build_periodo_nomina(empresa, label, env):
    hoy = date.today()
    return PeriodoNomina.objects.create(
        id_empresa=empresa,
        nombre_periodo=f"Período {label} Enero",
        fecha_inicio=hoy,
        fecha_fin=hoy + timedelta(days=30),
        fecha_pago=hoy + timedelta(days=35),
        tipo_periodo="MENSUAL",
        estado="ABIERTO",
    )


CASES: list[IsolationCase] = [
    IsolationCase("crm.Cliente", "/api/crm/clientes/", "id_cliente", _build_cliente,
                  {"razon_social": "Hackeado"}, "razon_social"),
    IsolationCase("contabilidad.PlanCuentas", "/api/contabilidad/plan-cuentas/", "id_cuenta_contable",
                  _build_plan_cuentas, {"nombre_cuenta": "Hackeado"}, "nombre_cuenta"),
    IsolationCase("control_asistencia.HorarioTrabajo", "/api/control-asistencia/horarios-trabajo/",
                  "id_horario", _build_horario, {"nombre_horario": "Hackeado"}, "nombre_horario"),
    IsolationCase("servicio_cliente.CategoriaTicket", "/api/servicio-cliente/categorias-ticket/",
                  "id_categoria_ticket", _build_categoria_ticket,
                  {"nombre_categoria": "Hackeado"}, "nombre_categoria"),
    IsolationCase("almacenes.Almacen", "/api/almacenes/almacenes/", "id_almacen", _build_almacen,
                  {"nombre_almacen": "Hackeado"}, "nombre_almacen"),
    IsolationCase("manufactura.CentroTrabajo", "/api/manufactura/centros-trabajo/", "id_centro_trabajo",
                  _build_centro_trabajo, {"nombre_centro": "Hackeado"}, "nombre_centro"),
    IsolationCase("gestion_aprobaciones.TipoAprobacion", "/api/gestion-aprobaciones/tipos-aprobacion/",
                  "id_tipo_aprobacion", _build_tipo_aprobacion, {"nombre_tipo": "Hackeado"}, "nombre_tipo"),
    IsolationCase("integracion_b2b.ConfiguracionIntegracion",
                  "/api/integracion-b2b/configuracion-integracion/", "id_configuracion",
                  _build_config_integracion, {"nombre_integracion": "Hackeado"}, "nombre_integracion"),
    IsolationCase("banca_electronica.CuentaBancariaEmpresa",
                  "/api/banca-electronica/cuentas-bancarias-empresa/", "id",
                  _build_cuenta_bancaria, {"banco": "Hackeado"}, "banco"),
    IsolationCase("personalizacion.PersonalizacionConfig", "/api/personalizacion/configuraciones/",
                  "id_config", _build_personalizacion, {"config_yaml": "campos: [hackeado]"}, "config_yaml"),
    IsolationCase("finanzas.Caja(tesoreria)", "/api/tesoreria/cajas/", "id_caja", _build_caja,
                  {"nombre": "Hackeado"}, "nombre"),
    IsolationCase("ventas.Cotizacion", "/api/ventas/cotizaciones/", "id_cotizacion", _build_cotizacion,
                  {"estado": "ACEPTADA"}, "estado"),
    IsolationCase("inventario.CategoriaProducto", "/api/inventario/categorias-producto/",
                  "id_categoria_producto", _build_categoria_producto,
                  {"nombre_categoria": "Hackeado"}, "nombre_categoria"),
    IsolationCase("finanzas.Pago", "/api/finanzas/pagos/", "id_pago", _build_pago,
                  {"monto": "999.00"}, "monto"),
    IsolationCase("compras.OrdenCompra", "/api/compras/ordenes-compra/", "id_orden_compra",
                  _build_orden_compra, {"estado": "APROBADA"}, "estado"),
    IsolationCase("proveedores.Proveedor", "/api/proveedores/proveedores/", "id_proveedor",
                  _build_proveedor, {"razon_social": "Hackeado"}, "razon_social"),
    IsolationCase("gastos.CategoriaGasto", "/api/gastos/categorias-gasto/", "id_categoria_gasto",
                  _build_categoria_gasto, {"nombre_categoria": "Hackeado"}, "nombre_categoria"),
    IsolationCase("nomina.PeriodoNomina", "/api/nomina/periodos-nomina/", "id_periodo_nomina",
                  _build_periodo_nomina, {"estado": "CERRADO"}, "estado"),
    IsolationCase("auditoria.LogAuditoria", "/api/auditoria/logs-auditoria/", "id_log_auditoria",
                  _build_log_auditoria, {"descripcion_accion": "Hackeado"}, "descripcion_accion",
                  writable=False),
]


@pytest.fixture
def env(moneda_usd, metodo_efectivo):
    """Dependencias compartidas que algunos modelos necesitan al construirse."""
    return SimpleNamespace(moneda=moneda_usd, metodo_pago=metodo_efectivo)


def _resultados(data):
    return data["results"] if isinstance(data, dict) and "results" in data else data


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_list_y_retrieve_aislados(case, user_a, empresa_a, empresa_b, env):
    """A lista/recupera: ve lo propio, jamás lo de B; GET de objeto ajeno → 404."""
    obj_a = case.build(empresa_a, "A", env)
    obj_b = case.build(empresa_b, "B", env)

    client = APIClient()
    client.force_authenticate(user=user_a)

    resp = client.get(case.url)
    assert resp.status_code == 200, f"{case.id}: list devolvió {resp.status_code}"
    ids = {str(r[case.pk_attr]) for r in _resultados(resp.data)}
    assert str(getattr(obj_a, case.pk_attr)) in ids, (
        f"{case.id}: el objeto propio de Empresa A no aparece en su listado."
    )
    assert str(getattr(obj_b, case.pk_attr)) not in ids, (
        f"{case.id}: LEAK — objeto de Empresa B visible en el listado de Empresa A."
    )

    pk_b = getattr(obj_b, case.pk_attr)
    resp = client.get(f"{case.url}{pk_b}/")
    assert resp.status_code == 404, (
        f"{case.id}: LEAK — GET de objeto de Empresa B devolvió {resp.status_code}, esperado 404."
    )


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_escritura_cross_tenant_bloqueada(case, user_a, empresa_a, empresa_b, env):
    """A no puede modificar (PATCH) ni borrar (DELETE) un objeto de B."""
    if not case.writable:
        pytest.skip(f"{case.id}: ViewSet de solo lectura; cubierto por list/retrieve.")
    obj_b = case.build(empresa_b, "B", env)
    pk_b = getattr(obj_b, case.pk_attr)
    valor_original = getattr(obj_b, case.unchanged_attr)

    client = APIClient()
    client.force_authenticate(user=user_a)

    # PATCH → 404, sin mutación.
    resp = client.patch(f"{case.url}{pk_b}/", case.patch_payload, format="json")
    assert resp.status_code == 404, (
        f"{case.id}: LEAK — PATCH de objeto de Empresa B devolvió {resp.status_code}, esperado 404."
    )
    obj_b.refresh_from_db()
    assert getattr(obj_b, case.unchanged_attr) == valor_original, (
        f"{case.id}: CRÍTICO — '{case.unchanged_attr}' de Empresa B fue modificado desde Empresa A."
    )

    # DELETE → nunca 2xx, y el objeto sobrevive.
    resp = client.delete(f"{case.url}{pk_b}/")
    assert resp.status_code not in (200, 202, 204), (
        f"{case.id}: LEAK — DELETE de objeto de Empresa B devolvió {resp.status_code} (borrado cross-tenant)."
    )
    assert type(obj_b).objects.filter(pk=pk_b).exists(), (
        f"{case.id}: CRÍTICO — objeto de Empresa B fue eliminado desde Empresa A."
    )
